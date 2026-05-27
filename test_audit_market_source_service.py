# -*- coding: utf-8 -*-
"""
test_audit_market_source_service.py — R7.5: Automatic market source tests.

Run:
    python -m pytest test_audit_market_source_service.py -v
"""

from __future__ import annotations

import pandas as pd
from unittest.mock import patch

from shopee_core.audit_market_source_service import (
    evaluate_scraping_market_quality,
    choose_audit_market_source,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_product(name="Mochila Teste"):
    return {"name": name, "itemid": "123", "shopid": "456", "price": 89.9}


def _make_competitor(price=50.0, title="Concorrente"):
    return {"preco": price, "titulo": title, "source": "shopee"}


def _good_scraping_df(n=10):
    return pd.DataFrame([_make_competitor(p, f"Produto {i}") for i, p in enumerate(range(30, 30 + n))])


def _poor_scraping_df(n=3):
    return pd.DataFrame([_make_competitor(None, "") for _ in range(n)])


def _make_radar_status(has=True, confidence="high", count=10, fresh=True):
    if not has:
        return {"has_radar": False, "confidence_level": None, "direct_count": 0,
                "is_fresh": False, "warnings": ["Nenhum radar."]}
    return {"has_radar": True, "product_uid": "abc-123",
            "confidence_level": confidence, "direct_count": count,
            "is_fresh": fresh, "warnings": []}


# ── Tests: evaluate_scraping_market_quality ─────────────────────────────


def test_scraping_none():
    """None input returns quality 0."""
    r = evaluate_scraping_market_quality(None)
    assert not r["ok"]
    assert r["competitor_count"] == 0


def test_scraping_empty_list():
    """Empty list returns quality 0."""
    r = evaluate_scraping_market_quality([])
    assert not r["ok"]
    assert r["competitor_count"] == 0


def test_scraping_good_df():
    """10 valid competitors → ok, quality >= 0.5."""
    r = evaluate_scraping_market_quality(_good_scraping_df(10))
    assert r["ok"]
    assert r["competitor_count"] == 10
    assert r["quality_score"] >= 0.5


def test_scraping_poor_df():
    """3 competitors without price/title → low quality."""
    r = evaluate_scraping_market_quality(_poor_scraping_df(3))
    assert r["competitor_count"] == 3
    assert r["quality_score"] < 0.5


# ── Tests: choose_audit_market_source ───────────────────────────────────


def test_scraping_good_no_radar():
    """Case A: scraping good + no radar → scraping."""
    prod = _make_product()
    result = choose_audit_market_source(prod, _good_scraping_df(10), _make_radar_status(has=False))
    assert result["source"] == "scraping"
    assert result["scraping_used"]
    assert not result["radar_used"]


def test_scraping_fails_radar_high():
    """Case B: scraping fails + radar high → radar."""
    prod = _make_product()
    result = choose_audit_market_source(prod, None, _make_radar_status(has=True, confidence="high", count=10))
    assert result["source"] == "radar"
    assert result["radar_used"]
    assert not result["scraping_used"]


def test_scraping_poor_radar_high():
    """Few scraping competitors + radar high → radar."""
    prod = _make_product()
    result = choose_audit_market_source(prod, _poor_scraping_df(3), _make_radar_status(has=True, confidence="high", count=10))
    assert result["source"] == "radar"


def test_both_good_hybrid():
    """Case C: both good → hybrid (radar preferred)."""
    prod = _make_product()
    result = choose_audit_market_source(prod, _good_scraping_df(10), _make_radar_status(has=True, confidence="high", count=10))
    assert result["source"] in ("hybrid", "radar")
    assert result["radar_used"]


def test_scraping_good_radar_low():
    """Scraping good + radar low → scraping."""
    prod = _make_product()
    result = choose_audit_market_source(prod, _good_scraping_df(10), _make_radar_status(has=True, confidence="low", count=2, fresh=False))
    assert result["source"] == "scraping"
    assert result["scraping_used"]
    assert not result["radar_used"]


def test_both_fail_none():
    """Case D: no scraping + no radar → none."""
    prod = _make_product()
    result = choose_audit_market_source(prod, None, _make_radar_status(has=False))
    assert result["source"] == "none"
    assert not result["scraping_used"]
    assert not result["radar_used"]


def test_radar_medium_scraping_few():
    """Radar medium + scraping few → radar with warning."""
    prod = _make_product()
    result = choose_audit_market_source(prod, _poor_scraping_df(2), _make_radar_status(has=True, confidence="medium", count=5))
    assert result["source"] == "radar"


def test_choose_returns_reason():
    """Result always has a non-empty reason."""
    prod = _make_product()
    result = choose_audit_market_source(prod, _good_scraping_df(10), _make_radar_status(has=False))
    assert result["reason"]
    assert isinstance(result["reason"], str)


# ── Tests: radar lookup ──────────────────────────────────────────────────


def test_get_radar_market_status_matches_product():
    """get_radar_market_status_for_audit finds matching product by title."""
    from shopee_core.audit_market_source_service import get_radar_market_status_for_audit
    with patch("shopee_core.radar_ui_service.list_radar_products_for_audit") as mock_list:
        mock_list.return_value = [
            {"product_uid": "uid-1", "title": "Mochila Infantil Rosa", "confidence": "high",
             "direct_count": 10, "can_use": True},
        ]
        prod = _make_product("Mochila Infantil Rosa Princesa")
        result = get_radar_market_status_for_audit(prod)
        assert result["has_radar"]
        assert result["product_uid"] == "uid-1"
        assert result["confidence_level"] == "high"


def test_get_radar_market_status_no_match():
    """When no Radar product matches, has_radar=False."""
    from shopee_core.audit_market_source_service import get_radar_market_status_for_audit
    with patch("shopee_core.radar_ui_service.list_radar_products_for_audit") as mock_list:
        mock_list.return_value = [
            {"product_uid": "uid-1", "title": "Tênis Corrida", "confidence": "high",
             "direct_count": 10, "can_use": True},
        ]
        prod = _make_product("Mochila Infantil")
        result = get_radar_market_status_for_audit(prod)
        assert not result["has_radar"]


# ── Runner ────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    print("\nTESTE R7.5 - Audit Market Source\n")
    tests = [
        ("scraping none", test_scraping_none),
        ("scraping empty list", test_scraping_empty_list),
        ("scraping good df", test_scraping_good_df),
        ("scraping poor df", test_scraping_poor_df),
        ("scraping good + no radar", test_scraping_good_no_radar),
        ("scraping fails + radar high", test_scraping_fails_radar_high),
        ("scraping poor + radar high", test_scraping_poor_radar_high),
        ("both good hybrid", test_both_good_hybrid),
        ("scraping good + radar low", test_scraping_good_radar_low),
        ("both fail none", test_both_fail_none),
        ("radar medium + scraping few", test_radar_medium_scraping_few),
        ("choose returns reason", test_choose_returns_reason),
        ("radar matching", test_get_radar_market_status_matches_product),
        ("radar no match", test_get_radar_market_status_no_match),
    ]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"PASS - {name}")
        except Exception as exc:
            print(f"FAIL - {name}: {exc}")
            import traceback; traceback.print_exc()
    print(f"\nTotal: {passed}/{len(tests)} passaram")
