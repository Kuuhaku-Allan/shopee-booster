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

VERSAO_ATUAL = "2.0.0"  # Atualizar a cada release

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

        # Procurar o asset .exe no release
        url_download = ""
        for asset in data.get("assets", []):
            if asset.get("name", "").endswith(".exe"):
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
    Baixa o novo .exe e cria um script .bat que:
    1. Aguarda este processo encerrar
    2. Substitui o .exe antigo pelo novo
    3. Reinicia o app
    Depois encerra o processo atual.
    """
    try:
        import tkinter as tk
        from tkinter import ttk

        # Janela de progresso
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

        # Baixar arquivo
        tmp_dir   = tempfile.mkdtemp()
        nome_exe  = url_download.split("/")[-1]
        caminho_novo = os.path.join(tmp_dir, nome_exe)

        with requests.get(url_download, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            with open(caminho_novo, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
                    root.update()

        barra.stop()
        root.destroy()

        # Caminho do exe atual
        caminho_atual = sys.executable if getattr(sys, "frozen", False) else ""

        if not caminho_atual or not caminho_atual.endswith(".exe"):
            # Modo dev: só avisar e abrir pasta
            import subprocess
            subprocess.Popen(["explorer", tmp_dir])
            return

        # Criar script bat que substitui o exe e reinicia
        bat_path = os.path.join(tmp_dir, "update.bat")
        bat_conteudo = (
            "@echo off\n"
            "timeout /t 2 /nobreak > nul\n"
            f'copy /y "{caminho_novo}" "{caminho_atual}"\n'
            f'start "" "{caminho_atual}"\n'
            "del \"%~f0\"\n"
        )
        with open(bat_path, "w") as f:
            f.write(bat_conteudo)

        subprocess.Popen(
            ["cmd", "/c", bat_path],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        os._exit(0)

    except Exception as e:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Erro na atualização", f"Não foi possível atualizar:\n{e}")
        root.destroy()