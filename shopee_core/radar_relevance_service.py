"""
shopee_core/radar_relevance_service.py - Rule-based Radar relevance filter.

R4 compares an own product against collected competitor candidates and records
explainable matches. It intentionally does not call AI models or integrate with
the current audit/sentinel/bot flows.
"""

from __future__ import annotations

import json
import re
import unicodedata
import uuid
from datetime import datetime
from typing import Any

from .radar_db import get_connection, init_db
from .radar_collector import validate_product_extraction
from .radar_service import classify_product, get_product, list_product_assets, list_products


MATCH_VERDICTS = {"competitor_direct", "competitor_partial", "rejected"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}

_STOPWORDS = {
    "a",
    "as",
    "com",
    "da",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "na",
    "no",
    "o",
    "os",
    "para",
    "por",
    "sem",
    "uma",
    "um",
}

_PRODUCT_TYPE_RULES = {
    "mochila": ["mochila", "mochilas", "backpack"],
    "bolsa": ["bolsa", "bolsas"],
    "lancheira": ["lancheira", "lancheiras", "merendeira"],
    "estojo": ["estojo", "estojos"],
    "mala": ["mala", "malas"],
}

_AUDIENCE_RULES = {
    "infantil": ["infantil", "crianca", "criancas", "kids", "menina", "menino"],
    "juvenil": ["juvenil", "adolescente", "teen"],
    "adulto": ["adulto", "adulta", "universitario", "universitaria", "executivo", "executiva"],
    "feminino": ["feminino", "feminina", "menina", "mulher", "princesa", "rosa"],
    "masculino": ["masculino", "masculina", "menino", "homem"],
    "unissex": ["unissex"],
    "bebe": ["bebe", "baby"],
}

_USE_CASE_RULES = {
    "escolar": ["escolar", "escola", "aula", "material escolar"],
    "faculdade": ["faculdade", "universidade", "universitario", "universitaria"],
    "notebook": ["notebook", "laptop"],
    "viagem": ["viagem", "viajar", "bordo"],
    "passeio": ["passeio", "dia a dia"],
    "trabalho": ["trabalho", "executivo", "executiva", "office"],
}

_STYLE_RULES = {
    "rosa": ["rosa", "pink"],
    "azul": ["azul"],
    "branca": ["branca", "branco"],
    "preta": ["preta", "preto"],
    "princesa": ["princesa", "princess"],
    "unicornio": ["unicornio", "unicorn"],
    "personagem": ["personagem", "personagens"],
    "minimalista": ["minimalista", "clean"],
    "premium": ["premium", "luxo"],
    "casual": ["casual"],
    "colorida": ["colorida", "colorido", "estampada", "estampado"],
}

_FEATURE_RULES = {
    "rodinhas": ["rodinha", "rodinhas", "rodas", "360"],
    "alca": ["alca", "alcas"],
    "reforcada": ["reforcada", "reforcado"],
    "impermeavel": ["impermeavel", "resistente a agua"],
    "grande": ["grande"],
    "pequena": ["pequena", "pequeno"],
    "notebook": ["notebook", "laptop"],
    "costura": ["costura", "costuras"],
    "ziper": ["ziper", "ziperes"],
}


def build_product_profile(product: dict) -> dict:
    """Build a simple semantic profile from a radar product row."""
    if not product:
        raise ValueError("product precisa ser informado")

    raw = _load_raw_json(product.get("raw_json"))
    raw_inner = raw.get("raw") if isinstance(raw.get("raw"), dict) else {}
    description = (
        raw.get("description")
        or raw_inner.get("description")
        or product.get("description")
        or ""
    )
    attributes = _coerce_dict(raw.get("attributes") or raw_inner.get("attributes"))
    category_path = _coerce_list(raw.get("category_path") or raw_inner.get("category_path"))

    text_parts = [
        product.get("title"),
        description,
        " ".join(category_path),
        " ".join(f"{key} {value}" for key, value in attributes.items()),
        product.get("shop_name"),
    ]
    text = _clean_text(" ".join(str(part or "") for part in text_parts))
    signals = extract_product_signals(text, raw)
    tokens = _tokenize(text)

    return {
        "product_uid": product.get("product_uid"),
        "title": product.get("title") or raw.get("title"),
        "text": text,
        "tokens": tokens,
        "product_type": signals["product_type"],
        "audience": signals["audience"],
        "use_case": signals["use_case"],
        "style": signals["style"],
        "features": signals["features"],
        "price": _coerce_float(product.get("price") or raw.get("price")),
        "marketplace": product.get("marketplace"),
        "shop_name": product.get("shop_name"),
        "category_path": category_path,
        "attributes": attributes,
        "signals": signals,
    }


def extract_product_signals(text: str, raw_json: dict | None = None) -> dict:
    """Extract rule-based product signals from Portuguese product text."""
    raw_json = raw_json or {}
    extra_text = ""
    if raw_json:
        extra_text = " ".join(
            [
                str(raw_json.get("description") or ""),
                " ".join(_coerce_list(raw_json.get("category_path"))),
                " ".join(
                    f"{key} {value}"
                    for key, value in _coerce_dict(raw_json.get("attributes")).items()
                ),
            ]
        )

    normalized = _normalize_text(f"{text or ''} {extra_text}")
    product_type = _best_matching_label_by_position(normalized, _PRODUCT_TYPE_RULES)

    return {
        "product_type": product_type,
        "audience": _matching_labels(normalized, _AUDIENCE_RULES),
        "use_case": _matching_labels(normalized, _USE_CASE_RULES),
        "style": _matching_labels(normalized, _STYLE_RULES),
        "features": _matching_labels(normalized, _FEATURE_RULES),
    }


def compare_product_profiles(own_profile: dict, candidate_profile: dict) -> dict:
    """Compare two product profiles and return score, verdict and reasons."""
    points = 0.0
    penalties = 0.0
    reasons: list[str] = []

    own_type = own_profile.get("product_type")
    candidate_type = candidate_profile.get("product_type")
    if own_type and candidate_type and own_type == candidate_type:
        points += 30
        reasons.append(f"Mesmo tipo de produto: {own_type}.")
    elif own_type and candidate_type:
        penalties += 40
        reasons.append(f"Tipo diferente: {own_type} vs {candidate_type}.")
    else:
        reasons.append("Tipo de produto incompleto em um dos lados.")

    audience_points, audience_reason = _score_overlap(
        own_profile.get("audience") or [],
        candidate_profile.get("audience") or [],
        25,
        "publico-alvo",
    )
    points += audience_points
    if audience_reason:
        reasons.append(audience_reason)
    audience_penalty = _audience_penalty(
        own_profile.get("audience") or [],
        candidate_profile.get("audience") or [],
    )
    penalties += audience_penalty
    if audience_penalty:
        reasons.append("Publico-alvo parece diferente.")

    use_points, use_reason = _score_overlap(
        own_profile.get("use_case") or [],
        candidate_profile.get("use_case") or [],
        20,
        "uso principal",
    )
    points += use_points
    if use_reason:
        reasons.append(use_reason)
    use_penalty = _use_case_penalty(
        own_profile.get("use_case") or [],
        candidate_profile.get("use_case") or [],
    )
    penalties += use_penalty
    if use_penalty:
        reasons.append("Uso principal parece diferente.")

    style_points, style_reason = _score_overlap(
        own_profile.get("style") or [],
        candidate_profile.get("style") or [],
        15,
        "estilo/tema",
    )
    points += style_points
    if style_reason:
        reasons.append(style_reason)

    price_points, price_penalty, price_reason = _score_price(
        own_profile.get("price"),
        candidate_profile.get("price"),
    )
    points += price_points
    penalties += price_penalty
    if price_reason:
        reasons.append(price_reason)

    raw_score = max(0.0, min(100.0, points - penalties))
    score = round(raw_score / 100.0, 4)
    verdict = _verdict_for_score(score)
    confidence = _confidence_for(score, verdict, points, penalties, own_profile, candidate_profile)

    return {
        "score": score,
        "verdict": verdict,
        "confidence": confidence,
        "reasons": reasons,
        "signals": {
            "own": _public_profile_signals(own_profile),
            "candidate": _public_profile_signals(candidate_profile),
            "points": round(points, 2),
            "penalties": round(penalties, 2),
        },
    }


def classify_candidate(own_product_uid: str, candidate_product_uid: str) -> dict:
    """Classify one candidate against one own product and persist the match."""
    own_product = get_product(own_product_uid)
    if not own_product:
        raise ValueError(f"Produto proprio nao encontrado: {own_product_uid}")

    candidate_product = get_product(candidate_product_uid)
    if not candidate_product:
        raise ValueError(f"Candidato nao encontrado: {candidate_product_uid}")

    quality = _product_quality(candidate_product)
    if not quality.get("ok"):
        comparison = _low_quality_comparison(candidate_product, quality)
        match = _upsert_match(
            own_product_uid=own_product_uid,
            candidate_product_uid=candidate_product_uid,
            comparison=comparison,
        )
        updated_candidate = classify_product(
            candidate_product_uid,
            "rejected",
            comparison["score"],
            rejection_reason="; ".join(comparison["reasons"][:4]),
        )
        return {
            "match": match,
            "own_product": own_product,
            "candidate_product": updated_candidate,
            "own_profile": build_product_profile(own_product),
            "candidate_profile": build_product_profile(candidate_product),
            **comparison,
        }

    own_profile = build_product_profile(own_product)
    candidate_profile = build_product_profile(candidate_product)
    comparison = compare_product_profiles(own_profile, candidate_profile)
    match = _upsert_match(
        own_product_uid=own_product_uid,
        candidate_product_uid=candidate_product_uid,
        comparison=comparison,
    )

    rejection_reason = None
    if comparison["verdict"] == "rejected":
        rejection_reason = "; ".join(comparison["reasons"][:4])
    updated_candidate = classify_product(
        candidate_product_uid,
        comparison["verdict"],
        comparison["score"],
        rejection_reason=rejection_reason,
    )

    return {
        "match": match,
        "own_product": own_product,
        "candidate_product": updated_candidate,
        "own_profile": own_profile,
        "candidate_profile": candidate_profile,
        **comparison,
    }


def classify_candidates_for_product(own_product_uid: str, limit: int = 100) -> dict:
    """Classify current competitor_candidate products against one own product."""
    candidates = [
        product
        for product in list_products(source_type="competitor_candidate", limit=limit)
        if product.get("product_uid") != own_product_uid
    ]
    results = [classify_candidate(own_product_uid, item["product_uid"]) for item in candidates]

    total = len(results)
    direct = sum(1 for item in results if item["verdict"] == "competitor_direct")
    partial = sum(1 for item in results if item["verdict"] == "competitor_partial")
    rejected = sum(1 for item in results if item["verdict"] == "rejected")
    average_score = (
        round(sum(item["score"] for item in results) / total, 4)
        if total
        else 0.0
    )

    return {
        "own_product_uid": own_product_uid,
        "total": total,
        "direct": direct,
        "partial": partial,
        "rejected": rejected,
        "average_score": average_score,
        "results": results,
    }


def get_matches_for_product(
    own_product_uid: str,
    verdict: str | None = None,
) -> list[dict]:
    """Return persisted matches with basic candidate product data."""
    if verdict is not None and verdict not in MATCH_VERDICTS:
        allowed = ", ".join(sorted(MATCH_VERDICTS))
        raise ValueError(f"verdict invalido: {verdict!r}. Use: {allowed}")

    init_db()
    filters = ["m.own_product_uid = ?"]
    params: list[Any] = [own_product_uid]
    if verdict:
        filters.append("m.verdict = ?")
        params.append(verdict)

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                m.*,
                p.title,
                p.price,
                p.marketplace,
                p.shop_name,
                p.canonical_url
            FROM radar_competitor_matches m
            JOIN radar_products p
              ON p.product_uid = m.candidate_product_uid
            WHERE {' AND '.join(filters)}
            ORDER BY m.relevance_score DESC, m.updated_at DESC
            """,
            params,
        ).fetchall()

    matches = []
    for row in rows:
        item = dict(row)
        item["reasons"] = _load_json_list(item.get("reasons_json"))
        item["signals"] = _load_json_dict(item.get("signals_json"))
        matches.append(item)
    return matches


def _product_quality(product: dict) -> dict:
    raw = _load_raw_json(product.get("raw_json"))
    data = dict(raw)
    data.setdefault("url", product.get("url"))
    data.setdefault("canonical_url", product.get("canonical_url"))
    data.setdefault("marketplace", product.get("marketplace"))
    data.setdefault("title", product.get("title"))
    data.setdefault("price", product.get("price"))
    data.setdefault("shop_name", product.get("shop_name"))
    data.setdefault("image_urls", _coerce_list(raw.get("image_urls")))
    data.setdefault("description_image_urls", _coerce_list(raw.get("description_image_urls")))
    quality = validate_product_extraction(data, product.get("marketplace") or "")
    asset_count = len(list_product_assets(product["product_uid"]))
    if asset_count > 80:
        quality = dict(quality)
        quality["errors"] = list(quality.get("errors") or [])
        quality["errors"].append(f"Assets demais registrados para um produto: {asset_count}.")
        quality["ok"] = False
        quality["quality_score"] = min(float(quality.get("quality_score") or 0), 0.5)
    return quality


def _low_quality_comparison(candidate_product: dict, quality: dict) -> dict:
    errors = quality.get("errors") or ["extracao de baixa qualidade"]
    warnings = quality.get("warnings") or []
    reasons = ["Extracao de baixa qualidade: " + "; ".join(str(item) for item in errors[:4])]
    if warnings:
        reasons.append("Avisos de qualidade: " + "; ".join(str(item) for item in warnings[:3]))

    return {
        "score": 0.0,
        "verdict": "rejected",
        "confidence": "high",
        "reasons": reasons,
        "signals": {
            "quality": quality,
            "candidate": {
                "title": candidate_product.get("title"),
                "price": candidate_product.get("price"),
            },
            "points": 0.0,
            "penalties": 100.0,
        },
    }


def _upsert_match(
    own_product_uid: str,
    candidate_product_uid: str,
    comparison: dict,
) -> dict:
    init_db()
    now = _now()
    reasons_json = json.dumps(comparison["reasons"], ensure_ascii=False, sort_keys=True)
    signals_json = json.dumps(comparison["signals"], ensure_ascii=False, sort_keys=True)

    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT match_uid, created_at FROM radar_competitor_matches
            WHERE own_product_uid = ? AND candidate_product_uid = ?
            """,
            (own_product_uid, candidate_product_uid),
        ).fetchone()

        if existing:
            match_uid = existing["match_uid"]
            created_at = existing["created_at"]
        else:
            match_uid = str(uuid.uuid4())
            created_at = now

        conn.execute(
            """
            INSERT INTO radar_competitor_matches (
                match_uid, own_product_uid, candidate_product_uid, verdict,
                relevance_score, confidence, reasons_json, signals_json,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                match_uid,
                own_product_uid,
                candidate_product_uid,
                comparison["verdict"],
                float(comparison["score"]),
                comparison["confidence"],
                reasons_json,
                signals_json,
                created_at,
                now,
            ),
        )

        row = conn.execute(
            "SELECT * FROM radar_competitor_matches WHERE match_uid = ?",
            (match_uid,),
        ).fetchone()
        match = dict(row)

    match["reasons"] = comparison["reasons"]
    match["signals"] = comparison["signals"]
    return match


def _score_overlap(
    own_values: list[str],
    candidate_values: list[str],
    max_points: float,
    label: str,
) -> tuple[float, str | None]:
    own_set = set(own_values)
    candidate_set = set(candidate_values)
    if not own_set or not candidate_set:
        return 0.0, None

    shared = sorted(own_set & candidate_set)
    if not shared:
        return 0.0, None

    divisor = max(1, min(len(own_set), len(candidate_set)))
    points = max_points * min(1.0, len(shared) / divisor)
    return points, f"Mesmo {label}: {', '.join(shared)}."


def _audience_penalty(own_values: list[str], candidate_values: list[str]) -> float:
    own_set = set(own_values)
    candidate_set = set(candidate_values)
    if not own_set or not candidate_set:
        return 0.0

    child = {"infantil", "bebe"}
    adult = {"adulto"}
    if (own_set & child and candidate_set & adult) or (candidate_set & child and own_set & adult):
        return 25.0
    if ("infantil" in own_set and "juvenil" in candidate_set and "infantil" not in candidate_set) or (
        "infantil" in candidate_set and "juvenil" in own_set and "infantil" not in own_set
    ):
        return 12.0
    if own_set & candidate_set:
        return 0.0
    if ("feminino" in own_set and "masculino" in candidate_set) or (
        "masculino" in own_set and "feminino" in candidate_set
    ):
        return 12.0
    return 0.0


def _use_case_penalty(own_values: list[str], candidate_values: list[str]) -> float:
    own_set = set(own_values)
    candidate_set = set(candidate_values)
    if not own_set or not candidate_set or own_set & candidate_set:
        return 0.0

    work_or_university = {"trabalho", "faculdade"}
    if ("escolar" in own_set and candidate_set & work_or_university) or (
        "escolar" in candidate_set and own_set & work_or_university
    ):
        return 20.0
    if ("viagem" in own_set and candidate_set & {"escolar", "trabalho"}) or (
        "viagem" in candidate_set and own_set & {"escolar", "trabalho"}
    ):
        return 12.0
    return 0.0


def _score_price(own_price, candidate_price) -> tuple[float, float, str | None]:
    own = _coerce_float(own_price)
    candidate = _coerce_float(candidate_price)
    if not own or not candidate or own <= 0 or candidate <= 0:
        return 0.0, 0.0, None

    ratio = min(own, candidate) / max(own, candidate)
    if ratio >= 0.75:
        return 10.0, 0.0, "Faixa de preco muito compativel."
    if ratio >= 0.5:
        return 7.0, 0.0, "Faixa de preco compativel."
    if ratio >= 0.33:
        return 3.0, 0.0, "Faixa de preco parcialmente compativel."
    return 0.0, 10.0, "Preco muito distante."


def _verdict_for_score(score: float) -> str:
    if score >= 0.72:
        return "competitor_direct"
    if score >= 0.45:
        return "competitor_partial"
    return "rejected"


def _confidence_for(
    score: float,
    verdict: str,
    points: float,
    penalties: float,
    own_profile: dict,
    candidate_profile: dict,
) -> str:
    sparse = len(own_profile.get("tokens") or []) < 3 or len(candidate_profile.get("tokens") or []) < 3
    if sparse:
        return "low"
    if verdict == "competitor_direct" and points >= 70 and penalties <= 10:
        return "high"
    if verdict == "rejected" and (penalties >= 35 or score < 0.25):
        return "high"
    if 0.40 <= score <= 0.50 or 0.68 <= score <= 0.76:
        return "medium"
    return "medium"


def _public_profile_signals(profile: dict) -> dict:
    return {
        "title": profile.get("title"),
        "product_type": profile.get("product_type"),
        "audience": profile.get("audience") or [],
        "use_case": profile.get("use_case") or [],
        "style": profile.get("style") or [],
        "features": profile.get("features") or [],
        "price": profile.get("price"),
    }


def _best_matching_label_by_position(normalized_text: str, rules: dict[str, list[str]]) -> str | None:
    matches = []
    for label, patterns in rules.items():
        for pattern in patterns:
            position = _pattern_position(normalized_text, pattern)
            if position is not None:
                matches.append((position, label))
                break
    if not matches:
        return None
    matches.sort(key=lambda item: item[0])
    return matches[0][1]


def _matching_labels(normalized_text: str, rules: dict[str, list[str]]) -> list[str]:
    labels = [
        label
        for label, patterns in rules.items()
        if any(_has_pattern(normalized_text, pattern) for pattern in patterns)
    ]
    return sorted(labels)


def _has_pattern(normalized_text: str, pattern: str) -> bool:
    return _pattern_position(normalized_text, pattern) is not None


def _pattern_position(normalized_text: str, pattern: str) -> int | None:
    normalized_pattern = _normalize_text(pattern)
    if " " in normalized_pattern:
        position = normalized_text.find(normalized_pattern)
        return position if position >= 0 else None
    match = re.search(rf"\b{re.escape(normalized_pattern)}\b", normalized_text)
    return match.start() if match else None


def _tokenize(text: str) -> list[str]:
    normalized = _normalize_text(text)
    tokens = re.findall(r"[a-z0-9]+", normalized)
    return [token for token in tokens if len(token) > 2 and token not in _STOPWORDS]


def _normalize_text(text: str) -> str:
    folded = unicodedata.normalize("NFKD", str(text or ""))
    ascii_text = "".join(char for char in folded if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _load_raw_json(value) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        data = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _load_json_list(value) -> list:
    if not value:
        return []
    try:
        data = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _load_json_dict(value) -> dict:
    if not value:
        return {}
    try:
        data = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _coerce_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, tuple):
        return [str(item) for item in value if item]
    if value:
        return [str(value)]
    return []


def _coerce_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _coerce_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _now() -> str:
    return datetime.utcnow().isoformat()
