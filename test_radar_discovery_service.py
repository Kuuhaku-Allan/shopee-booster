# -*- coding: utf-8 -*-
"""
test_radar_discovery_service.py - R7.3: Automatic competitor discovery tests.

Run:
    python -m pytest test_radar_discovery_service.py -v
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path

RUN_ID = uuid.uuid4().hex
os.environ["SHOPEE_RADAR_DB_PATH"] = str(Path("data") / f"radar_discovery_test_{RUN_ID}.db")

from shopee_core.radar_discovery_service import (
    generate_competitor_search_queries,
    _build_ml_search_url,
    _is_valid_ml_product_url,
    _normalize_discovered_url,
    _extract_ml_product_urls_from_page,
    calculate_radar_market_confidence,
    run_automatic_radar_cycle,
)
from unittest.mock import patch
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
    assert _normalize_discovered_url("https://lista.mercadolivre.com.br/mochila-rosa") is None
    return True


def test_extract_urls_dedupes_normalized_product_links():
    """Multiple href variants for the same listing count as one product URL."""

    class FakePage:
        def wait_for_timeout(self, _ms):
            return None

        def evaluate(self, _script):
            return [
                "https://www.mercadolivre.com.br/mochila-rosa/p/MLB60726487?tracking_id=abc",
                "https://www.mercadolivre.com.br/mochila-rosa/p/MLB60726487?position=2",
                "https://produto.mercadolivre.com.br/MLB-1234567890-mochila-princesa-_JM?utm_source=x",
                "https://lista.mercadolivre.com.br/mochila-rosa",
                "https://shopee.com.br/product/1/1",
            ]

    urls = _extract_ml_product_urls_from_page(FakePage())

    assert urls == [
        "https://mercadolivre.com.br/mochila-rosa/p/MLB60726487",
        "https://produto.mercadolivre.com.br/MLB-1234567890-mochila-princesa-_JM",
    ]
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
    from shopee_core.radar_cdp_service import ensure_radar_chrome_ready as real_ensure
    with patch("shopee_core.radar_cdp_service.ensure_radar_chrome_ready") as mock_ready:
        mock_ready.return_value = {
            "ok": False, "environment_error": True,
            "message": "Chrome do Radar nao respondeu.",
            "diagnostics": {},
        }
        result = run_automatic_radar_cycle("nonexistent", browser_mode="cdp", cdp_url="http://127.0.0.1:19222")
    assert not result.get("ok")
    assert result.get("step") == "chrome" or len(result.get("errors", [])) > 0
    return True


def test_cycle_stops_on_missing_product():
    """Cycle stops gracefully when product doesn't exist."""
    with patch("shopee_core.radar_cdp_service.ensure_radar_chrome_ready") as mock_ready:
        mock_ready.return_value = {"ok": True, "already_running": True}
        result = run_automatic_radar_cycle("nonexistent_uid_xyz")
    assert not result.get("ok")
    return True


# ── Runner ────────────────────────────────────────────────────────────────


def _cycle_counts(pending=0, total=0, direct=0, partial=0, rejected=0, failed=0):
    return {
        "total_candidates": total,
        "pending": pending,
        "failed": failed,
        "collected_unclassified": 0,
        "direct": direct,
        "partial": partial,
        "rejected": rejected,
        "title_coverage": 1.0,
        "price_coverage": 1.0,
    }


def test_cycle_continues_collecting_until_target_high():
    counts = iter([
        _cycle_counts(pending=0, total=0),
        _cycle_counts(pending=10, total=10),
        _cycle_counts(pending=5, total=10, direct=4),
        _cycle_counts(pending=5, total=10, direct=4),
        _cycle_counts(pending=5, total=10, direct=4),
        _cycle_counts(pending=0, total=10, direct=8),
        _cycle_counts(pending=0, total=10, direct=8),
    ])

    def next_counts(_uid):
        try:
            return next(counts)
        except StopIteration:
            return _cycle_counts(pending=0, total=10, direct=8)

    with patch("shopee_core.radar_cdp_service.ensure_radar_chrome_ready", return_value={"ok": True}):
        with patch("shopee_core.radar_discovery_service.get_product", return_value={"title": "Mochila Infantil Princesa Rosa Escolar"}):
            with patch("shopee_core.radar_discovery_service._get_auto_cycle_counts", side_effect=next_counts):
                with patch("shopee_core.radar_discovery_service.discover_marketplace_candidate_urls", return_value={
                    "ok": True, "urls_found": 12, "urls_inserted": 10, "urls_existing": 0,
                }):
                    with patch("shopee_core.radar_discovery_service.ensure_collection_jobs_for_linked_candidates"):
                        with patch("shopee_core.radar_discovery_service.run_linked_collection_for_product") as mock_collect:
                            mock_collect.side_effect = [
                                {"processed": 5, "succeeded": 5, "failed": 0, "skipped": 0, "errors": []},
                                {"processed": 5, "succeeded": 5, "failed": 0, "skipped": 0, "errors": []},
                            ]
                            with patch("shopee_core.radar_discovery_service.classify_linked_candidates_for_product", return_value={
                                "ok": True, "total": 8, "direct": 8, "partial": 0, "rejected": 0,
                            }):
                                with patch("shopee_core.radar_discovery_service.generate_pattern_report", return_value={"report_uid": "r1"}):
                                    with patch("shopee_core.radar_discovery_service.calculate_radar_market_confidence") as mock_conf:
                                        mock_conf.side_effect = [
                                            {"level": "medium", "score": 65, "warnings": []},
                                            {"level": "high", "score": 88, "warnings": []},
                                        ]
                                        result = run_automatic_radar_cycle(
                                            "own-1",
                                            target_confidence="high",
                                            max_cycles=3,
                                            max_collect_per_cycle=5,
                                        )

    assert result["status"] == "success"
    assert result["cycles_run"] == 2
    assert result["target_reached"]
    assert mock_collect.call_count == 2
    return True


def test_cycle_limit_reached_with_pending_candidates():
    counts = iter([
        _cycle_counts(pending=0, total=0),
        _cycle_counts(pending=12, total=12),
        _cycle_counts(pending=7, total=12, direct=3),
        _cycle_counts(pending=7, total=12, direct=3),
        _cycle_counts(pending=7, total=12, direct=3),
        _cycle_counts(pending=2, total=12, direct=5),
        _cycle_counts(pending=2, total=12, direct=5),
    ])

    def next_counts(_uid):
        try:
            return next(counts)
        except StopIteration:
            return _cycle_counts(pending=2, total=12, direct=5)

    with patch("shopee_core.radar_cdp_service.ensure_radar_chrome_ready", return_value={"ok": True}):
        with patch("shopee_core.radar_discovery_service.get_product", return_value={"title": "Mochila Infantil Princesa Rosa Escolar"}):
            with patch("shopee_core.radar_discovery_service._get_auto_cycle_counts", side_effect=next_counts):
                with patch("shopee_core.radar_discovery_service.discover_marketplace_candidate_urls", return_value={
                    "ok": True, "urls_found": 12, "urls_inserted": 12, "urls_existing": 0,
                }):
                    with patch("shopee_core.radar_discovery_service.ensure_collection_jobs_for_linked_candidates"):
                        with patch("shopee_core.radar_discovery_service.run_linked_collection_for_product", return_value={
                            "processed": 5, "succeeded": 5, "failed": 0, "skipped": 0, "errors": [],
                        }):
                            with patch("shopee_core.radar_discovery_service.classify_linked_candidates_for_product", return_value={
                                "ok": True, "total": 5, "direct": 5, "partial": 0, "rejected": 0,
                            }):
                                with patch("shopee_core.radar_discovery_service.generate_pattern_report", return_value={"report_uid": "r1"}):
                                    with patch("shopee_core.radar_discovery_service.calculate_radar_market_confidence", return_value={
                                        "level": "medium", "score": 68, "warnings": [],
                                    }):
                                        result = run_automatic_radar_cycle(
                                            "own-1",
                                            target_confidence="high",
                                            max_cycles=2,
                                            max_collect_per_cycle=5,
                                        )

    assert result["status"] == "limit_reached"
    assert result["pending"] == 2
    assert not result["target_reached"]
    return True


def test_confidence_high_blocked_when_pending_candidates_remain():
    report = {
        "report_uid": "r1",
        "direct_count": 8,
        "partial_count": 4,
        "created_at": datetime.utcnow().isoformat(),
        "raw": {"analyses": {"price": {}}},
        "evidence_list": ["a", "b", "c"],
    }
    with patch("shopee_core.radar_discovery_service._get_auto_cycle_counts", return_value=_cycle_counts(
        pending=3, total=15, direct=8, partial=4,
    )):
        with patch("shopee_core.radar_discovery_service.get_latest_pattern_report", return_value=report):
            conf = calculate_radar_market_confidence("own-1")

    assert conf["level"] == "medium"
    assert conf["pending_count"] == 3
    assert any("pendente" in w.lower() for w in conf["warnings"])
    return True


if __name__ == "__main__":
    print("\nTESTE R7.3 - Radar Discovery Service\n")

    tests = [
        ("queries infantis uteis", test_generate_queries_infantil_escolar),
        ("sem queries genericas", test_no_generic_queries),
        ("prioridades ordenadas", test_query_priorities),
        ("ML search URL", test_build_ml_search_url),
        ("ML product URL valida", test_is_valid_ml_product_url),
        ("normaliza URL descoberta", test_normalize_discovered_url),
        ("dedupe URL descoberta", test_extract_urls_dedupes_normalized_product_links),
        ("rejeita URL fake", test_reject_fake_url),
        ("confianca sem relatorio", test_confidence_without_report),
        ("confianca apos relatorio", test_confidence_after_report),
        ("ciclo sem chrome retorna erro", test_cycle_errors_without_chrome),
        ("ciclo para sem produto", test_cycle_stops_on_missing_product),
        ("R7.3D: ciclo continua ate high", test_cycle_continues_collecting_until_target_high),
        ("R7.3D: ciclo para por limite com pendentes", test_cycle_limit_reached_with_pending_candidates),
        ("R7.3D: high bloqueado com pendentes", test_confidence_high_blocked_when_pending_candidates_remain),
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
