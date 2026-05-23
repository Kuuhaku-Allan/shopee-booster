#!/usr/bin/env python3
"""
Export the latest R5.1 market smoke report to Markdown.

Usage:
    python scripts/radar_export_market_smoke_report.py
    python scripts/radar_export_market_smoke_report.py OWN_PRODUCT_UID
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shopee_core.radar_db import get_connection, init_db
from shopee_core.radar_patterns_service import get_latest_pattern_report
from shopee_core.radar_relevance_service import get_matches_for_product
from shopee_core.radar_service import get_product


SMOKE_OWNER_ID = "radar-r5-1-market-smoke"
DEFAULT_OUTPUT = ROOT_DIR / "data" / "reports" / "radar_market_smoke_mochilas.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Exporta relatorio Markdown do smoke R5.1.")
    parser.add_argument("own_product_uid", nargs="?")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    own_product_uid = args.own_product_uid or _find_latest_smoke_own_product_uid()
    if not own_product_uid:
        print("Produto proprio do smoke R5.1 nao encontrado.", file=sys.stderr)
        return 1

    own_product = get_product(own_product_uid)
    report = get_latest_pattern_report(own_product_uid)
    if not own_product or not report:
        print("Relatorio salvo nao encontrado para o produto informado.", file=sys.stderr)
        return 1

    matches = get_matches_for_product(own_product_uid)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_render_markdown(own_product, report, matches), encoding="utf-8")
    print(f"Relatorio exportado: {output}")
    return 0


def _find_latest_smoke_own_product_uid() -> str | None:
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT product_uid
            FROM radar_products
            WHERE owner_user_id = ?
              AND source_type = 'own_product'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (SMOKE_OWNER_ID,),
        ).fetchone()
    return row["product_uid"] if row else None


def _render_markdown(own_product: dict, report: dict, matches: list[dict]) -> str:
    direct = [match for match in matches if match["verdict"] == "competitor_direct"]
    rejected = [match for match in matches if match["verdict"] == "rejected"]
    partial = [match for match in matches if match["verdict"] == "competitor_partial"]

    lines = [
        "# Radar R5.1 - Smoke Mercado Livre Mochilas",
        "",
        "## Produto Proprio",
        "",
        f"- UID: `{own_product['product_uid']}`",
        f"- Titulo: {own_product.get('title')}",
        f"- Preco: {own_product.get('price')}",
        "",
        "## Distribuicao",
        "",
        f"- Concorrentes diretos: {len(direct)}",
        f"- Concorrentes parciais: {len(partial)}",
        f"- Rejeitados: {len(rejected)}",
        f"- Relatorio: `{report['report_uid']}`",
        "",
        "## Concorrentes Diretos",
        "",
    ]
    lines.extend(_match_lines(direct))
    lines.extend(["", "## Rejeitados", ""])
    lines.extend(_match_lines(rejected))
    lines.extend(["", "## Padroes de Preco", ""])
    lines.extend(
        [
            f"- Minimo: {report.get('price_min')}",
            f"- Medio: {report.get('price_avg')}",
            f"- Mediano: {report.get('price_median')}",
            f"- Maximo: {report.get('price_max')}",
        ]
    )
    lines.extend(["", "## Padroes de Titulo", ""])
    lines.extend(_frequency_lines(report["title_terms"].get("top_terms", []), "term"))
    lines.extend(["", "## Padroes de Features", ""])
    lines.extend(_frequency_lines(report["features"].get("features", []), "feature"))
    lines.extend(["", "## Padroes de Descricao", ""])
    lines.extend(_frequency_lines(report["description_patterns"].get("commercial_arguments", []), "argument"))
    lines.extend(["", "## Padroes de Imagem", ""])
    images = report.get("image_patterns") or {}
    lines.extend(
        [
            f"- Media de imagens: {images.get('avg_image_count')}",
            f"- Minimo de imagens: {images.get('min_image_count')}",
            f"- Maximo de imagens: {images.get('max_image_count')}",
            f"- Assets baixados: {images.get('downloaded_assets')}",
        ]
    )
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- {warning}" for warning in report.get("warnings") or []] or ["- Nenhum"])
    lines.extend(["", "## Recomendacoes", ""])
    for item in report.get("recommendations") or []:
        lines.append(f"- **[{item['priority']}] {item['type']}**: {item['recommendation']}")
        lines.append(f"  Evidencia: {item['evidence']}")

    lines.extend(["", "## Dados Brutos Resumidos", ""])
    lines.append("```json")
    lines.append(json.dumps({"report_uid": report["report_uid"], "confidence": report.get("confidence")}, ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def _match_lines(matches: list[dict]) -> list[str]:
    if not matches:
        return ["- Nenhum"]
    lines = []
    for match in matches:
        reasons = "; ".join(match.get("reasons") or [])
        lines.append(
            f"- `{match['relevance_score']:.2f}` {match.get('title')} "
            f"(R$ {match.get('price')}) - {reasons}"
        )
    return lines


def _frequency_lines(rows: list[dict], key: str) -> list[str]:
    if not rows:
        return ["- Nenhum"]
    return [
        f"- {row[key]}: {row['count']} ({row['frequency']:.0%})"
        for row in rows[:15]
    ]


if __name__ == "__main__":
    raise SystemExit(main())
