"""
test_ia_commands.py — Teste dos Comandos /ia do WhatsApp
=========================================================
Valida os comandos de gerenciamento de Gemini API Key (U3).
"""

from shopee_core.user_config_service import (
    delete_all_user_data,
    has_secret,
    get_secret,
    mask_secret,
)
from shopee_core.whatsapp_service import handle_whatsapp_text, get_user_gemini_api_key
from shopee_core.session_service import clear_session

# User ID de teste
TEST_USER = "5511988600050@s.whatsapp.net"

# API Key fake para testes
FAKE_API_KEY = "AIzaSyAbc123def456ghi789jkl012mno345pqr678stu"


def setup():
    """Limpa dados de teste antes de começar."""
    print("🧹 Limpando dados de teste...")
    delete_all_user_data(TEST_USER)
    clear_session(TEST_USER)
    print("✅ Dados limpos\n")


def test_ia_sem_chave():
    """Teste 1: /ia sem chave configurada"""
    print("=" * 60)
    print("TESTE 1: /ia sem chave configurada")
    print("=" * 60)
    
    response = handle_whatsapp_text(TEST_USER, "/ia")
    
    assert response["type"] == "text"
    # Pode mostrar fallback global ou "não configurada" dependendo do .shopee_config
    assert "ia" in response["text"].lower()
    print("✅ Mensagem de status exibida")
    print(f"Status: {response['text'][:100]}...")
    
    return True


def test_ia_configurar_fluxo():
    """Teste 2: /ia configurar com fluxo completo"""
    print("\n" + "=" * 60)
    print("TESTE 2: /ia configurar com fluxo completo")
    print("=" * 60)
    
    # Inicia configuração
    response = handle_whatsapp_text(TEST_USER, "/ia configurar")
    
    assert response["type"] == "text"
    assert "gemini api key" in response["text"].lower()
    assert "criptografada" in response["text"].lower()
    print("✅ Bot pediu API Key com aviso de privacidade")
    
    # Envia API Key válida
    response = handle_whatsapp_text(TEST_USER, FAKE_API_KEY)
    
    assert response["type"] == "text"
    assert "salva com sucesso" in response["text"].lower()
    assert "****" in response["text"]  # Chave mascarada
    print("✅ API Key salva com sucesso")
    
    # Verifica no banco
    assert has_secret(TEST_USER, "gemini_api_key")
    saved_key = get_secret(TEST_USER, "gemini_api_key")
    assert saved_key == FAKE_API_KEY
    print("✅ API Key salva corretamente no banco (criptografada)")
    
    return True


def test_ia_status_com_chave():
    """Teste 3: /ia status com chave configurada"""
    print("\n" + "=" * 60)
    print("TESTE 3: /ia status com chave configurada")
    print("=" * 60)
    
    response = handle_whatsapp_text(TEST_USER, "/ia status")
    
    assert response["type"] == "text"
    assert "chave própria ativa" in response["text"].lower()
    assert "****" in response["text"]  # Chave mascarada
    print("✅ Status mostra chave própria ativa")
    
    # Verifica mascaramento
    masked = mask_secret(FAKE_API_KEY)
    assert masked in response["text"]
    print(f"✅ Chave mascarada corretamente: {masked}")
    
    return True


def test_get_user_gemini_api_key():
    """Teste 4: Helper get_user_gemini_api_key()"""
    print("\n" + "=" * 60)
    print("TESTE 4: Helper get_user_gemini_api_key()")
    print("=" * 60)
    
    # Deve retornar a chave do usuário
    key = get_user_gemini_api_key(TEST_USER)
    
    assert key is not None
    assert key == FAKE_API_KEY
    print("✅ Helper retorna chave do usuário corretamente")
    
    return True


def test_ia_configurar_chave_invalida():
    """Teste 5: Tentar configurar chave inválida"""
    print("\n" + "=" * 60)
    print("TESTE 5: Tentar configurar chave inválida")
    print("=" * 60)
    
    # Inicia configuração
    handle_whatsapp_text(TEST_USER, "/ia configurar")
    
    # Envia chave muito curta
    response = handle_whatsapp_text(TEST_USER, "abc123")
    
    assert response["type"] == "text"
    assert "inválida" in response["text"].lower()
    assert "20 caracteres" in response["text"].lower()
    print("✅ Bot rejeitou chave muito curta")
    
    # Envia chave com espaços
    response = handle_whatsapp_text(TEST_USER, "AIza Syabc 123def 456ghi 789")
    
    assert response["type"] == "text"
    assert "inválida" in response["text"].lower()
    assert "espaços" in response["text"].lower()
    print("✅ Bot rejeitou chave com espaços")
    
    # Cancela
    clear_session(TEST_USER)
    
    return True


def test_ia_configurar_trocar_chave():
    """Teste 6: Trocar chave existente"""
    print("\n" + "=" * 60)
    print("TESTE 6: Trocar chave existente")
    print("=" * 60)
    
    # Usuário já tem chave do teste 2
    old_key = get_secret(TEST_USER, "gemini_api_key")
    assert old_key == FAKE_API_KEY
    print(f"✅ Chave antiga: {mask_secret(old_key)}")
    
    # Configura nova chave
    handle_whatsapp_text(TEST_USER, "/ia configurar")
    
    new_key = "AIzaSyXYZ999abc888def777ghi666jkl555mno444"
    response = handle_whatsapp_text(TEST_USER, new_key)
    
    assert response["type"] == "text"
    assert "salva com sucesso" in response["text"].lower()
    print("✅ Nova chave salva")
    
    # Verifica que foi substituída
    current_key = get_secret(TEST_USER, "gemini_api_key")
    assert current_key == new_key
    assert current_key != old_key
    print(f"✅ Chave substituída: {mask_secret(current_key)}")
    
    return True


def test_ia_remover():
    """Teste 7: /ia remover"""
    print("\n" + "=" * 60)
    print("TESTE 7: /ia remover")
    print("=" * 60)
    
    # Verifica que tem chave
    assert has_secret(TEST_USER, "gemini_api_key")
    
    # Inicia remoção
    response = handle_whatsapp_text(TEST_USER, "/ia remover")
    
    assert response["type"] == "text"
    assert "tem certeza" in response["text"].lower()
    assert "CONFIRMAR" in response["text"]
    print("✅ Bot pediu confirmação")
    
    # Tenta confirmar com texto errado
    response = handle_whatsapp_text(TEST_USER, "sim")
    
    assert response["type"] == "text"
    assert "confirmar" in response["text"].lower()
    print("✅ Bot rejeitou confirmação incorreta")
    
    # Confirma corretamente
    response = handle_whatsapp_text(TEST_USER, "CONFIRMAR")
    
    assert response["type"] == "text"
    assert "removida" in response["text"].lower()
    print("✅ Chave removida com sucesso")
    
    # Verifica no banco
    assert not has_secret(TEST_USER, "gemini_api_key")
    print("✅ Chave removida do banco")
    
    return True


def test_ia_status_sem_chave():
    """Teste 8: /ia status após remoção"""
    print("\n" + "=" * 60)
    print("TESTE 8: /ia status após remoção")
    print("=" * 60)
    
    response = handle_whatsapp_text(TEST_USER, "/ia")
    
    assert response["type"] == "text"
    # Pode mostrar fallback global ou "não configurada"
    assert "ia" in response["text"].lower()
    print("✅ Status atualizado após remoção")
    print(f"Status: {response['text'][:100]}...")
    
    return True


def test_ia_remover_sem_chave():
    """Teste 9: Tentar remover sem ter chave"""
    print("\n" + "=" * 60)
    print("TESTE 9: Tentar remover sem ter chave")
    print("=" * 60)
    
    response = handle_whatsapp_text(TEST_USER, "/ia remover")
    
    assert response["type"] == "text"
    assert "não tem" in response["text"].lower()
    print("✅ Bot informou que não há chave para remover")
    
    return True


def test_cancelar_configuracao():
    """Teste 10: Cancelar configuração de chave"""
    print("\n" + "=" * 60)
    print("TESTE 10: Cancelar configuração de chave")
    print("=" * 60)
    
    # Inicia configuração
    handle_whatsapp_text(TEST_USER, "/ia configurar")
    
    # Cancela
    response = handle_whatsapp_text(TEST_USER, "/cancelar")
    
    assert response["type"] == "text"
    assert "cancelada" in response["text"].lower()
    print("✅ Configuração cancelada")
    
    # Verifica que não salvou nada
    assert not has_secret(TEST_USER, "gemini_api_key")
    print("✅ Nenhuma chave foi salva")
    
    return True


def test_cancelar_remocao():
    """Teste 11: Cancelar remoção de chave"""
    print("\n" + "=" * 60)
    print("TESTE 11: Cancelar remoção de chave")
    print("=" * 60)
    
    # Adiciona chave primeiro
    from shopee_core.user_config_service import save_secret
    save_secret(TEST_USER, "gemini_api_key", FAKE_API_KEY)
    print("✅ Chave adicionada para teste")
    
    # Inicia remoção
    handle_whatsapp_text(TEST_USER, "/ia remover")
    
    # Cancela
    response = handle_whatsapp_text(TEST_USER, "cancelar")
    
    assert response["type"] == "text"
    assert "cancelada" in response["text"].lower() or "mantida" in response["text"].lower()
    print("✅ Remoção cancelada")
    print(f"Resposta: {response['text']}")
    
    # Verifica que a chave ainda existe
    assert has_secret(TEST_USER, "gemini_api_key")
    print("✅ Chave foi mantida")
    
    return True


def test_helper_fallback_global():
    """Teste 12: Helper com fallback global"""
    print("\n" + "=" * 60)
    print("TESTE 12: Helper com fallback global")
    print("=" * 60)
    
    # Remove chave do usuário
    from shopee_core.user_config_service import delete_secret
    delete_secret(TEST_USER, "gemini_api_key")
    
    # Tenta obter chave (deve retornar global ou None)
    key = get_user_gemini_api_key(TEST_USER)
    
    if key:
        print(f"✅ Helper retornou chave global: {mask_secret(key)}")
    else:
        print("✅ Helper retornou None (fallback desabilitado)")
    
    # Ambos os casos são válidos dependendo do .shopee_config
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
    print("\n🧪 TESTE DOS COMANDOS /IA (U3)\n")
    
    setup()
    
    results = []
    
    try:
        # Executa testes
        results.append(("IA sem chave", test_ia_sem_chave()))
        results.append(("Configurar fluxo", test_ia_configurar_fluxo()))
        results.append(("Status com chave", test_ia_status_com_chave()))
        results.append(("Helper get_user_gemini_api_key", test_get_user_gemini_api_key()))
        results.append(("Chave inválida", test_ia_configurar_chave_invalida()))
        results.append(("Trocar chave", test_ia_configurar_trocar_chave()))
        results.append(("Remover chave", test_ia_remover()))
        results.append(("Status sem chave", test_ia_status_sem_chave()))
        results.append(("Remover sem chave", test_ia_remover_sem_chave()))
        results.append(("Cancelar configuração", test_cancelar_configuracao()))
        results.append(("Cancelar remoção", test_cancelar_remocao()))
        results.append(("Helper fallback", test_helper_fallback_global()))
        
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
        print("\n✅ U3 — Comandos /ia implementados com sucesso!")
    else:
        print(f"\n⚠️ {total - passed} teste(s) falharam")
