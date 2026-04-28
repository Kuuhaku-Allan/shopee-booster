# start-tunnel.ps1 - Inicia Cloudflare Quick Tunnel e captura URL
# Automatiza o processo de obter URL pública temporária

param(
    [switch]$Silent = $false
)

# Configurações
$ProjectPath = "C:\Users\Defal\Documents\Faculdade\Projeto Shopee"
$EnvFile = ".env.local"
$LogFile = "$ProjectPath\deploy\local\logs\tunnel.log"
$TunnelTimeout = 60  # segundos para aguardar URL

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
Write-Log "Cloudflare Quick Tunnel - Iniciando..."
Write-Log "════════════════════════════════════════════════════════════"

# Ir para diretório do projeto
Set-Location $ProjectPath

# Verificar se cloudflared está instalado
Write-Log "Verificando cloudflared..."
try {
    $CloudflaredVersion = cloudflared --version 2>&1
    Write-Log "✅ Cloudflared encontrado: $($CloudflaredVersion -split "`n" | Select-Object -First 1)"
} catch {
    Write-Log "❌ Cloudflared não encontrado!"
    Write-Log "Instale com: winget install --id Cloudflare.cloudflared"
    exit 1
}

# Verificar se já está rodando
$ExistingProcess = Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue
if ($ExistingProcess) {
    Write-Log "⚠️  Cloudflared já está rodando (PID: $($ExistingProcess.Id))"
    Write-Log "Parando processo existente..."
    Stop-Process -Id $ExistingProcess.Id -Force
    Start-Sleep -Seconds 3
}

# Iniciar cloudflared em background e capturar output
Write-Log "Iniciando cloudflared tunnel..."
$TunnelJob = Start-Job -ScriptBlock {
    param($ProjectPath)
    Set-Location $ProjectPath
    cloudflared tunnel --url http://localhost:8787 2>&1
} -ArgumentList $ProjectPath

# Aguardar URL aparecer nos logs
Write-Log "Aguardando URL pública (timeout: ${TunnelTimeout}s)..."
$StartTime = Get-Date
$TunnelUrl = $null

while (((Get-Date) - $StartTime).TotalSeconds -lt $TunnelTimeout) {
    Start-Sleep -Seconds 2
    
    # Capturar output do job
    $JobOutput = Receive-Job -Job $TunnelJob -Keep
    
    if ($JobOutput) {
        foreach ($Line in $JobOutput) {
            Write-Log "  [cloudflared] $Line"
            
            # Procurar pela URL trycloudflare.com
            if ($Line -match "https://[a-zA-Z0-9\-]+\.trycloudflare\.com") {
                $TunnelUrl = $Matches[0]
                Write-Log "✅ URL capturada: $TunnelUrl"
                break
            }
        }
        
        if ($TunnelUrl) {
            break
        }
    }
}

if (-not $TunnelUrl) {
    Write-Log "❌ Timeout: Não foi possível capturar URL do tunnel"
    Stop-Job -Job $TunnelJob -PassThru | Remove-Job
    exit 1
}

# Atualizar .env.local com nova URL
Write-Log "Atualizando $EnvFile com nova URL..."
try {
    if (Test-Path $EnvFile) {
        $EnvContent = Get-Content $EnvFile
        $UpdatedContent = @()
        $UrlUpdated = $false
        
        foreach ($Line in $EnvContent) {
            if ($Line -match "^SHOPEE_API_PUBLIC_URL=") {
                $UpdatedContent += "SHOPEE_API_PUBLIC_URL=$TunnelUrl"
                $UrlUpdated = $true
                Write-Log "  Atualizado: SHOPEE_API_PUBLIC_URL=$TunnelUrl"
            } else {
                $UpdatedContent += $Line
            }
        }
        
        # Se não existia, adicionar
        if (-not $UrlUpdated) {
            $UpdatedContent += "SHOPEE_API_PUBLIC_URL=$TunnelUrl"
            Write-Log "  Adicionado: SHOPEE_API_PUBLIC_URL=$TunnelUrl"
        }
        
        # Salvar arquivo
        $UpdatedContent | Set-Content $EnvFile -Encoding UTF8
        Write-Log "✅ Arquivo $EnvFile atualizado"
    } else {
        Write-Log "❌ Arquivo $EnvFile não encontrado"
        exit 1
    }
} catch {
    Write-Log "❌ Erro ao atualizar $EnvFile: $_"
    exit 1
}

Write-Log "════════════════════════════════════════════════════════════"
Write-Log "Cloudflare Quick Tunnel configurado com sucesso!"
Write-Log "URL pública: $TunnelUrl"
Write-Log "Processo PID: $($TunnelJob.Id)"
Write-Log "════════════════════════════════════════════════════════════"

# Retornar informações para script pai
if (-not $Silent) {
    Write-Host ""
    Write-Host "URL pública: $TunnelUrl" -ForegroundColor Green
    Write-Host "Para parar: Get-Job | Stop-Job" -ForegroundColor Yellow
    Write-Host ""
}

# Manter job rodando em background
# O job continuará rodando mesmo após o script terminar
exit 0