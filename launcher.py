"""
launcher.py — Shopee Booster
Responsabilidades:
  - Iniciar o Streamlit em segundo plano
  - Ícone na bandeja do sistema (system tray)
  - Janela nativa via pywebview (modo "instalado")
  - Verificar atualizações no GitHub ao iniciar
  - Verificar e instalar Chromium do Playwright se necessário
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
import importlib  # Para importação dinâmica
import platform
import pystray
import webview
from PIL import Image, ImageDraw
import queue

from updater import verificar_atualizacao, VERSAO_ATUAL

# 🔥 MEDIDA DE SEGURANÇA: Forçar apenas CPU para evitar travamentos silenciosos da IA
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["ORT_LOGGING_LEVEL"] = "3"
os.environ["ONNXRUNTIME_PROVIDERS"] = "CPUExecutionProvider"

# ── Configurações ─────────────────────────────────────────────
PORTA = 8501
URL_APP = f"http://localhost:{PORTA}"
TITULO_JANELA = f"Shopee Booster v{VERSAO_ATUAL}"

# Caminho do app.py — funciona tanto em dev quanto no .exe
if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

APP_PY = os.path.join(BASE_DIR, "app.py")

# ══ RUNTIME_DIR unificado — importado do sentinela_db ════════
# Isso garante que launcher.py e sentinela_db.py concordem sobre
# onde ficam banco, logs e dados persistentes.
from sentinela_db import RUNTIME_DIR, SENTINELA_LOG_PATH

# Browsers do Playwright — pasta persistente ao lado do .exe
if getattr(sys, "frozen", False):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(RUNTIME_DIR, "pw-browsers")


# ── Estado global ─────────────────────────────────────────────
streamlit_proc = None
janela_webview = None
tray_icon = None
log_file = None  # Inicialização global para o linter

# ── Sinal para acordar o heartbeat quando credenciais mudam ───
_sentinela_wake = queue.Queue()

def wake_sentinela():
    """Acorda a thread do heartbeat para que releia credenciais do DB."""
    try:
        _sentinela_wake.put_nowait("wake")
    except Exception:
        pass


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
            "--theme.base", "dark",
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
            "--theme.base", "dark",
            "--global.developmentMode", "false",
        ]
    global log_file
    streamlit_log_path = os.path.join(RUNTIME_DIR, "streamlit_log.txt")
    log_file = open(streamlit_log_path, "w", encoding="utf-8")
    
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

    try:
        janela_webview = webview.create_window(
            TITULO_JANELA,
            URL_APP,
            width=1280,
            height=800,
            resizable=True,
            min_size=(900, 600),
        )
        webview.start(debug=False)
    except Exception as e:
        _sentinela_log(f"[WebView] ERRO ao abrir janela: {e}")
        # Fallback: abrir no navegador
        ctypes.windll.user32.MessageBoxW(
            0,
            f"Nao foi possivel abrir a janela nativa.\n\n"
            f"O app abrira no navegador.\n\n"
            f"Erro: {str(e)[:100]}",
            "Shopee Booster - Aviso",
            0 | 48
        )
        webbrowser.open(URL_APP)
    finally:
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
    """Checa GitHub e mostra diálogo se houver update (manual via tray)."""
    threading.Thread(target=_checar_e_notificar_manual, daemon=True).start()


def _checar_e_atualizar_automatico():
    """
    Verificação automática no startup.
    Se houver update, aplica automaticamente sem perguntar.
    """
    resultado = verificar_atualizacao()
    if resultado["disponivel"]:
        msg = (f"Nova versão disponível: {resultado['versao_nova']}\n"
               f"Versão atual: {VERSAO_ATUAL}\n\n"
               f"A atualização será aplicada agora.\n"
               f"O app será reiniciado automaticamente.")
        ctypes.windll.user32.MessageBoxW(0, msg, "Atualizando Shopee Booster", 0 | 64)
        from updater import baixar_e_aplicar_atualizacao
        baixar_e_aplicar_atualizacao(resultado["url_download"])


def _checar_e_notificar_manual():
    """
    Verificação manual via botão do tray.
    Mostra status e pergunta se deseja atualizar.
    """
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


def acao_reinstalar_chromium(icon, item):
    """Reinstala o Chromium do Playwright."""
    threading.Thread(target=_reinstalar_chromium_dialog, daemon=True).start()


def _reinstalar_chromium_dialog():
    """Thread para reinstalar Chromium com diálogo."""
    msg = (
        "Deseja reinstalar o navegador Chromium?\n\n"
        "Isso pode resolver problemas com a Auditoria e Sentinela.\n"
        "O download tem aproximadamente 130MB."
    )
    res = ctypes.windll.user32.MessageBoxW(
        0, msg, "Shopee Booster - Reinstalar Chromium", 4 | 64
    )

    if res == 6:  # IDYES
        success = instalar_chromium()
        if success:
            ctypes.windll.user32.MessageBoxW(
                0, "Chromium reinstalado com sucesso!", "Shopee Booster", 0 | 64
            )
        else:
            ctypes.windll.user32.MessageBoxW(
                0, "Falha ao reinstalar Chromium.\nVeja o log sentinela_log.txt para detalhes.",
                "Shopee Booster - Erro", 0 | 16
            )


def iniciar_tray():
    global tray_icon
    icone_img = criar_icone_imagem()

    # Verificar status do Chromium para tooltip
    chromium_ok = chromium_existe()
    status_chromium = "Chromium: OK" if chromium_ok else "Chromium: FALTANDO"

    menu = pystray.Menu(
        pystray.MenuItem("📦 Abrir Janela",      acao_abrir_janela, default=True),
        pystray.MenuItem("🌐 Abrir no Navegador", acao_abrir_navegador),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("🔄 Verificar Atualizações", acao_verificar_atualizacao),
        pystray.MenuItem("🌐 Reinstalar Chromium", acao_reinstalar_chromium),
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


# ════════════════════════════════════════════════════════════════════════════
# ── SENTINELA: Heartbeat em background ────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════

SENTINELA_INTERVALO_SEGUNDOS = 4 * 3600  # 4 horas

# Usa SENTINELA_LOG_PATH importado do sentinela_db (já calculado com RUNTIME_DIR)

def _sentinela_log(msg: str):
    """Grava uma linha no log da Sentinela com timestamp."""
    try:
        with open(SENTINELA_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════════════
# ── PLAYWRIGHT: Verificação do Chromium ──────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════

def get_chromium_path() -> str:
    """
    Retorna o caminho esperado do executável do Chromium headless.
    Caminho varia conforme versão do Playwright e sistema.
    """
    browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    if not browsers_path:
        # Fallback para desenvolvimento
        browsers_path = os.path.join(RUNTIME_DIR, "pw-browsers")

    system = platform.system().lower()
    if system == "windows":
        # Estrutura típica: pw-browsers/chromium_headless_shell-XXXX/chrome-headless-shell-win64/
        if os.path.exists(browsers_path):
            for item in os.listdir(browsers_path):
                if item.startswith("chromium_headless_shell-"):
                    exe_path = os.path.join(
                        browsers_path, item, "chrome-headless-shell-win64",
                        "chrome-headless-shell.exe"
                    )
                    if os.path.exists(exe_path):
                        return exe_path
    return ""


def chromium_existe() -> bool:
    """Verifica se o Chromium headless está instalado."""
    return bool(get_chromium_path())


def instalar_chromium() -> bool:
    """
    Instala o Chromium do Playwright automaticamente.
    Retorna True se instalação com sucesso ou já existir.

    NOTA: No modo .exe (frozen), isso NÃO funciona porque sys.executable
    é o próprio launcher. Usar o script install_browsers.py separado.
    """
    if chromium_existe():
        return True

    # No modo frozen, NÃO podemos usar sys.executable -m playwright
    # porque isso reabre o próprio app, causando loop infinito
    if getattr(sys, "frozen", False):
        _sentinela_log("[Playwright] Instalação automática não suportada no modo .exe. Use install_browsers.py")
        return False

    try:
        _sentinela_log("[Playwright] Chromium não encontrado. Instalando...")

        # Modo desenvolvimento - usar Python diretamente
        cmd = [sys.executable, "-m", "playwright", "install", "chromium"]

        # Executar instalação
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutos de timeout
        )

        if result.returncode == 0:
            _sentinela_log("[Playwright] Chromium instalado com sucesso.")
            return True
        else:
            _sentinela_log(f"[Playwright] ERRO ao instalar: {result.stderr[:500]}")
            return False

    except subprocess.TimeoutExpired:
        _sentinela_log("[Playwright] TIMEOUT na instalação do Chromium.")
        return False
    except Exception as e:
        _sentinela_log(f"[Playwright] Exceção ao instalar: {e}")
        return False


def garantir_chromium() -> bool:
    """
    Garante que o Chromium está instalado.
    Mostra diálogo se precisar instalar.
    Retorna True se Chromium disponível, False caso contrário.
    """
    if chromium_existe():
        return True

    # Verificar se está no modo .exe (frozen)
    is_frozen = getattr(sys, "frozen", False)

    if is_frozen:
        # No modo .exe, não podemos instalar automaticamente
        msg = (
            "O navegador Chromium não foi encontrado.\n\n"
            "Para a Auditoria e Sentinela funcionarem, você precisa:\n\n"
            "1. Copie a pasta 'pw-browsers' de uma instalação funcional\n"
            "   para a pasta onde está o ShopeeBooster.exe\n\n"
            "   OU\n\n"
            "2. Execute 'install_browsers.exe' que vem junto com o app\n\n"
            "O app continuará, mas a Auditoria e Sentinela não funcionarão\n"
            "até que o Chromium seja instalado."
        )
        ctypes.windll.user32.MessageBoxW(0, msg, "Shopee Booster - Chromium Ausente", 0 | 48)
        _sentinela_log("[Playwright] Chromium ausente no modo .exe. Auditoria/Sentinela podem falhar.")
        return False
    else:
        # Modo desenvolvimento - pode instalar automaticamente
        msg = (
            "O navegador Chromium (usado pela Auditoria e Sentinela) não foi encontrado.\n\n"
            "Deseja baixar e instalar agora?\n"
            "O download tem aproximadamente 130MB."
        )
        res = ctypes.windll.user32.MessageBoxW(
            0, msg, "Shopee Booster - Chromium necessário", 4 | 64
        )

        if res != 6:  # IDYES = 6
            _sentinela_log("[Playwright] Usuário recusou instalação do Chromium.")
            return False

        # Usuário clicou em Sim — instalar
        _sentinela_log("[Playwright] Iniciando instalação do Chromium...")
        success = instalar_chromium()

        if success:
            ctypes.windll.user32.MessageBoxW(
                0,
                "Chromium instalado com sucesso!\nO app continuará normalmente.",
                "Shopee Booster",
                0 | 64
            )
            return True
        else:
            ctypes.windll.user32.MessageBoxW(
                0,
                "Falha ao instalar Chromium automaticamente.\n\n"
                "Execute manualmente no terminal:\n"
                "python -m playwright install chromium",
                "Shopee Booster - Erro",
                0 | 16
            )
            return False


def _fetch_competitors_headless(keyword: str) -> list:
    """
    Busca concorrentes via Playwright em subprocess isolado (sem UI).
    Registra TODA saída de erro no sentinela_log.txt — nunca engole
    exceções silenciosamente.
    """
    kw_encoded = keyword.replace(" ", "+")

    script = f"""
import asyncio, json, sys
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

def parse_items(data):
    items = data.get("items") or data.get("data", {{}}).get("items") or []
    competitors = []
    seen_ids = set()

    for item in items[:20]:
        b = item.get("item_basic", item) or {{}}
        item_id = b.get("itemid") or item.get("itemid")
        if not item_id or item_id in seen_ids:
            continue
        seen_ids.add(item_id)

        rating = b.get("item_rating") or {{}}
        price_raw = b.get("price_min") or b.get("price") or 0
        competitors.append({{
            "item_id":    item_id,
            "shop_id":    b.get("shopid") or item.get("shopid"),
            "nome":       (b.get("name") or "")[:65],
            "preco":      price_raw / 100000 if price_raw > 1000 else price_raw,
            "avaliações": b.get("cmt_count", 0),
            "curtidas":   b.get("liked_count", 0),
            "estrelas":   round(rating.get("rating_star", 0), 1),
        }})

    return competitors[:10]

def is_search_response(response):
    if response.request.method == "OPTIONS":
        return False
    url = response.url
    return "api/v4/search/search_items" in url or "v4/search/search_items" in url

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
        search_url = "https://shopee.com.br/search?keyword={kw_encoded}&sortBy=sales"

        try:
            async with page.expect_response(is_search_response, timeout=30000) as response_info:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
            response = await response_info.value
            data = await response.json()
            competitors = parse_items(data)
            print(f"search_items url: {{response.url}}", file=sys.stderr)
            print(f"competitors parsed: {{len(competitors)}}", file=sys.stderr)
        except PlaywrightTimeoutError as e:
            print(f"search_items timeout: {{e}}", file=sys.stderr)
        except Exception as e:
            print(f"search_items parse err: {{e}}", file=sys.stderr)

        if not competitors:
            try:
                await page.goto(search_url, wait_until="load", timeout=45000)
            except Exception as e:
                print(f"fallback goto err: {{e}}", file=sys.stderr)
            await asyncio.sleep(5)

        await browser.close()
        print(json.dumps(competitors))

asyncio.run(run())
"""

    _sentinela_log(
        f"[headless] Iniciando busca '{keyword}' | "
        f"exe={sys.executable[:60]} | "
        f"PLAYWRIGHT_BROWSERS_PATH={os.environ.get('PLAYWRIGHT_BROWSERS_PATH','<não definido>')}"
    )

    try:
        import tempfile

        if getattr(sys, "frozen", False):
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
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
                capture_output=True, text=True, timeout=150,
            )

        # ── Log completo independente do resultado ────────────
        _sentinela_log(
            f"[headless] returncode={result.returncode} | "
            f"stdout_len={len(result.stdout.strip())} | "
            f"stderr={result.stderr.strip()[:500] if result.stderr.strip() else '<vazio>'}"
        )

        if result.returncode == 0 and result.stdout.strip():
            dados = json.loads(result.stdout.strip())
            _sentinela_log(f"[headless] '{keyword}' → {len(dados)} concorrentes.")
            return dados

        # returncode != 0 ou stdout vazio — log detalhado
        _sentinela_log(
            f"[headless] FALHA '{keyword}': returncode={result.returncode} | "
            f"stdout='{result.stdout.strip()[:200]}' | "
            f"stderr='{result.stderr.strip()[:500]}'"
        )
        return []

    except subprocess.TimeoutExpired:
        _sentinela_log(f"[headless] TIMEOUT para '{keyword}' (>150s).")
        return []
    except Exception as e:
        import traceback
        _sentinela_log(
            f"[headless] EXCEÇÃO para '{keyword}': {e}\n"
            + traceback.format_exc()[:600]
        )
        return []


def _sentinela_sleep(segundos: int):
    """Sleep que pode ser interrompido pelo sinal de wake."""
    try:
        _sentinela_wake.get(timeout=segundos)
        _sentinela_log("[wake] Heartbeat acordado antes do previsto.")
    except Exception:
        pass  # Timeout normal


def sentinela_heartbeat():
    """
    Coração da Sentinela — loop infinito em daemon thread.
    Recarrega credenciais e keywords a CADA ciclo.
    Nunca termina prematuramente.
    Quando credenciais faltam, acorda a cada 60s em vez de 4h.
    """
    from sentinela_db import init_db, listar_keywords, processar_mudancas_e_alertar
    from telegram_service import TelegramSentinela

    init_db()
    _sentinela_log(
        f"Sentinela thread iniciada. "
        f"RUNTIME_DIR={RUNTIME_DIR} | DB={__import__('sentinela_db').DB_PATH}"
    )

    primeiro_ciclo = True

    while True:
        try:
            telegram = TelegramSentinela()
            keywords = listar_keywords()

            if not telegram.token or not telegram.chat_id:
                _sentinela_log(
                    f"Sem credenciais Telegram — token={'presente' if telegram.token else 'AUSENTE'}, "
                    f"chat_id={'presente' if telegram.chat_id else 'AUSENTE'}. "
                    f"Rechecando em 60s."
                )
                _sentinela_sleep(60)
                continue

            if not keywords:
                _sentinela_log("Sem keywords definidas — aguardando próximo ciclo.")
                if primeiro_ciclo:
                    telegram.enviar_alerta(
                        "Sentinela ativa, mas sem nicho definido.\n"
                        "Cadastre keywords na aba *Sentinela → Nicho Monitorado* no app."
                    )
                _sentinela_sleep(SENTINELA_INTERVALO_SEGUNDOS)
                continue

            if primeiro_ciclo:
                telegram.enviar_alerta(
                    f"Sentinela iniciou o ciclo!\n"
                    f"Keywords: {', '.join(keywords[:5])}\n"
                    f"Buscando dados do mercado..."
                )

            _sentinela_log(f"Iniciando ciclo — {len(keywords)} keywords: {keywords}")

            for kw in keywords:
                try:
                    resultados = _fetch_competitors_headless(kw)
                    if resultados:
                        processar_mudancas_e_alertar(kw, resultados, telegram)
                        _sentinela_log(f"OK '{kw}': {len(resultados)} resultados processados.")
                    else:
                        _sentinela_log(f"Sem resultados para '{kw}' — veja log acima.")
                except Exception as e:
                    import traceback
                    _sentinela_log(
                        f"ERRO ao processar '{kw}': {e}\n"
                        + traceback.format_exc()[:400]
                    )

            _sentinela_log(
                f"Ciclo concluído. Próximo em {SENTINELA_INTERVALO_SEGUNDOS // 3600}h."
            )

        except Exception as e:
            import traceback
            _sentinela_log(
                f"ERRO inesperado no ciclo principal: {e}\n"
                + traceback.format_exc()[:400]
            )
        finally:
            primeiro_ciclo = False

        _sentinela_sleep(SENTINELA_INTERVALO_SEGUNDOS)


# ── Entrada principal ─────────────────────────────────────────
def main():
    _sentinela_log(f"[Main] Iniciando Shopee Booster v{VERSAO_ATUAL}")
    _sentinela_log(f"[Main] RUNTIME_DIR={RUNTIME_DIR}")
    _sentinela_log(f"[Main] frozen={getattr(sys, 'frozen', False)}")

    # 0. Verificar se o Chromium do Playwright está instalado
    chromium_ok = garantir_chromium()
    if not chromium_ok:
        _sentinela_log("[Main] Chromium não disponível. Auditoria pode falhar.")

    # 0.5 Garantir que PLAYWRIGHT_BROWSERS_PATH está definido
    if not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(RUNTIME_DIR, "pw-browsers")
    _sentinela_log(f"[Main] PLAYWRIGHT_BROWSERS_PATH={os.environ.get('PLAYWRIGHT_BROWSERS_PATH')}")

    # 1. Iniciar Streamlit em background
    _sentinela_log("[Main] Iniciando Streamlit...")
    iniciar_streamlit()

    # 2. Verificar atualização automaticamente (atualiza sem perguntar)
    threading.Thread(target=_checar_e_atualizar_automatico, daemon=True).start()

    # 2.5. Iniciar a Sentinela em segundo plano
    threading.Thread(target=sentinela_heartbeat, daemon=True).start()

    # 3. Aguardar Streamlit subir
    _sentinela_log("[Main] Aguardando Streamlit subir...")
    if not aguardar_streamlit(timeout=120):
        _sentinela_log("[Main] ERRO: Streamlit não iniciou")
        ctypes.windll.user32.MessageBoxW(0, "O servidor não iniciou no tempo limite (120s).", "Shopee Booster - Erro", 0 | 16)
        sys.exit(1)

    _sentinela_log("[Main] Streamlit OK. Iniciando janela...")

    # 3.5. Delay de respiro para o Streamlit renderizar o HTML inicial
    time.sleep(2)

    # 4. Iniciar bandeja em thread NÃO-DAEMON
    tray_thread = threading.Thread(target=iniciar_tray, daemon=False)
    tray_thread.start()

    # 5. Abrir janela nativa principal (bloqueante)
    _sentinela_log("[Main] Abrindo janela nativa...")
    abrir_janela_nativa()

    # Se chegamos aqui, o usuário fechou a janela no "X"
    # O app continua rodando via tray_thread (não-daemon)
    _sentinela_log("[Main] Janela fechada. Aguardando tray...")
    tray_thread.join()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    
    # Interceptar a chamada "run" para lançar o streamlit embutido
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        # Usamos importlib para silenciar o linter e manter compatibilidade total
        stcli = None
        for mod_name in ["streamlit.web.cli", "streamlit.cli"]:
            try:
                stcli = importlib.import_module(mod_name)
                break
            except ImportError:
                continue
        
        if stcli:
            sys.exit(stcli.main())
        else:
            sys.exit(1)
    
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
