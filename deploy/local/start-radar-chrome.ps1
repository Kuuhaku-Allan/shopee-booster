param(
    [int]$Port = 9222,
    [ValidateSet("mercadolivre", "shopee")]
    [string]$Marketplace = "mercadolivre",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ProfileDir = Join-Path $ProjectRoot "data\chrome_radar_profile"
New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null

$ChromeCandidates = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
)

$ChromePath = $ChromeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $ChromePath) {
    throw "chrome.exe nao encontrado. Instale o Google Chrome ou ajuste o caminho neste script."
}

if ($Marketplace -eq "shopee") {
    $StartUrl = "https://shopee.com.br/"
} else {
    $StartUrl = "https://www.mercadolivre.com.br/"
}

$Arguments = @(
    "--remote-debugging-port=$Port",
    "--user-data-dir=`"$ProfileDir`"",
    "--no-first-run",
    "--no-default-browser-check",
    $StartUrl
)

Write-Host "Chrome do Radar"
Write-Host "Perfil: $ProfileDir"
Write-Host "CDP: http://127.0.0.1:$Port"
Write-Host "URL inicial: $StartUrl"
Write-Host ""
Write-Host "Faca login/verificacao manualmente neste navegador."
Write-Host "Depois rode o coletor com: --browser-mode cdp --cdp-url http://127.0.0.1:$Port"

if ($DryRun) {
    Write-Host ""
    Write-Host "Dry-run: Chrome nao foi iniciado."
    Write-Host "$ChromePath $($Arguments -join ' ')"
    exit 0
}

Start-Process -FilePath $ChromePath -ArgumentList $Arguments -WindowStyle Normal
