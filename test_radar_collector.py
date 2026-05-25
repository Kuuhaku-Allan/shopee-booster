#!/usr/bin/env python3
"""
test_radar_collector.py - R2 assisted collector unit tests.

These tests do not use the internet or open a browser.

Run:
    python test_radar_collector.py
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from unittest.mock import patch


RUN_ID = uuid.uuid4().hex
os.environ["SHOPEE_RADAR_DB_PATH"] = str(
    Path("data") / f"radar_collector_test_{RUN_ID}.db"
)

from shopee_core.radar_collector import (
    IMAGE_URL_EXTRACT_TIMEOUT,
    _dismiss_common_overlays,
    collect_mercadolivre_product,
    collect_pending_jobs,
    collect_product_page,
    is_collection_blocked_or_empty,
    normalize_image_urls,
    parse_price,
)
from shopee_core.radar_service import (
    add_product_url,
    detect_marketplace,
    get_collection_job,
    get_product,
    list_product_assets,
    mark_product_collected,
    mark_product_failed,
    save_product_assets,
)


def _fake_collected_data(url: str) -> dict:
    marketplace = detect_marketplace(url)
    return {
        "url": url,
        "canonical_url": url,
        "marketplace": marketplace,
        "title": f"Produto fake {RUN_ID}",
        "price": 129.9,
        "shop_name": "Loja Fake Radar",
        "rating": 4.8,
        "review_count": 123,
        "sold_count": 456,
        "description": "Descricao fake para teste R2",
        "image_urls": [
            f"https://img.example.com/{RUN_ID}/1.jpg",
            f"https://img.example.com/{RUN_ID}/2.jpg",
        ],
        "video_urls": [],
        "raw": {"mock": True},
    }


def test_parse_price_simple_brl():
    assert parse_price("R$ 89,90") == 89.90
    return True


def test_parse_price_brl_thousands():
    assert parse_price("R$ 1.299,99") == 1299.99
    return True


def test_parse_price_decimal_dot():
    assert parse_price("89.90") == 89.90
    return True


def test_normalize_image_urls_deduplicates():
    urls = normalize_image_urls(
        [
            "",
            " https://example.com/a.jpg ",
            "https://example.com/a.jpg",
            "//example.com/b.jpg",
            "data:image/png;base64,abc",
        ]
    )
    assert urls == ["https://example.com/a.jpg", "https://example.com/b.jpg"]
    return True


def test_detect_marketplace_shopee():
    assert detect_marketplace("https://shopee.com.br/product/123/456") == "shopee"
    return True


def test_detect_marketplace_mercadolivre():
    assert (
        detect_marketplace("https://produto.mercadolivre.com.br/MLB-123-produto-_JM")
        == "mercadolivre"
    )
    return True


def test_unknown_marketplace_returns_friendly_error():
    try:
        collect_product_page("https://example.com/produto-teste")
    except ValueError as exc:
        assert "Marketplace unknown" in str(exc)
        assert "Shopee ou Mercado Livre" in str(exc)
        return True
    raise AssertionError("Marketplace unknown deveria retornar erro amigavel")


def test_fake_collected_data_saved():
    created = add_product_url(
        f"https://shopee.com.br/product/999/{RUN_ID}fake-save",
        "competitor_candidate",
    )
    product_uid = created["product"]["product_uid"]
    data = _fake_collected_data(created["product"]["canonical_url"])

    product = mark_product_collected(product_uid, data)
    assets = save_product_assets(product_uid, image_urls=data["image_urls"])

    assert product["status"] == "collected"
    assert product["title"] == data["title"]
    assert product["price"] == data["price"]
    assert len(assets) == 2
    assert len(list_product_assets(product_uid, "image")) >= 2
    return True


def test_mark_product_collected_clears_previous_rejection_reason():
    created = add_product_url(
        f"https://shopee.com.br/product/999/{RUN_ID}clear-rejection",
        "competitor_candidate",
    )
    product_uid = created["product"]["product_uid"]

    failed = mark_product_failed(product_uid, "previous_error")
    assert failed["rejection_reason"] == "previous_error"

    collected = mark_product_collected(
        product_uid,
        _fake_collected_data(created["product"]["canonical_url"]),
    )

    assert collected["status"] == "collected"
    assert collected["rejection_reason"] is None
    return True


def test_pending_job_done_after_mock_collection():
    created = add_product_url(
        f"https://produto.mercadolivre.com.br/MLB-{RUN_ID[:8]}-mock-job-_JM",
        "competitor_candidate",
    )
    product_uid = created["product"]["product_uid"]
    job_uid = created["job"]["job_uid"]

    summary = collect_pending_jobs(limit=500, collector_func=_fake_collected_data)
    product = get_product(product_uid)
    job = get_collection_job(job_uid)
    assets = list_product_assets(product_uid, "image")

    assert summary["done"] >= 1
    assert job["status"] == "done"
    assert product["status"] == "collected"
    assert len(assets) >= 2
    return True


def test_mercadolivre_fast_collection_skips_description_details():
    with patch("shopee_core.radar_collector._needs_manual_intervention", return_value=False), \
        patch("shopee_core.radar_collector._body_text", return_value="Mochila Infantil R$ 99,90 10 vendidos"), \
        patch("shopee_core.radar_collector._page_title", return_value="Mochila Infantil | Mercado Livre"), \
        patch(
            "shopee_core.radar_collector._extract_json_ld_product",
            return_value={"name": "Mochila Infantil", "price": "99.90", "image_urls": ["https://img.example.com/a.jpg"]},
        ), \
        patch("shopee_core.radar_collector._first_text", return_value=None), \
        patch("shopee_core.radar_collector._first_meta", return_value=None), \
        patch("shopee_core.radar_collector._first_text_quick", side_effect=AssertionError("description should be skipped")):
        data = collect_mercadolivre_product(
            object(),
            "https://produto.mercadolivre.com.br/MLB-123-mochila-infantil-_JM",
            collect_image_urls=False,
        )

    assert data["title"] == "Mochila Infantil"
    assert data["price"] == 99.9
    assert data["description"] is None
    assert data["raw"]["optional_details_status"] == "skipped_fast_primary_collection"
    return True


def test_collect_product_page_fast_mode_skips_interactive_retry():
    class FakePage:
        url = "about:blank"

        def __init__(self):
            self.close_called = False

        def set_default_timeout(self, _timeout):
            pass

        def set_default_navigation_timeout(self, _timeout):
            pass

        def goto(self, url, wait_until=None, timeout=None):
            self.url = url

        def wait_for_timeout(self, _timeout):
            pass

        def close(self):
            self.close_called = True

    class FakePlaywrightContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_page = FakePage()
    fast_data = {
        "url": "https://produto.mercadolivre.com.br/MLB-123-mochila-_JM",
        "canonical_url": "https://produto.mercadolivre.com.br/MLB-123-mochila-_JM",
        "marketplace": "mercadolivre",
        "title": "Mochila Infantil",
        "price": None,
        "shop_name": None,
        "rating": None,
        "review_count": None,
        "sold_count": None,
        "description": None,
        "image_urls": [],
        "video_urls": [],
        "raw": {"optional_details_status": "skipped_fast_primary_collection"},
    }

    with patch("playwright.sync_api.sync_playwright", return_value=FakePlaywrightContext()), \
        patch("shopee_core.radar_collector.connect_to_cdp_browser", return_value=(object(), object(), fake_page)), \
        patch("shopee_core.radar_collector._needs_manual_intervention", return_value=False), \
        patch("shopee_core.radar_collector.scroll_product_page"), \
        patch("shopee_core.radar_collector.collect_mercadolivre_product", return_value=fast_data), \
        patch("shopee_core.radar_collector._needs_interactive_retry", side_effect=AssertionError("interactive retry should be skipped")):
        data = collect_product_page(
            fast_data["url"],
            marketplace="mercadolivre",
            browser_mode="cdp",
            collect_image_urls=False,
        )

    assert data["title"] == "Mochila Infantil"
    assert data["raw"]["optional_details_status"] == "skipped_fast_primary_collection"
    assert fake_page.close_called is False
    return True


def test_fast_primary_title_only_is_not_treated_as_empty_collection():
    data = {
        "marketplace": "mercadolivre",
        "title": "Mochila Infantil Escolar",
        "price": None,
        "description": None,
        "image_urls": [],
        "raw": {"optional_details_status": "skipped_fast_primary_collection"},
    }

    assert is_collection_blocked_or_empty(data) is False
    return True


# ── R7.2H: Overlay dismissal and safe image extraction ──────────────────

def test_dismiss_common_overlays_com_entendi():
    """R7.2H: Overlay com botao Entendi e fechado sem quebrar."""
    from unittest.mock import MagicMock, patch
    mock_page = MagicMock()
    mock_page.evaluate.return_value = ["clicked:entendi", "removed:andes-modal"]
    result = _dismiss_common_overlays(mock_page, max_attempts=1)
    assert "clicked:entendi" in result
    assert "removed:andes-modal" in result
    mock_page.evaluate.assert_called_once()
    return True


def test_dismiss_common_overlays_sem_overlay():
    """R7.2J: Pagina sem overlay nao causa erro (pw fallback pode executar em mock)."""
    from unittest.mock import MagicMock
    mock_page = MagicMock()
    mock_page.evaluate.return_value = []
    result = _dismiss_common_overlays(mock_page)
    assert result != []  # R7.2J: pw fallback roda em mock por causa de .first/is_visible
    assert "pw_role_click" in result
    return True


def test_dismiss_common_overlays_falha_nao_quebra():
    """R7.2J: Falha ao clicar overlay nao quebra a coleta (pw fallback roda em mock)."""
    from unittest.mock import MagicMock
    mock_page = MagicMock()
    mock_page.evaluate.side_effect = RuntimeError("evaluate failed")
    result = _dismiss_common_overlays(mock_page)
    assert result != []  # R7.2J: pw fallback roda mesmo quando evaluate falha
    assert "pw_role_click" in result
    return True


def test_dismiss_common_overlays_page_none():
    """R7.2H: page=None retorna lista vazia."""
    result = _dismiss_common_overlays(None)
    assert result == []
    return True


def test_looks_like_product_url_ml_formats():
    """R7.2K: Valida formatos de URL do Mercado Livre (/MLB-, /p/MLB, /up/MLB)."""
    from shopee_core.radar_collector import _looks_like_product_url
    
    # Formatos aceitos
    assert _looks_like_product_url("https://produto.mercadolivre.com.br/MLB-5230234162-mochila", "mercadolivre")
    assert _looks_like_product_url("https://mercadolivre.com.br/mochila/p/MLB64529079", "mercadolivre")
    assert _looks_like_product_url("https://mercadolivre.com.br/mochila/up/MLBU3488001019", "mercadolivre")
    assert _looks_like_product_url("https://www.mercadolivre.com.br/mochila/p/MLB1234567", "mercadolivre")
    
    # Rejeitados
    assert not _looks_like_product_url("https://mercadolivre.com.br/lista/mochilas", "mercadolivre")
    assert not _looks_like_product_url("https://mercadolivre.com.br/categorias/mochilas", "mercadolivre")
    return True


def test_image_url_extract_timeout_constant():
    """R7.2H: Constante de timeout de imagem definida e positiva."""
    assert isinstance(IMAGE_URL_EXTRACT_TIMEOUT, (int, float))
    assert IMAGE_URL_EXTRACT_TIMEOUT > 0
    return True


if __name__ == "__main__":
    print("\nTESTE R2 - Coletor Assistido por URL\n")

    tests = [
        ("parse_price R$ 89,90", test_parse_price_simple_brl),
        ("parse_price R$ 1.299,99", test_parse_price_brl_thousands),
        ("parse_price 89.90", test_parse_price_decimal_dot),
        ("normalize_image_urls remove duplicatas", test_normalize_image_urls_deduplicates),
        ("detect_marketplace Shopee", test_detect_marketplace_shopee),
        ("detect_marketplace Mercado Livre", test_detect_marketplace_mercadolivre),
        ("collect_product_page unknown amigavel", test_unknown_marketplace_returns_friendly_error),
        ("integracao fake salva produto/assets", test_fake_collected_data_saved),
        ("mark_product_collected limpa erro antigo", test_mark_product_collected_clears_previous_rejection_reason),
        ("pending job vira done com coleta mockada", test_pending_job_done_after_mock_collection),
        ("mercadolivre coleta rapida pula descricao", test_mercadolivre_fast_collection_skips_description_details),
        ("coleta rapida pula retry interativo", test_collect_product_page_fast_mode_skips_interactive_retry),
        ("coleta rapida com titulo nao e vazia", test_fast_primary_title_only_is_not_treated_as_empty_collection),
        ("R7.2H: dismiss overlays com Entendi", test_dismiss_common_overlays_com_entendi),
        ("R7.2H: dismiss overlays sem overlay", test_dismiss_common_overlays_sem_overlay),
        ("R7.2H: dismiss overlays falha nao quebra", test_dismiss_common_overlays_falha_nao_quebra),
        ("R7.2H: dismiss overlays page None", test_dismiss_common_overlays_page_none),
        ("R7.2H: timeout constante definida", test_image_url_extract_timeout_constant),
        ("R7.2K: ML URL formats accepted", test_looks_like_product_url_ml_formats),
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

    total = len(tests)
    print(f"\nTotal: {passed}/{total} testes passaram")
