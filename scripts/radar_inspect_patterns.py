#!/usr/bin/env python3
"""
Inspect the latest saved R5 Radar pattern report.

Usage:
    python scripts/radar_inspect_patterns.py OWN_PRODUCT_UID
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shopee_core.radar_patterns_service import get_latest_pattern_report
from shopee_core.radar_service import get_product


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspeciona ultimo relatorio R5.")
    parser.add_argument("own_product_uid")
    args = parser.parse_args()

    own_product = get_product(args.own_product_uid)
    if not own_product:
        print(f"Produto proprio nao encontrado: {args.own_product_uid}", file=sys.stderr)
        return 1

    report = get_latest_pattern_report(args.own_product_uid)
    if not report:
        print("Nenhum relatorio salvo para este produto.", file=sys.stderr)
        return 1

    print(f"Produto proprio: {own_product.get('title') or own_product.get('canonical_url')}")
    print(f"report_uid: {report['report_uid']}")
    print(f"criado em: {report.get('created_at')}")
    print(f"concorrentes: {report['total_competitors']} | diretos: {report['direct_count']} | parciais: {report['partial_count']}")
    print(f"preco: min={report.get('price_min')} avg={report.get('price_avg')} median={report.get('price_median')} max={report.get('price_max')}")
    print(f"confianca: {report.get('confidence') or '-'}")

    print("\nTermos fortes:")
    for row in report["title_terms"].get("strong_terms", []):
        print(f"- {row['term']} ({row['frequency']:.0%})")

    print("\nFeatures fortes:")
    for row in report["features"].get("strong_patterns", []):
        print(f"- {row['feature']} ({row['frequency']:.0%})")

    print("\nArgumentos comuns:")
    for row in report["description_patterns"].get("common_promises", []):
        print(f"- {row['argument']} ({row['frequency']:.0%})")

    print("\nAvisos:")
    for warning in report.get("warnings") or []:
        print(f"- {warning}")

    print("\nRecomendacoes:")
    for item in report.get("recommendations") or []:
        print(f"- [{item['priority']}] {item['recommendation']}")
        print(f"  {item['evidence']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
