# update-env-url.ps1 - Atualiza URL pública no .env.local
# Usado quando a URL do Cloudflare muda

param(
    [Parameter(Mandatory=$true)]
    [string]$NewUrl,
    
    [string]$EnvFile = ".env.local",
    
    [switch]$Silent = $false
)

# Função para log
function Write-Log {
    param($Message)
    if (-not $Silent) {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Message"
    }
}

Write-Log "Atualizando URL pública para: $NewUrl"

# Verificar se arquivo existe
if (-not (Test-Path $EnvFile)) {
    Write-Log "❌ Arquivo não encontrado: $EnvFile"
    exit 1
}

# Validar URL
if ($NewUrl -notmatch "^https://[a-zA-Z0-9\-]+\.trycloudflare\.com$") {
    Write-Log "❌ URL inválida. Deve ser https://xxx.trycloudflare.com"
    exit 1
}

try {
    # Ler conteúdo atual
    $EnvContent = Get-Content $EnvFile -Encoding UTF8
    $UpdatedContent = @()
    $UrlUpdated = $false
    
    # Processar cada linha
    foreach ($Line in $EnvContent) {
        if ($Line -match "^SHOPEE_API_PUBLIC_URL=") {
            $OldUrl = ($Line -split "=", 2)[1]
            $UpdatedContent += "SHOPEE_API_PUBLIC_URL=$NewUrl"
            $UrlUpdated = $true
            Write-Log "  Alterado de: $OldUrl"
            Write-Log "  Para: $NewUrl"
        } else {
            $UpdatedContent += $Line
        }
    }
    
    # Se não existia a variável, adicionar
    if (-not $UrlUpdated) {
        $UpdatedContent += "SHOPEE_API_PUBLIC_URL=$NewUrl"
        Write-Log "  Adicionado: SHOPEE_API_PUBLIC_URL=$NewUrl"
    }
    
    # Salvar arquivo
    $UpdatedContent | Set-Content $EnvFile -Encoding UTF8
    Write-Log "✅ Arquivo $EnvFile atualizado com sucesso"
    
    # Retornar sucesso
    exit 0
    
} catch {
    Write-Log "❌ Erro ao atualizar arquivo: $_"
    exit 1
}