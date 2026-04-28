# install-watchdog-task.ps1 - Instala tarefa do Windows para executar watchdog a cada 5 minutos
# EXECUTE COMO ADMINISTRADOR

# Verificar se está rodando como administrador
$IsAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $IsAdmin) {
    Write-Host "❌ Este script precisa ser executado como Administrador!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Clique com botão direito no PowerShell e selecione 'Executar como Administrador'" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Pressione qualquer tecla para fechar..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Instalando Tarefa de Watchdog do ShopeeBooster Bot" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# Configurações
$TaskName = "ShopeeBooster Bot - Watchdog"
$ProjectPath = "C:\Users\Defal\Documents\Faculdade\Projeto Shopee"
$ScriptPath = "$ProjectPath\deploy\local\watchdog.ps1"
$Username = $env:USERNAME

# Verificar se script existe
if (-not (Test-Path $ScriptPath)) {
    Write-Host "❌ Script não encontrado: $ScriptPath" -ForegroundColor Red
    Write-Host ""
    Write-Host "Pressione qualquer tecla para fechar..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

Write-Host "✅ Script encontrado: $ScriptPath" -ForegroundColor Green
Write-Host ""

# Remover tarefa existente se houver
Write-Host "Verificando tarefas existentes..." -ForegroundColor Yellow
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($ExistingTask) {
    Write-Host "Removendo tarefa existente..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "✅ Tarefa existente removida" -ForegroundColor Green
}

Write-Host ""

# Criar ação
Write-Host "Criando tarefa..." -ForegroundColor Yellow
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`""

# Criar trigger (a cada 5 minutos)
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 365)

# Criar configurações
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

# Criar principal (usuário atual)
$Principal = New-ScheduledTaskPrincipal -UserId $Username -LogonType Interactive -RunLevel Highest

# Registrar tarefa
try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "Monitora e recupera o ShopeeBooster WhatsApp Bot automaticamente a cada 5 minutos" `
        -ErrorAction Stop | Out-Null
    
    Write-Host "✅ Tarefa criada com sucesso!" -ForegroundColor Green
} catch {
    Write-Host "❌ Erro ao criar tarefa: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Pressione qualquer tecla para fechar..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

Write-Host ""
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Tarefa instalada com sucesso!" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "Detalhes da tarefa:" -ForegroundColor Yellow
Write-Host "  Nome: $TaskName"
Write-Host "  Trigger: A cada 5 minutos"
Write-Host "  Ação: Executar $ScriptPath"
Write-Host "  Timeout: 2 minutos"
Write-Host "  Reinício automático: Sim (até 3 tentativas)"
Write-Host ""
Write-Host "O watchdog irá:" -ForegroundColor Green
Write-Host "  ✅ Verificar se Docker está rodando"
Write-Host "  ✅ Verificar se containers estão healthy"
Write-Host "  ✅ Testar health checks (/health)"
Write-Host "  ✅ Verificar status do WhatsApp"
Write-Host "  ✅ Reconfigurar webhook se necessário"
Write-Host "  ✅ Reiniciar serviços automaticamente se falharem"
Write-Host "  ✅ Enviar alertas via Telegram (se configurado)"
Write-Host ""
Write-Host "Logs do watchdog:" -ForegroundColor Yellow
Write-Host "  $ProjectPath\deploy\local\logs\watchdog.log"
Write-Host ""
Write-Host "Para testar agora, execute:" -ForegroundColor Yellow
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "Para desinstalar, execute:" -ForegroundColor Yellow
Write-Host "  Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
Write-Host ""
Write-Host "Pressione qualquer tecla para fechar..." -ForegroundColor Green
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

exit 0
