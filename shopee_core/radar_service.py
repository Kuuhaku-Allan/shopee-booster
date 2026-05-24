"""
shopee_core/radar_service.py - Assisted competitor radar service.

R1 exposes URL registration, product CRUD helpers and the persistent collection
queue. It intentionally does not open browsers, run Playwright, OCR, mouse
automation or any real scraper.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .radar_db import get_connection, init_db
from .radar_types import (
    ASSET_TYPES,
    JOB_STATUSES,
    JOB_TYPES,
    MARKETPLACES,
    PRODUCT_STATUSES,
    SOURCE_TYPES,
)


TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "gbraid",
    "wbraid",
    "msclkid",
    "sp_atk",
    "spm",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
    "xptdk",
}

TRACKING_PREFIXES = ("utm_",)


def _now() -> str:
    return datetime.utcnow().isoformat()


def _row_to_dict(row) -> Optional[dict]:
    return dict(row) if row else None


def _validate_allowed(value: str, allowed: set[str], field_name: str) -> None:
    if value not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ValueError(f"{field_name} invalido: {value!r}. Use: {allowed_values}")


def _validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"URL invalida: {url!r}")


def normalize_product_url(url: str) -> str:
    """Normalize a product URL and remove tracking/query noise."""
    if not isinstance(url, str):
        raise ValueError("URL invalida: valor precisa ser texto")

    raw_url = url.strip()
    _validate_url(raw_url)

    parsed = urlsplit(raw_url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    if netloc.startswith("www."):
        netloc = netloc[4:]

    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]
    elif netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]

    path = parsed.path.strip()
    if len(path) > 1:
        path = path.rstrip("/")

    marketplace = detect_marketplace(urlunsplit((scheme, netloc, path, "", "")))
    query = ""

    if marketplace == "unknown":
        query_items = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            clean_key = key.strip()
            lower_key = clean_key.lower()
            if lower_key in TRACKING_PARAMS:
                continue
            if any(lower_key.startswith(prefix) for prefix in TRACKING_PREFIXES):
                continue
            query_items.append((clean_key, value.strip()))
        query = urlencode(sorted(query_items))

    return urlunsplit((scheme, netloc, path, query, ""))


def detect_marketplace(url: str) -> str:
    """Return shopee, mercadolivre or unknown from the URL host."""
    try:
        host = urlsplit((url or "").strip()).netloc.lower()
    except Exception:
        return "unknown"

    if host.startswith("www."):
        host = host[4:]

    if "shopee." in host or host.startswith("shopee."):
        return "shopee"
    if "mercadolivre." in host or "mercadolibre." in host:
        return "mercadolivre"
    return "unknown"


def _get_product_by_canonical_url(conn, canonical_url: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM radar_products WHERE canonical_url = ?",
        (canonical_url,),
    ).fetchone()
    return _row_to_dict(row)


def _get_latest_job_for_product(conn, product_uid: str) -> Optional[dict]:
    row = conn.execute(
        """
        SELECT * FROM radar_collection_jobs
        WHERE product_uid = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (product_uid,),
    ).fetchone()
    return _row_to_dict(row)


def _get_job(job_uid: str) -> Optional[dict]:
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM radar_collection_jobs WHERE job_uid = ?",
            (job_uid,),
        ).fetchone()
        return _row_to_dict(row)


def get_collection_job(job_uid: str) -> dict | None:
    """Return one collection job by UID."""
    return _get_job(job_uid)


def add_product_url(
    url: str,
    source_type: str,
    owner_user_id: str | None = None,
    niche: str | None = None,
) -> dict:
    """Add one product URL and enqueue its initial collection job."""
    _validate_allowed(source_type, SOURCE_TYPES, "source_type")

    canonical_url = normalize_product_url(url)
    _validate_url(canonical_url)

    marketplace = detect_marketplace(canonical_url)
    _validate_allowed(marketplace, MARKETPLACES, "marketplace")

    init_db()

    with get_connection() as conn:
        existing = _get_product_by_canonical_url(conn, canonical_url)
        if existing:
            return {
                "created": False,
                "duplicate": True,
                "product": existing,
                "job": _get_latest_job_for_product(conn, existing["product_uid"]),
            }

        now = _now()
        product_uid = str(uuid.uuid4())
        job_uid = str(uuid.uuid4())

        conn.execute(
            """
            INSERT INTO radar_products (
                product_uid, owner_user_id, source_type, marketplace, url,
                canonical_url, niche, status, relevance_score, created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?)
            """,
            (
                product_uid,
                owner_user_id,
                source_type,
                marketplace,
                url.strip(),
                canonical_url,
                niche,
                now,
                now,
            ),
        )

        conn.execute(
            """
            INSERT INTO radar_collection_jobs (
                job_uid, product_uid, url, job_type, status, attempts,
                created_at, updated_at
            )
            VALUES (?, ?, ?, 'collect_product_page', 'pending', 0, ?, ?)
            """,
            (job_uid, product_uid, canonical_url, now, now),
        )

        product = _get_product_by_canonical_url(conn, canonical_url)
        job = _get_latest_job_for_product(conn, product_uid)

        return {
            "created": True,
            "duplicate": False,
            "product": product,
            "job": job,
        }


def add_product_urls_bulk(
    urls: list[str],
    source_type: str,
    owner_user_id=None,
    niche=None,
) -> dict:
    """Add several product URLs, counting created, duplicate and invalid items."""
    _validate_allowed(source_type, SOURCE_TYPES, "source_type")

    result = {
        "total_received": len(urls),
        "created": 0,
        "duplicates": 0,
        "invalid": 0,
        "products": [],
        "jobs": [],
        "errors": [],
    }

    for url in urls:
        try:
            item = add_product_url(
                url=url,
                source_type=source_type,
                owner_user_id=owner_user_id,
                niche=niche,
            )
        except Exception as exc:
            result["invalid"] += 1
            result["errors"].append({"url": url, "error": str(exc)})
            continue

        if item["created"]:
            result["created"] += 1
        elif item["duplicate"]:
            result["duplicates"] += 1

        result["products"].append(item["product"])
        if item.get("job"):
            result["jobs"].append(item["job"])

    return result


def list_products(
    source_type=None,
    status=None,
    marketplace=None,
    limit=100,
) -> list[dict]:
    """List products with optional filters."""
    if source_type is not None:
        _validate_allowed(source_type, SOURCE_TYPES, "source_type")
    if status is not None:
        _validate_allowed(status, PRODUCT_STATUSES, "status")
    if marketplace is not None:
        _validate_allowed(marketplace, MARKETPLACES, "marketplace")

    init_db()

    filters = []
    params: list[Any] = []

    if source_type is not None:
        filters.append("source_type = ?")
        params.append(source_type)
    if status is not None:
        filters.append("status = ?")
        params.append(status)
    if marketplace is not None:
        filters.append("marketplace = ?")
        params.append(marketplace)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    safe_limit = max(1, min(int(limit), 500))
    params.append(safe_limit)

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM radar_products
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]


def get_product(product_uid: str) -> dict | None:
    """Return one product by UID."""
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM radar_products WHERE product_uid = ?",
            (product_uid,),
        ).fetchone()
        return _row_to_dict(row)


def mark_product_collected(product_uid: str, data: dict) -> dict:
    """Store collected product fields after a future collector finishes."""
    if not isinstance(data, dict):
        raise ValueError("data precisa ser dict")

    product = get_product(product_uid)
    if not product:
        raise ValueError(f"Produto nao encontrado: {product_uid}")

    price = data.get("price")
    if price is not None:
        price = float(price)

    now = _now()
    raw_json = json.dumps(data, ensure_ascii=False, sort_keys=True)

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE radar_products
            SET title = ?, price = ?, shop_name = ?, raw_json = ?,
                status = 'collected', rejection_reason = NULL,
                updated_at = ?, collected_at = ?
            WHERE product_uid = ?
            """,
            (
                data.get("title"),
                price,
                data.get("shop_name"),
                raw_json,
                now,
                now,
                product_uid,
            ),
        )

    return get_product(product_uid)


def add_product_asset(
    product_uid: str,
    asset_type: str,
    source_url: str | None = None,
    local_path: str | None = None,
) -> dict:
    """Register one product asset reference without downloading the file."""
    _validate_allowed(asset_type, ASSET_TYPES, "asset_type")

    product = get_product(product_uid)
    if not product:
        raise ValueError(f"Produto nao encontrado: {product_uid}")

    if not source_url and not local_path:
        raise ValueError("source_url ou local_path precisa ser informado")

    init_db()
    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT * FROM radar_assets
            WHERE product_uid = ?
              AND asset_type = ?
              AND COALESCE(source_url, '') = COALESCE(?, '')
              AND COALESCE(local_path, '') = COALESCE(?, '')
            LIMIT 1
            """,
            (product_uid, asset_type, source_url, local_path),
        ).fetchone()

        if existing:
            return dict(existing)

        asset_uid = str(uuid.uuid4())
        now = _now()
        conn.execute(
            """
            INSERT INTO radar_assets (
                asset_uid, product_uid, asset_type, source_url, local_path,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (asset_uid, product_uid, asset_type, source_url, local_path, now),
        )

        row = conn.execute(
            "SELECT * FROM radar_assets WHERE asset_uid = ?",
            (asset_uid,),
        ).fetchone()
        return dict(row)


def save_product_assets(
    product_uid: str,
    image_urls: list[str] | None = None,
    video_urls: list[str] | None = None,
) -> list[dict]:
    """Persist image/video URLs as radar_assets rows."""
    assets = []

    for image_url in image_urls or []:
        if image_url:
            assets.append(add_product_asset(product_uid, "image", source_url=image_url))

    for video_url in video_urls or []:
        if video_url:
            assets.append(add_product_asset(product_uid, "video", source_url=video_url))

    return assets


def list_product_assets(product_uid: str, asset_type: str | None = None) -> list[dict]:
    """List assets registered for one product."""
    if asset_type is not None:
        _validate_allowed(asset_type, ASSET_TYPES, "asset_type")

    init_db()
    filters = ["product_uid = ?"]
    params: list[Any] = [product_uid]

    if asset_type is not None:
        filters.append("asset_type = ?")
        params.append(asset_type)

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM radar_assets
            WHERE {' AND '.join(filters)}
            ORDER BY created_at ASC
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]


def mark_product_failed(product_uid: str, error: str) -> dict:
    """Mark a product collection as failed."""
    product = get_product(product_uid)
    if not product:
        raise ValueError(f"Produto nao encontrado: {product_uid}")

    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE radar_products
            SET status = 'failed', rejection_reason = ?, updated_at = ?
            WHERE product_uid = ?
            """,
            (str(error), now, product_uid),
        )

    return get_product(product_uid)


def classify_product(
    product_uid: str,
    source_type: str,
    relevance_score: float,
    rejection_reason=None,
) -> dict:
    """Classify a product for future competitor filtering."""
    _validate_allowed(source_type, SOURCE_TYPES, "source_type")

    product = get_product(product_uid)
    if not product:
        raise ValueError(f"Produto nao encontrado: {product_uid}")

    now = _now()
    status_sql = ", status = 'rejected'" if source_type == "rejected" else ""

    with get_connection() as conn:
        conn.execute(
            f"""
            UPDATE radar_products
            SET source_type = ?, relevance_score = ?, rejection_reason = ?,
                updated_at = ?{status_sql}
            WHERE product_uid = ?
            """,
            (
                source_type,
                float(relevance_score),
                rejection_reason,
                now,
                product_uid,
            ),
        )

    return get_product(product_uid)


def get_pending_jobs(limit=20) -> list[dict]:
    """Return pending collection jobs in FIFO order."""
    init_db()
    safe_limit = max(1, min(int(limit), 500))
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM radar_collection_jobs
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def mark_job_running(job_uid: str) -> dict:
    """Mark a collection job as running and increment attempts."""
    job = _get_job(job_uid)
    if not job:
        raise ValueError(f"Job nao encontrado: {job_uid}")

    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE radar_collection_jobs
            SET status = 'running', attempts = attempts + 1,
                updated_at = ?, last_error = NULL
            WHERE job_uid = ?
            """,
            (now, job_uid),
        )

    return _get_job(job_uid)


def mark_job_done(job_uid: str) -> dict:
    """Mark a collection job as done."""
    job = _get_job(job_uid)
    if not job:
        raise ValueError(f"Job nao encontrado: {job_uid}")

    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE radar_collection_jobs
            SET status = 'done', updated_at = ?, finished_at = ?
            WHERE job_uid = ?
            """,
            (now, now, job_uid),
        )

    return _get_job(job_uid)


def mark_job_failed(job_uid: str, error: str) -> dict:
    """Mark a collection job as failed."""
    job = _get_job(job_uid)
    if not job:
        raise ValueError(f"Job nao encontrado: {job_uid}")

    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE radar_collection_jobs
            SET status = 'failed', last_error = ?, updated_at = ?,
                finished_at = ?
            WHERE job_uid = ?
            """,
            (str(error), now, now, job_uid),
        )

    return _get_job(job_uid)
