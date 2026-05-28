from shopee_core.radar_db import get_connection, init_db
from shopee_core.store_connection_service import (
    connect_store,
    disconnect_store,
    get_active_store,
    normalize_shop_slug,
    set_active_store,
)


def _clean_db():
    init_db()
    with get_connection() as conn:
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
        conn.execute("DELETE FROM store_connections")
        conn.execute("DELETE FROM radar_store_products")
        conn.execute("DELETE FROM radar_assets")
        conn.execute("DELETE FROM radar_reviews")
        conn.execute("DELETE FROM radar_candidate_links")
        conn.execute("DELETE FROM radar_collection_jobs")
        conn.execute("DELETE FROM radar_competitor_matches")
        conn.execute("DELETE FROM radar_pattern_reports")
        conn.execute("DELETE FROM radar_refresh_runs")
        conn.execute("DELETE FROM radar_refresh_state")
        conn.execute("DELETE FROM radar_stores")
        conn.execute("DELETE FROM radar_products")


def test_normalize_shop_slug_from_url():
    assert normalize_shop_slug("https://shopee.com.br/totalmenteseu") == "totalmenteseu"
    assert normalize_shop_slug("totalmenteseu") == "totalmenteseu"


def test_connect_store_returns_active_store():
    _clean_db()

    result = connect_store("https://shopee.com.br/totalmenteseu")
    active = get_active_store()

    assert result["ok"]
    assert active["has_active_store"]
    assert active["shop_slug"] == "totalmenteseu"
    assert active["store_uid"] == result["store_uid"]


def test_disconnect_store_clears_active_store():
    _clean_db()
    connect_store("https://shopee.com.br/totalmenteseu")

    result = disconnect_store()
    active = get_active_store()

    assert result["ok"]
    assert not active["has_active_store"]


def test_set_active_store_reuses_existing_store():
    _clean_db()
    first = connect_store("https://shopee.com.br/totalmenteseu")
    disconnect_store()

    result = set_active_store(first["store_uid"])
    active = get_active_store()

    assert result["ok"]
    assert active["has_active_store"]
    assert active["store_uid"] == first["store_uid"]
