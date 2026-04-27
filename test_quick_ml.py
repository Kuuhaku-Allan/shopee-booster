#!/usr/bin/env python3
"""
Teste rápido da função fetch_competitors_intercept corrigida.
"""

from backend_core import fetch_competitors_intercept

print("\n" + "="*60)
print("🧪 TESTE RÁPIDO: Buscar Concorrentes no Mercado Livre")
print("="*60 + "\n")

keyword = "mochila escolar"
print(f"📝 Keyword: {keyword}")
print("⏳ Buscando... (30-60s)\n")

competitors = fetch_competitors_intercept(keyword)

print("\n" + "="*60)
print("📊 RESULTADOS")
print("="*60 + "\n")

if not competitors:
    print("❌ FALHA: Nenhum produto retornado!")
    print("\n💡 Verifique os logs stderr acima para detalhes.")
else:
    print(f"✅ SUCESSO: {len(competitors)} produtos encontrados!\n")
    
    for i, prod in enumerate(competitors[:5], 1):
        print(f"🛒 Produto {i}:")
        print(f"   Nome: {prod['nome']}")
        print(f"   Preço: R$ {prod['preco']:.2f}")
        print(f"   Estrelas: {prod['estrelas']}")
        print(f"   Avaliações: {prod['avaliações']}")
        print(f"   Item ID: {prod['item_id']}")
        print()
    
    if len(competitors) > 5:
        print(f"   ... e mais {len(competitors) - 5} produtos\n")
    
    # Estatísticas
    precos = [p['preco'] for p in competitors if p['preco'] > 0]
    if precos:
        print(f"📈 Estatísticas:")
        print(f"   Preço Médio: R$ {sum(precos)/len(precos):.2f}")
        print(f"   Mínimo: R$ {min(precos):.2f}")
        print(f"   Máximo: R$ {max(precos):.2f}")

print("\n" + "="*60 + "\n")
