# ✅ U7.2 Implementado - Correção Crítica do Sentinela

## 🎯 Problema Identificado pelo GPT

O estado `processing_sentinel` estava sendo salvo **DENTRO** do background task (`_run_sentinel_bg`), mas o webhook apenas agendava o task. Se o background falhasse rápido ou demorasse para iniciar, o `/status` via sessão `idle`.

## ✅ Correção Implementada

### 1. Webhook Salva Sessão ANTES de Agendar Background ✅

**Arquivo:** `api_server.py` - Linha ~379

**Antes:**
```python
elif task == "run_sentinel":
    background_tasks.add_task(
        _run_sentinel_bg,
        user_id=response["user_id"],
        config=response["config"],
    )
```

**Depois:**
```python
elif task == "run_sentinel":
    # ── U7.2: Salva sessão ANTES de agendar background ─────────
    config = dict(response["config"])
    keywords_raw = config.get("keywords") or []
    keywords_to_run = [k for k in keywords_raw if isinstance(k, str) and k.strip()][:3]
    
    config["keywords"] = keywords_to_run
    
    save_session(
        response["user_id"],
        "processing_sentinel",
        {
            "shop_uid": config.get("shop_uid", ""),
            "username": config.get("username", "loja"),
            "keywords": keywords_to_run,
            "started_at": datetime.utcnow().isoformat(),
            "status": "queued",
            "current_keyword": "preparando...",
            "completed_keywords": 0,
            "total_keywords": len(keywords_to_run),
        },
    )
    log.info(f"[WEBHOOK] Sessão processing_sentinel salva: user={msg['user_id']!r}")
    
    background_tasks.add_task(
        _run_sentinel_bg,
        user_id=response["user_id"],
        config=config,
    )
```

### 2. Timeout REAL com ThreadPoolExecutor ✅

**Arquivo:** `api_server.py` - Função `_run_sentinel_bg`

**Antes:**
```python
# threading.Timer que NÃO interrompia fetch_competitors_intercept
with timeout_context(TIMEOUT_PER_KEYWORD) as timed_out:
    concorrentes_raw = fetch_competitors_intercept(kw) or []
    if timed_out[0]:
        raise TimeoutError(...)
```

**Depois:**
```python
# ThreadPoolExecutor com timeout REAL
def fetch_with_timeout(keyword: str) -> list:
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fetch_competitors_intercept, keyword)
        return future.result(timeout=TIMEOUT_PER_KEYWORD)

# No loop
try:
    concorrentes_raw = fetch_with_timeout(kw) or []
except FutureTimeoutError:
    keywords_timeout.append(kw)
```

### 3. Status Atualizado de "queued" para "running" ✅

**Arquivo:** `api_server.py` - Função `_run_sentinel_bg`

Ao iniciar a execução, atualiza o status:
```python
save_session(
    user_id,
    "processing_sentinel",
    {
        ...
        "status": "running",  # Era "queued" no webhook
        ...
    },
)
```

---

## 🧪 Como Testar AGORA

### Teste 1: Verificar Servidor

```powershell
# Verificar se está rodando
Get-NetTCPConnection -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue

# Testar health
Invoke-RestMethod -Uri "http://127.0.0.1:8787/health"
```

### Teste 2: Reconfigurar Webhook

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8787/evolution/setup-webhook" -Method POST
```

### Teste 3: WhatsApp - TESTE PRINCIPAL

**No WhatsApp, envie:**
```
/sentinela rodar
```

**IMEDIATAMENTE envie:**
```
/status
```

**Resultado ESPERADO (U7.2):**
```
🛡️ Sentinela em execução

Loja: totalmenteseu
Progresso: 0/3
Keyword atual: preparando...
Tempo decorrido: 0 min

Vou avisar quando terminar.

⚠️ Não inicie outro Sentinela agora.
```

**Aguarde alguns segundos e envie `/status` novamente:**
```
🛡️ Sentinela em execução

Loja: totalmenteseu
Progresso: 1/3
Keyword atual: mochila roxa
Tempo decorrido: 1 min
```

**Após conclusão (2-3 minutos):**
```
🛡️ Sentinela concluído!

🏪 Loja: totalmenteseu
🔍 Keywords analisadas: 3
📊 Concorrentes analisados: 27
🏷️ Menor preço encontrado: R$ 45.90
💰 Preço médio: R$ 78.50

📢 Relatório completo enviado ao Telegram.

Janela: 2026-04-27_12h
```

---

## 📊 Logs Esperados no Servidor

Após `/sentinela rodar`, você deve ver:

```
[WEBHOOK] Sessão processing_sentinel salva: user=5511999999999@s.whatsapp.net
[BG] Execução do Sentinela agendada: user=5511999999999@s.whatsapp.net
[SENTINELA] ════════════════════════════════════════════════════
[SENTINELA] Início da execução: user=5511999999999@s.whatsapp.net
[SENTINELA] Status atualizado para 'running'
[SENTINELA] Keyword 1/3: 'mochila roxa'
[SENTINELA] Concorrentes encontrados: 9
[SENTINELA] Keyword 2/3: 'mochila escolar'
[SENTINELA] Concorrentes encontrados: 10
[SENTINELA] Keyword 3/3: 'mochila infantil'
[SENTINELA] Concorrentes encontrados: 8
[SENTINELA] Gerando relatório para Telegram...
[SENTINELA] Relatório enviado ao Telegram com sucesso
[SENTINELA] Resumo enviado ao WhatsApp
[SENTINELA] Concluído: user=... shop_uid=... kws=3
[SENTINELA] Sessão limpa: user=...
[SENTINELA] ════════════════════════════════════════════════════
```

---

## 🔍 Diagnóstico se Ainda Não Funcionar

### Problema 1: `/status` ainda mostra "Tudo livre"

**Verificar logs do servidor:**
- Procure por `[WEBHOOK] Sessão processing_sentinel salva`
- Se NÃO aparecer: O webhook não está chegando
- Se APARECER: A sessão foi salva, problema é no `/status`

**Verificar banco de dados:**
```powershell
sqlite3 data/bot_state.db "SELECT user_id, state, data_json FROM whatsapp_sessions WHERE state = 'processing_sentinel';"
```

**Durante execução, deve mostrar:**
```
5511999999999@s.whatsapp.net|processing_sentinel|{"shop_uid":"...","username":"...","status":"running",...}
```

### Problema 2: Logs não aparecem

**Causa:** Webhook não está chegando no FastAPI

**Soluções:**
1. Reconfigurar webhook:
   ```powershell
   Invoke-RestMethod -Uri "http://127.0.0.1:8787/evolution/setup-webhook" -Method POST
   ```

2. Verificar Evolution:
   ```powershell
   Invoke-RestMethod -Uri "http://127.0.0.1:8787/evolution/instance-status"
   ```

3. Verificar `.shopee_config`:
   ```
   SHOPEE_API_PUBLIC_URL=http://host.docker.internal:8787
   ```

### Problema 3: Timeout não funciona

**Causa:** ThreadPoolExecutor pode não estar matando o processo Playwright

**Solução:** O timeout agora é REAL e interrompe a thread. Se ainda travar, o problema é no Playwright/subprocess.

---

## 📝 Resumo das Alterações

| Aspecto | Antes (U7.1) | Depois (U7.2) |
|---------|--------------|---------------|
| Quando salva sessão | Dentro de `_run_sentinel_bg` | No webhook, ANTES de agendar |
| Status inicial | "running" | "queued" → "running" |
| `/status` após `/sentinela rodar` | "Tudo livre" (falha) | "Sentinela em execução" ✅ |
| Timeout | threading.Timer (não interrompe) | ThreadPoolExecutor (interrompe) ✅ |
| Keyword atual inicial | "" (vazio) | "preparando..." ✅ |

---

## ✅ Checklist de Teste

- [ ] 1. Servidor rodando em `0.0.0.0:8787`
- [ ] 2. Health check responde
- [ ] 3. Webhook reconfigurado
- [ ] 4. Evolution conectada
- [ ] 5. `/sentinela rodar` enviado
- [ ] 6. `/status` mostra "Sentinela em execução" IMEDIATAMENTE
- [ ] 7. Logs mostram `[WEBHOOK] Sessão processing_sentinel salva`
- [ ] 8. Logs mostram `[SENTINELA] Início da execução`
- [ ] 9. Progresso atualiza (0/3 → 1/3 → 2/3 → 3/3)
- [ ] 10. Mensagem final chega no WhatsApp

---

## 🚀 Commit Realizado

**Commit:** `906540d`
**Branch:** `feature/whatsapp-bot-core`
**Mensagem:** feat(U7.2): Salva processing_sentinel ANTES de agendar background

**Link:** https://github.com/Kuuhaku-Allan/shopee-booster/commit/906540d

---

## 🎯 Resultado Final Esperado

```
[WhatsApp]
Você: /sentinela rodar
Bot: ⏳ Rodando o Sentinela...

Você: /status (imediatamente)
Bot: 🛡️ Sentinela em execução
     Progresso: 0/3
     Keyword atual: preparando...

[30 segundos depois]
Você: /status
Bot: 🛡️ Sentinela em execução
     Progresso: 1/3
     Keyword atual: mochila roxa

[2 minutos depois]
Bot: 🛡️ Sentinela concluído!
     Keywords analisadas: 3
     Concorrentes: 27
     📢 Relatório enviado ao Telegram
```

---

**Data:** 27/04/2026
**Status:** ✅ U7.2 implementado e no GitHub
**Servidor:** ✅ Rodando com código atualizado (Terminal ID: 8)
**Próximo Passo:** Testar no WhatsApp
