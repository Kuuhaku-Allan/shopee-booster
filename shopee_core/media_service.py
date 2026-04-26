"""
shopee_core/media_service.py — Serviço de Edição de Imagens
============================================================
Ponte entre o WhatsApp Bot / API e as funções de imagem do backend_core.

Futuramente será a camada que gerencia undo/redo no Bot:
  - Recebe instrução de edição
  - Persiste step no bot_state.py
  - Retorna imagem processada

Por ora, expõe as operações de imagem de forma stateless.

Fase 4A.1:
  - Sessão rembg cacheada (u2netp)
  - Resize para 1024px (WhatsApp)
  - Logs detalhados
"""

from __future__ import annotations

import io
import base64
import logging
import time
import traceback
from typing import Any

from PIL import Image

log = logging.getLogger("media_service")

# Tamanho máximo para imagens no WhatsApp
MAX_SIDE_WHATSAPP = 1024

# Sessão rembg cacheada
_rembg_session = None


def _get_rembg_session():
    """Retorna sessão rembg cacheada (u2netp - modelo leve)."""
    global _rembg_session
    if _rembg_session is None:
        from rembg import new_session
        log.info("[REMBG] Criando nova sessão u2netp...")
        _rembg_session = new_session("u2netp")
        log.info("[REMBG] Sessão u2netp criada com sucesso")
    return _rembg_session


def _load_image_from_bytes(data: bytes) -> Image.Image:
    """Converte bytes em PIL.Image."""
    return Image.open(io.BytesIO(data)).convert("RGBA")


def _image_to_bytes(image: Image.Image, fmt: str = "PNG") -> bytes:
    """Converte PIL.Image em bytes."""
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return buf.getvalue()


def _image_to_base64(image: Image.Image, fmt: str = "PNG") -> str:
    """Converte PIL.Image em string base64 para transporte via JSON."""
    return base64.b64encode(_image_to_bytes(image, fmt)).decode("utf-8")


def _resize_for_whatsapp(img: Image.Image) -> Image.Image:
    """Redimensiona imagem para no máximo 1024px no lado maior."""
    if img.width <= MAX_SIDE_WHATSAPP and img.height <= MAX_SIDE_WHATSAPP:
        return img

    img = img.copy()
    img.thumbnail((MAX_SIDE_WHATSAPP, MAX_SIDE_WHATSAPP), Image.LANCZOS)
    log.info(f"[RESIZE] Imagem redimensionada para {img.size}")
    return img


# ══════════════════════════════════════════════════════════════
# OPERAÇÕES DISPONÍVEIS
# ══════════════════════════════════════════════════════════════

def remove_background(image_bytes: bytes) -> dict:
    """
    Remove o fundo da imagem.

    Returns:
        ok, message, image_b64 (base64 PNG), elapsed_seconds
    """
    start = time.time()

    try:
        from rembg import remove as rembg_remove

        log.info(f"[MEDIA] remove_background iniciado. bytes={len(image_bytes)}")

        img = _load_image_from_bytes(image_bytes)
        orig_size = img.size
        log.info(f"[MEDIA] Imagem carregada: size={orig_size}, mode={img.mode}")

        # Resize para WhatsApp (1024px)
        work = _resize_for_whatsapp(img.convert("RGB"))
        log.info(f"[MEDIA] Imagem redimensionada: {work.size}")

        buf = io.BytesIO()
        work.save(buf, format="PNG")
        img_bytes_for_rembg = buf.getvalue()
        log.info(f"[MEDIA] Bytes para rembg: {len(img_bytes_for_rembg)}")

        # Usa sessão cacheada
        session = _get_rembg_session()
        log.info("[MEDIA] Executando rembg remove()...")

        no_bg = rembg_remove(img_bytes_for_rembg, session=session)

        result = Image.open(io.BytesIO(no_bg)).convert("RGBA")
        log.info(f"[MEDIA] Resultado rembg: size={result.size}")

        # Redimensiona de volta se necessário
        if result.size != orig_size:
            result = result.resize(orig_size, Image.LANCZOS)
            log.info(f"[MEDIA] Redimensionado de volta para {orig_size}")

        elapsed = time.time() - start
        log.info(f"[MEDIA] remove_background finalizado em {elapsed:.2f}s")

        return {
            "ok": True,
            "message": "Fundo removido com sucesso.",
            "image_b64": _image_to_base64(result),
            "elapsed_seconds": elapsed,
        }

    except Exception as e:
        elapsed = time.time() - start
        log.error(f"[MEDIA] Erro em remove_background após {elapsed:.2f}s: {e}\n{traceback.format_exc()}")
        return {
            "ok": False,
            "message": f"Erro ao remover fundo: {e}",
            "image_b64": "",
            "elapsed_seconds": elapsed,
            "error_traceback": traceback.format_exc(),
        }


def generate_product_scene(image_bytes: bytes, segmento: str) -> dict:
    """
    Remove o fundo e compõe com um cenário IA gerado.

    Returns:
        ok, message, image_b64
    """
    try:
        from backend_core import (
            generate_ai_scenario,
            generate_gradient_background,
            apply_contact_shadow,
        )

        img = _load_image_from_bytes(image_bytes)

        # Remove fundo
        rb = remove_background(image_bytes)
        if rb["ok"]:
            fg_bytes = base64.b64decode(rb["image_b64"])
            fg = Image.open(io.BytesIO(fg_bytes)).convert("RGBA")
        else:
            fg = img

        prompt_map = {
            "Escolar / Juvenil": "minimalist white geometric podium soft lavender background",
            "Viagem":            "stone platform outdoors golden hour soft focus",
            "Profissional / Tech": "sleek white desk surface modern office lighting",
            "Moda":              "white marble floor fashion studio aesthetic",
        }
        prompt = prompt_map.get(segmento, "product photography studio white background soft lighting")

        bg = generate_ai_scenario(prompt, segmento)
        if not bg:
            bg = generate_gradient_background(segmento)
            msg = "Cenário gradiente gerado (APIs de imagem indisponíveis)."
        else:
            msg = "Cenário IA gerado com sucesso!"

        bg = bg.resize((1024, 1024)).convert("RGBA")
        fg_copy = fg.copy()
        fg_copy.thumbnail((800, 800))
        offset = (
            (bg.width - fg_copy.width) // 2,
            int((bg.height - fg_copy.height) * 0.6),
        )
        bg = apply_contact_shadow(bg, fg_copy, offset)
        bg.paste(fg_copy, offset, fg_copy)

        return {
            "ok": True,
            "message": msg,
            "image_b64": _image_to_base64(bg),
        }
    except Exception as e:
        return {"ok": False, "message": f"Erro ao gerar cenário: {e}", "image_b64": ""}


def creative_edit(
    image_bytes: bytes,
    instruction: str,
    full_context: str = "",
    segmento: str = "",
) -> dict:
    """
    Aplica uma edição criativa guiada por instrução em linguagem natural.

    Returns:
        ok, message, description, image_b64
    """
    try:
        from backend_core import creative_edit_with_vision

        img = _load_image_from_bytes(image_bytes)
        edited, description = creative_edit_with_vision(
            img, instruction, full_context, segmento
        )
        return {
            "ok": True,
            "message": "Edição aplicada.",
            "description": description,
            "image_b64": _image_to_base64(edited),
        }
    except Exception as e:
        return {
            "ok": False,
            "message": f"Erro na edição: {e}",
            "description": "",
            "image_b64": "",
        }


def analyze_image(
    image_bytes: bytes,
    user_message: str,
    product_context: str = "",
    segmento: str = "",
) -> dict:
    """
    Analisa a imagem com Gemini Vision e retorna feedback textual.
    """
    try:
        from backend_core import analyze_product_image_vision

        img = _load_image_from_bytes(image_bytes).convert("RGB")
        feedback = analyze_product_image_vision(
            img, user_message, product_context, segmento
        )
        return {"ok": True, "message": feedback}
    except Exception as e:
        return {"ok": False, "message": f"Erro na análise: {e}"}
