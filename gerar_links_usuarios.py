"""
Script para gerar links exclusivos para usuarios que deram start mas nunca entraram no grupo.
"""
import sys
import asyncio
from telegram import Bot
from datetime import datetime
from database import init_db, listar_usuarios_sem_acesso, registrar_link_gerado, registrar_acesso
from config import BOT_TOKEN, CHANNEL_ID, TELEGRAM_API_BASE_URL, TELEGRAM_API_BASE_FILE_URL

# Configurar encoding para UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')


async def gerar_links_para_usuarios():
    """Gera links exclusivos para cada usuário que nunca entrou no grupo"""

    # Inicializar banco de dados
    init_db()

    # Inicializar bot
    bot = Bot(token=BOT_TOKEN, base_url=TELEGRAM_API_BASE_URL, base_file_url=TELEGRAM_API_BASE_FILE_URL)

    # Buscar usuários sem acesso (que nunca entraram no grupo)
    usuarios_sem_acesso = listar_usuarios_sem_acesso()
    total = len(usuarios_sem_acesso)

    print(f"\n{'='*60}")
    print(f"ANALISE DE USUARIOS SEM ACESSO AO CANAL")
    print(f"{'='*60}\n")
    print(f"Total de usuarios que deram /start mas NUNCA entraram: {total}\n")

    if total == 0:
        print("Nao ha usuarios pendentes!")
        return

    # Exibir preview dos usuarios
    print(f"{'─'*60}")
    print("USUARIOS ENCONTRADOS:")
    print(f"{'─'*60}\n")

    for i, (user_id, data_vis) in enumerate(usuarios_sem_acesso[:10], 1):
        data_str = datetime.fromtimestamp(data_vis).strftime("%d/%m/%Y %H:%M")
        print(f"{i}. User ID: {user_id} | /start em: {data_str}")

    if total > 10:
        print(f"... e mais {total - 10} usuários")

    print(f"\n{'─'*60}\n")

    # Confirmar acao
    resposta = input(f"Deseja gerar {total} links exclusivos? (SIM/NAO): ").strip().upper()

    if resposta != "SIM":
        print("\nOperacao cancelada.")
        return

    print(f"\n{'─'*60}")
    print("GERANDO LINKS EXCLUSIVOS...")
    print(f"{'─'*60}\n")

    links_gerados = []
    erros = []

    for i, (user_id, data_vis) in enumerate(usuarios_sem_acesso, 1):
        try:
            # Gerar nome único para o link
            nome_link = f"user_{user_id}_recuperacao"

            # Criar link de convite único (uso único)
            invite = await bot.create_chat_invite_link(
                chat_id=CHANNEL_ID,
                member_limit=1,
                name=nome_link
            )

            # Registrar no banco de dados
            link_id = registrar_link_gerado(nome_link, invite.invite_link)

            # Registrar acesso gratuito (valor 0.0)
            registrar_acesso(user_id, 0.0)

            # Preparar mensagem
            mensagem = (
                f"*Ola!*\n\n"
                f"Voce visitou nosso bot mas ainda nao teve a chance de assistir ao filme.\n\n"
                f"*'Seu Coracao Sera Partido'* esta disponivel *GRATUITAMENTE* para voce!\n\n"
                f"Assista em 4K com legendas profissionais no canal exclusivo.\n\n"
                f"Clique no link abaixo para entrar agora:\n\n"
                f"{invite.invite_link}\n\n"
                f"_Este e um link de uso unico e exclusivo para voce. Nao compartilhe!_\n\n"
                f"Aproveite o filme!"
            )

            links_gerados.append({
                'link_id': link_id,
                'user_id': user_id,
                'nome_link': nome_link,
                'invite_link': invite.invite_link,
                'mensagem': mensagem,
                'data_start': datetime.fromtimestamp(data_vis).strftime("%d/%m/%Y %H:%M")
            })

            print(f"✅ [{i}/{total}] Link gerado para User ID: {user_id}")

            # Pequeno delay para evitar rate limit
            await asyncio.sleep(0.3)

        except Exception as e:
            erros.append({'user_id': user_id, 'erro': str(e)})
            print(f"❌ [{i}/{total}] Erro para User ID {user_id}: {e}")

    # Resumo final
    print(f"\n{'='*60}")
    print("RESULTADO DA GERACAO DE LINKS")
    print(f"{'='*60}\n")
    print(f"Links gerados com sucesso: {len(links_gerados)}")
    print(f"Erros: {len(erros)}\n")

    # Salvar relatorio em arquivo
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    relatorio_file = f"relatorio_links_{timestamp}.txt"

    with open(relatorio_file, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("RELATORIO DE LINKS GERADOS - SEU CORACAO SERA PARTIDO\n")
        f.write("="*80 + "\n\n")
        f.write(f"Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
        f.write(f"Total de links gerados: {len(links_gerados)}\n")
        f.write(f"Total de erros: {len(erros)}\n\n")

        f.write("-"*80 + "\n")
        f.write("LINKS GERADOS E MENSAGENS\n")
        f.write("-"*80 + "\n\n")

        for item in links_gerados:
            f.write(f"ID do Link: {item['link_id']}\n")
            f.write(f"User ID: {item['user_id']}\n")
            f.write(f"Nome do Link: {item['nome_link']}\n")
            f.write(f"/start em: {item['data_start']}\n")
            f.write(f"Link: {item['invite_link']}\n\n")
            f.write("MENSAGEM PARA ENVIAR:\n")
            f.write("-"*40 + "\n")
            f.write(item['mensagem'] + "\n")
            f.write("-"*80 + "\n\n")

        if erros:
            f.write("\n" + "-"*80 + "\n")
            f.write("ERROS ENCONTRADOS\n")
            f.write("-"*80 + "\n\n")
            for erro in erros:
                f.write(f"User ID: {erro['user_id']}\n")
                f.write(f"Erro: {erro['erro']}\n\n")

    print(f"Relatorio completo salvo em: {relatorio_file}\n")

    # Salvar arquivo CSV para importacao
    csv_file = f"links_usuarios_{timestamp}.csv"
    with open(csv_file, 'w', encoding='utf-8') as f:
        f.write("user_id,link,nome_link,data_start\n")
        for item in links_gerados:
            f.write(f"{item['user_id']},{item['invite_link']},{item['nome_link']},{item['data_start']}\n")

    print(f"Arquivo CSV salvo em: {csv_file}\n")

    # Exibir preview de mensagens
    print(f"{'─'*60}")
    print("PREVIEW DAS MENSAGENS (primeiros 3 usuarios):")
    print(f"{'─'*60}\n")

    for item in links_gerados[:3]:
        print(f"Para User ID: {item['user_id']}")
        print(item['mensagem'])
        print(f"{'─'*60}\n")

    print(f"\nProcesso concluido!")
    print(f"Use o comando /admin no bot para enviar as mensagens automaticamente.")
    print(f"Ou use o relatorio {relatorio_file} para enviar manualmente.\n")


if __name__ == "__main__":
    asyncio.run(gerar_links_para_usuarios())
