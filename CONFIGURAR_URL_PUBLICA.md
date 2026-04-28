# 🌐 Configurar URL Pública - AGORA

## ⚡ Opção 1: Tunnel Temporário (Recomendado para Testar)

### Passo 1: Abrir PowerShell Separado

Abra um **NOVO PowerShell** (deixe o atual aberto) e execute:

```powershell
cd "C:\Users\Defal\Documents\Faculdade\Projeto Shopee"
.\deploy\local\start-tunnel-temp.ps1
```

**OU** execute diretamente:

```powershell
cloudflared tunnel --url http://localhost:8787
```

### Passo 2: Copiar URL

O comando vai mostrar algo assim:

```
2026-04-27T18:45:00Z INF +--------------------------------------------------------------------------------------------+
2026-04-27T18:45:00Z INF |  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |
2026-04-27T18:45:00Z INF |  https://purple-river-example-1234.trycloudflare.com                                       |
2026-04-27T18:45:00Z INF +--------------------------------------------------------------------------------------------+
```

**COPIE** a URL `https://....trycloudflare.com`

### Passo 3: Editar .env.local

No PowerShell original:

```powershell
notepad .env.local
```

Encontre a linha:

```env
SHOPEE_API_PUBLIC_URL=https://SEU_DOMINIO_AQUI
```

Substitua por:

```env
SHOPEE_API_PUBLIC_URL=https://purple-river-example-1234.trycloudflare.com
```

**⚠️ IMPORTANTE:**
- Use a URL que **você copiou** (não a do exemplo acima)
- **NÃO adicione** `/webhook/evolution` no final
- A URL deve começar com `https://`

**Salve e feche** o Notepad.

### Passo 4: Verificar

```powershell
.\deploy\local\check-config.ps1
```

Agora deve passar! ✅

### ⚠️ Lembre-se:

- **DEIXE o PowerShell com `cloudflared` RODANDO**
- Se fechar, a URL para de funcionar
- Se reiniciar, a URL muda (precisa atualizar .env.local)

---

## 🏢 Opção 2: Tunnel Fixo (Melhor para Produção)

### Pré-requisito:
- Ter um domínio na Cloudflare

### Passo 1: Criar Tunnel no Dashboard

1. Acesse: https://one.dash.cloudflare.com/
2. Vá em **Zero Trust > Networks > Tunnels**
3. Clique em **Create a tunnel**
4. Nome: `shopee-booster-bot`
5. Escolha **Cloudflared** como connector
6. **Copie o token** que aparece

### Passo 2: Configurar Public Hostname

No mesmo painel do tunnel:

1. Clique em **Public Hostname**
2. Clique em **Add a public hostname**
3. Preencha:
   - **Subdomain:** `bot` (ou outro nome)
   - **Domain:** `seudominio.com` (seu domínio)
   - **Service Type:** `HTTP`
   - **URL:** `host.docker.internal:8787`
4. Salve

### Passo 3: Editar .env.local

```powershell
notepad .env.local
```

Atualize:

```env
SHOPEE_API_PUBLIC_URL=https://bot.seudominio.com
```

**Salve e feche.**

### Passo 4: Verificar

```powershell
.\deploy\local\check-config.ps1
```

### ✅ Vantagens:

- URL fixa (não muda)
- Mais estável
- Não precisa deixar `cloudflared` rodando manualmente
- O container `cloudflared` no Docker Compose cuida disso

---

## 🎯 Qual Escolher?

| Opção | Quando Usar |
|-------|-------------|
| **Tunnel Temporário** | Testar agora, não tem domínio |
| **Tunnel Fixo** | Produção, tem domínio na Cloudflare |

---

## 📝 Resumo Rápido (Tunnel Temporário)

```powershell
# PowerShell 1 (novo)
cloudflared tunnel --url http://localhost:8787
# Copie a URL https://....trycloudflare.com

# PowerShell 2 (original)
notepad .env.local
# Cole a URL em SHOPEE_API_PUBLIC_URL=https://....trycloudflare.com
# Salve e feche

.\deploy\local\check-config.ps1
# Deve passar agora!
```

---

## ⚠️ Troubleshooting

### cloudflared não encontrado

```powershell
winget install --id Cloudflare.cloudflared
```

### Tunnel não conecta

```powershell
# Verificar se porta 8787 está livre
netstat -ano | findstr :8787

# Se estiver ocupada, pare o que estiver usando
```

---

**Escolha uma opção e configure agora!** 🚀
