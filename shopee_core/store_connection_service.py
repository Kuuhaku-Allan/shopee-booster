"""
Persistent active store connection for clean installs.

This keeps a small "which store is active" layer over the existing Radar store
mirror tables. Product data continues to live in radar_stores /
radar_store_products; this module only remembers the connected store.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from shopee_core.radar_db import get_connection, init_db
from shopee_core.radar_store_service import get_store_snapshot_status, upsert_store


def _now() -> str:
    return datetime.utcnow().isoformat()


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def normalize_shop_slug(shop_url_or_slug: str) -> str:
    """Extract a Shopee shop slug from a URL or return the cleaned slug."""
    value = str(shop_url_or_slug or "").strip()
    if not value:
        return ""

    if "://" not in value and "/" not in value:
        return value.strip("@/")

    parsed = urlparse(value if "://" in value else "https://" + value)
    path = parsed.path.strip("/")
    if not path:
        return ""

    first = path.split("/")[0].strip("@")
    if first in {"br", "shop", "mall"} and len(path.split("/")) > 1:
        first = path.split("/")[1].strip("@")
    return first


def normalize_shop_url(shop_url_or_slug: str, marketplace: str = "shopee") -> str:
    """Return a canonical shop URL for the supported marketplace."""
    value = str(shop_url_or_slug or "").strip()
    if value.startswith(("http://", "https://")):
        return value
    slug = normalize_shop_slug(value)
    if marketplace == "shopee" and slug:
        return f"https://shopee.com.br/{slug}"
    return value


def _ensure_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS store_connections (
            connection_uid TEXT PRIMARY KEY,
            store_uid TEXT NOT NULL,
            marketplace TEXT NOT NULL,
            shop_url TEXT,
            shop_slug TEXT,
            display_name TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            is_active INTEGER NOT NULL DEFAULT 1,
            connected_at TEXT NOT NULL,
            last_loaded_at TEXT,
            last_mirror_at TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_store_connections_active "
        "ON store_connections(is_active, status)"
    )


def _connection_uid(marketplace: str, store_uid: str) -> str:
    return f"{marketplace}:{store_uid}"


def _load_active(conn) -> dict | None:
    row = conn.execute(
        """
        SELECT c.*, s.shop_uid, s.shop_name, s.product_count,
               s.last_snapshot_at, s.last_successful_load_at, s.source_url
        FROM store_connections c
        LEFT JOIN radar_stores s ON s.store_uid = c.store_uid
        WHERE c.is_active = 1 AND c.status = 'active'
        ORDER BY c.updated_at DESC
        LIMIT 1
        """
    ).fetchone()
    return dict(row) if row else None


def connect_store(shop_url: str, marketplace: str = "shopee") -> dict:
    """Connect a store URL/slug and mark it as the active store."""
    init_db()
    shop_url = normalize_shop_url(shop_url, marketplace=marketplace)
    shop_slug = normalize_shop_slug(shop_url)
    if not shop_slug:
        return {
            "ok": False,
            "status": "invalid_url",
            "message": "URL de loja invalida.",
            "store": None,
        }

    store = upsert_store(
        shop_uid=None,
        shop_slug=shop_slug,
        shop_name=shop_slug,
        marketplace=marketplace,
        source_url=shop_url,
    )
    now = _now()
    uid = _connection_uid(marketplace, store["store_uid"])

    with get_connection() as conn:
        _ensure_table(conn)
        conn.execute("UPDATE store_connections SET is_active = 0 WHERE is_active = 1")
        conn.execute(
            """
            INSERT INTO store_connections (
                connection_uid, store_uid, marketplace, shop_url, shop_slug,
                display_name, status, is_active, connected_at, last_loaded_at,
                last_mirror_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'active', 1, ?, NULL, NULL, ?)
            ON CONFLICT(connection_uid) DO UPDATE SET
                shop_url = excluded.shop_url,
                shop_slug = excluded.shop_slug,
                display_name = excluded.display_name,
                status = 'active',
                is_active = 1,
                updated_at = excluded.updated_at
            """
            ,
            (
                uid,
                store["store_uid"],
                marketplace,
                shop_url,
                shop_slug,
                store.get("shop_name") or shop_slug,
                now,
                now,
            ),
        )
        active = _load_active(conn)

    return {
        "ok": True,
        "status": "connected",
        "store_uid": store["store_uid"],
        "store": active,
        "message": f"Loja conectada: {shop_slug}",
    }


def set_active_store(store_uid: str) -> dict:
    """Mark an existing radar_stores row as active."""
    init_db()
    now = _now()
    with get_connection() as conn:
        _ensure_table(conn)
        store = conn.execute(
            "SELECT * FROM radar_stores WHERE store_uid = ? LIMIT 1",
            (store_uid,),
        ).fetchone()
        if not store:
            return {"ok": False, "status": "not_found", "message": "Loja nao encontrada."}
        store = dict(store)
        marketplace = store.get("marketplace") or "shopee"
        uid = _connection_uid(marketplace, store_uid)
        conn.execute("UPDATE store_connections SET is_active = 0 WHERE is_active = 1")
        conn.execute(
            """
            INSERT INTO store_connections (
                connection_uid, store_uid, marketplace, shop_url, shop_slug,
                display_name, status, is_active, connected_at, last_loaded_at,
                last_mirror_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'active', 1, ?, NULL, ?, ?)
            ON CONFLICT(connection_uid) DO UPDATE SET
                status = 'active',
                is_active = 1,
                shop_url = excluded.shop_url,
                shop_slug = excluded.shop_slug,
                display_name = excluded.display_name,
                last_mirror_at = excluded.last_mirror_at,
                updated_at = excluded.updated_at
            """
            ,
            (
                uid,
                store_uid,
                marketplace,
                store.get("source_url"),
                store.get("shop_slug"),
                store.get("shop_name") or store.get("shop_slug"),
                now,
                store.get("last_snapshot_at"),
                now,
            ),
        )
        active = _load_active(conn)
    return {"ok": True, "status": "active", "store_uid": store_uid, "store": active}


def mark_store_loaded(store_uid: str, mirror_at: str | None = None) -> dict:
    """Update timestamps after a store load/mirror succeeds."""
    init_db()
    now = _now()
    with get_connection() as conn:
        _ensure_table(conn)
        conn.execute(
            """
            UPDATE store_connections
            SET last_loaded_at = ?,
                last_mirror_at = COALESCE(?, last_mirror_at),
                updated_at = ?
            WHERE store_uid = ? AND is_active = 1
            """
            ,
            (now, mirror_at, now, store_uid),
        )
        active = _load_active(conn)
    return {"ok": True, "store": active}


def get_active_store() -> dict:
    """Return the current active store and mirror summary."""
    init_db()
    with get_connection() as conn:
        _ensure_table(conn)
        active = _load_active(conn)
    if not active:
        return {
            "ok": False,
            "has_active_store": False,
            "status": "none",
            "store": None,
            "summary": None,
        }
    summary = get_store_snapshot_status(active["store_uid"])
    return {
        "ok": True,
        "has_active_store": True,
        "status": "active",
        "store_uid": active["store_uid"],
        "marketplace": active.get("marketplace"),
        "shop_url": active.get("shop_url") or active.get("source_url"),
        "shop_slug": active.get("shop_slug"),
        "display_name": active.get("display_name") or active.get("shop_name") or active.get("shop_slug"),
        "last_loaded_at": active.get("last_loaded_at"),
        "last_mirror_at": active.get("last_mirror_at") or active.get("last_snapshot_at"),
        "store": active,
        "summary": summary,
    }


def disconnect_store() -> dict:
    """Disconnect the active store without deleting the mirror data."""
    init_db()
    with get_connection() as conn:
        _ensure_table(conn)
        conn.execute(
            "UPDATE store_connections SET is_active = 0, status = 'disconnected', updated_at = ? WHERE is_active = 1",
            (_now(),),
        )
    return {"ok": True, "status": "disconnected", "message": "Loja desconectada."}
