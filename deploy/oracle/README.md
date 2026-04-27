# Deploy Oracle Cloud - Scripts e Ferramentas

Esta pasta contém scripts e ferramentas para fazer deploy do **ShopeeBooster WhatsApp Bot** na Oracle Cloud Always Free.

## 📁 Arquivos

### setup.sh

**Descrição:** Script de instalação automatizado para Oracle Cloud Ubuntu ARM.

**O que faz:**
- Atualiza sistema Ubuntu
- Instala Docker e Docker Compose
- Configura firewall UFW
- Cria diretórios necessários
- Adiciona usuário ao grupo docker

**Como usar:**

```bash
# Download
curl -fsSL https://raw.githubusercontent.com/Kuuhaku-Allan/shopee-booster/feature/whatsapp-bot-core/deploy/oracle/setup.sh -o setup.sh

# Permissão
chmod +x setup.sh

# Executar
./setup.sh

# Logout e login novamente
exit
ssh ubuntu@<IP_PUBLICO_VM>
```

### test-local-build.sh

**Descrição:** Testa build do `Dockerfile.api` localmente antes de fazer deploy.

**O que faz:**
- Verifica se Docker está instalado
- Verifica se todos os arquivos necessários existem
- Faz build da imagem Docker
- Testa se a imagem inicia corretamente
- Testa health check
- Limpa imagem de teste

**Como usar:**

```bash
# Permissão
chmod +x deploy/oracle/test-local-build.sh

# Executar
./deploy/oracle/test-local-build.sh
```

**Esperado:**

```
════════════════════════════════════════════════════════════
Teste Local - Build Dockerfile.api
════════════════════════════════════════════════════════════

ℹ Verificando Docker...
✓ Docker instalado
ℹ Verificando arquivos necessários...
✓ Todos os arquivos necessários encontrados
ℹ Fazendo build da imagem...
✓ Build concluído com sucesso!
ℹ Verificando tamanho da imagem...
ℹ Testando se a imagem inicia...
✓ Container iniciado: abc123...
ℹ Aguardando 10 segundos para o container inicializar...
ℹ Logs do container:
ℹ Testando health check...
✓ Health check passou!
ℹ Parando container...
✓ Container parado
ℹ Limpando imagem de teste...
✓ Imagem removida

════════════════════════════════════════════════════════════
Teste concluído com sucesso! ✅
════════════════════════════════════════════════════════════
```

### test-local-compose.sh

**Descrição:** Testa `docker-compose.prod.yml` localmente antes de fazer deploy.

**O que faz:**
- Verifica se Docker Compose está instalado
- Verifica se `.env` existe (cria a partir de `.env.example.production` se não existir)
- Valida sintaxe do `docker-compose.prod.yml`
- Faz build das imagens
- Inicia serviços
- Aguarda serviços ficarem healthy
- Testa endpoints (health checks)
- Mostra logs recentes

**Como usar:**

```bash
# Permissão
chmod +x deploy/oracle/test-local-compose.sh

# Executar
./deploy/oracle/test-local-compose.sh
```

**Esperado:**

```
════════════════════════════════════════════════════════════
Teste Local - docker-compose.prod.yml
════════════════════════════════════════════════════════════

ℹ Verificando Docker Compose...
✓ Docker Compose instalado
ℹ Verificando .env...
✓ .env encontrado
ℹ Validando sintaxe do docker-compose.prod.yml...
✓ Sintaxe válida!
ℹ Fazendo build das imagens...
✓ Build concluído!
ℹ Iniciando serviços...
✓ Serviços iniciados!
ℹ Aguardando serviços ficarem healthy (até 60 segundos)...
  Postgres: healthy | Evolution: healthy | ShopeeAPI: healthy
✓ Todos os serviços estão healthy!
ℹ Status dos containers:
NAME                IMAGE                           STATUS
shopee_api          shopee-booster-api             Up (healthy)
shopee_evolution    atendai/evolution-api:latest   Up (healthy)
shopee_postgres     postgres:15-alpine             Up (healthy)
ℹ Testando endpoints...
✓ ShopeeBooster API: OK
✓ Evolution API: OK

════════════════════════════════════════════════════════════
Teste concluído! ✅
════════════════════════════════════════════════════════════

Serviços rodando:
  - ShopeeBooster API: http://localhost:8787
  - Evolution API: http://localhost:8080
  - Postgres: localhost:5432

Comandos úteis:
  - Ver logs: docker compose -f docker-compose.prod.yml logs -f
  - Parar: docker compose -f docker-compose.prod.yml down
  - Restart: docker compose -f docker-compose.prod.yml restart

Próximos passos:
  1. Configurar webhook: curl -X POST http://localhost:8787/evolution/setup-webhook
  2. Escanear QR Code: http://localhost:8080/instance/connect/shopee_booster
  3. Testar bot no WhatsApp: /menu

Para parar os serviços:
  docker compose -f docker-compose.prod.yml down
```

## 🚀 Fluxo de Trabalho Recomendado

### 1. Testar Localmente (Antes de Deploy)

```bash
# 1. Testar build do Dockerfile
./deploy/oracle/test-local-build.sh

# 2. Testar docker-compose completo
./deploy/oracle/test-local-compose.sh

# 3. Se tudo passou, parar serviços locais
docker compose -f docker-compose.prod.yml down
```

### 2. Deploy na Oracle Cloud

```bash
# 1. Conectar via SSH
ssh ubuntu@<IP_PUBLICO_VM>

# 2. Executar setup
curl -fsSL https://raw.githubusercontent.com/Kuuhaku-Allan/shopee-booster/feature/whatsapp-bot-core/deploy/oracle/setup.sh -o setup.sh
chmod +x setup.sh
./setup.sh

# 3. Logout e login novamente
exit
ssh ubuntu@<IP_PUBLICO_VM>

# 4. Clonar repositório
git clone https://github.com/Kuuhaku-Allan/shopee-booster.git ~/shopee-booster
cd ~/shopee-booster
git checkout feature/whatsapp-bot-core

# 5. Configurar .env
cp .env.example.production .env
nano .env

# 6. Iniciar serviços
docker compose -f docker-compose.prod.yml up -d --build

# 7. Verificar logs
docker compose -f docker-compose.prod.yml logs -f
```

### 3. Configurar WhatsApp

```bash
# 1. Configurar webhook
curl -X POST http://localhost:8787/evolution/setup-webhook \
  -H "Content-Type: application/json" \
  -d '{"user_id": "admin", "shop_uid": "setup"}'

# 2. Obter QR Code
curl http://localhost:8080/instance/connect/shopee_booster \
  -H "apikey: SUA_EVOLUTION_API_KEY"

# 3. Escanear QR Code no WhatsApp

# 4. Testar bot
# Enviar /menu no WhatsApp
```

## 🔧 Troubleshooting

### Build falha

```bash
# Ver logs detalhados
docker build -f Dockerfile.api -t shopee-booster-api:debug . --progress=plain

# Verificar arquivos necessários
ls -la api_server.py backend_core.py telegram_service.py sentinela_db.py
ls -la shopee_core/
```

### Container não inicia

```bash
# Ver logs
docker compose -f docker-compose.prod.yml logs shopee_api

# Verificar variáveis de ambiente
docker compose -f docker-compose.prod.yml config

# Rebuild forçado
docker compose -f docker-compose.prod.yml up -d --build --force-recreate
```

### Health check falha

```bash
# Testar manualmente
curl http://localhost:8787/health
curl http://localhost:8080/health

# Ver logs de erro
docker compose -f docker-compose.prod.yml logs -f | grep ERROR
```

### Postgres não conecta

```bash
# Verificar status
docker compose -f docker-compose.prod.yml exec postgres pg_isready -U evolution

# Verificar logs
docker compose -f docker-compose.prod.yml logs postgres

# Recriar volume (CUIDADO: apaga dados!)
docker compose -f docker-compose.prod.yml down -v
docker compose -f docker-compose.prod.yml up -d
```

## 📚 Documentação Relacionada

- [DEPLOY_ORACLE.md](../../DEPLOY_ORACLE.md) - Documentação completa de deploy
- [FASE_D1_DEPLOY_ORACLE.md](../../FASE_D1_DEPLOY_ORACLE.md) - Status da Fase D1
- [docker-compose.prod.yml](../../docker-compose.prod.yml) - Configuração de serviços
- [Dockerfile.api](../../Dockerfile.api) - Container FastAPI
- [.env.example.production](../../.env.example.production) - Template de variáveis

## 🤝 Suporte

### Logs Úteis

```bash
# Ver todos os logs
docker compose -f docker-compose.prod.yml logs -f

# Ver logs de um serviço específico
docker compose -f docker-compose.prod.yml logs -f shopee_api
docker compose -f docker-compose.prod.yml logs -f evolution_api
docker compose -f docker-compose.prod.yml logs -f postgres

# Ver logs de erro
docker compose -f docker-compose.prod.yml logs -f | grep ERROR

# Ver logs do WhatsApp
docker compose -f docker-compose.prod.yml logs -f shopee_api | grep "\[WA\]"

# Ver logs do Sentinela
docker compose -f docker-compose.prod.yml logs -f shopee_api | grep "\[SENTINELA\]"
```

### Comandos Úteis

```bash
# Status dos containers
docker compose -f docker-compose.prod.yml ps

# Restart de um serviço
docker compose -f docker-compose.prod.yml restart shopee_api

# Parar todos os serviços
docker compose -f docker-compose.prod.yml down

# Parar e remover volumes (CUIDADO: apaga dados!)
docker compose -f docker-compose.prod.yml down -v

# Rebuild de um serviço
docker compose -f docker-compose.prod.yml up -d --build shopee_api

# Entrar no container
docker compose -f docker-compose.prod.yml exec shopee_api bash
docker compose -f docker-compose.prod.yml exec postgres psql -U evolution
```

## ⚠️ Avisos Importantes

1. **Nunca commite o arquivo `.env` com valores reais!**
2. **Use senhas fortes e únicas para cada serviço**
3. **Mantenha as chaves em segredo**
4. **Revogue e regenere chaves se forem expostas**
5. **Use HTTPS em produção (Cloudflare Tunnel ou domínio próprio)**
6. **Faça backup regularmente**
7. **Monitore logs de erro**

## 📝 Checklist de Deploy

- [ ] Testar build localmente (`test-local-build.sh`)
- [ ] Testar docker-compose localmente (`test-local-compose.sh`)
- [ ] Criar VM Oracle Cloud
- [ ] Configurar firewall Oracle
- [ ] Executar `setup.sh` na VM
- [ ] Clonar repositório
- [ ] Configurar `.env`
- [ ] Gerar chaves secretas
- [ ] Iniciar serviços
- [ ] Configurar domínio (Cloudflare Tunnel ou Nginx)
- [ ] Configurar webhook
- [ ] Escanear QR Code
- [ ] Testar bot no WhatsApp
- [ ] Configurar backup
- [ ] Monitorar logs

---

**Fase D1 — Deploy Oracle Cloud: ✅ PRONTO**

**Data:** 27/04/2026  
**Status:** Pronto para deploy  
**Próxima fase:** Testar deploy em VM Oracle
