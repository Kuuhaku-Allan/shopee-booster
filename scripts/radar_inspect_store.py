#!/usr/bin/env python3
"""
Inspect a store mirror saved in radar.db.

Usage:
    python scripts/radar_inspect_store.py --shop-uid totalmenteseu
    python scripts/radar_inspect_store.py --shop-uid totalmenteseu --show-raw
    python scripts/radar_inspect_store.py --shop-uid totalmenteseu --limit 20
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shopee_core.radar_db import DB_PATH, get_connection, init_db
from shopee_core.radar_store_service import (
    get_cached_store_products,
    get_store_snapshot_status,
)


def _find_store(identifier: str, marketplace: str = "shopee") -> dict | None:
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM radar_stores
            WHERE marketplace = ?
              AND (
                    store_uid = ?
                 OR shop_uid = ?
                 OR shop_slug = ?
              )
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (marketplace, identifier, identifier, identifier),
        ).fetchone()
        return dict(row) if row else None


def _get_product_details(store_uid: str, limit: int, include_removed: bool = True) -> list[dict]:
    """Retorna detalhes completos de produtos do espelho, incluindo source_type do radar."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT sp.store_product_uid,
                   sp.marketplace_product_id,
                   sp.title,
                   sp.price,
                   sp.image_url,
                   sp.status AS cache_status,
                   sp.first_seen_at,
                   sp.last_seen_at,
                   sp.last_changed_at,
                   sp.updated_at,
                   sp.radar_product_uid,
                   sp.canonical_url,
                   sp.raw_json,
                   p.source_type AS radar_source_type,
                   p.status AS radar_status,
                   p.collected_at
            FROM radar_store_products sp
            LEFT JOIN radar_products p ON p.product_uid = sp.radar_product_uid
            WHERE sp.store_uid = ?
            ORDER BY COALESCE(sp.last_seen_at, sp.updated_at, sp.created_at) DESC
            LIMIT ?
            """,
            (store_uid, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def _last_source(store: dict) -> str | None:
    try:
        raw = json.loads(store.get("raw_json") or "{}")
        return raw.get("last_source") or raw.get("last_summary", {}).get("source")
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspeciona espelho de loja salvo no Radar.")
    parser.add_argument("--shop-uid", default=None, help="store_uid, shop_uid ou slug da loja.")
    parser.add_argument("--store-uid", default=None)
    parser.add_argument("--marketplace", default="shopee")
    parser.add_argument("--limit", type=int, default=10, help="Número máximo de produtos a exibir.")
    parser.add_argument("--show-raw", action="store_true", help="Incluir raw_json de cada produto.")
    args = parser.parse_args()

    identifier = args.store_uid or args.shop_uid
    if not identifier:
        print("Informe --shop-uid ou --store-uid", file=sys.stderr)
        return 2

    store = _find_store(identifier, marketplace=args.marketplace)
    if not store:
        print(
            json.dumps(
                {
                    "ok": False,
                    "db_path": str(DB_PATH),
                    "message": "Loja nao encontrada no espelho do Radar.",
                    "identifier": identifier,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    status = get_store_snapshot_status(store["store_uid"])
    products = _get_product_details(store["store_uid"], limit=args.limit)
    last_src = _last_source(store)

    # Monta saída detalhada
    output = {
        "ok": True,
        "db_path": str(DB_PATH),
        "store": {
            "store_uid": store.get("store_uid"),
            "shop_uid": store.get("shop_uid"),
            "shop_slug": store.get("shop_slug"),
            "shop_name": store.get("shop_name"),
            "marketplace": store.get("marketplace"),
            "source_url": store.get("source_url"),
            "last_snapshot_at": store.get("last_snapshot_at"),
            "last_successful_load_at": store.get("last_successful_load_at"),
            "created_at": store.get("created_at"),
            "updated_at": store.get("updated_at"),
        },
        "status": {
            "total_products": status.get("total_products"),
            "active": status.get("active"),
            "changed": status.get("changed"),
            "missing": status.get("missing"),
            "removed": status.get("removed"),
            "cache_available": status.get("cache_available"),
            "counts_by_status": status.get("counts_by_status"),
        },
        "last_source": last_src,
        "latest_products": [
            {
                "title": item.get("title"),
                "price": item.get("price"),
                "cache_status": item.get("cache_status"),
                "marketplace_product_id": item.get("marketplace_product_id"),
                "canonical_url": item.get("canonical_url"),
                "radar_product_uid": item.get("radar_product_uid"),
                "radar_source_type": item.get("radar_source_type"),
                "radar_status": item.get("radar_status"),
                "first_seen_at": item.get("first_seen_at"),
                "last_seen_at": item.get("last_seen_at"),
                "last_changed_at": item.get("last_changed_at"),
                "updated_at": item.get("updated_at"),
                **({"raw_json": json.loads(item.get("raw_json") or "{}")} if args.show_raw else {}),
            }
            for item in products
        ],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
