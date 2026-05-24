"""
scripts/audit_with_radar_context.py - Teste manual de Auditoria com Radar.

Uso:
    python scripts/audit_with_radar_context.py RADAR_OWN_PRODUCT_UID [--dry-run-prompt]

Exemplos:
    python scripts/audit_with_radar_context.py 2777bd10-5e4f-40ff-b302-81d23f8834d9
    python scripts/audit_with_radar_context.py 2777bd10-5e4f-40ff-b302-81d23f8834d9 --dry-run-prompt

Flags:
    --dry-run-prompt: Imprime o prompt sem chamar Gemini (economiza quota)
"""

import sys
import os

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shopee_core.radar_service import get_product
from shopee_core.radar_audit_context_service import (
    get_radar_audit_context_status,
    build_radar_audit_context,
    build_radar_prompt_block,
)
from shopee_core.audit_service import generate_product_optimization


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    radar_own_product_uid = sys.argv[1]
    dry_run = "--dry-run-prompt" in sys.argv
    
    print("=" * 80)
    print("TESTE DE AUDITORIA COM RADAR")
    print("=" * 80)
    print(f"Radar UID: {radar_own_product_uid}")
    print(f"Modo: {'DRY RUN (sem Gemini)' if dry_run else 'COMPLETO (com Gemini)'}")
    print()
    
    # 1. Verificar status do Radar
    print("1. Verificando status do Radar...")
    status = get_radar_audit_context_status(radar_own_product_uid)
    print(f"   - can_use: {status.get('can_use')}")
    print(f"   - reason: {status.get('reason')}")
    print(f"   - confidence: {status.get('confidence')}")
    print(f"   - direct_count: {status.get('direct_count')}")
    print()
    
    if not status.get("can_use"):
        print("❌ Radar não disponível. Abortando.")
        sys.exit(1)
    
    # 2. Carregar produto do Radar
    print("2. Carregando produto do Radar...")
    own_product = get_product(radar_own_product_uid)
    if not own_product:
        print("❌ Produto não encontrado no Radar.")
        sys.exit(1)
    
    print(f"   - Título: {own_product.get('title')}")
    print(f"   - Preço: R$ {own_product.get('price', 0):.2f}")
    print(f"   - Marketplace: {own_product.get('marketplace')}")
    print()
    
    # 3. Construir contexto do Radar
    print("3. Construindo contexto do Radar...")
    context = build_radar_audit_context(radar_own_product_uid)
    if not context.get("ok"):
        print(f"❌ Erro ao construir contexto: {context.get('error')}")
        sys.exit(1)
    
    prompt_block = build_radar_prompt_block(context)
    print(f"   - Contexto construído: {len(prompt_block)} caracteres")
    print()
    
    # 4. Imprimir resumo do contexto
    print("4. Resumo do contexto do Radar:")
    print("-" * 80)
    market = context.get("market_summary", {})
    print(f"   Concorrentes diretos: {market.get('competitor_count', 0)}")
    print(f"   Confiança: {market.get('confidence', 'desconhecida')}")
    print(f"   Preço médio: R$ {market.get('price_avg', 0):.2f}")
    print()
    
    title_strat = context.get("title_strategy", {})
    strong_terms = title_strat.get("strong_terms", [])
    print(f"   Termos fortes: {', '.join(strong_terms[:5])}")
    print()
    
    feature_strat = context.get("feature_strategy", {})
    recommended = feature_strat.get("recommended_features", [])
    off_niche = feature_strat.get("off_niche_features", [])
    print(f"   Features recomendadas: {', '.join(recommended[:5])}")
    print(f"   Features off-niche: {', '.join(off_niche)}")
    print("-" * 80)
    print()
    
    # 5. Modo dry-run: imprimir prompt e sair
    if dry_run:
        print("5. MODO DRY RUN - Imprimindo prompt block:")
        print("=" * 80)
        print(prompt_block)
        print("=" * 80)
        print()
        print("✅ Dry run concluído. Prompt block acima seria enviado ao Gemini.")
        print()
        
        # Verificar se notebook aparece como off-niche
        if "notebook" in prompt_block.lower():
            if "off-niche" in prompt_block.lower() or "evitar" in prompt_block.lower():
                print("✅ VALIDAÇÃO: 'notebook' aparece como off-niche/evitar (correto)")
            else:
                print("⚠️  ATENÇÃO: 'notebook' aparece mas NÃO como off-niche/evitar")
        else:
            print("ℹ️  'notebook' não aparece no prompt block")
        
        sys.exit(0)
    
    # 6. Modo completo: chamar Auditoria com Radar
    print("5. Chamando Auditoria com Radar...")
    print("   (Isso vai consumir quota do Gemini)")
    print()
    
    # Montar produto fake para auditoria (usando dados do Radar)
    product_for_audit = {
        "name": own_product.get("title", ""),
        "price": own_product.get("price", 0),
        "itemid": radar_own_product_uid,  # Usar UID como itemid
        "shopid": "0",  # Fake shopid
    }
    
    result = generate_product_optimization(
        product=product_for_audit,
        segmento="Mochilas Escolares",  # Segmento padrão para teste
        api_key=None,  # Usa GOOGLE_API_KEY do ambiente
        radar_own_product_uid=radar_own_product_uid,
    )
    
    if not result.get("ok"):
        print(f"❌ Erro na auditoria: {result.get('message')}")
        sys.exit(1)
    
    data = result.get("data", {})
    optimization = data.get("optimization", "")
    radar_used = data.get("radar_used", False)
    radar_status_result = data.get("radar_status", {})
    
    print("6. Resultado da Auditoria:")
    print("-" * 80)
    print(f"   Radar usado: {radar_used}")
    print(f"   Radar status: {radar_status_result.get('reason', 'N/A')}")
    print(f"   Concorrentes encontrados: {len(data.get('competitors', []))}")
    print(f"   Avaliações coletadas: {len(data.get('reviews', []))}")
    print()
    print("   Otimização gerada:")
    print("-" * 80)
    print(optimization)
    print("-" * 80)
    print()
    
    # Validações
    print("7. Validações:")
    if radar_used:
        print("   ✅ Radar foi usado na auditoria")
    else:
        print("   ❌ Radar NÃO foi usado na auditoria")
    
    if "notebook" in optimization.lower():
        if any(word in optimization.lower() for word in ["evitar", "não recomend", "off-niche", "fora de nicho"]):
            print("   ✅ 'notebook' aparece como algo a evitar (correto)")
        else:
            print("   ⚠️  'notebook' aparece mas NÃO como algo a evitar")
    else:
        print("   ℹ️  'notebook' não aparece na otimização")
    
    print()
    print("=" * 80)
    print("TESTE CONCLUÍDO")
    print("=" * 80)


if __name__ == "__main__":
    main()
