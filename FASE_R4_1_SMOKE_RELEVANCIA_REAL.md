# Fase R4.1 - Smoke Test Real do Filtro de Relevancia

## Objetivo

Validar o filtro de relevancia R4 usando registros reais no `data/radar.db`, antes de avancar para a R5.

Esta fase nao adiciona IA, nao altera coleta/scraping e nao mexe em Bot WhatsApp, Auditoria ou Sentinela.

## Produto proprio

```text
Mochila Infantil Princesa Rosa Escolar Feminina Grande
```

Descricao usada:

```text
Mochila infantil feminina rosa para escola, ideal para meninas, com tema princesa, espaco para cadernos, estojo e material escolar. Produto voltado para criancas em idade escolar.
```

Preco:

```text
89.90
```

## Candidatos

| Candidato | Esperado |
| --- | --- |
| Mochila Escolar Infantil Feminina Princesa Rosa com Rodinhas | `competitor_direct` |
| Mochila Infantil Feminina Rosa Escolar Grande | `competitor_direct` ou `competitor_partial` alto |
| Mochila Escolar Juvenil Feminina Colorida | `competitor_partial` |
| Mochila Universitaria Notebook Executiva Preta | `rejected` ou `partial` baixo |
| Lancheira Infantil Rosa Princesa Termica | `rejected` |
| Estojo Escolar Infantil Rosa | `rejected` |

## Como rodar

```bash
python scripts/radar_seed_relevance_smoke.py
python scripts/radar_run_relevance_smoke.py
```

## Resultados obtidos

Execucao:

```bash
python scripts/radar_seed_relevance_smoke.py
python scripts/radar_run_relevance_smoke.py
```

Resumo:

```text
Total: 6
Diretos: 2
Parciais: 1
Rejeitados: 3
Score medio: 0.54
```

Resultados:

| Candidato | Resultado | Score | Confiança |
| --- | --- | ---: | --- |
| Mochila Escolar Infantil Feminina Princesa Rosa com Rodinhas | `competitor_direct` | 1.00 | high |
| Mochila Infantil Feminina Rosa Escolar Grande | `competitor_direct` | 1.00 | high |
| Mochila Escolar Juvenil Feminina Colorida | `competitor_partial` | 0.605 | medium |
| Mochila Universitaria Notebook Executiva Preta | `rejected` | 0.28 | medium |
| Lancheira Infantil Rosa Princesa Termica | `rejected` | 0.23 | high |
| Estojo Escolar Infantil Rosa | `rejected` | 0.10 | high |

Motivos observados:

- diretos: mesmo tipo `mochila`, mesmo publico `feminino/infantil`, mesmo uso `escolar`, estilo compativel e preco compativel.
- parcial juvenil: mesmo tipo e uso, mas publico-alvo parcialmente diferente (`infantil` vs `juvenil`).
- notebook executiva: mesmo tipo geral, mas publico/uso/preco afastam o produto proprio infantil escolar.
- lancheira/estojo: rejeitados por tipo de produto diferente, mesmo com sinais parecidos de publico/tema.

## Ajustes feitos

- O primeiro smoke revelou que `category_path` contendo `Mochilas e Bolsas` fazia `Lancheira` e `Estojo` serem detectados como `mochila`.
- A regra de `product_type` foi ajustada para escolher o tipo pela primeira ocorrencia semantica no texto, priorizando o titulo antes de categorias amplas.
- O seed tambem passou a registrar atributos de uso mais fieis para notebook/trabalho, lancheira e estojo.
- Foi adicionada cobertura unitária para garantir que `Lancheira Infantil...` continue sendo classificada como `lancheira` mesmo dentro de uma categoria ampla de mochilas/bolsas.

## Conclusao

R4 aprovada para seguir R5.

O filtro separou corretamente concorrentes diretos, parcial juvenil, notebook executiva e produtos complementares como lancheira/estojo, sem IA e com motivos legiveis persistidos em `radar_competitor_matches`.
