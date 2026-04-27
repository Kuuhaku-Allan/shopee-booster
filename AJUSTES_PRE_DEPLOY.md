# Ajustes Pré-Deploy - Fase D1

## ✅ Ajustes Realizados

**Data:** 27/04/2026  
**Motivo:** Recomendações do GPT antes do deploy real

---

## 🔧 Mudanças Implementadas

### 1. Fixar Versão da Evolution API

**Antes:**
```yaml
evolution_api:
  image: atendai/evolution-api:latest
```

**Depois:**
```yaml
evolution_api:
  image: atendai/evolution-api:v2.1.1
```

**Motivo:** A tag `latest` pode mudar e quebrar o bot sem você mexer em nada. Fixamos na versão v2.1.1 que foi testada localmente.

### 2. Remover Volume .shopee_config

**Antes:**
```yaml
volumes:
  - ./data:/app/data
  - ./uploads:/app/uploads
  - ./.shopee_config:/app/.shopee_config
```

**Depois:**
```yaml
volumes:
  - ./data:/app/data
  - ./uploads:/app/uploads
```

**Motivo:** Em produção, todas as variáveis são passadas via `.env`. O `.shopee_config` é usado apenas como override local, mas não é obrigatório. Removê-lo evita que o deploy falhe caso o arquivo não exista na VM.

**Como funciona:**
- O código lê `.env` primeiro
- Depois tenta ler `.shopee_config` (se existir) para sobrepor valores
- Se `.shopee_config` não existir, usa apenas `.env`
- Em produção, usamos apenas `.env`

### 3. Tornar Teste Local Obrigatório

**Adicionado na documentação:**

```bash
# OBRIGATÓRIO: Testar antes de criar VM Oracle
docker compose -f docker-compose.prod.yml config
docker compose -f docker-compose.prod.yml build shopee_api
```

**Motivo:** Evitar descobrir erros dentro da nuvem. Se o build local falhar, NÃO prosseguir para a Oracle.

---

## 🔐 Lembrete: Gerar Chaves Novas

**IMPORTANTE:** Gere chaves novas antes de ir para produção, principalmente:

1. **Evolution API Key:**
   ```bash
   openssl rand -hex 32
   ```

2. **Bot Secret Key (Fernet):**
   ```bash
   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

3. **Postgres Password:**
   - Senha forte única (mínimo 16 caracteres)

4. **Telegram Bot Token (se usar):**
   - Revogar token antigo com @BotFather (`/revoke`)
   - Gerar novo token com @BotFather (`/newbot`)

**Motivo:** Algumas chaves apareceram ao longo dos testes e podem ter sido expostas nos logs.

---

## 📋 Ordem de Deploy Atualizada

### 1. Testar Build Local (OBRIGATÓRIO)

```bash
# Validar sintaxe
docker compose -f docker-compose.prod.yml config

# Testar build
docker compose -f docker-compose.prod.yml build shopee_api

# Se passou, continuar
```

### 2. Criar VM Oracle ARM Ubuntu

- Shape: VM.Standard.A1.Flex (ARM Ampere)
- OCPUs: 2-4
- RAM: 12-24 GB
- Storage: 100-200 GB
- OS: Ubuntu 22.04 LTS (ARM64)

### 3. Configurar Firewall Oracle

- Porta 22 (SSH)
- Porta 80 (HTTP)
- Porta 443 (HTTPS)
- Porta 8787 (ShopeeBooster API)
- Porta 8080 (Evolution API)

### 4. Executar setup.sh

```bash
ssh ubuntu@<IP_PUBLICO_VM>
curl -fsSL https://raw.githubusercontent.com/Kuuhaku-Allan/shopee-booster/feature/whatsapp-bot-core/deploy/oracle/setup.sh -o setup.sh
chmod +x setup.sh
./setup.sh
exit
ssh ubuntu@<IP_PUBLICO_VM>
```

### 5. Clonar Repositório

```bash
git clone https://github.com/Kuuhaku-Allan/shopee-booster.git ~/shopee-booster
cd ~/shopee-booster
git checkout feature/whatsapp-bot-core
```

### 6. Criar .env Real

```bash
cp .env.example.production .env
nano .env
```

**Preencher com chaves NOVAS:**
- `EVOLUTION_API_KEY` (gerar nova)
- `POSTGRES_PASSWORD` (senha forte)
- `SHOPEE_API_PUBLIC_URL` (URL pública)
- `BOT_SECRET_KEY` (gerar nova)
- `ALLOW_GLOBAL_GEMINI_FALLBACK=false`

### 7. Subir Docker Compose

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f
docker compose -f docker-compose.prod.yml ps
```

### 8. Configurar Cloudflare Tunnel/Domínio

```bash
# Instalar cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared-linux-arm64.deb

# Autenticar e criar tunnel
cloudflared tunnel login
cloudflared tunnel create shopee-booster

# Configurar e iniciar
nano ~/.cloudflared/config.yml
sudo cloudflared service install
sudo systemctl start cloudflared
```

### 9. Configurar Webhook

```bash
curl -X POST http://localhost:8787/evolution/setup-webhook \
  -H "Content-Type: application/json" \
  -d '{"user_id": "admin", "shop_uid": "setup"}'
```

### 10. Escanear QR Code

```bash
curl http://localhost:8080/instance/connect/shopee_booster \
  -H "apikey: SUA_EVOLUTION_API_KEY_NOVA"
```

### 11. Testar /menu

Enviar mensagem no WhatsApp:
```
/menu
```

---

## 🔍 Verificações Antes do Deploy

### Checklist Pré-Deploy

- [ ] Build local passou (`docker compose build shopee_api`)
- [ ] Sintaxe do docker-compose válida (`docker compose config`)
- [ ] Chaves novas geradas (Evolution, Bot, Postgres, Telegram)
- [ ] `.env.example.production` revisado
- [ ] Documentação lida (`DEPLOY_ORACLE.md`)
- [ ] Checklist de deploy impresso (`deploy/oracle/CHECKLIST.md`)

### Checklist Pós-Ajustes

- [x] Versão da Evolution API fixada (v2.1.1)
- [x] Volume `.shopee_config` removido
- [x] Teste local tornado obrigatório na documentação
- [x] Lembrete de chaves novas adicionado
- [x] Ordem de deploy atualizada

---

## 📝 Notas Importantes

### Sobre .shopee_config

O arquivo `.shopee_config` é usado apenas localmente como override do `.env`. Em produção:

- ✅ Use apenas `.env` com todas as variáveis
- ✅ Não monte `.shopee_config` como volume
- ✅ O código funciona sem `.shopee_config` se `.env` estiver completo

### Sobre Versão da Evolution API

A versão v2.1.1 foi testada localmente e funciona. Se precisar atualizar:

1. Testar nova versão localmente primeiro
2. Atualizar tag no `docker-compose.prod.yml`
3. Rebuild e testar
4. Só então atualizar na Oracle

### Sobre Chaves Expostas

Durante os testes, algumas chaves podem ter aparecido nos logs:

- ❌ Token do Telegram foi exposto → Revogar e gerar novo
- ❌ Evolution API Key pode ter sido exposta → Gerar nova
- ❌ Bot Secret Key pode ter sido exposta → Gerar nova

**Sempre gere chaves novas antes de produção!**

---

## ✅ Status Final

**Ajustes:** ✅ Concluídos  
**Pronto para:** Teste local de build  
**Próximo passo:** `docker compose -f docker-compose.prod.yml build shopee_api`

---

**Data:** 27/04/2026  
**Commit:** Pendente (ajustes pré-deploy)
