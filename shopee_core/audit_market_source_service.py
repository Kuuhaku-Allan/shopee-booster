"""
shopee_core/audit_market_source_service.py — R7.5: Automatic market source selection.

Chooses the best competitor data source for the Audit:
- scraping: real-time Shopee/Meli scraping
- radar: local Radar database with pattern reports
- none: no source available
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger("audit_market_source")


def get_radar_market_status_for_audit(product: dict) -> dict:
    """Look up the best Radar own-product match for the audited product.

    Returns:
        has_radar, product_uid, confidence_level, confidence_score,
        competitor_count, direct_count, partial_count, report_uid,
        is_fresh, last_refresh_at, warnings
    """
    default = {
        "has_radar": False,
        "product_uid": None,
        "confidence_level": None,
        "confidence_score": None,
        "competitor_count": 0,
        "direct_count": 0,
        "partial_count": 0,
        "report_uid": None,
        "is_fresh": False,
        "last_refresh_at": None,
        "warnings": ["Nenhum produto Radar encontrado para este produto."],
    }

    product_name = (product.get("name") or product.get("title") or "").strip().lower()
    if not product_name:
        return {**default, "warnings": ["Produto sem nome — impossível buscar Radar."]}

    try:
        from shopee_core.radar_ui_service import list_radar_products_for_audit
    except Exception:
        return {**default, "warnings": ["Radar database not available."]}

    radar_products = list_radar_products_for_audit(limit=200)

    # Score each Radar product by title similarity
    tokenized = set(product_name.split())
    best = None
    best_score = 0

    for rp in radar_products:
        rp_title = (rp.get("title") or "").strip().lower()
        if not rp_title:
            continue
        rp_tokens = set(rp_title.split())
        if not rp_tokens:
            continue
        overlap = len(tokenized & rp_tokens)
        score = overlap / max(len(tokenized), len(rp_tokens))
        if score > best_score:
            best_score = score
            best = rp

    if best_score < 0.3 or best is None:
        return {**default, "warnings": [f"Nenhum produto Radar corresponde a '{product_name}' (melhor score: {best_score:.2f})."]}

    uid = best["product_uid"]
    confidence = best.get("confidence")
    direct_count = best.get("direct_count", 0)

    # Also check refresh status
    refresh_warnings = []
    try:
        from shopee_core.radar_refresh_service import get_radar_refresh_status
        refresh = get_radar_refresh_status(uid)
        is_fresh = refresh.get("status") == "fresh" and not refresh.get("is_due", True)
        if refresh.get("is_due"):
            refresh_warnings.append("Relatório Radar pode estar desatualizado (última renovação há mais de 7 dias).")
        if refresh.get("status") == "failed_refresh":
            refresh_warnings.append(f"Última renovação falhou: {refresh.get('last_error', 'erro desconhecido')}")
    except Exception:
        is_fresh = False
        refresh_warnings = []

    warnings = []
    if confidence == "insufficient":
        warnings.append("Confiança insuficiente — poucos concorrentes diretos.")
    elif confidence == "low":
        warnings.append("Confiança baixa — use com cautela.")
    if not is_fresh:
        warnings.extend(refresh_warnings)

    return {
        "has_radar": True,
        "product_uid": uid,
        "confidence_level": confidence,
        "direct_count": direct_count,
        "is_fresh": is_fresh,
        "warnings": warnings,
    }


def evaluate_scraping_market_quality(scraping_result) -> dict:
    """Evaluate how good the scraping result is.

    Args:
        scraping_result: DataFrame or list of competitor dicts.

    Returns:
        ok, competitor_count, has_prices, has_titles,
        price_count, title_count, quality_score, warnings
    """
    default = {
        "ok": False,
        "competitor_count": 0,
        "has_prices": False,
        "has_titles": False,
        "price_count": 0,
        "title_count": 0,
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

    # Count valid prices and titles
    price_count = 0
    title_count = 0
    for c in competitors:
        price = c.get("preco") or c.get("price")
        title = c.get("titulo") or c.get("nome") or c.get("title")
        if price is not None and (isinstance(price, (int, float)) and price > 0):
            price_count += 1
        if title and len(str(title).strip()) > 3:
            title_count += 1

    has_prices = price_count >= total * 0.5
    has_titles = title_count >= total * 0.5

    # Quality score: 0-1
    score = 0.0
    score += min(total / 15, 0.3)
    score += 0.25 if has_prices else 0
    score += 0.25 if has_titles else 0
    score += 0.2 if total >= 8 else 0.1 if total >= 5 else 0
    score = min(score, 1.0)

    warnings = []
    if total < 5:
        warnings.append(f"Apenas {total} concorrentes — amostra pequena.")
    if not has_prices:
        warnings.append("Muitos concorrentes sem preço válido.")
    if not has_titles:
        warnings.append("Muitos concorrentes sem título.")

    return {
        "ok": total >= 3,
        "competitor_count": total,
        "has_prices": has_prices,
        "has_titles": has_titles,
        "price_count": price_count,
        "title_count": title_count,
        "quality_score": round(score, 2),
        "warnings": warnings,
    }


def choose_audit_market_source(
    product: dict,
    scraping_result=None,
    radar_status: dict | None = None,
) -> dict:
    """Choose the best market source for the audit.

    Decision rules:
    - Radar if: confidence=high, direct_count>=8, is_fresh OR scraping is poor
    - Radar if: confidence in (high,medium), scraping has <5 valid competitors
    - Scraping if: scraping has 8+ valid competitors AND radar is None/insufficient/stale
    - Scraping if: scraping quality >= 0.6 AND radar is None
    - None if: scraping failed AND radar is None/insufficient
    - Hybrid if: both are good, prefer radar with scraping enrichment

    Returns:
        source: "radar" | "scraping" | "hybrid" | "none"
        reason: human-readable explanation
        radar_used: bool
        scraping_used: bool
        confidence_level: str | None
        warnings: list[str]
    """
    if radar_status is None:
        radar_status = get_radar_market_status_for_audit(product)

    scraping = evaluate_scraping_market_quality(scraping_result)

    scraping_ok = scraping.get("ok", False)
    scraping_count = scraping.get("competitor_count", 0)
    scraping_score = scraping.get("quality_score", 0.0)
    scraping_warnings = scraping.get("warnings", [])

    radar_ok = radar_status.get("has_radar", False)
    radar_confidence = radar_status.get("confidence_level")
    radar_count = radar_status.get("direct_count", 0)
    radar_fresh = radar_status.get("is_fresh", False)
    radar_warnings = radar_status.get("warnings", [])

    warnings = list(scraping_warnings)

    # ── Case D: scraping failed + no radar → none ──────────────
    if not scraping_ok and not radar_ok:
        return {
            "source": "none",
            "reason": (
                "Não foi possível buscar concorrentes em tempo real "
                "e este produto ainda não possui base Radar. "
                "Vá até a seção Radar Assistido para construir a base de mercado."
            ),
            "radar_used": False,
            "scraping_used": False,
            "confidence_level": radar_confidence,
            "warnings": warnings + radar_warnings + ["Nenhuma fonte de mercado disponível."],
        }

    # ── Case B: scraping failed + radar exists → radar ─────────
    if not scraping_ok and radar_ok:
        return {
            "source": "radar",
            "reason": "Scraping em tempo real indisponível. Usei a base local do Radar.",
            "radar_used": True,
            "scraping_used": False,
            "confidence_level": radar_confidence,
            "warnings": warnings + radar_warnings,
        }

    # ── Case A: scraping works + no radar → scraping ───────────
    if scraping_ok and not radar_ok:
        return {
            "source": "scraping",
            "reason": "Base usada: scraping em tempo real.",
            "radar_used": False,
            "scraping_used": True,
            "confidence_level": None,
            "warnings": warnings,
        }

    # ── Case C: both exist → compare quality ───────────────────
    # Radar is better when: high confidence + fresh + good count
    radar_good = (
        radar_confidence in ("high", "medium")
        and radar_count >= 5
    )

    # Scraping is better when: >=8 competitors with prices
    scraping_good = (
        scraping_count >= 8
        and scraping_score >= 0.5
    )

    # If scraping has very few, use radar
    if scraping_count < 5 and radar_good:
        return {
            "source": "radar",
            "reason": (
                f"Usei o Radar como base principal "
                f"(scraping retornou apenas {scraping_count} concorrentes)."
            ),
            "radar_used": True,
            "scraping_used": False,
            "confidence_level": radar_confidence,
            "warnings": warnings + radar_warnings,
        }

    # If both are good, prefer radar as it's more structured
    if radar_good and scraping_good:
        return {
            "source": "hybrid",
            "reason": (
                "Usei o Radar como base principal por sua base estruturada, "
                "complementada com dados de scraping em tempo real."
            ),
            "radar_used": True,
            "scraping_used": True,
            "confidence_level": radar_confidence,
            "warnings": warnings + radar_warnings,
        }

    # Radar is strong enough → use it
    if radar_good:
        return {
            "source": "radar",
            "reason": "Usei o Radar porque ele possui uma base mais robusta e renovada.",
            "radar_used": True,
            "scraping_used": False,
            "confidence_level": radar_confidence,
            "warnings": warnings + radar_warnings,
        }

    # Scraping is decent → use it
    if scraping_good:
        return {
            "source": "scraping",
            "reason": "Usei scraping em tempo real porque retornou base suficiente.",
            "radar_used": False,
            "scraping_used": True,
            "confidence_level": None,
            "warnings": warnings,
        }

    # Fallback: whatever is available
    if radar_ok:
        return {
            "source": "radar",
            "reason": "Usei o Radar como base disponível (scraping insuficiente).",
            "radar_used": True,
            "scraping_used": False,
            "confidence_level": radar_confidence,
            "warnings": warnings + radar_warnings,
        }

    return {
        "source": "scraping",
        "reason": "Usei scraping em tempo real como base disponível.",
        "radar_used": False,
        "scraping_used": True,
        "confidence_level": None,
        "warnings": warnings + ["Base de Radar não disponível para este produto."],
    }
