# 🎯 Instruções Finais - Teste Manual Necessário

## ✅ Status Atual

**Código:** ✅ Atualizado e no GitHub (commit 0068895)
**Branch:** ✅ feature/whatsapp-bot-core
**Alterações:** ✅ Todas as 9 correções U7.1 implementadas

## ⚠️ Problema Identificado pelo GPT

O servidor estava rodando em `127.0.0.1` mas o Docker precisa de `0.0.0.0` para que a Evolution API consiga acessar via `host.docker.internal`.

## 🚀 Comandos para Executar MANUALMENTE

### 1. Parar Todos os Processos Python

```powershell
Get-Process -Name "*python*" | Stop-Process -Force
```

### 2. Iniciar Servidor com 0.0.0.0

**⚠️ IMPORTANTE: Execute este comando em um terminal PowerShell SEPARADO**

```powershell
# Ativar ambiente virtual
.\venv\Scripts\Activate.ps1

# Iniciar servidor
.\venv\Scripts\python.exe -m uvicorn api_server:app --host 0.0.0.0 --port 8787 --reload
```

**Resultado esperado:**
```
INFO:     Uvicorn running on http://0.0.0.0:8787 (Press CTRL+C to quit)
INFO:     Started server process [XXXXX]
INFO:     Application startup complete.
```

### 3. Testar Health Check (Em OUTRO Terminal)

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8787/health"
```

**Resultado esperado:**
```
ok      : True
service : shopee-booster-bot-api
version : 0.2.0
```

### 4. Reconfigurar Webhook da Evolution

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8787/evolution/setup-webhook" -Method POST
```

**Resultado esperado:**
```json
{
  "ok": true,
  "message": "Webhook configurado com sucesso"
}
```

### 5. Verificar Status da Evolution

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8787/evolution/instance-status"
```

**Resultado esperado:**
```json
{
  "state": "open",
  "instance": "shopee_booster"
}
```

### 6. Teste de Envio Direto (Opcional)

**⚠️ Substitua `55SEUNUMERO` pelo seu número com DDD**

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8787/evolution/test-send?number=55SEUNUMERO" -Method POST
```

Se uma mensagem de teste chegar no WhatsApp, o envio está funcionando!

---

## 🧪 Teste Principal: WhatsApp

### Teste 1: Menu

Envie no WhatsApp:
```
/menu
```

**Observe o terminal do servidor!** Deve aparecer:
```
[INFO] /webhook/evolution event='MESSAGES_UPSERT' user='...' text='/menu'
```

**Resultado esperado no WhatsApp:**
```
🎯 Menu Principal

🏪 /loja — Gerenciar lojas
📊 /auditar — Otimizar produto
📦 /catalogo — Importar catálogo
🤖 /ia — Configurar IA
📱 /telegram — Configurar Telegram
🛡️ /sentinela — Monitorar concorrentes
📋 /status — Ver sessão atual
🔄 /cancelar — Cancelar e recomeçar

Ou me mande qualquer pergunta diretamente!
```

### Teste 2: Sentinela (PRINCIPAL)

```
/sentinela rodar
```

**Resultado esperado:**
```
⏳ Rodando o Sentinela para totalmenteseu...

Keywords:
• keyword1
• keyword2
• keyword3

Vou te enviar o resumo aqui e o relatório completo no Telegram.

Isso pode levar alguns minutos.
```

**Imediatamente envie:**
```
/status
```

**Resultado esperado (U7.1):**
```
🛡️ Sentinela em execução

Loja: totalmenteseu
Progresso: 0/3
Keyword atual: preparando...
Tempo decorrido: 0 min

Vou avisar quando terminar.

⚠️ Não inicie outro Sentinela agora.
```

**Observe os logs do servidor!** Deve aparecer:
```
[SENTINELA] ════════════════════════════════════════════════════
[SENTINELA] Início da execução: user=5511999999999@s.whatsapp.net
[SENTINELA] Sessão salva: processing_sentinel
[SENTINELA] Keyword 1/3: 'mochila roxa'
[SENTINELA] Concorrentes encontrados: 9
[SENTINELA] Keyword 2/3: 'mochila escolar'
...
```

---

## 🔍 Diagnóstico se Não Funcionar

### Problema 1: `/menu` não responde

**Causa:** Webhook não está chegando no FastAPI

**Verificações:**

1. **Servidor está rodando em 0.0.0.0?**
   ```powershell
   # No terminal do servidor, deve mostrar:
   # INFO: Uvicorn running on http://0.0.0.0:8787
   ```

2. **Webhook foi reconfigurado?**
   ```powershell
   Invoke-RestMethod -Uri "http://127.0.0.1:8787/evolution/setup-webhook" -Method POST
   ```

3. **Evolution está conectada?**
   ```powershell
   Invoke-RestMethod -Uri "http://127.0.0.1:8787/evolution/instance-status"
   # Deve retornar: "state": "open"
   ```

4. **Variáveis de ambiente corretas?**
   Verifique `.shopee_config`:
   ```
   EVOLUTION_API_URL=http://localhost:8080
   WHATSAPP_INSTANCE=shopee_booster
   SHOPEE_API_PUBLIC_URL=http://host.docker.internal:8787
   ```

### Problema 2: `/menu` responde mas `/status` mostra "Tudo livre"

**Causa:** Sessão não está sendo salva

**Verificações:**

1. **Logs mostram `[SENTINELA] Sessão salva: processing_sentinel`?**
   - Se SIM: O código está funcionando!
   - Se NÃO: O background task não está sendo executado

2. **Verificar sessão no banco:**
   ```powershell
   sqlite3 data/bot_state.db "SELECT user_id, state FROM whatsapp_sessions;"
   ```
   Durante execução, deve mostrar:
   ```
   5511999999999@s.whatsapp.net|processing_sentinel
   ```

### Problema 3: Mensagem de "from_me=True"

**Causa:** Você está enviando mensagem do próprio número do bot

**Solução:** Envie mensagens de OUTRO WhatsApp para o número do bot

---

## 🧪 Teste Isolado do Webhook (Avançado)

Para testar se o roteador funciona sem depender da Evolution:

```powershell
$body = @{
  event = "MESSAGES_UPSERT"
  data = @{
    key = @{
      remoteJid = "5511999999999@s.whatsapp.net"
      fromMe = $false
      id = "teste-menu-$(Get-Random)"
    }
    message = @{
      conversation = "/menu"
    }
  }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8787/webhook/evolution" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body
```

**Se isso retornar a resposta do menu:** O código do bot está funcionando!
**Se não retornar:** Há um problema no código (mas improvável, pois o commit está correto)

---

## ✅ Checklist Final

Execute em ordem:

- [ ] 1. Parar todos os processos Python
- [ ] 2. Iniciar servidor com `--host 0.0.0.0`
- [ ] 3. Verificar logs: "Uvicorn running on http://0.0.0.0:8787"
- [ ] 4. Testar health check: `http://127.0.0.1:8787/health`
- [ ] 5. Reconfigurar webhook: `/evolution/setup-webhook`
- [ ] 6. Verificar Evolution: `/evolution/instance-status`
- [ ] 7. Testar `/menu` no WhatsApp
- [ ] 8. Observar logs do servidor
- [ ] 9. Testar `/sentinela rodar` no WhatsApp
- [ ] 10. Testar `/status` imediatamente após
- [ ] 11. Verificar logs: `[SENTINELA] Sessão salva: processing_sentinel`

---

## 🎯 Resultado Final Esperado

### No WhatsApp:
```
Você: /sentinela rodar
Bot: ⏳ Rodando o Sentinela...

Você: /status
Bot: 🛡️ Sentinela em execução
     Progresso: 0/3
     Keyword atual: preparando...

[2 minutos depois]
Bot: 🛡️ Sentinela concluído!
     Keywords analisadas: 3
     Concorrentes: 27
     📢 Relatório enviado ao Telegram
```

### Nos Logs do Servidor:
```
[SENTINELA] ════════════════════════════════════════════════════
[SENTINELA] Início da execução: user=5511999999999@s.whatsapp.net
[SENTINELA] Sessão salva: processing_sentinel
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

## 📝 Resumo para o GPT

### O Que Foi Feito
- ✅ Código U7.1 implementado e no GitHub (commit 0068895)
- ✅ Processos Python antigos parados
- ✅ Tentativa de iniciar servidor com `0.0.0.0`

### Problema Técnico
- ⚠️ O servidor diz que iniciou mas a porta não está em uso
- ⚠️ Pode ser problema com processo filho do uvicorn
- ⚠️ Requer execução manual em terminal separado

### Próximo Passo
- 🔄 Usuário precisa executar manualmente em terminal PowerShell
- 🔄 Seguir checklist acima
- 🔄 Testar no WhatsApp e observar logs

---

**Data:** 27/04/2026
**Status:** ✅ Código pronto, aguardando teste manual
**Comando:** `.\venv\Scripts\python.exe -m uvicorn api_server:app --host 0.0.0.0 --port 8787 --reload`
