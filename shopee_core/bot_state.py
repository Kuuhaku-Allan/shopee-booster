"""
shopee_core/bot_state.py — Estado persistente do Bot
=====================================================
SQLite leve para:
  - Lock do Sentinela (evitar .exe e WhatsApp rodando ao mesmo tempo)
  - Histórico de edições por conversa (base para undo/redo futuro)
  - Estado de imagem ativa por usuário

Intencionalmente sem Streamlit — funciona em qualquer contexto.
"""

import sqlite3
import os
import sys
from pathlib import Path
from datetime import datetime


# ── Resolve DB_PATH igual ao sentinela_db.py ──────────────────────
if getattr(sys, "frozen", False):
    _BASE = Path(sys.executable).parent
else:
    # shopee_core/bot_state.py → dois níveis acima = raiz do projeto
    _BASE = Path(__file__).resolve().parent.parent

DB_PATH = _BASE / "data" / "bot_state.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # WAL mode = múltiplas leituras simultâneas sem bloquear escritas
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ══════════════════════════════════════════════════════════════
# INICIALIZAÇÃO
# ══════════════════════════════════════════════════════════════

def init_bot_state_db():
    """Cria as tabelas caso não existam. Idempotente."""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sentinela_locks (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                loja_id           TEXT    NOT NULL,
                keyword           TEXT    NOT NULL,
                janela_execucao   TEXT    NOT NULL,
                executor          TEXT    NOT NULL,
                status            TEXT    NOT NULL DEFAULT 'running',
                started_at        TEXT    NOT NULL,
                finished_at       TEXT,
                UNIQUE(loja_id, keyword, janela_execucao)
            );

            CREATE TABLE IF NOT EXISTS image_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT    NOT NULL,
                session_id  TEXT    NOT NULL,
                step        INTEGER NOT NULL,
                instruction TEXT    NOT NULL,
                image_path  TEXT,
                created_at  TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS active_image (
                user_id    TEXT PRIMARY KEY,
                image_path TEXT,
                session_id TEXT,
                updated_at TEXT
            );
        """)


# ══════════════════════════════════════════════════════════════
# SENTINELA — Lock de execução único
# ══════════════════════════════════════════════════════════════

def try_acquire_sentinel_lock(
    loja_id: str,
    keyword: str,
    janela_execucao: str,
    executor: str,
) -> bool:
    """
    Tenta adquirir o lock para a janela de execução.

    Retorna True se o lock foi adquirido (executor pode rodar).
    Retorna False se já existe um lock nessa janela (outro executor já rodou/está rodando).

    O campo UNIQUE(loja_id, keyword, janela_execucao) garante atomicidade via SQLite.
    """
    init_bot_state_db()
    try:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO sentinela_locks
                    (loja_id, keyword, janela_execucao, executor, status, started_at)
                VALUES (?, ?, ?, ?, 'running', ?)
                """,
                (loja_id, keyword, janela_execucao, executor,
                 datetime.utcnow().isoformat()),
            )
        return True
    except sqlite3.IntegrityError:
        # Violação de UNIQUE → lock já existe
        return False


def finish_sentinel_lock(
    loja_id: str,
    keyword: str,
    janela_execucao: str,
    status: str = "done",
):
    """Marca o lock como concluído (status='done') ou com erro (status='error')."""
    init_bot_state_db()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE sentinela_locks
               SET status = ?, finished_at = ?
             WHERE loja_id = ? AND keyword = ? AND janela_execucao = ?
            """,
            (status, datetime.utcnow().isoformat(),
             loja_id, keyword, janela_execucao),
        )


def get_sentinel_lock_status(
    loja_id: str,
    keyword: str,
    janela_execucao: str,
) -> dict | None:
    """Retorna o registro do lock, ou None se não existir."""
    init_bot_state_db()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM sentinela_locks
             WHERE loja_id = ? AND keyword = ? AND janela_execucao = ?
            """,
            (loja_id, keyword, janela_execucao),
        ).fetchone()
    return dict(row) if row else None


# ══════════════════════════════════════════════════════════════
# IMAGEM ATIVA por usuário
# ══════════════════════════════════════════════════════════════

def set_active_image(user_id: str, image_path: str, session_id: str):
    """Persiste qual imagem está ativa para um determinado usuário/conversa."""
    init_bot_state_db()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO active_image (user_id, image_path, session_id, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                image_path = excluded.image_path,
                session_id = excluded.session_id,
                updated_at = excluded.updated_at
            """,
            (user_id, image_path, session_id, datetime.utcnow().isoformat()),
        )


def get_active_image(user_id: str) -> dict | None:
    """Recupera a imagem ativa do usuário, ou None."""
    init_bot_state_db()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM active_image WHERE user_id = ?", (user_id,)
        ).fetchone()
    return dict(row) if row else None


# ══════════════════════════════════════════════════════════════
# HISTÓRICO DE EDIÇÕES (base para undo/redo)
# ══════════════════════════════════════════════════════════════

def push_image_history(
    user_id: str,
    session_id: str,
    instruction: str,
    image_path: str = "",
):
    """Adiciona um passo ao histórico de edições."""
    init_bot_state_db()
    with get_conn() as conn:
        # Determina o próximo step sequencial da sessão
        row = conn.execute(
            """
            SELECT COALESCE(MAX(step), -1) + 1 AS next_step
              FROM image_history
             WHERE user_id = ? AND session_id = ?
            """,
            (user_id, session_id),
        ).fetchone()
        next_step = row["next_step"] if row else 0
        conn.execute(
            """
            INSERT INTO image_history
                (user_id, session_id, step, instruction, image_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, session_id, next_step, instruction,
             image_path, datetime.utcnow().isoformat()),
        )


def get_image_history(user_id: str, session_id: str) -> list[dict]:
    """Retorna todos os passos da sessão de edição, em ordem."""
    init_bot_state_db()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM image_history
             WHERE user_id = ? AND session_id = ?
             ORDER BY step ASC
            """,
            (user_id, session_id),
        ).fetchall()
    return [dict(r) for r in rows]


def clear_image_history(user_id: str, session_id: str):
    """Limpa o histórico de uma sessão de edição."""
    init_bot_state_db()
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM image_history WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        )
