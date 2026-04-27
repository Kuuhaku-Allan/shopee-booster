# 🧪 INSTRUÇÕES DE TESTE - U7.3 Implementado

**Data:** 27/04/2026 14:40 BRT  
**Status:** ✅ Código implementado e servidor reiniciado  
**Servidor:** Rodando em `http://0.0.0.0:8787` (Terminal 15)

---

## ✅ O QUE FOI FEITO

### 1. Implementado U7.3 - Isolamento de backend_core
- ✅ Criado `shopee_core/competitor_service.py` com subprocess isolado
- ✅ Atualizado `api_server.py` para usar o novo serviço
- ✅ Removido import direto de `backend_core` (que travava)
- ✅ Timeout REAL via `subprocess.run(timeout=90)`
- ✅ Logs detalhados com prefixo `[COMPETITOR]`

### 2. Servidor Reiniciado
- ✅ Todos os processos antigos parados
- ✅ Novo servidor iniciado com código U7.3
- ✅ Health check confirmado: `http://localhost:8787/health` ✅

### 3. Commits Enviados ao GitHub
- ✅ `4a46041` - Implementação U7.3
- ✅ `2552e82` - Documentação U7.3
- ✅ `79f6656` - Status completo U7
- ✅ Branch: `feature/whatsapp-bot-core`

---

## 🧪 COMO TESTAR AGORA

### Passo 1: Verificar que o servidor está rodando

```powershell
Invoke-RestMethod -Uri "http://localhost:8787/health"
```

**Resultado esperado:**
```
ok      : True
service : shopee-booster-bot-api
version : 0.2.0
```

✅ **Confirmado!**

---

### Passo 2: Testar no WhatsApp

Envie a mensagem:
```
/sentinela rodar
```

**Resultado esperado:**
```
⏳ Sentinela iniciado!

Vou buscar concorrentes para 3 keywords.
Isso pode levar alguns minutos.

Use /status para acompanhar o progresso.
```

---

### Passo 3: Verificar progresso em tempo real

Envie a mensagem:
```
/status
```

**Resultado esperado (após alguns segundos):**
```
Sentinela em execução
Loja: totalmenteseu
Progresso: 1/3
Keyword atual: mochila roxa
Tempo decorrido: 2 min

Vou avisar quando terminar.
⚠️ Não inicie outro Sentinela agora.
```

**⚠️ IMPORTANTE:** O progresso deve MUDAR de `0/3` para `1/3`, `2/3`, `3/3` conforme as keywords são processadas.

---

### Passo 4: Verificar logs do servidor

Abra o terminal onde o servidor está rodando e procure por:

```
[SENTINELA] ════════════════════════════════════════════════════════
[SENTINELA] Início da execução: user=5511988600050@s.whatsapp.net
[SENTINELA] Etapa 1/6: importando competitor_service...
[SENTINELA] Etapa 1/6 OK: competitor_service importado
[SENTINELA] Etapa 2/6: lendo config...
[SENTINELA] Etapa 2/6 OK: shop_uid='...', username='totalmenteseu', keywords=3
[SENTINELA] Etapa 3/6: gerando janela_execucao...
[SENTINELA] Etapa 3/6 OK: janela=2026-04-27_14h
[SENTINELA] Etapa 4/6: salvando sessão running...
[SENTINELA] Etapa 4/6 OK: sessão running salva
[SENTINELA] Etapa 5/6: preparando estruturas de dados...
[SENTINELA] Etapa 5/6 OK: estruturas preparadas
[SENTINELA] Etapa 6/6: pronto para executar keywords
[SENTINELA] Etapa 6/6 OK: sistema pronto
[SENTINELA] Iniciando loop de 3 keywords...
```

**🎯 PONTO CRÍTICO:** Deve aparecer `Etapa 1/6 OK: competitor_service importado`

Se aparecer isso, significa que **U7.3 funcionou!** O travamento foi resolvido.

---

### Passo 5: Acompanhar execução das keywords

Os logs devem mostrar:

```
[SENTINELA] ──────────────────────────────────────────────
[SENTINELA] Keyword 1/3: 'mochila roxa'
[COMPETITOR] Buscando concorrentes para: 'mochila roxa'
```

Aguarde ~2-3 minutos por keyword. Deve aparecer:

```
[COMPETITOR] Encontrados 10 concorrentes
[SENTINELA] Concorrentes encontrados: 10
```

Depois continua para a próxima keyword:

```
[SENTINELA] Keyword 2/3: 'mochila escolar'
[COMPETITOR] Buscando concorrentes para: 'mochila escolar'
[COMPETITOR] Encontrados 10 concorrentes
[SENTINELA] Concorrentes encontrados: 10
```

E assim por diante até completar as 3 keywords.

---

### Passo 6: Aguardar mensagem final

Após ~5-10 minutos (dependendo das keywords), você deve receber no WhatsApp:

```
🛡️ Sentinela concluído!

🏪 Loja: totalmenteseu
🔍 Keywords analisadas: 3
📊 Concorrentes analisados: 30
🏷️ Menor preço encontrado: R$ 45.90
💰 Preço médio: R$ 78.50

📢 Relatório completo enviado ao Telegram.

Janela: 2026-04-27_14h
```

---

## 🎯 CRITÉRIOS DE SUCESSO

### ✅ U7.3 Funcionou Se:

1. **Etapa 1/6 completa:**
   ```
   [SENTINELA] Etapa 1/6 OK: competitor_service importado
   ```
   ✅ Não trava mais no import de `backend_core`

2. **Todas as 6 etapas completam:**
   ```
   [SENTINELA] Etapa 6/6 OK: sistema pronto
   ```
   ✅ Preparação completa antes do loop

3. **Loop de keywords executa:**
   ```
   [SENTINELA] Keyword 1/3: 'mochila roxa'
   [COMPETITOR] Buscando concorrentes...
   [COMPETITOR] Encontrados 10 concorrentes
   ```
   ✅ Scraping funciona via subprocess

4. **Progresso atualiza em tempo real:**
   ```
   /status → Progresso: 1/3
   /status → Progresso: 2/3
   /status → Progresso: 3/3
   ```
   ✅ `/status` mostra progresso real

5. **Mensagem final enviada:**
   ```
   🛡️ Sentinela concluído!
   ```
   ✅ Execução completa com sucesso

---

## ❌ PROBLEMAS POSSÍVEIS

### Problema 1: Ainda trava na Etapa 1/6

**Sintoma:**
```
[SENTINELA] Etapa 1/6: importando competitor_service...
[... NADA MAIS ...]
```

**Causa:** Código antigo ainda em cache ou servidor não reiniciou  
**Solução:**
1. Parar o servidor: `Ctrl+C` no terminal
2. Limpar cache: `.\venv\Scripts\python.exe -m py_compile shopee_core/competitor_service.py`
3. Reiniciar: `.\venv\Scripts\python.exe -m uvicorn api_server:app --host 0.0.0.0 --port 8787 --log-level debug`

---

### Problema 2: Timeout em todas as keywords

**Sintoma:**
```
[COMPETITOR] Timeout de 90s excedido para 'mochila roxa'
[COMPETITOR] Timeout de 90s excedido para 'mochila escolar'
```

**Causa:** Shopee está bloqueando ou Playwright não está funcionando  
**Solução:**
1. Testar manualmente: `.\venv\Scripts\python.exe -c "from backend_core import fetch_competitors_intercept; print(fetch_competitors_intercept('mochila'))"`
2. Se funcionar manualmente, aumentar timeout: `TIMEOUT_PER_KEYWORD = 120` em `api_server.py`
3. Se não funcionar, problema é no Playwright/Shopee (não relacionado a U7.3)

---

### Problema 3: Erro no subprocess

**Sintoma:**
```
[COMPETITOR] Erro no scraping: ModuleNotFoundError: No module named 'backend_core'
```

**Causa:** Subprocess não encontra o módulo  
**Solução:**
1. Verificar que `backend_core.py` está na raiz do projeto
2. Verificar que o venv está ativado: `.\venv\Scripts\python.exe` (não apenas `python`)
3. Testar: `.\venv\Scripts\python.exe -c "import backend_core; print('OK')"`

---

## 📊 COMPARAÇÃO: ANTES vs DEPOIS

### ANTES (U7.2 - com travamento)
```
[SENTINELA] Início da execução
[SENTINELA] Etapa 1/6: importando backend_core...
[... TRAVA AQUI ...]

/status → Progresso: 0/3, preparando...
/status → Progresso: 0/3, preparando...  (nunca muda)
```

### DEPOIS (U7.3 - com subprocess)
```
[SENTINELA] Início da execução
[SENTINELA] Etapa 1/6: importando competitor_service...
[SENTINELA] Etapa 1/6 OK: competitor_service importado
[SENTINELA] Etapa 2/6 OK...
[SENTINELA] Etapa 3/6 OK...
[SENTINELA] Etapa 4/6 OK...
[SENTINELA] Etapa 5/6 OK...
[SENTINELA] Etapa 6/6 OK...
[SENTINELA] Keyword 1/3: 'mochila roxa'
[COMPETITOR] Encontrados 10 concorrentes

/status → Progresso: 1/3, mochila roxa
/status → Progresso: 2/3, mochila escolar
/status → Progresso: 3/3, mochila infantil
```

---

## 📝 CHECKLIST DE TESTE

- [ ] Servidor rodando: `http://localhost:8787/health` ✅
- [ ] `/sentinela rodar` responde com "Sentinela iniciado!"
- [ ] `/status` mostra "Sentinela em execução"
- [ ] Logs mostram `Etapa 1/6 OK: competitor_service importado`
- [ ] Logs mostram todas as 6 etapas completando
- [ ] Logs mostram `Keyword 1/3` iniciando
- [ ] Logs mostram `[COMPETITOR] Encontrados X concorrentes`
- [ ] `/status` mostra progresso mudando (1/3, 2/3, 3/3)
- [ ] Mensagem final recebida no WhatsApp
- [ ] Relatório enviado ao Telegram (se configurado)

---

## 🎉 PRÓXIMOS PASSOS APÓS SUCESSO

1. **Documentar resultados** do teste
2. **Fazer merge** da branch `feature/whatsapp-bot-core` para `main`
3. **Criar release** com as correções U7.1, U7.2 e U7.3
4. **Monitorar** execuções reais do Sentinela
5. **Ajustar timeouts** se necessário (baseado em dados reais)

---

## 📚 DOCUMENTAÇÃO RELACIONADA

- `STATUS_U7_COMPLETO.md` - Status geral de todas as correções
- `U7_3_IMPLEMENTADO.md` - Detalhes da implementação U7.3
- `DIAGNOSTICO_FINAL_U7_3.md` - Diagnóstico do problema
- `shopee_core/competitor_service.py` - Código do serviço isolado

---

**Servidor rodando em:** Terminal 15  
**Comando:** `.\venv\Scripts\python.exe -m uvicorn api_server:app --host 0.0.0.0 --port 8787 --log-level debug`  
**Pronto para testar!** 🚀
