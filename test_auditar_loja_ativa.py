"""
test_auditar_loja_ativa.py — Teste da Integração /auditar com Loja Ativa (U5)
===============================================================================
Valida que /auditar usa a loja ativa e a IA do usuário.
"""

from shopee_core.user_config_service import (
    delete_all_user_data,
    add_shop,
    get_active_shop,
    save_secret,
    has_secret,
)
from shopee_core.whatsapp_service import handle_whatsapp_text, get_user_gemini_api_key
from shopee_core.session_service import clear_session

# User ID de teste
TEST_USER = "5511988600050@s.whatsapp.net"

# Dados fake
FAKE_SHOP_URL = "https://shopee.com.br/totalmenteseu"
FAKE_API_KEY = "AIzaSyAbc123def456ghi789jkl012mno345pqr678stu"


def setup():
    """Limpa dados de teste antes de começar."""
    print("🧹 Limpando dados de teste...")
    delete_all_user_data(TEST_USER)
    clear_session(TEST_USER)
    print("✅ Dados limpos\n")


def test_auditar_sem_loja_ativa():
    """Teste 1: /auditar sem loja ativa pede URL"""
    print("=" * 60)
    print("TESTE 1: /auditar sem loja ativa")
    print("=" * 60)
    
    response = handle_whatsapp_text(TEST_USER, "/auditar")
    
    assert response["type"] == "text"
    assert "não tem uma loja ativa" in response["text"].lower()
    assert "/loja adicionar" in response["text"]
    print("✅ Bot pediu URL ou orientou a cadastrar loja")
    
    return True


def test_auditar_com_loja_ativa():
    """Teste 2: /auditar com loja ativa usa a loja automaticamente"""
    print("\n" + "=" * 60)
    print("TESTE 2: /auditar com loja ativa")
    print("=" * 60)
    
    # Adiciona loja ativa
    shop_uid = add_shop(
        user_id=TEST_USER,
        shop_url=FAKE_SHOP_URL,
        username="totalmenteseu",
        set_as_active=True
    )
    print(f"✅ Loja adicionada: {shop_uid}")
    
    # Verifica que é a loja ativa
    active = get_active_shop(TEST_USER)
    assert active is not None
    assert active["username"] == "totalmenteseu"
    print("✅ Loja ativa confirmada")
    
    # Executa /auditar
    response = handle_whatsapp_text(TEST_USER, "/auditar")
    
    assert response["type"] == "background_task"
    assert response["task"] == "load_shop"
    assert "totalmenteseu" in response["text"]
    assert "loja ativa" in response["text"].lower()
    print("✅ Bot usou loja ativa automaticamente")
    print(f"Mensagem: {response['text'][:100]}...")
    
    # Limpa sessão para próximo teste
    clear_session(TEST_USER)
    
    return True


def test_auditar_url_inline():
    """Teste 3: /auditar com URL inline ignora loja ativa"""
    print("\n" + "=" * 60)
    print("TESTE 3: /auditar com URL inline")
    print("=" * 60)
    
    # Usuário já tem loja ativa do teste anterior
    active = get_active_shop(TEST_USER)
    assert active is not None
    print(f"✅ Loja ativa: {active['username']}")
    
    # Usa URL inline diferente
    other_url = "https://shopee.com.br/outra_loja"
    response = handle_whatsapp_text(TEST_USER, f"/auditar {other_url}")
    
    assert response["type"] == "background_task"
    assert response["task"] == "load_shop"
    assert response["shop_url"] == other_url
    print("✅ Bot usou URL inline (não a loja ativa)")
    
    # Limpa sessão
    clear_session(TEST_USER)
    
    return True


def test_get_user_gemini_api_key_sem_chave():
    """Teste 4: get_user_gemini_api_key sem chave do usuário"""
    print("\n" + "=" * 60)
    print("TESTE 4: get_user_gemini_api_key sem chave")
    print("=" * 60)
    
    # Usuário não tem chave própria
    assert not has_secret(TEST_USER, "gemini_api_key")
    
    # Tenta obter chave (deve retornar global ou None)
    api_key = get_user_gemini_api_key(TEST_USER)
    
    if api_key:
        print(f"✅ Retornou chave global (fallback ativo)")
    else:
        print("✅ Retornou None (fallback desabilitado)")
    
    # Ambos os casos são válidos
    return True


def test_get_user_gemini_api_key_com_chave():
    """Teste 5: get_user_gemini_api_key com chave do usuário"""
    print("\n" + "=" * 60)
    print("TESTE 5: get_user_gemini_api_key com chave própria")
    print("=" * 60)
    
    # Adiciona chave do usuário
    save_secret(TEST_USER, "gemini_api_key", FAKE_API_KEY)
    print("✅ Chave do usuário salva")
    
    # Obtém chave
    api_key = get_user_gemini_api_key(TEST_USER)
    
    assert api_key == FAKE_API_KEY
    print(f"✅ Retornou chave do usuário (prioridade sobre global)")
    
    return True


def test_auditar_url_invalida():
    """Teste 6: /auditar com URL inválida"""
    print("\n" + "=" * 60)
    print("TESTE 6: /auditar com URL inválida")
    print("=" * 60)
    
    response = handle_whatsapp_text(TEST_USER, "/auditar https://google.com")
    
    assert response["type"] == "text"
    assert "inválida" in response["text"].lower()
    print("✅ Bot rejeitou URL inválida")
    
    return True


def test_auditar_estado_awaiting_shop_url():
    """Teste 7: Estado awaiting_shop_url funciona"""
    print("\n" + "=" * 60)
    print("TESTE 7: Estado awaiting_shop_url")
    print("=" * 60)
    
    # Remove loja ativa
    from shopee_core.user_config_service import remove_shop
    active = get_active_shop(TEST_USER)
    if active:
        remove_shop(TEST_USER, active["shop_uid"])
    
    # Inicia /auditar sem loja
    response = handle_whatsapp_text(TEST_USER, "/auditar")
    assert response["type"] == "text"
    print("✅ Bot pediu URL")
    
    # Envia URL
    response = handle_whatsapp_text(TEST_USER, FAKE_SHOP_URL)
    
    assert response["type"] == "background_task"
    assert response["task"] == "load_shop"
    print("✅ Bot aceitou URL e iniciou carregamento")
    
    # Limpa sessão
    clear_session(TEST_USER)
    
    return True


def cleanup():
    """Limpa dados de teste após os testes."""
    print("\n" + "=" * 60)
    print("LIMPEZA FINAL")
    print("=" * 60)
    
    result = delete_all_user_data(TEST_USER)
    clear_session(TEST_USER)
    
    print(f"✅ {result['shops_removed']} loja(s) removida(s)")
    print(f"✅ {result['secrets_removed']} secret(s) removido(s)")


if __name__ == "__main__":
    print("\n🧪 TESTE DA INTEGRAÇÃO /AUDITAR COM LOJA ATIVA (U5)\n")
    
    setup()
    
    results = []
    
    try:
        # Executa testes
        results.append(("Auditar sem loja", test_auditar_sem_loja_ativa()))
        results.append(("Auditar com loja ativa", test_auditar_com_loja_ativa()))
        results.append(("Auditar URL inline", test_auditar_url_inline()))
        results.append(("get_user_gemini_api_key sem chave", test_get_user_gemini_api_key_sem_chave()))
        results.append(("get_user_gemini_api_key com chave", test_get_user_gemini_api_key_com_chave()))
        results.append(("Auditar URL inválida", test_auditar_url_invalida()))
        results.append(("Estado awaiting_shop_url", test_auditar_estado_awaiting_shop_url()))
        
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Erro", False))
    
    finally:
        cleanup()
    
    # Resumo
    print("\n" + "=" * 60)
    print("RESUMO DOS TESTES")
    print("=" * 60)
    
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")
    
    total = len(results)
    passed = sum(1 for _, s in results if s)
    
    print(f"\nTotal: {passed}/{total} testes passaram")
    
    if passed == total:
        print("\n🎉 Todos os testes passaram!")
        print("\n✅ U5 — Integração /auditar com loja ativa e IA do usuário implementada com sucesso!")
    else:
        print(f"\n⚠️ {total - passed} teste(s) falharam")
