# 🚀 Iniciar Bot Local - Guia Rápido

## Ordem de Execução

### 1️⃣ Gerar Chaves

```powershell
.\deploy\local\generate-keys.ps1
```

**Copie as 3 chaves geradas** (você vai precisar delas no próximo passo).

---

### 2️⃣ Configurar Cloudflare Tunnel

#### Opção A: Dashboard (Recomendado)

1. Acesse: https://one.dash.cloudflare.com/
2. **Access > Tunnels > Create a tunnel**
3. Nome: `shopee-booster-bot`
4. Connector: **Docker**
5. **COPIE O TOKEN**
6. Public Hostname:
   - Subdomain: `shopee-bot`
   - Domain: seu domínio
   - Service: `http://host.docker.internal:8787`
7. Salve

#### Opção B: Tunnel Temporário (Testes)

```powershell
# Instalar
winget install --id Cloudflare.cloudflared

# Criar tunnel temporário
cloudflared tunnel --url http://localhost:8787
```

⚠️ **Tunnel temporário muda a URL a cada reinício!**

---

### 3️⃣ Editar .env.local

```powershell
notepad .env.local
```

**Preencha:**

```env
EVOLUTION_API_KEY=<chave_gerada_1>
POSTGRES_PASSWORD=<chave_gerada_2>
BOT_SECRET_KEY=<chave_gerada_3>
SHOPEE_API_PUBLIC_URL=https://shopee-bot.seudominio.com
CLOUDFLARE_TUNNEL_TOKEN=<token_do_cloudflare>
```

**Deixe em branco** (configurar depois via WhatsApp):
- `GOOGLE_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Salve e feche.

---

### 4️⃣ Verificar Configuração

```powershell
.\deploy\local\check-config.ps1
```

Se aparecer ✅ **"Configuração OK!"**, prossiga.

---

### 5️⃣ Verificar Docker

```powershell
docker info
```

Se não estiver rodando, abra **Docker Desktop** e aguarde iniciar.

---

### 6️⃣ Iniciar Bot

```powershell
.\deploy\local\start-bot.ps1
```

Aguarde 1-2 minutos. O script vai:
- ✅ Verificar Docker
- ✅ Criar diretórios
- ✅ Subir containers
- ✅ Aguardar health checks
- ✅ Configurar webhook

---

### 7️⃣ Verificar Status

```powershell
.\deploy\local\status-bot.ps1
```

Ou:

```powershell
curl http://localhost:8787/health
```

Esperado:
```json
{"ok":true,"service":"shopee-booster-bot-api","version":"0.2.0"}
```

---

### 8️⃣ Conectar WhatsApp

#### Ver QR Code:

```powershell
# Opção 1: Via API
Invoke-RestMethod -Uri "http://localhost:8787/evolution/qrcode" -Method Get

# Opção 2: Ver logs
docker compose -f docker-compose.local.yml --env-file .env.local logs -f evolution_api

# Opção 3: Dashboard Evolution
# Abra: http://localhost:8080
```

**Escaneie o QR Code** com WhatsApp.

---

### 9️⃣ Testar Bot

Envie no WhatsApp:

```
/menu
/status
/loja
/catalogo
/ia
/telegram
/sentinela status
```

---

## ✅ Tudo Funcionando?

### Instalar Auto-Start (Opcional)

**Execute como Administrador:**

```powershell
.\deploy\local\install-startup-task.ps1
.\deploy\local\install-watchdog-task.ps1
```

Agora o bot inicia automaticamente no login do Windows!

---

## 🔧 Comandos Úteis

### Ligar
```powershell
.\deploy\local\start-bot.ps1
```

### Desligar
```powershell
.\deploy\local\stop-bot.ps1
```

### Status
```powershell
.\deploy\local\status-bot.ps1
```

### Logs
```powershell
docker compose -f docker-compose.local.yml --env-file .env.local logs -f
```

### Reconfigurar Webhook
```powershell
Invoke-RestMethod -Uri "http://localhost:8787/evolution/setup-webhook" -Method POST -Body '{"user_id":"admin","shop_uid":"setup"}' -ContentType "application/json"
```

---

## 📚 Documentação Completa

- **Setup Rápido:** `deploy/local/SETUP_RAPIDO.md`
- **README Completo:** `deploy/local/README.md`
- **Troubleshooting:** `deploy/local/README.md` (seção Troubleshooting)

---

## ⚠️ Problemas Comuns

### Docker não inicia
```powershell
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
Start-Sleep -Seconds 60
docker info
```

### Containers não sobem
```powershell
docker compose -f docker-compose.local.yml --env-file .env.local logs
docker compose -f docker-compose.local.yml --env-file .env.local up -d --build --force-recreate
```

### WhatsApp não conecta
```powershell
docker compose -f docker-compose.local.yml --env-file .env.local logs -f evolution_api
docker compose -f docker-compose.local.yml --env-file .env.local restart evolution_api
```

### Webhook não funciona
```powershell
# Verificar URL pública
curl https://shopee-bot.seudominio.com/health

# Reconfigurar
Invoke-RestMethod -Uri "http://localhost:8787/evolution/setup-webhook" -Method POST -Body '{"user_id":"admin","shop_uid":"setup"}' -ContentType "application/json"
```

---

**Pronto! Bot rodando 24/7 no seu PC.** 🎉
