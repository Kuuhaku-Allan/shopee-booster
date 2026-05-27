# Fase R7.3C — Restaurar perfil unico do Chrome do Radar

**Status:** Concluido  
**Precedencia:** R7.3B ✓

## Problema

Tanto o Radar Automatico quanto o Semiautomatico passaram a falhar com:
```
Chrome (PID xxxx) foi iniciado mas morreu em 2.5s.
```

## Causa raiz

Existiam **dois perfis diferentes** para o Chrome do Radar:

| Onde | Perfil |
|------|--------|
| Python `radar_cdp_service.py` | `data/radar_chrome_profile` |
| PS1 `deploy/local/start-radar-chrome.ps1` | `data/chrome_radar_profile` |

Isso causava:
- Python tentava abrir Chrome com `radar_chrome_profile` (perfil novo, vazio, com locks stale)
- `_is_radar_managed_process()` so reconhecia `radar_chrome_profile` — nao via Chrome aberto pelo PS1
- PID do PowerShell era salvo como PID do Chrome (errado, virava stale)
- Fluxos conflitavam entre si

## Solucao

### 1. Perfil oficial unico: `data/chrome_radar_profile`

```python
DEFAULT_PROFILE_DIR = _BASE / "data" / "chrome_radar_profile"
```

### 2. `_is_radar_managed_process()` aceita ambos os perfis

```python
def _is_radar_managed_process(proc) -> bool:
    cmdline = proc.CommandLine or ""
    if "remote-debugging-port=9222" not in cmdline:
        return False
    return "chrome_radar_profile" in cmdline or "radar_chrome_profile" in cmdline
```

### 3. PS1: PID correto do Chrome

Ao chamar `start-radar-chrome.ps1` via Python, o `proc.pid` e o PID do
PowerShell, nao do Chrome. Agora:
- Nao salva `proc.pid`
- Aguarda CDP responder (ate 15s)
- Busca o PID real do Chrome via WMI com o filtro correto
- Salva esse PID em `data/radar_chrome.pid`

### 4. Doctor alerta sobre divergencia de perfis

`scripts/radar_cdp_doctor.py` agora mostra:
- Perfil oficial atual
- Se `data/chrome_radar_profile` existe
- Se `data/radar_chrome_profile` (legado) tambem existe
- Se ha processos usando cada um
- Alerta: "Existem DOIS perfis de Radar"

## Arquivos modificados

- `shopee_core/radar_cdp_service.py`:
  - `DEFAULT_PROFILE_DIR` → `data/chrome_radar_profile`
  - `_is_radar_managed_process()` aceita ambos os perfis
  - `start_radar_chrome()`: PS1 nao salva PID do PowerShell, busca Chrome real
- `scripts/radar_cdp_doctor.py`: mostra divergencia de perfis
- `test_radar_cdp_service.py`: 31 testes (1 novo: legacy profile)

## Testes

```bash
python -m pytest test_radar_cdp_service.py -v       # 31 testes
```

## Smoke manual

### Passo 1: Verificar que PS1 funciona
```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\local\start-radar-chrome.ps1
Invoke-RestMethod http://127.0.0.1:9222/json/version
```

### Passo 2: Doctor
```bash
python scripts/radar_cdp_doctor.py
```
Verificar: perfil oficial = `chrome_radar_profile`, sem alerta de divergencia.

### Passo 3: Python —start
```bash
python scripts/radar_cdp_doctor.py --start
```
Verificar: CDP responde.

### Passo 4: UI
1. Fechar Chrome do Radar
2. Abrir app: `python app.py`
3. Clicar "Rodar Radar Automatico"
4. Verificar: passa da etapa chrome

## Proximas fases
- R7.4: Renovação semanal automática
