# U7.8 - Correção de Paths do Relatório

## Problema Identificado

O relatório do Sentinela estava sendo salvo no banco com `chart_path`, `csv_path` e `table_png_path` como `None`, mesmo quando havia 30 concorrentes coletados.

## Diagnóstico

### Teste Executado
```bash
.\venv\Scripts\python.exe -c "from shopee_core.bot_state import get_latest_sentinel_run; r=get_latest_sentinel_run('5511988600050@s.whatsapp.net','8de0c133-f9b3-475b-bf68-cd59be13f461'); print('concorrentes=', len(r.get('resultado', {}).get('concorrentes', []))); print('chart=', r.get('chart_path'))"
```

**Resultado:**
- ✅ `concorrentes= 30` (dados existem)
- ❌ `chart= None` (paths não salvos)

### Causa Raiz

**Matplotlib não estava instalado!**

O `sentinel_report_service.py` importa matplotlib, mas a biblioteca não estava no ambiente. Isso causava:
1. Exceção silenciosa no bloco `try/except` de geração de relatório
2. Variáveis `chart_path`, `csv_path`, `table_png_path` ficavam indefinidas
3. `save_sentinel_run()` recebia valores `None` ou causava erro

## Correções Implementadas

### 1. Instalação de Dependência Faltante
```bash
.\venv\Scripts\python.exe -m pip install matplotlib
```

### 2. Inicialização de Variáveis (api_server.py)
```python
# Inicializa variáveis antes do try (U7.8)
chart_path = None
table_csv_path = None
table_png_path = None
```

**Motivo:** Garante que as variáveis existam mesmo se houver exceção no bloco try.

### 3. Logs de Diagnóstico Detalhados (api_server.py)

#### Antes de gerar relatório:
```python
log.info(f"[RELATORIO] resultado.keys={list(resultado.keys())}")
log.info(f"[RELATORIO] concorrentes_len={len(resultado.get('concorrentes', []))}")
if resultado.get('concorrentes'):
    log.info(f"[RELATORIO] primeiro_concorrente={resultado.get('concorrentes', [None])[0]}")
```

#### Após gerar relatório:
```python
from pathlib import Path
chart_exists = Path(chart_path).exists() if chart_path else False
csv_exists = Path(table_csv_path).exists() if table_csv_path else False
png_exists = Path(table_png_path).exists() if table_png_path else False

log.info(f"[RELATORIO] chart_exists={chart_exists}")
log.info(f"[RELATORIO] csv_exists={csv_exists}")
log.info(f"[RELATORIO] table_png_exists={png_exists}")
```

#### Antes de salvar:
```python
log.info(f"[DEBUG] Salvando com chart_path={chart_path}, csv_path={table_csv_path}, png_path={table_png_path}")
```

#### Alerta de erro de normalização:
```python
if len(resultado.get('concorrentes', [])) > 0 and not chart_path:
    log.error("[RELATORIO] ERRO: Concorrentes existem mas chart_path está vazio - problema de normalização!")
```

### 4. Campos Adicionais nos Concorrentes (api_server.py)
```python
concorrentes.append({
    "ranking": i + 1,
    "titulo": c.get("nome", ""),
    "preco": float(c.get("preco", 0) or 0),
    "loja": str(c.get("shop_id") or ""),
    "url": c.get("url", ""),  # U7.8: Adicionar URL
    "is_new": False,
    "keyword": kw,
    "item_id": c.get("item_id"),
    "shop_id": c.get("shop_id"),
    "source": "shopee",  # U7.8: Adicionar source
})
```

### 5. Logs Detalhados no Report Service (sentinel_report_service.py)

#### Em `build_competitor_dataframe`:
```python
log.info(f"[REPORT] build_competitor_dataframe: recebeu {len(concorrentes)} concorrentes")
if concorrentes:
    log.info(f"[REPORT] Primeiro concorrente: {concorrentes[0]}")
log.info(f"[REPORT] DataFrame criado: {len(df)} linhas")
```

#### Em `generate_sentinel_report`:
```python
log.info(f"[REPORT] include_chart={include_chart}, include_csv={include_csv}, include_table_png={include_table_png}")
log.info("[REPORT] Construindo DataFrame...")
log.info(f"[REPORT] DataFrame construído: empty={df.empty}, shape={df.shape if not df.empty else 'N/A'}")

if not df.empty:
    log.info("[REPORT] DataFrame não está vazio, gerando arquivos...")
    # ... para cada arquivo:
    log.info(f"[REPORT] Gerando gráfico: {chart_path}")
    log.info(f"[REPORT] Gráfico gerado: {report['chart_path']}")
else:
    log.warning("[REPORT] DataFrame está vazio, não será possível gerar arquivos")
```

### 6. Script de Teste Isolado

Criado `scripts/test_sentinel_report_from_last_run.py` que:
1. Carrega último `sentinel_run` do banco
2. Imprime `len(resultado["concorrentes"])`
3. Gera gráfico/CSV/PNG
4. Verifica se arquivos existem no disco
5. Fornece diagnóstico detalhado

## Teste de Validação

```bash
.\venv\Scripts\python.exe scripts/test_sentinel_report_from_last_run.py
```

**Resultado:**
```
✅ Run encontrado: 5511988600050@s.whatsapp.net_2026-04-27-17
   Status: done
   Concorrentes: 30

✅ Relatório gerado:
   chart_path: data\reports\sentinela_mochila_roxa_20260427_143021_chart.png
   csv_path: data\reports\sentinela_mochila_roxa_20260427_143021_table.csv
   table_png_path: data\reports\sentinela_mochila_roxa_20260427_143021_table.png

✅ Arquivos existem no disco:
   chart: True
   csv: True
   png: True

✅ Tudo OK: Relatório gerado com sucesso
```

## Próximos Passos

### Para Validar a Correção Completa:

1. **Rodar novo Sentinela:**
   ```
   /sentinela rodar
   ```

2. **Verificar logs do servidor:**
   - `[RELATORIO] concorrentes_len=X` deve mostrar número > 0
   - `[RELATORIO] chart_exists=True` deve aparecer
   - `[DEBUG] Salvando com chart_path=data\reports\...` deve mostrar paths válidos

3. **Testar reenvio:**
   ```
   /sentinela relatorio
   ```
   
   **Esperado:**
   - ✅ resumo textual
   - ✅ gráfico de preços (PNG)
   - ✅ tabela CSV
   - ✅ tabela PNG (opcional)

4. **Verificar banco:**
   ```bash
   .\venv\Scripts\python.exe -c "from shopee_core.bot_state import get_latest_sentinel_run; r=get_latest_sentinel_run('5511988600050@s.whatsapp.net','8de0c133-f9b3-475b-bf68-cd59be13f461'); print('chart=', r.get('chart_path')); print('csv=', r.get('table_csv_path')); print('png=', r.get('table_png_path'))"
   ```
   
   **Esperado:** Todos os paths devem estar preenchidos (não `None`)

## Arquivos Modificados

1. `api_server.py` (função `_run_sentinel_bg`)
   - Inicialização de variáveis antes do try
   - Logs de diagnóstico detalhados
   - Validação de existência de arquivos
   - Campos adicionais nos concorrentes

2. `shopee_core/sentinel_report_service.py`
   - Logs detalhados em todas as funções
   - Rastreamento do fluxo de geração

3. `scripts/test_sentinel_report_from_last_run.py` (novo)
   - Script de teste isolado para validação

## Status

✅ **IMPLEMENTADO E TESTADO**

A geração de relatório está funcionando corretamente. O problema era a falta de matplotlib no ambiente. Com a biblioteca instalada e os logs adicionados, o próximo `/sentinela rodar` deve salvar os paths corretamente no banco.

## Commit

```bash
git add api_server.py shopee_core/sentinel_report_service.py scripts/test_sentinel_report_from_last_run.py U7_8_IMPLEMENTADO.md
git commit -m "fix(sentinela): U7.8 - Corrigir salvamento de paths do relatório

- Instalar matplotlib (dependência faltante)
- Inicializar variáveis chart_path/csv_path/png_path antes do try
- Adicionar logs detalhados de diagnóstico em todo fluxo
- Validar existência de arquivos após geração
- Adicionar campos url e source nos concorrentes
- Criar script de teste isolado test_sentinel_report_from_last_run.py
- Logs mostram: concorrentes recebidos, DataFrame criado, arquivos gerados
- Próximo /sentinela rodar deve salvar paths corretamente"
```
