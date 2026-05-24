#!/usr/bin/env python3
"""
Inspect a store mirror saved in radar.db.

Usage:
    python scripts/radar_inspect_store.py --shop-uid totalmenteseu
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspeciona espelho de loja salvo no Radar.")
    parser.add_argument("--shop-uid", default=None, help="store_uid, shop_uid ou slug da loja.")
    parser.add_argument("--store-uid", default=None)
    parser.add_argument("--marketplace", default="shopee")
    parser.add_argument("--limit", type=int, default=10)
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
    products = get_cached_store_products(store_uid=store["store_uid"], include_removed=True)
    latest_products = products[: max(1, args.limit)]

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
        },
        "status": status,
        "latest_products": [
            {
                "title": item.get("title") or item.get("name"),
                "price": item.get("price"),
                "status": item.get("cache_status"),
                "marketplace_product_id": item.get("marketplace_product_id"),
                "radar_product_uid": item.get("radar_product_uid"),
                "canonical_url": item.get("canonical_url"),
            }
            for item in latest_products
        ],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
