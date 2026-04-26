"""
scripts/test_shop_loader.py — Teste isolado do carregamento de produtos
=========================================================================
Testa o fluxo completo de carregamento de uma loja da Shopee
sem depender do Streamlit ou WhatsApp.

Uso:
    python scripts/test_shop_loader.py
"""

import sys
import os
from pathlib import Path

# Força UTF-8 no Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Adiciona o diretório raiz ao path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from shopee_core.shop_loader_service import load_shop_with_fallback


def test_shop_loader():
    """Testa o carregamento de produtos da loja totalmenteseu"""
    
    # URL de teste (deve retornar 6 produtos na v4.0.0)
    url = "https://shopee.com.br/totalmenteseu"
    
    print("=" * 70)
    print("TESTE DE CARREGAMENTO DE PRODUTOS DA LOJA")
    print("=" * 70)
    print(f"\n1. URL de entrada: {url}\n")
    
    # Usa o loader com fallback
    print("2. Carregando loja com fallback...")
    result = load_shop_with_fallback(url)
    
    print(f"\n3. RESULTADO:")
    print(f"   OK: {result.get('ok')}")
    print(f"   Message: {result.get('message')}")
    
    if not result.get("ok"):
        print("\n❌ ERRO: Falha ao carregar loja")
        return
    
    data = result.get("data", {})
    username = data.get("username", "N/A")
    shop = data.get("shop", {})
    products = data.get("products", [])
    method = data.get("method_used", "unknown")
    
    print(f"\n4. DETALHES:")
    print(f"   Username: {username}")
    print(f"   Shop ID: {shop.get('shopid', 'N/A')}")
    print(f"   Shop Name: {shop.get('name', 'N/A')}")
    print(f"   Method Used: {method}")
    print(f"   Products Count: {len(products)}")
    print(f"   Esperado: 6 produtos")
    
    if len(products) == 0:
        print("\n❌ REGRESSÃO AINDA PRESENTE: Nenhum produto carregado!")
        print("\n   Possíveis causas:")
        print("   - Fallback também falhou")
        print("   - Shopee bloqueou as requisições")
        print("   - Endpoints mudaram completamente")
    else:
        print(f"\n✓ Produtos carregados com sucesso via {method}!")
        print("\nDetalhes dos produtos:")
        for i, p in enumerate(products[:10], 1):  # Mostra apenas os primeiros 10
            item_id = p.get("itemid", "N/A")
            name = p.get("name", "Sem nome")
            price = p.get("price", 0)
            sold = p.get("sold", 0)
            print(f"\n   {i}. ID: {item_id}")
            print(f"      Nome: {name[:50]}...")
            print(f"      Preço: R$ {price:.2f}")
            print(f"      Vendidos: {sold}")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    try:
        test_shop_loader()
    except Exception as e:
        print(f"\n❌ ERRO DURANTE O TESTE:")
        print(f"   {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
