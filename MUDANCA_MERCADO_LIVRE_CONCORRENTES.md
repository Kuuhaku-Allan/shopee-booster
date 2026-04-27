# Mudança: Buscar Concorrentes Agora Usa Mercado Livre

**Data**: 26/04/2026  
**Status**: ✅ Implementado e pronto para teste

---

## 🎯 Problema Resolvido

A Shopee estava bloqueando o scraping de concorrentes (retornando 0 produtos), tornando impossível obter dados de mercado para análise competitiva.

## 💡 Solução Implementada

**Buscar Concorrentes agora usa o Mercado Livre** em vez da Shopee, seguindo o mesmo padrão já usado com sucesso para avaliações.

### Por que Mercado Livre?

1. ✅ **Mais estável**: Não tem o mesmo nível de anti-bot da Shopee
2. ✅ **Dados de mercado válidos**: O importante é ter referência de preços e produtos similares
3. ✅ **Já funciona**: Sistema de avaliações já usa ML com sucesso
4. ✅ **Mesma categoria de produtos**: Produtos similares existem em ambos marketplaces

---

## 🔧 Mudanças Técnicas

### 1. `backend_core.py` - Função `fetch_competitors_intercept()` (linha ~390)

**ANTES**: Buscava na Shopee via `https://shopee.com.br/api/v4/search/search_items`

**AGORA**: Busca no Mercado Livre via `https://lista.mercadolivre.com.br/{keyword}`

**Dados extraídos**:
- ✅ Nome do produto
- ✅ Preço (R$)
- ✅ Quantidade de avaliações
- ✅ Estrelas (rating)
- ✅ Item ID (MLB...)
- ⚠️ Curtidas = 0 (ML não tem curtidas, mas não afeta análise)

**Limite**: 10 produtos (suficiente para análise competitiva)

### 2. `app.py` - Interface do Usuário

**Mudanças**:
- ✅ Spinner atualizado: "🛒 Buscando concorrentes no Mercado Livre..."
- ✅ Info box adicionado: Explica que busca usa ML para maior estabilidade
- ✅ Sentinela também atualizado com nova mensagem

**Locais atualizados**:
- Linha ~611: Tab "Radar de Concorrentes" (Auditoria)
- Linha ~2521: Sentinela (monitoramento automático)

---

## 🧪 Como Testar

### Teste 1: Buscar Concorrentes Manual

1. **Recarregue a página** no navegador (F5 ou Ctrl+R)
2. Vá para **Auditoria** → Tab **"Radar de Concorrentes"**
3. Digite uma palavra-chave (ex: "mochila escolar")
4. Clique em **"🔍 Buscar Concorrentes"**

**Resultado esperado**:
- ✅ Spinner mostra "🛒 Buscando concorrentes no Mercado Livre..."
- ✅ Retorna ~10 produtos do Mercado Livre
- ✅ Tabela mostra: Nome, Preço, Avaliações, Curtidas (0), Estrelas
- ✅ Métricas: Preço Médio, Mínimo, Máximo
- ✅ Sugestão de preço de lançamento

### Teste 2: Otimização Completa com Produto do Catálogo

1. Carregue um catálogo (CSV/XLSX) ou use produtos já carregados
2. Selecione um produto
3. Clique em **"⚡ Otimizar"**
4. Aguarde a busca automática de concorrentes

**Resultado esperado**:
- ✅ Busca concorrentes automaticamente no ML
- ✅ Gera análise competitiva com dados do ML
- ✅ Otimização completa funciona normalmente

### Teste 3: Sentinela (Monitoramento)

1. Vá para **Sentinela**
2. Configure keywords para monitorar
3. Execute monitoramento

**Resultado esperado**:
- ✅ Busca concorrentes no ML para cada keyword
- ✅ Detecta mudanças de preço
- ✅ Envia alertas via Telegram

---

## 📊 Impacto nos Dados

### O que muda?

| Campo | Antes (Shopee) | Agora (ML) | Impacto |
|-------|----------------|------------|---------|
| Nome | ✅ | ✅ | Nenhum |
| Preço | ✅ | ✅ | Nenhum |
| Avaliações | ✅ | ✅ | Nenhum |
| Estrelas | ✅ | ✅ | Nenhum |
| Curtidas | ✅ | ❌ (sempre 0) | **Baixo** - não afeta análise de preço |
| Item ID | Shopee ID | MLB ID | Nenhum - apenas identificador |
| Shop ID | Shopee Shop | "mercadolivre" | Nenhum - apenas identificador |

### O que NÃO muda?

- ✅ **Catálogo da loja**: Continua vindo da Shopee (via CSV/XLSX ou scraping)
- ✅ **Avaliações**: Já usavam ML, continuam iguais
- ✅ **Análise de IA**: Funciona com dados de qualquer marketplace
- ✅ **Sentinela**: Continua monitorando mudanças de preço

---

## 🎯 Próximos Passos

1. ✅ **Testar busca manual** (Teste 1)
2. ✅ **Testar otimização completa** (Teste 2)
3. ⏳ **Testar com XLSX real** da amiga (quando disponível)
4. ⏳ **Testar Sentinela** em produção

---

## 💬 Mensagens para o Usuário

### Info Box (sempre visível)
```
💡 Busca de concorrentes agora usa o Mercado Livre para maior estabilidade 
   e dados de mercado mais confiáveis.
```

### Spinner (durante busca)
```
🛒 Buscando concorrentes no Mercado Livre... (30-60s)
```

---

## 🐛 Troubleshooting

### Problema: Ainda retorna 0 produtos

**Possíveis causas**:
1. Página não recarregada (ainda usando código antigo)
2. Keyword muito específica (não existe no ML)
3. Timeout de rede

**Solução**:
1. Recarregue a página (F5)
2. Tente keyword mais genérica (ex: "mochila" em vez de "mochila escolar infantil rosa")
3. Verifique logs no console (stderr)

### Problema: Erro de importação

**Causa**: Cache do Python

**Solução**:
```bash
# Pare o Streamlit (Ctrl+C)
# Limpe cache
python -c "import py_compile; py_compile.compile('backend_core.py')"
# Reinicie
python -m streamlit run app.py
```

---

## 📝 Notas Técnicas

### Seletores CSS do Mercado Livre (Verificados via Debug)

```python
# Cards de produtos
'.poly-card__content'  # ✅ 50 elementos encontrados

# Nome
'.poly-component__title'  # ✅ Funciona perfeitamente

# Preço
'.andes-money-amount__fraction'  # ✅ Retorna valor numérico

# Avaliações e Estrelas
'[class*="review"]'  # ✅ Retorna formato " 4.5" ou "4.5 (123)"

# Link (para item_id)
'a[href*="/MLB"]'  # ✅ Retorna URL com MLB ID
```

### Regex para Extração

```python
# Item ID
mlb_match = re.search(r'MLB[\d]+', href)

# Estrelas (do texto de review)
star_match = re.search(r'(\d+[,.]\d*)', reviews_text)

# Número de avaliações (se houver)
review_count_match = re.search(r'\((\d+)\)', reviews_text)
```

---

## ✅ Checklist de Implementação

- [x] Função `fetch_competitors_intercept()` reescrita
- [x] Seletores CSS do ML implementados
- [x] Extração de dados testada
- [x] Mensagens de UI atualizadas (app.py)
- [x] Info box adicionado
- [x] Sentinela atualizado
- [x] Documentação criada
- [ ] **Teste real com usuário** (próximo passo)

---

**Pronto para teste! 🚀**
