# Fase R2 - Coletor Assistido de Pagina de Produto por URL

## Objetivo

A fase R2 implementa o primeiro coletor real do Radar Assistido. Ele consome URLs ja
cadastradas na R1, abre a pagina em um navegador Chromium visivel, coleta dados basicos
do produto e salva o resultado no `data/radar.db`.

Esta fase ainda nao faz descoberta automatica de concorrentes, busca por keyword, filtro
por IA, analise de nicho, OCR, automacao de mouse, bypass de bloqueios, integracao com
Auditoria, Sentinela ou WhatsApp.

## Perfil Persistente

O navegador usa um perfil local persistente em:

```text
data/browser_profile/
```

Se Shopee ou Mercado Livre pedir login, captcha ou verificacao, o usuario resolve
manualmente no navegador visivel. A sessao fica salva nesse perfil para proximas coletas.

O tempo de espera manual padrao antes da extracao e de 8 segundos. Para aumentar:

```powershell
$env:RADAR_MANUAL_WAIT_SECONDS = "45"
```

Se a pagina parecer login, captcha ou verificacao, o coletor espera mais 60 segundos
por padrao antes de extrair. Para ajustar:

```powershell
$env:RADAR_MANUAL_INTERVENTION_SECONDS = "120"
```

## Dependencia

O projeto ja possui `playwright` nos requirements. Se o Chromium ainda nao estiver instalado
no ambiente local, rode:

```powershell
python -m playwright install chromium
```

## Coletar Uma URL

Para apenas abrir e imprimir os dados coletados:

```powershell
python scripts/radar_collect_url.py "https://shopee.com.br/produto..."
```

Para coletar e salvar no `radar.db`:

```powershell
python scripts/radar_collect_url.py "https://produto.mercadolivre.com.br/..." --save
```

O `--save` cria ou reaproveita o produto pelo `canonical_url`, marca como `collected` e
salva URLs de imagens/videos em `radar_assets`. Nesta fase os arquivos de midia nao sao
baixados para disco.

## Coletar Fila Pendente

Para processar jobs pendentes criados pela R1:

```powershell
python scripts/radar_collect_pending.py --limit 5
```

Fluxo:

```text
pending job -> running -> navegador visivel -> coleta -> radar_products collected -> radar_assets -> done
```

Se houver erro, o produto fica como `failed` e o job como `failed`, com `last_error`.

## Dados Coletados

O coletor retorna um dict normalizado:

```text
url
canonical_url
marketplace
title
price
shop_name
rating
review_count
sold_count
description
image_urls
video_urls
raw
```

## Limitacoes Atuais

- A coleta depende do HTML visivel e os seletores podem variar por marketplace.
- Login, captcha ou verificacao sao sempre resolvidos manualmente pelo usuario.
- A R2 salva URLs de imagens/videos, mas nao baixa os arquivos.
- Avaliacoes profundas e midias completas ficam para a R3.
- Marketplaces fora de Shopee e Mercado Livre retornam erro amigavel.

## Proximo Passo

R3 deve baixar imagens/videos, guardar `local_path` em `radar_assets` e coletar avaliacoes
e descricao com mais profundidade.
