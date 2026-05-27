# -*- coding: utf-8 -*-
"""
Tests for R7.6 Chatbot integration with Radar market context.
"""

from unittest.mock import patch

import backend_core
from backend_core import process_chat_turn
from shopee_core.chatbot_service import run_chatbot_turn


class _DummyResponse:
    text = "Resposta gerada com contexto."


class _DummyModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, model, contents, config=None):
        self.calls.append({"model": model, "contents": contents, "config": config})
        return _DummyResponse()


class _DummyClient:
    def __init__(self):
        self.models = _DummyModels()


def _market_context(used=True):
    return {
        "ok": True,
        "use_market_context": used,
        "market_context_used": used,
        "market_context_source": "radar" if used else "none",
        "radar_confidence": "high" if used else None,
        "radar_report_uid": "report-1" if used else None,
        "context_block": "BLOCO RADAR TESTE" if used else "",
        "warnings": [],
    }


def _product():
    return {"name": "Mochila Infantil Princesa", "price": 89.9}


@patch("backend_core.MODELOS_TEXTO", ["gemini-3.1-flash-lite"])
@patch("backend_core.detect_chat_intents", return_value=["general"])
@patch("shopee_core.chatbot_market_context_service.get_chatbot_radar_context")
def test_process_chat_turn_injects_radar_for_market_question(mock_market, mock_intents):
    dummy_client = _DummyClient()
    mock_market.return_value = _market_context(used=True)

    with patch("backend_core.get_client", return_value=dummy_client):
        result = process_chat_turn(
            user_message="Meu preco esta bom comparado aos concorrentes?",
            attachments=[],
            attachment_types=[],
            chat_history=[],
            full_context="CONTEXTO BASE",
            segmento="Mochilas",
            selected_product=_product(),
        )

    assert result["market_context_used"]
    assert result["market_context_source"] == "radar"
    assert result["radar_confidence"] == "high"
    prompt = dummy_client.models.calls[0]["contents"][0]
    assert "CONTEXTO BASE" in prompt
    assert "BLOCO RADAR TESTE" in prompt


@patch("backend_core.MODELOS_TEXTO", ["gemini-3.1-flash-lite"])
@patch("backend_core.detect_chat_intents", return_value=["general"])
@patch("shopee_core.chatbot_market_context_service.get_chatbot_radar_context")
def test_process_chat_turn_does_not_inject_radar_for_general_question(mock_market, mock_intents):
    dummy_client = _DummyClient()
    mock_market.return_value = _market_context(used=False)

    with patch("backend_core.get_client", return_value=dummy_client):
        result = process_chat_turn(
            user_message="Como conecto o WhatsApp?",
            attachments=[],
            attachment_types=[],
            chat_history=[],
            full_context="CONTEXTO BASE",
            segmento="Mochilas",
        )

    assert not result["market_context_used"]
    prompt = dummy_client.models.calls[0]["contents"][0]
    assert "BLOCO RADAR TESTE" not in prompt


@patch("backend_core.detect_chat_intents", return_value=["general"])
@patch("shopee_core.chatbot_market_context_service.get_chatbot_radar_context")
def test_process_chat_turn_asks_for_product_when_market_context_has_no_active_product(mock_market, mock_intents):
    mock_market.return_value = {
        "ok": False,
        "use_market_context": True,
        "market_context_used": False,
        "market_context_source": "none",
        "needs_product": True,
        "context_block": "",
        "warnings": ["Posso usar o Radar, mas preciso saber qual produto voce quer analisar."],
    }

    result = process_chat_turn(
        user_message="Meu preco esta bom?",
        attachments=[],
        attachment_types=[],
        chat_history=[],
        full_context="",
        segmento="Mochilas",
        channel="whatsapp",
    )

    assert not result["market_context_used"]
    assert "preciso saber qual produto" in result["text"].lower()


@patch("backend_core.detect_chat_intents", return_value=["optimize_listing"])
@patch("shopee_core.chatbot_market_context_service.get_chatbot_radar_context")
@patch("backend_core.generate_full_optimization")
def test_optimize_listing_passes_radar_context_to_generator(mock_generate, mock_market, mock_intents):
    mock_market.return_value = _market_context(used=True)
    mock_generate.return_value = "Otimizacao com Radar"

    result = process_chat_turn(
        user_message="Crie um titulo melhor",
        attachments=[],
        attachment_types=[],
        chat_history=[],
        full_context="",
        segmento="Mochilas",
        selected_product=_product(),
    )

    assert result["text"] == "Otimizacao com Radar"
    assert result["market_context_used"]
    call_kwargs = mock_generate.call_args[1]
    assert call_kwargs["radar_context_block"] == "BLOCO RADAR TESTE"


def test_run_chatbot_turn_preserves_market_metadata():
    with patch("backend_core.process_chat_turn") as mock_process:
        mock_process.return_value = {
            "text": "ok",
            "intent": "general",
            "images": [],
            "captions": [],
            "post_actions": [],
            "market_context_used": True,
            "market_context_source": "radar",
            "radar_confidence": "medium",
            "radar_report_uid": "report-2",
            "warnings": ["Radar vencido."],
        }

        result = run_chatbot_turn(
            user_message="Meu preco esta bom?",
            segmento="Mochilas",
            selected_product=_product(),
        )

    assert result["market_context_used"]
    assert result["market_context_source"] == "radar"
    assert result["radar_confidence"] == "medium"
    assert result["warnings"] == ["Radar vencido."]


def test_model_fallback_has_three_current_text_models():
    assert backend_core.MODELOS_TEXTO == [
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
    ]
