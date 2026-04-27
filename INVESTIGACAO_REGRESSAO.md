# Investigação: Regressão de Carregamento de Produtos

## 📋 Resumo Executivo

**Status**: ✅ Investigação Completa  
**Conclusão**: Shopee mudou completamente a arquitetura. Não é regressão no código.  
**Impacto**: Auditoria, Sentinela e Otimização Completa afetados.

---

## 🔍 Descobertas Críticas

### 1. Confirmação da Mudança na Shopee
- ✅ **v4.0.0 também falha hoje** (testado com executável)
- ✅ **Não é regressão no código** - é mudança na Shopee
- ✅ **Mudança ocorreu entre a release v4.0.0 e hoje**

### 2. Endpoints Antigos Não Existem Mais
```
❌ /api/v4/shop/rcmd_items - NÃO EXISTE
❌ /api/v4/shop/shop_page - NÃO EXISTE
```

**Endpoints Disponíveis Hoje**:
```
✅ /api/v4/shop/get_shop_base_v2 - informações da loja
✅ /api/v4/shop/get_categories - categorias (sem produtos)
✅ /api/v4/shop/get_shop_seo - SEO (sem produtos)
✅ /api/v4/shop/get_shop_tab - tabs (sem produtos)
✅ /api/v4/shop/is_show - status (sem produtos)
```

**Nenhum endpoint retorna produtos!**

### 3. Produtos NÃO Estão no HTML
```
❌ Palavras-chave dos produtos: 0 ocorrências
❌ JSON embutido com produtos: não encontrado
❌ itemids no HTML: não encontrado
❌ Server-Side Rendering: não usado
```

### 4. Nova Arquitetura da Shopee
```
✅ Module Federation (Webpack 5)
✅ React 18.3.1
✅ Carregamento dinâmico via JavaScript modules
✅ Produtos carregados após renderização inicial
```

### 5. Fallback via API Direta Bloqueado
```
❌ /api/v4/search/search_items - HTTP 403 (Forbidden)
❌ /api/v4/shop/get_shop_items - HTTP 404 (Not Found)
```

---

## 📊 Evidências

### Teste 1: Executável v4.0.0
**Resultado**: "Galeria não carregou. Verifique os logs de debug acima."  
**Conclusão**: Mesmo código que funcionava antes não funciona mais.

### Teste 2: Intercept de Endpoints
**Capturados**: 17 endpoints de API  
**Com produtos**: 0  
**Arquivo**: `shopee_endpoints_investigation.json`

### Teste 3: Análise do HTML
**Tamanho**: 159,590 bytes  
**Produtos encontrados**: 0  
**Arquivo**: `shop_page.html`

### Teste 4: Script Isolado
**Loja**: totalmenteseu (shopid: 1744033972)  
**Produtos esperados**: 6  
**Produtos retornados**: 0  
**Arquivo**: `scripts/test_shop_loader.py`

---

## 🎯 Opções Disponíveis

### Opção A: Esperar por Elementos DOM (RECOMENDADA)
**Estratégia**: Usar Playwright para esperar os produtos aparecerem no DOM após o JavaScript carregar.

**Vantagens**:
- Funciona com a arquitetura atual da Shopee
- Não depende de endpoints específicos
- Mais resiliente a mudanças

**Desvantagens**:
- Mais lento (precisa esperar JavaScript)
- Pode ser bloqueado por anti-bot

**Implementação**:
```python
# Esperar por elementos de produto no DOM
await page.wait_for_selector('[data-sqe="link"]', timeout=30000)
products = await page.query_selector_all('[data-sqe="link"]')

for product in products:
    name = await product.get_attribute('title')
    href = await product.get_attribute('href')
    # Extrair itemid do href
```

### Opção B: Engenharia Reversa do Module Federation
**Estratégia**: Interceptar os módulos JavaScript que carregam produtos.

**Vantagens**:
- Mais rápido que esperar DOM
- Acesso direto aos dados

**Desvantagens**:
- Complexo de implementar
- Frágil (módulos podem mudar)
- Requer análise profunda do código JS

### Opção C: Usar Selenium com Espera Explícita
**Estratégia**: Trocar Playwright por Selenium e esperar elementos específicos.

**Vantagens**:
- Selenium pode ser mais tolerante
- Mais opções de espera

**Desvantagens**:
- Mesmos problemas do Playwright
- Não resolve o problema fundamental

### Opção D: Aceitar Limitação Temporária
**Estratégia**: Manter fallback manual e documentar limitação.

**Vantagens**:
- Não bloqueia desenvolvimento
- Sentinela continua funcionando (manual)

**Desvantagens**:
- Auditoria e Otimização Completa ficam limitadas
- Experiência do usuário degradada

---

## 💡 Decisão Final: Importação de Catálogo

**CONTEXTO**: v4.0.0 também falha hoje (confirmado pelo usuário).  
**CONCLUSÃO**: A Shopee mudou a arquitetura e está bloqueando scraping automatizado.

### Estratégia Escolhida: Fase 6A - Importação de Catálogo

Em vez de tentar driblar a detecção da Shopee (guerra técnica instável), implementar **importação de catálogo autorizado**:

1. **Usuário exporta produtos do Shopee Seller Center** (XLSX/CSV)
2. **ShopeeBooster importa e cacheia** os produtos
3. **Produtos voltam a funcionar** em Auditoria, Sentinela e Otimização

### Vantagens
- ✅ Sem CNPJ ou API oficial
- ✅ Sem guerra contra anti-bot
- ✅ Fonte autorizada (próprio Seller Center)
- ✅ Mais estável que scraping
- ✅ Cache local para uso offline

### Ordem de Prioridade de Fontes
1. **Scraping público** (tentativa 1, pode falhar)
2. **Catálogo cacheado** (importado anteriormente)
3. **Upload XLSX/CSV** (solicita ao usuário)
4. **Keywords manuais** (Sentinela apenas, plano B)

---

## 📝 Próximos Passos

### ✅ CONCLUÍDO
1. ✅ Investigação completa da regressão
2. ✅ Confirmação: v4.0.0 também falha (não é regressão no código)
3. ✅ Criado `shopee_core/catalog_service.py` completo
4. ✅ Criado scripts de investigação manual e automatizada

### ⏳ EM ANDAMENTO - Fase 6A: Importação de Catálogo

#### Imediato (Hoje)
1. ⏳ Integrar `catalog_service.py` com `shop_loader_service.py`
   - Modificar `load_shop_with_fallback()` para usar catálogo cacheado
   - Ordem: scraping → catálogo cache → solicitar importação

2. ⏳ Adicionar suporte no WhatsApp (`whatsapp_service.py`)
   - Comando `/catalogo` ou `/catálogo` para importar
   - Aceitar arquivos XLSX/CSV em `/auditar`
   - Mensagem quando scraping falhar: "Encontrei catálogo importado, usar?"

3. ⏳ Adicionar suporte no Streamlit (`app.py`)
   - Botão "Importar catálogo da Shopee (.xlsx/.csv)" na Auditoria
   - Upload de arquivo
   - Listar produtos importados

4. ⏳ Integrar com Sentinela
   - Usar catálogo para gerar keywords automáticas quando scraping falhar

#### Curto Prazo (Esta Semana)
1. ⏳ Testar fluxo completo:
   - Importação → cache → uso em Auditoria → uso em Sentinela
2. ⏳ Documentar processo de exportação do Seller Center
3. ⏳ Atualizar README com novo fluxo
4. ⏳ Merge para main

#### Médio Prazo (Próximas Semanas)
1. ⏳ Monitorar estabilidade do catálogo
2. ⏳ Adicionar sincronização automática (opcional)
3. ⏳ Considerar investigação de novo endpoint (se necessário)

---

## 📚 Arquivos Relacionados

### Scripts de Investigação
- `scripts/test_shop_loader.py` - Teste isolado
- `scripts/investigate_shopee_endpoints.py` - Captura de endpoints
- `scripts/check_html_products.py` - Análise de HTML
- `scripts/discover_new_endpoint.py` - **NOVO**: Descoberta automatizada de endpoints
- `scripts/manual_browser_investigation.md` - **NOVO**: Guia de investigação manual

### Evidências
- `shopee_endpoints_investigation.json` - Todos os endpoints capturados
- `shop_page.html` - HTML completo da página
- `test_output.log` - Logs do teste

### Código Implementado
- `shopee_core/catalog_service.py` - **NOVO**: Serviço de importação de catálogo
- `backend_core.py` - `fetch_shop_products_intercept()` (tentativa DOM - falhou)
- `shopee_core/audit_service.py` - `load_shop_from_url()`
- `shopee_core/shop_loader_service.py` - `load_shop_with_fallback()` (precisa integração)

---

## 🔗 Referências

- [Stack Overflow: Shopee API Changes](https://stackoverflow.com)
- [Apify: Shopee Scraping](https://apify.com)
- [Webpack Module Federation](https://webpack.js.org/concepts/module-federation/)

---

**Data da Investigação**: 26/04/2026  
**Investigador**: Kiro AI Agent  
**Branch**: `fix/restore-shop-products-loader`
