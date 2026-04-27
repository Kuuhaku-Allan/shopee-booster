"""
shopee_core/sentinel_whatsapp_service.py — Sentinela para WhatsApp
==================================================================
Serviço específico para configurar e executar o Sentinela via WhatsApp.

Funcionalidades:
  - Configuração de loja e keywords via conversa
  - Execução manual do Sentinela
  - Status e controle via comandos
  - Integração com sistema de locks
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("sentinel_whatsapp")

# ── Resolve DB_PATH (igual aos outros serviços) ───────────────────
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


def _init_sentinel_config_table():
    """Cria a tabela de configuração do Sentinela no WhatsApp."""
    with _get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS whatsapp_sentinel_config (
                user_id         TEXT PRIMARY KEY,
                shop_url        TEXT NOT NULL,
                username        TEXT,
                shop_id         TEXT,
                keywords_json   TEXT NOT NULL DEFAULT '[]',
                is_active       BOOLEAN NOT NULL DEFAULT 1,
                interval_minutes INTEGER NOT NULL DEFAULT 360,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
            """
        )


# ══════════════════════════════════════════════════════════════════
# API PÚBLICA
# ══════════════════════════════════════════════════════════════════

def get_sentinel_config(user_id: str) -> Optional[dict]:
    """Retorna a configuração do Sentinela para o usuário."""
    _init_sentinel_config_table()
    
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM whatsapp_sentinel_config WHERE user_id = ?",
            (user_id,)
        ).fetchone()
    
    if not row:
        return None
    
    # Tenta carregar keywords_json como dict (novo formato) ou list (formato legado)
    keywords_json = row["keywords_json"] or "{}"
    try:
        keywords_data = json.loads(keywords_json)
        if isinstance(keywords_data, list):
            # Formato legado: apenas lista de keywords
            keywords = keywords_data
            auto_generated = False
            from_catalog = False
        else:
            # Novo formato: dict com metadados
            keywords = keywords_data.get("keywords", [])
            auto_generated = keywords_data.get("auto_generated", False)
            from_catalog = keywords_data.get("from_catalog", False)
    except:
        keywords = []
        auto_generated = False
        from_catalog = False
    
    return {
        "user_id": row["user_id"],
        "shop_url": row["shop_url"],
        "username": row["username"],
        "shop_id": row["shop_id"],
        "keywords": keywords,
        "is_active": bool(row["is_active"]),
        "interval_minutes": row["interval_minutes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "auto_generated": auto_generated,
        "from_catalog": from_catalog,
    }


def save_sentinel_config(
    user_id: str,
    shop_url: str,
    username: str = "",
    shop_id: str = "",
    keywords: list[str] = None,
    is_active: bool = True,
    interval_minutes: int = 360,
    auto_generated: bool = False,
    from_catalog: bool = False,
):
    """Salva ou atualiza a configuração do Sentinela."""
    _init_sentinel_config_table()
    
    if keywords is None:
        keywords = []
    
    now = datetime.utcnow().isoformat()
    
    # Adiciona metadados extras ao JSON de keywords
    keywords_data = {
        "keywords": keywords,
        "auto_generated": auto_generated,
        "from_catalog": from_catalog,
    }
    
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO whatsapp_sentinel_config 
            (user_id, shop_url, username, shop_id, keywords_json, is_active, interval_minutes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                shop_url = excluded.shop_url,
                username = excluded.username,
                shop_id = excluded.shop_id,
                keywords_json = excluded.keywords_json,
                is_active = excluded.is_active,
                interval_minutes = excluded.interval_minutes,
                updated_at = excluded.updated_at
            """,
            (user_id, shop_url, username, shop_id, json.dumps(keywords_data), 
             is_active, interval_minutes, now, now)
        )


def delete_sentinel_config(user_id: str):
    """Remove a configuração do Sentinela para o usuário."""
    _init_sentinel_config_table()
    
    with _get_conn() as conn:
        conn.execute(
            "DELETE FROM whatsapp_sentinel_config WHERE user_id = ?",
            (user_id,)
        )


def generate_keywords_from_shop(shop_data: dict) -> list[str]:
    """
    Gera keywords automaticamente baseado nos produtos da loja.
    
    Args:
        shop_data: dados da loja retornados por load_shop_from_url()
    
    Returns:
        Lista de keywords para monitoramento
    """
    keywords = set()
    products = shop_data.get("products", [])
    
    # Extrai palavras-chave dos nomes dos produtos
    for product in products[:10]:  # Limita a 10 produtos para não gerar muitas keywords
        name = product.get("name", "").lower()
        
        # Remove caracteres especiais e divide em palavras
        import re
        words = re.findall(r'\b\w+\b', name)
        
        # Filtra palavras relevantes (mínimo 3 caracteres, não números puros)
        relevant_words = [
            word for word in words 
            if len(word) >= 3 and not word.isdigit()
            and word not in {"para", "com", "sem", "por", "kit", "pcs", "und"}
        ]
        
        # Gera combinações de 2-3 palavras
        for i, word in enumerate(relevant_words):
            if i < len(relevant_words) - 1:
                # Combinação de 2 palavras
                combo = f"{word} {relevant_words[i + 1]}"
                keywords.add(combo)
                
                # Combinação de 3 palavras se houver
                if i < len(relevant_words) - 2:
                    combo3 = f"{word} {relevant_words[i + 1]} {relevant_words[i + 2]}"
                    keywords.add(combo3)
    
    # Limita a 20 keywords mais relevantes
    return list(keywords)[:20]


def format_sentinel_status(config: dict) -> str:
    """Formata o status do Sentinela para exibição no WhatsApp."""
    if not config:
        return (
            "🛡️ *Sentinela não configurado*\n\n"
            "Use */sentinela configurar* para começar."
        )
    
    status_emoji = "🟢" if config["is_active"] else "🔴"
    status_text = "Ativo" if config["is_active"] else "Pausado"
    
    interval_hours = config["interval_minutes"] // 60
    interval_text = f"{interval_hours}h" if interval_hours >= 1 else f"{config['interval_minutes']}min"
    
    keywords_preview = config["keywords"][:5]  # Mostra até 5 keywords
    keywords_text = "\n".join(f"• {kw}" for kw in keywords_preview)
    if len(config["keywords"]) > 5:
        keywords_text += f"\n• ... e mais {len(config['keywords']) - 5} keywords"
    
    # Indica origem das keywords se disponível
    keywords_origin = ""
    if config.get("auto_generated"):
        keywords_origin = "\n_🤖 Keywords geradas automaticamente dos produtos_"
    elif config.get("from_catalog"):
        keywords_origin = "\n_📦 Keywords geradas do catálogo importado_"
    
    return (
        f"🛡️ *Status do Sentinela*\n\n"
        f"{status_emoji} Status: *{status_text}*\n"
        f"🏪 Loja: _{config['username'] or 'Carregando...'}_\n"
        f"⏰ Intervalo: {interval_text}\n"
        f"🔍 Keywords monitoradas ({len(config['keywords'])}):\n{keywords_text}{keywords_origin}\n\n"
        f"_Configurado em {config['created_at'][:10]}_"
    )


def format_sentinel_menu() -> str:
    """Retorna o menu principal do Sentinela."""
    return (
        "🛡️ *Sentinela ShopeeBooster*\n\n"
        "Comandos disponíveis:\n\n"
        "*/sentinela configurar* — cadastrar loja e preferências\n"
        "*/sentinela rodar* — fazer uma checagem agora\n"
        "*/sentinela status* — ver monitoramento atual\n"
        "*/sentinela keywords* — atualizar palavras-chave\n"
        "*/sentinela pausar* — pausar alertas automáticos\n"
        "*/sentinela cancelar* — remover configuração atual\n\n"
        "_O Sentinela monitora concorrentes e te avisa sobre mudanças de preços e novos produtos._"
    )


def generate_janela_execucao() -> str:
    """
    Gera identificador único para a janela de execução.
    Formato: YYYY-MM-DD-HH-{uuid_short}
    """
    now = datetime.utcnow()
    date_part = now.strftime("%Y-%m-%d-%H")
    uuid_short = str(uuid.uuid4())[:8]
    return f"{date_part}-{uuid_short}"


def extract_shop_id_from_url(shop_url: str) -> str:
    """
    Extrai shop_id da URL da Shopee.
    
    Exemplos:
        https://shopee.com.br/loja_exemplo → loja_exemplo
        https://shopee.com.br/loja_exemplo?page=1 → loja_exemplo
    """
    import re
    
    # Remove protocolo e domínio
    path = shop_url.replace("https://", "").replace("http://", "")
    if "shopee.com.br/" in path:
        path = path.split("shopee.com.br/", 1)[1]
    
    # Remove parâmetros de query
    shop_id = path.split("?")[0].split("#")[0]
    
    # Remove trailing slash
    shop_id = shop_id.rstrip("/")
    
    return shop_id or "unknown"