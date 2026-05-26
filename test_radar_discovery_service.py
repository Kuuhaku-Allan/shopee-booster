# -*- coding: utf-8 -*-
"""
test_radar_discovery_service.py - R7.3: Automatic competitor discovery tests.

Run:
    python -m pytest test_radar_discovery_service.py -v
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

RUN_ID = uuid.uuid4().hex
os.environ["SHOPEE_RADAR_DB_PATH"] = str(Path("data") / f"radar_discovery_test_{RUN_ID}.db")

from shopee_core.radar_discovery_service import (
    generate_competitor_search_queries,
    _build_ml_search_url,
    _is_valid_ml_product_url,
    _normalize_discovered_url,
    calculate_radar_market_confidence,
    run_automatic_radar_cycle,
)
from shopee_core.radar_service import get_product, add_product_url, mark_product_collected
from shopee_core.radar_relevance_service import classify_candidate
from shopee_core.radar_patterns_service import generate_pattern_report, get_latest_pattern_report
from shopee_core.radar_db import get_connection, init_db


# ── Helpers ──────────────────────────────────────────────────────────────


def _create_product(title, price, source_type="competitor_candidate", marketplace="mercadolivre"):
    created = add_product_url(
        f"https://produto.mercadolivre.com.br/MLB-{RUN_ID[:8]}{uuid.uuid4().hex[:8]}-disc-_JM",
        source_type,
    )
    uid = created["product"]["product_uid"]
    data = {
        "title": title,
        "price": price,
        "shop_name": "Loja Teste",
        "marketplace": marketplace,
        "description": "Mochila para teste automatizado.",
        "image_urls": [],
        "video_urls": [],
        "attributes": {},
        "category_path": ["Mochilas", "Escolar"],
        "raw": {"test": "R7.3"},
    }
    return mark_product_collected(uid, data)


def _own_product(title="Mochila Infantil Princesa Rosa Escolar Feminina Grande", price=89.9):
    return _create_product(title, price, source_type="own_product")


# ── Tests: Search query generator ────────────────────────────────────────


def test_generate_queries_infantil_escolar():
    """Generates useful queries for a mochila infantil princesa product."""
    own = {"title": "Mochila Infantil Princesa Rosa Escolar Feminina Grande", "price": 89.9}
    queries = generate_competitor_search_queries(own)
    assert len(queries) >= 3, f"Expected >=3 queries, got {len(queries)}"
    # All queries should contain 'mochila'
    all_queries = [q["query"] for q in queries]
    assert any("mochila" in q for q in all_queries)
    assert any("infantil" in q for q in all_queries)
    assert any("escolar" in q for q in all_queries)
    return True


def test_no_generic_queries():
    """Should NOT generate overly generic queries like 'mochila' or 'bolsa' alone."""
    own = {"title": "Mochila Infantil Princesa Rosa Escolar Feminina Grande", "price": 89.9}
    queries = generate_competitor_search_queries(own)
    single_word = [q["query"] for q in queries if len(q["query"].split()) <= 2]
    # No 1-word queries
    assert all(len(q.split()) > 2 for q in [q["query"] for q in queries])
    return True


def test_query_priorities():
    """High-priority queries come before low-priority ones."""
    own = {"title": "Mochila Infantil Princesa Rosa Escolar Feminina Grande", "price": 89.9}
    queries = generate_competitor_search_queries(own)
    priorities = [q["priority"] for q in queries]
    # List should be sorted by priority
    for i in range(len(priorities) - 1):
        assert priorities[i] <= priorities[i + 1], f"Priority order violated at index {i}: {priorities}"
    return True


# ── Tests: ML URL helpers ────────────────────────────────────────────────


def test_build_ml_search_url():
    """Builds correct ML search URL from query."""
    url = _build_ml_search_url("mochila infantil princesa escolar")
    assert "lista.mercadolivre.com.br" in url
    assert "mochila-infantil-princesa-escolar" in url
    return True


def test_is_valid_ml_product_url():
    """Recognizes valid ML product URLs."""
    assert _is_valid_ml_product_url("https://produto.mercadolivre.com.br/MLB-1234567890")
    assert _is_valid_ml_product_url("https://www.mercadolivre.com.br/p/MLB1234567890")
    assert _is_valid_ml_product_url("https://mercadolivre.com.br/up/MLBU1234567890")
    # Invalid
    assert not _is_valid_ml_product_url("")
    assert not _is_valid_ml_product_url("https://lista.mercadolivre.com.br/mochilas")
    assert not _is_valid_ml_product_url("https://shopee.com.br/product/1/1")
    return True


def test_normalize_discovered_url():
    """Normalizes and validates discovered ML URLs."""
    url = _normalize_discovered_url("https://produto.mercadolivre.com.br/MLB-1234567890?extra=tracking")
    assert url is not None
    assert "MLB-1234567890" in url
    assert "extra" not in url
    # Invalid URL
    assert _normalize_discovered_url("") is None
    assert _normalize_discovered_url("not-a-url") is None
    return True


def test_reject_fake_url():
    """Fake/test shopee URLs are rejected."""
    url = _normalize_discovered_url("https://shopee.com.br/product/1/1")
    assert url is None
    return True


# ── Tests: Confidence calculator ─────────────────────────────────────────


def test_confidence_without_report():
    """No report yields insufficient confidence."""
    conf = calculate_radar_market_confidence("nonexistent_uid")
    assert conf["level"] == "insufficient"
    assert conf["score"] == 0
    return True


def test_confidence_after_report():
    """Report with 5 direct yields medium confidence."""
    own = _own_product()
    for i in range(5):
        p = _create_product(f"Mochila Infantil Rosa Escolar Variante {i}", 70.0 + i)
        classify_candidate(own["product_uid"], p["product_uid"])
    report = generate_pattern_report(own["product_uid"])
    conf = calculate_radar_market_confidence(own["product_uid"], report["report_uid"])
    assert conf["level"] in ("medium", "low"), f"Got {conf['level']} for 5 direct"
    assert conf["score"] >= 35, f"Score too low: {conf['score']}"
    return True


# ── Tests: Cycle limits ──────────────────────────────────────────────────


def test_cycle_errors_without_chrome():
    """Cycle returns error when Chrome is not available."""
    # This will fail at chrome step because there's no CDP browser in testing
    result = run_automatic_radar_cycle("nonexistent", browser_mode="cdp", cdp_url="http://127.0.0.1:19222")
    assert not result.get("ok")
    assert result.get("step") == "chrome" or len(result.get("errors", [])) > 0
    return True


def test_cycle_stops_on_missing_product():
    """Cycle stops gracefully when product doesn't exist."""
    result = run_automatic_radar_cycle("nonexistent_uid_xyz")
    assert not result.get("ok")
    return True


# ── Runner ────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    print("\nTESTE R7.3 - Radar Discovery Service\n")

    tests = [
        ("queries infantis uteis", test_generate_queries_infantil_escolar),
        ("sem queries genericas", test_no_generic_queries),
        ("prioridades ordenadas", test_query_priorities),
        ("ML search URL", test_build_ml_search_url),
        ("ML product URL valida", test_is_valid_ml_product_url),
        ("normaliza URL descoberta", test_normalize_discovered_url),
        ("rejeita URL fake", test_reject_fake_url),
        ("confianca sem relatorio", test_confidence_without_report),
        ("confianca apos relatorio", test_confidence_after_report),
        ("ciclo sem chrome retorna erro", test_cycle_errors_without_chrome),
        ("ciclo para sem produto", test_cycle_stops_on_missing_product),
    ]

    passed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"PASS - {name}")
        except Exception as exc:
            print(f"FAIL - {name}: {exc}")
            raise

    print(f"\nTotal: {passed}/{len(tests)} testes passaram")
