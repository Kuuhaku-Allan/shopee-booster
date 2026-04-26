"""
shopee_core/config.py — Configuração centralizada
==================================================
Lê .env e .shopee_config sem depender de Streamlit.
Tanto o .exe quanto a API e o Bot de WhatsApp usam este módulo.
"""

import os
import sys
from dotenv import load_dotenv


def _resolve_config_dir() -> str:
    """
    Resolve o diretório de configuração:
    - .exe  → pasta do executável
    - dev   → pasta onde este arquivo está (raiz do projeto)
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # __file__ = shopee_core/config.py → sobe um nível para a raiz
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_app_config() -> dict:
    """
    Carrega todas as configurações do ambiente.
    Retorna um dict com as chaves relevantes para o núcleo.
    """
    config_dir = _resolve_config_dir()

    # Carrega .env (projeto) e depois sobrepõe com .shopee_config
    load_dotenv(os.path.join(config_dir, ".env"))
    load_dotenv(os.path.join(config_dir, ".shopee_config"), override=True)

    return {
        "google_api_key": os.getenv("GOOGLE_API_KEY", ""),
        "hf_token": os.getenv("HF_TOKEN", ""),
        "runtime_dir": os.getenv("SHOPEE_RUNTIME_DIR", config_dir),
        "config_dir": config_dir,

        # Futuramente: credenciais da Evolution API / WhatsApp Bot
        "evolution_api_url": os.getenv("EVOLUTION_API_URL", ""),
        "evolution_api_key": os.getenv("EVOLUTION_API_KEY", ""),
        "whatsapp_instance": os.getenv("WHATSAPP_INSTANCE", ""),
    }


def get_google_api_key() -> str:
    """Atalho para obter a chave do Gemini sem carregar o config completo."""
    cfg = load_app_config()
    key = cfg["google_api_key"]
    if not key:
        raise ValueError(
            "GOOGLE_API_KEY não configurada. "
            "Defina no .env ou .shopee_config do projeto."
        )
    return key
