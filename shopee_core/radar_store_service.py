"""
shopee_core/radar_store_service.py - Local store mirror for Radar.

R7.0 keeps a trustworthy local snapshot of the seller's own products in
radar.db. It does not scrape competitors, call Gemini, or invent catalog items.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from .radar_db import get_connection, init_db


ACTIVE_CACHE_STATUSES = {"active", "changed", "unknown"}


def _now() -> str:
    return datetime.utcnow().isoformat()


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _json_dumps(data: Any) -> str:
    return json.dumps(data or {}, ensure_ascii=False, sort_keys=True)


def _row_to_dict(row) -> dict | None:
    return dict(row) if row else None


def _stable_uid(namespace: str, *parts: Any) -> str:
    raw = "|".join(str(part or "").strip().lower() for part in parts)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"shopee-booster:{namespace}:{raw}"))


def _fingerprint(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, str):
            clean = (
                value.replace("R$", "")
                .replace("\xa0", " ")
                .replace(".", "")
                .replace(",", ".")
                .strip()
            )
            return float(clean) if clean else None
        number = float(value)
        if number >= 100000:
            number = number / 100000
        return number
    except Exception:
        return None


def _first_value(data: dict, keys: list[str]) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def _looks_like_url(value: str | None) -> bool:
    if not value:
        return False
    return value.startswith("http://") or value.startswith("https://")


def _canonical_from_ids(shop_id: str | None, item_id: str | None) -> str | None:
    if shop_id and item_id:
        return f"https://shopee.com.br/i.{shop_id}.{item_id}"
    return None


def _store_lookup_clause(
    shop_uid: str | None = None,
    shop_slug: str | None = None,
    store_uid: str | None = None,
    marketplace: str = "shopee",
) -> tuple[str, list[Any]]:
    filters = []
    params: list[Any] = []

    if store_uid:
        filters.append("store_uid = ?")
        params.append(store_uid)

    aliases = [value for value in {_clean_text(shop_uid), _clean_text(shop_slug)} if value]
    if aliases:
        alias_filters = []
        for alias in aliases:
            alias_filters.append("shop_uid = ?")
            params.append(alias)
            alias_filters.append("shop_slug = ?")
            params.append(alias)
        filters.append("(" + " OR ".join(alias_filters) + ")")

    if marketplace:
        filters.append("(marketplace = ? OR marketplace IS NULL)")
        params.append(marketplace)

    if not filters:
        raise ValueError("Informe store_uid, shop_uid ou shop_slug")

    return " AND ".join(filters), params


def _find_store(
    conn,
    shop_uid: str | None = None,
    shop_slug: str | None = None,
    store_uid: str | None = None,
    marketplace: str = "shopee",
) -> dict | None:
    where, params = _store_lookup_clause(
        shop_uid=shop_uid,
        shop_slug=shop_slug,
        store_uid=store_uid,
        marketplace=marketplace,
    )
    row = conn.execute(
        f"""
        SELECT * FROM radar_stores
        WHERE {where}
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        params,
    ).fetchone()
    return _row_to_dict(row)


def _make_store_uid(
    shop_uid: str | None,
    shop_slug: str | None,
    shop_name: str | None,
    marketplace: str,
    source_url: str | None,
) -> str:
    key = shop_slug or shop_uid or source_url or shop_name
    if not key:
        raise ValueError("Loja precisa de shop_uid, shop_slug, shop_name ou source_url")
    return _stable_uid("store", marketplace, key)


def _make_internal_url(store_uid: str, normalized: dict) -> str:
    key = (
        normalized.get("marketplace_product_id")
        or normalized.get("canonical_url")
        or normalized.get("title")
        or uuid.uuid4().hex
    )
    return f"https://local.shopee-booster/radar-store/{store_uid}/{_fingerprint(str(key))}"


def normalize_store_product(raw_product: dict) -> dict:
    """Normalize one product from audit/catalog/scraping into store mirror fields."""
    if not isinstance(raw_product, dict):
        raise ValueError("raw_product precisa ser dict")

    marketplace_product_id = _clean_text(
        _first_value(
            raw_product,
            [
                "marketplace_product_id",
                "itemid",
                "item_id",
                "product_id",
                "id",
            ],
        )
    )
    title = _clean_text(
        _first_value(raw_product, ["title", "name", "nome", "product_name"])
    )
    if not title:
        raise ValueError("Produto sem titulo nao pode entrar no espelho da loja")

    shop_id = _clean_text(
        _first_value(raw_product, ["shopid", "shop_id", "shop_uid", "seller_id"])
    )
    canonical_url = _clean_text(
        _first_value(
            raw_product,
            ["canonical_url", "product_url", "url", "link", "item_url"],
        )
    )
    if not _looks_like_url(canonical_url):
        canonical_url = _canonical_from_ids(shop_id, marketplace_product_id)

    image_url = _clean_text(
        _first_value(
            raw_product,
            ["image_url", "image", "cover", "thumbnail", "pic_url"],
        )
    )

    return {
        "marketplace_product_id": marketplace_product_id,
        "title": title,
        "price": _to_float(_first_value(raw_product, ["price", "preco", "valor"])),
        "image_url": image_url,
        "canonical_url": canonical_url,
        "raw_json": dict(raw_product),
    }


def upsert_store(
    shop_uid: str | None,
    shop_slug: str | None,
    shop_name: str | None,
    marketplace: str = "shopee",
    source_url: str | None = None,
) -> dict:
    """Create or update a store row in radar_stores."""
    init_db()

    shop_uid = _clean_text(shop_uid)
    shop_slug = _clean_text(shop_slug)
    shop_name = _clean_text(shop_name)
    marketplace = _clean_text(marketplace) or "shopee"
    source_url = _clean_text(source_url)
    now = _now()

    with get_connection() as conn:
        existing = _find_store(
            conn,
            shop_uid=shop_uid,
            shop_slug=shop_slug,
            marketplace=marketplace,
        )
        store_uid = (
            existing["store_uid"]
            if existing
            else _make_store_uid(shop_uid, shop_slug, shop_name, marketplace, source_url)
        )
        raw_json = _json_dumps(
            {
                "shop_uid": shop_uid,
                "shop_slug": shop_slug,
                "shop_name": shop_name,
                "marketplace": marketplace,
                "source_url": source_url,
            }
        )

        if existing:
            conn.execute(
                """
                UPDATE radar_stores
                SET shop_uid = COALESCE(?, shop_uid),
                    shop_slug = COALESCE(?, shop_slug),
                    shop_name = COALESCE(?, shop_name),
                    marketplace = ?,
                    source_url = COALESCE(?, source_url),
                    raw_json = ?,
                    updated_at = ?
                WHERE store_uid = ?
                """,
                (
                    shop_uid,
                    shop_slug,
                    shop_name,
                    marketplace,
                    source_url,
                    raw_json,
                    now,
                    store_uid,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO radar_stores (
                    store_uid, shop_uid, shop_slug, shop_name, marketplace,
                    source_url, product_count, raw_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    store_uid,
                    shop_uid,
                    shop_slug,
                    shop_name,
                    marketplace,
                    source_url,
                    raw_json,
                    now,
                    now,
                ),
            )

        return _find_store(conn, store_uid=store_uid, marketplace=marketplace)


def _store_product_key(product: dict) -> str:
    return (
        product.get("marketplace_product_id")
        or product.get("canonical_url")
        or product.get("title")
        or ""
    ).strip().lower()


def _load_store_products(conn, store_uid: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM radar_store_products
        WHERE store_uid = ?
        ORDER BY COALESCE(last_seen_at, updated_at, created_at) DESC
        """,
        (store_uid,),
    ).fetchall()
    return [dict(row) for row in rows]


def _find_radar_product_by_canonical_url(conn, canonical_url: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM radar_products WHERE canonical_url = ?",
        (canonical_url,),
    ).fetchone()
    return _row_to_dict(row)


def _upsert_radar_product(
    conn,
    store: dict,
    normalized: dict,
    canonical_url: str,
    raw_json: str,
    now: str,
) -> str:
    existing = _find_radar_product_by_canonical_url(conn, canonical_url)
    if existing:
        product_uid = existing["product_uid"]
        conn.execute(
            """
            UPDATE radar_products
            SET source_type = 'own_product',
                marketplace = ?,
                url = ?,
                canonical_url = ?,
                title = ?,
                price = ?,
                shop_name = ?,
                status = 'collected',
                raw_json = ?,
                updated_at = ?,
                collected_at = ?
            WHERE product_uid = ?
            """,
            (
                store.get("marketplace") or "shopee",
                canonical_url,
                canonical_url,
                normalized.get("title"),
                normalized.get("price"),
                store.get("shop_name"),
                raw_json,
                now,
                now,
                product_uid,
            ),
        )
        return product_uid

    product_uid = _stable_uid("radar-product", canonical_url)
    conn.execute(
        """
        INSERT INTO radar_products (
            product_uid, owner_user_id, source_type, marketplace, url,
            canonical_url, title, price, shop_name, status, relevance_score,
            raw_json, created_at, updated_at, collected_at
        )
        VALUES (?, ?, 'own_product', ?, ?, ?, ?, ?, ?, 'collected', 0, ?, ?, ?, ?)
        """,
        (
            product_uid,
            store.get("store_uid"),
            store.get("marketplace") or "shopee",
            canonical_url,
            canonical_url,
            normalized.get("title"),
            normalized.get("price"),
            store.get("shop_name"),
            raw_json,
            now,
            now,
            now,
        ),
    )
    return product_uid


def _has_product_changes(existing: dict, normalized: dict) -> bool:
    old_price = existing.get("price")
    new_price = normalized.get("price")
    if old_price is None and new_price is not None:
        return True
    if old_price is not None and new_price is None:
        return True
    if old_price is not None and new_price is not None:
        if round(float(old_price), 2) != round(float(new_price), 2):
            return True

    fields = ["title", "image_url", "canonical_url"]
    return any((existing.get(field) or "") != (normalized.get(field) or "") for field in fields)


def save_store_snapshot(store_info: dict, products: list[dict], source: str) -> dict:
    """Save a successful store snapshot and mirror products into radar_products."""
    if not isinstance(store_info, dict):
        raise ValueError("store_info precisa ser dict")

    source = _clean_text(source) or "unknown"
    marketplace = _clean_text(store_info.get("marketplace")) or "shopee"
    init_db()

    normalized_items = []
    errors = []
    for index, raw_product in enumerate(products or []):
        try:
            normalized_items.append(normalize_store_product(raw_product))
        except Exception as exc:
            errors.append({"index": index, "error": str(exc)})

    store = upsert_store(
        shop_uid=store_info.get("shop_uid") or store_info.get("shopid") or store_info.get("shop_id"),
        shop_slug=store_info.get("shop_slug") or store_info.get("username") or store_info.get("slug"),
        shop_name=store_info.get("shop_name") or store_info.get("name"),
        marketplace=marketplace,
        source_url=store_info.get("source_url"),
    )
    store_uid = store["store_uid"]
    now = _now()

    summary = {
        "store_uid": store_uid,
        "total_received": len(products or []),
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "missing": 0,
        "removed": 0,
        "errors": errors,
    }

    with get_connection() as conn:
        store = _find_store(conn, store_uid=store_uid, marketplace=marketplace)
        existing_rows = _load_store_products(conn, store_uid)
        existing_by_key = {_store_product_key(row): row for row in existing_rows}
        seen_uids = set()

        for normalized in normalized_items:
            canonical_url = normalized.get("canonical_url") or _make_internal_url(
                store_uid,
                normalized,
            )
            normalized["canonical_url"] = canonical_url
            raw_payload = {
                "source": source,
                "store_uid": store_uid,
                "product": normalized.get("raw_json") or {},
            }
            raw_json = _json_dumps(raw_payload)
            radar_product_uid = _upsert_radar_product(
                conn,
                store,
                normalized,
                canonical_url,
                raw_json,
                now,
            )

            key = _store_product_key(normalized)
            existing = existing_by_key.get(key)
            store_product_uid = (
                existing["store_product_uid"]
                if existing
                else _stable_uid("store-product", store_uid, key or canonical_url)
            )
            seen_uids.add(store_product_uid)

            if existing:
                changed = _has_product_changes(existing, normalized)
                status = "changed" if changed else "active"
                if changed or existing.get("status") in {"missing", "removed", "unknown"}:
                    summary["updated"] += 1
                else:
                    summary["unchanged"] += 1

                conn.execute(
                    """
                    UPDATE radar_store_products
                    SET radar_product_uid = ?,
                        marketplace_product_id = ?,
                        canonical_url = ?,
                        title = ?,
                        price = ?,
                        image_url = ?,
                        status = ?,
                        last_seen_at = ?,
                        last_changed_at = CASE WHEN ? THEN ? ELSE last_changed_at END,
                        raw_json = ?,
                        updated_at = ?
                    WHERE store_product_uid = ?
                    """,
                    (
                        radar_product_uid,
                        normalized.get("marketplace_product_id"),
                        canonical_url,
                        normalized.get("title"),
                        normalized.get("price"),
                        normalized.get("image_url"),
                        status,
                        now,
                        1 if changed else 0,
                        now,
                        raw_json,
                        now,
                        store_product_uid,
                    ),
                )
            else:
                summary["created"] += 1
                conn.execute(
                    """
                    INSERT INTO radar_store_products (
                        store_product_uid, store_uid, radar_product_uid,
                        marketplace_product_id, canonical_url, title, price,
                        image_url, status, first_seen_at, last_seen_at,
                        last_changed_at, raw_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        store_product_uid,
                        store_uid,
                        radar_product_uid,
                        normalized.get("marketplace_product_id"),
                        canonical_url,
                        normalized.get("title"),
                        normalized.get("price"),
                        normalized.get("image_url"),
                        now,
                        now,
                        now,
                        raw_json,
                        now,
                        now,
                    ),
                )

        for existing in existing_rows:
            if existing["store_product_uid"] in seen_uids:
                continue
            if existing.get("status") in {"removed", "missing"}:
                continue
            summary["missing"] += 1
            conn.execute(
                """
                UPDATE radar_store_products
                SET status = 'missing',
                    last_changed_at = ?,
                    updated_at = ?
                WHERE store_product_uid = ?
                """,
                (now, now, existing["store_product_uid"]),
            )

        store_raw_json = _json_dumps(
            {
                "store_info": store_info,
                "last_source": source,
                "last_summary": summary,
            }
        )
        conn.execute(
            """
            UPDATE radar_stores
            SET last_snapshot_at = ?,
                last_successful_load_at = ?,
                product_count = ?,
                raw_json = ?,
                updated_at = ?
            WHERE store_uid = ?
            """,
            (
                now,
                now if normalized_items else store.get("last_successful_load_at"),
                len(normalized_items),
                store_raw_json,
                now,
                store_uid,
            ),
        )

    return summary


def get_cached_store_products(
    shop_uid: str | None = None,
    shop_slug: str | None = None,
    store_uid: str | None = None,
    include_removed: bool = False,
) -> list[dict]:
    """Return cached store products for fallback in audit/catalog flows."""
    init_db()
    with get_connection() as conn:
        store = _find_store(
            conn,
            shop_uid=shop_uid,
            shop_slug=shop_slug,
            store_uid=store_uid,
        )
        if not store:
            return []

        if include_removed:
            status_filter = ""
            params: list[Any] = [store["store_uid"]]
        else:
            placeholders = ", ".join("?" for _ in ACTIVE_CACHE_STATUSES)
            status_filter = f"AND status IN ({placeholders})"
            params = [store["store_uid"], *sorted(ACTIVE_CACHE_STATUSES)]

        rows = conn.execute(
            f"""
            SELECT * FROM radar_store_products
            WHERE store_uid = ?
            {status_filter}
            ORDER BY COALESCE(last_seen_at, updated_at, created_at) DESC
            """,
            params,
        ).fetchall()

    products = []
    for row in rows:
        product = dict(row)
        raw_payload = {}
        try:
            raw_payload = json.loads(product.get("raw_json") or "{}")
        except Exception:
            raw_payload = {}
        raw_product = raw_payload.get("product") or {}
        marketplace_product_id = product.get("marketplace_product_id")
        image_url = product.get("image_url")
        products.append(
            {
                **raw_product,
                "itemid": raw_product.get("itemid") or marketplace_product_id,
                "shopid": raw_product.get("shopid") or store.get("shop_uid"),
                "name": raw_product.get("name") or product.get("title"),
                "title": product.get("title"),
                "price": product.get("price") or 0,
                "image": raw_product.get("image") or image_url or "",
                "image_url": image_url,
                "canonical_url": product.get("canonical_url"),
                "marketplace_product_id": marketplace_product_id,
                "store_product_uid": product.get("store_product_uid"),
                "store_uid": product.get("store_uid"),
                "radar_product_uid": product.get("radar_product_uid"),
                "cache_status": product.get("status"),
                "source": "radar_store_mirror",
            }
        )
    return products


def get_store_snapshot_status(store_uid: str) -> dict:
    """Return aggregate status for one mirrored store."""
    init_db()
    with get_connection() as conn:
        store = _find_store(conn, store_uid=store_uid)
        if not store:
            return {
                "ok": False,
                "store_uid": store_uid,
                "cache_available": False,
                "total_products": 0,
                "active": 0,
                "removed": 0,
                "last_snapshot_at": None,
                "last_source": None,
            }

        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS total
            FROM radar_store_products
            WHERE store_uid = ?
            GROUP BY status
            """,
            (store_uid,),
        ).fetchall()
        counts = {row["status"] or "unknown": row["total"] for row in rows}

    last_source = None
    try:
        last_source = json.loads(store.get("raw_json") or "{}").get("last_source")
    except Exception:
        last_source = None

    active_total = sum(counts.get(status, 0) for status in ACTIVE_CACHE_STATUSES)
    total_products = sum(counts.values())
    return {
        "ok": True,
        "store_uid": store_uid,
        "shop_uid": store.get("shop_uid"),
        "shop_slug": store.get("shop_slug"),
        "shop_name": store.get("shop_name"),
        "marketplace": store.get("marketplace"),
        "total_products": total_products,
        "active": active_total,
        "missing": counts.get("missing", 0),
        "removed": counts.get("removed", 0),
        "changed": counts.get("changed", 0),
        "last_snapshot_at": store.get("last_snapshot_at"),
        "last_successful_load_at": store.get("last_successful_load_at"),
        "last_source": last_source,
        "cache_available": active_total > 0,
        "counts_by_status": counts,
    }


def diff_store_snapshot(store_uid: str, new_products: list[dict]) -> dict:
    """Compare a new product list with the latest saved snapshot."""
    init_db()
    normalized_items = []
    errors = []
    for index, raw_product in enumerate(new_products or []):
        try:
            normalized_items.append(normalize_store_product(raw_product))
        except Exception as exc:
            errors.append({"index": index, "error": str(exc)})

    new_by_key = {_store_product_key(item): item for item in normalized_items}
    with get_connection() as conn:
        existing_rows = _load_store_products(conn, store_uid)

    existing_by_key = {_store_product_key(row): row for row in existing_rows}
    result = {
        "store_uid": store_uid,
        "new_products": [],
        "missing_products": [],
        "price_changed": [],
        "title_changed": [],
        "image_changed": [],
        "unchanged": [],
        "errors": errors,
    }

    for key, new_product in new_by_key.items():
        old_product = existing_by_key.get(key)
        if not old_product:
            result["new_products"].append(new_product)
            continue

        changed_any = False
        old_price = old_product.get("price")
        new_price = new_product.get("price")
        if old_price is not None or new_price is not None:
            if round(float(old_price or 0), 2) != round(float(new_price or 0), 2):
                result["price_changed"].append(
                    {"old": old_product, "new": new_product}
                )
                changed_any = True

        if (old_product.get("title") or "") != (new_product.get("title") or ""):
            result["title_changed"].append({"old": old_product, "new": new_product})
            changed_any = True

        if (old_product.get("image_url") or "") != (new_product.get("image_url") or ""):
            result["image_changed"].append({"old": old_product, "new": new_product})
            changed_any = True

        if not changed_any:
            result["unchanged"].append(new_product)

    for key, old_product in existing_by_key.items():
        if key not in new_by_key and old_product.get("status") != "removed":
            result["missing_products"].append(old_product)

    result["summary"] = {
        "new": len(result["new_products"]),
        "missing": len(result["missing_products"]),
        "price_changed": len(result["price_changed"]),
        "title_changed": len(result["title_changed"]),
        "image_changed": len(result["image_changed"]),
        "unchanged": len(result["unchanged"]),
    }
    return result


def find_radar_product_for_store_product(store_product_uid: str) -> dict | None:
    """Return the linked radar_products row for a store mirror product."""
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT p.*
            FROM radar_store_products sp
            JOIN radar_products p ON p.product_uid = sp.radar_product_uid
            WHERE sp.store_product_uid = ?
            LIMIT 1
            """,
            (store_product_uid,),
        ).fetchone()
        return _row_to_dict(row)
