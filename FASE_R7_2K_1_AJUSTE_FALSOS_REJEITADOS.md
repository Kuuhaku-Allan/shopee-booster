# Fase R7.2K.1 — Ajuste de Falsos Rejeitados

## Problema
Após R7.2K, o candidato "Mochila Infantil Menina Fofa Reforçada Bolsa Escolar Viagem" (e1a1f6c25cec41fe8fbc9bb53ae68f07) ainda scoring 0.25 (rejected) com a descrição rica do Mercado Livre.

Falso rejeitado identificado — a descrição continha "Compartimento para notebook: Sim" e "Idade: Adultos" nos atributos do produto, que o classificador convertia em sinais `notebook` (feature) e `adulto` (audience), ativando a penalidade de -35 em `_niche_mismatch_penalty`.

## Causa Raiz
A descrição rica dos candidatos ML inclui campos de especificação técnica (ex: "Com compartimento para notebook": "Sim", "Idade": "Adultos") que geram tokens `notebook` e `adulto` no perfil. A função `_niche_mismatch_penalty` penalizava em -35 sempre que via `has_notebook + (has_work_signals or has_adult_signals)`, sem considerar se o candidato também tem fortes sinais infantis/escolares.

## Solução
Em `_niche_mismatch_penalty()`, quando o candidato tem sinais claros de público infantil/escolar (`infantil` ou `feminino` na audience + `escolar` no use_case) junto com `notebook`/`adulto`, a penalidade cai de -35 para -15. A lógica: "Compartimento para notebook" é um acessório da mochila, não define seu público. O mesmo para "Idade: Adultos" que é um campo de categorização do ML.

## Impacto
- Viagem candidate: 0.25 → 0.45 (competitor_partial)
- COSITAS variant (title-only test): 0.85 (competitor_direct) — já estava ok
- Nenhum teste existente quebrado (33/33 passing)

## Arquivos Alterados
- `shopee_core/radar_relevance_service.py` — `_niche_mismatch_penalty()`: condicional `cand_has_strong_child_school` reduz penalidade
- `scripts/radar_debug_relevance.py` — encoding fix para Windows console (UTF-8 reconfigure)

## Testes
- `test_r72k_menina_fofa_reforcada_bolsa_escolar_viagem` — assert score >= 0.45 (novo threshold)
- `test_r72k_infantil_escolar_organizadora_reforcada_impermeavel` — assert score >= 0.45 (já passava)
- Todos os 33 testes do radar relevance passam
