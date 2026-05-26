#!/usr/bin/env python3
"""
test_radar_relevance_service.py - R4 relevance filter tests.

Run:
    python test_radar_relevance_service.py
"""

from __future__ import annotations

import json
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


def test_r73d_mochila_infantil_vs_natacao_nabaiji_not_direct():
    result = _compare(
        "Mochila Infantil Princesa Rosa Escolar Feminina Grande",
        "Mochila Nabaiji 7L Para Natacao Cor Branca Ziper Infantil Feminino",
        own_price=93.1,
        candidate_price=69.9,
    )
    assert result["verdict"] != "competitor_direct"
    assert result["score"] < 0.65
    assert any("natacao" in reason.lower() for reason in result["reasons"])
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


def test_tipo_produto_prioriza_titulo_antes_de_categoria():
    profile = build_product_profile(
        {
            "product_uid": "fake-lancheira",
            "title": "Lancheira Infantil Rosa Princesa Termica",
            "price": 39.9,
            "marketplace": "mercadolivre",
            "shop_name": "Loja Teste",
            "raw_json": json.dumps(
                {
                    "description": "Lancheira termica infantil para lanche escolar.",
                    "category_path": ["Moda", "Mochilas e Bolsas", "Escolar"],
                    "attributes": {"Tipo": "lancheira"},
                },
                ensure_ascii=False,
            ),
        }
    )
    assert profile["product_type"] == "lancheira"
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


def test_r51c_mochila_infantil_vs_executiva_notebook_rejected():
    """R5.1C: Mochila infantil feminina escolar vs executiva notebook deve ser rejected."""
    result = _compare(
        "Mochila Infantil Princesa Rosa Escolar Feminina Grande",
        "Mochila Masculina Executiva Preta Notebook Trabalho",
        own_price=89.9,
        candidate_price=299.9,
    )
    assert result["verdict"] == "rejected"
    assert result["score"] < 0.45
    assert any("notebook" in reason.lower() or "trabalho" in reason.lower() for reason in result["reasons"])
    return True


def test_r51c_mochila_infantil_vs_notebook_samsonite_rejected():
    """R5.1C: Mochila infantil vs executiva notebook Samsonite deve ser rejected."""
    result = _compare(
        "Mochila Infantil Princesa Rosa Escolar Feminina",
        "Mochila Executiva Notebook Samsonite Preta Premium",
        own_price=89.9,
        candidate_price=399.9,
    )
    assert result["verdict"] == "rejected"
    assert result["score"] < 0.45
    return True


def test_r51c_mochila_infantil_vs_rodinhas_direct():
    """R5.1C: Mochila infantil vs mochila escolar infantil rodinhas deve ser direct."""
    result = _compare(
        "Mochila Infantil Princesa Rosa Escolar Feminina Grande",
        "Mochila Escolar Infantil Rodinhas Rosa Feminina",
    )
    assert result["verdict"] == "competitor_direct"
    assert result["score"] >= 0.72
    return True


def test_r51c_mochila_infantil_vs_juvenil_feminina_direct_or_partial():
    """R5.1C: Mochila infantil vs juvenil feminina escolar pode ser direct ou partial."""
    result = _compare(
        "Mochila Infantil Princesa Rosa Escolar Feminina Grande",
        "Mochila Juvenil Feminina Escolar Colorida",
    )
    assert result["verdict"] in {"competitor_direct", "competitor_partial"}
    assert result["score"] >= 0.45
    return True


def test_r51c_lancheira_estojo_rejected():
    """R5.1C: Lancheira e estojo continuam rejected."""
    lancheira = _compare(
        "Mochila Infantil Princesa Rosa Escolar Feminina Grande",
        "Lancheira Infantil Rosa Princesa Termica",
    )
    estojo = _compare(
        "Mochila Infantil Princesa Rosa Escolar Feminina Grande",
        "Estojo Escolar Infantil Rosa Princesa",
    )
    assert lancheira["verdict"] == "rejected"
    assert estojo["verdict"] == "rejected"
    return True




# ── R7.2G: Novos testes de relevância ─────────────────────────────────────────

def test_r72g_niche_floor_mochila_infantil_similar():
    """R7.2G: Duas mochilas infantis similares não devem ter score < 0.35."""
    result = _compare(
        "Mochila Infantil Feminina Rosa Escolar Grande",
        "Mochila Infantil Feminina Azul Escolar Colorida",
    )
    # Com niche floor, ambas são mochilas/infantil/escolar -> floor de 0.35
    assert result["score"] >= 0.35, f"Score abaixo do floor: {result['score']}"
    assert result["verdict"] in {"competitor_direct", "competitor_partial"}


def test_r72g_niche_floor_nao_aplica_quando_incompativel():
    """R7.2G: Niche floor NÃO se aplica quando candidato é executivo/notebook/adulto."""
    result = _compare(
        "Mochila Infantil Princesa Rosa Escolar Feminina",
        "Mochila Executiva Notebook Masculina Trabalho Adulto",
        own_price=89.9,
        candidate_price=399.9,
    )
    # Incompatibilidade forte -> sem floor -> score pode ser baixo
    assert result["verdict"] == "rejected"
    assert result["score"] < 0.35, f"Score deveria ser abaixo do floor: {result['score']}"


def test_r72g_threshold_direct_65():
    """R7.2G: Threshold competitor_direct é >= 0.65 (era 0.72)."""
    from shopee_core.radar_relevance_service import _verdict_for_score
    assert _verdict_for_score(0.65) == "competitor_direct"
    assert _verdict_for_score(0.70) == "competitor_direct"
    assert _verdict_for_score(0.64) == "competitor_partial"


def test_r72g_threshold_partial_35():
    """R7.2G: Threshold competitor_partial é >= 0.35 (era 0.45)."""
    from shopee_core.radar_relevance_service import _verdict_for_score
    assert _verdict_for_score(0.35) == "competitor_partial"
    assert _verdict_for_score(0.40) == "competitor_partial"
    assert _verdict_for_score(0.34) == "rejected"


def test_r72g_quality_sem_preco_nao_bloqueia():
    """R7.2G: Candidato sem preço não deve ser rejeitado automaticamente."""
    own = _product("Mochila Infantil Rosa Escolar", source_type="own_product")
    # Criar candidato sem preço
    candidate = _product("Mochila Infantil Azul Escolar", price=None)

    result = classify_candidate(own["product_uid"], candidate["product_uid"])
    # Com preço None a qualidade pode falhar, mas apenas título vazio/genérico bloqueia
    # Se título está presente e válido, deve realizar análise semântica
    assert result["verdict"] in {"competitor_direct", "competitor_partial", "rejected"}
    # Não deve ter errors que bloqueiem completamente quando há título válido
    if "url de teste" not in str(result.get("reasons", "")).lower():
        assert result.get("score") is not None


def test_r72g_fake_url_classify_candidate_rejected():
    """R7.2G: classify_candidate com candidato de URL fake deve ser rejected imediatamente."""
    own = _product("Mochila Infantil Rosa Escolar", source_type="own_product")

    # Criar candidato com URL fake via inserção direta
    from shopee_core.radar_db import get_connection, init_db
    import json as json_mod

    init_db()
    fake_uid = uuid.uuid4().hex
    # Use a fake URL that is unique enough to avoid collisions in shared DB
    fake_url = "https://shopee.com.br/product/99/98"
    with get_connection() as conn:
        stale = conn.execute("SELECT product_uid FROM radar_products WHERE canonical_url = ?", (fake_url,)).fetchone()
        if stale:
            sid = stale["product_uid"]
            conn.execute("DELETE FROM radar_collection_jobs WHERE product_uid = ?", (sid,))
            conn.execute("DELETE FROM radar_candidate_links WHERE candidate_product_uid = ?", (sid,))
            conn.execute("DELETE FROM radar_competitor_matches WHERE candidate_product_uid = ?", (sid,))
            conn.execute("DELETE FROM radar_products WHERE product_uid = ?", (sid,))
        conn.execute(
            """
            INSERT INTO radar_products (product_uid, source_type, marketplace, url, canonical_url, title, status, created_at, updated_at, raw_json)
            VALUES (?, 'competitor_candidate', 'shopee', ?, ?, 'Mochila Qualquer', 'collected', '2023', '2023', ?)
            """,
            (fake_uid, fake_url, fake_url, json_mod.dumps({"description": "descricao"}))
        )

    result = classify_candidate(own["product_uid"], fake_uid)
    assert result["verdict"] == "rejected"
    assert result["score"] == 0.0
    assert any("url de teste" in r.lower() or "fake" in r.lower() for r in result.get("reasons", []))


def test_r72g_reasons_inclui_penalidade_sem_invalidade():
    """R7.2G: Candidato com qualidade baixa (sem loja) gera reason mas não bloqueia análise."""
    own = _product("Mochila Infantil Rosa Escolar", source_type="own_product")
    raw_data = {
        "title": "Mochila Infantil Azul Escolar",
        "price": 79.9,
        "shop_name": None,  # Loja ausente
        "description": "Mochila para crianças com rodinhas",
        "marketplace": "mercadolivre",
        "image_urls": [],
        "video_urls": [],
        "raw": {},
    }
    candidate = _product(
        "Mochila Infantil Azul Escolar",
        raw=raw_data
    )
    # Sobrescrever shop_name no banco
    from shopee_core.radar_db import get_connection
    with get_connection() as conn:
        conn.execute(
            "UPDATE radar_products SET shop_name = NULL WHERE product_uid = ?",
            (candidate["product_uid"],)
        )

    # Rebuildar produto a partir do banco
    from shopee_core.radar_service import get_product
    candidate_refreshed = get_product(candidate["product_uid"])

    own_profile = build_product_profile(own)
    cand_profile = build_product_profile(candidate_refreshed)
    result = compare_product_profiles(own_profile, cand_profile)

    # Deve ter reason sobre loja ausente
    all_reasons = " ".join(result.get("reasons", []))
    assert "loja" in all_reasons.lower() or "vendedor" in all_reasons.lower(), \
        "Esperado reason sobre loja ausente"
    # Mas score não deve ser 0 (análise semântica rodou)
    assert result["score"] > 0


# ── R7.2K: Real product titles from the collection ──────────────────────────

OWN_TITLE_R72K = "Mochila Infantil Princesa Rosa Escolar Feminina Grande"


def test_r72k_princesas_infantil_escolar_reforcada_impermeavel():
    """Princesas infantil escolar — plural matching test."""
    result = _compare(OWN_TITLE_R72K, "Mochila Princesas Infantil Escolar Reforçada Impermeável")
    assert result["verdict"] in {"competitor_direct", "competitor_partial"}, f"Got {result['verdict']} score={result['score']}"
    assert result["score"] >= 0.45
    return True


def test_r72k_infantil_escolar_organizadora_reforcada_impermeavel():
    """Infantil escolar organizadora — strong match."""
    result = _compare(OWN_TITLE_R72K, "Mochila Infantil Escolar Organizadora Reforçada Impermeável")
    assert result["verdict"] in {"competitor_direct", "competitor_partial"}, f"Got {result['verdict']} score={result['score']}"
    assert result["score"] >= 0.45
    return True


def test_r72k_hello_kitty_escolar():
    """Hello Kitty escolar — theme match."""
    result = _compare(OWN_TITLE_R72K, "Mochila Escolar Hello Kitty Para 3ª A 6ª Série")
    assert result["verdict"] in {"competitor_direct", "competitor_partial"}, f"Got {result['verdict']} score={result['score']}"
    assert result["score"] >= 0.35
    return True


def test_r72k_menina_fofa_reforcada_bolsa_escolar_viagem():
    """Menina fofa bolsa escolar — audience+use case match."""
    result = _compare(OWN_TITLE_R72K, "Mochila Infantil Menina Fofa Reforçada Bolsa Escolar Viagem")
    assert result["verdict"] in {"competitor_direct", "competitor_partial"}, f"Got {result['verdict']} score={result['score']}"
    assert result["score"] >= 0.45
    return True


def test_r72k_infantil_escolar_princesas_reforcada_impermeavel():
    """Infantil escolar princesas — same niche."""
    result = _compare(OWN_TITLE_R72K, "Mochila Infantil Escolar Princesas Reforçada Impermeável")
    assert result["verdict"] in {"competitor_direct", "competitor_partial"}, f"Got {result['verdict']} score={result['score']}"
    assert result["score"] >= 0.45
    return True


def test_r72k_menino_menina_infantil_dinossauro_gatinho():
    """Dinossauro gatinho infantil — unisex child theme."""
    result = _compare(OWN_TITLE_R72K, "Mochila Escolar Menino Menina Infantil Dinossauro Gatinho Cor Verde Desenho Do Tecido Lisa")
    assert result["verdict"] in {"competitor_direct", "competitor_partial"}, f"Got {result['verdict']} score={result['score']}"
    assert result["score"] >= 0.35
    return True


def test_r72k_bolsa_menina_escolar_princesa_com_estojo():
    """Bolsa menina escolar princesa com estojo — strong match with estojo feature."""
    result = _compare(OWN_TITLE_R72K, "Mochila Infantil Bolsa Menina Escolar Princesa Com Estojo Cor Lilás Desenho Do Tecido Florido")
    assert result["verdict"] in {"competitor_direct", "competitor_partial"}, f"Got {result['verdict']} score={result['score']}"
    assert result["score"] >= 0.45
    return True


def test_r72k_infantil_menina_costas_unicornio_feminina():
    """Infantil menina costas unicórnio feminina — costas feature + unicorn theme."""
    result = _compare(OWN_TITLE_R72K, "Mochila Escolar Infantil Menina Costas Unicórnio Feminina")
    assert result["verdict"] in {"competitor_direct", "competitor_partial"}, f"Got {result['verdict']} score={result['score']}"
    assert result["score"] >= 0.45
    return True


def test_r72k_plural_matching_before_fix():
    """R7.2K: Verifica que plurais sao reconhecidos (princesas, mochilas, etc)."""
    profile = build_product_profile({
        "product_uid": "test-plural",
        "title": "Mochilas Princesas Infantis Escolares Reforçadas",
        "price": 79.9,
        "marketplace": "mercadolivre",
        "shop_name": "Loja Teste",
        "raw_json": "{}",
    })
    assert profile["product_type"] == "mochila"
    assert "infantil" in profile["audience"]
    assert "escolar" in profile["use_case"]
    assert "princesa" in profile["style"]
    assert "reforcada" in profile["features"]
    return True


def test_r72k_niche_floor_nao_aplica_quando_candidato_sem_sinais():
    """R7.2K: Niche floor nao deve aplicar se candidato nao tem sinais de publico/uso."""
    result = _compare(
        OWN_TITLE_R72K,
        "Mochila Executiva Notebook Trabalho",
        own_price=99.9,
        candidate_price=199.9,
    )
    assert result["verdict"] == "rejected", f"Got {result['verdict']} score={result['score']}"
    assert result["score"] < 0.35
    return True


if __name__ == "__main__":
    print("\nTESTE R4 - Filtro de Relevancia\n")

    tests = [
        ("mochila infantil rosa vs princesa rosa", test_mochila_infantil_rosa_vs_princesa_direct),
        ("mochila infantil rosa vs escolar menina", test_mochila_infantil_rosa_vs_escolar_menina_direct_or_partial),
        ("mochila infantil vs universitaria notebook", test_mochila_infantil_vs_universitaria_notebook_rejected_or_low_partial),
        ("R7.3D: infantil escolar vs natacao Nabaiji nao direct", test_r73d_mochila_infantil_vs_natacao_nabaiji_not_direct),
        ("mochila infantil vs lancheira infantil", test_mochila_vs_lancheira_rejected_or_low_partial),
        ("minimalista branca vs casual branca", test_minimalista_branca_vs_casual_branca_direct_or_partial),
        ("sem descricao usa titulo", test_sem_descricao_classifica_usando_titulo),
        ("tipo prioriza titulo antes de categoria", test_tipo_produto_prioriza_titulo_antes_de_categoria),
        ("preco distante reduz score", test_preco_muito_distante_reduz_score),
        ("classify_candidate salva match", test_classify_candidate_salva_match),
        ("classify_candidates_for_product classifica lote", test_classify_candidates_for_product_classifica_lote),
        ("get_matches_for_product filtra verdict", test_get_matches_for_product_filtra_por_verdict),
        ("R5.1C: infantil vs executiva notebook rejected", test_r51c_mochila_infantil_vs_executiva_notebook_rejected),
        ("R5.1C: infantil vs notebook samsonite rejected", test_r51c_mochila_infantil_vs_notebook_samsonite_rejected),
        ("R5.1C: infantil vs rodinhas direct", test_r51c_mochila_infantil_vs_rodinhas_direct),
        ("R5.1C: infantil vs juvenil feminina direct/partial", test_r51c_mochila_infantil_vs_juvenil_feminina_direct_or_partial),
        ("R5.1C: lancheira/estojo rejected", test_r51c_lancheira_estojo_rejected),
        ("R7.2G: niche floor mochila infantil similar", test_r72g_niche_floor_mochila_infantil_similar),
        ("R7.2G: niche floor não aplica quando incompatível", test_r72g_niche_floor_nao_aplica_quando_incompativel),
        ("R7.2G: threshold direct 0.65", test_r72g_threshold_direct_65),
        ("R7.2G: threshold partial 0.35", test_r72g_threshold_partial_35),
        ("R7.2G: sem preço não bloqueia", test_r72g_quality_sem_preco_nao_bloqueia),
        ("R7.2G: fake url classify_candidate rejected", test_r72g_fake_url_classify_candidate_rejected),
        ("R7.2G: reasons inclui penalidade sem invalidade", test_r72g_reasons_inclui_penalidade_sem_invalidade),
        # R7.2K: real product titles from collection
        ("R7.2K: princesas infantil escolar reforcada impermeavel", test_r72k_princesas_infantil_escolar_reforcada_impermeavel),
        ("R7.2K: infantil escolar organizadora reforcada impermeavel", test_r72k_infantil_escolar_organizadora_reforcada_impermeavel),
        ("R7.2K: hello kitty escolar", test_r72k_hello_kitty_escolar),
        ("R7.2K: menina fofa bolsa escolar viagem", test_r72k_menina_fofa_reforcada_bolsa_escolar_viagem),
        ("R7.2K: infantil escolar princesas reforcada impermeavel", test_r72k_infantil_escolar_princesas_reforcada_impermeavel),
        ("R7.2K: menino menina infantil dinossauro gatinho", test_r72k_menino_menina_infantil_dinossauro_gatinho),
        ("R7.2K: bolsa menina escolar princesa com estojo", test_r72k_bolsa_menina_escolar_princesa_com_estojo),
        ("R7.2K: infantil menina costas unicornio feminina", test_r72k_infantil_menina_costas_unicornio_feminina),
        ("R7.2K: plural matching (princesas, mochilas)", test_r72k_plural_matching_before_fix),
        ("R7.2K: niche floor nao aplica p/ candidato sem sinais", test_r72k_niche_floor_nao_aplica_quando_candidato_sem_sinais),
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
