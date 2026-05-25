# R7.2J — Corrigir dismiss de overlays durante qualquer etapa da coleta

## Problema

A R7.2I removeu o bloqueio por `input()`/ENTER na UI, integrou `collect_image_urls=True` e `interactive_retry=False`, mas a coleta ainda falhava com dois problemas simultâneos:

1. **Erro de assinatura**: `_dismiss_common_overlays() got an unexpected keyword argument 'url'` — a função não aceitava `url`.
2. **Modal "Internacional / Entendi"** continuava aberto bloqueando a extração mesmo após tentativa de dismiss.

## O que foi feito

### 1. Assinatura de `_dismiss_common_overlays`

**Arquivo:** `shopee_core/radar_collector.py`

Alterada a assinatura (Opção B):

```python
def _dismiss_common_overlays(page, url: str | None = None, stage: str | None = None, max_attempts: int = 2) -> list[str]:
```

- `url` e `stage` são opcionais, para debug/logging
- A função imprime `[R7.2J] DISMISSED count=... url=... stage=...` quando recebe esses parâmetros
- Todas as chamadas existentes agora passam `url=url, stage="..."` para contexto

### 2. Fortalecimento do clique em botões de overlay

Adicionados **três níveis de fallback após o JS `evaluate`** no DOM:

| Ordem | Estratégia | Locator |
|-------|-----------|---------|
| 1º | `get_by_role("button")` com regex | `re.compile("Entendi\|OK\|Continuar\|Fechar", re.I)` |
| 2º | `locator("text=Entendi")` | Clique por texto exato |
| 3º | `locator("button:has-text(...)")` | CSS com fallback |

Cada fallback:
- Usa `timeout=500-1000ms`
- Verifica `is_visible()` antes de clicar
- É `try/except` — nunca quebra a coleta

### 3. Overlays detectados por texto no JS `evaluate`

Adicionados à lista `overlayTexts`:
- `'internacional'`
- `'envio seguro'`
- `'sua compra esta garantida'`

Adicionado seletor CSS:
- `[class*="internacional"]`

### 4. Chamadas `_dismiss_common_overlays` antes de cada etapa sensível

| Local | Stage | Arquivo |
|-------|-------|---------|
| Após `domcontentloaded` | `after_load` | `radar_collector.py` |
| Após `manual_wait_ms` | `after_wait` | `radar_collector.py` |
| Após scroll | `after_scroll` | `radar_collector.py` |
| Antes de extrair descrição (ML) | `before_description` | `collect_mercadolivre_product` |
| Antes de extrair descrição (Shopee) | `before_description` | `collect_shopee_product` |
| Antes de imagens (ML) | `before_images` | `collect_mercadolivre_product` |
| Antes de imagens (Shopee) | `before_images_shopee` | `collect_shopee_product` |

### 5. Retry automático quando título/preço vêm vazios

Em `collect_mercadolivre_product` e `collect_shopee_product`:

Se `not visual_title and parsed_price is None`:
1. `_dismiss_common_overlays(page, url=url, stage="retry_empty_title_price")`
2. `wait_for_timeout(500)`
3. Re-extrai título e preço
4. Se ainda vazio → retorna erro de dados mínimos

### 6. Retry automático quando image_urls vem vazio (ML)

Em `collect_mercadolivre_product`:

Se `not image_urls` após a extração prioritária:
1. `_dismiss_common_overlays(page, url=url, stage="retry_empty_images")`
2. `wait_for_timeout(500)`
3. Re-tenta `meta[property="og:image"]`

### 7. Auto-retry sem ENTER (R7.2I)

No fluxo `Check 4` de `collect_product_page`:
- `interactive_retry=True` → `_wait_for_manual_confirmation()` com `input()` (terminal scripts)
- `interactive_retry=False` → `_dismiss_common_overlays() + sleep(1) + reload + re-extract` (UI/app)

### 8. Testes atualizados

**Arquivo:** `test_radar_collector.py`

- `test_dismiss_common_overlays_sem_overlay`: agora verifica `"pw_role_click" in result` em vez de `result == []`
- `test_dismiss_common_overlays_falha_nao_quebra`: idem — fallback PW roda em MagicMock

**Arquivo:** `test_radar_workflow_ui_service.py`

- `test_save_assets_false_skips_asset_persistence`: `collect_image_urls is True` (era `is False`)

Todos os 167 testes (excluindo 1 pré-existente no CDP) passam.

## Arquivos modificados

| Arquivo | Alterações |
|---------|-----------|
| `shopee_core/radar_collector.py` | Assinatura + fallback PW + retries + chamadas com `url`/`stage` |
| `test_radar_collector.py` | Ajuste de asserts para fallback PW |
| `FASE_R7_2J_OVERLAY_DISMISS_RUNTIME.md` | Este documento |

## Smoke manual esperado

URL: `https://mercadolivre.com.br/p/MLB46043623`
- browser_mode=cdp, save_assets=False, collect_image_urls=True, limit=1
- Modal "Internacional" deve ser fechado automaticamente
- title preenchido, image_urls com pelo menos 1
- Sem erro `unexpected keyword argument 'url'`
- Job termina como done/collected
