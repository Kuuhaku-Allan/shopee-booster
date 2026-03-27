"""
launcher.py — Shopee Booster
Responsabilidades:
  - Iniciar o Streamlit em segundo plano
  - Ícone na bandeja do sistema (system tray)
  - Janela nativa via pywebview (modo "instalado")
  - Verificar atualizações no GitHub ao iniciar
"""

import subprocess
import sys
import os
import time
import threading
import webbrowser
import socket
import ctypes

import pystray
import webview
from PIL import Image, ImageDraw

from updater import verificar_atualizacao, VERSAO_ATUAL

# 🔥 MEDIDA DE SEGURANÇA: Forçar apenas CPU para evitar travamentos silenciosos da IA
# No Windows/PyInstaller, o onnxruntime trava tentando buscar drivers de GPU (CUDA/DirectML)
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["ORT_LOGGING_LEVEL"] = "3" # Suprime logs fúteis
os.environ["ONNXRUNTIME_PROVIDERS"] = "CPUExecutionProvider" # Força o motor local já no launcher

# ── Configurações ─────────────────────────────────────────────
PORTA = 8501
URL_APP = f"http://localhost:{PORTA}"
TITULO_JANELA = f"Shopee Booster v{VERSAO_ATUAL}"

# Caminho do app.py — funciona tanto em dev quanto no .exe
if getattr(sys, "frozen", False):
    # Rodando como .exe (PyInstaller)
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

APP_PY = os.path.join(BASE_DIR, "app.py")

# Aponta o Playwright para os browsers embutidos no .exe
if getattr(sys, "frozen", False):
    pw_browsers = os.path.join(BASE_DIR, "pw-browsers")
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = pw_browsers

# ── Estado global ─────────────────────────────────────────────
streamlit_proc = None
janela_webview = None
tray_icon = None


# ── Utilidades ────────────────────────────────────────────────
def porta_em_uso(porta: int) -> bool:
    """Verifica se o Streamlit já está rodando na porta."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", porta)) == 0


def aguardar_streamlit(timeout: int = 30) -> bool:
    """Aguarda o Streamlit subir na porta antes de abrir a janela."""
    inicio = time.time()
    while time.time() - inicio < timeout:
        if porta_em_uso(PORTA):
            return True
        time.sleep(0.5)
    return False


# ── Streamlit ─────────────────────────────────────────────────
def iniciar_streamlit():
    """Inicia o processo do Streamlit em background."""
    global streamlit_proc
    if porta_em_uso(PORTA):
        return  # Já está rodando

    if getattr(sys, "frozen", False):
        cmd = [
            sys.executable, "run", APP_PY,
            "--server.port", str(PORTA),
            "--server.headless", "true",
            "--server.runOnSave", "false",
            "--server.enableCORS", "false",
            "--server.enableXsrfProtection", "false",
            "--browser.gatherUsageStats", "false",
            "--theme.base", "light",
            "--global.developmentMode", "false",
        ]
    else:
        cmd = [
            sys.executable, "-m", "streamlit", "run", APP_PY,
            "--server.port", str(PORTA),
            "--server.headless", "true",
            "--server.runOnSave", "false",
            "--server.enableCORS", "false",
            "--server.enableXsrfProtection", "false",
            "--browser.gatherUsageStats", "false",
            "--theme.base", "light",
            "--global.developmentMode", "false",
        ]
    global log_file
    log_file = open("streamlit_log.txt", "w", encoding="utf-8")
    
    streamlit_proc = subprocess.Popen(
        cmd,
        cwd=BASE_DIR,
        stdout=log_file,
        stderr=log_file,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )

def encerrar_streamlit():
    global streamlit_proc, log_file
    if streamlit_proc and streamlit_proc.poll() is None:
        streamlit_proc.terminate()
        try:
            streamlit_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            streamlit_proc.kill()
    streamlit_proc = None


# ── Janela nativa (pywebview) ─────────────────────────────────
def abrir_janela_nativa():
    """
    Abre o Streamlit numa janela nativa (modo 'instalado').
    DEVE rodar na main thread no Windows para funcionar.
    Fechar a janela NÃO encerra o app — ele continua na bandeja.
    """
    global janela_webview
    
    # Downloads vão automaticamente para a pasta Downloads do usuário
    downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    
    janela_webview = webview.create_window(
        TITULO_JANELA,
        URL_APP,
        width=1280,
        height=800,
        resizable=True,
        min_size=(900, 600),
    )
    webview.start(debug=False, download_dir=downloads_dir)
    janela_webview = None


def abrir_no_navegador():
    """Abre no navegador padrão (modo 'browser')."""
    webbrowser.open(URL_APP)


# ── Ícone da bandeja ──────────────────────────────────────────
def criar_icone_imagem() -> Image.Image:
    """Carrega o ícone da pasta assets ou gera um simples se não existir."""
    icon_path = os.path.join(BASE_DIR, "assets", "icon.ico")
    if os.path.exists(icon_path):
        return Image.open(icon_path)
    
    # Fallback
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=(238, 77, 45, 255))
    return img


def acao_abrir_janela(icon, item):
    if not porta_em_uso(PORTA):
        iniciar_streamlit()
        aguardar_streamlit()
    abrir_janela_nativa()


def acao_abrir_navegador(icon, item):
    if not porta_em_uso(PORTA):
        iniciar_streamlit()
        aguardar_streamlit()
    abrir_no_navegador()


def acao_verificar_atualizacao(icon, item):
    """Checa GitHub e mostra diálogo se houver update."""
    threading.Thread(target=_checar_e_notificar, daemon=True).start()


def _checar_e_notificar():
    resultado = verificar_atualizacao()
    if resultado["disponivel"]:
        msg = (f"Nova versão: {resultado['versao_nova']}\n"
               f"Versão atual: {VERSAO_ATUAL}\n\n"
               f"Deseja atualizar agora?\n"
               f"O app será reiniciado automaticamente.")
        res = ctypes.windll.user32.MessageBoxW(0, msg, "Atualização disponível! 🚀", 4 | 64)
        if res == 6: # IDYES
            from updater import baixar_e_aplicar_atualizacao
            baixar_e_aplicar_atualizacao(resultado["url_download"])
    else:
        ctypes.windll.user32.MessageBoxW(0, f"Você já está na versão mais recente ({VERSAO_ATUAL}).", "Shopee Booster", 0 | 64)


def acao_sair(icon, item):
    icon.stop()
    encerrar_streamlit()
    os._exit(0)


def iniciar_tray():
    global tray_icon
    icone_img = criar_icone_imagem()
    menu = pystray.Menu(
        pystray.MenuItem("📦 Abrir Janela",      acao_abrir_janela, default=True),
        pystray.MenuItem("🌐 Abrir no Navegador", acao_abrir_navegador),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("🔄 Verificar Atualizações", acao_verificar_atualizacao),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("❌ Sair",               acao_sair),
    )
    tray_icon = pystray.Icon(
        "ShopeeBooster",
        icone_img,
        f"Shopee Booster v{VERSAO_ATUAL}",
        menu,
    )
    tray_icon.run()


# ── Entrada principal ─────────────────────────────────────────
def main():
    # 1. Iniciar Streamlit em background
    iniciar_streamlit()

    # 2. Verificar atualização silenciosamente em thread separada
    threading.Thread(target=_checar_e_notificar, daemon=True).start()

    # 3. Aguardar Streamlit subir
    if not aguardar_streamlit(timeout=60):
        ctypes.windll.user32.MessageBoxW(0, "O servidor não iniciou no tempo limite (60s). Verifique os processos.\nO aplicativo será encerrado.", "Shopee Booster - Erro", 0 | 16)
        sys.exit(1)

    # 4. Iniciar bandeja em background
    threading.Thread(target=iniciar_tray, daemon=True).start()

    # 5. Abrir janela nativa principal (bloqueante)
    abrir_janela_nativa()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    
    # Interceptar a chamada "run" para lançar o streamlit embutido
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        try:
            import streamlit.web.cli as stcli
        except ImportError:
            import streamlit.cli as stcli
        sys.exit(stcli.main())
    
    # 🚀 NOVO: Handler para rodar scripts em background (Playwright)
    # Isso evita que o ShopeeBooster.exe abra uma nova janela ao tentar rodar um script
    elif len(sys.argv) > 1 and sys.argv[1] == "runscript":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        try:
            script_path = sys.argv[2]
            with open(script_path, "r", encoding="utf-8") as f:
                exec(compile(f.read(), script_path, "exec"))
            sys.exit(0)
        except Exception as e:
            print(f"Erro ao rodar script: {e}", file=sys.stderr)
            sys.exit(1)
        
    main()
