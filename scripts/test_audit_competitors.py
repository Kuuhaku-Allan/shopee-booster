"""
Test script para validar busca de concorrentes na Auditoria
"""
import sys
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_competitor_service():
    """Testa o competitor_service diretamente"""
    
    from shopee_core.competitor_service import search_competitors
    
    print("=" * 60)
    print("TESTE 1: competitor_service direto")
    print("=" * 60)
    
    keyword = "Mochila Branca Minimalista"
    print(f"\nKeyword: {keyword}")
    print("Providers: shopee, mercadolivre")
    print("Limit: 10\n")
    
    competitors = search_competitors(
        keyword=keyword,
        providers=["shopee", "mercadolivre"],
        limit=10,
    )
    
    print(f"✅ Concorrentes encontrados: {len(competitors)}")
    
    if competitors:
        sources = set(c.get("source", "unknown") for c in competitors)
        print(f"Providers usados: {', '.join(sources)}")
        
        print("\nPrimeiro concorrente:")
        primeiro = competitors[0]
        for key, value in primeiro.items():
            print(f"  {key}: {value}")
    else:
        print("⚠️ Nenhum concorrente encontrado")
    
    return len(competitors)


def test_audit_service():
    """Testa o audit_service com normalização"""
    
    from shopee_core.audit_service import _normalize_competitors_for_audit
    from shopee_core.competitor_service import search_competitors
    import pandas as pd
    
    print("\n" + "=" * 60)
    print("TESTE 2: audit_service com normalização")
    print("=" * 60)
    
    keyword = "Mochila Branca Minimalista"
    print(f"\nKeyword: {keyword}\n")
    
    # Busca concorrentes
    competitors = search_competitors(
        keyword=keyword,
        providers=["shopee", "mercadolivre"],
        limit=10,
    )
    
    print(f"Concorrentes brutos: {len(competitors)}")
    
    # Normaliza
    competitors_for_df = _normalize_competitors_for_audit(competitors)
    print(f"Concorrentes normalizados: {len(competitors_for_df)}")
    
    # Cria DataFrame
    df = pd.DataFrame(competitors_for_df) if competitors_for_df else pd.DataFrame()
    print(f"DataFrame: {len(df)} linhas")
    
    if not df.empty:
        print(f"\nColunas do DataFrame: {list(df.columns)}")
        print("\nPrimeira linha:")
        print(df.iloc[0].to_dict())
        
        print("\nEstatísticas de preço:")
        print(f"  Média: R$ {df['preco'].mean():.2f}")
        print(f"  Mínimo: R$ {df['preco'].min():.2f}")
        print(f"  Máximo: R$ {df['preco'].max():.2f}")
    else:
        print("⚠️ DataFrame vazio")
    
    return len(df)


def test_full_optimization():
    """Testa o fluxo completo de otimização"""
    
    from shopee_core.audit_service import generate_product_optimization
    
    print("\n" + "=" * 60)
    print("TESTE 3: Fluxo completo de otimização")
    print("=" * 60)
    
    # Produto de teste
    product = {
        "name": "Mochila Branca Minimalista",
        "price": 89.90,
        "itemid": "test123",
        "shopid": "test456",
    }
    
    print(f"\nProduto: {product['name']}")
    print(f"Preço: R$ {product['price']:.2f}\n")
    
    print("Executando otimização...\n")
    
    result = generate_product_optimization(
        product=product,
        segmento="Moda e Acessórios",
        api_key=None,  # Usa GOOGLE_API_KEY do ambiente
    )
    
    if result["ok"]:
        data = result["data"]
        
        print("✅ Otimização concluída!")
        print(f"\nConcorrentes: {len(data.get('competitors', []))}")
        print(f"Avaliações: {len(data.get('reviews', []))}")
        print(f"Otimização: {len(data.get('optimization', ''))} caracteres")
        
        optimization = data.get("optimization", "")
        if optimization:
            print("\nPrimeiras 500 caracteres da otimização:")
            print("-" * 60)
            print(optimization[:500])
            print("-" * 60)
        
        return True
    else:
        print(f"❌ Falha: {result['message']}")
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Testa busca de concorrentes na Auditoria")
    parser.add_argument("--full", action="store_true", help="Executa teste completo com IA")
    parser.add_argument("--quick", action="store_true", help="Apenas testa competitor_service")
    
    args = parser.parse_args()
    
    try:
        if args.quick:
            # Teste rápido
            count = test_competitor_service()
            print(f"\n{'✅' if count > 0 else '❌'} Teste rápido: {count} concorrentes")
        elif args.full:
            # Teste completo
            test_competitor_service()
            test_audit_service()
            success = test_full_optimization()
            print(f"\n{'✅' if success else '❌'} Teste completo")
        else:
            # Testes 1 e 2 (sem IA)
            count1 = test_competitor_service()
            count2 = test_audit_service()
            print(f"\n{'✅' if count1 > 0 and count2 > 0 else '❌'} Testes básicos: {count1}/{count2} concorrentes")
    
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
