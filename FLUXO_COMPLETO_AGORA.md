# 🎯 Fluxo Completo - Execute AGORA

## 📋 Status Atual

Você já tem:
- ✅ `.env.local` criado
- ✅ `EVOLUTION_API_KEY` configurado
- ✅ `POSTGRES_PASSWORD` configurado
- ✅ `BOT_SECRET_KEY` configurado
- ✅ `CLOUDFLARE_TUNNEL_TOKEN` configurado

Falta:
- ❌ Instalar `cloudflared`
- ❌ Iniciar bot localmente
- ❌ Criar tunnel e obter URL pública
- ❌ Atualizar `SHOPEE_API_PUBLIC_URL`

---

## 🚀 Passo a Passo

### 1️⃣ Instalar cloudflared

```powershell
winget install --id Cloudflare.cloudflared
```

**Aguarde a instalação terminar.**

### 2️⃣ Fechar e Reabrir PowerShell

**IMPORTANTE:** Feche este PowerShell e abra um novo para o PATH ser atualizado.

### 3️⃣ Verificar Instalação

```powershell
cd "C:\Users\Defal\Documents\Faculdade\Projeto Shopee"
cloudflared --version
```

**Esperado:** Deve mostrar a versão.

Se não funcionar, veja: `INSTALAR_CLOUDFLARED.md`

---

### 4️⃣ Verificar Docker

```powershell
docker info
```

Se não estiver rodando, abra **Docker Desktop** e aguarde iniciar.

---

### 5️⃣ Iniciar Bot Localmente (SEM tunnel ainda)

Por enquanto, vamos deixar `SHOPEE_API_PUBLIC_URL` como está e iniciar o bot:

```powershell
.\deploy\local\start-bot.ps1
```

**Aguarde 1-2 minutos.** O script vai:
- Verificar Docker
- Criar diretórios
- Subir containers
- Aguardar health checks

**Ignore o erro do webhook por enquanto** (ele vai falhar porque a URL pública ainda não está configurada).

---

### 6️⃣ Verificar se Bot Está Rodando

```powershell
curl http://localhost:8787/health
```

**Esperado:**
```json
{"ok":true,"service":"shopee-booster-bot-api","version":"0.2.0"}
```

Se não responder, veja os logs:
```powershell
docker compose -f docker-compose.local.yml --env-file .env.local logs -f shopee_api
```

---

### 7️⃣ Criar Tunnel (Agora sim!)

Abra um **NOVO PowerShell** (deixe o atual aberto) e execute:

```powershell
cd "C:\Users\Defal\Documents\Faculdade\Projeto Shopee"
.\deploy\local\start-tunnel-temp.ps1
```

**OU** execute diretamente:

```powershell
cloudflared tunnel --url http://localhost:8787
```

**Aguarde aparecer a URL:**

```
+--------------------------------------------------------------------------------------------+
|  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |
|  https://purple-river-example-1234.trycloudflare.com                                       |
+--------------------------------------------------------------------------------------------+
```

**COPIE** a URL `https://....trycloudflare.com`

**⚠️ DEIXE ESTE POWERSHELL RODANDO!**

---

### 8️⃣ Atualizar .env.local

No PowerShell original:

```powershell
notepad .env.local
```

Encontre:
```env
SHOPEE_API_PUBLIC_URL=https://SEU_DOMINIO_AQUI
```

Substitua por (use SUA URL copiada):
```env
SHOPEE_API_PUBLIC_URL=https://purple-river-example-1234.trycloudflare.com
```

**Salve e feche.**

---

### 9️⃣ Verificar Configuração

```powershell
.\deploy\local\check-config.ps1
```

Agora deve passar! ✅

---

### 🔟 Reconfigurar Webhook

Agora que a URL pública está configurada, reconfigure o webhook:

```powershell
Invoke-RestMethod -Uri "http://localhost:8787/evolution/setup-webhook" -Method POST -Body '{"user_id":"admin","shop_uid":"setup"}' -ContentType "application/json"
```

**Esperado:**
```json
{"ok":true,"webhook_url":"https://purple-river-example-1234.trycloudflare.com/webhook/evolution"}
```

---

### 1️⃣1️⃣ Conectar WhatsApp

Abra no navegador:
```
http://localhost:8080
```

Procure pela instância `shopee_booster` e **escaneie o QR Code**.

**OU** veja o QR Code nos logs:

```powershell
docker compose -f docker-compose.local.yml --env-file .env.local logs -f evolution_api
```

---

### 1️⃣2️⃣ Testar Bot

Envie no WhatsApp:
```
/menu
```

Se responder, está funcionando! 🎉

---

## 📊 Checklist Final

- [ ] `cloudflared --version` funcionou
- [ ] Docker está rodando
- [ ] `start-bot.ps1` executou sem erros
- [ ] `curl http://localhost:8787/health` respondeu OK
- [ ] Tunnel criado e URL copiada
- [ ] `.env.local` atualizado com URL pública
- [ ] `check-config.ps1` passou
- [ ] Webhook reconfigurado
- [ ] WhatsApp conectado
- [ ] `/menu` respondeu

---

## 🔍 Comandos Úteis

### Ver Status
```powershell
.\deploy\local\status-bot.ps1
```

### Ver Logs
```powershell
# Todos os serviços
docker compose -f docker-compose.local.yml --env-file .env.local logs -f

# Apenas API
docker compose -f docker-compose.local.yml --env-file .env.local logs -f shopee_api

# Apenas Evolution
docker compose -f docker-compose.local.yml --env-file .env.local logs -f evolution_api
```

### Reiniciar Bot
```powershell
.\deploy\local\stop-bot.ps1
.\deploy\local\start-bot.ps1
```

---

## ⚠️ Lembre-se

- **DEIXE** o PowerShell com `cloudflared` rodando
- Se fechar, o tunnel para de funcionar
- Se reiniciar o tunnel, a URL muda (precisa atualizar .env.local e reconfigurar webhook)

---

## 📚 Documentação

- **Instalar cloudflared:** `INSTALAR_CLOUDFLARED.md`
- **Configurar URL:** `CONFIGURAR_URL_PUBLICA.md`
- **Passo a passo:** `PASSO_A_PASSO_AGORA.md`
- **README completo:** `deploy/local/README.md`

---

**Execute agora e me reporte os resultados!** 🚀
