#!/usr/bin/env python3
"""
test_radar_relevance_service.py - R4 relevance filter tests.

Run:
    python test_radar_relevance_service.py
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path


RUN_ID = uuid.uuid4().hex
os.environ["SHOPEE_RADAR_DB_PATH"] = str(Path("data") / f"radar_relevance_test_{RUN_ID}.db")

from shopee_core.radar_relevance_service import (
    build_product_profile,
    classify_candidate,
    classify_candidates_for_product,
    compare_product_profiles,
    get_matches_for_product,
)
from shopee_core.radar_service import add_product_url, get_product, mark_product_collected


def _url(suffix: str) -> str:
    return f"https://produto.mercadolivre.com.br/MLB-{RUN_ID[:8]}{suffix}-radar-r4-_JM"


def _product(title: str, price=99.9, source_type="competitor_candidate", description=None, raw=None) -> dict:
    created = add_product_url(_url(uuid.uuid4().hex[:8]), source_type)
    product_uid = created["product"]["product_uid"]
    data = {
        "title": title,
        "price": price,
        "shop_name": "Loja Teste R4",
        "description": description,
        "marketplace": "mercadolivre",
        "image_urls": [],
        "video_urls": [],
        "raw": {},
    }
    if raw:
        data.update(raw)
    return mark_product_collected(product_uid, data)


def _compare(own_title: str, candidate_title: str, own_price=99.9, candidate_price=99.9):
    own = _product(own_title, price=own_price, source_type="own_product")
    candidate = _product(candidate_title, price=candidate_price)
    return compare_product_profiles(build_product_profile(own), build_product_profile(candidate))


def test_mochila_infantil_rosa_vs_princesa_direct():
    result = _compare(
        "Mochila infantil escolar rosa com rodinhas",
        "Mochila princesa rosa infantil escolar com rodinhas",
    )
    assert result["verdict"] == "competitor_direct"
    assert result["score"] >= 0.72
    return True


def test_mochila_infantil_rosa_vs_escolar_menina_direct_or_partial():
    result = _compare(
        "Mochila infantil rosa escolar",
        "Mochila escolar menina colorida",
    )
    assert result["verdict"] in {"competitor_direct", "competitor_partial"}
    assert result["score"] >= 0.45
    return True


def test_mochila_infantil_vs_universitaria_notebook_rejected_or_low_partial():
    result = _compare(
        "Mochila infantil rosa escolar",
        "Mochila universitaria notebook preta para trabalho adulto",
        own_price=89.9,
        candidate_price=299.9,
    )
    assert result["verdict"] in {"rejected", "competitor_partial"}
    assert result["score"] < 0.55
    return True


def test_mochila_vs_lancheira_rejected_or_low_partial():
    result = _compare(
        "Mochila infantil rosa escolar",
        "Lancheira infantil rosa escolar",
    )
    assert result["verdict"] in {"rejected", "competitor_partial"}
    assert result["score"] < 0.45
    return True


def test_minimalista_branca_vs_casual_branca_direct_or_partial():
    result = _compare(
        "Mochila minimalista branca grande",
        "Mochila casual branca reforcada",
    )
    assert result["verdict"] in {"competitor_direct", "competitor_partial"}
    assert result["score"] >= 0.45
    return True


def test_sem_descricao_classifica_usando_titulo():
    product = _product("Mochila escolar infantil rosa", description=None)
    profile = build_product_profile(product)
    assert profile["product_type"] == "mochila"
    assert "infantil" in profile["audience"]
    assert "escolar" in profile["use_case"]
    return True


def test_preco_muito_distante_reduz_score():
    close = _compare(
        "Mochila infantil rosa escolar com rodinhas",
        "Mochila infantil rosa escolar com rodinhas",
        own_price=100,
        candidate_price=110,
    )
    distant = _compare(
        "Mochila infantil rosa escolar com rodinhas",
        "Mochila infantil rosa escolar com rodinhas",
        own_price=100,
        candidate_price=900,
    )
    assert distant["score"] < close["score"]
    assert any("Preco muito distante" in reason for reason in distant["reasons"])
    return True


def test_classify_candidate_salva_match():
    own = _product("Mochila infantil rosa escolar com rodinhas", source_type="own_product")
    candidate = _product("Mochila princesa rosa infantil escolar com rodinhas")

    result = classify_candidate(own["product_uid"], candidate["product_uid"])
    matches = get_matches_for_product(own["product_uid"])
    updated = get_product(candidate["product_uid"])

    assert result["match"]["candidate_product_uid"] == candidate["product_uid"]
    assert len(matches) == 1
    assert updated["source_type"] == result["verdict"]
    return True


def test_classify_candidates_for_product_classifica_lote():
    own = _product("Mochila infantil rosa escolar com rodinhas", source_type="own_product")
    _product("Mochila princesa rosa infantil escolar com rodinhas")
    _product("Mochila universitaria notebook preta para trabalho adulto", price=399.9)
    _product("Lancheira infantil rosa escolar")

    summary = classify_candidates_for_product(own["product_uid"], limit=10)

    assert summary["total"] >= 3
    assert summary["direct"] >= 1
    assert summary["rejected"] >= 1
    assert summary["average_score"] >= 0
    return True


def test_get_matches_for_product_filtra_por_verdict():
    own = _product("Mochila infantil rosa escolar com rodinhas", source_type="own_product")
    direct_candidate = _product("Mochila princesa rosa infantil escolar com rodinhas")
    rejected_candidate = _product("Lancheira infantil rosa escolar")

    classify_candidate(own["product_uid"], direct_candidate["product_uid"])
    classify_candidate(own["product_uid"], rejected_candidate["product_uid"])
    direct_matches = get_matches_for_product(own["product_uid"], verdict="competitor_direct")
    rejected_matches = get_matches_for_product(own["product_uid"], verdict="rejected")

    assert all(match["verdict"] == "competitor_direct" for match in direct_matches)
    assert all(match["verdict"] == "rejected" for match in rejected_matches)
    assert direct_matches
    assert rejected_matches
    return True


if __name__ == "__main__":
    print("\nTESTE R4 - Filtro de Relevancia\n")

    tests = [
        ("mochila infantil rosa vs princesa rosa", test_mochila_infantil_rosa_vs_princesa_direct),
        ("mochila infantil rosa vs escolar menina", test_mochila_infantil_rosa_vs_escolar_menina_direct_or_partial),
        ("mochila infantil vs universitaria notebook", test_mochila_infantil_vs_universitaria_notebook_rejected_or_low_partial),
        ("mochila infantil vs lancheira infantil", test_mochila_vs_lancheira_rejected_or_low_partial),
        ("minimalista branca vs casual branca", test_minimalista_branca_vs_casual_branca_direct_or_partial),
        ("sem descricao usa titulo", test_sem_descricao_classifica_usando_titulo),
        ("preco distante reduz score", test_preco_muito_distante_reduz_score),
        ("classify_candidate salva match", test_classify_candidate_salva_match),
        ("classify_candidates_for_product classifica lote", test_classify_candidates_for_product_classifica_lote),
        ("get_matches_for_product filtra verdict", test_get_matches_for_product_filtra_por_verdict),
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
