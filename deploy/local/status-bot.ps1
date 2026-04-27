# status-bot.ps1 - Verifica status do ShopeeBooster Bot

# Configurações
$ProjectPath = "C:\Users\Defal\Documents\Faculdade\Projeto Shopee"
$ComposeFile = "docker-compose.local.yml"
$EnvFile = ".env.local"

Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "ShopeeBooster Bot - Status" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# Ir para diretório do projeto
Set-Location $ProjectPath

# Verificar se Docker está rodando
Write-Host "Docker:" -ForegroundColor Yellow
try {
    $dockerInfo = docker info 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✅ Rodando" -ForegroundColor Green
    } else {
        Write-Host "  ❌ Não está rodando" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "  ❌ Erro ao verificar: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Status dos containers
Write-Host "Containers:" -ForegroundColor Yellow
docker compose -f $ComposeFile --env-file $EnvFile ps

Write-Host ""

# Health checks
Write-Host "Health Checks:" -ForegroundColor Yellow

try {
    $ApiHealth = Invoke-RestMethod -Uri "http://localhost:8787/health" -Method Get -TimeoutSec 5
    Write-Host "  ✅ ShopeeBooster API: OK" -ForegroundColor Green
} catch {
    Write-Host "  ❌ ShopeeBooster API: FALHOU" -ForegroundColor Red
}

try {
    $EvolutionHealth = Invoke-RestMethod -Uri "http://localhost:8080/health" -Method Get -TimeoutSec 5
    Write-Host "  ✅ Evolution API: OK" -ForegroundColor Green
} catch {
    Write-Host "  ❌ Evolution API: FALHOU" -ForegroundColor Red
}

Write-Host ""

# Status da instância WhatsApp
Write-Host "WhatsApp:" -ForegroundColor Yellow
try {
    $InstanceStatus = Invoke-RestMethod -Uri "http://localhost:8787/evolution/instance-status" -Method Get -TimeoutSec 5
    
    if ($InstanceStatus.ok -and $InstanceStatus.state -eq "open") {
        Write-Host "  ✅ Conectado (state: $($InstanceStatus.state))" -ForegroundColor Green
    } elseif ($InstanceStatus.ok) {
        Write-Host "  ⚠️  Desconectado (state: $($InstanceStatus.state))" -ForegroundColor Yellow
    } else {
        Write-Host "  ❌ Erro: $($InstanceStatus.error)" -ForegroundColor Red
    }
} catch {
    Write-Host "  ❌ Erro ao verificar: $_" -ForegroundColor Red
}

Write-Host ""

# Uso de recursos
Write-Host "Recursos:" -ForegroundColor Yellow
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"

Write-Host ""
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "Comandos úteis:" -ForegroundColor Yellow
Write-Host "  - Ver logs: docker compose -f $ComposeFile --env-file $EnvFile logs -f"
Write-Host "  - Reiniciar: docker compose -f $ComposeFile --env-file $EnvFile restart"
Write-Host "  - Parar: .\deploy\local\stop-bot.ps1"
Write-Host "  - Iniciar: .\deploy\local\start-bot.ps1"
Write-Host ""

Write-Host "Pressione qualquer tecla para fechar..." -ForegroundColor Green
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
