# Fase R3 - Coleta Profunda de Produto no Mercado Livre

## Objetivo

Consolidar o Mercado Livre como fonte confiavel do Radar Assistido, expandindo a coleta por URL para dados mais ricos e download de imagens.

Esta fase nao implementa descoberta automatica de concorrentes, IA, bypass, OCR, Sentinela, Bot WhatsApp ou integracao com a Auditoria atual.

## O que a R3 coleta

Para paginas do Mercado Livre, o coletor tenta extrair:

- titulo
- preco atual
- preco original
- desconto
- vendedor/loja
- reputacao do vendedor
- nota media
- quantidade de avaliacoes
- quantidade vendida
- descricao
- atributos/ficha tecnica
- breadcrumbs/categoria
- variacoes visiveis
- imagens principais
- imagens da descricao, quando existirem
- videos visiveis, quando existirem

Campos profundos como `rating`, `review_count`, `sold_count`, `description`, `attributes`, `category_path` e `variation_labels` ficam dentro de `raw_json`. A R3 nao migra a tabela `radar_products`, para manter o contrato da R1 estavel enquanto a coleta ainda amadurece.

## Assets

As imagens baixadas ficam em:

```text
data/radar_assets/{product_uid}/images/
```

Videos, se encontrados e baixados, ficam em:

```text
data/radar_assets/{product_uid}/videos/
```

Cada arquivo baixado tambem e registrado em `radar_assets` com `source_url` e `local_path`.

## Como rodar por URL

```bash
python scripts/radar_collect_deep_url.py "https://produto.mercadolivre.com.br/MLB-3452273391-mochila-de-rodinhas-360-e-costas-escolar-notebook-up4you-_JM" --save-assets
```

O script salva o produto no `data/radar.db`, marca o job inicial como `done` e imprime um resumo com titulo, preco, loja, avaliacoes, vendidos, descricao e assets.
Se o perfil persistente tiver sido aberto antes com Chrome ou Edge instalado, use `--browser-channel chrome` ou `--browser-channel msedge`.

## Como rodar a fila pendente

```bash
python scripts/radar_collect_pending.py --limit 5 --deep --save-assets
```

Para Mercado Livre, `--save-assets` baixa imagens e registra `local_path`.
Para Shopee, o comportamento continua limitado ao modo R2: sem bypass de login, captcha ou verificacao.

## Inspecionar produto

```bash
python scripts/radar_inspect_product.py PRODUCT_UID
```

Mostra dados principais, contagem de assets, caminhos locais baixados e tamanho do `raw_json`.

## Limitacoes atuais

- A qualidade da descricao e atributos depende do layout visivel do Mercado Livre.
- A R3 baixa imagens, mas ainda nao faz analise visual nem comparacao por IA.
- Avaliacoes completas ficam para uma fase futura.
- Shopee permanece em modo limitado por bloqueio identificado na R2.2.
- Se o Mercado Livre devolver login, reCAPTCHA ou `negative_traffic`, a coleta nao tenta bypass. O job deve falhar de forma transparente para nova tentativa assistida.

## Smoke real

URL testada:

```text
https://produto.mercadolivre.com.br/MLB-3452273391-mochila-de-rodinhas-360-e-costas-escolar-notebook-up4you-_JM
```

Comando usado:

```bash
python scripts/radar_collect_deep_url.py "https://produto.mercadolivre.com.br/MLB-3452273391-mochila-de-rodinhas-360-e-costas-escolar-notebook-up4you-_JM" --save-assets --browser-channel chrome
```

Resultado aprovado por URL:

- status: `collected`
- titulo: `Mochila Escolar 4 Rodinhas 360 Notebook Up4you + Chaveiro`
- preco: `598.83`
- loja: `Vendido porVantice`
- nota: `5.0`
- avaliacoes: `50`
- vendidos: `50`
- descricao coletada: sim
- imagens principais apos deduplicacao: `14`
- assets baixados: `14`
- erros de asset: `0`

Observacao operacional: o Chromium embutido do Playwright falhou ao abrir o perfil persistente depois que o mesmo perfil foi usado com Chrome/Edge instalado. Para esse caso, `--browser-channel chrome` funcionou.

Ao repetir coletas em sequencia pela fila, o Mercado Livre eventualmente retornou tela de login/`negative_traffic`. A R3 foi ajustada para tratar esse caso como coleta bloqueada/incompleta, sem salvar login como produto coletado e sem qualquer tentativa de bypass.

## Proximos passos

R4 deve filtrar relevancia de concorrentes usando regras e/ou IA sobre a base rica ja coletada: nicho, titulo, atributos, preco, imagens e sinais de mercado.
