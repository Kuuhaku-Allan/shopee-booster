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


RUN_ID = uuid.uuid4().hex
os.environ["SHOPEE_RADAR_DB_PATH"] = str(
    Path("data") / f"radar_collector_test_{RUN_ID}.db"
)

from shopee_core.radar_collector import (
    collect_pending_jobs,
    collect_product_page,
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
        ("pending job vira done com coleta mockada", test_pending_job_done_after_mock_collection),
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
