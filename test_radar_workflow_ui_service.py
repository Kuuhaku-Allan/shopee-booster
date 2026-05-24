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
        conn.execute("DELETE FROM radar_assets")
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

from unittest.mock import patch, MagicMock
from shopee_core.radar_workflow_ui_service import (
    ensure_collection_jobs_for_linked_candidates,
    run_linked_collection_for_product,
    mark_stale_running_jobs_as_pending_or_failed
)

def test_get_competitor_table_for_product_isolates():
    _clear_tables()
    _insert_own_product("own-1")
    url = "https://shopee.com.br/product/1/1"
    add_competitor_urls_for_product("own-1", url)
    
    table = get_competitor_table_for_product("own-1")
    assert len(table) == 1
    assert table[0]["status"] == "pending"
    
    table2 = get_competitor_table_for_product("own-2")
    assert len(table2) == 0

# 1. Valida que diferentes estados de jobs e produtos resultam nos status ingleses corretos
def test_get_competitor_table_status_mappings():
    _clear_tables()
    _insert_own_product("own-1")
    
    # Adiciona 4 concorrentes
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1/1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/2/2")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/3/3")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/4/4")
    
    table = get_competitor_table_for_product("own-1")
    assert len(table) == 4
    
    cand_uids = [r["product_uid"] for r in table]
    
    with get_connection() as conn:
        # cand 0: mantido como pending
        # cand 1: falha na coleta
        conn.execute("UPDATE radar_collection_jobs SET status = 'failed', last_error = 'Timeout' WHERE product_uid = ?", (cand_uids[1],))
        # cand 2: coletado
        conn.execute("UPDATE radar_products SET status = 'collected', title = 'Coletado' WHERE product_uid = ?", (cand_uids[2],))
        conn.execute("UPDATE radar_collection_jobs SET status = 'done' WHERE product_uid = ?", (cand_uids[2],))
        # cand 3: match direto
        conn.execute("UPDATE radar_products SET status = 'collected', title = 'Match' WHERE product_uid = ?", (cand_uids[3],))
        conn.execute("UPDATE radar_collection_jobs SET status = 'done' WHERE product_uid = ?", (cand_uids[3],))
        conn.execute(
            "INSERT INTO radar_competitor_matches (match_uid, own_product_uid, candidate_product_uid, verdict, relevance_score, created_at, updated_at) VALUES (?, 'own-1', ?, 'competitor_direct', 0.95, '2023-01-01', '2023-01-01')",
            (uuid.uuid4().hex, cand_uids[3])
        )
        
    table = get_competitor_table_for_product("own-1")
    statuses = {r["product_uid"]: r["status"] for r in table}
    
    assert statuses[cand_uids[0]] == "pending"
    assert statuses[cand_uids[1]] == "failed"
    assert statuses[cand_uids[2]] == "collected"
    assert statuses[cand_uids[3]] == "competitor_direct"

# 2. Testa que a reconciliação cria jobs ausentes para candidatos que precisam de coleta
def test_ensure_collection_jobs_creates_missing_jobs():
    _clear_tables()
    _insert_own_product("own-1")
    
    # Cria candidato diretamente sem job de coleta
    cand_uid = uuid.uuid4().hex
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO radar_products (product_uid, source_type, marketplace, url, status, created_at, updated_at) VALUES (?, 'competitor_candidate', 'shopee', 'https://shopee.com.br/product/1/1', 'pending', '2023', '2023')",
            (cand_uid,)
        )
        conn.execute(
            "INSERT INTO radar_candidate_links (link_uid, own_product_uid, candidate_product_uid, source, created_at, updated_at) VALUES (?, 'own-1', ?, 'manual_url', '2023', '2023')",
            (uuid.uuid4().hex, cand_uid)
        )
        
    # Garante que não tem jobs
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) as c FROM radar_collection_jobs WHERE product_uid = ?", (cand_uid,)).fetchone()["c"] == 0
        
    # Reconcilia
    summary = ensure_collection_jobs_for_linked_candidates("own-1")
    assert summary["jobs_created"] == 1
    
    # Agora deve ter 1 job
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) as c FROM radar_collection_jobs WHERE product_uid = ?", (cand_uid,)).fetchone()["c"] == 1

# 3. Testa que jobs que já estão pending ou running são ignorados na reconciliação para evitar duplicação
def test_ensure_collection_jobs_skips_existing_active_jobs():
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1/1")
    
    # Roda uma vez e deve ignorar porque ja existe job pending
    summary = ensure_collection_jobs_for_linked_candidates("own-1")
    assert summary["jobs_created"] == 0
    assert summary["jobs_existing"] == 1

# 4. Testa que produtos já coletados com sucesso (status "collected" ou que já têm título) não ganham novos jobs
def test_ensure_collection_jobs_skips_completed_products():
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1/1")
    
    # Atualiza produto para status="collected" e title="Algum produto"
    with get_connection() as conn:
        conn.execute("UPDATE radar_products SET status = 'collected', title = 'Concorrente Legal' WHERE source_type = 'competitor_candidate'")
        # Marca job antigo como done
        conn.execute("UPDATE radar_collection_jobs SET status = 'done'")
        
    summary = ensure_collection_jobs_for_linked_candidates("own-1")
    assert summary["jobs_created"] == 0
    assert summary["skipped_done"] == 1

def test_ensure_collection_jobs_resets_failed_products():
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1/1")
    
    # Simula falha anterior: atualiza produto para status='failed'
    with get_connection() as conn:
        conn.execute("UPDATE radar_products SET status = 'failed' WHERE source_type = 'competitor_candidate'")
        conn.execute("UPDATE radar_collection_jobs SET status = 'failed'")
        
    summary = ensure_collection_jobs_for_linked_candidates("own-1")
    assert summary["jobs_created"] == 1
    
    with get_connection() as conn:
        prod = conn.execute("SELECT status FROM radar_products WHERE source_type = 'competitor_candidate'").fetchone()
        assert prod["status"] == "pending"
        
        # O último job inserido deve ser pending
        job = conn.execute("SELECT status FROM radar_collection_jobs ORDER BY created_at DESC LIMIT 1").fetchone()
        assert job["status"] == "pending"

# 5. Testa o fluxo completo de coleta com sucesso, usando mock de rc.collect_product_page
@patch("shopee_core.radar_collector.collect_product_page")
def test_run_linked_collection_with_successful_mock(mock_collect):
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1/1")
    
    # Configura retorno simulado do scraper
    mock_collect.return_value = {
        "url": "https://shopee.com.br/product/1/1",
        "marketplace": "shopee",
        "title": "Mochila Top",
        "price": 120.0,
        "shop_name": "Loja Top",
        "rating": 4.8,
        "review_count": 10,
        "sold_count": 50,
        "description": "Uma mochila de qualidade",
        "image_urls": ["http://img1.jpg"],
        "video_urls": [],
        "quality": {"ok": True, "quality_score": 1.0, "errors": [], "warnings": []}
    }
    
    res = run_linked_collection_for_product("own-1", limit=5)
    
    assert res["processed"] == 1
    assert res["succeeded"] == 1
    assert res["failed"] == 0
    assert len(res["errors"]) == 0
    
    # Verifica que o banco de dados foi atualizado
    with get_connection() as conn:
        prod = conn.execute("SELECT status, title, price FROM radar_products WHERE source_type = 'competitor_candidate'").fetchone()
        assert prod["status"] == "collected"
        assert prod["title"] == "Mochila Top"
        assert prod["price"] == 120.0
        
        job = conn.execute("SELECT status FROM radar_collection_jobs").fetchone()
        assert job["status"] == "done"

# 6. Testa que se a coleta retornar bloqueada/vazia, o job e o produto são marcados como falhos
@patch("shopee_core.radar_collector.collect_product_page")
def test_run_linked_collection_with_blocked_mock(mock_collect):
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1/1")
    
    # Simula captcha/bloqueio
    mock_collect.return_value = {
        "url": "https://shopee.com.br/product/1/1",
        "marketplace": "shopee",
        "title": "Acesse sua conta",
        "price": None,
        "quality": {"ok": False, "errors": ["Bloqueio detectado"]}
    }
    
    res = run_linked_collection_for_product("own-1", limit=5)
    
    assert res["processed"] == 1
    assert res["failed"] == 1
    assert res["succeeded"] == 0
    assert len(res["errors"]) == 1
    assert "bloqueada ou incompleta" in res["errors"][0]["error"].lower()
    
    with get_connection() as conn:
        prod = conn.execute("SELECT status FROM radar_products WHERE source_type = 'competitor_candidate'").fetchone()
        assert prod["status"] == "failed"
        
        job = conn.execute("SELECT status, last_error FROM radar_collection_jobs").fetchone()
        assert job["status"] == "failed"
        assert "bloqueada ou incompleta" in job["last_error"].lower()

# 7. Testa que se a qualidade for ruim, o job falha
@patch("shopee_core.radar_collector.collect_product_page")
def test_run_linked_collection_with_low_quality_mock(mock_collect):
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1/1")
    
    # Qualidade ruim sem título ou com erro de qualidade
    mock_collect.return_value = {
        "url": "https://shopee.com.br/product/1/1",
        "marketplace": "shopee",
        "title": "",
        "price": None,
        "quality": {
            "ok": False,
            "errors": ["Titulo vazio.", "Preco suspeito."]
        }
    }
    
    res = run_linked_collection_for_product("own-1", limit=5)
    
    assert res["processed"] == 1
    assert res["failed"] == 1
    assert "baixa qualidade" in res["errors"][0]["error"].lower()
    
    with get_connection() as conn:
        job = conn.execute("SELECT status, last_error FROM radar_collection_jobs").fetchone()
        assert job["status"] == "failed"
        assert "baixa qualidade" in job["last_error"].lower()

# 8. Testa o comportamento com marketplace não suportado
def test_run_linked_collection_with_unsupported_marketplace():
    _clear_tables()
    _insert_own_product("own-1")
    
    cand_uid = uuid.uuid4().hex
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO radar_products (product_uid, source_type, marketplace, url, status, created_at, updated_at) VALUES (?, 'competitor_candidate', 'unknown', 'https://unknown.com/1', 'pending', '2023', '2023')",
            (cand_uid,)
        )
        conn.execute(
            "INSERT INTO radar_candidate_links (link_uid, own_product_uid, candidate_product_uid, source, created_at, updated_at) VALUES (?, 'own-1', ?, 'manual_url', '2023', '2023')",
            (uuid.uuid4().hex, cand_uid)
        )
        conn.execute(
            "INSERT INTO radar_collection_jobs (job_uid, product_uid, url, job_type, status, created_at, updated_at) VALUES (?, ?, 'https://unknown.com/1', 'product_data', 'pending', '2023', '2023')",
            (uuid.uuid4().hex, cand_uid)
        )
        
    res = run_linked_collection_for_product("own-1", limit=5)
    assert res["processed"] == 1
    assert res["failed"] == 1
    assert "não suportado" in res["errors"][0]["error"].lower() or "nao tem coletor" in res["errors"][0]["error"].lower() or "unknown" in res["errors"][0]["error"].lower()
    
    with get_connection() as conn:
        job = conn.execute("SELECT status, last_error FROM radar_collection_jobs").fetchone()
        assert job["status"] == "failed"
        assert "suportado" in job["last_error"].lower() or "nao tem coletor" in job["last_error"].lower() or "unknown" in job["last_error"].lower()

# 9. Testa o tratamento de exceções durante o download/coleta de página
@patch("shopee_core.radar_collector.collect_product_page")
def test_run_linked_collection_exception_handling(mock_collect):
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1/1")
    
    mock_collect.side_effect = RuntimeError("Playwright connection refused")
    
    res = run_linked_collection_for_product("own-1", limit=5)
    
    assert res["processed"] == 1
    assert res["failed"] == 1
    assert "connection refused" in res["errors"][0]["error"].lower()
    
    with get_connection() as conn:
        job = conn.execute("SELECT status, last_error FROM radar_collection_jobs").fetchone()
        assert job["status"] == "failed"
        assert "connection refused" in job["last_error"].lower()

# 10. Valida que o limite de coleta é estritamente respeitado
@patch("shopee_core.radar_collector.collect_product_page")
def test_run_linked_collection_limits_concurrency(mock_collect):
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1/1\nhttps://shopee.com.br/product/2/2")
    
    mock_collect.return_value = {
        "url": "https://shopee.com.br/product/1/1",
        "marketplace": "shopee",
        "title": "Mochila",
        "price": 100.0,
        "quality": {"ok": True}
    }
    
    res = run_linked_collection_for_product("own-1", limit=1)
    
    assert res["processed"] == 1
    assert res["succeeded"] == 1
    
    with get_connection() as conn:
        jobs = conn.execute("SELECT status FROM radar_collection_jobs ORDER BY created_at ASC").fetchall()
        assert len(jobs) == 2
        assert jobs[0]["status"] == "done"
        assert jobs[1]["status"] == "pending"

# 11. Testes da Fase R7.2C: Timeouts, recuperação de jobs, cancelamento e bloqueios
@patch("shopee_core.radar_collector.collect_product_page")
def test_run_linked_collection_timeout_marks_failed(mock_collect):
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1/1\nhttps://shopee.com.br/product/2/2")
    
    # Primeiro mock falha por timeout, segundo Mock tem sucesso
    mock_collect.side_effect = [
        TimeoutError("timeout_after_30s"),
        {
            "url": "https://shopee.com.br/product/2/2",
            "marketplace": "shopee",
            "title": "Produto 2",
            "price": 120.0,
            "quality": {"ok": True}
        }
    ]
    
    res = run_linked_collection_for_product("own-1", limit=2)
    assert res["processed"] == 2
    assert res["failed"] == 1
    assert res["succeeded"] == 1
    
    with get_connection() as conn:
        jobs = conn.execute("SELECT status, last_error FROM radar_collection_jobs ORDER BY url ASC").fetchall()
        assert jobs[0]["status"] == "failed"
        assert "timeout_after_30s" in jobs[0]["last_error"]
        assert jobs[1]["status"] == "done"

def test_stale_running_jobs_resets_candidates():
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1/1\nhttps://shopee.com.br/product/2/2")
    
    from datetime import datetime, timedelta
    old_time = (datetime.utcnow() - timedelta(minutes=15)).isoformat()
    now_time = datetime.utcnow().isoformat()
    
    with get_connection() as conn:
        conn.execute("UPDATE radar_collection_jobs SET status = 'running', updated_at = ? WHERE url = 'https://shopee.com.br/product/1/1'", (old_time,))
        conn.execute("UPDATE radar_collection_jobs SET status = 'running', updated_at = ? WHERE url = 'https://shopee.com.br/product/2/2'", (now_time,))
        
    recovered = mark_stale_running_jobs_as_pending_or_failed(max_age_minutes=10)
    assert recovered == 1
    
    with get_connection() as conn:
        job1 = conn.execute("SELECT status, last_error FROM radar_collection_jobs WHERE url = 'https://shopee.com.br/product/1/1'").fetchone()
        assert job1["status"] == "failed"
        assert job1["last_error"] == "stale_running_job_recovered"
        
        prod1 = conn.execute("SELECT status FROM radar_products WHERE url = 'https://shopee.com.br/product/1/1'").fetchone()
        assert prod1["status"] == "pending"
        
        job2 = conn.execute("SELECT status FROM radar_collection_jobs WHERE url = 'https://shopee.com.br/product/2/2'").fetchone()
        assert job2["status"] == "running"

@patch("shopee_core.radar_collector.collect_product_page")
def test_run_linked_collection_cancellation_marks_skipped(mock_collect):
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1/1\nhttps://shopee.com.br/product/2/2")
    
    from pathlib import Path
    flag_file = Path("data/radar_stop_collection.flag")
    
    def simulate_cancel(*args, **kwargs):
        flag_file.parent.mkdir(parents=True, exist_ok=True)
        flag_file.write_text("stop")
        return {
            "url": "https://shopee.com.br/product/1/1",
            "marketplace": "shopee",
            "title": "Produto 1",
            "price": 50.0,
            "quality": {"ok": True}
        }
    
    mock_collect.side_effect = simulate_cancel
    
    res = run_linked_collection_for_product("own-1", limit=2)
    assert res["processed"] == 1
    assert res["succeeded"] == 1
    assert res["skipped"] == 1
    assert not flag_file.exists()

@patch("shopee_core.radar_collector.collect_product_page")
def test_run_linked_collection_blocked_login_required(mock_collect):
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1/1")
    
    mock_collect.side_effect = RuntimeError("blocked_or_login_required")
    
    res = run_linked_collection_for_product("own-1", limit=1)
    assert res["processed"] == 1
    assert res["failed"] == 1
    assert res["errors"][0]["error"] == "blocked_or_login_required"
    
    with get_connection() as conn:
        job = conn.execute("SELECT status, last_error FROM radar_collection_jobs").fetchone()
        assert job["status"] == "failed"
        assert job["last_error"] == "blocked_or_login_required"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
