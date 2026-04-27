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
    """Cria a tabela de configuração do Sentinela no WhatsApp (U7), com migração suave."""
    with _get_conn() as conn:
        # Detecta schema existente para migração
        try:
            cols = conn.execute("PRAGMA table_info(whatsapp_sentinel_config)").fetchall()
            col_names = {c["name"] for c in cols} if cols else set()
        except Exception:
            col_names = set()

        # Se existe tabela em formato legado (sem shop_uid/config_id), migra para v2
        if col_names and ("shop_uid" not in col_names or "config_id" not in col_names):
            log.info("[SENTINEL] Migrando whatsapp_sentinel_config para schema U7 (v2)")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS whatsapp_sentinel_config_v2 (
                    config_id        TEXT PRIMARY KEY,
                    user_id          TEXT NOT NULL,
                    shop_uid         TEXT NOT NULL,
                    shop_url         TEXT NOT NULL,
                    username         TEXT,
                    shop_id          TEXT,
                    keywords_json    TEXT NOT NULL DEFAULT '[]',
                    keyword_source   TEXT NOT NULL DEFAULT 'manual',
                    is_active        BOOLEAN NOT NULL DEFAULT 1,
                    interval_minutes INTEGER NOT NULL DEFAULT 360,
                    created_at       TEXT NOT NULL,
                    updated_at       TEXT NOT NULL,
                    UNIQUE(user_id, shop_uid)
                )
                """
            )

            # Copia o que der do legado (assume 1 config por user) para shop_uid='legacy'
            try:
                legacy_rows = conn.execute("SELECT * FROM whatsapp_sentinel_config").fetchall()
            except Exception:
                legacy_rows = []

            for r in legacy_rows:
                # Alguns legados tinham keywords_json como dict; mantemos e normalizamos depois no getter.
                conn.execute(
                    """
                    INSERT OR IGNORE INTO whatsapp_sentinel_config_v2
                        (config_id, user_id, shop_uid, shop_url, username, shop_id,
                         keywords_json, keyword_source, is_active, interval_minutes, created_at, updated_at)
                    VALUES
                        (?, ?, 'legacy', ?, ?, ?, ?, 'manual', ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        r["user_id"],
                        (r["shop_url"] if "shop_url" in col_names else "") or "",
                        (r["username"] if "username" in col_names else "") or "",
                        (r["shop_id"] if "shop_id" in col_names else "") or "",
                        (r["keywords_json"] if "keywords_json" in col_names else "[]") or "[]",
                        int(r["is_active"]) if "is_active" in col_names else 1,
                        int(r["interval_minutes"]) if "interval_minutes" in col_names else 360,
                        (r["created_at"] if "created_at" in col_names else datetime.utcnow().isoformat()),
                        (r["updated_at"] if "updated_at" in col_names else datetime.utcnow().isoformat()),
                    ),
                )

            # Troca as tabelas
            conn.execute("DROP TABLE IF EXISTS whatsapp_sentinel_config")
            conn.execute("ALTER TABLE whatsapp_sentinel_config_v2 RENAME TO whatsapp_sentinel_config")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS whatsapp_sentinel_config (
                config_id        TEXT PRIMARY KEY,
                user_id          TEXT NOT NULL,
                shop_uid         TEXT NOT NULL,
                shop_url         TEXT NOT NULL,
                username         TEXT,
                shop_id          TEXT,
                keywords_json    TEXT NOT NULL DEFAULT '[]',
                keyword_source   TEXT NOT NULL DEFAULT 'manual',
                is_active        BOOLEAN NOT NULL DEFAULT 1,
                interval_minutes INTEGER NOT NULL DEFAULT 360,
                created_at       TEXT NOT NULL,
                updated_at       TEXT NOT NULL,
                UNIQUE(user_id, shop_uid)
            )
            """
        )


# ══════════════════════════════════════════════════════════════════
# API PÚBLICA (U7 — Multiusuário)
# ══════════════════════════════════════════════════════════════════

def get_sentinel_config(user_id: str, shop_uid: str = None) -> Optional[dict]:
    """
    Retorna a configuração do Sentinela para o usuário e loja.
    
    Args:
        user_id: JID do WhatsApp
        shop_uid: UID da loja (opcional, usa loja ativa se não fornecido)
    
    Returns:
        Dict com configuração ou None
    """
    _init_sentinel_config_table()
    
    # Se não forneceu shop_uid, busca da loja ativa
    if not shop_uid:
        from shopee_core.user_config_service import get_active_shop
        active_shop = get_active_shop(user_id)
        if not active_shop:
            return None
        shop_uid = active_shop.get("shop_uid")
    
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM whatsapp_sentinel_config WHERE user_id = ? AND shop_uid = ?",
            (user_id, shop_uid)
        ).fetchone()
    
    if not row:
        return None
    
    # Tenta carregar keywords_json
    keywords_json = row["keywords_json"] or "[]"
    try:
        keywords = json.loads(keywords_json)
        if not isinstance(keywords, list):
            keywords = []
    except:
        keywords = []
    
    return {
        "config_id": row["config_id"],
        "user_id": row["user_id"],
        "shop_uid": row["shop_uid"],
        "shop_url": row["shop_url"],
        "username": row["username"],
        "shop_id": row["shop_id"],
        "keywords": keywords,
        "keyword_source": row["keyword_source"],
        "is_active": bool(row["is_active"]),
        "interval_minutes": row["interval_minutes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def save_sentinel_config(
    user_id: str,
    shop_uid: str,
    shop_url: str,
    username: str = "",
    shop_id: str = "",
    keywords: list[str] = None,
    keyword_source: str = "manual",
    is_active: bool = True,
    interval_minutes: int = 360,
):
    """
    Salva ou atualiza a configuração do Sentinela.
    
    Args:
        user_id: JID do WhatsApp
        shop_uid: UID da loja
        shop_url: URL da loja
        username: Nome da loja
        shop_id: ID numérico da Shopee
        keywords: Lista de keywords para monitoramento
        keyword_source: Origem das keywords (catalog, scraping, manual)
        is_active: Se o Sentinela está ativo
        interval_minutes: Intervalo entre execuções
    """
    _init_sentinel_config_table()
    
    if keywords is None:
        keywords = []
    
    config_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO whatsapp_sentinel_config 
            (config_id, user_id, shop_uid, shop_url, username, shop_id, keywords_json, keyword_source, is_active, interval_minutes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, shop_uid) DO UPDATE SET
                shop_url = excluded.shop_url,
                username = excluded.username,
                shop_id = excluded.shop_id,
                keywords_json = excluded.keywords_json,
                keyword_source = excluded.keyword_source,
                is_active = excluded.is_active,
                interval_minutes = excluded.interval_minutes,
                updated_at = excluded.updated_at
            """,
            (config_id, user_id, shop_uid, shop_url, username, shop_id, 
             json.dumps(keywords), keyword_source, is_active, interval_minutes, now, now)
        )
    
    log.info(f"[SENTINEL] Config salva: user={user_id} shop={username} keywords={len(keywords)} source={keyword_source}")


def delete_sentinel_config(user_id: str, shop_uid: str = None):
    """
    Remove a configuração do Sentinela para o usuário e loja.
    
    Args:
        user_id: JID do WhatsApp
        shop_uid: UID da loja (opcional, usa loja ativa se não fornecido)
    """
    _init_sentinel_config_table()
    
    # Se não forneceu shop_uid, busca da loja ativa
    if not shop_uid:
        from shopee_core.user_config_service import get_active_shop
        active_shop = get_active_shop(user_id)
        if not active_shop:
            return
        shop_uid = active_shop.get("shop_uid")
    
    with _get_conn() as conn:
        conn.execute(
            "DELETE FROM whatsapp_sentinel_config WHERE user_id = ? AND shop_uid = ?",
            (user_id, shop_uid)
        )
    
    log.info(f"[SENTINEL] Config removida: user={user_id} shop_uid={shop_uid}")


def update_sentinel_keywords(user_id: str, shop_uid: str, keywords: list[str], keyword_source: str = "manual"):
    """
    Atualiza apenas as keywords do Sentinela.
    
    Args:
        user_id: JID do WhatsApp
        shop_uid: UID da loja
        keywords: Nova lista de keywords
        keyword_source: Origem das keywords
    """
    _init_sentinel_config_table()
    
    now = datetime.utcnow().isoformat()
    
    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE whatsapp_sentinel_config
            SET keywords_json = ?, keyword_source = ?, updated_at = ?
            WHERE user_id = ? AND shop_uid = ?
            """,
            (json.dumps(keywords), keyword_source, now, user_id, shop_uid)
        )
    
    log.info(f"[SENTINEL] Keywords atualizadas: user={user_id} shop_uid={shop_uid} count={len(keywords)}")


def pause_sentinel(user_id: str, shop_uid: str = None):
    """
    Pausa o Sentinela (is_active=False).
    
    Args:
        user_id: JID do WhatsApp
        shop_uid: UID da loja (opcional, usa loja ativa se não fornecido)
    """
    _init_sentinel_config_table()
    
    if not shop_uid:
        from shopee_core.user_config_service import get_active_shop
        active_shop = get_active_shop(user_id)
        if not active_shop:
            return
        shop_uid = active_shop.get("shop_uid")
    
    now = datetime.utcnow().isoformat()
    
    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE whatsapp_sentinel_config
            SET is_active = 0, updated_at = ?
            WHERE user_id = ? AND shop_uid = ?
            """,
            (now, user_id, shop_uid)
        )
    
    log.info(f"[SENTINEL] Pausado: user={user_id} shop_uid={shop_uid}")


def resume_sentinel(user_id: str, shop_uid: str = None):
    """
    Retoma o Sentinela (is_active=True).
    
    Args:
        user_id: JID do WhatsApp
        shop_uid: UID da loja (opcional, usa loja ativa se não fornecido)
    """
    _init_sentinel_config_table()
    
    if not shop_uid:
        from shopee_core.user_config_service import get_active_shop
        active_shop = get_active_shop(user_id)
        if not active_shop:
            return
        shop_uid = active_shop.get("shop_uid")
    
    now = datetime.utcnow().isoformat()
    
    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE whatsapp_sentinel_config
            SET is_active = 1, updated_at = ?
            WHERE user_id = ? AND shop_uid = ?
            """,
            (now, user_id, shop_uid)
        )
    
    log.info(f"[SENTINEL] Retomado: user={user_id} shop_uid={shop_uid}")


def generate_keywords_from_products(products: list[dict], max_keywords: int = 15) -> list[str]:
    """
    Gera keywords automaticamente baseado em uma lista de produtos.
    
    Args:
        products: Lista de produtos (de scraping ou catálogo)
        max_keywords: Número máximo de keywords a gerar
    
    Returns:
        Lista de keywords para monitoramento
    """
    keywords = set()
    
    # Extrai palavras-chave dos nomes dos produtos
    for product in products[:20]:  # Limita a 20 produtos para análise
        name = product.get("name", "").lower()
        
        # Remove caracteres especiais e divide em palavras
        import re
        words = re.findall(r'\b\w+\b', name)
        
        # Filtra palavras relevantes (mínimo 3 caracteres, não números puros)
        stopwords = {
            "para", "com", "sem", "por", "kit", "pcs", "und", "unidade",
            "peça", "peca", "conjunto", "pack", "novo", "nova", "original",
            "gratis", "frete", "envio", "entrega", "promocao", "oferta"
        }
        
        relevant_words = [
            word for word in words 
            if len(word) >= 3 
            and not word.isdigit()
            and word not in stopwords
        ]
        
        # Gera combinações de 2-3 palavras
        for i, word in enumerate(relevant_words):
            if i < len(relevant_words) - 1:
                # Combinação de 2 palavras
                combo = f"{word} {relevant_words[i + 1]}"
                if len(combo) <= 50:  # Limita tamanho
                    keywords.add(combo)
                
                # Combinação de 3 palavras se houver
                if i < len(relevant_words) - 2:
                    combo3 = f"{word} {relevant_words[i + 1]} {relevant_words[i + 2]}"
                    if len(combo3) <= 50:
                        keywords.add(combo3)
    
    # Ordena por frequência (palavras que aparecem em mais produtos)
    # e retorna as mais relevantes
    keyword_list = list(keywords)
    
    # Se tiver muitas keywords, prioriza as mais curtas (mais genéricas)
    if len(keyword_list) > max_keywords:
        keyword_list.sort(key=lambda x: (len(x.split()), len(x)))
    
    return keyword_list[:max_keywords]


def generate_keywords_from_shop(shop_data: dict) -> list[str]:
    """
    Gera keywords automaticamente baseado nos produtos da loja.
    
    Args:
        shop_data: dados da loja retornados por load_shop_from_url()
    
    Returns:
        Lista de keywords para monitoramento
    """
    products = shop_data.get("products", [])
    return generate_keywords_from_products(products, max_keywords=15)


def generate_keywords_from_catalog(user_id: str, shop_uid: str) -> list[str]:
    """
    Gera keywords automaticamente baseado no catálogo importado.
    
    Args:
        user_id: JID do WhatsApp
        shop_uid: UID da loja
    
    Returns:
        Lista de keywords para monitoramento
    """
    from shopee_core.catalog_service import get_catalog, get_catalog_products
    
    catalog = get_catalog(user_id, shop_uid)
    if not catalog:
        return []
    
    products = get_catalog_products(catalog["catalog_id"])
    return generate_keywords_from_products(products, max_keywords=15)


def format_sentinel_status(config: dict, telegram_configured: bool = False) -> str:
    """
    Formata o status do Sentinela para exibição no WhatsApp.
    
    Args:
        config: Configuração do Sentinela
        telegram_configured: Se o usuário tem Telegram configurado
    
    Returns:
        Mensagem formatada
    """
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
    
    # Indica origem das keywords
    source_map = {
        "catalog": "📦 catálogo importado",
        "scraping": "🌐 scraping público",
        "manual": "✍️ inseridas manualmente",
    }
    keywords_origin = source_map.get(config.get("keyword_source", "manual"), "manual")
    
    # Status do Telegram
    telegram_status = "✅ Configurado" if telegram_configured else "⚠️ Não configurado"
    telegram_note = "" if telegram_configured else "\n_Use /telegram configurar para receber relatórios completos_"
    
    return (
        f"🛡️ *Status do Sentinela*\n\n"
        f"{status_emoji} Status: *{status_text}*\n"
        f"🏪 Loja: *{config['username'] or 'Carregando...'}*\n"
        f"⏰ Intervalo: {interval_text}\n"
        f"📢 Telegram: {telegram_status}{telegram_note}\n\n"
        f"🔍 *Keywords monitoradas ({len(config['keywords'])}):*\n{keywords_text}\n"
        f"_Origem: {keywords_origin}_\n\n"
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
    Formato: YYYY-MM-DD-HH

    Importante (U7):
    Este identificador NÃO deve ter UUID aleatório, pois o lock precisa
    deduplicar execuções dentro da mesma janela de tempo.
    """
    now = datetime.utcnow()
    return now.strftime("%Y-%m-%d-%H")


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