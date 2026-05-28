"""
shopee_core/audit_market_source_service.py - R7.5A automatic market source selection.

Chooses the best competitor data source for the Audit:
- scraping: real-time Shopee/Mercado Livre data
- radar: local Radar database with pattern reports
- hybrid: Radar evidence plus live scraping
- none: no usable source available
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from math import ceil
from typing import Any

log = logging.getLogger("audit_market_source")


def _empty_radar_status(warnings: list[str] | None = None) -> dict:
    return {
        "has_radar": False,
        "product_uid": None,
        "radar_product_uid": None,
        "confidence_level": "insufficient",
        "confidence_score": None,
        "competitor_count": 0,
        "effective_competitor_count": 0,
        "effective_direct_count": 0,
        "effective_partial_count": 0,
        "direct_count": 0,
        "partial_count": 0,
        "report_uid": None,
        "radar_report_uid": None,
        "is_fresh": False,
        "last_refresh_at": None,
        "last_report_at": None,
        "status": "missing",
        "warnings": warnings or ["Nenhum produto Radar encontrado para este produto."],
    }


def _normalize_tokens(text: str) -> set[str]:
    clean = re.sub(r"[^a-z0-9A-ZÀ-ÿ]+", " ", text or "").strip().lower()
    return {token for token in clean.split() if len(token) > 2}


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


def _is_placeholder_title(title: str) -> bool:
    clean = re.sub(r"\s+", " ", str(title or "")).strip().lower()
    if len(clean) < 4:
        return True
    placeholders = {"produto", "sem titulo", "sem título", "concorrente", "n/a", "none"}
    return clean in placeholders


def _has_identity(row: dict) -> bool:
    return _first_present(
        row,
        "url",
        "canonical_url",
        "permalink",
        "item_id",
        "itemid",
        "shop_id",
        "shopid",
        "id",
    ) is not None


def _unique_warnings(*groups: list[str]) -> list[str]:
    seen = set()
    out = []
    for group in groups:
        for warning in group or []:
            if not warning or warning in seen:
                continue
            seen.add(warning)
            out.append(warning)
    return out


def _report_age_days(report: dict | None) -> int | None:
    if not report:
        return None
    created = report.get("created_at") or report.get("updated_at")
    if not created:
        return None
    try:
        return (datetime.utcnow() - datetime.fromisoformat(str(created))).days
    except Exception:
        return None


def _has_severe_radar_warning(warnings: list[str]) -> bool:
    severe_terms = (
        "off-niche",
        "fora de nicho",
        "feature off",
        "bloqueada",
        "pendente",
        "cobertura de titulo",
        "cobertura de preco",
        "insuficiente",
    )
    text = " ".join(warnings or []).lower()
    return any(term in text for term in severe_terms)


def get_radar_market_status_for_audit(product: dict) -> dict:
    """Look up the best Radar own-product match for the audited product."""
    product_name = (product.get("name") or product.get("title") or "").strip().lower()
    if not product_name:
        return _empty_radar_status(["Produto sem nome - impossivel buscar Radar."])

    try:
        from shopee_core.radar_ui_service import list_radar_products_for_audit
    except Exception:
        return _empty_radar_status(["Banco do Radar indisponivel."])

    radar_products = list_radar_products_for_audit(limit=200)
    tokenized = _normalize_tokens(product_name)
    if not tokenized:
        return _empty_radar_status(["Produto sem termos suficientes para buscar Radar."])

    best = None
    best_score = 0.0
    for radar_product in radar_products:
        radar_title = (radar_product.get("title") or "").strip().lower()
        radar_tokens = _normalize_tokens(radar_title)
        if not radar_tokens:
            continue
        score = len(tokenized & radar_tokens) / max(len(tokenized), len(radar_tokens), 1)
        if score > best_score:
            best_score = score
            best = radar_product

    if best is None or best_score < 0.3:
        return _empty_radar_status([
            f"Nenhum produto Radar corresponde a '{product_name}' (melhor score: {best_score:.2f})."
        ])

    uid = best["product_uid"]
    report = None
    confidence_gate = {}
    refresh = {}

    try:
        from shopee_core.radar_patterns_service import get_latest_pattern_report

        report = get_latest_pattern_report(uid)
    except Exception as exc:
        log.warning("[R7.5A] Falha ao ler relatorio Radar: %s", exc)

    report_uid = (report or {}).get("report_uid")
    try:
        from shopee_core.radar_discovery_service import calculate_radar_market_confidence

        confidence_gate = calculate_radar_market_confidence(uid, report_uid=report_uid)
    except Exception as exc:
        log.warning("[R7.5A] Falha ao calcular confidence gate Radar: %s", exc)

    confidence = (
        confidence_gate.get("level")
        or (report or {}).get("confidence")
        or best.get("confidence")
        or "insufficient"
    )
    direct_count = int((report or {}).get("direct_count") or best.get("direct_count") or 0)
    partial_count = int((report or {}).get("partial_count") or best.get("partial_count") or 0)
    effective_direct = int(
        confidence_gate.get("effective_direct_count")
        or (report or {}).get("effective_direct_count")
        or direct_count
        or 0
    )
    effective_partial = int(
        confidence_gate.get("effective_partial_count")
        or (report or {}).get("effective_partial_count")
        or partial_count
        or 0
    )
    effective_total = int(
        confidence_gate.get("effective_competitor_count")
        or (report or {}).get("effective_competitor_count")
        or (effective_direct + effective_partial)
        or 0
    )
    competitor_count = int((report or {}).get("total_competitors") or direct_count + partial_count)

    refresh_warnings = []
    try:
        from shopee_core.radar_refresh_service import get_radar_refresh_status

        refresh = get_radar_refresh_status(uid)
    except Exception as exc:
        log.warning("[R7.5A] Falha ao ler refresh state Radar: %s", exc)

    if refresh:
        is_fresh = refresh.get("status") == "fresh" and not refresh.get("is_due", True)
        if refresh.get("is_due"):
            refresh_warnings.append("Relatorio Radar vencido ou pendente de renovacao.")
        if refresh.get("status") == "failed_refresh":
            refresh_warnings.append(f"Ultima renovacao falhou: {refresh.get('last_error', 'erro desconhecido')}")
    else:
        age_days = _report_age_days(report)
        is_fresh = age_days is not None and age_days <= 7
        if report and not is_fresh:
            refresh_warnings.append("Relatorio Radar pode estar desatualizado.")

    warnings = []
    if not report:
        warnings.append("Produto Radar ainda nao possui relatorio de padroes.")
    if confidence == "insufficient":
        warnings.append("Confianca insuficiente - poucos concorrentes efetivos.")
    elif confidence == "low":
        warnings.append("Confianca baixa - use com cautela.")
    if not is_fresh:
        warnings.extend(refresh_warnings)
    warnings.extend(confidence_gate.get("warnings") or [])
    warnings.extend((report or {}).get("warnings") or [])

    return {
        "has_radar": True,
        "product_uid": uid,
        "radar_product_uid": uid,
        "confidence_level": confidence,
        "confidence_score": confidence_gate.get("score") or refresh.get("last_confidence_score"),
        "competitor_count": competitor_count,
        "effective_competitor_count": effective_total,
        "effective_direct_count": effective_direct,
        "effective_partial_count": effective_partial,
        "direct_count": direct_count,
        "partial_count": partial_count,
        "report_uid": report_uid,
        "radar_report_uid": report_uid or refresh.get("last_report_uid"),
        "is_fresh": is_fresh,
        "last_refresh_at": refresh.get("last_refresh_at"),
        "last_report_at": (report or {}).get("created_at"),
        "status": refresh.get("status") or ("fresh" if is_fresh else "needs_refresh"),
        "warnings": _unique_warnings(warnings),
    }


def evaluate_scraping_market_quality(scraping_result) -> dict:
    """Evaluate whether scraping produced usable market evidence."""
    default = {
        "ok": False,
        "competitor_count": 0,
        "useful_competitor_count": 0,
        "has_prices": False,
        "has_titles": False,
        "has_identity": False,
        "price_count": 0,
        "title_count": 0,
        "identity_count": 0,
        "quality_score": 0.0,
        "warnings": ["Nenhum concorrente obtido via scraping."],
    }

    if scraping_result is None:
        return default

    import pandas as pd

    if isinstance(scraping_result, pd.DataFrame):
        competitors = scraping_result.to_dict("records") if not scraping_result.empty else []
    elif isinstance(scraping_result, list):
        competitors = scraping_result
    else:
        return default

    if not competitors:
        return default

    total = len(competitors)
    min_majority = max(1, ceil(total * 0.5))
    price_count = 0
    title_count = 0
    identity_count = 0
    useful_count = 0

    for row in competitors:
        price = _parse_float(_first_present(row, "preco", "price", "valor"))
        title = _first_present(row, "titulo", "nome", "name", "title")
        has_price = price is not None and price > 0
        has_title = title is not None and not _is_placeholder_title(str(title))
        has_identity = _has_identity(row)

        if has_price:
            price_count += 1
        if has_title:
            title_count += 1
        if has_identity:
            identity_count += 1
        if has_price and has_title and has_identity:
            useful_count += 1

    has_prices = price_count >= min_majority
    has_titles = title_count >= min_majority
    has_identity = identity_count >= min_majority

    score = 0.0
    score += min(useful_count / 10, 0.35)
    score += 0.2 if has_prices else max(0.0, (price_count / max(total, 1)) * 0.1)
    score += 0.2 if has_titles else max(0.0, (title_count / max(total, 1)) * 0.1)
    score += 0.15 if has_identity else max(0.0, (identity_count / max(total, 1)) * 0.05)
    score += 0.1 if useful_count >= 8 else 0.05 if useful_count >= 5 else 0
    score = min(score, 1.0)

    warnings = []
    if useful_count < 3:
        warnings.append("Scraping sem dados minimos de concorrentes uteis.")
    if total < 5:
        warnings.append(f"Apenas {total} concorrentes retornados pelo scraping.")
    if not has_prices:
        warnings.append("Muitos concorrentes sem preco valido.")
    if not has_titles:
        warnings.append("Muitos concorrentes sem titulo.")
    if not has_identity:
        warnings.append("Muitos concorrentes sem URL ou identificacao.")

    return {
        "ok": useful_count >= 3 and has_prices and has_titles and has_identity and score >= 0.45,
        "competitor_count": total,
        "useful_competitor_count": useful_count,
        "has_prices": has_prices,
        "has_titles": has_titles,
        "has_identity": has_identity,
        "price_count": price_count,
        "title_count": title_count,
        "identity_count": identity_count,
        "quality_score": round(score, 2),
        "warnings": warnings,
    }


def _source_result(
    source: str,
    reason: str,
    radar_status: dict,
    scraping_quality: dict,
    warnings: list[str],
) -> dict:
    return {
        "source": source,
        "reason": reason,
        "market_source": source,
        "market_source_reason": reason,
        "radar_used": source in {"radar", "hybrid"},
        "scraping_used": source in {"scraping", "hybrid"},
        "confidence_level": radar_status.get("confidence_level"),
        "radar_confidence": radar_status.get("confidence_level"),
        "radar_report_uid": radar_status.get("radar_report_uid") or radar_status.get("report_uid"),
        "radar_product_uid": radar_status.get("radar_product_uid") or radar_status.get("product_uid"),
        "scraping_quality": scraping_quality,
        "radar_status": radar_status,
        "warnings": _unique_warnings(warnings),
    }


def choose_audit_market_source(
    product: dict,
    scraping_result=None,
    radar_status: dict | None = None,
) -> dict:
    """Choose the best market source for the audit."""
    if radar_status is None:
        radar_status = get_radar_market_status_for_audit(product)

    scraping = evaluate_scraping_market_quality(scraping_result)
    scraping_ok = scraping.get("ok", False)
    scraping_useful = int(scraping.get("useful_competitor_count", 0) or 0)
    scraping_score = float(scraping.get("quality_score", 0.0) or 0.0)
    scraping_good = scraping_ok and scraping_useful >= 8 and scraping_score >= 0.65

    radar_has = bool(radar_status.get("has_radar"))
    radar_confidence = radar_status.get("confidence_level") or "insufficient"
    radar_fresh = bool(radar_status.get("is_fresh"))
    effective_total = int(
        radar_status.get("effective_competitor_count")
        or radar_status.get("effective_direct_count")
        or radar_status.get("direct_count")
        or 0
    )
    effective_direct = int(radar_status.get("effective_direct_count") or radar_status.get("direct_count") or 0)
    effective_partial = int(radar_status.get("effective_partial_count") or radar_status.get("partial_count") or 0)
    radar_warnings = radar_status.get("warnings") or []
    severe_radar_warning = _has_severe_radar_warning(radar_warnings)

    radar_has_enough = effective_direct >= 8 or (effective_direct >= 5 and effective_partial >= 8)
    radar_can_fallback = radar_has and radar_confidence in {"high", "medium"} and effective_total >= 3
    radar_good_fresh = (
        radar_can_fallback
        and radar_fresh
        and effective_total >= 5
        and not severe_radar_warning
    )
    radar_strong_fresh = radar_good_fresh and radar_confidence == "high" and radar_has_enough

    warnings = _unique_warnings(scraping.get("warnings") or [], radar_warnings)

    if not scraping_ok and not radar_can_fallback:
        return _source_result(
            "none",
            (
                "Nao foi possivel buscar concorrentes em tempo real e este produto "
                "ainda nao possui base Radar suficiente. Construa a base de mercado no Radar de Concorrentes."
            ),
            radar_status,
            scraping,
            warnings + ["Nenhuma fonte de mercado disponivel."],
        )

    if not scraping_ok and radar_can_fallback:
        extra = []
        reason = "Scraping em tempo real indisponivel. Usei a base local do Radar."
        if not radar_fresh:
            reason += " A base esta vencida, entao use com cautela e renove o Radar."
            extra.append("Radar usado como fallback, mas a base esta vencida. Recomenda-se renovar.")
        return _source_result("radar", reason, radar_status, scraping, warnings + extra)

    if scraping_good and radar_has and not radar_fresh:
        return _source_result(
            "scraping",
            "Usei scraping em tempo real porque retornou base suficiente e o Radar esta vencido.",
            radar_status,
            scraping,
            warnings + ["Radar disponivel, mas vencido. Recomenda-se renovar antes de usa-lo como base principal."],
        )

    if scraping_good and not radar_strong_fresh:
        return _source_result(
            "scraping",
            "Usei scraping em tempo real porque retornou base suficiente.",
            radar_status,
            scraping,
            warnings,
        )

    if radar_strong_fresh and scraping_good:
        return _source_result(
            "hybrid",
            "Usei o Radar como base principal por sua base efetiva e renovada, complementada pelo scraping.",
            radar_status,
            scraping,
            warnings,
        )

    if radar_good_fresh:
        return _source_result(
            "radar",
            "Usei o Radar porque ele possui uma base mais robusta e renovada que o scraping atual.",
            radar_status,
            scraping,
            warnings,
        )

    if scraping_ok:
        return _source_result(
            "scraping",
            "Usei scraping em tempo real como base disponivel; o Radar nao esta pronto para uso automatico.",
            radar_status,
            scraping,
            warnings,
        )

    if radar_can_fallback:
        extra = []
        reason = "Usei o Radar como fallback porque o scraping nao retornou base util."
        if not radar_fresh:
            reason += " A base esta vencida, entao recomenda-se renovar."
            extra.append("Radar usado como fallback, mas a base esta vencida. Recomenda-se renovar.")
        return _source_result("radar", reason, radar_status, scraping, warnings + extra)

    return _source_result(
        "none",
        "Nenhuma base de mercado util esta disponivel para esta auditoria.",
        radar_status,
        scraping,
        warnings + ["Construa uma base Radar ou tente novamente o scraping em tempo real."],
    )
