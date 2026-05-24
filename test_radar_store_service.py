#!/usr/bin/env python3
"""
test_radar_store_service.py - R7.0 local store mirror tests.

Run:
    python test_radar_store_service.py
"""

from __future__ import annotations

import atexit
import os
import uuid
from pathlib import Path


RUN_ID = uuid.uuid4().hex
TEST_DB_PATH = Path("data") / f"radar_store_service_test_{RUN_ID}.db"
os.environ["SHOPEE_RADAR_DB_PATH"] = str(TEST_DB_PATH)


def _cleanup_test_db() -> None:
    try:
        import gc
        import sqlite3

        gc.collect()
        conn = sqlite3.connect(TEST_DB_PATH)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
    except Exception:
        pass
    for suffix in ("", "-wal", "-shm"):
        try:
            Path(str(TEST_DB_PATH) + suffix).unlink(missing_ok=True)
        except Exception:
            pass


atexit.register(_cleanup_test_db)

from shopee_core.radar_db import DB_PATH, get_connection
from shopee_core.radar_store_service import (
    diff_store_snapshot,
    find_radar_product_for_store_product,
    get_cached_store_products,
    get_store_snapshot_status,
    save_store_snapshot,
    upsert_store,
)


def _store(case: str) -> dict:
    return {
        "shop_uid": f"shop-{case}-{RUN_ID}",
        "shop_slug": f"slug-{case}-{RUN_ID}",
        "shop_name": f"Loja {case}",
        "marketplace": "shopee",
        "source_url": f"https://shopee.com.br/slug-{case}-{RUN_ID}",
    }


def _product(itemid: str, title: str, price: float, image: str = "img-a") -> dict:
    return {
        "itemid": itemid,
        "shopid": "shop-test",
        "name": title,
        "price": price,
        "image": image,
    }


def _count(table: str, where: str = "1=1", params: tuple = ()) -> int:
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) AS total FROM {table} WHERE {where}",
            params,
        ).fetchone()
        return int(row["total"])


def test_upsert_store_creates_store():
    store = upsert_store(
        shop_uid=_store("upsert")["shop_uid"],
        shop_slug=_store("upsert")["shop_slug"],
        shop_name=_store("upsert")["shop_name"],
        marketplace="shopee",
        source_url=_store("upsert")["source_url"],
    )

    assert store["store_uid"]
    assert store["shop_slug"] == _store("upsert")["shop_slug"]
    assert DB_PATH.exists()
    return True


def test_save_store_snapshot_saves_products():
    summary = save_store_snapshot(
        _store("snapshot"),
        [
            _product("1001", "Mochila Infantil Rosa", 93.1),
            _product("1002", "Mochila Escolar Rodinhas", 120.0),
        ],
        source="test",
    )

    cached = get_cached_store_products(shop_slug=_store("snapshot")["shop_slug"])
    assert summary["created"] == 2
    assert summary["total_received"] == 2
    assert len(cached) == 2
    return True


def test_save_store_snapshot_creates_own_radar_products():
    summary = save_store_snapshot(
        _store("own"),
        [_product("2001", "Mochila Princesa Own", 88.9)],
        source="test",
    )

    cached = get_cached_store_products(store_uid=summary["store_uid"])
    assert cached[0]["radar_product_uid"]
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM radar_products WHERE product_uid = ?",
            (cached[0]["radar_product_uid"],),
        ).fetchone()
    assert row["source_type"] == "own_product"
    assert row["status"] == "collected"
    return True


def test_repeated_snapshot_does_not_duplicate_products():
    store = _store("repeat")
    products = [
        _product("3001", "Mochila Repetida A", 50),
        _product("3002", "Mochila Repetida B", 60),
    ]

    first = save_store_snapshot(store, products, source="test")
    second = save_store_snapshot(store, products, source="test")

    assert first["created"] == 2
    assert second["created"] == 0
    assert second["unchanged"] == 2
    assert _count("radar_store_products", "store_uid = ?", (first["store_uid"],)) == 2
    return True


def test_price_change_marks_changed_and_updated():
    store = _store("price")
    first = save_store_snapshot(
        store,
        [_product("4001", "Mochila Preco", 70)],
        source="test",
    )
    second = save_store_snapshot(
        store,
        [_product("4001", "Mochila Preco", 79.9)],
        source="test",
    )

    cached = get_cached_store_products(store_uid=first["store_uid"])
    assert second["updated"] == 1
    assert cached[0]["cache_status"] == "changed"
    assert cached[0]["price"] == 79.9
    return True


def test_missing_product_is_marked_missing():
    store = _store("missing")
    first = save_store_snapshot(
        store,
        [
            _product("5001", "Mochila Presente", 40),
            _product("5002", "Mochila Ausente", 45),
        ],
        source="test",
    )
    second = save_store_snapshot(
        store,
        [_product("5001", "Mochila Presente", 40)],
        source="test",
    )

    cached = get_cached_store_products(store_uid=first["store_uid"])
    status = get_store_snapshot_status(first["store_uid"])
    assert second["missing"] == 1
    assert len(cached) == 1
    assert status["missing"] == 1
    return True


def test_get_cached_store_products_returns_active_products():
    summary = save_store_snapshot(
        _store("cache"),
        [_product("6001", "Mochila Cache", 101)],
        source="test",
    )

    cached = get_cached_store_products(shop_uid=_store("cache")["shop_uid"])
    assert len(cached) == 1
    assert cached[0]["name"] == "Mochila Cache"
    assert cached[0]["source"] == "radar_store_mirror"
    assert cached[0]["store_uid"] == summary["store_uid"]
    return True


def test_diff_store_snapshot_detects_new_product():
    summary = save_store_snapshot(
        _store("diff-new"),
        [_product("7001", "Mochila Base", 30)],
        source="test",
    )

    diff = diff_store_snapshot(
        summary["store_uid"],
        [
            _product("7001", "Mochila Base", 30),
            _product("7002", "Mochila Nova", 35),
        ],
    )
    assert diff["summary"]["new"] == 1
    assert diff["new_products"][0]["marketplace_product_id"] == "7002"
    return True


def test_diff_store_snapshot_detects_price_change():
    summary = save_store_snapshot(
        _store("diff-price"),
        [_product("8001", "Mochila Diff Preco", 44)],
        source="test",
    )

    diff = diff_store_snapshot(
        summary["store_uid"],
        [_product("8001", "Mochila Diff Preco", 48.5)],
    )
    assert diff["summary"]["price_changed"] == 1
    return True


def test_empty_cache_does_not_break():
    cached = get_cached_store_products(shop_slug=f"missing-{RUN_ID}")
    assert cached == []
    return True


def test_find_radar_product_for_store_product():
    summary = save_store_snapshot(
        _store("find"),
        [_product("9001", "Mochila Vinculada", 55)],
        source="test",
    )
    cached = get_cached_store_products(store_uid=summary["store_uid"])
    product = find_radar_product_for_store_product(cached[0]["store_product_uid"])

    assert product
    assert product["product_uid"] == cached[0]["radar_product_uid"]
    assert product["source_type"] == "own_product"
    return True


if __name__ == "__main__":
    print("\nTESTE R7.0 - Espelho da Loja no Radar\n")

    tests = [
        ("upsert_store cria loja", test_upsert_store_creates_store),
        ("save_store_snapshot salva produtos", test_save_store_snapshot_saves_products),
        ("save_store_snapshot cria radar_products own_product", test_save_store_snapshot_creates_own_radar_products),
        ("snapshot repetido nao duplica produtos", test_repeated_snapshot_does_not_duplicate_products),
        ("preco alterado marca changed/updated", test_price_change_marks_changed_and_updated),
        ("produto ausente vira missing", test_missing_product_is_marked_missing),
        ("get_cached_store_products retorna ativos", test_get_cached_store_products_returns_active_products),
        ("diff detecta produto novo", test_diff_store_snapshot_detects_new_product),
        ("diff detecta alteracao de preco", test_diff_store_snapshot_detects_price_change),
        ("cache vazio nao quebra", test_empty_cache_does_not_break),
        ("find_radar_product_for_store_product vincula Radar", test_find_radar_product_for_store_product),
    ]

    passed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"PASS - {name}")
        except Exception as exc:
            print(f"FAIL - {name}: {exc}")
            raise

    print(f"\nTotal: {passed}/{len(tests)} testes passaram")
    print(f"DB: {DB_PATH}")
    _cleanup_test_db()
