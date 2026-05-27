# Fase R7.5 — Auditoria usa Radar automaticamente

**Status:** Concluído  
**Precedência:** R7.4 ✓

## Objetivo

Integrar o Radar à Auditoria Pro de forma automática, limpa e sem poluir a tela.
A Auditoria escolhe a melhor base de concorrentes:

1. Scraping normal se funcionar bem
2. Radar se existir base local confiável
3. Radar como fallback automático se scraping falhar
4. Aviso guiado se ambos falharem

## O que mudou

### UI da Auditoria (app.py)

**Removido:**
- Expansor "📡 Radar Assistido de Concorrentes" (seleção manual)
- Checkbox "Usar Radar Assistido nesta auditoria"
- Selectbox de produto Radar
- Input manual de UID
- Debug checkbox público
- Badge "Radar Assistido usado nesta auditoria"

**Adicionado:**
- Bloco compacto "📊 Base de Mercado" — mostra status do Radar automaticamente
- Badge pós-otimização: "📡 Base usada: Radar" ou "🌐 Base usada: Scraping"
- Expansor "Ver detalhes da base usada" opcional
- Debug atrás de env var `SHOPEE_DEV_DEBUG_RADAR=1`

### Novo serviço: `audit_market_source_service.py`

Três funções principais:

```python
get_radar_market_status_for_audit(product: dict) -> dict
```
Busca produto Radar correspondente por similaridade de título.
Retorna: has_radar, product_uid, confidence_level, direct_count, is_fresh, warnings

```python
evaluate_scraping_market_quality(scraping_result) -> dict
```
Avalia qualidade do scraping.
Retorna: ok, competitor_count, has_prices, has_titles, quality_score (0-1), warnings

```python
choose_audit_market_source(product, scraping_result=None, radar_status=None) -> dict
```
Escolhe a melhor fonte automaticamente.
Retorna: source, reason, radar_used, scraping_used, warnings

### Regra de decisão

| Caso | Scraping | Radar | Resultado |
|------|----------|-------|-----------|
| A | Bom | Não existe | Scraping |
| B | Falha | Existe (high/medium) | Radar |
| C1 | Bom | Bom (high/medium) | Hybrid (prefere Radar) |
| C2 | Bom | Baixo/Stale | Scraping |
| C3 | Fraco (<5) | Bom | Radar |
| D | Falha | Não existe | None + aviso |

### Fluxo da otimização

1. Produto selecionado → auto-detecta Radar (`get_radar_market_status_for_audit`)
2. "Gerar Otimização" → `choose_audit_market_source(prod, df_comp, radar_status)`
3. Se Radar escolhido: `build_radar_audit_context()` + `build_radar_prompt_block()`
4. Gera listing com contexto do Radar ou só scraping
5. Exibe badge: "Base usada: Radar" com expander de detalhes

## Arquivos

- `shopee_core/audit_market_source_service.py` — novo: seletor automático
- `app.py` — UI limpa, auto-source, badge
- `test_audit_market_source_service.py` — 14 testes

## Testes

```bash
python -W ignore -m pytest test_audit_market_source_service.py -v
# 14 testes
```

Criar também `test_audit_market_source_sanity.py` para smoke:
- Scraping ok + sem Radar → scraping
- Scraping falha + Radar high → radar
- Ambos falham → none
- Ambos ok → hybrid/radar

## Smoke manual

### Cenário A: Produto com Radar high
1. Selecionar produto que tem base Radar
2. Verificar bloco "Radar disponível: confiança high"
3. Clicar "Gerar Otimização Completa"
4. Esperado: badge "📡 Base usada: Radar"

### Cenário B: Produto sem Radar
1. Selecionar produto sem base Radar
2. Verificar "produto não possui base Radar"
3. Clicar "Gerar Otimização Completa" (scraping precisa ter sido feito)
4. Esperado: badge "🌐 Base usada: Scraping"

### Cenário C: Sem scraping + sem Radar
1. Não buscar concorrentes, selecionar produto sem Radar
2. Clicar "Gerar Otimização Completa"
3. Esperado: badge "⚠️ Nenhuma base de mercado disponível"
