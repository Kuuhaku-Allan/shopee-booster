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

def resolve_lid_to_jid(jid: str) -> str:
    """
    Resolve LID (Local Identifier) para JID (WhatsApp ID) real.
    
    Fontes de mapeamento (em ordem de prioridade):
    1. data/lid_map.json
    2. EVOLUTION_LID_MAP no .env
    3. Se não encontrar, retorna None para evitar envio para número fake
    """
    if not jid or not jid.endswith("@lid"):
        return jid
    
    import json
    import os
    
    # 1. Tentar data/lid_map.json
    lid_map_file = "data/lid_map.json"
    if os.path.exists(lid_map_file):
        try:
            with open(lid_map_file, 'r', encoding='utf-8') as f:
                lid_map = json.load(f)
                if jid in lid_map:
                    resolved = lid_map[jid]
                    log.info(f"[LID] Mapeado via arquivo: {jid} → {resolved}")
                    return resolved
        except Exception as e:
            log.warning(f"[LID] Erro ao ler {lid_map_file}: {e}")
    
    # 2. Tentar EVOLUTION_LID_MAP no .env
    try:
        cfg = load_app_config()
        lid_map_env = cfg.get("evolution_lid_map", "")
        if lid_map_env:
            # Formato: "220035536678945@lid=5511988600050@s.whatsapp.net"
            for mapping in lid_map_env.split(","):
                if "=" in mapping:
                    lid, real_jid = mapping.strip().split("=", 1)
                    if lid == jid:
                        log.info(f"[LID] Mapeado via env: {jid} → {real_jid}")
                        return real_jid
    except Exception as e:
        log.warning(f"[LID] Erro ao ler EVOLUTION_LID_MAP: {e}")
    
    # 3. Se não encontrar mapeamento, logar erro e retornar None
    log.error(f"[LID] ERRO: Não foi encontrado mapeamento para {jid}. "
              f"Adicione no data/lid_map.json ou EVOLUTION_LID_MAP no .env.local")
    return None


def normalize_whatsapp_number(user_id: str) -> str:
    """
    Converte JID do WhatsApp em número puro (apenas dígitos).
    Inclui resolução automática de LID → JID.

    Exemplos:
        "5511999999999@s.whatsapp.net" → "5511999999999"
        "220035536678945@lid"          → "5511988600050" (via mapeamento)
        "5511999999999"                → "5511999999999"
        "+55 (11) 99999-9999"          → "5511999999999"
    """
    if not user_id:
        return ""
    
    # Resolver LID para JID real se necessário
    resolved_jid = resolve_lid_to_jid(user_id)
    if resolved_jid is None:
        # LID sem mapeamento - não tentar enviar
        return ""
    
    user_id = resolved_jid
    
    # Remove sufixo JID (@s.whatsapp.net, @g.us etc.)
    number = user_id.split("@")[0]
    # Alguns IDs vêm como "5511...:63@s.whatsapp.net" (device/agent suffix).
    # Para envio, a Evolution espera apenas o número base antes do ":".
    if ":" in number:
        number = number.split(":", 1)[0]
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

    # Formato oficial da Evolution API v2.1.1
    # Documentação: https://docs.evoapicloud.com/api-reference/message-controller/send-text
    url = f"{_base_url()}/message/sendText/{_instance()}"
    
    # Payload conforme documentação oficial
    payload = {
        "number": number,
        "text": text
    }

    log.info(f"[EVO] _send_single_text → {url} number={number} text_len={len(text)}")

    try:
        r = requests.post(
            url,
            json=payload,
            headers=_headers(),
            timeout=30,
        )
        
        log.info(f"[EVO] _send_single_text status={r.status_code} ok={r.ok}")

        # Sucesso
        if r.ok:
            return {
                "ok": True,
                "status_code": r.status_code,
                "data": r.json() if r.content else {},
            }

        # Falha - loga detalhes completos
        error_data = r.json() if r.content else {}
        log.error(
            f"[EVO] _send_single_text FALHOU: "
            f"status={r.status_code} response={r.text[:500]}"
        )
        
        return {
            "ok": False,
            "status_code": r.status_code,
            "data": error_data,
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


def send_media(
    user_id: str,
    base64_media: str,
    mediatype: str = "image",
    mimetype: str = "image/png",
    caption: str = "",
    filename: str = "shopeebooster.png",
) -> dict:
    """
    Envia uma mídia (imagem, arquivo) para o usuário via Evolution API.
    A API Evolution v2 mapeia isso no endpoint /message/sendMedia/{instance}.
    """
    number = normalize_whatsapp_number(user_id)
    if not number:
        return {"ok": False, "error": "Número/JID inválido ou vazio."}

    url = f"{_base_url()}/message/sendMedia/{_instance()}"
    log.info(f"[EVO] send_media → {url} number={number} type={mimetype}")

    payload = {
        "number": number,
        "mediatype": mediatype,
        "mimetype": mimetype,
        "caption": caption,
        "media": base64_media,
        "fileName": filename,
        "filename": filename  # Fallback property added to address known issue #2459
    }

    try:
        r = requests.post(
            url,
            json=payload,
            headers=_headers(),
            timeout=30
        )
        if r.status_code in (200, 201):
            return {"ok": True, "result": r.json()}
        else:
            log.error(f"[EVO] send_media error: {r.status_code} - {r.text}")
            return {"ok": False, "error": f"HTTP {r.status_code}", "raw": r.text}
    except Exception as e:
        log.error(f"[EVO] send_media exception: {e}")
        return {"ok": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO DE WEBHOOK
# ══════════════════════════════════════════════════════════════════

def set_webhook(webhook_url: str, events: list[str] | None = None) -> dict:
    """
    Configura o webhook da instância para receber eventos do WhatsApp.
    Compatível com Evolution API v1.x (formato com wrapper "webhook").
    """
    if events is None:
        events = ["MESSAGES_UPSERT", "CONNECTION_UPDATE", "SEND_MESSAGE"]

    url = f"{_base_url()}/webhook/set/{_instance()}"

    payload = {
        "webhook": {
            "enabled": True,
            "url": webhook_url,
            "events": events,
            "webhookByEvents": False,
            "webhookBase64": True,
        }
    }

    log.info(f"[EVO] set_webhook → {url} webhook_url={webhook_url} events={events}")

    try:
        r = requests.post(
            url,
            json=payload,
            headers=_headers(),
            timeout=30,
        )

        log.info(f"[EVO] set_webhook status={r.status_code} ok={r.ok} body={r.text[:500]}")

        return {
            "ok": r.ok,
            "status_code": r.status_code,
            "data": r.json() if r.content else {},
            "raw": r.text[:500] if not r.ok else "",
        }

    except requests.exceptions.ConnectionError:
        return {
            "ok": False,
            "error": "Não foi possível conectar à Evolution API. Verifique se o Docker está rodando.",
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
