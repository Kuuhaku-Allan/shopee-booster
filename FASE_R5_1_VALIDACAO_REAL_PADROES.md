# Fase R5.1 - Validacao Real de Padroes com Dataset Maior

## Objetivo

Validar a analise de padroes R5 usando uma base maior de produtos reais do Mercado Livre antes de integrar o Radar com a Auditoria.

Esta fase nao usa IA generativa, nao integra Bot WhatsApp, Auditoria ou Sentinela, nao mexe em Shopee e nao implementa descoberta automatica de URLs.

## Entrada

Arquivo:

```text
data/radar_smoke_urls_mochilas_ml.txt
```

O arquivo contem URLs reais do Mercado Livre misturando:

- mochila infantil feminina
- mochila escolar rosa
- mochila com rodinhas
- mochila juvenil feminina
- mochila notebook/adulta
- lancheira
- estojo
- mala infantil

## Como rodar

Smoke completo:

```bash
python scripts/radar_run_full_market_smoke.py
```

Export Markdown:

```bash
python scripts/radar_export_market_smoke_report.py
```

Saida Markdown:

```text
data/reports/radar_market_smoke_mochilas.md
```

## Fluxo

1. Cria ou reaproveita o produto proprio:

```text
Mochila Infantil Princesa Rosa Escolar Feminina Grande
```

2. Le as URLs reais do arquivo.
3. Adiciona cada URL como `competitor_candidate`.
4. Coleta via R3 com Mercado Livre.
5. Classifica via R4.
6. Gera relatorio R5 em `radar_pattern_reports`.
7. Exporta um Markdown de leitura humana.

## Resultados

### Antes do Chrome real via CDP

Tentativa com o navegador persistente Playwright:

- URLs recebidas: 18
- Coletadas com sucesso: 1
- Falhas: 17
- Concorrentes diretos: 1
- Relatorio salvo: `75b05db5-dc27-4bba-b2db-0b9f71ac3e2e`

Resultado observado: o Mercado Livre exibiu login/verificacao em grande parte das URLs. Isso invalida a conclusao estatistica da R5.1, porque a base coletada ficou pequena demais.

### Antes do Data Quality Gate

Tentativa com Chrome real dedicado via CDP:

- URLs recebidas: 18
- Coletadas com sucesso: 18
- Falhas: 0

O CDP resolveu o bloqueio operacional, mas o resultado ainda nao foi aprovado para R6 por problemas de qualidade:

- Alguns produtos vieram com titulo generico `Mochilas`.
- Alguns produtos tiveram assets demais, como `assets=171`.
- O relatorio gerou preco minimo `R$ 3.00`, provavelmente parcela/frete/numero lateral.
- A feature `notebook` apareceu forte demais para um recorte infantil/feminino.

## Ajustes feitos

- A R5.1 nao foi considerada aprovada.
- Foi criada a fase intermediaria R5.1A para usar um Chrome real dedicado via CDP.
- Foi criada a R5.1B para adicionar Data Quality Gate antes de R6.

### Correcoes R5.1B

- `validate_product_extraction()` valida titulo, URL de produto, preco plausivel, excesso de imagens e bloqueio/login.
- `filter_product_image_urls()` remove imagens de layout, deduplica e limita imagens principais a 20.
- Precos de mochila abaixo de `R$ 20` ou acima de `R$ 1500` sao considerados suspeitos.
- R4 rejeita candidatos com baixa qualidade em vez de classificar como `competitor_direct`.
- R5 ignora concorrentes diretos antigos que tenham baixa qualidade.
- `scripts/radar_quality_report.py` lista titulos genericos, precos suspeitos, assets demais e principais problemas.
- O smoke R5.1 agora imprime qualidade OK, warnings, ignorados por baixa qualidade, media de assets, titulos genericos e precos suspeitos.

## Como repetir depois do Data Quality Gate

Com o Chrome do Radar aberto e logado:

```bash
python scripts/radar_run_full_market_smoke.py --browser-mode cdp --manual-login-check
```

Relatorio de qualidade:

```bash
python scripts/radar_quality_report.py
```

Resultado local apos implementar a R5.1B, antes de repetir o smoke completo:

- O relatorio de qualidade passou a identificar produtos antigos com `Mochilas`, preco `R$ 3.00` e assets excessivos.
- O relatorio R5 passou a avisar quando concorrentes diretos antigos sao ignorados por baixa qualidade.
- A aprovacao da R5.1 ainda depende de uma nova rodada completa com `--browser-mode cdp`.

Export Markdown:

```bash
python scripts/radar_export_market_smoke_report.py
```

## Conclusao

R5.1 segue pendente ate uma nova rodada com o Data Quality Gate.

Criterios para aprovar R5.1 rumo a R6:

- Pelo menos 12 produtos com `quality.ok = true`.
- Nenhum produto com titulo `Mochilas` usado como concorrente direto.
- Nenhum preco abaixo de `R$ 20` usado na analise de preco.
- Nenhum produto com mais de 30 imagens principais.
- Produtos executivos/notebook devem ser rejeitados ou ficar parciais baixos quando nao competirem com mochila infantil/feminina.
