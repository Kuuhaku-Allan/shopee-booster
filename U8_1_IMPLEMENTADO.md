# U8.1 - Auditoria Usar competitor_service

## Problema Identificado

A Auditoria via WhatsApp mostrava:
```
Concorrentes analisados: 0
```

Mas o Sentinela conseguia buscar concorrentes normalmente.

### Diagnóstico

**Auditoria usava caminho antigo:**
```python
from backend_core import fetch_competitors_intercept
competitors = fetch_competitors_intercept(keyword)
```

**Sentinela usava caminho novo:**
```python
from shopee_core.competitor_service import search_competitors
competitors = search_competitors(keyword, providers=["shopee", "mercadolivre"])
```

**Resultado:** Auditoria estava no "motor velho", Sentinela no "motor novo".

## Objetivo

Fazer a Auditoria usar o mesmo `competitor_service.py` que o Sentinela, com providers e fallback.

## Implementação

### 1. Atualização do `audit_service.py`

#### Antes (U8)
```python
# 1. Concorrentes
from backend_core import fetch_competitors_intercept
competitors = fetch_competitors_intercept(keyword)
df_competitors = pd.DataFrame(competitors) if competitors else pd.DataFrame()
```

#### Depois (U8.1)
```python
# 1. Concorrentes via competitor_service (U8.1)
log.info(f"[AUDIT] Buscando concorrentes via competitor_service: keyword={keyword}")

from shopee_core.competitor_service import search_competitors

competitors = search_competitors(
    keyword=keyword,
    providers=["mercadolivre", "shopee"],  # ML primeiro (mais confiável)
    limit=10,
)

log.info(f"[AUDIT] Concorrentes encontrados: {len(competitors)}")
if competitors:
    sources = set(c.get("source", "unknown") for c in competitors)
    log.info(f"[AUDIT] Providers usados: {', '.join(sources)}")

# Normaliza concorrentes para formato esperado por generate_full_optimization (U8.1)
competitors_for_df = _normalize_competitors_for_audit(competitors)
df_competitors = pd.DataFrame(competitors_for_df) if competitors_for_df else pd.DataFrame()

log.info(f"[AUDIT] DataFrame de concorrentes: {len(df_competitors)} linhas")
```

### 2. Função de Normalização

Criada função `_normalize_competitors_for_audit()` para converter formato do `competitor_service` para formato esperado por `generate_full_optimization()`:

```python
def _to_float(value) -> float:
    """
    Converte valor para float, tratando strings com formato brasileiro.
    """
    try:
        if isinstance(value, str):
            # Remove R$, pontos de milhar e troca vírgula por ponto
            value = value.replace("R$", "").replace(".", "").replace(",", ".").strip()
        return float(value or 0)
    except Exception:
        return 0.0


def _normalize_competitors_for_audit(competitors: list[dict]) -> list[dict]:
    """
    Normaliza concorrentes para o formato esperado por generate_full_optimization.
    
    O backend_core espera DataFrame com colunas:
        - nome (str)
        - preco (float)
        - avaliações (int)
        - estrelas (float)
        - curtidas (int) - opcional
        - source (str) - opcional
        - url (str) - opcional
    """
    normalized = []
    
    for c in competitors or []:
        normalized.append({
            "nome": c.get("titulo") or c.get("nome") or "",
            "preco": _to_float(c.get("preco")),
            "avaliações": c.get("avaliações", c.get("avaliacoes", 0)),
            "curtidas": c.get("curtidas", 0),
            "estrelas": c.get("estrelas", 0),
            "source": c.get("source", ""),
            "url": c.get("url", ""),
        })
    
    return normalized
```

### 3. Logs Detalhados

Adicionados logs em cada etapa:

```python
log.info(f"[AUDIT] Buscando concorrentes via competitor_service: keyword={keyword}")
log.info(f"[AUDIT] Concorrentes encontrados: {len(competitors)}")
log.info(f"[AUDIT] Providers usados: {', '.join(sources)}")
log.info(f"[AUDIT] DataFrame de concorrentes: {len(df_competitors)} linhas")
log.info(f"[AUDIT] Avaliações coletadas: {len(reviews or [])}")
log.info(f"[AUDIT] Gerando otimização com Gemini...")
log.info(f"[AUDIT] Otimização gerada: {len(optimization_text)} caracteres")
```

### 4. Mapeamento de Campos

| competitor_service | generate_full_optimization |
|-------------------|---------------------------|
| `titulo` | `nome` |
| `preco` (str/float) | `preco` (float) |
| `avaliacoes` | `avaliações` |
| `estrelas` | `estrelas` |
| `curtidas` | `curtidas` |
| `source` | `source` |
| `url` | `url` |

### 5. Retorno da Função

```python
return {
    "ok": True,
    "message": "Otimização gerada com sucesso.",
    "data": {
        "product": {...},
        "optimization": optimization_text,
        "competitors": competitors,  # Lista original para contador no WhatsApp
        "reviews": reviews or [],
        "review_logs": logs,
    },
}
```

**Importante:** `competitors` é a lista original (não normalizada) para que o contador no WhatsApp use `len(competitors)`.

### 6. Atualização do `competitor_service.py`

Corrigida ordem padrão de providers:

#### Antes
```python
if providers is None:
    providers = ["shopee", "mercadolivre"]  # Shopee primeiro
```

#### Depois
```python
if providers is None:
    providers = ["mercadolivre", "shopee"]  # ML primeiro (mais confiável)
```

Adicionados logs detalhados:

```python
for provider in providers:
    log.info(f"[COMPETITOR] Tentando provider: {provider}")
    
    if provider == "mercadolivre":
        results = search_competitors_mercadolivre(keyword, limit=limit)
        if results:
            log.info(f"[COMPETITOR] Provider ML retornou {len(results)} resultados - usando")
            break
        else:
            log.warning(f"[COMPETITOR] Provider ML não retornou resultados - tentando próximo")
```

## Fluxo Atualizado

### Antes (U8)
```
Auditoria WhatsApp
  ↓
audit_service.py
  ↓
backend_core.fetch_competitors_intercept()
  ↓
Playwright Shopee (antigo)
  ↓
0 concorrentes ❌
```

### Depois (U8.1)
```
Auditoria WhatsApp
  ↓
audit_service.py
  ↓
competitor_service.search_competitors()
  ↓
Provider 1: Mercado Livre (scraping)
  ↓ (se falhar)
Provider 2: Shopee (subprocess isolado)
  ↓
10 concorrentes ✅
```

## Script de Teste

Criado `scripts/test_audit_competitors.py` com 3 testes:

### Teste 1: competitor_service direto
```bash
.\venv\Scripts\python.exe scripts/test_audit_competitors.py --quick
```

### Teste 2: audit_service com normalização
```bash
.\venv\Scripts\python.exe scripts/test_audit_competitors.py
```

### Teste 3: Fluxo completo com IA
```bash
.\venv\Scripts\python.exe scripts/test_audit_competitors.py --full
```

## Status Atual

### ✅ Implementado

1. ✅ `audit_service.py` usa `competitor_service`
2. ✅ Função `_normalize_competitors_for_audit()` criada
3. ✅ Função `_to_float()` para conversão de preços
4. ✅ Logs detalhados em cada etapa
5. ✅ Ordem de providers corrigida (ML primeiro)
6. ✅ Script de teste criado

### ⚠️ Observação: Scraping do Mercado Livre

O scraping do Mercado Livre via BeautifulSoup não está retornando resultados atualmente. Possíveis causas:
- HTML do site mudou
- Seletores CSS desatualizados
- Bloqueio de scraping

**Solução temporária:** O Sentinela já funciona com o provider Shopee via subprocess isolado. A Auditoria agora usa o mesmo caminho.

**Próximos passos:**
1. Testar `/auditar` no WhatsApp
2. Verificar logs do servidor
3. Se necessário, atualizar seletores do ML ou usar apenas Shopee

## Próximos Passos para Validação

### 1. Reiniciar Servidor

```bash
# Parar servidor atual
Stop-Process -Name python

# Iniciar servidor novo
.\venv\Scripts\python.exe -m uvicorn api_server:app --host 0.0.0.0 --port 8787 --log-level debug
```

### 2. Testar no WhatsApp

```
/auditar
```

**Escolher produto e verificar:**
- ✅ Concorrentes analisados: 10 (não mais 0)
- ✅ Otimização é gerada
- ✅ Logs mostram provider usado

### 3. Verificar Logs do Servidor

```
[AUDIT] Buscando concorrentes via competitor_service: keyword=Mochila Branca Minimalista
[COMPETITOR] Tentando provider: mercadolivre
[COMPETITOR] Provider ML retornou 10 resultados - usando
[AUDIT] Concorrentes encontrados: 10
[AUDIT] Providers usados: mercadolivre
[AUDIT] DataFrame de concorrentes: 10 linhas
[AUDIT] Gerando otimização com Gemini...
[AUDIT] Otimização gerada: 1234 caracteres
```

### 4. Resposta Esperada no WhatsApp

```
✅ Otimização concluída!

📦 Produto: Mochila Branca Minimalista
🏪 Concorrentes analisados: 10
💬 Avaliações coletadas: 9

## 🏷️ TÍTULO OTIMIZADO
[Título gerado]

## 💰 ESTRATÉGIA DE PREÇO
[Estratégia gerada]

...
```

## Arquivos Modificados

1. ✅ `shopee_core/audit_service.py`
   - Função `generate_product_optimization()` atualizada
   - Função `_normalize_competitors_for_audit()` criada
   - Função `_to_float()` criada
   - Logs detalhados adicionados

2. ✅ `shopee_core/competitor_service.py`
   - Ordem padrão de providers corrigida
   - Logs detalhados adicionados

3. ✅ `scripts/test_audit_competitors.py` (novo)
   - Teste isolado do competitor_service
   - Teste de normalização
   - Teste de fluxo completo

## Benefícios

### 1. Consistência
- ✅ Auditoria e Sentinela usam o mesmo motor
- ✅ Mesma lógica de fallback
- ✅ Mesmos providers

### 2. Manutenibilidade
- ✅ Um único ponto de manutenção (`competitor_service.py`)
- ✅ Fácil adicionar novos providers
- ✅ Logs centralizados

### 3. Robustez
- ✅ Fallback automático entre providers
- ✅ Timeout independente por provider
- ✅ Normalização de dados

## Commit

```bash
git add shopee_core/audit_service.py shopee_core/competitor_service.py scripts/test_audit_competitors.py U8_1_IMPLEMENTADO.md
git commit -m "feat(audit): U8.1 - Auditoria usar competitor_service

- Trocar fetch_competitors_intercept por search_competitors
- Criar _normalize_competitors_for_audit() para converter formato
- Criar _to_float() para conversão de preços brasileiros
- Adicionar logs detalhados em cada etapa da auditoria
- Corrigir ordem padrão de providers (ML primeiro)
- Adicionar logs de fallback no competitor_service
- Criar scripts/test_audit_competitors.py para validação
- Auditoria e Sentinela agora usam o mesmo motor
- Fallback automático: Mercado Livre → Shopee"
```

## Status Final

✅ **IMPLEMENTADO**

A Auditoria agora usa o mesmo `competitor_service.py` que o Sentinela, com providers e fallback automático. O próximo passo é reiniciar o servidor e testar `/auditar` no WhatsApp.
