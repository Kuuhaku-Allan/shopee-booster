"""
shopee_core/media_service.py — Serviço de Edição de Imagens
============================================================
Ponte entre o WhatsApp Bot / API e as funções de imagem do backend_core.

Futuramente será a camada que gerencia undo/redo no Bot:
  - Recebe instrução de edição
  - Persiste step no bot_state.py
  - Retorna imagem processada

Por ora, expõe as operações de imagem de forma stateless.
"""

from __future__ import annotations

import io
import base64
from typing import Any

from PIL import Image


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


# ══════════════════════════════════════════════════════════════
# OPERAÇÕES DISPONÍVEIS
# ══════════════════════════════════════════════════════════════

def remove_background(image_bytes: bytes) -> dict:
    """
    Remove o fundo da imagem.

    Returns:
        ok, message, image_b64 (base64 PNG)
    """
    try:
        from rembg import remove as rembg_remove
        img = _load_image_from_bytes(image_bytes)

        # Resize preventivo (igual ao backend_core)
        orig_size = img.size
        work = img.convert("RGB")
        MAX_SIDE = 1280
        if work.width > MAX_SIDE or work.height > MAX_SIDE:
            work = work.copy()
            work.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)

        buf = io.BytesIO()
        work.save(buf, format="PNG")
        no_bg = rembg_remove(buf.getvalue())
        result = Image.open(io.BytesIO(no_bg)).convert("RGBA")

        if result.size != orig_size:
            result = result.resize(orig_size, Image.LANCZOS)

        return {
            "ok": True,
            "message": "Fundo removido com sucesso.",
            "image_b64": _image_to_base64(result),
        }
    except Exception as e:
        return {"ok": False, "message": f"Erro ao remover fundo: {e}", "image_b64": ""}


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
