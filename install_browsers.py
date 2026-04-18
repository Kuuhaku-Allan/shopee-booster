"""
install_browsers.py — Shopee Booster
Instala os navegadores do Playwright (Chromium) necessários para
a Auditoria e Sentinela funcionarem.

Este script deve ser empacotado como um executável separado
que roda ANTES do app principal.
"""

import subprocess
import sys
import os

def get_runtime_dir():
    """Retorna o diretório onde o .exe está localizado."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def get_browsers_path():
    """Retorna o caminho onde os browsers devem ser instalados."""
    return os.path.join(get_runtime_dir(), "pw-browsers")


def check_chromium_installed():
    """Verifica se o Chromium já está instalado."""
    browsers_path = get_browsers_path()
    if not os.path.exists(browsers_path):
        return False

    for item in os.listdir(browsers_path):
        if item.startswith("chromium_headless_shell-"):
            exe_path = os.path.join(
                browsers_path, item, "chrome-headless-shell-win64",
                "chrome-headless-shell.exe"
            )
            if os.path.exists(exe_path):
                return True
    return False


def install_chromium():
    """Instala o Chromium do Playwright."""
    browsers_path = get_browsers_path()

    # Garantir que a pasta existe
    os.makedirs(browsers_path, exist_ok=True)

    # Definir o environment para o Playwright
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path

    print(f"Instalando Chromium em: {browsers_path}")
    print("Isso pode demorar alguns minutos...")
    print()

    try:
        # No modo frozen, usar o Python embutido
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
        else:
            cmd = [sys.executable, "-m", "playwright", "install", "chromium"]

        result = subprocess.run(
            cmd,
            env=env,
            timeout=300,  # 5 minutos
        )

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        print("ERRO: Timeout ao instalar Chromium (>5 minutos)")
        return False
    except Exception as e:
        print(f"ERRO: {e}")
        return False


def main():
    print("=" * 50)
    print("Shopee Booster - Instalador de Navegadores")
    print("=" * 50)
    print()

    browsers_path = get_browsers_path()
    print(f"Diretório de instalação: {browsers_path}")
    print()

    if check_chromium_installed():
        print("Chromium já está instalado!")
        print()
        input("Pressione Enter para sair...")
        return

    print("Chromium não encontrado.")
    print("Iniciando instalação...")
    print()

    success = install_chromium()

    print()
    if success:
        print("Chromium instalado com sucesso!")
        print("A Auditoria e Sentinela agora funcionarão corretamente.")
    else:
        print("Falha ao instalar Chromium.")
        print()
        print("Tente executar manualmente no terminal:")
        print(f"  set PLAYWRIGHT_BROWSERS_PATH={browsers_path}")
        print("  python -m playwright install chromium")

    print()
    input("Pressione Enter para sair...")


if __name__ == "__main__":
    main()