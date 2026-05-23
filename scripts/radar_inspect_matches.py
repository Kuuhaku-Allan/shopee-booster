#!/usr/bin/env python3
"""
Inspect persisted Radar competitor matches for one own product.

Usage:
    python scripts/radar_inspect_matches.py OWN_PRODUCT_UID
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shopee_core.radar_relevance_service import get_matches_for_product
from shopee_core.radar_service import get_product


def main() -> int:
    parser = argparse.ArgumentParser(description="Lista matches do Radar R4.")
    parser.add_argument("own_product_uid")
    parser.add_argument(
        "--verdict",
        choices=["competitor_direct", "competitor_partial", "rejected"],
        default=None,
    )
    args = parser.parse_args()

    own_product = get_product(args.own_product_uid)
    if not own_product:
        print(f"Produto proprio nao encontrado: {args.own_product_uid}", file=sys.stderr)
        return 1

    print(f"Produto proprio: {own_product.get('title') or own_product.get('canonical_url')}")
    print("verdict              | score | preco      | titulo | motivos")
    print("-" * 110)

    for match in get_matches_for_product(args.own_product_uid, verdict=args.verdict):
        reasons = "; ".join(match.get("reasons") or [])[:80]
        title = (match.get("title") or match.get("canonical_url") or "")[:70]
        print(
            f"{match['verdict']:<20} | "
            f"{match['relevance_score']:.2f}  | "
            f"{str(match.get('price') or '-'):>10} | "
            f"{title} | {reasons}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
