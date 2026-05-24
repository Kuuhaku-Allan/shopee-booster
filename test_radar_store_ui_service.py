import os
import sqlite3
import pytest
from pathlib import Path
import uuid
import importlib

from shopee_core.radar_db import DB_PATH, get_connection, init_db
from shopee_core.radar_store_service import save_store_snapshot, get_cached_store_products
from shopee_core.radar_store_ui_service import (
    get_db_diagnostic,
    list_store_mirrors,
    get_store_mirror_summary,
    list_store_mirror_products,
    format_store_label,
)

def _setup_db():
    from shopee_core.radar_db import init_db, get_connection
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM radar_store_products")
        conn.execute("DELETE FROM radar_stores")
        conn.execute("DELETE FROM radar_assets")
        conn.execute("DELETE FROM radar_reviews")
        conn.execute("DELETE FROM radar_collection_jobs")
        conn.execute("DELETE FROM radar_competitor_matches")
        conn.execute("DELETE FROM radar_pattern_reports")
        conn.execute("DELETE FROM radar_products")

def _store(slug="test-store"):
    return {
        "shop_uid": slug + "-123",
        "shop_slug": slug,
        "shop_name": f"Loja {slug}",
        "marketplace": "shopee",
        "source_url": f"https://shopee.com.br/{slug}"
    }

def _product(itemid, title, price=100.0, image="img.jpg", radar_uid=None):
    p = {
        "itemid": itemid,
        "name": title,
        "price": price,
        "image": image,
    }
    if radar_uid:
        p["radar_product_uid"] = radar_uid
    return p

# ── Testes ─────────────────────────────────────────────────────────────

def test_db_diagnostic_no_db_does_not_break():
    from unittest.mock import patch
    from pathlib import Path
    dummy = Path("Z:\\caminho\\inexistente\\radar.db")
    with patch("shopee_core.radar_store_ui_service.DB_PATH", dummy):
        diag = get_db_diagnostic()
        assert diag["db_exists"] is False
        assert diag["total_stores"] == 0

def test_list_store_mirrors_empty_returns_empty():
    _setup_db()
    stores = list_store_mirrors()
    assert stores == []

def test_format_store_label_handles_missing_fields():
    # Loja completa
    assert "lojateste" in format_store_label({"shop_slug": "lojateste", "product_count": 5, "last_snapshot_at": "2026-04-27T10:00:00Z"})
    
    # Loja sem nada
    assert format_store_label({}) == "Loja desconhecida"
    
    # Loja com data nula
    assert "Nunca" in format_store_label({"shop_slug": "lojanula", "last_snapshot_at": None})

def test_list_store_mirrors_returns_counts():
    _setup_db()
    st = _store("loja-counts")
    save_store_snapshot(st, [
        _product("p1", "Prod 1"),
        _product("p2", "Prod 2")
    ], source="test")
    
    stores = list_store_mirrors()
    assert len(stores) == 1
    s = stores[0]
    assert s["shop_slug"] == "loja-counts"
    assert s["product_count"] == 2
    assert s["active_count"] == 2

def test_get_store_mirror_summary_counts_by_status():
    _setup_db()
    st = _store("loja-summary")
    summary1 = save_store_snapshot(st, [_product("p1", "Prod 1"), _product("p2", "Prod 2")], source="test")
    uid = summary1["store_uid"]
    
    # Salvar de novo, removendo p2 e alterando preço do p1
    save_store_snapshot(st, [_product("p1", "Prod 1", price=200)], source="test2")
    
    summary = get_store_mirror_summary(uid)
    assert summary["ok"] is True
    assert summary["total_products"] == 2
    assert summary["active"] == 1
    assert summary["missing"] == 1
    assert summary["changed"] == 1  # p1 alterado conta no 'active' do store_service, e tb flag 'changed'
    assert summary["counts_by_status"]["missing"] == 1
    assert summary["counts_by_status"]["changed"] == 1

def test_list_store_mirror_products_filters_by_status():
    _setup_db()
    st = _store("loja-filters")
    summary1 = save_store_snapshot(st, [_product("p1", "Prod 1"), _product("p2", "Prod 2"), _product("p3", "Prod 3")], source="test")
    uid = summary1["store_uid"]
    
    # Snapshot 2: p1 preco muda (changed), p2 some (missing), p3 igual, p4 novo (active)
    save_store_snapshot(st, [_product("p1", "Prod 1", price=999), _product("p3", "Prod 3"), _product("p4", "Prod 4")], source="test2")
    
    prods_all = list_store_mirror_products(uid, status_filter="Todos")
    if len(prods_all) != 4: print("ALL:", [p["title"] for p in prods_all])
    assert len(prods_all) == 4
    
    prods_active = list_store_mirror_products(uid, status_filter="active")
    assert len(prods_active) == 2 # p3 (igual) e p4 (novo)
    
    prods_changed = list_store_mirror_products(uid, status_filter="changed")
    assert len(prods_changed) == 1 # p1
    assert prods_changed[0]["title"] == "Prod 1"
    
    prods_missing = list_store_mirror_products(uid, status_filter="missing")
    assert len(prods_missing) == 1 # p2

def test_inexistent_store_returns_friendly():
    _setup_db()
    summary = get_store_mirror_summary("inexistente-123")
    assert summary["ok"] is False

def test_product_without_image_does_not_break():
    _setup_db()
    st = _store("loja-noimg")
    summary = save_store_snapshot(st, [_product("p1", "Prod No Image", image=None)], source="test")
    uid = summary["store_uid"]
    
    prods = list_store_mirror_products(uid, "Todos")
    if len(prods) != 1: print("NOIMG:", prods)
    assert len(prods) == 1
    assert prods[0]["image_url"] in [None, ""]

def test_product_without_radar_product_uid_does_not_break():
    _setup_db()
    st = _store("loja-noradar")
    summary = save_store_snapshot(st, [_product("p1", "Prod No Radar")], source="test")
    uid = summary["store_uid"]
    
    # Força remoção do radar_product_uid no banco para simular
    with get_connection() as conn:
        conn.execute("UPDATE radar_store_products SET radar_product_uid = NULL WHERE store_uid = ?", (uid,))
        
    prods = list_store_mirror_products(uid, "Todos")
    if len(prods) != 1: print("NORADAR:", prods)
    assert len(prods) == 1
    assert prods[0]["radar_product_uid"] is None
    assert prods[0]["display_source"] == "unknown"


if __name__ == "__main__":
    tests = [
        ("no_db_does_not_break", test_db_diagnostic_no_db_does_not_break),
        ("empty_returns_empty", test_list_store_mirrors_empty_returns_empty),
        ("handles_missing_fields", test_format_store_label_handles_missing_fields),
        ("returns_counts", test_list_store_mirrors_returns_counts),
        ("counts_by_status", test_get_store_mirror_summary_counts_by_status),
        ("filters_by_status", test_list_store_mirror_products_filters_by_status),
        ("inexistent_store_friendly", test_inexistent_store_returns_friendly),
        ("without_image_ok", test_product_without_image_does_not_break),
        ("without_radar_uid_ok", test_product_without_radar_product_uid_does_not_break),
    ]

    passed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"PASS - {name}")
        except Exception as exc:
            print(f"FAIL - {name}: {exc}")
            import traceback
            traceback.print_exc()

    print(f"\\nTotal: {passed}/{len(tests)} testes passaram")
