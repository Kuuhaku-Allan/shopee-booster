import os
import sys
import json
import time
import subprocess
import tempfile
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
_CREATE_NO_WINDOW = 0x08000000


def is_cdp_available(cdp_url: str = DEFAULT_CDP_URL, timeout: float = 2.0) -> bool:
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
    version_url = cdp_url.rstrip("/") + "/json/version"
    try:
        req = Request(version_url, method="GET")
        with urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="ignore")
            return json.loads(raw)
    except Exception:
        return None


# ── Chrome/Edge discovery ─────────────────────────────────────────────────


def find_chrome_executable() -> str | None:
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
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid))


def _clear_radar_pid():
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except OSError:
        pass


def _is_radar_managed_process(proc) -> bool:
    try:
        cmdline = proc.CommandLine or ""
    except Exception:
        return False
    return "remote-debugging-port=9222" in cmdline and "radar_chrome_profile" in cmdline


def _is_process_alive(pid: int) -> bool:
    try:
        proc = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        )
        return str(pid) in proc.stdout
    except Exception:
        return False


def _get_wmi_processes() -> list:
    result = []
    try:
        ps = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"name='chrome.exe' OR name='msedge.exe'\" | "
             "Select-Object ProcessId, Name, CommandLine | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=15,
            creationflags=_CREATE_NO_WINDOW,
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
    pid = _read_radar_pid()
    if pid and _is_process_alive(pid):
        return {"pid": pid, "source": "pid_file"}
    procs = _get_wmi_processes()
    for p in procs:
        if _is_radar_managed_process(p):
            return {"pid": p["pid"], "source": "wmi", "command_line": p.get("command_line", "")}
    return None


def _is_port_open(port: int = CDP_PORT, timeout: float = 1.0) -> bool:
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


# ── Profile lock cleanup ──────────────────────────────────────────────────


_LOCK_FILES = ["SingletonLock", "SingletonCookie", "SingletonSocket", "SingletonConnectedSocket"]


def _clean_stale_locks(profile_dir: Path):
    """Remove stale Chrome profile lock files if no CDP is active."""
    if is_cdp_available():
        return
    radar_proc = _find_radar_chrome_process()
    if radar_proc and _is_process_alive(radar_proc["pid"]):
        return
    for name in _LOCK_FILES:
        lock = profile_dir / name
        if lock.exists():
            try:
                lock.unlink()
            except OSError:
                pass


# ── PS1 script path ────────────────────────────────────────────────────────


_PS1_SCRIPT = _BASE / "deploy" / "local" / "start-radar-chrome.ps1"


# ── Chrome process management ──────────────────────────────────────────────


def kill_managed_radar_chrome() -> dict:
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
            creationflags=_CREATE_NO_WINDOW,
        )
        results.append(pid)
    except Exception:
        pass

    procs = _get_wmi_processes()
    for p in procs:
        if _is_radar_managed_process(p) and p["pid"] not in results:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(p["pid"]), "/F"],
                    capture_output=True, timeout=10,
                    creationflags=_CREATE_NO_WINDOW,
                )
                results.append(p["pid"])
            except Exception:
                pass

    _clear_radar_pid()
    label = "Chrome do Radar encerrado" if len(results) <= 1 else "Chromens do Radar encerrados"
    return {"ok": True, "killed": bool(results), "message": f"{label}: PID(s) {results}.", "pids": results}


def _build_chrome_cmd(chrome_path: str, cdp_port: int, profile_dir: Path) -> list[str]:
    """Build command line for Chrome, matching the PS1 script that works."""
    return [
        chrome_path,
        f"--remote-debugging-port={cdp_port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://www.mercadolivre.com.br/",
    ]


def start_radar_chrome(cdp_port: int = CDP_PORT, user_data_dir: Path | None = None) -> dict:
    """Inicia Chrome/Edge configurado para CDP, exatamente como o PS1 que funciona.

    Usa o mesmo script start-radar-chrome.ps1 do fluxo semiautomatico.
    Fallback: subprocess direto se o PS1 nao existir.
    """
    cdp_url = f"http://127.0.0.1:{cdp_port}"
    if is_cdp_available(cdp_url):
        return {
            "ok": True, "started": False, "already_running": True,
            "message": "Navegador com suporte a CDP já está em execução.",
            "cdp_url": cdp_url,
        }

    chrome_path = find_chrome_executable()
    if not chrome_path:
        return {
            "ok": False, "started": False, "already_running": False,
            "environment_error": True,
            "message": "Executável do Chrome ou Edge não foi encontrado em caminhos comuns do sistema.",
            "chrome_found": False,
        }

    profile_dir = user_data_dir or DEFAULT_PROFILE_DIR
    profile_dir = profile_dir.resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)

    # Clean stale locks
    _clean_stale_locks(profile_dir)

    # ── Method 1: PS1 script (preferred, same as semiautomatic) ──────
    if _PS1_SCRIPT.exists() and sys.platform == "win32":
        ps1_cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", str(_PS1_SCRIPT),
            "-Port", str(cdp_port),
            "-Marketplace", "mercadolivre",
        ]
        try:
            proc = subprocess.Popen(
                ps1_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            pid = proc.pid

            time.sleep(2.5)
            alive = _is_process_alive(pid)
            # The PS1 finishes quickly (Start-Process returns immediately),
            # so the powershell PID might not be alive. That's OK.
            # Check if Chrome CDP is now available instead.
            if is_cdp_available(cdp_url):
                _write_radar_pid(pid)
                return {
                    "ok": True, "started": True, "already_running": False,
                    "message": f"Chrome iniciado via PS1 (PID {pid}).",
                    "pid": pid, "chrome_path": chrome_path,
                    "user_data_dir": str(profile_dir), "cdp_url": cdp_url,
                }

            # If PS1 finished but CDP still not available, try direct method
        except Exception as e:
            pass  # fall through to direct method

    # ── Method 2: Direct subprocess (fallback) ───────────────────────
    cmd = _build_chrome_cmd(chrome_path, cdp_port, profile_dir)

    stderr_tmp = tempfile.NamedTemporaryFile(
        prefix="radar_chrome_stderr_", suffix=".log", delete=False, dir=profile_dir
    )
    stderr_path = stderr_tmp.name
    stderr_tmp.close()

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=open(stderr_path, "wb"),
        )
        pid = proc.pid

        time.sleep(2.5)
        alive = _is_process_alive(pid)
        stderr_output = ""
        try:
            with open(stderr_path, "r", errors="ignore") as f:
                stderr_output = f.read().strip()
        except Exception:
            pass

        if not alive:
            _clear_radar_pid()
            msg = f"Chrome (PID {pid}) foi iniciado mas morreu em 2.5s."
            if stderr_output:
                msg += f" Stderr: {stderr_output[:500]}"
            return {
                "ok": False, "started": True, "already_running": False,
                "environment_error": True,
                "message": msg,
                "pid": pid,
                "chrome_path": chrome_path,
                "user_data_dir": str(profile_dir),
                "stderr": stderr_output[:2000],
                "chrome_process_exited_before_cdp_ready": True,
            }

        _write_radar_pid(pid)
        return {
            "ok": True, "started": True, "already_running": False,
            "message": f"Navegador iniciado com sucesso (PID {pid}).",
            "pid": pid, "chrome_path": chrome_path,
            "user_data_dir": str(profile_dir), "cdp_url": cdp_url,
        }
    except Exception as e:
        return {
            "ok": False, "started": False, "already_running": False,
            "environment_error": True,
            "message": f"Erro ao disparar processo do navegador: {e}",
            "chrome_path": chrome_path,
        }


# ── Ensure Chrome ready (unified helper) ──────────────────────────────────


def ensure_radar_chrome_ready(cdp_url: str = DEFAULT_CDP_URL, progress_callback=None) -> dict:
    """Helper unificado: usado pelo Radar Semiautomatico e Automatico.

    1. Reutiliza CDP existente se disponivel
    2. Detecta porta ocupada sem CDP
    3. Encerra processo gerenciado stale
    4. Abre novo Chrome via start_radar_chrome()
    5. Aguarda ate 45s com polling
    6. Detecta processo que morreu antes do CDP
    7. Retorna diagnostico completo
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
        "cdp_url": cdp_url, "port": port,
        "chrome_executable": find_chrome_executable(),
        "user_data_dir": str(DEFAULT_PROFILE_DIR.resolve()),
        "pid_file": str(PID_FILE), "pid_file_exists": PID_FILE.exists(),
        "radar_process": None, "port_open": False,
        "cdp_responded": False, "json_version": None,
        "process_started": False, "pid": None,
        "json_version_error": None, "chrome_stderr": None,
        "chrome_process_exited_before_cdp_ready": False,
    }

    # 1. CDP ja disponivel?
    _cb("chrome_check", "Verificando se CDP ja esta disponivel...")
    version_data = _fetch_json_version(cdp_url)
    if version_data:
        diagnostics["cdp_responded"] = True
        diagnostics["json_version"] = version_data
        diagnostics["port_open"] = True
        _cb("done", f"CDP ativo: {version_data.get('Browser', 'chrome')}")
        return {
            "ok": True, "started": False, "already_running": True,
            "cdp_url": cdp_url,
            "message": f"Chrome do Radar ja estava ativo ({version_data.get('Browser', 'chrome')}).",
            "diagnostics": diagnostics,
        }

    # 2. Porta ocupada mas sem CDP?
    _cb("chrome_occupied", "Verificando se porta esta ocupada...")
    diagnostics["port_open"] = _is_port_open(port)
    if diagnostics["port_open"]:
        port_procs = [p for p in _get_wmi_processes() if p.get("name") in ("chrome.exe", "msedge.exe")]
        occupant = None
        for p in port_procs:
            if "remote-debugging-port" in (p.get("command_line") or "").lower():
                occupant = p
                break
        if occupant:
            diagnostics["radar_process"] = occupant
            _cb("error", f"Porta ocupada por PID {occupant['pid']} mas CDP nao responde.")
            return {
                "ok": False, "environment_error": True,
                "message": (
                    f"Porta {port} esta ocupada por {'Edge' if 'msedge' in occupant.get('name','') else 'Chrome'} "
                    f"(PID {occupant['pid']}) que nao respondeu como CDP. "
                    "Tente reiniciar o Chrome do Radar."
                ),
                "diagnostics": diagnostics,
            }

    # 3. Processo gerenciado stale?
    _cb("chrome_kill_stale", "Verificando processos gerenciados do Radar...")
    radar_proc = _find_radar_chrome_process()
    if radar_proc:
        diagnostics["radar_process"] = radar_proc
        _cb("chrome_kill_stale", f"Limpando Chrome travado (PID {radar_proc['pid']})...")
        kill_managed_radar_chrome()
        time.sleep(1.0)

    # 4. Abrir Chrome
    _cb("chrome_start", "Abrindo Chrome do Radar...")
    start_res = start_radar_chrome(cdp_port=port)
    diagnostics["process_started"] = start_res.get("started", False)
    diagnostics["pid"] = start_res.get("pid")
    diagnostics["chrome_stderr"] = start_res.get("stderr")
    if start_res.get("chrome_process_exited_before_cdp_ready"):
        diagnostics["chrome_process_exited_before_cdp_ready"] = True

    if not start_res.get("ok"):
        diag = {**diagnostics}
        _cb("error", f"Falha ao abrir Chrome: {start_res['message']}")
        return {
            "ok": False, "environment_error": True,
            "message": start_res["message"],
            "diagnostics": diag,
        }

    # 5. Aguardar CDP responder (ate 45s)
    _cb("chrome_wait", "Aguardando Chrome responder na porta 9222...")
    for attempt in range(90):
        time.sleep(0.5)

        # Check if process died during wait
        pid = start_res.get("pid")
        if pid and not _is_process_alive(pid):
            stderr_output = ""
            try:
                stderr_path = Path(str(DEFAULT_PROFILE_DIR.resolve())) / "radar_chrome_stderr_*.log"
                logs = list(Path(DEFAULT_PROFILE_DIR.resolve()).glob("radar_chrome_stderr_*.log"))
                if logs:
                    logs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                    stderr_output = logs[0].read_text(errors="ignore").strip()[:500]
            except Exception:
                pass

            diagnostics["chrome_process_exited_before_cdp_ready"] = True
            diagnostics["chrome_stderr"] = stderr_output
            _cb("error", f"Chrome morreu antes do CDP. Stderr: {stderr_output[:200]}")
            return {
                "ok": False, "environment_error": True,
                "message": (
                    f"Chrome (PID {pid}) morreu durante a espera do CDP ({45 - attempt//2}s restantes)."
                    + (f" Stderr: {stderr_output[:300]}" if stderr_output else "")
                ),
                "diagnostics": diagnostics,
            }

        version_data = _fetch_json_version(cdp_url)
        if version_data:
            diagnostics["cdp_responded"] = True
            diagnostics["json_version"] = version_data
            diagnostics["port_open"] = True
            _cb("chrome_validate", f"CDP validado: {version_data.get('Browser', 'chrome')}")
            return {
                "ok": True, "started": True, "already_running": False,
                "cdp_url": cdp_url,
                "message": f"Chrome do Radar foi iniciado com sucesso ({version_data.get('Browser', 'chrome')}).",
                "pid": start_res.get("pid"),
                "diagnostics": diagnostics,
            }

    # 6. Timeout
    diagnostics["port_open"] = _is_port_open(port)
    version_error = None
    try:
        with urlopen(Request(cdp_url.rstrip("/") + "/json/version", method="GET"), timeout=3) as resp:
            version_error = f"Resposta HTTP {resp.status}"
    except Exception as e:
        version_error = str(e)
    diagnostics["json_version_error"] = version_error

    _cb("error", f"Timeout: Chrome nao respondeu em 45s ({version_error})")
    return {
        "ok": False, "environment_error": True,
        "message": (
            f"O Chrome do Radar foi disparado (PID {start_res.get('pid')}), "
            f"mas nao respondeu na porta {port} no tempo limite de 45s. "
            f"Erro ao acessar /json/version: {version_error}. "
            "Verifique se ha outras instancias travadas ou se o Chrome abriu sem CDP."
        ),
        "diagnostics": diagnostics,
    }
