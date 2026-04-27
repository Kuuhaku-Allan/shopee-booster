# Fase D2 — Deploy Real na Oracle Cloud

## ✅ STATUS: PRONTO PARA EXECUÇÃO

**Data:** 27/04/2026  
**Branch:** `feature/whatsapp-bot-core`  
**Pré-requisito:** Fase D1 concluída e testada localmente

---

## 📋 Pré-requisitos

### Fase D1 Concluída

- [x] Build local testado e passou
- [x] `docker-compose.prod.yml` validado
- [x] `requirements-api.txt` criado
- [x] Versão Evolution API fixada (v2.1.1)
- [x] Documentação completa
- [x] Arquivos no GitHub

### Antes de Começar

- [ ] Conta Oracle Cloud criada e verificada
- [ ] Cartão de crédito cadastrado (não será cobrado)
- [ ] Tempo disponível (1-2 horas para deploy completo)
- [ ] Conexão estável de internet
- [ ] Cliente SSH configurado

---

## ⚠️ Avisos Importantes

### Sobre Oracle Always Free

**Recursos Garantidos:**
- ✅ 4 OCPUs ARM Ampere A1 (total)
- ✅ 24 GB RAM (total)
- ✅ 200 GB storage
- ✅ 10 TB bandwidth/mês
- ✅ Sem limite de tempo

**ATENÇÃO - Política de Inatividade:**

A Oracle pode **recuperar instâncias Always Free consideradas inativas** se, por 7 dias consecutivos, ficarem com:
- CPU < 10-20% (média)
- Rede < 10-20% (média)
- Memória < 10-20% (média)

**Fonte:** [Oracle Cloud Infrastructure Documentation](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)

**Como evitar:**
- ✅ Bot WhatsApp com Evolution API gera atividade constante
- ✅ Webhook recebe mensagens regularmente
- ✅ Postgres e FastAPI mantêm processos ativos
- ✅ Monitorar uso de recursos periodicamente

**Recomendação:** Configure monitoramento básico para garantir que a VM está ativa.

### Sobre Recursos

**Recomendação inicial:**
- **OCPUs:** 2 (não 4)
- **RAM:** 12 GB (não 24 GB)
- **Storage:** 80-100 GB (não 200 GB)

**Motivo:**
- Economiza margem do Always Free
- Reduz risco de capacidade indisponível
- Pode aumentar depois se necessário

---

## 🚀 Passo a Passo

### Passo 1: Criar Conta Oracle Cloud

1. Acesse: https://www.oracle.com/cloud/free/
2. Clique em **Start for free**
3. Preencha dados:
   - Email
   - País/Região
   - Nome completo
4. Verifique email
5. Configure senha
6. Adicione cartão de crédito (não será cobrado)
7. Aguarde aprovação (pode levar alguns minutos)

**IMPORTANTE:** Guarde suas credenciais em local seguro!

---

### Passo 2: Criar VM Ubuntu ARM

#### 2.1. Acessar Console

1. Login em: https://cloud.oracle.com/
2. Vá em **Compute > Instances**
3. Clique em **Create Instance**

#### 2.2. Configurar Instância

**Nome:**
```
shopee-booster-bot
```

**Placement:**
- Availability Domain: Qualquer (deixe padrão)
- Fault Domain: Deixe padrão

**Image and Shape:**

1. Clique em **Change Image**
   - **Image:** Canonical Ubuntu 22.04 (ou 24.04)
   - **Image Build:** Latest
   - **Architecture:** ARM (Ampere)
   - Clique em **Select Image**

2. Clique em **Change Shape**
   - **Instance Type:** Virtual Machine
   - **Shape Series:** Ampere (ARM)
   - **Shape:** VM.Standard.A1.Flex
   - **OCPUs:** 2 (recomendado inicialmente)
   - **Memory (GB):** 12 (recomendado inicialmente)
   - Clique em **Select Shape**

**Networking:**
- **VCN:** Criar nova ou usar existente
- **Subnet:** Pública (Public Subnet)
- **Assign public IPv4 address:** ✅ SIM

**Add SSH Keys:**
- **Generate SSH key pair:** Clique e baixe as chaves
  - `ssh-key-YYYY-MM-DD.key` (privada)
  - `ssh-key-YYYY-MM-DD.key.pub` (pública)
- **OU** cole sua chave pública SSH existente

**Boot Volume:**
- **Size (GB):** 80-100 GB (recomendado)
- **Backup Policy:** Deixe padrão

#### 2.3. Criar Instância

1. Clique em **Create**
2. Aguarde status mudar para **Running** (1-3 minutos)
3. Anote o **Public IP Address**

**Exemplo:**
```
Public IP: 123.45.67.89
```

---

### Passo 3: Configurar Firewall Oracle

#### 3.1. Security List

1. No console Oracle, vá em **Networking > Virtual Cloud Networks**
2. Clique na VCN da sua instância
3. Clique em **Security Lists**
4. Clique na Security List padrão (Default Security List)
5. Clique em **Add Ingress Rules**

#### 3.2. Regras de Ingress

**Adicione as seguintes regras:**

**Regra 1 - SSH:**
```
Source CIDR: 0.0.0.0/0
IP Protocol: TCP
Source Port Range: All
Destination Port Range: 22
Description: SSH
```

**Regra 2 - HTTP (opcional - apenas se usar Nginx):**
```
Source CIDR: 0.0.0.0/0
IP Protocol: TCP
Source Port Range: All
Destination Port Range: 80
Description: HTTP
```

**Regra 3 - HTTPS (opcional - apenas se usar Nginx):**
```
Source CIDR: 0.0.0.0/0
IP Protocol: TCP
Source Port Range: All
Destination Port Range: 443
Description: HTTPS
```

**NOTA:** Se usar **Cloudflare Tunnel**, você NÃO precisa das regras HTTP/HTTPS. Apenas SSH é suficiente.

#### 3.3. Salvar

Clique em **Add Ingress Rules** para cada regra.

---

### Passo 4: Conectar via SSH

#### 4.1. Configurar Permissões da Chave (Linux/Mac)

```bash
chmod 400 ~/Downloads/ssh-key-YYYY-MM-DD.key
```

#### 4.2. Conectar

```bash
ssh -i ~/Downloads/ssh-key-YYYY-MM-DD.key ubuntu@123.45.67.89
```

**Substitua:**
- `~/Downloads/ssh-key-YYYY-MM-DD.key` pelo caminho da sua chave privada
- `123.45.67.89` pelo IP público da sua VM

**Primeira conexão:**
```
The authenticity of host '123.45.67.89' can't be established.
Are you sure you want to continue connecting (yes/no)? yes
```

**Esperado:**
```
Welcome to Ubuntu 22.04.X LTS (GNU/Linux ...)
ubuntu@shopee-booster-bot:~$
```

---

### Passo 5: Executar Script de Setup

#### 5.1. Download do Script

```bash
curl -fsSL https://raw.githubusercontent.com/Kuuhaku-Allan/shopee-booster/feature/whatsapp-bot-core/deploy/oracle/setup.sh -o setup.sh
```

#### 5.2. Dar Permissão

```bash
chmod +x setup.sh
```

#### 5.3. Executar

```bash
./setup.sh
```

**O script irá:**
- ✅ Atualizar sistema Ubuntu
- ✅ Instalar Docker e Docker Compose
- ✅ Configurar firewall UFW
- ✅ Criar diretórios necessários
- ✅ Adicionar usuário ao grupo docker

**Tempo estimado:** 5-10 minutos

#### 5.4. Logout e Login

**IMPORTANTE:** Você DEVE fazer logout e login novamente para que o grupo docker seja aplicado.

```bash
exit
```

```bash
ssh -i ~/Downloads/ssh-key-YYYY-MM-DD.key ubuntu@123.45.67.89
```

---

### Passo 6: Clonar Repositório

```bash
git clone -b feature/whatsapp-bot-core https://github.com/Kuuhaku-Allan/shopee-booster.git ~/shopee-booster
cd ~/shopee-booster
```

**Verificar branch:**
```bash
git branch --show-current
```

**Esperado:**
```
feature/whatsapp-bot-core
```

---

### Passo 7: Criar .env Real

#### 7.1. Copiar Template

```bash
cp .env.example.production .env
```

#### 7.2. Gerar Chaves Novas

**Evolution API Key:**
```bash
openssl rand -hex 32
```

**Exemplo de saída:**
```
a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2
```

**Bot Secret Key (Fernet):**
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Exemplo de saída:**
```
abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ==
```

**Postgres Password:**
- Gere uma senha forte única (mínimo 16 caracteres)
- Use letras, números e símbolos
- Exemplo: `P@ssw0rd!2026#Postgres$Secure`

#### 7.3. Editar .env

```bash
nano .env
```

**Preencha as variáveis obrigatórias:**

```env
# Evolution API
EVOLUTION_API_KEY=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2
WHATSAPP_INSTANCE=shopee_booster

# Postgres
POSTGRES_PASSWORD=P@ssw0rd!2026#Postgres$Secure

# ShopeeBooster API
SHOPEE_API_PUBLIC_URL=https://TEMPORARIO_SERA_ATUALIZADO_DEPOIS
BOT_SECRET_KEY=abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ==
ALLOW_GLOBAL_GEMINI_FALLBACK=false

# Opcional (usuários podem configurar via bot)
GOOGLE_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

**Salvar:**
- `Ctrl + O` (salvar)
- `Enter` (confirmar)
- `Ctrl + X` (sair)

**IMPORTANTE:** Vamos atualizar `SHOPEE_API_PUBLIC_URL` depois de configurar o Cloudflare Tunnel.

---

### Passo 8: Subir Containers

#### 8.1. Build e Start

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

**Esperado:**
```
[+] Building ...
[+] Running 4/4
 ✔ Network shopee_network           Created
 ✔ Container shopee_postgres        Started
 ✔ Container shopee_evolution       Started
 ✔ Container shopee_api             Started
```

**Tempo estimado:** 5-10 minutos (primeira vez)

#### 8.2. Verificar Status

```bash
docker compose -f docker-compose.prod.yml ps
```

**Esperado:**
```
NAME                IMAGE                           STATUS
shopee_api          shopee-booster-api             Up (healthy)
shopee_evolution    atendai/evolution-api:v2.1.1   Up (healthy)
shopee_postgres     postgres:15-alpine             Up (healthy)
```

**Se algum container não estiver `Up (healthy)`, veja os logs:**

```bash
docker compose -f docker-compose.prod.yml logs -f shopee_api
docker compose -f docker-compose.prod.yml logs -f shopee_evolution
docker compose -f docker-compose.prod.yml logs -f shopee_postgres
```

#### 8.3. Testar Health Checks

```bash
curl http://localhost:8787/health
```

**Esperado:**
```json
{"status":"ok"}
```

```bash
curl http://localhost:8080/health
```

**Esperado:**
```json
{"status":"ok"}
```

---

### Passo 9: Configurar Cloudflare Tunnel

#### 9.1. Instalar cloudflared

```bash
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared-linux-arm64.deb
```

#### 9.2. Autenticar

```bash
cloudflared tunnel login
```

**O comando irá:**
1. Abrir uma URL no navegador
2. Pedir para você fazer login na Cloudflare
3. Selecionar o domínio (ou criar um gratuito)
4. Autorizar o tunnel

**Se você não tem domínio:**
- Cloudflare oferece subdomínios gratuitos `.trycloudflare.com`
- Ou você pode registrar um domínio barato (~R$ 40/ano)

#### 9.3. Criar Tunnel

```bash
cloudflared tunnel create shopee-booster
```

**Esperado:**
```
Tunnel credentials written to /home/ubuntu/.cloudflared/<TUNNEL_ID>.json
Created tunnel shopee-booster with id <TUNNEL_ID>
```

**Anote o TUNNEL_ID!**

#### 9.4. Configurar Tunnel

```bash
nano ~/.cloudflared/config.yml
```

**Conteúdo:**
```yaml
tunnel: <TUNNEL_ID>
credentials-file: /home/ubuntu/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: bot.seudominio.com
    service: http://localhost:8787
  - service: http_status:404
```

**Substitua:**
- `<TUNNEL_ID>` pelo ID do tunnel criado
- `bot.seudominio.com` pelo seu domínio ou subdomínio

**Salvar:**
- `Ctrl + O`, `Enter`, `Ctrl + X`

#### 9.5. Configurar DNS

**Se você tem domínio próprio:**

1. Vá em Cloudflare Dashboard
2. Selecione seu domínio
3. Vá em **DNS > Records**
4. Adicione um registro CNAME:
   - **Type:** CNAME
   - **Name:** bot (ou outro subdomínio)
   - **Target:** `<TUNNEL_ID>.cfargotunnel.com`
   - **Proxy status:** Proxied (laranja)

**Se você não tem domínio:**
- Use o subdomínio gratuito fornecido pelo Cloudflare
- Exemplo: `shopee-booster-abc123.trycloudflare.com`

#### 9.6. Iniciar Tunnel como Serviço

```bash
sudo cloudflared service install
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
```

#### 9.7. Verificar Status

```bash
sudo systemctl status cloudflared
```

**Esperado:**
```
● cloudflared.service - cloudflared
     Loaded: loaded
     Active: active (running)
```

#### 9.8. Testar URL Pública

```bash
curl https://bot.seudominio.com/health
```

**Esperado:**
```json
{"status":"ok"}
```

---

### Passo 10: Atualizar SHOPEE_API_PUBLIC_URL

#### 10.1. Editar .env

```bash
nano .env
```

#### 10.2. Atualizar URL

**Antes:**
```env
SHOPEE_API_PUBLIC_URL=https://TEMPORARIO_SERA_ATUALIZADO_DEPOIS
```

**Depois:**
```env
SHOPEE_API_PUBLIC_URL=https://bot.seudominio.com
```

**Salvar:**
- `Ctrl + O`, `Enter`, `Ctrl + X`

#### 10.3. Reiniciar Containers

```bash
docker compose -f docker-compose.prod.yml restart shopee_api
```

#### 10.4. Verificar Logs

```bash
docker compose -f docker-compose.prod.yml logs -f shopee_api | grep "SHOPEE_API_PUBLIC_URL"
```

---

### Passo 11: Configurar Webhook da Evolution

#### 11.1. Chamar Endpoint

```bash
curl -X POST http://localhost:8787/evolution/setup-webhook \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "admin",
    "shop_uid": "setup"
  }'
```

**Esperado:**
```json
{
  "ok": true,
  "message": "Webhook configurado com sucesso",
  "webhook_url": "https://bot.seudominio.com/webhook/evolution"
}
```

**Se der erro:**
- Verifique se `SHOPEE_API_PUBLIC_URL` está correto no `.env`
- Verifique se `EVOLUTION_API_KEY` está correto no `.env`
- Veja os logs: `docker compose -f docker-compose.prod.yml logs -f shopee_api`

---

### Passo 12: Escanear QR Code

#### 12.1. Obter QR Code

**Via curl:**
```bash
curl http://localhost:8080/instance/connect/shopee_booster \
  -H "apikey: SUA_EVOLUTION_API_KEY"
```

**OU via navegador:**

1. Abra: `http://123.45.67.89:8080/instance/connect/shopee_booster`
2. Adicione header `apikey: SUA_EVOLUTION_API_KEY` (use extensão como ModHeader)

**OU via túnel SSH:**

```bash
# No seu PC local
ssh -i ~/Downloads/ssh-key-YYYY-MM-DD.key -L 8080:localhost:8080 ubuntu@123.45.67.89
```

Depois abra no navegador: `http://localhost:8080/instance/connect/shopee_booster`

#### 12.2. Escanear no WhatsApp

1. Abra WhatsApp no celular
2. Vá em **Configurações > Aparelhos conectados**
3. Clique em **Conectar um aparelho**
4. Escaneie o QR Code exibido

**Esperado:**
```
✅ Conectado com sucesso!
```

---

### Passo 13: Verificar Conexão

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

---

### Passo 14: Testar Bot no WhatsApp

#### 14.1. Enviar Mensagem

No WhatsApp, envie para o número conectado:

```
/menu
```

#### 14.2. Esperado

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

#### 14.3. Testar Outros Comandos

```
/loja
/ia
/telegram
/sentinela status
/ajuda
```

---

## ✅ Checklist de Validação

### Infraestrutura

- [ ] VM Oracle criada e rodando
- [ ] SSH funcionando
- [ ] Docker e Docker Compose instalados
- [ ] Firewall configurado (Oracle + UFW)

### Deploy

- [ ] Repositório clonado
- [ ] `.env` criado com chaves novas
- [ ] Containers rodando (`docker compose ps`)
- [ ] Todos os containers `Up (healthy)`
- [ ] Health checks passando (`/health`)

### Rede

- [ ] Cloudflare Tunnel configurado
- [ ] DNS configurado
- [ ] URL pública acessível via HTTPS
- [ ] `SHOPEE_API_PUBLIC_URL` atualizado

### WhatsApp

- [ ] Webhook configurado
- [ ] QR Code escaneado
- [ ] Instância conectada (`state: open`)
- [ ] `/menu` funcionando
- [ ] Outros comandos funcionando

### Funcionalidades

- [ ] `/loja` - Gerenciar lojas
- [ ] `/auditar` - Auditar produto (com mock)
- [ ] `/catalogo` - Importar catálogo
- [ ] `/sentinela` - Monitoramento (com mock)
- [ ] `/ia` - Configurar IA
- [ ] `/telegram` - Configurar Telegram
- [ ] `/ajuda` - Ajuda

---

## 🔧 Troubleshooting

### Container não inicia

```bash
# Ver logs
docker compose -f docker-compose.prod.yml logs shopee_api

# Verificar configuração
docker compose -f docker-compose.prod.yml config

# Rebuild forçado
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
curl -X POST http://localhost:8787/evolution/setup-webhook \
  -H "Content-Type: application/json" \
  -d '{"user_id":"admin","shop_uid":"setup"}'
```

### Cloudflare Tunnel não funciona

```bash
# Verificar status
sudo systemctl status cloudflared

# Ver logs
sudo journalctl -u cloudflared -f

# Reiniciar
sudo systemctl restart cloudflared

# Testar manualmente
cloudflared tunnel run shopee-booster
```

### Sem espaço em disco

```bash
# Verificar espaço
df -h

# Limpar imagens não usadas
docker system prune -a

# Limpar volumes não usados
docker volume prune

# Limpar logs antigos
sudo journalctl --vacuum-time=7d
```

---

## 📊 Monitoramento

### Logs em Tempo Real

```bash
# Todos os serviços
docker compose -f docker-compose.prod.yml logs -f

# Apenas ShopeeBooster API
docker compose -f docker-compose.prod.yml logs -f shopee_api

# Apenas Evolution API
docker compose -f docker-compose.prod.yml logs -f evolution_api

# Ver logs de erro
docker compose -f docker-compose.prod.yml logs -f | grep ERROR

# Ver logs do WhatsApp
docker compose -f docker-compose.prod.yml logs -f shopee_api | grep "\[WA\]"

# Ver logs do Sentinela
docker compose -f docker-compose.prod.yml logs -f shopee_api | grep "\[SENTINELA\]"
```

### Uso de Recursos

```bash
# Status dos containers
docker compose -f docker-compose.prod.yml ps

# Uso de recursos
docker stats

# Espaço em disco
df -h

# Memória
free -h

# CPU
top
```

---

## 🔒 Segurança

### Checklist

- [ ] Firewall configurado (UFW + Oracle Security List)
- [ ] HTTPS habilitado (Cloudflare Tunnel)
- [ ] Senhas fortes geradas
- [ ] `.env` não commitado
- [ ] Chaves únicas geradas
- [ ] SSH com chave privada (não senha)
- [ ] Portas desnecessárias fechadas

### Boas Práticas

1. **Nunca exponha portas desnecessárias**
2. **Use HTTPS sempre**
3. **Mantenha sistema atualizado**
4. **Faça backup regularmente**
5. **Monitore logs de erro**
6. **Revogue chaves expostas imediatamente**

---

## 💾 Backup

### Backup Manual

```bash
# Backup data/
tar -czf backup-data-$(date +%Y%m%d).tar.gz data/

# Backup Evolution instances
docker compose -f docker-compose.prod.yml exec evolution_api tar -czf /tmp/instances-backup.tar.gz /evolution/instances
docker cp shopee_evolution:/tmp/instances-backup.tar.gz ./instances-backup-$(date +%Y%m%d).tar.gz

# Backup Postgres
docker compose -f docker-compose.prod.yml exec postgres pg_dump -U evolution evolution > backup-postgres-$(date +%Y%m%d).sql

# Download backups para PC local
scp -i ~/Downloads/ssh-key-YYYY-MM-DD.key ubuntu@123.45.67.89:~/shopee-booster/backup-*.tar.gz ~/backups/
```

### Backup Automático (Opcional)

```bash
# Criar script de backup
nano ~/backup.sh
```

**Conteúdo:**
```bash
#!/bin/bash
cd ~/shopee-booster
tar -czf backup-data-$(date +%Y%m%d).tar.gz data/
# Manter apenas últimos 7 backups
ls -t backup-data-*.tar.gz | tail -n +8 | xargs rm -f
```

**Agendar com cron:**
```bash
chmod +x ~/backup.sh
crontab -e
```

**Adicionar linha:**
```
0 3 * * * /home/ubuntu/backup.sh
```

---

## 📝 Próximos Passos

Após deploy bem-sucedido:

1. ✅ Monitorar logs por 24h
2. ✅ Testar todas as funcionalidades
3. ✅ Configurar backup automático
4. ✅ Documentar para equipe
5. ✅ Configurar Telegram (opcional)
6. ✅ Importar catálogo
7. ✅ Configurar Sentinela
8. ⚠️ **Corrigir provider de concorrentes** (futuro)

---

## ⚠️ Limitações Conhecidas

### Provider de Concorrentes (Mock)

- ⚠️ Concorrentes são simulados (não reais)
- ⚠️ API Mercado Livre retorna 403 Forbidden
- ⚠️ Shopee Playwright não funciona via subprocess

**Impacto:**
- ✅ Auditoria funciona (com concorrentes simulados)
- ✅ Sentinela funciona (com concorrentes simulados)
- ⚠️ Dados não são reais

**Solução futura:**
- Corrigir API do Mercado Livre
- Implementar scraping via proxy
- Usar .exe local para scraping real

### IP de Datacenter

- ⚠️ Oracle usa IP de datacenter
- ⚠️ Pode ter taxa de bloqueio maior em e-commerce

**Recomendação:**
- ✅ Bot 24h → Oracle Cloud
- ✅ Scraping pesado → .exe local (IP residencial)

---

## 📚 Documentação Relacionada

- [DEPLOY_ORACLE.md](DEPLOY_ORACLE.md) - Documentação completa
- [FASE_D1_DEPLOY_ORACLE.md](FASE_D1_DEPLOY_ORACLE.md) - Status da Fase D1
- [AJUSTES_PRE_DEPLOY.md](AJUSTES_PRE_DEPLOY.md) - Ajustes realizados
- [deploy/oracle/README.md](deploy/oracle/README.md) - Scripts de deploy
- [deploy/oracle/CHECKLIST.md](deploy/oracle/CHECKLIST.md) - Checklist completo

---

**Fase D2 — Deploy Real na Oracle Cloud: ✅ PRONTO PARA EXECUÇÃO**

**Pré-requisito:** Fase D1 concluída ✅  
**Build local:** Testado e passou ✅  
**Documentação:** Completa ✅  
**Tempo estimado:** 1-2 horas

**O Bot está pronto para rodar 24/7 na Oracle Cloud com custo zero!** 🚀

---

**Data:** 27/04/2026  
**Status:** Pronto para execução  
**Próxima fase:** Executar deploy real na Oracle Cloud
