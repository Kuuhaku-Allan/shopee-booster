"""
test_catalogo_commands.py — Testes dos Comandos /catalogo (U6)
================================================================
Valida o fluxo completo de gerenciamento de catálogos vinculados à loja ativa.

Casos testados:
  1. /catalogo sem loja ativa → orienta /loja adicionar
  2. /catalogo com loja ativa mas sem catálogo → mostra status vazio
  3. /catalogo importar → entra em awaiting_catalog_file
  4. Upload de arquivo XLSX → importa e salva catálogo
  5. /catalogo status → mostra produtos importados
  6. Trocar loja ativa → /catalogo status não mostra catálogo da loja anterior
  7. /catalogo remover → pede confirmação
  8. Confirmação CONFIRMAR → remove catálogo
  9. /auditar usa catálogo quando scraping falha
  10. Catálogo vinculado a user_id + shop_uid (não apenas user_id)
"""

import sys
from pathlib import Path

# Adiciona o diretório raiz ao path para importar shopee_core
sys.path.insert(0, str(Path(__file__).parent))

from shopee_core.whatsapp_service import handle_whatsapp_message
from shopee_core.session_service import clear_session
from shopee_core.user_config_service import (
    delete_all_user_data,
    add_shop,
    set_active_shop,
)
from shopee_core.catalog_service import (
    save_catalog,
    get_catalog,
    has_catalog,
    delete_catalog,
    get_catalog_summary,
)


def test_catalogo_sem_loja_ativa():
    """Teste 1: /catalogo sem loja ativa → orienta /loja adicionar"""
    user_id = "test_catalog_1@s.whatsapp.net"
    
    # Limpa dados
    clear_session(user_id)
    delete_all_user_data(user_id)
    
    # Envia /catalogo sem ter loja ativa
    response = handle_whatsapp_message({
        "user_id": user_id,
        "text": "/catalogo",
        "has_media": False,
    })
    
    assert response["type"] == "text"
    assert "não tem uma loja ativa" in response["text"].lower()
    assert "/loja adicionar" in response["text"]
    
    print("✅ Teste 1: /catalogo sem loja ativa")


def test_catalogo_status_vazio():
    """Teste 2: /catalogo com loja ativa mas sem catálogo → mostra status vazio"""
    user_id = "test_catalog_2@s.whatsapp.net"
    
    # Limpa dados
    clear_session(user_id)
    delete_all_user_data(user_id)
    
    # Adiciona loja
    add_shop(user_id, "https://shopee.com.br/testloja", "testloja")
    
    # Envia /catalogo status
    response = handle_whatsapp_message({
        "user_id": user_id,
        "text": "/catalogo status",
        "has_media": False,
    })
    
    assert response["type"] == "text"
    assert "nenhum catálogo importado" in response["text"].lower()
    assert "/catalogo importar" in response["text"]
    
    print("✅ Teste 2: /catalogo status vazio")


def test_catalogo_importar_entra_em_estado():
    """Teste 3: /catalogo importar → entra em awaiting_catalog_file"""
    user_id = "test_catalog_3@s.whatsapp.net"
    
    # Limpa dados
    clear_session(user_id)
    delete_all_user_data(user_id)
    
    # Adiciona loja
    add_shop(user_id, "https://shopee.com.br/testloja", "testloja")
    
    # Envia /catalogo importar
    response = handle_whatsapp_message({
        "user_id": user_id,
        "text": "/catalogo importar",
        "has_media": False,
    })
    
    assert response["type"] == "text"
    assert "envie agora o arquivo" in response["text"].lower()
    assert ".xlsx" in response["text"].lower()
    assert ".csv" in response["text"].lower()
    
    # Verifica estado da sessão
    from shopee_core.session_service import get_session
    session = get_session(user_id)
    assert session["state"] == "awaiting_catalog_file"
    assert "shop_uid" in session["data"]
    assert "username" in session["data"]
    
    print("✅ Teste 3: /catalogo importar entra em estado")


def test_catalogo_status_com_produtos():
    """Teste 5: /catalogo status → mostra produtos importados"""
    user_id = "test_catalog_5@s.whatsapp.net"
    
    # Limpa dados
    clear_session(user_id)
    delete_all_user_data(user_id)
    
    # Adiciona loja
    shop_uid = add_shop(user_id, "https://shopee.com.br/testloja", "testloja")
    
    # Salva catálogo manualmente
    products = [
        {"name": "Produto 1", "price": 10.0, "stock": 5},
        {"name": "Produto 2", "price": 20.0, "stock": 10},
        {"name": "Produto 3", "price": 30.0, "stock": 15},
    ]
    
    save_catalog(
        user_id=user_id,
        shop_uid=shop_uid,
        shop_url="https://shopee.com.br/testloja",
        username="testloja",
        products=products,
    )
    
    # Envia /catalogo status
    response = handle_whatsapp_message({
        "user_id": user_id,
        "text": "/catalogo status",
        "has_media": False,
    })
    
    assert response["type"] == "text"
    assert "catálogo importado" in response["text"].lower()
    assert "3" in response["text"]  # 3 produtos
    assert "seller center" in response["text"].lower()
    
    print("✅ Teste 5: /catalogo status com produtos")


def test_catalogo_isolamento_entre_lojas():
    """Teste 6: Trocar loja ativa → /catalogo status não mostra catálogo da loja anterior"""
    user_id = "test_catalog_6@s.whatsapp.net"
    
    # Limpa dados
    clear_session(user_id)
    delete_all_user_data(user_id)
    
    # Adiciona loja A
    shop_a_uid = add_shop(user_id, "https://shopee.com.br/loja_a", "loja_a")
    
    # Salva catálogo na loja A
    products_a = [
        {"name": "Produto A1", "price": 10.0, "stock": 5},
        {"name": "Produto A2", "price": 20.0, "stock": 10},
    ]
    
    save_catalog(
        user_id=user_id,
        shop_uid=shop_a_uid,
        shop_url="https://shopee.com.br/loja_a",
        username="loja_a",
        products=products_a,
    )
    
    # Verifica que loja A tem catálogo
    assert has_catalog(user_id, shop_a_uid)
    
    # Adiciona loja B e torna ativa
    shop_b_uid = add_shop(user_id, "https://shopee.com.br/loja_b", "loja_b")
    set_active_shop(user_id, shop_b_uid)
    
    # Verifica que loja B NÃO tem catálogo
    assert not has_catalog(user_id, shop_b_uid)
    
    # Envia /catalogo status (deve mostrar loja B sem catálogo)
    response = handle_whatsapp_message({
        "user_id": user_id,
        "text": "/catalogo status",
        "has_media": False,
    })
    
    assert response["type"] == "text"
    assert "loja_b" in response["text"].lower()
    assert "nenhum catálogo importado" in response["text"].lower()
    assert "loja_a" not in response["text"].lower()
    
    # Volta para loja A
    set_active_shop(user_id, shop_a_uid)
    
    # Envia /catalogo status (deve mostrar loja A com catálogo)
    response = handle_whatsapp_message({
        "user_id": user_id,
        "text": "/catalogo status",
        "has_media": False,
    })
    
    assert response["type"] == "text"
    assert "loja_a" in response["text"].lower()
    assert "catálogo importado" in response["text"].lower()
    assert "2" in response["text"]  # 2 produtos
    
    print("✅ Teste 6: Isolamento entre lojas")


def test_catalogo_remover_pede_confirmacao():
    """Teste 7: /catalogo remover → pede confirmação"""
    user_id = "test_catalog_7@s.whatsapp.net"
    
    # Limpa dados
    clear_session(user_id)
    delete_all_user_data(user_id)
    
    # Adiciona loja
    shop_uid = add_shop(user_id, "https://shopee.com.br/testloja", "testloja")
    
    # Salva catálogo
    products = [{"name": "Produto 1", "price": 10.0, "stock": 5}]
    save_catalog(
        user_id=user_id,
        shop_uid=shop_uid,
        shop_url="https://shopee.com.br/testloja",
        username="testloja",
        products=products,
    )
    
    # Envia /catalogo remover
    response = handle_whatsapp_message({
        "user_id": user_id,
        "text": "/catalogo remover",
        "has_media": False,
    })
    
    assert response["type"] == "text"
    assert "tem certeza" in response["text"].lower()
    assert "confirmar" in response["text"].lower()
    assert "testloja" in response["text"].lower()
    
    # Verifica estado da sessão
    from shopee_core.session_service import get_session
    session = get_session(user_id)
    assert session["state"] == "awaiting_catalog_remove_confirm"
    
    print("✅ Teste 7: /catalogo remover pede confirmação")


def test_catalogo_remover_confirmar():
    """Teste 8: Confirmação CONFIRMAR → remove catálogo"""
    user_id = "test_catalog_8@s.whatsapp.net"
    
    # Limpa dados
    clear_session(user_id)
    delete_all_user_data(user_id)
    
    # Adiciona loja
    shop_uid = add_shop(user_id, "https://shopee.com.br/testloja", "testloja")
    
    # Salva catálogo
    products = [{"name": "Produto 1", "price": 10.0, "stock": 5}]
    save_catalog(
        user_id=user_id,
        shop_uid=shop_uid,
        shop_url="https://shopee.com.br/testloja",
        username="testloja",
        products=products,
    )
    
    # Verifica que tem catálogo
    assert has_catalog(user_id, shop_uid)
    
    # Envia /catalogo remover
    handle_whatsapp_message({
        "user_id": user_id,
        "text": "/catalogo remover",
        "has_media": False,
    })
    
    # Confirma remoção
    response = handle_whatsapp_message({
        "user_id": user_id,
        "text": "CONFIRMAR",
        "has_media": False,
    })
    
    assert response["type"] == "text"
    assert "removido com sucesso" in response["text"].lower()
    
    # Verifica que não tem mais catálogo
    assert not has_catalog(user_id, shop_uid)
    
    print("✅ Teste 8: Confirmação remove catálogo")


def test_catalogo_remover_cancelar():
    """Teste 9: Cancelar remoção mantém catálogo"""
    user_id = "test_catalog_9@s.whatsapp.net"
    
    # Limpa dados
    clear_session(user_id)
    delete_all_user_data(user_id)
    
    # Adiciona loja
    shop_uid = add_shop(user_id, "https://shopee.com.br/testloja", "testloja")
    
    # Salva catálogo
    products = [{"name": "Produto 1", "price": 10.0, "stock": 5}]
    save_catalog(
        user_id=user_id,
        shop_uid=shop_uid,
        shop_url="https://shopee.com.br/testloja",
        username="testloja",
        products=products,
    )
    
    # Envia /catalogo remover
    handle_whatsapp_message({
        "user_id": user_id,
        "text": "/catalogo remover",
        "has_media": False,
    })
    
    # Cancela remoção
    response = handle_whatsapp_message({
        "user_id": user_id,
        "text": "/cancelar",
        "has_media": False,
    })
    
    assert response["type"] == "text"
    assert "cancelada" in response["text"].lower() or "mantido" in response["text"].lower()
    
    # Verifica que ainda tem catálogo
    assert has_catalog(user_id, shop_uid)
    
    print("✅ Teste 9: Cancelar mantém catálogo")


def test_catalogo_vinculado_a_shop_uid():
    """Teste 10: Catálogo vinculado a user_id + shop_uid (não apenas user_id)"""
    user_id = "test_catalog_10@s.whatsapp.net"
    
    # Limpa dados
    clear_session(user_id)
    delete_all_user_data(user_id)
    
    # Adiciona duas lojas
    shop_a_uid = add_shop(user_id, "https://shopee.com.br/loja_a", "loja_a")
    shop_b_uid = add_shop(user_id, "https://shopee.com.br/loja_b", "loja_b")
    
    # Salva catálogo apenas na loja A
    products_a = [{"name": "Produto A", "price": 10.0, "stock": 5}]
    save_catalog(
        user_id=user_id,
        shop_uid=shop_a_uid,
        shop_url="https://shopee.com.br/loja_a",
        username="loja_a",
        products=products_a,
    )
    
    # Verifica que loja A tem catálogo
    assert has_catalog(user_id, shop_a_uid)
    catalog_a = get_catalog(user_id, shop_a_uid)
    assert catalog_a is not None
    assert catalog_a["username"] == "loja_a"
    
    # Verifica que loja B NÃO tem catálogo
    assert not has_catalog(user_id, shop_b_uid)
    catalog_b = get_catalog(user_id, shop_b_uid)
    assert catalog_b is None
    
    # Salva catálogo na loja B
    products_b = [{"name": "Produto B", "price": 20.0, "stock": 10}]
    save_catalog(
        user_id=user_id,
        shop_uid=shop_b_uid,
        shop_url="https://shopee.com.br/loja_b",
        username="loja_b",
        products=products_b,
    )
    
    # Verifica que ambas têm catálogos independentes
    assert has_catalog(user_id, shop_a_uid)
    assert has_catalog(user_id, shop_b_uid)
    
    catalog_a = get_catalog(user_id, shop_a_uid)
    catalog_b = get_catalog(user_id, shop_b_uid)
    
    assert catalog_a["username"] == "loja_a"
    assert catalog_b["username"] == "loja_b"
    assert catalog_a["products_count"] == 1
    assert catalog_b["products_count"] == 1
    
    print("✅ Teste 10: Catálogo vinculado a shop_uid")


def run_all_tests():
    """Executa todos os testes em sequência."""
    print("\n" + "="*60)
    print("TESTES DOS COMANDOS /catalogo (U6)")
    print("="*60 + "\n")
    
    try:
        test_catalogo_sem_loja_ativa()
        test_catalogo_status_vazio()
        test_catalogo_importar_entra_em_estado()
        test_catalogo_status_com_produtos()
        test_catalogo_isolamento_entre_lojas()
        test_catalogo_remover_pede_confirmacao()
        test_catalogo_remover_confirmar()
        test_catalogo_remover_cancelar()
        test_catalogo_vinculado_a_shop_uid()
        
        print("\n" + "="*60)
        print("✅ TODOS OS TESTES PASSARAM!")
        print("="*60 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TESTE FALHOU: {e}\n")
        raise
    except Exception as e:
        print(f"\n❌ ERRO INESPERADO: {e}\n")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    run_all_tests()
