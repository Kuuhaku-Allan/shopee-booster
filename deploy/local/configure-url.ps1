# configure-url.ps1 - Configura a URL pública do bot

Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Configurar URL Pública - ShopeeBooster Bot" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

$EnvFile = ".env.local"

if (-not (Test-Path $EnvFile)) {
    Write-Host "❌ Arquivo .env.local não encontrado!" -ForegroundColor Red
    exit 1
}

Write-Host "Você já tem um CLOUDFLARE_TUNNEL_TOKEN configurado." -ForegroundColor Green
Write-Host ""
Write-Host "Agora você precisa configurar a URL pública do bot." -ForegroundColor Yellow
Write-Host ""
Write-Host "Opções:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. Você tem um domínio na Cloudflare?" -ForegroundColor White
Write-Host "   Exemplo: https://bot.seudominio.com" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Você quer usar um tunnel temporário?" -ForegroundColor White
Write-Host "   Exemplo: https://alguma-coisa.trycloudflare.com" -ForegroundColor Gray
Write-Host "   (URL muda a cada reinício)" -ForegroundColor Yellow
Write-Host ""

$Choice = Read-Host "Digite 1 ou 2"

if ($Choice -eq "1") {
    Write-Host ""
    Write-Host "Digite a URL do seu domínio (com https://):" -ForegroundColor Yellow
    Write-Host "Exemplo: https://bot.seudominio.com" -ForegroundColor Gray
    $Url = Read-Host "URL"
    
    if ($Url -notmatch "^https://") {
        Write-Host "❌ URL deve começar com https://" -ForegroundColor Red
        exit 1
    }
    
    # Atualizar .env.local
    $EnvContent = Get-Content $EnvFile -Raw
    $EnvContent = $EnvContent -replace "SHOPEE_API_PUBLIC_URL=.*", "SHOPEE_API_PUBLIC_URL=$Url"
    Set-Content -Path $EnvFile -Value $EnvContent -NoNewline
    
    Write-Host ""
    Write-Host "✅ URL configurada: $Url" -ForegroundColor Green
    Write-Host ""
    Write-Host "Próximo passo:" -ForegroundColor Yellow
    Write-Host "  .\deploy\local\check-config.ps1" -ForegroundColor White
    
} elseif ($Choice -eq "2") {
    Write-Host ""
    Write-Host "Para usar tunnel temporário:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "1. Abra um PowerShell SEPARADO" -ForegroundColor White
    Write-Host "2. Execute: cloudflared tunnel --url http://localhost:8787" -ForegroundColor White
    Write-Host "3. Copie a URL que aparecer (https://....trycloudflare.com)" -ForegroundColor White
    Write-Host "4. Cole aqui:" -ForegroundColor White
    Write-Host ""
    $Url = Read-Host "URL do tunnel temporário"
    
    if ($Url -notmatch "^https://") {
        Write-Host "❌ URL deve começar com https://" -ForegroundColor Red
        exit 1
    }
    
    # Atualizar .env.local
    $EnvContent = Get-Content $EnvFile -Raw
    $EnvContent = $EnvContent -replace "SHOPEE_API_PUBLIC_URL=.*", "SHOPEE_API_PUBLIC_URL=$Url"
    Set-Content -Path $EnvFile -Value $EnvContent -NoNewline
    
    Write-Host ""
    Write-Host "✅ URL configurada: $Url" -ForegroundColor Green
    Write-Host ""
    Write-Host "⚠️  IMPORTANTE: Deixe o PowerShell com cloudflared rodando!" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Próximo passo:" -ForegroundColor Yellow
    Write-Host "  .\deploy\local\check-config.ps1" -ForegroundColor White
    
} else {
    Write-Host "❌ Opção inválida!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Pressione qualquer tecla para fechar..." -ForegroundColor Green
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
