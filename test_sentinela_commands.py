"""
test_sentinela_commands.py — Teste dos Comandos /sentinela do WhatsApp (U7)
===========================================================================
Valida o fluxo multiusuário do Sentinela:
  - Loja ativa obrigatória
  - Configuração por user_id + shop_uid
  - Keywords por catálogo ou manual
  - Status com Telegram por usuário
  - Lock por (user_id, shop_uid, keyword, janela_execucao)
"""

from shopee_core.session_service import clear_session
from shopee_core.user_config_service import delete_all_user_data, get_active_shop
from shopee_core.whatsapp_service import handle_whatsapp_text
from shopee_core.sentinel_whatsapp_service import get_sentinel_config


TEST_USER = "5511988600050@s.whatsapp.net"


def setup():
    print("Limpando dados de teste...")
    delete_all_user_data(TEST_USER)
    clear_session(TEST_USER)
    print("Dados limpos\n")


def test_configurar_sem_loja_ativa():
    print("=" * 60)
    print("TESTE 1: /sentinela configurar sem loja ativa")
    print("=" * 60)

    resp = handle_whatsapp_text(TEST_USER, "/sentinela configurar")
    assert resp["type"] == "text"
    assert "/loja adicionar" in resp["text"]
    return True


def test_configurar_com_catalogo_gera_keywords_e_confirma():
    print("\n" + "=" * 60)
    print("TESTE 2: /sentinela configurar com catalogo - keywords automaticas")
    print("=" * 60)

    # Cria loja ativa
    resp = handle_whatsapp_text(TEST_USER, "/loja adicionar https://shopee.com.br/totalmenteseu")
    assert resp["type"] == "text"
    active = get_active_shop(TEST_USER)
    assert active is not None

    # Salva catálogo vinculado à loja ativa
    from shopee_core.catalog_service import save_catalog

    products = [
        {"itemid": "1", "shopid": "10", "name": "Mochila Infantil Princesa Rosa", "price": 99.9},
        {"itemid": "2", "shopid": "10", "name": "Mochila Escolar Rosa Menina", "price": 89.9},
        {"itemid": "3", "shopid": "10", "name": "Mochila Infantil Feminina", "price": 79.9},
    ]
    save_catalog(
        user_id=TEST_USER,
        shop_uid=active["shop_uid"],
        shop_url=active["shop_url"],
        username=active["username"],
        products=products,
        source_type="seller_center",
    )

    # Configura sentinela (deve gerar keywords do catálogo)
    resp = handle_whatsapp_text(TEST_USER, "/sentinela configurar")
    assert resp["type"] == "text"
    assert "digite" in resp["text"].lower()
    assert "confirmar" in resp["text"].lower()

    # Confirma
    resp = handle_whatsapp_text(TEST_USER, "CONFIRMAR")
    assert resp["type"] == "text"
    assert "sentinela configurado" in resp["text"].lower()

    cfg = get_sentinel_config(TEST_USER, active["shop_uid"])
    assert cfg is not None
    assert cfg["user_id"] == TEST_USER
    assert cfg["shop_uid"] == active["shop_uid"]
    assert cfg["keyword_source"] == "catalog"
    assert len(cfg["keywords"]) >= 1
    return True


def test_status_mostra_telegram_nao_configurado():
    print("\n" + "=" * 60)
    print("TESTE 3: /sentinela status mostra Telegram não configurado")
    print("=" * 60)

    resp = handle_whatsapp_text(TEST_USER, "/sentinela status")
    assert resp["type"] == "text"
    assert "telegram" in resp["text"].lower()
    assert "não configurado" in resp["text"].lower()
    return True


def test_rodar_sem_telegram_agenda_background():
    print("\n" + "=" * 60)
    print("TESTE 4: /sentinela rodar sem Telegram - background_task")
    print("=" * 60)

    resp = handle_whatsapp_text(TEST_USER, "/sentinela rodar")
    assert resp["type"] == "background_task"
    assert resp["task"] == "run_sentinel"
    assert "relatório completo" in resp["text"].lower()
    return True


def test_lock_duplica_impede_segunda_execucao():
    print("\n" + "=" * 60)
    print("TESTE 5: lock duplicado impede segunda execução")
    print("=" * 60)

    active = get_active_shop(TEST_USER)
    assert active is not None
    cfg = get_sentinel_config(TEST_USER, active["shop_uid"])
    assert cfg is not None
    keyword = cfg["keywords"][0]

    from shopee_core.sentinel_service import request_sentinel_execution

    janela = "2099-01-01-00"  # fixa para teste
    r1 = request_sentinel_execution(
        loja_id=cfg.get("shop_id") or "unknown",
        user_id=TEST_USER,
        shop_uid=active["shop_uid"],
        keyword=keyword,
        janela_execucao=janela,
        executor="whatsapp",
    )
    assert r1["ok"] is True

    r2 = request_sentinel_execution(
        loja_id=cfg.get("shop_id") or "unknown",
        user_id=TEST_USER,
        shop_uid=active["shop_uid"],
        keyword=keyword,
        janela_execucao=janela,
        executor="whatsapp",
    )
    assert r2["ok"] is False
    return True


def test_pausar_ativar_cancelar():
    print("\n" + "=" * 60)
    print("TESTE 6: /sentinela pausar, ativar e cancelar")
    print("=" * 60)

    active = get_active_shop(TEST_USER)
    assert active is not None

    resp = handle_whatsapp_text(TEST_USER, "/sentinela pausar")
    assert resp["type"] == "text"
    assert "pausado" in resp["text"].lower()
    cfg = get_sentinel_config(TEST_USER, active["shop_uid"])
    assert cfg is not None and cfg["is_active"] is False

    resp = handle_whatsapp_text(TEST_USER, "/sentinela ativar")
    assert resp["type"] == "text"
    assert "ativado" in resp["text"].lower()
    cfg = get_sentinel_config(TEST_USER, active["shop_uid"])
    assert cfg is not None and cfg["is_active"] is True

    resp = handle_whatsapp_text(TEST_USER, "/sentinela cancelar")
    assert resp["type"] == "text"
    assert "configuração removida" in resp["text"].lower()
    cfg = get_sentinel_config(TEST_USER, active["shop_uid"])
    assert cfg is None
    return True


if __name__ == "__main__":
    setup()
    results = []
    results.append(("configurar_sem_loja_ativa", test_configurar_sem_loja_ativa()))
    results.append(("configurar_com_catalogo", test_configurar_com_catalogo_gera_keywords_e_confirma()))
    results.append(("status_telegram_nao_configurado", test_status_mostra_telegram_nao_configurado()))
    results.append(("rodar_sem_telegram", test_rodar_sem_telegram_agenda_background()))
    results.append(("lock_duplica", test_lock_duplica_impede_segunda_execucao()))
    results.append(("pausar_ativar_cancelar", test_pausar_ativar_cancelar()))

    print("\n" + "=" * 60)
    print("RESULTADOS FINAIS")
    print("=" * 60)
    for name, ok in results:
        print(f"{'OK' if ok else 'FAIL'} {name}")
    print("=" * 60)

