# Investigação Manual no Navegador - Shopee 2026

## 🎯 Objetivo
Descobrir como a Shopee carrega produtos hoje após a mudança de arquitetura.

## 📋 Passo a Passo

### 1. Abrir DevTools
1. Abra Chrome/Edge normal (não Playwright)
2. Pressione `F12` para abrir DevTools
3. Vá para aba **Network**
4. Marque **Preserve log**
5. Filtre por **Fetch/XHR**

### 2. Acessar a Loja
1. Cole no navegador: `https://shopee.com.br/totalmenteseu`
2. Aguarde a página carregar completamente
3. Role a página até aparecerem os produtos

### 3. Procurar Endpoints
No filtro de busca do Network, pesquise por:
- `item`
- `shop`
- `search`
- `tab`
- `collection`
- `product`

### 4. Identificar o Endpoint Correto
Para cada request encontrada:
1. Clique na request
2. Vá para aba **Preview** ou **Response**
3. Procure por nomes de produtos como:
   - "Mochila Feminina Rosa"
   - "Mochila Infantil Princesa Rosa"
   - "Minions Rosa"

### 5. Exportar HAR (Opcional)
1. Clique com botão direito na lista de requests
2. **Save all as HAR with content**
3. Salve como `shopee_investigation.har`

## 🔍 Endpoints Conhecidos para Testar

Baseado em referências externas, tente procurar por:

```
/api/v4/shop/search_items
/api/v4/shop/get_shop_tab
/api/v4/search/search_items
/api/v4/item/get_list
/api/v4/shop/get_shop_detail
/api/v4/shop/get_shop_items
```

## 📝 Informações a Coletar

Quando encontrar o endpoint correto, anote:

1. **URL completa**
2. **Método** (GET/POST)
3. **Query parameters** (se GET)
4. **Body** (se POST)
5. **Headers importantes**:
   - User-Agent
   - Referer
   - Accept
   - Cookie (se necessário)
   - X-API-Key (se houver)
   - X-Shopee-Language
   - X-Requested-With

6. **Formato da resposta**:
   - Estrutura JSON
   - Onde estão os produtos (path no JSON)
   - Campos disponíveis (itemid, name, price, etc.)

## 🎯 Loja de Teste

**URL**: https://shopee.com.br/totalmenteseu
**Shop ID**: 1744033972
**Produtos esperados**: 6
**Produtos conhecidos**:
- Mochila Feminina Rosa
- Mochila Infantil Princesa Rosa
- Minions Rosa

## 📊 Resultado Esperado

Ao final, você deve ter:
- ✅ URL do endpoint que retorna produtos
- ✅ Parâmetros necessários
- ✅ Headers obrigatórios
- ✅ Estrutura da resposta JSON
- ✅ Como extrair itemid, name, price, etc.

## 🚀 Próximo Passo

Com essas informações, podemos:
1. Replicar a request em Python
2. Atualizar `fetch_shop_products_intercept()` ou criar novo método
3. Testar no .exe e FastAPI
4. Restaurar funcionalidade completa da Auditoria

---

**Data**: 26/04/2026
**Status**: Aguardando investigação manual
**Branch**: `fix/restore-shop-products-loader`
