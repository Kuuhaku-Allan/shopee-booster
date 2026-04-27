# Fase U — Configurações por Usuário (Planejamento)

**Data**: 26/04/2026  
**Versão**: 4.1.0+  
**Status**: 📋 Planejamento

---

## 🎯 Problema Atual

O bot WhatsApp usa configurações **globais**:
- ❌ Uma única API Key do Gemini para todos
- ❌ Um único token do Telegram para todos
- ❌ Uma única loja fixa
- ❌ Um único catálogo
- ❌ Sessões não isoladas por usuário

**Consequência**: Não é um produto real, apenas um protótipo para um usuário.

---

## 🎯 Objetivo

Transformar o bot em um **sistema multiusuário** onde cada número de WhatsApp tem:
- ✅ Suas próprias lojas cadastradas
- ✅ Sua própria API Key do Gemini
- ✅ Seu próprio bot do Telegram
- ✅ Seus próprios catálogos
- ✅ Suas próprias configurações do Sentinela

---

## 📊 Arquitetura de Dados

### Tabela: `whatsapp_user_profiles`
```sql
CREATE TABLE whatsapp_user_profiles (
    user_id TEXT PRIMARY KEY,           -- JID do WhatsApp (5511988600050@s.whatsapp.net)
    display_name TEXT,                  -- Nome opcional do usuário
    active_shop_uid TEXT,               -- UID da loja ativa
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (active_shop_uid) REFERENCES whatsapp_user_shops(shop_uid)
);
```

### Tabela: `whatsapp_user_secrets`
```sql
CREATE TABLE whatsapp_user_secrets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    secret_name TEXT NOT NULL,          -- 'gemini_api_key', 'telegram_token', 'telegram_chat_id'
    encrypted_value TEXT NOT NULL,      -- Valor criptografado com Fernet
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, secret_name),
    FOREIGN KEY (user_id) REFERENCES whatsapp_user_profiles(user_id)
);
```

### Tabela: `whatsapp_user_shops`
```sql
CREATE TABLE whatsapp_user_shops (
    shop_uid TEXT PRIMARY KEY,          -- UUID único da loja
    user_id TEXT NOT NULL,
    shop_url TEXT NOT NULL,             -- URL completa da Shopee
    username TEXT NOT NULL,             -- Nome da loja (extraído da URL)
    shop_id TEXT,                       -- ID numérico da Shopee (se disponível)
    display_name TEXT,                  -- Nome customizado pelo usuário
    is_active INTEGER DEFAULT 0,        -- 1 se é a loja ativa
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES whatsapp_user_profiles(user_id)
);
```

### Tabela: `whatsapp_sentinel_config` (atualizada)
```sql
CREATE TABLE whatsapp_sentinel_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    shop_uid TEXT NOT NULL,             -- Vinculado à loja específica
    keywords_json TEXT NOT NULL,        -- {"keywords": [...], "auto_generated": bool, "from_catalog": bool}
    keyword_source TEXT,                -- 'scraping', 'catalog', 'manual'
    is_active INTEGER DEFAULT 1,
    interval_minutes INTEGER DEFAULT 360,
    telegram_enabled INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, shop_uid),
    FOREIGN KEY (user_id) REFERENCES whatsapp_user_profiles(user_id),
    FOREIGN KEY (shop_uid) REFERENCES whatsapp_user_shops(shop_uid)
);
```

### Tabela: `sentinela_locks` (atualizada)
```sql
CREATE TABLE sentinela_locks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    shop_uid TEXT NOT NULL,
    keyword TEXT NOT NULL,
    janela_execucao TEXT NOT NULL,      -- YYYY-MM-DD-HH-{uuid}
    executor TEXT NOT NULL,             -- 'whatsapp', 'desktop'
    status TEXT NOT NULL,               -- 'running', 'done', 'error'
    started_at TEXT NOT NULL,
    finished_at TEXT,
    UNIQUE(user_id, shop_uid, keyword, janela_execucao)
);
```

### Atualização: `shop_catalog_cache`
```sql
-- Adicionar shop_uid para vincular ao sistema de lojas
ALTER TABLE shop_catalog_cache ADD COLUMN shop_uid TEXT;
```

---

## 🔐 Criptografia de Secrets

### Chave Mestra
```python
# .shopee_config ou .env
BOT_SECRET_KEY=chave_fernet_gerada_uma_vez_base64
```

### Geração da Chave (uma vez)
```python
from cryptography.fernet import Fernet

# Gerar chave (fazer uma vez e salvar no .shopee_config)
key = Fernet.generate_key()
print(key.decode())  # Salvar no BOT_SECRET_KEY
```

### Criptografar/Descriptografar
```python
from cryptography.fernet import Fernet
import os

def get_cipher():
    key = os.getenv("BOT_SECRET_KEY")
    if not key:
        raise ValueError("BOT_SECRET_KEY não configurada")
    return Fernet(key.encode())

def encrypt_secret(value: str) -> str:
    cipher = get_cipher()
    return cipher.encrypt(value.encode()).decode()

def decrypt_secret(encrypted: str) -> str:
    cipher = get_cipher()
    return cipher.decrypt(encrypted.encode()).decode()
```

---

## 🤖 Comandos do WhatsApp

### Menu de Configuração
```
/config

Resposta:
⚙️ Configurações do ShopeeBooster

Lojas:
• /loja adicionar
• /loja listar
• /loja selecionar
• /loja remover

Catálogo:
• /catalogo importar
• /catalogo status
• /catalogo remover

IA:
• /ia configurar
• /ia status
• /ia remover

Telegram:
• /telegram configurar
• /telegram testar
• /telegram status
• /telegram remover

Sentinela:
• /sentinela configurar
• /sentinela rodar
• /sentinela status
```

---

## 📝 Fluxos Detalhados

### U1 — Sistema de Lojas

#### `/loja adicionar`
```
Bot: Me envie a URL da loja Shopee.

Usuário: https://shopee.com.br/totalmenteseu

Bot: ⏳ Validando loja...

Bot: ✅ Loja salva!

🏪 Nome: totalmenteseu
📍 Status: loja ativa

Agora você pode:
• importar catálogo com /catalogo importar
• auditar com /auditar
• configurar Sentinela com /sentinela configurar
```

#### `/loja listar`
```
🏪 Suas lojas salvas:

1. totalmenteseu ✅ ativa
   Catálogo: ✓ importado (20 produtos)
   Sentinela: ✓ configurado

2. outra_loja
   Catálogo: ✗ não importado
   Sentinela: ✗ não configurado

Para selecionar: /loja selecionar
Para adicionar: /loja adicionar
```

#### `/loja selecionar`
```
Qual loja você quer usar como ativa?

1. totalmenteseu
2. outra_loja

Responda com o número.
```

#### `/loja remover`
```
Qual loja deseja remover?

1. totalmenteseu
2. outra_loja

⚠️ Isso também removerá:
• Catálogo importado
• Configuração do Sentinela
• Histórico de monitoramento

Responda com o número ou /cancelar.
```

### U2 — Sistema de IA

#### `/ia configurar`
```
🤖 Configuração da IA

Envie sua chave da API do Gemini.

Ela será salva criptografada e usada apenas para processar suas próprias solicitações.

Para obter uma chave gratuita:
https://aistudio.google.com/app/apikey

Para cancelar: /cancelar
```

Usuário cola a chave.

```
⏳ Validando chave...

✅ Chave de IA configurada com sucesso!

A partir de agora, suas auditorias e análises usarão sua própria chave.
```

#### `/ia status`
```
🤖 Status da IA

✅ Chave configurada
Chave: ****abcd
Configurada em: 26/04/2026

Para remover: /ia remover
```

#### `/ia remover`
```
⚠️ Tem certeza que deseja remover sua chave de IA?

Você precisará configurar novamente para usar:
• /auditar
• /chat
• /sentinela

Digite CONFIRMAR para remover.
```

### U3 — Sistema de Telegram

#### `/telegram configurar`
```
📢 Configuração do Telegram

Vamos configurar onde o Sentinela vai enviar alertas.

Você vai precisar de:
1. Token do seu bot do Telegram
2. Seu chat_id

Quer ver o tutorial? Responda:
• tutorial - para ver instruções
• ou envie o token do bot diretamente
```

**Se escolher tutorial**:
```
📖 Tutorial - Criar Bot no Telegram

1️⃣ Criar o bot:
   • Abra o Telegram
   • Procure por @BotFather
   • Envie /newbot
   • Escolha um nome
   • Copie o token gerado

2️⃣ Descobrir seu chat_id:
   • Envie qualquer mensagem para o seu bot
   • Abra no navegador:
     https://api.telegram.org/botSEU_TOKEN/getUpdates
   • Procure por "chat":{"id":...}
   • Copie o número do ID

Quando tiver o token, envie aqui.
```

Usuário envia token.

```
✅ Token salvo!

Agora envie seu chat_id do Telegram.
```

Usuário envia chat_id.

```
⏳ Testando conexão...

✅ Telegram configurado!

Enviei uma mensagem de teste para confirmar.
Verifique seu Telegram!
```

#### `/telegram testar`
```
⏳ Enviando mensagem de teste...

✅ Mensagem enviada!

Se você recebeu a mensagem no Telegram, está tudo certo.
```

#### `/telegram status`
```
📢 Status do Telegram

✅ Telegram configurado
Bot token: ****1234
Chat ID: 123456789
Configurado em: 26/04/2026

Para testar: /telegram testar
Para remover: /telegram remover
```

#### `/telegram remover`
```
⚠️ Tem certeza que deseja remover a configuração do Telegram?

O Sentinela não poderá enviar alertas até você configurar novamente.

Digite CONFIRMAR para remover.
```

---

## 🔄 Fluxos Atualizados

### `/auditar` (atualizado)
```
Se tem loja ativa:
  🔍 Auditoria

  Usando loja ativa: totalmenteseu

  Carregando produtos...
  [usa scraping → catálogo → fallback]

Se não tem loja ativa:
  ❌ Você ainda não tem uma loja ativa.

  Use /loja adicionar para cadastrar uma loja primeiro.
```

### `/catalogo` (atualizado)
```
Se tem loja ativa:
  📦 Catálogo da loja totalmenteseu

  Envie o arquivo XLSX/CSV exportado do Seller Center.

Se não tem loja ativa:
  ❌ Você ainda não selecionou uma loja.

  Use /loja adicionar para cadastrar uma loja primeiro.
```

### `/sentinela configurar` (atualizado)
```
Se não tem loja ativa:
  ❌ Você ainda não tem uma loja ativa.
  Use /loja adicionar primeiro.

Se não tem IA configurada:
  ❌ Você ainda não configurou sua chave de IA.
  Use /ia configurar primeiro.

Se tem loja ativa e IA:
  🛡️ Configurando Sentinela para: totalmenteseu

  Vou usar esta ordem:
  1. produtos da Shopee, se disponíveis
  2. catálogo importado
  3. keywords manuais

  Continuar?
```

### `/sentinela rodar` (atualizado)
```
Verificações:
1. ✓ Loja ativa: totalmenteseu
2. ✓ Keywords configuradas: 5
3. ✓ IA configurada
4. ✓ Telegram configurado

⏳ Rodando o Sentinela agora...

[executa em background]

[envia resumo no WhatsApp]
[envia relatório completo no Telegram]
```

---

## 🔧 Implementação

### Ordem de Desenvolvimento

#### **U1 — Banco e user_config_service.py**
- [ ] Criar `shopee_core/user_config_service.py`
- [ ] Criar tabelas no banco
- [ ] Implementar criptografia de secrets
- [ ] Testes unitários

#### **U2 — Sistema de Lojas**
- [ ] `/loja adicionar`
- [ ] `/loja listar`
- [ ] `/loja selecionar`
- [ ] `/loja remover`
- [ ] Testes de fluxo

#### **U3 — Sistema de IA**
- [ ] `/ia configurar`
- [ ] `/ia status`
- [ ] `/ia remover`
- [ ] Integrar com `run_chatbot_turn()`
- [ ] Fallback global opcional

#### **U4 — Sistema de Telegram**
- [ ] `/telegram configurar`
- [ ] `/telegram testar`
- [ ] `/telegram status`
- [ ] `/telegram remover`
- [ ] Integrar com `TelegramSentinela`

#### **U5 — Atualizar Auditoria**
- [ ] Usar loja ativa
- [ ] Usar IA do usuário
- [ ] Fallback para URL manual

#### **U6 — Atualizar Catálogo**
- [ ] Salvar na loja ativa
- [ ] Vincular shop_uid
- [ ] Status por loja

#### **U7 — Atualizar Sentinela**
- [ ] Usar loja ativa
- [ ] Usar IA do usuário
- [ ] Usar Telegram do usuário
- [ ] Lock com user_id + shop_uid
- [ ] Executor = "whatsapp"

---

## 🧪 Testes

### Teste de Criptografia
```python
def test_encryption():
    secret = "AIzaSyAbc123..."
    encrypted = encrypt_secret(secret)
    decrypted = decrypt_secret(encrypted)
    assert decrypted == secret
```

### Teste de Perfil
```python
def test_user_profile():
    user_id = "5511988600050@s.whatsapp.net"
    create_user_profile(user_id)
    profile = get_user_profile(user_id)
    assert profile["user_id"] == user_id
```

### Teste de Loja
```python
def test_user_shop():
    user_id = "5511988600050@s.whatsapp.net"
    shop_url = "https://shopee.com.br/totalmenteseu"
    shop_uid = add_user_shop(user_id, shop_url)
    shops = list_user_shops(user_id)
    assert len(shops) == 1
```

### Teste de Secret
```python
def test_user_secret():
    user_id = "5511988600050@s.whatsapp.net"
    save_user_secret(user_id, "gemini_api_key", "AIzaSy...")
    api_key = get_user_secret(user_id, "gemini_api_key")
    assert api_key == "AIzaSy..."
```

---

## 📝 Notas Importantes

### Segurança
- ✅ Secrets sempre criptografados no banco
- ✅ Nunca logar secrets completos
- ✅ Mostrar apenas últimos 4 caracteres em status
- ✅ BOT_SECRET_KEY nunca commitada
- ✅ Permitir remover todos os dados com comandos

### Privacidade
- ✅ Cada usuário vê apenas seus próprios dados
- ✅ Isolamento completo entre usuários
- ✅ Dados criptografados em repouso
- ✅ Logs não contêm informações sensíveis

### Compatibilidade
- ✅ Manter comandos antigos funcionando
- ✅ Fallback para configuração global em dev
- ✅ Migração suave de dados existentes
- ✅ Não quebrar .exe desktop

### Performance
- ✅ Índices nas tabelas principais
- ✅ Cache de secrets descriptografados em memória (sessão)
- ✅ Lazy loading de configurações
- ✅ Cleanup de sessões antigas

---

## 🎯 Resultado Final

Após a Fase U, o bot será um **produto real multiusuário**:

✅ Cada usuário tem suas próprias configurações  
✅ Secrets criptografados e seguros  
✅ Múltiplas lojas por usuário  
✅ Configuração 100% pelo WhatsApp  
✅ Isolamento completo entre usuários  
✅ Pronto para uso em produção  

---

**Status**: 📋 Planejamento completo  
**Próximo**: Começar implementação U1
