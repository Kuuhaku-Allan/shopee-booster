# start-bot.ps1 - Inicia o ShopeeBooster Bot localmente
# Este script é chamado automaticamente no boot/login do Windows

param(
    [switch]$Silent = $false
)

# Configurações
$ProjectPath = "C:\Users\Defal\Documents\Faculdade\Projeto Shopee"
$ComposeFile = "docker-compose.local.yml"
$EnvFile = ".env.local"
$LogFile = "$ProjectPath\deploy\local\logs\start-bot.log"

# Criar diretório de logs se não existir
$LogDir = Split-Path -Parent $LogFile
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

# Função para log
function Write-Log {
    param($Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogMessage = "[$Timestamp] $Message"
    Add-Content -Path $LogFile -Value $LogMessage
    if (-not $Silent) {
        Write-Host $LogMessage
    }
}

Write-Log "════════════════════════════════════════════════════════════"
Write-Log "ShopeeBooster Bot - Iniciando..."
Write-Log "════════════════════════════════════════════════════════════"

# Verificar se Docker está rodando
Write-Log "Verificando Docker..."
try {
    $dockerInfo = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Log "❌ Docker não está rodando!"
        Write-Log "Iniciando Docker Desktop..."
        Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        Write-Log "Aguardando Docker iniciar (60 segundos)..."
        Start-Sleep -Seconds 60
        
        # Verificar novamente
        $dockerInfo = docker info 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Log "❌ Falha ao iniciar Docker!"
            exit 1
        }
    }
    Write-Log "✅ Docker está rodando"
} catch {
    Write-Log "❌ Erro ao verificar Docker: $_"
    exit 1
}

# Ir para diretório do projeto
Write-Log "Navegando para: $ProjectPath"
Set-Location $ProjectPath

# Verificar se arquivos existem
if (-not (Test-Path $ComposeFile)) {
    Write-Log "❌ Arquivo não encontrado: $ComposeFile"
    exit 1
}

if (-not (Test-Path $EnvFile)) {
    Write-Log "❌ Arquivo não encontrado: $EnvFile"
    Write-Log "Copie .env.example.local para .env.local e configure!"
    exit 1
}

Write-Log "✅ Arquivos encontrados"

# Criar diretórios necessários
Write-Log "Criando diretórios necessários..."
$Directories = @("data", "data/reports", "uploads", "uploads/catalogs", "evolution_instances", "evolution_store", "postgres_data")
foreach ($Dir in $Directories) {
    if (-not (Test-Path $Dir)) {
        New-Item -ItemType Directory -Path $Dir -Force | Out-Null
        Write-Log "  Criado: $Dir"
    }
}

# Iniciar containers
Write-Log "Iniciando containers..."
try {
    docker compose -f $ComposeFile --env-file $EnvFile up -d 2>&1 | ForEach-Object {
        Write-Log "  $_"
    }
    
    if ($LASTEXITCODE -ne 0) {
        Write-Log "❌ Falha ao iniciar containers!"
        exit 1
    }
    
    Write-Log "✅ Containers iniciados"
} catch {
    Write-Log "❌ Erro ao iniciar containers: $_"
    exit 1
}

# Aguardar containers ficarem healthy
Write-Log "Aguardando containers ficarem healthy (até 60 segundos)..."
$MaxWait = 60
$Elapsed = 0
$AllHealthy = $false

while ($Elapsed -lt $MaxWait) {
    Start-Sleep -Seconds 5
    $Elapsed += 5
    
    try {
        $ContainerStatus = docker compose -f $ComposeFile --env-file $EnvFile ps --format json | ConvertFrom-Json
        
        $PostgresHealthy = ($ContainerStatus | Where-Object { $_.Service -eq "postgres" }).Health -eq "healthy"
        $EvolutionHealthy = ($ContainerStatus | Where-Object { $_.Service -eq "evolution_api" }).Health -eq "healthy"
        $ApiHealthy = ($ContainerStatus | Where-Object { $_.Service -eq "shopee_api" }).Health -eq "healthy"
        
        Write-Log "  Postgres: $(if ($PostgresHealthy) { 'healthy' } else { 'starting' }) | Evolution: $(if ($EvolutionHealthy) { 'healthy' } else { 'starting' }) | API: $(if ($ApiHealthy) { 'healthy' } else { 'starting' })"
        
        if ($PostgresHealthy -and $EvolutionHealthy -and $ApiHealthy) {
            $AllHealthy = $true
            break
        }
    } catch {
        Write-Log "  Aguardando containers..."
    }
}

if ($AllHealthy) {
    Write-Log "✅ Todos os containers estão healthy!"
} else {
    Write-Log "⚠️  Timeout aguardando containers ficarem healthy"
    Write-Log "Verifique os logs: docker compose -f $ComposeFile --env-file $EnvFile logs"
}

# Testar health checks
Write-Log "Testando health checks..."

Start-Sleep -Seconds 5

try {
    $ApiHealth = Invoke-RestMethod -Uri "http://localhost:8787/health" -Method Get -TimeoutSec 10
    Write-Log "✅ ShopeeBooster API: OK"
} catch {
    Write-Log "❌ ShopeeBooster API: FALHOU"
    Write-Log "  Erro: $_"
}

try {
    $EvolutionHealth = Invoke-RestMethod -Uri "http://localhost:8080/" -Method Get -TimeoutSec 10
    Write-Log "✅ Evolution API: OK"
} catch {
    Write-Log "❌ Evolution API: FALHOU"
    Write-Log "  Erro: $_"
}

# Configurar webhook
Write-Log "Configurando webhook..."
try {
    $WebhookResponse = Invoke-RestMethod -Uri "http://localhost:8787/evolution/setup-webhook" -Method POST -TimeoutSec 10
    
    if ($WebhookResponse.ok) {
        Write-Log "✅ Webhook configurado: $($WebhookResponse.webhook_url)"
    } else {
        Write-Log "⚠️  Webhook não configurado: $($WebhookResponse.error)"
    }
} catch {
    Write-Log "⚠️  Erro ao configurar webhook: $_"
}

# Verificar status da instância WhatsApp
Write-Log "Verificando instância WhatsApp..."
try {
    $InstanceStatus = Invoke-RestMethod -Uri "http://localhost:8787/evolution/instance-status" -Method Get -TimeoutSec 10
    
    if ($InstanceStatus.ok) {
        Write-Log "✅ Instância WhatsApp: $($InstanceStatus.state)"
        
        if ($InstanceStatus.state -eq "close") {
            Write-Log "⚠️  WhatsApp desconectado! Gerando QR Code..."
            try {
                # Gerar QR Code e salvar como arquivo
                $QrResponse = Invoke-RestMethod -Uri "http://localhost:8787/evolution/qrcode" -Method Get -TimeoutSec 15
                Write-Log "✅ QR Code disponível em: http://localhost:8787/evolution/qrcode"
                Write-Log "📱 AÇÃO NECESSÁRIA: Escaneie o QR Code para conectar o WhatsApp!"
            } catch {
                Write-Log "❌ Erro ao gerar QR Code: $_"
            }
        }
    } else {
        Write-Log "❌ Erro ao verificar instância: $($InstanceStatus.error)"
    }
} catch {
    Write-Log "⚠️  Erro ao verificar instância WhatsApp: $_"
}

Write-Log "════════════════════════════════════════════════════════════"
Write-Log "ShopeeBooster Bot iniciado com sucesso!"
Write-Log "════════════════════════════════════════════════════════════"
Write-Log ""
Write-Log "Serviços rodando:"
Write-Log "  - ShopeeBooster API: http://localhost:8787"
Write-Log "  - Evolution API: http://localhost:8080"
Write-Log "  - Postgres: localhost:5432"
Write-Log ""
Write-Log "Comandos úteis:"
Write-Log "  - Ver logs: docker compose -f $ComposeFile --env-file $EnvFile logs -f"
Write-Log "  - Ver status: docker compose -f $ComposeFile --env-file $EnvFile ps"
Write-Log "  - Parar: .\deploy\local\stop-bot.ps1"
Write-Log ""

if (-not $Silent) {
    Write-Host ""
    Write-Host "Pressione qualquer tecla para fechar..." -ForegroundColor Green
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

exit 0
