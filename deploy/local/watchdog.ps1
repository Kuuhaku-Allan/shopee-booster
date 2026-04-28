# watchdog.ps1 - Monitora e recupera o ShopeeBooster Bot automaticamente
# Roda a cada 5 minutos via Task Scheduler

# Configurações
$ProjectPath = "C:\Users\Defal\Documents\Faculdade\Projeto Shopee"
$ComposeFile = "docker-compose.local.yml"
$EnvFile = ".env.local"
$LogFile = "$ProjectPath\deploy\local\logs\watchdog.log"
$MaxLogSize = 10MB

# Criar diretório de logs se não existir
$LogDir = Split-Path -Parent $LogFile
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

# Rotacionar log se muito grande
if ((Test-Path $LogFile) -and ((Get-Item $LogFile).Length -gt $MaxLogSize)) {
    $BackupLog = "$LogFile.old"
    if (Test-Path $BackupLog) {
        Remove-Item $BackupLog -Force
    }
    Move-Item $LogFile $BackupLog -Force
}

# Função para log
function Write-Log {
    param($Message, $Level = "INFO")
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogMessage = "[$Timestamp] [$Level] $Message"
    Add-Content -Path $LogFile -Value $LogMessage
}

Write-Log "════════════════════════════════════════════════════════════" "INFO"
Write-Log "Watchdog - Verificando saúde do bot..." "INFO"

# Ir para diretório do projeto
Set-Location $ProjectPath

# 1. Verificar se Docker está rodando
Write-Log "Verificando Docker..." "INFO"
try {
    $dockerInfo = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Docker não está rodando!" "ERROR"
        Write-Log "Tentando iniciar Docker Desktop..." "WARN"
        Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        Start-Sleep -Seconds 60
        
        $dockerInfo = docker info 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Log "Falha ao iniciar Docker!" "ERROR"
            exit 1
        }
        Write-Log "Docker iniciado com sucesso" "INFO"
    }
} catch {
    Write-Log "Erro ao verificar Docker: $_" "ERROR"
    exit 1
}

# 2. Verificar status dos containers
Write-Log "Verificando containers..." "INFO"
try {
    $ContainerStatus = docker compose -f $ComposeFile --env-file $EnvFile ps --format json 2>&1
    
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Erro ao verificar containers" "ERROR"
        Write-Log "Tentando reiniciar containers..." "WARN"
        docker compose -f $ComposeFile --env-file $EnvFile up -d 2>&1 | Out-Null
        Start-Sleep -Seconds 30
    }
} catch {
    Write-Log "Erro ao verificar containers: $_" "ERROR"
}

# 3. Testar ShopeeBooster API
Write-Log "Testando ShopeeBooster API..." "INFO"
$ApiOk = $false
try {
    $ApiHealth = Invoke-RestMethod -Uri "http://localhost:8787/health" -Method Get -TimeoutSec 10
    if ($ApiHealth.ok -eq $true) {
        Write-Log "ShopeeBooster API: OK" "INFO"
        $ApiOk = $true
    } else {
        Write-Log "ShopeeBooster API: resposta inesperada" "WARN"
    }
} catch {
    Write-Log "ShopeeBooster API: FALHOU - $_" "ERROR"
}

# Se API falhou, tentar reiniciar
if (-not $ApiOk) {
    Write-Log "Tentando reiniciar ShopeeBooster API..." "WARN"
    try {
        docker compose -f $ComposeFile --env-file $EnvFile restart shopee_api 2>&1 | Out-Null
        Start-Sleep -Seconds 20
        
        $ApiHealth = Invoke-RestMethod -Uri "http://localhost:8787/health" -Method Get -TimeoutSec 10
        if ($ApiHealth.ok -eq $true) {
            Write-Log "ShopeeBooster API reiniciada com sucesso" "INFO"
            $ApiOk = $true
        }
    } catch {
        Write-Log "Falha ao reiniciar ShopeeBooster API: $_" "ERROR"
    }
}

# 4. Testar Evolution API
Write-Log "Testando Evolution API..." "INFO"
$EvolutionOk = $false
try {
    $EvolutionHealth = Invoke-RestMethod -Uri "http://localhost:8080/" -Method Get -TimeoutSec 10
    Write-Log "Evolution API: OK" "INFO"
    $EvolutionOk = $true
} catch {
    Write-Log "Evolution API: FALHOU - $_" "ERROR"
}

# Se Evolution falhou, tentar reiniciar
if (-not $EvolutionOk) {
    Write-Log "Tentando reiniciar Evolution API..." "WARN"
    try {
        docker compose -f $ComposeFile --env-file $EnvFile restart evolution_api 2>&1 | Out-Null
        Start-Sleep -Seconds 20
        
        $EvolutionHealth = Invoke-RestMethod -Uri "http://localhost:8080/" -Method Get -TimeoutSec 10
        Write-Log "Evolution API reiniciada com sucesso" "INFO"
        $EvolutionOk = $true
    } catch {
        Write-Log "Falha ao reiniciar Evolution API: $_" "ERROR"
    }
}

# 5. Verificar status da instância WhatsApp
if ($ApiOk) {
    Write-Log "Verificando instância WhatsApp..." "INFO"
    try {
        $InstanceStatus = Invoke-RestMethod -Uri "http://localhost:8787/evolution/instance-status" -Method Get -TimeoutSec 10
        
        if ($InstanceStatus.ok -and $InstanceStatus.state -eq "open") {
            Write-Log "WhatsApp: Conectado (state: $($InstanceStatus.state))" "INFO"
        } elseif ($InstanceStatus.ok) {
            Write-Log "WhatsApp: Desconectado (state: $($InstanceStatus.state))" "WARN"
            Write-Log "AÇÃO NECESSÁRIA: Escanear QR Code novamente!" "WARN"
            Write-Log "Acesse: http://localhost:8787/evolution/qrcode" "WARN"
            
            # Gerar arquivo qrcode.png para facilitar acesso
            try {
                $QrResponse = Invoke-RestMethod -Uri "http://localhost:8787/evolution/qrcode" -Method Get -TimeoutSec 15
                Write-Log "QR Code gerado: http://localhost:8787/evolution/qrcode" "INFO"
            } catch {
                Write-Log "Erro ao gerar QR Code: $_" "WARN"
            }
        } else {
            Write-Log "WhatsApp: Erro - $($InstanceStatus.error)" "ERROR"
        }
    } catch {
        Write-Log "Erro ao verificar instância WhatsApp: $_" "WARN"
    }
}

# 6. Verificar webhook
if ($ApiOk -and $EvolutionOk) {
    Write-Log "Verificando webhook..." "INFO"
    try {
        # Tentar reconfigurar webhook (idempotente)
        $WebhookBody = @{
            user_id = "admin"
            shop_uid = "watchdog"
        } | ConvertTo-Json
        
        $WebhookResponse = Invoke-RestMethod -Uri "http://localhost:8787/evolution/setup-webhook" -Method Post -Body $WebhookBody -ContentType "application/json" -TimeoutSec 10
        
        if ($WebhookResponse.ok) {
            Write-Log "Webhook: OK" "INFO"
        } else {
            Write-Log "Webhook: Erro - $($WebhookResponse.error)" "WARN"
        }
    } catch {
        Write-Log "Erro ao verificar webhook: $_" "WARN"
    }
}

# 7. Verificar Cloudflare Tunnel (processo Windows, não container)
Write-Log "Verificando Cloudflare Tunnel..." "INFO"
try {
    $CloudflaredProcess = Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue
    
    if ($CloudflaredProcess) {
        Write-Log "Cloudflare Tunnel: Rodando (PID: $($CloudflaredProcess.Id))" "INFO"
    } else {
        Write-Log "Cloudflare Tunnel: Não está rodando" "WARN"
        Write-Log "AÇÃO NECESSÁRIA: Iniciar cloudflared manualmente ou via start-tunnel.ps1" "WARN"
    }
} catch {
    Write-Log "Erro ao verificar Cloudflare Tunnel: $_" "WARN"
}

# 8. Resumo
Write-Log "════════════════════════════════════════════════════════════" "INFO"
Write-Log "Watchdog concluído" "INFO"
Write-Log "  - Docker: OK" "INFO"
Write-Log "  - ShopeeBooster API: $(if ($ApiOk) { 'OK' } else { 'FALHOU' })" $(if ($ApiOk) { "INFO" } else { "ERROR" })
Write-Log "  - Evolution API: $(if ($EvolutionOk) { 'OK' } else { 'FALHOU' })" $(if ($EvolutionOk) { "INFO" } else { "ERROR" })
Write-Log "════════════════════════════════════════════════════════════" "INFO"

exit 0
