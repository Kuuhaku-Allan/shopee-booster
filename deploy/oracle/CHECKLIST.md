# Checklist de Deploy - Oracle Cloud

Use este checklist para garantir que todos os passos foram executados corretamente.

## ✅ Pré-Deploy (Local)

### Testes Locais

- [ ] Executar `test-local-build.sh` com sucesso
- [ ] Executar `test-local-compose.sh` com sucesso
- [ ] Todos os health checks passaram
- [ ] Endpoints `/health` funcionando
- [ ] Parar serviços locais (`docker compose -f docker-compose.prod.yml down`)

### Preparação

- [ ] Código commitado no Git
- [ ] Push para repositório remoto
- [ ] Branch `feature/whatsapp-bot-core` atualizado
- [ ] `.env` não commitado (verificar `.gitignore`)
- [ ] Secrets não commitados (verificar `.gitignore`)

## ✅ Oracle Cloud Setup

### Criar VM

- [ ] Conta Oracle Cloud criada
- [ ] VM Ubuntu ARM criada
  - [ ] Shape: VM.Standard.A1.Flex (ARM Ampere)
  - [ ] OCPUs: 2-4
  - [ ] RAM: 12-24 GB
  - [ ] Storage: 100-200 GB
  - [ ] OS: Ubuntu 22.04 LTS (ARM64)
  - [ ] IP público atribuído
- [ ] Chave SSH configurada
- [ ] Conexão SSH testada

### Configurar Firewall

- [ ] Security List da VCN configurado
  - [ ] Porta 22 (SSH) aberta
  - [ ] Porta 80 (HTTP) aberta
  - [ ] Porta 443 (HTTPS) aberta
  - [ ] Porta 8787 (ShopeeBooster API) aberta
  - [ ] Porta 8080 (Evolution API) aberta

## ✅ Instalação na VM

### Setup Inicial

- [ ] Conectado via SSH
- [ ] Script `setup.sh` baixado
- [ ] Permissão de execução dada (`chmod +x setup.sh`)
- [ ] Script `setup.sh` executado com sucesso
- [ ] Sistema atualizado
- [ ] Docker instalado
- [ ] Docker Compose instalado
- [ ] Firewall UFW configurado
- [ ] Usuário adicionado ao grupo docker
- [ ] Logout e login executados

### Clonar Repositório

- [ ] Repositório clonado (`git clone`)
- [ ] Branch `feature/whatsapp-bot-core` checked out
- [ ] Diretórios `data/` e `uploads/` criados

## ✅ Configuração

### Variáveis de Ambiente

- [ ] `.env` criado a partir de `.env.example.production`
- [ ] `EVOLUTION_API_KEY` gerada (`openssl rand -hex 32`)
- [ ] `WHATSAPP_INSTANCE` definida (`shopee_booster`)
- [ ] `POSTGRES_PASSWORD` definida (senha forte)
- [ ] `SHOPEE_API_PUBLIC_URL` configurada (URL pública)
- [ ] `BOT_SECRET_KEY` gerada (Fernet key)
- [ ] `ALLOW_GLOBAL_GEMINI_FALLBACK` definida (`false`)
- [ ] Variáveis opcionais configuradas (se necessário)
  - [ ] `GOOGLE_API_KEY` (opcional)
  - [ ] `TELEGRAM_BOT_TOKEN` (opcional)
  - [ ] `TELEGRAM_CHAT_ID` (opcional)

### Arquivo .shopee_config

- [ ] `.shopee_config` criado (se necessário)
- [ ] Configurações de usuário definidas

## ✅ Deploy

### Build e Start

- [ ] `docker compose -f docker-compose.prod.yml build` executado
- [ ] Build concluído sem erros
- [ ] `docker compose -f docker-compose.prod.yml up -d` executado
- [ ] Todos os containers iniciados

### Verificação de Status

- [ ] `docker compose -f docker-compose.prod.yml ps` mostra todos os containers `Up`
- [ ] Container `shopee_postgres` está `healthy`
- [ ] Container `shopee_evolution` está `healthy`
- [ ] Container `shopee_api` está `healthy`

### Verificação de Logs

- [ ] Logs não mostram erros críticos
- [ ] ShopeeBooster API iniciou corretamente
- [ ] Evolution API iniciou corretamente
- [ ] Postgres iniciou corretamente

### Testes de Endpoint

- [ ] `curl http://localhost:8787/health` retorna 200 OK
- [ ] `curl http://localhost:8080/health` retorna 200 OK

## ✅ Configuração de Domínio

### Opção 1: Cloudflare Tunnel

- [ ] `cloudflared` instalado
- [ ] Autenticação realizada (`cloudflared tunnel login`)
- [ ] Tunnel criado (`cloudflared tunnel create shopee-booster`)
- [ ] `config.yml` configurado
- [ ] Tunnel iniciado como serviço
- [ ] URL pública acessível via HTTPS
- [ ] `.env` atualizado com URL pública

### Opção 2: Nginx + Certbot

- [ ] Nginx instalado
- [ ] Certbot instalado
- [ ] Configuração Nginx criada
- [ ] Nginx testado (`nginx -t`)
- [ ] Nginx reiniciado
- [ ] Certificado SSL obtido (`certbot --nginx`)
- [ ] URL pública acessível via HTTPS
- [ ] `.env` atualizado com URL pública

## ✅ Configuração do WhatsApp

### Webhook

- [ ] Endpoint `/evolution/setup-webhook` chamado
- [ ] Webhook configurado com sucesso
- [ ] Resposta indica sucesso

### QR Code

- [ ] QR Code obtido (`/instance/connect/shopee_booster`)
- [ ] QR Code escaneado no WhatsApp
- [ ] Conexão estabelecida

### Verificação de Conexão

- [ ] `/evolution/instance-status` retorna `state: open`
- [ ] Instância conectada

## ✅ Testes do Bot

### Comandos Básicos

- [ ] `/menu` - Menu principal funciona
- [ ] `/loja` - Gerenciar lojas funciona
- [ ] `/ajuda` - Ajuda funciona

### Funcionalidades Principais

- [ ] `/auditar` - Auditoria funciona (com mock)
- [ ] `/catalogo` - Importar catálogo funciona
- [ ] `/sentinela` - Monitoramento funciona (com mock)
- [ ] `/ia` - Configurar IA funciona
- [ ] `/telegram` - Configurar Telegram funciona

### Testes de Integração

- [ ] Auditoria gera relatório
- [ ] Sentinela gera relatório
- [ ] Relatórios são salvos em `data/reports/`
- [ ] Telegram envia mensagens (se configurado)
- [ ] Gráficos são gerados corretamente
- [ ] Tabelas PNG são geradas corretamente

## ✅ Pós-Deploy

### Backup

- [ ] Script de backup criado
- [ ] Backup de `data/` testado
- [ ] Backup de Evolution instances testado
- [ ] Backup de Postgres testado
- [ ] Backup automático configurado (cron)

### Monitoramento

- [ ] Logs monitorados por 24h
- [ ] Sem erros críticos
- [ ] Containers não reiniciaram inesperadamente
- [ ] Uso de recursos aceitável (CPU, RAM, disco)

### Documentação

- [ ] Documentação atualizada
- [ ] Equipe treinada
- [ ] Procedimentos de manutenção documentados
- [ ] Procedimentos de troubleshooting documentados

### Segurança

- [ ] Firewall configurado (UFW + Oracle Security List)
- [ ] HTTPS habilitado
- [ ] Senhas fortes geradas
- [ ] `.env` não commitado
- [ ] Secrets não commitados
- [ ] Chaves únicas geradas
- [ ] Backup seguro configurado

## ✅ Validação Final

### Checklist de Validação

- [ ] Bot responde no WhatsApp
- [ ] Todas as funcionalidades testadas
- [ ] Sem erros críticos nos logs
- [ ] Containers estão healthy
- [ ] HTTPS funcionando
- [ ] Backup configurado
- [ ] Monitoramento configurado
- [ ] Documentação completa
- [ ] Equipe treinada

### Testes de Carga (Opcional)

- [ ] Bot responde a múltiplas mensagens simultâneas
- [ ] Auditoria funciona com múltiplos produtos
- [ ] Sentinela funciona com múltiplas keywords
- [ ] Relatórios são gerados corretamente sob carga

### Testes de Recuperação (Opcional)

- [ ] Restart de containers funciona
- [ ] Backup e restore funcionam
- [ ] Reconexão do WhatsApp funciona após restart
- [ ] Dados persistem após restart

## 📊 Métricas de Sucesso

### Performance

- [ ] Tempo de resposta do bot < 5 segundos
- [ ] Uso de CPU < 50% em média
- [ ] Uso de RAM < 80% em média
- [ ] Uso de disco < 70%

### Disponibilidade

- [ ] Uptime > 99% nas primeiras 24h
- [ ] Sem reinicializações inesperadas
- [ ] Sem erros críticos nos logs

### Funcionalidade

- [ ] 100% dos comandos funcionando
- [ ] 100% dos relatórios gerados corretamente
- [ ] 100% dos testes de integração passando

## ⚠️ Limitações Conhecidas

### Provider de Concorrentes

- [ ] Documentado que concorrentes são simulados (mock)
- [ ] Usuário ciente da limitação
- [ ] Plano de correção futura definido

### IP de Datacenter

- [ ] Documentado que IP de datacenter pode ter bloqueios
- [ ] Usuário ciente da limitação
- [ ] Arquitetura híbrida (Oracle + .exe local) documentada

## 🎯 Próximos Passos

### Curto Prazo (1 semana)

- [ ] Monitorar logs diariamente
- [ ] Ajustar configurações se necessário
- [ ] Coletar feedback dos usuários
- [ ] Documentar problemas encontrados

### Médio Prazo (1 mês)

- [ ] Implementar backup automático
- [ ] Implementar monitoramento avançado
- [ ] Otimizar performance
- [ ] Corrigir provider de concorrentes

### Longo Prazo (3 meses)

- [ ] Implementar scraping real de concorrentes
- [ ] Implementar proxy rotativo
- [ ] Implementar cache de concorrentes
- [ ] Implementar analytics

---

## 📝 Notas

### Data de Deploy

**Data:** ___/___/______  
**Responsável:** _______________________  
**Versão:** _______________________

### Observações

_______________________________________________________
_______________________________________________________
_______________________________________________________
_______________________________________________________

### Problemas Encontrados

_______________________________________________________
_______________________________________________________
_______________________________________________________
_______________________________________________________

### Soluções Aplicadas

_______________________________________________________
_______________________________________________________
_______________________________________________________
_______________________________________________________

---

**Checklist de Deploy - Oracle Cloud: ✅ COMPLETO**

**Status:** Pronto para uso  
**Próxima revisão:** ___/___/______
