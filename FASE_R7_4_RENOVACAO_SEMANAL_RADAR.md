# Fase R7.4 — Renovação Semanal Automática do Radar

**Status:** Concluído  
**Precedência:** R7.3C ✓ → R7.4A ✓

## Objetivo

Criar um sistema de renovacao semanal do Radar que:
- Revalida concorrentes existentes antes de buscar novos
- Atualiza precos, titulos e status de disponibilidade
- Marca itens indisponiveis apos 3 falhas consecutivas
- So descobre novos concorrentes se a confianca cair abaixo do alvo
- Preserva a base antiga se CDP/site falhar

## Conceito

Cada produto proprio tem um estado de atualizacao:

| Estado | Significado |
|--------|-------------|
| `fresh` | Relatorio recente, confianca suficiente |
| `needs_refresh` | Sem refresh ou vencido |
| `failed_refresh` | Ultima tentativa falhou, base antiga preservada |

Prazo padrao: **7 dias** (`REFRESH_INTERVAL_DAYS`)

## Schema

### `radar_refresh_state`
Metadados de renovacao por produto:
- `own_product_uid`, `status`, `target_confidence`
- `last_confidence_level`, `last_confidence_score`
- `last_report_uid`, `last_refresh_at`, `last_successful_refresh_at`
- `next_refresh_due_at`, `last_error`

### `radar_refresh_runs`
Historico de cada execucao:
- `refresh_uid`, `own_product_uid`, `status`
- `existing_checked`, `existing_updated`, `marked_unavailable`
- `new_urls_found`, `new_candidates_collected`
- `direct_before`, `direct_after`
- `confidence_before`, `confidence_after`

### Campos adicionados em `radar_products`
- `availability_status`: `active`, `unavailable`, `recheck_failed`, `unknown`
- `last_checked_at`, `consecutive_failures` (max 3 antes de marcar unavailable)
- `last_price_seen`, `last_title_seen`

## Fluxo de renovacao (`refresh_radar_for_product`)

1. Garantir Chrome CDP
2. Rechecar concorrentes existentes (abre URL, atualiza preco/titulo)
3. Reclassificar com force
4. Gerar relatorio de padroes
5. Calcular confianca
6. Se confianca < target:
   - Rodar ciclo automatico (max 3 ciclos)
   - Coletar/classificar novos candidatos
   - Gerar relatorio final
7. Atualizar `radar_refresh_state`

### Politica de indisponiveis
- 1 falha: `recheck_failed`
- 2 falhas: `recheck_failed`
- 3 falhas consecutivas: `unavailable` + match alterado para `rejected_unavailable`
- Nunca deletar concorrente na primeira falha

## UI

Seção "Renovação do Radar" no Radar Assistido:
- Status, dias desde ultima, confianca, vencido?
- Aviso de produtos vencidos
- Botoes: "Renovar agora", "Renovar vencidos", "Forcar renovacao completa"
- Progresso durante renovacao

## Arquivos criados/modificados

- `shopee_core/radar_db.py` — tabelas `radar_refresh_state`, `radar_refresh_runs`, colunas availability
- `shopee_core/radar_refresh_service.py` — novo: refresh state, recheck, refresh flow
- `shopee_core/radar_workflow_ui_service.py` — wrappers: `get_refresh_status`, `list_due_for_refresh`, `refresh_product`
- `app.py` — seção "Renovação do Radar" com botões e progresso
- `test_radar_refresh_service.py` — 21 testes (15 R7.4 + 6 R7.4A)

## Correção R7.4A — Refresh usa CDP centralizado

A renovação semanal **não abre Chrome por conta própria**. Ela usa o mesmo helper unificado do Radar Automático/Semiautomático:

1. `ensure_radar_chrome_ready_for_ui()` tenta **reutilizar CDP existente** antes de abrir
2. Se CDP responde em `http://127.0.0.1:9222/json/version`, retorna imediatamente
3. Se não, delega para `ensure_radar_chrome_ready()` que usa o fluxo PS1 + fallback direto
4. Se Chrome falha, o refresh seta `failed_refresh` com `last_error` — sem perder base antiga
5. `recheck_existing_competitors()` verifica CDP antes de conectar Playwright

### Arquivos alterados
- `shopee_core/radar_cdp_service.py` — adicionado `ensure_radar_chrome_ready_for_ui()`
- `shopee_core/radar_refresh_service.py` — usa novo helper, adicionado `_set_failed_refresh_state()`, CDP alive check em `recheck_existing_competitors()`
- `test_radar_refresh_service.py` — 6 novos testes: failed_refresh state, CDP reuse, helper correto

### Critérios de aceite
- Semiautomático continua funcionando ✓ (31 CDP tests)
- Automático continua funcionando ✓ (CDP reuse test)
- Renovação com Chrome já aberto: `ensure_radar_chrome_ready_for_ui()` detecta CDP e reutiliza
- Renovação com Chrome fechado: tenta abrir pelo helper oficial (PS1 + fallback)
- Falha de Chrome não corrompe base antiga ✓ (testado)
- Perfil único: `data/chrome_radar_profile` ✓

## Testes

```bash
python -m pytest test_radar_refresh_service.py -v    # 21 testes
python -m pytest test_radar_cdp_service.py -v          # 31 testes
python -m pytest test_radar_relevance_service.py -v     # 33 testes
python -m pytest test_radar_patterns_service.py -v      # 27 testes
# Total: 112 testes
```

## Smoke manual

### Cenario A: Renovar produto existente
1. Abrir app, navegar para Radar Assistido
2. Selecionar produto com dados de Radar
3. Clicar "Renovar agora"
4. Verificar: recheck executa, relatorio atualizado

### Cenario B: Sem Chrome
1. Fechar Chrome do Radar
2. Clicar "Renovar agora"
3. Verificar: erro "Chrome nao disponivel", base antiga preservada

### Cenario C: Renovar vencidos
1. Clicar "Renovar vencidos"
2. Verificar: produtos vencidos sao renovados em sequencia

## Proximas fases
- R7.5: Auditoria Pro usa dados do Radar
- R7.6: Chatbot usa dados do Radar
- R7.7: Sentinela usa dados do Radar
