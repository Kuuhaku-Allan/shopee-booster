# 🚀 APLICAR CORREÇÃO - Bot Não Envia Mensagens

## ⚡ Correção Rápida (1 Comando)

Abra o PowerShell na **raiz do projeto** e execute:

```powershell
.\deploy\local\fix-lid-restart.ps1
```

Este script vai:
1. ✅ Parar os containers
2. ✅ Reconstruir a imagem do bot (com correção)
3. ✅ Subir os containers (com `WPP_LID_MODE=false`)
4. ✅ Mostrar próximos passos

---

## 📱 Após Executar o Script

### 1. Reconectar WhatsApp (OBRIGATÓRIO!)

Acesse no navegador:
```
http://localhost:8787/evolution/qrcode
```

Escaneie o **novo QR Code** com seu WhatsApp.

**⚠️ IMPORTANTE**: Como mudamos o modo LID, você **DEVE** reconectar o WhatsApp!

### 2. Verificar Conexão

Aguarde até ver `state: open` nos logs:

```powershell
docker logs shopee_evolution_local -f
```

Pressione `Ctrl+C` para sair dos logs.

### 3. Testar Envio

Envie uma mensagem de **OUTRO NÚMERO** (não do número conectado) para o bot:

```
/menu
```

O bot deve responder! 🎉

---

## 🔍 Verificar Logs do Bot

```powershell
docker logs shopee_api_local -f
```

### Logs Esperados (Sucesso) ✅

```
[INFO] shopee_api — /webhook/evolution event='messages.upsert' user='5511999999999@s.whatsapp.net' text='/menu'
[INFO] shopee_evolution — [EVO] _send_single_text status=200 ok=True
```

### Logs Antigos (Erro) ❌

```
[INFO] shopee_api — /webhook/evolution event='messages.upsert' user='220035536678945@lid' text='/menu'
[INFO] shopee_evolution — [EVO] _send_single_text status=404 ok=False
[WARNING] shopee_api — [EVO] Falha no envio: Cannot POST /message/sendText
```

---

## 🛠️ Correção Manual (Se Preferir)

Se não quiser usar o script, execute manualmente:

```powershell
# 1. Parar containers
docker-compose -f docker-compose.local.yml down

# 2. Reconstruir imagem
docker-compose -f docker-compose.local.yml build shopee_api

# 3. Subir containers
docker-compose -f docker-compose.local.yml up -d

# 4. Ver logs
docker logs shopee_api_local -f
```

Depois reconecte o WhatsApp em: http://localhost:8787/evolution/qrcode

---

## ❓ O Que Foi Corrigido?

### Problema
- WhatsApp mudou para usar **LID** (`220035536678945@lid`) em vez de JID tradicional (`5511999999999@s.whatsapp.net`)
- Evolution API não conseguia enviar mensagens para LIDs
- Endpoint `/message/sendText` retornava erro 404

### Solução
1. **Desabilitado modo LID**: Adicionado `WPP_LID_MODE=false` na Evolution API
2. **Corrigido endpoint**: Simplificado para usar apenas formato oficial documentado
3. **Agora usa JID tradicional**: Números voltam no formato `@s.whatsapp.net`

---

## 📚 Documentação Completa

Para mais detalhes, veja:
- `CORRECAO_LID_ENVIO_MENSAGENS.md` - Explicação técnica completa
- `deploy/local/fix-lid-restart.ps1` - Script de correção

---

## ✅ Checklist

- [ ] Executei `.\deploy\local\fix-lid-restart.ps1`
- [ ] Acessei http://localhost:8787/evolution/qrcode
- [ ] Escaneei o novo QR Code
- [ ] Vi `state: open` nos logs
- [ ] Testei enviando `/menu` de outro número
- [ ] Bot respondeu corretamente! 🎉

---

**Data**: 27/04/2026  
**Status**: ✅ Correção Pronta para Aplicar
