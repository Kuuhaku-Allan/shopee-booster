#!/bin/bash
# setup.sh - Script de setup para Oracle Cloud Ubuntu ARM
# ShopeeBooster WhatsApp Bot

set -e

echo "════════════════════════════════════════════════════════════"
echo "ShopeeBooster WhatsApp Bot - Setup Oracle Cloud"
echo "════════════════════════════════════════════════════════════"
echo ""

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Função para print colorido
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

# Verifica se está rodando como root
if [ "$EUID" -eq 0 ]; then
    print_error "Não rode este script como root!"
    exit 1
fi

# 1. Atualiza sistema
echo ""
print_info "Atualizando sistema..."
sudo apt-get update
sudo apt-get upgrade -y
print_success "Sistema atualizado"

# 2. Instala dependências
echo ""
print_info "Instalando dependências..."
sudo apt-get install -y \
    curl \
    git \
    ca-certificates \
    gnupg \
    lsb-release
print_success "Dependências instaladas"

# 3. Instala Docker
echo ""
print_info "Instalando Docker..."
if ! command -v docker &> /dev/null; then
    # Adiciona repositório Docker
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Instala Docker
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    # Adiciona usuário ao grupo docker
    sudo usermod -aG docker $USER
    
    print_success "Docker instalado"
    print_warning "Você precisa fazer logout e login novamente para usar Docker sem sudo"
else
    print_success "Docker já instalado"
fi

# 4. Verifica instalação
echo ""
print_info "Verificando instalação..."
docker --version
docker compose version
print_success "Verificação concluída"

# 5. Cria diretórios
echo ""
print_info "Criando diretórios..."
mkdir -p ~/shopee-booster
cd ~/shopee-booster
mkdir -p data/reports uploads/catalogs
print_success "Diretórios criados"

# 6. Clona repositório (se não existir)
echo ""
if [ ! -d ".git" ]; then
    print_info "Clone o repositório manualmente:"
    echo "  git clone https://github.com/Kuuhaku-Allan/shopee-booster.git ~/shopee-booster"
    echo "  cd ~/shopee-booster"
    echo "  git checkout feature/whatsapp-bot-core"
else
    print_success "Repositório já clonado"
fi

# 7. Configura firewall
echo ""
print_info "Configurando firewall..."
if command -v ufw &> /dev/null; then
    sudo ufw allow 22/tcp    # SSH
    sudo ufw allow 80/tcp    # HTTP
    sudo ufw allow 443/tcp   # HTTPS
    sudo ufw allow 8787/tcp  # ShopeeBooster API
    sudo ufw allow 8080/tcp  # Evolution API
    sudo ufw --force enable
    print_success "Firewall configurado"
else
    print_warning "UFW não encontrado, configure o firewall manualmente"
fi

# 8. Instruções finais
echo ""
echo "════════════════════════════════════════════════════════════"
echo "Setup concluído! Próximos passos:"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "1. Faça logout e login novamente para usar Docker sem sudo:"
echo "   exit"
echo ""
echo "2. Clone o repositório (se ainda não fez):"
echo "   git clone https://github.com/Kuuhaku-Allan/shopee-booster.git ~/shopee-booster"
echo "   cd ~/shopee-booster"
echo "   git checkout feature/whatsapp-bot-core"
echo ""
echo "3. Configure variáveis de ambiente:"
echo "   cp .env.example.production .env"
echo "   nano .env"
echo ""
echo "4. Gere chaves secretas:"
echo "   # Evolution API Key"
echo "   openssl rand -hex 32"
echo ""
echo "   # Bot Secret Key (Fernet)"
echo "   python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
echo ""
echo "5. Inicie os serviços:"
echo "   docker compose -f docker-compose.prod.yml up -d"
echo ""
echo "6. Verifique os logs:"
echo "   docker compose -f docker-compose.prod.yml logs -f"
echo ""
echo "7. Configure webhook e escaneie QR Code (veja DEPLOY_ORACLE.md)"
echo ""
echo "════════════════════════════════════════════════════════════"
