"""
shopee_core/radar_discovery_service.py - R7.3: Automatic competitor discovery.

Discovers competitor product URLs from marketplace search results,
then orchestrates collection, classification and pattern report generation.
"""

from __future__ import annotations

import re
import time
import uuid
from datetime import datetime
from typing import Any

from shopee_core.radar_db import get_connection, init_db
from shopee_core.radar_service import detect_marketplace, normalize_product_url, get_product
from shopee_core.radar_workflow_ui_service import (
    add_competitor_urls_for_product,
    classify_linked_candidates_for_product,
    ensure_collection_jobs_for_linked_candidates,
    run_pattern_analysis_for_product,
    run_linked_collection_for_product,
)
from shopee_core.radar_patterns_service import generate_pattern_report, get_latest_pattern_report


# ── Part 1: Search query generator ───────────────────────────────────────


def generate_competitor_search_queries(own_product: dict) -> list[dict]:
    """Generate ordered search queries from own product title/signals.

    Returns list of {query, reason, priority}.
    """
    title = (own_product.get("title") or "").lower()
    tokens = [t for t in re.findall(r"[a-z0-9]+", title) if len(t) > 2]

    # Product type is almost always the first token
    product_type = tokens[0] if tokens else ""

    # Identify key signal categories from title
    has_infantil = any(t in tokens for t in ["infantil", "crianca"])
    has_escolar = "escolar" in tokens
    has_feminina = any(t in tokens for t in ["feminina", "feminino", "menina", "princesa"])
    has_masculina = any(t in tokens for t in ["masculina", "masculino", "menino"])
    has_rosa = "rosa" in tokens
    has_grande = "grande" in tokens
    has_reforcada = "reforcada" in tokens

    # Extract style/themes
    themes = [t for t in tokens if t in (
        "princesa", "princesas", "unicornio", "unicornios", "kawaii",
        "hello", "kitty", "dinossauro", "dinossauros", "gatinho",
        "cachorrinho", "ursinho", "sereia", "patrulha", "canina",
        "carros", "homem", "aranha", "batman", "super", "herois",
    )]

    queries: list[dict] = []
    added_set: set[str] = set()

    def add(q: str, reason: str, priority: int):
        if q in added_set:
            return
        added_set.add(q)
        queries.append({"query": q, "reason": reason, "priority": priority})

    # Priority 1: core product type + audience + use case
    core_a = product_type
    if has_infantil:
        core_a += " infantil"
    if has_escolar:
        core_a += " escolar"
    if has_feminina:
        core_a += f" {'feminina' if 'feminina' not in core_a else ''}"
    add(core_a.strip(), "Produto + publico + uso principal", 1)

    # Priority 1b: add rosa if present
    if has_rosa:
        add(f"{product_type} {'infantil' if has_infantil else ''} rosa {'escolar' if has_escolar else ''}", "Cor predominante", 1)

    # Priority 2: with theme/style
    for theme in themes[:2]:
        add(f"{product_type} infantil {theme} escolar", f"Tema: {theme}", 2)

    # Priority 2b: feminina/menina variants
    if has_feminina:
        add(f"{product_type} escolar menina {'princesa' if 'princesa' in tokens else ''}", "Publico feminino escolar", 2)

    # Priority 3: practical features
    if has_reforcada:
        add(f"{product_type} infantil reforcada escolar", "Feature: reforcada", 3)

    # Priority 3b: combinations without one signal
    if has_infantil and has_escolar and has_feminina:
        alt = f"{product_type} {'infantil' if has_infantil else ''} escolar feminina"
        if alt not in added_set:
            add(alt, "Alternativa feminina escolar", 3)

    # Priority 4: theme variants (lower priority)
    extra_themes = [t for t in ["unicornio", "kawaii", "hello kitty", "dinossauro", "princesa"] if t not in themes[:2]]
    for theme in extra_themes[:2]:
        add(f"{product_type} infantil {theme} {'escolar' if has_escolar else ''}", f"Tema alternativo: {theme}", 4)

    return queries


# ── Part 2: ML search helper ──────────────────────────────────────────────


_BUILD_QUERY_CACHE: dict[str, str] = {}


def _build_ml_search_url(query: str) -> str:
    """Build a Mercado Livre search URL from a query string."""
    # Cache normalization for tests
    key = query.strip().lower()
    if key in _BUILD_QUERY_CACHE:
        return _BUILD_QUERY_CACHE[key]
    encoded = re.sub(r"\s+", "-", key.strip())
    url = f"https://lista.mercadolivre.com.br/{encoded}"
    _BUILD_QUERY_CACHE[key] = url
    return url


_ML_PRODUCT_URL_RE = re.compile(
    r"(?:https?://)?(?:[^/]+\.)?mercadolivre\.com\.br"
    r"(?:/[^/]+)?(?:/p/MLB\d+|/up/MLBU\d+|/MLB-\d+)"
)


def _is_valid_ml_product_url(url: str) -> bool:
    """Check if a URL is a valid Mercado Livre product URL (not search, not login, etc.)."""
    if not url:
        return False
    stripped = url.strip().split("?")[0].split("#")[0]
    return bool(_ML_PRODUCT_URL_RE.search(stripped))


def _normalize_discovered_url(raw_url: str) -> str | None:
    """Normalize a discovered URL, return canonical form or None if invalid."""
    try:
        canonical = normalize_product_url(raw_url)
    except Exception:
        return None
    if not canonical or detect_marketplace(canonical) not in ("mercadolivre",):
        return None
    # Reject fake/test URLs
    if re.search(r"shopee\.com\.br/product/\d{1,2}/\d{1,2}$", canonical, re.I):
        return None
    return canonical


_EXTRACT_URL_JS = """
() => {
    const results = [];
    const seen = new Set();
    // Collect all hrefs from <a> tags
    document.querySelectorAll('a[href]').forEach(a => {
        const href = a.href;
        if (!href || seen.has(href)) return;
        seen.add(href);
        results.push(href);
    });
    // Also check data attributes used by ML
    document.querySelectorAll('[data-product-id]').forEach(el => {
        const pid = el.getAttribute('data-product-id');
        if (pid) {
            const url = 'https://produto.mercadolivre.com.br/MLB-' + pid;
            if (!seen.has(url)) {
                seen.add(url);
                results.push(url);
            }
        }
    });
    return results;
}
"""


def _extract_ml_product_urls_from_page(page) -> list[str]:
    """Extract candidate product URLs from a loaded ML search page."""
    try:
        page.wait_for_timeout(500)
        urls = page.evaluate(_EXTRACT_URL_JS)
    except Exception:
        return []

    valid: list[str] = []
    for url in urls:
        norm = _normalize_discovered_url(url)
        if norm:
            valid.append(norm)
    return valid


# ── Part 3: Discover marketplace candidate URLs ──────────────────────────


def discover_marketplace_candidate_urls(
    own_product_uid: str,
    marketplace: str = "mercadolivre",
    max_queries: int = 6,
    max_urls_per_query: int = 10,
    browser_mode: str = "cdp",
    cdp_url: str = "http://127.0.0.1:9222",
) -> dict:
    """Search marketplace and collect candidate URLs.

    Opens ML search pages in CDP Chrome, extracts product card URLs,
    normalizes and inserts them as linked candidates.
    """
    own_product = get_product(own_product_uid)
    if not own_product:
        return {"ok": False, "error": "Produto proprio nao encontrado.", "urls_found": 0, "urls_inserted": 0}

    if marketplace != "mercadolivre":
        return {"ok": False, "error": f"Marketplace '{marketplace}' nao suportado para descoberta automatica.",
                "urls_found": 0, "urls_inserted": 0}

    queries = generate_competitor_search_queries(own_product)
    if not queries:
        return {"ok": False, "error": "Nenhuma busca gerada a partir do titulo do produto.",
                "urls_found": 0, "urls_inserted": 0}

    queries = queries[:max_queries]
    all_norm_urls: list[str] = []
    errors: list[str] = []

    # Open CDP browser once, reuse for all queries
    from playwright.sync_api import sync_playwright
    from shopee_core.radar_browser_service import connect_to_cdp_browser
    from shopee_core.radar_collector import _dismiss_common_overlays

    try:
        with sync_playwright() as pw:
            browser, context, page = connect_to_cdp_browser(pw, cdp_url=cdp_url)

            for q in queries:
                search_url = _build_ml_search_url(q["query"])
                try:
                    page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(1.5)
                    _dismiss_common_overlays(page, url=search_url, stage="ml_search")
                    page.wait_for_timeout(800)

                    urls = _extract_ml_product_urls_from_page(page)
                    # Limit per query
                    urls = urls[:max_urls_per_query]
                    all_norm_urls.extend(urls)
                except Exception as e:
                    errors.append(f"Busca '{q['query']}': {e}")

            # Close context/browser if we opened it
            try:
                context.close()
            except Exception:
                pass
    except Exception as e:
        errors.append(f"Erro de conexao CDP: {e}")

    # Deduplicate found URLs
    seen_urls: set[str] = set()
    unique_urls: list[str] = []
    for url in all_norm_urls:
        if url not in seen_urls:
            seen_urls.add(url)
            unique_urls.append(url)

    # Insert via existing workflow function
    urls_text = "\n".join(unique_urls)
    insert_result = add_competitor_urls_for_product(own_product_uid, urls_text)

    return {
        "ok": True,
        "queries_used": len(queries),
        "urls_found": len(all_norm_urls),
        "urls_unique": len(unique_urls),
        "urls_inserted": insert_result.get("created", 0),
        "urls_existing": insert_result.get("duplicates", 0),
        "invalid": insert_result.get("invalid", 0),
        "errors": errors,
    }


# ── Part 4: Radar confidence score ───────────────────────────────────────


def calculate_radar_market_confidence(
    own_product_uid: str,
    report_uid: str | None = None,
) -> dict:
    """Calculate a numeric confidence score for the radar market analysis.

    Critérios:
    - direct_count (+10 each, max 50)
    - partial_count (+3 each, max 15)
    - failed_coleta (-5 each, floor 0)
    - price_dispersion (-15 if high CV)
    - freshness (+5 if report < 1 day, +2 if < 7 days)
    - evidence_count (+1 each, max 10)
    - report_exists (+10)
    """
    init_db()

    report = None
    if report_uid:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM radar_pattern_reports WHERE report_uid = ?",
                (report_uid,),
            ).fetchone()
            if row:
                from shopee_core.radar_patterns_service import _decode_report_row
                report = _decode_report_row(dict(row))

    if not report:
        report = get_latest_pattern_report(own_product_uid)

    if not report:
        return {"level": "insufficient", "score": 0, "warnings": ["Nenhum relatorio encontrado."]}

    direct_count = report.get("direct_count", 0)
    partial_count = report.get("partial_count", 0)
    evidence_list = report.get("evidence_list", []) or report.get("raw", {}).get("evidence_list", [])

    # Count failed collections
    failed_count = 0
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM radar_collection_jobs j "
            "JOIN radar_candidate_links l ON l.candidate_product_uid = j.product_uid "
            "WHERE l.own_product_uid = ? AND j.status = 'failed'",
            (own_product_uid,),
        ).fetchone()
        if row:
            failed_count = row["c"]

    # Freshness
    freshness_days = 999
    created_at = report.get("created_at") or report.get("updated_at", "")
    if created_at:
        try:
            created_dt = datetime.fromisoformat(created_at)
            freshness_days = (datetime.utcnow() - created_dt).days
        except Exception:
            pass

    # Build score
    score = 0
    score += min(direct_count * 10, 50)
    score += min(partial_count * 3, 15)
    score = max(0, score - failed_count * 5)
    score += 5 if freshness_days < 1 else (2 if freshness_days < 7 else 0)
    score += min(len(evidence_list), 10)
    score += 10  # report_exists

    # Price dispersion penalty
    price_analysis = report.get("raw", {}).get("analyses", {}).get("price", {})
    if price_analysis.get("dispersion_warning"):
        score = max(0, score - 15)

    # Determine level
    level = "insufficient"
    if score >= 80:
        level = "high"
    elif score >= 55:
        level = "medium"
    elif score >= 35:
        level = "low"

    warnings = []
    if direct_count < 8:
        warnings.append(f"Poucos concorrentes diretos ({direct_count}); ideal > 8.")
    if failed_count > 3:
        warnings.append(f"{failed_count} coletas com falha.")
    if freshness_days > 7:
        warnings.append("Relatorio desatualizado (mais de 7 dias).")
    if price_analysis.get("dispersion_warning"):
        warnings.append("Alta dispersao de precos.")

    return {
        "level": level,
        "score": score,
        "direct_count": direct_count,
        "partial_count": partial_count,
        "failed_count": failed_count,
        "freshness_days": freshness_days,
        "warnings": warnings,
    }


# ── Part 5: Full automatic cycle ──────────────────────────────────────────


def run_automatic_radar_cycle(
    own_product_uid: str,
    marketplace: str = "mercadolivre",
    target_confidence: str = "high",
    max_queries: int = 6,
    max_urls_per_query: int = 10,
    max_collect: int = 15,
    candidate_scope: str = "direct_plus_partial",
    browser_mode: str = "cdp",
    cdp_url: str = "http://127.0.0.1:9222",
    progress_callback=None,
) -> dict:
    """Run the full automatic radar cycle: discover -> collect -> classify -> report.

    Steps:
    1. Ensure Chrome is ready
    2. Generate search queries from product title
    3. Discover candidate URLs on marketplace
    4. Ensure collection jobs for new candidates
    5. Collect pending candidates (up to max_collect)
    6. Reclassify with force
    7. Generate pattern report
    8. Calculate confidence
    """
    result: dict[str, Any] = {
        "ok": False,
        "step": "",
        "discovery": None,
        "collection": None,
        "classification": None,
        "report": None,
        "confidence": None,
        "errors": [],
    }

    def _progress(stage: str, message: str):
        if progress_callback:
            try:
                progress_callback({"stage": stage, "message": message})
            except Exception:
                pass

    # Step 0: Ensure Chrome ready
    _progress("chrome_check", "Procurando Chrome/Edge no sistema...")
    from shopee_core.radar_cdp_service import ensure_radar_chrome_ready
    chrome = ensure_radar_chrome_ready(cdp_url)
    if not chrome.get("ok"):
        result["step"] = "chrome"
        result["errors"].append(chrome.get("message", "Falha ao abrir Chrome do Radar."))
        result["diagnostics"] = chrome.get("diagnostics", {})
        return result
    _progress("chrome_validate", "Chrome CDP pronto e validado.")

    # Step 1: Generate queries
    _progress("queries", "Gerando buscas...")
    own_product = get_product(own_product_uid)
    if not own_product:
        result["step"] = "queries"
        result["errors"].append("Produto proprio nao encontrado.")
        return result
    queries = generate_competitor_search_queries(own_product)
    result["queries_generated"] = len(queries)

    # Step 2: Discover
    _progress("discover", "Buscando URLs no Mercado Livre...")
    discovery = discover_marketplace_candidate_urls(
        own_product_uid=own_product_uid,
        marketplace=marketplace,
        max_queries=max_queries,
        max_urls_per_query=max_urls_per_query,
        browser_mode=browser_mode,
        cdp_url=cdp_url,
    )
    result["discovery"] = discovery
    if not discovery.get("ok"):
        result["step"] = "discover"
        result["errors"].append(discovery.get("error", "Falha na descoberta de URLs."))
        return result

    # Step 3: Ensure collection jobs
    _progress("jobs", "Preparando coletas...")
    ensure_collection_jobs_for_linked_candidates(own_product_uid)

    # Step 4: Collect
    _progress("collect", f"Coletando ate {max_collect} candidatos...")
    collection = run_linked_collection_for_product(
        own_product_uid=own_product_uid,
        limit=max_collect,
        save_assets=False,
        browser_mode=browser_mode,
        cdp_url=cdp_url,
        collect_image_urls=True,
    )
    result["collection"] = collection

    # Step 5: Classify with force
    _progress("classify", "Classificando concorrentes...")
    try:
        classification = classify_linked_candidates_for_product(
            own_product_uid, force_reclassify=True
        )
        result["classification"] = classification
    except Exception as e:
        result["step"] = "classify"
        result["errors"].append(f"Falha na classificacao: {e}")
        return result

    # Step 6: Generate report
    _progress("report", "Gerando relatorio de padroes...")
    try:
        report = generate_pattern_report(
            own_product_uid, candidate_scope=candidate_scope
        )
        result["report"] = report
    except Exception as e:
        result["step"] = "report"
        result["errors"].append(f"Falha ao gerar relatorio: {e}")
        return result

    # Step 7: Calculate confidence
    _progress("confidence", "Calculando confianca...")
    report_uid = report.get("report_uid") if report else None
    confidence = calculate_radar_market_confidence(
        own_product_uid, report_uid=report_uid
    )
    result["confidence"] = confidence

    result["ok"] = True
    result["step"] = "done"

    # Check if target confidence reached
    if confidence.get("level") == target_confidence or target_confidence == "high":
        result["target_reached"] = confidence.get("level") == target_confidence
    else:
        result["target_reached"] = False

    return result
