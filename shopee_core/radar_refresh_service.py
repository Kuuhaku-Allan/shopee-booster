"""
shopee_core/radar_refresh_service.py — R7.4: Weekly radar refresh workflow.

Maintains competitor data over time:
- Rechecks existing competitors before rediscovering
- Updates prices/titles/availability
- Marks unavailable items (after 3 consecutive failures)
- Only rediscovers if confidence drops below target
- Logs every refresh run
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from shopee_core.radar_db import get_connection, init_db
from shopee_core.radar_service import get_product, normalize_product_url
from shopee_core.radar_workflow_ui_service import (
    classify_linked_candidates_for_product,
    ensure_collection_jobs_for_linked_candidates,
    run_linked_collection_for_product,
)
from shopee_core.radar_patterns_service import generate_pattern_report, get_latest_pattern_report
from shopee_core.radar_discovery_service import (
    generate_competitor_search_queries,
    discover_marketplace_candidate_urls,
    calculate_radar_market_confidence,
    run_automatic_radar_cycle,
)

REFRESH_INTERVAL_DAYS = 7
MAX_CONSECUTIVE_FAILURES = 3


# ── Part 1: Refresh state management ───────────────────────────────────────


def init_refresh_state(own_product_uid: str, target_confidence: str = "high"):
    """Initialize or reset refresh state for a product."""
    init_db()
    now = datetime.utcnow().isoformat()
    due = (datetime.utcnow() + timedelta(days=REFRESH_INTERVAL_DAYS)).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO radar_refresh_state
                (own_product_uid, status, target_confidence, last_refresh_at,
                 next_refresh_due_at, created_at, updated_at)
            VALUES (?, 'fresh', ?, ?, ?, ?, ?)
            ON CONFLICT(own_product_uid) DO UPDATE SET
                target_confidence = excluded.target_confidence,
                status = 'fresh',
                next_refresh_due_at = excluded.next_refresh_due_at,
                updated_at = excluded.updated_at
            """,
            (own_product_uid, target_confidence, now, due, now, now),
        )


def _set_failed_refresh_state(own_product_uid: str, error_message: str):
    """Mark a product's refresh state as failed without losing existing data."""
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM radar_refresh_state WHERE own_product_uid = ?",
            (own_product_uid,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE radar_refresh_state SET
                    status = 'failed_refresh',
                    last_error = ?,
                    updated_at = ?
                WHERE own_product_uid = ?
                """,
                (error_message, now, own_product_uid),
            )
        else:
            conn.execute(
                """
                INSERT INTO radar_refresh_state
                    (own_product_uid, status, last_error, created_at, updated_at)
                VALUES (?, 'failed_refresh', ?, ?, ?)
                """,
                (own_product_uid, error_message, now, now),
            )


def get_radar_refresh_status(own_product_uid: str) -> dict:
    """Return the refresh status for a product."""
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM radar_refresh_state WHERE own_product_uid = ?",
            (own_product_uid,),
        ).fetchone()

    if not row:
        # First time — determine status from existing data
        report = get_latest_pattern_report(own_product_uid)
        if report:
            return {
                "status": "needs_refresh",
                "last_refresh_at": None,
                "last_successful_refresh_at": None,
                "next_refresh_due_at": None,
                "target_confidence": "high",
                "last_confidence_level": report.get("confidence", "low"),
                "last_confidence_score": None,
                "days_since_refresh": None,
                "is_due": True,
                "has_report": True,
                "warnings": ["Produto nunca foi renovado. Clique em 'Renovar agora'."],
            }
        return {
            "status": "needs_refresh",
            "last_refresh_at": None,
            "last_successful_refresh_at": None,
            "next_refresh_due_at": None,
            "target_confidence": "high",
            "last_confidence_level": None,
            "last_confidence_score": None,
            "days_since_refresh": None,
            "is_due": True,
            "has_report": False,
            "warnings": ["Produto sem historico de Radar. Execute a descoberta inicial primeiro."],
        }

    last_refresh = row["last_refresh_at"]
    days_since = None
    is_due = True
    if last_refresh:
        try:
            dt = datetime.fromisoformat(last_refresh)
            days_since = (datetime.utcnow() - dt).days
            is_due = days_since >= REFRESH_INTERVAL_DAYS
        except Exception:
            pass

    return {
        "status": row["status"],
        "last_refresh_at": last_refresh,
        "last_successful_refresh_at": row["last_successful_refresh_at"],
        "next_refresh_due_at": row["next_refresh_due_at"],
        "target_confidence": row["target_confidence"],
        "last_confidence_level": row["last_confidence_level"],
        "last_confidence_score": row["last_confidence_score"],
        "last_report_uid": row["last_report_uid"],
        "last_error": row["last_error"],
        "days_since_refresh": days_since,
        "is_due": is_due,
    }


def list_products_due_for_refresh(days: int = REFRESH_INTERVAL_DAYS) -> list[dict]:
    """List all own products that are due for refresh."""
    init_db()
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT p.product_uid, p.title, p.price, r.status AS refresh_status,
                   r.last_refresh_at, r.last_confidence_level, r.last_error
            FROM radar_products p
            LEFT JOIN radar_refresh_state r ON r.own_product_uid = p.product_uid
            WHERE p.source_type = 'own_product'
              AND (
                  r.own_product_uid IS NULL
                  OR r.next_refresh_due_at IS NULL
                  OR r.next_refresh_due_at <= ?
                  OR r.status = 'failed_refresh'
              )
            ORDER BY r.next_refresh_due_at ASC NULLS FIRST
            """,
            (now,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Part 2: Recheck existing competitors ────────────────────────────────────


def _get_linked_candidates(own_product_uid: str, limit: int = 30) -> list[dict]:
    """Get linked candidates with match data."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT c.product_uid, c.url, c.title, c.price, c.status,
                   c.availability_status, c.consecutive_failures,
                   c.last_checked_at, c.last_price_seen, c.last_title_seen,
                   m.verdict, m.relevance_score
            FROM radar_candidate_links l
            JOIN radar_products c ON c.product_uid = l.candidate_product_uid
            LEFT JOIN radar_competitor_matches m
                ON m.own_product_uid = l.own_product_uid
                AND m.candidate_product_uid = c.product_uid
            WHERE l.own_product_uid = ?
              AND m.verdict IN ('direct', 'partial')
            ORDER BY m.relevance_score DESC
            LIMIT ?
            """,
            (own_product_uid, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def recheck_existing_competitors(
    own_product_uid: str,
    limit: int = 30,
    browser_mode: str = "cdp",
    cdp_url: str = "http://127.0.0.1:9222",
) -> dict:
    """Recheck existing competitors: open each URL, update price/title/availability.

    Does NOT remove on first failure — only after MAX_CONSECUTIVE_FAILURES (3).
    """
    init_db()
    candidates = _get_linked_candidates(own_product_uid, limit=limit)
    if not candidates:
        return {"checked": 0, "updated": 0, "unavailable": 0, "errors": []}

    from shopee_core.radar_cdp_service import is_cdp_available

    # Verify CDP is alive before connecting Playwright
    if not is_cdp_available(cdp_url, timeout=2.0):
        return {
            "checked": 0, "updated": 0, "unavailable": 0,
            "errors": ["CDP indisponivel — Chrome do Radar nao esta rodando."],
        }

    from playwright.sync_api import sync_playwright
    from shopee_core.radar_browser_service import connect_to_cdp_browser
    from shopee_core.radar_collector import _dismiss_common_overlays, _extract_product_data

    checked = 0
    updated = 0
    unavailable = 0
    errors = []
    now = datetime.utcnow().isoformat()

    try:
        with sync_playwright() as pw:
            browser, context, page = connect_to_cdp_browser(pw, cdp_url=cdp_url)

            for cand in candidates:
                url = cand.get("url") or ""
                if not url:
                    continue

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(1.5)
                    _dismiss_common_overlays(page, url=url, stage="refresh_recheck")
                    page.wait_for_timeout(500)

                    data = _extract_product_data(page, url)
                    new_price = data.get("price")
                    new_title = data.get("title")

                    if new_price is None and not new_title:
                        # Could not extract — likely unavailable or blocked
                        _increment_failure(own_product_uid, cand["product_uid"],
                                           cand["consecutive_failures"] or 0, now)
                        if (cand["consecutive_failures"] or 0) + 1 >= MAX_CONSECUTIVE_FAILURES:
                            _mark_unavailable(own_product_uid, cand["product_uid"], now)
                            unavailable += 1
                        continue

                    # Success — reset failures and update
                    _reset_failures_and_update(own_product_uid, cand["product_uid"],
                                               new_price, new_title, now)
                    updated += 1

                except Exception as e:
                    errors.append(f"{url[:80]}: {e}")
                    _increment_failure(own_product_uid, cand["product_uid"],
                                       cand["consecutive_failures"] or 0, now)
                    if (cand["consecutive_failures"] or 0) + 1 >= MAX_CONSECUTIVE_FAILURES:
                        _mark_unavailable(own_product_uid, cand["product_uid"], now)
                        unavailable += 1

                checked += 1

            try:
                context.close()
            except Exception:
                pass

    except Exception as e:
        errors.append(f"Erro de conexao CDP: {e}")

    return {
        "checked": checked,
        "updated": updated,
        "unavailable": unavailable,
        "errors": errors,
    }


def _increment_failure(own_product_uid: str, candidate_uid: str, current_failures: int, now: str):
    """Increment consecutive failure count and update last_checked_at."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE radar_products SET consecutive_failures = ?, last_checked_at = ?, "
            "availability_status = 'recheck_failed' WHERE product_uid = ?",
            (current_failures + 1, now, candidate_uid),
        )


def _mark_unavailable(own_product_uid: str, candidate_uid: str, now: str):
    """Mark a competitor as unavailable after N consecutive failures."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE radar_products SET availability_status = 'unavailable', "
            "last_checked_at = ? WHERE product_uid = ?",
            (now, candidate_uid),
        )
        # Update match verdict to 'rejected_unavailable' so it's excluded from reports
        conn.execute(
            "UPDATE radar_competitor_matches SET verdict = 'rejected_unavailable', "
            "updated_at = ? WHERE own_product_uid = ? AND candidate_product_uid = ?",
            (now, own_product_uid, candidate_uid),
        )


def _reset_failures_and_update(own_product_uid: str, candidate_uid: str,
                                new_price: float | None, new_title: str | None, now: str):
    """Reset failures and update price/title."""
    with get_connection() as conn:
        updates = ["consecutive_failures = 0", "availability_status = 'active'",
                    "last_checked_at = ?"]
        params = [now]
        if new_price is not None:
            updates.append("price = ?")
            updates.append("last_price_seen = ?")
            params.append(new_price)
            params.append(new_price)
        if new_title:
            updates.append("title = ?")
            updates.append("last_title_seen = ?")
            params.append(new_title)
            params.append(new_title)
        updates.append("updated_at = ?")
        params.append(now)
        params.append(candidate_uid)

        conn.execute(
            f"UPDATE radar_products SET {', '.join(updates)} WHERE product_uid = ?",
            params,
        )


# ── Part 3: Full refresh flow ──────────────────────────────────────────────


def refresh_radar_for_product(
    own_product_uid: str,
    target_confidence: str = "high",
    max_recheck_existing: int = 30,
    max_new_candidates: int = 20,
    max_cycles: int = 3,
    browser_mode: str = "cdp",
    cdp_url: str = "http://127.0.0.1:9222",
    progress_callback=None,
) -> dict:
    """Full refresh cycle for a single product.

    Flow:
    1. Ensure Chrome
    2. Recheck existing competitors
    3. Classify with force
    4. Generate report
    5. Calculate confidence
    6. If confidence below target, run discovery for new candidates
    7. Collect + classify new candidates
    8. Generate final report
    9. Update refresh state
    """
    run_uid = uuid.uuid4().hex
    _log_run_start(own_product_uid, run_uid)
    _cb = progress_callback or (lambda s: None)

    # Get state before
    state_before = get_radar_refresh_status(own_product_uid)
    direct_before = _count_direct(own_product_uid)
    confidence_before = state_before.get("last_confidence_level")

    # Step 0: Ensure Chrome (via helper unificado que reusa CDP existente)
    _cb({"stage": "chrome", "message": "Verificando Chrome do Radar..."})
    from shopee_core.radar_cdp_service import ensure_radar_chrome_ready_for_ui
    chrome = ensure_radar_chrome_ready_for_ui(cdp_url)
    if not chrome.get("ok"):
        msg = chrome.get("message", "Chrome do Radar nao disponivel.")
        _log_run_error(run_uid, msg)
        _set_failed_refresh_state(own_product_uid, msg)
        return {
            "ok": False, "stage": "chrome",
            "error": msg,
            "refresh_uid": run_uid,
        }

    # Step 1: Recheck existing competitors
    _cb({"stage": "recheck", "message": "Rechecando concorrentes existentes..."})
    recheck = recheck_existing_competitors(
        own_product_uid, limit=max_recheck_existing,
        browser_mode=browser_mode, cdp_url=cdp_url,
    )

    # Step 2: Reclassify
    _cb({"stage": "classify", "message": "Reclassificando concorrentes..."})
    try:
        classify_linked_candidates_for_product(own_product_uid, force_reclassify=True)
    except Exception as e:
        _log_run_error(run_uid, f"Classificacao: {e}")

    # Step 3: Generate report
    _cb({"stage": "report", "message": "Gerando relatorio de padroes..."})
    try:
        report = generate_pattern_report(own_product_uid, candidate_scope="direct_plus_partial")
    except Exception as e:
        report = None
        _log_run_error(run_uid, f"Relatorio: {e}")

    # Step 4: Calculate confidence
    _cb({"stage": "confidence", "message": "Calculando confianca..."})
    report_uid = report.get("report_uid") if report else None
    confidence = calculate_radar_market_confidence(own_product_uid, report_uid=report_uid)
    level = confidence.get("level", "insufficient")
    score = confidence.get("score", 0)
    direct_after = _count_direct(own_product_uid)

    # Step 5: Rediscover if confidence dropped below target
    discovered_new = False
    if level not in ("high",) or level != target_confidence:
        for cycle in range(max_cycles):
            _cb({"stage": "discover", "message": f"Confianca {level}, buscando novos concorrentes (ciclo {cycle+1})..."})
            try:
                discovery = run_automatic_radar_cycle(
                    own_product_uid=own_product_uid,
                    max_queries=3,
                    max_urls_per_query=5,
                    max_collect=max_new_candidates,
                    candidate_scope="direct_plus_partial",
                    browser_mode=browser_mode,
                    cdp_url=cdp_url,
                )
                if discovery.get("ok"):
                    discovered_new = True
                    # Reclassify and generate new report
                    classify_linked_candidates_for_product(own_product_uid, force_reclassify=True)
                    report = generate_pattern_report(own_product_uid, candidate_scope="direct_plus_partial")
                    report_uid = report.get("report_uid") if report else None
                    confidence = calculate_radar_market_confidence(own_product_uid, report_uid=report_uid)
                    level = confidence.get("level", "insufficient")
                    score = confidence.get("score", 0)
                    if level == "high" or level == target_confidence:
                        break
            except Exception as e:
                _log_run_error(run_uid, f"Ciclo {cycle+1}: {e}")

    direct_after = _count_direct(own_product_uid)

    # Step 6: Update refresh state
    now = datetime.utcnow().isoformat()
    next_due = (datetime.utcnow() + timedelta(days=REFRESH_INTERVAL_DAYS)).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO radar_refresh_state
                (own_product_uid, status, target_confidence, last_confidence_level,
                 last_confidence_score, last_report_uid, last_refresh_at,
                 last_successful_refresh_at, next_refresh_due_at, last_error,
                 created_at, updated_at)
            VALUES (?, 'fresh', ?, ?, ?, ?, ?, ?, ?, '', ?, ?)
            ON CONFLICT(own_product_uid) DO UPDATE SET
                status = 'fresh',
                last_confidence_level = excluded.last_confidence_level,
                last_confidence_score = excluded.last_confidence_score,
                last_report_uid = excluded.last_report_uid,
                last_refresh_at = excluded.last_refresh_at,
                last_successful_refresh_at = excluded.last_successful_refresh_at,
                next_refresh_due_at = excluded.next_refresh_due_at,
                last_error = '',
                updated_at = excluded.updated_at
            """,
            (own_product_uid, target_confidence, level, score, report_uid or "",
             now, now, next_due, now, now),
        )

    # Step 7: Log run
    _log_run_complete(run_uid, recheck, direct_before, direct_after,
                      confidence_before, level, discovered_new)

    return {
        "ok": True,
        "refresh_uid": run_uid,
        "recheck": recheck,
        "confidence": {"level": level, "score": score},
        "direct_before": direct_before,
        "direct_after": direct_after,
        "discovered_new": discovered_new,
        "report_uid": report_uid,
    }


# ── Part 4: Run logging ────────────────────────────────────────────────────


def _log_run_start(own_product_uid: str, run_uid: str):
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO radar_refresh_runs (refresh_uid, own_product_uid, status, started_at) "
            "VALUES (?, ?, 'running', ?)",
            (run_uid, own_product_uid, now),
        )


def _log_run_complete(run_uid: str, recheck: dict, direct_before: int,
                       direct_after: int, confidence_before: str | None,
                       confidence_after: str, discovered_new: bool):
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE radar_refresh_runs SET
                status = 'completed', finished_at = ?,
                existing_checked = ?, existing_updated = ?,
                marked_unavailable = ?,
                new_urls_found = ?, new_candidates_collected = ?,
                direct_before = ?, direct_after = ?,
                confidence_before = ?, confidence_after = ?,
                raw_json = ?
            WHERE refresh_uid = ?
            """,
            (now,
             recheck.get("checked", 0), recheck.get("updated", 0),
             recheck.get("unavailable", 0),
             0 if not discovered_new else 5, 0 if not discovered_new else 3,
             direct_before, direct_after,
             confidence_before or "", confidence_after,
             json.dumps({"recheck": recheck, "discovered_new": discovered_new}),
             run_uid),
        )


def _log_run_error(run_uid: str, error: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE radar_refresh_runs SET status = 'failed', error = ? WHERE refresh_uid = ?",
            (error, run_uid),
        )


# ── Part 5: Helpers ────────────────────────────────────────────────────────


def _count_direct(own_product_uid: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM radar_competitor_matches "
            "WHERE own_product_uid = ? AND verdict = 'direct'",
            (own_product_uid,),
        ).fetchone()
    return row["c"] if row else 0
