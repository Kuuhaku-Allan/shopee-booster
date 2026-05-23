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

Primeira tentativa com o navegador persistente Playwright:

- URLs recebidas: 18
- Coletadas com sucesso: 1
- Falhas: 17
- Concorrentes diretos: 1
- Relatorio salvo: `75b05db5-dc27-4bba-b2db-0b9f71ac3e2e`

Resultado observado: o Mercado Livre exibiu login/verificacao em grande parte das URLs. Isso invalida a conclusao estatistica da R5.1, porque a base coletada ficou pequena demais.

## Ajustes feitos

- A R5.1 nao foi considerada aprovada.
- Foi criada a fase intermediaria R5.1A para usar um Chrome real dedicado via CDP.
- O smoke deve ser repetido com:

```bash
python scripts/radar_run_full_market_smoke.py --browser-mode cdp --manual-login-check
```

## Conclusao

R5.1 segue pendente. A validacao real deve ser repetida depois que o usuario fizer login manual no Chrome dedicado do Radar.
