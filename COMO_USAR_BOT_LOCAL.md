# 🚀 Como Usar o ShopeeBooster Bot Local

## 📋 Guia Rápido

### ▶️ **Ligar o Bot**
```
Duplo clique em: "Ligar Bot.bat"
```
- Inicia Docker Desktop automaticamente
- Sobe todos os containers (Postgres, Evolution API, ShopeeBooster API)
- Configura webhook automaticamente
- Verifica status do WhatsApp

### ⏹️ **Desligar o Bot**
```
Duplo clique em: "Desligar Bot.bat"
```
- Para todos os containers
- Mantém dados salvos

### 📊 **Ver Status**
```
Duplo clique em: "Status Bot.bat"
```
- Mostra status de todos os serviços
- Indica se WhatsApp está conectado
- Mostra URLs de acesso

### 📱 **Conectar WhatsApp**
```
Duplo clique em: "Abrir QR Code.bat"
```
- Abre QR Code no navegador
- Escaneie com WhatsApp do celular
- Conexão é automática

---

## 🔧 Comandos Avançados

### 🔍 **Ver Logs em Tempo Real**
```powershell
docker compose -f docker-compose.local.yml --env-file .env.local logs -f
```

### 🔄 **Reiniciar Apenas a API**
```powershell
docker compose -f docker-compose.local.yml --env-file .env.local restart shopee_api
```

### 🌐 **Verificar URL Pública**
```powershell
# Ver URL atual
Get-Content .env.local | Select-String "SHOPEE_API_PUBLIC_URL"

# Atualizar URL manualmente
.\deploy\local\update-env-url.ps1 -NewUrl "https://nova-url.trycloudflare.com"
```

---

## 🛠️ Resolução de Problemas

### ❌ **Bot não responde no WhatsApp**

1. **Verificar se WhatsApp está conectado:**
   ```
   Duplo clique em: "Status Bot.bat"
   ```

2. **Se aparecer "close" ou "connecting":**
   ```
   Duplo clique em: "Abrir QR Code.bat"
   Escaneie o QR Code novamente
   ```

3. **Verificar webhook:**
   ```powershell
   Invoke-RestMethod -Uri "http://localhost:8787/evolution/setup-webhook" -Method POST
   ```

### 🔄 **Após reiniciar o PC**

1. **Ligar o bot normalmente:**
   ```
   Duplo clique em: "Ligar Bot.bat"
   ```

2. **Se a URL pública mudou:**
   - O sistema detecta automaticamente
   - Reconfigura webhook sozinho
   - Não precisa fazer nada manual

### 🆔 **Novo LID do WhatsApp**

Se aparecer erro como `"220035536678945@lid não encontrado"`:

1. **Adicionar no arquivo de mapeamento:**
   ```json
   // Editar: data/lid_map.json
   {
     "220035536678945@lid": "5511988600050@s.whatsapp.net",
     "NOVO_LID@lid": "SEU_NUMERO@s.whatsapp.net"
   }
   ```

2. **Ou adicionar no .env.local:**
   ```
   EVOLUTION_LID_MAP=220035536678945@lid=5511988600050@s.whatsapp.net,NOVO_LID@lid=SEU_NUMERO@s.whatsapp.net
   ```

3. **Reiniciar API:**
   ```powershell
   docker compose -f docker-compose.local.yml --env-file .env.local restart shopee_api
   ```

---

## 📂 Estrutura de Arquivos

```
📁 Projeto Shopee/
├── 🚀 Ligar Bot.bat           # Iniciar bot
├── ⏹️ Desligar Bot.bat        # Parar bot  
├── 📊 Status Bot.bat          # Ver status
├── 📱 Abrir QR Code.bat       # QR WhatsApp
├── 📄 .env.local              # Configurações
├── 📄 data/lid_map.json       # Mapeamento LID
└── 📁 deploy/local/
    ├── 📄 start-bot.ps1       # Script principal
    ├── 📄 stop-bot.ps1        # Parar serviços
    ├── 📄 status-bot.ps1      # Verificar status
    ├── 📄 watchdog.ps1        # Monitoramento
    └── 📁 logs/
        ├── 📄 start-bot.log   # Logs de inicialização
        ├── 📄 watchdog.log    # Logs de monitoramento
        └── 📄 tunnel.log      # Logs do Cloudflare
```

---

## 🤖 Automação (Opcional)

### ⚙️ **Instalar Inicialização Automática**
```powershell
# Executar como Administrador
.\deploy\local\install-startup-task.ps1
.\deploy\local\install-watchdog-task.ps1
```

**O que faz:**
- Bot liga automaticamente no boot do Windows
- Monitora saúde a cada 5 minutos
- Recupera automaticamente de falhas
- Reconfigura webhook se necessário

### 🔍 **Verificar Tarefas Automáticas**
```powershell
# Ver tarefas instaladas
Get-ScheduledTask | Where-Object { $_.TaskName -like "*ShopeeBooster*" }

# Ver logs das tarefas
Get-WinEvent -LogName "Microsoft-Windows-TaskScheduler/Operational" | Where-Object { $_.Message -like "*ShopeeBooster*" }
```

---

## 📞 URLs de Acesso

| Serviço | URL | Descrição |
|---------|-----|-----------|
| **ShopeeBooster API** | http://localhost:8787 | API principal |
| **Evolution API** | http://localhost:8080 | WhatsApp API |
| **QR Code WhatsApp** | http://localhost:8787/evolution/qrcode | Conectar WhatsApp |
| **Health Check** | http://localhost:8787/health | Status da API |
| **Documentação** | http://localhost:8787/docs | Swagger/OpenAPI |

---

## 🎯 Comandos do WhatsApp

Envie estas mensagens no WhatsApp para testar:

| Comando | Descrição |
|---------|-----------|
| `/menu` | Menu principal |
| `/otimizar` | Otimizar produtos |
| `/sentinela` | Monitoramento |
| `/ajuda` | Ajuda completa |

---

## 📝 Logs Importantes

### 📄 **Ver Logs de Inicialização**
```powershell
Get-Content "deploy\local\logs\start-bot.log" -Tail 50
```

### 📄 **Ver Logs do Watchdog**
```powershell
Get-Content "deploy\local\logs\watchdog.log" -Tail 50
```

### 📄 **Ver Logs do Docker**
```powershell
docker compose -f docker-compose.local.yml --env-file .env.local logs --tail 100
```

---

## ✅ Checklist de Funcionamento

- [ ] Docker Desktop instalado e rodando
- [ ] Cloudflared instalado (`winget install --id Cloudflare.cloudflared`)
- [ ] Arquivo `.env.local` configurado
- [ ] Containers sobem sem erro (`Ligar Bot.bat`)
- [ ] WhatsApp conectado (QR Code escaneado)
- [ ] Bot responde `/menu` no WhatsApp
- [ ] URL pública funcionando (webhook configurado)

**Se todos os itens estão ✅, o bot está 100% funcional!**