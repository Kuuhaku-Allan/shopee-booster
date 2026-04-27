# U7.9 - Melhorar Tabela PNG do Telegram

## Problema Identificado

A tabela de concorrentes enviada ao Telegram estava difícil de ler porque:
- ❌ Sem bordas visíveis nas células (tudo "grudado")
- ❌ CSV não fica legível no Telegram (é só arquivo de dados)
- ❌ Falta de alinhamento adequado por coluna
- ❌ Títulos longos sem quebra de linha
- ❌ Espaçamento inadequado

## Objetivo

Criar uma tabela PNG profissional e legível para o Telegram, com:
- ✅ Bordas visíveis em todas as células
- ✅ Cabeçalho destacado
- ✅ Alinhamento por coluna (centro para números, esquerda para texto)
- ✅ Quebra de linha em títulos longos
- ✅ Altura de linha adequada
- ✅ Zebra striping (linhas alternadas)
- ✅ Destaque para novos concorrentes (fundo verde-claro)

## Implementação

### 1. Melhorias na Função `generate_competitor_table_png()` (sentinel_report_service.py)

#### Renomeação de Colunas (mais curtas)
```python
df_display = df_display.rename(columns={
    "Ranking": "Rank",
    "Título": "Produto",
    "Preço": "Preço",
    "Loja": "Loja",
    "Novo": "Novo"
})
```

#### Quebra de Linha em Textos Longos
```python
import textwrap

# Títulos com até 28 caracteres por linha
df_display["Produto"] = df_display["Produto"].apply(
    lambda x: "\n".join(textwrap.wrap(str(x), width=28))
)

# Lojas com até 18 caracteres por linha
df_display["Loja"] = df_display["Loja"].apply(
    lambda x: "\n".join(textwrap.wrap(str(x), width=18))
)
```

#### Altura Dinâmica da Figura
```python
nrows = len(df_display)
fig_height = max(4, nrows * 0.65 + 1.6)  # Altura proporcional ao número de linhas
```

#### Larguras de Coluna Otimizadas
```python
colWidths=[0.08, 0.42, 0.14, 0.24, 0.12]
# Rank (8%), Produto (42%), Preço (14%), Loja (24%), Novo (12%)
```

#### Bordas Visíveis e Estilo Profissional
```python
for (row, col), cell in table.get_celld().items():
    # Bordas em todas as células
    cell.set_edgecolor("#B8B8B8")
    cell.set_linewidth(0.8)
    
    if row == 0:
        # Cabeçalho destacado
        cell.set_facecolor("#2E86AB")
        cell.set_text_props(weight="bold", color="white", ha="center", va="center")
        cell.set_linewidth(1.2)
        cell.set_edgecolor("#7A7A7A")
    else:
        # Zebra striping
        cell.set_facecolor("#F7F7F7" if row % 2 == 0 else "white")
        
        # Destaca novos concorrentes com fundo verde-claro
        if col == 4 and df_display.iloc[row - 1]["Novo"] == "✓":
            cell.set_facecolor("#D4EDDA")
        
        # Alinhamento por coluna
        if col in [0, 2, 4]:  # Rank, Preço, Novo
            cell.set_text_props(ha="center", va="center")
        else:  # Produto, Loja
            cell.set_text_props(ha="left", va="center")
```

#### Resolução Aumentada
```python
plt.savefig(output_path, dpi=180, bbox_inches="tight", pad_inches=0.15)
# DPI aumentado de 150 para 180 para melhor qualidade
```

### 2. Atualização do Telegram Service (telegram_service.py)

#### Novo Parâmetro `table_png_path`
```python
def enviar_relatorio_sentinela(
    self,
    resultado: dict,
    chart_path: Optional[str] = None,
    table_path: Optional[str] = None,
    table_png_path: Optional[str] = None  # U7.9: Adicionar tabela PNG
) -> bool:
```

#### Ordem de Envio Otimizada
```python
# 1. Resumo textual
mensagem = self._formatar_relatorio_sentinela(resultado)
self.enviar_mensagem(mensagem)

# 2. Gráfico de preços (PNG)
if chart_path and Path(chart_path).exists():
    self.enviar_foto(chart_path, caption="📊 <b>Gráfico de Preços</b>")

# 3. Tabela PNG (leitura humana) - PRIORIDADE
if table_png_path and Path(table_png_path).exists():
    self.enviar_foto(table_png_path, caption="📋 <b>Tabela de Concorrentes</b>")

# 4. CSV (exportação/análise) - OPCIONAL
if table_path and Path(table_path).exists():
    self.enviar_documento(table_path, caption="📄 <b>Dados para Exportação (CSV)</b>")
```

**Lógica:**
- **PNG da tabela** = leitura humana (visual, legível)
- **CSV** = exportação/análise (dados brutos)

### 3. Atualização do API Server (api_server.py)

```python
telegram.enviar_relatorio_sentinela(
    resultado=resultado,
    chart_path=chart_path,
    table_path=table_csv_path,
    table_png_path=table_png_path,  # U7.9: Adicionar tabela PNG
)
```

### 4. Atualização do WhatsApp Service (whatsapp_service.py)

#### Comando `/sentinela relatorio`
```python
telegram.enviar_relatorio_sentinela(
    resultado=resultado,
    chart_path=chart_path if chart_exists or chart_path else None,
    table_path=csv_path if csv_exists or csv_path else None,
    table_png_path=table_png_path if table_png_exists or table_png_path else None,  # U7.9
)
```

#### Feedback Atualizado
```python
items = ["• resumo"]
if chart_exists or chart_path:
    items.append("• gráfico de preços")
if csv_exists or csv_path:
    items.append("• tabela CSV")
if table_png_exists:
    items.append("• tabela PNG")  # U7.9

items_text = "\n".join(items)
```

## Resultado Visual

### Antes (U7.8)
- Células sem bordas (tudo grudado)
- Difícil de distinguir linhas
- Títulos truncados sem quebra
- Alinhamento inconsistente

### Depois (U7.9)
- ✅ Bordas visíveis (#B8B8B8, 0.8pt)
- ✅ Cabeçalho azul destacado (#2E86AB)
- ✅ Zebra striping (#F7F7F7 / branco)
- ✅ Novos concorrentes com fundo verde (#D4EDDA)
- ✅ Títulos com quebra de linha (28 chars)
- ✅ Lojas com quebra de linha (18 chars)
- ✅ Alinhamento correto:
  - Centro: Rank, Preço, Novo
  - Esquerda: Produto, Loja
- ✅ Altura de linha 1.6x (mais espaçoso)
- ✅ DPI 180 (alta qualidade)

## Teste de Validação

```bash
.\venv\Scripts\python.exe scripts/test_sentinel_report_from_last_run.py
```

**Resultado:**
```
✅ Relatório gerado:
   chart_path: data\reports\sentinela_mochila_roxa_20260427_144144_chart.png
   csv_path: data\reports\sentinela_mochila_roxa_20260427_144144_table.csv
   table_png_path: data\reports\sentinela_mochila_roxa_20260427_144144_table.png

✅ Arquivos existem no disco:
   chart: True
   csv: True
   png: True

✅ Tudo OK: Relatório gerado com sucesso
```

## Ordem de Envio no Telegram

1. **📝 Resumo textual** (mensagem HTML)
   - Loja, keyword, concorrentes analisados
   - Novos concorrentes
   - Preço médio, mínimo, máximo

2. **📊 Gráfico de preços** (PNG)
   - Linha de preços por ranking
   - Destaque para novos concorrentes (estrela vermelha)
   - Linha de preço médio

3. **📋 Tabela de concorrentes** (PNG) - **NOVO!**
   - Top 15 concorrentes
   - Bordas visíveis
   - Zebra striping
   - Novos destacados em verde
   - Quebra de linha em títulos longos

4. **📄 CSV para exportação** (documento)
   - Dados brutos para análise
   - Importação em Excel/Sheets

## Próximos Passos para Validação

1. **Rodar novo Sentinela:**
   ```
   /sentinela rodar
   ```

2. **Verificar Telegram:**
   - ✅ Resumo textual
   - ✅ Gráfico de preços
   - ✅ Tabela PNG (legível, com bordas)
   - ✅ CSV (opcional)

3. **Testar reenvio:**
   ```
   /sentinela relatorio
   ```
   
   **Esperado:**
   ```
   ✅ Relatório enviado ao Telegram!
   
   Itens enviados:
   • resumo
   • gráfico de preços
   • tabela CSV
   • tabela PNG
   ```

## Arquivos Modificados

1. `shopee_core/sentinel_report_service.py`
   - Função `generate_competitor_table_png()` completamente reescrita
   - Bordas, alinhamento, quebra de linha, zebra striping
   - Destaque para novos concorrentes

2. `telegram_service.py`
   - Novo parâmetro `table_png_path` em `enviar_relatorio_sentinela()`
   - Ordem de envio otimizada (PNG antes de CSV)
   - Legendas atualizadas

3. `api_server.py`
   - Passa `table_png_path` ao Telegram

4. `shopee_core/whatsapp_service.py`
   - Comando `/sentinela relatorio` atualizado
   - Feedback com lista de itens enviados

## Status

✅ **IMPLEMENTADO E TESTADO**

A tabela PNG agora está profissional e legível, com bordas visíveis, alinhamento correto, quebra de linha e destaque para novos concorrentes. O Telegram receberá:
1. Resumo textual
2. Gráfico de preços
3. **Tabela PNG (visual, legível)**
4. CSV (dados brutos)

## Commit

```bash
git add shopee_core/sentinel_report_service.py telegram_service.py api_server.py shopee_core/whatsapp_service.py U7_9_IMPLEMENTADO.md
git commit -m "feat(sentinela): U7.9 - Melhorar tabela PNG do Telegram

- Reescrever generate_competitor_table_png() com formatação profissional
- Adicionar bordas visíveis em todas as células (#B8B8B8, 0.8pt)
- Cabeçalho destacado em azul (#2E86AB) com bordas mais grossas
- Zebra striping para melhor leitura (#F7F7F7 / branco)
- Destaque para novos concorrentes (fundo verde #D4EDDA)
- Quebra de linha em títulos (28 chars) e lojas (18 chars)
- Alinhamento por coluna (centro para números, esquerda para texto)
- Altura de linha aumentada (1.6x) para melhor espaçamento
- DPI aumentado para 180 (alta qualidade)
- Renomear colunas (Ranking → Rank, Título → Produto)
- Adicionar table_png_path em enviar_relatorio_sentinela()
- Ordem de envio: resumo → gráfico → tabela PNG → CSV
- Atualizar /sentinela relatorio para enviar tabela PNG
- PNG = leitura humana, CSV = exportação/análise"
```
