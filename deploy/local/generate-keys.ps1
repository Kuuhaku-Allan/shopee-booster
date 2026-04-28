# generate-keys.ps1 - Gera chaves necessárias para .env.local

Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Gerador de Chaves - ShopeeBooster Bot" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# Verificar se Python está disponível
try {
    $pythonPath = ".\venv\Scripts\python.exe"
    if (-not (Test-Path $pythonPath)) {
        Write-Host "❌ Python venv não encontrado em: $pythonPath" -ForegroundColor Red
        Write-Host "Tentando usar python global..." -ForegroundColor Yellow
        $pythonPath = "python"
    }
    
    # Testar Python
    & $pythonPath --version 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Python não está disponível!" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "✅ Python encontrado" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "❌ Erro ao verificar Python: $_" -ForegroundColor Red
    exit 1
}

# Gerar EVOLUTION_API_KEY
Write-Host "1. EVOLUTION_API_KEY (64 caracteres hex):" -ForegroundColor Yellow
try {
    $evolutionKey = & $pythonPath -c "import secrets; print(secrets.token_hex(32))"
    Write-Host "   $evolutionKey" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "   ❌ Erro ao gerar: $_" -ForegroundColor Red
}

# Gerar POSTGRES_PASSWORD
Write-Host "2. POSTGRES_PASSWORD (32 caracteres hex):" -ForegroundColor Yellow
try {
    $postgresPassword = & $pythonPath -c "import secrets; print(secrets.token_hex(16))"
    Write-Host "   $postgresPassword" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "   ❌ Erro ao gerar: $_" -ForegroundColor Red
}

# Gerar BOT_SECRET_KEY (Fernet)
Write-Host "3. BOT_SECRET_KEY (Fernet key):" -ForegroundColor Yellow
try {
    $botSecretKey = & $pythonPath -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    Write-Host "   $botSecretKey" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "   ❌ Erro ao gerar: $_" -ForegroundColor Red
    Write-Host "   Certifique-se de que 'cryptography' está instalado:" -ForegroundColor Yellow
    Write-Host "   pip install cryptography" -ForegroundColor Yellow
}

Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Copie essas chaves para o arquivo .env.local" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "Próximos passos:" -ForegroundColor Yellow
Write-Host "1. Abra .env.local: notepad .env.local" -ForegroundColor White
Write-Host "2. Cole as chaves geradas acima" -ForegroundColor White
Write-Host "3. Configure CLOUDFLARE_TUNNEL_TOKEN" -ForegroundColor White
Write-Host "4. Configure SHOPEE_API_PUBLIC_URL" -ForegroundColor White
Write-Host ""

Write-Host "Pressione qualquer tecla para fechar..." -ForegroundColor Green
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
