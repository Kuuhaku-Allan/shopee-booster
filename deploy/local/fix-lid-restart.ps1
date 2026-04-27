# fix-lid-restart.ps1 - Aplica correção LID e reinicia containers
# ShopeeBooster WhatsApp Bot - Deploy Local

Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  ShopeeBooster - Correção LID + Restart" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# Verifica se está no diretório correto
if (-not (Test-Path "docker-compose.local.yml")) {
    Write-Host "❌ Erro: docker-compose.local.yml não encontrado!" -ForegroundColor Red
    Write-Host "Execute este script na raiz do projeto." -ForegroundColor Yellow
    exit 1
}

# Verifica se Docker está rodando
Write-Host "🔍 Verificando Docker..." -ForegroundColor Yellow
try {
    docker ps | Out-Null
    Write-Host "✅ Docker está rodando" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker não está rodando ou não está instalado!" -ForegroundColor Red
    Write-Host "Inicie o Docker Desktop e tente novamente." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "📋 Esta correção vai:" -ForegroundColor Cyan
Write-Host "  1. Parar os containers" -ForegroundColor White
Write-Host "  2. Reconstruir a imagem do bot (com endpoint correto)" -ForegroundColor White
Write-Host "  3. Subir os containers (com WPP_LID_MODE=false)" -ForegroundColor White
Write-Host "  4. Você precisará reconectar o WhatsApp (novo QR Code)" -ForegroundColor Yellow
Write-Host ""

$confirm = Read-Host "Deseja continuar? (s/n)"
if ($confirm -ne "s" -and $confirm -ne "S") {
    Write-Host "❌ Operação cancelada." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "PASSO 1: Parando containers..." -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan

docker-compose -f docker-compose.local.yml down

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Erro ao parar containers!" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Containers parados" -ForegroundColor Green
Write-Host ""

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "PASSO 2: Reconstruindo imagem do bot..." -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan

docker-compose -f docker-compose.local.yml build shopee_api

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Erro ao reconstruir imagem!" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Imagem reconstruída" -ForegroundColor Green
Write-Host ""

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "PASSO 3: Subindo containers..." -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan

docker-compose -f docker-compose.local.yml up -d

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Erro ao subir containers!" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Containers iniciados" -ForegroundColor Green
Write-Host ""

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "PASSO 4: Aguardando containers ficarem prontos..." -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan

Start-Sleep -Seconds 10

Write-Host "✅ Containers prontos" -ForegroundColor Green
Write-Host ""

Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  ✅ CORREÇÃO APLICADA COM SUCESSO!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""

Write-Host "PROXIMOS PASSOS:" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Reconectar WhatsApp (OBRIGATORIO):" -ForegroundColor Yellow
Write-Host "   http://localhost:8787/evolution/qrcode" -ForegroundColor White
Write-Host ""
Write-Host "2. Verificar logs:" -ForegroundColor Yellow
Write-Host "   docker logs shopee_api_local -f" -ForegroundColor White
Write-Host ""
Write-Host "3. Testar envio:" -ForegroundColor Yellow
Write-Host "   Envie '/menu' de OUTRO número para o bot" -ForegroundColor White
Write-Host ""

Write-Host "📊 Status dos containers:" -ForegroundColor Cyan
docker-compose -f docker-compose.local.yml ps

Write-Host ""
Write-Host "💡 Dica: Aguarde ~30 segundos antes de escanear o QR Code" -ForegroundColor Yellow
Write-Host ""
