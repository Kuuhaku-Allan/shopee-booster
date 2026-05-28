from unittest.mock import patch

from shopee_core.radar_db import get_connection, init_db
from shopee_core.radar_store_mirror_builder import build_store_mirror_from_url
from shopee_core.radar_store_service import get_cached_store_products
from shopee_core.store_connection_service import get_active_store


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


def _product(i=1):
    return {
        "itemid": f"item-{i}",
        "shopid": "shop-1",
        "name": f"Mochila escolar {i}",
        "price": 79.9 + i,
        "image": f"https://img.test/{i}.jpg",
        "canonical_url": f"https://shopee.com.br/i.shop-1.item-{i}",
    }


def test_scraping_zero_triggers_cdp_and_saves_products():
    _clean_db()

    with (
        patch(
            "shopee_core.radar_store_mirror_builder._collect_products_via_scraping",
            return_value=({"shopid": "shop-1", "name": "totalmenteseu"}, [], []),
        ),
        patch(
            "shopee_core.radar_store_mirror_builder._collect_products_via_cdp",
            return_value=([_product(1), _product(2)], []),
        ),
    ):
        result = build_store_mirror_from_url("https://shopee.com.br/totalmenteseu")

    assert result["ok"]
    assert result["source"] == "cdp"
    assert result["products_found"] == 2
    assert len(result["products"]) == 2

    cached = get_cached_store_products(store_uid=result["store_uid"])
    assert len(cached) == 2
    assert all(item.get("radar_product_uid") for item in cached)


def test_scraping_products_are_saved_even_when_shop_info_is_empty():
    _clean_db()

    with patch(
        "shopee_core.radar_store_mirror_builder._collect_products_via_scraping",
        return_value=({}, [_product(1), _product(2)], ["Metadados da loja indisponiveis."]),
    ):
        result = build_store_mirror_from_url("https://shopee.com.br/totalmenteseu")

    assert result["ok"]
    assert result["source"] == "scraping"
    assert result["products_found"] == 2
    assert result["warnings"]


def test_mirror_sets_active_store_for_audit_and_chatbot():
    _clean_db()

    with patch(
        "shopee_core.radar_store_mirror_builder._collect_products_via_scraping",
        return_value=({"shopid": "shop-1", "name": "totalmenteseu"}, [_product(1)], []),
    ):
        result = build_store_mirror_from_url("https://shopee.com.br/totalmenteseu")

    active = get_active_store()

    assert result["ok"]
    assert active["has_active_store"]
    assert active["store_uid"] == result["store_uid"]


def test_audit_can_reuse_active_store_without_url(monkeypatch):
    _clean_db()

    with patch(
        "shopee_core.radar_store_mirror_builder._collect_products_via_scraping",
        return_value=({"shopid": "shop-1", "name": "totalmenteseu"}, [_product(1)], []),
    ):
        build_store_mirror_from_url("https://shopee.com.br/totalmenteseu")

    monkeypatch.setenv("SHOPEE_FORCE_RADAR_STORE_FALLBACK", "true")
    from shopee_core.audit_service import load_shop_from_url

    result = load_shop_from_url("")

    assert result["ok"]
    assert result["data"]["username"] == "totalmenteseu"
    assert len(result["data"]["products"]) == 1
