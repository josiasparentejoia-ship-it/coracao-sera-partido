import sqlite3
import time

_conn = sqlite3.connect("coracao.db", check_same_thread=False, timeout=30)
_conn.execute("PRAGMA journal_mode=WAL")
_cur = _conn.cursor()


def init_db():
    _cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios_canal (
            user_id     INTEGER PRIMARY KEY,
            data_acesso INTEGER,
            valor_pago  REAL
        )
    """)
    _cur.execute("""
        CREATE TABLE IF NOT EXISTS progresso_projeto (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)
    _cur.execute("""
        CREATE TABLE IF NOT EXISTS canal_painel (
            id         INTEGER PRIMARY KEY CHECK (id = 1),
            message_id INTEGER,
            texto      TEXT,
            botoes     TEXT
        )
    """)
    _cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios_intro (
            user_id  INTEGER PRIMARY KEY,
            data_vis INTEGER
        )
    """)
    _cur.execute("""
        CREATE TABLE IF NOT EXISTS links_gerados (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            nome          TEXT,
            link          TEXT,
            data_criacao  INTEGER,
            usado         INTEGER DEFAULT 0,
            user_id_uso   INTEGER,
            data_uso      INTEGER
        )
    """)
    _cur.execute("""
        CREATE TABLE IF NOT EXISTS catalogo_filmes (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            nome          TEXT NOT NULL,
            slug          TEXT UNIQUE NOT NULL,
            descricao     TEXT,
            poster_path   TEXT,
            video_path    TEXT,
            canal_id      INTEGER NOT NULL,
            principal     INTEGER DEFAULT 0,
            ativo         INTEGER DEFAULT 1,
            data_criacao  INTEGER
        )
    """)
    _defaults = [
        ("progresso",        "0"),
        ("valor_arrecadado", "0,00"),
        ("proxima_meta",     "Iniciar tradução do roteiro"),
        ("etapa_atual",      "🟡 Planejamento inicial"),
    ]
    for chave, valor in _defaults:
        _cur.execute("INSERT OR IGNORE INTO progresso_projeto VALUES (?,?)", (chave, valor))
    _conn.commit()


def get_progresso() -> dict:
    _cur.execute("SELECT chave, valor FROM progresso_projeto")
    return dict(_cur.fetchall())


def set_progresso(chave: str, valor: str):
    _cur.execute("INSERT OR REPLACE INTO progresso_projeto VALUES (?,?)", (chave, valor))
    _conn.commit()


def registrar_acesso(user_id: int, valor_pago: float):
    _cur.execute(
        "INSERT OR REPLACE INTO usuarios_canal VALUES (?,?,?)",
        (user_id, int(time.time()), valor_pago)
    )
    _conn.commit()


def ja_tem_acesso(user_id: int) -> bool:
    _cur.execute("SELECT 1 FROM usuarios_canal WHERE user_id=?", (user_id,))
    return _cur.fetchone() is not None


def marcar_intro_vista(user_id: int):
    _cur.execute(
        "INSERT OR IGNORE INTO usuarios_intro VALUES (?,?)",
        (user_id, int(time.time()))
    )
    _conn.commit()


def ja_viu_intro(user_id: int) -> bool:
    _cur.execute("SELECT 1 FROM usuarios_intro WHERE user_id=?", (user_id,))
    return _cur.fetchone() is not None


def get_painel_canal() -> dict | None:
    _cur.execute("SELECT message_id, texto, botoes FROM canal_painel WHERE id=1")
    row = _cur.fetchone()
    if not row:
        return None
    return {"message_id": row[0], "texto": row[1], "botoes": row[2]}


def set_painel_canal(message_id: int, texto: str, botoes_json: str):
    _cur.execute(
        "INSERT OR REPLACE INTO canal_painel (id, message_id, texto, botoes) VALUES (1, ?, ?, ?)",
        (message_id, texto, botoes_json)
    )
    _conn.commit()


def set_painel_message_id(message_id: int):
    _cur.execute("UPDATE canal_painel SET message_id=? WHERE id=1", (message_id,))
    _conn.commit()


def registrar_link_gerado(nome: str, link: str) -> int:
    """Registra um link gerado e retorna o ID"""
    _cur.execute(
        "INSERT INTO links_gerados (nome, link, data_criacao) VALUES (?, ?, ?)",
        (nome, link, int(time.time()))
    )
    _conn.commit()
    return _cur.lastrowid


def marcar_link_usado(nome: str, user_id: int):
    """Marca um link como usado"""
    _cur.execute(
        "UPDATE links_gerados SET usado=1, user_id_uso=?, data_uso=? WHERE nome=? AND usado=0",
        (user_id, int(time.time()), nome)
    )
    _conn.commit()


def listar_links_gerados(limite: int = 20):
    """Lista os últimos links gerados"""
    _cur.execute("""
        SELECT id, nome, link, data_criacao, usado, user_id_uso, data_uso
        FROM links_gerados
        ORDER BY data_criacao DESC
        LIMIT ?
    """, (limite,))
    return _cur.fetchall()


def contar_links_ativos():
    """Conta quantos links ainda não foram usados"""
    _cur.execute("SELECT COUNT(*) FROM links_gerados WHERE usado=0")
    return _cur.fetchone()[0]


def listar_usuarios_sem_acesso():
    """Lista usuários que deram start mas não têm acesso ao canal"""
    _cur.execute("""
        SELECT ui.user_id, ui.data_vis
        FROM usuarios_intro ui
        LEFT JOIN usuarios_canal uc ON ui.user_id = uc.user_id
        WHERE uc.user_id IS NULL
        ORDER BY ui.data_vis DESC
    """)
    return _cur.fetchall()


def contar_usuarios_sem_acesso():
    """Conta quantos usuários deram start mas não têm acesso"""
    _cur.execute("""
        SELECT COUNT(*)
        FROM usuarios_intro ui
        LEFT JOIN usuarios_canal uc ON ui.user_id = uc.user_id
        WHERE uc.user_id IS NULL
    """)
    return _cur.fetchone()[0]


# ═══════════════════════════════════════════════════════════
# CATÁLOGO DE FILMES
# ═══════════════════════════════════════════════════════════

def adicionar_filme(nome: str, slug: str, descricao: str, poster_path: str,
                   video_path: str, canal_id: int, principal: bool = False):
    """Adiciona um novo filme ao catálogo"""
    if principal:
        # Remove o destaque de outros filmes
        _cur.execute("UPDATE catalogo_filmes SET principal=0")

    _cur.execute("""
        INSERT INTO catalogo_filmes
        (nome, slug, descricao, poster_path, video_path, canal_id, principal, data_criacao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (nome, slug, descricao, poster_path, video_path, canal_id,
          1 if principal else 0, int(time.time())))
    _conn.commit()
    return _cur.lastrowid


def listar_filmes_ativos():
    """Lista todos os filmes ativos do catálogo"""
    _cur.execute("""
        SELECT id, nome, slug, descricao, poster_path, video_path, canal_id, principal
        FROM catalogo_filmes
        WHERE ativo=1
        ORDER BY principal DESC, data_criacao DESC
    """)
    return _cur.fetchall()


def obter_filme_por_slug(slug: str):
    """Obtém informações de um filme pelo slug"""
    _cur.execute("""
        SELECT id, nome, slug, descricao, poster_path, video_path, canal_id, principal
        FROM catalogo_filmes
        WHERE slug=? AND ativo=1
    """, (slug,))
    row = _cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "nome": row[1],
        "slug": row[2],
        "descricao": row[3],
        "poster_path": row[4],
        "video_path": row[5],
        "canal_id": row[6],
        "principal": row[7]
    }


def definir_filme_principal(slug: str):
    """Define um filme como principal (destaque)"""
    _cur.execute("UPDATE catalogo_filmes SET principal=0")
    _cur.execute("UPDATE catalogo_filmes SET principal=1 WHERE slug=?", (slug,))
    _conn.commit()


def remover_filme(slug: str):
    """Remove (desativa) um filme do catálogo"""
    _cur.execute("UPDATE catalogo_filmes SET ativo=0 WHERE slug=?", (slug,))
    _conn.commit()


def contar_filmes_ativos():
    """Conta quantos filmes estão no catálogo"""
    _cur.execute("SELECT COUNT(*) FROM catalogo_filmes WHERE ativo=1")
    return _cur.fetchone()[0]


def listar_todos_usuarios():
    """Lista todos os usuários que já interagiram com o bot (deram /start)"""
    _cur.execute("""
        SELECT DISTINCT user_id
        FROM usuarios_intro
        ORDER BY data_vis DESC
    """)
    return [row[0] for row in _cur.fetchall()]


def contar_todos_usuarios():
    """Conta quantos usuários já interagiram com o bot"""
    _cur.execute("SELECT COUNT(*) FROM usuarios_intro")
    return _cur.fetchone()[0]
