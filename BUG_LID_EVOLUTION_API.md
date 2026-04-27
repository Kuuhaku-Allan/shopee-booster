# 🐛 BUG: Evolution API v2.1.1 - LID Não Converte para JID

**Data**: 27/04/2026  
**Status**: ❌ NÃO RESOLVIDO  
**Severidade**: CRÍTICA - Bot não consegue enviar mensagens

---

## 📋 Resumo do Problema

A Evolution API v2.1.1 está enviando números no formato **LID** (`220035536678945@lid`) em vez de JID tradicional (`5511988600050@s.whatsapp.net`), mesmo com `WPP_LID_MODE=false` configurado.

Quando o bot tenta enviar mensagem para o LID, a Evolution API retorna erro 400:

```json
{
  "status": 400,
  "error": "Bad Request",
  "response": {
    "message": [{
      "exists": false,
      "jid": "220035536678945@s.whatsapp.net",
      "number": "220035536678945"
    }]
  }
}
```

---

## 🔍 Diagnóstico Completo

### Configuração Aplicada

**Arquivo**: `docker-compose.local.yml`

```yaml
evolution_api:
  environment:
    # LID Mode (desabilitar para usar JID tradicional)
    WPP_LID_MODE: "false"
```

**Verificação**: ✅ Variável está no ambiente do container

```bash
$ docker exec shopee_evolution_local env | grep WPP_LID
WPP_LID_MODE=false
```

### Logs do Problema

**Bot recebe mensagem com LID**:
```
2026-04-27 23:33:14,914 [INFO] shopee_api — /webhook/evolution event='messages.upsert' user='220035536678945@lid' from_me=False text='/menu'
```

**Bot tenta enviar para o número extraído do LID**:
```
2026-04-27 23:33:14,983 [INFO] shopee_evolution — [EVO] _send_single_text → http://evolution_api:8080/message/sendText/shopee_booster number=220035536678945 text_len=592
```

**Evolution API retorna erro 400**:
```
2026-04-27 23:33:15,305 [ERROR] shopee_evolution — [EVO] _send_single_text FALHOU: status=400 response={"status":400,"error":"Bad Request","response":{"message":[{"exists":false,"jid":"220035536678945@s.whatsapp.net","number":"220035536678945"}]}}
```

---

## 🔧 Tentativas de Correção

### 1. ✅ Adicionado `WPP_LID_MODE=false`
- **Arquivo**: `docker-compose.local.yml` e `docker-compose.prod.yml`
- **Resultado**: Variável carregada, mas LID continua

### 2. ✅ Reiniciado Evolution API
- **Comando**: `docker-compose restart evolution_api`
- **Resultado**: LID continua

### 3. ✅ Desconectado e Reconectado WhatsApp
- **Comando**: `DELETE /instance/logout/shopee_booster`
- **Resultado**: LID continua mesmo após nova conexão

### 4. ✅ Corrigido Endpoint de Envio
- **Arquivo**: `shopee_core/evolution_client.py`
- **Mudança**: Simplificado para usar apenas formato oficial
- **Resultado**: Endpoint correto, mas número LID inválido

---

## 🎯 Números Reais Envolvidos

- **Número do Bot** (conectado na Evolution): `5511989554756`
- **Número do Usuário** (enviando /menu): `5511988600050`
- **LID recebido pela Evolution**: `220035536678945@lid`
- **Número extraído do LID**: `220035536678945` (INVÁLIDO)

**O número `220035536678945` NÃO corresponde a nenhum dos números reais!**

---

## 📊 Comparação: Esperado vs Real

| Aspecto | Esperado | Real |
|---------|----------|------|
| **Formato recebido** | `5511988600050@s.whatsapp.net` | `220035536678945@lid` |
| **WPP_LID_MODE** | `false` | `false` ✅ |
| **Número extraído** | `5511988600050` | `220035536678945` |
| **Envio** | Sucesso (200) | Erro 400 |
| **Mensagem de erro** | - | `{"exists": false}` |

---

## 🔍 Análise Técnica

### Por que o LID não converte?

1. **Bug da Evolution API v2.1.1**: A variável `WPP_LID_MODE=false` não está sendo respeitada
2. **Sessão antiga**: Mesmo reconectando, a sessão pode estar mantendo o modo LID
3. **Versão do Baileys**: A biblioteca subjacente pode ter mudado o comportamento padrão

### Por que o número é diferente?

O LID `220035536678945` é um **identificador interno** do WhatsApp que não corresponde ao número real. É como um "apelido" que o WhatsApp usa internamente.

---

## 🚀 Soluções Possíveis

### Opção 1: Downgrade da Evolution API (RECOMENDADO)

Usar uma versão anterior que não tinha o problema de LID:

```yaml
evolution_api:
  image: atendai/evolution-api:v2.0.10  # ou v1.x.x
```

### Opção 2: Usar Fork Alternativo

Alguns forks da Evolution API corrigiram esse problema:
- `codechat/evolution-api`
- Outros forks da comunidade

### Opção 3: Mapear LID para JID

Criar um mapeamento manual no código:

```python
# Mapeamento temporário LID → JID
LID_TO_JID_MAP = {
    "220035536678945@lid": "5511988600050@s.whatsapp.net"
}

def normalize_whatsapp_number(user_id: str) -> str:
    # Verificar se é LID e mapear
    if user_id in LID_TO_JID_MAP:
        user_id = LID_TO_JID_MAP[user_id]
    
    # Resto do código...
```

### Opção 4: Reportar Bug Oficial

Abrir issue no repositório oficial:
- https://github.com/EvolutionAPI/evolution-api/issues

---

## 📝 Arquivos Modificados

### Correções Aplicadas (mas não resolveram)

1. ✅ `docker-compose.local.yml` - Adicionado `WPP_LID_MODE=false`
2. ✅ `docker-compose.prod.yml` - Adicionado `WPP_LID_MODE=false`
3. ✅ `shopee_core/evolution_client.py` - Corrigido endpoint de envio
4. ✅ `api_server.py` - Adicionado endpoint `/evolution/qrcode`

### Documentação Criada

1. ✅ `CORRECAO_LID_ENVIO_MENSAGENS.md`
2. ✅ `APLICAR_CORRECAO_AGORA.md`
3. ✅ `U7_5_CORRECAO_LID_IMPLEMENTADA.md`
4. ✅ `deploy/local/fix-lid-restart.ps1`
5. ✅ `BUG_LID_EVOLUTION_API.md` (este arquivo)

---

## 🔗 Referências

1. **n8n Community - LID Issue**  
   https://community.n8n.io/t/problema-con-evolution-api-1-6-1-lid-en-vez-de-numero-real/270857

2. **Evolution API Documentation**  
   https://docs.evoapicloud.com/api-reference/message-controller/send-text

3. **WhatsApp LID Explanation**  
   https://developer.z-api.io/en/tips/lid

4. **Baileys GitHub - LID Groups Issue**  
   https://github.com/WhiskeySockets/Baileys/issues/1465

---

## ⚠️ Conclusão

O problema **NÃO é o número do usuário** (que é real e válido).  
O problema **É um bug da Evolution API v2.1.1** que não respeita `WPP_LID_MODE=false`.

**Recomendação**: Fazer downgrade para Evolution API v2.0.10 ou usar fork alternativo.

---

**Última atualização**: 27/04/2026 23:35  
**Tempo gasto tentando resolver**: ~3 dias  
**Status**: Problema não resolvido, requer mudança de versão da Evolution API
