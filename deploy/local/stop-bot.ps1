# stop-bot.ps1 - Para o ShopeeBooster Bot localmente

param(
    [switch]$Down = $false,
    [switch]$Silent = $false
)

# Configurações
$ProjectPath = "C:\Users\Defal\Documents\Faculdade\Projeto Shopee"
$ComposeFile = "docker-compose.local.yml"
$EnvFile = ".env.local"
$LogFile = "$ProjectPath\deploy\local\logs\stop-bot.log"

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
Write-Log "ShopeeBooster Bot - Parando..."
Write-Log "════════════════════════════════════════════════════════════"

# Ir para diretório do projeto
Set-Location $ProjectPath

if ($Down) {
    Write-Log "Parando e removendo containers..."
    docker compose -f $ComposeFile --env-file $EnvFile down 2>&1 | ForEach-Object {
        Write-Log "  $_"
    }
} else {
    Write-Log "Parando containers (mantendo dados)..."
    docker compose -f $ComposeFile --env-file $EnvFile stop 2>&1 | ForEach-Object {
        Write-Log "  $_"
    }
}

if ($LASTEXITCODE -eq 0) {
    Write-Log "✅ Bot parado com sucesso!"
} else {
    Write-Log "❌ Erro ao parar bot!"
    exit 1
}

Write-Log "════════════════════════════════════════════════════════════"

if (-not $Silent) {
    Write-Host ""
    Write-Host "Pressione qualquer tecla para fechar..." -ForegroundColor Green
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

exit 0
