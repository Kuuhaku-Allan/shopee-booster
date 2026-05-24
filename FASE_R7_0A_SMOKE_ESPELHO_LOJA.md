# Fase R7.0A — Smoke Real do Espelho da Loja

**Status:** ✅ Concluído  
**Data:** 2026-05-24  

---

## Objetivo

Validar em fluxo real que o Espelho da Loja salva produtos carregados pela Auditoria e consegue servir como fallback quando a Shopee falha ou retorna loja vazia.

---

## O Que Foi Feito

### 1. `shopee_core/audit_service.py`

- **`_is_force_fallback()`** — helper que lê `SHOPEE_FORCE_RADAR_STORE_FALLBACK`
  - Aceita: `true`, `1`, `yes`, `sim` (case insensitive)
  - Padrão: `False` (jamais ativo sem ser explicitamente setado)
- **`load_shop_from_url()`** — refatorado com:
  - Modo force-fallback: pula Shopee inteiramente e carrega só do espelho local
  - Snapshot só é salvo quando há carga real bem-sucedida (não durante fallback)
  - Logs `[R7.0]` melhorados: incluem `store_uid`, `shop_slug`, `shop_uid`, contagem
  - `source_label: "espelho local do Radar"` em todas as respostas de cache
- **`_save_store_mirror()`** foi inlined na lógica principal e usa `save_store_snapshot` diretamente

### 2. `app.py`

- **`_is_force_fallback_app()`** — helper idêntico ao do `audit_service`, isolado para o módulo UI
- **`_save_audit_store_mirror()`** — docstring + log melhorado (inclui `store_uid`)
- **`_load_audit_store_mirror()`** — docstring + log de aviso quando cache está vazio
- **`render_auditoria()`** — bloco de carregamento da loja agora suporta:
  ```
  if SHOPEE_FORCE_RADAR_STORE_FALLBACK:
      → pula Shopee, carrega espelho local
      → mostra warning visual de "Modo debug"
      → mensagem de erro amigável se cache estiver vazio
  else:
      → fluxo normal: Shopee → fallback automático → erro
  ```

### 3. `scripts/radar_store_smoke.py` *(NOVO)*

Script de smoke automatizado (6 passos):

1. Snapshot inicial com 5 produtos realistas
2. Inspecionar cache e status agregado
3. Verificar `radar_products` vinculados como `own_product`
4. Diff preview entre snapshot 1 e snapshot 2
5. Aplicar snapshot 2 (1 novo, 1 preço alterado, 1 ausente)
6. Confirmar estado final (active/changed/missing)

**IDs únicos por run** — evita conflito entre execuções no mesmo DB.

### 4. `scripts/radar_inspect_store.py` *(MELHORADO)*

Output agora inclui:
- `store_uid`, `shop_uid`, `shop_slug` separados
- Contagens: `total_products`, `active`, `changed`, `missing`, `removed`
- `last_seen_at`, `radar_source_type`, `last_source`
- Flag `--show-raw` para dump do `raw_json`

### 5. `test_radar_store_service.py` — 5 novos testes R7.0A

| Teste | Valida |
|-------|--------|
| `test_force_fallback_returns_cache_when_exists` | Env var ativa + cache preenchido → retorna produtos do espelho |
| `test_force_fallback_returns_empty_friendly_when_no_cache` | Sem cache → lista vazia sem excecão |
| `test_force_fallback_env_false_by_default` | Sem env var → `_is_force_fallback()` retorna `False` |
| `test_force_fallback_save_snapshot_not_called_when_forced` | Force-fallback só lê, nunca escreve |
| `test_force_fallback_accepts_multiple_truthy_values` | Aceita `true/1/yes/sim` e rejeita `false/0/no/off` |

---

## Resultados

```
TESTE R7.0 + R7.0A - Espelho da Loja no Radar

PASS - upsert_store cria loja
PASS - save_store_snapshot salva produtos
PASS - save_store_snapshot cria radar_products own_product
PASS - snapshot repetido nao duplica produtos
PASS - preco alterado marca changed/updated
PASS - produto ausente vira missing
PASS - get_cached_store_products retorna ativos
PASS - diff detecta produto novo
PASS - diff detecta alteracao de preco
PASS - cache vazio nao quebra
PASS - find_radar_product_for_store_product vincula Radar
PASS - [R7.0A] force_fallback retorna cache quando existe
PASS - [R7.0A] force_fallback retorna vazio amigavel sem cache
PASS - [R7.0A] force_fallback False por padrao
PASS - [R7.0A] force_fallback nao salva snapshot (so leitura)
PASS - [R7.0A] force_fallback aceita true/1/yes/sim

Total: 16/16 testes passaram
```

**Smoke script:** 6/6 passos OK (snapshot → cache → own_products → diff → snapshot v2 → estado final → cleanup)

---

## Como Usar o Fallback Forçado

```bash
# Ativar force-fallback (para teste/debug)
$env:SHOPEE_FORCE_RADAR_STORE_FALLBACK = "true"

# Rodar o app
streamlit run app.py

# Desativar
Remove-Item Env:SHOPEE_FORCE_RADAR_STORE_FALLBACK
```

A UI mostrará um aviso amarelo: **"Modo debug: SHOPEE_FORCE_RADAR_STORE_FALLBACK ativo"**

---

## Regra de Ouro

> **O fallback forçado só lê. Nunca salva. Nunca sobrescreve.**
>
> `save_store_snapshot()` só é chamado quando `_is_force_fallback() == False`
> e a carga real da Shopee retornou produtos.

---

## Próxima Fase

**R7.1 — Tela do Espelho da Loja no .exe**
- Mostrar produtos salvos com status (active/changed/missing)
- Botão de atualização e histórico de diffs
- Uso do cache na UI sem precisar da variável de ambiente

---

## Arquivos Modificados

| Arquivo | Tipo | Mudança |
|---------|------|---------|
| `shopee_core/audit_service.py` | MODIFICADO | `_is_force_fallback()`, `load_shop_from_url()` |
| `app.py` | MODIFICADO | `_is_force_fallback_app()`, helpers, `render_auditoria()` |
| `scripts/radar_store_smoke.py` | NOVO | Smoke automatizado 6-passos |
| `scripts/radar_inspect_store.py` | MELHORADO | Output rico, `--show-raw` |
| `test_radar_store_service.py` | MODIFICADO | 5 novos testes R7.0A |
