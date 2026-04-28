# start-tunnel-temp.ps1 - Inicia tunnel temporário do Cloudflare

Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Cloudflare Tunnel Temporário" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# Verificar se cloudflared está instalado
Write-Host "Verificando cloudflared..." -ForegroundColor Yellow
try {
    $version = cloudflared --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ cloudflared instalado: $version" -ForegroundColor Green
    } else {
        Write-Host "❌ cloudflared não encontrado!" -ForegroundColor Red
        Write-Host ""
        Write-Host "Instale com:" -ForegroundColor Yellow
        Write-Host "  winget install --id Cloudflare.cloudflared" -ForegroundColor White
        Write-Host ""
        Write-Host "Depois feche e reabra o PowerShell." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Pressione qualquer tecla para fechar..." -ForegroundColor Green
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        exit 1
    }
} catch {
    Write-Host "❌ cloudflared não encontrado!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Instale com:" -ForegroundColor Yellow
    Write-Host "  winget install --id Cloudflare.cloudflared" -ForegroundColor White
    Write-Host ""
    Write-Host "Depois feche e reabra o PowerShell." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Pressione qualquer tecla para fechar..." -ForegroundColor Green
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

Write-Host ""

# Verificar se localhost:8787 está respondendo
Write-Host "Verificando se bot está rodando em localhost:8787..." -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "http://localhost:8787/health" -Method Get -TimeoutSec 5
    Write-Host "✅ Bot está rodando!" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Bot não está respondendo em localhost:8787" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "O tunnel vai abrir, mas não vai funcionar até o bot iniciar." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Inicie o bot primeiro:" -ForegroundColor Yellow
    Write-Host "  .\deploy\local\start-bot.ps1" -ForegroundColor White
    Write-Host ""
    Write-Host "Pressione qualquer tecla para continuar mesmo assim..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

Write-Host ""
Write-Host "Iniciando tunnel para http://localhost:8787..." -ForegroundColor Yellow
Write-Host ""
Write-Host "⚠️  IMPORTANTE:" -ForegroundColor Yellow
Write-Host "   1. Copie a URL https://....trycloudflare.com que aparecer" -ForegroundColor White
Write-Host "   2. Cole no .env.local em SHOPEE_API_PUBLIC_URL" -ForegroundColor White
Write-Host "   3. DEIXE ESTE POWERSHELL RODANDO!" -ForegroundColor White
Write-Host ""
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

cloudflared tunnel --url http://localhost:8787
