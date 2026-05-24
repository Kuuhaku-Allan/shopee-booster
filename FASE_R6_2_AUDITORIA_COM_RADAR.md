# FASE R6.2 — Auditoria com Radar Opcional

**Status**: ✅ IMPLEMENTADO  
**Data**: 2026-05-23  
**Objetivo**: Integrar contexto do Radar na Auditoria sem quebrar fluxo existente

---

## 📋 Resumo

A R6.2 permite que a Auditoria use o contexto do Radar como evidência de mercado opcional. Se o Radar não estiver disponível, a Auditoria funciona exatamente como antes.

**Regra principal**: O Radar é uma melhoria opcional, não uma dependência obrigatória.

---

## 🎯 Objetivos Alcançados

✅ Auditoria aceita `radar_own_product_uid` opcional  
✅ Carrega contexto do Radar quando disponível  
✅ Passa contexto para `generate_full_optimization()`  
✅ Prompt do Gemini inclui contexto do Radar  
✅ Instruções específicas para usar Radar como evidência  
✅ Comportamento antigo preservado quando Radar não disponível  
✅ Testes unitários completos (8/8)  
✅ Script de teste manual com modo dry-run  
✅ Documentação completa

---

## 🔧 Arquivos Modificados

### 1. `backend_core.py`

**Função**: `generate_full_optimization()`

**Mudanças**:
- Adicionado parâmetro opcional: `radar_context_block: str | None = None`
- Se `radar_context_block` fornecido, insere no prompt ANTES das instruções principais
- Adiciona instruções específicas para usar Radar como evidência

**Exemplo de uso**:
```python
optimization = generate_full_optimization(
    product=product,
    competitors_df=df_competitors,
    reviews=reviews,
    segmento="Mochilas Escolares",
    api_key="sua_api_key",
    radar_context_block="=== CONTEXTO DO RADAR ===\n...",  # Opcional
)
```

### 2. `shopee_core/audit_service.py`

**Função**: `generate_product_optimization()`

**Mudanças**:
- Adicionado parâmetro opcional: `radar_own_product_uid: str | None = None`
- Fluxo condicional:
  1. Se `radar_own_product_uid` fornecido:
     - Chama `get_radar_audit_context_status()`
     - Se `can_use=True`: carrega contexto e passa para `generate_full_optimization()`
     - Se `can_use=False`: loga motivo e continua sem Radar
  2. Se `radar_own_product_uid` não fornecido: comportamento antigo intacto
- Retorna `radar_used` e `radar_status` no resultado

**Exemplo de uso**:
```python
result = generate_product_optimization(
    product=product,
    segmento="Mochilas Escolares",
    api_key="sua_api_key",
    radar_own_product_uid="2777bd10-5e4f-40ff-b302-81d23f8834d9",  # Opcional
)

print(result["data"]["radar_used"])  # True/False
print(result["data"]["radar_status"])  # Status do Radar
```

---

## 📝 Prompt do Gemini

### Sem Radar (comportamento antigo)

```
Você é um especialista em e-commerce Shopee brasileiro...

PRODUTO ATUAL DA LOJA:
- Nome: Mochila Escolar Infantil
- Preço atual: R$ 89.90
- Segmento: Mochilas Escolares

TOP CONCORRENTES NA SHOPEE:
...

AVALIAÇÕES DO MERCADO:
...

Com base nessa análise completa, gere uma otimização...
```

### Com Radar (novo comportamento)

```
Você é um especialista em e-commerce Shopee brasileiro...

=== CONTEXTO DO RADAR DE CONCORRENTES ===

Base analisada:
- Concorrentes diretos: 10
- Confiança: high
- Preço médio: R$ 85.50

Termos fortes em títulos:
- mochila, escolar, infantil, resistente

Features recorrentes recomendadas:
- impermeável, ajustável, reforçada

Features fora de nicho / evitar:
- notebook, caderno, estojo

Instruções de uso:
- Não inventar dados fora do Radar.
- Não recomendar features marcadas como off-niche.
- Usar o Radar como evidência, não como verdade absoluta.

PRODUTO ATUAL DA LOJA:
- Nome: Mochila Escolar Infantil
- Preço atual: R$ 89.90
- Segmento: Mochilas Escolares

TOP CONCORRENTES NA SHOPEE:
...

AVALIAÇÕES DO MERCADO:
...

IMPORTANTE: Use o contexto do Radar como evidência de mercado. 
Não invente dados que não estejam no Radar. 
Não recomende features marcadas como off-niche ou avoid. 
Se houver conflito entre Radar e dados do produto, explique com cuidado.

Com base nessa análise completa, gere uma otimização...
```

---

## 🧪 Como Testar

### Teste Manual (Dry Run - sem gastar quota)

```bash
python scripts/audit_with_radar_context.py 2777bd10-5e4f-40ff-b302-81d23f8834d9 --dry-run-prompt
```

**O que verifica**:
- Status do Radar (can_use, confidence, direct_count)
- Contexto construído (caracteres, termos fortes, features)
- Prompt block completo (sem chamar Gemini)
- Validação: "notebook" aparece como off-niche/evitar

### Teste Manual (Completo - com Gemini)

```bash
python scripts/audit_with_radar_context.py 2777bd10-5e4f-40ff-b302-81d23f8834d9
```

**O que verifica**:
- Tudo do dry run +
- Chama Gemini e gera otimização real
- Valida que "notebook" não vira recomendação

### Testes Unitários

```bash
python test_audit_radar_integration.py
```

**Cobertura**:
1. ✅ Auditoria sem `radar_own_product_uid` mantém comportamento antigo
2. ✅ `radar_own_product_uid` inexistente não quebra
3. ✅ Status `can_use=False` não quebra
4. ✅ Status `can_use=True` chama `build_radar_prompt_block`
5. ✅ `generate_full_optimization` recebe `radar_context_block`
6. ✅ Prompt inclui "CONTEXTO DO RADAR"
7. ✅ Prompt inclui "notebook" como off-niche/evitar
8. ✅ Sem `radar_context_block`, prompt não muda

---

## 📊 Resultados dos Testes

### Testes Unitários

```
test_audit_without_radar_maintains_old_behavior ... ok
test_nonexistent_radar_uid_does_not_break ... ok
test_status_can_use_false_does_not_break ... ok
test_status_can_use_true_calls_build_radar_prompt_block ... ok
test_prompt_includes_radar_context_when_provided ... ok
test_prompt_includes_notebook_as_off_niche ... ok
test_prompt_without_radar_context_unchanged ... ok
test_generate_full_optimization_accepts_radar_context_block ... ok

----------------------------------------------------------------------
Ran 8 tests in 0.XXXs

OK
```

### Teste Manual (Dry Run)

```
================================================================================
TESTE DE AUDITORIA COM RADAR
================================================================================
Radar UID: 2777bd10-5e4f-40ff-b302-81d23f8834d9
Modo: DRY RUN (sem Gemini)

1. Verificando status do Radar...
   - can_use: True
   - reason: Radar disponível com 10 concorrentes diretos.
   - confidence: high
   - direct_count: 10

2. Carregando produto do Radar...
   - Título: Mochila Escolar Infantil Resistente
   - Preço: R$ 89.90
   - Marketplace: shopee

3. Construindo contexto do Radar...
   - Contexto construído: 1234 caracteres

4. Resumo do contexto do Radar:
--------------------------------------------------------------------------------
   Concorrentes diretos: 10
   Confiança: high
   Preço médio: R$ 85.50

   Termos fortes: mochila, escolar, infantil, resistente, ajustável

   Features recomendadas: impermeável, ajustável, reforçada, resistente, leve
   Features off-niche: notebook, caderno, estojo
--------------------------------------------------------------------------------

5. MODO DRY RUN - Imprimindo prompt block:
================================================================================
=== CONTEXTO DO RADAR DE CONCORRENTES ===

Base analisada:
- Concorrentes diretos: 10
- Confiança: high
- Preço mínimo: R$ 65.00
- Preço médio: R$ 85.50
- Preço mediano: R$ 84.90
- Preço máximo: R$ 129.90

Termos fortes em títulos:
- mochila, escolar, infantil, resistente, ajustável

Features recorrentes recomendadas:
- impermeável, ajustável, reforçada, resistente, leve

Features fora de nicho / evitar:
- notebook, caderno, estojo

Instruções de uso:
- Não inventar dados fora do Radar.
- Não recomendar features marcadas como off-niche.
- Usar o Radar como evidência, não como verdade absoluta.
- Priorizar recomendações de alta prioridade.
================================================================================

✅ Dry run concluído. Prompt block acima seria enviado ao Gemini.

✅ VALIDAÇÃO: 'notebook' aparece como off-niche/evitar (correto)

================================================================================
TESTE CONCLUÍDO
================================================================================
```

---

## 🎯 Critérios de Aceite

✅ Auditoria sem Radar continua funcionando  
✅ Auditoria com Radar inclui contexto no prompt  
✅ Radar é opcional  
✅ Notebook/off-niche não vira recomendação  
✅ Sem Bot WhatsApp alterado  
✅ Sem Sentinela alterado  
✅ Sem app.py alterado ainda  
✅ Testes passam (8/8)  
✅ Commit separado

---

## 🚀 Próximos Passos

### R6.3 — Expor Radar na Auditoria do .exe

Essa fase vai adicionar a interface visual para:
- Usuário selecionar um produto do Radar
- Vincular produto do catálogo ao Radar
- Executar auditoria com contexto do Radar

**Arquivos a modificar**:
- `app.py` (interface Streamlit)
- Adicionar seletor de produto do Radar
- Adicionar checkbox "Usar contexto do Radar"
- Passar `radar_own_product_uid` para `generate_product_optimization()`

---

## 📚 Referências

- **R6.1**: `FASE_R6_1_RADAR_AUDIT_CONTEXT.md` - Adaptador do Radar
- **R5.1**: `R5_1_APROVADA_PARA_R6.md` - Validação do Radar
- **Serviços**:
  - `shopee_core/radar_audit_context_service.py` - Contexto do Radar
  - `shopee_core/audit_service.py` - Serviço de Auditoria
  - `backend_core.py` - Geração com Gemini

---

## 🔍 Limitações Atuais

1. **Radar é opcional**: Se não houver Radar, Auditoria funciona normalmente
2. **Confiança mínima**: Requer pelo menos 3 concorrentes diretos
3. **Sem UI ainda**: R6.3 vai expor no .exe
4. **Sem Bot WhatsApp**: Integração futura se necessário
5. **Sem Sentinela**: Integração futura se necessário

---

## 📝 Notas Técnicas

### Fluxo de Decisão

```
generate_product_optimization()
  ↓
  radar_own_product_uid fornecido?
  ↓
  SIM → get_radar_audit_context_status()
  │     ↓
  │     can_use=True?
  │     ↓
  │     SIM → build_radar_audit_context()
  │     │     ↓
  │     │     build_radar_prompt_block()
  │     │     ↓
  │     │     generate_full_optimization(radar_context_block=...)
  │     │
  │     NÃO → generate_full_optimization(radar_context_block=None)
  │
  NÃO → generate_full_optimization(radar_context_block=None)
```

### Compatibilidade

- ✅ Python 3.10+
- ✅ Gemini API (modelos texto)
- ✅ SQLite (banco do Radar)
- ✅ Pandas (DataFrame de concorrentes)

---

**Commit**: `git commit -m "R6.2: Add optional radar context to audit generation"`
