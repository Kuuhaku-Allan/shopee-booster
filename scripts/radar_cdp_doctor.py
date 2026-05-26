#!/usr/bin/env python3
"""
radar_cdp_doctor.py - Diagnostico do Chrome CDP do Radar.

Uso:
    python scripts/radar_cdp_doctor.py            # diagnostico completo
    python scripts/radar_cdp_doctor.py --print-start-command  # exibe comando usado
    python scripts/radar_cdp_doctor.py --start     # abre Chrome e testa CDP

Exibe:
- CDP responde? (versao do browser)
- Processo gerenciado pelo Radar existe?
- Porta 9222 ocupada?
- Chrome/Edge encontrado?
- user_data_dir
- PID file
- Lock files no profile
- Recomendacao final
"""

from __future__ import annotations

import json
import os
import sys
import time
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
    _build_chrome_cmd,
    start_radar_chrome,
    ensure_radar_chrome_ready,
    PID_FILE,
    DEFAULT_PROFILE_DIR,
    DEFAULT_CDP_URL,
    CDP_PORT,
    _BASE,
    _OFFICIAL_PROFILE_NAME,
    _LEGACY_PROFILE_NAME,
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


def print_start_command():
    """Print the exact command that would be used to start Chrome CDP."""
    chrome_path = find_chrome_executable()
    if not chrome_path:
        print("Chrome/Edge nao encontrado. Nao e possivel montar comando.")
        return

    profile_dir = DEFAULT_PROFILE_DIR.resolve()
    cmd = _build_chrome_cmd(chrome_path, CDP_PORT, profile_dir)

    print("Comando que seria usado para abrir Chrome CDP:")
    print()
    # Show one flag per line for readability
    print(f"  {cmd[0]}")
    for flag in cmd[1:-1]:
        print(f"    {flag}")
    print(f"    {cmd[-1]}")
    print()
    print(f"  Caminho absoluto:     {chrome_path}")
    print(f"  User data dir:        {profile_dir}")
    print(f"  CDP endpoint:         http://127.0.0.1:{CDP_PORT}")
    print(f"  Profile dir existe:   {profile_dir.exists()}")
    if profile_dir.exists():
        locks = [f.name for f in profile_dir.iterdir() if "Singleton" in f.name]
        if locks:
            print(f"  Lock files presentes: {', '.join(locks)}")
        else:
            print("  Lock files: nenhum")


def start_and_test():
    """Start Chrome and wait for CDP, print progress and result."""
    print("Iniciando Chrome do Radar e aguardando CDP...")
    print()

    already = is_cdp_available()
    if already:
        v = _fetch_json_version()
        browser = (v or {}).get("Browser", "desconhecido")
        print(f"CDP JA ESTAVA ATIVO: {browser}")
        return True

    # Print the command first
    print_start_command()
    print()

    # Start Chrome
    print("Abrindo Chrome...")
    res = start_radar_chrome()
    if not res.get("ok"):
        print(f"FALHA ao abrir Chrome: {res.get('message')}")
        if res.get("stderr"):
            print(f"Stderr: {res['stderr'][:500]}")
        if res.get("chrome_process_exited_before_cdp_ready"):
            print("O processo Chrome morreu antes de expor a porta CDP.")
            print("Possiveis causas:")
            print("  - Chrome ja estava aberto e rejeitou a nova instancia")
            print("  - Flag --remote-debugging-port ignorada")
            print("  - Lock file stale no profile")
        return False

    print(f"Chrome iniciado (PID {res.get('pid')}). Aguardando CDP...")

    # Wait up to 30s
    for attempt in range(60):
        time.sleep(0.5)
        v = _fetch_json_version()
        if v:
            print(f"\nCDP RESPONDEU apos {attempt//2 + 1}s: {v.get('Browser', 'chrome')}")
            return True
        if attempt % 4 == 0:
            pid = res.get("pid")
            alive = False
            try:
                check = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                alive = str(pid) in check.stdout
            except Exception:
                pass
            if not alive:
                print(f"\nProcesso (PID {pid}) MORREU durante a espera!")
                # Try to find stderr
                try:
                    logs = list(Path(DEFAULT_PROFILE_DIR.resolve()).glob("radar_chrome_stderr_*.log"))
                    if logs:
                        logs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                        stderr = logs[0].read_text(errors="ignore")[:500]
                        if stderr:
                            print(f"Stderr: {stderr}")
                except Exception:
                    pass
                return False
            print(".", end="", flush=True)

    print("\nTimeout de 30s: CDP nao respondeu.")
    return False


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
        alive = True
        try:
            check = subprocess.run(
                ["tasklist", "/FI", f"PID eq {radar_proc['pid']}", "/NH"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            alive = str(radar_proc['pid']) in check.stdout
        except Exception:
            pass
        print(f"    Encontrado: PID {radar_proc['pid']} (fonte: {radar_proc['source']})")
        print(f"    Processo vivo: {'SIM' if alive else 'NAO (stale)'}")
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
    ud = Path(DEFAULT_PROFILE_DIR.resolve())
    legacy_ud = _BASE / "data" / _LEGACY_PROFILE_NAME
    print(f"\n[8] User data dir (oficial): {ud}")
    if ud.exists():
        items = list(ud.iterdir())
        print(f"    Existe: sim ({len(items)} itens)")
        locks = [f.name for f in items if "Singleton" in f.name]
        if locks:
            print(f"    Lock files: {', '.join(locks)}")
        else:
            print("    Lock files: nenhum")
    else:
        print("    Existe: nao (sera criado ao iniciar Chrome)")

    # Legacy profile check
    if legacy_ud.exists():
        legacy_items = list(legacy_ud.iterdir())
        print(f"\n    [!] Perfil legado {_LEGACY_PROFILE_NAME} tambem existe ({len(legacy_items)} itens)")
        print(f"    Caminho: {legacy_ud}")
        print("    ATENCAO: existem DOIS perfis de Radar. O oficial e data/chrome_radar_profile.")
        # Check which profile is in use by running processes
        procs = _get_wmi_processes()
        for p in procs:
            cmd = p.get("command_line", "") or ""
            if _OFFICIAL_PROFILE_NAME in cmd:
                print(f"    Perfil oficial em uso por PID {p['pid']}")
            elif _LEGACY_PROFILE_NAME in cmd:
                print(f"    Perfil legado em uso por PID {p['pid']}")
    else:
        print(f"\n    Perfil legado {_LEGACY_PROFILE_NAME}: nao existe")

    # 9. Command line
    print("\n[9] Comando que seria usado para abrir Chrome CDP:")
    print_start_command()

    # 10. Recommendation
    print("\n" + "=" * 60)
    print("  RECOMENDACAO")
    print("=" * 60)

    if cdp_ok:
        print("  CDP OK - O Radar deve funcionar normalmente.")
        print("  Se ainda houver erro na etapa chrome, verifique se o Chrome nao travou.")
    elif port_open:
        print("  Porta 9222 ocupada mas CDP nao responde.")
        print("  Execute: python -c \"from shopee_core.radar_cdp_service import kill_managed_radar_chrome; kill_managed_radar_chrome()\"")
        print("  Depois tente novamente.")
    elif not chrome_path:
        print("  Chrome/Edge nao encontrado. Instale o Chrome ou Edge.")
    else:
        print("  Chrome encontrado mas nao esta rodando com CDP.")
        print("  O Radar deve abri-lo automaticamente ao clicar em 'Rodar Radar Automatico'.")
        print("  Para testar manualmente:")
        print(f"    python scripts/radar_cdp_doctor.py --start")
        print()
        print("  Se falhar, diagnostique com:")
        print(f"    tasklist /FI \"IMAGENAME eq chrome.exe\"")
        print(f"    netstat -ano | findstr :9222")

    print()


if __name__ == "__main__":
    if "--print-start-command" in sys.argv:
        print_start_command()
    elif "--start" in sys.argv:
        ok = start_and_test()
        sys.exit(0 if ok else 1)
    else:
        doctor()
