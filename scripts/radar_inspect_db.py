#!/usr/bin/env python3
"""
Inspect the assisted Radar SQLite database.

Usage:
    python scripts/radar_inspect_db.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shopee_core.radar_db import DB_PATH, get_connection, init_db


def _count_by(conn, table: str, column: str) -> dict:
    rows = conn.execute(
        f"""
        SELECT {column} AS key, COUNT(*) AS total
        FROM {table}
        GROUP BY {column}
        ORDER BY total DESC, key ASC
        """
    ).fetchall()
    return {row["key"]: row["total"] for row in rows}


def main() -> int:
    init_db()

    with get_connection() as conn:
        total_products = conn.execute(
            "SELECT COUNT(*) AS total FROM radar_products"
        ).fetchone()["total"]
        total_assets = conn.execute(
            "SELECT COUNT(*) AS total FROM radar_assets"
        ).fetchone()["total"]
        total_jobs = conn.execute(
            "SELECT COUNT(*) AS total FROM radar_collection_jobs"
        ).fetchone()["total"]

        latest_rows = conn.execute(
            """
            SELECT
                p.product_uid,
                p.marketplace,
                p.source_type,
                p.status,
                p.title,
                p.price,
                p.shop_name,
                p.canonical_url,
                p.collected_at,
                COUNT(a.asset_uid) AS assets_count
            FROM radar_products p
            LEFT JOIN radar_assets a ON a.product_uid = p.product_uid
            GROUP BY p.product_uid
            ORDER BY COALESCE(p.collected_at, p.created_at) DESC
            LIMIT 10
            """
        ).fetchall()

        summary = {
            "db_path": str(DB_PATH),
            "total_products": total_products,
            "total_assets": total_assets,
            "total_jobs": total_jobs,
            "products_by_status": _count_by(conn, "radar_products", "status"),
            "products_by_marketplace": _count_by(conn, "radar_products", "marketplace"),
            "jobs_by_status": _count_by(conn, "radar_collection_jobs", "status"),
            "latest_products": [dict(row) for row in latest_rows],
        }

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
