"""
test_telegram_commands.py — Teste dos Comandos /telegram do WhatsApp
=====================================================================
Valida os comandos de gerenciamento de Telegram (U4).
"""

from shopee_core.user_config_service import (
    delete_all_user_data,
    has_secret,
    get_secret,
    mask_secret,
)
from shopee_core.whatsapp_service import handle_whatsapp_text, get_user_telegram_config
from shopee_core.session_service import clear_session

# User ID de teste
TEST_USER = "5511988600050@s.whatsapp.net"

# Configurações fake para testes
FAKE_TOKEN = "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ123456"
FAKE_CHAT_ID = "987654321"
FAKE_GROUP_CHAT_ID = "-1001234567890"


def setup():
    """Limpa dados de teste antes de começar."""
    print("🧹 Limpando dados de teste...")
    delete_all_user_data(TEST_USER)
    clear_session(TEST_USER)
    print("✅ Dados limpos\n")


def test_telegram_sem_config():
    """Teste 1: /telegram sem configuração"""
    print("=" * 60)
    print("TESTE 1: /telegram sem configuração")
    print("=" * 60)
    
    response = handle_whatsapp_text(TEST_USER, "/telegram")
    
    assert response["type"] == "text"
    assert "não configurado" in response["text"].lower()
    assert "sentinela" in response["text"].lower()
    print("✅ Mensagem de status exibida")
    
    return True


def test_telegram_configurar_fluxo():
    """Teste 2: /telegram configurar com fluxo completo"""
    print("\n" + "=" * 60)
    print("TESTE 2: /telegram configurar com fluxo completo")
    print("=" * 60)
    
    # Inicia configuração
    response = handle_whatsapp_text(TEST_USER, "/telegram configurar")
    
    assert response["type"] == "text"
    assert "token do bot" in response["text"].lower()
    assert "botfather" in response["text"].lower()
    print("✅ Bot pediu token com tutorial")
    
    # Envia token válido
    response = handle_whatsapp_text(TEST_USER, FAKE_TOKEN)
    
    assert response["type"] == "text"
    assert "token recebido" in response["text"].lower()
    assert "chat_id" in response["text"].lower()
    print("✅ Token aceito, bot pediu chat_id")
    
    # Envia chat_id válido
    response = handle_whatsapp_text(TEST_USER, FAKE_CHAT_ID)
    
    assert response["type"] == "text"
    # Pode ter sucesso ou falha no teste automático (depende se o bot existe)
    assert "configurado" in response["text"].lower()
    print("✅ Configuração salva")
    
    # Verifica no banco
    assert has_secret(TEST_USER, "telegram_token")
    assert has_secret(TEST_USER, "telegram_chat_id")
    
    saved_token = get_secret(TEST_USER, "telegram_token")
    saved_chat_id = get_secret(TEST_USER, "telegram_chat_id")
    
    assert saved_token == FAKE_TOKEN
    assert saved_chat_id == FAKE_CHAT_ID
    print("✅ Token e chat_id salvos corretamente no banco (criptografados)")
    
    return True


def test_telegram_status_com_config():
    """Teste 3: /telegram status com configuração"""
    print("\n" + "=" * 60)
    print("TESTE 3: /telegram status com configuração")
    print("=" * 60)
    
    response = handle_whatsapp_text(TEST_USER, "/telegram status")
    
    assert response["type"] == "text"
    assert "ativo" in response["text"].lower()
    assert "****" in response["text"]  # Token mascarado
    assert FAKE_CHAT_ID in response["text"]  # Chat ID visível
    print("✅ Status mostra configuração ativa")
    
    # Verifica mascaramento do token
    masked = mask_secret(FAKE_TOKEN)
    assert masked in response["text"]
    print(f"✅ Token mascarado corretamente: {masked}")
    
    return True


def test_get_user_telegram_config():
    """Teste 4: Helper get_user_telegram_config()"""
    print("\n" + "=" * 60)
    print("TESTE 4: Helper get_user_telegram_config()")
    print("=" * 60)
    
    config = get_user_telegram_config(TEST_USER)
    
    assert config is not None
    assert config["token"] == FAKE_TOKEN
    assert config["chat_id"] == FAKE_CHAT_ID
    print("✅ Helper retorna configuração corretamente")
    
    return True


def test_telegram_token_invalido():
    """Teste 5: Tentar configurar token inválido"""
    print("\n" + "=" * 60)
    print("TESTE 5: Tentar configurar token inválido")
    print("=" * 60)
    
    # Remove configuração atual
    from shopee_core.user_config_service import delete_secret
    delete_secret(TEST_USER, "telegram_token")
    delete_secret(TEST_USER, "telegram_chat_id")
    
    # Inicia configuração
    handle_whatsapp_text(TEST_USER, "/telegram configurar")
    
    # Token muito curto
    response = handle_whatsapp_text(TEST_USER, "abc123")
    
    assert response["type"] == "text"
    assert "inválido" in response["text"].lower()
    assert "30 caracteres" in response["text"].lower()
    print("✅ Bot rejeitou token muito curto")
    
    # Token sem ":"
    response = handle_whatsapp_text(TEST_USER, "123456789ABCdefGHIjklMNOpqrSTUvwxYZ")
    
    assert response["type"] == "text"
    assert "inválido" in response["text"].lower()
    assert ":" in response["text"]
    print("✅ Bot rejeitou token sem ':'")
    
    # Token com parte não numérica antes do ":"
    response = handle_whatsapp_text(TEST_USER, "abc:ABCdefGHIjklMNOpqrSTUvwxYZ123456")
    
    assert response["type"] == "text"
    assert "inválido" in response["text"].lower()
    assert "numérica" in response["text"].lower()
    print("✅ Bot rejeitou token com parte não numérica")
    
    # Cancela
    clear_session(TEST_USER)
    
    return True


def test_telegram_chat_id_invalido():
    """Teste 6: Tentar configurar chat_id inválido"""
    print("\n" + "=" * 60)
    print("TESTE 6: Tentar configurar chat_id inválido")
    print("=" * 60)
    
    # Inicia configuração
    handle_whatsapp_text(TEST_USER, "/telegram configurar")
    handle_whatsapp_text(TEST_USER, FAKE_TOKEN)
    
    # Chat ID não numérico
    response = handle_whatsapp_text(TEST_USER, "abc123")
    
    assert response["type"] == "text"
    assert "inválido" in response["text"].lower()
    print("✅ Bot rejeitou chat_id não numérico")
    
    # Chat ID vazio
    response = handle_whatsapp_text(TEST_USER, "   ")
    
    assert response["type"] == "text"
    assert "inválido" in response["text"].lower()
    print("✅ Bot rejeitou chat_id vazio")
    
    # Cancela
    clear_session(TEST_USER)
    
    return True


def test_telegram_chat_id_grupo():
    """Teste 7: Configurar com chat_id de grupo (negativo)"""
    print("\n" + "=" * 60)
    print("TESTE 7: Configurar com chat_id de grupo (negativo)")
    print("=" * 60)
    
    # Inicia configuração
    handle_whatsapp_text(TEST_USER, "/telegram configurar")
    handle_whatsapp_text(TEST_USER, FAKE_TOKEN)
    
    # Envia chat_id negativo (grupo/canal)
    response = handle_whatsapp_text(TEST_USER, FAKE_GROUP_CHAT_ID)
    
    assert response["type"] == "text"
    assert "configurado" in response["text"].lower()
    print("✅ Bot aceitou chat_id negativo (grupo)")
    
    # Verifica no banco
    saved_chat_id = get_secret(TEST_USER, "telegram_chat_id")
    assert saved_chat_id == FAKE_GROUP_CHAT_ID
    print(f"✅ Chat ID de grupo salvo: {saved_chat_id}")
    
    return True


def test_telegram_trocar_config():
    """Teste 8: Trocar configuração existente"""
    print("\n" + "=" * 60)
    print("TESTE 8: Trocar configuração existente")
    print("=" * 60)
    
    # Configuração atual
    old_config = get_user_telegram_config(TEST_USER)
    print(f"✅ Config antiga: token={mask_secret(old_config['token'])}, chat_id={old_config['chat_id']}")
    
    # Nova configuração
    new_token = "987654321:ZYXwvuTSRqpONMlkjIHGfedCBA987654"
    new_chat_id = "111222333"
    
    handle_whatsapp_text(TEST_USER, "/telegram configurar")
    handle_whatsapp_text(TEST_USER, new_token)
    response = handle_whatsapp_text(TEST_USER, new_chat_id)
    
    assert response["type"] == "text"
    assert "configurado" in response["text"].lower()
    print("✅ Nova configuração salva")
    
    # Verifica que foi substituída
    new_config = get_user_telegram_config(TEST_USER)
    assert new_config["token"] == new_token
    assert new_config["chat_id"] == new_chat_id
    assert new_config["token"] != old_config["token"]
    print(f"✅ Config substituída: token={mask_secret(new_config['token'])}, chat_id={new_config['chat_id']}")
    
    return True


def test_telegram_remover():
    """Teste 9: /telegram remover"""
    print("\n" + "=" * 60)
    print("TESTE 9: /telegram remover")
    print("=" * 60)
    
    # Verifica que tem configuração
    assert get_user_telegram_config(TEST_USER) is not None
    
    # Inicia remoção
    response = handle_whatsapp_text(TEST_USER, "/telegram remover")
    
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
    print("✅ Configuração removida com sucesso")
    
    # Verifica no banco
    assert not has_secret(TEST_USER, "telegram_token")
    assert not has_secret(TEST_USER, "telegram_chat_id")
    assert get_user_telegram_config(TEST_USER) is None
    print("✅ Configuração removida do banco")
    
    return True


def test_telegram_status_sem_config():
    """Teste 10: /telegram status após remoção"""
    print("\n" + "=" * 60)
    print("TESTE 10: /telegram status após remoção")
    print("=" * 60)
    
    response = handle_whatsapp_text(TEST_USER, "/telegram")
    
    assert response["type"] == "text"
    assert "não configurado" in response["text"].lower()
    print("✅ Status atualizado após remoção")
    
    return True


def test_telegram_testar_sem_config():
    """Teste 11: Tentar testar sem configuração"""
    print("\n" + "=" * 60)
    print("TESTE 11: Tentar testar sem configuração")
    print("=" * 60)
    
    response = handle_whatsapp_text(TEST_USER, "/telegram testar")
    
    assert response["type"] == "text"
    assert "não configurado" in response["text"].lower()
    print("✅ Bot informou que não há configuração")
    
    return True


def test_cancelar_configuracao():
    """Teste 12: Cancelar configuração"""
    print("\n" + "=" * 60)
    print("TESTE 12: Cancelar configuração")
    print("=" * 60)
    
    # Inicia configuração
    handle_whatsapp_text(TEST_USER, "/telegram configurar")
    
    # Cancela
    response = handle_whatsapp_text(TEST_USER, "/cancelar")
    
    assert response["type"] == "text"
    assert "cancelada" in response["text"].lower()
    print("✅ Configuração cancelada")
    
    # Verifica que não salvou nada
    assert get_user_telegram_config(TEST_USER) is None
    print("✅ Nenhuma configuração foi salva")
    
    return True


def test_cancelar_remocao():
    """Teste 13: Cancelar remoção"""
    print("\n" + "=" * 60)
    print("TESTE 13: Cancelar remoção")
    print("=" * 60)
    
    # Adiciona configuração primeiro
    from shopee_core.user_config_service import save_secret
    save_secret(TEST_USER, "telegram_token", FAKE_TOKEN)
    save_secret(TEST_USER, "telegram_chat_id", FAKE_CHAT_ID)
    print("✅ Configuração adicionada para teste")
    
    # Inicia remoção
    handle_whatsapp_text(TEST_USER, "/telegram remover")
    
    # Cancela
    response = handle_whatsapp_text(TEST_USER, "cancelar")
    
    assert response["type"] == "text"
    print("✅ Remoção cancelada")
    
    # Verifica que a configuração ainda existe
    config = get_user_telegram_config(TEST_USER)
    assert config is not None
    assert config["token"] == FAKE_TOKEN
    assert config["chat_id"] == FAKE_CHAT_ID
    print("✅ Configuração foi mantida")
    
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
    print("\n🧪 TESTE DOS COMANDOS /TELEGRAM (U4)\n")
    
    setup()
    
    results = []
    
    try:
        # Executa testes
        results.append(("Telegram sem config", test_telegram_sem_config()))
        results.append(("Configurar fluxo", test_telegram_configurar_fluxo()))
        results.append(("Status com config", test_telegram_status_com_config()))
        results.append(("Helper get_user_telegram_config", test_get_user_telegram_config()))
        results.append(("Token inválido", test_telegram_token_invalido()))
        results.append(("Chat ID inválido", test_telegram_chat_id_invalido()))
        results.append(("Chat ID grupo", test_telegram_chat_id_grupo()))
        results.append(("Trocar config", test_telegram_trocar_config()))
        results.append(("Remover config", test_telegram_remover()))
        results.append(("Status sem config", test_telegram_status_sem_config()))
        results.append(("Testar sem config", test_telegram_testar_sem_config()))
        results.append(("Cancelar configuração", test_cancelar_configuracao()))
        results.append(("Cancelar remoção", test_cancelar_remocao()))
        
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
        print("\n✅ U4 — Comandos /telegram implementados com sucesso!")
    else:
        print(f"\n⚠️ {total - passed} teste(s) falharam")
