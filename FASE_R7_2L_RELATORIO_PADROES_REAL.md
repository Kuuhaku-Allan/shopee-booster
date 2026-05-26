# Fase R7.2L — Relatório Real de Padrões com Concorrentes Reclassificados

## Contexto
Após R7.2K.1 corrigir os falsos rejeitados, a tabela de relevância ficou coerente:
- **5 competitor_direct**
- **5 competitor_partial**
- **1 rejected**

Produto próprio: "Mochila Infantil Princesa Rosa Escolar Feminina Grande"

Esta fase valida se o Radar consegue gerar um relatório de padrões útil a partir
desses concorrentes reclassificados.

## O que foi feito

### 1. `candidate_scope` em `generate_pattern_report()`
Novo parâmetro `candidate_scope` (valores: `"direct_only"` ou `"direct_plus_partial"`):
- `direct_only` (default): apenas `competitor_direct`
- `direct_plus_partial`: `competitor_direct` peso 1.0, `competitor_partial` peso 0.5

O parâmetro `include_partial` legado continua funcionando, mas `candidate_scope` o substitui quando fornecido.

### 2. Análise ponderada (weighted)
Todas as funções de análise (`analyze_price_patterns`, `analyze_title_terms`,
`analyze_feature_patterns`, `analyze_description_patterns`) agora aceitam um
parâmetro opcional `weights: dict[str, float]` para ponderar a contribuição
de cada concorrente. Para `direct_plus_partial`, cada `competitor_partial` 
contribui com metade do peso de um `competitor_direct`.

### 3. Novos tiers de confiança
| Tiers | Critério |
|-------|----------|
| high | 10+ diretos OU 7+ diretos com parciais bons |
| medium | 5+ diretos |
| low | 3-4 diretos |
| insufficient | menos de 3 |

Para o caso atual (5 direct, 5 partial): **medium**.

### 4. Seções de estratégia no relatório
O relatório agora inclui:

**A) Resumo de Mercado:**
- total_direct, total_partial
- preço min/max/avg/median
- dispersão (aviso se CV > 0.5)
- confiança

**B) Estratégia de Título (`strategy_title`):**
- Termos fortes (≥40% frequência)
- Termos secundários (20-40%)
- Termos a evitar (<20%)

**C) Estratégia de Features (`strategy_features`):**
- Features recomendadas (strong patterns)
- Features off-niche
- Warnings

**D) Estratégia de Descrição (`strategy_description`):**
- Argumentos comerciais recorrentes
- Termos de qualidade
- Argumentos de uso
- Observações/oportunidades

**E) Estratégia de Imagem (`strategy_images`):**
- Média de imagens
- Recomendações

**F) Evidências (`evidence_list`):**
- Lista de concorrentes usados com score, verdict, preço

### 5. Filtragem aprimorada
- Rejected nunca entra no relatório (já existia, verificado)
- Candidatos sem título/preço são excluídos via `validate_product_extraction` (já existia)
- URLs fake são filtradas (já existia)
- Apenas produtos vinculados ao `own_product_uid` atual (já existia)

### 6. Integração na UI
Na tela "Radar Assistido":
- Seletor de escopo: "Diretos apenas" / "Diretos + Parciais"
- Botão "Gerar/Atualizar Relatório de Padrões"
- Preview com 5 abas (Termos do Título, Features, Descrição, Imagens, Evidências)
- Métricas de confiança, total, escopo, faixa de preço
- Detalhes de preço em expander

### 7. Script de inspeção
`scripts/radar_inspect_patterns.py` — exibe o relatório mais recente ou gera
um novo com escopo especificado.

## Arquivos Alterados
- `shopee_core/radar_patterns_service.py` — análise ponderada, strategy sections,
  confidence tiers, `candidate_scope`
- `shopee_core/radar_workflow_ui_service.py` — `run_pattern_analysis_for_product`
  aceita `candidate_scope`
- `app.py` — UI do relatório com seletor de escopo e preview
- `test_radar_patterns_service.py` — 8 novos testes R7.2L
- `scripts/radar_inspect_patterns.py` — novo script de inspeção
- `FASE_R7_2L_RELATORIO_PADROES_REAL.md` — esta documentação

## Testes (18 total, todos passam)
- `test_candidate_scope_direct_only` — apenas diretos
- `test_candidate_scope_direct_plus_partial` — inclui parciais
- `test_confidence_medium_with_5_direct` — confidence medium
- `test_confidence_high_with_10_direct` — confidence high
- `test_strategy_sections_present` — todas as seções existem
- `test_evidence_list_includes_competitors` — evidências corretas
- `test_price_dispersion_warning` — aviso de dispersão
- `test_relatorio_escopo_salvo_e_recuperado` — escopo persiste no banco

## Limitações
- Análise de imagens ainda sem CV (apenas contagem)
- Preço sugerido é banda simples (mediana ±15%)
- A ponderação 0.5 para partials é um valor fixo; poderia ser refinado
  com base no relevance_score no futuro

## Recomendação
O relatório agora está acessível na UI e pode ser consumido pela Auditoria
via `get_latest_pattern_report()`. A fase R7.3 (busca semiautomática de
concorrentes) pode começar — o fluxo base está completo.
