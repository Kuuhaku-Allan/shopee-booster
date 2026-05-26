"""
scripts/radar_inspect_patterns.py - R7.2L: Inspect the latest pattern report.

Usage:
    python scripts/radar_inspect_patterns.py <own_product_uid> [direct_only|direct_plus_partial]

Shows the latest (or freshly generated) pattern report for a product.
"""

import sys
import json
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shopee_core.radar_patterns_service import generate_pattern_report, get_latest_pattern_report


def _j(items):
    return "`, `".join(items) if items else "(none)"


def _print_report(report: dict, label: str):
    print(f"\n{'=' * 72}")
    print(f"RELATORIO DE PADROES — {label}")
    print(f"UID: {report.get('report_uid', 'N/A')}")
    print(f"Confianca: {report.get('confidence', 'N/A').upper()}")
    print(f"Escopo: {report.get('candidate_scope', 'N/A')}")
    print(f"Concorrentes usados: {report.get('total_competitors', 0)}")
    print(f"  Direct: {report.get('direct_count', 0)}")
    print(f"  Partial: {report.get('partial_count', 0)}")
    print(f"{'=' * 72}")

    # Price
    print("\n--- PRECO ---")
    print(f"  Min:    R$ {report.get('price_min', 'N/A')}")
    print(f"  Max:    R$ {report.get('price_max', 'N/A')}")
    print(f"  Avg:    R$ {report.get('price_avg', 'N/A')}")
    print(f"  Median: R$ {report.get('price_median', 'N/A')}")

    # Strategy sections
    st = report.get("strategy_title", {})
    if st:
        print(f"\n--- ESTRATEGIA DE TITULO ---")
        print(f"  Termos fortes:      {_j(st.get('strong_terms', []))}")
        print(f"  Termos secundarios: {_j(st.get('secondary_terms', []))}")
        if st.get("avoid_terms"):
            print(f"  Termos a evitar:    {_j(st['avoid_terms'])}")

    sf = report.get("strategy_features", {})
    if sf:
        print(f"\n--- ESTRATEGIA DE FEATURES ---")
        print(f"  Recomendadas: {_j(sf.get('recommended', []))}")
        if sf.get("off_niche"):
            print(f"  Off-niche:    {_j(sf['off_niche'])}")

    sd = report.get("strategy_description", {})
    if sd:
        print(f"\n--- ESTRATEGIA DE DESCRICAO ---")
        print(f"  Argumentos comerciais: {_j(sd.get('commercial_arguments', []))}")
        for obs in sd.get("observations", []):
            print(f"  Obs: {obs}")

    si = report.get("strategy_images", {})
    if si:
        print(f"\n--- ESTRATEGIA DE IMAGENS ---")
        print(f"  Media de imagens: {si.get('avg_image_count', 0):.1f}")
        for r in si.get("recommendations", []):
            print(f"  -> {r}")

    # Warnings
    warnings = report.get("warnings", [])
    if warnings:
        print(f"\n--- AVISOS ---")
        for w in warnings:
            print(f"  ! {w}")

    # Evidence
    evidence = report.get("evidence_list", [])
    if evidence:
        print(f"\n--- EVIDENCIAS ({len(evidence)} concorrentes) ---")
        for e in evidence:
            score = e.get("match_relevance_score") or "N/A"
            verdict = e.get("match_verdict", "N/A").replace("competitor_", "")
            price = f"R$ {e['price']:.2f}" if e.get("price") else "N/A"
            print(f"  [{verdict}] score={score} price={price}")
            print(f"    Title: {e.get('title', 'N/A')}")
            print(f"    Marketplace: {e.get('marketplace', 'N/A')}")

    print(f"{'=' * 72}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <own_product_uid> [scope]", file=sys.stderr)
        sys.exit(1)

    uid = sys.argv[1]
    scope = sys.argv[2] if len(sys.argv) > 2 else "direct_only"

    if scope not in ("direct_only", "direct_plus_partial"):
        print(f"Invalid scope '{scope}'. Use 'direct_only' or 'direct_plus_partial'.", file=sys.stderr)
        sys.exit(1)

    # Try latest saved first
    report = get_latest_pattern_report(uid)

    # If scope mismatches, generate fresh
    if report and report.get("candidate_scope") != scope:
        print(f"(escopo atual: {report.get('candidate_scope')}, solicitado: {scope} — gerando novo)")
        report = None

    if not report:
        report = generate_pattern_report(uid, candidate_scope=scope)

    if not report:
        print("Nenhum relatorio encontrado ou gerado.", file=sys.stderr)
        sys.exit(1)

    scope_label = "Diretos" if scope == "direct_only" else "Diretos + Parciais"
    _print_report(report, scope_label)
