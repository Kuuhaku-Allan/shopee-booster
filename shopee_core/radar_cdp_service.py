import os
import sys
import json
import time
import subprocess
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

if getattr(sys, "frozen", False):
    _BASE = Path(sys.executable).parent
else:
    _BASE = Path(__file__).resolve().parent.parent

DEFAULT_CDP_URL = "http://127.0.0.1:9222"
DEFAULT_PROFILE_DIR = _BASE / "data" / "radar_chrome_profile"

def is_cdp_available(cdp_url: str = DEFAULT_CDP_URL, timeout: float = 2.0) -> bool:
    """Return True when a Chrome CDP endpoint is reachable."""
    version_url = cdp_url.rstrip("/") + "/json/version"
    try:
        with urlopen(version_url, timeout=timeout) as response:
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

def find_chrome_executable() -> str | None:
    """Procurar Chrome ou Edge nos caminhos padrão do Windows."""
    if sys.platform != "win32":
        return None
        
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    ]
    
    prog_files = os.getenv("ProgramFiles")
    prog_files_x86 = os.getenv("ProgramFiles(x86)")
    local_app_data = os.getenv("LocalAppData")
    
    if prog_files:
        paths.append(str(Path(prog_files) / "Google/Chrome/Application/chrome.exe"))
        paths.append(str(Path(prog_files) / "Microsoft/Edge/Application/msedge.exe"))
    if prog_files_x86:
        paths.append(str(Path(prog_files_x86) / "Google/Chrome/Application/chrome.exe"))
        paths.append(str(Path(prog_files_x86) / "Microsoft/Edge/Application/msedge.exe"))
    if local_app_data:
        paths.append(str(Path(local_app_data) / "Google/Chrome/Application/chrome.exe"))
        
    for p in paths:
        if Path(p).exists():
            return p
            
    return None

def start_radar_chrome(cdp_port: int = 9222, user_data_dir: Path | None = None) -> dict:
    """Inicia o navegador Chrome ou Edge em segundo plano configurado para CDP."""
    cdp_url = f"http://127.0.0.1:{cdp_port}"
    if is_cdp_available(cdp_url):
        return {
            "ok": True,
            "started": False,
            "already_running": True,
            "message": "Navegador com suporte a CDP já está em execução."
        }
        
    chrome_path = find_chrome_executable()
    if not chrome_path:
        return {
            "ok": False,
            "started": False,
            "already_running": False,
            "message": "Executável do Chrome ou Edge não foi encontrado em caminhos comuns do sistema."
        }
        
    profile_dir = user_data_dir or DEFAULT_PROFILE_DIR
    profile_dir.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        chrome_path,
        f"--remote-debugging-port={cdp_port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check"
    ]
    
    try:
        creationflags = 0
        if sys.platform == "win32":
            # DETACHED_PROCESS (0x00000008) garante que o processo viva de forma independente
            creationflags = 0x00000008
            
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags
        )
        return {
            "ok": True,
            "started": True,
            "already_running": False,
            "message": "Navegador iniciado com sucesso."
        }
    except Exception as e:
        return {
            "ok": False,
            "started": False,
            "already_running": False,
            "message": f"Erro ao disparar processo do navegador: {e}"
        }

def ensure_radar_chrome_ready(cdp_url: str = DEFAULT_CDP_URL) -> dict:
    """Garante que o Chrome CDP esteja aberto. Tenta abri-lo se não estiver, esperando até 15 segundos."""
    if is_cdp_available(cdp_url):
        return {
            "ok": True,
            "started": False,
            "already_running": True,
            "cdp_url": cdp_url,
            "message": "Chrome do Radar já estava ativo."
        }
        
    import re
    port_match = re.search(r":(\d+)", cdp_url)
    port = int(port_match.group(1)) if port_match else 9222
    
    start_res = start_radar_chrome(cdp_port=port)
    if not start_res["ok"]:
        return {
            "ok": False,
            "environment_error": True,
            "message": f"Não foi possível abrir o Chrome do Radar automaticamente: {start_res['message']}"
        }
        
    for _ in range(30):
        time.sleep(0.5)
        if is_cdp_available(cdp_url):
            return {
                "ok": True,
                "started": True,
                "already_running": False,
                "cdp_url": cdp_url,
                "message": "Chrome do Radar foi iniciado com sucesso."
            }
            
    return {
        "ok": False,
        "environment_error": True,
        "message": f"O Chrome do Radar foi disparado, mas não respondeu na porta {port} no tempo limite de 15s. Verifique se há outras instâncias travadas."
    }
