#!/usr/bin/env python3
"""
test_radar_service.py - R1 assisted radar foundation tests.

Run:
    python test_radar_service.py
"""

from __future__ import annotations

import json
import uuid

from shopee_core.radar_db import DB_PATH
from shopee_core.radar_service import (
    add_product_url,
    add_product_urls_bulk,
    classify_product,
    get_pending_jobs,
    get_product,
    list_products,
    mark_product_collected,
)


RUN_ID = uuid.uuid4().hex


def _url_shopee(suffix: str) -> str:
    return f"https://shopee.com.br/product/12345/{RUN_ID}{suffix}"


def _url_ml(suffix: str) -> str:
    return f"https://produto.mercadolivre.com.br/MLB-{RUN_ID[:8]}{suffix}-produto-teste-_JM"


def test_add_unique_shopee_url():
    result = add_product_url(
        _url_shopee("01") + "?utm_source=teste&sp_atk=abc",
        "own_product",
        owner_user_id="user-radar-test",
        niche="escolar",
    )

    assert result["created"] is True
    assert result["duplicate"] is False
    assert result["product"]["marketplace"] == "shopee"
    assert result["product"]["status"] == "pending"
    assert result["product"]["canonical_url"].endswith(f"{RUN_ID}01")
    assert result["job"]["status"] == "pending"
    assert DB_PATH.exists()
    return True


def test_add_unique_mercadolivre_url():
    result = add_product_url(
        _url_ml("02") + "?matt_tool=tracking&utm_campaign=teste",
        "competitor_candidate",
        niche="escolar",
    )

    assert result["created"] is True
    assert result["product"]["marketplace"] == "mercadolivre"
    assert "?" not in result["product"]["canonical_url"]
    assert result["job"]["job_type"] == "collect_product_page"
    return True


def test_duplicate_with_different_querystring():
    base_url = _url_shopee("03")
    first = add_product_url(base_url + "?utm_source=a", "competitor_candidate")
    second = add_product_url(base_url + "?utm_source=b&sp_atk=xyz", "competitor_candidate")

    assert first["created"] is True
    assert second["created"] is False
    assert second["duplicate"] is True
    assert second["product"]["product_uid"] == first["product"]["product_uid"]
    return True


def test_bulk_add_urls():
    first = _url_shopee("04") + "?utm_medium=a"
    urls = [
        first,
        _url_ml("05") + "?utm_source=b",
        first + "&sp_atk=duplicate",
        "not a url",
    ]

    result = add_product_urls_bulk(
        urls,
        "competitor_candidate",
        owner_user_id="bulk-user",
        niche="papelaria",
    )

    assert result["total_received"] == 4
    assert result["created"] == 2
    assert result["duplicates"] == 1
    assert result["invalid"] == 1
    assert len(result["products"]) == 3
    assert len(result["jobs"]) == 3
    return True


def test_reject_invalid_url():
    try:
        add_product_url("not a url", "competitor_candidate")
    except ValueError:
        return True
    raise AssertionError("URL invalida deveria levantar ValueError")


def test_job_created_automatically():
    result = add_product_url(_url_shopee("06"), "own_product")
    product_uid = result["product"]["product_uid"]
    job = result["job"]

    assert job is not None
    assert job["product_uid"] == product_uid
    assert job["status"] == "pending"
    assert job["url"] == result["product"]["canonical_url"]
    return True


def test_list_pending_jobs():
    result = add_product_url(_url_ml("07"), "competitor_candidate")
    product_uid = result["product"]["product_uid"]
    jobs = get_pending_jobs(limit=500)

    assert any(job["product_uid"] == product_uid for job in jobs)
    assert all(job["status"] == "pending" for job in jobs)
    return True


def test_mark_product_collected():
    result = add_product_url(_url_shopee("08"), "competitor_candidate")
    product_uid = result["product"]["product_uid"]

    product = mark_product_collected(
        product_uid,
        {
            "title": "Mochila escolar teste",
            "price": 89.9,
            "shop_name": "Loja Radar Teste",
            "extra": {"reviews": 10},
        },
    )

    assert product["status"] == "collected"
    assert product["title"] == "Mochila escolar teste"
    assert product["price"] == 89.9
    assert product["shop_name"] == "Loja Radar Teste"
    assert product["collected_at"]
    assert json.loads(product["raw_json"])["extra"]["reviews"] == 10
    return True


def test_classify_product_competitor_direct():
    result = add_product_url(_url_ml("09"), "competitor_candidate")
    product_uid = result["product"]["product_uid"]

    product = classify_product(product_uid, "competitor_direct", 0.87)

    assert product["source_type"] == "competitor_direct"
    assert product["relevance_score"] == 0.87
    assert product["status"] == "pending"
    assert get_product(product_uid)["source_type"] == "competitor_direct"
    return True


def test_classify_product_rejected():
    result = add_product_url(_url_shopee("10"), "competitor_candidate")
    product_uid = result["product"]["product_uid"]

    product = classify_product(
        product_uid,
        "rejected",
        0.0,
        rejection_reason="Produto fora do nicho",
    )

    assert product["source_type"] == "rejected"
    assert product["status"] == "rejected"
    assert product["rejection_reason"] == "Produto fora do nicho"
    return True


def test_list_products_filters():
    add_product_url(_url_shopee("11"), "competitor_partial")
    products = list_products(
        source_type="competitor_partial",
        status="pending",
        marketplace="shopee",
        limit=50,
    )

    assert any(product["canonical_url"].endswith(f"{RUN_ID}11") for product in products)
    return True


if __name__ == "__main__":
    print("\nTESTE R1 - Radar Assistido\n")

    tests = [
        ("Adicionar URL unica da Shopee", test_add_unique_shopee_url),
        ("Adicionar URL unica do Mercado Livre", test_add_unique_mercadolivre_url),
        ("Detectar duplicada com querystring diferente", test_duplicate_with_different_querystring),
        ("Adicionar URLs em lote", test_bulk_add_urls),
        ("Rejeitar URL invalida", test_reject_invalid_url),
        ("Criar job automaticamente", test_job_created_automatically),
        ("Listar pending jobs", test_list_pending_jobs),
        ("Marcar produto como collected", test_mark_product_collected),
        ("Classificar como competitor_direct", test_classify_product_competitor_direct),
        ("Classificar como rejected", test_classify_product_rejected),
        ("Listar produtos com filtros", test_list_products_filters),
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
    print(f"DB: {DB_PATH}")
