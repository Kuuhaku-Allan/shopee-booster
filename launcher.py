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
import tkinter as tk
from tkinter import messagebox

import pystray
from PIL import Image, ImageDraw
import webview

from updater import verificar_atualizacao, VERSAO_ATUAL

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

    cmd = [
        sys.executable, "-m", "streamlit", "run", APP_PY,
        "--server.port", str(PORTA),
        "--server.headless", "true",
        "--server.runOnSave", "false",
        "--browser.gatherUsageStats", "false",
        "--theme.base", "light",
    ]
    streamlit_proc = subprocess.Popen(
        cmd,
        cwd=BASE_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def encerrar_streamlit():
    global streamlit_proc
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
    Fechar a janela NÃO encerra o app — ele continua na bandeja.
    """
    global janela_webview

    def _run():
        global janela_webview
        janela_webview = webview.create_window(
            TITULO_JANELA,
            URL_APP,
            width=1280,
            height=800,
            resizable=True,
            min_size=(900, 600),
        )
        # on_closed: apenas esconde, não mata o processo
        # janela_webview.events.closed += lambda: None 
        webview.start(debug=False)
        janela_webview = None

    t = threading.Thread(target=_run, daemon=True)
    t.start()


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
    root = tk.Tk()
    root.withdraw()
    if resultado["disponivel"]:
        resposta = messagebox.askyesno(
            "Atualização disponível! 🚀",
            f"Nova versão: {resultado['versao_nova']}\n"
            f"Versão atual: {VERSAO_ATUAL}\n\n"
            f"Deseja atualizar agora?\n"
            f"O app será reiniciado automaticamente.",
        )
        if resposta:
            from updater import baixar_e_aplicar_atualizacao
            root.destroy()
            baixar_e_aplicar_atualizacao(resultado["url_download"])
    else:
        messagebox.showinfo(
            "Shopee Booster",
            f"✅ Você já está na versão mais recente ({VERSAO_ATUAL}).",
        )
    root.destroy()


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
    if not aguardar_streamlit(timeout=30):
        tk.Tk().withdraw()
        messagebox.showerror(
            "Shopee Booster",
            "❌ O servidor não iniciou. Verifique o .env e tente novamente."
        )
        sys.exit(1)

    # 4. Abrir janela nativa na inicialização
    abrir_janela_nativa()

    # 5. Iniciar bandeja (bloqueia até "Sair")
    iniciar_tray()


if __name__ == "__main__":
    main()
