# -*- coding: utf-8 -*-
"""
Tests for R7.6 Chatbot Radar market context.
"""

from unittest.mock import patch

from shopee_core.chatbot_market_context_service import (
    build_chatbot_market_context_block,
    get_chatbot_radar_context,
    should_use_market_context_for_chat,
)


def _product():
    return {"name": "Mochila Infantil Princesa Rosa Escolar", "price": 89.9}


def _radar_status(confidence="high", fresh=True, has_radar=True):
    if not has_radar:
        return {
            "has_radar": False,
            "confidence_level": "insufficient",
            "warnings": ["Nenhum produto Radar encontrado."],
        }
    return {
        "has_radar": True,
        "radar_product_uid": "uid-radar",
        "confidence_level": confidence,
        "effective_competitor_count": 9,
        "effective_direct_count": 8,
        "direct_count": 10,
        "radar_report_uid": "report-1",
        "is_fresh": fresh,
        "warnings": [] if fresh else ["Relatorio Radar vencido."],
    }


def _radar_context():
    return {
        "ok": True,
        "market_summary": {
            "competitor_count": 10,
            "price_min": 33.65,
            "price_avg": 79.9,
            "price_median": 75.5,
            "price_max": 129.9,
            "confidence": "high",
        },
        "title_strategy": {
            "strong_terms": ["mochila", "infantil", "princesa", "escolar"],
        },
        "feature_strategy": {
            "recommended_features": ["escolar", "alca acolchoada", "notebook"],
            "off_niche_features": ["notebook", "natacao"],
        },
        "description_strategy": {
            "commercial_arguments": ["material resistente", "ideal para escola"],
        },
        "warnings": [],
    }


def test_price_question_activates_market_context():
    result = should_use_market_context_for_chat("Meu preco esta bom?")
    assert result["use_market_context"]
    assert result["intent"] == "price"


def test_competitor_question_activates_market_context():
    result = should_use_market_context_for_chat("Quais concorrentes estao melhores?")
    assert result["use_market_context"]
    assert result["intent"] == "competitors"


def test_general_question_does_not_activate_market_context():
    result = should_use_market_context_for_chat("Como conecto o WhatsApp?")
    assert not result["use_market_context"]
    assert result["intent"] == "general"


def test_without_active_product_requests_selection():
    result = get_chatbot_radar_context(None, "Meu preco esta bom?")
    assert result["use_market_context"]
    assert not result["market_context_used"]
    assert result["needs_product"]
    assert any("produto" in warning.lower() for warning in result["warnings"])


@patch("shopee_core.chatbot_market_context_service.build_radar_audit_context")
@patch("shopee_core.chatbot_market_context_service.get_radar_market_status_for_audit")
def test_high_fresh_radar_generates_chat_context(mock_status, mock_context):
    mock_status.return_value = _radar_status(confidence="high", fresh=True)
    mock_context.return_value = _radar_context()

    result = get_chatbot_radar_context(_product(), "Meu preco esta bom?")

    assert result["market_context_used"]
    assert result["market_context_source"] == "radar"
    assert result["radar_confidence"] == "high"
    assert "BASE RADAR PARA O CHATBOT" in result["context_block"]
    assert "R$ 33,65" in result["context_block"]


@patch("shopee_core.chatbot_market_context_service.build_radar_audit_context")
@patch("shopee_core.chatbot_market_context_service.get_radar_market_status_for_audit")
def test_stale_radar_generates_context_with_warning(mock_status, mock_context):
    mock_status.return_value = _radar_status(confidence="high", fresh=False)
    mock_context.return_value = _radar_context()

    result = get_chatbot_radar_context(_product(), "Crie um titulo melhor")

    assert result["market_context_used"]
    assert any("vencid" in warning.lower() for warning in result["warnings"])
    assert "base radar vencida" in result["context_block"].lower()


@patch("shopee_core.chatbot_market_context_service.get_radar_market_status_for_audit")
def test_absent_radar_returns_friendly_warning(mock_status):
    mock_status.return_value = _radar_status(has_radar=False)

    result = get_chatbot_radar_context(_product(), "Quais concorrentes eu tenho?")

    assert not result["market_context_used"]
    assert result["market_context_source"] == "none"
    assert any("radar" in warning.lower() for warning in result["warnings"])


def test_off_niche_notebook_never_enters_recommended_features():
    block = build_chatbot_market_context_block(
        _radar_context(),
        radar_status=_radar_status(),
        intent_info={"intent": "listing"},
    )

    recommended_line = next(
        line for line in block.splitlines()
        if line.startswith("Features recomendadas:")
    )
    assert "notebook" not in recommended_line.lower()
    assert "notebook" in block.lower()
