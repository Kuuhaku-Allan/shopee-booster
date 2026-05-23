#!/usr/bin/env python3
"""
Inspect one Radar product and its downloaded assets.

Usage:
    python scripts/radar_inspect_product.py PRODUCT_UID
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shopee_core.radar_service import get_product, list_product_assets


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspeciona um produto do Radar.")
    parser.add_argument("product_uid")
    args = parser.parse_args()

    product = get_product(args.product_uid)
    if not product:
        print(f"Produto nao encontrado: {args.product_uid}", file=sys.stderr)
        return 1

    raw = {}
    if product.get("raw_json"):
        try:
            raw = json.loads(product["raw_json"])
        except json.JSONDecodeError:
            raw = {}

    assets = list_product_assets(args.product_uid)
    local_paths = [asset["local_path"] for asset in assets if asset.get("local_path")]

    summary = {
        "product_uid": product["product_uid"],
        "title": product.get("title"),
        "marketplace": product.get("marketplace"),
        "price": product.get("price"),
        "status": product.get("status"),
        "shop_name": product.get("shop_name"),
        "rating": raw.get("rating"),
        "review_count": raw.get("review_count"),
        "sold_count": raw.get("sold_count"),
        "assets_count": len(assets),
        "local_assets_count": len(local_paths),
        "local_paths": local_paths,
        "raw_json_size": len(product.get("raw_json") or ""),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
