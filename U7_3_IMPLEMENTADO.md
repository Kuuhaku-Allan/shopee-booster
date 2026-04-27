# ✅ U7.3 IMPLEMENTADO - Isolamento de backend_core via Subprocess

**Data:** 27/04/2026  
**Commit:** `4a46041`  
**Branch:** `feature/whatsapp-bot-core`

---

## 🎯 Problema Identificado

O Sentinela travava na **Etapa 1/6** ao tentar importar `backend_core`:

```
[SENTINELA] Etapa 1/6: importando backend_core.fetch_competitors_intercept...
[... NADA MAIS ...]
```

**Causa raiz:** `backend_core.py` é um módulo muito pesado que importa:
- `streamlit` (framework web completo)
- `pandas` (processamento de dados)
- `PIL` (processamento de imagens)
- `google.genai` (IA do Google)
- Carrega `.env` e configura variáveis globais
- Configura CUDA, ONNX Runtime, rembg

Quando executado dentro de um background task do FastAPI, o import travava ou demorava indefinidamente.

---

## ✅ Solução Implementada

### 1. Criado `shopee_core/competitor_service.py`

Serviço leve que **não importa `backend_core` diretamente**. Em vez disso, usa **subprocess isolado**:

```python
def fetch_competitors(keyword: str, timeout_seconds: int = 120) -> list:
    """
    Busca concorrentes via subprocess isolado.
    
    - Importa backend_core DENTRO do subprocess
    - Timeout REAL: subprocess.run(timeout=X) mata o processo
    - Isolamento completo: não afeta o FastAPI
    """
    code = r"""
import sys
import json
from backend_core import fetch_competitors_intercept

keyword = sys.argv[1]
result = fetch_competitors_intercept(keyword)
print(json.dumps(result, ensure_ascii=False))
"""
    
    result = subprocess.run(
        [sys.executable, "-c", code, keyword],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout_seconds,
    )
    
    # Parse e retorna resultados
    return json.loads(result.stdout or "[]")
```

### 2. Atualizado `api_server.py` → `_run_sentinel_bg()`

**Antes:**
```python
from backend_core import fetch_competitors_intercept

def fetch_with_timeout(keyword: str) -> list:
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fetch_competitors_intercept, keyword)
        return future.result(timeout=TIMEOUT_PER_KEYWORD)

concorrentes_raw = fetch_with_timeout(kw) or []
```

**Depois:**
```python
from shopee_core.competitor_service import fetch_competitors

# Não precisa mais de fetch_with_timeout!
# O fetch_competitors já tem timeout interno via subprocess

concorrentes_raw = fetch_competitors(kw, timeout_seconds=TIMEOUT_PER_KEYWORD) or []
```

### 3. Tratamento de Erros Específico

```python
try:
    concorrentes_raw = fetch_competitors(kw, timeout_seconds=90) or []
    
except TimeoutError:
    # Timeout real: processo foi morto após 90s
    log.error(f"[SENTINELA] Timeout na keyword={kw!r}")
    keywords_timeout.append(kw)
    
except RuntimeError as e:
    # Erro no scraping (Playwright, Shopee, etc.)
    log.error(f"[SENTINELA] Erro no scraping: {e}")
    keywords_com_erro.append(kw)
    
except Exception as e:
    # Erro inesperado
    log.error(f"[SENTINELA] Erro inesperado: {e}")
    keywords_com_erro.append(kw)
```

---

## 🚀 Vantagens da Solução

### 1. **Isolamento Completo**
- `backend_core` roda em processo Python separado
- Se travar, não afeta o FastAPI
- Cada keyword é executada em processo independente

### 2. **Timeout REAL**
- `subprocess.run(timeout=120)` mata o processo se exceder
- Não fica travado indefinidamente
- ThreadPoolExecutor não garantia isso (thread podia continuar presa)

### 3. **Sem Conflitos**
- Não há conflito de threads
- Não há deadlock
- Streamlit não tenta inicializar em contexto errado

### 4. **Logs Claros**
- Erros do subprocess aparecem no stderr
- Logs com prefixo `[COMPETITOR]` para diagnóstico
- Fácil de debugar

### 5. **Compatibilidade**
- Funciona em Windows, Linux, macOS
- Não depende de threading complexo
- Usa apenas biblioteca padrão do Python

---

## 📊 Resultado Esperado

Após a correção, os logs devem mostrar:

```
[SENTINELA] ════════════════════════════════════════════════════════
[SENTINELA] Início da execução: user=5511988600050@s.whatsapp.net
[SENTINELA] Etapa 1/6: importando competitor_service...
[SENTINELA] Etapa 1/6 OK: competitor_service importado
[SENTINELA] Etapa 2/6: lendo config...
[SENTINELA] Etapa 2/6 OK: shop_uid='...', username='totalmenteseu', keywords=3
[SENTINELA] Etapa 3/6: gerando janela_execucao...
[SENTINELA] Etapa 3/6 OK: janela=2026-04-27_14h
[SENTINELA] Etapa 4/6: salvando sessão running...
[SENTINELA] Etapa 4/6 OK: sessão running salva
[SENTINELA] Etapa 5/6: preparando estruturas de dados...
[SENTINELA] Etapa 5/6 OK: estruturas preparadas
[SENTINELA] Etapa 6/6: pronto para executar keywords
[SENTINELA] Etapa 6/6 OK: sistema pronto
[SENTINELA] Iniciando loop de 3 keywords...
[SENTINELA] ──────────────────────────────────────────────
[SENTINELA] Keyword 1/3: 'mochila roxa'
[COMPETITOR] Buscando concorrentes para: 'mochila roxa'
[COMPETITOR] Encontrados 10 concorrentes
[SENTINELA] Concorrentes encontrados: 10
[SENTINELA] Keyword 2/3: 'mochila escolar'
[COMPETITOR] Buscando concorrentes para: 'mochila escolar'
[COMPETITOR] Encontrados 10 concorrentes
[SENTINELA] Concorrentes encontrados: 10
[SENTINELA] Keyword 3/3: 'mochila infantil'
[COMPETITOR] Buscando concorrentes para: 'mochila infantil'
[COMPETITOR] Encontrados 10 concorrentes
[SENTINELA] Concorrentes encontrados: 10
[SENTINELA] Resumo enviado ao WhatsApp
[SENTINELA] Concluído: user=5511988600050@s.whatsapp.net shop_uid=... kws=3
[SENTINELA] ════════════════════════════════════════════════════════
```

---

## 🧪 Como Testar

### 1. Reiniciar o servidor (sem --reload)

```powershell
# Parar processos antigos
Get-Process -Name "*python*" | Stop-Process -Force

# Subir servidor
.\venv\Scripts\python.exe -m uvicorn api_server:app --host 0.0.0.0 --port 8787 --log-level debug
```

### 2. Testar no WhatsApp

```
/sentinela rodar
```

### 3. Verificar progresso em tempo real

Em outro terminal:
```
/status
```

Deve mostrar:
```
Sentinela em execução
Loja: totalmenteseu
Progresso: 1/3
Keyword atual: mochila roxa
Tempo decorrido: 2 min
```

### 4. Verificar logs do servidor

Os logs devem mostrar todas as 6 etapas completando com sucesso, seguidas do loop de keywords.

---

## 📝 Arquivos Modificados

### Criados:
- `shopee_core/competitor_service.py` - Serviço isolado de busca de concorrentes

### Modificados:
- `api_server.py` - Função `_run_sentinel_bg()` linha ~1040-1400
  - Removido import direto de `backend_core`
  - Removido `ThreadPoolExecutor` e `fetch_with_timeout()`
  - Adicionado import de `competitor_service`
  - Atualizado tratamento de exceções (TimeoutError, RuntimeError)

---

## 🎯 Status

- ✅ **U7.1:** Observabilidade e estabilidade implementada
- ✅ **U7.2:** Timing de salvamento de sessão corrigido
- ✅ **U7.3:** Isolamento de backend_core via subprocess implementado
- 🧪 **Próximo:** Testar `/sentinela rodar` e verificar se passa da Etapa 1

---

## 📚 Referências

- Commit: `4a46041`
- Branch: `feature/whatsapp-bot-core`
- Documentos relacionados:
  - `DIAGNOSTICO_FINAL_U7_3.md` - Diagnóstico completo do problema
  - `CORRECOES_U7_1_SENTINELA.md` - Correções de observabilidade
  - `U7_2_IMPLEMENTADO.md` - Correção de timing de sessão

---

**Implementado por:** Kiro AI  
**Revisado por:** GPT (via usuário)  
**Data:** 27/04/2026 14:30 BRT
