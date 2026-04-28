# check-config.ps1 - Verifica se .env.local está configurado corretamente

Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Verificador de Configuração - ShopeeBooster Bot" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

$ProjectPath = "C:\Users\Defal\Documents\Faculdade\Projeto Shopee"
$EnvFile = "$ProjectPath\.env.local"

# Verificar se .env.local existe
if (-not (Test-Path $EnvFile)) {
    Write-Host "❌ Arquivo .env.local não encontrado!" -ForegroundColor Red
    Write-Host "   Execute: copy .env.example.local .env.local" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ Arquivo .env.local encontrado" -ForegroundColor Green
Write-Host ""

# Ler .env.local
$EnvContent = Get-Content $EnvFile -Raw

# Função para verificar variável
function Test-EnvVar {
    param($VarName, $Required = $true)
    
    $Pattern = "$VarName=(.+)"
    if ($EnvContent -match $Pattern) {
        $Value = $Matches[1].Trim()
        
        # Verificar se não é placeholder
        $Placeholders = @(
            "SUA_CHAVE_EVOLUTION_AQUI",
            "SUA_SENHA_POSTGRES_AQUI",
            "SUA_CHAVE_FERNET_AQUI",
            "SEU_DOMINIO_AQUI",
            "SEU_TOKEN_CLOUDFLARE_AQUI"
        )
        
        $IsPlaceholder = $false
        foreach ($Placeholder in $Placeholders) {
            if ($Value -like "*$Placeholder*") {
                $IsPlaceholder = $true
                break
            }
        }
        
        if ($Value -and -not $IsPlaceholder) {
            Write-Host "  ✅ $VarName" -ForegroundColor Green -NoNewline
            Write-Host " (configurado)" -ForegroundColor Gray
            return $true
        } else {
            if ($Required) {
                Write-Host "  ❌ $VarName" -ForegroundColor Red -NoNewline
                Write-Host " (não configurado ou placeholder)" -ForegroundColor Yellow
            } else {
                Write-Host "  ⚠️  $VarName" -ForegroundColor Yellow -NoNewline
                Write-Host " (opcional - não configurado)" -ForegroundColor Gray
            }
            return $false
        }
    } else {
        if ($Required) {
            Write-Host "  ❌ $VarName" -ForegroundColor Red -NoNewline
            Write-Host " (não encontrado)" -ForegroundColor Yellow
        } else {
            Write-Host "  ⚠️  $VarName" -ForegroundColor Yellow -NoNewline
            Write-Host " (opcional - não encontrado)" -ForegroundColor Gray
        }
        return $false
    }
}

# Verificar variáveis obrigatórias
Write-Host "Variáveis Obrigatórias:" -ForegroundColor Yellow
$AllRequired = $true
$AllRequired = (Test-EnvVar "EVOLUTION_API_KEY") -and $AllRequired
$AllRequired = (Test-EnvVar "POSTGRES_PASSWORD") -and $AllRequired
$AllRequired = (Test-EnvVar "BOT_SECRET_KEY") -and $AllRequired
$AllRequired = (Test-EnvVar "SHOPEE_API_PUBLIC_URL") -and $AllRequired
$AllRequired = (Test-EnvVar "CLOUDFLARE_TUNNEL_TOKEN") -and $AllRequired
$AllRequired = (Test-EnvVar "WHATSAPP_INSTANCE") -and $AllRequired

Write-Host ""

# Verificar variáveis opcionais
Write-Host "Variáveis Opcionais:" -ForegroundColor Yellow
Test-EnvVar "GOOGLE_API_KEY" $false | Out-Null
Test-EnvVar "TELEGRAM_BOT_TOKEN" $false | Out-Null
Test-EnvVar "TELEGRAM_CHAT_ID" $false | Out-Null

Write-Host ""
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan

if ($AllRequired) {
    Write-Host "✅ Configuração OK! Pronto para iniciar o bot." -ForegroundColor Green
    Write-Host ""
    Write-Host "Próximo passo:" -ForegroundColor Yellow
    Write-Host "  .\deploy\local\start-bot.ps1" -ForegroundColor White
    exit 0
} else {
    Write-Host "❌ Configuração incompleta!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Próximos passos:" -ForegroundColor Yellow
    Write-Host "  1. Gerar chaves: .\deploy\local\generate-keys.ps1" -ForegroundColor White
    Write-Host "  2. Editar .env.local: notepad .env.local" -ForegroundColor White
    Write-Host "  3. Configurar Cloudflare Tunnel" -ForegroundColor White
    Write-Host "  4. Verificar novamente: .\deploy\local\check-config.ps1" -ForegroundColor White
    exit 1
}

Write-Host ""
Write-Host "Pressione qualquer tecla para fechar..." -ForegroundColor Green
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
