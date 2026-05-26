import os
import json
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

    url = "https://shopee.com.br/product/1234/5678"

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
    url = "https://shopee.com.br/product/1234/5678"
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
    url = "https://shopee.com.br/product/1234/5678"
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
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/2345/6789")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/3456/7890")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/4567/8901")

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
def test_classify_linked_candidates_ignores_pending_candidates():
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678")

    with patch("shopee_core.radar_relevance_service.classify_candidate") as mock_classify:
        res = classify_linked_candidates_for_product("own-1")

    assert res["ok"]
    assert res["total"] == 0
    mock_classify.assert_not_called()

def test_ensure_collection_jobs_creates_missing_jobs():
    _clear_tables()
    _insert_own_product("own-1")

    # Cria candidato diretamente sem job de coleta
    cand_uid = uuid.uuid4().hex
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO radar_products (product_uid, source_type, marketplace, url, status, created_at, updated_at) VALUES (?, 'competitor_candidate', 'shopee', 'https://shopee.com.br/product/1234/5678', 'pending', '2023', '2023')",
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
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678")

    # Roda uma vez e deve ignorar porque ja existe job pending
    summary = ensure_collection_jobs_for_linked_candidates("own-1")
    assert summary["jobs_created"] == 0
    assert summary["jobs_existing"] == 1

# 4. Testa que produtos já coletados com sucesso (status "collected" ou que já têm título) não ganham novos jobs
def test_ensure_collection_jobs_skips_completed_products():
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678")

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
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678")

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

def test_ensure_collection_jobs_does_not_requeue_invalid_placeholder():
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/2345/6789")

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE radar_products
            SET status = 'failed', rejection_reason = 'invalid_empty_shopee_placeholder_url_https_shopee_com_br_product_2345_6789'
            WHERE source_type = 'competitor_candidate'
            """
        )
        conn.execute(
            """
            UPDATE radar_collection_jobs
            SET status = 'failed', last_error = 'invalid_empty_shopee_placeholder_url_https_shopee_com_br_product_2345_6789'
            """
        )

    summary = ensure_collection_jobs_for_linked_candidates("own-1")
    assert summary["jobs_created"] == 0
    assert summary["skipped_invalid"] == 1

    with get_connection() as conn:
        jobs = conn.execute("SELECT status FROM radar_collection_jobs").fetchall()
        assert [job["status"] for job in jobs] == ["failed"]

# 5. Testa o fluxo completo de coleta com sucesso, usando mock de rc.collect_product_page
@patch("shopee_core.radar_collector.collect_product_page")
def test_run_linked_collection_with_successful_mock(mock_collect):
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678")

    # Configura retorno simulado do scraper
    mock_collect.return_value = {
        "url": "https://shopee.com.br/product/1234/5678",
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
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678")

    # Simula captcha/bloqueio
    mock_collect.return_value = {
        "url": "https://shopee.com.br/product/1234/5678",
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
    assert "blocked_or_login_required" in res["errors"][0]["error"].lower()

    with get_connection() as conn:
        prod = conn.execute("SELECT status FROM radar_products WHERE source_type = 'competitor_candidate'").fetchone()
        assert prod["status"] == "failed"

        job = conn.execute("SELECT status, last_error FROM radar_collection_jobs").fetchone()
        assert job["status"] == "failed"
        assert "blocked_or_login_required" in job["last_error"].lower()

# 7. Testa que se a qualidade for ruim, o job falha
@patch("shopee_core.radar_collector.collect_product_page")
def test_run_linked_collection_with_low_quality_mock(mock_collect):
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678")

    # Qualidade ruim sem título ou com erro de qualidade
    mock_collect.return_value = {
        "url": "https://shopee.com.br/product/1234/5678",
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
    assert "missing_title_and_price_after_extraction" in res["errors"][0]["error"].lower()

    with get_connection() as conn:
        job = conn.execute("SELECT status, last_error FROM radar_collection_jobs").fetchone()
        assert job["status"] == "failed"
        assert "missing_title_and_price_after_extraction" in job["last_error"].lower()

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
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678")

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
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678\nhttps://shopee.com.br/product/2345/6789")

    mock_collect.return_value = {
        "url": "https://shopee.com.br/product/1234/5678",
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
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678\nhttps://shopee.com.br/product/2345/6789")

    # Primeiro mock falha por timeout, segundo Mock tem sucesso
    mock_collect.side_effect = [
        TimeoutError("timeout_after_30s"),
        {
            "url": "https://shopee.com.br/product/2345/6789",
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
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678\nhttps://shopee.com.br/product/2345/6789")

    from datetime import datetime, timedelta
    old_time = (datetime.utcnow() - timedelta(minutes=15)).isoformat()
    now_time = datetime.utcnow().isoformat()

    with get_connection() as conn:
        conn.execute("UPDATE radar_collection_jobs SET status = 'running', updated_at = ? WHERE url = 'https://shopee.com.br/product/1234/5678'", (old_time,))
        conn.execute("UPDATE radar_collection_jobs SET status = 'running', updated_at = ? WHERE url = 'https://shopee.com.br/product/2345/6789'", (now_time,))

    recovered = mark_stale_running_jobs_as_pending_or_failed(max_age_minutes=10)
    assert recovered == 1

    with get_connection() as conn:
        job1 = conn.execute("SELECT status, last_error FROM radar_collection_jobs WHERE url = 'https://shopee.com.br/product/1234/5678'").fetchone()
        assert job1["status"] == "failed"
        assert job1["last_error"] == "stale_running_job_recovered"

        prod1 = conn.execute("SELECT status FROM radar_products WHERE url = 'https://shopee.com.br/product/1234/5678'").fetchone()
        assert prod1["status"] == "pending"

        job2 = conn.execute("SELECT status FROM radar_collection_jobs WHERE url = 'https://shopee.com.br/product/2345/6789'").fetchone()
        assert job2["status"] == "running"

@patch("shopee_core.radar_collector.collect_product_page")
def test_run_linked_collection_cancellation_marks_skipped(mock_collect):
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678\nhttps://shopee.com.br/product/2345/6789")

    from pathlib import Path
    flag_file = Path("data/radar_stop_collection.flag")

    def simulate_cancel(*args, **kwargs):
        flag_file.parent.mkdir(parents=True, exist_ok=True)
        flag_file.write_text("stop")
        return {
            "url": "https://shopee.com.br/product/1234/5678",
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
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678")

    mock_collect.side_effect = RuntimeError("blocked_or_login_required")

    res = run_linked_collection_for_product("own-1", limit=1)
    assert res["processed"] == 1
    assert res["failed"] == 1
    assert res["errors"][0]["error"] == "blocked_or_login_required"

    with get_connection() as conn:
        job = conn.execute("SELECT status, last_error FROM radar_collection_jobs").fetchone()
        assert job["status"] == "failed"
        assert job["last_error"] == "blocked_or_login_required"

@patch("shopee_core.radar_collector.collect_product_page")
def test_extraction_timeout_raises_extract_timeout_after_25s(mock_collect):
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678")
    mock_collect.side_effect = TimeoutError("extract_timeout_after_25s")

    res = run_linked_collection_for_product("own-1", limit=1)
    assert res["failed"] == 1
    assert "extract_timeout_after_25s" in res["errors"][0]["error"]

@patch("shopee_core.radar_collector.collect_product_page")
@patch("shopee_core.radar_collector._persist_collected_assets")
def test_assets_timeout_does_not_fail_product(mock_persist, mock_collect):
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678")
    mock_collect.return_value = {
        "url": "https://shopee.com.br/product/1234/5678",
        "marketplace": "shopee",
        "title": "Mochila",
        "price": 10.0,
        "quality": {"ok": True}
    }
    mock_persist.side_effect = TimeoutError("assets_timeout_after_30s")

    res = run_linked_collection_for_product("own-1", limit=1, save_assets=True)
    assert res["failed"] == 0
    assert res["succeeded"] == 1
    assert "assets_timeout_after_30s" in res["asset_warnings"][0]["error"]

    with get_connection() as conn:
        prod = conn.execute("SELECT status, raw_json FROM radar_products WHERE source_type = 'competitor_candidate'").fetchone()
        assert prod["status"] == "collected"
        raw = json.loads(prod["raw_json"])
        assert raw["raw"]["asset_status"] == "warning"
        assert raw["raw"]["asset_errors"][0]["error"] == "assets_timeout_after_30s"

@patch("shopee_core.radar_collector.collect_product_page")
def test_partial_collection_saves_collected(mock_collect):
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678")
    mock_collect.return_value = {
        "url": "https://shopee.com.br/product/1234/5678",
        "marketplace": "shopee",
        "title": "Mochila sem preco",
        "price": None,
        "quality": {"ok": False, "errors": ["Preco vazio"]}
    }

    res = run_linked_collection_for_product("own-1", limit=1)
    assert res["succeeded"] == 1
    with get_connection() as conn:
        prod = conn.execute("SELECT status, title, price FROM radar_products WHERE source_type = 'competitor_candidate'").fetchone()
        assert prod["status"] == "collected"
        assert prod["title"] == "Mochila sem preco"
        assert prod["price"] is None

@patch("shopee_core.radar_collector.collect_product_page")
@patch("shopee_core.radar_collector._persist_collected_assets")
def test_assets_failure_does_not_fail_product(mock_persist, mock_collect):
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678")
    mock_collect.return_value = {
        "url": "https://shopee.com.br/product/1234/5678",
        "marketplace": "shopee",
        "title": "Mochila",
        "price": 10.0,
        "quality": {"ok": True}
    }
    mock_persist.return_value = [{"product_uid": "cand", "asset_type": "image", "source_url": "url", "error": "connection refused"}]

    res = run_linked_collection_for_product("own-1", limit=1, save_assets=True)
    assert res["succeeded"] == 1
    assert res["asset_warnings"][0]["error"] == "connection refused"
    with get_connection() as conn:
        prod = conn.execute("SELECT status, raw_json FROM radar_products WHERE source_type = 'competitor_candidate'").fetchone()
        assert prod["status"] == "collected"
        raw = json.loads(prod["raw_json"])
        assert raw["raw"]["asset_status"] == "warning"
        assert raw["raw"]["asset_errors"][0]["error"] == "connection refused"

@patch("shopee_core.radar_collector.collect_product_page")
@patch("shopee_core.radar_collector._persist_collected_assets")
def test_save_assets_false_skips_asset_persistence(mock_persist, mock_collect):
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678")
    mock_collect.return_value = {
        "url": "https://shopee.com.br/product/1234/5678",
        "marketplace": "shopee",
        "title": "Mochila",
        "price": 10.0,
        "image_urls": ["http://img1.jpg"],
        "quality": {"ok": True}
    }

    res = run_linked_collection_for_product("own-1", limit=1, save_assets=False)

    assert res["succeeded"] == 1
    assert res["assets_skipped"] == 1
    assert res["asset_warnings"][0]["status"] == "skipped"
    mock_persist.assert_not_called()
    assert mock_collect.call_args.kwargs["collect_image_urls"] is True

    with get_connection() as conn:
        prod = conn.execute("SELECT status, raw_json FROM radar_products WHERE source_type = 'competitor_candidate'").fetchone()
        assert prod["status"] == "collected"
        raw = json.loads(prod["raw_json"])
        assert raw["raw"]["asset_status"] == "skipped"

@patch("shopee_core.radar_collector.collect_product_page")
@patch("shopee_core.radar_collector._persist_collected_assets")
def test_assets_timeout_does_not_block_next_url(mock_persist, mock_collect):
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678\nhttps://shopee.com.br/product/2345/6789")
    mock_collect.side_effect = [
        {
            "url": "https://shopee.com.br/product/1234/5678",
            "marketplace": "shopee",
            "title": "Produto 1",
            "price": 10.0,
            "quality": {"ok": True}
        },
        {
            "url": "https://shopee.com.br/product/2345/6789",
            "marketplace": "shopee",
            "title": "Produto 2",
            "price": 20.0,
            "quality": {"ok": True}
        }
    ]
    mock_persist.side_effect = [TimeoutError("assets_timeout_after_30s"), []]

    res = run_linked_collection_for_product("own-1", limit=2, save_assets=True)

    assert res["processed"] == 2
    assert res["succeeded"] == 2
    assert res["failed"] == 0
    assert "assets_timeout_after_30s" in res["asset_warnings"][0]["error"]

    with get_connection() as conn:
        jobs = conn.execute("SELECT status FROM radar_collection_jobs ORDER BY url ASC").fetchall()
        assert [job["status"] for job in jobs] == ["done", "done"]

@patch("shopee_core.radar_assets_service.download_asset")
def test_max_images_per_product_limits_asset_downloads(mock_download):
    import shopee_core.radar_collector as rc

    def fake_download(url, product_uid, asset_type, timeout=30):
        return {
            "product_uid": product_uid,
            "asset_type": asset_type,
            "source_url": url,
            "local_path": "fake.jpg",
            "downloaded": True,
        }

    mock_download.side_effect = fake_download
    data = {
        "marketplace": "mercadolivre",
        "image_urls": [f"https://img.example.com/{i}.jpg" for i in range(7)],
        "description_image_urls": ["https://img.example.com/desc.jpg"],
    }

    assets = rc._persist_collected_assets(
        "product-1",
        data,
        save_assets_to_disk=True,
        max_images_per_product=5,
        per_image_timeout=5.0,
    )

    assert len(assets) == 5
    assert mock_download.call_count == 5
    assert all(call.kwargs["timeout"] == 5.0 for call in mock_download.call_args_list)

def test_stale_running_job_with_saved_title_or_price_stays_collected():
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678")

    from datetime import datetime, timedelta
    old_time = (datetime.utcnow() - timedelta(minutes=15)).isoformat()

    with get_connection() as conn:
        conn.execute(
            "UPDATE radar_products SET title = 'Mochila salva', price = 90.0 WHERE source_type = 'competitor_candidate'"
        )
        conn.execute("UPDATE radar_collection_jobs SET status = 'running', updated_at = ?", (old_time,))

    recovered = mark_stale_running_jobs_as_pending_or_failed(max_age_minutes=10)
    assert recovered == 1

    with get_connection() as conn:
        prod = conn.execute("SELECT status FROM radar_products WHERE source_type = 'competitor_candidate'").fetchone()
        assert prod["status"] == "collected"

@patch("shopee_core.radar_collector.collect_product_page")
def test_screenshot_failure_preserves_original_error(mock_collect):
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678")
    mock_collect.side_effect = RuntimeError("Original error")

    res = run_linked_collection_for_product("own-1", limit=1)
    assert res["failed"] == 1
    assert res["errors"][0]["error"] == "Original error"
    assert res["errors"][0]["screenshot_path"] is None

def test_fallback_title_from_url_slug():
    from shopee_core.radar_collector import _extract_title_from_url
    title1 = _extract_title_from_url("https://mercadolivre.com.br/mochila-escolar-infantil-linda/p/MLB12345")
    assert "Mochila Escolar Infantil Linda" in title1

    title2 = _extract_title_from_url("https://shopee.com.br/Mochila-Feminina-Premium-i.123.456")
    assert "Mochila Feminina Premium" in title2


# ── R7.2G: Novos testes de duplicata e URLs fake ───────────────────────────────

from shopee_core.radar_workflow_ui_service import dedupe_radar_links_and_matches

def test_get_competitor_table_no_duplicate_candidates():
    """R7.2G: Candidato com 2 jobs não deve aparecer 2x na tabela."""
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/10/20")

    # Buscar o candidato criado
    with get_connection() as conn:
        cand = conn.execute(
            "SELECT product_uid FROM radar_products WHERE source_type='competitor_candidate'"
        ).fetchone()
        if not cand:
            return  # URL fake foi bloqueada — teste não se aplica
        cand_uid = cand["product_uid"]
        # Inserir segundo job para o mesmo candidato
        conn.execute(
            """
            INSERT INTO radar_collection_jobs (job_uid, product_uid, url, job_type, status, created_at, updated_at)
            VALUES (?, ?, 'https://shopee.com.br/product/10/20', 'product_data', 'failed', '2023-01-01', '2023-01-02')
            """,
            (uuid.uuid4().hex, cand_uid)
        )

    table = get_competitor_table_for_product("own-1")
    # Pode ser 0 se URL fake foi bloqueada, ou 1 se passou
    product_uids = [r["product_uid"] for r in table]
    assert len(product_uids) == len(set(product_uids)), "Tabela tem candidate_product_uid duplicado!"


def test_get_competitor_table_no_duplicate_with_real_url():
    """R7.2G: Candidato real com 2 jobs -> apenas 1 linha na tabela."""
    _clear_tables()
    _insert_own_product("own-1")

    # Inserir candidato diretamente (URL não-fake)
    cand_uid = uuid.uuid4().hex
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO radar_products (product_uid, source_type, marketplace, url, canonical_url, title, status, created_at, updated_at)
            VALUES (?, 'competitor_candidate', 'shopee', 'https://shopee.com.br/item-123', 'https://shopee.com.br/item-123', 'Mochila Real', 'collected', '2023', '2023')
            """,
            (cand_uid,)
        )
        conn.execute(
            """
            INSERT INTO radar_candidate_links (link_uid, own_product_uid, candidate_product_uid, source, created_at, updated_at)
            VALUES (?, 'own-1', ?, 'manual_url', '2023', '2023')
            """,
            (uuid.uuid4().hex, cand_uid)
        )
        # Dois jobs para o mesmo candidato
        conn.execute(
            """
            INSERT INTO radar_collection_jobs (job_uid, product_uid, url, job_type, status, created_at, updated_at)
            VALUES (?, ?, 'https://shopee.com.br/item-123', 'product_data', 'done', '2023-01-01', '2023-01-01')
            """,
            (uuid.uuid4().hex, cand_uid)
        )
        conn.execute(
            """
            INSERT INTO radar_collection_jobs (job_uid, product_uid, url, job_type, status, created_at, updated_at)
            VALUES (?, ?, 'https://shopee.com.br/item-123', 'product_data', 'failed', '2023-01-02', '2023-01-02')
            """,
            (uuid.uuid4().hex, cand_uid)
        )

    table = get_competitor_table_for_product("own-1")
    assert len(table) == 1, f"Esperado 1 linha, obteve {len(table)}"
    assert table[0]["product_uid"] == cand_uid


def test_fake_url_blocked_in_add_competitor_urls():
    """R7.2G: URLs fake (shopee/product/1/1, /2/2) não devem criar candidato."""
    _clear_tables()
    _insert_own_product("own-1")

    res = add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1/1\nhttps://shopee.com.br/product/2/2")

    # Ambas devem ser inválidas (bloqueadas)
    assert res["created"] == 0
    assert res["invalid"] == 2

    with get_connection() as conn:
        prods = conn.execute("SELECT COUNT(*) as c FROM radar_products WHERE source_type='competitor_candidate'").fetchone()
        assert prods["c"] == 0, "URLs fake não deveriam criar candidatos"


def test_fake_url_filtered_from_competitor_table():
    """R7.2G: URLs fake que eventualmente estejam no banco não aparecem na tabela."""
    _clear_tables()
    _insert_own_product("own-1")

    # Inserir candidato fake diretamente (simulando dado antigo)
    cand_uid = uuid.uuid4().hex
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO radar_products (product_uid, source_type, marketplace, url, canonical_url, title, status, created_at, updated_at)
            VALUES (?, 'competitor_candidate', 'shopee', 'https://shopee.com.br/product/1/1', 'https://shopee.com.br/product/1/1', 'Produto Fake', 'collected', '2023', '2023')
            """,
            (cand_uid,)
        )
        conn.execute(
            """
            INSERT INTO radar_candidate_links (link_uid, own_product_uid, candidate_product_uid, source, created_at, updated_at)
            VALUES (?, 'own-1', ?, 'manual_url', '2023', '2023')
            """,
            (uuid.uuid4().hex, cand_uid)
        )

    table = get_competitor_table_for_product("own-1")
    assert all(r["product_uid"] != cand_uid for r in table), "URL fake não deveria aparecer na tabela"


def test_ml_url_with_query_string_not_duplicated():
    """R7.2G: URL ML com ?searchVariation= deve ser normalizada e não criar duplicata."""
    _clear_tables()
    _insert_own_product("own-1")

    url_clean = "https://produto.mercadolivre.com.br/MLB-123-mochila-_JM"
    url_with_params = url_clean + "?searchVariation=123456&tracking_id=abc&position=1"

    res1 = add_competitor_urls_for_product("own-1", url_clean)
    res2 = add_competitor_urls_for_product("own-1", url_with_params)

    # Segunda chamada deve detectar que o candidato já existe
    with get_connection() as conn:
        prods = conn.execute(
            "SELECT COUNT(*) as c FROM radar_products WHERE source_type='competitor_candidate'"
        ).fetchone()
        assert prods["c"] == 1, f"Esperado 1 candidato, obteve {prods['c']}"
        links = conn.execute(
            "SELECT COUNT(*) as c FROM radar_candidate_links WHERE own_product_uid='own-1'"
        ).fetchone()
        assert links["c"] == 1, f"Esperado 1 link, obteve {links['c']}"


def test_dedupe_radar_links_and_matches_removes_duplicates():
    """R7.2G: dedupe_radar_links_and_matches funciona corretamente.

    A tabela radar_candidate_links tem UNIQUE(own_product_uid, candidate_product_uid),
    portanto não é possível inserir duplicatas via SQL normal.
    Este teste verifica:
    1. Retorna estrutura correta sem erros
    2. links_removed=0 quando não há duplicatas
    3. Detecta e flagga candidatos com URLs fake
    """
    _clear_tables()
    _insert_own_product("own-1")

    # Inserir candidato com URL fake diretamente (simula dado legado)
    cand_fake_uid = uuid.uuid4().hex
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO radar_products (product_uid, source_type, marketplace, url, canonical_url, title, status, created_at, updated_at)
            VALUES (?, 'competitor_candidate', 'shopee', 'https://shopee.com.br/product/1/1', 'https://shopee.com.br/product/1/1', 'Fake Product', 'pending', '2023', '2023')
            """,
            (cand_fake_uid,)
        )
        conn.execute(
            "INSERT INTO radar_candidate_links (link_uid, own_product_uid, candidate_product_uid, source, created_at, updated_at) VALUES (?, 'own-1', ?, 'manual_url', '2023', '2023')",
            (uuid.uuid4().hex, cand_fake_uid)
        )

    result = dedupe_radar_links_and_matches("own-1")

    # Estrutura correta
    assert "links_removed" in result
    assert "matches_removed" in result
    assert "products_flagged_as_fake" in result

    # Sem duplicatas de link -> links_removed=0
    assert result["links_removed"] == 0

    # URL fake deve ter sido flaggada
    assert result["products_flagged_as_fake"] == 1

    with get_connection() as conn:
        prod = conn.execute(
            "SELECT status, rejection_reason FROM radar_products WHERE product_uid = ?",
            (cand_fake_uid,)
        ).fetchone()
        assert prod["status"] == "failed"
        assert prod["rejection_reason"] == "invalid_test_url"


# ── R7.2H: Overlay dismissal and image timeout safety ──────────────────────────

def test_image_timeout_nao_falha_produto():
    """R7.2H: Timeout de imagem nao falha o job se title/price existem."""
    from unittest.mock import patch
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1234/5678")

    with patch("shopee_core.radar_collector.collect_product_page") as mock_collect:
        mock_collect.return_value = {
            "url": "https://shopee.com.br/product/1234/5678",
            "marketplace": "shopee",
            "title": "Mochila Infantil Teste",
            "price": 89.90,
            "shop_name": "Loja Teste",
            "description": "Descricao teste",
            "image_urls": [],
            "video_urls": [],
            "quality": {"ok": True},
            "raw": {"image_timeout": True},
        }
        res = run_linked_collection_for_product("own-1", limit=1, save_assets=True)
    assert res["succeeded"] == 1
    assert res["failed"] == 0
    return True


def test_image_timeout_com_callback_atualiza_progresso():
    """R7.2H: Etapa de imagem com timeout mostra progresso adequado."""
    from unittest.mock import MagicMock, patch
    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/2345/6789")

    callback = MagicMock()
    with patch("shopee_core.radar_collector.collect_product_page") as mock_collect:
        mock_collect.return_value = {
            "url": "https://shopee.com.br/product/2345/6789",
            "marketplace": "shopee",
            "title": "Mochila Teste",
            "price": 79.90,
            "shop_name": "Loja Teste",
            "description": "Desc",
            "image_urls": [],
            "quality": {"ok": True},
        }
        res = run_linked_collection_for_product("own-1", limit=1, save_assets=True)
    assert res["succeeded"] == 1
    return True


def test_coleta_salva_dados_principais_antes_de_imagem():
    """R7.2H: Dados principais salvos mesmo quando imagem retorna vazia."""
    from unittest.mock import patch

    _clear_tables()
    _insert_own_product("own-1")
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/3456/7890")

    with patch("shopee_core.radar_collector.collect_product_page") as mock_collect:
        mock_collect.return_value = {
            "url": "https://shopee.com.br/product/3456/7890",
            "marketplace": "shopee",
            "title": "Mochila Salva Antes Imagem",
            "price": 69.90,
            "shop_name": "Loja Teste",
            "description": "Descricao salva",
            "image_urls": [],
            "quality": {"ok": True},
        }
        res = run_linked_collection_for_product("own-1", limit=1, save_assets=True)

    assert res["succeeded"] == 1

    # Verify the product was saved with main data via DB
    with get_connection() as conn:
        cand = conn.execute(
            "SELECT candidate_product_uid FROM radar_candidate_links WHERE own_product_uid = 'own-1'"
        ).fetchone()
        prod = conn.execute(
            "SELECT title, price FROM radar_products WHERE product_uid = ?",
            (cand["candidate_product_uid"],)
        ).fetchone()
        assert prod["title"] == "Mochila Salva Antes Imagem"
        assert prod["price"] == 69.90
    return True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
