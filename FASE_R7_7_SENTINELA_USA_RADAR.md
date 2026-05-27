# Fase R7.7 - Sentinela usa Radar como fallback

## Objetivo

Adicionar o Radar como fonte opcional de concorrentes para a Sentinela, sem
alterar gatilho, lock, agendamento, estado ou fluxo de disparo.

## Regra de seguranca

Esta fase nao refatora a Sentinela. O lock continua em `request_sentinel_execution()`
e `mark_sentinel_finished()`, e o agendamento continua fora do novo provider.

O Radar entra apenas na etapa em que a Sentinela ja tem uma lista de
concorrentes para analisar.

## Feature flag

O uso do Radar na Sentinela depende de:

```powershell
$env:SHOPEE_SENTINEL_USE_RADAR = "1"
```

Com a flag desligada, a fonte atual permanece como antes. Se a fonte atual
falhar e a flag estiver desligada, a Sentinela apenas informa que nao ha fonte
de concorrentes suficiente.

## Fonte de concorrentes

Novo servico:

```text
shopee_core/sentinel_competitor_source_service.py
```

Funcoes principais:

- `get_radar_competitors_for_sentinel(own_product_uid, limit=10)`
- `choose_sentinel_competitor_source(product, current_competitors, radar_status, limit=10)`
- `normalize_sentinel_competitors(competitors, keyword, limit=10)`

Regras:

- concorrente valido precisa de titulo, preco, URL e marketplace/fonte;
- Radar usa `competitor_direct` primeiro;
- se faltar espaco, completa com `competitor_partial`;
- `rejected` nao entra;
- produtos removidos/indisponiveis sao ignorados;
- itens sem preco nao entram como concorrente principal;
- limite padrao do Telegram/relatorio continua pequeno, top 10 na fonte e top 5 no resumo.

## Decisao

- Fonte atual com 5+ concorrentes uteis vence por padrao.
- Fonte atual usando `mock` perde para Radar high/medium com base suficiente.
- Fonte atual fraca ou vazia usa Radar high/medium quando disponivel.
- Radar vencido so entra como fallback e gera aviso de renovacao.
- Sem fonte atual e sem Radar suficiente, a Sentinela retorna `source="none"` sem quebrar.

## Integracao

O helper `select_sentinel_competitors()` foi adicionado em
`shopee_core/sentinel_service.py`, mas nao altera as funcoes de lock.

O fluxo `_run_sentinel_bg()` continua:

```text
adquire lock -> busca fonte atual -> escolhe concorrentes -> gera relatorio -> finaliza lock
```

A unica diferenca e que a lista de concorrentes passa por `select_sentinel_competitors()`.
Se o Radar falhar, o helper cai para a fonte atual e registra warning.

## Telegram

Quando o Radar for usado, o payload do Telegram inclui um bloco discreto:

```text
Base de concorrentes: Radar
Confianca: HIGH
Concorrentes efetivos: 9
Concorrentes monitorados
1. Produto... - R$ 99.90
```

Nao ha JSON bruto nem debug.

## Testes

Arquivos adicionados:

- `test_sentinel_competitor_source_service.py`
- `test_sentinel_radar_integration.py`

Cobertura:

- Radar high/fresh retorna concorrentes;
- Radar ignora item sem preco;
- Radar nao consulta rejected;
- fonte atual boa vence quando Radar nao e claramente melhor;
- provider mock perde para Radar;
- fonte atual falha + Radar high usa Radar;
- Radar stale entra com warning quando e fallback;
- fonte atual falha + Radar ausente retorna none;
- helper nao deixa falha do Radar escapar;
- wrappers de lock continuam chamando `try_acquire_sentinel_lock` e `finish_sentinel_lock`;
- Telegram mostra resumo Radar sem JSON.

## Smoke manual sugerido

1. Ativar a flag:

```powershell
$env:SHOPEE_SENTINEL_USE_RADAR = "1"
```

2. Rodar um ciclo manual da Sentinela em produto com Radar high.
3. Confirmar:

- lock inicia;
- concorrentes usam Radar quando a fonte atual estiver fraca/mock;
- Telegram mostra "Base de concorrentes: Radar";
- lock finaliza;
- status volta ao normal.

4. Desligar/indisponibilizar Radar e repetir:

- fluxo atual continua;
- Sentinela nao trava;
- lock finaliza normalmente.
