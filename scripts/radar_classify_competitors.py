#!/usr/bin/env python3
"""
Classify Radar competitor candidates against one own product.

Usage:
    python scripts/radar_classify_competitors.py OWN_PRODUCT_UID --limit 50
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shopee_core.radar_relevance_service import (
    build_product_profile,
    classify_candidates_for_product,
    compare_product_profiles,
)
from shopee_core.radar_service import get_product, list_products


def main() -> int:
    parser = argparse.ArgumentParser(description="Classifica concorrentes do Radar R4.")
    parser.add_argument("own_product_uid")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--show-rejected", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Calcula sem salvar matches")
    args = parser.parse_args()

    own_product = get_product(args.own_product_uid)
    if not own_product:
        print(f"Produto proprio nao encontrado: {args.own_product_uid}", file=sys.stderr)
        return 1

    if args.dry_run:
        results = _dry_run(args.own_product_uid, args.limit)
        summary = _summary_from_results(args.own_product_uid, results)
    else:
        summary = classify_candidates_for_product(args.own_product_uid, limit=args.limit)
        results = summary["results"]

    print(f"Produto proprio: {own_product.get('title') or own_product.get('canonical_url')}")
    print(f"Total de candidatos: {summary['total']}")
    print(f"Diretos: {summary['direct']}")
    print(f"Parciais: {summary['partial']}")
    print(f"Rejeitados: {summary['rejected']}")
    print(f"Score medio: {summary['average_score']:.2f}")

    _print_top("Top diretos", results, "competitor_direct")
    _print_top("Top parciais", results, "competitor_partial")
    if args.show_rejected:
        _print_top("Top rejeitados", results, "rejected")

    return 0


def _dry_run(own_product_uid: str, limit: int) -> list[dict]:
    own_product = get_product(own_product_uid)
    own_profile = build_product_profile(own_product)
    results = []
    for candidate in list_products(source_type="competitor_candidate", limit=limit):
        if candidate["product_uid"] == own_product_uid:
            continue
        candidate_profile = build_product_profile(candidate)
        comparison = compare_product_profiles(own_profile, candidate_profile)
        results.append(
            {
                "candidate_product": candidate,
                "candidate_profile": candidate_profile,
                **comparison,
            }
        )
    return results


def _summary_from_results(own_product_uid: str, results: list[dict]) -> dict:
    total = len(results)
    return {
        "own_product_uid": own_product_uid,
        "total": total,
        "direct": sum(1 for item in results if item["verdict"] == "competitor_direct"),
        "partial": sum(1 for item in results if item["verdict"] == "competitor_partial"),
        "rejected": sum(1 for item in results if item["verdict"] == "rejected"),
        "average_score": (
            sum(item["score"] for item in results) / total if total else 0.0
        ),
    }


def _print_top(title: str, results: list[dict], verdict: str) -> None:
    items = [item for item in results if item["verdict"] == verdict]
    if not items:
        return

    print(f"\n{title}:")
    for item in sorted(items, key=lambda row: row["score"], reverse=True)[:10]:
        candidate = item.get("candidate_product") or {}
        reason = item["reasons"][0] if item.get("reasons") else "Sem motivo registrado"
        print(
            f"- {item['score']:.2f} | "
            f"{candidate.get('price') or '-'} | "
            f"{candidate.get('title') or candidate.get('canonical_url')} | "
            f"{reason}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
