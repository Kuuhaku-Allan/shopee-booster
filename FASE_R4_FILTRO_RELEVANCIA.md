# Fase R4 - Filtro de Relevancia de Concorrentes

## Objetivo

Criar o primeiro filtro de relevancia do Radar Assistido, comparando um produto proprio com produtos candidatos ja cadastrados/coletados.

A R4 classifica cada candidato como:

- `competitor_direct`
- `competitor_partial`
- `rejected`

Esta fase nao integra com Bot WhatsApp, Auditoria, Sentinela, scraping Shopee, descoberta automatica de URLs ou geracao final de otimizacao.

## Persistencia

A R4 cria a tabela `radar_competitor_matches`:

- `match_uid`
- `own_product_uid`
- `candidate_product_uid`
- `verdict`
- `relevance_score`
- `confidence`
- `reasons_json`
- `signals_json`
- `created_at`
- `updated_at`

Existe uma restricao unica para `own_product_uid + candidate_product_uid`, entao reclassificar o mesmo par atualiza o match em vez de duplicar.

## Criterios de pontuacao

O filtro e baseado em regras simples em portugues:

- mesmo tipo de produto: ate 30 pontos
- mesmo publico-alvo: ate 25 pontos
- mesmo uso principal: ate 20 pontos
- estilo/tema parecido: ate 15 pontos
- faixa de preco compativel: ate 10 pontos

Penalidades:

- produto claramente diferente: -40
- publico claramente diferente: -25
- uso claramente diferente: -20
- preco muito distante: -10

Classificacao:

- `score >= 0.72`: `competitor_direct`
- `score >= 0.45`: `competitor_partial`
- `score < 0.45`: `rejected`

## Exemplos

Concorrente direto:

```text
Mochila infantil escolar rosa com rodinhas
vs
Mochila princesa rosa infantil escolar com rodinhas
```

Concorrente parcial:

```text
Mochila minimalista branca grande
vs
Mochila casual branca reforcada
```

Rejeitado:

```text
Mochila infantil rosa escolar
vs
Lancheira infantil rosa escolar
```

## Como rodar

Classificar candidatos:

```bash
python scripts/radar_classify_competitors.py OWN_PRODUCT_UID --limit 50
```

Simular sem salvar:

```bash
python scripts/radar_classify_competitors.py OWN_PRODUCT_UID --limit 50 --dry-run
```

Mostrar rejeitados no relatorio:

```bash
python scripts/radar_classify_competitors.py OWN_PRODUCT_UID --show-rejected
```

Inspecionar matches persistidos:

```bash
python scripts/radar_inspect_matches.py OWN_PRODUCT_UID
```

## Limitacoes

- O filtro e deterministico e nao usa IA.
- Sinonimos, girias e marcas ainda podem escapar das regras.
- A classificacao depende da qualidade do titulo, descricao, atributos e categoria coletados.
- Imagens baixadas na R3 ainda nao entram na decisao.
- O score foi calibrado para ser explicavel primeiro; a precisao deve melhorar com exemplos reais.

## Proximos passos

R5 deve analisar padroes de sucesso entre concorrentes diretos:

- argumentos recorrentes
- atributos valorizados
- faixa de preco normal
- imagens essenciais
- reclamacoes repetidas
