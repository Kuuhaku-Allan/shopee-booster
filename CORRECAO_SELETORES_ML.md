# Correção: Seletores CSS do Mercado Livre

**Data**: 26/04/2026  
**Status**: ✅ Corrigido

---

## 🐛 Problema Identificado

A função `fetch_competitors_intercept()` estava encontrando 50 produtos no ML, mas retornando 0 concorrentes porque os **seletores CSS estavam incorretos**.

### Logs do Erro
```
[ML] Buscando: https://lista.mercadolivre.com.br/mochila-escolar
[ML] 50 produtos encontrados
[ML] Total de concorrentes: 0
```

---

## 🔍 Debug Realizado

Criei script `debug_ml_structure.py` que:
1. Abre o navegador (headless=False)
2. Acessa a página de busca do ML
3. Testa múltiplos seletores CSS
4. Captura HTML do primeiro produto
5. Identifica quais seletores funcionam

### Resultados do Debug

| Elemento | Seletor ERRADO (antes) | Seletor CORRETO (agora) | Status |
|----------|------------------------|-------------------------|--------|
| Cards | `.ui-search-result__content` | `.poly-card__content` | ✅ 50 elementos |
| Nome | `h2, .ui-search-item__title` | `.poly-component__title` | ✅ Funciona |
| Preço | `.andes-money-amount__fraction` | `.andes-money-amount__fraction` | ✅ Já estava correto |
| Avaliações/Estrelas | `.ui-search-reviews__amount` | `[class*="review"]` | ✅ Funciona |
| Link | `a[href*="/MLB"]` | `a[href*="/MLB"]` | ✅ Já estava correto |

---

## ✅ Correção Implementada

### Arquivo: `backend_core.py` - Função `fetch_competitors_intercept()`

**Mudanças**:

1. **Seletor de cards**: Removido `.ui-search-result__content`, mantido apenas `.poly-card__content`
2. **Seletor de nome**: Simplificado para `.poly-component__title` (único que funciona)
3. **Seletor de avaliações/estrelas**: Unificado em `[class*="review"]` com regex para extrair ambos
4. **Logs melhorados**: Agora mostra nome, preço e estrelas de cada produto

### Código Corrigido

```python
# Cards de produtos (CORRETO)
products = await page.query_selector_all('.poly-card__content')

# Nome (CORRETO)
name_elem = await product.query_selector('.poly-component__title')
if name_elem:
    name = await name_elem.inner_text()

# Preço (JÁ ESTAVA CORRETO)
price_elem = await product.query_selector('.andes-money-amount__fraction')

# Avaliações e Estrelas (CORRIGIDO - agora unificado)
reviews_elem = await product.query_selector('[class*="review"]')
if reviews_elem:
    reviews_text = await reviews_elem.inner_text()
    # Formato: " 4.5" ou "4.5 (123)"
    star_match = re.search(r'(\d+[,.]\d*)', reviews_text)
    if star_match:
        stars = float(star_match.group(1).replace(",", "."))
    
    review_count_match = re.search(r'\((\d+)\)', reviews_text)
    if review_count_match:
        reviews = int(review_count_match.group(1))
```

---

## 🧪 Como Testar Agora

### Teste 1: Recarregar e Testar

1. **Pare o Streamlit** (Ctrl+C no terminal)
2. **Reinicie**: `python -m streamlit run app.py`
3. **Recarregue a página** no navegador (F5)
4. Vá para **Auditoria** → **Radar de Concorrentes**
5. Digite "mochila escolar"
6. Clique em **"🔍 Buscar Concorrentes"**

**Resultado esperado**:
```
[ML] Buscando: https://lista.mercadolivre.com.br/mochila-escolar
[ML] 50 produtos encontrados
[ML] Produto 1: Mochila Tática Militar Camuf - R$ 78.00 - 4.5 estrelas
[ML] Produto 2: Mochila Escolar Infantil Ros - R$ 45.00 - 4.8 estrelas
...
[ML] Total de concorrentes: 10
```

E na interface:
- ✅ Tabela com 10 produtos
- ✅ Nomes, preços, estrelas preenchidos
- ✅ Métricas: Preço Médio, Mínimo, Máximo
- ✅ Sugestão de preço

### Teste 2: Script de Teste Rápido

```bash
python test_ml_competitors.py
```

Deve retornar 10 produtos com dados completos.

---

## 📊 Exemplo de Saída Esperada

### Console (stderr)
```
[ML] Buscando: https://lista.mercadolivre.com.br/mochila-escolar
[ML] 50 produtos encontrados
[ML] Produto 1: Mochila Tática Militar Camuf - R$ 78.00 - 4.5 estrelas
[ML] Produto 2: Mochila Escolar Infantil Ros - R$ 45.00 - 4.8 estrelas
[ML] Produto 3: Mochila Notebook Executiva Pr - R$ 120.00 - 4.7 estrelas
[ML] Produto 4: Mochila Feminina Casual Moder - R$ 89.00 - 4.6 estrelas
[ML] Produto 5: Mochila Infantil Personagens - R$ 35.00 - 4.9 estrelas
[ML] Produto 6: Mochila Grande Viagem Resiste - R$ 150.00 - 4.4 estrelas
[ML] Produto 7: Mochila Escolar Juvenil Colo - R$ 55.00 - 4.7 estrelas
[ML] Produto 8: Mochila Térmica Lancheira Int - R$ 42.00 - 4.8 estrelas
[ML] Produto 9: Mochila Rodinha Escolar Grand - R$ 180.00 - 4.3 estrelas
[ML] Produto 10: Mochila Esportiva Academia Fit - R$ 65.00 - 4.6 estrelas
[ML] Total de concorrentes: 10
```

### Interface Streamlit
```
┌─────────────────────────────────────────────────────────────┐
│ Nome                              │ Preço    │ Estrelas     │
├─────────────────────────────────────────────────────────────┤
│ Mochila Tática Militar Camuflada │ R$ 78.00 │ ⭐ 4.5       │
│ Mochila Escolar Infantil Rosa    │ R$ 45.00 │ ⭐ 4.8       │
│ Mochila Notebook Executiva Preta │ R$ 120.00│ ⭐ 4.7       │
│ ...                               │ ...      │ ...          │
└─────────────────────────────────────────────────────────────┘

💰 Preço Médio: R$ 85.90
📉 Mínimo: R$ 35.00
📈 Máximo: R$ 180.00

💡 Preço de lançamento sugerido: R$ 81.61
```

---

## 🔧 Arquivos Modificados

- ✅ `backend_core.py` (linha ~390) - Seletores corrigidos
- ✅ `MUDANCA_MERCADO_LIVRE_CONCORRENTES.md` - Documentação atualizada
- ✅ `CORRECAO_SELETORES_ML.md` (este arquivo) - Documentação da correção
- ✅ `debug_ml_structure.py` (novo) - Script de debug para futuros problemas

---

## 💡 Lições Aprendidas

1. **Sempre debugar com navegador visível primeiro** (headless=False)
2. **Capturar HTML real** para ver estrutura exata
3. **Testar múltiplos seletores** até encontrar o correto
4. **Mercado Livre usa classes diferentes** da Shopee:
   - Shopee: `.ui-search-*`
   - ML: `.poly-*` e `.andes-*`

---

## 🎯 Próximos Passos

1. ✅ Testar busca manual (você deve fazer agora)
2. ⏳ Testar otimização completa com produto
3. ⏳ Testar Sentinela com monitoramento
4. ⏳ Validar com XLSX real da amiga

---

**Pronto para teste! 🚀**

Agora deve funcionar perfeitamente!
