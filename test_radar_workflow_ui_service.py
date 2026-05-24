import os
import uuid
import pytest
from pathlib import Path

# Configura DB em memória isolado para os testes do script
RUN_ID = uuid.uuid4().hex
TEST_DB = Path("data") / f"radar_workflow_ui_test_{RUN_ID}.db"
os.environ["SHOPEE_RADAR_DB_PATH"] = str(TEST_DB)

from shopee_core.radar_db import init_db, get_connection
from shopee_core.radar_workflow_ui_service import (
    list_own_products_for_radar,
    format_own_product_label,
    add_competitor_urls_for_product,
    get_radar_queue_summary,
    get_competitor_table_for_product,
    classify_linked_candidates_for_product
)

def setup_module(module):
    init_db()

def teardown_module(module):
    if TEST_DB.exists():
        try:
            TEST_DB.unlink()
        except:
            pass

def _clear_tables():
    with get_connection() as conn:
        conn.execute("DELETE FROM radar_candidate_links")
        conn.execute("DELETE FROM radar_collection_jobs")
        conn.execute("DELETE FROM radar_competitor_matches")
        conn.execute("DELETE FROM radar_pattern_reports")
        conn.execute("DELETE FROM radar_store_products")
        conn.execute("DELETE FROM radar_stores")
        conn.execute("DELETE FROM radar_products")

def _insert_own_product(uid="own-1", title="Produto Teste", source="own_product"):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO radar_products (product_uid, source_type, marketplace, url, title, price, status, created_at, updated_at)
            VALUES (?, ?, 'shopee', 'http://shopee/1', ?, 100.0, 'active', '2023-01-01', '2023-01-01')
            """,
            (uid, source, title)
        )

# ── Testes ─────────────────────────────────────────────────────────────

def test_list_own_products_empty():
    _clear_tables()
    res = list_own_products_for_radar()
    assert len(res) == 0

def test_list_own_products_finds_own_product():
    _clear_tables()
    _insert_own_product("own-1", "Base")
    res = list_own_products_for_radar()
    assert len(res) == 1
    assert res[0]["title"] == "Base"
    assert res[0]["source"] == "own_product"

def test_format_own_product_label():
    label = format_own_product_label({"title": "Mochila", "price": 50.0, "direct_count": 2})
    assert label == "Mochila — R$ 50.00 — 2 concorrentes diretos"
    
    label2 = format_own_product_label({"price": None, "direct_count": 0})
    assert "Produto sem título" in label2
    assert "Sem preço" in label2

def test_add_competitor_urls_for_product_valid():
    _clear_tables()
    _insert_own_product("own-1")
    
    urls = "https://shopee.com.br/product/123/456\n   \nhttps://produto.mercadolivre.com.br/MLB-123-teste-_JM"
    res = add_competitor_urls_for_product("own-1", urls)
    
    assert res["total_received"] == 2
    assert res["created"] == 2
    assert res["duplicates"] == 0
    assert res["invalid"] == 0
    
    # Verifica candidate links
    with get_connection() as conn:
        links = conn.execute("SELECT * FROM radar_candidate_links").fetchall()
        assert len(links) == 2
        assert links[0]["own_product_uid"] == "own-1"

def test_add_competitor_urls_rejects_invalid():
    _clear_tables()
    urls = "https://invalid.com/123\nnot-a-url"
    res = add_competitor_urls_for_product("own-1", urls)
    assert res["created"] == 0
    assert res["invalid"] == 2

def test_add_competitor_urls_deduplicates_and_reuses():
    _clear_tables()
    _insert_own_product("own-1")
    _insert_own_product("own-2")
    
    url = "https://shopee.com.br/product/1/1"
    
    # own-1 cadastra 2 vezes na mesma string
    res1 = add_competitor_urls_for_product("own-1", f"{url}\n{url}")
    assert res1["created"] == 1
    assert res1["duplicates"] == 1
    
    # own-2 cadastra a mesma URL (reusa radar_product mas cria novo link)
    res2 = add_competitor_urls_for_product("own-2", url)
    assert res2["created"] == 1
    assert res2["duplicates"] == 0
    
    with get_connection() as conn:
        links = conn.execute("SELECT own_product_uid FROM radar_candidate_links").fetchall()
        assert len(links) == 2
        owns = [L["own_product_uid"] for L in links]
        assert "own-1" in owns
        assert "own-2" in owns
        
        # Mas apenas 1 produto candidato foi criado
        prods = conn.execute("SELECT product_uid FROM radar_products WHERE source_type='competitor_candidate'").fetchall()
        assert len(prods) == 1

def test_get_radar_queue_summary():
    _clear_tables()
    _insert_own_product("own-1")
    url = "https://shopee.com.br/product/1/1"
    add_competitor_urls_for_product("own-1", url)
    
    summary = get_radar_queue_summary("own-1")
    assert summary["jobs_pending"] == 1
    assert summary["candidates"] == 1
    
    # Outro produto nao ve a queue do own-1
    _insert_own_product("own-2")
    summary2 = get_radar_queue_summary("own-2")
    assert summary2["jobs_pending"] == 0
    assert summary2["candidates"] == 0

def test_get_competitor_table_for_product_isolates():
    _clear_tables()
    _insert_own_product("own-1")
    url = "https://shopee.com.br/product/1/1"
    add_competitor_urls_for_product("own-1", url)
    
    table = get_competitor_table_for_product("own-1")
    assert len(table) == 1
    assert table[0]["status"] == "coleta_pendente"
    
    table2 = get_competitor_table_for_product("own-2")
    assert len(table2) == 0

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
