#!/usr/bin/env python3
"""
test_radar_quality_service.py - R5.1B data quality gate tests.

These tests do not use the internet or open a browser.

Run:
    python test_radar_quality_service.py
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


RUN_ID = uuid.uuid4().hex
RUN_NUM = str(uuid.uuid4().int % 10_000_000_000)
os.environ["SHOPEE_RADAR_DB_PATH"] = str(
    Path("data") / f"radar_quality_test_{RUN_ID}.db"
)

from shopee_core.radar_collector import (  # noqa: E402
    filter_product_image_urls,
    is_plausible_price,
    validate_product_extraction,
)
from shopee_core.radar_db import get_connection, init_db  # noqa: E402
from shopee_core.radar_patterns_service import generate_pattern_report  # noqa: E402
from shopee_core.radar_relevance_service import classify_candidate  # noqa: E402
from shopee_core.radar_service import add_product_url, mark_product_collected  # noqa: E402


def _ml_url(suffix: str) -> str:
    return f"https://produto.mercadolivre.com.br/MLB-{RUN_NUM}{suffix}-radar-quality-_JM"


def _product_data(title: str, price: float, image_count: int = 2) -> dict:
    image_urls = [
        f"https://http2.mlstatic.com/D_NQ_NP_2X_{index}-MLB{RUN_NUM}_{index}.webp"
        for index in range(image_count)
    ]
    return {
        "url": _ml_url("9"),
        "canonical_url": _ml_url("9"),
        "marketplace": "mercadolivre",
        "title": title,
        "price": price,
        "shop_name": "Loja Teste",
        "rating": None,
        "review_count": None,
        "sold_count": None,
        "description": "Mochila infantil feminina rosa escolar com rodinhas.",
        "image_urls": image_urls,
        "video_urls": [],
        "raw": {"mock": True},
    }


def _create_collected_product(url_suffix: str, source_type: str, data: dict) -> dict:
    created = add_product_url(_ml_url(url_suffix), source_type)
    product_uid = created["product"]["product_uid"]
    data = dict(data)
    data["url"] = created["product"]["url"]
    data["canonical_url"] = created["product"]["canonical_url"]
    return mark_product_collected(product_uid, data)


def test_generic_title_is_invalid():
    quality = validate_product_extraction(
        _product_data("Mochilas", 89.9),
        "mercadolivre",
    )
    assert quality["ok"] is False
    assert any("Titulo generico" in error for error in quality["errors"])
    return True


def test_mochila_price_3_is_invalid():
    assert is_plausible_price(3.0, "mochila") is False
    assert is_plausible_price(89.9, "mochila") is True
    quality = validate_product_extraction(
        _product_data("Mochila Infantil Rosa Escolar", 3.0),
        "mercadolivre",
    )
    assert quality["ok"] is False
    assert any("Preco suspeito" in error for error in quality["errors"])
    return True


def test_too_many_images_generates_warning_and_error():
    quality = validate_product_extraction(
        _product_data("Mochila Infantil Rosa Escolar", 89.9, image_count=81),
        "mercadolivre",
    )
    assert quality["ok"] is False
    assert any("Imagens principais demais" in warning for warning in quality["warnings"])
    assert any("Assets/imagens demais" in error for error in quality["errors"])
    return True


def test_filter_product_image_urls_limits_and_deduplicates():
    urls = [
        "https://http2.mlstatic.com/frontend-assets/logo.svg",
        "https://http2.mlstatic.com/D_NQ_NP_2X_1-MLB123_1.webp",
        "https://http2.mlstatic.com/D_NQ_NP_2X_1-MLB123_1.webp",
    ]
    urls.extend(
        f"https://http2.mlstatic.com/D_NQ_NP_2X_{index}-MLB123_{index}.webp"
        for index in range(2, 30)
    )
    filtered = filter_product_image_urls(urls)
    assert len(filtered) == 20
    assert filtered[0].endswith("1-MLB123_1.webp")
    assert not any("logo.svg" in url for url in filtered)
    return True


def test_low_quality_candidate_is_not_direct():
    own = _create_collected_product(
        "1",
        "own_product",
        _product_data("Mochila Infantil Princesa Rosa Escolar Feminina Grande", 89.9),
    )
    candidate = _create_collected_product(
        "2",
        "competitor_candidate",
        _product_data("Mochilas", 3.0, image_count=81),
    )

    result = classify_candidate(own["product_uid"], candidate["product_uid"])
    assert result["verdict"] == "rejected"
    assert result["score"] == 0.0
    assert any("Extracao de baixa qualidade" in reason for reason in result["reasons"])
    return True


def test_low_quality_direct_match_is_ignored_by_pattern_report():
    own = _create_collected_product(
        "3",
        "own_product",
        _product_data("Mochila Infantil Princesa Rosa Escolar Feminina Grande", 89.9),
    )
    good = _create_collected_product(
        "4",
        "competitor_candidate",
        _product_data("Mochila Escolar Infantil Feminina Princesa Rosa", 99.9),
    )
    bad = _create_collected_product(
        "5",
        "competitor_candidate",
        _product_data("Mochilas", 3.0, image_count=81),
    )

    classify_candidate(own["product_uid"], good["product_uid"])
    _force_direct_match(own["product_uid"], bad["product_uid"])

    report = generate_pattern_report(own["product_uid"], min_direct=1, save=True)
    assert report["price_min"] == 99.9
    assert report["direct_count"] == 1
    assert report["raw"]["ignored_low_quality"] == 1
    assert any("ignorados por baixa qualidade" in warning for warning in report["warnings"])
    return True


def _force_direct_match(own_product_uid: str, candidate_product_uid: str) -> None:
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO radar_competitor_matches (
                match_uid, own_product_uid, candidate_product_uid, verdict,
                relevance_score, confidence, reasons_json, signals_json,
                created_at, updated_at
            )
            VALUES (?, ?, ?, 'competitor_direct', 0.9, 'high', ?, ?, ?, ?)
            ON CONFLICT(own_product_uid, candidate_product_uid)
            DO UPDATE SET
                verdict = excluded.verdict,
                relevance_score = excluded.relevance_score,
                confidence = excluded.confidence,
                reasons_json = excluded.reasons_json,
                signals_json = excluded.signals_json,
                updated_at = excluded.updated_at
            """,
            (
                str(uuid.uuid4()),
                own_product_uid,
                candidate_product_uid,
                json.dumps(["forced direct for quality regression test"]),
                json.dumps({}),
                now,
                now,
            ),
        )


if __name__ == "__main__":
    print("\nTESTE R5.1B - Data Quality Gate\n")

    tests = [
        ("titulo Mochilas invalido", test_generic_title_is_invalid),
        ("preco 3 invalido para mochila", test_mochila_price_3_is_invalid),
        ("imagens demais geram warning/erro", test_too_many_images_generates_warning_and_error),
        ("filter_product_image_urls limita/deduplica", test_filter_product_image_urls_limits_and_deduplicates),
        ("low quality nao vira direct", test_low_quality_candidate_is_not_direct),
        ("low quality nao entra em pattern report", test_low_quality_direct_match_is_ignored_by_pattern_report),
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
