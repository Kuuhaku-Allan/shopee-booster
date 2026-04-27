#!/usr/bin/env python3
"""
Script de teste rápido para verificar se a busca de concorrentes
no Mercado Livre está funcionando.

Uso:
    python test_ml_competitors.py
"""

import sys
from backend_core import fetch_competitors_intercept

def test_competitors(keyword: str):
    """Testa busca de concorrentes no Mercado Livre."""
    print(f"\n{'='*60}")
    print(f"🧪 TESTE: Buscar Concorrentes no Mercado Livre")
    print(f"{'='*60}")
    print(f"📝 Keyword: {keyword}")
    print(f"{'='*60}\n")
    
    print("🔍 Buscando produtos no Mercado Livre...")
    print("⏳ Aguarde 30-60 segundos...\n")
    
    try:
        competitors = fetch_competitors_intercept(keyword)
        
        print(f"\n{'='*60}")
        print(f"📊 RESULTADOS")
        print(f"{'='*60}\n")
        
        if not competitors:
            print("❌ FALHA: Nenhum produto encontrado!")
            print("\n💡 Possíveis causas:")
            print("   1. Keyword muito específica")
            print("   2. Timeout de rede")
            print("   3. Seletores CSS do ML mudaram")
            print("\n🔧 Tente:")
            print("   - Keyword mais genérica (ex: 'mochila' em vez de 'mochila escolar')")
            print("   - Verificar logs stderr acima")
            return False
        
        print(f"✅ SUCESSO: {len(competitors)} produtos encontrados!\n")
        
        # Mostra primeiros 3 produtos
        for i, prod in enumerate(competitors[:3], 1):
            print(f"🛒 Produto {i}:")
            print(f"   Nome: {prod.get('nome', 'N/A')[:50]}")
            print(f"   Preço: R$ {prod.get('preco', 0):.2f}")
            print(f"   Avaliações: {prod.get('avaliações', 0)}")
            print(f"   Estrelas: {prod.get('estrelas', 0):.1f}")
            print(f"   Item ID: {prod.get('item_id', 'N/A')}")
            print()
        
        if len(competitors) > 3:
            print(f"   ... e mais {len(competitors) - 3} produtos\n")
        
        # Estatísticas
        precos = [p.get('preco', 0) for p in competitors if p.get('preco', 0) > 0]
        if precos:
            print(f"📈 Estatísticas de Preço:")
            print(f"   Média: R$ {sum(precos)/len(precos):.2f}")
            print(f"   Mínimo: R$ {min(precos):.2f}")
            print(f"   Máximo: R$ {max(precos):.2f}")
            print(f"   Sugestão (95% da média): R$ {(sum(precos)/len(precos))*0.95:.2f}")
        
        print(f"\n{'='*60}")
        print("✅ TESTE PASSOU!")
        print(f"{'='*60}\n")
        return True
        
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"❌ ERRO DURANTE O TESTE")
        print(f"{'='*60}\n")
        print(f"Erro: {e}")
        print(f"\nTraceback completo:")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Keywords de teste
    test_keywords = [
        "mochila escolar",
        "tenis feminino",
        "fone de ouvido",
    ]
    
    if len(sys.argv) > 1:
        # Usa keyword fornecida pelo usuário
        keyword = " ".join(sys.argv[1:])
        test_competitors(keyword)
    else:
        # Testa primeira keyword da lista
        print("\n💡 Dica: Você pode passar uma keyword como argumento:")
        print("   python test_ml_competitors.py mochila escolar\n")
        test_competitors(test_keywords[0])
