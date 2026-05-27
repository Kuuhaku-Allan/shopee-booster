# -*- coding: utf-8 -*-
"""Tests for R7.7 Sentinel competitor source selection."""

from __future__ import annotations

from unittest.mock import patch

from shopee_core.sentinel_competitor_source_service import (
    choose_sentinel_competitor_source,
    get_radar_competitors_for_sentinel,
    normalize_sentinel_competitors,
)


def _current_competitor(i=1, source="shopee"):
    return {
        "titulo": f"Mochila infantil escolar {i}",
        "preco": 79.9 + i,
        "url": f"https://shopee.com.br/produto-{i}",
        "shop_id": f"shop-{i}",
        "item_id": f"item-{i}",
        "source": source,
    }


def _radar_match(i=1, verdict="competitor_direct", price=89.9):
    return {
        "candidate_product_uid": f"radar-cand-{i}",
        "title": f"Mochila princesa escolar concorrente {i}",
        "price": price,
        "canonical_url": f"https://produto.mercadolivre.com.br/MLB-{i}-mochila-_JM",
        "marketplace": "mercadolivre",
        "shop_name": f"Loja Radar {i}",
        "relevance_score": 0.8,
        "verdict": verdict,
    }


def _radar_status(confidence="high", fresh=True, count=8):
    return {
        "has_radar": True,
        "radar_product_uid": "own-radar",
        "confidence_level": confidence,
        "effective_competitor_count": count,
        "is_fresh": fresh,
        "radar_report_uid": "report-1",
        "warnings": [] if fresh else ["Relatorio Radar vencido."],
    }


def _radar_result(confidence="high", count=8):
    return {
        "ok": True,
        "source": "radar",
        "confidence": confidence,
        "report_uid": "report-1",
        "effective_competitor_count": count,
        "competitors": [_radar_match(i) for i in range(1, count + 1)],
        "warnings": [],
    }


@patch("shopee_core.radar_relevance_service.get_matches_for_product")
@patch("shopee_core.radar_patterns_service.get_latest_pattern_report")
def test_radar_high_fresh_returns_competitors(mock_report, mock_matches):
    mock_report.return_value = {
        "confidence": "high",
        "effective_competitor_count": 8,
        "report_uid": "report-1",
    }
    mock_matches.side_effect = lambda uid, verdict=None: [_radar_match(1, verdict), _radar_match(2, verdict)]

    result = get_radar_competitors_for_sentinel("own-radar", limit=2)

    assert result["ok"]
    assert result["source"] == "radar"
    assert result["confidence"] == "high"
    assert len(result["competitors"]) == 2
    requested_verdicts = [call.kwargs.get("verdict") for call in mock_matches.call_args_list]
    assert "competitor_rejected" not in requested_verdicts
    assert "rejected" not in requested_verdicts


@patch("shopee_core.radar_relevance_service.get_matches_for_product")
@patch("shopee_core.radar_patterns_service.get_latest_pattern_report")
def test_radar_ignores_items_without_price(mock_report, mock_matches):
    mock_report.return_value = {
        "confidence": "high",
        "effective_competitor_count": 5,
        "report_uid": "report-1",
    }
    mock_matches.side_effect = [
        [_radar_match(1, price=None), _radar_match(2, price=99.9)],
        [],
    ]

    result = get_radar_competitors_for_sentinel("own-radar", limit=10)

    assert result["ok"]
    assert len(result["competitors"]) == 1
    assert result["competitors"][0]["price"] == 99.9
    assert any("ignorado" in warning.lower() for warning in result["warnings"])


def test_normalize_limits_top_10():
    competitors = [_current_competitor(i) for i in range(1, 16)]

    result = normalize_sentinel_competitors(competitors, keyword="mochila", limit=10)

    assert len(result) == 10
    assert result[0]["ranking"] == 1
    assert result[-1]["ranking"] == 10


def test_current_good_wins_when_radar_not_clearly_better(monkeypatch):
    monkeypatch.setenv("SHOPEE_SENTINEL_USE_RADAR", "1")
    current = [_current_competitor(i) for i in range(1, 7)]

    with patch(
        "shopee_core.sentinel_competitor_source_service.get_radar_competitors_for_sentinel",
        return_value=_radar_result(count=7),
    ):
        result = choose_sentinel_competitor_source(
            {"name": "Mochila infantil"},
            current_competitors=current,
            radar_status=_radar_status(count=7),
            limit=10,
        )

    assert result["source"] == "current"
    assert result["current_used"]
    assert not result["radar_used"]


def test_feature_flag_disabled_preserves_current_flow(monkeypatch):
    monkeypatch.delenv("SHOPEE_SENTINEL_USE_RADAR", raising=False)
    current = [_current_competitor(1)]

    result = choose_sentinel_competitor_source(
        {"name": "Mochila infantil"},
        current_competitors=current,
        radar_status=_radar_status(count=8),
        limit=10,
    )

    assert result["source"] == "current"
    assert result["competitors"]
    assert not result["radar_used"]


def test_current_mock_loses_to_high_fresh_radar(monkeypatch):
    monkeypatch.setenv("SHOPEE_SENTINEL_USE_RADAR", "1")
    current = [_current_competitor(i, source="mock") for i in range(1, 8)]

    with patch(
        "shopee_core.sentinel_competitor_source_service.get_radar_competitors_for_sentinel",
        return_value=_radar_result(count=8),
    ):
        result = choose_sentinel_competitor_source(
            {"name": "Mochila infantil"},
            current_competitors=current,
            radar_status=_radar_status(count=8),
            limit=10,
        )

    assert result["source"] == "radar"
    assert result["radar_used"]
    assert "mock" in result["reason"].lower()


def test_current_fails_high_fresh_radar_chosen(monkeypatch):
    monkeypatch.setenv("SHOPEE_SENTINEL_USE_RADAR", "1")

    with patch(
        "shopee_core.sentinel_competitor_source_service.get_radar_competitors_for_sentinel",
        return_value=_radar_result(count=8),
    ):
        result = choose_sentinel_competitor_source(
            {"name": "Mochila infantil"},
            current_competitors=[],
            radar_status=_radar_status(count=8),
            limit=10,
        )

    assert result["source"] == "radar"
    assert result["radar_used"]


def test_current_fails_stale_radar_chosen_with_warning(monkeypatch):
    monkeypatch.setenv("SHOPEE_SENTINEL_USE_RADAR", "1")

    with patch(
        "shopee_core.sentinel_competitor_source_service.get_radar_competitors_for_sentinel",
        return_value=_radar_result(count=8),
    ):
        result = choose_sentinel_competitor_source(
            {"name": "Mochila infantil"},
            current_competitors=[],
            radar_status=_radar_status(fresh=False, count=8),
            limit=10,
        )

    assert result["source"] == "radar"
    assert any("vencid" in warning.lower() for warning in result["warnings"])


def test_current_fails_absent_radar_returns_none(monkeypatch):
    monkeypatch.setenv("SHOPEE_SENTINEL_USE_RADAR", "1")
    radar_status = {
        "has_radar": False,
        "confidence_level": "insufficient",
        "effective_competitor_count": 0,
        "is_fresh": False,
        "warnings": ["Base Radar ausente."],
    }

    result = choose_sentinel_competitor_source(
        {"name": "Mochila infantil"},
        current_competitors=[],
        radar_status=radar_status,
        limit=10,
    )

    assert result["source"] == "none"
    assert not result["ok"]
    assert any("radar" in warning.lower() for warning in result["warnings"])


def test_keyword_cycle_infers_radar_product_for_fallback(monkeypatch):
    monkeypatch.setenv("SHOPEE_SENTINEL_USE_RADAR", "1")
    empty_status = {
        "has_radar": False,
        "confidence_level": "insufficient",
        "effective_competitor_count": 0,
        "is_fresh": False,
        "warnings": ["Produto sem UID Radar."],
    }

    with (
        patch(
            "shopee_core.audit_market_source_service.get_radar_market_status_for_audit",
            side_effect=[empty_status, _radar_status(count=8)],
        ),
        patch(
            "shopee_core.radar_ui_service.list_radar_products_for_audit",
            return_value=[
                {
                    "product_uid": "own-radar",
                    "title": "Mochila Infantil Princesa Rosa Escolar Feminina Grande",
                    "confidence": "high",
                    "can_use": True,
                }
            ],
        ),
        patch(
            "shopee_core.sentinel_competitor_source_service.get_radar_competitors_for_sentinel",
            return_value=_radar_result(count=8),
        ),
    ):
        result = choose_sentinel_competitor_source(
            {"keyword": "mochilas"},
            current_competitors=[],
            radar_status=None,
            limit=10,
        )

    assert result["source"] == "radar"
    assert result["radar_used"]
    assert result["radar_status"].get("sentinel_inferred_from_keyword") is True
