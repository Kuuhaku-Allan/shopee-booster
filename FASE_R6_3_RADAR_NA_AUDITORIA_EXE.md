# FASE R6.3 — Radar Assistido na Auditoria do .exe

**Status**: ✅ IMPLEMENTADO  
**Data**: 2026-05-23  
**Objetivo**: Expor o Radar Assistido na interface de Auditoria do app Streamlit/.exe

---

## 📋 Resumo

A R6.3 adiciona suporte visual ao Radar Assistido na tela de Auditoria do app Streamlit/.exe, usando a integração segura criada na R6.2.

**Regra principal**: A Auditoria continua funcionando sem Radar exatamente como antes. O Radar é opcional.

---

## 🎯 Objetivos Alcançados

✅ Helper de UI criado (`shopee_core/radar_ui_service.py`)  
✅ Seção expansível "Radar Assistido de Concorrentes" na Auditoria  
✅ Checkbox para ativar/desativar Radar  
✅ Selectbox com produtos disponíveis do Radar  
✅ Preview do contexto do Radar antes de gerar  
✅ Badge indicando quando Radar foi usado  
✅ Tratamento de erros sem quebrar a Auditoria  
✅ Testes completos (6/6)  
✅ Documentação completa

---

## 🔧 Arquivos Criados/Modificados

### Criados

**1. `shopee_core/radar_ui_service.py`**

Helper com 3 funções principais:

```python
def list_radar_products_for_audit(limit: int = 100) -> list[dict]:
    """
    Lista produtos próprios do Radar disponíveis para uso na Auditoria.
    
    Retorna produtos com:
    - source_type = own_product
    - status = collected
    - Informações sobre pattern report e confiança
    """

def format_radar_product_label(product: dict) -> str:
    """
    Formata label para exibição no selectbox da UI.
    
    Exemplo:
        "Mochila Infantil Princesa Rosa — 5 concorrentes diretos — confiança média"
    """

def get_radar_preview_for_ui(product_uid: str) -> dict:
    """
    Gera preview do contexto do Radar para exibição na UI.
    
    Retorna:
    - confidence, direct_count
    - price_min, price_avg, price_median, price_max
    - strong_terms, recommended_features, off_niche_features
    - commercial_arguments, warnings
    """
```

**2. `test_radar_ui_service.py`**

6 testes cobrindo:
1. ✅ list_radar_products_for_audit retorna lista sem quebrar
2. ✅ list_radar_products_for_audit retorna dados enriquecidos
3. ✅ format_radar_product_label inclui título e confiança
4. ✅ format_radar_product_label trunca título longo
5. ✅ get_radar_preview_for_ui retorna estrutura correta
6. ✅ get_radar_preview_for_ui não quebra com UID inválido

### Modificados

**1. `app.py`**

**Session State** (linhas ~153-180):
```python
_DEFAULTS = {
    # ... existentes ...
    # R6.3: Radar Assistido na Auditoria
    "use_radar_in_audit":      False,
    "selected_radar_product_uid": None,
    "optimization_used_radar": False,
    "optimization_radar_uid":  None,
    # ...
}
```

**Seção de Auditoria** (linhas ~399-500):

Adicionado **antes** do botão "Gerar Otimização Completa":

```python
# ── R6.3: Radar Assistido de Concorrentes (opcional) ──────
with st.expander("📡 Radar Assistido de Concorrentes", expanded=False):
    st.caption("Use o Radar Assistido para enriquecer a auditoria...")
    
    # Checkbox para ativar Radar
    use_radar = st.checkbox("Usar Radar Assistido nesta auditoria", ...)
    
    if use_radar:
        # Listar produtos disponíveis
        radar_products = list_radar_products_for_audit(limit=100)
        
        if not radar_products:
            st.warning("Nenhum relatório do Radar disponível...")
        else:
            # Selectbox com produtos
            selected_uid = st.selectbox(...)
            
            # Preview do Radar
            preview = get_radar_preview_for_ui(selected_uid)
            
            if preview["ok"]:
                st.success(f"Radar disponível — Confiança: {preview['confidence']}")
                # Mostrar faixa de preço, termos fortes, features, etc.
```

**Botão de Otimização** (linhas ~500-510):
```python
if st.button("🤖 Gerar Otimização Completa", type="primary"):
    # R6.3: Passar radar_own_product_uid se disponível
    radar_uid = st.session_state.get("selected_radar_product_uid") if st.session_state.get("use_radar_in_audit") else None
    
    # ... gerar otimização ...
    
    # R6.3: Armazenar se Radar foi usado
    if radar_uid:
        st.session_state.optimization_used_radar = True
        st.session_state.optimization_radar_uid = radar_uid
```

**Resultado da Otimização** (linhas ~510-530):
```python
if st.session_state.optimization_result:
    # R6.3: Mostrar badge se Radar foi usado
    if st.session_state.get("optimization_used_radar"):
        st.success("📡 **Radar Assistido usado nesta auditoria**")
        
        # Mostrar resumo do Radar usado
        st.caption(f"Confiança: {preview['confidence']} | {preview['direct_count']} concorrentes diretos | ...")
    
    st.markdown("### 📈 Listing Otimizado pela IA")
    st.markdown(st.session_state.optimization_result)
```

---

## 🎨 Interface do Usuário

### 1. Seção Expansível (Recolhida por Padrão)

```
┌─────────────────────────────────────────────────────────────┐
│ ▶ 📡 Radar Assistido de Concorrentes                       │
└─────────────────────────────────────────────────────────────┘
```

### 2. Seção Expandida (Sem Radar Disponível)

```
┌─────────────────────────────────────────────────────────────┐
│ ▼ 📡 Radar Assistido de Concorrentes                       │
├─────────────────────────────────────────────────────────────┤
│ Use o Radar Assistido para enriquecer a auditoria...       │
│                                                             │
│ ☐ Usar Radar Assistido nesta auditoria                     │
└─────────────────────────────────────────────────────────────┘
```

### 3. Seção Expandida (Com Radar Marcado, Sem Produtos)

```
┌─────────────────────────────────────────────────────────────┐
│ ▼ 📡 Radar Assistido de Concorrentes                       │
├─────────────────────────────────────────────────────────────┤
│ Use o Radar Assistido para enriquecer a auditoria...       │
│                                                             │
│ ☑ Usar Radar Assistido nesta auditoria                     │
│                                                             │
│ ⚠️ Nenhum relatório do Radar disponível ainda.             │
│    Execute o Radar Assistido antes ou continue a           │
│    auditoria sem Radar.                                    │
└─────────────────────────────────────────────────────────────┘
```

### 4. Seção Expandida (Com Radar Marcado, Com Produtos)

```
┌─────────────────────────────────────────────────────────────┐
│ ▼ 📡 Radar Assistido de Concorrentes                       │
├─────────────────────────────────────────────────────────────┤
│ Use o Radar Assistido para enriquecer a auditoria...       │
│                                                             │
│ ☑ Usar Radar Assistido nesta auditoria                     │
│                                                             │
│ Selecione o produto do Radar:                              │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Mochila Infantil Princesa Rosa — 5 concorrentes dire...│ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ✅ Radar disponível — Confiança: medium — 5 concorrentes   │
│                                                             │
│ ┌──────────────────────────┬──────────────────────────────┐ │
│ │ Faixa de preço:          │ Features recomendadas:       │ │
│ │ R$ 59.00 - R$ 302.53     │ escolar, infantil, rodinhas  │ │
│ │ (média: R$ 185.10)       │                              │ │
│ │                          │ ⚠️ Features a evitar:        │ │
│ │ Termos fortes:           │ notebook                     │ │
│ │ mochila, infantil, rosa  │                              │ │
│ └──────────────────────────┴──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 5. Resultado com Radar Usado

```
┌─────────────────────────────────────────────────────────────┐
│ ✅ 📡 Radar Assistido usado nesta auditoria                 │
│ Confiança: medium | 5 concorrentes diretos | Preço médio:  │
│ R$ 185.10                                                   │
├─────────────────────────────────────────────────────────────┤
│ ### 📈 Listing Otimizado pela IA                            │
│                                                             │
│ ## 🏷️ TÍTULO OTIMIZADO                                     │
│ Mochila Escolar Infantil Feminina Rosa com Rodinhas...     │
│                                                             │
│ ## 💰 ESTRATÉGIA DE PREÇO                                   │
│ ...                                                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 🧪 Como Testar

### Teste Unitário

```bash
python test_radar_ui_service.py
```

**Resultado esperado**: 6/6 testes passando

### Teste Manual no .exe

**Cenário A: Auditoria sem Radar (comportamento antigo)**

1. Rodar o app: `streamlit run app.py`
2. Ir para "Auditoria Pro"
3. Carregar uma loja
4. Selecionar um produto
5. **NÃO** marcar "Usar Radar Assistido"
6. Clicar em "Gerar Otimização Completa"
7. ✅ Verificar que funciona como antes

**Cenário B: Auditoria com Radar**

1. Rodar o app: `streamlit run app.py`
2. Ir para "Auditoria Pro"
3. Carregar uma loja
4. Selecionar um produto
5. Expandir "📡 Radar Assistido de Concorrentes"
6. ☑ Marcar "Usar Radar Assistido nesta auditoria"
7. Selecionar produto: `2777bd10-5e4f-40ff-b302-81d23f8834d9`
8. ✅ Verificar preview (confiança, preço, termos, features)
9. ✅ Verificar que "notebook" aparece como "Features a evitar"
10. Clicar em "Gerar Otimização Completa"
11. ✅ Verificar badge "📡 Radar Assistido usado nesta auditoria"
12. ✅ Verificar que "notebook" NÃO aparece como recomendação principal

**Cenário C: Radar sem produtos disponíveis**

1. Rodar o app: `streamlit run app.py`
2. Ir para "Auditoria Pro"
3. Carregar uma loja
4. Selecionar um produto
5. Expandir "📡 Radar Assistido de Concorrentes"
6. ☑ Marcar "Usar Radar Assistido nesta auditoria"
7. ✅ Verificar warning: "Nenhum relatório do Radar disponível ainda"
8. Clicar em "Gerar Otimização Completa"
9. ✅ Verificar que auditoria continua sem Radar

**Cenário D: Erro ao carregar Radar**

1. Renomear `data/radar.db` temporariamente
2. Rodar o app: `streamlit run app.py`
3. Ir para "Auditoria Pro"
4. Carregar uma loja
5. Selecionar um produto
6. Expandir "📡 Radar Assistido de Concorrentes"
7. ☑ Marcar "Usar Radar Assistido nesta auditoria"
8. ✅ Verificar que app não quebra
9. ✅ Verificar mensagem de erro amigável
10. Clicar em "Gerar Otimização Completa"
11. ✅ Verificar que auditoria continua sem Radar

---

## 📊 Resultados dos Testes

### Testes Unitários (6/6) ✅

```
test_list_radar_products_empty_when_no_products ... ok
test_list_radar_products_returns_enriched_data ... ok
test_format_radar_product_label_includes_title_and_confidence ... ok
test_format_radar_product_label_truncates_long_title ... ok
test_get_radar_preview_returns_structure ... ok
test_get_radar_preview_does_not_break_with_invalid_uid ... ok

Ran 6 tests in 0.208s - OK
```

### Testes de Regressão ✅

- ✅ `test_audit_radar_integration.py`: 8/8
- ✅ `test_radar_audit_context_service.py`: 10/10
- ✅ `test_radar_service.py`: 11/11
- ✅ `test_radar_relevance_service.py`: 16/16
- ✅ `test_radar_patterns_service.py`: 10/10

**Total**: 61/61 testes passando (100%)

---

## ✅ Critérios de Aceite (TODOS ATENDIDOS)

- ✅ Auditoria sem Radar continua funcionando
- ✅ Auditoria com Radar funciona
- ✅ Radar aparece como opcional na UI
- ✅ Preview do Radar aparece antes de gerar
- ✅ Resultado indica se Radar foi usado
- ✅ Erros do Radar não quebram a Auditoria
- ✅ Bot WhatsApp não foi alterado
- ✅ Sentinela não foi alterado
- ✅ Testes passam (6/6 novos + 55/55 regressão)

---

## 🚀 Próximos Passos

### R6.4 — Vincular Produto do Catálogo ao Radar

**Objetivo**: Permitir vincular automaticamente ou manualmente um produto do catálogo/loja a um produto do Radar.

**Funcionalidades**:
- Botão "Vincular ao Radar" ao lado de cada produto do catálogo
- Busca automática por título/preço similar
- Confirmação manual se múltiplas correspondências
- Armazenar vínculo no banco de dados
- Usar vínculo automaticamente na Auditoria

### R7 — Interface Completa do Radar Assistido

**Objetivo**: Criar interface dedicada para gerenciar o Radar Assistido.

**Funcionalidades**:
- Adicionar URLs de produtos próprios
- Adicionar URLs de concorrentes
- Visualizar produtos coletados
- Classificar concorrentes (direto/parcial/rejeitado)
- Visualizar relatórios de padrões
- Executar coletas em lote
- Limpar assets históricos

---

## 🔍 Limitações Atuais

1. **Radar é opcional**: Se não houver Radar, Auditoria funciona normalmente
2. **Confiança mínima**: Requer pelo menos 3 concorrentes diretos
3. **Sem vínculo automático**: R6.4 vai resolver
4. **Sem interface dedicada**: R7 vai resolver
5. **Sem coleta pela UI**: R7 vai resolver

---

## 📝 Notas Técnicas

### Tratamento de Erros

A interface trata graciosamente os seguintes cenários:

1. **Banco de dados não existe**: Retorna lista vazia, não quebra
2. **Nenhum produto disponível**: Mostra warning amigável
3. **Produto sem pattern report**: Filtra automaticamente
4. **Base insuficiente (<3 concorrentes)**: Filtra automaticamente
5. **Erro ao carregar preview**: Mostra erro, continua sem Radar
6. **Exceção no helper**: Captura, mostra erro, continua sem Radar

### Fluxo de Decisão

```
Usuário marca "Usar Radar"
  ↓
list_radar_products_for_audit()
  ↓
Produtos disponíveis?
  ↓
SIM → Mostrar selectbox
  │     ↓
  │     Usuário seleciona produto
  │     ↓
  │     get_radar_preview_for_ui()
  │     ↓
  │     Mostrar preview (preço, termos, features)
  │     ↓
  │     Usuário clica "Gerar Otimização"
  │     ↓
  │     generate_full_optimization(radar_context_block=...)
  │     ↓
  │     Mostrar badge "Radar usado"
  │
NÃO → Mostrar warning
      ↓
      Usuário clica "Gerar Otimização"
      ↓
      generate_full_optimization(radar_context_block=None)
      ↓
      Auditoria normal
```

---

## 📚 Referências

- **R6.2**: `FASE_R6_2_AUDITORIA_COM_RADAR.md` - Integração backend
- **R6.1**: `FASE_R6_1_RADAR_AUDIT_CONTEXT.md` - Adaptador do Radar
- **R5.1**: `R5_1_APROVADA_PARA_R6.md` - Validação do Radar

---

**Commit**: `git commit -m "R6.3: Expose optional radar context in audit UI"`
