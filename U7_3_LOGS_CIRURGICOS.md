# ✅ U7.3 Implementado - Logs Cirúrgicos para Diagnóstico

## 🎯 Objetivo

Identificar EXATAMENTE onde o background task do Sentinela está travando.

## 🔍 Problema Atual

- ✅ `/status` funciona perfeitamente (U7.2)
- ❌ Background task trava após `[SENTINELA] Início da execução`
- ❌ Nunca chega em `[SENTINELA] Status atualizado para 'running'`
- ❌ Nenhuma keyword processada

**Suspeita principal:** Import de `backend_core` travando

## ✅ Correções Implementadas

### 1. Logs Cirúrgicos em 6 Etapas

```python
log.info("[SENTINELA] Etapa 1/6: importando backend_core.fetch_competitors_intercept...")
from backend_core import fetch_competitors_intercept
log.info("[SENTINELA] Etapa 1/6 OK: backend_core importado")

log.info("[SENTINELA] Etapa 2/6: lendo config...")
# ... leitura de config ...
log.info(f"[SENTINELA] Etapa 2/6 OK: shop_uid={shop_uid!r}, keywords={total_keywords}")

log.info("[SENTINELA] Etapa 3/6: gerando janela_execucao...")
janela_execucao = generate_janela_execucao()
log.info(f"[SENTINELA] Etapa 3/6 OK: janela={janela_execucao}")

log.info("[SENTINELA] Etapa 4/6: salvando sessão running...")
save_session(...)
log.info("[SENTINELA] Etapa 4/6 OK: sessão running salva")

log.info("[SENTINELA] Etapa 5/6: preparando estruturas de dados...")
# ... preparação ...
log.info("[SENTINELA] Etapa 5/6 OK: estruturas preparadas")

log.info("[SENTINELA] Etapa 6/6: definindo fetch_with_timeout...")
def fetch_with_timeout(...): ...
log.info("[SENTINELA] Etapa 6/6 OK: função definida")

log.info(f"[SENTINELA] Iniciando loop de {total_keywords} keywords...")
```

### 2. BaseException em Vez de Exception

```python
except BaseException as e:
    log.error(f"[SENTINELA] ❌ ERRO FATAL: {type(e).__name__}: {e}")
    log.error(f"[SENTINELA] Traceback completo:")
    log.error(traceback.format_exc())
```

**Captura:**
- `Exception` (erros normais)
- `KeyboardInterrupt` (Ctrl+C)
- `SystemExit` (sys.exit())
- Outros travamentos

### 3. Mensagem de Erro Detalhada ao Usuário

```python
evo_send_text(
    user_id=user_id,
    text=(
        f"❌ *O Sentinela travou antes de buscar concorrentes.*\n\n"
        f"Erro: {type(e).__name__}\n\n"
        f"Veja os logs do servidor para mais detalhes.\n"
        f"Tente novamente com */sentinela rodar*."
    ),
)
```

### 4. Logs Detalhados no Loop de Keywords

```python
for idx, kw in enumerate(keywords, 1):
    log.info(f"[SENTINELA] ──────────────────────────────────────────────")
    log.info(f"[SENTINELA] Keyword {idx}/{total_keywords}: {kw!r}")
    log.info(f"[SENTINELA] Salvando progresso antes da keyword {idx}...")
    # ...
```

---

## 🧪 Como Testar

### 1. Enviar no WhatsApp

```
/sentinela rodar
```

### 2. Observar Logs do Servidor

**Logs esperados (se tudo funcionar):**
```
[SENTINELA] ════════════════════════════════════════════════════
[SENTINELA] Início da execução: user=5511988600050@s.whatsapp.net
[SENTINELA] Etapa 1/6: importando backend_core.fetch_competitors_intercept...
[SENTINELA] Etapa 1/6 OK: backend_core importado
[SENTINELA] Etapa 2/6: lendo config...
[SENTINELA] Etapa 2/6 OK: shop_uid='...', username='totalmenteseu', keywords=3
[SENTINELA] Etapa 3/6: gerando janela_execucao...
[SENTINELA] Etapa 3/6 OK: janela=2026-04-27_13h
[SENTINELA] Etapa 4/6: salvando sessão running...
[SENTINELA] Etapa 4/6 OK: sessão running salva
[SENTINELA] Etapa 5/6: preparando estruturas de dados...
[SENTINELA] Etapa 5/6 OK: estruturas preparadas
[SENTINELA] Etapa 6/6: definindo fetch_with_timeout...
[SENTINELA] Etapa 6/6 OK: função definida
[SENTINELA] Iniciando loop de 3 keywords...
[SENTINELA] ──────────────────────────────────────────────
[SENTINELA] Keyword 1/3: 'mochila roxa'
[SENTINELA] Salvando progresso antes da keyword 1...
```

**Se travar na Etapa 1:**
```
[SENTINELA] Início da execução: user=...
[SENTINELA] Etapa 1/6: importando backend_core.fetch_competitors_intercept...
[... NADA MAIS ...]
```

**Conclusão:** Import de `backend_core` está travando!

**Se travar na Etapa 3:**
```
[SENTINELA] Etapa 2/6 OK: ...
[SENTINELA] Etapa 3/6: gerando janela_execucao...
[... NADA MAIS ...]
```

**Conclusão:** `generate_janela_execucao()` está travando!

---

## 📊 Diagnóstico por Etapa

### Se Parar na Etapa 1/6 (Import)

**Causa:** `backend_core.py` é muito pesado
- Importa: streamlit, pandas, PIL, google.genai
- Carrega .env
- Configura variáveis globais

**Solução:**
1. Criar `shopee_core/competitor_service.py` leve
2. Mover apenas `fetch_competitors_intercept` para lá
3. Não importar `backend_core` no Sentinela

### Se Parar na Etapa 3/6 (Janela)

**Causa:** `generate_janela_execucao()` pode estar fazendo I/O

**Solução:**
- Verificar implementação da função
- Simplificar geração de janela

### Se Parar na Etapa 4/6 (Save Session)

**Causa:** `save_session()` pode estar travando no SQLite

**Solução:**
- Verificar locks no banco de dados
- Adicionar timeout no SQLite

### Se Parar na Etapa 6/6 (Fetch Timeout)

**Causa:** Definição da função `fetch_with_timeout` travando

**Solução:**
- Mover definição para fora do try
- Simplificar a função

### Se Chegar no Loop mas Travar na Primeira Keyword

**Causa:** `fetch_competitors_intercept()` travando

**Solução:**
- Usar subprocess em vez de ThreadPoolExecutor
- Timeout real que mata o processo

---

## 🔗 Próximos Passos (Baseado no Diagnóstico)

### Cenário A: Trava na Etapa 1 (Import)

**Criar `shopee_core/competitor_service.py`:**
```python
"""
competitor_service.py — Serviço leve de busca de concorrentes
Não depende de backend_core pesado
"""

def fetch_competitors(keyword: str) -> list:
    """Busca concorrentes via subprocess isolado."""
    import subprocess
    import sys
    import json
    
    code = r"""
import sys, json
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
        timeout=120,  # 2 minutos
    )
    
    if result.returncode != 0:
        raise RuntimeError(f"Erro no scraping: {result.stderr[-500:]}")
    
    return json.loads(result.stdout or "[]")
```

**No `_run_sentinel_bg`:**
```python
from shopee_core.competitor_service import fetch_competitors

# Em vez de:
# from backend_core import fetch_competitors_intercept
```

### Cenário B: Trava em Outra Etapa

Aguardar logs para diagnóstico específico.

---

## 📦 Commit Realizado

**Commit:** `4d2e49a`
**Branch:** `feature/whatsapp-bot-core`
**Mensagem:** feat(U7.3): Adiciona logs cirúrgicos para diagnóstico do travamento

**Link:** https://github.com/Kuuhaku-Allan/shopee-booster/commit/4d2e49a

---

## ✅ Checklist de Teste

- [ ] 1. Servidor rodando em `0.0.0.0:8787`
- [ ] 2. `/sentinela rodar` enviado no WhatsApp
- [ ] 3. Observar logs do servidor
- [ ] 4. Identificar em qual etapa trava
- [ ] 5. Anotar última etapa que apareceu
- [ ] 6. Compartilhar logs com GPT

---

## 🎯 Resultado Esperado

**Logs vão mostrar EXATAMENTE onde trava:**

```
[SENTINELA] Etapa X/6: fazendo algo...
[... NADA MAIS ...]
```

**Com isso, saberemos:**
- Se é o import de `backend_core` (Etapa 1)
- Se é `generate_janela_execucao()` (Etapa 3)
- Se é `save_session()` (Etapa 4)
- Se é o loop de keywords (depois da Etapa 6)

**Próximo passo:** Implementar correção específica baseada no diagnóstico.

---

**Data:** 27/04/2026
**Status:** ✅ U7.3 implementado e no GitHub
**Servidor:** ✅ Rodando com código atualizado (Terminal ID: 12)
**Próximo:** Testar e observar logs para diagnóstico
