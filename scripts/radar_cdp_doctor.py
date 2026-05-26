#!/usr/bin/env python3
"""
radar_cdp_doctor.py - Diagnostico do Chrome CDP do Radar.

Uso:
    python scripts/radar_cdp_doctor.py

Exibe:
- CDP responde? (versao do browser)
- Processo gerenciado pelo Radar existe?
- Porta 9222 ocupada?
- Chrome/Edge encontrado?
- user_data_dir
- PID file
- Recomendacao final
"""

from __future__ import annotations

import json
import os
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shopee_core.radar_cdp_service import (
    is_cdp_available,
    _fetch_json_version,
    find_chrome_executable,
    _find_radar_chrome_process,
    _read_radar_pid,
    _is_port_open,
    _get_wmi_processes,
    _is_radar_managed_process,
    PID_FILE,
    DEFAULT_PROFILE_DIR,
    DEFAULT_CDP_URL,
    CDP_PORT,
)


def _wmi_query_raw(query: str) -> str:
    try:
        ps = subprocess.run(
            ["powershell", "-NoProfile", "-Command", query],
            capture_output=True, text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return ps.stdout.strip() or "(vazio)"
    except Exception as e:
        return f"(erro: {e})"


def doctor():
    print("=" * 60)
    print("  RADAR CDP DOCTOR - Diagnostico do Chrome/CDP")
    print("=" * 60)

    # 1. Chrome executable
    print("\n[1] Chrome/Edge executavel")
    chrome_path = find_chrome_executable()
    if chrome_path:
        print(f"    Encontrado: {chrome_path}")
    else:
        print("    NAO ENCONTRADO - Chrome ou Edge nao esta instalado em caminhos comuns.")

    # 2. CDP availability
    print(f"\n[2] CDP endpoint: {DEFAULT_CDP_URL}/json/version")
    cdp_ok = is_cdp_available(DEFAULT_CDP_URL)
    if cdp_ok:
        version = _fetch_json_version(DEFAULT_CDP_URL)
        browser = (version or {}).get("Browser", "desconhecido")
        print(f"    OK - Chrome CDP respondendo: {browser}")
    else:
        print("    FALHA - /json/version nao respondeu")

    # 3. Port check
    port_open = _is_port_open(CDP_PORT)
    print(f"\n[3] Porta {CDP_PORT}")
    if port_open:
        print(f"    Porta {CDP_PORT} esta OCUPADA (algo esta ouvindo)")
    else:
        print(f"    Porta {CDP_PORT} esta LIVRE")

    # 4. Process radar managed
    radar_proc = _find_radar_chrome_process()
    print("\n[4] Processo gerenciado pelo Radar")
    if radar_proc:
        print(f"    Encontrado: PID {radar_proc['pid']} (fonte: {radar_proc['source']})")
    else:
        print("    Nenhum processo gerenciado do Radar encontrado.")

    # 5. All Chrome/Edge processes with debugging flag
    print("\n[5] Processos Chrome/Edge com --remote-debugging-port=9222")
    procs = _get_wmi_processes()
    radar_flags = [p for p in procs if _is_radar_managed_process(p)]
    other_cdp = [p for p in procs if "remote-debugging-port" in (p.get("command_line") or "") and p not in radar_flags]
    if radar_flags:
        for p in radar_flags:
            print(f"    [RADAR] PID {p['pid']} - {p['name']}")
    if other_cdp:
        for p in other_cdp:
            print(f"    [OUTRO] PID {p['pid']} - {p['name']}")
    if not radar_flags and not other_cdp:
        print("    Nenhum processo com remote-debugging-port encontrado.")

    # 6. All Chrome/Edge processes (brief)
    chrome_procs = [p for p in procs if p.get("name") in ("chrome.exe", "msedge.exe")]
    print(f"\n[6] Total de processos Chrome/Edge no sistema: {len(chrome_procs)}")
    for p in chrome_procs[:10]:
        flag = "[RADAR]" if _is_radar_managed_process(p) else "       "
        cmd_preview = (p.get("command_line") or "")[:120]
        print(f"    {flag} PID {p['pid']:>6}  {cmd_preview}")
    if len(chrome_procs) > 10:
        print(f"    ... e mais {len(chrome_procs) - 10} processo(s)")

    # 7. PID file
    print(f"\n[7] PID file: {PID_FILE}")
    if PID_FILE.exists():
        pid = _read_radar_pid()
        alive = False
        if pid:
            try:
                check = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                alive = str(pid) in check.stdout
            except Exception:
                pass
        print(f"    Existe: sim (PID registrado: {pid})")
        print(f"    Processo vivo: {'SIM' if alive else 'NAO (stale)'}")
    else:
        print("    Nao existe")

    # 8. user_data_dir
    print(f"\n[8] User data dir: {DEFAULT_PROFILE_DIR.resolve()}")
    ud = Path(DEFAULT_PROFILE_DIR.resolve())
    if ud.exists():
        items = list(ud.iterdir())
        print(f"    Existe: sim ({len(items)} itens)")
    else:
        print("    Existe: nao (sera criado ao iniciar Chrome)")

    # 9. PowerShell raw check for debugging
    print("\n[9] Diagnostico extra (PowerShell)")
    raw = _wmi_query_raw(
        "Get-CimInstance Win32_Process -Filter \"name='chrome.exe' OR name='msedge.exe'\" | "
        "Select-Object ProcessId, Name, CommandLine | ConvertTo-Json -Compress"
    )
    print(f"    {raw[:300]}")

    # ── Recommendation ─────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  RECOMENDACAO")
    print("=" * 60)

    if cdp_ok:
        print("  CDP OK - O Radar deve funcionar normalmente.")
        print("  Se ainda houver erro, verifique se o Chrome nao travou.")
    elif port_open:
        print("  Porta 9222 ocupada mas CDP nao responde.")
        print("  Execute: python -c \"from shopee_core.radar_cdp_service import kill_managed_radar_chrome; kill_managed_radar_chrome()\"")
        print("  Depois tente novamente.")
    elif not chrome_path:
        print("  Chrome/Edge nao encontrado. Instale o Chrome ou Edge.")
    else:
        print("  Chrome encontrado mas nao esta rodando com CDP.")
        print("  O Radar deve abri-lo automaticamente ao clicar em 'Rodar Radar Automatico'.")
        print("  Se falhar, abra manualmente:")
        print(f"    \"{chrome_path}\" --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 --user-data-dir=\"{DEFAULT_PROFILE_DIR.resolve()}\" --no-first-run --no-default-browser-check about:blank")

    print()


if __name__ == "__main__":
    doctor()
