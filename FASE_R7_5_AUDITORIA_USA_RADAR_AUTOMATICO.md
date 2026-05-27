# Fase R7.5 - Auditoria usa Radar automaticamente

**Status:** R7.5A concluida  
**Precedencia:** R7.4 concluida

## Objetivo

Integrar o Radar a Auditoria Pro como uma camada automatica de evidencia de mercado.
O usuario escolhe o produto e gera a otimizacao; o sistema decide se usa scraping em
tempo real, Radar local, uma composicao dos dois ou nenhuma base.

## R7.5 parcial vs R7.5A

A primeira entrega da R7.5 deixou a tela mais limpa, mas a decisao ainda estava
concentrada na UI. A Auditoria real, usada por servicos como WhatsApp/API, continuava
dependendo do parametro manual `radar_own_product_uid`.

A R7.5A fecha essa lacuna:

- `generate_product_optimization()` agora chama `choose_audit_market_source()`.
- A decisao scraping/Radar acontece no core da Auditoria.
- A UI apenas pre-visualiza status e mostra o resultado retornado pelo core.
- `radar_own_product_uid` segue existindo como override de desenvolvimento.

## Regra final de decisao

| Scraping | Radar | Resultado |
|---|---|---|
| Bom, com titulo/preco/identificacao | Ausente | `scraping` |
| Falho/fraco | High/medium fresh e efetivo | `radar` |
| Bom | High fresh, efetivo e mais robusto | `hybrid` |
| Bom | Stale/vencido | `scraping` + warning para renovar |
| Falho | High/medium stale | `radar` + warning de base vencida |
| Falho | Ausente/low/insufficient | `none` + aviso para construir Radar |

## Qualidade do scraping

Scraping nao e mais considerado bom apenas por retornar linhas. Agora precisa ter:

- pelo menos 3 concorrentes uteis;
- titulo presente na maioria;
- preco valido na maioria;
- URL ou identificacao na maioria;
- baixa chance de dados placeholder.

Exemplo corrigido: 3 linhas sem titulo e sem preco retornam `ok=False`.

## Status Radar para Auditoria

`get_radar_market_status_for_audit(product)` retorna:

- `has_radar`
- `product_uid` / `radar_product_uid`
- `confidence_level`
- `confidence_score`
- `competitor_count`
- `effective_competitor_count`
- `effective_direct_count`
- `effective_partial_count`
- `direct_count`
- `partial_count`
- `report_uid` / `radar_report_uid`
- `is_fresh`
- `last_refresh_at`
- `last_report_at`
- `status`
- `warnings`

As contagens efetivas e avisos vem do quality gate da R7.3E, sempre que disponivel.

## Retorno da Auditoria

`generate_product_optimization()` agora inclui no retorno:

```python
{
    "market_source": "scraping|radar|hybrid|none",
    "market_source_reason": "...",
    "radar_used": True,
    "scraping_used": False,
    "radar_confidence": "high",
    "radar_report_uid": "...",
    "warnings": [...],
    "market_source_details": {...},
}
```

## UI

`app.py` continua mostrando o bloco "Base de Mercado", mas a geracao chama
`generate_product_optimization()` e usa `market_source_details` retornado pelo core.

Debug segue escondido atras de:

```bash
SHOPEE_DEV_DEBUG_RADAR=1
```

## Testes

Validados:

```bash
python -m py_compile shopee_core/audit_market_source_service.py shopee_core/audit_service.py shopee_core/radar_audit_context_service.py backend_core.py app.py
python -m pytest test_audit_market_source_service.py test_audit_radar_integration.py -q -p no:cacheprovider
```

Coberturas adicionadas:

- scraping com 3 linhas sem titulo/preco vira `ok=False`;
- Radar high fresh retorna status completo;
- Radar high stale gera warning;
- scraping bom + Radar stale escolhe scraping;
- scraping falha + Radar high fresh escolhe Radar;
- scraping falha + Radar stale escolhe Radar com warning;
- scraping falha + Radar ausente escolhe none;
- `effective_competitor_count` influencia decisao;
- `generate_product_optimization()` chama o seletor automatico;
- quando Radar e escolhido, `radar_context_block` chega ao `generate_full_optimization()`;
- retorno da Auditoria inclui `market_source` e motivo.

## Smoke manual esperado

### Produto com Radar high fresh + scraping falho

Esperado:

- `market_source = radar`
- contexto Radar enviado ao prompt
- badge "Base usada: Radar"

### Produto sem Radar + scraping bom

Esperado:

- `market_source = scraping`
- otimizacao segue normalmente

### Produto sem Radar + scraping falho

Esperado:

- `market_source = none`
- UI orienta construir base Radar

### Produto com Radar stale + scraping bom

Esperado:

- `market_source = scraping`
- warning para renovar Radar
