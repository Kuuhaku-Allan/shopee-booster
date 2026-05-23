#!/usr/bin/env python3
"""
Run the R4.1 relevance smoke test against products in radar.db.

Usage:
    python scripts/radar_run_relevance_smoke.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shopee_core.radar_db import get_connection, init_db
from shopee_core.radar_relevance_service import (
    classify_candidates_for_product,
    get_matches_for_product,
)
from shopee_core.radar_service import classify_product


SMOKE_OWNER_ID = "radar-r4-1-smoke"

EXPECTED = {
    "direct_rodinhas": {"allowed": {"competitor_direct"}, "min_score": 0.72},
    "direct_or_partial_grande": {
        "allowed": {"competitor_direct", "competitor_partial"},
        "min_score": 0.60,
    },
    "partial_juvenil": {"allowed": {"competitor_partial"}, "min_score": 0.45, "max_score": 0.71},
    "low_notebook": {"allowed": {"rejected", "competitor_partial"}, "max_score": 0.55},
    "rejected_lancheira": {"allowed": {"rejected"}, "max_score": 0.44},
    "rejected_estojo": {"allowed": {"rejected"}, "max_score": 0.44},
}


def main() -> int:
    own_product = _find_own_product()
    if not own_product:
        print(
            "Produto proprio do smoke nao encontrado. Rode: "
            "python scripts/radar_seed_relevance_smoke.py",
            file=sys.stderr,
        )
        return 1

    candidates = _find_smoke_candidates()
    if len(candidates) < len(EXPECTED):
        print(
            "Candidatos do smoke incompletos. Rode: "
            "python scripts/radar_seed_relevance_smoke.py",
            file=sys.stderr,
        )
        return 1

    for candidate in candidates:
        classify_product(candidate["product_uid"], "competitor_candidate", 0.0, None)

    summary = classify_candidates_for_product(own_product["product_uid"], limit=500)
    matches = {
        match["candidate_product_uid"]: match
        for match in get_matches_for_product(own_product["product_uid"])
    }

    print(f"Produto proprio: {own_product['title']}")
    print(f"Total: {summary['total']}")
    print(f"Diretos: {summary['direct']}")
    print(f"Parciais: {summary['partial']}")
    print(f"Rejeitados: {summary['rejected']}")
    print(f"Score medio: {summary['average_score']:.2f}")
    print()
    print("verdict              | score | confidence | titulo | motivos")
    print("-" * 120)

    failures = []
    rows = []
    for candidate in candidates:
        match = matches.get(candidate["product_uid"])
        if not match:
            failures.append(f"{candidate['title']}: sem match persistido")
            continue

        reasons = "; ".join(match.get("reasons") or [])
        print(
            f"{match['verdict']:<20} | "
            f"{match['relevance_score']:.2f}  | "
            f"{match.get('confidence') or '-':<10} | "
            f"{candidate['title']} | "
            f"{reasons}"
        )
        rows.append(_row(candidate, match))

        error = _validate_expected(candidate, match)
        if error:
            failures.append(error)

    print()
    print(json.dumps({"smoke_rows": rows}, ensure_ascii=False, indent=2))

    if failures:
        print("\nFalhas de validacao:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("\nR4.1 aprovado: resultados semanticamente coerentes.")
    return 0


def _find_own_product() -> dict | None:
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM radar_products
            WHERE owner_user_id = ?
              AND source_type = 'own_product'
              AND url LIKE '%radar-r41-own%'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (SMOKE_OWNER_ID,),
        ).fetchone()
        return dict(row) if row else None


def _find_smoke_candidates() -> list[dict]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM radar_products
            WHERE owner_user_id = ?
              AND url LIKE '%radar-r41-%'
              AND url NOT LIKE '%radar-r41-own%'
            ORDER BY url ASC
            """,
            (SMOKE_OWNER_ID,),
        ).fetchall()
        return [dict(row) for row in rows]


def _validate_expected(candidate: dict, match: dict) -> str | None:
    raw = _load_raw(candidate)
    key = raw.get("raw", {}).get("smoke_key")
    expected = EXPECTED.get(key)
    if not expected:
        return None

    verdict = match["verdict"]
    score = float(match["relevance_score"])
    if verdict not in expected["allowed"]:
        return f"{candidate['title']}: esperado {sorted(expected['allowed'])}, veio {verdict}"
    if "min_score" in expected and score < expected["min_score"]:
        return f"{candidate['title']}: score {score:.2f} abaixo de {expected['min_score']:.2f}"
    if "max_score" in expected and score > expected["max_score"]:
        return f"{candidate['title']}: score {score:.2f} acima de {expected['max_score']:.2f}"
    return None


def _row(candidate: dict, match: dict) -> dict:
    return {
        "title": candidate["title"],
        "verdict": match["verdict"],
        "score": match["relevance_score"],
        "confidence": match.get("confidence"),
        "reasons": match.get("reasons") or [],
    }


def _load_raw(product: dict) -> dict:
    try:
        return json.loads(product.get("raw_json") or "{}")
    except json.JSONDecodeError:
        return {}


if __name__ == "__main__":
    raise SystemExit(main())
