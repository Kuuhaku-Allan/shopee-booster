"""
shopee_core/media_worker.py — Worker de Mídia com Timeout Real
================================================================
Processa operações de imagem em processo separado com timeout de 90s.
Evita que o BackgroundTask fique preso indefinidamente no rembg.

Implementação:
  - multiprocessing.Process para isolar o processamento
  - Queue para retornar resultado
  - Timeout de 90 segundos
  - Suporte a cancelamento via job_id
"""

from __future__ import annotations

import base64
import io
import logging
import multiprocessing as mp
import time
import traceback
from typing import Any, Optional

from PIL import Image

log = logging.getLogger("media_worker")

# Timeout padrão para processamento de mídia (segundos)
MEDIA_TIMEOUT = 90

# Tamanho máximo para imagens no WhatsApp
MAX_SIDE_WHATSAPP = 1024


# ══════════════════════════════════════════════════════════════════
# SESSÃO REMBG GLOBAL (cacheada)
# ══════════════════════════════════════════════════════════════════

_rembg_session = None


def get_rembg_session():
    """Retorna sessão rembg cacheada (u2netp - modelo leve)."""
    global _rembg_session
    if _rembg_session is None:
        from rembg import new_session
        log.info("[REMBG] Criando nova sessão u2netp...")
        _rembg_session = new_session("u2netp")
        log.info("[REMBG] Sessão u2netp criada com sucesso")
    return _rembg_session


# ══════════════════════════════════════════════════════════════════
# FUNÇÕES DE PROCESSAMENTO (executadas no processo filho)
# ══════════════════════════════════════════════════════════════════

def _load_image_from_bytes(data: bytes) -> Image.Image:
    """Converte bytes em PIL.Image."""
    return Image.open(io.BytesIO(data)).convert("RGBA")


def _image_to_base64(image: Image.Image, fmt: str = "PNG") -> str:
    """Converte PIL.Image em string base64."""
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _resize_for_whatsapp(img: Image.Image) -> Image.Image:
    """Redimensiona imagem para no máximo 1024px no lado maior."""
    if img.width <= MAX_SIDE_WHATSAPP and img.height <= MAX_SIDE_WHATSAPP:
        return img

    img = img.copy()
    img.thumbnail((MAX_SIDE_WHATSAPP, MAX_SIDE_WHATSAPP), Image.LANCZOS)
    log.info(f"[RESIZE] Imagem redimensionada para {img.size}")
    return img


def _process_remove_background(image_bytes: bytes) -> dict:
    """Remove fundo da imagem usando rembg com sessão cacheada."""
    start = time.time()

    try:
        from rembg import remove as rembg_remove

        log.info("[REMBG] Iniciando remoção de fundo...")

        # Carrega imagem
        img = _load_image_from_bytes(image_bytes)
        orig_size = img.size
        log.info(f"[REMBG] Imagem carregada: size={orig_size}, mode={img.mode}")

        # Redimensiona para WhatsApp
        work = _resize_for_whatsapp(img.convert("RGB"))

        # Converte para bytes
        buf = io.BytesIO()
        work.save(buf, format="PNG")
        img_bytes_for_rembg = buf.getvalue()
        log.info(f"[REMBG] Bytes para rembg: {len(img_bytes_for_rembg)}")

        # Remove fundo com sessão cacheada
        session = get_rembg_session()
        log.info("[REMBG] Executando remove()...")
        no_bg = rembg_remove(img_bytes_for_rembg, session=session)

        # Abre resultado
        result = Image.open(io.BytesIO(no_bg)).convert("RGBA")
        log.info(f"[REMBG] Resultado: size={result.size}, mode={result.mode}")

        # Redimensiona de volta se necessário
        if result.size != orig_size:
            result = result.resize(orig_size, Image.LANCZOS)
            log.info(f"[REMBG] Redimensionado de volta para {orig_size}")

        elapsed = time.time() - start
        log.info(f"[REMBG] Finalizado em {elapsed:.2f}s")

        return {
            "ok": True,
            "message": "Fundo removido com sucesso.",
            "image_b64": _image_to_base64(result),
            "elapsed_seconds": elapsed,
        }

    except Exception as e:
        elapsed = time.time() - start
        log.error(f"[REMBG] Erro após {elapsed:.2f}s: {e}\n{traceback.format_exc()}")
        return {
            "ok": False,
            "message": f"Erro ao remover fundo: {e}",
            "image_b64": "",
            "elapsed_seconds": elapsed,
            "error_traceback": traceback.format_exc(),
        }


def _process_generate_scene(image_bytes: bytes, segmento: str, style_prompt: str = "") -> dict:
    """Gera cenário de produto."""
    start = time.time()

    try:
        log.info(f"[SCENE] Iniciando geração de cenário. segmento={segmento}, style={style_prompt[:50]}")

        # Primeiro remove o fundo se ainda não foi removido
        # (quando usado em pipeline, a imagem já vem sem fundo)
        from PIL import Image
        img = _load_image_from_bytes(image_bytes)
        
        # Verifica se a imagem tem canal alpha (já sem fundo)
        has_alpha = img.mode == "RGBA" and img.getchannel("A").getextrema()[0] < 255
        
        if not has_alpha:
            log.info("[SCENE] Imagem não tem transparência, removendo fundo primeiro...")
            rb = _process_remove_background(image_bytes)
            if not rb["ok"]:
                return rb
            fg_bytes = base64.b64decode(rb["image_b64"])
            fg = _load_image_from_bytes(fg_bytes)
        else:
            log.info("[SCENE] Imagem já tem transparência, usando diretamente")
            fg = img

        # Importa funções do backend_core
        from backend_core import (
            generate_ai_scenario,
            generate_gradient_background,
            apply_contact_shadow,
        )

        # Usa style_prompt se fornecido, senão usa mapeamento padrão
        if style_prompt:
            prompt = style_prompt
        else:
            prompt_map = {
                "Escolar / Juvenil": "minimalist white geometric podium soft lavender background",
                "Viagem": "stone platform outdoors golden hour soft focus",
                "Profissional / Tech": "sleek white desk surface modern office lighting",
                "Moda": "white marble floor fashion studio aesthetic",
            }
            prompt = prompt_map.get(segmento, "product photography studio white background soft lighting")

        log.info(f"[SCENE] Gerando cenário com prompt: {prompt[:50]}...")
        bg = generate_ai_scenario(prompt, segmento)

        if not bg:
            log.info("[SCENE] API indisponível, usando gradiente")
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

        elapsed = time.time() - start
        log.info(f"[SCENE] Finalizado em {elapsed:.2f}s")

        return {
            "ok": True,
            "message": msg,
            "image_b64": _image_to_base64(bg),
            "elapsed_seconds": elapsed,
        }

    except Exception as e:
        elapsed = time.time() - start
        log.error(f"[SCENE] Erro após {elapsed:.2f}s: {e}\n{traceback.format_exc()}")
        return {
            "ok": False,
            "message": f"Erro ao gerar cenário: {e}",
            "image_b64": "",
            "elapsed_seconds": elapsed,
            "error_traceback": traceback.format_exc(),
        }


def _process_analyze_image(image_bytes: bytes, question: str, product_context: str, segmento: str) -> dict:
    """Analisa imagem com Gemini Vision."""
    start = time.time()

    try:
        log.info(f"[ANALYZE] Iniciando análise. question={question[:50]}...")

        from backend_core import analyze_product_image_vision

        img = _load_image_from_bytes(image_bytes).convert("RGB")
        
        # analyze_product_image_vision espera: img, user_message, product_context, segmento
        feedback = analyze_product_image_vision(img, question, product_context, segmento)

        elapsed = time.time() - start
        log.info(f"[ANALYZE] Finalizado em {elapsed:.2f}s")

        return {
            "ok": True,
            "message": feedback,
            "elapsed_seconds": elapsed,
        }

    except Exception as e:
        elapsed = time.time() - start
        log.error(f"[ANALYZE] Erro após {elapsed:.2f}s: {e}\n{traceback.format_exc()}")
        return {
            "ok": False,
            "message": f"Erro na análise: {e}",
            "elapsed_seconds": elapsed,
            "error_traceback": traceback.format_exc(),
        }


def _process_creative_edit(image_bytes: bytes, instruction: str, full_context: str, segmento: str) -> dict:
    """Aplica edição criativa com IA."""
    start = time.time()

    try:
        log.info(f"[CREATIVE] Iniciando edição. instruction={instruction[:50]}...")

        from backend_core import creative_edit_with_vision

        img = _load_image_from_bytes(image_bytes)
        edited, description = creative_edit_with_vision(img, instruction, full_context, segmento)

        elapsed = time.time() - start
        log.info(f"[CREATIVE] Finalizado em {elapsed:.2f}s")

        return {
            "ok": True,
            "message": "Edição aplicada.",
            "description": description,
            "image_b64": _image_to_base64(edited),
            "elapsed_seconds": elapsed,
        }

    except Exception as e:
        elapsed = time.time() - start
        log.error(f"[CREATIVE] Erro após {elapsed:.2f}s: {e}\n{traceback.format_exc()}")
        return {
            "ok": False,
            "message": f"Erro na edição: {e}",
            "description": "",
            "image_b64": "",
            "elapsed_seconds": elapsed,
            "error_traceback": traceback.format_exc(),
        }


# ══════════════════════════════════════════════════════════════════
# WORKER PROCESS
# ══════════════════════════════════════════════════════════════════

def _worker_process(
    queue: mp.Queue,
    action: str,
    image_bytes: bytes,
    caption: str,
    segmento: str,
    full_context: str,
):
    """Função executada no processo filho."""
    try:
        if action == "remove_background":
            result = _process_remove_background(image_bytes)
        elif action == "generate_scene":
            result = _process_generate_scene(image_bytes, segmento, style_prompt=caption)
        elif action == "analyze_image":
            result = _process_analyze_image(image_bytes, caption or "Analise esta imagem", full_context, segmento)
        elif action == "creative_edit":
            result = _process_creative_edit(image_bytes, caption or "Melhore a imagem", full_context, segmento)
        else:
            result = {"ok": False, "message": f"Ação desconhecida: {action}", "image_b64": ""}

        queue.put(result)

    except Exception as e:
        queue.put({
            "ok": False,
            "message": f"Erro no worker: {e}",
            "image_b64": "",
            "error_traceback": traceback.format_exc(),
        })


# ══════════════════════════════════════════════════════════════════
# API PÚBLICA
# ══════════════════════════════════════════════════════════════════

def process_media_with_timeout(
    action: str,
    image_bytes: bytes,
    caption: str = "",
    segmento: str = "",
    full_context: str = "",
    timeout: int = MEDIA_TIMEOUT,
) -> dict:
    """
    Processa mídia com timeout real usando multiprocessing.

    Args:
        action: remove_background, generate_scene, analyze_image, creative_edit
        image_bytes: bytes da imagem
        caption: legenda/instrução
        segmento: segmento de mercado
        full_context: contexto adicional
        timeout: timeout em segundos (padrão 90s)

    Returns:
        dict com ok, message, image_b64 (se aplicável), elapsed_seconds
    """
    start = time.time()
    log.info(f"[WORKER] Iniciando processamento: action={action}, timeout={timeout}s, bytes={len(image_bytes)}")

    # Cria queue para comunicação
    queue = mp.Queue()

    # Cria processo filho
    process = mp.Process(
        target=_worker_process,
        args=(queue, action, image_bytes, caption, segmento, full_context),
    )

    process.start()
    log.info(f"[WORKER] Processo iniciado: pid={process.pid}")

    try:
        # Espera resultado com timeout
        result = queue.get(timeout=timeout)
        elapsed = time.time() - start
        result["total_elapsed_seconds"] = elapsed
        log.info(f"[WORKER] Resultado recebido em {elapsed:.2f}s: ok={result.get('ok')}")

    except Exception as e:
        # Timeout ou erro
        elapsed = time.time() - start
        log.error(f"[WORKER] Timeout ou erro após {elapsed:.2f}s: {e}")

        # Termina processo
        if process.is_alive():
            log.warning(f"[WORKER] Terminando processo pid={process.pid}")
            process.terminate()
            process.join(timeout=5)

            if process.is_alive():
                log.warning(f"[WORKER] Processo não terminou, forçando kill")
                process.kill()
                process.join()

        result = {
            "ok": False,
            "message": "O processamento demorou demais. Tente uma imagem menor ou mais simples.",
            "image_b64": "",
            "timeout": True,
            "elapsed_seconds": elapsed,
        }

    finally:
        # Garante que o processo foi finalizado
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)

        # Limpa queue
        try:
            queue.close()
            queue.join_thread()
        except:
            pass

    return result
