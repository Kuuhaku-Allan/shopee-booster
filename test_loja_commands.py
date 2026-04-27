"""
test_loja_commands.py — Teste dos Comandos /loja do WhatsApp
=============================================================
Valida os comandos de gerenciamento de lojas (U2).
"""

from shopee_core.user_config_service import (
    delete_all_user_data,
    list_shops,
    get_active_shop,
)
from shopee_core.whatsapp_service import handle_whatsapp_text
from shopee_core.session_service import clear_session

# User ID de teste
TEST_USER = "5511988600050@s.whatsapp.net"


def setup():
    """Limpa dados de teste antes de começar."""
    print("🧹 Limpando dados de teste...")
    delete_all_user_data(TEST_USER)
    clear_session(TEST_USER)
    print("✅ Dados limpos\n")


def test_loja_empty():
    """Teste 1: /loja sem lojas cadastradas"""
    print("=" * 60)
    print("TESTE 1: /loja sem lojas cadastradas")
    print("=" * 60)
    
    response = handle_whatsapp_text(TEST_USER, "/loja")
    
    assert response["type"] == "text"
    assert "ainda não tem uma loja cadastrada" in response["text"].lower()
    print("✅ Mensagem correta para usuário sem lojas")
    
    return True


def test_loja_adicionar_inline():
    """Teste 2: /loja adicionar com URL inline"""
    print("\n" + "=" * 60)
    print("TESTE 2: /loja adicionar com URL inline")
    print("=" * 60)
    
    response = handle_whatsapp_text(
        TEST_USER,
        "/loja adicionar https://shopee.com.br/totalmenteseu"
    )
    
    assert response["type"] == "text"
    assert "cadastrada" in response["text"].lower()
    assert "totalmenteseu" in response["text"]
    print("✅ Loja adicionada com sucesso")
    
    # Verifica no banco
    shops = list_shops(TEST_USER)
    assert len(shops) == 1
    assert shops[0]["username"] == "totalmenteseu"
    print("✅ Loja salva no banco")
    
    # Verifica que é a loja ativa (primeira loja)
    active = get_active_shop(TEST_USER)
    assert active is not None
    assert active["username"] == "totalmenteseu"
    print("✅ Primeira loja definida como ativa automaticamente")
    
    return True


def test_loja_adicionar_fluxo():
    """Teste 3: /loja adicionar com fluxo guiado"""
    print("\n" + "=" * 60)
    print("TESTE 3: /loja adicionar com fluxo guiado")
    print("=" * 60)
    
    # Inicia comando
    response = handle_whatsapp_text(TEST_USER, "/loja adicionar")
    
    assert response["type"] == "text"
    assert "me envie a url" in response["text"].lower()
    print("✅ Bot pediu URL")
    
    # Envia URL
    response = handle_whatsapp_text(
        TEST_USER,
        "https://shopee.com.br/outra_loja"
    )
    
    assert response["type"] == "text"
    assert "cadastrada" in response["text"].lower()
    assert "outra_loja" in response["text"]
    print("✅ Segunda loja adicionada")
    
    # Verifica no banco
    shops = list_shops(TEST_USER)
    assert len(shops) == 2
    print(f"✅ Total de lojas: {len(shops)}")
    
    return True


def test_loja_listar():
    """Teste 4: /loja listar"""
    print("\n" + "=" * 60)
    print("TESTE 4: /loja listar")
    print("=" * 60)
    
    response = handle_whatsapp_text(TEST_USER, "/loja listar")
    
    assert response["type"] == "text"
    assert "totalmenteseu" in response["text"]
    assert "outra_loja" in response["text"]
    assert "✅" in response["text"]  # Marca de loja ativa
    print("✅ Lista de lojas exibida corretamente")
    
    return True


def test_loja_selecionar():
    """Teste 5: /loja selecionar"""
    print("\n" + "=" * 60)
    print("TESTE 5: /loja selecionar")
    print("=" * 60)
    
    # Inicia seleção
    response = handle_whatsapp_text(TEST_USER, "/loja selecionar")
    
    assert response["type"] == "text"
    assert "selecione a loja ativa" in response["text"].lower()
    print("✅ Bot mostrou lista para seleção")
    
    # Seleciona loja 1 (outra_loja)
    response = handle_whatsapp_text(TEST_USER, "1")
    
    assert response["type"] == "text"
    assert "ativada" in response["text"].lower()
    assert "outra_loja" in response["text"]
    print("✅ Loja trocada com sucesso")
    
    # Verifica no banco
    active = get_active_shop(TEST_USER)
    assert active["username"] == "outra_loja"
    print("✅ Loja ativa atualizada no banco")
    
    return True


def test_loja_comando_base():
    """Teste 6: /loja mostra loja ativa"""
    print("\n" + "=" * 60)
    print("TESTE 6: /loja mostra loja ativa")
    print("=" * 60)
    
    response = handle_whatsapp_text(TEST_USER, "/loja")
    
    assert response["type"] == "text"
    assert "loja ativa" in response["text"].lower()
    assert "outra_loja" in response["text"]
    assert "/loja adicionar" in response["text"]
    print("✅ Comando /loja mostra status e comandos")
    
    return True


def test_loja_remover():
    """Teste 7: /loja remover"""
    print("\n" + "=" * 60)
    print("TESTE 7: /loja remover")
    print("=" * 60)
    
    # Verifica lojas atuais
    shops = list_shops(TEST_USER)
    print(f"Lojas antes da remoção: {[s['username'] for s in shops]}")
    
    # Inicia remoção
    response = handle_whatsapp_text(TEST_USER, "/loja remover")
    
    assert response["type"] == "text"
    assert "remover loja" in response["text"].lower()
    print("✅ Bot mostrou lista para remoção")
    print(f"Resposta: {response['text'][:200]}")
    
    # Seleciona loja 1 (segunda na lista, que deve ser totalmenteseu)
    response = handle_whatsapp_text(TEST_USER, "1")
    
    assert response["type"] == "text"
    assert "confirmar remoção" in response["text"].lower()
    print("✅ Bot pediu confirmação")
    print(f"Loja a remover: {response['text']}")
    
    # Confirma remoção
    response = handle_whatsapp_text(TEST_USER, "confirmar")
    
    assert response["type"] == "text"
    assert "removida" in response["text"].lower()
    print("✅ Loja removida com sucesso")
    
    # Verifica no banco
    shops = list_shops(TEST_USER)
    assert len(shops) == 1
    assert shops[0]["username"] == "outra_loja"
    print(f"✅ Loja removida do banco. Restam {len(shops)} loja(s)")
    
    return True


def test_loja_adicionar_duplicada():
    """Teste 8: Tentar adicionar loja duplicada"""
    print("\n" + "=" * 60)
    print("TESTE 8: Tentar adicionar loja duplicada")
    print("=" * 60)
    
    response = handle_whatsapp_text(
        TEST_USER,
        "/loja adicionar https://shopee.com.br/outra_loja"
    )
    
    assert response["type"] == "text"
    assert "já está cadastrada" in response["text"].lower()
    print("✅ Bot detectou loja duplicada")
    
    return True


def test_loja_url_invalida():
    """Teste 9: URL inválida"""
    print("\n" + "=" * 60)
    print("TESTE 9: URL inválida")
    print("=" * 60)
    
    # Inicia comando
    handle_whatsapp_text(TEST_USER, "/loja adicionar")
    
    # Envia URL inválida
    response = handle_whatsapp_text(TEST_USER, "https://google.com")
    
    assert response["type"] == "text"
    assert "inválida" in response["text"].lower()
    print("✅ Bot rejeitou URL inválida")
    
    # Limpa sessão
    clear_session(TEST_USER)
    
    return True


def test_cancelar_fluxo():
    """Teste 10: Cancelar fluxo de adição"""
    print("\n" + "=" * 60)
    print("TESTE 10: Cancelar fluxo de adição")
    print("=" * 60)
    
    # Inicia comando
    handle_whatsapp_text(TEST_USER, "/loja adicionar")
    
    # Cancela
    response = handle_whatsapp_text(TEST_USER, "/cancelar")
    
    assert response["type"] == "text"
    assert "cancelada" in response["text"].lower()
    print("✅ Fluxo cancelado com sucesso")
    
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
    print("\n🧪 TESTE DOS COMANDOS /LOJA (U2)\n")
    
    setup()
    
    results = []
    
    try:
        # Executa testes
        results.append(("Loja vazia", test_loja_empty()))
        results.append(("Adicionar inline", test_loja_adicionar_inline()))
        results.append(("Adicionar fluxo", test_loja_adicionar_fluxo()))
        results.append(("Listar", test_loja_listar()))
        results.append(("Selecionar", test_loja_selecionar()))
        results.append(("Comando base", test_loja_comando_base()))
        results.append(("Remover", test_loja_remover()))
        results.append(("Duplicada", test_loja_adicionar_duplicada()))
        results.append(("URL inválida", test_loja_url_invalida()))
        results.append(("Cancelar", test_cancelar_fluxo()))
        
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
        print("\n✅ U2 — Comandos /loja implementados com sucesso!")
    else:
        print(f"\n⚠️ {total - passed} teste(s) falharam")
