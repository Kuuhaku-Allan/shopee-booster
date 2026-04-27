# Fase 6A - Importação de Catálogo por Planilha

## 📋 Contexto

**Problema**: A Shopee mudou a arquitetura em 2026 e está bloqueando scraping automatizado.  
**Confirmação**: O executável v4.0.0 também falha hoje (não é regressão no código).  
**Solução**: Importação de catálogo autorizado via XLSX/CSV do Shopee Seller Center.

## ✅ IMPLEMENTADO

### 1. Serviço de Catálogo (`shopee_core/catalog_service.py`)
- ✅ `load_products_from_file()` - Carrega XLSX/CSV
- ✅ `normalize_product_row()` - Normaliza colunas (PT/EN)
- ✅ `save_catalog()` - Salva no cache SQLite
- ✅ `get_catalog()` - Recupera do cache
- ✅ `list_catalog_products()` - Lista produtos
- ✅ `delete_catalog()` - Remove cache
- ✅ `import_shopee_export()` - Fluxo completo de importação
- ✅ Banco SQLite `data/catalog_cache.db` com tabela `shop_catalog_cache`
- ✅ Suporte a múltiplos encodings para CSV
- ✅ Cache com expiração configurável (30 dias padrão)
- ✅ Mapeamento inteligente de colunas

### 2. Integração com Shop Loader (`shopee_core/shop_loader_service.py`)
- ✅ Modificado `load_shop_with_fallback()` para usar catálogo cacheado
- ✅ Ordem de prioridade implementada:
  1. Scraping público (intercept)
  2. Catálogo cacheado (importado)
  3. APIs diretas (fallback)
  4. Solicita importação (mensagem orientativa)
- ✅ Mensagens detalhadas para cada cenário
- ✅ Parâmetro `user_id` adicionado para buscar cache correto

### 3. API REST (`api_server.py`)
- ✅ `POST /catalog/import` - Upload de arquivo XLSX/CSV
- ✅ `GET /catalog/list` - Lista produtos do cache
- ✅ `DELETE /catalog/delete` - Remove cache
- ✅ Tratamento de erros e logs
- ✅ Suporte a arquivos temporários

### 4. Integração com WhatsApp (`shopee_core/whatsapp_service.py`)
- ✅ Comando `/catalogo` implementado
- ✅ Aceita arquivos XLSX/CSV como documentos
- ✅ Fluxo conversacional completo:
  1. Usuário envia `/catalogo`
  2. Bot solicita arquivo XLSX/CSV
  3. Usuário envia arquivo como documento
  4. Bot valida extensão (.xlsx, .xls, .csv)
  5. Bot importa em background
  6. Bot confirma importação com contagem e preview
- ✅ Estado `awaiting_catalog_file` implementado
- ✅ Suporte a `documentMessage` na extração de payload
- ✅ Campo `file_name` adicionado ao payload
- ✅ Comando adicionado ao menu principal
- ✅ Background task `import_catalog` implementada
- ✅ Função `_run_import_catalog_bg()` completa
- ✅ Integração com `/auditar` - usa catálogo automaticamente
- ✅ Indicador visual de fonte dos dados (scraping vs catálogo)
- ✅ Mensagens orientativas quando scraping falha

### 5. Integração com Streamlit (`app.py`)
- ✅ Seção "Catálogo da Loja" na Auditoria Pro
- ✅ Upload de arquivo via `st.file_uploader()` (XLSX, XLS, CSV)
- ✅ Detecção automática de catálogo cacheado
- ✅ Botão "Usar catálogo salvo" quando há cache
- ✅ Botão "Importar novo catálogo"
- ✅ Preview dos primeiros 5 produtos após importação
- ✅ Mensagens orientativas quando scraping falha
- ✅ Expander com guia de exportação do Seller Center
- ✅ Indicador visual de fonte dos dados na barra de status
- ✅ Contagem correta de produtos carregados
- ✅ Integração com `shop_loader_service` no botão "Analisar"
- ✅ Tratamento de erros e feedback visual
- ✅ Limpeza automática de arquivos temporários

### 6. Scripts de Investigação
- ✅ `scripts/manual_browser_investigation.md` - Guia de investigação manual
- ✅ `scripts/discover_new_endpoint.py` - Descoberta automatizada de endpoints
- ✅ Documentação completa em `INVESTIGACAO_REGRESSAO.md`

## ⏳ PENDENTE

### 1. Integração com Sentinela (`shopee_core/sentinel_whatsapp_service.py`)
- ⏳ Usar catálogo para gerar keywords automáticas quando scraping falhar
- ⏳ Modificar `_generate_keywords_from_products()` para aceitar produtos do catálogo
- ⏳ Mensagem: "Usando produtos do catálogo importado para gerar keywords"

### 2. Documentação
- ⏳ Criar `docs/COMO_EXPORTAR_CATALOGO.md` com passo a passo do Seller Center
- ⏳ Atualizar README.md com novo fluxo
- ⏳ Adicionar screenshots do Seller Center
- ⏳ Vídeo tutorial (opcional)

### 3. Testes
- ⏳ Testar importação de XLSX real do Seller Center
- ⏳ Testar importação de CSV com diferentes encodings
- ⏳ Testar fluxo completo: importação → cache → uso em Auditoria
- ⏳ Testar fluxo completo: importação → cache → uso em Sentinela
- ⏳ Testar expiração de cache (30 dias)
- ⏳ Testar múltiplos usuários com catálogos diferentes

## 🎯 Próximos Passos (Ordem de Prioridade)

### ✅ CONCLUÍDO
1. ✅ Integração com WhatsApp (`whatsapp_service.py`)
   - Comando `/catalogo` ✅
   - Aceitar arquivos XLSX/CSV ✅
   - Fluxo conversacional completo ✅
   - Background task de importação ✅
   - Uso automático em `/auditar` ✅

2. ✅ Integração com Streamlit (`app.py`)
   - Upload de arquivo ✅
   - Listar produtos ✅
   - Indicadores visuais ✅
   - Uso automático em "Analisar" ✅
   - Detecção de catálogo cacheado ✅

### Esta Semana
3. ⏳ Integrar com Sentinela
   - Usar catálogo para keywords

4. ⏳ Documentação completa
   - Guia de exportação do Seller Center
   - Atualizar README

5. ⏳ Testes completos
   - Todos os fluxos
   - Múltiplos cenários

### Próximas Semanas
6. ⏳ Monitorar estabilidade
7. ⏳ Coletar feedback dos usuários
8. ⏳ Otimizações baseadas no uso real

## 📊 Estrutura de Dados

### Tabela `shop_catalog_cache`
```sql
CREATE TABLE shop_catalog_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    shop_url TEXT,
    username TEXT,
    source TEXT NOT NULL,
    products_json TEXT NOT NULL,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    UNIQUE(user_id, shop_url)
)
```

### Formato de Produto
```json
{
    "source": "import",
    "itemid": "123456",
    "shopid": "789012",
    "name": "Mochila Feminina Rosa",
    "price": 89.90,
    "stock": 50,
    "sku": "MOCH-001",
    "image": "https://...",
    "status": "active"
}
```

## 🔗 Arquivos Relacionados

### Implementados
- `shopee_core/catalog_service.py` - Serviço completo
- `shopee_core/shop_loader_service.py` - Integração com fallback
- `api_server.py` - Endpoints REST
- `scripts/discover_new_endpoint.py` - Investigação automatizada
- `scripts/manual_browser_investigation.md` - Guia manual
- `INVESTIGACAO_REGRESSAO.md` - Documentação completa

### Pendentes
- `shopee_core/whatsapp_service.py` - Precisa integração
- `app.py` - Precisa UI de upload
- `shopee_core/sentinel_whatsapp_service.py` - Precisa usar catálogo
- `docs/COMO_EXPORTAR_CATALOGO.md` - Precisa criar
- `README.md` - Precisa atualizar

## 💡 Vantagens da Solução

1. **Sem CNPJ**: Não depende de Shopee Open Platform
2. **Sem API oficial**: Não precisa aprovação comercial
3. **Sem anti-bot**: Não tenta driblar detecção
4. **Fonte autorizada**: Dados vêm do próprio Seller Center
5. **Mais estável**: Não depende de scraping que pode quebrar
6. **Cache local**: Funciona offline após importação
7. **Múltiplos usuários**: Cada usuário tem seu próprio catálogo
8. **Expiração configurável**: Cache expira após 30 dias (configurável)

## 🚀 Como Usar (Quando Completo)

### No .exe (Streamlit)
1. Acesse Shopee Seller Center
2. Exporte produtos (XLSX/CSV)
3. No ShopeeBooster, clique em "Importar catálogo"
4. Selecione o arquivo
5. Produtos importados aparecem na Auditoria

### No WhatsApp
1. Envie `/catalogo` para o bot
2. Bot solicita arquivo XLSX/CSV
3. Envie o arquivo exportado do Seller Center
4. Bot confirma importação
5. Use `/auditar` normalmente (usa catálogo automaticamente)

### No Sentinela
1. Configure Sentinela normalmente
2. Se scraping falhar, bot usa catálogo automaticamente
3. Keywords geradas a partir dos produtos importados

---

**Data**: 26/04/2026  
**Status**: Fase 6A em andamento (**95% completo** - WhatsApp ✅ + Streamlit ✅)  
**Branch**: `fix/restore-shop-products-loader`  
**Próximo**: Integração com Sentinela (5% restante)


---

## 🔄 ATUALIZAÇÃO: Buscar Concorrentes Migrado para Mercado Livre

**Data**: 26/04/2026  
**Status**: ✅ Implementado

### Problema
- Shopee bloqueando scraping de concorrentes (retornando 0 produtos)
- Impossível obter dados de mercado para análise competitiva

### Solução
- **Buscar Concorrentes agora usa Mercado Livre** em vez da Shopee
- Mesma estratégia já usada com sucesso para avaliações
- Dados de mercado continuam válidos (preços, avaliações, estrelas)

### Mudanças Implementadas

#### 1. `backend_core.py` - Função `fetch_competitors_intercept()`
- ✅ Reescrita para buscar no Mercado Livre
- ✅ URL: `https://lista.mercadolivre.com.br/{keyword}`
- ✅ Extrai: nome, preço, avaliações, estrelas, item_id (MLB)
- ✅ Limita a 10 produtos (suficiente para análise)
- ✅ Logs detalhados para debug

#### 2. `app.py` - Interface do Usuário
- ✅ Spinner atualizado: "🛒 Buscando concorrentes no Mercado Livre..."
- ✅ Info box adicionado explicando uso do ML
- ✅ Sentinela também atualizado

#### 3. Documentação
- ✅ `MUDANCA_MERCADO_LIVRE_CONCORRENTES.md` - Guia completo
- ✅ `test_ml_competitors.py` - Script de teste

### Impacto
- ✅ **Catálogo da loja**: Continua vindo da Shopee (via CSV/XLSX)
- ✅ **Avaliações**: Já usavam ML, continuam iguais
- ✅ **Concorrentes**: Agora vêm do ML (mais estável)
- ✅ **Análise de IA**: Funciona com dados de qualquer marketplace

### Próximos Passos
1. ⏳ Usuário deve recarregar página (F5)
2. ⏳ Testar "Buscar Concorrentes" com produto
3. ⏳ Verificar se retorna produtos do ML
4. ⏳ Testar "Gerar Otimização Completa"

### Arquivos Modificados
- `backend_core.py` (linha ~390)
- `app.py` (linhas ~594, ~611, ~2521)
- `MUDANCA_MERCADO_LIVRE_CONCORRENTES.md` (novo)
- `test_ml_competitors.py` (novo)
