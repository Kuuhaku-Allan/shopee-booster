"""
shopee_core/user_config_service.py — Configurações por Usuário do WhatsApp
===========================================================================
Sistema multiusuário para o Bot do WhatsApp.

Funcionalidades:
  - Perfis de usuário por JID do WhatsApp
  - Lojas cadastradas por usuário
  - Secrets criptografados (Gemini API Key, Telegram token/chat_id)
  - Isolamento completo entre usuários
  - Compatibilidade com configs globais legadas

Não quebra o .exe desktop que usa configs globais.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet

log = logging.getLogger("user_config")

# ── Resolve DB_PATH (igual aos outros serviços) ───────────────────
if getattr(sys, "frozen", False):
    _BASE = Path(sys.executable).parent
else:
    _BASE = Path(__file__).resolve().parent.parent

DB_PATH = _BASE / "data" / "bot_state.db"


def _get_conn() -> sqlite3.Connection:
    """Retorna conexão com o banco de dados."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _get_cipher() -> Fernet:
    """
    Retorna cipher Fernet para criptografia de secrets.
    
    Raises:
        ValueError: Se BOT_SECRET_KEY não estiver configurada
    """
    from dotenv import load_dotenv
    
    # Carrega .shopee_config
    config_path = _BASE / ".shopee_config"
    if config_path.exists():
        load_dotenv(config_path)
    
    key = os.getenv("BOT_SECRET_KEY")
    
    if not key:
        raise ValueError(
            "BOT_SECRET_KEY não configurada!\n\n"
            "Para gerar uma chave:\n"
            "  python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"\n\n"
            "Depois adicione ao .shopee_config:\n"
            "  BOT_SECRET_KEY=sua_chave_aqui"
        )
    
    try:
        return Fernet(key.encode())
    except Exception as e:
        raise ValueError(f"BOT_SECRET_KEY inválida: {e}")


def init_user_tables():
    """Cria as tabelas de usuários se não existirem."""
    with _get_conn() as conn:
        # Tabela de perfis
        conn.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_user_profiles (
                user_id TEXT PRIMARY KEY,
                display_name TEXT,
                active_shop_uid TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # Tabela de lojas
        conn.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_user_shops (
                shop_uid TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                shop_url TEXT NOT NULL,
                username TEXT NOT NULL,
                shop_id TEXT,
                display_name TEXT,
                is_active INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES whatsapp_user_profiles(user_id)
            )
        """)
        
        # Tabela de secrets
        conn.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_user_secrets (
                user_id TEXT NOT NULL,
                secret_name TEXT NOT NULL,
                encrypted_value TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, secret_name),
                FOREIGN KEY (user_id) REFERENCES whatsapp_user_profiles(user_id)
            )
        """)
        
        # Índices para performance
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_shops_user_id 
            ON whatsapp_user_shops(user_id)
        """)
        
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_shops_active 
            ON whatsapp_user_shops(user_id, is_active)
        """)
        
        log.info("[USER_CONFIG] Tabelas inicializadas")


# ══════════════════════════════════════════════════════════════════
# PERFIS DE USUÁRIO
# ══════════════════════════════════════════════════════════════════

def get_or_create_profile(user_id: str) -> dict:
    """
    Obtém ou cria perfil do usuário.
    
    Args:
        user_id: JID do WhatsApp (ex: 5511988600050@s.whatsapp.net)
    
    Returns:
        Dict com dados do perfil
    """
    init_user_tables()
    
    with _get_conn() as conn:
        # Tenta buscar
        row = conn.execute(
            "SELECT * FROM whatsapp_user_profiles WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        
        if row:
            return dict(row)
        
        # Cria novo perfil
        now = datetime.utcnow().isoformat()
        conn.execute(
            """
            INSERT INTO whatsapp_user_profiles 
            (user_id, created_at, updated_at)
            VALUES (?, ?, ?)
            """,
            (user_id, now, now)
        )
        
        log.info(f"[USER_CONFIG] Perfil criado: user_id={user_id}")
        
        return {
            "user_id": user_id,
            "display_name": None,
            "active_shop_uid": None,
            "created_at": now,
            "updated_at": now,
        }


def update_profile(user_id: str, display_name: str = None, active_shop_uid: str = None):
    """
    Atualiza perfil do usuário.
    
    Args:
        user_id: JID do WhatsApp
        display_name: Nome opcional do usuário
        active_shop_uid: UID da loja ativa
    """
    init_user_tables()
    
    now = datetime.utcnow().isoformat()
    
    with _get_conn() as conn:
        updates = ["updated_at = ?"]
        params = [now]
        
        if display_name is not None:
            updates.append("display_name = ?")
            params.append(display_name)
        
        if active_shop_uid is not None:
            updates.append("active_shop_uid = ?")
            params.append(active_shop_uid)
        
        params.append(user_id)
        
        conn.execute(
            f"UPDATE whatsapp_user_profiles SET {', '.join(updates)} WHERE user_id = ?",
            params
        )
        
        log.info(f"[USER_CONFIG] Perfil atualizado: user_id={user_id}")


# ══════════════════════════════════════════════════════════════════
# LOJAS
# ══════════════════════════════════════════════════════════════════

def add_shop(
    user_id: str,
    shop_url: str,
    username: str,
    shop_id: str = None,
    display_name: str = None,
    set_as_active: bool = True
) -> str:
    """
    Adiciona loja para o usuário.
    
    Args:
        user_id: JID do WhatsApp
        shop_url: URL completa da loja
        username: Nome da loja (extraído da URL)
        shop_id: ID numérico da Shopee (opcional)
        display_name: Nome customizado (opcional)
        set_as_active: Se True, define como loja ativa
    
    Returns:
        shop_uid gerado
    """
    init_user_tables()
    get_or_create_profile(user_id)
    
    shop_uid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    
    with _get_conn() as conn:
        # Se set_as_active, desativa outras lojas
        if set_as_active:
            conn.execute(
                "UPDATE whatsapp_user_shops SET is_active = 0 WHERE user_id = ?",
                (user_id,)
            )
        
        # Insere nova loja
        conn.execute(
            """
            INSERT INTO whatsapp_user_shops
            (shop_uid, user_id, shop_url, username, shop_id, display_name, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (shop_uid, user_id, shop_url, username, shop_id, display_name, 
             1 if set_as_active else 0, now, now)
        )
        
        # Atualiza perfil (dentro da mesma conexão)
        if set_as_active:
            conn.execute(
                "UPDATE whatsapp_user_profiles SET active_shop_uid = ?, updated_at = ? WHERE user_id = ?",
                (shop_uid, now, user_id)
            )
        
        log.info(f"[USER_CONFIG] Loja adicionada: user_id={user_id} shop={username} uid={shop_uid}")
        
        return shop_uid


def list_shops(user_id: str) -> list[dict]:
    """
    Lista lojas do usuário.
    
    Args:
        user_id: JID do WhatsApp
    
    Returns:
        Lista de dicts com dados das lojas
    """
    init_user_tables()
    
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM whatsapp_user_shops 
            WHERE user_id = ? 
            ORDER BY is_active DESC, created_at DESC
            """,
            (user_id,)
        ).fetchall()
        
        return [dict(row) for row in rows]


def get_active_shop(user_id: str) -> Optional[dict]:
    """
    Retorna loja ativa do usuário.
    
    Args:
        user_id: JID do WhatsApp
    
    Returns:
        Dict com dados da loja ou None
    """
    init_user_tables()
    
    with _get_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM whatsapp_user_shops 
            WHERE user_id = ? AND is_active = 1
            LIMIT 1
            """,
            (user_id,)
        ).fetchone()
        
        return dict(row) if row else None


def set_active_shop(user_id: str, shop_uid: str) -> bool:
    """
    Define loja ativa do usuário.
    
    Args:
        user_id: JID do WhatsApp
        shop_uid: UID da loja
    
    Returns:
        True se alterou com sucesso
    """
    init_user_tables()
    
    now = datetime.utcnow().isoformat()
    
    with _get_conn() as conn:
        # Verifica se loja existe e pertence ao usuário
        row = conn.execute(
            "SELECT 1 FROM whatsapp_user_shops WHERE shop_uid = ? AND user_id = ?",
            (shop_uid, user_id)
        ).fetchone()
        
        if not row:
            log.warning(f"[USER_CONFIG] Loja não encontrada: uid={shop_uid} user={user_id}")
            return False
        
        # Desativa outras lojas
        conn.execute(
            "UPDATE whatsapp_user_shops SET is_active = 0 WHERE user_id = ?",
            (user_id,)
        )
        
        # Ativa loja selecionada
        conn.execute(
            "UPDATE whatsapp_user_shops SET is_active = 1 WHERE shop_uid = ?",
            (shop_uid,)
        )
        
        # Atualiza perfil (dentro da mesma conexão)
        conn.execute(
            "UPDATE whatsapp_user_profiles SET active_shop_uid = ?, updated_at = ? WHERE user_id = ?",
            (shop_uid, now, user_id)
        )
        
        log.info(f"[USER_CONFIG] Loja ativada: user_id={user_id} uid={shop_uid}")
        return True


def remove_shop(user_id: str, shop_uid: str) -> bool:
    """
    Remove loja do usuário.
    
    Args:
        user_id: JID do WhatsApp
        shop_uid: UID da loja
    
    Returns:
        True se removeu com sucesso
    """
    init_user_tables()
    
    now = datetime.utcnow().isoformat()
    
    with _get_conn() as conn:
        # Verifica se loja existe e pertence ao usuário
        row = conn.execute(
            "SELECT is_active FROM whatsapp_user_shops WHERE shop_uid = ? AND user_id = ?",
            (shop_uid, user_id)
        ).fetchone()
        
        if not row:
            log.warning(f"[USER_CONFIG] Loja não encontrada: uid={shop_uid} user={user_id}")
            return False
        
        was_active = bool(row["is_active"])
        
        # Remove loja
        conn.execute(
            "DELETE FROM whatsapp_user_shops WHERE shop_uid = ?",
            (shop_uid,)
        )
        
        # Se era a loja ativa, limpa do perfil (dentro da mesma conexão)
        if was_active:
            conn.execute(
                "UPDATE whatsapp_user_profiles SET active_shop_uid = NULL, updated_at = ? WHERE user_id = ?",
                (now, user_id)
            )
        
        log.info(f"[USER_CONFIG] Loja removida: user_id={user_id} uid={shop_uid}")
        return True


# ══════════════════════════════════════════════════════════════════
# SECRETS (CRIPTOGRAFADOS)
# ══════════════════════════════════════════════════════════════════

def save_secret(user_id: str, secret_name: str, value: str):
    """
    Salva secret criptografado.
    
    Args:
        user_id: JID do WhatsApp
        secret_name: Nome do secret ('gemini_api_key', 'telegram_token', 'telegram_chat_id')
        value: Valor a criptografar
    
    Raises:
        ValueError: Se BOT_SECRET_KEY não estiver configurada
    """
    init_user_tables()
    get_or_create_profile(user_id)
    
    cipher = _get_cipher()
    encrypted = cipher.encrypt(value.encode()).decode()
    
    now = datetime.utcnow().isoformat()
    
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO whatsapp_user_secrets 
            (user_id, secret_name, encrypted_value, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, secret_name) DO UPDATE SET
                encrypted_value = excluded.encrypted_value,
                updated_at = excluded.updated_at
            """,
            (user_id, secret_name, encrypted, now, now)
        )
        
        log.info(f"[USER_CONFIG] Secret salvo: user_id={user_id} name={secret_name}")


def get_secret(user_id: str, secret_name: str) -> Optional[str]:
    """
    Recupera secret descriptografado.
    
    Args:
        user_id: JID do WhatsApp
        secret_name: Nome do secret
    
    Returns:
        Valor descriptografado ou None
    
    Raises:
        ValueError: Se BOT_SECRET_KEY não estiver configurada ou for inválida
    """
    init_user_tables()
    
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT encrypted_value FROM whatsapp_user_secrets WHERE user_id = ? AND secret_name = ?",
            (user_id, secret_name)
        ).fetchone()
        
        if not row:
            return None
        
        cipher = _get_cipher()
        
        try:
            decrypted = cipher.decrypt(row["encrypted_value"].encode()).decode()
            return decrypted
        except Exception as e:
            log.error(f"[USER_CONFIG] Erro ao descriptografar secret: {e}")
            raise ValueError(f"Erro ao descriptografar {secret_name}. BOT_SECRET_KEY pode ter mudado.")


def has_secret(user_id: str, secret_name: str) -> bool:
    """
    Verifica se usuário tem secret configurado.
    
    Args:
        user_id: JID do WhatsApp
        secret_name: Nome do secret
    
    Returns:
        True se existe
    """
    init_user_tables()
    
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM whatsapp_user_secrets WHERE user_id = ? AND secret_name = ?",
            (user_id, secret_name)
        ).fetchone()
        
        return bool(row)


def delete_secret(user_id: str, secret_name: str) -> bool:
    """
    Remove secret do usuário.
    
    Args:
        user_id: JID do WhatsApp
        secret_name: Nome do secret
    
    Returns:
        True se removeu
    """
    init_user_tables()
    
    with _get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM whatsapp_user_secrets WHERE user_id = ? AND secret_name = ?",
            (user_id, secret_name)
        )
        
        deleted = cursor.rowcount > 0
        
        if deleted:
            log.info(f"[USER_CONFIG] Secret removido: user_id={user_id} name={secret_name}")
        
        return deleted


def mask_secret(value: str, show_last: int = 4) -> str:
    """
    Mascara secret para exibição.
    
    Args:
        value: Valor a mascarar
        show_last: Quantos caracteres finais mostrar
    
    Returns:
        String mascarada (ex: ****abcd)
    """
    if not value:
        return ""
    
    # Se o valor é muito curto (menos que 4 + show_last), mascara tudo
    min_length = 4 + show_last
    if len(value) < min_length:
        return "*" * len(value)
    
    # Mostra sempre 4 asteriscos + últimos N caracteres
    return "*" * 4 + value[-show_last:]


# ══════════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════════

def get_user_config_summary(user_id: str) -> dict:
    """
    Retorna resumo das configurações do usuário.
    
    Args:
        user_id: JID do WhatsApp
    
    Returns:
        Dict com resumo completo
    """
    init_user_tables()
    
    profile = get_or_create_profile(user_id)
    shops = list_shops(user_id)
    active_shop = get_active_shop(user_id)
    
    # Verifica secrets (sem descriptografar)
    secrets_status = {
        "gemini_api_key": has_secret(user_id, "gemini_api_key"),
        "telegram_token": has_secret(user_id, "telegram_token"),
        "telegram_chat_id": has_secret(user_id, "telegram_chat_id"),
    }
    
    return {
        "user_id": user_id,
        "display_name": profile.get("display_name"),
        "shops_count": len(shops),
        "active_shop": active_shop,
        "secrets": secrets_status,
        "created_at": profile.get("created_at"),
    }


def delete_all_user_data(user_id: str) -> dict:
    """
    Remove TODOS os dados do usuário.
    
    Args:
        user_id: JID do WhatsApp
    
    Returns:
        Dict com contadores do que foi removido
    """
    init_user_tables()
    
    with _get_conn() as conn:
        # Conta antes de remover
        shops_count = conn.execute(
            "SELECT COUNT(*) as c FROM whatsapp_user_shops WHERE user_id = ?",
            (user_id,)
        ).fetchone()["c"]
        
        secrets_count = conn.execute(
            "SELECT COUNT(*) as c FROM whatsapp_user_secrets WHERE user_id = ?",
            (user_id,)
        ).fetchone()["c"]
        
        # Remove tudo
        conn.execute("DELETE FROM whatsapp_user_secrets WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM whatsapp_user_shops WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM whatsapp_user_profiles WHERE user_id = ?", (user_id,))
        
        log.info(f"[USER_CONFIG] Todos os dados removidos: user_id={user_id}")
        
        return {
            "shops_removed": shops_count,
            "secrets_removed": secrets_count,
        }
