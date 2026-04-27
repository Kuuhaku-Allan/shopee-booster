# Deploy Oracle Cloud - ShopeeBooster WhatsApp Bot

## Visão Geral

Este guia explica como fazer deploy do **ShopeeBooster WhatsApp Bot** na **Oracle Cloud Always Free** usando Ubuntu ARM (Ampere A1).

### O Que Será Hospedado

- ✅ **FastAPI** (api_server.py) - Bot WhatsApp
- ✅ **Evolution API** - Gerenciamento WhatsApp
- ✅ **PostgreSQL** - Banco da Evolution
- ✅ **Volumes persistentes** - data/, reports/, uploads/

### O Que NÃO Será Hospedado

- ❌ **Streamlit .exe** - Continua local no PC
- ❌ **Playwright scraping** - Continua local (melhor IP residencial)

## Pré-requisitos

### 1. Conta Oracle Cloud

1. Acesse: https://www.oracle.com/cloud/free/
2. Crie conta gratuita (Always Free)
3. Verifique email e configure billing (não será cobrado)

### 2. Criar VM Ubuntu ARM

**Especificações recomendadas (Always Free):**
- **Shape:** VM.Standard.A1.Flex (ARM Ampere)
- **OCPUs:** 2-4 (até 4 OCPUs grátis)
- **RAM:** 12-24 GB (até 24 GB grátis)
- **Storage:** 100-200 GB (até 200 GB grátis)
- **OS:** Ubuntu 22.04 LTS (ARM64)

**Passos:**
1. No console Oracle, vá em **Compute > Instances**
2. Clique em **Create Instance**
3. Nome: `shopee-booster-bot`
4. Image: **Ubuntu 22.04 (ARM64)**
5. Shape: **VM.Standard.A1.Flex**
   - OCPUs: 2-4
   - Memory: 12-24 GB
6. Networking:
   - VCN: Criar nova ou usar existente
   - Subnet: Pública
   - Assign public IP: **Sim**
7. SSH Keys: Adicione sua chave pública SSH
8. Clique em **Create**

### 3. Configurar Firewall Oracle

No console Oracle, configure **Security List** da VCN:

**Ingress Rules:**
```
Source: 0.0.0.0/0, Protocol: TCP, Port: 22   (SSH)
Source: 0.0.0.0/0, Protocol: TCP, Port: 80   (HTTP)
Source: 0.0.0.0/0, Protocol: TCP, Port: 443  (HTTPS)
Source: 0.0.0.0/0, Protocol: TCP, Port: 8787 (ShopeeBooster API)
Source: 0.0.0.0/0, Protocol: TCP, Port: 8080 (Evolution API)
```

## Instalação

### 1. Conectar via SSH

```bash
ssh ubuntu@<IP_PUBLICO_VM>
```

### 2. Executar Script de Setup

```bash
# Download do script
curl -fsSL https://raw.githubusercontent.com/Kuuhaku-Allan/shopee-booster/feature/whatsapp-bot-core/deploy/oracle/setup.sh -o setup.sh

# Dar permissão de execução
chmod +x setup.sh

# Executar
./setup.sh
```

**O script irá:**
- ✅ Atualizar sistema
- ✅ Instalar Docker e Docker Compose
- ✅ Configurar firewall UFW
- ✅ Criar diretórios necessários

### 3. Logout e Login

```bash
exit
ssh ubuntu@<IP_PUBLICO_VM>
```

### 4. Clonar Repositório

```bash
git clone https://github.com/Kuuhaku-Allan/shopee-booster.git ~/shopee-booster
cd ~/shopee-booster
git checkout feature/whatsapp-bot-core
```

### 5. Testar Build Localmente (OBRIGATÓRIO)

**IMPORTANTE:** Teste localmente ANTES de criar a VM Oracle para evitar descobrir erros na nuvem.

```bash
# 1. Validar sintaxe do docker-compose
docker compose -f docker-compose.prod.yml config

# 2. Testar build do Dockerfile
docker compose -f docker-compose.prod.yml build shopee_api

# 3. (Opcional) Testar docker-compose completo
chmod +x deploy/oracle/test-local-build.sh
./deploy/oracle/test-local-build.sh

chmod +x deploy/oracle/test-local-compose.sh
./deploy/oracle/test-local-compose.sh

# 4. Se tudo passou, parar serviços locais
docker compose -f docker-compose.prod.yml down
```

**Se o build local falhar, NÃO prossiga para a Oracle. Corrija os erros primeiro.**

Veja [deploy/oracle/README.md](deploy/oracle/README.md) para mais detalhes sobre os scripts de teste.

### 6. Configurar Variáveis de Ambiente

```bash
# Copiar exemplo
cp .env.example.production .env

# Editar
nano .env
```

**Gerar chaves secretas:**

```bash
# Evolution API Key
openssl rand -hex 32

# Bot Secret Key (Fernet)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Exemplo de .env:**
```env
# Evolution API
EVOLUTION_API_KEY=abc123def456...
WHATSAPP_INSTANCE=shopee_booster

# Postgres
POSTGRES_PASSWORD=senha_forte_aqui

# ShopeeBooster API
SHOPEE_API_PUBLIC_URL=https://bot.seudominio.com
BOT_SECRET_KEY=chave_fernet_aqui
ALLOW_GLOBAL_GEMINI_FALLBACK=false

# Opcional
GOOGLE_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

### 6. Iniciar Serviços

```bash
# Build e start
docker compose -f docker-compose.prod.yml up -d --build

# Verificar logs
docker compose -f docker-compose.prod.yml logs -f

# Verificar status
docker compose -f docker-compose.prod.yml ps
```

**Esperado:**
```
NAME                IMAGE                           STATUS
shopee_api          shopee-booster-api             Up (healthy)
shopee_evolution    atendai/evolution-api:latest   Up (healthy)
shopee_postgres     postgres:15-alpine             Up (healthy)
```

## Configuração do Domínio

### Opção 1: Cloudflare Tunnel (Recomendado)

**Vantagens:**
- ✅ HTTPS automático
- ✅ Não precisa comprar domínio
- ✅ Proteção DDoS
- ✅ Fácil configuração

**Instalação:**

```bash
# Instalar cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared-linux-arm64.deb

# Autenticar
cloudflared tunnel login

# Criar tunnel
cloudflared tunnel create shopee-booster

# Configurar
nano ~/.cloudflared/config.yml
```

**config.yml:**
```yaml
tunnel: <TUNNEL_ID>
credentials-file: /home/ubuntu/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: bot.seudominio.com
    service: http://localhost:8787
  - service: http_status:404
```

**Iniciar tunnel:**
```bash
# Testar
cloudflared tunnel run shopee-booster

# Rodar como serviço
sudo cloudflared service install
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
```

### Opção 2: Domínio Próprio + Nginx

**Se você tem domínio próprio:**

```bash
# Instalar Nginx
sudo apt-get install -y nginx certbot python3-certbot-nginx

# Configurar
sudo nano /etc/nginx/sites-available/shopee-booster
```

**Configuração Nginx:**
```nginx
server {
    listen 80;
    server_name bot.seudominio.com;

    location / {
        proxy_pass http://localhost:8787;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Ativar e obter SSL:**
```bash
sudo ln -s /etc/nginx/sites-available/shopee-booster /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
sudo certbot --nginx -d bot.seudominio.com
```

## Configuração do WhatsApp

### 1. Verificar Health

```bash
# ShopeeBooster API
curl http://localhost:8787/health

# Evolution API
curl http://localhost:8080/health
```

### 2. Configurar Webhook

**Via curl:**
```bash
curl -X POST http://localhost:8787/evolution/setup-webhook \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "admin",
    "shop_uid": "setup"
  }'
```

**Ou via navegador:**
```
http://<IP_PUBLICO>:8787/docs
```

Acesse o endpoint `/evolution/setup-webhook` e execute.

### 3. Escanear QR Code

**Obter QR Code:**
```bash
curl http://localhost:8080/instance/connect/shopee_booster \
  -H "apikey: SUA_EVOLUTION_API_KEY"
```

**Ou via navegador:**
```
http://<IP_PUBLICO>:8080/instance/connect/shopee_booster
```

**Escanear:**
1. Abra WhatsApp no celular
2. Vá em **Configurações > Aparelhos conectados**
3. Clique em **Conectar um aparelho**
4. Escaneie o QR Code

### 4. Verificar Conexão

```bash
curl http://localhost:8787/evolution/instance-status
```

**Esperado:**
```json
{
  "ok": true,
  "instance": "shopee_booster",
  "state": "open",
  "message": "Instância conectada"
}
```

### 5. Testar Bot

Envie mensagem no WhatsApp:
```
/menu
```

**Esperado:**
```
🤖 ShopeeBooster - Menu Principal

Escolha uma opção:

📦 /loja - Gerenciar lojas
🔍 /auditar - Auditar produto
📊 /catalogo - Importar catálogo
🛡️ /sentinela - Monitoramento
🤖 /ia - Configurar IA
📢 /telegram - Configurar Telegram
ℹ️ /ajuda - Ajuda e suporte
```

## Manutenção

### Logs

```bash
# Todos os serviços
docker compose -f docker-compose.prod.yml logs -f

# Apenas ShopeeBooster API
docker compose -f docker-compose.prod.yml logs -f shopee_api

# Apenas Evolution API
docker compose -f docker-compose.prod.yml logs -f evolution_api
```

### Restart

```bash
# Todos os serviços
docker compose -f docker-compose.prod.yml restart

# Apenas um serviço
docker compose -f docker-compose.prod.yml restart shopee_api
```

### Atualizar Código

```bash
cd ~/shopee-booster
git pull origin feature/whatsapp-bot-core
docker compose -f docker-compose.prod.yml up -d --build
```

### Backup

```bash
# Backup data/
tar -czf backup-data-$(date +%Y%m%d).tar.gz data/

# Backup Evolution instances
docker compose -f docker-compose.prod.yml exec evolution_api tar -czf /tmp/instances-backup.tar.gz /evolution/instances
docker cp shopee_evolution:/tmp/instances-backup.tar.gz ./instances-backup-$(date +%Y%m%d).tar.gz

# Backup Postgres
docker compose -f docker-compose.prod.yml exec postgres pg_dump -U evolution evolution > backup-postgres-$(date +%Y%m%d).sql
```

### Monitoramento

```bash
# Status dos containers
docker compose -f docker-compose.prod.yml ps

# Uso de recursos
docker stats

# Espaço em disco
df -h

# Logs do sistema
sudo journalctl -u docker -f
```

## Troubleshooting

### Container não inicia

```bash
# Ver logs
docker compose -f docker-compose.prod.yml logs shopee_api

# Verificar configuração
docker compose -f docker-compose.prod.yml config

# Rebuild
docker compose -f docker-compose.prod.yml up -d --build --force-recreate
```

### Evolution API não conecta

```bash
# Verificar logs
docker compose -f docker-compose.prod.yml logs evolution_api

# Verificar Postgres
docker compose -f docker-compose.prod.yml exec postgres psql -U evolution -c "\l"

# Recriar instância
curl -X DELETE http://localhost:8080/instance/logout/shopee_booster \
  -H "apikey: SUA_EVOLUTION_API_KEY"
```

### Webhook não funciona

```bash
# Verificar URL pública
echo $SHOPEE_API_PUBLIC_URL

# Testar webhook manualmente
curl -X POST https://bot.seudominio.com/webhook/evolution \
  -H "Content-Type: application/json" \
  -d '{"event":"test"}'

# Reconfigurar webhook
curl -X POST http://localhost:8787/evolution/setup-webhook
```

### Sem espaço em disco

```bash
# Limpar imagens não usadas
docker system prune -a

# Limpar volumes não usados
docker volume prune

# Limpar logs antigos
sudo journalctl --vacuum-time=7d
```

## Limitações Conhecidas

### ⚠️ Provider de Concorrentes

O sistema atualmente usa **provider mock** para concorrentes porque:
- API do Mercado Livre retorna 403 Forbidden
- Shopee Playwright não funciona via subprocess

**Impacto:**
- ✅ Auditoria funciona (com concorrentes simulados)
- ✅ Sentinela funciona (com concorrentes simulados)
- ⚠️ Concorrentes não são reais

**Solução futura:**
- Corrigir API do Mercado Livre
- Implementar scraping via proxy
- Usar .exe local para scraping real

### ⚠️ IP de Datacenter

Oracle Cloud usa IP de datacenter, que pode ter:
- Taxa de bloqueio maior em e-commerce
- Reputação pior que IP residencial

**Recomendação:**
- Bot 24h → Oracle Cloud ✅
- Scraping pesado → .exe local ✅

## Segurança

### Checklist

- [ ] Firewall configurado (UFW + Oracle Security List)
- [ ] HTTPS habilitado (Cloudflare Tunnel ou Certbot)
- [ ] Senhas fortes geradas
- [ ] .env não commitado no Git
- [ ] Evolution API Key única
- [ ] Bot Secret Key única
- [ ] Postgres com senha forte
- [ ] Backup automático configurado
- [ ] Logs monitorados

### Boas Práticas

1. **Nunca exponha portas desnecessárias**
2. **Use HTTPS sempre**
3. **Mantenha sistema atualizado**
4. **Faça backup regularmente**
5. **Monitore logs de erro**
6. **Revogue chaves expostas imediatamente**

## Custos

### Oracle Cloud Always Free

- ✅ **VM ARM:** 4 OCPUs + 24 GB RAM (grátis para sempre)
- ✅ **Storage:** 200 GB (grátis para sempre)
- ✅ **Bandwidth:** 10 TB/mês (grátis)
- ✅ **IP público:** 1 grátis

**Custo total:** R$ 0,00/mês 🎉

### Cloudflare Tunnel

- ✅ **Tunnel:** Grátis
- ✅ **HTTPS:** Grátis
- ✅ **DDoS protection:** Grátis

**Custo total:** R$ 0,00/mês 🎉

### Domínio (Opcional)

- ⚠️ **Registro:** ~R$ 40/ano (.com.br)
- ✅ **DNS Cloudflare:** Grátis

## Suporte

### Documentação

- [Oracle Cloud Docs](https://docs.oracle.com/en-us/iaas/Content/home.htm)
- [Evolution API Docs](https://doc.evolution-api.com/)
- [Docker Docs](https://docs.docker.com/)
- [Cloudflare Tunnel Docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)

### Logs Úteis

```bash
# Ver todos os logs
docker compose -f docker-compose.prod.yml logs -f

# Ver logs de erro
docker compose -f docker-compose.prod.yml logs -f | grep ERROR

# Ver logs do WhatsApp
docker compose -f docker-compose.prod.yml logs -f shopee_api | grep "\[WA\]"

# Ver logs do Sentinela
docker compose -f docker-compose.prod.yml logs -f shopee_api | grep "\[SENTINELA\]"
```

## Próximos Passos

Após deploy bem-sucedido:

1. ✅ Testar todos os comandos do bot
2. ✅ Configurar Telegram (opcional)
3. ✅ Importar catálogo
4. ✅ Testar auditoria
5. ✅ Configurar Sentinela
6. ✅ Monitorar logs por 24h
7. ✅ Configurar backup automático
8. ✅ Documentar para equipe

**O bot está pronto para uso 24/7!** 🚀
