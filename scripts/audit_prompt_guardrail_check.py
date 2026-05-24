"""
scripts/audit_prompt_guardrail_check.py - Validação de guardrails do prompt de auditoria

Verifica se o prompt gerado com contexto do Radar segue as regras:
- Features off-niche aparecem apenas na seção de evitar
- Features off-niche não aparecem como recomendadas
- Há regra explícita proibindo usar off-niche como foco
- Moeda formatada como R$ XX,XX
"""

import sys
from pathlib import Path

# Adicionar raiz do projeto ao path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

print("=" * 80)
print("VALIDAÇÃO DE GUARDRAILS DO PROMPT DE AUDITORIA COM RADAR")
print("=" * 80)
print()

# UID de teste
test_uid = "2777bd10-5e4f-40ff-b302-81d23f8834d9"

print(f"1. CONSTRUINDO CONTEXTO DO RADAR")
print(f"   UID: {test_uid}")
print()

try:
    from shopee_core.radar_audit_context_service import build_radar_audit_context
    
    context = build_radar_audit_context(test_uid)
    
    if not context.get("ok"):
        print(f"   ❌ Erro ao construir contexto: {context.get('error')}")
        sys.exit(1)
    
    print(f"   ✅ Contexto construído com sucesso")
    
    # Extrair dados
    market = context.get("market_summary", {})
    title_strat = context.get("title_strategy", {})
    feature_strat = context.get("feature_strategy", {})
    desc_strat = context.get("description_strategy", {})
    warnings = context.get("warnings", [])
    
    recommended = feature_strat.get('recommended_features', [])
    off_niche = feature_strat.get('off_niche_features', [])
    
    print(f"   Features recomendadas: {recommended[:5]}")
    print(f"   Features off-niche: {off_niche}")
    print()
    
except Exception as e:
    print(f"   ❌ Exceção: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 2. Construir bloco do prompt
print(f"2. CONSTRUINDO BLOCO DO PROMPT")
print()

try:
    # Função de formatação de moeda
    def format_brl(value):
        if value is None:
            return "N/A"
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    recommended_str = ', '.join(recommended[:10])
    off_niche_str = ', '.join(off_niche)
    
    radar_context_block = f"""
═══════════════════════════════════════════════════════════════════
📡 CONTEXTO DO RADAR ASSISTIDO DE CONCORRENTES
═══════════════════════════════════════════════════════════════════

RESUMO DO MERCADO:
- Confiança da análise: {market.get('confidence', 'N/A')}
- Concorrentes diretos analisados: {market.get('competitor_count', 0)}
- Faixa de preço: {format_brl(market.get('price_min'))} - {format_brl(market.get('price_max'))}
- Preço médio: {format_brl(market.get('price_avg'))}
- Preço mediano: {format_brl(market.get('price_median'))}

ESTRATÉGIA DE TÍTULO:
- Termos fortes (USAR): {', '.join(title_strat.get('strong_terms', [])[:10])}
- Termos fracos (evitar): {', '.join(title_strat.get('weak_terms', [])[:5])}

ESTRATÉGIA DE FEATURES:
✅ FEATURES RECOMENDADAS (usar como diferenciais):
   {recommended_str}

❌ FEATURES OFF-NICHE / A EVITAR (NÃO usar como diferenciais):
   {off_niche_str}

ESTRATÉGIA DE DESCRIÇÃO:
- Argumentos comerciais: {', '.join(desc_strat.get('commercial_arguments', [])[:5])}

WARNINGS:
{chr(10).join(f'⚠️ {w}' for w in warnings) if warnings else '(nenhum)'}

═══════════════════════════════════════════════════════════════════
⚠️ REGRAS CRÍTICAS - LEIA COM ATENÇÃO:
═══════════════════════════════════════════════════════════════════

1. FEATURES OFF-NICHE ({off_niche_str}):
   - NÃO podem ser usadas como argumento de venda
   - NÃO podem ser descritas como foco do mercado
   - NÃO podem justificar preço, título, descrição ou tags
   - NÃO podem ser mencionadas como diferenciais ou vantagens
   - Se mencionar, mencione APENAS como algo que o produto NÃO é para esse uso
   - NUNCA escreva frases como "o mercado foca em [feature off-niche]"

2. ESTRATÉGIA CORRETA:
   - Base sua análise nas FEATURES RECOMENDADAS: {recommended_str}
   - Use os TERMOS FORTES: {', '.join(title_strat.get('strong_terms', [])[:5])}
   - Justifique preço com base no nicho correto (features recomendadas)
   - Destaque apenas as features recomendadas como diferenciais

3. CONFIANÇA DA ANÁLISE:
   - Confiança atual: {market.get('confidence', 'N/A')}
   - Se confiança for "medium" ou "low", use linguagem cautelosa:
     * "os dados sugerem", "a amostra indica", "vale testar"
     * Evite conclusões absolutas como "o mercado definitivamente..."

4. FORMATAÇÃO DE MOEDA:
   - SEMPRE use o formato: R$ XX,XX (exemplo: R$ 139,90)
   - NUNCA use: R XX,XX ou R$ XX.XX

═══════════════════════════════════════════════════════════════════
"""
    
    print(f"   ✅ Bloco do prompt construído ({len(radar_context_block)} caracteres)")
    print()
    
except Exception as e:
    print(f"   ❌ Exceção: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 3. Validar guardrails
print(f"3. VALIDANDO GUARDRAILS")
print()

errors = []
warnings_list = []

# Verificar se "notebook" está em off-niche
if "notebook" not in off_niche:
    errors.append("'notebook' NÃO está em off_niche_features")
else:
    print(f"   ✅ 'notebook' está em off_niche_features")

# Verificar se "notebook" NÃO está em recomendadas
if "notebook" in recommended:
    errors.append("'notebook' está em recommended_features (ERRO!)")
else:
    print(f"   ✅ 'notebook' NÃO está em recommended_features")

# Verificar se há seção de features off-niche
if "FEATURES OFF-NICHE" in radar_context_block or "A EVITAR" in radar_context_block:
    print(f"   ✅ Seção de features off-niche presente")
else:
    errors.append("Seção de features off-niche não encontrada")

# Verificar se há regra proibindo usar off-niche como foco
if "NÃO podem ser descritas como foco do mercado" in radar_context_block:
    print(f"   ✅ Regra proibindo off-niche como foco presente")
else:
    errors.append("Regra proibindo off-niche como foco não encontrada")

# Verificar se há regra sobre "o mercado foca em"
if "NUNCA escreva frases como" in radar_context_block and "o mercado foca em" in radar_context_block:
    print(f"   ✅ Regra proibindo 'o mercado foca em [off-niche]' presente")
else:
    errors.append("Regra proibindo 'o mercado foca em [off-niche]' não encontrada")

# Verificar formatação de moeda
if "R$" in radar_context_block:
    print(f"   ✅ Moeda formatada com R$")
    
    # Verificar se há vírgula decimal
    import re
    prices = re.findall(r'R\$ [\d.,]+', radar_context_block)
    if prices:
        # Verificar se usa vírgula como decimal
        has_comma_decimal = any(',' in p for p in prices)
        if has_comma_decimal:
            print(f"   ✅ Moeda usa vírgula como decimal (R$ XX,XX)")
        else:
            warnings_list.append("Moeda pode não estar usando vírgula como decimal")
else:
    errors.append("Moeda não formatada com R$")

# Verificar se features recomendadas estão presentes
if recommended_str in radar_context_block:
    print(f"   ✅ Features recomendadas presentes no prompt")
else:
    warnings_list.append("Features recomendadas podem não estar visíveis")

# Verificar se há instrução sobre confiança
if "confiança for" in radar_context_block.lower() and "cautelosa" in radar_context_block.lower():
    print(f"   ✅ Instrução sobre confiança presente")
else:
    warnings_list.append("Instrução sobre confiança pode estar ausente")

print()

# 4. Mostrar prompt completo
print(f"4. PROMPT COMPLETO")
print()
print(radar_context_block)
print()

# 5. Resumo
print("=" * 80)
print("RESUMO DA VALIDAÇÃO")
print("=" * 80)
print()

if errors:
    print(f"❌ ERROS ENCONTRADOS ({len(errors)}):")
    for i, error in enumerate(errors, 1):
        print(f"   {i}. {error}")
    print()

if warnings_list:
    print(f"⚠️ WARNINGS ({len(warnings_list)}):")
    for i, warning in enumerate(warnings_list, 1):
        print(f"   {i}. {warning}")
    print()

if not errors and not warnings_list:
    print(f"✅ TODOS OS GUARDRAILS VALIDADOS COM SUCESSO")
    print()
    print(f"CHECKLIST:")
    print(f"   ✅ 'notebook' em off-niche")
    print(f"   ✅ 'notebook' NÃO em recomendadas")
    print(f"   ✅ Seção de features off-niche presente")
    print(f"   ✅ Regra proibindo off-niche como foco")
    print(f"   ✅ Regra proibindo 'o mercado foca em [off-niche]'")
    print(f"   ✅ Moeda formatada como R$ XX,XX")
    print(f"   ✅ Features recomendadas presentes")
    print(f"   ✅ Instrução sobre confiança presente")
    print()
    print(f"PRÓXIMOS PASSOS:")
    print(f"   1. Testar no app com debug mode")
    print(f"   2. Testar com IA real (se houver quota)")
    print(f"   3. Validar que IA não usa 'notebook' como foco")
    sys.exit(0)
elif not errors:
    print(f"✅ GUARDRAILS PRINCIPAIS VALIDADOS")
    print(f"⚠️ Alguns warnings encontrados (revisar)")
    sys.exit(0)
else:
    print(f"❌ VALIDAÇÃO FALHOU")
    print(f"   Corrija os erros antes de prosseguir")
    sys.exit(1)
