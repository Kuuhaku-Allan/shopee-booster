# 📦 Instalar Cloudflared - Passo a Passo

## ⚡ Opção 1: Instalar via winget (Recomendado)

### Passo 1: Instalar

```powershell
winget install --id Cloudflare.cloudflared
```

### Passo 2: Fechar e Reabrir PowerShell

**IMPORTANTE:** Feche o PowerShell e abra novamente para o PATH ser atualizado.

### Passo 3: Verificar Instalação

```powershell
cloudflared --version
```

**Esperado:** Deve mostrar a versão (ex: `cloudflared version 2024.x.x`)

Se aparecer a versão, está instalado! ✅

---

## 🔧 Opção 2: Instalação Manual (Se winget não funcionar)

### Passo 1: Baixar

Acesse: https://github.com/cloudflare/cloudflared/releases/latest

Baixe: `cloudflared-windows-amd64.exe`

### Passo 2: Criar Pasta

```powershell
mkdir C:\Cloudflared
```

### Passo 3: Mover e Renomear

1. Mova o arquivo baixado para `C:\Cloudflared\`
2. Renomeie para `cloudflared.exe`

### Passo 4: Testar

```powershell
C:\Cloudflared\cloudflared.exe --version
```

### Passo 5: Adicionar ao PATH (Opcional)

Para não precisar digitar o caminho completo:

```powershell
# Adicionar ao PATH do usuário
$env:Path += ";C:\Cloudflared"
[Environment]::SetEnvironmentVariable("Path", $env:Path, [EnvironmentVariableTarget]::User)
```

Feche e reabra o PowerShell, depois teste:

```powershell
cloudflared --version
```

---

## 🚀 Depois de Instalar

### ⚠️ IMPORTANTE: Ordem Correta

**NÃO inicie o tunnel ainda!** Primeiro precisamos:

1. ✅ Verificar se Docker está rodando
2. ✅ Iniciar o bot localmente
3. ✅ Confirmar que `http://localhost:8787/health` responde
4. ✅ Só então criar o tunnel

### Por quê?

O tunnel vai apontar para `http://localhost:8787`. Se o bot não estiver rodando, o tunnel abre mas não funciona.

---

## 📋 Ordem de Execução Completa

### 1. Instalar cloudflared (você está aqui)

```powershell
winget install --id Cloudflare.cloudflared
```

Feche e reabra o PowerShell.

### 2. Verificar Docker

```powershell
docker info
```

Se não estiver rodando, abra Docker Desktop.

### 3. Iniciar Bot (SEM tunnel ainda)

Por enquanto, vamos deixar a URL pública como está e iniciar o bot localmente:

```powershell
.\deploy\local\start-bot.ps1
```

### 4. Testar Localmente

```powershell
curl http://localhost:8787/health
```

**Esperado:**
```json
{"ok":true,"service":"shopee-booster-bot-api","version":"0.2.0"}
```

### 5. Criar Tunnel (só depois que localhost funcionar)

Abra um **NOVO PowerShell** e execute:

```powershell
cloudflared tunnel --url http://localhost:8787
```

Copie a URL `https://....trycloudflare.com`

### 6. Atualizar .env.local

No PowerShell original:

```powershell
notepad .env.local
```

Atualize:
```env
SHOPEE_API_PUBLIC_URL=https://sua-url-copiada.trycloudflare.com
```

Salve e feche.

### 7. Reconfigurar Webhook

```powershell
Invoke-RestMethod -Uri "http://localhost:8787/evolution/setup-webhook" -Method POST -Body '{"user_id":"admin","shop_uid":"setup"}' -ContentType "application/json"
```

### 8. Conectar WhatsApp

Abra: http://localhost:8080

Escaneie o QR Code.

### 9. Testar

Envie `/menu` no WhatsApp.

---

## 🎯 Resumo Visual

```
1. winget install cloudflared
   ↓
2. Fechar e reabrir PowerShell
   ↓
3. cloudflared --version (verificar)
   ↓
4. docker info (verificar Docker)
   ↓
5. .\deploy\local\start-bot.ps1
   ↓
6. curl http://localhost:8787/health (verificar)
   ↓
7. cloudflared tunnel --url http://localhost:8787 (PowerShell separado)
   ↓
8. Copiar URL e colar em .env.local
   ↓
9. Reconfigurar webhook
   ↓
10. Conectar WhatsApp
```

---

## ⚠️ Troubleshooting

### winget não encontrado

Atualize o App Installer:
1. Abra Microsoft Store
2. Procure por "App Installer"
3. Atualize

Ou use instalação manual (Opção 2).

### cloudflared não encontrado após instalar

Feche e reabra o PowerShell. O PATH só é atualizado em novas sessões.

### Tunnel não conecta

Verifique se `http://localhost:8787` está respondendo primeiro:

```powershell
curl http://localhost:8787/health
```

Se não responder, o bot não está rodando. Execute:

```powershell
.\deploy\local\start-bot.ps1
```

---

**Execute agora e me reporte:**
- ✅ ou ❌ `cloudflared --version` funcionou?
- ✅ ou ❌ Qual opção você usou? (winget ou manual)
