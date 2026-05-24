# 🧪 TESTE R6.3B AGORA — SMOKE AUDITORIA COM RADAR

**Status**: ✅ PRONTO PARA TESTE  
**Tempo**: 10 minutos  
**Objetivo**: Validar que o Radar realmente é usado na otimização

---

## ⚡ Testes Rápidos

### 1️⃣ Cenário A: SEM Radar (2 minutos)

**Objetivo**: Validar que fluxo antigo continua funcionando

```bash
streamlit run app.py
```

**Passos**:
1. Ir para "Auditoria Pro"
2. Inserir qualquer título e descrição
3. NÃO marcar "Usar Radar Assistido"
4. Clicar "Gerar Otimização Completa"

**Resultado esperado**:
- ✅ Otimização gerada normalmente
- ✅ Sem badge "Radar usado"
- ✅ Logs mostram: `[R6.3B] Radar checkbox = False`

**Logs no terminal**:
```
[R6.3B] Radar checkbox = False
[R6.3B] selected_radar_product_uid = None
[R6.3B] Radar NÃO usado no resultado
```

---

### 2️⃣ Cenário B: COM Radar + Debug SEM IA (3 minutos)

**Objetivo**: Validar contexto do Radar sem gastar quota

**Passos**:
1. Ir para "Auditoria Pro"
2. Inserir qualquer título e descrição
3. Expandir "📡 Radar Assistido de Concorrentes"
4. Marcar "Usar Radar Assistido nesta auditoria"
5. Selecionar produto: `2777bd10-5e4f-40ff-b302-81d23f8834d9`
6. Marcar "🐛 Debug: mostrar contexto do Radar sem chamar IA"
7. Clicar "Gerar Otimização Completa"

**Resultado esperado**:
- ✅ Mostra "🐛 Modo Debug Ativado"
- ✅ Mostra resumo do mercado (JSON)
- ✅ Mostra estratégia de título (JSON)
- ✅ Mostra estratégia de features (JSON)
- ✅ Mostra "✅ 'notebook' está corretamente marcado como off-niche/evitar"
- ✅ Mostra "ℹ️ Modo debug ativo - IA não foi chamada"
- ✅ NÃO gera otimização (economiza quota)

**Logs no terminal**:
```
[R6.3B] Radar checkbox = True
[R6.3B] selected_radar_product_uid = 2777bd10-5e4f-40ff-b302-81d23f8834d9
[R6.3B] radar can_use = True
[R6.3B] radar confidence = medium
[R6.3B] radar direct_count = 5
[R6.3B] Construindo contexto do Radar para UID: 2777bd10...
[R6.3B] Off-niche features: ['notebook']
```

**UI esperada**:
```
🐛 Modo Debug Ativado - Mostrando contexto do Radar sem chamar IA

✅ Contexto do Radar construído com sucesso

📊 Resumo do Mercado:
{
  "confidence": "medium",
  "competitor_count": 5,
  "price_min": 59.0,
  "price_avg": 185.10,
  "price_max": 302.53
}

✨ Estratégia de Features:
{
  "recommended_features": ["escolar", "infantil", "rodinhas", ...],
  "off_niche_features": ["notebook"]
}

✅ 'notebook' está corretamente marcado como off-niche/evitar
```

---

### 3️⃣ Cenário C: COM Radar + IA Real (5 minutos)

**Objetivo**: Validar que IA usa contexto do Radar

**Pré-requisito**: Ter quota/API do Gemini funcionando

**Passos**:
1. Ir para "Auditoria Pro"
2. Inserir título e descrição de uma mochila infantil
3. Expandir "📡 Radar Assistido de Concorrentes"
4. Marcar "Usar Radar Assistido nesta auditoria"
5. Selecionar produto: `2777bd10-5e4f-40ff-b302-81d23f8834d9`
6. NÃO marcar debug
7. Clicar "Gerar Otimização Completa"

**Resultado esperado**:
- ✅ Badge "📡 Radar Assistido usado nesta auditoria"
- ✅ Linha de resumo: "Confiança: medium | 5 concorrentes diretos | Preço médio: R$ 185.10"
- ✅ Expander "📊 Ver detalhes do Radar usado"
- ✅ Otimização usa termos: infantil, escolar, feminina, rodinhas, rosa
- ✅ Otimização NÃO recomenda "notebook" como diferencial
- ✅ Se mencionar "notebook", apenas como termo a evitar

**Logs no terminal**:
```
[R6.3B] Radar checkbox = True
[R6.3B] selected_radar_product_uid = 2777bd10-5e4f-40ff-b302-81d23f8834d9
[R6.3B] radar can_use = True
[R6.3B] radar confidence = medium
[R6.3B] radar direct_count = 5
[R6.3B] Enviando radar_own_product_uid para auditoria: 2777bd10...
[R6.3B] Construindo contexto do Radar...
[R6.3B] Contexto do Radar construído: XXXX caracteres
[R6.3B] Off-niche features: ['notebook']
[R6.3B] Otimização gerada: XXXX caracteres
[R6.3B] Radar marcado como usado no resultado
```

**UI esperada**:
```
📡 Radar Assistido usado nesta auditoria
Confiança: medium | 5 concorrentes diretos | Preço médio: R$ 185.10

▼ 📊 Ver detalhes do Radar usado
   Faixa de preço: R$ 59.00 - R$ 302.53
   Termos fortes: mochila, infantil, rosa, escolar, feminina
   Features recomendadas: escolar, infantil, rodinhas, feminina, rosa
   ⚠️ Features evitadas (off-niche): notebook

### 📈 Listing Otimizado pela IA
[Otimização que usa termos do Radar e evita "notebook"]
```

---

## 🎯 O que Validar

### ✅ Cenário A (sem Radar)
- [ ] Otimização gerada normalmente
- [ ] Sem badge "Radar usado"
- [ ] Logs mostram `Radar checkbox = False`

### ✅ Cenário B (debug sem IA)
- [ ] Modo debug ativado
- [ ] Mostra resumo do mercado
- [ ] Mostra estratégia de features
- [ ] "notebook" em off-niche
- [ ] Mensagem "✅ 'notebook' está corretamente marcado"
- [ ] NÃO chama IA (economiza quota)

### ✅ Cenário C (IA real)
- [ ] Badge "Radar usado" aparece
- [ ] Resumo do Radar aparece
- [ ] Expander com detalhes
- [ ] Otimização usa termos do Radar
- [ ] "notebook" NÃO é recomendação principal
- [ ] Logs mostram contexto construído

---

## 🐛 Se Encontrar Problema

### Problema: Logs não aparecem no terminal
**Solução**: Verificar se está rodando `streamlit run app.py` no terminal (não no .exe)

### Problema: Debug não mostra contexto
**Solução**: 
1. Verificar se marcou checkbox "Debug"
2. Verificar se selecionou produto do Radar
3. Verificar logs no terminal

### Problema: Badge "Radar usado" não aparece
**Solução**:
1. Verificar logs: `[R6.3B] Radar marcado como usado`
2. Verificar se contexto foi construído
3. Verificar se `radar_context_block` não é None

### Problema: "notebook" não está em off-niche
**Solução**:
1. Rodar diagnóstico: `python scripts/radar_debug_app_visibility.py`
2. Verificar se produto tem pattern report
3. Verificar se relevance service marcou "notebook" corretamente

---

## 📸 Screenshots Esperados

### Cenário B: Debug Sem IA
```
🐛 Modo Debug Ativado - Mostrando contexto do Radar sem chamar IA

✅ Contexto do Radar construído com sucesso

📊 Resumo do Mercado:
{
  "confidence": "medium",
  "competitor_count": 5,
  "price_min": 59.0,
  "price_avg": 185.10,
  "price_median": 185.10,
  "price_max": 302.53
}

🏷️ Estratégia de Título:
{
  "strong_terms": ["mochila", "infantil", "rosa", "escolar", "feminina"],
  "weak_terms": ["notebook", ...]
}

✨ Estratégia de Features:
{
  "recommended_features": ["escolar", "infantil", "rodinhas", "feminina", "rosa"],
  "off_niche_features": ["notebook"]
}

✅ 'notebook' está corretamente marcado como off-niche/evitar

▼ 📄 Ver contexto completo (JSON)
   [JSON completo do contexto]

ℹ️ Modo debug ativo - IA não foi chamada. Desmarque o debug para gerar otimização real.
```

### Cenário C: IA Real
```
📡 Radar Assistido usado nesta auditoria
Confiança: medium | 5 concorrentes diretos | Preço médio: R$ 185.10

▼ 📊 Ver detalhes do Radar usado
   Faixa de preço: R$ 59.00 - R$ 302.53
   Termos fortes: mochila, infantil, rosa, escolar, feminina
   Features recomendadas: escolar, infantil, rodinhas, feminina, rosa
   ⚠️ Features evitadas (off-niche): notebook

### 📈 Listing Otimizado pela IA

**Título Otimizado:**
Mochila Infantil Escolar Feminina Rosa com Rodinhas - Grande Capacidade

**Descrição:**
Perfeita para meninas que amam princesas! Esta mochila infantil combina estilo e praticidade...
[Não menciona "notebook" como vantagem]
```

---

## ✅ Checklist Completo

### Implementação
- [x] Logs claros em todas as etapas
- [x] Modo debug sem IA
- [x] Construção do contexto do Radar
- [x] Passagem do contexto para Gemini
- [x] Badge visual no resultado
- [x] Expander com detalhes do Radar

### Cenário A (sem Radar)
- [ ] Otimização funciona
- [ ] Sem badge
- [ ] Logs corretos

### Cenário B (debug)
- [ ] Modo debug ativa
- [ ] Mostra contexto
- [ ] "notebook" em off-niche
- [ ] NÃO chama IA

### Cenário C (IA real)
- [ ] Badge aparece
- [ ] Resumo correto
- [ ] Otimização usa Radar
- [ ] "notebook" não é recomendação

---

## 🚀 Após Validação

Se tudo funcionar:
1. ✅ Marcar R6.3B como VALIDADO
2. ✅ Recompilar o .exe
3. ✅ Copiar `data/radar.db` para `dist/ShopeeBooster/data/`
4. ✅ Testar .exe com os 3 cenários

Se encontrar problemas:
1. ❌ Reportar erro com logs
2. ❌ Incluir screenshot
3. ❌ Descrever cenário que falhou

---

## 📚 Documentação

- **Técnica**: `FASE_R6_3B_SMOKE_AUDITORIA_RADAR_UI.md`
- **Teste**: `TESTE_R6_3B_AGORA.md` (este arquivo)

---

**Tempo estimado**: 10 minutos  
**Dificuldade**: Média  
**Pré-requisito**: Ter `data/radar.db` com produto `2777bd10...`

**UID de teste**: `2777bd10-5e4f-40ff-b302-81d23f8834d9`
