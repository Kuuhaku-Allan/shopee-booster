# U8.2 - Status: Unificação de Busca de Concorrentes

## ✅ Implementação Concluída

### Código Atualizado

1. ✅ **Função `search_competitors_safe()` criada** em `competitor_service.py`
   - Mercado Livre primeiro
   - Shopee como fallback
   - Logs detalhados
   - Nunca trava

2. ✅ **Auditoria atualizada** (`audit_service.py`)
   - Usa `search_competitors_safe()`
   - Normalização de dados
   - Logs detalhados

3. ✅ **Sentinela atualizado** (`api_server.py`)
   - Usa `search_competitors_safe()`
   - Formato unificado
   - Logs detalhados

4. ✅ **Script de teste criado** (`scripts/test_competitors_runtime.py`)
   - Testa 4 keywords
   - Mostra provider usado
   - Top 3 produtos

## ❌ Problema Identificado: Providers Não Funcionam

### Teste Executado

```bash
.\venv\Scripts\python.exe scripts/test_competitors_runtime.py
```

**Resultado:**
```
❌ Mochila Branca Minimalista: 0 concorrentes
❌ mochila roxa: 0 concorrentes
❌ mochila azul: 0 concorrentes
❌ mochila rosa: 0 concorrentes

❌ TODOS OS TESTES FALHARAM
```

### Diagnóstico

#### 1. Mercado Livre (BeautifulSoup)
```
[COMPETITOR] Provider ML erro inesperado: The markup you provided was rejected by the parser
```

**Causa:** O HTML do Mercado Livre mudou ou o parser não consegue processar.

**Possíveis soluções:**
- Atualizar seletores CSS
- Usar parser diferente (`lxml` em vez de `html.parser`)
- Usar API oficial do ML (se disponível)

#### 2. Shopee (Playwright via subprocess)
```
[COMPETITOR] Provider Shopee não retornou resultados
```

**Causa:** O `fetch_competitors_intercept` do `backend_core.py` não está funcionando via subprocess.

**Possíveis causas:**
- Playwright não instalado no ambiente
- Shopee bloqueando scraping
- Timeout muito curto
- Erro no subprocess

## Situação Atual

### Código
- ✅ Auditoria e Sentinela usam a mesma função
- ✅ Logs detalhados implementados
- ✅ Fallback automático implementado
- ✅ Normalização de dados implementada

### Runtime
- ❌ Mercado Livre não retorna resultados
- ❌ Shopee não retorna resultados
- ❌ Nenhum provider funciona atualmente

## Próximos Passos

### Opção 1: Corrigir Mercado Livre (Recomendado)

O scraping do ML é mais simples e confiável que Playwright.

**Tarefas:**
1. Atualizar seletores CSS do ML
2. Testar com parser `lxml`
3. Adicionar fallback para diferentes estruturas HTML
4. Validar com múltiplas keywords

**Script de teste:**
```python
import requests
from bs4 import BeautifulSoup

url = "https://lista.mercadolivre.com.br/mochila"
response = requests.get(url, headers={...})
soup = BeautifulSoup(response.text, 'lxml')  # Tentar lxml

# Inspecionar estrutura
print(soup.prettify()[:1000])
```

### Opção 2: Corrigir Shopee Playwright

**Tarefas:**
1. Verificar se Playwright está instalado
2. Testar `fetch_competitors_intercept` diretamente
3. Aumentar timeout
4. Adicionar logs detalhados no subprocess

**Script de teste:**
```python
from backend_core import fetch_competitors_intercept

competitors = fetch_competitors_intercept("mochila")
print(f"Encontrados: {len(competitors)}")
```

### Opção 3: Provider Mock para Desenvolvimento

Criar provider mock que retorna dados simulados para permitir desenvolvimento/teste do resto do sistema.

**Implementação:**
```python
def search_competitors_mock(keyword: str, limit: int = 10) -> List[Dict]:
    """Provider mock para desenvolvimento"""
    return [
        {
            "ranking": i,
            "titulo": f"Produto {i} - {keyword}",
            "preco": 50.0 + (i * 5),
            "loja": "Loja Teste",
            "url": f"https://example.com/produto-{i}",
            "item_id": f"MOCK{i}",
            "shop_id": "mock_shop",
            "source": "mock",
            "keyword": keyword,
            "is_new": False,
        }
        for i in range(1, limit + 1)
    ]
```

## Recomendação

**Prioridade 1:** Corrigir Mercado Livre
- Mais simples que Playwright
- Mais confiável
- Não precisa de browser

**Prioridade 2:** Provider Mock
- Permite testar resto do sistema
- Desenvolvimento não fica bloqueado
- Pode ser removido depois

**Prioridade 3:** Corrigir Shopee
- Mais complexo (Playwright)
- Menos confiável (bloqueios)
- Pode ser fallback depois

## Arquivos Modificados

1. ✅ `shopee_core/competitor_service.py`
   - Função `search_competitors_safe()` adicionada
   - Logs detalhados

2. ✅ `shopee_core/audit_service.py`
   - Usa `search_competitors_safe()`

3. ✅ `api_server.py`
   - Sentinela usa `search_competitors_safe()`

4. ✅ `scripts/test_competitors_runtime.py` (novo)
   - Teste de runtime

## Commit Pendente

```bash
git add shopee_core/competitor_service.py shopee_core/audit_service.py api_server.py scripts/test_competitors_runtime.py U8_2_STATUS.md
git commit -m "feat(competitor): U8.2 - Unificar busca de concorrentes

- Criar search_competitors_safe() como função unificada
- Auditoria usa search_competitors_safe()
- Sentinela usa search_competitors_safe()
- Mercado Livre primeiro, Shopee fallback
- Logs detalhados em cada tentativa
- Criar scripts/test_competitors_runtime.py
- NOTA: Providers não funcionam atualmente (ML parser error, Shopee sem resultados)
- Próximo passo: Corrigir scraping do Mercado Livre ou adicionar provider mock"
```

## Status Final

✅ **Código unificado e pronto**  
❌ **Providers não funcionam em runtime**  
⏳ **Aguardando correção de providers ou implementação de mock**

**Não adianta testar /auditar ou /sentinela rodar no WhatsApp até que pelo menos um provider funcione.**
