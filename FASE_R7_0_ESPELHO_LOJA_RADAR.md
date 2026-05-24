# Fase R7.0 - Espelho da Loja no Radar Assistido

Data: 2026-05-24

## Objetivo

Criar uma memoria local confiavel dos produtos proprios da loja dentro do `radar.db`, para que a Auditoria consiga reaproveitar o ultimo catalogo salvo quando a Shopee falhar ou devolver a lista vazia.

## Por que o espelho local e necessario

A Auditoria depende de carregamento ao vivo da Shopee para montar o catalogo da loja. Esse carregamento pode falhar por bloqueio, instabilidade, Cloudflare, mudanca de endpoint ou resposta incompleta. O espelho local evita que uma loja ja conhecida pareca vazia quando a Shopee nao responde bem naquele momento.

Nesta fase o espelho nao tenta completar a loja sozinho. Se a Auditoria encontrou 6 produtos, o Radar salva 6 produtos. A memoria e fiel ao que foi visto, nao uma simulacao de catalogo completo.

## Banco de dados

Foram adicionadas duas tabelas em `shopee_core/radar_db.py`.

### radar_stores

Guarda a loja espelhada:

- `store_uid`
- `shop_uid`
- `shop_slug`
- `shop_name`
- `marketplace`
- `source_url`
- `last_snapshot_at`
- `last_successful_load_at`
- `product_count`
- `raw_json`
- `created_at`
- `updated_at`

### radar_store_products

Guarda os produtos do espelho:

- `store_product_uid`
- `store_uid`
- `radar_product_uid`
- `marketplace_product_id`
- `canonical_url`
- `title`
- `price`
- `image_url`
- `status`
- `first_seen_at`
- `last_seen_at`
- `last_changed_at`
- `raw_json`
- `created_at`
- `updated_at`

Status usados nesta fase:

- `active`: produto presente no snapshot atual.
- `changed`: produto presente, mas com preco, titulo, imagem ou URL alterados.
- `missing`: produto existia antes, mas nao apareceu no snapshot atual.
- `removed`: reservado para uma fase futura com confirmacao mais forte.
- `unknown`: reservado para dados incompletos.

A regra escolhida para ausencias foi `missing`, nao `removed`, porque snapshots vindos da Auditoria podem ser parciais.

## Como produtos da Auditoria viram own_product

O servico novo `shopee_core/radar_store_service.py` normaliza cada produto da loja e grava:

1. Um registro em `radar_store_products`.
2. Um registro correspondente em `radar_products` com `source_type='own_product'`.
3. O vinculo `radar_store_products.radar_product_uid -> radar_products.product_uid`.

O produto do Radar usa `status='collected'`, titulo, preco, URL canonica, marketplace e `raw_json` do produto original. Snapshots repetidos usam chaves estaveis e nao duplicam produtos.

## Fallback da Auditoria

A integracao minima foi feita em dois pontos:

- `shopee_core/audit_service.py`
- `app.py`, no fluxo principal da `Auditoria Pro`

Comportamento:

1. Se a Auditoria carrega produtos da Shopee com sucesso, chama `save_store_snapshot()`.
2. Se a Shopee falha ao carregar dados da loja, tenta `get_cached_store_products()` pelo slug da loja.
3. Se a Shopee encontra a loja, mas devolve catalogo vazio, tenta `get_cached_store_products()` por `shopid` e slug.
4. Se houver cache, usa a fonte `radar_store_mirror`.
5. Se nao houver cache, mantem o comportamento atual de erro/lista vazia.

Log esperado quando salva:

```text
[R7.0] Espelho da loja atualizado: X produtos
```

## Scripts

Salvar um snapshot a partir de JSON:

```powershell
python scripts/radar_store_snapshot.py --shop-uid totalmenteseu --input data/store_products_sample.json
```

Inspecionar o espelho:

```powershell
python scripts/radar_inspect_store.py --shop-uid totalmenteseu
```

O script de inspecao mostra:

- loja
- status agregado
- total de produtos
- contagem por status
- ultimos produtos
- `radar_product_uid` vinculado
- ultima atualizacao

## Limitacoes

- Nao coleta concorrentes.
- Nao chama Gemini.
- Nao altera Bot WhatsApp nem Sentinela.
- Nao tenta resolver Cloudflare.
- Nao declara produto como removido definitivamente nesta fase.
- O fallback depende de a loja ja ter sido carregada pelo menos uma vez com sucesso.

## Validacoes

Comandos alvo da fase:

```powershell
python test_radar_store_service.py
python test_radar_service.py
python test_radar_ui_service.py
python test_audit_radar_integration.py
python -m compileall shopee_core scripts
```

O teste novo cobre:

- `upsert_store` cria loja.
- `save_store_snapshot` salva produtos.
- Produtos viram `own_product` em `radar_products`.
- Snapshot repetido nao duplica.
- Alteracao de preco marca `changed`/updated.
- Produto ausente vira `missing`.
- Cache retorna produtos ativos.
- Diff detecta produto novo.
- Diff detecta alteracao de preco.
- Cache vazio nao quebra.
- Vinculo store product -> radar product funciona.

Resultado executado nesta fase:

- `test_radar_store_service.py`: 11/11 testes OK.
- `test_radar_service.py`: 11/11 testes OK.
- `test_radar_ui_service.py`: 6/6 testes OK.
- `test_audit_radar_integration.py`: 8/8 testes OK.
- `python -m compileall shopee_core scripts`: OK.
- `scripts/radar_inspect_store.py --shop-uid loja-inexistente-r7-test`: retorna JSON controlado de loja nao encontrada, sem traceback.

## Proximos passos

- R7.1 - Tela de Espelho da Loja no `.exe`: produtos salvos, ultima atualizacao, fonte, alteracoes detectadas, botao "usar cache" e botao "atualizar loja".
- R7.2 - Tela completa do Radar Assistido para cadastrar URLs de concorrentes, coletar, classificar e gerar relatorio.
- R8 - Bot/Sentinela usando Radar como fallback quando scraping falhar.
