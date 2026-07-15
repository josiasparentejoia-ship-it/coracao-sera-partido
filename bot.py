import asyncio
import json
import logging
from io import BytesIO

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, WebAppInfo
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

from config import (
    BOT_TOKEN, CHANNEL_ID, ADMIN_ID, MINI_APP_URL, SUPPORT_LINK, TIKTOK_LINK,
    TELEGRAM_API_BASE_URL, TELEGRAM_API_BASE_FILE_URL, FILMES
)
from database import (
    init_db, get_progresso, set_progresso, registrar_acesso, ja_tem_acesso,
    get_painel_canal, set_painel_canal, set_painel_message_id,
    marcar_intro_vista, ja_viu_intro,
    registrar_link_gerado, marcar_link_usado, listar_links_gerados, contar_links_ativos,
    listar_usuarios_sem_acesso, contar_usuarios_sem_acesso,
    adicionar_filme, listar_filmes_ativos, obter_filme_por_slug,
    definir_filme_principal, remover_filme, contar_filmes_ativos,
    listar_todos_usuarios, contar_todos_usuarios
)
from horsepay_payments import start_pix_if_needed, polling_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# TECLADOS
# ──────────────────────────────────────────────────────────

# Removido kb_principal - não é mais usado
# Usuários usam apenas o mini app
# Admin usa kb_admin()

def kb_valores():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("R$ 5,00",  callback_data="valor_500"),
            InlineKeyboardButton("R$ 10,00", callback_data="valor_1000"),
        ],
        [
            InlineKeyboardButton("R$ 15,00", callback_data="valor_1500"),
            InlineKeyboardButton("R$ 20,00", callback_data="valor_2000"),
        ],
        [InlineKeyboardButton("💰 Outro valor", callback_data="valor_outro")],
        [InlineKeyboardButton("◀️ Voltar",       callback_data="menu_principal")],
    ])

def kb_voltar():
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Voltar", callback_data="menu_principal")]])


# ──────────────────────────────────────────────────────────
# NOTIFICAÇÕES PARA O ADMIN
# ──────────────────────────────────────────────────────────

def _identificacao(user) -> str:
    username = f"@{user.username}" if user.username else "sem username"
    return f"{user.first_name or '—'} ({username}, `{user.id}`)"


async def _gerar_catalogo_json():
    """Gera arquivo JSON com o catálogo de filmes para o mini app consumir"""
    filmes = listar_filmes_ativos()
    catalogo = []

    for filme_data in filmes:
        filme_id, nome, slug, descricao, poster_path, video_path, canal_id, principal = filme_data
        catalogo.append({
            "id": filme_id,
            "nome": nome,
            "slug": slug,
            "descricao": descricao,
            "poster": poster_path,
            "video": video_path,
            "principal": principal == 1
        })

    # Salvar JSON na pasta raiz
    import json
    with open("catalogo.json", "w", encoding="utf-8") as f:
        json.dump({"filmes": catalogo}, f, ensure_ascii=False, indent=2)


async def _notificar_admin(context: ContextTypes.DEFAULT_TYPE, texto: str):
    try:
        await context.bot.send_message(ADMIN_ID, texto, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Erro ao notificar admin: {e}")


# ──────────────────────────────────────────────────────────
# CONTROLE DE MENUS (fecha o menu anterior ao abrir um novo,
# para não poluir a conversa — não se aplica às mensagens
# enviadas após a confirmação de pagamento)
# ──────────────────────────────────────────────────────────

async def _fechar_menu_anterior(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    old_id = context.user_data.pop("menu_msg_id", None)
    if old_id:
        try:
            await context.bot.delete_message(chat_id, old_id)
        except Exception:
            pass


async def _abrir_menu(context: ContextTypes.DEFAULT_TYPE, chat_id: int, texto: str, reply_markup=None):
    await _fechar_menu_anterior(context, chat_id)
    m = await context.bot.send_message(chat_id, texto, parse_mode="Markdown", reply_markup=reply_markup)
    context.user_data["menu_msg_id"] = m.message_id
    return m


_TEXTO_AGRADECIMENTO_DUBLAGEM = (
    "❤️ *Obrigado por apoiar nosso projeto!*\n\n"
    "Estamos trabalhando na dublagem profissional da *Parte 1* de Seu Coração Será Partido, "
    "e a *Parte 2* do filme está prevista para chegar no início de 2027.\n\n"
    "Você pode contribuir com qualquer valor a partir de *R$ 5,00* para ajudar a custear todo "
    "o processo de dublagem profissional.\n\n"
    "🙏 Agradecemos de coração a todos que ajudam esse projeto a se tornar realidade!\n\n"
    "Escolha o valor da sua contribuição:"
)


# ──────────────────────────────────────────────────────────
# /start
# ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id  = update.effective_user.id
    chat_id  = update.effective_chat.id
    is_admin = user_id == ADMIN_ID

    if not is_admin:
        await _notificar_admin(context, f"🚀 *Novo /start:* {_identificacao(update.effective_user)}")

    # Gerar JSON do catálogo para o mini app consumir
    await _gerar_catalogo_json()

    # Deep linking - verificar se tem filme específico no parâmetro
    filme_slug = None
    if context.args and len(context.args) > 0:
        param = context.args[0]
        # Se for "apoiar_dublagem", tratar especialmente
        if param == "apoiar_dublagem":
            marcar_intro_vista(user_id)
            await _abrir_menu(context, chat_id, _TEXTO_AGRADECIMENTO_DUBLAGEM, kb_valores())
            return
        # Senão, assume que é slug de filme
        filme_slug = param

    marcar_intro_vista(user_id)

    # ═══════════════════════════════════════════════════════════
    # ADMIN: Mostrar menu inline (sem mini app)
    # ═══════════════════════════════════════════════════════════
    if is_admin:
        await _abrir_menu(
            context, chat_id,
            "⚙️ *Painel Admin*\n\nEscolha uma opção:",
            kb_admin()
        )
        return

    # ═══════════════════════════════════════════════════════════
    # USUÁRIOS: SEMPRE mostrar botão do mini app
    # ═══════════════════════════════════════════════════════════
    total_filmes = contar_filmes_ativos()

    if total_filmes == 0:
        await update.message.reply_text(
            "❌ *Catálogo vazio*\n\n"
            "Ainda não há filmes disponíveis. Volte em breve! 🎬",
            parse_mode="Markdown"
        )
        return

    # Construir URL do mini app com filme em destaque (se houver)
    mini_app_url = MINI_APP_URL
    if filme_slug:
        mini_app_url = f"{MINI_APP_URL}?filme={filme_slug}"

    # Botão SEMPRE aparece (não é one_time)
    kb = ReplyKeyboardMarkup(
        [[KeyboardButton("🎬 ABRIR CATÁLOGO ILOVEDRAMAX", web_app=WebAppInfo(url=mini_app_url))]],
        resize_keyboard=True,
        one_time_keyboard=False  # NÃO desaparece após clicar
    )

    # Mensagem de boas-vindas
    mensagem = "🎬 *Bem-vindo ao IloveDramax!*\n\n"

    if filme_slug:
        filme = obter_filme_por_slug(filme_slug)
        if filme:
            mensagem += f"✨ *Filme em destaque:* {filme['nome']}\n\n"

    mensagem += (
        f"📱 Temos *{total_filmes} filme(s)* disponíveis para você assistir *gratuitamente*!\n\n"
        f"👇 *Clique no botão abaixo para explorar o catálogo:*"
    )

    await update.message.reply_text(
        mensagem,
        parse_mode="Markdown",
        reply_markup=kb
    )


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_admin = update.effective_user.id == ADMIN_ID
    await _abrir_menu(
        context, update.effective_chat.id,
        "❤️ *Projeto: Seu Coração Será Partido*\n\nEscolha uma opção abaixo:",
        kb_principal(is_admin)
    )


# ──────────────────────────────────────────────────────────
# MINI APP → recebe dado quando usuário clica "Assistir ao Filme"
# ──────────────────────────────────────────────────────────

async def handler_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.effective_message.web_app_data.data
    user = update.effective_user
    user_id = user.id
    chat_id = update.effective_chat.id

    # O data agora é o slug do filme escolhido (ex: "coracao_partido")
    filme_slug = data

    # Buscar informações do filme no banco
    filme = obter_filme_por_slug(filme_slug)

    if not filme:
        await context.bot.send_message(
            chat_id,
            "❌ Filme não encontrado.\n\n"
            "Tente novamente ou contate o suporte:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Suporte", url=SUPPORT_LINK)]])
        )
        return

    # Gerar link único para o canal deste filme
    try:
        invite = await context.bot.create_chat_invite_link(
            chat_id=filme["canal_id"],
            member_limit=1,
            name=f"user_{user_id}_{filme_slug}"
        )

        # Registrar link gerado
        registrar_link_gerado(f"user_{user_id}_{filme_slug}", invite.invite_link)

        # Registrar acesso gratuito
        registrar_acesso(user_id, 0.0)

        # Notificar admin
        await _notificar_admin(
            context,
            f"🎬 *Novo acesso:* {_identificacao(user)}\n"
            f"Filme: *{filme['nome']}*"
        )

        # Botão do mini app (sempre disponível)
        kb_miniapp = ReplyKeyboardMarkup(
            [[KeyboardButton("🎬 ABRIR CATÁLOGO ILOVEDRAMAX", web_app=WebAppInfo(url=MINI_APP_URL))]],
            resize_keyboard=True,
            one_time_keyboard=False
        )

        # Enviar link para o usuário COM o botão do mini app
        await context.bot.send_message(
            chat_id,
            f"🎬 *{filme['nome']}*\n\n"
            f"✅ Seu acesso foi liberado!\n\n"
            f"Clique no link abaixo para entrar no canal exclusivo e assistir:\n\n"
            f"👉 {invite.invite_link}\n\n"
            f"⚠️ _Este link é de uso único — não compartilhe._\n\n"
            f"💡 *Quer assistir mais filmes?* Use o botão abaixo para voltar ao catálogo! 👇",
            parse_mode="Markdown",
            reply_markup=kb_miniapp
        )

    except Exception as e:
        logger.error(f"Erro ao criar invite link para filme {filme_slug}, user {user_id}: {e}")
        await context.bot.send_message(
            chat_id,
            f"❌ Erro ao gerar seu link de acesso para *{filme['nome']}*.\n\n"
            f"Contate o suporte:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Suporte", url=SUPPORT_LINK)]])
        )


# ──────────────────────────────────────────────────────────
# MENU PRINCIPAL (callback)
# ──────────────────────────────────────────────────────────

async def cb_menu_principal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    is_admin = update.effective_user.id == ADMIN_ID
    await _abrir_menu(
        context, q.message.chat_id,
        "❤️ *Projeto: Seu Coração Será Partido*\n\nEscolha uma opção abaixo:",
        kb_principal(is_admin)
    )


# ──────────────────────────────────────────────────────────
# APOIAR
# ──────────────────────────────────────────────────────────

async def cb_apoiar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    await _abrir_menu(
        context, q.message.chat_id,
        "❤️ *Apoie o Projeto!*\n\n"
        "O filme já é gratuito — seu acesso ao canal exclusivo é liberado automaticamente. 🎬\n\n"
        "Se quiser ajudar a custear a dublagem profissional, contribua com qualquer valor a "
        "partir de *R$ 5,00*:\n\n"
        "Escolha o valor da sua contribuição:",
        kb_valores()
    )


async def cb_escolher_valor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "valor_outro":
        context.user_data["aguardando_valor"] = True
        await _abrir_menu(
            context, q.message.chat_id,
            "💰 *Digite o valor que deseja contribuir:*\n\n"
            "_Mínimo R$ 5,00 — exemplo: `25` ou `30.50`_"
        )
        return

    mapa = {"valor_500": 5.0, "valor_1000": 10.0, "valor_1500": 15.0, "valor_2000": 20.0}
    valor = mapa.get(q.data)
    if valor:
        await _fechar_menu_anterior(context, q.message.chat_id)
        await _iniciar_pagamento(update, context, valor)


async def _iniciar_pagamento(update: Update, context: ContextTypes.DEFAULT_TYPE, valor: float):
    user    = update.effective_user
    user_id = user.id
    nome    = user.first_name or "Usuario"
    chat_id = update.effective_chat.id

    tinha_acesso_antes = ja_tem_acesso(user_id)

    await context.bot.send_message(chat_id, "⏳ Gerando seu QR Code PIX...")

    try:
        pix = start_pix_if_needed(
            user_id=user_id,
            payer_name=nome,
            amount_reais=valor,
            callback_url="https://placeholder.com/callback",
            ctx_for_delivery={"user_id": user_id}
        )
    except Exception as e:
        logger.error(f"Erro HorsePay user {user_id}: {e}")
        await context.bot.send_message(
            chat_id,
            "❌ Erro ao gerar PIX. Tente novamente ou contate o suporte.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Suporte", url=SUPPORT_LINK)]])
        )
        return

    msg_ids = []

    if pix.get("payment_img_bytes"):
        buf      = BytesIO(pix["payment_img_bytes"])
        buf.name = "qr.png"
        m = await context.bot.send_photo(
            chat_id,
            photo=buf,
            caption=(
                f"💳 *Pague R$ {valor:.2f} via PIX*\n\n"
                f"Escaneie o QR Code ou copie o código abaixo.\n\n"
                f"✅ Seu acesso ao canal será liberado *automaticamente* após o pagamento!"
            ),
            parse_mode="Markdown"
        )
        msg_ids.append(m.message_id)

    if pix.get("copy_past"):
        m = await context.bot.send_message(
            chat_id,
            f"📋 *Copia e Cola PIX:*\n`{pix['copy_past']}`",
            parse_mode="Markdown"
        )
        msg_ids.append(m.message_id)

    async def on_paid(_ctx):
        for mid in msg_ids:
            try:
                await context.bot.delete_message(chat_id, mid)
            except Exception:
                pass

        # Quem já tinha acesso está fazendo uma contribuição voluntária extra —
        # não precisa de novo link, só o agradecimento. Essas mensagens de
        # pós-pagamento nunca são fechadas/apagadas pelo controle de menus.
        if tinha_acesso_antes:
            registrar_acesso(user_id, valor)
            await _notificar_admin(
                context,
                f"💰 *Nova contribuição extra:* {_identificacao(user)}\nValor: R$ {valor:.2f}"
            )
            await context.bot.send_message(
                chat_id,
                f"❤️ *Muito obrigado pela sua contribuição voluntária de R$ {valor:.2f}!*\n\n"
                f"Sua doação ajuda a custear a dublagem profissional e a trazer a Parte 2 do "
                f"projeto mais perto da realidade.\n\n"
                f"🙏 Contamos com você para seguir essa jornada até o fim!",
                parse_mode="Markdown"
            )
            return

        await context.bot.send_message(chat_id, "✅ Pagamento confirmado! Liberando seu acesso...")
        await _notificar_admin(
            context,
            f"💰 *Nova compra (acesso liberado):* {_identificacao(user)}\nValor: R$ {valor:.2f}"
        )

        try:
            invite = await context.bot.create_chat_invite_link(
                chat_id=CHANNEL_ID,
                member_limit=1,
                name=f"user_{user_id}"
            )
            registrar_acesso(user_id, valor)
            await context.bot.send_message(
                chat_id,
                f"🎬 *Acesso Liberado!*\n\n"
                f"Obrigado pela sua contribuição de R$ {valor:.2f}! ❤️\n\n"
                f"Clique no link abaixo para entrar no canal exclusivo:\n\n"
                f"👉 {invite.invite_link}\n\n"
                f"⚠️ _Este link é de uso único — não compartilhe._",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Erro ao criar invite link para user {user_id}: {e}")
            await context.bot.send_message(
                chat_id,
                f"✅ Pagamento confirmado! Obrigado por contribuir com R$ {valor:.2f}! ❤️\n\n"
                f"Entre em contato com o suporte para receber seu link de acesso:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Suporte", url=SUPPORT_LINK)]])
            )

    asyncio.create_task(polling_loop(user_id, 10, on_paid))


# ──────────────────────────────────────────────────────────
# SOBRE O FILME
# ──────────────────────────────────────────────────────────

_SINOPSE = (
    "🎬 *Sinopse Oficial*\n\n"
    "Polina, uma estudante do ensino médio, é salva do bullying em sua nova escola e faz um acordo "
    "com o principal valentão, Bars: ele deve fingir ser seu namorado e protegê-la, e ela deve fazer "
    "tudo o que ele mandar. Durante esse jogo, o casal desenvolve sentimentos verdadeiros, mas sua "
    "família e colegas de classe têm motivos para separá-los."
)

_DETALHES = (
    "📖 *Mais Informações*\n\n"
    "Em *Seu Coração Será Partido*, somos apresentados a Polina Tumanova, uma estudante que, "
    "após se mudar para uma nova cidade, se vê alvo de bullying na nova escola. Para escapar, "
    "Polina faz um acordo inusitado com Bars, o valentão mais temido do colégio: ele fingirá ser "
    "seu namorado e a protegerá, enquanto ela se compromete a fazer tudo o que ele mandar.\n\n"
    "O que começa como um arranjo estratégico aos poucos se transforma em algo mais profundo e "
    "inesperado. Sentimentos reais surgem entre os dois, desafiando as regras impostas.\n\n"
    "*Contexto da Produção*\n"
    "Drama romântico russo adaptado do romance de Anna Jane. Direção de Mikhail Vaynberg. "
    "Elenco: Veronika Zhuravleva (Polina) e Daniel Vegas (Bars). "
    "Produção: All Media, Sverdlovskaya Kinostudiya e START.\n\n"
    "*Temas:* bullying, primeiro amor, relacionamentos adolescentes, superação.\n\n"
    "⭐ Baseado em best-seller russo, com grande base de fãs ansiosos pela adaptação."
)


async def cb_sobre_filme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await _fechar_menu_anterior(context, q.message.chat_id)
    await q.message.reply_text(_SINOPSE, parse_mode="Markdown")
    m = await q.message.reply_text(_DETALHES, parse_mode="Markdown", reply_markup=kb_voltar())
    context.user_data["menu_msg_id"] = m.message_id


# ──────────────────────────────────────────────────────────
# ANDAMENTO DO PROJETO
# ──────────────────────────────────────────────────────────

async def cb_andamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    prog  = get_progresso()
    texto = (
        f"📊 *Andamento do Projeto*\n\n"
        f"🎬 *Projeto:* Seu Coração Será Partido\n\n"
        f"📈 *Progresso Geral:* {prog.get('progresso', '0')}%\n"
        f"💰 *Valor arrecadado:* R$ {prog.get('valor_arrecadado', '0,00')}\n"
        f"🎯 *Próxima meta:* {prog.get('proxima_meta', 'A definir')}\n\n"
        f"📌 *Etapa atual:*\n{prog.get('etapa_atual', 'Planejamento inicial')}"
    )
    await _abrir_menu(context, q.message.chat_id, texto, kb_voltar())


# ──────────────────────────────────────────────────────────
# FALAR COM A EQUIPE
# ──────────────────────────────────────────────────────────

async def cb_falar_equipe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    texto = (
        "💬 *Falar com a Equipe*\n\n"
        "Nossa equipe está à disposição para tirar dúvidas, receber sugestões "
        "ou conversar sobre o projeto.\n\n"
        "Escolha uma das opções abaixo:"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Conversar pelo Telegram", url=SUPPORT_LINK)],
        [InlineKeyboardButton("🎵 TikTok — @ilovedoramaxx", url=TIKTOK_LINK)],
        [InlineKeyboardButton("◀️ Voltar",                  callback_data="menu_principal")],
    ])
    await _abrir_menu(context, q.message.chat_id, texto, kb)


# ──────────────────────────────────────────────────────────
# ADMIN
# ──────────────────────────────────────────────────────────

def kb_admin():
    usuarios_pendentes = contar_usuarios_sem_acesso()
    texto_pendentes = f"📨 Enviar Convites ({usuarios_pendentes})" if usuarios_pendentes > 0 else "📨 Enviar Convites"

    total_filmes = contar_filmes_ativos()
    texto_catalogo = f"🎬 Gerenciar Catálogo ({total_filmes})" if total_filmes > 0 else "🎬 Gerenciar Catálogo"

    total_usuarios = contar_todos_usuarios()
    texto_broadcast = f"📢 Enviar Mensagem para Todos ({total_usuarios})"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(texto_catalogo,                     callback_data="admin_catalogo")],
        [InlineKeyboardButton("📊 Atualizar Progresso",           callback_data="admin_editar_progresso")],
        [InlineKeyboardButton(texto_broadcast,                    callback_data="admin_broadcast")],
        [InlineKeyboardButton("📌 Publicar Botões no Canal",      callback_data="admin_painel_canal")],
        [InlineKeyboardButton("🔗 Publicar no Canal + Gerar Link", callback_data="admin_enviar_canal")],
        [InlineKeyboardButton("🎟️ Gerar Link Único de Acesso",    callback_data="admin_gerar_link")],
        [InlineKeyboardButton("📋 Ver Links Gerados",             callback_data="admin_ver_links")],
        [InlineKeyboardButton(texto_pendentes,                    callback_data="admin_enviar_convites")],
        [InlineKeyboardButton("◀️ Menu Principal",                callback_data="menu_principal")],
    ])


def _link_mensagem_canal(message_id: int) -> str:
    chat_id_str = str(CHANNEL_ID)
    internal_id = chat_id_str[4:] if chat_id_str.startswith("-100") else chat_id_str.lstrip("-")
    return f"https://t.me/c/{internal_id}/{message_id}"


async def _publicar_e_linkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("admin_modo", None)
    try:
        resultado = await context.bot.copy_message(
            chat_id=CHANNEL_ID,
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id
        )
        link = _link_mensagem_canal(resultado.message_id)
        await update.message.reply_text(
            f"✅ Publicado no canal!\n\n"
            f"🔗 *Link direto para essa mensagem:*\n`{link}`\n\n"
            f"Use esse link no lugar de uma URL normal ao criar botões no painel do canal "
            f"(ex: `Ver Vídeo | {link}`).",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Erro ao publicar/linkar mensagem no canal: {e}")
        await update.message.reply_text(f"❌ Erro ao publicar no canal: {e}")


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await _abrir_menu(context, update.effective_chat.id, "⚙️ *Painel Admin*", kb_admin())


async def cb_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await q.answer("Sem permissão.", show_alert=True)
        return
    await q.answer()
    await _abrir_menu(context, q.message.chat_id, "⚙️ *Painel Admin*", kb_admin())


async def cb_admin_editar_progresso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await q.answer("Sem permissão.", show_alert=True)
        return
    await q.answer()

    prog = get_progresso()
    context.user_data["admin_modo"] = "editar_progresso"

    await _abrir_menu(
        context, q.message.chat_id,
        "📊 *Editar Progresso do Projeto*\n\n"
        "Envie as informações no formato abaixo (envie só o que quiser alterar):\n\n"
        "`PROGRESSO: 30`\n"
        "`VALOR: 1.500,00`\n"
        "`META: Iniciar gravação das vozes`\n"
        "`ETAPA: 🎙️ Tradução do roteiro em andamento`\n\n"
        f"*Valores atuais:*\n"
        f"• Progresso: {prog.get('progresso', '0')}%\n"
        f"• Valor: R$ {prog.get('valor_arrecadado', '0,00')}\n"
        f"• Meta: {prog.get('proxima_meta', 'A definir')}\n"
        f"• Etapa: {prog.get('etapa_atual', 'Planejamento inicial')}"
    )


async def cb_admin_painel_canal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await q.answer("Sem permissão.", show_alert=True)
        return
    await q.answer()

    # Listar canais disponíveis (dos filmes cadastrados)
    filmes = listar_filmes_ativos()

    if not filmes:
        await q.message.reply_text("❌ Nenhum canal disponível. Adicione filmes primeiro!")
        return

    # Criar botões para cada canal
    botoes = []
    for filme_data in filmes:
        filme_id, nome, slug, descricao, poster_path, video_path, canal_id, principal = filme_data
        botoes.append([InlineKeyboardButton(
            f"📺 {nome}",
            callback_data=f"painel_canal_{canal_id}"
        )])

    botoes.append([InlineKeyboardButton("◀️ Voltar", callback_data="admin_menu")])

    await _abrir_menu(
        context, q.message.chat_id,
        "📌 *Publicar Mensagem com Botões no Canal*\n\n"
        "Escolha o canal onde deseja publicar:",
        InlineKeyboardMarkup(botoes)
    )


async def cb_painel_canal_escolhido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await q.answer("Sem permissão.", show_alert=True)
        return
    await q.answer()

    # Extrair canal_id do callback_data
    canal_id = int(q.data.split("_")[-1])

    # Buscar informações do filme/canal
    filmes = listar_filmes_ativos()
    filme_info = None
    for filme_data in filmes:
        if filme_data[6] == canal_id:  # filme_data[6] é o canal_id
            filme_info = {
                'id': filme_data[0],
                'nome': filme_data[1],
                'slug': filme_data[2],
                'canal_id': filme_data[6]
            }
            break

    if not filme_info:
        await q.message.reply_text("❌ Canal não encontrado!")
        return

    # Salvar informações do canal escolhido
    context.user_data["admin_modo"] = "painel_canal_mensagem"
    context.user_data["canal_escolhido"] = filme_info

    # Editar a mensagem existente ao invés de criar nova
    try:
        await q.message.edit_text(
            f"📌 *Publicar em: {filme_info['nome']}*\n\n"
            f"Envie a mensagem no seguinte formato:\n\n"
            f"*Exemplo:*\n"
            f"```\n"
            f"❤️ Bem-vindo ao canal oficial!\n"
            f"Assista ao filme completo em 4K!\n\n"
            f"BOTAO_GATEWAY: 🎬 Explorar Catálogo\n"
            f"LINK_FILME: https://t.me/c/1234567890/123\n"
            f"```\n\n"
            f"*Explicação:*\n"
            f"• Texto da mensagem (linhas normais)\n"
            f"• `BOTAO_GATEWAY:` texto do botão que abre o catálogo\n"
            f"• `LINK_FILME:` link da postagem do filme no canal\n\n"
            f"Os botões de Suporte e TikTok são adicionados automaticamente!",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Erro ao editar mensagem: {e}")
        await q.message.reply_text(
            f"📌 *Publicar em: {filme_info['nome']}*\n\n"
            f"Envie a mensagem no seguinte formato:\n\n"
            f"*Exemplo:*\n"
            f"```\n"
            f"❤️ Bem-vindo ao canal oficial!\n"
            f"Assista ao filme completo em 4K!\n\n"
            f"BOTAO_GATEWAY: 🎬 Explorar Catálogo\n"
            f"LINK_FILME: https://t.me/c/1234567890/123\n"
            f"```\n\n"
            f"*Explicação:*\n"
            f"• Texto da mensagem (linhas normais)\n"
            f"• `BOTAO_GATEWAY:` texto do botão que abre o catálogo\n"
            f"• `LINK_FILME:` link da postagem do filme no canal\n\n"
            f"Os botões de Suporte e TikTok são adicionados automaticamente!",
            parse_mode="Markdown"
        )


async def cb_admin_enviar_canal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await q.answer("Sem permissão.", show_alert=True)
        return
    await q.answer()

    context.user_data["admin_modo"] = "enviar_canal"

    await _abrir_menu(
        context, q.message.chat_id,
        "🔗 *Publicar no Canal e Gerar Link*\n\n"
        "Me envie agora o que você quer publicar no canal: texto, foto, vídeo, documento, "
        "o que for.\n\n"
        "Vou publicar exatamente como você enviou e te devolver o link direto para essa "
        "mensagem, que ficou lá em cima na conversa. Você pode usar esse link em qualquer "
        "botão do painel do canal."
    )


async def cb_admin_gerar_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await q.answer("Sem permissão.", show_alert=True)
        return
    await q.answer()

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎟️ Link Simples (uso único)", callback_data="gerar_link_simples")],
        [InlineKeyboardButton("✏️ Link Personalizado", callback_data="gerar_link_personalizado")],
        [InlineKeyboardButton("◀️ Voltar", callback_data="admin_menu")],
    ])

    await _abrir_menu(
        context, q.message.chat_id,
        "🎟️ *Gerar Link Único de Acesso ao Canal*\n\n"
        "*Link Simples:* Gera um link de uso único imediatamente.\n\n"
        "*Link Personalizado:* Permite adicionar um nome/descrição ao link para "
        "identificar depois quem usou (ex: `influencer_joao`, `parceiro_maria`).\n\n"
        "Escolha uma opção:",
        kb
    )


async def cb_gerar_link_simples(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await q.answer("Sem permissão.", show_alert=True)
        return
    await q.answer("Gerando link...")

    try:
        import time
        timestamp = int(time.time())
        nome_link = f"admin_manual_{timestamp}"
        invite = await context.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            name=nome_link
        )

        # Registrar no banco de dados
        registrar_link_gerado(nome_link, invite.invite_link)

        await _abrir_menu(
            context, q.message.chat_id,
            f"✅ *Link gerado com sucesso!*\n\n"
            f"🔗 Link de acesso único:\n`{invite.invite_link}`\n\n"
            f"⚠️ *Este link pode ser usado apenas 1 vez*\n\n"
            f"📋 Você pode copiar e enviar para quem quiser. Quando a pessoa usar, "
            f"o acesso será liberado automaticamente.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Voltar ao Admin", callback_data="admin_menu")
            ]])
        )
    except Exception as e:
        logger.error(f"Erro ao gerar link de convite: {e}")
        await q.message.reply_text(f"❌ Erro ao gerar link: {e}")


async def cb_gerar_link_personalizado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await q.answer("Sem permissão.", show_alert=True)
        return
    await q.answer()

    context.user_data["admin_modo"] = "gerar_link_personalizado"

    await _abrir_menu(
        context, q.message.chat_id,
        "✏️ *Gerar Link Personalizado*\n\n"
        "Envie agora o *nome/descrição* para identificar este link.\n\n"
        "*Exemplos:*\n"
        "`influencer_joao`\n"
        "`parceiro_maria_tiktok`\n"
        "`sorteio_instagram`\n"
        "`presente_amigo`\n\n"
        "⚠️ Use apenas letras, números e _ (sem espaços)",
        parse_mode="Markdown"
    )


async def cb_admin_ver_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await q.answer("Sem permissão.", show_alert=True)
        return
    await q.answer()

    try:
        links = listar_links_gerados(limite=10)
        ativos = contar_links_ativos()

        if not links:
            texto = "📋 *Links Gerados*\n\n❌ Nenhum link foi gerado ainda."
        else:
            from datetime import datetime
            texto = f"📋 *Últimos Links Gerados*\n\n🎟️ *Links ativos:* {ativos}\n\n"

            for link_data in links:
                link_id, nome, link_url, data_criacao, usado, user_id_uso, data_uso = link_data
                data_str = datetime.fromtimestamp(data_criacao).strftime("%d/%m/%Y %H:%M")

                status = "✅ Usado" if usado else "⏳ Disponível"
                if usado and data_uso:
                    data_uso_str = datetime.fromtimestamp(data_uso).strftime("%d/%m/%Y %H:%M")
                    user_info = f" por `{user_id_uso}`" if user_id_uso else ""
                    status_completo = f"{status} em {data_uso_str}{user_info}"
                else:
                    status_completo = status

                texto += f"━━━━━━━━━━━━\n"
                texto += f"*#{link_id}* — `{nome}`\n"
                texto += f"📅 Criado: {data_str}\n"
                texto += f"📊 Status: {status_completo}\n"

            texto += "\n━━━━━━━━━━━━\n_Mostrando os 10 links mais recentes_"

        await _abrir_menu(
            context, q.message.chat_id,
            texto,
            InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Atualizar", callback_data="admin_ver_links"),
                InlineKeyboardButton("◀️ Voltar", callback_data="admin_menu")
            ]])
        )
    except Exception as e:
        logger.error(f"Erro ao listar links: {e}")
        await q.message.reply_text(f"❌ Erro ao listar links: {e}")


async def cb_admin_enviar_convites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await q.answer("Sem permissão.", show_alert=True)
        return
    await q.answer()

    try:
        usuarios_sem_acesso = listar_usuarios_sem_acesso()
        total = len(usuarios_sem_acesso)

        if total == 0:
            await _abrir_menu(
                context, q.message.chat_id,
                "📨 *Enviar Convites em Massa*\n\n"
                "✅ Não há usuários pendentes!\n\n"
                "Todos que deram /start já têm acesso ao canal.",
                InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Voltar", callback_data="admin_menu")
                ]])
            )
            return

        # Mostrar preview dos primeiros 5 usuários
        from datetime import datetime
        preview = ""
        for i, (user_id, data_vis) in enumerate(usuarios_sem_acesso[:5]):
            data_str = datetime.fromtimestamp(data_vis).strftime("%d/%m/%Y %H:%M")
            preview += f"• User ID: `{user_id}` (start em {data_str})\n"

        if total > 5:
            preview += f"• ... e mais {total - 5} usuários\n"

        texto = (
            f"📨 *Enviar Convites em Massa*\n\n"
            f"📊 *Total de usuários sem acesso:* {total}\n\n"
            f"*Prévia dos usuários:*\n{preview}\n\n"
            f"🎬 *Mensagem que será enviada:*\n"
            f"_\"🎬 Olá! Notamos que você visitou nosso bot mas ainda não assistiu ao filme.\n\n"
            f"O filme 'Seu Coração Será Partido' está disponível GRATUITAMENTE! ❤️\n\n"
            f"Clique no link abaixo para entrar no canal exclusivo e assistir agora em 4K com legendas:\n\n"
            f"[Link exclusivo único para você]\n\n"
            f"⚠️ Este é um link de uso único. Não compartilhe!\"_\n\n"
            f"⚠️ *Esta ação vai:*\n"
            f"• Gerar {total} links únicos\n"
            f"• Enviar uma mensagem para cada usuário\n"
            f"• Registrar cada link no banco de dados\n\n"
            f"🕐 Tempo estimado: ~{total * 2} segundos\n\n"
            f"Deseja continuar?"
        )

        await _abrir_menu(
            context, q.message.chat_id,
            texto,
            InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Sim, Enviar Agora", callback_data="confirmar_envio_convites")],
                [InlineKeyboardButton("◀️ Cancelar", callback_data="admin_menu")],
            ])
        )
    except Exception as e:
        logger.error(f"Erro ao preparar envio de convites: {e}")
        await q.message.reply_text(f"❌ Erro: {e}")


async def cb_admin_catalogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await q.answer("Sem permissão.", show_alert=True)
        return
    await q.answer()

    total_filmes = contar_filmes_ativos()
    filmes = listar_filmes_ativos()

    texto = f"🎬 *Gerenciar Catálogo de Filmes*\n\n"
    texto += f"📊 *Total de filmes:* {total_filmes}\n\n"

    if total_filmes > 0:
        texto += "*Filmes no catálogo:*\n"
        for filme_data in filmes:
            filme_id, nome, slug, descricao, poster_path, video_path, canal_id, principal = filme_data
            destaque = " ⭐ Principal" if principal else ""
            texto += f"\n• *{nome}*{destaque}\n"
            texto += f"  Slug: `{slug}`\n"
            texto += f"  Canal ID: `{canal_id}`\n"
    else:
        texto += "❌ Nenhum filme no catálogo ainda."

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Adicionar Filme", callback_data="admin_add_filme")],
        [InlineKeyboardButton("◀️ Voltar", callback_data="admin_menu")],
    ])

    await _abrir_menu(context, q.message.chat_id, texto, kb)


async def cb_admin_add_filme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await q.answer("Sem permissão.", show_alert=True)
        return
    await q.answer()

    context.user_data["admin_modo"] = "add_filme_nome"

    await _abrir_menu(
        context, q.message.chat_id,
        "➕ *Adicionar Filme ao Catálogo*\n\n"
        "*Passo 1 de 5: Nome do Filme*\n\n"
        "Digite o nome completo do filme:\n\n"
        "*Exemplo:* `Seu Coração Será Partido`"
    )


async def cb_confirmar_envio_convites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await q.answer("Sem permissão.", show_alert=True)
        return
    await q.answer("Iniciando envio...")

    try:
        usuarios_sem_acesso = listar_usuarios_sem_acesso()
        total = len(usuarios_sem_acesso)

        if total == 0:
            await q.message.reply_text("❌ Não há usuários para enviar convites.")
            return

        # Enviar mensagem de progresso
        msg_progresso = await context.bot.send_message(
            q.message.chat_id,
            f"📨 *Enviando convites...*\n\n"
            f"⏳ Processando 0/{total} usuários...",
            parse_mode="Markdown"
        )

        enviados = 0
        erros = 0
        usuarios_com_erro = []

        for i, (user_id, data_vis) in enumerate(usuarios_sem_acesso):
            try:
                # Gerar link único para este usuário
                nome_link = f"convite_massa_{user_id}"
                invite = await context.bot.create_chat_invite_link(
                    chat_id=CHANNEL_ID,
                    member_limit=1,
                    name=nome_link
                )

                # Registrar no banco de dados
                registrar_link_gerado(nome_link, invite.invite_link)

                # Enviar mensagem para o usuário
                mensagem = (
                    f"🎬 *Olá!*\n\n"
                    f"Notamos que você visitou nosso bot mas ainda não assistiu ao filme.\n\n"
                    f"O filme *'Seu Coração Será Partido'* está disponível *GRATUITAMENTE*! ❤️\n\n"
                    f"Clique no link abaixo para entrar no canal exclusivo e assistir agora em 4K com legendas:\n\n"
                    f"👉 {invite.invite_link}\n\n"
                    f"⚠️ _Este é um link de uso único e exclusivo para você. Não compartilhe!_\n\n"
                    f"🎥 Aproveite o filme!"
                )

                await context.bot.send_message(
                    user_id,
                    mensagem,
                    parse_mode="Markdown"
                )

                # Registrar acesso gratuito no banco
                registrar_acesso(user_id, 0.0)

                enviados += 1

                # Atualizar progresso a cada 5 usuários ou no último
                if (i + 1) % 5 == 0 or (i + 1) == total:
                    await context.bot.edit_message_text(
                        f"📨 *Enviando convites...*\n\n"
                        f"⏳ Processando {i + 1}/{total} usuários...\n"
                        f"✅ Enviados: {enviados}\n"
                        f"❌ Erros: {erros}",
                        chat_id=q.message.chat_id,
                        message_id=msg_progresso.message_id,
                        parse_mode="Markdown"
                    )

                # Delay para evitar rate limit do Telegram
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Erro ao enviar convite para user {user_id}: {e}")
                erros += 1
                usuarios_com_erro.append((user_id, str(e)))

        # Mensagem final
        texto_final = (
            f"✅ *Envio Concluído!*\n\n"
            f"📊 *Resultados:*\n"
            f"• Total processado: {total}\n"
            f"• ✅ Enviados com sucesso: {enviados}\n"
            f"• ❌ Erros: {erros}\n"
        )

        if usuarios_com_erro and len(usuarios_com_erro) <= 10:
            texto_final += f"\n*Usuários com erro:*\n"
            for user_id, erro in usuarios_com_erro:
                # Pegar só o tipo do erro para não ficar muito grande
                erro_resumo = erro.split(':')[0][:30]
                texto_final += f"• `{user_id}`: {erro_resumo}\n"

        await context.bot.edit_message_text(
            texto_final,
            chat_id=q.message.chat_id,
            message_id=msg_progresso.message_id,
            parse_mode="Markdown"
        )

        # Notificar admin sobre o resultado
        await _notificar_admin(
            context,
            f"📨 *Envio em massa concluído*\n\n"
            f"✅ Enviados: {enviados}\n"
            f"❌ Erros: {erros}"
        )

    except Exception as e:
        logger.error(f"Erro geral ao enviar convites: {e}")
        await q.message.reply_text(f"❌ Erro ao enviar convites: {e}")


async def cb_admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await q.answer("Sem permissão.", show_alert=True)
        return
    await q.answer()

    total_usuarios = contar_todos_usuarios()

    context.user_data["admin_modo"] = "broadcast_mensagem"

    await _abrir_menu(
        context, q.message.chat_id,
        f"📢 *Enviar Mensagem para Todos os Usuários*\n\n"
        f"📊 *Total de usuários:* {total_usuarios}\n\n"
        f"Digite agora a mensagem que deseja enviar para todos.\n\n"
        f"A mensagem será enviada com um botão que abre o mini app.\n\n"
        f"💡 *Dica:* Use Markdown para formatação:\n"
        f"• `*negrito*` para *negrito*\n"
        f"• `_itálico_` para _itálico_\n"
        f"• `` `código` `` para `código`\n\n"
        f"⚠️ *Atenção:* Esta ação enviará a mensagem para TODOS os {total_usuarios} usuários!",
        parse_mode="Markdown"
    )


async def cb_confirmar_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await q.answer("Sem permissão.", show_alert=True)
        return
    await q.answer("Iniciando envio em massa...")

    try:
        mensagem = context.user_data.get("broadcast_mensagem", "")
        if not mensagem:
            await q.message.reply_text("❌ Erro: Mensagem não encontrada.")
            return

        usuarios = listar_todos_usuarios()
        total = len(usuarios)

        if total == 0:
            await q.message.reply_text("❌ Não há usuários para enviar.")
            return

        # Criar botão do mini app
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 ABRIR CATÁLOGO ILOVEDRAMAX", web_app=WebAppInfo(url=MINI_APP_URL))]
        ])

        # Mensagem de progresso
        msg_progresso = await context.bot.send_message(
            q.message.chat_id,
            f"📢 *Enviando mensagem em massa...*\n\n"
            f"⏳ Processando 0/{total} usuários...",
            parse_mode="Markdown"
        )

        enviados = 0
        erros = 0
        usuarios_com_erro = []

        for i, user_id in enumerate(usuarios):
            try:
                # Enviar mensagem com botão do mini app
                await context.bot.send_message(
                    user_id,
                    mensagem,
                    parse_mode="Markdown",
                    reply_markup=kb
                )

                enviados += 1

                # Atualizar progresso a cada 5 usuários ou no último
                if (i + 1) % 5 == 0 or (i + 1) == total:
                    await context.bot.edit_message_text(
                        f"📢 *Enviando mensagem em massa...*\n\n"
                        f"⏳ Processando {i + 1}/{total} usuários...\n"
                        f"✅ Enviados: {enviados}\n"
                        f"❌ Erros: {erros}",
                        chat_id=q.message.chat_id,
                        message_id=msg_progresso.message_id,
                        parse_mode="Markdown"
                    )

                # Delay para evitar rate limit
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Erro ao enviar broadcast para user {user_id}: {e}")
                erros += 1
                usuarios_com_erro.append((user_id, str(e)))

        # Mensagem final
        texto_final = (
            f"✅ *Envio em Massa Concluído!*\n\n"
            f"📊 *Resultados:*\n"
            f"• Total processado: {total}\n"
            f"• ✅ Enviados com sucesso: {enviados}\n"
            f"• ❌ Erros: {erros}\n"
        )

        if usuarios_com_erro and len(usuarios_com_erro) <= 10:
            texto_final += f"\n*Usuários com erro:*\n"
            for user_id, erro in usuarios_com_erro:
                erro_resumo = erro.split(':')[0][:30]
                texto_final += f"• `{user_id}`: {erro_resumo}\n"

        await context.bot.edit_message_text(
            texto_final,
            chat_id=q.message.chat_id,
            message_id=msg_progresso.message_id,
            parse_mode="Markdown"
        )

        # Limpar dados temporários
        context.user_data.pop("broadcast_mensagem", None)
        context.user_data.pop("admin_modo", None)

    except Exception as e:
        logger.error(f"Erro geral ao enviar broadcast: {e}")
        await q.message.reply_text(f"❌ Erro ao enviar broadcast: {e}")


def _parse_painel(texto_bruto: str):
    if "BOTOES:" in texto_bruto:
        texto, _, bloco = texto_bruto.partition("BOTOES:")
        texto = texto.strip()
        botoes = []
        for linha in bloco.strip().splitlines():
            if "|" in linha:
                label, _, alvo = linha.partition("|")
                label = label.strip()
                alvo = alvo.strip()
                if label and alvo:
                    botoes.append([label, alvo])
        return texto, botoes
    return texto_bruto.strip(), []


def _kb_from_botoes(botoes, bot_username: str):
    if not botoes:
        return None
    linhas = []
    for label, alvo in botoes:
        if alvo.strip().upper() == "APOIAR":
            linhas.append([InlineKeyboardButton(
                label, url=f"https://t.me/{bot_username}?start=apoiar_dublagem"
            )])
        else:
            linhas.append([InlineKeyboardButton(label, url=alvo)])
    return InlineKeyboardMarkup(linhas)


# ──────────────────────────────────────────────────────────
# HANDLER DE TEXTO (valor customizado + input admin)
# ──────────────────────────────────────────────────────────

async def handler_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Admin enviando mensagem de broadcast
    if user_id == ADMIN_ID and context.user_data.get("admin_modo") == "broadcast_mensagem":
        context.user_data.pop("admin_modo", None)
        mensagem = update.message.text.strip()

        if len(mensagem) < 10:
            await update.message.reply_text("❌ Mensagem muito curta. Digite uma mensagem com pelo menos 10 caracteres.")
            return

        # Salvar mensagem temporariamente
        context.user_data["broadcast_mensagem"] = mensagem

        total_usuarios = contar_todos_usuarios()

        # Mostrar preview da mensagem e pedir confirmação
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Sim, Enviar Agora", callback_data="confirmar_broadcast")],
            [InlineKeyboardButton("◀️ Cancelar", callback_data="admin_menu")],
        ])

        # Criar preview com o botão do mini app
        kb_preview = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 ABRIR CATÁLOGO ILOVEDRAMAX", web_app=WebAppInfo(url=MINI_APP_URL))]
        ])

        await update.message.reply_text(
            f"📢 *Preview da Mensagem de Broadcast*\n\n"
            f"👥 Será enviada para: *{total_usuarios} usuários*\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n",
            parse_mode="Markdown"
        )

        await update.message.reply_text(
            mensagem,
            parse_mode="Markdown",
            reply_markup=kb_preview
        )

        await update.message.reply_text(
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⚠️ *Atenção:*\n"
            f"Esta ação enviará a mensagem acima para *{total_usuarios} usuários*!\n\n"
            f"🕐 Tempo estimado: ~{total_usuarios * 0.5:.0f} segundos\n\n"
            f"Deseja continuar?",
            parse_mode="Markdown",
            reply_markup=kb
        )
        return

    # Admin editando progresso
    if user_id == ADMIN_ID and context.user_data.get("admin_modo") == "editar_progresso":
        context.user_data.pop("admin_modo", None)
        updates = {}
        for linha in update.message.text.splitlines():
            if ":" in linha:
                chave, _, valor = linha.partition(":")
                chave = chave.strip().upper()
                valor = valor.strip()
                if chave == "PROGRESSO":
                    updates["progresso"] = valor.replace("%", "").strip()
                elif chave == "VALOR":
                    updates["valor_arrecadado"] = valor
                elif chave == "META":
                    updates["proxima_meta"] = valor
                elif chave == "ETAPA":
                    updates["etapa_atual"] = valor
        for k, v in updates.items():
            set_progresso(k, v)
        resp = f"✅ {len(updates)} campo(s) atualizado(s)!" if updates else "⚠️ Nenhum campo reconhecido."
        await update.message.reply_text(resp)
        return

    # Admin gerando link personalizado
    if user_id == ADMIN_ID and context.user_data.get("admin_modo") == "gerar_link_personalizado":
        context.user_data.pop("admin_modo", None)
        nome_link = update.message.text.strip()

        # Validação do nome
        import re
        if not re.match(r'^[a-zA-Z0-9_]+$', nome_link):
            await update.message.reply_text(
                "❌ Nome inválido! Use apenas letras, números e _ (sem espaços).\n\n"
                "Tente novamente:",
                parse_mode="Markdown"
            )
            context.user_data["admin_modo"] = "gerar_link_personalizado"
            return

        try:
            invite = await context.bot.create_chat_invite_link(
                chat_id=CHANNEL_ID,
                member_limit=1,
                name=nome_link
            )

            # Registrar no banco de dados
            registrar_link_gerado(nome_link, invite.invite_link)

            await update.message.reply_text(
                f"✅ *Link gerado com sucesso!*\n\n"
                f"📝 Nome: `{nome_link}`\n"
                f"🔗 Link: `{invite.invite_link}`\n\n"
                f"⚠️ *Este link pode ser usado apenas 1 vez*\n\n"
                f"📋 Quando alguém usar este link, você poderá identificar pela notificação que "
                f"vai aparecer com o nome `{nome_link}`.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Voltar ao Admin", callback_data="admin_menu")
                ]])
            )
        except Exception as e:
            logger.error(f"Erro ao gerar link personalizado '{nome_link}': {e}")
            await update.message.reply_text(f"❌ Erro ao gerar link: {e}")
        return

    # Admin publicando painel de botões no canal (novo formato com canal escolhido)
    if user_id == ADMIN_ID and context.user_data.get("admin_modo") == "painel_canal_mensagem":
        context.user_data.pop("admin_modo", None)
        canal_info = context.user_data.get("canal_escolhido")

        if not canal_info:
            await update.message.reply_text("❌ Erro: nenhum canal escolhido!")
            return

        # Parse da mensagem
        mensagem_completa = update.message.text.strip()
        linhas = mensagem_completa.split('\n')

        # Extrair informações
        texto_mensagem = []
        botao_gateway_texto = None
        link_filme = None

        for linha in linhas:
            if linha.startswith("BOTAO_GATEWAY:"):
                botao_gateway_texto = linha.replace("BOTAO_GATEWAY:", "").strip()
            elif linha.startswith("LINK_FILME:"):
                link_filme = linha.replace("LINK_FILME:", "").strip()
            elif not linha.startswith("BOTAO_") and not linha.startswith("LINK_"):
                texto_mensagem.append(linha)

        texto_final = "\n".join(texto_mensagem).strip()

        # Validações
        if not botao_gateway_texto:
            await update.message.reply_text("❌ Você precisa definir o texto do botão gateway!\nUse: `BOTAO_GATEWAY: Seu texto aqui`", parse_mode="Markdown")
            return

        if not link_filme:
            await update.message.reply_text("❌ Você precisa definir o link do filme!\nUse: `LINK_FILME: https://t.me/...`", parse_mode="Markdown")
            return

        # Criar botões
        bot_username = (await context.bot.get_me()).username
        mini_app_url = f"https://t.me/{bot_username}/catalogo"

        keyboard = [
            [InlineKeyboardButton(botao_gateway_texto, web_app=WebAppInfo(url=mini_app_url))],
            [InlineKeyboardButton(f"🎬 {canal_info['nome']}", url=link_filme)],
            [InlineKeyboardButton("💬 Suporte", url="https://t.me/DrBuscaOfc")],
            [InlineKeyboardButton("🎵 TikTok", url="https://www.tiktok.com/@ilovedoramaxx")]
        ]

        kb = InlineKeyboardMarkup(keyboard)

        # Publicar no canal
        try:
            m = await context.bot.send_message(
                canal_info['canal_id'],
                texto_final,
                parse_mode="Markdown",
                reply_markup=kb
            )
            await update.message.reply_text(
                f"✅ Mensagem publicada no canal *{canal_info['nome']}*!\n\n"
                f"ID da mensagem: `{m.message_id}`",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Erro ao publicar painel no canal: {e}")
            await update.message.reply_text(f"❌ Erro ao publicar no canal: {e}")

        context.user_data.pop("canal_escolhido", None)
        return

    # Admin publicando conteúdo no canal para gerar link direto
    if user_id == ADMIN_ID and context.user_data.get("admin_modo") == "enviar_canal":
        await _publicar_e_linkar(update, context)
        return

    # Admin adicionando filme - Passo 1: Nome
    if user_id == ADMIN_ID and context.user_data.get("admin_modo") == "add_filme_nome":
        nome_filme = update.message.text.strip()
        if len(nome_filme) < 3:
            await update.message.reply_text("❌ Nome muito curto. Digite novamente:")
            return

        # Gerar slug a partir do nome
        import re
        slug = re.sub(r'[^a-z0-9]+', '_', nome_filme.lower()).strip('_')

        context.user_data["novo_filme"] = {"nome": nome_filme, "slug": slug}
        context.user_data["admin_modo"] = "add_filme_descricao"

        await update.message.reply_text(
            f"✅ Nome: *{nome_filme}*\n"
            f"🔗 Slug: `{slug}`\n\n"
            f"*Passo 2 de 5: Descrição*\n\n"
            f"Digite uma breve descrição do filme:\n\n"
            f"*Exemplo:* `Um drama romântico russo emocionante sobre amor e superação.`",
            parse_mode="Markdown"
        )
        return

    # Admin adicionando filme - Passo 2: Descrição
    if user_id == ADMIN_ID and context.user_data.get("admin_modo") == "add_filme_descricao":
        descricao = update.message.text.strip()
        context.user_data["novo_filme"]["descricao"] = descricao
        context.user_data["admin_modo"] = "add_filme_poster"

        await update.message.reply_text(
            f"✅ Descrição salva!\n\n"
            f"*Passo 3 de 5: Poster (Foto)*\n\n"
            f"Envie agora a imagem do poster do filme.\n\n"
            f"⚠️ A imagem será salva como `{context.user_data['novo_filme']['slug']}_poster.jpg` na pasta raiz.",
            parse_mode="Markdown"
        )
        return

    # Admin pulando vídeo
    if user_id == ADMIN_ID and context.user_data.get("admin_modo") == "add_filme_video":
        if update.message.text.strip().upper() == "PULAR":
            context.user_data["novo_filme"]["video_path"] = ""
            context.user_data["admin_modo"] = "add_filme_canal_id"

            await update.message.reply_text(
                f"⏭️ Vídeo pulado.\n\n"
                f"*Passo 5 de 5: ID do Canal*\n\n"
                f"Digite o ID do canal onde este filme está hospedado.\n\n"
                f"💡 Para obter o ID:\n"
                f"1. Encaminhe uma mensagem do canal para @userinfobot\n"
                f"2. Copie o número que aparece\n\n"
                f"*Exemplo:* `-1001234567890`",
                parse_mode="Markdown"
            )
            return
        # Se não for PULAR e não for vídeo, pedir para enviar vídeo ou pular
        await update.message.reply_text("Envie um vídeo ou digite `PULAR` para continuar.")
        return

    # Admin adicionando filme - Passo 4: ID do Canal
    if user_id == ADMIN_ID and context.user_data.get("admin_modo") == "add_filme_canal_id":
        try:
            canal_id = int(update.message.text.strip())
            context.user_data["novo_filme"]["canal_id"] = canal_id
            context.user_data["admin_modo"] = "add_filme_confirmar"

            filme = context.user_data["novo_filme"]
            texto_confirmacao = (
                f"📋 *Confirme os dados do filme:*\n\n"
                f"🎬 *Nome:* {filme['nome']}\n"
                f"🔗 *Slug:* `{filme['slug']}`\n"
                f"📝 *Descrição:* {filme['descricao']}\n"
                f"🖼️ *Poster:* {filme.get('poster_path', 'N/A')}\n"
                f"🎥 *Vídeo:* {filme.get('video_path', 'N/A')}\n"
                f"📺 *Canal ID:* `{canal_id}`\n\n"
                f"Digite `SIM` para confirmar ou `NAO` para cancelar:"
            )

            await update.message.reply_text(texto_confirmacao, parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text("❌ ID inválido. Digite apenas números (ex: `-1001234567890`):")
        return

    # Admin adicionando filme - Passo 5: Confirmação
    if user_id == ADMIN_ID and context.user_data.get("admin_modo") == "add_filme_confirmar":
        resposta = update.message.text.strip().upper()

        if resposta == "SIM":
            try:
                filme = context.user_data["novo_filme"]
                adicionar_filme(
                    nome=filme["nome"],
                    slug=filme["slug"],
                    descricao=filme["descricao"],
                    poster_path=filme.get("poster_path", ""),
                    video_path=filme.get("video_path", ""),
                    canal_id=filme["canal_id"],
                    principal=False
                )

                # Gerar JSON atualizado
                await _gerar_catalogo_json()

                context.user_data.pop("novo_filme", None)
                context.user_data.pop("admin_modo", None)

                await update.message.reply_text(
                    f"✅ *Filme adicionado com sucesso!*\n\n"
                    f"🎬 {filme['nome']}\n\n"
                    f"O filme já está disponível no catálogo.\n\n"
                    f"🔗 Link direto: `/start {filme['slug']}`",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("◀️ Voltar ao Admin", callback_data="admin_menu")
                    ]])
                )
            except Exception as e:
                logger.error(f"Erro ao adicionar filme: {e}")
                await update.message.reply_text(f"❌ Erro ao adicionar filme: {e}")
        elif resposta == "NAO":
            context.user_data.pop("novo_filme", None)
            context.user_data.pop("admin_modo", None)
            await update.message.reply_text("❌ Operação cancelada.")
        else:
            await update.message.reply_text("Digite `SIM` para confirmar ou `NAO` para cancelar:")
        return

    # Usuário digitando valor personalizado
    if context.user_data.get("aguardando_valor"):
        try:
            valor = float(update.message.text.replace(",", ".").strip())
            if valor < 5.0:
                await update.message.reply_text("❌ O valor mínimo é R$ 5,00. Tente novamente:")
                return
            context.user_data.pop("aguardando_valor", None)
            await _iniciar_pagamento(update, context, valor)
        except ValueError:
            await update.message.reply_text(
                "❌ Valor inválido. Digite só números (ex: `25` ou `30.50`):",
                parse_mode="Markdown"
            )


async def handler_midia_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Admin enviando conteúdo para o canal
    if user_id == ADMIN_ID and context.user_data.get("admin_modo") == "enviar_canal":
        await _publicar_e_linkar(update, context)
        return

    # Admin enviando poster do filme
    if user_id == ADMIN_ID and context.user_data.get("admin_modo") == "add_filme_poster":
        if update.message.photo:
            try:
                import httpx

                # Pegar a foto em melhor qualidade
                photo = update.message.photo[-1]
                file = await context.bot.get_file(photo.file_id)

                slug = context.user_data["novo_filme"]["slug"]
                poster_filename = f"{slug}_poster.jpg"

                logger.info("="*80)
                logger.info("DOWNLOAD DE POSTER - DEBUG")
                logger.info("="*80)
                logger.info(f"File ID: {photo.file_id}")
                logger.info(f"File Path (original): {file.file_path}")
                logger.info(f"Slug: {slug}")
                logger.info(f"Poster Filename: {poster_filename}")
                logger.info(f"BOT_TOKEN: {BOT_TOKEN}")
                logger.info(f"TELEGRAM_API_BASE_FILE_URL: {TELEGRAM_API_BASE_FILE_URL}")

                # Com API local, file.file_path contém o caminho do arquivo
                # Exemplo: /var/lib/telegram-bot-api/8901182972:AAFK9tEYLWZii17AhwvsE9HBXHVDTcWaJ0U/photos/file_3.jpg
                # Precisamos construir: http://telegram-bot-api:8081/file/bot8901182972:AAFK9tEYLWZii17AhwvsE9HBXHVDTcWaJ0U/photos/file_3.jpg

                if file.file_path.startswith('http'):
                    logger.info("File path já é HTTP")
                    # VERIFICAR se a URL HTTP está correta ou tem /var/lib/ (URL incorreta da API local)
                    if '/var/lib/' in file.file_path:
                        logger.warning("URL HTTP contém /var/lib/ - está incorreta! Reconstruindo...")
                        # O token aparece 2x na URL incorreta, pegar a ULTIMA parte do split
                        token_without_bot = BOT_TOKEN
                        if token_without_bot in file.file_path:
                            parts = file.file_path.split(token_without_bot)
                            logger.info(f"Split pelo token gerou {len(parts)} partes")
                            if len(parts) >= 2:
                                # Pegar a ULTIMA parte (contém /photos/file_X.jpg)
                                last_part = parts[-1]
                                relative_path = last_part.lstrip('/')
                                file_url = f"{TELEGRAM_API_BASE_FILE_URL}{BOT_TOKEN}/{relative_path}"
                                logger.info(f"URL reconstruída: {file_url}")
                            else:
                                logger.warning("Split não gerou partes suficientes")
                                file_url = file.file_path
                        else:
                            logger.warning("Token não encontrado na URL HTTP")
                            file_url = file.file_path
                    else:
                        logger.info("URL HTTP parece correta, usando direto")
                        file_url = file.file_path
                else:
                    logger.info("File path é local, construindo URL...")
                    # Pegar apenas a parte depois do token no caminho
                    # Ex: /var/lib/telegram-bot-api/TOKEN/photos/file_3.jpg -> photos/file_3.jpg
                    token_without_bot = BOT_TOKEN  # Já vem sem 'bot'

                    # Procurar o token no caminho
                    logger.info(f"Procurando token no file_path...")
                    logger.info(f"Token sem 'bot': {token_without_bot}")
                    logger.info(f"Token está no file_path? {token_without_bot in file.file_path}")

                    if token_without_bot in file.file_path:
                        # Dividir pelo token e pegar a parte depois
                        parts = file.file_path.split(token_without_bot)
                        logger.info(f"Split pelo token resultou em {len(parts)} partes:")
                        for i, part in enumerate(parts):
                            logger.info(f"  Parte {i}: '{part}'")

                        if len(parts) > 1:
                            # Pegar tudo depois do token, removendo a barra inicial
                            relative_path = parts[1].lstrip('/')
                            file_url = f"{TELEGRAM_API_BASE_FILE_URL}{BOT_TOKEN}/{relative_path}"
                            logger.info(f"Caminho relativo: {relative_path}")
                            logger.info(f"URL construída: {file_url}")
                        else:
                            # Fallback: usar file.file_path diretamente do método download
                            logger.warning("FALLBACK 1: Split não gerou partes suficientes")
                            file_url = file.file_path
                            logger.info(f"URL (fallback 1): {file_url}")
                    else:
                        # Fallback: usar file.file_path diretamente
                        logger.warning("FALLBACK 2: Token não encontrado no file_path")
                        file_url = file.file_path
                        logger.info(f"URL (fallback 2): {file_url}")

                logger.info(f"URL construída (referência): {file_url}")
                logger.info("Baixando usando file_id via download_as_bytearray()...")

                # Usar download_as_bytearray() que usa file_id, não file_path
                # Isso evita o problema com a URL HTTP incorreta
                file_bytes = await file.download_as_bytearray()

                # Salvar no disco
                with open(poster_filename, 'wb') as f:
                    f.write(file_bytes)

                logger.info(f"Arquivo salvo com sucesso: {poster_filename}")
                logger.info(f"Tamanho do arquivo: {len(file_bytes)} bytes")
                logger.info("="*80)

                context.user_data["novo_filme"]["poster_path"] = poster_filename
                context.user_data["admin_modo"] = "add_filme_video"

                await update.message.reply_text(
                    f"✅ Poster salvo como `{poster_filename}`!\n\n"
                    f"*Passo 4 de 5: Vídeo (Trailer/Amostra)*\n\n"
                    f"Envie agora um vídeo curto (trailer ou amostra do filme).\n\n"
                    f"💡 *Ou* digite `PULAR` se não quiser adicionar vídeo agora.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Erro ao salvar poster: {e}")
                await update.message.reply_text(f"❌ Erro ao salvar poster: {e}")
        return

    # Admin enviando vídeo do filme
    if user_id == ADMIN_ID and context.user_data.get("admin_modo") == "add_filme_video":
        if update.message.video:
            try:
                import httpx

                video = update.message.video
                file = await context.bot.get_file(video.file_id)

                slug = context.user_data["novo_filme"]["slug"]
                video_filename = f"{slug}_trailer.mp4"

                # Com API local, file.file_path contém o caminho do arquivo
                if file.file_path.startswith('http'):
                    # VERIFICAR se a URL HTTP está correta ou tem /var/lib/
                    if '/var/lib/' in file.file_path:
                        logger.warning("URL HTTP de vídeo contém /var/lib/ - reconstruindo...")
                        token_without_bot = BOT_TOKEN
                        if token_without_bot in file.file_path:
                            parts = file.file_path.split(token_without_bot)
                            if len(parts) >= 2:
                                last_part = parts[-1]
                                relative_path = last_part.lstrip('/')
                                file_url = f"{TELEGRAM_API_BASE_FILE_URL}{BOT_TOKEN}/{relative_path}"
                            else:
                                file_url = file.file_path
                        else:
                            file_url = file.file_path
                    else:
                        file_url = file.file_path
                else:
                    # Pegar apenas a parte depois do token no caminho
                    token_without_bot = BOT_TOKEN

                    if token_without_bot in file.file_path:
                        parts = file.file_path.split(token_without_bot)
                        if len(parts) > 1:
                            relative_path = parts[1].lstrip('/')
                            file_url = f"{TELEGRAM_API_BASE_FILE_URL}{BOT_TOKEN}/{relative_path}"
                        else:
                            file_url = file.file_path
                    else:
                        file_url = file.file_path

                # Baixar usando file_id via download_as_bytearray()
                logger.info("Baixando vídeo usando download_as_bytearray()...")
                file_bytes = await file.download_as_bytearray()

                # Salvar no disco
                with open(video_filename, 'wb') as f:
                    f.write(file_bytes)

                logger.info(f"Vídeo salvo com sucesso: {video_filename}")
                logger.info(f"Tamanho: {len(file_bytes)} bytes")

                context.user_data["novo_filme"]["video_path"] = video_filename
                context.user_data["admin_modo"] = "add_filme_canal_id"

                await update.message.reply_text(
                    f"✅ Vídeo salvo como `{video_filename}`!\n\n"
                    f"*Passo 5 de 5: ID do Canal*\n\n"
                    f"Digite o ID do canal onde este filme está hospedado.\n\n"
                    f"💡 Para obter o ID:\n"
                    f"1. Encaminhe uma mensagem do canal para @userinfobot\n"
                    f"2. Copie o número que aparece\n\n"
                    f"*Exemplo:* `-1001234567890`",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Erro ao salvar vídeo: {e}")
                await update.message.reply_text(f"❌ Erro ao salvar vídeo: {e}")
        return


# ──────────────────────────────────────────────────────────
# PAINEL FIXO NO CANAL (reenvia sempre no final)
# ──────────────────────────────────────────────────────────

async def handler_canal_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = update.channel_post
    if post is None or post.chat_id != CHANNEL_ID:
        return

    # Ignora as mensagens que o próprio bot envia (o reenvio do painel)
    if post.from_user and post.from_user.id == context.bot.id:
        return

    painel = get_painel_canal()
    if not painel or not painel.get("message_id"):
        return

    if post.message_id == painel["message_id"]:
        return

    try:
        await context.bot.delete_message(CHANNEL_ID, painel["message_id"])
    except Exception:
        pass

    try:
        botoes = json.loads(painel["botoes"]) if painel.get("botoes") else []
        bot_username = (await context.bot.get_me()).username
        kb = _kb_from_botoes(botoes, bot_username)
        m = await context.bot.send_message(CHANNEL_ID, painel["texto"], parse_mode="Markdown", reply_markup=kb)
        set_painel_message_id(m.message_id)
    except Exception as e:
        logger.error(f"Erro ao reenviar painel do canal: {e}")


# ──────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────

def main():
    init_db()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .base_url(TELEGRAM_API_BASE_URL)
        .base_file_url(TELEGRAM_API_BASE_FILE_URL)
        .local_mode(True)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu",  cmd_menu))
    app.add_handler(CommandHandler("admin", cmd_admin))

    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handler_web_app_data))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, handler_canal_post))

    app.add_handler(CallbackQueryHandler(cb_menu_principal,          pattern="^menu_principal$"))
    app.add_handler(CallbackQueryHandler(cb_apoiar,                  pattern="^apoiar$"))
    app.add_handler(CallbackQueryHandler(cb_escolher_valor,          pattern="^valor_"))
    app.add_handler(CallbackQueryHandler(cb_sobre_filme,             pattern="^sobre_filme$"))
    app.add_handler(CallbackQueryHandler(cb_andamento,               pattern="^andamento$"))
    app.add_handler(CallbackQueryHandler(cb_falar_equipe,            pattern="^falar_equipe$"))
    app.add_handler(CallbackQueryHandler(cb_admin_menu,              pattern="^admin_menu$"))
    app.add_handler(CallbackQueryHandler(cb_admin_editar_progresso,  pattern="^admin_editar_progresso$"))
    app.add_handler(CallbackQueryHandler(cb_admin_painel_canal,      pattern="^admin_painel_canal$"))
    app.add_handler(CallbackQueryHandler(cb_painel_canal_escolhido,  pattern="^painel_canal_"))
    app.add_handler(CallbackQueryHandler(cb_admin_enviar_canal,      pattern="^admin_enviar_canal$"))
    app.add_handler(CallbackQueryHandler(cb_admin_gerar_link,        pattern="^admin_gerar_link$"))
    app.add_handler(CallbackQueryHandler(cb_gerar_link_simples,      pattern="^gerar_link_simples$"))
    app.add_handler(CallbackQueryHandler(cb_gerar_link_personalizado, pattern="^gerar_link_personalizado$"))
    app.add_handler(CallbackQueryHandler(cb_admin_ver_links,         pattern="^admin_ver_links$"))
    app.add_handler(CallbackQueryHandler(cb_admin_enviar_convites,   pattern="^admin_enviar_convites$"))
    app.add_handler(CallbackQueryHandler(cb_confirmar_envio_convites, pattern="^confirmar_envio_convites$"))
    app.add_handler(CallbackQueryHandler(cb_admin_catalogo,          pattern="^admin_catalogo$"))
    app.add_handler(CallbackQueryHandler(cb_admin_add_filme,         pattern="^admin_add_filme$"))
    app.add_handler(CallbackQueryHandler(cb_admin_broadcast,         pattern="^admin_broadcast$"))
    app.add_handler(CallbackQueryHandler(cb_confirmar_broadcast,     pattern="^confirmar_broadcast$"))

    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, handler_texto))
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (
            filters.PHOTO | filters.VIDEO | filters.Document.ALL |
            filters.AUDIO | filters.ANIMATION | filters.VOICE
        ),
        handler_midia_admin
    ))

    logger.info("Bot iniciado!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
