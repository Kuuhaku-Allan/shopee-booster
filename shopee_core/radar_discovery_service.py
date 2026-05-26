"""
shopee_core/radar_discovery_service.py - R7.3: Automatic competitor discovery.

Discovers competitor product URLs from marketplace search results,
then orchestrates collection, classification and pattern report generation.
"""

from __future__ import annotations

import re
import json
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from shopee_core.radar_db import get_connection, init_db
from shopee_core.radar_service import detect_marketplace, normalize_product_url, get_product
from shopee_core.radar_workflow_ui_service import (
    add_competitor_urls_for_product,
    classify_linked_candidates_for_product,
    ensure_collection_jobs_for_linked_candidates,
    get_competitor_table_for_product,
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

    # Infantil/feminina com temas como princesa costuma puxar concorrencia escolar.
    # Sem esse reforco, ML retorna nichos fracos como natacao/esporte.
    if product_type == "mochila" and has_infantil and (has_feminina or themes):
        has_escolar = True

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
    if not _is_valid_ml_product_url(canonical):
        return None
    # Reject fake/test URLs
    if re.search(r"shopee\.com\.br/product/\d{1,2}/\d{1,2}$", canonical, re.I):
        return None
    return canonical


_EXTRACT_URL_JS = """
() => {
    const results = [];
    const seen = new Set();
    const push = (href) => {
        if (!href || seen.has(href)) return;
        seen.add(href);
        results.push(href);
    };
    // Collect all hrefs from <a> tags
    document.querySelectorAll('a[href]').forEach(a => {
        push(a.href);
    });
    // Also check data attributes used by ML
    document.querySelectorAll('[data-product-id]').forEach(el => {
        const pid = el.getAttribute('data-product-id');
        if (pid) {
            const url = 'https://produto.mercadolivre.com.br/MLB-' + pid;
            push(url);
        }
    });
    // Some ML result links live inside hydrated JSON rather than plain anchors.
    const html = document.documentElement ? document.documentElement.innerHTML : '';
    const matches = html.match(/https?:\\/\\/[^"'<>\\s]+mercadolivre\\.com\\.br\\/[^"'<>\\s]+/g) || [];
    matches.forEach(push);
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
    seen_norm: set[str] = set()
    for url in urls:
        norm = _normalize_discovered_url(url)
        if norm and norm not in seen_norm:
            seen_norm.add(norm)
            valid.append(norm)
    return valid


# ── Part 3: Discover marketplace candidate URLs ──────────────────────────


def _discover_marketplace_candidate_urls_direct(
    own_product_uid: str,
    marketplace: str = "mercadolivre",
    max_queries: int = 6,
    max_urls_per_query: int = 10,
    max_unique_urls: int | None = None,
    browser_mode: str = "cdp",
    cdp_url: str = "http://127.0.0.1:9222",
    progress_callback=None,
) -> dict:
    """Search marketplace and collect candidate URLs in the current process.

    Opens ML search pages in CDP Chrome, extracts product card URLs,
    normalizes and inserts them as linked candidates.
    """
    def _progress(message: str):
        if progress_callback:
            try:
                progress_callback({"stage": "discover", "message": message})
            except Exception:
                pass

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
                    _progress(f"Buscando no Mercado Livre: {q['query']}")
                    print(f"[R7.3] SEARCH query={q['query']} url={search_url}", flush=True)
                    page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(1.5)
                    _dismiss_common_overlays(page, url=search_url, stage="ml_search")
                    page.wait_for_timeout(800)

                    urls = _extract_ml_product_urls_from_page(page)
                    # Limit per query
                    urls = urls[:max_urls_per_query]
                    print(f"[R7.3] FOUND query={q['query']} urls={len(urls)}", flush=True)
                    _progress(f"{len(urls)} URL(s) de produto encontradas para: {q['query']}")
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

    urls_discovered_unique = len(unique_urls)
    urls_limited = 0
    if max_unique_urls is not None:
        max_unique_urls = max(0, int(max_unique_urls))
        if len(unique_urls) > max_unique_urls:
            urls_limited = len(unique_urls) - max_unique_urls
            unique_urls = unique_urls[:max_unique_urls]

    # Insert via existing workflow function
    urls_text = "\n".join(unique_urls)
    insert_result = add_competitor_urls_for_product(own_product_uid, urls_text) if unique_urls else {
        "created": 0,
        "duplicates": 0,
        "invalid": 0,
    }

    if not unique_urls and not all_norm_urls:
        return {
            "ok": False,
            "error": "; ".join(errors) if errors else "Nenhuma URL de produto encontrada nas buscas do Mercado Livre.",
            "queries_used": len(queries),
            "urls_found": len(all_norm_urls),
            "urls_unique": len(unique_urls),
            "urls_discovered_unique": urls_discovered_unique,
            "urls_limited": urls_limited,
            "urls_inserted": 0,
            "urls_existing": 0,
            "invalid": 0,
            "errors": errors,
        }

    return {
        "ok": True,
        "queries_used": len(queries),
        "urls_found": len(all_norm_urls),
        "urls_unique": len(unique_urls),
        "urls_discovered_unique": urls_discovered_unique,
        "urls_limited": urls_limited,
        "urls_inserted": insert_result.get("created", 0),
        "urls_existing": insert_result.get("duplicates", 0),
        "invalid": insert_result.get("invalid", 0),
        "errors": errors,
    }


def discover_marketplace_candidate_urls(
    own_product_uid: str,
    marketplace: str = "mercadolivre",
    max_queries: int = 6,
    max_urls_per_query: int = 10,
    max_unique_urls: int | None = None,
    browser_mode: str = "cdp",
    cdp_url: str = "http://127.0.0.1:9222",
    progress_callback=None,
    use_subprocess: bool | None = None,
) -> dict:
    """Search marketplace and collect candidate URLs.

    In Streamlit on Windows, Playwright's sync driver can fail inside the app
    event loop. Production runs the discovery in a subprocess, mirroring the
    existing linked-collection worker.
    """
    is_testing = "pytest" in sys.modules or "unittest" in sys.modules
    if use_subprocess is False or is_testing:
        return _discover_marketplace_candidate_urls_direct(
            own_product_uid=own_product_uid,
            marketplace=marketplace,
            max_queries=max_queries,
            max_urls_per_query=max_urls_per_query,
            max_unique_urls=max_unique_urls,
            browser_mode=browser_mode,
            cdp_url=cdp_url,
            progress_callback=progress_callback,
        )

    worker_path = Path(__file__).resolve().parent.parent / "scripts" / "radar_discover_worker.py"
    cmd = [
        sys.executable,
        "-u",
        str(worker_path),
        own_product_uid,
        marketplace,
        str(max_queries),
        str(max_urls_per_query),
        str(max_unique_urls) if max_unique_urls is not None else "None",
        browser_mode,
        cdp_url if cdp_url is not None else "None",
    ]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )

        stdout_lines: list[str] = []
        final_json_str = None

        for line in iter(process.stdout.readline, ""):
            line_str = line.strip()
            if not line_str:
                continue
            stdout_lines.append(line_str)

            if line_str.startswith("[R7.3]") and progress_callback:
                try:
                    progress_callback({
                        "stage": "discover",
                        "message": line_str.replace("[R7.3]", "").strip(),
                    })
                except Exception:
                    pass

            if line_str.startswith("{") and line_str.endswith("}"):
                final_json_str = line_str

        process.stdout.close()
        returncode = process.wait()

        if final_json_str:
            try:
                parsed = json.loads(final_json_str)
                if returncode != 0 and "worker_returncode" not in parsed:
                    parsed["worker_returncode"] = returncode
                return parsed
            except Exception as e:
                return {
                    "ok": False,
                    "error": f"Erro decodificando retorno JSON da descoberta: {e}",
                    "urls_found": 0,
                    "urls_inserted": 0,
                    "errors": [final_json_str],
                }

        err_msg = f"Erro executando subprocesso de descoberta (code {returncode})"
        if stdout_lines:
            err_msg += f". Ultimas linhas: {stdout_lines[-5:]}"
        return {
            "ok": False,
            "error": err_msg,
            "urls_found": 0,
            "urls_inserted": 0,
            "errors": stdout_lines[-20:],
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"Erro disparando subprocesso de descoberta: {e}",
            "urls_found": 0,
            "urls_inserted": 0,
            "errors": [str(e)],
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
    counts = _get_auto_cycle_counts(own_product_uid)

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
        warnings = ["Nenhum relatorio encontrado."]
        if counts["pending"]:
            warnings.append(f"Ainda ha {counts['pending']} candidato(s) pendente(s) de coleta.")
        return {
            "level": "insufficient",
            "score": 0,
            "pending_count": counts["pending"],
            "failed_count": counts["failed"],
            "title_coverage": counts["title_coverage"],
            "price_coverage": counts["price_coverage"],
            "warnings": warnings,
        }

    raw_report = report.get("raw") or {}
    direct_count = max(int(report.get("direct_count", 0) or 0), counts["direct"])
    partial_count = max(int(report.get("partial_count", 0) or 0), counts["partial"])
    effective_direct_value = report.get("effective_direct_count")
    if effective_direct_value is None:
        effective_direct_value = raw_report.get("effective_direct_count")
    if effective_direct_value is None:
        effective_direct_value = direct_count
    effective_direct_count = int(effective_direct_value)

    effective_partial_value = report.get("effective_partial_count")
    if effective_partial_value is None:
        effective_partial_value = raw_report.get("effective_partial_count")
    if effective_partial_value is None:
        effective_partial_value = partial_count
    effective_partial_count = int(effective_partial_value)

    effective_total_value = report.get("effective_competitor_count")
    if effective_total_value is None:
        effective_total_value = raw_report.get("effective_competitor_count")
    if effective_total_value is None:
        effective_total_value = effective_direct_count + effective_partial_count
    effective_competitor_count = int(effective_total_value)

    variants_grouped_value = report.get("variants_grouped")
    if variants_grouped_value is None:
        variants_grouped_value = raw_report.get("variants_grouped")
    variants_grouped = int(variants_grouped_value or 0)
    evidence_list = report.get("evidence_list", []) or report.get("raw", {}).get("evidence_list", [])
    strategy_features = report.get("strategy_features") or raw_report.get("strategy_features") or {}
    recommended_features = set(strategy_features.get("recommended") or [])
    off_niche_features = set(strategy_features.get("off_niche") or [])
    quality_gate_off_niche = {
        "notebook",
        "natacao",
        "natação",
        "praia",
        "esportiva",
        "executivo",
        "corporativo",
        "urbano adulto",
        "trekking",
        "hidratacao",
        "hidratação",
    }
    off_niche_recommended = sorted(
        recommended_features & (off_niche_features | quality_gate_off_niche)
    )

    pending_count = counts["pending"]
    failed_count = counts["failed"]
    price_coverage = counts["price_coverage"]
    title_coverage = counts["title_coverage"]

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
    score += min(effective_direct_count * 10, 50)
    score += min(effective_partial_count * 3, 15)
    score = max(0, score - failed_count * 5)
    score += 5 if freshness_days < 1 else (2 if freshness_days < 7 else 0)
    score += min(len(evidence_list), 10)
    score += 10  # report_exists
    score += 5 if title_coverage >= 0.9 else (2 if title_coverage >= 0.75 else 0)
    score += 5 if price_coverage >= 0.8 else (2 if price_coverage >= 0.6 else 0)

    # Price dispersion penalty
    price_analysis = report.get("raw", {}).get("analyses", {}).get("price", {})
    if price_analysis.get("dispersion_warning"):
        score = max(0, score - 15)
    if pending_count:
        score = max(0, score - min(15, pending_count * 2))
    if variants_grouped:
        score = max(0, score - min(10, variants_grouped * 2))
    if off_niche_recommended:
        score = max(0, score - 20)

    # Determine level
    level = "insufficient"
    if score >= 80:
        level = "high"
    elif score >= 55:
        level = "medium"
    elif score >= 35:
        level = "low"

    warnings = []
    if effective_direct_count < 8:
        warnings.append(f"Poucos concorrentes diretos efetivos ({effective_direct_count}); ideal > 8.")
    if variants_grouped:
        warnings.append(f"{variants_grouped} variacao(oes) agrupada(s); contagem bruta nao foi usada como base de HIGH.")
    if pending_count:
        warnings.append(f"Ainda ha {pending_count} candidato(s) pendente(s) que podem alterar a base.")
    if failed_count > 3:
        warnings.append(f"{failed_count} coletas com falha.")
    if title_coverage < 0.9:
        warnings.append(f"Cobertura de titulo incompleta ({title_coverage:.0%}).")
    if price_coverage < 0.8:
        warnings.append(f"Cobertura de preco incompleta ({price_coverage:.0%}).")
    if freshness_days > 7:
        warnings.append("Relatorio desatualizado (mais de 7 dias).")
    if price_analysis.get("dispersion_warning"):
        warnings.append("Alta dispersao de precos.")
    if off_niche_recommended:
        warnings.append(
            "Features off-niche apareceram como recomendadas: "
            + ", ".join(off_niche_recommended)
            + "."
        )

    high_has_enough_competitors = effective_direct_count >= 8 or (
        effective_direct_count >= 5 and effective_partial_count >= 8
    )
    if level == "high" and not high_has_enough_competitors:
        level = "medium"
        warnings.append("Confiança alta bloqueada: base efetiva ainda tem poucos diretos/parciais fortes.")
    if level == "high" and pending_count:
        level = "medium"
        warnings.append("Confiança alta bloqueada: ainda ha candidatos pendentes.")
    if level == "high" and (title_coverage < 0.9 or price_coverage < 0.8):
        level = "medium"
        warnings.append("Confiança alta bloqueada: cobertura de titulo/preco insuficiente.")
    if level == "high" and off_niche_recommended:
        level = "medium"
        warnings.append("Confiança alta bloqueada: feature off-niche foi recomendada.")

    return {
        "level": level,
        "score": score,
        "direct_count": direct_count,
        "partial_count": partial_count,
        "effective_direct_count": effective_direct_count,
        "effective_partial_count": effective_partial_count,
        "effective_competitor_count": effective_competitor_count,
        "variants_grouped": variants_grouped,
        "off_niche_recommended": off_niche_recommended,
        "pending_count": pending_count,
        "failed_count": failed_count,
        "title_coverage": title_coverage,
        "price_coverage": price_coverage,
        "freshness_days": freshness_days,
        "warnings": warnings,
    }


# ── Part 5: Full automatic cycle ──────────────────────────────────────────


_CONFIDENCE_RANK = {
    "insufficient": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
}


def _confidence_reaches(level: str | None, target: str | None) -> bool:
    return _CONFIDENCE_RANK.get(str(level or "insufficient"), 0) >= _CONFIDENCE_RANK.get(str(target or "high"), 3)


def _get_auto_cycle_counts(own_product_uid: str) -> dict:
    table = get_competitor_table_for_product(own_product_uid)
    counts = {
        "total_candidates": len(table),
        "pending": 0,
        "failed": 0,
        "collected_unclassified": 0,
        "direct": 0,
        "partial": 0,
        "rejected": 0,
        "title_coverage": 0.0,
        "price_coverage": 0.0,
    }

    collected_rows = []
    for row in table:
        status = row.get("status")
        if status == "pending":
            counts["pending"] += 1
        elif status == "failed":
            counts["failed"] += 1
        elif status == "collected":
            counts["collected_unclassified"] += 1
            collected_rows.append(row)
        elif status == "competitor_direct":
            counts["direct"] += 1
            collected_rows.append(row)
        elif status == "competitor_partial":
            counts["partial"] += 1
            collected_rows.append(row)
        elif status == "rejected":
            counts["rejected"] += 1
            collected_rows.append(row)

    if collected_rows:
        counts["title_coverage"] = round(
            sum(1 for row in collected_rows if row.get("title")) / len(collected_rows),
            4,
        )
        counts["price_coverage"] = round(
            sum(1 for row in collected_rows if row.get("price") is not None) / len(collected_rows),
            4,
        )

    return counts


def _empty_collection_result() -> dict:
    return {
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
        "errors": [],
    }


def run_automatic_radar_cycle(
    own_product_uid: str,
    marketplace: str = "mercadolivre",
    target_confidence: str = "high",
    max_queries: int = 6,
    max_urls_per_query: int = 10,
    max_collect: int = 15,
    max_collect_per_cycle: int | None = None,
    max_cycles: int = 3,
    max_total_candidates: int = 60,
    max_total_runtime_minutes: int = 20,
    candidate_scope: str = "direct_plus_partial",
    browser_mode: str = "cdp",
    cdp_url: str = "http://127.0.0.1:9222",
    discover_new_urls: bool = True,
    progress_callback=None,
) -> dict:
    """Run discovery, collection, classification and reporting in bounded cycles."""
    max_collect_per_cycle = int(max_collect_per_cycle or max_collect or 15)
    max_cycles = max(1, int(max_cycles or 1))
    max_total_candidates = max(1, int(max_total_candidates or 1))
    max_total_runtime_minutes = max(1, int(max_total_runtime_minutes or 1))
    start_time = time.monotonic()

    result: dict[str, Any] = {
        "ok": False,
        "status": "error",
        "step": "",
        "target_confidence": target_confidence,
        "final_confidence": "insufficient",
        "cycles_run": 0,
        "cycle_results": [],
        "urls_found": 0,
        "candidates_inserted": 0,
        "urls_existing": 0,
        "collected": 0,
        "pending": 0,
        "failed": 0,
        "direct": 0,
        "partial": 0,
        "rejected": 0,
        "report_uid": None,
        "discovery": None,
        "collection": None,
        "classification": None,
        "report": None,
        "confidence": None,
        "errors": [],
        "warnings": [],
    }

    def _progress(stage: str, message: str):
        if progress_callback:
            try:
                progress_callback({"stage": stage, "message": message})
            except Exception:
                pass

    def _warn_once(message: str):
        if message not in result["warnings"]:
            result["warnings"].append(message)

    _progress("chrome_check", "Procurando Chrome/Edge no sistema...")
    from shopee_core.radar_cdp_service import ensure_radar_chrome_ready
    chrome = ensure_radar_chrome_ready(cdp_url)
    if not chrome.get("ok"):
        result["step"] = "chrome"
        result["errors"].append(chrome.get("message", "Falha ao abrir Chrome do Radar."))
        result["diagnostics"] = chrome.get("diagnostics", {})
        return result
    _progress("chrome_validate", "Chrome CDP pronto e validado.")

    _progress("queries", "Gerando buscas...")
    own_product = get_product(own_product_uid)
    if not own_product:
        result["step"] = "queries"
        result["errors"].append("Produto proprio nao encontrado.")
        return result
    queries = generate_competitor_search_queries(own_product)
    result["queries_generated"] = len(queries)

    stop_reason = ""

    for cycle in range(1, max_cycles + 1):
        elapsed_minutes = (time.monotonic() - start_time) / 60
        if elapsed_minutes >= max_total_runtime_minutes:
            result["status"] = "limit_reached"
            stop_reason = f"Tempo maximo atingido ({max_total_runtime_minutes} min)."
            break

        result["cycles_run"] = cycle
        _progress("cycle", f"Ciclo {cycle}/{max_cycles}")

        discovery = {
            "ok": True,
            "queries_used": 0,
            "urls_found": 0,
            "urls_unique": 0,
            "urls_inserted": 0,
            "urls_existing": 0,
            "invalid": 0,
            "errors": [],
        }

        counts_before = _get_auto_cycle_counts(own_product_uid)
        discovery_slots_left = max(0, max_total_candidates - counts_before["total_candidates"])
        should_discover = (
            discover_new_urls
            and cycle == 1
            and discovery_slots_left > 0
        )

        if should_discover:
            _progress("discover", "Buscando URLs no Mercado Livre...")
            discovery = discover_marketplace_candidate_urls(
                own_product_uid=own_product_uid,
                marketplace=marketplace,
                max_queries=max_queries,
                max_urls_per_query=max_urls_per_query,
                max_unique_urls=discovery_slots_left,
                browser_mode=browser_mode,
                cdp_url=cdp_url,
                progress_callback=progress_callback,
            )
            result["discovery"] = discovery
            result["urls_found"] += int(discovery.get("urls_found") or 0)
            result["candidates_inserted"] += int(discovery.get("urls_inserted") or 0)
            result["urls_existing"] += int(discovery.get("urls_existing") or 0)

            if not discovery.get("ok"):
                counts_after_failed_discovery = _get_auto_cycle_counts(own_product_uid)
                has_existing_work = (
                    counts_after_failed_discovery["pending"]
                    or counts_after_failed_discovery["collected_unclassified"]
                    or counts_after_failed_discovery["direct"]
                    or counts_after_failed_discovery["partial"]
                )
                if not has_existing_work:
                    result["step"] = "discover"
                    result["errors"].append(discovery.get("error", "Falha na descoberta de URLs."))
                    return result
                _warn_once(
                    "Descoberta de URLs falhou, mas havia candidatos existentes; continuando com a fila atual."
                )
            if int(discovery.get("urls_limited") or 0) > 0:
                _warn_once(
                    f"Descoberta limitada a {discovery_slots_left} novo(s) candidato(s); "
                    f"{int(discovery.get('urls_limited') or 0)} URL(s) ficaram fora do limite configurado."
                )
        elif not discover_new_urls:
            _warn_once("Descoberta pulada; continuando a partir dos candidatos pendentes existentes.")
        elif cycle == 1 and discovery_slots_left <= 0:
            _warn_once(
                f"Limite de novos candidatos ja atingido "
                f"({counts_before['total_candidates']}/{max_total_candidates}); "
                "continuando a coleta dos pendentes existentes."
            )

        _progress("jobs", "Preparando coletas...")
        ensure_collection_jobs_for_linked_candidates(own_product_uid)
        counts_ready = _get_auto_cycle_counts(own_product_uid)

        if counts_ready["total_candidates"] >= max_total_candidates:
            _warn_once(
                f"Limite de descoberta de novos candidatos atingido "
                f"({counts_ready['total_candidates']}/{max_total_candidates}); pendentes existentes seguem em coleta."
            )

        if counts_ready["pending"] > 0:
            collect_limit = min(max_collect_per_cycle, counts_ready["pending"])
            _progress("collect", f"Coletando {collect_limit} candidato(s) pendente(s)...")
            collection = run_linked_collection_for_product(
                own_product_uid=own_product_uid,
                limit=collect_limit,
                save_assets=False,
                browser_mode=browser_mode,
                cdp_url=cdp_url,
                collect_image_urls=True,
                progress_callback=progress_callback,
            )
        else:
            collection = _empty_collection_result()

        result["collection"] = collection
        result["collected"] += int(collection.get("succeeded") or 0)

        _progress("classify", "Classificando candidatos coletados...")
        try:
            classification = classify_linked_candidates_for_product(
                own_product_uid, force_reclassify=True
            )
            result["classification"] = classification
        except Exception as e:
            result["step"] = "classify"
            result["errors"].append(f"Falha na classificacao: {e}")
            return result

        _progress("report", "Gerando relatorio de padroes...")
        report = None
        try:
            report = generate_pattern_report(
                own_product_uid, candidate_scope=candidate_scope
            )
            result["report"] = report
            result["report_uid"] = report.get("report_uid") if report else None
        except Exception as e:
            result["warnings"].append(f"Falha ao gerar relatorio neste ciclo: {e}")

        _progress("confidence", "Calculando confianca...")
        report_uid = report.get("report_uid") if report else result.get("report_uid")
        confidence = calculate_radar_market_confidence(
            own_product_uid, report_uid=report_uid
        )
        result["confidence"] = confidence
        result["final_confidence"] = confidence.get("level", "insufficient")

        counts_after = _get_auto_cycle_counts(own_product_uid)
        result["cycle_results"].append({
            "cycle": cycle,
            "discovery": discovery,
            "collection": collection,
            "classification": classification,
            "confidence": confidence,
            "counts": counts_after,
        })

        if _confidence_reaches(confidence.get("level"), target_confidence):
            result["status"] = "success"
            stop_reason = f"Confianca alvo atingida: {confidence.get('level')}."
            break

        if counts_after["pending"] <= 0:
            result["status"] = "exhausted"
            stop_reason = "Nao ha candidatos pendentes para continuar coletando."
            break

        if cycle >= max_cycles:
            result["status"] = "limit_reached"
            stop_reason = f"Limite de ciclos atingido ({max_cycles})."
            break

    final_counts = _get_auto_cycle_counts(own_product_uid)
    result["pending"] = final_counts["pending"]
    result["failed"] = final_counts["failed"]
    result["direct"] = final_counts["direct"]
    result["partial"] = final_counts["partial"]
    result["rejected"] = final_counts["rejected"]
    result["total_candidates"] = final_counts["total_candidates"]
    result["title_coverage"] = final_counts["title_coverage"]
    result["price_coverage"] = final_counts["price_coverage"]

    if result["status"] != "error":
        result["ok"] = True
    else:
        result["ok"] = False

    if result["ok"] and result["status"] == "error":
        result["status"] = "needs_more_collection" if result["pending"] else "exhausted"

    result["target_reached"] = result["status"] == "success"
    result["stop_reason"] = stop_reason or (
        "Ainda existem candidatos pendentes." if result["pending"] else "Ciclo encerrado."
    )
    if result["pending"] and result["status"] != "success":
        _warn_once(
            f"Ainda existem {result['pending']} candidato(s) pendente(s); a confianca pode mudar apos novas coletas."
        )
    result["step"] = result["status"]
    _progress("done", result["stop_reason"])

    return result
