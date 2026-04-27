# Testes da Fase 6A - Importação de Catálogo

## 🎯 Objetivo
Validar que a importação de catálogo funciona corretamente no .exe, WhatsApp e API REST antes de integrar com o Sentinela.

---

## ✅ CHECKLIST DE TESTES

### 1. Teste no .exe / Streamlit (CRÍTICO)

**Loja de teste**: https://shopee.com.br/totalmenteseu

#### Fluxo Completo:
- [ ] 1.1. Abrir o .exe
- [ ] 1.2. Ir para aba "Auditoria Pro"
- [ ] 1.3. Colar URL: `https://shopee.com.br/totalmenteseu`
- [ ] 1.4. Clicar em "🔍 Analisar"
- [ ] 1.5. **Verificar**: Scraping falha ou retorna 0 produtos
- [ ] 1.6. **Verificar**: Aparece seção "📦 Catálogo da Loja"
- [ ] 1.7. **Verificar**: Aparece expander "Por que não consegui carregar os produtos?"
- [ ] 1.8. **Verificar**: Aparece seção de upload de arquivo
- [ ] 1.9. Fazer upload de arquivo XLSX ou CSV do Seller Center
- [ ] 1.10. **Verificar**: Aparece "⏳ Importando catálogo..."
- [ ] 1.11. **Verificar**: Aparece "✅ X produto(s) importado(s) com sucesso!"
- [ ] 1.12. **Verificar**: Aparece preview dos primeiros 5 produtos
- [ ] 1.13. **Verificar**: Barra de status mostra "📦 Catálogo importado"
- [ ] 1.14. **Verificar**: Métrica "📦 Produtos" mostra contagem correta
- [ ] 1.15. Rolar para baixo até "Galeria de Produtos"
- [ ] 1.16. **Verificar**: Produtos aparecem na galeria
- [ ] 1.17. Clicar em "⚡ Otimizar" em um produto
- [ ] 1.18. **Verificar**: Produto é selecionado
- [ ] 1.19. **Verificar**: Aparece painel "Otimização: [nome do produto]"
- [ ] 1.20. Clicar em "🤖 Gerar Otimização Completa"
- [ ] 1.21. **Verificar**: IA processa e gera listing otimizado
- [ ] 1.22. **Verificar**: Resultado aparece com título, descrição, tags, etc.

**Resultado Esperado**: ✅ Fluxo completo funciona do início ao fim

---

### 2. Teste de Cache no .exe

#### Fluxo:
- [ ] 2.1. **Fechar completamente o .exe**
- [ ] 2.2. Abrir o .exe novamente
- [ ] 2.3. Ir para "Auditoria Pro"
- [ ] 2.4. Colar a mesma URL: `https://shopee.com.br/totalmenteseu`
- [ ] 2.5. Clicar em "🔍 Analisar"
- [ ] 2.6. **Verificar**: Scraping falha novamente
- [ ] 2.7. **Verificar**: Aparece "📦 Catálogo salvo encontrado!"
- [ ] 2.8. **Verificar**: Mostra contagem de produtos, data de importação
- [ ] 2.9. **Verificar**: Aparece botão "✅ Usar catálogo salvo"
- [ ] 2.10. Clicar em "✅ Usar catálogo salvo"
- [ ] 2.11. **Verificar**: Produtos carregam instantaneamente (sem novo upload)
- [ ] 2.12. **Verificar**: Barra de status mostra "📦 Catálogo importado (cache)"
- [ ] 2.13. **Verificar**: Produtos aparecem na galeria

**Resultado Esperado**: ✅ Cache SQLite funciona corretamente

---

### 3. Teste no WhatsApp (se Evolution API estiver configurada)

#### Fluxo:
- [ ] 3.1. Enviar `/catalogo` para o bot
- [ ] 3.2. **Verificar**: Bot responde com instruções de exportação
- [ ] 3.3. Enviar arquivo XLSX/CSV como **documento** (não como imagem)
- [ ] 3.4. **Verificar**: Bot responde "⏳ Importando catálogo..."
- [ ] 3.5. **Verificar**: Bot confirma "✅ Catálogo importado com sucesso!"
- [ ] 3.6. **Verificar**: Bot mostra contagem e preview dos primeiros produtos
- [ ] 3.7. Enviar `/auditar https://shopee.com.br/totalmenteseu`
- [ ] 3.8. **Verificar**: Bot responde "⏳ Carregando sua loja..."
- [ ] 3.9. **Verificar**: Bot usa catálogo importado (não scraping)
- [ ] 3.10. **Verificar**: Bot mostra "📦 Produtos carregados do catálogo importado"
- [ ] 3.11. **Verificar**: Bot lista produtos numerados
- [ ] 3.12. Enviar número do produto (ex: `0`)
- [ ] 3.13. **Verificar**: Bot processa otimização
- [ ] 3.14. **Verificar**: Bot envia resultado da otimização

**Resultado Esperado**: ✅ WhatsApp funciona com catálogo importado

---

### 4. Teste de API REST (opcional, para desenvolvedores)

#### Endpoints:
```bash
# 1. Importar catálogo
POST http://localhost:8787/catalog/import
Body: multipart/form-data
  - user_id: "test_user"
  - shop_url: "https://shopee.com.br/totalmenteseu"
  - file_content: [bytes do arquivo]
  - file_name: "catalog.xlsx"

# 2. Listar catálogo
GET http://localhost:8787/catalog/list?user_id=test_user

# 3. Deletar catálogo
DELETE http://localhost:8787/catalog/delete?user_id=test_user
```

**Resultado Esperado**: ✅ Todos os endpoints respondem corretamente

---

### 5. Teste de Erros Controlados

#### 5.1. Arquivo Inválido
- [ ] Tentar importar arquivo .txt ou .pdf
- [ ] **Verificar**: Mensagem de erro clara (não traceback)
- [ ] **Verificar**: "Arquivo inválido. Por favor, envie XLSX ou CSV"

#### 5.2. Planilha Sem Produtos
- [ ] Importar planilha vazia ou sem coluna de nome
- [ ] **Verificar**: Mensagem de erro clara
- [ ] **Verificar**: "Nenhum produto válido encontrado no arquivo"

#### 5.3. Loja Sem Cache
- [ ] Tentar carregar loja nova (sem cache)
- [ ] **Verificar**: Não quebra
- [ ] **Verificar**: Mostra opção de importar

#### 5.4. Scraping Retornando 0
- [ ] Usar loja que retorna 0 produtos
- [ ] **Verificar**: Não quebra
- [ ] **Verificar**: Oferece importação de catálogo

**Resultado Esperado**: ✅ Todos os erros são tratados graciosamente

---

## 🎯 Critérios de Sucesso

Para considerar a Fase 6A **APROVADA**, todos os testes abaixo devem passar:

### Obrigatórios (Bloqueantes):
- ✅ Teste 1.1 a 1.22 - Fluxo completo no .exe
- ✅ Teste 2.1 a 2.13 - Cache funciona
- ✅ Teste 5.1 a 5.4 - Erros controlados

### Opcionais (Não-bloqueantes):
- ⏳ Teste 3 - WhatsApp (se Evolution API configurada)
- ⏳ Teste 4 - API REST (para desenvolvedores)

---

## 📝 Como Reportar Problemas

Se algum teste falhar, anote:

1. **Qual teste falhou** (número do teste)
2. **O que aconteceu** (comportamento observado)
3. **O que era esperado** (comportamento correto)
4. **Mensagem de erro** (se houver)
5. **Screenshot** (se possível)

Exemplo:
```
❌ Teste 1.11 FALHOU

Observado: Após upload, aparece erro "KeyError: 'name'"
Esperado: Deveria mostrar "✅ X produto(s) importado(s)"
Erro: Traceback completo no terminal
Screenshot: anexo
```

---

## 🚀 Após Aprovação

Quando todos os testes obrigatórios passarem:

1. ✅ Fase 6A está **COMPLETA**
2. ✅ .exe voltou a funcionar
3. ✅ WhatsApp funciona com catálogo
4. ⏳ Pode iniciar integração com Sentinela

---

## 📦 Arquivos Necessários para Teste

### Onde conseguir arquivo XLSX/CSV de teste:

**Opção 1: Shopee Seller Center (REAL)**
1. Acesse https://seller.shopee.com.br/
2. Vá em Produtos → Meus Produtos
3. Clique em Exportar
4. Baixe o arquivo

**Opção 2: Criar arquivo de teste (MOCK)**
Crie um arquivo Excel com estas colunas:

| Product Name | Price | Stock | SKU |
|--------------|-------|-------|-----|
| Mochila Rosa | 89.90 | 10 | MOCH-001 |
| Mochila Azul | 79.90 | 5 | MOCH-002 |
| Mochila Verde | 99.90 | 8 | MOCH-003 |

Salve como `catalog_test.xlsx`

---

## 🔍 Verificação Rápida

Antes de começar os testes, verifique:

- [ ] .exe está compilado e atualizado
- [ ] Arquivo XLSX/CSV de teste está pronto
- [ ] API Key do Google Gemini está configurada
- [ ] Banco de dados `data/catalog_cache.db` pode ser criado
- [ ] Pasta `data/` existe e tem permissão de escrita

---

**Data**: 26/04/2026  
**Versão**: Fase 6A (95% completa)  
**Testador**: [Seu nome]  
**Status**: ⏳ Aguardando testes
