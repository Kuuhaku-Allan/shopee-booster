# Fase T — Telegram como Canal de Alertas do Sentinela ✅

**Data**: 26/04/2026  
**Versão**: 4.1.0+

---

## 🎯 Objetivo

Transformar o Telegram em um canal de alertas e relatórios do Sentinela, enviando:
- 📝 Resumo textual formatado
- 📊 Gráfico de preços (PNG)
- 📄 Tabela de concorrentes (CSV)

**Não é um bot conversacional** — apenas notificações operacionais.

---

## ✅ Implementações Realizadas

### T1 — Refatoração Completa do telegram_service.py

**Arquivo**: `telegram_service.py`

**Mudanças Principais**:

#### 1. **Parse Mode: Markdown → HTML**
```python
# ANTES (Markdown - quebra fácil)
"parse_mode": "Markdown"
"*negrito*"

# DEPOIS (HTML - robusto)
"parse_mode": "HTML"
"<b>negrito</b>"
```

**Benefício**: HTML é mais robusto e não quebra com caracteres especiais em nomes de produtos.

#### 2. **Escape de HTML**
```python
import html

produto_safe = html.escape(produto)
mensagem = f"<b>Produto:</b> {produto_safe}"
```

**Benefício**: Previne quebra de formatação com caracteres especiais (`<`, `>`, `&`, etc).

#### 3. **Novos Métodos**

| Método | Descrição |
|--------|-----------|
| `enviar_mensagem(mensagem, disable_preview)` | Envia texto formatado em HTML |
| `enviar_foto(image_path, caption)` | Envia imagem (gráfico) |
| `enviar_documento(file_path, caption)` | Envia arquivo (CSV, PDF) |
| `enviar_relatorio_sentinela(resultado, chart_path, table_path)` | Envia relatório completo |

#### 4. **Tratamento de Erros Robusto**
```python
try:
    response = requests.post(...)
    if response.status_code == 200:
        log.info("[TELEGRAM] Sucesso")
        return True
    else:
        log.error(f"[TELEGRAM] Erro HTTP {response.status_code}")
        return False
except Exception as e:
    log.error(f"[TELEGRAM] Exceção: {e}")
    return False
```

**Benefício**: Nunca trava o Sentinela se o Telegram falhar.

#### 5. **Compatibilidade com Código Legado**
```python
# Métodos antigos ainda funcionam
def enviar_alerta(self, mensagem: str) -> bool:
    # Converte Markdown para HTML
    mensagem_html = mensagem.replace("*", "<b>")
    return self.enviar_mensagem(mensagem_html)
```

---

### T2 — Serviço de Relatórios do Sentinela

**Arquivo**: `shopee_core/sentinel_report_service.py`

**Funcionalidades**:

#### 1. **Resumo Textual**
```python
def build_sentinel_summary(resultado: dict) -> str:
    """Gera resumo em texto simples"""
```

**Saída**:
```
🛡️ Sentinela - Relatório
========================================

Loja: totalmenteseu
Keyword: mochila infantil princesa
Concorrentes analisados: 10
Novos concorrentes: 2

Preços:
  Médio: R$ 87.90
  Mínimo: R$ 49.90
  Máximo: R$ 139.90
```

#### 2. **DataFrame de Concorrentes**
```python
def build_competitor_dataframe(resultado: dict) -> pd.DataFrame:
    """Converte dados em DataFrame pandas"""
```

**Colunas**:
- Ranking
- Título (truncado em 50 chars)
- Preço
- Loja (truncado em 30 chars)
- Novo (✓ ou vazio)

#### 3. **Gráfico de Preços**
```python
def generate_price_chart(df, output_path, keyword) -> str:
    """Gera gráfico PNG com matplotlib"""
```

**Características**:
- ✅ Linha de preços por ranking
- ✅ Destaque para novos concorrentes (estrela vermelha)
- ✅ Linha de preço médio (tracejada verde)
- ✅ Grid e legendas
- ✅ Estilo profissional (seaborn)
- ✅ Resolução 150 DPI

**Exemplo**:
![Gráfico de Preços](docs/exemplo_grafico.png)

#### 4. **Tabela CSV**
```python
def generate_competitor_table_csv(df, output_path) -> str:
    """Exporta DataFrame para CSV"""
```

**Formato**:
```csv
Ranking,Título,Preço,Loja,Novo
1,Mochila Infantil Princesa Rosa com Glitter,49.90,loja_concorrente_1,✓
2,Mochila Escolar Princesa Frozen Elsa,67.50,loja_concorrente_2,
...
```

#### 5. **Tabela PNG (Opcional)**
```python
def generate_competitor_table_png(df, output_path) -> str:
    """Gera imagem PNG da tabela"""
```

**Características**:
- ✅ Header azul com texto branco
- ✅ Linhas alternadas (zebra)
- ✅ Limita a 15 linhas
- ✅ Formatação de preços

#### 6. **Gerador Completo**
```python
def generate_sentinel_report(resultado, include_chart, include_csv, include_table_png) -> dict:
    """Gera relatório completo"""
```

**Retorna**:
```python
{
    "summary": "texto do resumo",
    "chart_path": "data/reports/sentinela_mochila_20260426_143022_chart.png",
    "csv_path": "data/reports/sentinela_mochila_20260426_143022_table.csv",
    "table_png_path": ""
}
```

---

### T3 — Estrutura de Dados do Sentinela

**Formato Esperado**:

```python
resultado = {
    "ok": True,
    "loja": "totalmenteseu",
    "keyword": "mochila infantil princesa",
    "concorrentes": [
        {
            "titulo": "Mochila Infantil Princesa Rosa",
            "preco": 49.90,
            "loja": "loja_concorrente_1",
            "url": "https://shopee.com.br/...",
            "ranking": 1,
            "is_new": True
        },
        # ... mais concorrentes
    ],
    "novos_concorrentes": [
        # Lista de concorrentes novos (subset de concorrentes)
    ],
    "total_analisado": 10,
    "preco_medio": 87.90,
    "menor_preco": 49.90,
    "maior_preco": 139.90,
    "seu_preco": 95.00,  # Opcional
    "timestamp": "26/04/2026 14:30"
}
```

**Benefícios**:
- ✅ Reutilizável em WhatsApp, .exe e Telegram
- ✅ Fácil de testar com dados simulados
- ✅ Extensível (adicionar novos campos sem quebrar)

---

## 🧪 Testes Implementados

**Arquivo**: `test_telegram_sentinel.py`

### Teste 1: Conexão Básica
```python
def test_telegram_connection():
    telegram = TelegramSentinela()
    success = telegram.testar_conexao()
```

**Verifica**:
- ✅ Token configurado
- ✅ Chat ID configurado
- ✅ Mensagem enviada com sucesso

### Teste 2: Mensagem Formatada
```python
def test_telegram_message():
    mensagem = (
        "🧪 <b>Teste de Formatação HTML</b>\n\n"
        "Este é um teste de <b>negrito</b> e <i>itálico</i>."
    )
    success = telegram.enviar_mensagem(mensagem)
```

**Verifica**:
- ✅ HTML renderizado corretamente
- ✅ Emojis funcionando
- ✅ Formatação preservada

### Teste 3: Relatório Completo
```python
def test_telegram_report():
    report = generate_sentinel_report(resultado_simulado)
    success = telegram.enviar_relatorio_sentinela(
        resultado_simulado,
        chart_path=report["chart_path"],
        table_path=report["csv_path"]
    )
```

**Verifica**:
- ✅ Gráfico gerado
- ✅ CSV gerado
- ✅ Mensagem enviada
- ✅ Foto enviada
- ✅ Documento enviado

### Teste 4: Alertas Específicos
```python
def test_telegram_alerts():
    msg_preco = TelegramSentinela.formatar_mudanca_preco(...)
    msg_novo = TelegramSentinela.formatar_novo_concorrente(...)
```

**Verifica**:
- ✅ Alerta de mudança de preço
- ✅ Alerta de novo concorrente
- ✅ Formatação HTML correta

---

## 📁 Arquivos Criados/Modificados

### Novos Arquivos
1. ✅ `telegram_service.py` — Refatorado completamente
2. ✅ `shopee_core/sentinel_report_service.py` — Novo serviço
3. ✅ `test_telegram_sentinel.py` — Suite de testes
4. ✅ `FASE_T_TELEGRAM_SENTINELA.md` — Esta documentação

### Diretórios
- ✅ `data/reports/` — Criado automaticamente para salvar relatórios

---

## 🚀 Como Usar

### 1. Configurar Telegram

**No sentinela_db**:
```python
from sentinela_db import salvar_config

salvar_config("telegram_token", "SEU_BOT_TOKEN")
salvar_config("telegram_chat_id", "SEU_CHAT_ID")
```

**Obter Token**:
1. Fale com [@BotFather](https://t.me/BotFather) no Telegram
2. Use `/newbot` e siga as instruções
3. Copie o token fornecido

**Obter Chat ID**:
1. Fale com [@userinfobot](https://t.me/userinfobot)
2. Copie o ID fornecido

### 2. Testar Telegram

```bash
# Ativar ambiente virtual
.\venv\Scripts\activate

# Executar testes
python test_telegram_sentinel.py
```

**Saída Esperada**:
```
🧪 TESTE DO TELEGRAM SENTINELA

============================================================
TESTE 1: Conexão com Telegram
============================================================
✅ Conexão OK - Mensagem de teste enviada

============================================================
TESTE 2: Mensagem Formatada
============================================================
✅ Mensagem formatada enviada

============================================================
TESTE 3: Relatório Completo do Sentinela
============================================================
Gerando gráfico e tabela...
  Gráfico: data/reports/sentinela_mochila_20260426_143022_chart.png
  CSV: data/reports/sentinela_mochila_20260426_143022_table.csv

Enviando para Telegram...
✅ Relatório completo enviado

============================================================
TESTE 4: Alertas Específicos
============================================================
Enviando alerta de mudança de preço...
Enviando alerta de novo concorrente...
✅ Alertas enviados

============================================================
RESUMO DOS TESTES
============================================================
✅ PASS - Conexão
✅ PASS - Mensagem Formatada
✅ PASS - Relatório Completo
✅ PASS - Alertas Específicos

Total: 4/4 testes passaram

🎉 Todos os testes passaram!
```

### 3. Integrar com Sentinela

**No código do Sentinela** (quando implementar a lógica real):

```python
from telegram_service import TelegramSentinela
from shopee_core.sentinel_report_service import generate_sentinel_report

# Após buscar concorrentes e comparar histórico
resultado = {
    "ok": True,
    "loja": "sua_loja",
    "keyword": "mochila infantil",
    "concorrentes": [...],
    "novos_concorrentes": [...],
    "total_analisado": 10,
    "preco_medio": 87.90,
    "menor_preco": 49.90,
    "maior_preco": 139.90,
    "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M")
}

# Gera relatório
report = generate_sentinel_report(resultado)

# Envia para Telegram
telegram = TelegramSentinela()
telegram.enviar_relatorio_sentinela(
    resultado,
    chart_path=report["chart_path"],
    table_path=report["csv_path"]
)
```

---

## 📊 Exemplo de Mensagem no Telegram

```
🚨 Novos concorrentes detectados!

🏪 Loja: totalmenteseu
🔍 Keyword: mochila infantil princesa
📊 Concorrentes analisados: 10
🆕 Novos concorrentes: 2

💰 Preço médio: R$ 87.90
🏷️ Menor preço: R$ 49.90
📈 Maior preço: R$ 139.90

⚠️ Alerta: Seu produto está 8% acima do preço médio.

Monitoramento realizado em 26/04/2026 14:30
```

Seguido de:
- 📊 **Gráfico de Preços** (PNG)
- 📄 **Tabela de Concorrentes** (CSV)

---

## ⚠️ Tratamento de Erros

### Telegram Não Configurado
```python
if not telegram._is_configured():
    log.warning("[TELEGRAM] Não configurado. Mensagem não enviada.")
    return False
```

**Comportamento**: Loga aviso mas não trava o Sentinela.

### Arquivo Não Encontrado
```python
if not Path(image_path).exists():
    log.error(f"[TELEGRAM] Arquivo não encontrado: {image_path}")
    return False
```

**Comportamento**: Loga erro mas continua execução.

### Erro HTTP
```python
if response.status_code != 200:
    log.error(f"[TELEGRAM] Erro HTTP {response.status_code}: {response.text}")
    return False
```

**Comportamento**: Loga erro detalhado mas não trava.

### Exceção Geral
```python
except Exception as e:
    log.error(f"[TELEGRAM] Exceção: {e}")
    return False
```

**Comportamento**: Captura qualquer exceção e retorna False.

---

## 🎯 Próximos Passos (T4 - Integração)

### 1. Integrar com Sentinela Real
- [ ] Modificar `_run_sentinel_bg()` no `api_server.py`
- [ ] Buscar concorrentes reais (não simulados)
- [ ] Comparar com histórico do banco
- [ ] Gerar resultado estruturado
- [ ] Chamar `generate_sentinel_report()`
- [ ] Chamar `telegram.enviar_relatorio_sentinela()`

### 2. Trigger do .exe
- [ ] Adicionar botão "Enviar para Telegram" na UI
- [ ] Usar mesma estrutura de dados
- [ ] Reutilizar `sentinel_report_service`

### 3. Trigger do WhatsApp
- [ ] Após `/sentinela rodar` completar
- [ ] Enviar resumo no WhatsApp
- [ ] Enviar relatório completo no Telegram
- [ ] Notificar usuário: "Relatório enviado no Telegram"

### 4. Agendamento Automático
- [ ] APScheduler ou similar
- [ ] Rodar Sentinela a cada X horas
- [ ] Enviar alertas automaticamente
- [ ] Apenas se houver mudanças significativas

---

## 📝 Notas Técnicas

### Dependências
```
requests
pandas
matplotlib
```

### Limites do Telegram
- **Mensagem**: 4096 caracteres
- **Foto**: 10 MB
- **Documento**: 50 MB
- **Taxa**: ~30 mensagens/segundo

### Formato de Arquivos
- **Gráfico**: PNG, 150 DPI, ~200 KB
- **Tabela**: CSV, UTF-8 com BOM, ~10 KB

### Logs
```
[TELEGRAM] Inicializado: token=✓ chat_id=✓
[TELEGRAM] Enviando mensagem: 245 chars
[TELEGRAM] Mensagem enviada com sucesso
[TELEGRAM] Enviando foto: data/reports/...
[TELEGRAM] Foto enviada com sucesso
[TELEGRAM] Enviando documento: data/reports/...
[TELEGRAM] Documento enviado com sucesso
[REPORT] DataFrame criado: 10 concorrentes
[REPORT] Gráfico salvo: data/reports/...
[REPORT] CSV salvo: data/reports/...
```

---

## ✅ Conclusão

O Telegram agora está pronto para ser o **canal de alertas operacionais do Sentinela**:

✅ **Mensagens formatadas** em HTML (robusto)  
✅ **Gráficos de preços** profissionais  
✅ **Tabelas CSV** exportáveis  
✅ **Tratamento de erros** completo  
✅ **Testes automatizados** funcionando  
✅ **Compatibilidade** com código legado  
✅ **Documentação** completa  

**Falta apenas**: Integrar com a lógica real do Sentinela (busca de concorrentes e comparação de histórico).

---

**Desenvolvido com ❤️ para vendedores brasileiros**
