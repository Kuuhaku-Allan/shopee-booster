# Deploy Local 24/7 - ShopeeBooster WhatsApp Bot

## 📋 Visão Geral

Deploy local do ShopeeBooster WhatsApp Bot no Windows com inicialização automática, watchdog e Cloudflare Tunnel.

**Arquitetura:**
```
Seu PC Windows
│
├── Docker Desktop / WSL2
│   ├── shopee_api (FastAPI - porta 8787)
│   ├── evolution_api (WhatsApp - porta 8080)
│   ├── postgres (Banco Evolution)
│   └── cloudflared (Cloudflare Tunnel)
│
├── Task Scheduler do Windows
│   ├── Startup: Inicia bot no login
│   └── Watchdog: Monitora a cada 5 minutos
│
└── Cloudflare Tunnel
    └── https://bot.seudominio.com → localhost:8787
```

**Vantagens:**
- ✅ Inicia automaticamente no boot/login
- ✅ Watchdog monitora e recupera automaticamente
- ✅ HTTPS via Cloudflare Tunnel (sem abrir portas)
- ✅ Não precisa de IP fixo
- ✅ Volumes persistentes (não perde dados)
- ✅ Restart automático de containers

**Limitações:**
- ⚠️ PC precisa estar ligado e logado
- ⚠️ Depende de energia e internet estáveis
- ⚠️ QR Code precisa ser escaneado manualmente se desconectar

---

## 🚀 Instalação

### Pré-requisitos

- [x] Windows 10/11
- [x] Docker Desktop instalado
- [x] WSL2 configurado
- [x] Git instalado
- [x] PowerShell 5.1+

### Passo 1: Clonar Repositório

```powershell
cd "C:\Users\Defal\Documents\Faculdade"
git clone -b feature/whatsapp-bot-core https://github.com/Kuuhaku-Allan/shopee-booster.git "Projeto Shopee"
cd "Projeto Shopee"
```

### Passo 2: Criar .env.local

```powershell
cp .env.example.local .env.local
notepad .env.local
```

**Preencha as variáveis obrigatórias:**

```env
# Evolution API Key
EVOLUTION_API_KEY=<gerar com: python -c "import secrets; print(secrets.token_hex(32))">

# Postgres Password
POSTGRES_PASSWORD=<senha forte única>

# Bot Secret Key (Fernet)
BOT_SECRET_KEY=<gerar com: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">

# Cloudflare Tunnel Token
CLOUDFLARE_TUNNEL_TOKEN=<obter em: https://one.dash.cloudflare.com/>

# URL pública (será fornecida pelo Cloudflare Tunnel)
SHOPEE_API_PUBLIC_URL=https://bot.seudominio.com
```

### Passo 3: Configurar Cloudflare Tunnel

#### Opção A: Via Dashboard (Recomendado)

1. Acesse: https://one.dash.cloudflare.com/
2. Vá em **Access > Tunnels**
3. Clique em **Create a tunnel**
4. Nome: `shopee-booster-bot`
5. Escolha **Docker** como connector
6. Copie o **token** que aparece no comando
7. Cole o token em `.env.local` na variável `CLOUDFLARE_TUNNEL_TOKEN`
8. Configure o **Public Hostname**:
   - **Subdomain:** bot (ou outro)
   - **Domain:** seudominio.com (ou use subdomínio gratuito)
   - **Service:** http://host.docker.internal:8787
9. Salve

#### Opção B: Via CLI

```powershell
# Instalar cloudflared
winget install --id Cloudflare.cloudflared

# Autenticar
cloudflared tunnel login

# Criar tunnel
cloudflared tunnel create shopee-booster-bot

# Obter token
cloudflared tunnel token shopee-booster-bot
```

### Passo 4: Testar Manualmente

```powershell
# Iniciar bot
.\deploy\local\start-bot.ps1

# Aguardar containers ficarem healthy (1-2 minutos)

# Verificar status
.\deploy\local\status-bot.ps1

# Escanear QR Code
# Abra: http://localhost:8080/instance/connect/shopee_booster
# Escaneie com WhatsApp

# Testar bot
# Envie /menu no WhatsApp
```

### Passo 5: Instalar Tarefas Automáticas

**IMPORTANTE:** Execute como Administrador!

```powershell
# Clique com botão direito no PowerShell
# Selecione "Executar como Administrador"

# Instalar tarefa de inicialização (no login)
.\deploy\local\install-startup-task.ps1

# Instalar tarefa de watchdog (a cada 5 minutos)
.\deploy\local\install-watchdog-task.ps1
```

### Passo 6: Criar Atalhos na Área de Trabalho

**Atalho 1: Ligar ShopeeBooster Bot**

1. Clique com botão direito na Área de Trabalho
2. Novo > Atalho
3. Localização:
   ```
   powershell.exe -ExecutionPolicy Bypass -File "C:\Users\Defal\Documents\Faculdade\Projeto Shopee\deploy\local\start-bot.ps1"
   ```
4. Nome: `Ligar ShopeeBooster Bot`
5. Ícone: Escolha um ícone (opcional)

**Atalho 2: Desligar ShopeeBooster Bot**

1. Clique com botão direito na Área de Trabalho
2. Novo > Atalho
3. Localização:
   ```
   powershell.exe -ExecutionPolicy Bypass -File "C:\Users\Defal\Documents\Faculdade\Projeto Shopee\deploy\local\stop-bot.ps1"
   ```
4. Nome: `Desligar ShopeeBooster Bot`
5. Ícone: Escolha um ícone (opcional)

**Atalho 3: Status ShopeeBooster Bot**

1. Clique com botão direito na Área de Trabalho
2. Novo > Atalho
3. Localização:
   ```
   powershell.exe -ExecutionPolicy Bypass -File "C:\Users\Defal\Documents\Faculdade\Projeto Shopee\deploy\local\status-bot.ps1"
   ```
4. Nome: `Status ShopeeBooster Bot`
5. Ícone: Escolha um ícone (opcional)

---

## 🔧 Uso Diário

### Iniciar Bot

**Opção 1:** Duplo clique no atalho `Ligar ShopeeBooster Bot`

**Opção 2:** PowerShell
```powershell
.\deploy\local\start-bot.ps1
```

### Parar Bot

**Opção 1:** Duplo clique no atalho `Desligar ShopeeBooster Bot`

**Opção 2:** PowerShell
```powershell
# Parar (mantém dados)
.\deploy\local\stop-bot.ps1

# Parar e remover containers
.\deploy\local\stop-bot.ps1 -Down
```

### Ver Status

**Opção 1:** Duplo clique no atalho `Status ShopeeBooster Bot`

**Opção 2:** PowerShell
```powershell
.\deploy\local\status-bot.ps1
```

### Ver Logs

```powershell
# Todos os serviços
docker compose -f docker-compose.local.yml --env-file .env.local logs -f

# Apenas ShopeeBooster API
docker compose -f docker-compose.local.yml --env-file .env.local logs -f shopee_api

# Apenas Evolution API
docker compose -f docker-compose.local.yml --env-file .env.local logs -f evolution_api

# Ver logs de erro
docker compose -f docker-compose.local.yml --env-file .env.local logs -f | Select-String "ERROR"
```

---

## 🤖 Watchdog

O watchdog monitora o bot a cada 5 minutos e:

- ✅ Verifica se Docker está rodando
- ✅ Verifica se containers estão healthy
- ✅ Testa health checks (/health)
- ✅ Verifica status do WhatsApp
- ✅ Reconfigura webhook se necessário
- ✅ Reinicia serviços automaticamente se falharem
- ✅ Envia alertas via Telegram (se configurado)

**Logs do watchdog:**
```
C:\Users\Defal\Documents\Faculdade\Projeto Shopee\deploy\local\logs\watchdog.log
```

**Ver logs do watchdog:**
```powershell
Get-Content ".\deploy\local\logs\watchdog.log" -Tail 50
```

**Testar watchdog manualmente:**
```powershell
.\deploy\local\watchdog.ps1
```

---

## ⚙️ Configuração Avançada

### Iniciar no Boot (sem login)

Se você quer que o bot inicie mesmo sem fazer login no Windows:

1. Configure Windows para login automático
2. OU configure a tarefa para rodar no boot do sistema:

```powershell
# Execute como Administrador
$TaskName = "ShopeeBooster Bot - Startup"
$Trigger = New-ScheduledTaskTrigger -AtStartup
Set-ScheduledTask -TaskName $TaskName -Trigger $Trigger
```

### Configurar BIOS para Ligar Após Queda de Energia

1. Reinicie o PC e entre no BIOS/UEFI (geralmente F2, F10, Del)
2. Procure por:
   - `Restore on AC Power Loss`
   - `AC Power Recovery`
   - `Power On after Power Failure`
3. Configure como: `Power On` ou `Last State`
4. Salve e saia

**NOTA:** Nem todos os PCs/notebooks têm essa opção.

### Alterar Intervalo do Watchdog

Por padrão, o watchdog roda a cada 5 minutos. Para alterar:

```powershell
# Execute como Administrador
$TaskName = "ShopeeBooster Bot - Watchdog"
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration ([TimeSpan]::MaxValue)
Set-ScheduledTask -TaskName $TaskName -Trigger $Trigger
```

---

## 🔍 Troubleshooting

### Docker não inicia

```powershell
# Verificar se Docker Desktop está instalado
docker --version

# Iniciar Docker Desktop manualmente
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"

# Aguardar 60 segundos
Start-Sleep -Seconds 60

# Verificar novamente
docker info
```

### Containers não iniciam

```powershell
# Ver logs
docker compose -f docker-compose.local.yml --env-file .env.local logs

# Rebuild forçado
docker compose -f docker-compose.local.yml --env-file .env.local up -d --build --force-recreate

# Verificar .env.local
notepad .env.local
```

### WhatsApp desconectou

1. Abra: http://localhost:8080/instance/connect/shopee_booster
2. Escaneie o QR Code novamente no WhatsApp
3. Aguarde conexão
4. Teste: `/menu` no WhatsApp

### Cloudflare Tunnel não funciona

```powershell
# Verificar se container está rodando
docker ps | Select-String "cloudflared"

# Ver logs
docker logs shopee_cloudflared

# Verificar token no .env.local
notepad .env.local

# Reiniciar tunnel
docker compose -f docker-compose.local.yml --env-file .env.local restart cloudflared
```

### Webhook não funciona

```powershell
# Reconfigurar webhook
Invoke-RestMethod -Uri "http://localhost:8787/evolution/setup-webhook" -Method Post -Body '{"user_id":"admin","shop_uid":"setup"}' -ContentType "application/json"

# Verificar URL pública no .env.local
notepad .env.local

# Testar URL pública
Invoke-RestMethod -Uri "https://bot.seudominio.com/health"
```

---

## 💾 Backup

### Backup Manual

```powershell
# Backup data/
Compress-Archive -Path ".\data" -DestinationPath "backup-data-$(Get-Date -Format 'yyyyMMdd').zip"

# Backup Evolution instances
docker cp shopee_evolution_local:/evolution/instances ./evolution_instances_backup
Compress-Archive -Path ".\evolution_instances_backup" -DestinationPath "backup-evolution-$(Get-Date -Format 'yyyyMMdd').zip"

# Backup Postgres
docker compose -f docker-compose.local.yml --env-file .env.local exec postgres pg_dump -U evolution evolution > "backup-postgres-$(Get-Date -Format 'yyyyMMdd').sql"
```

### Backup Automático

Crie um script `backup.ps1`:

```powershell
$BackupDir = "C:\Backups\ShopeeBooster"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

$Date = Get-Date -Format "yyyyMMdd"
Compress-Archive -Path ".\data" -DestinationPath "$BackupDir\backup-data-$Date.zip" -Force

# Manter apenas últimos 7 backups
Get-ChildItem $BackupDir -Filter "backup-data-*.zip" | Sort-Object LastWriteTime -Descending | Select-Object -Skip 7 | Remove-Item
```

Agende com Task Scheduler para rodar diariamente às 3h da manhã.

---

## 📊 Monitoramento

### Uso de Recursos

```powershell
# Status dos containers
docker compose -f docker-compose.local.yml --env-file .env.local ps

# Uso de recursos
docker stats

# Espaço em disco
Get-PSDrive C
```

### Logs

```powershell
# Logs do bot
Get-Content ".\deploy\local\logs\start-bot.log" -Tail 50

# Logs do watchdog
Get-Content ".\deploy\local\logs\watchdog.log" -Tail 50

# Logs dos containers
docker compose -f docker-compose.local.yml --env-file .env.local logs -f
```

---

## ⚠️ Limitações Conhecidas

### Provider de Concorrentes (Mock)

- ⚠️ Concorrentes são simulados (não reais)
- ⚠️ API Mercado Livre retorna 403 Forbidden
- ⚠️ Shopee Playwright não funciona via subprocess

**Impacto:**
- ✅ Auditoria funciona (com concorrentes simulados)
- ✅ Sentinela funciona (com concorrentes simulados)
- ⚠️ Dados não são reais

**Solução futura:**
- Corrigir API do Mercado Livre
- Implementar scraping via proxy
- Usar .exe local para scraping real

### Dependência de PC Ligado

- ⚠️ PC precisa estar ligado e logado
- ⚠️ Depende de energia estável
- ⚠️ Depende de internet estável

**Recomendação:**
- Configure BIOS para ligar após queda de energia
- Use no-break (UPS) se possível
- Configure login automático do Windows

---

## 📚 Arquivos

- `docker-compose.local.yml` - Configuração Docker Compose
- `.env.example.local` - Template de variáveis de ambiente
- `start-bot.ps1` - Inicia o bot
- `stop-bot.ps1` - Para o bot
- `status-bot.ps1` - Verifica status do bot
- `watchdog.ps1` - Monitora e recupera o bot
- `install-startup-task.ps1` - Instala tarefa de inicialização
- `install-watchdog-task.ps1` - Instala tarefa de watchdog
- `README.md` - Este arquivo

---

## 🤝 Suporte

### Comandos Úteis

```powershell
# Ver tarefas agendadas
Get-ScheduledTask | Where-Object { $_.TaskName -like "*ShopeeBooster*" }

# Executar tarefa manualmente
Start-ScheduledTask -TaskName "ShopeeBooster Bot - Startup"
Start-ScheduledTask -TaskName "ShopeeBooster Bot - Watchdog"

# Desinstalar tarefas
Unregister-ScheduledTask -TaskName "ShopeeBooster Bot - Startup" -Confirm:$false
Unregister-ScheduledTask -TaskName "ShopeeBooster Bot - Watchdog" -Confirm:$false

# Limpar containers e volumes
docker compose -f docker-compose.local.yml --env-file .env.local down -v
```

---

**Deploy Local 24/7 - ShopeeBooster WhatsApp Bot**

**Status:** Pronto para uso  
**Plataforma:** Windows 10/11  
**Custo:** R$ 0,00 (apenas energia elétrica)

**O Bot roda 24/7 no seu PC com inicialização e recuperação automáticas!** 🚀
