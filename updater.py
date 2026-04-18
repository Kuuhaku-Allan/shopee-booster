"""
updater.py — Shopee Booster
Verifica GitHub Releases, baixa e aplica a atualização automaticamente.
"""

import os
import sys
import time
import shutil
import requests
import tempfile
import subprocess

# ── Configure aqui ────────────────────────────────────────────
# Substitua com o usuário e repositório corretos no GitHub
GITHUB_USUARIO = "AmaDeusAlsoSatan"
GITHUB_REPO    = "shopee-booster"

VERSAO_ATUAL = "4.0.0"  # Atualizar a cada release

API_URL = f"https://api.github.com/repos/{GITHUB_USUARIO}/{GITHUB_REPO}/releases/latest"


# ── Comparador de versão simples ──────────────────────────────
def _versao_maior(v_nova: str, v_atual: str) -> bool:
    """Retorna True se v_nova > v_atual (ex: '1.2.0' > '1.1.5')."""
    try:
        nova  = tuple(int(x) for x in v_nova.strip("v").split("."))
        atual = tuple(int(x) for x in v_atual.strip("v").split("."))
        return nova > atual
    except Exception:
        return False


# ── Verificação ───────────────────────────────────────────────
def verificar_atualizacao() -> dict:
    """
    Consulta GitHub Releases e retorna:
    {
        "disponivel":   bool,
        "versao_nova":  str,
        "url_download": str,   # URL do .exe no release
        "notas":        str,
    }
    """
    resultado = {
        "disponivel":   False,
        "versao_nova":  VERSAO_ATUAL,
        "url_download": "",
        "notas":        "",
    }
    try:
        r = requests.get(API_URL, timeout=10, headers={"Accept": "application/vnd.github+json"})
        if r.status_code != 200:
            return resultado

        data = r.json()
        versao_nova = data.get("tag_name", "").strip("v")
        notas       = data.get("body", "")

        # Procurar o asset .zip no release
        url_download = ""
        for asset in data.get("assets", []):
            if asset.get("name", "").lower().endswith(".zip"):
                url_download = asset.get("browser_download_url", "")
                break

        if versao_nova and _versao_maior(versao_nova, VERSAO_ATUAL) and url_download:
            resultado["disponivel"]   = True
            resultado["versao_nova"]  = versao_nova
            resultado["url_download"] = url_download
            resultado["notas"]        = notas

    except Exception:
        pass  # Sem internet ou outro erro — silencioso

    return resultado


# ── Download + aplicação ──────────────────────────────────────
def baixar_e_aplicar_atualizacao(url_download: str):
    """
    Baixa o .zip da nova versão, extrai e sincroniza a pasta.
    """
    import zipfile
    import tkinter as tk
    from tkinter import ttk, messagebox

    # 1. Download
    try:
        root = tk.Tk()
        root.title("Atualizando Shopee Booster...")
        root.geometry("400x120")
        root.resizable(False, False)
        root.eval("tk::PlaceWindow . center")

        tk.Label(root, text="⬇️ Baixando atualização, aguarde...").pack(pady=10)
        barra = ttk.Progressbar(root, length=360, mode="indeterminate")
        barra.pack(padx=20)
        barra.start()
        root.update()

        tmp_dir = tempfile.mkdtemp()
        nome_zip = url_download.split("/")[-1]
        caminho_zip = os.path.join(tmp_dir, nome_zip)

        with requests.get(url_download, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            with open(caminho_zip, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
                    root.update()

        barra.stop()
        root.destroy()
    except Exception as e:
        messagebox.showerror("Erro no download", f"Não foi possível baixar:\n{e}")
        return

    # 2. Extração
    try:
        root = tk.Tk()
        root.title("Extraindo Shopee Booster...")
        root.geometry("400x120")
        root.resizable(False, False)
        root.eval("tk::PlaceWindow . center")
        tk.Label(root, text="📦 Extraindo arquivos, aguarde...").pack(pady=10)
        barra = ttk.Progressbar(root, length=360, mode="indeterminate")
        barra.pack(padx=20)
        barra.start()
        root.update()

        extract_dir = os.path.join(tmp_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(caminho_zip, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        barra.stop()
        root.destroy()
    except Exception as e:
        messagebox.showerror("Erro na extração", f"Não foi possível extrair arquivos:\n{e}")
        return

    # 3. Aplicação
    try:
        if getattr(sys, "frozen", False):
            app_dir = os.path.dirname(sys.executable)
            caminho_atual_exe = sys.executable
        else:
            subprocess.Popen(["explorer", extract_dir])
            return

        bat_path = os.path.join(tmp_dir, "update.bat")
        # Script BAT para sincronização via robocopy
        # /XD exclui pastas, /XF exclui arquivos específicos
        bat_conteudo = (
            "@echo off\n"
            "echo Aplicando atualizacao... Aguarde 5 segundos.\n"
            "timeout /t 5 /nobreak > nul\n"
            f'robocopy "{extract_dir}" "{app_dir}" /E /v /it /is /XD data logs pw-browsers /XF .shopee_config\n'
            "echo Reiniciando...\n"
            f'start "" "{caminho_atual_exe}"\n'
            "del \"%~f0\"\n"
        )
        with open(bat_path, "w", encoding="cp1252") as f:
            f.write(bat_conteudo)

        subprocess.Popen(
            ["cmd", "/c", bat_path],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        os._exit(0)

    except Exception as e:
        messagebox.showerror("Erro na aplicação", f"Erro ao aplicar atualização:\n{e}")