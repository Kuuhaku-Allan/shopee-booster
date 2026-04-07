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
import json
import subprocess

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
    webview.start(debug=False)
    janela_webview = None


def abrir_no_navegador():
    """Abre no navegador padrão (modo 'browser')."""
    webbrowser.open(URL_APP)


# ── Ícone da bandeja ──────────────────────────────────────────
def criar_icone_imagem() -> Image.Image:
    """Carrega o ícone da pasta assets (preferência PNG para transparência) ou gera um fallback."""
    png_path = os.path.join(BASE_DIR, "assets", "icon.png")
    ico_path = os.path.join(BASE_DIR, "assets", "icon.ico")
    
    if os.path.exists(png_path):
        # PNG com alpha é melhor para evitar a 'barra cinza' na bandeja do Windows
        return Image.open(png_path).convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
    elif os.path.exists(ico_path):
        return Image.open(ico_path).convert("RGBA")
    
    # Fallback caso nada seja encontrado
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
    """Encerra tudo de forma agressiva para não deixar processos zumbis."""
    icon.stop()
    encerrar_streamlit()
    # os._exit garante que o processo pai e todos os threads/subprocessos morram
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


# ══════════════════════════════════════════════════════════════════════════
# ── SENTINELA: Heartbeat em background ──────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════

SENTINELA_INTERVALO_SEGUNDOS = 4 * 3600  # 4 horas

def _fetch_competitors_headless(keyword: str) -> list:
    """Busca concorrentes via Playwright em modo 100% headless (sem Streamlit)."""
    kw_encoded = keyword.replace(" ", "+")
    script = f"""
import asyncio, json
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="pt-BR",
            viewport={{"width": 1280, "height": 800}},
            extra_http_headers={{"Accept-Language": "pt-BR,pt;q=0.9"}}
        )
        page = await context.new_page()
        competitors = []

        async def handle_response(response):
            if response.request.method == "OPTIONS": return
            url = response.url
            if ("search_items" in url or "v4/search" in url) and not competitors:
                try:
                    data = await response.json()
                    items = (
                        data.get("items") or
                        data.get("data", {{}}).get("items") or
                        []
                    )
                    for item in items[:10]:
                        b = item.get("item_basic", item)
                        if b.get("itemid"):
                            competitors.append({{
                                "item_id":    b.get("itemid"),
                                "shop_id":    b.get("shopid"),
                                "nome":       b.get("name", "")[:65],
                                "preco":      b.get("price_min", b.get("price", 0)) / 100000,
                                "avaliações": b.get("cmt_count", 0),
                                "curtidas":   b.get("liked_count", 0),
                                "estrelas":   round(b.get("item_rating", {{}}).get("rating_star", 0), 1),
                            }})
                except Exception:
                    pass

        page.on("response", handle_response)
        await page.goto(
            "https://shopee.com.br/search?keyword={kw_encoded}&sortBy=sales",
            wait_until="networkidle", timeout=45000
        )
        await asyncio.sleep(6)
        if not competitors:
            for _ in range(5):
                await page.mouse.wheel(0, 900)
                await asyncio.sleep(2)
            await asyncio.sleep(4)
        await browser.close()
        print(json.dumps(competitors))

asyncio.run(run())
"""
    # Usa runscript para evitar abrir janela
    try:
        if getattr(sys, "frozen", False):
            import tempfile
            import io as _io
            sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace") if hasattr(sys.stdout, "buffer") else sys.stdout
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
                f.write(script)
                script_path = f.name
            try:
                result = subprocess.run(
                    [sys.executable, "runscript", script_path],
                    capture_output=True, text=True, timeout=150,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
            finally:
                try:
                    os.unlink(script_path)
                except Exception:
                    pass
        else:
            result = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True, text=True, timeout=150
            )

        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip())
        return []
    except Exception:
        return []


def sentinela_heartbeat():
    """O coração que acorda a cada 4 horas para vigiar o mercado."""
    from sentinela_db import init_db, listar_keywords, processar_mudancas_e_alertar
    from telegram_service import TelegramSentinela

    init_db()
    telegram = TelegramSentinela()

    # Se não tiver credenciais, nem tenta
    if not telegram.token or not telegram.chat_id:
        return

    keywords = listar_keywords()
    if not keywords:
        telegram.enviar_alerta(
            "Sentinela ativa, mas sem nicho definido.\n"
            "Cadastre keywords na aba **Sentinela → Nicho Monitorado** no app."
        )
        return  # Sai do loop se não tem keywords

    # Notifica que o robô começou
    telegram.enviar_alerta(
        f"Sentinela iniciou o ciclo!\n"
        f"Keywords: {', '.join(keywords[:5])}\n"
        f"Buscando dados do mercado..."
    )

    while True:
        for kw in keywords:
            try:
                resultados = _fetch_competitors_headless(kw)
                if resultados:
                    processar_mudancas_e_alertar(kw, resultados, telegram)
                else:
                    # Log silencioso em arquivo
                    with open("sentinela_log.txt", "a", encoding="utf-8") as log:
                        log.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Sem resultados para '{kw}'\n")
            except Exception as e:
                with open("sentinela_log.txt", "a", encoding="utf-8") as log:
                    log.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERRO: {e}\n")

        # Dorme por 4 horas (modo furtivo)
        time.sleep(SENTINELA_INTERVALO_SEGUNDOS)


# ── Entrada principal ─────────────────────────────────────────
def main():
    # 1. Iniciar Streamlit em background
    iniciar_streamlit()

    # 2. Verificar atualização silenciosamente
    threading.Thread(target=_checar_e_notificar, daemon=True).start()

    # 2.5. 📡 Iniciar a Sentinela em segundo plano
    threading.Thread(target=sentinela_heartbeat, daemon=True).start()

    # 3. Aguardar Streamlit subir
    if not aguardar_streamlit(timeout=60):
        ctypes.windll.user32.MessageBoxW(0, "O servidor não iniciou no tempo limite (60s).", "Shopee Booster - Erro", 0 | 16)
        sys.exit(1)

    # 4. Iniciar bandeja em thread NÃO-DAEMON
    # Isso faz com que o processo Python continue vivo mesmo se a janela principal fechar
    tray_thread = threading.Thread(target=iniciar_tray, daemon=False)
    tray_thread.start()

    # 5. Abrir janela nativa principal (bloqueante)
    abrir_janela_nativa()

    # 🚀 Se chegamos aqui, o usuário fechou a janela no "X"
    # O app continua rodando via tray_thread (não-daemon)
    # Aguardamos a thread da bandeja terminar (quando clicar em 'Sair')
    tray_thread.join()


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
