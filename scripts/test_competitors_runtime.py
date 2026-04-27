"""
Test script para validar search_competitors_safe em runtime
Testa exatamente a mesma função usada por Auditoria e Sentinela
"""
import sys
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_keyword(keyword: str):
    """Testa busca de concorrentes para uma keyword"""
    
    from shopee_core.competitor_service import search_competitors_safe
    
    print(f"\n{'='*60}")
    print(f"Keyword: {keyword}")
    print('='*60)
    
    competitors = search_competitors_safe(keyword, limit=10)
    
    print(f"Resultados: {len(competitors)} concorrentes")
    
    if competitors:
        # Provider usado
        sources = set(c.get("source", "unknown") for c in competitors)
        print(f"Provider: {', '.join(sources)}")
        
        # Top 3 produtos
        print(f"\nTop 3 produtos:")
        for i, c in enumerate(competitors[:3], 1):
            titulo = c.get("titulo", "")[:50]
            preco = c.get("preco", 0)
            source = c.get("source", "")
            print(f"  {i}. {titulo} - R$ {preco:.2f} ({source})")
        
        return len(competitors)
    else:
        print("⚠️ Nenhum concorrente encontrado")
        return 0


def main():
    """Testa múltiplas keywords"""
    
    print("=" * 60)
    print("TESTE: search_competitors_safe (Runtime)")
    print("=" * 60)
    print("\nTestando a mesma função usada por Auditoria e Sentinela\n")
    
    keywords = [
        "Mochila Branca Minimalista",
        "mochila roxa",
        "mochila azul",
        "mochila rosa",
    ]
    
    results = {}
    
    for keyword in keywords:
        try:
            count = test_keyword(keyword)
            results[keyword] = count
        except Exception as e:
            print(f"❌ ERRO: {e}")
            results[keyword] = 0
            import traceback
            traceback.print_exc()
    
    # Resumo
    print("\n" + "=" * 60)
    print("RESUMO")
    print("=" * 60)
    
    total = sum(results.values())
    success = sum(1 for count in results.values() if count > 0)
    
    for keyword, count in results.items():
        status = "✅" if count > 0 else "❌"
        print(f"{status} {keyword}: {count} concorrentes")
    
    print(f"\nTotal: {total} concorrentes em {len(keywords)} keywords")
    print(f"Sucesso: {success}/{len(keywords)} keywords")
    
    if success == len(keywords):
        print("\n✅ TODOS OS TESTES PASSARAM")
        print("Pode testar /auditar e /sentinela rodar no WhatsApp")
    elif success > 0:
        print(f"\n⚠️ ALGUNS TESTES FALHARAM ({len(keywords) - success}/{len(keywords)})")
        print("Verifique os logs acima para detalhes")
    else:
        print("\n❌ TODOS OS TESTES FALHARAM")
        print("Não adianta testar WhatsApp - problema está no competitor_service")
    
    return success == len(keywords)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
