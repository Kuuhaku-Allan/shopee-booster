# 🎯 Passo a Passo - Executar AGORA

## ✅ Checklist de Execução

### 1️⃣ Gerar Chaves

```powershell
cd "C:\Users\Defal\Documents\Faculdade\Projeto Shopee"
.\deploy\local\generate-keys.ps1
```

**Copie as 3 chaves** que aparecerem na tela.

---

### 2️⃣ Editar .env.local

```powershell
notepad .env.local
```

**Preencha estas variáveis:**

```env
EVOLUTION_API_KEY=<cole_chave_1_aqui>
POSTGRES_PASSWORD=<cole_chave_2_aqui>
BOT_SECRET_KEY=<cole_chave_3_aqui>
WHATSAPP_INSTANCE=shopee_booster
ALLOW_GLOBAL_GEMINI_FALLBACK=false
```

**Salve e feche** o Notepad.

---

### 3️⃣ Cloudflare Tunnel

#### Opção A: Tem Domínio na Cloudflare? ✅

1. Acesse: https://one.dash.cloudflare.com/
2. **Zero Trust > Networks > Tunnels > Create tunnel**
3. Nome: `shopee-booster-bot`
4. Copie o **CLOUDFLARE_TUNNEL_TOKEN**
5. Configure **Public Hostname**:
   - Subdomain: `bot`
   - Domain: `seudominio.com`
   - Service: `http://host.docker.internal:8787`

**Volte ao .env.local:**

```powershell
notepad .env.local
```

**Adicione:**

```env
CLOUDFLARE_TUNNEL_TOKEN=<token_copiado>
SHOPEE_API_PUBLIC_URL=https://bot.seudominio.com
```

**Salve e feche.**

#### Opção B: NÃO Tem Domínio? ⚠️

**Abra um PowerShell separado** e deixe rodando:

```powershell
cloudflared tunnel --url http://localhost:8787
```

Ele vai mostrar uma URL tipo:
```
https://alguma-coisa-aleatoria.trycloudflare.com
```

**Copie essa URL** e volte ao .env.local:

```powershell
notepad .env.local
```

**Adicione:**

```env
SHOPEE_API_PUBLIC_URL=https://alguma-coisa-aleatoria.trycloudflare.com
```

**Salve e feche.**

⚠️ **IMPORTANTE:** Se usar tunnel temporário, **NÃO adicione** `CLOUDFLARE_TUNNEL_TOKEN` no .env.local. Deixe o PowerShell com `cloudflared` rodando em segundo plano.

---

### 4️⃣ Verificar Configuração

```powershell
.\deploy\local\check-config.ps1
```

**Esperado:** ✅ "Configuração OK!"

Se der erro, revise o .env.local.

---

### 5️⃣ Iniciar Bot

```powershell
.\deploy\local\start-bot.ps1
```

Aguarde 1-2 minutos. O script vai mostrar o progresso.

---

### 6️⃣ Verificar Status

```powershell
.\deploy\local\status-bot.ps1
```

Ou:

```powershell
curl http://localhost:8787/health
```

**Esperado:**
```json
{"ok":true,"service":"shopee-booster-bot-api","version":"0.2.0"}
```

---

### 7️⃣ Configurar Webhook

```powershell
Invoke-RestMethod -Uri "http://localhost:8787/evolution/setup-webhook" -Method POST
```

---

### 8️⃣ Conectar WhatsApp

Abra no navegador:
```
http://localhost:8080
```

Procure pela instância `shopee_booster` e **escaneie o QR Code**.

---

### 9️⃣ Testar no WhatsApp

Envie:
```
/menu
```

---

## 📊 Reporte os Resultados

**Me diga apenas:**

- [ ] `check-config.ps1` → passou ou deu erro?
- [ ] `start-bot.ps1` → subiu ou deu erro?
- [ ] `curl http://localhost:8787/health` → respondeu ou não?
- [ ] `http://localhost:8080` → abriu ou não?
- [ ] `/menu` no WhatsApp → respondeu ou não?

**Se der erro, copie a mensagem de erro (sem tokens/senhas).**

---

## ⚠️ NÃO Instale Auto-Start Ainda!

Só instale depois que tudo funcionar manualmente:
- ❌ `install-startup-task.ps1` (NÃO executar ainda)
- ❌ `install-watchdog-task.ps1` (NÃO executar ainda)

---

## 🔍 Se Precisar Ver Logs

```powershell
# Todos os serviços
docker compose -f docker-compose.local.yml --env-file .env.local logs -f

# Apenas API
docker compose -f docker-compose.local.yml --env-file .env.local logs -f shopee_api

# Apenas Evolution
docker compose -f docker-compose.local.yml --env-file .env.local logs -f evolution_api
```

---

**Boa sorte! Execute os passos acima e me reporte os resultados.** 🚀
