"""
test_user_config.py — Teste do Sistema de Configurações por Usuário
====================================================================
Valida o user_config_service.py sem depender do WhatsApp.
"""

from shopee_core.user_config_service import (
    get_or_create_profile,
    add_shop,
    list_shops,
    get_active_shop,
    set_active_shop,
    remove_shop,
    save_secret,
    get_secret,
    has_secret,
    delete_secret,
    mask_secret,
    get_user_config_summary,
    delete_all_user_data,
)

# User IDs de teste
USER_A = "5511988600050@s.whatsapp.net"
USER_B = "5511999999999@s.whatsapp.net"


def test_profile():
    """Teste 1: Criar e recuperar perfil"""
    print("=" * 60)
    print("TESTE 1: Perfil de Usuário")
    print("=" * 60)
    
    # Cria perfil
    profile = get_or_create_profile(USER_A)
    print(f"✅ Perfil criado: {profile['user_id']}")
    
    # Recupera novamente (não deve duplicar)
    profile2 = get_or_create_profile(USER_A)
    assert profile["user_id"] == profile2["user_id"]
    print("✅ Perfil recuperado sem duplicar")
    
    return True


def test_shops():
    """Teste 2: Adicionar, listar e gerenciar lojas"""
    print("\n" + "=" * 60)
    print("TESTE 2: Sistema de Lojas")
    print("=" * 60)
    
    # Adiciona primeira loja
    shop1_uid = add_shop(
        USER_A,
        "https://shopee.com.br/totalmenteseu",
        "totalmenteseu",
        shop_id="12345",
        display_name="Minha Loja Principal"
    )
    print(f"✅ Loja 1 adicionada: {shop1_uid}")
    
    # Adiciona segunda loja
    shop2_uid = add_shop(
        USER_A,
        "https://shopee.com.br/outra_loja",
        "outra_loja",
        set_as_active=False
    )
    print(f"✅ Loja 2 adicionada: {shop2_uid}")
    
    # Lista lojas
    shops = list_shops(USER_A)
    assert len(shops) == 2
    print(f"✅ Listou {len(shops)} lojas")
    
    # Verifica loja ativa
    active = get_active_shop(USER_A)
    assert active["shop_uid"] == shop1_uid
    print(f"✅ Loja ativa: {active['username']}")
    
    # Troca loja ativa
    success = set_active_shop(USER_A, shop2_uid)
    assert success
    active = get_active_shop(USER_A)
    assert active["shop_uid"] == shop2_uid
    print(f"✅ Loja ativa trocada para: {active['username']}")
    
    # Remove loja
    success = remove_shop(USER_A, shop1_uid)
    assert success
    shops = list_shops(USER_A)
    assert len(shops) == 1
    print(f"✅ Loja removida. Restam {len(shops)} loja(s)")
    
    return True


def test_secrets():
    """Teste 3: Salvar, recuperar e remover secrets"""
    print("\n" + "=" * 60)
    print("TESTE 3: Secrets Criptografados")
    print("=" * 60)
    
    # Salva Gemini API Key
    api_key = "AIzaSyAbc123def456ghi789"
    save_secret(USER_A, "gemini_api_key", api_key)
    print("✅ Gemini API Key salva")
    
    # Salva Telegram token
    telegram_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    save_secret(USER_A, "telegram_token", telegram_token)
    print("✅ Telegram token salvo")
    
    # Salva Telegram chat_id
    chat_id = "123456789"
    save_secret(USER_A, "telegram_chat_id", chat_id)
    print("✅ Telegram chat_id salvo")
    
    # Verifica existência
    assert has_secret(USER_A, "gemini_api_key")
    assert has_secret(USER_A, "telegram_token")
    assert has_secret(USER_A, "telegram_chat_id")
    print("✅ Secrets existem")
    
    # Recupera secrets
    recovered_api_key = get_secret(USER_A, "gemini_api_key")
    assert recovered_api_key == api_key
    print(f"✅ API Key recuperada: {mask_secret(recovered_api_key)}")
    
    recovered_token = get_secret(USER_A, "telegram_token")
    assert recovered_token == telegram_token
    print(f"✅ Telegram token recuperado: {mask_secret(recovered_token, 6)}")
    
    recovered_chat_id = get_secret(USER_A, "telegram_chat_id")
    assert recovered_chat_id == chat_id
    print(f"✅ Chat ID recuperado: {mask_secret(recovered_chat_id)}")
    
    # Remove um secret
    success = delete_secret(USER_A, "telegram_token")
    assert success
    assert not has_secret(USER_A, "telegram_token")
    print("✅ Telegram token removido")
    
    return True


def test_isolation():
    """Teste 4: Isolamento entre usuários"""
    print("\n" + "=" * 60)
    print("TESTE 4: Isolamento entre Usuários")
    print("=" * 60)
    
    # User A já tem dados dos testes anteriores
    
    # User B adiciona loja
    shop_b_uid = add_shop(
        USER_B,
        "https://shopee.com.br/loja_user_b",
        "loja_user_b"
    )
    print(f"✅ User B adicionou loja: {shop_b_uid}")
    
    # User B salva secret
    save_secret(USER_B, "gemini_api_key", "AIzaSyXYZ999")
    print("✅ User B salvou API Key")
    
    # Verifica isolamento
    shops_a = list_shops(USER_A)
    shops_b = list_shops(USER_B)
    
    assert len(shops_a) == 1  # User A tem 1 loja (removeu 1 no teste anterior)
    assert len(shops_b) == 1  # User B tem 1 loja
    assert shops_a[0]["username"] != shops_b[0]["username"]
    print(f"✅ Isolamento de lojas: A={len(shops_a)}, B={len(shops_b)}")
    
    # Verifica secrets isolados
    api_key_a = get_secret(USER_A, "gemini_api_key")
    api_key_b = get_secret(USER_B, "gemini_api_key")
    
    assert api_key_a != api_key_b
    print(f"✅ Isolamento de secrets: A={mask_secret(api_key_a)}, B={mask_secret(api_key_b)}")
    
    return True


def test_summary():
    """Teste 5: Resumo de configurações"""
    print("\n" + "=" * 60)
    print("TESTE 5: Resumo de Configurações")
    print("=" * 60)
    
    summary = get_user_config_summary(USER_A)
    
    print(f"User ID: {summary['user_id']}")
    print(f"Lojas: {summary['shops_count']}")
    print(f"Loja ativa: {summary['active_shop']['username'] if summary['active_shop'] else 'Nenhuma'}")
    print(f"Secrets:")
    print(f"  - Gemini API Key: {'✓' if summary['secrets']['gemini_api_key'] else '✗'}")
    print(f"  - Telegram token: {'✓' if summary['secrets']['telegram_token'] else '✗'}")
    print(f"  - Telegram chat_id: {'✓' if summary['secrets']['telegram_chat_id'] else '✗'}")
    
    print("✅ Resumo gerado com sucesso")
    
    return True


def test_delete_all():
    """Teste 6: Remover todos os dados"""
    print("\n" + "=" * 60)
    print("TESTE 6: Remover Todos os Dados")
    print("=" * 60)
    
    # Remove dados do User A
    result = delete_all_user_data(USER_A)
    print(f"✅ User A: {result['shops_removed']} loja(s) removida(s)")
    print(f"✅ User A: {result['secrets_removed']} secret(s) removido(s)")
    
    # Verifica que foi removido
    shops = list_shops(USER_A)
    assert len(shops) == 0
    assert not has_secret(USER_A, "gemini_api_key")
    print("✅ Todos os dados do User A foram removidos")
    
    # Verifica que User B não foi afetado
    shops_b = list_shops(USER_B)
    assert len(shops_b) == 1
    assert has_secret(USER_B, "gemini_api_key")
    print("✅ User B não foi afetado")
    
    # Limpa User B também
    delete_all_user_data(USER_B)
    print("✅ User B limpo")
    
    return True


def test_mask_secret():
    """Teste 7: Mascaramento de secrets"""
    print("\n" + "=" * 60)
    print("TESTE 7: Mascaramento de Secrets")
    print("=" * 60)
    
    tests = [
        ("AIzaSyAbc123def456ghi789", "****i789"),
        ("123456:ABC-DEF", "****-DEF"),
        ("short", "*****"),  # 5 chars <= 4, então mascara tudo
        ("ab", "**"),
        ("", ""),
    ]
    
    for value, expected in tests:
        masked = mask_secret(value)
        assert masked == expected, f"Esperado {expected}, obteve {masked}"
        print(f"✅ {value[:10] if value else '(vazio)'}... → {masked}")
    
    return True


if __name__ == "__main__":
    print("\n🧪 TESTE DO USER_CONFIG_SERVICE\n")
    
    results = []
    
    try:
        # Executa testes
        results.append(("Perfil", test_profile()))
        results.append(("Lojas", test_shops()))
        results.append(("Secrets", test_secrets()))
        results.append(("Isolamento", test_isolation()))
        results.append(("Resumo", test_summary()))
        results.append(("Remover Dados", test_delete_all()))
        results.append(("Mascaramento", test_mask_secret()))
        
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Erro", False))
    
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
        print("\n✅ U1 — Fundação multiusuário implementada com sucesso!")
    else:
        print(f"\n⚠️ {total - passed} teste(s) falharam")
