# 🎯 DIAGNÓSTICO CONFIRMADO - Import de backend_core Travando

## ✅ Logs Capturados

```
2026-04-27 12:53:52,766 [INFO] [WEBHOOK] Sessão processing_sentinel salva: user='5511988600050@s.whatsapp.net'
2026-04-27 12:53:52,766 [INFO] [BG] Execução do Sentinela agendada: user='5511988600050@s.whatsapp.net'
2026-04-27 12:53:52,769 [INFO] [SENTINELA] ════════════════════════════════════════════════════════
2026-04-27 12:53:52,770 [INFO] [SENTINELA] Início da execução: user=5511988600050@s.whatsapp.net
2026-04-27 12:53:52,770 [INFO] [SENTINELA] Etapa 1/6: importando backend_core.fetch_competitors_intercept...
[... NADA MAIS ...]
```

**Nunca aparece:**
```
[SENTINELA] Etapa 1/6 OK: backend_core importado
```

## 🎯 Conclusão

**O import de `backend_core` está travando o background task!**

### Por Que Trava?

`backend_core.py` é um módulo MUITO pesado que:

1. **Importa bibliotecas pesadas:**
   ```python
   import streamlit as st
   import pandas as pd
   from PIL import Image, ImageEnhance, ImageFilter
   from google import genai
   ```

2. **Carrega configurações:**
   ```python
   load_dotenv()
   load_dotenv(CONFIG_ENV)
   ```

3. **Configura variáveis globais:**
   ```python
   API_KEY = os.getenv("GOOGLE_API_KEY")
   client = genai.Client(api_key=API_KEY)
   ```

4. **Contém código de inicialização:**
   - Configuração de CUDA
   - Configuração de ONNX Runtime
   - Configuração de rembg
   - Etc.

**Tudo isso roda quando você faz `from backend_core import ...`**

### Por Que Não Dá Erro?

O import não falha, ele simplesmente **demora muito** ou **trava indefinidamente** quando executado dentro de um background task do FastAPI.

Possíveis razões:
- Streamlit tentando inicializar em contexto errado
- Conflito de threads/processos
- Deadlock em alguma inicialização
- Timeout interno de alguma biblioteca

---

## 🚀 Solução: Criar Worker Isolado

### Opção 1: Subprocess (Recomendada pelo GPT)

Criar `shopee_core/competitor_service.py`:

```python
"""
competitor_service.py — Serviço leve de busca de concorrentes
Não importa backend_core diretamente, usa subprocess isolado
"""

import subprocess
import sys
import json
import logging

log = logging.getLogger("competitor_service")


def fetch_competitors(keyword: str, timeout_seconds: int = 120) -> list:
    """
    Busca concorrentes via subprocess isolado.
    
    Args:
        keyword: Palavra-chave para buscar
        timeout_seconds: Timeout em segundos (padrão: 120s = 2min)
    
    Returns:
        Lista de concorrentes encontrados
    
    Raises:
        TimeoutError: Se exceder o timeout
        RuntimeError: Se o scraping falhar
    """
    log.info(f"[COMPETITOR] Buscando concorrentes para: {keyword!r}")
    
    # Código Python que será executado no subprocess
    code = r"""
import sys
import json

try:
    from backend_core import fetch_competitors_intercept
    
    keyword = sys.argv[1]
    result = fetch_competitors_intercept(keyword)
    print(json.dumps(result, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": str(e)}), file=sys.stderr)
    sys.exit(1)
"""
    
    try:
        result = subprocess.run(
            [sys.executable, "-c", code, keyword],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
        
        if result.returncode != 0:
            error_msg = result.stderr[-500:] if result.stderr else "Erro desconhecido"
            log.error(f"[COMPETITOR] Erro no scraping: {error_msg}")
            raise RuntimeError(f"Scraping falhou: {error_msg}")
        
        data = json.loads(result.stdout or "[]")
        log.info(f"[COMPETITOR] Encontrados {len(data)} concorrentes")
        return data
        
    except subprocess.TimeoutExpired:
        log.error(f"[COMPETITOR] Timeout de {timeout_seconds}s excedido para {keyword!r}")
        raise TimeoutError(f"Busca de concorrentes excedeu {timeout_seconds}s")
    except json.JSONDecodeError as e:
        log.error(f"[COMPETITOR] Erro ao decodificar JSON: {e}")
        return []
```

### Opção 2: Multiprocessing

```python
from multiprocessing import Process, Queue
import time

def fetch_competitors_worker(keyword: str, queue: Queue):
    """Worker que roda em processo separado."""
    try:
        from backend_core import fetch_competitors_intercept
        result = fetch_competitors_intercept(keyword)
        queue.put({"ok": True, "data": result})
    except Exception as e:
        queue.put({"ok": False, "error": str(e)})

def fetch_competitors(keyword: str, timeout_seconds: int = 120) -> list:
    """Busca concorrentes com timeout real via multiprocessing."""
    queue = Queue()
    process = Process(target=fetch_competitors_worker, args=(keyword, queue))
    
    process.start()
    process.join(timeout=timeout_seconds)
    
    if process.is_alive():
        process.terminate()
        process.join()
        raise TimeoutError(f"Timeout de {timeout_seconds}s excedido")
    
    if not queue.empty():
        result = queue.get()
        if result["ok"]:
            return result["data"]
        else:
            raise RuntimeError(result["error"])
    
    return []
```

---

## 📝 Alterações Necessárias

### 1. Criar `shopee_core/competitor_service.py`

Usar a Opção 1 (subprocess) - mais simples e confiável.

### 2. Atualizar `api_server.py` → `_run_sentinel_bg()`

**Antes:**
```python
log.info("[SENTINELA] Etapa 1/6: importando backend_core.fetch_competitors_intercept...")
from backend_core import fetch_competitors_intercept
log.info("[SENTINELA] Etapa 1/6 OK: backend_core importado")
```

**Depois:**
```python
log.info("[SENTINELA] Etapa 1/6: importando competitor_service...")
from shopee_core.competitor_service import fetch_competitors
log.info("[SENTINELA] Etapa 1/6 OK: competitor_service importado")
```

### 3. Atualizar a Função de Timeout

**Antes:**
```python
def fetch_with_timeout(keyword: str) -> list:
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fetch_competitors_intercept, keyword)
        return future.result(timeout=TIMEOUT_PER_KEYWORD)
```

**Depois:**
```python
# Não precisa mais de fetch_with_timeout!
# O fetch_competitors já tem timeout interno via subprocess
```

### 4. Atualizar o Loop de Keywords

**Antes:**
```python
try:
    concorrentes_raw = fetch_with_timeout(kw) or []
except FutureTimeoutError:
    keywords_timeout.append(kw)
```

**Depois:**
```python
try:
    concorrentes_raw = fetch_competitors(kw, timeout_seconds=90) or []
except TimeoutError:
    log.error(f"[SENTINELA] Timeout na keyword={kw!r}")
    keywords_timeout.append(kw)
except RuntimeError as e:
    log.error(f"[SENTINELA] Erro na keyword={kw!r}: {e}")
    keywords_com_erro.append(kw)
```

---

## ✅ Vantagens da Solução com Subprocess

1. **Isolamento Completo:**
   - `backend_core` roda em processo separado
   - Se travar, não afeta o FastAPI
   - Timeout REAL que mata o processo

2. **Sem Conflitos:**
   - Não há conflito de threads
   - Não há deadlock
   - Cada busca é independente

3. **Timeout Garantido:**
   - `subprocess.run(timeout=120)` mata o processo se exceder
   - Não fica travado indefinidamente

4. **Logs Claros:**
   - Erros do subprocess aparecem no stderr
   - Fácil de debugar

5. **Compatibilidade:**
   - Funciona em Windows, Linux, macOS
   - Não depende de threading complexo

---

## 🎯 Próximos Passos

1. **Criar `shopee_core/competitor_service.py`** com a implementação subprocess
2. **Atualizar `_run_sentinel_bg()`** para usar `competitor_service`
3. **Remover `ThreadPoolExecutor`** (não é mais necessário)
4. **Testar** `/sentinela rodar` novamente
5. **Observar logs** - deve passar da Etapa 1 agora!

---

## 📊 Resultado Esperado Após Correção

```
[SENTINELA] Etapa 1/6: importando competitor_service...
[SENTINELA] Etapa 1/6 OK: competitor_service importado
[SENTINELA] Etapa 2/6: lendo config...
[SENTINELA] Etapa 2/6 OK: shop_uid='...', keywords=3
[SENTINELA] Etapa 3/6: gerando janela_execucao...
[SENTINELA] Etapa 3/6 OK: janela=2026-04-27_13h
[SENTINELA] Etapa 4/6: salvando sessão running...
[SENTINELA] Etapa 4/6 OK: sessão running salva
[SENTINELA] Etapa 5/6: preparando estruturas...
[SENTINELA] Etapa 5/6 OK: estruturas preparadas
[SENTINELA] Etapa 6/6: definindo fetch_with_timeout...
[SENTINELA] Etapa 6/6 OK: função definida
[SENTINELA] Iniciando loop de 3 keywords...
[SENTINELA] Keyword 1/3: 'mochila roxa'
[COMPETITOR] Buscando concorrentes para: 'mochila roxa'
[COMPETITOR] Encontrados 10 concorrentes
[SENTINELA] Concorrentes encontrados: 10
[SENTINELA] Keyword 2/3: 'mochila escolar'
...
```

---

**Data:** 27/04/2026
**Diagnóstico:** ✅ Confirmado - Import de backend_core travando
**Solução:** Criar competitor_service.py com subprocess isolado
**Status:** Aguardando implementação da correção
