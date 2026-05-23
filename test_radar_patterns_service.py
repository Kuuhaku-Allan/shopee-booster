#!/usr/bin/env python3
"""
test_radar_patterns_service.py - R5 pattern analysis tests.

Run:
    python test_radar_patterns_service.py
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path


RUN_ID = uuid.uuid4().hex
os.environ["SHOPEE_RADAR_DB_PATH"] = str(Path("data") / f"radar_patterns_test_{RUN_ID}.db")

from shopee_core.radar_patterns_service import (
    analyze_description_patterns,
    analyze_feature_patterns,
    analyze_image_patterns,
    analyze_price_patterns,
    analyze_title_terms,
    build_recommendations,
    generate_pattern_report,
    get_latest_pattern_report,
)
from shopee_core.radar_relevance_service import classify_candidate
from shopee_core.radar_service import (
    add_product_asset,
    add_product_url,
    get_product,
    mark_product_collected,
)


def _product_row(title, price, description="", image_urls=None, assets=None, product_uid=None):
    return {
        "product_uid": product_uid or uuid.uuid4().hex,
        "title": title,
        "price": price,
        "description": description,
        "raw": {
            "description": description,
            "image_urls": image_urls or [],
            "attributes": {},
            "category_path": [],
        },
        "image_urls": image_urls or [],
        "assets": assets or [],
    }


def _create_product(title, price, source_type="competitor_candidate", description="", image_urls=None):
    created = add_product_url(
        f"https://produto.mercadolivre.com.br/MLB-{RUN_ID[:8]}{uuid.uuid4().hex[:8]}-patterns-_JM",
        source_type,
    )
    product_uid = created["product"]["product_uid"]
    data = {
        "title": title,
        "price": price,
        "shop_name": "Loja Padroes",
        "marketplace": "mercadolivre",
        "description": description,
        "image_urls": image_urls or [],
        "video_urls": [],
        "attributes": {},
        "category_path": ["Mochilas", "Escolar"],
        "raw": {"test": "R5"},
    }
    return mark_product_collected(product_uid, data)


def _seed_report_products():
    own = _create_product(
        "Mochila Infantil Rosa Escolar",
        89.9,
        source_type="own_product",
        description="Mochila infantil rosa para escola.",
        image_urls=["https://img.example.com/own.jpg"],
    )
    direct_1 = _create_product(
        "Mochila Infantil Rosa Escolar com Rodinhas",
        99.9,
        description="Mochila duravel com espaco interno, material resistente e alca acolchoada.",
        image_urls=["https://img.example.com/a1.jpg", "https://img.example.com/a2.jpg"],
    )
    direct_2 = _create_product(
        "Mochila Infantil Rosa Escolar Princesa Grande",
        79.9,
        description="Mochila com organizacao, conforto, qualidade premium e costura reforcada.",
        image_urls=["https://img.example.com/b1.jpg", "https://img.example.com/b2.jpg", "https://img.example.com/b3.jpg"],
    )
    rejected = _create_product(
        "Lancheira Infantil Rosa Princesa Termica",
        39.9,
        description="Lancheira termica infantil para lanche escolar.",
        image_urls=["https://img.example.com/c1.jpg"],
    )
    classify_candidate(own["product_uid"], direct_1["product_uid"])
    classify_candidate(own["product_uid"], direct_2["product_uid"])
    classify_candidate(own["product_uid"], rejected["product_uid"])
    return own, direct_1, direct_2, rejected


def test_analyze_price_patterns():
    products = [
        _product_row("A", 10),
        _product_row("B", 20),
        _product_row("C", 30),
    ]
    result = analyze_price_patterns(products)
    assert result["min"] == 10
    assert result["max"] == 30
    assert result["avg"] == 20
    assert result["median"] == 20
    return True


def test_analyze_title_terms():
    products = [
        _product_row("Mochila Infantil Rosa com Rodinhas", 90),
        _product_row("Mochila Escolar Infantil Rosa", 80),
    ]
    result = analyze_title_terms(products)
    terms = {row["term"]: row["count"] for row in result["top_terms"]}
    assert terms["mochila"] == 2
    assert terms["infantil"] == 2
    assert "com" not in terms
    return True


def test_analyze_feature_patterns():
    products = [
        _product_row("Mochila com rodinhas", 90, "alca acolchoada e costura reforcada"),
        _product_row("Mochila rodinhas princesa", 80, "costura reforcada"),
    ]
    result = analyze_feature_patterns(products)
    features = {row["feature"]: row for row in result["features"]}
    assert features["rodinhas"]["count"] == 2
    assert any(row["feature"] == "costura reforcada" for row in result["strong_patterns"])
    return True


def test_analyze_description_patterns():
    products = [
        _product_row("Mochila A", 90, "material resistente com espaco interno e conforto"),
        _product_row("Mochila B", 80, "alta qualidade premium com garantia"),
    ]
    result = analyze_description_patterns(products)
    arguments = {row["argument"] for row in result["commercial_arguments"]}
    assert "material resistente" in arguments
    assert "espaco interno" in arguments
    assert "garantia" in arguments
    return True


def test_analyze_image_patterns():
    products = [
        _product_row("A", 90, image_urls=["1", "2", "3"]),
        _product_row("B", 80, image_urls=["1"]),
    ]
    result = analyze_image_patterns(products)
    assert result["avg_image_count"] == 2
    assert result["min_image_count"] == 1
    assert result["max_image_count"] == 3
    return True


def test_build_recommendations_title():
    own = {"product_uid": "own", "title": "Mochila Rosa", "price": 120, "raw_json": "{}"}
    analyses = {
        "title_terms": {"strong_terms": [{"term": "infantil", "count": 3, "frequency": 1.0}]},
        "price": {"avg": 80, "median": 80, "suggested_band": {"low": 70, "high": 90}},
        "features": {"strong_patterns": []},
        "description": {"common_promises": []},
        "images": {"avg_image_count": 0},
    }
    recommendations = build_recommendations(own, analyses)
    assert any(item["type"] == "title" and "infantil" in item["recommendation"] for item in recommendations)
    return True


def test_generate_pattern_report_salva():
    own, *_ = _seed_report_products()
    report = generate_pattern_report(own["product_uid"])
    latest = get_latest_pattern_report(own["product_uid"])
    assert report["report_uid"] == latest["report_uid"]
    assert report["direct_count"] == 2
    assert report["total_competitors"] == 2
    return True


def test_menos_de_3_concorrentes_gera_warning():
    own = _create_product("Mochila Infantil Rosa Escolar", 89.9, source_type="own_product")
    direct = _create_product("Mochila Infantil Rosa Escolar com Rodinhas", 99.9)
    classify_candidate(own["product_uid"], direct["product_uid"])
    report = generate_pattern_report(own["product_uid"])
    assert any("Base pequena" in warning for warning in report["warnings"])
    return True


def test_get_latest_pattern_report():
    own, *_ = _seed_report_products()
    first = generate_pattern_report(own["product_uid"])
    second = generate_pattern_report(own["product_uid"])
    latest = get_latest_pattern_report(own["product_uid"])
    assert latest["report_uid"] == second["report_uid"]
    assert latest["report_uid"] != first["report_uid"]
    return True


def test_relatorio_ignora_rejected():
    own, direct_1, direct_2, rejected = _seed_report_products()
    report = generate_pattern_report(own["product_uid"])
    titles = [item["title"] for item in report["raw"]["competitors"]]
    assert direct_1["title"] in titles
    assert direct_2["title"] in titles
    assert rejected["title"] not in titles
    return True


if __name__ == "__main__":
    print("\nTESTE R5 - Analise de Padroes\n")

    tests = [
        ("price min/max/avg/median", test_analyze_price_patterns),
        ("title terms remove stopwords", test_analyze_title_terms),
        ("feature patterns recorrentes", test_analyze_feature_patterns),
        ("description arguments", test_analyze_description_patterns),
        ("image patterns media", test_analyze_image_patterns),
        ("recommendation de titulo", test_build_recommendations_title),
        ("generate_pattern_report salva", test_generate_pattern_report_salva),
        ("menos de 3 gera warning", test_menos_de_3_concorrentes_gera_warning),
        ("get_latest_pattern_report", test_get_latest_pattern_report),
        ("relatorio ignora rejected", test_relatorio_ignora_rejected),
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
