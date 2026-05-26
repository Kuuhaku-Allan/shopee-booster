# Fase R7.3B — Unificar boot do Chrome CDP entre Radar Semiautomatico e Automatico

**Status:** Em desenvolvimento  
**Precedencia:** R7.3A ✓

## Problema observado

O Radar Semiautomatico funciona com CDP (via `start-radar-chrome.ps1` aberto manualmente),
mas o Radar Automatico falha na etapa "Abrindo Chrome":

```
Chrome (PID 22816) foi iniciado mas morreu em 2.5s.
```

Diagnostico completo:
- Chrome executable encontrado
- Porta 9222 livre
- `/json/version` nao responde
- Processo PID 22816 foi criado mas morreu
- stderr vazio (Chrome crashou silenciosamente)
- Nenhum outro processo Chrome com `remote-debugging-port`

## Causa raiz

O `subprocess.Popen()` do Python nao consegue iniciar o Chrome com as flags
`--remote-debugging-port` corretamente, mesmo com as mesmas flags do PS1.
O processo Chrome morre antes de expor a porta CDP, sem output de erro.

O `Start-Process` do PowerShell usado no PS1 funciona porque lida de forma
diferente com processos GUI no Windows (grupo de janela independente).

## Solucao

O `start_radar_chrome()` agora:
1. **Tenta o PS1 primeiro**: `powershell -ExecutionPolicy Bypass -File deploy/local/start-radar-chrome.ps1`
2. **Fallback**: `subprocess.Popen` direto (se PS1 nao existir ou falhar)

Isso garante que o automatico use **exatamente o mesmo caminho** que o
semiautomatico ja testado e funcional.

## Arquivos modificados

- `shopee_core/radar_cdp_service.py`:
  - `start_radar_chrome()`: tenta PS1 primeiro, fallback subprocess
  - Nova constante `_PS1_SCRIPT = _BASE / "deploy" / "local" / "start-radar-chrome.ps1"`
  - `_clean_stale_locks()`: remove SingletonLock/Cookie/Socket stale
  - `ensure_radar_chrome_ready()`: detecta processo que morre durante espera
  - stderr capturado em arquivo temporario para diagnostico
- `scripts/radar_cdp_doctor.py`:
  - `--start`: abre Chrome e testa CDP
  - `--print-start-command`: exibe comando usado
  - Mostra lock files no profile
  - `_build_chrome_cmd()` exportada para doctor

## Testes

```bash
python -m pytest test_radar_cdp_service.py -v       # 30 testes
python -m pytest test_radar_relevance_service.py test_radar_patterns_service.py -v  # 55 testes
python -m pytest test_radar_discovery_service.py -v   # 11 testes
```

## Smoke manual

### Cenario 1: PS1 direto
```powershell
powershell -ExecutionPolicy Bypass -File deploy/local/start-radar-chrome.ps1
```
Verificar: Chrome abre, http://127.0.0.1:9222/json/version responde.

### Cenario 2: Doctor --start
```bash
python scripts/radar_cdp_doctor.py --start
```
Verificar: Chrome abre, CDP responde, script retorna codigo 0.

### Cenario 3: UI "Rodar Radar Automatico"
1. Abrir app: `python app.py`
2. Navegar para Radar Assistido
3. Clicar "Rodar Radar Automatico"
4. Verificar: passa da etapa chrome, avanca para buscas

### Cenario 4: Reutilizar CDP existente
1. Abrir Chrome via PS1 manualmente
2. Clicar "Rodar Radar Automatico"
3. Verificar: "Chrome do Radar ja estava ativo", pula etapa de abertura

## Proximas fases
- R7.4: Renovacao semanal automatica
