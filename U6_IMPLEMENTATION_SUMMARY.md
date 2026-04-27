# U6 — /catalogo vinculado à loja ativa

## ✅ Status: CONCLUÍDO

## 📋 Objetivo
Implementar sistema de catálogo importado vinculado à loja ativa do usuário, permitindo que o bot use produtos do catálogo quando o scraping público falhar.

## 🎯 Funcionalidades Implementadas

### 1. Comandos de Catálogo
- **`/catalogo`** ou **`/catalogo status`**: Mostra status do catálogo da loja ativa
- **`/catalogo importar`**: Inicia fluxo de importação de arquivo
- **`/catalogo remover`**: Remove catálogo com confirmação obrigatória

### 2. Fluxo de Importação
1. Usuário envia `/catalogo importar`
2. Bot entra em estado `awaiting_catalog_file`
3. Usuário envia arquivo XLSX/XLS/CSV
4. Bot valida formato e agenda processamento em background
5. Background task processa arquivo com pandas
6. Bot salva produtos no banco vinculados a `user_id + shop_uid`
7. Bot envia preview dos primeiros 5 produtos

### 3. Integração com /auditar
- Quando scraping público falha, bot busca catálogo da loja ativa
- Mensagens indicam fonte dos produtos:
  - 🌐 scraping público
  - 📦 catálogo importado
- Se não houver catálogo, orienta importação

### 4. Isolamento por Loja
- Cada loja tem seu próprio catálogo
- Trocar loja ativa muda o catálogo exibido
- Catálogo vinculado a `user_id + shop_uid` (não apenas `user_id`)
- Remover loja não afeta catálogos de outras lojas

## 📁 Arquivos Criados/Modificados

### Novos Arquivos
- `shopee_core/catalog_service.py` — Serviço de gerenciamento de catálogos
- `test_catalogo_commands.py` — Suite de testes (9 testes, todos passando)

### Arquivos Modificados
- `shopee_core/whatsapp_service.py`:
  - Adicionado `_handle_catalogo_command()` — Roteador de comandos
  - Adicionado `_handle_catalogo_remove_confirm()` — Confirmação de remoção
  - Adicionado `_handle_catalog_file_upload()` — Validação de arquivo
  - Atualizado `_handle_media_message()` — Handler especial para catálogo
  - Atualizado `_handle_shop_url()` — Passa parâmetros de loja ativa
  - Atualizado menu com comando `/catalogo`

- `api_server.py`:
  - Adicionado `_run_import_catalog_bg()` — Processa arquivo XLSX/XLS/CSV
  - Atualizado `_run_load_shop_bg()` — Usa catálogo como fallback
  - Adicionado dispatch de task `import_catalog` no webhook

## 🗄️ Estrutura do Banco de Dados

### Tabela: `whatsapp_shop_catalogs`
```sql
CREATE TABLE whatsapp_shop_catalogs (
    catalog_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    shop_uid TEXT NOT NULL,
    shop_url TEXT NOT NULL,
    username TEXT NOT NULL,
    products_count INTEGER DEFAULT 0,
    source_type TEXT DEFAULT 'seller_center',
    imported_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, shop_uid)
)
```

### Tabela: `whatsapp_catalog_products`
```sql
CREATE TABLE whatsapp_catalog_products (
    product_id TEXT PRIMARY KEY,
    catalog_id TEXT NOT NULL,
    itemid TEXT,
    shopid TEXT,
    name TEXT NOT NULL,
    price REAL DEFAULT 0,
    stock INTEGER DEFAULT 0,
    category TEXT,
    description TEXT,
    images TEXT,
    product_data TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (catalog_id) REFERENCES whatsapp_shop_catalogs(catalog_id) ON DELETE CASCADE
)
```

## 🔧 Funções Principais

### catalog_service.py
- `save_catalog(user_id, shop_uid, shop_url, username, products)` — Salva catálogo
- `get_catalog(user_id, shop_uid)` — Busca catálogo
- `get_catalog_products(catalog_id)` — Busca produtos
- `has_catalog(user_id, shop_uid)` — Verifica existência
- `delete_catalog(user_id, shop_uid)` — Remove catálogo
- `get_catalog_summary(user_id, shop_uid)` — Resumo do catálogo

### whatsapp_service.py
- `_handle_catalogo_command()` — Roteador de comandos
- `_handle_catalogo_remove_confirm()` — Confirmação de remoção
- `_handle_catalog_file_upload()` — Validação e agendamento

### api_server.py
- `_run_import_catalog_bg()` — Processamento de arquivo com pandas
- `_run_load_shop_bg()` — Carregamento com fallback para catálogo

## 📊 Formatos Suportados

### XLSX/XLS (Excel)
- Leitura com `pandas.read_excel()`
- Suporta múltiplas planilhas (usa primeira)
- Normalização de colunas case-insensitive

### CSV
- Leitura com `pandas.read_csv()`
- Detecta delimitador automaticamente (`,`, `;`, `\t`)
- Suporta UTF-8

### Colunas Reconhecidas
- **Nome**: `nome do produto`, `product name`, `nome`, `name`
- **Preço**: `preço`, `preco`, `price`
- **Estoque**: `estoque`, `stock`, `quantidade`
- **Categoria**: `categoria`, `category`
- **Descrição**: `descrição`, `descricao`, `description`
- **SKU**: `sku`
- **Item ID**: `item id`, `itemid`

## ✅ Testes Implementados

### test_catalogo_commands.py (9 testes)
1. ✅ `/catalogo` sem loja ativa → orienta `/loja adicionar`
2. ✅ `/catalogo status` com loja ativa mas sem catálogo → mostra status vazio
3. ✅ `/catalogo importar` → entra em `awaiting_catalog_file`
4. ✅ `/catalogo status` → mostra produtos importados
5. ✅ Trocar loja ativa → `/catalogo status` não mostra catálogo da loja anterior
6. ✅ `/catalogo remover` → pede confirmação
7. ✅ Confirmação `CONFIRMAR` → remove catálogo
8. ✅ Cancelar remoção mantém catálogo
9. ✅ Catálogo vinculado a `user_id + shop_uid` (não apenas `user_id`)

## 🔒 Validações e Segurança

### Validações de Arquivo
- ✅ Tipo de mídia deve ser `document`
- ✅ Mimetype deve ser XLSX, XLS ou CSV
- ✅ Base64 não pode estar vazio
- ✅ Arquivo deve ter pelo menos 1 produto válido
- ✅ Produto válido = nome preenchido

### Validações de Loja
- ✅ Usuário deve ter loja ativa para importar catálogo
- ✅ Catálogo vinculado a `shop_uid` específico
- ✅ Remover catálogo exige confirmação `CONFIRMAR`
- ✅ Cancelar com `/cancelar` mantém catálogo

### Isolamento
- ✅ Cada loja tem seu próprio catálogo
- ✅ Trocar loja ativa não afeta catálogos de outras lojas
- ✅ Remover loja não remove catálogos de outras lojas

## 📝 Mensagens ao Usuário

### Status Vazio
```
📦 Catálogo da loja testloja

⚠️ Status: nenhum catálogo importado.

Envie /catalogo importar para adicionar um arquivo.
```

### Status com Catálogo
```
📦 Catálogo da loja testloja

✅ Status: catálogo importado
📦 Produtos salvos: 6
📄 Fonte: Seller Center XLSX/CSV
🕐 Última atualização: 27/04/2026 15:40

Comandos:
• /catalogo importar — atualizar catálogo
• /catalogo remover — remover catálogo
```

### Importação Bem-Sucedida
```
✅ Catálogo importado com sucesso!

🏪 Loja: testloja
📦 Produtos salvos: 6

Preview:
1. Mochila Infantil Rosa - R$ 89.90
2. Mochila Escolar Azul - R$ 79.90
3. Mochila de Viagem - R$ 129.90
4. Mochila Executiva - R$ 149.90
5. Mochila Esportiva - R$ 99.90
... e mais 1 produtos

Use /catalogo status para ver detalhes ou /auditar para usar o catálogo.
```

### Auditoria com Catálogo
```
✅ Loja testloja carregada com 6 produto(s).
📄 Fonte: catálogo importado

0 — Mochila Infantil Rosa | R$ 89.90
1 — Mochila Escolar Azul | R$ 79.90
2 — Mochila de Viagem | R$ 129.90
3 — Mochila Executiva | R$ 149.90
4 — Mochila Esportiva | R$ 99.90
5 — Mochila Casual | R$ 69.90

Escolha o número do produto que deseja otimizar. Ex: 0
```

## 🚀 Próximos Passos (U7)

A próxima fase é **U7 — /sentinela com loja ativa + Telegram + lock**, que vai:
- Vincular Sentinela à loja ativa
- Usar catálogo para gerar keywords quando scraping falhar
- Enviar alertas para Telegram do usuário
- Implementar lock distribuído para evitar execuções duplicadas

## 📊 Métricas

- **Arquivos criados**: 2
- **Arquivos modificados**: 2
- **Linhas de código**: ~800
- **Testes**: 9 (100% passando)
- **Cobertura**: Comandos, importação, remoção, isolamento, integração

## 🎉 Conclusão

U6 foi implementado com sucesso! O sistema de catálogo está completamente funcional e integrado com o fluxo de auditoria. Todos os testes passaram e o código está pronto para produção.

**Branch**: `feature/whatsapp-bot-core`  
**Commit**: `8b4b8f6` — feat(U6): Implementar /catalogo vinculado à loja ativa  
**Data**: 27/04/2026
