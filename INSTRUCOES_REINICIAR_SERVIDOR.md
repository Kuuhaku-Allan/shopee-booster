# 🔄 Instruções para Reiniciar o Servidor com Código Atualizado

## ✅ Status Atual

**Código:** ✅ Atualizado e no GitHub (commit 0068895)
**Problema:** Servidor pode estar rodando código antigo

## 🔍 Processos Python Detectados

```
Id: 23292 - venv\Scripts\python.exe
Id: 23424 - C:\Python313\python.exe
```

**⚠️ Há 2 processos Python rodando!**

---

## 🛑 Passo 1: Parar TODOS os Processos Python

Execute no PowerShell:

```powershell
Get-Process -Name "*python*" | Stop-Process -Force
```

**Resultado esperado:** Todos os processos Python terminados

---

## 🚀 Passo 2: Iniciar o Servidor Atualizado

### Opção A: Com Reload Automático (Desenvolvimento)

```powershell
# Ativar ambiente virtual
.\venv\Scripts\Activate.ps1

# Iniciar servidor
python -m uvicorn api_server:app --host 0.0.0.0 --port 8787 --reload
```

### Opção B: Sem Reload (Produção)

```powershell
# Ativar ambiente virtual
.\venv\Scripts\Activate.ps1

# Iniciar servidor
python -m uvicorn api_server:app --host 0.0.0.0 --port 8787
```

---

## ✅ Passo 3: Verificar se o Servidor Iniciou Corretamente

### 3.1. Verificar Logs de Inicialização

Procure por:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8787
```

### 3.2. Testar Health Check

Em outro terminal:
```powershell
curl http://localhost:8787/health
```

**Resultado esperado:**
```json
{
  "ok": true,
  "service": "shopee-booster-bot-api",
  "version": "0.2.0"
}
```

---

## 🧪 Passo 4: Testar o Sentinela

### 4.1. Enviar pelo WhatsApp

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

### 4.2. Verificar Status Imediatamente

```
/status
```

**Resultado esperado:**
```
🛡️ Sentinela em execução

Loja: totalmenteseu
Progresso: 0/3
Keyword atual: preparando...
Tempo decorrido: 0 min

Vou avisar quando terminar.

⚠️ Não inicie outro Sentinela agora.
```

### 4.3. Verificar Logs do Servidor

No terminal do servidor, procure por:
```
[SENTINELA] ════════════════════════════════════════════════════
[SENTINELA] Início da execução: user=...
[SENTINELA] Sessão salva: processing_sentinel
[SENTINELA] Keyword 1/3: ...
```

---

## 🔍 Passo 5: Diagnóstico se Ainda Não Funcionar

### 5.1. Verificar qual arquivo está sendo executado

```powershell
python -c "import api_server; print(api_server.__file__)"
```

**Resultado esperado:**
```
C:\Users\Defal\Documents\Faculdade\Projeto Shopee\api_server.py
```

### 5.2. Verificar se processing_sentinel está no arquivo

```powershell
python -c "with open('api_server.py', 'r', encoding='utf-8') as f: print('processing_sentinel' in f.read())"
```

**Resultado esperado:**
```
True
```

### 5.3. Verificar sessão no banco de dados

```powershell
sqlite3 data/bot_state.db "SELECT user_id, state, data_json FROM whatsapp_sessions WHERE state = 'processing_sentinel';"
```

**Resultado esperado (durante execução):**
```
5511999999999@s.whatsapp.net|processing_sentinel|{"shop_uid":"...","username":"...","keywords":[...],...}
```

---

## 📊 Checklist de Verificação

Após reiniciar o servidor:

- [ ] Processos Python antigos foram terminados
- [ ] Servidor iniciou sem erros
- [ ] Health check retorna `{"ok": true}`
- [ ] `/sentinela rodar` retorna mensagem inicial
- [ ] `/status` mostra "Sentinela em execução"
- [ ] Logs mostram `[SENTINELA] Sessão salva: processing_sentinel`
- [ ] Mensagem final chega no WhatsApp após conclusão

---

## ⚠️ Problemas Comuns

### Problema 1: "Address already in use"
**Causa:** Porta 8787 já está em uso
**Solução:**
```powershell
# Encontrar processo na porta 8787
netstat -ano | findstr :8787

# Matar processo (substitua PID)
taskkill /PID <PID> /F
```

### Problema 2: "Module not found"
**Causa:** Ambiente virtual não ativado
**Solução:**
```powershell
.\venv\Scripts\Activate.ps1
```

### Problema 3: Logs não aparecem
**Causa:** Nível de log muito alto
**Solução:** Adicionar `--log-level debug` ao comando uvicorn

### Problema 4: `/status` ainda mostra "Tudo livre"
**Causa:** Sessão não está sendo salva
**Solução:** Verificar logs para ver se `save_session` está sendo chamado

---

## 🎯 Resultado Final Esperado

Após seguir todos os passos:

```
[WhatsApp]
Você: /sentinela rodar
Bot: ⏳ Rodando o Sentinela...

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

```
[Logs do Servidor]
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

**Data:** 27/04/2026
**Ação Necessária:** Reiniciar servidor para carregar código atualizado
**Código:** ✅ Confirmado no GitHub (commit 0068895)
