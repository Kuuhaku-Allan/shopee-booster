# Fase R7.2L.1 — Polimento do Relatório de Padrões

## Problemas Identificados nos Prints
1. Preço formatado como `R 50.91 - R 68.88` em vez de `R$ 50,91 - R$ 68,88`
2. Termos fortes incluíam ruído do ML: `cor`, `desenho`, `tecido`
3. `masculina` aparecia como off-niche mesmo em produtos unissex "menino menina"
4. Faixa sugerida parecia recomendação absoluta, sem advertência
5. Média de imagens mostrava `2` em vez de `1,6`

## O que foi feito

### 1. Formatação BRL (`_brl()`)
Helper `_brl()` no `app.py` que converte `R$ 50.91` → `R$ 50,91`.
Aplicado em:
- Card de faixa de preço
- Detalhes de preço (min/max/avg/median)
- Faixa competitiva observada
- Evidências (preço de cada concorrente)

### 2. Filtro de termos ruidosos
Adicionados ao `TITLE_STOPWORDS` em `radar_patterns_service.py`:
- `cor`, `desenho`, `tecido`, `lisa`, `unidade`, `vendido`, `mercado`, `livre`

Esses termos são metadados de variação do ML, não estratégia de título.
Agora são filtrados como stopwords (nem aparecem em top_terms).

### 3. Off-niche masculina ajustada
Em `analyze_feature_patterns()`, quando `feature == "masculina"`:
- Se `feminina` também está presente nas features (unissex), a feature NÃO é marcada como off-niche
- Só é off-niche quando `masculina` aparece sozinha (adulto/masculino predominante)

### 4. Faixa de preço renomeada
- "Faixa sugerida" → "Faixa competitiva observada"
- Adicionado disclaimer: *"Use esta faixa como referência de mercado, não como preço final automático. A decisão deve considerar margem, qualidade, marca, frete e posicionamento."*
- Campos `band_label` e `band_disclaimer` na resposta de `analyze_price_patterns()`

### 5. Média de imagens
- Agora exibe 1 casa decimal com separador `,` (ex: `1,6`)
- Recommendation text também usa `,` como separador decimal

### 6. Evidências
- Preço formatado via `_brl()`

## Arquivos Alterados
- `shopee_core/radar_patterns_service.py` — stopwords, off-niche masculina, band label, image text
- `app.py` — `_brl()` helper, price formatting, band rename, image count format
- `test_radar_patterns_service.py` — 4 novos testes R7.2L.1 (22/22 passando)

## Testes Novos
- `test_noise_terms_removed_from_strong` — cor/desenho/tecido/lisa não são strong_terms
- `test_notebook_off_niche` — notebook continua off-niche
- `test_menino_menina_not_off_niche` — "menino menina" não ativa masculina off-niche
- `test_price_has_band_label` — band_label e band_disclaimer presentes

## Smoke Esperado (após deploy)
- Preço formatado como R$ XX,XX (vírgula)
- Strong terms sem cor/desenho/tecido
- Off-niche mostra notebook, não alerta masculino para "menino menina"
- Faixa de preço aparece como "Faixa competitiva observada" com disclaimer
- Evidências formatadas em BRL
