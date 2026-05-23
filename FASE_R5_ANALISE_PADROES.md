# Fase R5 - Analise de Padroes de Sucesso

## Objetivo

Criar o primeiro motor de analise de padroes do Radar Assistido.

A R5 usa produtos ja classificados pela R4 como `competitor_direct` para gerar um relatorio estruturado de nicho com:

- faixa de preco
- termos fortes em titulos
- features recorrentes
- argumentos comerciais nas descricoes
- sinais simples de imagens/assets
- recomendacoes explicaveis

Esta fase nao integra com Bot WhatsApp, Auditoria, Sentinela, geracao final de listing, coleta Shopee, descoberta automatica de URLs ou IA generativa obrigatoria.

## Como o relatorio e gerado

1. Carrega matches `competitor_direct` em `radar_competitor_matches`.
2. Busca os produtos candidatos completos em `radar_products`.
3. Enriquecce com `raw_json` e `radar_assets`.
4. Calcula padroes de preco, titulo, features, descricao e imagens.
5. Gera recomendacoes deterministicas com evidencia.
6. Salva o resultado em `radar_pattern_reports`.

## Tabela criada

`radar_pattern_reports` guarda:

- produto proprio analisado
- total de concorrentes usados
- contagem de diretos/parciais
- preco minimo, maximo, medio e mediano
- termos de titulo em JSON
- features em JSON
- padroes de descricao em JSON
- padroes de imagem em JSON
- avisos
- recomendacoes
- relatorio bruto em JSON

## Como rodar

Gerar e salvar relatorio:

```bash
python scripts/radar_analyze_patterns.py OWN_PRODUCT_UID --save
```

Incluir parciais na analise, se a base de diretos estiver pequena:

```bash
python scripts/radar_analyze_patterns.py OWN_PRODUCT_UID --include-partial --save
```

Inspecionar ultimo relatorio salvo:

```bash
python scripts/radar_inspect_patterns.py OWN_PRODUCT_UID
```

## Limites da analise sem IA

- Nao interpreta imagens visualmente; usa apenas quantidade, URLs e assets.
- Nao entende sinonimos complexos fora dos dicionarios de regras.
- Nao mede qualidade real de venda, apenas padroes dos concorrentes classificados.
- Relatorios com menos de 3 concorrentes diretos recebem aviso de base pequena.
- Relatorios com menos de 5 diretos usam confianca `low` ou `medium`.

## Exemplo de saida

```text
Produto proprio: Mochila Infantil Princesa Rosa Escolar Feminina Grande
Concorrentes analisados: 2
Diretos: 2
Preco: min R$ 89.90 | avg R$ 94.90 | median R$ 94.90 | max R$ 99.90
Top termos: mochila, infantil, feminina, rosa, escolar
Top features: escolar, infantil, feminina, princesa, rodinhas
Aviso: Base pequena. Recomendacoes podem ser pouco confiaveis.
```

## Smoke R5

Produto usado:

```text
7be29cd3-e6aa-4bda-9fb9-b9c94dc398db
Mochila Infantil Princesa Rosa Escolar Feminina Grande
```

Comandos executados:

```bash
python scripts/radar_seed_relevance_smoke.py
python scripts/radar_run_relevance_smoke.py
python scripts/radar_analyze_patterns.py 7be29cd3-e6aa-4bda-9fb9-b9c94dc398db --save
python scripts/radar_inspect_patterns.py 7be29cd3-e6aa-4bda-9fb9-b9c94dc398db
```

Resultado salvo:

```text
report_uid: f88ca54b-5b6b-45c7-8b92-4f283b051fc0
concorrentes analisados: 2
diretos: 2
parciais cadastrados: 3
confianca: low
preco: min=84.9 avg=92.4 median=92.4 max=99.9
```

Termos fortes:

```text
escolar, feminina, infantil, mochila, rosa, grande, princesa, rodinhas
```

Features fortes:

```text
escolar, feminina, infantil, grande, princesa, rodinhas
```

Argumento comum:

```text
espaco interno
```

Avisos gerados:

```text
Base pequena. Recomendacoes podem ser pouco confiaveis.
Concorrentes diretos abaixo do minimo solicitado (3).
Concorrentes diretos tem poucas imagens em media.
Nenhum asset baixado encontrado; analise de imagens usa apenas URLs/metadados.
```

Recomendacoes geradas:

```text
Incluir "rodinhas" no titulo.
Destacar "rodinhas" como feature.
Adicionar "espaco interno" na descricao.
```

Conclusao: R5 aprovada. O relatorio foi salvo em `radar_pattern_reports`, analisou somente `competitor_direct`, ignorou rejeitados e alertou corretamente sobre base pequena.

## Proximos passos

R6 deve integrar o relatorio do Radar com a Auditoria do `.exe`, para que sugestoes de titulo, preco, descricao e argumentos sejam baseadas em evidencias dos concorrentes diretos.
