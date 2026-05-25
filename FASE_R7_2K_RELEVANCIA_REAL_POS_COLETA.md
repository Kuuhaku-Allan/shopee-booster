# R7.2K — Corrigir relevância real pós-coleta

## Problema

A coleta (R7.2J) agora funciona melhor, mas a classificação dos concorrentes ainda estava errada. Vários produtos claramente relacionados a uma mochila infantil/princesa/escolar apareciam como `rejected` com scores 0, 0.07, 0.1:

| Produto | Score (antes) | Esperado |
|---------|:---:|:---:|
| Mochila Princesas Infantil Escolar Reforçada Impermeável | 0.07 | direct/partial |
| Mochila Infantil Escolar Organizadora Reforçada Impermeável | 0.10 | direct/partial |
| Mochila Infantil Menina Fofa Reforçada Bolsa Escolar Viagem | 0.07 | direct/partial |
| Mochila Infantil Escolar Princesas Reforçada Impermeável | 0.07 | direct/partial |
| Mochila Escolar Infantil Menina Costas Unicórnio Feminina | 0.07 | direct/partial |

## Causa raiz

### 1. Plural/sufixo não era reconhecido (principal causa)

`_pattern_position()` usava `\bword\b` para matching de palavras únicas, que exige correspondência EXATA. Isso **não reconhecia plurais**:

| Texto | Sinônimo | Correspondia? |
|-------|----------|:---:|
| "princesas" | "princesa" | ❌ (`\bprincesa\b` não casa "princesas") |
| "infantis" | "infantil" | ❌ |
| "reforçadas" | "reforcada" | ❌ (era "reforçadas" no título) |

Sem o plural, o candidato perdia sinais de:
- Público (`feminino` de "princesas")
- Estilo (`princesa` de "princesas")
- Features (`reforcada` de "reforcadas")

Resultado: candidatos fúteis sem quase nenhum sinal de audience/style/feature, gerando scores próximos de 0.

### 2. Tokens faltando

"costas", "dinossauro", "gatinho", "florido", "lilás", "hello kitty" não estavam em nenhuma lista de sinônimos.

### 3. Niche floor aplicava mesmo sem candidato ter sinais do nicho

`_apply_niche_floor()` só verificava o produto próprio. Se candidato não tivesse nenhum sinal de público/uso compatível (por falha de matching), o floor ainda assim podia elevar o score artificialmente.

## O que foi feito

### 1. `_pattern_position` — matching flexível para plurais

```python
# Antes (R7.2H):
match = re.search(rf"\b{re.escape(pattern)}\b", text)

# Depois (R7.2K):
match = re.search(rf"\b{re.escape(pattern)}\w{{0,3}}\b", text)
```

O `\w{0,3}` permite até 3 caracteres extras após a palavra base, cobrindo plurais comuns do português:
- "princesa" → "princesas" ✓ (sufixo "s")
- "reforcada" → "reforcadas" ✓ (sufixo "s")
- "organizadora" → "organizadoras" ✓ (sufixo "s")
- "mochila" → "mochilas" ✓ (sufixo "s")
- "escolar" → "escolares" ✓ (sufixo "es")

Sem falsos positivos porque o limite de 3 caracteres impede matches acidentais longos.

### 2. Sinônimos adicionados

**`_STYLE_RULES`**:
| Label | Novos sinônimos |
|-------|----------------|
| `kawaii` | fofinha, fofinho |
| `dinossauro` | dinossauro, dinosaur, t rex, t-rex |
| `gatinho` | gatinho, gatinha, kitten, gato |
| `floral` | floral, florido, florida, flowers |
| `lilas` | lilas, roxo, purple, violeta |
| `personagem` | hello kitty, pokemon, disney, batman, super heroi |
| `personagem_fantasia` | sereia, fada, bailarina, boneca |
| `personagem_infantil` | ursinho, cachorrinho, coelhinho, patinho |

**`_FEATURE_RULES`**:
| Label | Novos sinônimos |
|-------|----------------|
| `costas` | costas, mochila de costas |

**`_AUDIENCE_RULES`**:
| Label | Novos sinônimos |
|-------|----------------|
| `infantil` | infantis |

### 3. Niche floor verifica sinais do candidato (R7.2K)

`_apply_niche_floor()` agora também verifica se o candidato tem pelo menos um sinal de público OU uso compatível antes de aplicar o floor:

```python
has_candidate_niche_signals = (
    "infantil" in cand_audience
    or "feminino" in cand_audience
    or "escolar" in cand_use_case
)
if not has_candidate_niche_signals:
    return score  # não aplica floor
```

### 4. `force_reclassify` em `classify_linked_candidates_for_product`

Novo parâmetro `force_reclassify=True` que roda `dedupe_radar_links_and_matches()` antes de reclassificar, garantindo que matches antigos/stale não interfiram.

### 5. Botão "Reclassificar Concorrentes (forçar)" na UI

Adicionado na interface do Radar em `app.py` — 3 colunas: Classificar | Relatório | Reclassificar (forçar).

### 6. Debug script

`scripts/radar_debug_relevance.py` — uso:

```bash
python scripts/radar_debug_relevance.py OWN_PRODUCT_UID CANDIDATE_PRODUCT_UID
```

Imprime perfil completo de ambos os produtos, score por componente, penalidades, niche floor, verdict e reasons.

### 7. Testes com títulos reais

10 novos testes em `test_radar_relevance_service.py`:

| Teste | Produto Próprio | Candidato | Score mínimo |
|-------|-----------------|-----------|:---:|
| `princesas_infantil_escolar_reforcada_impermeavel` | Mochila Infantil Princesa Rosa Escolar Feminina Grande | Mochila Princesas Infantil Escolar Reforçada Impermeável | >= 0.45 |
| `infantil_escolar_organizadora_reforcada_impermeavel` | idem | Mochila Infantil Escolar Organizadora Reforçada Impermeável | >= 0.45 |
| `hello_kitty_escolar` | idem | Mochila Escolar Hello Kitty Para 3ª A 6ª Série | >= 0.35 |
| `menina_fofa_bolsa_escolar_viagem` | idem | Mochila Infantil Menina Fofa Reforçada Bolsa Escolar Viagem | >= 0.45 |
| `infantil_escolar_princesas_reforcada_impermeavel` | idem | Mochila Infantil Escolar Princesas Reforçada Impermeável | >= 0.45 |
| `menino_menina_infantil_dinossauro_gatinho` | idem | Mochila Escolar Menino Menina Infantil Dinossauro Gatinho | >= 0.35 |
| `bolsa_menina_escolar_princesa_com_estojo` | idem | Mochila Infantil Bolsa Menina Escolar Princesa Com Estojo | >= 0.45 |
| `infantil_menina_costas_unicornio_feminina` | idem | Mochila Escolar Infantil Menina Costas Unicórnio Feminina | >= 0.45 |
| `plural_matching` | — | Mochilas Princesas Infantis Escolares Reforçadas | plurais reconhecidos |
| `niche_floor_sem_sinais` | idem | Mochila Executiva Notebook Trabalho | < 0.35 (rejected) |

### 8. Smoke real esperado

Com produto próprio "Mochila Infantil Princesa Rosa Escolar Feminina Grande":
- Rodar `dedupe_radar_links_and_matches()` 
- Rodar `classify_linked_candidates_for_product(own_uid, force_reclassify=True)`
- Abrir tabela de concorrentes

Esperado:
- Cada candidato aparece uma vez (sem duplicatas)
- Produtos similares deixam de ser todos rejected
- Pelo menos 6 dos 8 candidatos de mochila viram partial/direct
- Reasons explicam sinais positivos (público, uso, features)

## Arquivos modificados

| Arquivo | Alterações |
|---------|-----------|
| `shopee_core/radar_relevance_service.py` | Plural matching, novos sinônimos, niche floor c/ candidato |
| `shopee_core/radar_workflow_ui_service.py` | `force_reclassify` em `classify_linked_candidates_for_product` |
| `app.py` | Botão "Reclassificar Concorrentes (forçar)" |
| `test_radar_relevance_service.py` | 10 novos testes com títulos reais |
| `scripts/radar_debug_relevance.py` | Script de debug de relevância (novo) |
| `FASE_R7_2K_RELEVANCIA_REAL_POS_COLETA.md` | Este documento |
