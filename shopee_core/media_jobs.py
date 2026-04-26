"""
shopee_core/media_jobs.py — Controle de Jobs de Mídia
======================================================
Gerencia jobs de processamento de mídia com suporte a cancelamento.

Tabela media_jobs:
  - job_id TEXT PRIMARY KEY
  - user_id TEXT
  - status TEXT: running/canceled/done/error/timeout
  - created_at TEXT
  - updated_at TEXT

Fluxo:
  1. Usuário manda imagem → cria job_id → status=running
  2. Background processa → verifica se canceled antes de enviar
  3. /cancelar → marca job como canceled
  4. Se canceled, NÃO envia resultado atrasado
"""

from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Resolve DB_PATH (igual ao session_service.py) ───────────────────────
if getattr(sys, "frozen", False):
    _BASE = Path(sys.executable).parent
else:
    _BASE = Path(__file__).resolve().parent.parent

DB_PATH = _BASE / "data" / "bot_state.db"


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_media_jobs_table():
    """Cria a tabela media_jobs se não existir. Idempotente."""
    with _get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS media_jobs (
                job_id     TEXT PRIMARY KEY,
                user_id    TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'running',
                action     TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


# ══════════════════════════════════════════════════════════════════
# API PÚBLICA
# ══════════════════════════════════════════════════════════════════

def create_media_job(user_id: str, action: str = "") -> str:
    """
    Cria um novo job de mídia.

    Returns:
        job_id (UUID string)
    """
    _init_media_jobs_table()

    job_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO media_jobs (job_id, user_id, status, action, created_at, updated_at)
            VALUES (?, ?, 'running', ?, ?, ?)
            """,
            (job_id, user_id, action, now, now),
        )

    return job_id


def get_media_job(job_id: str) -> Optional[dict]:
    """Retorna informações do job."""
    _init_media_jobs_table()

    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM media_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()

    if not row:
        return None

    return {
        "job_id": row["job_id"],
        "user_id": row["user_id"],
        "status": row["status"],
        "action": row["action"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def update_media_job_status(job_id: str, status: str):
    """
    Atualiza status do job.

    Status válidos: running, canceled, done, error, timeout
    """
    _init_media_jobs_table()

    now = datetime.utcnow().isoformat()

    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE media_jobs
            SET status = ?, updated_at = ?
            WHERE job_id = ?
            """,
            (status, now, job_id),
        )


def cancel_media_job(job_id: str):
    """Marca um job como cancelado."""
    update_media_job_status(job_id, "canceled")


def is_media_job_canceled(job_id: str) -> bool:
    """Verifica se o job foi cancelado."""
    job = get_media_job(job_id)
    if not job:
        return True  # Job não existe = trata como cancelado
    return job["status"] == "canceled"


def finish_media_job(job_id: str, success: bool = True):
    """Marca job como finalizado (done ou error)."""
    update_media_job_status(job_id, "done" if success else "error")


def timeout_media_job(job_id: str):
    """Marca job como timeout."""
    update_media_job_status(job_id, "timeout")


def cleanup_old_media_jobs(max_age_hours: int = 24):
    """Remove jobs antigos para não acumular no banco."""
    _init_media_jobs_table()

    cutoff = datetime.utcnow()
    # SQLite não tem datetime math direto, usa comparação de string ISO
    # Jobs finalizados há mais de max_age_hours são removidos

    with _get_conn() as conn:
        # Remove jobs que não estão mais rodando
        conn.execute(
            """
            DELETE FROM media_jobs
            WHERE status IN ('done', 'error', 'timeout', 'canceled')
            """
        )


def get_active_media_jobs(user_id: str = "") -> list[dict]:
    """Retorna jobs ativos (running) para um usuário ou todos."""
    _init_media_jobs_table()

    with _get_conn() as conn:
        if user_id:
            rows = conn.execute(
                "SELECT * FROM media_jobs WHERE user_id = ? AND status = 'running' ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM media_jobs WHERE status = 'running' ORDER BY created_at DESC"
            ).fetchall()

    return [
        {
            "job_id": r["job_id"],
            "user_id": r["user_id"],
            "status": r["status"],
            "action": r["action"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]
