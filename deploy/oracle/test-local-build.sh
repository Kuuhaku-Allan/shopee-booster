#!/bin/bash
# test-local-build.sh - Testa build do Dockerfile.api localmente
# Execute antes de fazer deploy na Oracle

set -e

echo "════════════════════════════════════════════════════════════"
echo "Teste Local - Build Dockerfile.api"
echo "════════════════════════════════════════════════════════════"
echo ""

# Cores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${NC}ℹ${NC} $1"
}

# 1. Verificar se Docker está instalado
print_info "Verificando Docker..."
if ! command -v docker &> /dev/null; then
    print_error "Docker não encontrado! Instale Docker primeiro."
    exit 1
fi
print_success "Docker instalado"

# 2. Verificar arquivos necessários
print_info "Verificando arquivos necessários..."
required_files=(
    "Dockerfile.api"
    "requirements.txt"
    "api_server.py"
    "backend_core.py"
    "telegram_service.py"
    "sentinela_db.py"
    "shopee_core/__init__.py"
)

for file in "${required_files[@]}"; do
    if [ ! -f "$file" ] && [ ! -d "$(dirname "$file")" ]; then
        print_error "Arquivo não encontrado: $file"
        exit 1
    fi
done
print_success "Todos os arquivos necessários encontrados"

# 3. Build da imagem
print_info "Fazendo build da imagem..."
docker build -f Dockerfile.api -t shopee-booster-api:test .

if [ $? -eq 0 ]; then
    print_success "Build concluído com sucesso!"
else
    print_error "Build falhou!"
    exit 1
fi

# 4. Verificar tamanho da imagem
print_info "Verificando tamanho da imagem..."
docker images shopee-booster-api:test --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"

# 5. Testar se a imagem inicia
print_info "Testando se a imagem inicia..."
container_id=$(docker run -d --rm \
    -e EVOLUTION_API_URL=http://localhost:8080 \
    -e EVOLUTION_API_KEY=test \
    -e WHATSAPP_INSTANCE=test \
    -e SHOPEE_API_PUBLIC_URL=http://localhost:8787 \
    -e BOT_SECRET_KEY=test \
    -e ALLOW_GLOBAL_GEMINI_FALLBACK=false \
    -p 8787:8787 \
    shopee-booster-api:test)

if [ $? -eq 0 ]; then
    print_success "Container iniciado: $container_id"
    
    # Aguardar 10 segundos
    print_info "Aguardando 10 segundos para o container inicializar..."
    sleep 10
    
    # Verificar logs
    print_info "Logs do container:"
    docker logs "$container_id" 2>&1 | tail -20
    
    # Testar health check
    print_info "Testando health check..."
    if curl -f http://localhost:8787/health &> /dev/null; then
        print_success "Health check passou!"
    else
        print_error "Health check falhou!"
    fi
    
    # Parar container
    print_info "Parando container..."
    docker stop "$container_id" &> /dev/null
    print_success "Container parado"
else
    print_error "Falha ao iniciar container!"
    exit 1
fi

# 6. Limpar imagem de teste
print_info "Limpando imagem de teste..."
docker rmi shopee-booster-api:test &> /dev/null
print_success "Imagem removida"

echo ""
echo "════════════════════════════════════════════════════════════"
echo "Teste concluído com sucesso! ✅"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Próximos passos:"
echo "1. Fazer commit das alterações"
echo "2. Push para o repositório"
echo "3. Fazer deploy na Oracle Cloud"
echo ""
