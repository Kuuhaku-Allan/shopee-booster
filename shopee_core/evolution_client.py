"""
shopee_core/evolution_client.py — Cliente HTTP da Evolution API
===============================================================
Responsável por toda comunicação com a Evolution API:
  - Enviar texto ao usuário (send_text)
  - Configurar webhook na instância (set_webhook)
  - Verificar status da instância (instance_status)

Não importa Streamlit. Usado pelo api_server.py após processar
uma mensagem do WhatsApp via handle_whatsapp_text().
"""

from __future__ import annotations

import logging
import re

import requests

from shopee_core.config import load_app_config

log = logging.getLogger("shopee_evolution")


# ══════════════════════════════════════════════════════════════════
# HELPERS INTERNOS
# ══════════════════════════════════════════════════════════════════

def _cfg() -> dict:
    """Carrega e valida as configurações obrigatórias da Evolution API."""
    cfg = load_app_config()

    missing = []
    if not cfg.get("evolution_api_url"):
        missing.append("EVOLUTION_API_URL")
    if not cfg.get("evolution_api_key"):
        missing.append("EVOLUTION_API_KEY")
    if not cfg.get("whatsapp_instance"):
        missing.append("WHATSAPP_INSTANCE")

    if missing:
        raise ValueError(
            f"Configurações ausentes para Evolution API: {', '.join(missing)}. "
            "Defina no .env ou .shopee_config do projeto."
        )

    return cfg


def _headers() -> dict:
    """Headers padrão para requisições à Evolution API."""
    return {
        "Content-Type": "application/json",
        "apikey": _cfg()["evolution_api_key"],
    }


def _base_url() -> str:
    """URL base da Evolution API sem trailing slash."""
    return _cfg()["evolution_api_url"].rstrip("/")


def _instance() -> str:
    """Nome da instância WhatsApp configurada."""
    return _cfg()["whatsapp_instance"]


# ══════════════════════════════════════════════════════════════════
# UTILITÁRIOS PÚBLICOS
# ══════════════════════════════════════════════════════════════════

def normalize_whatsapp_number(user_id: str) -> str:
    """
    Converte JID do WhatsApp em número puro (apenas dígitos).

    Exemplos:
        "5511999999999@s.whatsapp.net" → "5511999999999"
        "5511999999999"                → "5511999999999"
        "+55 (11) 99999-9999"          → "5511999999999"
    """
    if not user_id:
        return ""
    # Remove sufixo JID (@s.whatsapp.net, @g.us etc.)
    number = user_id.split("@")[0]
    # Remove qualquer caractere não numérico
    return re.sub(r"\D", "", number)


# ══════════════════════════════════════════════════════════════════
# ENVIO DE MENSAGENS
# ══════════════════════════════════════════════════════════════════

def send_text(user_id: str, text: str) -> dict:
    """
    Envia uma mensagem de texto simples para o usuário pelo WhatsApp.
    Divide automaticamente a mensagem se for muito longa (>3500 chars).
    """
    MAX_LEN = 3500
    if len(text) <= MAX_LEN:
        return _send_single_text(user_id, text)

    # Divide a mensagem em blocos
    chunks = []
    paragraphs = text.split("\n\n")
    current_chunk = ""
    for p in paragraphs:
        if len(current_chunk) + len(p) + 2 > MAX_LEN:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = p
        else:
            current_chunk += ("\n\n" + p) if current_chunk else p

    if current_chunk:
        chunks.append(current_chunk.strip())

    # Fallback caso um parágrafo único seja gigante
    if not chunks:
        chunks = [text[i:i+MAX_LEN] for i in range(0, len(text), MAX_LEN)]

    total = len(chunks)
    last_result = None
    for i, chunk in enumerate(chunks, start=1):
        chunk_text = f"{chunk}\n\n_[Parte {i}/{total}]_" if total > 1 else chunk
        last_result = _send_single_text(user_id, chunk_text)
        if not last_result.get("ok"):
            log.warning(f"[EVO] Falha ao enviar parte {i}/{total}")
            return last_result

    return last_result or {"ok": False, "error": "Empty chunks"}


def _send_single_text(user_id: str, text: str) -> dict:
    """Helper interno que de fato faz a chamada HTTP para enviar uma mensagem."""
    number = normalize_whatsapp_number(user_id)
    if not number:
        return {"ok": False, "error": "Número/JID inválido ou vazio."}

    url = f"{_base_url()}/message/sendText/{_instance()}"
    log.info(f"[EVO] _send_single_text → {url} number={number} len={len(text)}")

    # Formato primário (Evolution API v2)
    payload_v2 = {"number": number, "text": text}
    # Formato alternativo (algumas versões/forks)
    payload_v1 = {"number": number, "textMessage": {"text": text}}

    for attempt, payload in enumerate([payload_v2, payload_v1], start=1):
        try:
            r = requests.post(
                url,
                json=payload,
                headers=_headers(),
                timeout=30,
            )
            log.info(
                f"[EVO] _send_single_text attempt={attempt} "
                f"status={r.status_code} ok={r.ok}"
            )

            # Sucesso
            if r.ok:
                return {
                    "ok": True,
                    "status_code": r.status_code,
                    "data": r.json() if r.content else {},
                }

            # 400/422 no primeiro formato → tenta o alternativo
            if r.status_code in (400, 422) and attempt == 1:
                log.warning(
                    f"[EVO] Formato v2 rejeitado ({r.status_code}), "
                    "tentando formato v1..."
                )
                continue

            # Outro erro — não há mais alternativas
            return {
                "ok": False,
                "status_code": r.status_code,
                "data": r.json() if r.content else {},
                "raw": r.text[:500],
            }

        except requests.exceptions.ConnectionError:
            log.error("[EVO] _send_single_text — Evolution API inacessível (ConnectionError)")
            return {
                "ok": False,
                "error": (
                    "Não foi possível conectar à Evolution API. "
                    "Verifique se o Docker está rodando e EVOLUTION_API_URL está correto."
                ),
            }
        except Exception as e:
            log.error(f"[EVO] _send_single_text — exceção inesperada: {e}")
            return {"ok": False, "error": str(e)}

    return {"ok": False, "error": "Todos os formatos de envio falharam."}


# ══════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO DE WEBHOOK
# ══════════════════════════════════════════════════════════════════

def set_webhook(webhook_url: str, events: list[str] | None = None) -> dict:
    """
    Configura o webhook da instância para receber eventos do WhatsApp.

    Args:
        webhook_url — URL pública que a Evolution API vai chamar
                      Ex: "http://host.docker.internal:8787/webhook/evolution"
        events      — Lista de eventos a receber (padrão: MESSAGES_UPSERT)

    Returns dict com ok, status_code, data.
    """
    if events is None:
        events = ["MESSAGES_UPSERT"]

    url = f"{_base_url()}/webhook/set/{_instance()}"
    payload = {
        "enabled": True,
        "url": webhook_url,
        "events": events,
        "base64": True,
    }

    log.info(f"[EVO] set_webhook → {url} webhook_url={webhook_url} events={events}")

    try:
        r = requests.post(
            url,
            json=payload,
            headers=_headers(),
            timeout=30,
        )
        log.info(f"[EVO] set_webhook status={r.status_code} ok={r.ok}")
        return {
            "ok": r.ok,
            "status_code": r.status_code,
            "data": r.json() if r.content else {},
            "raw": r.text[:500] if not r.ok else "",
        }
    except requests.exceptions.ConnectionError:
        return {
            "ok": False,
            "error": (
                "Não foi possível conectar à Evolution API. "
                "Verifique se o Docker está rodando."
            ),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════════
# STATUS DA INSTÂNCIA
# ══════════════════════════════════════════════════════════════════

def instance_status() -> dict:
    """
    Verifica o status de conexão da instância WhatsApp.
    Útil para saber se o QR Code já foi lido e o número está conectado.

    Returns dict com ok, state (ex: "open", "connecting", "close").
    """
    url = f"{_base_url()}/instance/connectionState/{_instance()}"
    log.info(f"[EVO] instance_status → {url}")

    try:
        r = requests.get(url, headers=_headers(), timeout=15)
        data = r.json() if r.content else {}
        state = (
            data.get("instance", {}).get("state")
            or data.get("state")
            or "unknown"
        )
        log.info(f"[EVO] instance_status state={state!r}")
        return {
            "ok": r.ok,
            "state": state,
            "status_code": r.status_code,
            "data": data,
        }
    except requests.exceptions.ConnectionError:
        return {
            "ok": False,
            "state": "unreachable",
            "error": "Evolution API inacessível.",
        }
    except Exception as e:
        return {"ok": False, "state": "error", "error": str(e)}
