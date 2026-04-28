# ✅ Deploy Local - SUCESSO!

## Data: 27/04/2026

## 🎉 Status Final

| Componente | Status | Detalhes |
|------------|--------|----------|
| **Cloudflared** | ✅ Funcionando | Tunnel temporário ativo |
| **Docker** | ✅ Rodando | 3 containers ativos |
| **Postgres** | ✅ Healthy | Porta 5432 |
| **Evolution API** | ✅ Funcionando | v2.1.1 com workaround |
| **Bot API** | ✅ Funcionando | Porta 8787 |
| **WhatsApp** | ✅ Conectado | Estado: `open` |
| **Webhook** | ✅ Configurado | Eventos: MESSAGES_UPSERT, CONNECTION_UPDATE, SEND_MESSAGE |
| **URL Pública** | ✅ Funcionando | `https://listings-materials-qualified-maps.trycloudflare.com` |

---

## 🛠️ Problemas Resolvidos

### 1. Cloudflared não instalado
**Solução:** Download manual do executável e instalação em `C:\Cloudflared\`

### 2. Evolution API - QR Code não gerava
**Problema:** Bug conhecido da v2.1.1 - `/instance/connect` retornava `{"count": 0}`

**Solução:** Workaround com variáveis de ambiente:
```yaml
CACHE_REDIS_ENABLED: "false"
CACHE_LOCAL_ENABLED: "true"
DATABASE_SAVE_DATA_CHATS: "false"
DATABASE_SAVE_DATA_CONTACTS: "false"
DATABASE_SAVE_DATA_HISTORIC: "false"
DATABASE_SAVE_DATA_LABELS: "false"
CONFIG_SESSION_PHONE_VERSION: "2.3000.1033773198"
```

**Documentação:** `WORKAROUND_EVOLUTION_QR.md`

### 3. Porta 8080 já em uso
**Problema:** Containers antigos da Evolution rodando

**Solução:** Remover containers antigos antes de subir novos

### 4. Erro de autenticação no Postgres
**Problema:** Volumes antigos com senha diferente

**Solução:** Remover todos os volumes e pastas locais antes de recriar

### 5. Webhook não configurado corretamente
**Problema:** Eventos `MESSAGES_UPSERT` não estavam ativos

**Solução:** Configurar webhook via API com estrutura correta:
```json
{
  "webhook": {
    "enabled": true,
    "url": "https://...trycloudflare.com/webhook/evolution",
    "webhookByEvents": false,
    "webhookBase64": false,
    "events": ["MESSAGES_UPSERT", "CONNECTION_UPDATE", "SEND_MESSAGE"]
  }
}
```

---

## 📋 Configuração Final

### Containers Rodando

```
shopee_postgres_local    - Up (healthy)
shopee_evolution_local   - Up
shopee_api_local         - Up (healthy)
```

### Portas

- **8787** - Bot API (FastAPI)
- **8080** - Evolution API
- **5432** - Postgres (interno)

### Volumes

- `postgres_data/` - Dados do Postgres
- `evolution_instances/` - Sessões do WhatsApp
- `evolution_store/` - Store da Evolution
- `data/` - Dados do bot (relatórios, etc)
- `uploads/` - Uploads (catálogos, etc)

### Tunnel

- **Tipo:** Temporário (trycloudflare.com)
- **URL:** `https://listings-materials-qualified-maps.trycloudflare.com`
- **Processo:** Rodando em background (terminal ID: 11)

---

## 🔗 Webhook Configurado

**URL:** `https://listings-materials-qualified-maps.trycloudflare.com/webhook/evolution`

**Eventos:**
- ✅ `MESSAGES_UPSERT` - Mensagens recebidas
- ✅ `CONNECTION_UPDATE` - Status de conexão
- ✅ `SEND_MESSAGE` - Mensagens enviadas

**Configuração:**
- `enabled: true`
- `webhookByEvents: false`
- `webhookBase64: false`

---

## 📱 Como Testar

### 1. Enviar de OUTRO número

⚠️ **IMPORTANTE:** Não pode ser do mesmo número conectado no bot!

### 2. Comandos para testar

```
/menu
/status
/loja
/catalogo
/ia
/telegram
/sentinela status
```

### 3. Monitorar logs

```powershell
docker logs shopee_api_local -f
```

---

## ⚠️ Limitações Atuais

### URL Temporária

A URL `https://listings-materials-qualified-maps.trycloudflare.com` é **temporária**.

**Se reiniciar o cloudflared:**
1. URL pode mudar
2. Precisa atualizar `.env.local`
3. Recriar container do bot
4. Reconfigurar webhook

**Soluções futuras:**
- **Opção A:** Usar domínio próprio na Cloudflare (URL fixa)
- **Opção B:** Adaptar scripts para capturar nova URL automaticamente

### Provider de Concorrentes

- ⚠️ Concorrentes são simulados (mock)
- ⚠️ API Mercado Livre retorna 403
- ⚠️ Shopee Playwright não funciona via subprocess

**Impacto:**
- ✅ Auditoria funciona (com dados simulados)
- ✅ Sentinela funciona (com dados simulados)
- ⚠️ Dados não são reais

---

## 🚀 Próximos Passos

### 1. Testar Bot

- [ ] Enviar `/menu` de outro número
- [ ] Verificar se responde
- [ ] Testar outros comandos

### 2. Commitar Workaround

```powershell
git add docker-compose.local.yml docker-compose.prod.yml WORKAROUND_EVOLUTION_QR.md
git commit -m "fix: aplicar workaround Evolution API v2.1.1 para QR Code"
```

### 3. Decidir sobre Auto-Start

Antes de instalar `install-startup-task.ps1` e `install-watchdog-task.ps1`:
- Decidir se vai usar domínio próprio
- Ou adaptar scripts para URL temporária

### 4. Documentar Processo

- [ ] Atualizar README com instruções de deploy local
- [ ] Documentar workarounds aplicados
- [ ] Criar guia de troubleshooting

---

## 📚 Arquivos Criados

- ✅ `docker-compose.local.yml` - Compose para deploy local
- ✅ `.env.local` - Variáveis de ambiente
- ✅ `deploy/local/start-bot.ps1` - Script de inicialização
- ✅ `deploy/local/stop-bot.ps1` - Script para parar
- ✅ `deploy/local/status-bot.ps1` - Script de status
- ✅ `deploy/local/watchdog.ps1` - Script de monitoramento
- ✅ `deploy/local/install-startup-task.ps1` - Instalar auto-start
- ✅ `deploy/local/install-watchdog-task.ps1` - Instalar watchdog
- ✅ `deploy/local/README.md` - Documentação completa
- ✅ `deploy/local/generate-keys.ps1` - Gerar chaves
- ✅ `deploy/local/check-config.ps1` - Verificar configuração
- ✅ `WORKAROUND_EVOLUTION_QR.md` - Documentação do workaround
- ✅ `INICIAR_BOT_LOCAL.md` - Guia rápido
- ✅ `FLUXO_COMPLETO_AGORA.md` - Fluxo completo
- ✅ `INSTALAR_CLOUDFLARED.md` - Guia de instalação
- ✅ `CONFIGURAR_URL_PUBLICA.md` - Guia de configuração
- ✅ `qrcode.png` - QR Code gerado

---

## 🎯 Comandos Úteis

### Gerenciar Bot

```powershell
# Iniciar
.\deploy\local\start-bot.ps1

# Parar
.\deploy\local\stop-bot.ps1

# Status
.\deploy\local\status-bot.ps1
```

### Ver Logs

```powershell
# Bot
docker logs shopee_api_local -f

# Evolution
docker logs shopee_evolution_local -f

# Postgres
docker logs shopee_postgres_local -f
```

### Webhook

```powershell
# Reconfigurar
$apiKey = (Get-Content .env.local | Where-Object { $_ -match '^EVOLUTION_API_KEY=' }) -replace '^EVOLUTION_API_KEY=', ''
$apiKey = $apiKey.Trim()
$publicUrl = (Get-Content .env.local | Where-Object { $_ -match '^SHOPEE_API_PUBLIC_URL=' }) -replace '^SHOPEE_API_PUBLIC_URL=', ''
$publicUrl = $publicUrl.Trim()
$webhookUrl = "$publicUrl/webhook/evolution"

$body = @{
  webhook = @{
    enabled = $true
    url = $webhookUrl
    webhookByEvents = $false
    webhookBase64 = $false
    events = @("MESSAGES_UPSERT", "CONNECTION_UPDATE", "SEND_MESSAGE")
  }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri "http://localhost:8080/webhook/set/shopee_booster" -Method POST -Headers @{ apikey = $apiKey } -ContentType "application/json" -Body $body

# Verificar
Invoke-RestMethod -Uri "http://localhost:8080/webhook/find/shopee_booster" -Method GET -Headers @{ apikey = $apiKey }
```

### Status WhatsApp

```powershell
Invoke-RestMethod -Uri "http://localhost:8787/evolution/instance-status" -Method GET
```

---

## ✅ Conclusão

O deploy local está **funcionando** e pronto para testes!

**Próximo passo:** Enviar `/menu` de outro número no WhatsApp e verificar se o bot responde.

---

**Data:** 27/04/2026  
**Status:** ✅ SUCESSO  
**Versão Bot:** 0.2.0  
**Versão Evolution:** 2.1.1  
