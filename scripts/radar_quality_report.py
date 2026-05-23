#!/usr/bin/env python3
"""
Inspect Radar extraction quality across products.

Usage:
    python scripts/radar_quality_report.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shopee_core.radar_collector import validate_product_extraction
from shopee_core.radar_service import list_product_assets, list_products


def main() -> int:
    parser = argparse.ArgumentParser(description="Relatorio de qualidade do Radar.")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    rows = []
    for product in list_products(limit=args.limit):
        quality = _product_quality(product)
        assets = list_product_assets(product["product_uid"])
        asset_count = len(assets)
        if asset_count > 80:
            quality = dict(quality)
            quality["errors"] = list(quality.get("errors") or [])
            quality["errors"].append(f"Assets demais registrados para um produto: {asset_count}.")
            quality["ok"] = False
        rows.append(
            {
                "product_uid": product["product_uid"],
                "title": product.get("title"),
                "price": product.get("price"),
                "marketplace": product.get("marketplace"),
                "status": product.get("status"),
                "source_type": product.get("source_type"),
                "asset_count": asset_count,
                "quality": quality,
            }
        )

    problems = [row for row in rows if not row["quality"].get("ok") or row["quality"].get("warnings")]
    generic_titles = _count_problem(rows, "Titulo generico")
    suspicious_prices = _count_problem(rows, "Preco suspeito")
    too_many_assets = sum(1 for row in rows if row["asset_count"] > 80 or _has_problem(row, "Assets/imagens demais"))

    print("===== Radar Quality Report =====")
    print(f"Total de produtos: {len(rows)}")
    print(f"Produtos OK: {sum(1 for row in rows if row['quality'].get('ok'))}")
    print(f"Produtos com titulo generico: {generic_titles}")
    print(f"Produtos com preco suspeito: {suspicious_prices}")
    print(f"Produtos com assets demais: {too_many_assets}")
    print("")
    print("Top 20 problemas:")

    for row in sorted(problems, key=_problem_sort_key)[:20]:
        messages = list(row["quality"].get("errors") or []) + list(row["quality"].get("warnings") or [])
        print(
            f"- {row['product_uid']} | {row['status']} | {row['source_type']} | "
            f"R$ {row['price']} | assets={row['asset_count']} | {row['title']}"
        )
        for message in messages[:5]:
            print(f"  - {message}")

    return 0


def _product_quality(product: dict) -> dict:
    raw = _load_json(product.get("raw_json"))
    data = dict(raw)
    data.setdefault("url", product.get("url"))
    data.setdefault("canonical_url", product.get("canonical_url"))
    data.setdefault("marketplace", product.get("marketplace"))
    data.setdefault("title", product.get("title"))
    data.setdefault("price", product.get("price"))
    data.setdefault("shop_name", product.get("shop_name"))
    return validate_product_extraction(data, product.get("marketplace") or "")


def _load_json(value) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        data = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _count_problem(rows: list[dict], needle: str) -> int:
    return sum(1 for row in rows if _has_problem(row, needle))


def _has_problem(row: dict, needle: str) -> bool:
    quality = row.get("quality") or {}
    messages = list(quality.get("errors") or []) + list(quality.get("warnings") or [])
    return any(needle in str(message) for message in messages)


def _problem_sort_key(row: dict) -> tuple:
    quality = row["quality"]
    return (
        0 if not quality.get("ok") else 1,
        -len(quality.get("errors") or []),
        -row["asset_count"],
        row.get("title") or "",
    )


if __name__ == "__main__":
    raise SystemExit(main())
