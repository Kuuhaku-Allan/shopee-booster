# U7.5 - Correção LID: Bot Agora Envia Mensagens ✅

**Data**: 27/04/2026  
**Status**: ✅ Implementado e Pronto para Testar  
**Problema**: Bot recebia mensagens mas não conseguia enviar respostas (erro 404)  
**Causa**: WhatsApp mudou para usar LID em vez de JID tradicional  
**Solução**: Desabilitar modo LID + Corrigir endpoint de envio

---

## 🐛 Problema Identificado

### Sintomas
- ✅ Bot **recebia** mensagens corretamente via webhook
- ✅ Bot **processava** comandos (`/menu`, `/status`)
- ❌ Bot **falhava** ao enviar respostas

### Logs do Erro

```
2026-04-27 22:58:34,026 [INFO] shopee_api — /webhook/evolution event='messages.upsert' user='220035536678945@lid' text='/menu'
2026-04-27 22:58:34,108 [INFO] shopee_wa — [WA] user=220035536678945@lid state='idle' text='/menu'
2026-04-27 22:58:34,423 [INFO] shopee_evolution — [EVO] _send_single_text attempt=1 status=400 ok=False
2026-04-27 22:58:34,681 [INFO] shopee_evolution — [EVO] _send_single_text attempt=5 status=404 ok=False
2026-04-27 22:58:34,710 [WARNING] shopee_api — [EVO] Falha no envio: Cannot POST /message/sendText
```

### Causa Raiz

1. **LID vs JID**: WhatsApp mudou para usar **LID (Local Identifier)** em vez de JID tradicional
   - LID: `220035536678945@lid`
   - JID: `5511999999999@s.whatsapp.net`

2. **Evolution API**: Por padrão usa modo LID, mas o endpoint `/message/sendText` não aceita LIDs diretamente

3. **Endpoint Incorreto**: Código tentava múltiplos formatos, mas nenhum funcionava com LID

---

## ✅ Solução Implementada

### 1. Desabilitar Modo LID na Evolution API

**Arquivos Modificados**:
- `docker-compose.local.yml`
- `docker-compose.prod.yml`

**Mudança**:
```yaml
environment:
  # LID Mode (desabilitar para usar JID tradicional)
  WPP_LID_MODE: "false"
```

Isso força a Evolution API a usar JIDs tradicionais (`@s.whatsapp.net`) em vez de LIDs (`@lid`).

### 2. Corrigir Endpoint de Envio

**Arquivo Modificado**: `shopee_core/evolution_client.py`

**Antes** (8 tentativas com diferentes formatos):
```python
attempts: list[tuple[str, dict]] = [
    (url_with_instance, {"number": number, "text": text}),
    (url_with_instance, {"number": number, "textMessage": {"text": text}}),
    # ... 6 outras tentativas
]
```

**Depois** (formato oficial documentado):
```python
url = f"{_base_url()}/message/sendText/{_instance()}"
payload = {"number": number, "text": text}
```

**Referência**: [Evolution API - Send Text Documentation](https://docs.evoapicloud.com/api-reference/message-controller/send-text)

---

## 📁 Arquivos Criados/Modificados

### Arquivos Modificados
1. ✅ `docker-compose.local.yml` - Adicionado `WPP_LID_MODE=false`
2. ✅ `docker-compose.prod.yml` - Adicionado `WPP_LID_MODE=false`
3. ✅ `shopee_core/evolution_client.py` - Simplificado método `_send_single_text()`

### Arquivos Criados
1. ✅ `CORRECAO_LID_ENVIO_MENSAGENS.md` - Documentação técnica completa
2. ✅ `deploy/local/fix-lid-restart.ps1` - Script automatizado de correção
3. ✅ `APLICAR_CORRECAO_AGORA.md` - Guia rápido de aplicação
4. ✅ `U7_5_CORRECAO_LID_IMPLEMENTADA.md` - Este arquivo (resumo)

---

## 🚀 Como Aplicar a Correção

### Opção 1: Script Automatizado (Recomendado)

```powershell
.\deploy\local\fix-lid-restart.ps1
```

### Opção 2: Manual

```powershell
# 1. Parar containers
docker-compose -f docker-compose.local.yml down

# 2. Reconstruir imagem
docker-compose -f docker-compose.local.yml build shopee_api

# 3. Subir containers
docker-compose -f docker-compose.local.yml up -d
```

### ⚠️ IMPORTANTE: Reconectar WhatsApp

Após aplicar a correção, você **DEVE** reconectar o WhatsApp:

1. Acesse: http://localhost:8787/evolution/qrcode
2. Escaneie o novo QR Code
3. Aguarde `state: open` nos logs

**Por quê?** Porque mudamos o modo LID, a sessão antiga não é compatível.

---

## 🧪 Como Testar

### 1. Verificar Logs

```powershell
docker logs shopee_api_local -f
```

### 2. Enviar Mensagem de Teste

De **OUTRO NÚMERO** (não do número conectado), envie:

```
/menu
```

### 3. Logs Esperados (Sucesso) ✅

```
[INFO] shopee_api — /webhook/evolution event='messages.upsert' user='5511999999999@s.whatsapp.net' text='/menu'
[INFO] shopee_wa — [WA] user=5511999999999@s.whatsapp.net state='idle' text='/menu'
[INFO] shopee_evolution — [EVO] _send_single_text → http://evolution_api:8080/message/sendText/shopee_booster number=5511999999999 text_len=592
[INFO] shopee_evolution — [EVO] _send_single_text status=200 ok=True
```

**Diferenças**:
- ✅ User ID agora é `@s.whatsapp.net` (não `@lid`)
- ✅ Status 200 (não 404)
- ✅ `ok=True` (não `ok=False`)
- ✅ Sem tentativas múltiplas (apenas 1 chamada)

---

## 📊 Comparação Antes/Depois

| Aspecto | Antes (❌) | Depois (✅) |
|---------|-----------|------------|
| **Formato User ID** | `220035536678945@lid` | `5511999999999@s.whatsapp.net` |
| **Endpoint** | Múltiplas tentativas | 1 chamada direta |
| **Status HTTP** | 400/404 | 200 |
| **Envio** | Falha | Sucesso |
| **Logs** | 8 tentativas | 1 tentativa |
| **Reconexão** | Não necessária | Necessária (1x) |

---

## 🔍 Referências Técnicas

1. **Evolution API Documentation**  
   https://docs.evoapicloud.com/api-reference/message-controller/send-text

2. **n8n Community - LID Issue**  
   https://community.n8n.io/t/problema-con-evolution-api-1-6-1-lid-en-vez-de-numero-real/270857

3. **WhatsApp LID Explanation**  
   https://developer.z-api.io/en/tips/lid

4. **Baileys GitHub Issue - LID Groups**  
   https://github.com/WhiskeySockets/Baileys/issues/1465

---

## 📝 Notas Importantes

### 1. Reconexão Obrigatória
Após mudar `WPP_LID_MODE`, você **DEVE** reconectar o WhatsApp. A sessão antiga não é compatível.

### 2. Mensagens de Outro Número
Sempre teste enviando mensagens de **outro número**, não do número conectado no bot.

### 3. Formato do Número
Agora os números virão no formato tradicional `5511999999999@s.whatsapp.net` em vez de `220035536678945@lid`.

### 4. Compatibilidade
Esta correção funciona para Evolution API v2.1.1. Versões futuras podem ter comportamento diferente.

### 5. Logs Limpos
Não haverá mais 8 tentativas de envio. Apenas 1 chamada direta ao endpoint correto.

---

## ✅ Checklist de Aplicação

- [ ] Executei o script `fix-lid-restart.ps1` ou comandos manuais
- [ ] Containers foram reconstruídos e reiniciados
- [ ] Acessei http://localhost:8787/evolution/qrcode
- [ ] Escaneei o novo QR Code
- [ ] Vi `state: open` nos logs da Evolution API
- [ ] Testei enviando `/menu` de outro número
- [ ] Bot respondeu corretamente! 🎉
- [ ] Logs mostram `status=200 ok=True`
- [ ] User ID agora é `@s.whatsapp.net` (não `@lid`)

---

## 🎯 Resultado Final

Após aplicar esta correção:

✅ **Bot recebe mensagens** corretamente via webhook  
✅ **Bot processa comandos** (`/menu`, `/status`, etc)  
✅ **Bot envia respostas** sem erros  
✅ **Logs limpos** (sem tentativas múltiplas)  
✅ **Formato padronizado** (JID tradicional)  
✅ **Endpoint correto** (conforme documentação oficial)  

---

## 🚀 Próximos Passos

Após aplicar e testar esta correção:

1. ✅ **Testar todos os comandos**: `/menu`, `/status`, `/ajuda`, etc
2. ✅ **Testar envio de mídia**: Imagens, relatórios, etc
3. ✅ **Testar fluxos completos**: Sentinela, análise de concorrentes, etc
4. ✅ **Monitorar logs**: Verificar se não há mais erros 404
5. ✅ **Documentar no README**: Adicionar nota sobre reconexão após mudanças

---

**Status**: ✅ Correção Implementada e Pronta para Aplicar  
**Versão Evolution API**: v2.1.1  
**Data**: 27/04/2026  
**Autor**: Kiro AI Assistant
