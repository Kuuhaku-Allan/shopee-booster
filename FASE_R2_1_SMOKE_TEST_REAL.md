# Fase R2.1 - Smoke Test Real do Coletor Assistido

Data do teste: 2026-05-23

## Objetivo

Validar a R2 com URLs reais antes de avancar para R3. Esta fase nao implementou
descoberta automatica, download de midias, filtro por IA, OCR, bypass, Bot WhatsApp,
Auditoria ou Sentinela.

## Commits Confirmados

- R1: `72fa541 Add assisted radar R1 foundation`
- R2: `2ca6a80 Add assisted radar R2 URL collector`

Durante o smoke foram feitos ajustes pequenos encontrados no teste real:

- `scripts/radar_collect_url.py --save` agora marca o job associado como `done`.
- `test_radar_service.py` e `test_radar_collector.py` usam bancos isolados para nao
  criar jobs artificiais em `data/radar.db`.
- O coletor reconhece textos de intervencao manual como "Por seguranca" e evita usar
  esse texto como titulo quando o `page_title` contem o produto.
- Foi criado `scripts/radar_inspect_db.py` para inspecionar produtos, status, marketplaces,
  jobs e assets.

## URLs Testadas

### Shopee - URL direta

URL:

```text
https://shopee.com.br/Mochila-Notebook-Grande-15-6-I-Connect-Sestini--i.833275000.58209898331
```

Comandos:

```powershell
python scripts/radar_collect_url.py "https://shopee.com.br/Mochila-Notebook-Grande-15-6-I-Connect-Sestini--i.833275000.58209898331"
python scripts/radar_collect_url.py "https://shopee.com.br/Mochila-Notebook-Grande-15-6-I-Connect-Sestini--i.833275000.58209898331" --save
```

Resultado:

- `marketplace`: `shopee`
- `status`: `collected`
- `raw_json`: preenchido com a tentativa real
- `assets`: 6 registros no produto salvo
- `title`: veio como pagina generica da Shopee
- `price`: vazio
- `shop_name`: vazio
- `description`: vazio

Problema encontrado:

A Shopee exibiu pagina de login/verificacao:

```text
Pagina indisponivel. Parece que voce ainda nao esta logado. Faca login para continuar.
```

O coletor nao tentou bypass. O comportamento ficou correto para R2: navegador visivel,
tentativa registrada e persistencia funcionando. Para extrair produto real da Shopee, o
usuario precisa fazer login manual no perfil persistente `data/browser_profile/` e repetir
o teste.

### Mercado Livre - URL direta

URL:

```text
https://produto.mercadolivre.com.br/MLB-3452273391-mochila-de-rodinhas-360-e-costas-escolar-notebook-up4you-_JM
```

Comandos:

```powershell
python scripts/radar_collect_url.py "https://produto.mercadolivre.com.br/MLB-3452273391-mochila-de-rodinhas-360-e-costas-escolar-notebook-up4you-_JM"
python scripts/radar_collect_url.py "https://produto.mercadolivre.com.br/MLB-3452273391-mochila-de-rodinhas-360-e-costas-escolar-notebook-up4you-_JM" --save
```

Resultado salvo:

- `marketplace`: `mercadolivre`
- `status`: `collected`
- `title`: `Mochila Escolar 4 Rodinhas 360 Notebook Up4you + Chaveiro`
- `price`: `598.83`
- `shop_name`: `Vendido porVantice`
- `rating`: `5.0`
- `review_count`: `50`
- `sold_count`: `50`
- `description`: preenchida
- `assets`: 365 registros
- `raw_json`: preenchido

Observacao:

Em uma execucao intermediaria o Mercado Livre exibiu "Por seguranca, complete esta etapa".
Ao repetir, o fluxo voltou a carregar a pagina de produto e salvou corretamente.

## Teste da Fila Pendente

URLs cadastradas em lote:

```text
https://shopee.com.br/Mochila-Olympikus-Essential-I-Preta-i.1337527569.23798378644
https://produto.mercadolivre.com.br/MLB-2699927551-mochila-masculina-infantil-pequena-com-2-rodinhas-_JM
```

Comando:

```powershell
python scripts/radar_collect_pending.py --limit 2
```

Resultado:

- `total`: 2
- `done`: 2
- `failed`: 0

Produto Shopee da fila:

- `status`: `collected`
- `title`: pagina generica da Shopee
- `price`: vazio
- `assets`: 4
- Motivo: login/verificacao da Shopee.

Produto Mercado Livre da fila:

- `status`: `collected`
- `title`: `Mochila Masculina Infantil Pequena Com 2 Rodinhas`
- `price`: `164.2`
- `shop_name`: `Vendido porPLUSSERVIOSEASESORIAADMIN`
- `assets`: 315
- `job`: `done`, `attempts=1`, `last_error=null`

## Inspecao Direta do Banco

Produtos reais consultados:

```text
Shopee direto:      9c7304f2-f9ca-4a92-a8d5-bed82809e2ab
Mercado Livre direto: 911aa81e-ff43-4234-845c-d3966c0ea91f
Shopee fila:        e10d31c6-d5a8-49b9-90a7-c7f1c7f5dbe0
Mercado Livre fila: 0eccec7b-6148-4a41-a3e5-b3b4fb57ce97
```

Status confirmado:

- Todos os 4 produtos ficaram com `status=collected`.
- Todos os jobs desses produtos ficaram com `status=done`.
- Os dois produtos Mercado Livre tiveram titulo e preco preenchidos.
- Os dois produtos Shopee salvaram tentativa e assets da pagina de verificacao, mas nao
  dados completos do produto.

## Comandos de Verificacao

```powershell
python test_radar_service.py
python test_radar_collector.py
python scripts/radar_inspect_db.py
```

Resultados:

- `test_radar_service.py`: 11/11 passou
- `test_radar_collector.py`: 9/9 passou
- `radar_inspect_db.py`: funcional

Nota:

Antes do isolamento dos testes, algumas linhas sinteticas foram criadas em `data/radar.db`.
Os testes agora usam bancos `data/radar_service_test_*.db` e
`data/radar_collector_test_*.db`, ignorados pelo Git, para evitar poluir o banco real.

## Decisao

R2.1 aprovada para:

- coletar URLs reais do Mercado Livre;
- salvar produto como `collected`;
- preencher `title`, `price`, `shop_name`, `description`, `raw_json`;
- registrar imagens em `radar_assets`;
- processar fila `pending -> running -> done`;
- manter o navegador visivel e sem bypass.

R2.1 ainda tem ressalva para Shopee:

- o pipeline salva a tentativa e conclui o job;
- a extracao completa da Shopee depende de login/verificacao manual no navegador persistente;
- antes de considerar a Shopee pronta para R3, repetir o smoke com o usuario logado no perfil
  `data/browser_profile/`.

Proxima acao recomendada:

Fazer login manual na Shopee usando o navegador persistente da R2 e repetir somente o smoke
Shopee. Se passar, avancar para R3.
