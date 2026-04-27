#!/bin/bash
# test-local-compose.sh - Testa docker-compose.prod.yml localmente
# Execute antes de fazer deploy na Oracle

set -e

echo "════════════════════════════════════════════════════════════"
echo "Teste Local - docker-compose.prod.yml"
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

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${NC}ℹ${NC} $1"
}

# 1. Verificar se Docker Compose está instalado
print_info "Verificando Docker Compose..."
if ! command -v docker compose &> /dev/null; then
    print_error "Docker Compose não encontrado! Instale Docker Compose primeiro."
    exit 1
fi
print_success "Docker Compose instalado"

# 2. Verificar se .env existe
print_info "Verificando .env..."
if [ ! -f ".env" ]; then
    print_warning ".env não encontrado! Criando a partir de .env.example.production..."
    cp .env.example.production .env
    print_warning "IMPORTANTE: Edite o .env e preencha as variáveis obrigatórias!"
    print_info "Variáveis obrigatórias:"
    echo "  - EVOLUTION_API_KEY (gerar com: openssl rand -hex 32)"
    echo "  - POSTGRES_PASSWORD (senha forte)"
    echo "  - SHOPEE_API_PUBLIC_URL (ex: https://bot.seudominio.com)"
    echo "  - BOT_SECRET_KEY (gerar com: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\")"
    echo ""
    read -p "Pressione ENTER após editar o .env..."
fi
print_success ".env encontrado"

# 3. Validar sintaxe do docker-compose
print_info "Validando sintaxe do docker-compose.prod.yml..."
docker compose -f docker-compose.prod.yml config > /dev/null

if [ $? -eq 0 ]; then
    print_success "Sintaxe válida!"
else
    print_error "Sintaxe inválida!"
    exit 1
fi

# 4. Build das imagens
print_info "Fazendo build das imagens..."
docker compose -f docker-compose.prod.yml build

if [ $? -eq 0 ]; then
    print_success "Build concluído!"
else
    print_error "Build falhou!"
    exit 1
fi

# 5. Iniciar serviços
print_info "Iniciando serviços..."
docker compose -f docker-compose.prod.yml up -d

if [ $? -eq 0 ]; then
    print_success "Serviços iniciados!"
else
    print_error "Falha ao iniciar serviços!"
    exit 1
fi

# 6. Aguardar serviços ficarem healthy
print_info "Aguardando serviços ficarem healthy (até 60 segundos)..."
timeout=60
elapsed=0

while [ $elapsed -lt $timeout ]; do
    # Verificar status dos containers
    postgres_health=$(docker inspect shopee_postgres --format='{{.State.Health.Status}}' 2>/dev/null || echo "starting")
    evolution_health=$(docker inspect shopee_evolution --format='{{.State.Health.Status}}' 2>/dev/null || echo "starting")
    shopee_health=$(docker inspect shopee_api --format='{{.State.Health.Status}}' 2>/dev/null || echo "starting")
    
    if [ "$postgres_health" = "healthy" ] && [ "$evolution_health" = "healthy" ] && [ "$shopee_health" = "healthy" ]; then
        print_success "Todos os serviços estão healthy!"
        break
    fi
    
    echo "  Postgres: $postgres_health | Evolution: $evolution_health | ShopeeAPI: $shopee_health"
    sleep 5
    elapsed=$((elapsed + 5))
done

if [ $elapsed -ge $timeout ]; then
    print_warning "Timeout aguardando serviços ficarem healthy"
    print_info "Verificando logs..."
    docker compose -f docker-compose.prod.yml logs --tail=50
fi

# 7. Verificar status dos containers
print_info "Status dos containers:"
docker compose -f docker-compose.prod.yml ps

# 8. Testar endpoints
print_info "Testando endpoints..."

# ShopeeBooster API
if curl -f http://localhost:8787/health &> /dev/null; then
    print_success "ShopeeBooster API: OK"
else
    print_error "ShopeeBooster API: FALHOU"
fi

# Evolution API
if curl -f http://localhost:8080/health &> /dev/null; then
    print_success "Evolution API: OK"
else
    print_error "Evolution API: FALHOU"
fi

# 9. Mostrar logs recentes
print_info "Logs recentes (últimas 20 linhas):"
docker compose -f docker-compose.prod.yml logs --tail=20

# 10. Instruções finais
echo ""
echo "════════════════════════════════════════════════════════════"
echo "Teste concluído! ✅"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Serviços rodando:"
echo "  - ShopeeBooster API: http://localhost:8787"
echo "  - Evolution API: http://localhost:8080"
echo "  - Postgres: localhost:5432"
echo ""
echo "Comandos úteis:"
echo "  - Ver logs: docker compose -f docker-compose.prod.yml logs -f"
echo "  - Parar: docker compose -f docker-compose.prod.yml down"
echo "  - Restart: docker compose -f docker-compose.prod.yml restart"
echo ""
echo "Próximos passos:"
echo "  1. Configurar webhook: curl -X POST http://localhost:8787/evolution/setup-webhook"
echo "  2. Escanear QR Code: http://localhost:8080/instance/connect/shopee_booster"
echo "  3. Testar bot no WhatsApp: /menu"
echo ""
echo "Para parar os serviços:"
echo "  docker compose -f docker-compose.prod.yml down"
echo ""
