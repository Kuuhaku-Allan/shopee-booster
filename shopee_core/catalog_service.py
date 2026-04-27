"""
shopee_core/catalog_service.py — Gerenciamento de Catálogos por Loja
======================================================================
Sistema de importação e armazenamento de catálogos vinculados à loja ativa.

Funcionalidades:
  - Importar catálogo XLSX/XLS/CSV do Seller Center
  - Salvar catálogo vinculado a user_id + shop_uid
  - Buscar catálogo da loja ativa
  - Remover catálogo de loja específica
  - Isolamento completo entre lojas

Não permite catálogo "solto" - sempre vinculado a uma loja.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
import json

log = logging.getLogger("catalog")

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


def init_catalog_tables():
    """Cria as tabelas de catálogos se não existirem."""
    with _get_conn() as conn:
        # Tabela de catálogos
        conn.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_shop_catalogs (
                catalog_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                shop_uid TEXT NOT NULL,
                shop_url TEXT NOT NULL,
                username TEXT NOT NULL,
                products_count INTEGER DEFAULT 0,
                source_type TEXT DEFAULT 'seller_center',
                imported_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, shop_uid)
            )
        """)
        
        # Tabela de produtos do catálogo
        conn.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_catalog_products (
                product_id TEXT PRIMARY KEY,
                catalog_id TEXT NOT NULL,
                itemid TEXT,
                shopid TEXT,
                name TEXT NOT NULL,
                price REAL DEFAULT 0,
                stock INTEGER DEFAULT 0,
                category TEXT,
                description TEXT,
                images TEXT,
                product_data TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (catalog_id) REFERENCES whatsapp_shop_catalogs(catalog_id) ON DELETE CASCADE
            )
        """)
        
        # Índices para performance
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_catalog_user_shop 
            ON whatsapp_shop_catalogs(user_id, shop_uid)
        """)
        
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_products_catalog 
            ON whatsapp_catalog_products(catalog_id)
        """)
        
        log.info("[CATALOG] Tabelas inicializadas")


# ══════════════════════════════════════════════════════════════════
# SALVAR CATÁLOGO
# ══════════════════════════════════════════════════════════════════

def save_catalog(
    user_id: str,
    shop_uid: str,
    shop_url: str,
    username: str,
    products: list[dict],
    source_type: str = "seller_center"
) -> dict:
    """
    Salva catálogo vinculado a uma loja específica.
    
    Args:
        user_id: JID do WhatsApp
        shop_uid: UID da loja
        shop_url: URL da loja
        username: Nome da loja
        products: Lista de produtos
        source_type: Tipo de fonte (seller_center, scraping, etc)
    
    Returns:
        Dict com catalog_id e contadores
    """
    init_catalog_tables()
    
    import uuid
    
    catalog_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    
    with _get_conn() as conn:
        # Remove catálogo anterior desta loja (se existir)
        conn.execute(
            "DELETE FROM whatsapp_shop_catalogs WHERE user_id = ? AND shop_uid = ?",
            (user_id, shop_uid)
        )
        
        # Insere novo catálogo
        conn.execute(
            """
            INSERT INTO whatsapp_shop_catalogs
            (catalog_id, user_id, shop_uid, shop_url, username, products_count, source_type, imported_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (catalog_id, user_id, shop_uid, shop_url, username, len(products), source_type, now, now)
        )
        
        # Insere produtos
        for product in products:
            product_id = str(uuid.uuid4())
            
            # Serializa dados completos do produto
            product_data = json.dumps(product, ensure_ascii=False)
            
            # Serializa imagens
            images = json.dumps(product.get("images", []), ensure_ascii=False)
            
            conn.execute(
                """
                INSERT INTO whatsapp_catalog_products
                (product_id, catalog_id, itemid, shopid, name, price, stock, category, description, images, product_data, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product_id,
                    catalog_id,
                    product.get("itemid"),
                    product.get("shopid"),
                    product.get("name", ""),
                    product.get("price", 0),
                    product.get("stock", 0),
                    product.get("category", ""),
                    product.get("description", ""),
                    images,
                    product_data,
                    now
                )
            )
        
        log.info(f"[CATALOG] Catálogo salvo: user={user_id} shop={username} products={len(products)}")
        
        return {
            "catalog_id": catalog_id,
            "products_count": len(products),
            "imported_at": now,
        }


# ══════════════════════════════════════════════════════════════════
# BUSCAR CATÁLOGO
# ══════════════════════════════════════════════════════════════════

def get_catalog(user_id: str, shop_uid: str) -> Optional[dict]:
    """
    Busca catálogo de uma loja específica.
    
    Args:
        user_id: JID do WhatsApp
        shop_uid: UID da loja
    
    Returns:
        Dict com dados do catálogo ou None
    """
    init_catalog_tables()
    
    with _get_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM whatsapp_shop_catalogs 
            WHERE user_id = ? AND shop_uid = ?
            """,
            (user_id, shop_uid)
        ).fetchone()
        
        if not row:
            return None
        
        return dict(row)


def get_catalog_products(catalog_id: str) -> list[dict]:
    """
    Busca produtos de um catálogo.
    
    Args:
        catalog_id: ID do catálogo
    
    Returns:
        Lista de produtos
    """
    init_catalog_tables()
    
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM whatsapp_catalog_products 
            WHERE catalog_id = ?
            ORDER BY name
            """,
            (catalog_id,)
        ).fetchall()
        
        products = []
        for row in rows:
            # Deserializa product_data completo
            product_data = json.loads(row["product_data"])
            products.append(product_data)
        
        return products


def has_catalog(user_id: str, shop_uid: str) -> bool:
    """
    Verifica se uma loja tem catálogo importado.
    
    Args:
        user_id: JID do WhatsApp
        shop_uid: UID da loja
    
    Returns:
        True se existe catálogo
    """
    init_catalog_tables()
    
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM whatsapp_shop_catalogs WHERE user_id = ? AND shop_uid = ?",
            (user_id, shop_uid)
        ).fetchone()
        
        return bool(row)


# ══════════════════════════════════════════════════════════════════
# REMOVER CATÁLOGO
# ══════════════════════════════════════════════════════════════════

def delete_catalog(user_id: str, shop_uid: str) -> bool:
    """
    Remove catálogo de uma loja específica.
    
    Args:
        user_id: JID do WhatsApp
        shop_uid: UID da loja
    
    Returns:
        True se removeu
    """
    init_catalog_tables()
    
    with _get_conn() as conn:
        # Remove catálogo (produtos são removidos por CASCADE)
        cursor = conn.execute(
            "DELETE FROM whatsapp_shop_catalogs WHERE user_id = ? AND shop_uid = ?",
            (user_id, shop_uid)
        )
        
        deleted = cursor.rowcount > 0
        
        if deleted:
            log.info(f"[CATALOG] Catálogo removido: user={user_id} shop_uid={shop_uid}")
        
        return deleted


# ══════════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════════

def get_catalog_summary(user_id: str, shop_uid: str) -> Optional[dict]:
    """
    Retorna resumo do catálogo de uma loja.
    
    Args:
        user_id: JID do WhatsApp
        shop_uid: UID da loja
    
    Returns:
        Dict com resumo ou None
    """
    catalog = get_catalog(user_id, shop_uid)
    
    if not catalog:
        return None
    
    return {
        "username": catalog["username"],
        "products_count": catalog["products_count"],
        "source_type": catalog["source_type"],
        "imported_at": catalog["imported_at"],
        "updated_at": catalog["updated_at"],
    }
