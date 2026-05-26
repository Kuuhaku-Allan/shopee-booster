"""
shopee_core/radar_patterns_service.py - Radar R5 pattern analysis.

R5 analyzes products already classified as direct competitors and produces an
explainable, rule-based report. It does not call AI models and does not
integrate with audit, bot or sentinel flows.
"""

from __future__ import annotations

import json
import re
import statistics
import unicodedata
import uuid
from collections import Counter
from datetime import datetime
from typing import Any

from .radar_collector import is_plausible_price, validate_product_extraction
from .radar_db import get_connection, init_db
from .radar_relevance_service import get_matches_for_product
from .radar_service import get_product, list_product_assets


TITLE_STOPWORDS = {
    "a",
    "as",
    "com",
    "da",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "envio",
    "entrega",
    "oferta",
    "original",
    "os",
    "ou",
    "para",
    "pronta",
    "produto",
    "promocao",
    "sem",
    "uma",
    "um",
}

FEATURE_PATTERNS = {
    "rodinhas": ["rodinha", "rodinhas", "rodas", "360"],
    "notebook": ["notebook", "laptop"],
    "impermeavel": ["impermeavel", "resistente a agua"],
    "reforcada": ["reforcada", "reforcado", "reforco"],
    "costura reforcada": ["costura reforcada", "costuras reforcadas"],
    "ziper resistente": ["ziper resistente", "ziperes resistentes", "ziper reforcado"],
    "alca acolchoada": ["alca acolchoada", "alcas acolchoadas"],
    "grande": ["grande"],
    "pequena": ["pequena", "pequeno"],
    "termica": ["termica", "termico"],
    "personagem": ["personagem", "personagens"],
    "princesa": ["princesa"],
    "unicornio": ["unicornio"],
    "escolar": ["escolar", "escola"],
    "infantil": ["infantil", "crianca", "criancas"],
    "feminina": ["feminina", "feminino", "menina"],
    "masculina": ["masculina", "masculino", "menino"],
    "minimalista": ["minimalista", "clean"],
    "premium": ["premium", "luxo"],
}

DESCRIPTION_ARGUMENTS = {
    "durabilidade": ["durabilidade", "duravel", "dura muito"],
    "conforto": ["conforto", "confortavel", "acolchoada", "acolchoado"],
    "espaco interno": ["espaco interno", "amplo espaco", "cabe cadernos", "capacidade"],
    "organizacao": ["organizacao", "compartimentos", "bolsos", "divisorias"],
    "material resistente": ["material resistente", "resistente", "poliester", "nylon"],
    "facil limpeza": ["facil limpeza", "limpar", "limpeza"],
    "presente": ["presente", "presentear"],
    "volta as aulas": ["volta as aulas", "volta aulas"],
    "frete/envio rapido": ["frete", "envio rapido", "pronta entrega"],
    "garantia": ["garantia"],
    "qualidade premium": ["qualidade premium", "alta qualidade", "premium"],
}


def get_direct_competitors_for_analysis(
    own_product_uid: str,
    include_partial: bool = False,
    include_low_quality: bool = False,
) -> list[dict]:
    """Load matched direct competitors with raw data and assets."""
    verdicts = ["competitor_direct"]
    if include_partial:
        verdicts.append("competitor_partial")

    init_db()
    placeholders = ", ".join("?" for _ in verdicts)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                p.*,
                m.verdict AS match_verdict,
                m.relevance_score AS match_relevance_score,
                m.confidence AS match_confidence,
                m.reasons_json AS match_reasons_json,
                m.signals_json AS match_signals_json
            FROM radar_competitor_matches m
            JOIN radar_products p
              ON p.product_uid = m.candidate_product_uid
            WHERE m.own_product_uid = ?
              AND m.verdict IN ({placeholders})
            ORDER BY m.relevance_score DESC, m.updated_at DESC
            """,
            [own_product_uid, *verdicts],
        ).fetchall()

    products = []
    for row in rows:
        product = dict(row)
        raw = _load_json_dict(product.get("raw_json"))
        product["raw"] = raw
        product["description"] = _product_description(product, raw)
        product["attributes"] = _product_attributes(raw)
        product["category_path"] = _product_category_path(raw)
        product["image_urls"] = _product_image_urls(raw)
        product["assets"] = list_product_assets(product["product_uid"])
        product["match_reasons"] = _load_json_list(product.get("match_reasons_json"))
        product["match_signals"] = _load_json_dict(product.get("match_signals_json"))
        product["quality"] = _product_quality(product, raw)
        if not include_low_quality and not product["quality"].get("ok"):
            continue
        products.append(product)

    return products


def analyze_price_patterns(products: list[dict], weights: dict[str, float] | None = None) -> dict:
    """Calculate basic price statistics and simple outlier signals."""
    weighted_pairs = []
    for product in products:
        p = _coerce_float(product.get("price"))
        if p is None or not is_plausible_price(p, _category_hint(product)):
            continue
        w = (weights or {}).get(product.get("product_uid"), 1.0)
        weighted_pairs.append((p, w))

    if not weighted_pairs:
        return {
            "min": None, "max": None, "avg": None, "median": None,
            "suggested_band": {"low": None, "high": None},
            "outliers": [], "dispersion_warning": None,
        }

    prices = [p for p, _ in weighted_pairs]
    total_weight = sum(w for _, w in weighted_pairs)
    avg = sum(p * w for p, w in weighted_pairs) / total_weight if total_weight else 0
    # Weighted median: sort by price, accumulate weights until reaching half
    sorted_pairs = sorted(weighted_pairs, key=lambda x: x[0])
    cumulative = 0.0
    median = sorted_pairs[-1][0]
    for p, w in sorted_pairs:
        cumulative += w
        if cumulative >= total_weight / 2:
            median = p
            break

    median = round(median, 2)
    low_band = round(max(min(prices), median * 0.85), 2)
    high_band = round(min(max(prices), median * 1.15), 2)
    outliers = []

    for product in products:
        price = _coerce_float(product.get("price"))
        if price is None or price <= 0:
            continue
        if price < median * 0.55:
            outliers.append(_price_outlier(product, "low"))
        elif price > median * 1.8:
            outliers.append(_price_outlier(product, "high"))

    dispersion_warning = None
    if len(prices) >= 3 and max(prices) > 0:
        cv = statistics.stdev(prices) / statistics.mean(prices)
        if cv > 0.5:
            dispersion_warning = f"Alta dispersao de precos (CV={cv:.2f}). Mediana ({median}) e mais representativa que media ({round(avg, 2)})."

    return {
        "min": round(min(prices), 2),
        "max": round(max(prices), 2),
        "avg": round(avg, 2),
        "median": median,
        "suggested_band": {"low": low_band, "high": high_band},
        "outliers": outliers,
        "dispersion_warning": dispersion_warning,
    }


def analyze_title_terms(products: list[dict], weights: dict[str, float] | None = None) -> dict:
    """Extract frequent meaningful title terms."""
    counter: Counter[str] = Counter()
    for product in products:
        w = (weights or {}).get(product.get("product_uid"), 1.0)
        terms = set(_tokenize(product.get("title") or ""))
        for term in terms:
            counter[term] += w

    total_weight = sum((weights or {}).get(p.get("product_uid"), 1.0) for p in products) or 1.0
    top_terms = _counter_to_frequency_rows(counter, total_weight)
    return {
        "top_terms": top_terms[:20],
        "strong_terms": [row for row in top_terms if row["frequency"] >= 0.4],
        "weak_terms": [row for row in top_terms if row["frequency"] < 0.2],
    }


def analyze_feature_patterns(products: list[dict], own_product: dict | None = None, weights: dict[str, float] | None = None) -> dict:
    """
    Detect recurring product features from title, description and raw data.
    R5.1C: Separa features off-niche quando produto proprio e fornecido.
    """
    counter: Counter[str] = Counter()
    feature_sources: dict[str, list[str]] = {}
    total_weight = sum((weights or {}).get(p.get("product_uid"), 1.0) for p in products) or 1.0

    for product in products:
        w = (weights or {}).get(product.get("product_uid"), 1.0)
        text = _product_full_text(product)
        title = _normalize_text(product.get("title") or "")

        for feature, patterns in FEATURE_PATTERNS.items():
            if any(_has_pattern(text, pattern) for pattern in patterns):
                counter[feature] += w
                if feature not in feature_sources:
                    feature_sources[feature] = []
                if any(_has_pattern(title, pattern) for pattern in patterns):
                    feature_sources[feature].append("title")
                else:
                    feature_sources[feature].append("description")

    features = _counter_to_frequency_rows(counter, total_weight, key_name="feature")
    
    # R5.1C: Detectar features off-niche
    off_niche_features = []
    in_niche_features = []
    
    if own_product:
        own_profile = _build_simple_profile(own_product)
        is_child_school = (
            ("infantil" in own_profile.get("audience", []) or "feminino" in own_profile.get("audience", []))
            and "escolar" in own_profile.get("use_case", [])
        )
        
        for row in features:
            feature = row["feature"]
            # Features problematicas para nicho infantil/feminino/escolar
            if is_child_school and feature in {"notebook", "masculina", "premium", "minimalista"}:
                off_niche_features.append({
                    **row,
                    "warning": f"Feature '{feature}' pode ser ruido/off-niche para produto infantil feminino escolar.",
                })
            else:
                in_niche_features.append(row)
    else:
        in_niche_features = features

    return {
        "features": in_niche_features,
        "off_niche_features": off_niche_features,
        "strong_patterns": [row for row in in_niche_features if row["frequency"] >= 0.4],
        "medium_patterns": [
            row for row in in_niche_features if 0.2 <= row["frequency"] < 0.4
        ],
        "possible_differentials": [
            row for row in in_niche_features if row["frequency"] < 0.2
        ],
    }


def analyze_description_patterns(products: list[dict], weights: dict[str, float] | None = None) -> dict:
    """Detect recurring commercial arguments in descriptions."""
    counter: Counter[str] = Counter()
    total_weight = sum((weights or {}).get(p.get("product_uid"), 1.0) for p in products) or 1.0

    for product in products:
        w = (weights or {}).get(product.get("product_uid"), 1.0)
        text = _normalize_text(
            " ".join(
                [
                    product.get("description") or "",
                    _attributes_text(product.get("attributes") or {}),
                ]
            )
        )
        arguments = {
            argument
            for argument, patterns in DESCRIPTION_ARGUMENTS.items()
            if any(_has_pattern(text, pattern) for pattern in patterns)
        }
        for arg in arguments:
            counter[arg] += w

    rows = _counter_to_frequency_rows(counter, total_weight, key_name="argument")
    found = {row["argument"] for row in rows}
    return {
        "commercial_arguments": rows,
        "common_promises": [row for row in rows if row["frequency"] >= 0.4],
        "missing_opportunities": [
            argument for argument in DESCRIPTION_ARGUMENTS if argument not in found
        ],
    }


def analyze_image_patterns(products: list[dict]) -> dict:
    """Analyze simple image metadata without computer vision."""
    counts = []
    product_rows = []
    downloaded_assets = 0

    for product in products:
        image_count = _image_count(product)
        local_assets = [
            asset for asset in product.get("assets", []) if asset.get("local_path")
        ]
        downloaded_assets += len(local_assets)
        counts.append(image_count)
        product_rows.append(
            {
                "product_uid": product.get("product_uid"),
                "title": product.get("title"),
                "image_count": image_count,
                "downloaded_assets": len(local_assets),
            }
        )

    if not counts:
        return {
            "avg_image_count": 0,
            "min_image_count": 0,
            "max_image_count": 0,
            "products_with_many_images": [],
            "products_with_few_images": [],
            "downloaded_assets": 0,
            "warnings": ["Nenhum concorrente direto com imagens para analisar."],
        }

    avg = sum(counts) / len(counts)
    warnings = []
    if avg < 3:
        warnings.append("Concorrentes diretos tem poucas imagens em media.")
    if downloaded_assets == 0:
        warnings.append("Nenhum asset baixado encontrado; analise de imagens usa apenas URLs/metadados.")

    return {
        "avg_image_count": round(avg, 2),
        "min_image_count": min(counts),
        "max_image_count": max(counts),
        "products_with_many_images": [
            row for row in product_rows if row["image_count"] >= max(6, avg)
        ],
        "products_with_few_images": [
            row for row in product_rows if row["image_count"] <= 2
        ],
        "downloaded_assets": downloaded_assets,
        "warnings": warnings,
    }


def _build_simple_profile(product: dict) -> dict:
    """Build a simple profile for niche detection."""
    raw = _load_json_dict(product.get("raw_json"))
    text = _normalize_text(
        " ".join([
            product.get("title") or "",
            _product_description(product, raw),
        ])
    )
    
    audience = []
    if any(pattern in text for pattern in ["infantil", "crianca", "menina", "menino"]):
        audience.append("infantil")
    if any(pattern in text for pattern in ["feminino", "feminina", "menina", "princesa", "rosa"]):
        audience.append("feminino")
    if any(pattern in text for pattern in ["masculino", "masculina", "menino"]):
        audience.append("masculino")
    if any(pattern in text for pattern in ["adulto", "adulta", "executivo", "executiva"]):
        audience.append("adulto")
    
    use_case = []
    if any(pattern in text for pattern in ["escolar", "escola"]):
        use_case.append("escolar")
    if any(pattern in text for pattern in ["notebook", "laptop"]):
        use_case.append("notebook")
    if any(pattern in text for pattern in ["trabalho", "executivo", "executiva", "office"]):
        use_case.append("trabalho")
    if any(pattern in text for pattern in ["faculdade", "universidade", "universitario"]):
        use_case.append("faculdade")
    
    return {
        "audience": audience,
        "use_case": use_case,
    }


def _compute_competitor_weights(
    competitors: list[dict], candidate_scope: str
) -> dict[str, float]:
    """Compute analysis weight per competitor based on scope."""
    weights: dict[str, float] = {}
    for prod in competitors:
        uid = prod.get("product_uid")
        if candidate_scope == "direct_only":
            weights[uid] = 1.0 if prod.get("match_verdict") == "competitor_direct" else 0.0
        else:
            weights[uid] = 1.0 if prod.get("match_verdict") == "competitor_direct" else 0.5
    return weights


def _compute_confidence(direct_count: int, partial_count: int, candidate_scope: str) -> str:
    """R7.2L: Confidence tiers based on count and scope."""
    effective = direct_count
    if candidate_scope == "direct_plus_partial":
        effective = direct_count + int(partial_count * 0.5)

    if effective >= 10 or (direct_count >= 7 and partial_count >= 3):
        return "high"
    if effective >= 5:
        return "medium"
    if effective >= 3:
        return "low"
    return "insufficient"


def _build_strategy_title(analyses: dict) -> dict:
    """Build title strategy section from term analysis."""
    strong = analyses.get("title_terms", {}).get("strong_terms", [])
    weak = analyses.get("title_terms", {}).get("weak_terms", [])
    all_terms = analyses.get("title_terms", {}).get("top_terms", [])

    strong_set = {r["term"] for r in strong}
    weak_set = {r["term"] for r in weak}
    secondary = [r for r in all_terms if r["term"] not in strong_set and r["term"] not in weak_set]

    return {
        "strong_terms": [r["term"] for r in strong],
        "secondary_terms": [r["term"] for r in secondary],
        "avoid_terms": [r["term"] for r in weak],
        "evidence_note": "Termos fortes aparecem em pelo menos 40% dos concorrentes; secundarios entre 20% e 40%.",
    }


def _build_strategy_features(analyses: dict) -> dict:
    """Build feature strategy section from feature analysis."""
    features_data = analyses.get("features", {})
    return {
        "recommended": [r["feature"] for r in features_data.get("strong_patterns", [])],
        "recurring": [r["feature"] for r in features_data.get("medium_patterns", [])],
        "off_niche": [r["feature"] for r in features_data.get("off_niche_features", [])],
        "warnings": [f.get("warning", "") for f in features_data.get("off_niche_features", [])],
    }


def _build_strategy_description(analyses: dict) -> dict:
    """Build description strategy section from description analysis."""
    desc = analyses.get("description", {})
    common = desc.get("common_promises", [])
    all_args = desc.get("commercial_arguments", [])
    missing = desc.get("missing_opportunities", [])

    quality_terms = [r for r in all_args if r.get("argument") in (
        "material resistente", "qualidade premium", "durabilidade", "facil limpeza", "garantia")]
    use_arguments = [r for r in all_args if r.get("argument") in (
        "conforto", "espaco interno", "organizacao", "volta as aulas")]
    observations = []
    if missing:
        observations.append(f"Oportunidades nao exploradas: {', '.join(missing[:4])}.")

    return {
        "commercial_arguments": [r["argument"] for r in all_args],
        "quality_terms": [r["argument"] for r in quality_terms],
        "use_arguments": [r["argument"] for r in use_arguments],
        "observations": observations,
    }


def _build_strategy_images(analyses: dict) -> dict:
    """Build image strategy section."""
    img = analyses.get("images", {})
    avg = img.get("avg_image_count", 0)
    recs = []
    if avg >= 3:
        recs.append(f"Manter pelo menos {int(avg)} imagens, seguindo a media dos concorrentes.")
    elif avg > 0:
        recs.append(f"Media baixa de imagens ({avg:.0f}); considerar aumentar para pelo menos 3.")
    if img.get("downloaded_assets", 0) == 0 and avg > 0:
        recs.append("Registrar imagens como assets para analise visual futura.")
    return {
        "avg_image_count": avg,
        "main_image_presence": "Presente" if avg > 0 else "Nao verificado",
        "recommendations": recs,
    }


def _build_evidence_list(competitors: list[dict]) -> list[dict]:
    """Build evidence list of competitors used in the report."""
    evidence = []
    for prod in competitors:
        evidence.append({
            "product_uid": prod.get("product_uid"),
            "title": prod.get("title"),
            "price": prod.get("price"),
            "marketplace": prod.get("marketplace"),
            "shop_name": prod.get("shop_name"),
            "match_verdict": prod.get("match_verdict"),
            "match_relevance_score": prod.get("match_relevance_score"),
        })
    return evidence


def build_recommendations(own_product: dict, analyses: dict) -> list[dict]:
    """Build deterministic recommendations from pattern evidence."""
    recommendations = []
    own_title_terms = set(_tokenize(own_product.get("title") or ""))
    strong_terms = analyses.get("title_terms", {}).get("strong_terms", [])
    missing_terms = [
        row["term"]
        for row in strong_terms
        if row["term"] not in own_title_terms
    ][:6]
    if missing_terms:
        recommendations.append(
            {
                "type": "title",
                "priority": "high",
                "recommendation": (
                    "Incluir termos fortes no titulo: "
                    + ", ".join(missing_terms)
                    + "."
                ),
                "evidence": "Esses termos aparecem com alta frequencia entre concorrentes diretos.",
            }
        )

    price = _coerce_float(own_product.get("price"))
    price_analysis = analyses.get("price", {})
    band = price_analysis.get("suggested_band") or {}
    if price and band.get("high") and price > band["high"]:
        recommendations.append(
            {
                "type": "price",
                "priority": "medium",
                "recommendation": (
                    f"Reavaliar preco acima de R$ {band['high']:.2f} "
                    "para este recorte de concorrentes."
                ),
                "evidence": (
                    f"Preco medio dos concorrentes diretos: R$ {price_analysis.get('avg'):.2f}."
                ),
            }
        )
    elif price and band.get("low") and price < band["low"]:
        recommendations.append(
            {
                "type": "price",
                "priority": "medium",
                "recommendation": (
                    f"Verificar se preco abaixo de R$ {band['low']:.2f} "
                    "esta comunicando valor suficiente."
                ),
                "evidence": (
                    f"Mediana dos concorrentes diretos: R$ {price_analysis.get('median'):.2f}."
                ),
            }
        )

    own_text = _normalize_text(
        " ".join(
            [
                own_product.get("title") or "",
                _product_description(own_product, _load_json_dict(own_product.get("raw_json"))),
            ]
        )
    )
    
    # R5.1C: Usar apenas features in-niche, ignorar off-niche
    missing_features = []
    for row in analyses.get("features", {}).get("strong_patterns", []):
        feature = row["feature"]
        if not _has_pattern(own_text, feature):
            missing_features.append(feature)
    
    # Avisar sobre features off-niche se existirem
    off_niche = analyses.get("features", {}).get("off_niche_features", [])
    if off_niche:
        warnings_text = "; ".join([f["warning"] for f in off_niche[:3]])
        recommendations.append(
            {
                "type": "features",
                "priority": "low",
                "recommendation": f"Features off-niche detectadas: {', '.join([f['feature'] for f in off_niche[:3]])}.",
                "evidence": warnings_text,
            }
        )
    
    if missing_features:
        recommendations.append(
            {
                "type": "features",
                "priority": "high",
                "recommendation": (
                    "Destacar features recorrentes: "
                    + ", ".join(missing_features[:5])
                    + "."
                ),
                "evidence": "Essas features aparecem em pelo menos 40% dos concorrentes diretos.",
            }
        )

    common_promises = analyses.get("description", {}).get("common_promises", [])
    missing_promises = [
        row["argument"]
        for row in common_promises
        if not _has_pattern(own_text, row["argument"])
    ][:4]
    if missing_promises:
        recommendations.append(
            {
                "type": "description",
                "priority": "medium",
                "recommendation": (
                    "Adicionar argumentos na descricao: "
                    + ", ".join(missing_promises)
                    + "."
                ),
                "evidence": "Argumentos comerciais recorrentes aparecem nas descricoes dos concorrentes diretos.",
            }
        )

    own_image_count = _image_count(
        {
            "raw": _load_json_dict(own_product.get("raw_json")),
            "assets": list_product_assets(own_product["product_uid"]),
        }
    )
    image_analysis = analyses.get("images", {})
    if image_analysis.get("avg_image_count", 0) and own_image_count < image_analysis["avg_image_count"]:
        recommendations.append(
            {
                "type": "images",
                "priority": "medium",
                "recommendation": "Aumentar quantidade/variedade de imagens do produto.",
                "evidence": (
                    "Media de imagens dos concorrentes diretos: "
                    f"{image_analysis['avg_image_count']}."
                ),
            }
        )

    return recommendations


def generate_pattern_report(
    own_product_uid: str,
    include_partial: bool = False,
    candidate_scope: str | None = None,
    min_direct: int = 3,
    save: bool = True,
) -> dict:
    """Generate and optionally save a full R5 pattern report.

    Args:
        own_product_uid: Product UID of the own product.
        include_partial: Legacy flag (True = include partial matches).
        candidate_scope: 'direct_only' (default) or 'direct_plus_partial'.
                         Overrides include_partial if provided.
        min_direct: Minimum direct competitors for reliable report.
        save: Whether to persist the report to DB.
    """
    # R7.2L: candidate_scope overrides include_partial
    if candidate_scope is None:
        candidate_scope = "direct_plus_partial" if include_partial else "direct_only"

    own_product = get_product(own_product_uid)
    if not own_product:
        raise ValueError(f"Produto proprio nao encontrado: {own_product_uid}")

    all_competitors = get_direct_competitors_for_analysis(
        own_product_uid,
        include_partial=(candidate_scope == "direct_plus_partial"),
        include_low_quality=True,
    )
    competitors = [
        product for product in all_competitors if product.get("quality", {}).get("ok")
    ]
    ignored_low_quality = len(all_competitors) - len(competitors)

    # Filter by scope — only keep products with weight > 0
    weights = _compute_competitor_weights(competitors, candidate_scope)
    scoped_competitors = [p for p in competitors if weights.get(p.get("product_uid"), 0) > 0]
    # Recompute weights for the scoped set only
    weights = _compute_competitor_weights(scoped_competitors, candidate_scope)
    # Filter out products with zero weight (should not happen but safeguard)
    scoped_competitors = [p for p in scoped_competitors if weights.get(p.get("product_uid"), 0) > 0]
    # Recompute weights one more time for the clean set
    weights = _compute_competitor_weights(scoped_competitors, candidate_scope)

    direct_count = sum(
        1 for p in scoped_competitors if p.get("match_verdict") == "competitor_direct"
    )
    partial_count = sum(
        1 for p in scoped_competitors if p.get("match_verdict") == "competitor_partial"
    )

    analyses = {
        "price": analyze_price_patterns(scoped_competitors, weights),
        "title_terms": analyze_title_terms(scoped_competitors, weights),
        "features": analyze_feature_patterns(scoped_competitors, own_product=own_product, weights=weights),
        "description": analyze_description_patterns(scoped_competitors, weights),
        "images": analyze_image_patterns(scoped_competitors),
    }

    warnings = []
    if direct_count < 3:
        warnings.append("Base pequena. Recomendacoes podem ser pouco confiaveis.")
    if direct_count < min_direct:
        warnings.append(f"Concorrentes diretos abaixo do minimo solicitado ({min_direct}).")
    if ignored_low_quality:
        warnings.append(f"{ignored_low_quality} produtos ignorados por baixa qualidade de extracao.")
    warnings.extend(analyses["images"].get("warnings") or [])
    dispersion_warning = analyses["price"].get("dispersion_warning")
    if dispersion_warning:
        warnings.append(dispersion_warning)

    confidence = _compute_confidence(direct_count, partial_count, candidate_scope)

    # R7.2L: Strategy sections and evidence list
    strategy_title = _build_strategy_title(analyses)
    strategy_features = _build_strategy_features(analyses)
    strategy_description = _build_strategy_description(analyses)
    strategy_images = _build_strategy_images(analyses)
    evidence_list = _build_evidence_list(scoped_competitors)

    recommendations = build_recommendations(own_product, analyses)
    raw = {
        "own_product": _public_product(own_product),
        "competitors": [_public_product(p) for p in scoped_competitors],
        "analyses": analyses,
        "confidence": confidence,
        "candidate_scope": candidate_scope,
        "ignored_low_quality": ignored_low_quality,
        "strategy_title": strategy_title,
        "strategy_features": strategy_features,
        "strategy_description": strategy_description,
        "strategy_images": strategy_images,
        "evidence_list": evidence_list,
    }
    report = {
        "report_uid": str(uuid.uuid4()),
        "own_product_uid": own_product_uid,
        "total_competitors": len(scoped_competitors),
        "direct_count": direct_count,
        "partial_count": partial_count,
        "candidate_scope": candidate_scope,
        "price_min": analyses["price"]["min"],
        "price_max": analyses["price"]["max"],
        "price_avg": analyses["price"]["avg"],
        "price_median": analyses["price"]["median"],
        "title_terms": analyses["title_terms"],
        "features": analyses["features"],
        "description_patterns": analyses["description"],
        "image_patterns": analyses["images"],
        "warnings": warnings,
        "recommendations": recommendations,
        "strategy_title": strategy_title,
        "strategy_features": strategy_features,
        "strategy_description": strategy_description,
        "strategy_images": strategy_images,
        "evidence_list": evidence_list,
        "raw": raw,
        "confidence": confidence,
        "ignored_low_quality": ignored_low_quality,
    }

    if save:
        return _save_pattern_report(report)

    return report


def get_latest_pattern_report(own_product_uid: str) -> dict | None:
    """Return the newest saved pattern report for one own product."""
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM radar_pattern_reports
            WHERE own_product_uid = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (own_product_uid,),
        ).fetchone()

    return _decode_report_row(dict(row)) if row else None


def _save_pattern_report(report: dict) -> dict:
    init_db()
    now = _now()
    report_uid = report.get("report_uid") or str(uuid.uuid4())

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO radar_pattern_reports (
                report_uid, own_product_uid, total_competitors, direct_count,
                partial_count, price_min, price_max, price_avg, price_median,
                title_terms_json, feature_terms_json,
                description_patterns_json, image_patterns_json, warnings_json,
                recommendations_json, raw_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_uid,
                report["own_product_uid"],
                int(report["total_competitors"]),
                int(report["direct_count"]),
                int(report["partial_count"]),
                report["price_min"],
                report["price_max"],
                report["price_avg"],
                report["price_median"],
                _json(report["title_terms"]),
                _json(report["features"]),
                _json(report["description_patterns"]),
                _json(report["image_patterns"]),
                _json(report["warnings"]),
                _json(report["recommendations"]),
                _json(report["raw"]),
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM radar_pattern_reports WHERE report_uid = ?",
            (report_uid,),
        ).fetchone()

    return _decode_report_row(dict(row))


def _decode_report_row(row: dict) -> dict:
    row["title_terms"] = _load_json_dict(row.pop("title_terms_json", None))
    row["features"] = _load_json_dict(row.pop("feature_terms_json", None))
    row["description_patterns"] = _load_json_dict(row.pop("description_patterns_json", None))
    row["image_patterns"] = _load_json_dict(row.pop("image_patterns_json", None))
    row["warnings"] = _load_json_list(row.pop("warnings_json", None))
    row["recommendations"] = _load_json_list(row.pop("recommendations_json", None))
    row["raw"] = _load_json_dict(row.pop("raw_json", None))
    row["confidence"] = row["raw"].get("confidence")
    row["ignored_low_quality"] = row["raw"].get("ignored_low_quality", 0)
    # R7.2L: Decode strategy sections from raw
    row["candidate_scope"] = row["raw"].get("candidate_scope", "direct_only")
    row["strategy_title"] = row["raw"].get("strategy_title", {})
    row["strategy_features"] = row["raw"].get("strategy_features", {})
    row["strategy_description"] = row["raw"].get("strategy_description", {})
    row["strategy_images"] = row["raw"].get("strategy_images", {})
    row["evidence_list"] = row["raw"].get("evidence_list", [])
    return row


def _product_quality(product: dict, raw: dict | None = None) -> dict:
    raw = raw if raw is not None else _load_json_dict(product.get("raw_json"))
    data = dict(raw)
    data.setdefault("url", product.get("url"))
    data.setdefault("canonical_url", product.get("canonical_url"))
    data.setdefault("marketplace", product.get("marketplace"))
    data.setdefault("title", product.get("title"))
    data.setdefault("price", product.get("price"))
    data.setdefault("shop_name", product.get("shop_name"))
    data.setdefault("image_urls", _product_image_urls(raw))
    data.setdefault("description_image_urls", raw.get("description_image_urls") or [])
    quality = validate_product_extraction(data, product.get("marketplace") or "")
    asset_count = len(product.get("assets") or [])
    if asset_count > 80:
        quality = dict(quality)
        quality["errors"] = list(quality.get("errors") or [])
        quality["errors"].append(f"Assets demais registrados para um produto: {asset_count}.")
        quality["ok"] = False
        quality["quality_score"] = min(float(quality.get("quality_score") or 0), 0.5)
    return quality


def _count_matches(own_product_uid: str, verdict: str) -> int:
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM radar_competitor_matches
            WHERE own_product_uid = ? AND verdict = ?
            """,
            (own_product_uid, verdict),
        ).fetchone()
    return int(row["total"] if row else 0)


def _counter_to_frequency_rows(
    counter: Counter,
    total: int,
    key_name: str = "term",
) -> list[dict]:
    if total <= 0:
        return []
    rows = [
        {
            key_name: key,
            "count": count,
            "frequency": round(count / total, 4),
        }
        for key, count in counter.items()
    ]
    return sorted(rows, key=lambda row: (-row["count"], row[key_name]))


def _price_outlier(product: dict, kind: str) -> dict:
    return {
        "product_uid": product.get("product_uid"),
        "title": product.get("title"),
        "price": _coerce_float(product.get("price")),
        "type": kind,
    }


def _product_description(product: dict, raw: dict | None = None) -> str:
    raw = raw if raw is not None else _load_json_dict(product.get("raw_json"))
    raw_inner = raw.get("raw") if isinstance(raw.get("raw"), dict) else {}
    return (
        raw.get("description")
        or raw_inner.get("description")
        or product.get("description")
        or ""
    )


def _product_attributes(raw: dict) -> dict:
    raw_inner = raw.get("raw") if isinstance(raw.get("raw"), dict) else {}
    attrs = raw.get("attributes") or raw_inner.get("attributes")
    return attrs if isinstance(attrs, dict) else {}


def _product_category_path(raw: dict) -> list[str]:
    raw_inner = raw.get("raw") if isinstance(raw.get("raw"), dict) else {}
    values = raw.get("category_path") or raw_inner.get("category_path") or []
    if isinstance(values, list):
        return [str(value) for value in values if value]
    return [str(values)] if values else []


def _product_image_urls(raw: dict) -> list[str]:
    raw_inner = raw.get("raw") if isinstance(raw.get("raw"), dict) else {}
    urls = raw.get("image_urls") or raw_inner.get("image_urls") or []
    return [str(url) for url in urls if url] if isinstance(urls, list) else []


def _product_full_text(product: dict) -> str:
    raw = product.get("raw") if isinstance(product.get("raw"), dict) else _load_json_dict(product.get("raw_json"))
    parts = [
        product.get("title") or "",
        product.get("description") or _product_description(product, raw),
        " ".join(product.get("category_path") or _product_category_path(raw)),
        _attributes_text(product.get("attributes") or _product_attributes(raw)),
    ]
    return _normalize_text(" ".join(parts))


def _category_hint(product: dict) -> str | None:
    text = _product_full_text(product)
    if "mochila" in text:
        return "mochila"
    return None


def _attributes_text(attributes: dict) -> str:
    return " ".join(f"{key} {value}" for key, value in attributes.items())


def _image_count(product: dict) -> int:
    raw = product.get("raw") if isinstance(product.get("raw"), dict) else _load_json_dict(product.get("raw_json"))
    urls = set(product.get("image_urls") or _product_image_urls(raw))
    for asset in product.get("assets", []):
        if asset.get("asset_type") in {"image", "thumbnail", "description_image"}:
            if asset.get("source_url"):
                urls.add(asset["source_url"])
            elif asset.get("local_path"):
                urls.add(asset["local_path"])
    return len(urls)


def _public_product(product: dict) -> dict:
    return {
        "product_uid": product.get("product_uid"),
        "title": product.get("title"),
        "price": product.get("price"),
        "marketplace": product.get("marketplace"),
        "shop_name": product.get("shop_name"),
        "match_verdict": product.get("match_verdict"),
        "match_relevance_score": product.get("match_relevance_score"),
    }


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", _normalize_text(text))
    return [
        token
        for token in tokens
        if len(token) > 2 and token not in TITLE_STOPWORDS
    ]


def _has_pattern(normalized_text: str, pattern: str) -> bool:
    normalized_pattern = _normalize_text(pattern)
    if " " in normalized_pattern:
        return normalized_pattern in normalized_text
    return re.search(rf"\b{re.escape(normalized_pattern)}\b", normalized_text) is not None


def _normalize_text(text: str) -> str:
    folded = unicodedata.normalize("NFKD", str(text or ""))
    ascii_text = "".join(char for char in folded if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()


def _load_json_dict(value) -> dict:
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
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        data = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _coerce_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _now() -> str:
    return datetime.utcnow().isoformat()
