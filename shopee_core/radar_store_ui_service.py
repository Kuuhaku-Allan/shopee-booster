"""
UI Service for rendering the Store Mirror (Loja) in the Streamlit app.
Provides helpers that aggregate data from radar_store_service to feed the UI.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from shopee_core.radar_db import DB_PATH, get_connection, init_db
from shopee_core.radar_store_service import (
    get_store_snapshot_status,
)


def get_db_diagnostic() -> dict:
    """Retorna um diagnostico do arquivo radar.db: caminho, tamanho, total de lojas/produtos."""
    init_db()
    
    diagnostic = {
        "db_path": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
        "db_size_bytes": 0,
        "total_stores": 0,
        "total_store_products": 0,
        "total_own_products": 0,
    }

    if not diagnostic["db_exists"]:
        return diagnostic

    diagnostic["db_size_bytes"] = DB_PATH.stat().st_size

    try:
        with get_connection() as conn:
            row_stores = conn.execute("SELECT COUNT(*) FROM radar_stores").fetchone()
            diagnostic["total_stores"] = row_stores[0] if row_stores else 0

            row_sp = conn.execute("SELECT COUNT(*) FROM radar_store_products").fetchone()
            diagnostic["total_store_products"] = row_sp[0] if row_sp else 0

            row_own = conn.execute("SELECT COUNT(*) FROM radar_products WHERE source_type = 'own_product'").fetchone()
            diagnostic["total_own_products"] = row_own[0] if row_own else 0
    except Exception as exc:
        print(f"[R7.1] Erro ao ler diagnostic DB: {exc}")

    return diagnostic


def format_store_label(store: dict) -> str:
    """Formata a label da loja para o selectbox.
    Exemplo: "lojateste — 6 produtos — atualizado em 27/04/2026"
    Resiliente a campos nulos ou ausentes.
    """
    if not store:
        return "Loja desconhecida"

    slug = store.get("shop_slug") or store.get("shop_name") or store.get("shop_uid") or "Loja sem nome"
    total = store.get("product_count", 0)
    
    last_snap = store.get("last_snapshot_at")
    if last_snap:
        try:
            # Assume ISO format se for string
            if isinstance(last_snap, str):
                dt = datetime.fromisoformat(last_snap.replace("Z", "+00:00"))
                data_str = dt.strftime("%d/%m/%Y")
            else:
                data_str = last_snap.strftime("%d/%m/%Y")
        except Exception:
            data_str = str(last_snap)[:10]
    else:
        data_str = "Nunca"

    return f"{slug} — {total} produtos — atualizado em {data_str}"


def list_store_mirrors(limit: int = 100) -> list[dict]:
    """Lista lojas no espelho com totais preenchidos, ordenado por last_snapshot_at."""
    init_db()
    stores = []
    try:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT store_uid, shop_uid, shop_slug, shop_name, marketplace, 
                       source_url, last_snapshot_at, last_successful_load_at
                FROM radar_stores
                ORDER BY last_snapshot_at DESC NULLS LAST
                LIMIT ?
                """,
                (limit,)
            ).fetchall()
        
        for row in rows:
            store_dict = dict(row)
            # Busca status para agregar as contagens
            status = get_store_snapshot_status(store_dict["store_uid"])
            
            store_dict["product_count"] = status.get("total_products", 0)
            store_dict["active_count"] = status.get("active", 0)
            store_dict["changed_count"] = status.get("changed", 0)
            store_dict["missing_count"] = status.get("missing", 0)
            store_dict["removed_count"] = status.get("removed", 0)
            stores.append(store_dict)
            
    except Exception as exc:
        print(f"[R7.1] Erro em list_store_mirrors: {exc}")

    return stores


def get_store_mirror_summary(store_uid: str) -> dict:
    """Busca o resumo de uma loja (status counts, detalhes, se desatualizada)."""
    status = get_store_snapshot_status(store_uid)
    if not status.get("ok"):
        return {"ok": False}
        
    last_snap = status.get("last_snapshot_at")
    is_outdated = False
    
    if last_snap:
        try:
            if isinstance(last_snap, str):
                dt = datetime.fromisoformat(last_snap.replace("Z", "+00:00"))
            else:
                dt = last_snap
            # Considera timezone-aware se necessario
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            
            now = datetime.now(timezone.utc)
            diff = now - dt
            if diff.days > 7:
                is_outdated = True
        except Exception:
            pass

    status["is_outdated"] = is_outdated
    return status


def list_store_mirror_products(store_uid: str, status_filter: str = None, limit: int = 200) -> list[dict]:
    """Lista produtos do espelho de uma loja, com suporte a filtro de status.
    Inclui JOIN com radar_products para extrair metadata extra se disponivel.
    
    status_filter: "active", "changed", "missing", "removed", "unknown", "all", ou None
    """
    init_db()
    
    query = """
        SELECT sp.store_product_uid, sp.marketplace_product_id, sp.title, sp.price, 
               sp.image_url, sp.status AS cache_status, sp.first_seen_at, 
               sp.last_seen_at, sp.last_changed_at, sp.updated_at, sp.canonical_url,
               sp.radar_product_uid, sp.raw_json,
               p.source_type AS radar_source_type, p.status AS radar_status
        FROM radar_store_products sp
        LEFT JOIN radar_products p ON p.product_uid = sp.radar_product_uid
        WHERE sp.store_uid = ?
    """
    params = [store_uid]
    
    if status_filter and status_filter.lower() not in ["all", "todos"]:
        query += " AND sp.status = ?"
        params.append(status_filter.lower())
        
    query += " ORDER BY COALESCE(sp.last_seen_at, sp.updated_at) DESC LIMIT ?"
    params.append(limit)
    
    products = []
    try:
        with get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            
        for row in rows:
            p = dict(row)
            
            # Formatar raw_json se existir
            if p.get("raw_json"):
                try:
                    p["raw_json_parsed"] = json.loads(p["raw_json"])
                except Exception:
                    p["raw_json_parsed"] = {}
            else:
                p["raw_json_parsed"] = {}
                
            # Identifica fonte/origem
            src = "unknown"
            if p.get("radar_source_type") == "own_product":
                src = "espelho local"
            # Poderia ser estendido para catálogo, scraping
                
            p["display_source"] = src
            products.append(p)
            
    except Exception as exc:
        print(f"[R7.1] Erro em list_store_mirror_products: {exc}")
        
    return products
