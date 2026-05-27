# -*- coding: utf-8 -*-
"""R7.7 integration guards for Sentinel + Radar source."""

from __future__ import annotations

from unittest.mock import patch

from shopee_core.sentinel_service import (
    mark_sentinel_finished,
    request_sentinel_execution,
    select_sentinel_competitors,
)
from telegram_service import TelegramSentinela


def _current():
    return [
        {
            "titulo": "Mochila escolar atual",
            "preco": 88.9,
            "url": "https://shopee.com.br/produto",
            "shop_id": "shop-1",
            "item_id": "item-1",
            "source": "shopee",
        }
    ]


def _radar_raw():
    return [
        {
            "title": "Mochila princesa Radar",
            "price": 99.9,
            "url": "https://produto.mercadolivre.com.br/MLB-1",
            "marketplace": "mercadolivre",
            "seller": "Loja Radar",
            "source": "radar",
            "competitor_source": "radar",
            "verdict": "competitor_direct",
        }
    ]


def test_lock_wrapper_still_calls_acquire_with_same_arguments():
    with patch("shopee_core.sentinel_service.try_acquire_sentinel_lock", return_value=True) as acquire:
        result = request_sentinel_execution(
            loja_id="loja-1",
            keyword="mochila",
            janela_execucao="2026-05-27T10",
            executor="whatsapp",
            user_id="user-1",
            shop_uid="shop-uid",
        )

    assert result["ok"]
    acquire.assert_called_once_with(
        loja_id="loja-1",
        keyword="mochila",
        janela_execucao="2026-05-27T10",
        executor="whatsapp",
        user_id="user-1",
        shop_uid="shop-uid",
    )


def test_lock_finish_wrapper_still_calls_finish_with_same_arguments():
    with patch("shopee_core.sentinel_service.finish_sentinel_lock") as finish:
        result = mark_sentinel_finished(
            loja_id="loja-1",
            keyword="mochila",
            janela_execucao="2026-05-27T10",
            status="done",
            user_id="user-1",
            shop_uid="shop-uid",
        )

    assert result["ok"]
    finish.assert_called_once_with(
        loja_id="loja-1",
        keyword="mochila",
        janela_execucao="2026-05-27T10",
        status="done",
        user_id="user-1",
        shop_uid="shop-uid",
    )


@patch("shopee_core.sentinel_competitor_source_service.choose_sentinel_competitor_source")
def test_select_sentinel_competitors_normalizes_radar_choice(mock_choose):
    mock_choose.return_value = {
        "ok": True,
        "source": "radar",
        "reason": "Radar escolhido.",
        "competitors": _radar_raw(),
        "radar_used": True,
        "current_used": False,
        "confidence": "high",
        "report_uid": "report-1",
        "effective_competitor_count": 9,
        "warnings": [],
    }

    result = select_sentinel_competitors(
        {"name": "Mochila infantil", "keyword": "mochila infantil"},
        current_competitors=_current(),
        limit=10,
    )

    assert result["source"] == "radar"
    assert result["radar_used"]
    assert result["competitors"][0]["titulo"] == "Mochila princesa Radar"
    assert result["competitors"][0]["competitor_source"] == "radar"


@patch("shopee_core.sentinel_competitor_source_service.choose_sentinel_competitor_source")
def test_radar_failure_falls_back_to_current_without_raising(mock_choose):
    mock_choose.side_effect = RuntimeError("radar offline")

    result = select_sentinel_competitors(
        {"name": "Mochila infantil", "keyword": "mochila infantil"},
        current_competitors=_current(),
        limit=10,
    )

    assert result["source"] == "current"
    assert result["competitors"]
    assert not result["radar_used"]
    assert any("radar" in warning.lower() for warning in result["warnings"])


def test_telegram_payload_includes_radar_summary_without_json():
    telegram = TelegramSentinela(token="token", chat_id="chat")
    payload = telegram._formatar_relatorio_sentinela(
        {
            "loja": "Loja Teste",
            "keyword": "mochila infantil",
            "total_analisado": 1,
            "novos_concorrentes": [],
            "preco_medio": 99.9,
            "menor_preco": 99.9,
            "maior_preco": 99.9,
            "timestamp": "2026-05-27 10:00",
            "competitor_source": "radar",
            "radar_used": True,
            "radar_confidence": "high",
            "radar_effective_competitor_count": 9,
            "concorrentes": [
                {
                    "titulo": "Mochila princesa Radar",
                    "preco": 99.9,
                    "source": "radar",
                    "competitor_source": "radar",
                }
            ],
        }
    )

    assert "Base de concorrentes" in payload
    assert "Radar" in payload
    assert "HIGH" in payload
    assert "Mochila princesa Radar" in payload
    assert "{" not in payload
