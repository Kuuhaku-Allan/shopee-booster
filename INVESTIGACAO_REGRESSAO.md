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

## 💡 Recomendação Final

**Implementar Opção A** (Esperar por Elementos DOM) com as seguintes melhorias:

1. **Modificar `fetch_shop_products_intercept`**:
   - Remover dependência de `rcmd_items` e `shop_page`
   - Adicionar espera por elementos DOM de produtos
   - Extrair dados dos elementos renderizados

2. **Adicionar Timeout Configurável**:
   - Permitir ajustar tempo de espera
   - Fallback para manual se timeout

3. **Melhorar Logs**:
   - Mostrar progresso do carregamento
   - Indicar quando produtos aparecem

4. **Manter Fallback Manual**:
   - Como plano B para o Sentinela
   - Não remover, apenas complementar

---

## 📝 Próximos Passos

### Imediato (Hoje)
1. ✅ Investigação completa - CONCLUÍDO
2. ⏳ Implementar Opção A (espera por DOM)
3. ⏳ Testar com loja totalmenteseu
4. ⏳ Validar com .exe e FastAPI

### Curto Prazo (Esta Semana)
1. ⏳ Documentar nova abordagem
2. ⏳ Atualizar testes
3. ⏳ Merge para main

### Médio Prazo (Próximas Semanas)
1. ⏳ Monitorar estabilidade
2. ⏳ Considerar Opção B se necessário
3. ⏳ Otimizar performance

---

## 📚 Arquivos Relacionados

### Scripts de Investigação
- `scripts/test_shop_loader.py` - Teste isolado
- `scripts/investigate_shopee_endpoints.py` - Captura de endpoints
- `scripts/check_html_products.py` - Análise de HTML

### Evidências
- `shopee_endpoints_investigation.json` - Todos os endpoints capturados
- `shop_page.html` - HTML completo da página
- `test_output.log` - Logs do teste

### Código Afetado
- `backend_core.py` - `fetch_shop_products_intercept()`
- `shopee_core/audit_service.py` - `load_shop_from_url()`
- `shopee_core/shop_loader_service.py` - `load_shop_with_fallback()`

---

## 🔗 Referências

- [Stack Overflow: Shopee API Changes](https://stackoverflow.com)
- [Apify: Shopee Scraping](https://apify.com)
- [Webpack Module Federation](https://webpack.js.org/concepts/module-federation/)

---

**Data da Investigação**: 26/04/2026  
**Investigador**: Kiro AI Agent  
**Branch**: `fix/restore-shop-products-loader`
