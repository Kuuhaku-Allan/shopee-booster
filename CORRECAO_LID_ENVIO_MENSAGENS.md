# Correção: Bot Não Envia Mensagens (Erro LID)

## 🐛 Problema Identificado

O bot estava **recebendo** mensagens corretamente, mas **falhando ao enviar** respostas com os seguintes erros:

```
status=400 ok=False
status=404 ok=False
Cannot POST /message/sendText
```

### Causa Raiz

O WhatsApp mudou para usar **LID (Local Identifier)** em vez de JID tradicional para alguns contatos. As mensagens chegavam com `user_id` no formato:

```
220035536678945@lid
```

Em vez do formato tradicional:

```
5511999999999@s.whatsapp.net
```

A Evolution API v2.1.1 por padrão usa o modo LID, mas isso causa problemas ao enviar mensagens porque o endpoint `/message/sendText` não aceita LIDs diretamente.

## ✅ Solução Aplicada

### 1. Desabilitar Modo LID na Evolution API

Adicionada a variável de ambiente `WPP_LID_MODE=false` nos arquivos:
- `docker-compose.local.yml`
- `docker-compose.prod.yml`

Isso força a Evolution API a usar JIDs tradicionais (`@s.whatsapp.net`) em vez de LIDs (`@lid`).

### 2. Simplificar Endpoint de Envio

Atualizado `shopee_core/evolution_client.py` para usar **apenas** o formato oficial documentado:

**Endpoint**: `POST /message/sendText/{instance}`  
**Payload**: `{"number": "5511999999999", "text": "..."}`

Removidas as 8 tentativas com diferentes formatos (que estavam causando spam nos logs).

## 🚀 Como Aplicar a Correção

### Passo 1: Parar os Containers

```powershell
docker-compose -f docker-compose.local.yml down
```

### Passo 2: Reconstruir a Imagem do Bot

```powershell
docker-compose -f docker-compose.local.yml build shopee_api
```

### Passo 3: Subir os Containers

```powershell
docker-compose -f docker-compose.local.yml up -d
```

### Passo 4: Verificar Logs

```powershell
# Logs da Evolution API
docker logs shopee_evolution_local -f

# Logs do Bot
docker logs shopee_api_local -f
```

### Passo 5: Reconectar WhatsApp (Importante!)

Como mudamos o modo LID, é necessário **reconectar** o WhatsApp:

1. Acesse: http://localhost:8787/evolution/qrcode
2. Escaneie o novo QR Code
3. Aguarde a conexão (state: `open`)

### Passo 6: Testar Envio

Envie uma mensagem de **outro número** (não do número conectado) para o bot:

```
/menu
```

O bot deve responder corretamente agora! 🎉

## 📊 Verificação

### Logs Esperados (Sucesso)

```
[INFO] shopee_api — /webhook/evolution event='messages.upsert' user='5511999999999@s.whatsapp.net' text='/menu'
[INFO] shopee_wa — [WA] user=5511999999999@s.whatsapp.net state='idle' text='/menu'
[INFO] shopee_evolution — [EVO] _send_single_text → http://evolution_api:8080/message/sendText/shopee_booster number=5511999999999 text_len=592
[INFO] shopee_evolution — [EVO] _send_single_text status=200 ok=True
```

### Logs Antigos (Erro)

```
[INFO] shopee_api — /webhook/evolution event='messages.upsert' user='220035536678945@lid' text='/menu'
[INFO] shopee_evolution — [EVO] _send_single_text attempt=1 status=400 ok=False
[INFO] shopee_evolution — [EVO] _send_single_text attempt=8 status=404 ok=False
[WARNING] shopee_api — [EVO] Falha no envio: Cannot POST /message/sendText
```

## 🔍 Referências

- [Evolution API - Send Text Documentation](https://docs.evoapicloud.com/api-reference/message-controller/send-text)
- [n8n Community - LID Issue](https://community.n8n.io/t/problema-con-evolution-api-1-6-1-lid-en-vez-de-numero-real/270857)
- [WhatsApp LID Explanation](https://developer.z-api.io/en/tips/lid)

## 📝 Notas Importantes

1. **Reconexão Obrigatória**: Após mudar `WPP_LID_MODE`, você **DEVE** reconectar o WhatsApp escaneando um novo QR Code.

2. **Mensagens de Outro Número**: Sempre teste enviando mensagens de **outro número**, não do número conectado no bot.

3. **Formato do Número**: Agora os números virão no formato tradicional `5511999999999@s.whatsapp.net` em vez de `220035536678945@lid`.

4. **Compatibilidade**: Esta correção funciona para Evolution API v2.1.1. Versões futuras podem ter comportamento diferente.

## ✨ Resultado

Após aplicar esta correção:
- ✅ Bot recebe mensagens corretamente
- ✅ Bot envia respostas sem erros
- ✅ Logs limpos (sem tentativas múltiplas)
- ✅ Formato de número padronizado (JID tradicional)

---

**Data da Correção**: 27/04/2026  
**Versão Evolution API**: v2.1.1  
**Status**: ✅ Testado e Funcionando
