"""
shopee_core/session_service.py — Estado conversacional do WhatsApp Bot
=======================================================================
Armazena em qual etapa do fluxo cada usuário está, e os dados associados
(ex: lista de produtos carregada, URL da loja, produto selecionado).

Usa o mesmo banco SQLite do bot_state.py (data/bot_state.db) para evitar
proliferação de arquivos.

Estados definidos:
    idle                  — sem fluxo ativo
    awaiting_shop_url     — esperando o usuário mandar a URL da loja
    awaiting_product_index — loja carregada, esperando o número do produto
    awaiting_edit_image   — imagem ativa, esperando instrução de edição
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


# ── Resolve DB_PATH (igual ao bot_state.py) ───────────────────────
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


def _init_session_table():
    """Cria a tabela de sessões se não existir. Idempotente."""
    with _get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS whatsapp_sessions (
                user_id    TEXT PRIMARY KEY,
                state      TEXT NOT NULL DEFAULT 'idle',
                data_json  TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL
            )
            """
        )


# ══════════════════════════════════════════════════════════════════
# API PÚBLICA
# ══════════════════════════════════════════════════════════════════

def get_session(user_id: str) -> dict:
    """
    Retorna a sessão atual do usuário.

    Returns dict com:
        user_id (str)
        state   (str)  — estado atual do fluxo
        data    (dict) — dados associados ao estado
    """
    _init_session_table()

    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM whatsapp_sessions WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    if not row:
        return {"user_id": user_id, "state": "idle", "data": {}}

    return {
        "user_id": row["user_id"],
        "state": row["state"],
        "data": json.loads(row["data_json"] or "{}"),
    }


def save_session(user_id: str, state: str, data: dict):
    """
    Salva ou atualiza o estado da sessão do usuário.

    Args:
        user_id — JID do WhatsApp (ex: "5511999999999@s.whatsapp.net")
        state   — Novo estado do fluxo
        data    — Dados associados (serializados como JSON)
    """
    _init_session_table()

    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO whatsapp_sessions (user_id, state, data_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                state      = excluded.state,
                data_json  = excluded.data_json,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                state,
                json.dumps(data, ensure_ascii=False),
                datetime.utcnow().isoformat(),
            ),
        )


def clear_session(user_id: str):
    """
    Remove a sessão do usuário (reset completo).
    Usado pelo comando /reset ou após conclusão de um fluxo.
    """
    _init_session_table()

    with _get_conn() as conn:
        conn.execute(
            "DELETE FROM whatsapp_sessions WHERE user_id = ?",
            (user_id,),
        )


def get_all_active_sessions() -> list[dict]:
    """
    Retorna todas as sessões ativas (state != 'idle').
    Útil para diagnóstico e monitoramento.
    """
    _init_session_table()

    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM whatsapp_sessions WHERE state != 'idle' ORDER BY updated_at DESC"
        ).fetchall()

    return [
        {
            "user_id": r["user_id"],
            "state": r["state"],
            "data": json.loads(r["data_json"] or "{}"),
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]
