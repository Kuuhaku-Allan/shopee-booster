# Fase R7.3A — Boot Robusto do Chrome/CDP no Radar Automatico

**Status:** Em desenvolvimento  
**Precedencia:** R7.3 ✓

## Problema observado

Ao clicar em "Rodar Radar Automatico", o ciclo parava na etapa "Abrindo Chrome":
o Chrome abria visualmente mas o app nao conseguia acessar
`http://127.0.0.1:9222/json/version` no tempo limite de 15s.

## Causas provaveis

1. Chrome aberto **sem `--remote-debugging-port=9222`**
2. Chrome aberto com perfil travado ou porta ocupada
3. Instancia antiga do Chrome Radar ocupando o perfil/porta
4. Timeout de 15s curto demais para Windows
5. Falta de `--remote-debugging-address=127.0.0.1`
6. `user-data-dir` nao era caminho absoluto

## O que foi corrigido

### 1. Centralizacao do boot (ja existia)
`radar_discovery_service.py` ja usava `ensure_radar_chrome_ready()` de
`radar_cdp_service.py` — nenhuma logica duplicada.

### 2. `ensure_radar_chrome_ready()` melhorada
- Timeout: 15s → **45s** (90 tentativas a cada 0.5s)
- Progress callback opcional com stages detalhados
- Diagnostico completo em caso de falha:
  ```json
  {
    "chrome_executable": "C:\\...\\chrome.exe",
    "user_data_dir": "C:\\...\\data\\radar_chrome_profile",
    "pid_file": "C:\\...\\data\\radar_chrome.pid",
    "port_open": true,
    "cdp_responded": false,
    "json_version_error": "Connection refused",
    "process_started": true,
    "pid": 1234
  }
  ```

### 3. Flags corretas ao abrir Chrome
```text
--remote-debugging-port=9222
--remote-debugging-address=127.0.0.1
--user-data-dir=<ABSOLUTE_PATH>/data/radar_chrome_profile
--no-first-run
--no-default-browser-check
--disable-sync
--disable-default-apps
--disable-extensions
about:blank
```

### 4. PID file management
- PID salvo em `data/radar_chrome.pid`
- `_read_radar_pid()`, `_write_radar_pid()`, `_clear_radar_pid()`
- `kill_managed_radar_chrome()`: mata APENAS processos com:
  - `remote-debugging-port=9222` **E** `radar_chrome_profile` no command line
  - **Nunca** mata Chrome pessoal do usuario

### 5. Porta ocupada sem CDP
Se porta 9222 estiver ocupada mas `/json/version` nao responder,
retorna erro claro com PID do processo ocupante.

### 6. Script de diagnostico
`scripts/radar_cdp_doctor.py`:
```bash
python scripts/radar_cdp_doctor.py
```
Mostra: CDP responde?, Chrome encontrado, PID file, processos com flag,
porta 9222, recomendacao final.

### 7. UI melhorada
- Progresso com stages detalhados: "Procurando Chrome/Edge" →
  "Abrindo Chrome do Radar" → "Aguardando porta 9222" → "Validando CDP"
- Botoes: "Reconectar ao Chrome aberto" e "Reiniciar Chrome do Radar"
- Em falha: expander com diagnostico, botoes retry reconectar/reiniciar

### 8. Erro de Chrome nao marca jobs/produtos como failed
O ciclo retorna `environment_error=True` e `step="chrome"` antes de
qualquer operacao de banco de dados. Nenhum candidato e inserido,
nenhuma coleta disparada, nenhuma classificacao feita.

## Arquivos modificados/criados

- `shopee_core/radar_cdp_service.py` — reescrito: timeout 45s, PID file,
  diagnostico, progress callback, kill de processo gerenciado, deteccao
  de porta ocupada
- `shopee_core/radar_discovery_service.py` — resultado inclui `diagnostics`,
  progresso mais detalhado na etapa Chrome
- `app.py` — botoes reconectar/reiniciar, progresso com stages,
  expander de diagnostico em falha
- `test_radar_cdp_service.py` — 30 testes
- `test_radar_discovery_service.py` — 2 testes atualizados (mock Chrome)
- `scripts/radar_cdp_doctor.py` — novo script de diagnostico CLI
- `FASE_R7_3A_CDP_BOOT_ROBUSTO.md` — esta documentacao

## Testes

```bash
python -m pytest test_radar_cdp_service.py -v       # 30 testes
python -m pytest test_radar_discovery_service.py -v   # 11 testes
python -m pytest test_radar_relevance_service.py test_radar_patterns_service.py -v  # 55 testes
```

## Smoke manual

### Cenario A: Chrome fechado
1. Fechar Chrome do Radar (se estiver aberto)
2. Abrir app: `python app.py`
3. Navegar para Radar Assistido
4. Clicar "Rodar Radar Automatico"
5. Esperado: Chrome abre, `/json/version` responde, ciclo continua

### Cenario B: Chrome ja aberto
1. Garantir que Chrome do Radar esta aberto com CDP
2. Clicar "Rodar Radar Automatico"
3. Esperado: reutiliza CDP existente, pula etapa de abertura

### Cenario C: Processo travado
1. Executar `scripts/radar_cdp_doctor.py`
2. Verificar diagnostico
3. Clicar "Reiniciar Chrome do Radar" na UI
4. Esperado: Chrome antigo encerrado, novo aberto

## Proximas fases
- R7.4: Renovação semanal automática (usa o mesmo boot robusto)
