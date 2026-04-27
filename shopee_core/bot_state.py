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
        # Migração suave do lock do Sentinela (schema legado → U7)
        try:
            cols = conn.execute("PRAGMA table_info(sentinela_locks)").fetchall()
            col_names = {c["name"] for c in cols} if cols else set()
        except Exception:
            col_names = set()

        if col_names and ("user_id" not in col_names or "shop_uid" not in col_names):
            # Cria tabela nova com schema U7 e copia dados existentes (user_id/shop_uid = NULL)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sentinela_locks_v2 (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id           TEXT,
                    shop_uid          TEXT,
                    loja_id           TEXT    NOT NULL,
                    keyword           TEXT    NOT NULL,
                    janela_execucao   TEXT    NOT NULL,
                    executor          TEXT    NOT NULL,
                    status            TEXT    NOT NULL DEFAULT 'running',
                    started_at        TEXT    NOT NULL,
                    finished_at       TEXT,
                    UNIQUE(user_id, shop_uid, keyword, janela_execucao)
                );
                """
            )

            try:
                legacy_rows = conn.execute("SELECT * FROM sentinela_locks").fetchall()
            except Exception:
                legacy_rows = []

            for r in legacy_rows:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO sentinela_locks_v2
                        (id, user_id, shop_uid, loja_id, keyword, janela_execucao, executor, status, started_at, finished_at)
                    VALUES
                        (?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        r["id"] if "id" in col_names else None,
                        r["loja_id"],
                        r["keyword"],
                        r["janela_execucao"],
                        r["executor"],
                        r["status"] if "status" in col_names else "running",
                        r["started_at"] if "started_at" in col_names else datetime.utcnow().isoformat(),
                        r["finished_at"] if "finished_at" in col_names else None,
                    ),
                )

            conn.execute("DROP TABLE IF EXISTS sentinela_locks")
            conn.execute("ALTER TABLE sentinela_locks_v2 RENAME TO sentinela_locks")

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sentinela_locks (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id           TEXT,
                shop_uid          TEXT,
                loja_id           TEXT    NOT NULL,
                keyword           TEXT    NOT NULL,
                janela_execucao   TEXT    NOT NULL,
                executor          TEXT    NOT NULL,
                status            TEXT    NOT NULL DEFAULT 'running',
                started_at        TEXT    NOT NULL,
                finished_at       TEXT,
                UNIQUE(user_id, shop_uid, keyword, janela_execucao)
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

# Status que permitem retry (não bloqueiam nova execução)
RETRYABLE_STATUSES = {"timeout", "error", "failed", "cancelled"}


def try_acquire_sentinel_lock(
    loja_id: str,
    keyword: str,
    janela_execucao: str,
    executor: str,
    user_id: str = None,
    shop_uid: str = None,
) -> bool:
    """
    Tenta adquirir o lock para a janela de execução.

    Retorna True se o lock foi adquirido (executor pode rodar).
    Retorna False se já existe um lock nessa janela com status 'running' ou 'done'.

    Se existe lock com status retryable (timeout/error/failed/cancelled),
    reaproveita o lock e atualiza para 'running'.

    O campo UNIQUE garante atomicidade via SQLite.
    
    Args:
        loja_id: ID da loja (legado, mantido para compatibilidade)
        keyword: Keyword sendo monitorada
        janela_execucao: Identificador da janela de tempo
        executor: Quem está executando (whatsapp, desktop, etc)
        user_id: JID do WhatsApp (U7)
        shop_uid: UID da loja (U7)
    """
    init_bot_state_db()
    
    with get_conn() as conn:
        # Verifica se já existe lock
        existing = get_sentinel_lock_status(
            loja_id=loja_id,
            keyword=keyword,
            janela_execucao=janela_execucao,
            user_id=user_id,
            shop_uid=shop_uid,
        )
        
        if existing:
            status = existing.get("status")
            
            # Se status é retryable, reaproveita o lock
            if status in RETRYABLE_STATUSES:
                if user_id and shop_uid:
                    # Novo formato (U7)
                    conn.execute(
                        """
                        UPDATE sentinela_locks
                        SET executor = ?,
                            status = 'running',
                            started_at = ?,
                            finished_at = NULL
                        WHERE user_id = ?
                          AND shop_uid = ?
                          AND keyword = ?
                          AND janela_execucao = ?
                        """,
                        (
                            executor,
                            datetime.utcnow().isoformat(),
                            user_id,
                            shop_uid,
                            keyword,
                            janela_execucao,
                        ),
                    )
                else:
                    # Formato legado
                    conn.execute(
                        """
                        UPDATE sentinela_locks
                        SET executor = ?,
                            status = 'running',
                            started_at = ?,
                            finished_at = NULL
                        WHERE loja_id = ?
                          AND keyword = ?
                          AND janela_execucao = ?
                        """,
                        (
                            executor,
                            datetime.utcnow().isoformat(),
                            loja_id,
                            keyword,
                            janela_execucao,
                        ),
                    )
                return True
            
            # Status 'running' ou 'done' → bloqueia
            return False
        
        # Não existe lock → cria novo
        try:
            conn.execute(
                """
                INSERT INTO sentinela_locks
                    (user_id, shop_uid, loja_id, keyword, janela_execucao, executor, status, started_at)
                VALUES (?, ?, ?, ?, ?, ?, 'running', ?)
                """,
                (user_id, shop_uid, loja_id, keyword, janela_execucao, executor,
                 datetime.utcnow().isoformat()),
            )
            return True
        except sqlite3.IntegrityError:
            # Race condition: outro processo criou o lock entre o SELECT e o INSERT
            return False


def finish_sentinel_lock(
    loja_id: str,
    keyword: str,
    janela_execucao: str,
    status: str = "done",
    user_id: str = None,
    shop_uid: str = None,
):
    """
    Marca o lock como concluído (status='done') ou com erro (status='error').
    
    Args:
        loja_id: ID da loja (legado)
        keyword: Keyword sendo monitorada
        janela_execucao: Identificador da janela de tempo
        status: Status final (done, error)
        user_id: JID do WhatsApp (U7)
        shop_uid: UID da loja (U7)
    """
    init_bot_state_db()
    with get_conn() as conn:
        if user_id and shop_uid:
            # Novo formato (U7)
            conn.execute(
                """
                UPDATE sentinela_locks
                   SET status = ?, finished_at = ?
                 WHERE user_id = ? AND shop_uid = ? AND keyword = ? AND janela_execucao = ?
                """,
                (status, datetime.utcnow().isoformat(),
                 user_id, shop_uid, keyword, janela_execucao),
            )
        else:
            # Formato legado
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
    user_id: str = None,
    shop_uid: str = None,
) -> dict | None:
    """
    Retorna o registro do lock, ou None se não existir.
    
    Args:
        loja_id: ID da loja (legado)
        keyword: Keyword sendo monitorada
        janela_execucao: Identificador da janela de tempo
        user_id: JID do WhatsApp (U7)
        shop_uid: UID da loja (U7)
    """
    init_bot_state_db()
    with get_conn() as conn:
        if user_id and shop_uid:
            # Novo formato (U7)
            row = conn.execute(
                """
                SELECT * FROM sentinela_locks
                 WHERE user_id = ? AND shop_uid = ? AND keyword = ? AND janela_execucao = ?
                """,
                (user_id, shop_uid, keyword, janela_execucao),
            ).fetchone()
        else:
            # Formato legado
            row = conn.execute(
                """
                SELECT * FROM sentinela_locks
                 WHERE loja_id = ? AND keyword = ? AND janela_execucao = ?
                """,
                (loja_id, keyword, janela_execucao),
            ).fetchone()
    return dict(row) if row else None


def clear_retryable_sentinel_locks(
    user_id: str = None,
    shop_uid: str = None,
    loja_id: str = None,
    janela_execucao: str = None,
) -> int:
    """
    Remove locks com status retryable (timeout/error/failed/cancelled).
    
    Args:
        user_id: JID do WhatsApp (U7)
        shop_uid: UID da loja (U7)
        loja_id: ID da loja (legado)
        janela_execucao: Janela específica (None = janela atual)
    
    Returns:
        Número de locks removidos
    """
    init_bot_state_db()
    
    if janela_execucao is None:
        from shopee_core.sentinel_whatsapp_service import generate_janela_execucao
        janela_execucao = generate_janela_execucao()
    
    with get_conn() as conn:
        if user_id and shop_uid:
            # Novo formato (U7)
            cur = conn.execute(
                """
                DELETE FROM sentinela_locks
                WHERE user_id = ?
                  AND shop_uid = ?
                  AND janela_execucao = ?
                  AND status IN ('timeout', 'error', 'failed', 'cancelled')
                """,
                (user_id, shop_uid, janela_execucao),
            )
        elif loja_id:
            # Formato legado
            cur = conn.execute(
                """
                DELETE FROM sentinela_locks
                WHERE loja_id = ?
                  AND janela_execucao = ?
                  AND status IN ('timeout', 'error', 'failed', 'cancelled')
                """,
                (loja_id, janela_execucao),
            )
        else:
            # Remove todos os locks retryable da janela
            cur = conn.execute(
                """
                DELETE FROM sentinela_locks
                WHERE janela_execucao = ?
                  AND status IN ('timeout', 'error', 'failed', 'cancelled')
                """,
                (janela_execucao,),
            )
        
        conn.commit()
        return cur.rowcount


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
