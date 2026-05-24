#!/usr/bin/env python3
"""
Save a local store mirror snapshot into radar.db.

Usage:
    python scripts/radar_store_snapshot.py --shop-uid totalmenteseu --input data/store_products_sample.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shopee_core.radar_store_service import save_store_snapshot


def _load_input(path: Path) -> tuple[dict, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {}, data
    if isinstance(data, dict):
        products = data.get("products") or data.get("items") or []
        store = data.get("store") or data.get("store_info") or {}
        return store, products
    raise ValueError("Arquivo precisa ser JSON list ou dict com products")


def main() -> int:
    parser = argparse.ArgumentParser(description="Salva snapshot do espelho da loja no Radar.")
    parser.add_argument("--shop-uid", required=True, help="Identificador da loja ou slug.")
    parser.add_argument("--shop-slug", default=None, help="Slug da loja na Shopee.")
    parser.add_argument("--shop-name", default=None, help="Nome exibido da loja.")
    parser.add_argument("--marketplace", default="shopee")
    parser.add_argument("--source-url", default=None)
    parser.add_argument("--source", default="script")
    parser.add_argument("--input", required=True, help="JSON com lista de produtos ou {products: [...]}.")
    args = parser.parse_args()

    input_path = Path(args.input)
    store_from_file, products = _load_input(input_path)

    shop_slug = args.shop_slug or store_from_file.get("shop_slug") or store_from_file.get("username")
    if not shop_slug and args.shop_uid and not str(args.shop_uid).isdigit():
        shop_slug = args.shop_uid

    store_info = {
        **store_from_file,
        "shop_uid": args.shop_uid or store_from_file.get("shop_uid"),
        "shop_slug": shop_slug,
        "shop_name": args.shop_name or store_from_file.get("shop_name") or store_from_file.get("name"),
        "marketplace": args.marketplace or store_from_file.get("marketplace") or "shopee",
        "source_url": args.source_url or store_from_file.get("source_url"),
    }

    summary = save_store_snapshot(store_info, products, source=args.source)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
