"""
R7.7 - Optional Radar competitor source for Sentinela.

This module only decides and normalizes competitor data. It does not own
Sentinela scheduling, locks, state, triggers, or dispatch.
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger("sentinel_competitor_source")

MIN_CURRENT_USEFUL = 5
MIN_RADAR_EFFECTIVE = 3
RADAR_CONFIDENCES = {"high", "medium"}
UNAVAILABLE_STATUSES = {"unavailable", "removed", "deleted", "inactive", "indisponivel"}


def _radar_enabled() -> bool:
    value = os.getenv("SHOPEE_SENTINEL_USE_RADAR", "").strip().lower()
    return value in {"1", "true", "yes", "y", "sim", "on"}


def _first_present(row: dict, *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _parse_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        clean = value.replace("R$", "").replace(" ", "").strip()
        if not clean:
            return None
        if "," in clean:
            clean = clean.replace(".", "").replace(",", ".")
        try:
            return float(clean)
        except ValueError:
            return None
    return None


def _marketplace_from_url(url: str | None) -> str:
    url = (url or "").lower()
    if "mercadolivre" in url or "mercadolibre" in url:
        return "mercadolivre"
    if "shopee" in url:
        return "shopee"
    if "amazon" in url:
        return "amazon"
    return ""


def _is_unavailable(row: dict) -> bool:
    status = str(
        _first_present(row, "availability_status", "status", "item_status", "product_status") or ""
    ).strip().lower()
    return status in UNAVAILABLE_STATUSES


def _normalize_one_for_sentinel(row: dict, ranking: int, keyword: str = "") -> dict | None:
    if not isinstance(row, dict) or _is_unavailable(row):
        return None

    title = _first_present(row, "titulo", "nome", "title", "name")
    price = _parse_float(_first_present(row, "preco", "price", "valor"))
    url = _first_present(row, "url", "canonical_url", "permalink")
    marketplace = (
        _first_present(row, "marketplace")
        or _marketplace_from_url(str(url or ""))
        or _first_present(row, "source")
    )

    if not title or price is None or price <= 0 or not url or not marketplace:
        return None

    seller = _first_present(row, "shop_id", "shopid", "seller", "shop_name", "loja")
    item_id = _first_present(row, "item_id", "itemid", "candidate_product_uid", "product_uid", "id")
    verdict = _first_present(row, "verdict", "match_verdict")
    score = _parse_float(_first_present(row, "score", "relevance_score"))

    return {
        "ranking": ranking,
        "titulo": str(title).strip(),
        "preco": float(price),
        "loja": str(seller or ""),
        "url": str(url).strip(),
        "is_new": bool(row.get("is_new", False)),
        "keyword": keyword or str(row.get("keyword") or ""),
        "item_id": str(item_id or url),
        "shop_id": str(seller or row.get("shop_id") or ""),
        "source": str(_first_present(row, "source", "competitor_source") or marketplace),
        "marketplace": str(marketplace),
        "score": score,
        "verdict": verdict,
        "competitor_source": str(row.get("competitor_source") or "current"),
    }


def normalize_sentinel_competitors(
    competitors: list[dict] | None,
    keyword: str = "",
    limit: int = 10,
) -> list[dict]:
    """Normalize competitors to the shape expected by the Sentinela report."""
    normalized: list[dict] = []
    for row in competitors or []:
        item = _normalize_one_for_sentinel(row, len(normalized) + 1, keyword=keyword)
        if not item:
            continue
        normalized.append(item)
        if len(normalized) >= limit:
            break
    return normalized


def _current_quality(current_competitors: list[dict] | None, limit: int = 20) -> dict:
    normalized = normalize_sentinel_competitors(current_competitors or [], limit=limit)
    sources = {
        str(_first_present(row, "source", "competitor_source", "marketplace") or "").lower()
        for row in current_competitors or []
        if isinstance(row, dict)
    }
    warnings = []
    if len(normalized) < MIN_CURRENT_USEFUL:
        warnings.append("Fonte atual retornou poucos concorrentes uteis para a Sentinela.")
    if "mock" in sources:
        warnings.append("Fonte atual esta usando provider mock.")
    return {
        "ok": len(normalized) >= MIN_CURRENT_USEFUL,
        "useful_count": len(normalized),
        "sources": sorted(source for source in sources if source),
        "is_mock": "mock" in sources,
        "warnings": warnings,
    }


def _radar_match_to_competitor(match: dict, fallback_verdict: str) -> dict | None:
    if not isinstance(match, dict) or _is_unavailable(match):
        return None

    title = _first_present(match, "title", "titulo", "name", "nome")
    price = _parse_float(_first_present(match, "price", "preco", "valor"))
    url = _first_present(match, "url", "canonical_url", "permalink")
    marketplace = _first_present(match, "marketplace") or _marketplace_from_url(str(url or ""))
    if not title or price is None or price <= 0 or not url or not marketplace:
        return None

    seller = _first_present(match, "seller", "shop_name", "loja", "shop_id")
    verdict = _first_present(match, "verdict", "match_verdict") or fallback_verdict
    score = _parse_float(_first_present(match, "relevance_score", "score"))
    product_uid = _first_present(match, "candidate_product_uid", "product_uid", "item_id")

    return {
        "title": str(title).strip(),
        "titulo": str(title).strip(),
        "price": float(price),
        "preco": float(price),
        "url": str(url).strip(),
        "canonical_url": str(url).strip(),
        "marketplace": str(marketplace),
        "seller": str(seller or ""),
        "shop_name": str(seller or ""),
        "score": score,
        "relevance_score": score,
        "verdict": str(verdict),
        "item_id": str(product_uid or url),
        "shop_id": str(seller or ""),
        "source": "radar",
        "competitor_source": "radar",
    }


def get_radar_competitors_for_sentinel(own_product_uid: str, limit: int = 10) -> dict:
    """Return valid Radar competitors for Sentinela without touching Sentinela state."""
    if not own_product_uid:
        return {
            "ok": False,
            "source": "radar",
            "confidence": "insufficient",
            "report_uid": None,
            "effective_competitor_count": 0,
            "competitors": [],
            "warnings": ["Produto Radar nao informado."],
        }

    warnings: list[str] = []
    report = {}
    try:
        from shopee_core.radar_patterns_service import get_latest_pattern_report

        report = get_latest_pattern_report(own_product_uid) or {}
    except Exception as exc:
        warnings.append(f"Falha ao ler relatorio Radar: {exc}")
        log.warning("[R7.7] Falha ao ler relatorio Radar: %s", exc)

    confidence = str(report.get("confidence") or "insufficient").lower()
    effective_count = int(report.get("effective_competitor_count") or 0)
    report_uid = report.get("report_uid")

    direct_matches: list[dict] = []
    partial_matches: list[dict] = []
    try:
        from shopee_core.radar_relevance_service import get_matches_for_product

        direct_matches = get_matches_for_product(own_product_uid, verdict="competitor_direct")
        if len(direct_matches) < limit:
            partial_matches = get_matches_for_product(own_product_uid, verdict="competitor_partial")
    except Exception as exc:
        warnings.append(f"Falha ao ler concorrentes Radar: {exc}")
        log.warning("[R7.7] Falha ao ler concorrentes Radar: %s", exc)

    competitors: list[dict] = []
    skipped = 0
    for verdict, matches in (
        ("competitor_direct", direct_matches),
        ("competitor_partial", partial_matches),
    ):
        for match in matches:
            item = _radar_match_to_competitor(match, verdict)
            if not item:
                skipped += 1
                continue
            competitors.append(item)
            if len(competitors) >= limit:
                break
        if len(competitors) >= limit:
            break

    if skipped:
        warnings.append(f"{skipped} concorrente(s) Radar ignorado(s) por dados minimos ausentes.")
    if not competitors:
        warnings.append("Radar nao possui concorrentes validos para a Sentinela.")
    if confidence not in RADAR_CONFIDENCES:
        warnings.append(f"Confianca Radar insuficiente para fonte principal: {confidence}.")

    return {
        "ok": bool(competitors) and confidence in RADAR_CONFIDENCES,
        "source": "radar",
        "confidence": confidence,
        "report_uid": report_uid,
        "effective_competitor_count": effective_count,
        "competitors": competitors[:limit],
        "warnings": warnings,
    }


def _empty_radar_status(warnings: list[str] | None = None) -> dict:
    return {
        "has_radar": False,
        "radar_product_uid": None,
        "confidence_level": "insufficient",
        "effective_competitor_count": 0,
        "is_fresh": False,
        "report_uid": None,
        "radar_report_uid": None,
        "warnings": warnings or ["Base Radar ausente para este produto."],
    }


def _load_radar_status(product: dict) -> dict:
    try:
        from shopee_core.audit_market_source_service import get_radar_market_status_for_audit

        return get_radar_market_status_for_audit(product or {})
    except Exception as exc:
        log.warning("[R7.7] Falha ao obter status Radar para Sentinela: %s", exc)
        return _empty_radar_status([f"Falha ao obter status Radar: {exc}"])


def _source_result(
    source: str,
    reason: str,
    competitors: list[dict],
    current_quality: dict,
    radar_status: dict,
    radar_result: dict | None = None,
    warnings: list[str] | None = None,
) -> dict:
    radar_result = radar_result or {}
    return {
        "ok": bool(competitors),
        "source": source,
        "reason": reason,
        "competitors": competitors,
        "current_used": source in {"current", "hybrid"},
        "radar_used": source in {"radar", "hybrid"},
        "confidence": radar_result.get("confidence") or radar_status.get("confidence_level"),
        "report_uid": radar_result.get("report_uid") or radar_status.get("radar_report_uid") or radar_status.get("report_uid"),
        "effective_competitor_count": (
            radar_result.get("effective_competitor_count")
            or radar_status.get("effective_competitor_count")
            or 0
        ),
        "current_quality": current_quality,
        "radar_status": radar_status,
        "warnings": _unique_warnings(warnings or []),
    }


def _unique_warnings(warnings: list[str]) -> list[str]:
    seen = set()
    result = []
    for warning in warnings:
        if not warning or warning in seen:
            continue
        seen.add(warning)
        result.append(warning)
    return result


def choose_sentinel_competitor_source(
    product: dict,
    current_competitors: list[dict] | None = None,
    radar_status: dict | None = None,
    limit: int = 10,
) -> dict:
    """Choose current scraping/mock, Radar, or none for Sentinela competitors."""
    current_quality = _current_quality(current_competitors or [], limit=max(limit, 20))
    current_normalized = normalize_sentinel_competitors(current_competitors or [], limit=limit)
    current_ok = bool(current_quality.get("ok"))

    if not _radar_enabled():
        if current_normalized:
            return _source_result(
                "current",
                "Fonte atual da Sentinela mantida; Radar desativado por feature flag.",
                current_normalized,
                current_quality,
                radar_status or _empty_radar_status(["Radar desativado por SHOPEE_SENTINEL_USE_RADAR."]),
                warnings=current_quality.get("warnings") or [],
            )
        return _source_result(
            "none",
            "Fonte atual sem concorrentes suficientes e Radar desativado por feature flag.",
            [],
            current_quality,
            radar_status or _empty_radar_status(["Radar desativado por SHOPEE_SENTINEL_USE_RADAR."]),
            warnings=current_quality.get("warnings") or ["Nenhuma fonte de concorrentes disponivel."],
        )

    if radar_status is None:
        radar_status = _load_radar_status(product or {})

    radar_has = bool(radar_status.get("has_radar"))
    radar_uid = radar_status.get("radar_product_uid") or radar_status.get("product_uid")
    radar_confidence = str(radar_status.get("confidence_level") or "insufficient").lower()
    radar_fresh = bool(radar_status.get("is_fresh"))
    effective_count = int(radar_status.get("effective_competitor_count") or 0)
    radar_can_fallback = radar_has and radar_confidence in RADAR_CONFIDENCES and effective_count >= MIN_RADAR_EFFECTIVE

    radar_result = None
    if radar_can_fallback and radar_uid:
        radar_result = get_radar_competitors_for_sentinel(str(radar_uid), limit=limit)
        radar_can_fallback = bool(radar_result.get("ok") and radar_result.get("competitors"))

    warnings = _unique_warnings(
        (current_quality.get("warnings") or [])
        + (radar_status.get("warnings") or [])
        + ((radar_result or {}).get("warnings") or [])
    )

    if current_ok and not current_quality.get("is_mock") and not (
        radar_can_fallback
        and radar_fresh
        and radar_confidence == "high"
        and effective_count >= int(current_quality.get("useful_count") or 0) + 3
    ):
        return _source_result(
            "current",
            "Fonte atual da Sentinela retornou concorrentes suficientes.",
            current_normalized,
            current_quality,
            radar_status,
            radar_result,
            warnings,
        )

    if radar_can_fallback:
        radar_competitors = radar_result.get("competitors") or []
        if not radar_fresh:
            warnings.append("Radar usado como fallback, mas a base esta vencida. Recomenda-se renovar.")
        if current_ok and current_quality.get("is_mock"):
            reason = "Usando Radar como base de concorrentes porque a fonte atual esta em provider mock."
        elif current_ok:
            reason = "Usando Radar como base de concorrentes por possuir maior confianca."
        else:
            reason = "Fonte atual de concorrentes indisponivel ou fraca. Usando base local do Radar."
        return _source_result(
            "radar",
            reason,
            radar_competitors,
            current_quality,
            radar_status,
            radar_result,
            warnings,
        )

    if current_ok:
        return _source_result(
            "current",
            "Fonte atual da Sentinela mantida; Radar ausente, fraco ou vencido sem necessidade de fallback.",
            current_normalized,
            current_quality,
            radar_status,
            radar_result,
            warnings,
        )

    if current_normalized:
        return _source_result(
            "current",
            "Fonte atual da Sentinela retornou poucos concorrentes, mas foi mantida porque o Radar nao esta disponivel.",
            current_normalized,
            current_quality,
            radar_status,
            radar_result,
            warnings,
        )

    return _source_result(
        "none",
        "Nao foi possivel obter concorrentes. Crie ou renove a base Radar para este produto.",
        [],
        current_quality,
        radar_status,
        radar_result,
        warnings + ["Nenhuma fonte de concorrentes disponivel para a Sentinela."],
    )
