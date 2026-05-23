#!/usr/bin/env python3
"""
Generate an R5 Radar pattern report.

Usage:
    python scripts/radar_analyze_patterns.py OWN_PRODUCT_UID --save
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shopee_core.radar_patterns_service import generate_pattern_report
from shopee_core.radar_service import get_product


def main() -> int:
    parser = argparse.ArgumentParser(description="Analisa padroes R5 do Radar.")
    parser.add_argument("own_product_uid")
    parser.add_argument("--include-partial", action="store_true")
    parser.add_argument("--min-direct", type=int, default=3)
    parser.add_argument("--save", action="store_true", help="Salva em radar_pattern_reports")
    args = parser.parse_args()

    own_product = get_product(args.own_product_uid)
    if not own_product:
        print(f"Produto proprio nao encontrado: {args.own_product_uid}", file=sys.stderr)
        return 1

    report = generate_pattern_report(
        args.own_product_uid,
        include_partial=args.include_partial,
        min_direct=args.min_direct,
        save=args.save,
    )
    _print_report(own_product, report, saved=args.save)
    return 0


def _print_report(own_product: dict, report: dict, saved: bool) -> None:
    print(f"Produto proprio: {own_product.get('title') or own_product.get('canonical_url')}")
    print(f"Relatorio salvo: {'sim' if saved else 'nao'}")
    if saved:
        print(f"report_uid: {report['report_uid']}")
    print(f"Concorrentes analisados: {report['total_competitors']}")
    print(f"Diretos: {report['direct_count']}")
    print(f"Parciais cadastrados: {report['partial_count']}")
    print(f"Confianca: {report.get('confidence') or '-'}")

    print("\nPreco:")
    print(
        f"- min R$ {report.get('price_min')} | "
        f"avg R$ {report.get('price_avg')} | "
        f"median R$ {report.get('price_median')} | "
        f"max R$ {report.get('price_max')}"
    )

    print("\nTop termos de titulo:")
    for row in report["title_terms"].get("top_terms", [])[:10]:
        print(f"- {row['term']} ({row['count']} / {row['frequency']:.0%})")

    print("\nTop features:")
    for row in report["features"].get("features", [])[:10]:
        print(f"- {row['feature']} ({row['count']} / {row['frequency']:.0%})")

    print("\nArgumentos de descricao:")
    for row in report["description_patterns"].get("commercial_arguments", [])[:10]:
        print(f"- {row['argument']} ({row['count']} / {row['frequency']:.0%})")

    images = report["image_patterns"]
    print("\nImagens:")
    print(
        f"- media {images.get('avg_image_count')} | "
        f"min {images.get('min_image_count')} | "
        f"max {images.get('max_image_count')} | "
        f"assets baixados {images.get('downloaded_assets')}"
    )

    if report.get("warnings"):
        print("\nAvisos:")
        for warning in report["warnings"]:
            print(f"- {warning}")

    print("\nRecomendacoes:")
    for item in report.get("recommendations") or []:
        print(f"- [{item['priority']}] {item['type']}: {item['recommendation']}")
        print(f"  Evidencia: {item['evidence']}")


if __name__ == "__main__":
    raise SystemExit(main())
