import os
import sys
import uuid
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Configura DB em memória isolado para os testes do script
RUN_ID = uuid.uuid4().hex
TEST_DB = Path("data") / f"radar_cdp_test_{RUN_ID}.db"
os.environ["SHOPEE_RADAR_DB_PATH"] = str(TEST_DB)

from shopee_core.radar_db import init_db, get_connection
from shopee_core.radar_cdp_service import is_cdp_available, ensure_radar_chrome_ready, find_chrome_executable
from shopee_core.radar_workflow_ui_service import run_linked_collection_for_product

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

# 1. is_cdp_available retorna false quando endpoint não responde
@patch("shopee_core.radar_cdp_service.urlopen")
def test_is_cdp_available_false_on_timeout(mock_urlopen):
    mock_urlopen.side_effect = OSError("Connection refused")
    assert is_cdp_available("http://127.0.0.1:9222") is False

# 2. is_cdp_available retorna true quando endpoint responde com payload do browser
@patch("shopee_core.radar_cdp_service.urlopen")
def test_is_cdp_available_true_when_ok(mock_urlopen):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = b'{"Browser": "Chrome/110", "webSocketDebuggerUrl": "ws://..."}'
    mock_urlopen.return_value.__enter__.return_value = mock_response
    assert is_cdp_available("http://127.0.0.1:9222") is True

# 3. ensure_radar_chrome_ready retorna already_running se CDP já responde
@patch("shopee_core.radar_cdp_service.is_cdp_available")
def test_ensure_radar_chrome_ready_already_running(mock_available):
    mock_available.return_value = True
    res = ensure_radar_chrome_ready("http://127.0.0.1:9222")
    assert res["ok"] is True
    assert res["already_running"] is True
    assert res["started"] is False

# 4. ensure_radar_chrome_ready tenta start quando CDP fechado e retorna started=True se ficar ativo
@patch("shopee_core.radar_cdp_service.is_cdp_available")
@patch("shopee_core.radar_cdp_service.start_radar_chrome")
def test_ensure_radar_chrome_ready_starts_successfully(mock_start, mock_available):
    mock_available.side_effect = [False, True]
    mock_start.return_value = {"ok": True, "started": True, "already_running": False, "message": "Started"}
    
    res = ensure_radar_chrome_ready("http://127.0.0.1:9222")
    assert res["ok"] is True
    assert res["started"] is True
    assert res["already_running"] is False

# 5. ensure_radar_chrome_ready retorna environment_error se o start falhar
@patch("shopee_core.radar_cdp_service.is_cdp_available")
@patch("shopee_core.radar_cdp_service.start_radar_chrome")
def test_ensure_radar_chrome_ready_fails_when_start_fails(mock_start, mock_available):
    mock_available.return_value = False
    mock_start.return_value = {"ok": False, "started": False, "already_running": False, "message": "Executable not found"}
    
    res = ensure_radar_chrome_ready("http://127.0.0.1:9222")
    assert res["ok"] is False
    assert res["environment_error"] is True
    assert "Não foi possível abrir" in res["message"]

# 6. run_linked_collection_for_product não marca jobs como failed quando CDP não abre
@patch("shopee_core.radar_cdp_service.ensure_radar_chrome_ready")
def test_run_linked_collection_no_failure_on_cdp_env_error(mock_ready):
    mock_ready.return_value = {"ok": False, "environment_error": True, "message": "Chrome fechado"}
    
    _clear_tables()
    _insert_own_product("own-1")
    from shopee_core.radar_workflow_ui_service import add_competitor_urls_for_product
    add_competitor_urls_for_product("own-1", "https://shopee.com.br/product/1/1")
    
    res = run_linked_collection_for_product("own-1", browser_mode="cdp")
    
    assert res["processed"] == 0
    assert res["failed"] == 0
    assert res["succeeded"] == 0
    assert res["environment_error"] is True
    
    with get_connection() as conn:
        prod = conn.execute("SELECT status FROM radar_products WHERE source_type = 'competitor_candidate'").fetchone()
        assert prod["status"] == "pending"
        
        job = conn.execute("SELECT status FROM radar_collection_jobs").fetchone()
        assert job["status"] == "pending"
