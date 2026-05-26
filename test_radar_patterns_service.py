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
    cluster_competitor_variants,
    format_brl_markdown,
    generate_pattern_report,
    get_latest_pattern_report,
    _build_strategy_features,
)
from shopee_core.radar_db import get_connection, init_db
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


# ── R7.2L Tests ──────────────────────────────────────────────────────────


def test_candidate_scope_direct_only():
    """Direct_only uses only competitor_direct matches."""
    own = _create_product("Mochila Infantil Rosa Escolar", 89.9, source_type="own_product")
    direct = _create_product("Mochila Infantil Rosa com Rodinhas", 99.9)
    partial = _create_product("Mochila Juvenil Rosa Escolar", 79.9)
    classify_candidate(own["product_uid"], direct["product_uid"])
    classify_candidate(own["product_uid"], partial["product_uid"])
    # Force partial verdict for the second candidate
    with get_connection() as conn:
        conn.execute(
            "UPDATE radar_competitor_matches SET verdict = 'competitor_partial' WHERE own_product_uid = ? AND candidate_product_uid = ?",
            (own["product_uid"], partial["product_uid"])
        )

    report = generate_pattern_report(own["product_uid"], candidate_scope="direct_only")
    assert report["direct_count"] == 1
    assert report["partial_count"] == 0
    assert report["total_competitors"] == 1
    return True


def test_candidate_scope_direct_plus_partial():
    """Direct_plus_partial includes partial matches."""
    own = _create_product("Mochila Infantil Rosa Escolar", 89.9, source_type="own_product")
    direct = _create_product("Mochila Infantil Rosa com Rodinhas", 99.9)
    partial = _create_product("Mochila Juvenil Rosa Escolar", 79.9)
    classify_candidate(own["product_uid"], direct["product_uid"])
    classify_candidate(own["product_uid"], partial["product_uid"])
    with get_connection() as conn:
        conn.execute(
            "UPDATE radar_competitor_matches SET verdict = 'competitor_partial' WHERE own_product_uid = ? AND candidate_product_uid = ?",
            (own["product_uid"], partial["product_uid"])
        )

    report = generate_pattern_report(own["product_uid"], candidate_scope="direct_plus_partial")
    assert report["direct_count"] == 1
    assert report["partial_count"] == 1
    assert report["total_competitors"] == 2
    return True


def test_confidence_medium_with_5_direct():
    """5 direct competitors yields medium confidence."""
    own = _create_product("Mochila Infantil Rosa Escolar", 89.9, source_type="own_product")
    titles = [
        "Mochila Infantil Rosa Escolar Princesa Grande",
        "Mochila Infantil Rosa Escolar Unicornio Reforcada",
        "Mochila Infantil Rosa Escolar Rodinhas Costas",
        "Mochila Infantil Rosa Escolar Gatinho Organizadora",
        "Mochila Infantil Rosa Escolar Sereia Impermeavel",
    ]
    for i, title in enumerate(titles):
        p = _create_product(title, 80.0 + i * 8)
        classify_candidate(own["product_uid"], p["product_uid"])
    report = generate_pattern_report(own["product_uid"])
    assert report["direct_count"] >= 5, f"Got {report['direct_count']} direct, expected >=5"
    assert report["effective_direct_count"] >= 5
    assert report["confidence"] == "medium"
    return True


def test_confidence_high_with_10_direct():
    """10 direct competitors yields high confidence."""
    own = _create_product("Mochila Infantil Rosa Escolar", 89.9, source_type="own_product")
    titles = [
        "Mochila Infantil Rosa Escolar Princesa Grande",
        "Mochila Infantil Rosa Escolar Unicornio Reforcada",
        "Mochila Infantil Rosa Escolar Rodinhas Costas",
        "Mochila Infantil Rosa Escolar Gatinho Organizadora",
        "Mochila Infantil Rosa Escolar Sereia Impermeavel",
        "Mochila Infantil Rosa Escolar Floral Lilas",
        "Mochila Infantil Rosa Escolar Dinossauro Colorida",
        "Mochila Infantil Rosa Escolar Hello Kitty",
        "Mochila Infantil Rosa Escolar Bailarina",
        "Mochila Infantil Rosa Escolar Feminina Premium",
    ]
    for i, title in enumerate(titles):
        p = _create_product(title, 70.0 + i * 9)
        classify_candidate(own["product_uid"], p["product_uid"])
    report = generate_pattern_report(own["product_uid"])
    assert report["direct_count"] >= 10, f"Got {report['direct_count']} direct, expected >=10"
    assert report["effective_direct_count"] >= 10
    assert report["confidence"] == "high"
    return True


def test_strategy_sections_present():
    """Report has all R7.2L strategy sections."""
    own, direct_1, direct_2, _ = _seed_report_products()
    report = generate_pattern_report(own["product_uid"])
    assert "strategy_title" in report
    assert "strategy_features" in report
    assert "strategy_description" in report
    assert "strategy_images" in report
    assert "evidence_list" in report
    assert "candidate_scope" in report
    return True


def test_evidence_list_includes_competitors():
    """Evidence list contains all competitors used in report."""
    own, direct_1, direct_2, _ = _seed_report_products()
    report = generate_pattern_report(own["product_uid"])
    evidence_uids = {e["product_uid"] for e in report["evidence_list"]}
    assert direct_1["product_uid"] in evidence_uids
    assert direct_2["product_uid"] in evidence_uids
    return True


def test_price_dispersion_warning():
    """High price dispersion generates warning."""
    products = [
        _product_row("A", 10),
        _product_row("B", 100),
        _product_row("C", 200),
    ]
    result = analyze_price_patterns(products)
    assert result["dispersion_warning"] is not None
    assert "dispersao" in result["dispersion_warning"]
    return True


def test_relatorio_escopo_salvo_e_recuperado():
    """candidate_scope is saved and recovered from DB."""
    own = _create_product("Mochila Teste", 89.9, source_type="own_product")
    p = _create_product("Mochila Similar", 99.9)
    classify_candidate(own["product_uid"], p["product_uid"])
    report = generate_pattern_report(own["product_uid"], candidate_scope="direct_plus_partial")
    latest = get_latest_pattern_report(own["product_uid"])
    assert latest["candidate_scope"] == "direct_plus_partial"
    return True


# ── R7.2L.1 Tests ────────────────────────────────────────────────────────


def test_noise_terms_removed_from_strong():
    """Noise terms (cor, desenho, tecido, lisa) are not in strong_terms."""
    products = [
        _product_row("Mochila Cor Rosa Desenho Princesa Tecido Lisa", 90),
        _product_row("Mochila Rosa Cor Tecido Lisa", 80),
    ]
    result = analyze_title_terms(products)
    strong = {row["term"] for row in result["strong_terms"]}
    for noise in ("cor", "desenho", "tecido", "lisa"):
        assert noise not in strong, f"Noise term '{noise}' found in strong_terms"
    # But meaningful terms should be there
    assert "mochila" in strong
    assert "rosa" in strong
    return True


def test_notebook_off_niche():
    """Notebook continues to be detected as off-niche for child school niche."""
    own = _product_row("Mochila Infantil Rosa Escolar", 89.9, product_uid="own")
    products = [
        _product_row("Mochila Infantil Rosa Escolar com Notebook", 99.9),
    ]
    result = analyze_feature_patterns(products, own_product=own)
    off_niche = {row["feature"] for row in result["off_niche_features"]}
    assert "notebook" in off_niche
    return True


def test_menino_menina_not_off_niche():
    """Both genders (menino menina) does NOT trigger masculina off-niche."""
    own = _product_row("Mochila Infantil Rosa Escolar", 89.9, product_uid="own")
    products = [
        _product_row("Mochila Infantil Menino Menina Escolar", 99.9),
    ]
    result = analyze_feature_patterns(products, own_product=own)
    off_niche = {row["feature"] for row in result["off_niche_features"]}
    assert "masculina" not in off_niche, "menino menina should not be off-niche"
    return True


def test_price_has_band_label():
    """Price analysis includes band_label and band_disclaimer."""
    products = [
        _product_row("A", 50),
        _product_row("B", 100),
    ]
    result = analyze_price_patterns(products)
    assert "band_label" in result
    assert "band_disclaimer" in result
    assert "Faixa competitiva" in result["band_label"]
    return True


def test_notebook_off_niche_never_recommended():
    own = _product_row("Mochila Infantil Princesa Rosa Escolar", 89.9, product_uid="own")
    products = [
        _product_row("Mochila Escolar Infantil com Notebook", 99.9),
        _product_row("Mochila Infantil Feminina Notebook Reforcada", 109.9),
        _product_row("Mochila Princesa Infantil Notebook Grande", 119.9),
    ]
    features = analyze_feature_patterns(products, own_product=own)
    strategy = _build_strategy_features({"features": features})

    assert "notebook" in {row["feature"] for row in features["off_niche_features"]}
    assert "notebook" not in strategy["recommended"]
    assert not (set(strategy["recommended"]) & set(strategy["off_niche"]))
    return True


def test_cluster_competitor_variants_counts_duplicate_title_as_one():
    candidates = [
        {
            "product_uid": "a",
            "url": "https://produto.mercadolivre.com.br/MLB-111-a-_JM",
            "title": "Mochila Escolar Infantil Menino Menina Gatinho Dinossauro 3d",
            "shop_name": "Loja Kids",
            "price": 79.9,
            "match_verdict": "competitor_direct",
            "match_relevance_score": 0.82,
        },
        {
            "product_uid": "b",
            "url": "https://produto.mercadolivre.com.br/MLB-222-b-_JM",
            "title": "Mochila Escolar Infantil Menino Menina Gatinho Dinossauro 3d",
            "shop_name": "Loja Kids",
            "price": 81.0,
            "match_verdict": "competitor_direct",
            "match_relevance_score": 0.8,
        },
    ]
    clusters = cluster_competitor_variants(candidates)
    assert len(clusters) == 1
    assert clusters[0]["variants_count"] == 2
    return True


def test_low_recurrence_terms_filter_numeric_brands_and_noise():
    products = [
        _product_row("Mochila Nabaiji 10L Prova Agua Up4you Marechal", 90),
        _product_row("Mochila Infantil Escolar Princesa", 80),
        _product_row("Mochila Infantil Escolar Feminina", 85),
    ]
    result = analyze_title_terms(products)
    terms = {row["term"] for row in result["top_terms"]}
    for noise in {"10l", "nabaiji", "up4you", "marechal", "agua", "prova"}:
        assert noise not in terms
    return True


def test_brl_markdown_formatter_preserves_dollar_sign():
    assert format_brl_markdown(33.65) == r"R\$ 33,65"
    assert format_brl_markdown(264.1) == r"R\$ 264,10"
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
        # R7.2L
        ("scope direct_only", test_candidate_scope_direct_only),
        ("scope direct_plus_partial", test_candidate_scope_direct_plus_partial),
        ("confidence medium com 5 direct", test_confidence_medium_with_5_direct),
        ("confidence high com 10 direct", test_confidence_high_with_10_direct),
        ("strategy sections present", test_strategy_sections_present),
        ("evidence list includes competitors", test_evidence_list_includes_competitors),
        ("price dispersion warning", test_price_dispersion_warning),
        ("scope salvo e recuperado", test_relatorio_escopo_salvo_e_recuperado),
        # R7.2L.1
        ("noise terms removidos", test_noise_terms_removed_from_strong),
        ("notebook off-niche", test_notebook_off_niche),
        ("menino menina nao off-niche", test_menino_menina_not_off_niche),
        ("price band label presente", test_price_has_band_label),
        ("notebook nunca recomendado", test_notebook_off_niche_never_recommended),
        ("cluster duplica titulo como um", test_cluster_competitor_variants_counts_duplicate_title_as_one),
        ("termos ruido filtrados", test_low_recurrence_terms_filter_numeric_brands_and_noise),
        ("BRL markdown preserva cifrao", test_brl_markdown_formatter_preserves_dollar_sign),
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
