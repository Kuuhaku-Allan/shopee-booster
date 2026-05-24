# Fase R7.2E - Assets opcionais e nao bloqueantes

## Objetivo

A coleta principal do Radar nao deve depender de baixar imagens/assets. A prioridade passa a ser salvar os dados principais do concorrente: URL, titulo, preco, descricao, metricas disponiveis e metadados basicos.

## Mudancas aplicadas

- A UI "Coletar URLs Pendentes" agora tem o checkbox "Baixar imagens/assets" desmarcado por padrao.
- Quando `save_assets=False`, o workflow nao chama `_persist_collected_assets()`.
- A coleta com assets desligados pula a etapa lenta de galeria e tenta salvar apenas metadados de imagem baratos, como `og:image` ou JSON-LD quando ja estiver disponivel.
- O produto e salvo no banco antes de qualquer persistencia/download opcional de assets.
- Falhas ou timeouts em assets viram `asset_warnings` e `raw.asset_errors`, sem marcar o produto ou job como failed.
- O limite de assets foi endurecido para 5 imagens por produto, timeout por imagem de 5s e timeout total de assets de 30s.
- O progresso separa as etapas:
  - `SAVING_MAIN_DATA`
  - `EXTRACTING_IMAGE_URLS`
  - `DOWNLOADING_ASSETS`
  - `ASSETS_SKIPPED`
  - `ASSETS_WARNING`
- Jobs `running` antigos preservam o produto como `collected` quando ja existe titulo ou preco salvo.

## Comportamento esperado

Com "Baixar imagens/assets" desmarcado:

- A coleta nao trava em imagens.
- Cada URL salva os dados principais quando titulo ou preco estiverem disponiveis.
- A etapa de assets aparece como pulada no resultado.
- O fluxo segue para a proxima URL.

Com "Baixar imagens/assets" marcado:

- No maximo 5 imagens sao persistidas/baixadas por produto.
- Timeout ou erro de assets nao falha o concorrente.
- Os avisos ficam em `asset_warnings` no resultado e em `raw.asset_errors` no produto.

## Testes adicionados

- `save_assets=False` nao chama persistencia de assets.
- Falha/timeout em assets nao impede salvar produto.
- Timeout em assets nao impede a proxima URL.
- `max_images_per_product` limita downloads.
- Produto com dados principais e asset error continua `collected`.
- Job `running` recuperado com titulo/preco salvo permanece `collected`.
