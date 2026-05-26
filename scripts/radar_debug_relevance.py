#!/usr/bin/env python3
"""
R7.2K: Debug script for radar relevance scoring.

Uso:
  python scripts/radar_debug_relevance.py OWN_PRODUCT_UID CANDIDATE_PRODUCT_UID

Imprime:
  - Dados completos de ambos os produtos
  - Sinais extraídos (tipo, público, uso, estilo, features, temas)
  - Score por componente (type, audience, use_case, style, features, price)
  - Penalidades (audience, use_case, niche_mismatch, price)
  - Niche floor application
  - Verdict final e reasons
"""

import sys
import json
from pathlib import Path

# R7.2K.1: Ensure UTF-8 output for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.append(str(Path(__file__).resolve().parent.parent))

from shopee_core.radar_relevance_service import (
    build_product_profile,
    compare_product_profiles,
    _apply_niche_floor,
    _niche_mismatch_penalty,
    _audience_penalty,
    _use_case_penalty,
    _score_price,
    _score_overlap,
    _verdict_for_score,
)
from shopee_core.radar_db import get_connection


def get_product_by_uid(uid: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM radar_products WHERE product_uid = ?", (uid,)
        ).fetchone()
    return dict(row) if row else None


def format_signals(signals: dict) -> str:
    return json.dumps(signals, indent=2, ensure_ascii=False)


def main():
    if len(sys.argv) < 3:
        print("Uso: python scripts/radar_debug_relevance.py OWN_PRODUCT_UID CANDIDATE_PRODUCT_UID")
        sys.exit(1)

    own_uid = sys.argv[1]
    cand_uid = sys.argv[2]

    own_product = get_product_by_uid(own_uid)
    cand_product = get_product_by_uid(cand_uid)

    if not own_product:
        print(f"ERRO: Produto próprio '{own_uid}' não encontrado.")
        sys.exit(1)
    if not cand_product:
        print(f"ERRO: Candidato '{cand_uid}' não encontrado.")
        sys.exit(1)

    print("=" * 72)
    print("DEBUG DE RELEVÂNCIA")
    print("=" * 72)

    print("\n── PRODUTO PRÓPRIO ──")
    print(f"  UID:            {own_product['product_uid']}")
    print(f"  Título:         {own_product['title']}")
    print(f"  Preço:          {own_product['price']}")
    print(f"  Marketplace:    {own_product['marketplace']}")
    print(f"  Status:         {own_product['status']}")
    if own_product.get("canonical_url"):
        print(f"  URL:            {own_product['canonical_url'][:120]}")

    print("\n── CANDIDATO ──")
    print(f"  UID:            {cand_product['product_uid']}")
    print(f"  Título:         {cand_product['title']}")
    print(f"  Preço:          {cand_product['price']}")
    print(f"  Marketplace:    {cand_product['marketplace']}")
    print(f"  Status:         {cand_product['status']}")
    if cand_product.get("canonical_url"):
        print(f"  URL:            {cand_product['canonical_url'][:120]}")

    print("\n── PERFIS EXTRAÍDOS ──")
    own_profile = build_product_profile(own_product)
    cand_profile = build_product_profile(cand_product)
    print(f"\nPerfil Próprio:\n{format_signals(own_profile)}")
    print(f"\nPerfil Candidato:\n{format_signals(cand_profile)}")

    print("\n── COMPARAÇÃO COMPONENTE POR COMPONENTE ──")

    # Type comparison
    own_type = own_profile.get("product_type")
    cand_type = cand_profile.get("product_type")
    print(f"\n1. TIPO:             próprio={own_type!r}  candidato={cand_type!r}")
    if own_type and cand_type and own_type == cand_type:
        print(f"   → +30 pontos (mesmo tipo)")
    elif own_type and cand_type:
        print(f"   → -40 pontos (tipo diferente)")
    else:
        print(f"   → 0 pontos (incompleto)")

    # Audience overlap
    audit_own = own_profile.get("audience") or []
    audit_cand = cand_profile.get("audience") or []
    score_a, reason_a = _score_overlap(audit_own, audit_cand, 25, "publico-alvo")
    penalty_a = _audience_penalty(audit_own, audit_cand)
    print(f"\n2. AUDIÊNCIA:        próprio={audit_own}  candidato={audit_cand}")
    print(f"   → Overlap: +{score_a} pontos {reason_a or ''}")
    if penalty_a:
        print(f"   → Penalidade: -{penalty_a}")

    # Features
    own_features = set(own_profile.get("features") or [])
    cand_features = set(cand_profile.get("features") or [])
    shared_features = own_features & cand_features
    feature_points = min(10.0, len(shared_features) * 3) if own_features and cand_features and shared_features else 0.0
    print(f"\n3. FEATURES:         próprio={list(own_features)}  candidato={list(cand_features)}")
    print(f"   → Compartilhadas: {list(shared_features)}")
    print(f"   → +{feature_points} pontos")

    # Use case
    uc_own = own_profile.get("use_case") or []
    uc_cand = cand_profile.get("use_case") or []
    score_u, reason_u = _score_overlap(uc_own, uc_cand, 20, "uso principal")
    penalty_u = _use_case_penalty(uc_own, uc_cand)
    print(f"\n4. USO:              próprio={uc_own}  candidato={uc_cand}")
    print(f"   → Overlap: +{score_u} pontos {reason_u or ''}")
    if penalty_u:
        print(f"   → Penalidade: -{penalty_u}")

    # Niche mismatch
    niche_penalty, niche_reason = _niche_mismatch_penalty(own_profile, cand_profile)
    print(f"\n5. NICHE MISMATCH:   {niche_reason or 'nenhuma'}")
    if niche_penalty:
        print(f"   → Penalidade: -{niche_penalty}")

    # Style
    style_own = own_profile.get("style") or []
    style_cand = cand_profile.get("style") or []
    score_s, reason_s = _score_overlap(style_own, style_cand, 15, "estilo/tema")
    print(f"\n6. ESTILO:           próprio={style_own}  candidato={style_cand}")
    print(f"   → Overlap: +{score_s} pontos {reason_s or ''}")

    # Price
    price_points, price_penalty, price_reason = _score_price(own_product.get("price"), cand_product.get("price"))
    print(f"\n7. PREÇO:            próprio={own_product.get('price')}  candidato={cand_product.get('price')}")
    if price_reason:
        print(f"   → {price_reason}")
    print(f"   → +{price_points} pontos, penalidade -{price_penalty}")

    # Raw score
    points = 0.0
    penalties = 0.0
    if own_type and cand_type and own_type == cand_type:
        points += 30
    elif own_type and cand_type:
        penalties += 40
    points += score_a
    penalties += penalty_a
    points += feature_points
    points += score_u
    penalties += penalty_u
    penalties += niche_penalty
    points += score_s
    points += price_points
    penalties += price_penalty

    raw_score = max(0.0, min(100.0, points - penalties))
    score = round(raw_score / 100.0, 4)

    print(f"\n── SCORE BRUTO ──")
    print(f"  Points:    {points}")
    print(f"  Penalties: {penalties}")
    print(f"  Raw score: {raw_score}")
    print(f"  Score:     {score}")

    # Niche floor
    reasons_debug = []
    score_after_floor = _apply_niche_floor(score, own_profile, cand_profile, reasons_debug)
    print(f"\n── NICHE FLOOR ──")
    if score_after_floor > score:
        print(f"  Floor aplicado! Score subiu de {score} → {score_after_floor}")
    else:
        print(f"  Floor não aplicado. Score mantido: {score_after_floor}")
    for r in reasons_debug:
        print(f"  Razão: {r}")

    # Final
    final_score = score_after_floor
    verdict = _verdict_for_score(final_score)
    print(f"\n── VEREDITO FINAL ──")
    print(f"  Score:      {final_score}")
    print(f"  Verdict:    {verdict}")
    print()

    # All reasons
    print("── REASONS COMPLETOS ──")
    all_reasons = []
    if own_type and cand_type and own_type == cand_type:
        all_reasons.append(f"Mesmo tipo de produto: {own_type}.")
    elif own_type and cand_type:
        all_reasons.append(f"Tipo diferente: {own_type} vs {cand_type}.")
    if reason_a:
        all_reasons.append(reason_a)
    if penalty_a:
        all_reasons.append("Publico-alvo parece diferente.")
    if shared_features:
        all_reasons.append(f"Features compartilhadas: {', '.join(shared_features)}.")
    if reason_u:
        all_reasons.append(reason_u)
    if penalty_u:
        all_reasons.append("Uso principal parece diferente.")
    if niche_reason:
        all_reasons.append(niche_reason)
    if reason_s:
        all_reasons.append(reason_s)
    if price_reason:
        all_reasons.append(price_reason)
    all_reasons.extend(reasons_debug)
    for r in all_reasons:
        print(f"  • {r}")

    if not all_reasons:
        print("  (nenhum)")

    print()
    print("=" * 72)
    print("FIM DO DEBUG")
    print("=" * 72)


if __name__ == "__main__":
    main()
