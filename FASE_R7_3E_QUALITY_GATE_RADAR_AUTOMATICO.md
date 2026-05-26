# Fase R7.3E - Quality Gate do Radar Automatico

## Problema observado

O Radar Automatico passou a executar o ciclo completo e atingir `HIGH`, mas a base ainda podia conter ruido:

- produtos fora de nicho, como mochila de natacao, aparecendo como concorrente direto;
- variacoes muito parecidas inflando a contagem bruta;
- `notebook` voltando como feature recomendada;
- faixas de preco em Markdown perdendo o `$`;
- termos de baixa recorrencia misturando numeros, marcas e ruido de vendedor.

## Quality Gate

O relatorio agora separa contagem bruta de concorrentes da base efetiva:

- `total_competitors`: produtos classificados usados antes do agrupamento;
- `effective_competitor_count`: representantes apos agrupamento de variacoes;
- `effective_direct_count`: diretos efetivos;
- `effective_partial_count`: parciais efetivos;
- `variants_grouped`: variacoes agrupadas.

O `HIGH` passa a depender da base efetiva, nao da contagem bruta.

## Clustering de variacoes

Foi criada a funcao `cluster_competitor_variants(candidates)`.

Ela agrupa candidatos quando ha evidencia de duplicidade ou variacao muito proxima:

- mesmo marketplace product id;
- mesma URL canonica;
- titulo muito semelhante com vendedor igual ou preco aproximado;
- variacao do mesmo vendedor com preco proximo.

Cada cluster retorna:

- `cluster_id`;
- `representative_candidate`;
- `variants_count`;
- `candidates`;
- `reason`.

As analises de preco, titulo, features, descricao, imagens e evidencias usam o representante do cluster.

## Nichos paralelos e off-niche

Foram reforcadas penalidades para usos fora do nicho infantil escolar:

- natacao/Nabaiji/piscina;
- praia;
- esporte/academia;
- trekking/trilha;
- hidratacao;
- notebook;
- executivo/corporativo/urbano adulto.

Se o produto proprio e mochila infantil escolar e o candidato tem natacao sem sinais fortes de escola/personagem/princesa/unicornio, o score e capado em `0.45` e nao pode virar `competitor_direct`.

## Features recomendadas

`recommended_features` agora remove qualquer feature presente em `off_niche_features`.

Além disso, a confiança bloqueia `HIGH` se algum termo off-niche conhecido aparecer como recomendado, como `notebook`.

## Termos de baixa recorrencia

Os termos de titulo passam a filtrar ruido antes da estrategia:

- tokens numericos ou com digitos, como `10l`, `16l`, `20l`;
- marcas/vendedores observados como `nabaiji`, `up4you`, `marechal`;
- termos operacionais como `agua`, `prova`, `partes`, `alca`, `alcas`, `top`.

A lista visual de baixa recorrencia fica limitada a 20 termos ja limpos.

## BRL em Markdown

Foi criado `format_brl_markdown(value)`, que retorna valores como `R\$ 33,65`.

Esse formato evita que o Streamlit Markdown interprete `$` como delimitador matematico e renderize `R 33,65`.

## Resultado esperado

Ao rodar o Radar no produto atual:

- Nabaiji/natacao nao deve ser `competitor_direct`;
- `notebook` pode aparecer em off-niche, mas nunca em features recomendadas;
- o relatorio mostra concorrentes brutos, efetivos e variacoes agrupadas;
- `HIGH` so aparece quando a base efetiva for robusta;
- faixas de preco aparecem como `R$`;
- termos de baixa recorrencia ficam mais limpos.

## Validacao

Comandos usados:

```bash
python -m py_compile shopee_core/radar_patterns_service.py shopee_core/radar_relevance_service.py shopee_core/radar_discovery_service.py app.py scripts/radar_discover_worker.py
python -m pytest test_radar_patterns_service.py test_radar_relevance_service.py test_radar_discovery_service.py -q -p no:cacheprovider
```
