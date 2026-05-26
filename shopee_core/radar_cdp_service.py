import os
import sys
import json
import time
import subprocess
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen, Request

if getattr(sys, "frozen", False):
    _BASE = Path(sys.executable).parent
else:
    _BASE = Path(__file__).resolve().parent.parent

DEFAULT_CDP_URL = "http://127.0.0.1:9222"
DEFAULT_PROFILE_DIR = _BASE / "data" / "radar_chrome_profile"
PID_FILE = _BASE / "data" / "radar_chrome.pid"
CDP_PORT = 9222


def is_cdp_available(cdp_url: str = DEFAULT_CDP_URL, timeout: float = 2.0) -> bool:
    """Return True when a Chrome CDP endpoint is reachable."""
    version_url = cdp_url.rstrip("/") + "/json/version"
    try:
        req = Request(version_url, method="GET")
        with urlopen(req, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if status < 200 or status >= 300:
                return False
            try:
                payload = json.loads(response.read().decode("utf-8", errors="ignore"))
            except Exception:
                return True
            return bool(payload.get("Browser") or payload.get("webSocketDebuggerUrl"))
    except (OSError, URLError, TimeoutError, ValueError):
        return False


def _fetch_json_version(cdp_url: str = DEFAULT_CDP_URL, timeout: float = 3.0) -> dict | None:
    """Fetch /json/version from CDP endpoint, return parsed dict or None."""
    version_url = cdp_url.rstrip("/") + "/json/version"
    try:
        req = Request(version_url, method="GET")
        with urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="ignore")
            return json.loads(raw)
    except Exception:
        return None


def find_chrome_executable() -> str | None:
    """Procurar Chrome ou Edge nos caminhos padrão do Windows."""
    if sys.platform != "win32":
        return None

    prog_files = os.getenv("ProgramFiles")
    prog_files_x86 = os.getenv("ProgramFiles(x86)")
    local_app_data = os.getenv("LocalAppData")

    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]

    if prog_files:
        paths.append(str(Path(prog_files) / "Google/Chrome/Application/chrome.exe"))
        paths.append(str(Path(prog_files) / "Microsoft/Edge/Application/msedge.exe"))
    if prog_files_x86:
        paths.append(str(Path(prog_files_x86) / "Google/Chrome/Application/chrome.exe"))
        paths.append(str(Path(prog_files_x86) / "Microsoft/Edge/Application/msedge.exe"))
    if local_app_data:
        paths.append(str(Path(local_app_data) / "Google/Chrome/Application/chrome.exe"))

    seen = set()
    for p in paths:
        normal = str(Path(p).resolve())
        if normal in seen:
            continue
        seen.add(normal)
        if Path(normal).exists():
            return normal

    return None


# ── PID file management ───────────────────────────────────────────────────


def _read_radar_pid() -> int | None:
    """Read saved PID from pid file."""
    if not PID_FILE.exists():
        return None
    try:
        raw = PID_FILE.read_text().strip()
        if not raw:
            return None
        pid = int(raw)
        return pid if pid > 0 else None
    except (ValueError, OSError):
        return None


def _write_radar_pid(pid: int):
    """Write PID to pid file."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid))


def _clear_radar_pid():
    """Remove the pid file."""
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except OSError:
        pass


def _is_radar_managed_process(proc) -> bool:
    """Check if a process is a Radar-managed Chrome (right flags)."""
    try:
        cmdline = proc.CommandLine or ""
    except Exception:
        return False
    return "remote-debugging-port=9222" in cmdline and "radar_chrome_profile" in cmdline


def _is_process_alive(pid: int) -> bool:
    """Check if a process with given PID is alive."""
    try:
        proc = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return str(pid) in proc.stdout
    except Exception:
        return False


def _get_processes_with_flag(flag: str = "remote-debugging-port=9222") -> list[dict]:
    """Get all Chrome/Edge processes with given flag in command line."""
    result = []
    try:
        import ctypes
        from ctypes import wintypes

        psapi = ctypes.windll.psapi
        kernel32 = ctypes.windll.kernel32

        EnumProcesses = psapi.EnumProcesses
        GetModuleBaseNameW = psapi.GetModuleBaseNameW
        OpenProcess = kernel32.OpenProcess
        CloseHandle = kernel32.CloseHandle
        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_VM_READ = 0x0010

        pids_arr = (wintypes.DWORD * 4096)()
        needed = wintypes.DWORD()
        if not EnumProcesses(ctypes.byref(pids_arr), ctypes.sizeof(pids_arr), ctypes.byref(needed)):
            return result
        count = needed.value // ctypes.sizeof(wintypes.DWORD)

        for i in range(count):
            pid = pids_arr[i]
            if pid == 0:
                continue
            h_process = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
            if h_process:
                try:
                    exe_name = ctypes.create_unicode_buffer(260)
                    size = wintypes.DWORD(260)
                    if GetModuleBaseNameW(h_process, None, exe_name, size):
                        name = exe_name.value.lower()
                        if name in ("chrome.exe", "msedge.exe"):
                            result.append({"pid": pid, "name": name})
                finally:
                    CloseHandle(h_process)
        return result
    except Exception:
        return result


def _get_wmi_processes() -> list:
    """Get Chrome/Edge processes via WMI with command line."""
    result = []
    try:
        import subprocess
        ps = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"name='chrome.exe' OR name='msedge.exe'\" | "
             "Select-Object ProcessId, Name, CommandLine | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if ps.returncode == 0 and ps.stdout.strip():
            data = json.loads(ps.stdout)
            if isinstance(data, dict):
                data = [data]
            for entry in data:
                result.append({
                    "pid": entry.get("ProcessId"),
                    "name": entry.get("Name", "").lower(),
                    "command_line": entry.get("CommandLine", "") or "",
                })
    except Exception:
        pass
    return result


def _find_radar_chrome_process() -> dict | None:
    """Find a Radar-managed Chrome process by pid file or command line."""
    pid = _read_radar_pid()
    if pid and _is_process_alive(pid):
        return {"pid": pid, "source": "pid_file"}

    procs = _get_wmi_processes()
    for p in procs:
        if _is_radar_managed_process(p):
            return {"pid": p["pid"], "source": "wmi", "command_line": p.get("command_line", "")}

    return None


def _is_port_open(port: int = CDP_PORT, timeout: float = 1.0) -> bool:
    """Check if something is listening on the given port."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False
    finally:
        s.close()


# ── Chrome process management ──────────────────────────────────────────────


def kill_managed_radar_chrome() -> dict:
    """Kill only the Radar-managed Chrome process (identified by pid file or flags).

    Never kills a Chrome that isn't flagged as Radar-managed.
    """
    results = []
    proc = _find_radar_chrome_process()
    if not proc:
        _clear_radar_pid()
        return {"ok": True, "killed": False, "message": "Nenhum processo gerenciado do Radar encontrado.", "pids": []}

    pid = proc["pid"]
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        results.append(pid)
    except Exception:
        pass

    # Also kill any orphan with radar flags
    procs = _get_wmi_processes()
    for p in procs:
        if _is_radar_managed_process(p) and p["pid"] not in results:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(p["pid"]), "/F"],
                    capture_output=True, timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                results.append(p["pid"])
            except Exception:
                pass

    _clear_radar_pid()
    label = "Chrome do Radar encerrado" if len(results) <= 1 else "Chromens do Radar encerrados"
    return {"ok": True, "killed": bool(results), "message": f"{label}: PID(s) {results}.", "pids": results}


def start_radar_chrome(cdp_port: int = CDP_PORT, user_data_dir: Path | None = None) -> dict:
    """Inicia o navegador Chrome ou Edge em segundo plano configurado para CDP.

    Returns detailed result with PID on success.
    """
    cdp_url = f"http://127.0.0.1:{cdp_port}"
    if is_cdp_available(cdp_url):
        return {
            "ok": True,
            "started": False,
            "already_running": True,
            "message": "Navegador com suporte a CDP já está em execução.",
            "cdp_url": cdp_url,
        }

    chrome_path = find_chrome_executable()
    if not chrome_path:
        return {
            "ok": False,
            "started": False,
            "already_running": False,
            "environment_error": True,
            "message": "Executável do Chrome ou Edge não foi encontrado em caminhos comuns do sistema.",
            "chrome_found": False,
        }

    profile_dir = user_data_dir or DEFAULT_PROFILE_DIR
    profile_dir = profile_dir.resolve()  # ensure absolute
    profile_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        chrome_path,
        f"--remote-debugging-port={cdp_port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-popup-blocking",
        "https://www.mercadolivre.com.br/",
    ]

    # Set environment to prevent Chrome from trying to reuse existing instance
    env = os.environ.copy()
    env["CHROME_CRASH_HANDLER_PIPE_COUNT"] = "0"

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )

        pid = proc.pid
        _write_radar_pid(pid)

        return {
            "ok": True,
            "started": True,
            "already_running": False,
            "message": f"Navegador iniciado com sucesso (PID {pid}).",
            "pid": pid,
            "chrome_path": chrome_path,
            "user_data_dir": str(profile_dir),
            "cdp_url": cdp_url,
        }
    except Exception as e:
        return {
            "ok": False,
            "started": False,
            "already_running": False,
            "environment_error": True,
            "message": f"Erro ao disparar processo do navegador: {e}",
            "chrome_path": chrome_path,
        }


def ensure_radar_chrome_ready(cdp_url: str = DEFAULT_CDP_URL, progress_callback=None) -> dict:
    """Garante que o Chrome CDP esteja aberto.

    Tenta reutilizar CDP existente. Se não disponível:
    - Detecta porta ocupada
    - Limpa processo Radar travado
    - Abre novo Chrome
    - Aguarda até 45 segundos com polling a cada 0.5s
    - Retorna diagnóstico detalhado em caso de falha
    """
    import re
    port_match = re.search(r":(\d+)", cdp_url)
    port = int(port_match.group(1)) if port_match else CDP_PORT

    def _cb(stage: str, message: str):
        if progress_callback:
            try:
                progress_callback({"stage": stage, "message": message})
            except Exception:
                pass

    diagnostics = {
        "cdp_url": cdp_url,
        "port": port,
        "chrome_executable": find_chrome_executable(),
        "user_data_dir": str(DEFAULT_PROFILE_DIR.resolve()),
        "pid_file": str(PID_FILE),
        "pid_file_exists": PID_FILE.exists(),
        "radar_process": None,
        "port_open": False,
        "cdp_responded": False,
        "json_version": None,
        "process_started": False,
        "pid": None,
        "port_responded": False,
        "json_version_error": None,
    }

    # 1. Check if CDP already available
    _cb("chrome_check", "Verificando se CDP ja esta disponivel...")
    version_data = _fetch_json_version(cdp_url)
    if version_data:
        diagnostics["cdp_responded"] = True
        diagnostics["json_version"] = version_data
        diagnostics["port_open"] = True
        _cb("done", f"CDP ativo: {version_data.get('Browser', 'chrome')}")
        return {
            "ok": True,
            "started": False,
            "already_running": True,
            "cdp_url": cdp_url,
            "message": f"Chrome do Radar já estava ativo ({version_data.get('Browser', 'chrome')}).",
            "diagnostics": diagnostics,
        }

    # 2. Check if port is open but not responding as CDP
    _cb("chrome_occupied", "Verificando se porta esta ocupada...")
    diagnostics["port_open"] = _is_port_open(port)
    if diagnostics["port_open"]:
        port_procs = [p for p in _get_wmi_processes() if p.get("name") in ("chrome.exe", "msedge.exe")]
        occupant = None
        for p in port_procs:
            cmdline = (p.get("command_line") or "").lower()
            if "remote-debugging-port" in cmdline:
                occupant = p
                break
        if occupant:
            diagnostics["radar_process"] = occupant
            _cb("error", f"Porta ocupada por PID {occupant['pid']} mas CDP nao responde.")
            return {
                "ok": False,
                "environment_error": True,
                "message": (
                    f"Porta {port} está ocupada por {'Edge' if 'msedge' in occupant.get('name','') else 'Chrome'} "
                    f"(PID {occupant['pid']}) que não respondeu como CDP. "
                    "Tente reiniciar o Chrome do Radar."
                ),
                "diagnostics": diagnostics,
            }

    # 3. Check for managed radar process that might be stale
    _cb("chrome_kill_stale", "Verificando processos gerenciados do Radar...")
    radar_proc = _find_radar_chrome_process()
    if radar_proc:
        diagnostics["radar_process"] = radar_proc
        _cb("chrome_kill_stale", f"Limpando Chrome travado (PID {radar_proc['pid']})...")
        kill_managed_radar_chrome()

    # 4. Start Chrome
    _cb("chrome_start", "Abrindo Chrome do Radar...")
    start_res = start_radar_chrome(cdp_port=port)
    diagnostics["process_started"] = start_res.get("started", False)
    diagnostics["pid"] = start_res.get("pid")

    if not start_res.get("ok"):
        diag = {**diagnostics}
        _cb("error", f"Falha ao abrir Chrome: {start_res['message']}")
        return {
            "ok": False,
            "environment_error": True,
            "message": f"Não foi possível abrir o Chrome do Radar automaticamente: {start_res['message']}",
            "diagnostics": diag,
        }

    # 5. Wait up to 45s polling every 0.5s
    _cb("chrome_wait", "Aguardando Chrome responder na porta 9222...")
    if not start_res.get("already_running"):
        for attempt in range(90):  # 90 * 0.5 = 45s
            time.sleep(0.5)
            version_data = _fetch_json_version(cdp_url)
            if version_data:
                diagnostics["cdp_responded"] = True
                diagnostics["json_version"] = version_data
                diagnostics["port_open"] = True
                _cb("chrome_validate", f"CDP validado: {version_data.get('Browser', 'chrome')}")
                return {
                    "ok": True,
                    "started": True,
                    "already_running": False,
                    "cdp_url": cdp_url,
                    "message": f"Chrome do Radar foi iniciado com sucesso ({version_data.get('Browser', 'chrome')}).",
                    "pid": start_res.get("pid"),
                    "diagnostics": diagnostics,
                }

    # 6. Timeout - build detailed diagnostic
    diagnostics["port_open"] = _is_port_open(port)
    version_error = None
    try:
        version_url = cdp_url.rstrip("/") + "/json/version"
        req = Request(version_url, method="GET")
        with urlopen(req, timeout=3) as resp:
            version_error = f"Resposta HTTP {resp.status}"
    except Exception as e:
        version_error = str(e)
    diagnostics["json_version_error"] = version_error

    _cb("error", f"Timeout: Chrome nao respondeu em 45s ({version_error})")
    return {
        "ok": False,
        "environment_error": True,
        "message": (
            f"O Chrome do Radar foi disparado (PID {start_res.get('pid')}), "
            f"mas não respondeu na porta {port} no tempo limite de 45s. "
            f"Erro ao acessar /json/version: {version_error}. "
            "Verifique se há outras instâncias travadas ou se o Chrome abriu sem CDP."
        ),
        "diagnostics": diagnostics,
    }
