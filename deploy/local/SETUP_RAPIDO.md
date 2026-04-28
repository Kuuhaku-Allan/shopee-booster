# Setup Rápido - Deploy Local

## ✅ Checklist de Configuração

### 1. Gerar Chaves

Execute o gerador de chaves:

```powershell
.\deploy\local\generate-keys.ps1
```

Copie as 3 chaves geradas:
- `EVOLUTION_API_KEY`
- `POSTGRES_PASSWORD`
- `BOT_SECRET_KEY`

### 2. Configurar Cloudflare Tunnel

#### Opção A: Dashboard (Mais Fácil)

1. Acesse: https://one.dash.cloudflare.com/
2. Vá em **Access > Tunnels**
3. Clique em **Create a tunnel**
4. Nome: `shopee-booster-bot`
5. Escolha **Docker** como connector
6. **COPIE O TOKEN** que aparece no comando
7. Configure **Public Hostname**:
   - **Subdomain:** `shopee-bot` (ou outro)
   - **Domain:** seu domínio (ou use subdomínio gratuito do Cloudflare)
   - **Service Type:** HTTP
   - **URL:** `host.docker.internal:8787`
8. Salve

#### Opção B: Tunnel Temporário (Para Testes)

Se não tiver domínio, use tunnel temporário:

```powershell
# Instalar cloudflared
winget install --id Cloudflare.cloudflared

# Criar tunnel temporário (gera URL aleatória)
cloudflared tunnel --url http://localhost:8787
```

**NOTA:** Tunnel temporário muda a URL a cada reinício!

### 3. Editar .env.local

Abra o arquivo:

```powershell
notepad .env.local
```

Preencha as variáveis obrigatórias:

```env
# ══════════════════════════════════════════════════════════════════
# EVOLUTION API
# ══════════════════════════════════════════════════════════════════

EVOLUTION_API_KEY=COLE_AQUI_A_CHAVE_GERADA_1

# ══════════════════════════════════════════════════════════════════
# POSTGRES
# ══════════════════════════════════════════════════════════════════

POSTGRES_PASSWORD=COLE_AQUI_A_CHAVE_GERADA_2

# ══════════════════════════════════════════════════════════════════
# SHOPEE BOOSTER API
# ══════════════════════════════════════════════════════════════════

SHOPEE_API_PUBLIC_URL=https://shopee-bot.seudominio.com
BOT_SECRET_KEY=COLE_AQUI_A_CHAVE_GERADA_3
ALLOW_GLOBAL_GEMINI_FALLBACK=false

# ══════════════════════════════════════════════════════════════════
# CLOUDFLARE TUNNEL
# ══════════════════════════════════════════════════════════════════

CLOUDFLARE_TUNNEL_TOKEN=COLE_AQUI_O_TOKEN_DO_CLOUDFLARE
```

**Deixe em branco (opcional):**
- `GOOGLE_API_KEY` - Configurar depois via `/ia configurar`
- `TELEGRAM_BOT_TOKEN` - Configurar depois via `/telegram configurar`
- `TELEGRAM_CHAT_ID` - Configurar depois via `/telegram configurar`

Salve e feche.

### 4. Verificar Docker

Certifique-se de que Docker Desktop está rodando:

```powershell
docker info
```

Se não estiver rodando, abra Docker Desktop e aguarde iniciar.

### 5. Iniciar Bot

```powershell
.\deploy\local\start-bot.ps1
```

Aguarde 1-2 minutos. O script vai:
- ✅ Verificar Docker
- ✅ Criar diretórios necessários
- ✅ Subir containers
- ✅ Aguardar health checks
- ✅ Configurar webhook

### 6. Verificar Status

```powershell
.\deploy\local\status-bot.ps1
```

Ou manualmente:

```powershell
# Health check da API
curl http://localhost:8787/health

# Status dos containers
docker compose -f docker-compose.local.yml --env-file .env.local ps

# Logs
docker compose -f docker-compose.local.yml --env-file .env.local logs -f
```

### 7. Conectar WhatsApp

#### Opção A: Via API (Recomendado)

```powershell
# Ver QR Code no terminal
Invoke-RestMethod -Uri "http://localhost:8787/evolution/qrcode" -Method Get
```

#### Opção B: Via Evolution Dashboard

Abra no navegador:
```
http://localhost:8080
```

Procure pela instância `shopee_booster` e escaneie o QR Code.

#### Opção C: Ver logs da Evolution

```powershell
docker compose -f docker-compose.local.yml --env-file .env.local logs -f evolution_api
```

O QR Code aparece nos logs.

### 8. Testar Bot

Envie mensagens no WhatsApp:

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

## 🔧 Comandos Úteis

### Ligar Bot
```powershell
.\deploy\local\start-bot.ps1
```

### Desligar Bot
```powershell
# Parar (mantém dados)
.\deploy\local\stop-bot.ps1

# Parar e remover containers
.\deploy\local\stop-bot.ps1 -Down
```

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

# Apenas Cloudflare Tunnel
docker compose -f docker-compose.local.yml --env-file .env.local logs -f cloudflared
```

### Reconfigurar Webhook
```powershell
Invoke-RestMethod -Uri "http://localhost:8787/evolution/setup-webhook" -Method POST -Body '{"user_id":"admin","shop_uid":"setup"}' -ContentType "application/json"
```

### Ver Status da Instância WhatsApp
```powershell
Invoke-RestMethod -Uri "http://localhost:8787/evolution/instance-status" -Method Get
```

---

## ⚠️ Troubleshooting Rápido

### Docker não inicia
```powershell
# Abrir Docker Desktop
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
Start-Sleep -Seconds 60
docker info
```

### Containers não sobem
```powershell
# Ver erro
docker compose -f docker-compose.local.yml --env-file .env.local logs

# Rebuild
docker compose -f docker-compose.local.yml --env-file .env.local up -d --build --force-recreate
```

### WhatsApp não conecta
```powershell
# Ver logs da Evolution
docker compose -f docker-compose.local.yml --env-file .env.local logs -f evolution_api

# Reiniciar Evolution
docker compose -f docker-compose.local.yml --env-file .env.local restart evolution_api
```

### Webhook não funciona
```powershell
# Verificar URL pública
notepad .env.local

# Testar URL pública
curl https://shopee-bot.seudominio.com/health

# Reconfigurar webhook
Invoke-RestMethod -Uri "http://localhost:8787/evolution/setup-webhook" -Method POST -Body '{"user_id":"admin","shop_uid":"setup"}' -ContentType "application/json"
```

---

## 🚀 Próximos Passos

Depois que tudo estiver funcionando manualmente:

### Instalar Auto-Start

```powershell
# Execute como Administrador!
.\deploy\local\install-startup-task.ps1
.\deploy\local\install-watchdog-task.ps1
```

### Criar Atalhos na Área de Trabalho

Veja instruções completas em: `deploy/local/README.md`

---

**Pronto! Agora é só seguir os passos acima.** 🎉
