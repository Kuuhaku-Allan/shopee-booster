# Workaround Evolution API v2.1.1 - QR Code

## Problema

A Evolution API v2.1.1 tem um bug conhecido onde o QR Code não é gerado corretamente:
- Endpoint `/instance/connect/:instanceName` retorna `{"count": 0}`
- Manager fica eternamente carregando
- Instância fica em estado `connecting` ou `close`

**Referências:**
- https://github.com/EvolutionAPI/evolution-api/issues (QR Code never appears)

## Solução Aplicada

Adicionar as seguintes variáveis de ambiente no `docker-compose.local.yml`:

```yaml
environment:
  # Cache (workaround para QR Code)
  CACHE_REDIS_ENABLED: "false"
  CACHE_LOCAL_ENABLED: "true"
  
  # Database - desabilitar sync pesado
  DATABASE_SAVE_DATA_CHATS: "false"
  DATABASE_SAVE_DATA_CONTACTS: "false"
  DATABASE_SAVE_DATA_HISTORIC: "false"
  DATABASE_SAVE_DATA_LABELS: "false"
  
  # Versão do telefone
  CONFIG_SESSION_PHONE_VERSION: "2.3000.1033773198"
```

## O Que Cada Configuração Faz

### Cache
- `CACHE_REDIS_ENABLED: "false"` - Desabilita Redis (não temos Redis no stack)
- `CACHE_LOCAL_ENABLED: "true"` - Usa cache local em memória

### Database
- `DATABASE_SAVE_DATA_CHATS: "false"` - Não salva histórico de chats
- `DATABASE_SAVE_DATA_CONTACTS: "false"` - Não salva contatos
- `DATABASE_SAVE_DATA_HISTORIC: "false"` - Não salva histórico completo
- `DATABASE_SAVE_DATA_LABELS: "false"` - Não salva labels

**Motivo:** Reduz carga no banco e evita problemas de sincronização que podem travar a geração do QR Code.

### Versão do Telefone
- `CONFIG_SESSION_PHONE_VERSION: "2.3000.1033773198"` - Fixa versão do WhatsApp Web

**Motivo:** Evita problemas de compatibilidade com versões mais recentes.

## Resultado

✅ QR Code gerado com sucesso  
✅ Instância conecta normalmente  
✅ Webhook funciona  
✅ Bot responde mensagens  

## Impacto

### Positivo
- QR Code funciona
- Conexão estável
- Menos carga no banco

### Negativo
- Não salva histórico de mensagens no banco
- Não salva contatos no banco
- Histórico de conversas não é persistido

**Nota:** Para o caso de uso do ShopeeBooster Bot, isso não é problema pois:
- O bot responde comandos em tempo real
- Não precisa de histórico de mensagens
- Não precisa de lista de contatos persistida

## Aplicação em Produção

Este workaround deve ser aplicado em:
- ✅ `docker-compose.local.yml` (deploy local)
- ✅ `docker-compose.prod.yml` (deploy Oracle Cloud)

## Alternativas Futuras

Se o problema for corrigido em versões futuras da Evolution API:
1. Atualizar para versão mais recente (ex: v2.2.x)
2. Remover o workaround
3. Testar se QR Code funciona sem as configurações

## Data de Aplicação

- **Data:** 27/04/2026
- **Versão Evolution API:** v2.1.1
- **Status:** Funcionando ✅
