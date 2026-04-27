"""
test_competitor_service.py — Script de teste do serviço de concorrentes
========================================================================

Uso:
    python scripts/test_competitor_service.py "mochila rosa"
    python scripts/test_competitor_service.py "mochila escolar"
    python scripts/test_competitor_service.py "mochila infantil"

Testa os providers de concorrentes isoladamente antes de rodar no WhatsApp.
"""

import sys
import os

# Adiciona o diretório raiz ao path para importar shopee_core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shopee_core.competitor_service import search_competitors
import logging

# Configura logging para ver os detalhes
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s — %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


def main():
    if len(sys.argv) < 2:
        print("❌ Uso: python scripts/test_competitor_service.py \"keyword\"")
        print("\nExemplos:")
        print("  python scripts/test_competitor_service.py \"mochila rosa\"")
        print("  python scripts/test_competitor_service.py \"mochila escolar\"")
        print("  python scripts/test_competitor_service.py \"mochila infantil\"")
        sys.exit(1)
    
    keyword = sys.argv[1]
    
    print("=" * 70)
    print(f"🔍 Testando busca de concorrentes para: {keyword!r}")
    print("=" * 70)
    print()
    
    # Busca concorrentes
    competitors = search_competitors(keyword, providers=["mercadolivre", "shopee"], limit=10)
    
    print()
    print("=" * 70)
    print(f"📊 RESULTADO FINAL")
    print("=" * 70)
    print(f"Total de concorrentes encontrados: {len(competitors)}")
    print()
    
    if not competitors:
        print("❌ Nenhum concorrente encontrado!")
        print("\nPossíveis causas:")
        print("  - Keyword muito específica")
        print("  - Providers bloqueados/indisponíveis")
        print("  - Erro de conexão")
        sys.exit(1)
    
    # Mostra provider usado
    provider = competitors[0].get("source", "desconhecido")
    print(f"✅ Provider usado: {provider}")
    print()
    
    # Mostra top 5 concorrentes
    print("🏆 TOP 5 CONCORRENTES:")
    print("-" * 70)
    for i, comp in enumerate(competitors[:5], 1):
        titulo = comp.get("titulo", "")[:50]
        preco = comp.get("preco", 0)
        loja = comp.get("loja", "")[:30]
        print(f"{i}. {titulo}")
        print(f"   💰 R$ {preco:.2f} | 🏪 {loja}")
        print()
    
    # Estatísticas
    precos = [c.get("preco", 0) for c in competitors if c.get("preco", 0) > 0]
    if precos:
        print("-" * 70)
        print("📈 ESTATÍSTICAS:")
        print(f"   Menor preço: R$ {min(precos):.2f}")
        print(f"   Maior preço: R$ {max(precos):.2f}")
        print(f"   Preço médio: R$ {sum(precos) / len(precos):.2f}")
    
    print()
    print("=" * 70)
    print("✅ Teste concluído com sucesso!")
    print("=" * 70)


if __name__ == "__main__":
    main()
