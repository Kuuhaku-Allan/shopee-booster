# Fase R1 - Radar Assistido de Concorrentes

## Objetivo

A fase R1 cria a fundacao persistente do Radar Assistido de Concorrentes do ShopeeBooster.
Ela entrega banco SQLite, contratos de dados, fila de URLs, funcoes CRUD e testes para que as
proximas fases possam coletar, revisar, reprocessar e classificar produtos sem improviso.

Esta fase nao implementa navegador, mouse, Playwright, OCR, extensao, scraping real, Bot WhatsApp,
Sentinela ou integracao com a auditoria atual.

## Banco

O banco e criado automaticamente em:

```text
data/radar.db
```

## Tabelas Criadas

### radar_products

Guarda o cadastro central de produtos proprios, candidatos de concorrencia, concorrentes diretos,
concorrentes parciais e descartes.

Campos principais:

- `product_uid`
- `owner_user_id`
- `source_type`
- `marketplace`
- `url`
- `canonical_url`
- `title`
- `price`
- `shop_name`
- `niche`
- `status`
- `relevance_score`
- `rejection_reason`
- `raw_json`
- `created_at`
- `updated_at`
- `collected_at`

Indices:

- `UNIQUE(canonical_url)`
- `source_type`
- `marketplace`
- `status`
- `owner_user_id`

### radar_assets

Guarda referencias futuras para imagens, videos, imagens de descricao e thumbnails ligados a um produto.

Campos:

- `asset_uid`
- `product_uid`
- `asset_type`
- `source_url`
- `local_path`
- `created_at`

### radar_reviews

Guarda avaliacoes coletadas futuramente para cada produto.

Campos:

- `review_uid`
- `product_uid`
- `rating`
- `text`
- `author`
- `created_at`
- `raw_json`

### radar_collection_jobs

Guarda a fila de coleta por URL.

Campos:

- `job_uid`
- `product_uid`
- `url`
- `job_type`
- `status`
- `attempts`
- `last_error`
- `created_at`
- `updated_at`
- `finished_at`

## Funcoes

As funcoes publicas ficam em `shopee_core/radar_service.py`:

- `normalize_product_url`
- `detect_marketplace`
- `add_product_url`
- `add_product_urls_bulk`
- `list_products`
- `get_product`
- `mark_product_collected`
- `mark_product_failed`
- `classify_product`
- `get_pending_jobs`
- `mark_job_running`
- `mark_job_done`
- `mark_job_failed`

## Fluxo Futuro

```text
URL -> fila -> coleta -> classificacao -> analise de padroes -> auditoria/sentinela
```

R1 termina no cadastro persistente e na fila. R2 podera consumir `radar_collection_jobs`,
abrir a URL em navegador real e preencher `radar_products`, `radar_assets` e `radar_reviews`.
Depois, R4 e R5 poderao classificar concorrentes e extrair padroes de sucesso para alimentar a
auditoria e a sentinela sem competir com elas.
