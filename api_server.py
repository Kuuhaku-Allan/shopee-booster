"""
api_server.py — FastAPI do Shopee Booster Bot
==============================================
Servidor HTTP que expõe o shopee_core como API REST.

Interfaces que vão consumir esta API:
  - WhatsApp Bot via Evolution API (webhook POST /webhook/evolution)
  - .exe (para locks de Sentinela e futura sincronização)

Como iniciar (desenvolvimento):
    uvicorn api_server:app --reload --port 8787

Como iniciar (produção):
    uvicorn api_server:app --host 0.0.0.0 --port 8787 --workers 2

Fases implementadas:
  v0.1.0 — health, chat, audit, sentinel
  v0.2.0 — webhook Evolution API, endpoints de mídia, sessões
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from fastapi import FastAPI, BackgroundTasks, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from shopee_core.types import (
    ChatRequest,
    AuditRequest,
    SentinelLockRequest,
    SentinelFinishRequest,
)
from shopee_core.chatbot_service import run_chatbot_turn
from shopee_core.audit_service import (
    load_shop_from_url,
    generate_product_optimization,
    list_products_summary,
)
from shopee_core.sentinel_service import (
    request_sentinel_execution,
    mark_sentinel_finished,
    check_sentinel_status,
)
from shopee_core.whatsapp_service import (
    extract_evolution_message,
    handle_whatsapp_text,
    format_optimization_result,
)
from shopee_core.media_service import (
    remove_background,
    generate_product_scene,
    creative_edit,
    analyze_image,
)
from shopee_core.session_service import get_all_active_sessions, save_session, clear_session
from shopee_core.audit_service import generate_product_optimization, load_shop_from_url
from shopee_core.evolution_client import (
    send_text as evo_send_text,
    set_webhook as evo_set_webhook,
    instance_status as evo_instance_status,
)
from shopee_core.config import load_app_config

# ── Configuração de logging ────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("shopee_api")

# ── App ────────────────────────────────────────────────────────────
app = FastAPI(
    title="Shopee Booster Bot API",
    description=(
        "Núcleo compartilhado do ShopeeBooster exposto como API REST. "
        "Consumido pelo .exe (para locks de Sentinela) e pelo futuro Bot de WhatsApp."
    ),
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — liberado para desenvolvimento local; restringir em produção
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ══════════════════════════════════════════════════════════════════

@app.get("/health", tags=["Status"])
def health():
    """Verifica se o serviço está respondendo."""
    return {
        "ok": True,
        "service": "shopee-booster-bot-api",
        "version": "0.2.0",
    }


# ══════════════════════════════════════════════════════════════════
# CHAT
# ══════════════════════════════════════════════════════════════════

@app.post("/chat", tags=["Chat"])
def chat(req: ChatRequest):
    """
    Processa uma mensagem do usuário e retorna a resposta do assistente.

    Suporta múltiplos intents: FAQ, otimização, análise de imagem etc.
    Nota: para intents que precisam de imagem (remove_bg, generate_scene),
    envie has_media=True e passe o caminho local via media_path (fase futura).
    """
    log.info(f"/chat user_id={req.user_id} intent=? message={req.message[:60]!r}")
    try:
        result = run_chatbot_turn(
            user_message=req.message,
            segmento=req.segmento,
            chat_history=req.chat_history,
            full_context=req.full_context,
            attachments=[],
            attachment_types=[],
            selected_product=req.selected_product,
        )
        log.info(f"/chat intent={result.get('intent')} ok=True")
        return result
    except Exception as e:
        log.error(f"/chat ERRO: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno no chat: {e}",
        )


# ══════════════════════════════════════════════════════════════════
# AUDITORIA
# ══════════════════════════════════════════════════════════════════

@app.post("/audit/load-shop", tags=["Auditoria"])
def audit_load_shop(req: AuditRequest):
    """
    Carrega os dados e produtos de uma loja Shopee.

    Retorna: username, shop_data, lista de produtos.
    Esse endpoint é o primeiro passo do fluxo de auditoria no WhatsApp:
    o bot chama aqui e apresenta a lista numerada de produtos ao usuário.
    """
    log.info(f"/audit/load-shop user_id={req.user_id} url={req.shop_url!r}")
    try:
        result = load_shop_from_url(req.shop_url)
        if result["ok"]:
            # Injeta resumo compacto para facilitar apresentação no WhatsApp
            result["data"]["products_summary"] = list_products_summary(
                result["data"].get("products", [])
            )
        return result
    except Exception as e:
        log.error(f"/audit/load-shop ERRO: {e}")
        raise HTTPException(500, detail=str(e))


@app.post("/audit/optimize-selected", tags=["Auditoria"])
def audit_optimize_selected(req: AuditRequest):
    """
    Executa a otimização completa para um produto específico.

    Fluxo:
      1. Carrega a loja (Playwright)
      2. Seleciona o produto pelo índice
      3. Busca concorrentes + avaliações
      4. Gera listing otimizado com Gemini

    Esta operação pode levar de 30s a 3 minutos (Playwright + Gemini).
    Para uso no WhatsApp, considere chamar via BackgroundTasks e
    notificar o usuário quando concluir.
    """
    log.info(
        f"/audit/optimize-selected user_id={req.user_id} "
        f"url={req.shop_url!r} index={req.product_index}"
    )
    try:
        loaded = load_shop_from_url(req.shop_url)

        if not loaded["ok"]:
            return loaded

        products = loaded["data"].get("products", [])

        if not products:
            return {
                "ok": False,
                "message": "Nenhum produto encontrado nessa loja.",
                "data": {},
            }

        index = req.product_index if req.product_index is not None else 0

        if index < 0 or index >= len(products):
            return {
                "ok": False,
                "message": (
                    f"Índice {index} inválido. "
                    f"A loja tem {len(products)} produto(s) (0 a {len(products)-1})."
                ),
                "data": {"products_summary": list_products_summary(products)},
            }

        product = products[index]
        return generate_product_optimization(product, req.segmento)

    except Exception as e:
        log.error(f"/audit/optimize-selected ERRO: {e}")
        raise HTTPException(500, detail=str(e))


# ══════════════════════════════════════════════════════════════════
# SENTINELA — Lock de execução
# ══════════════════════════════════════════════════════════════════

@app.post("/sentinel/lock", tags=["Sentinela"])
def sentinel_lock(req: SentinelLockRequest):
    """
    Tenta adquirir o lock para executar o Sentinela nessa janela.

    Retorna ok=True se este executor pode rodar.
    Retorna ok=False se outro executor já tem o lock.

    Use este endpoint ANTES de rodar o Sentinela — tanto no .exe
    quanto no WhatsApp Bot.
    """
    log.info(
        f"/sentinel/lock loja={req.loja_id!r} kw={req.keyword!r} "
        f"janela={req.janela_execucao!r} executor={req.executor!r}"
    )
    return request_sentinel_execution(
        loja_id=req.loja_id,
        keyword=req.keyword,
        janela_execucao=req.janela_execucao,
        executor=req.executor,
    )


@app.post("/sentinel/finish", tags=["Sentinela"])
def sentinel_finish(req: SentinelFinishRequest):
    """
    Marca a execução do Sentinela como concluída.
    Chamar após terminar o scraping, com status='done' ou 'error'.
    """
    log.info(
        f"/sentinel/finish loja={req.loja_id!r} kw={req.keyword!r} "
        f"janela={req.janela_execucao!r} status={req.status!r}"
    )
    return mark_sentinel_finished(
        loja_id=req.loja_id,
        keyword=req.keyword,
        janela_execucao=req.janela_execucao,
        status=req.status,
    )


@app.get("/sentinel/status", tags=["Sentinela"])
def sentinel_status(loja_id: str, keyword: str, janela_execucao: str):
    """
    Consulta o status do lock de uma janela de execução.
    Útil para o .exe verificar se o WhatsApp Bot já rodou.
    """
    return check_sentinel_status(
        loja_id=loja_id,
        keyword=keyword,
        janela_execucao=janela_execucao,
    )


# ══════════════════════════════════════════════════════════════════
# WHATSAPP — Webhook da Evolution API
# ══════════════════════════════════════════════════════════════════

@app.post("/webhook/evolution", tags=["WhatsApp"])
def evolution_webhook(payload: dict, background_tasks: BackgroundTasks):
    """
    Recebe eventos da Evolution API (MESSAGES_UPSERT etc.) e envia a resposta
    de volta ao usuário via Evolution API (send_text).

    Fluxo completo (Fase 3B/3C):
      WhatsApp → Evolution API → POST /webhook/evolution
        → extract_evolution_message()
        → handle_whatsapp_text()           ← lógica do bot
        → type="text"    → evo_send_text() imediato
        → type="background_task" → envia "aguarde" + agenda otimização
    """
    msg = extract_evolution_message(payload)

    log.info(
        f"/webhook/evolution event={msg['event']!r} "
        f"user={msg['user_id']!r} from_me={msg['from_me']} "
        f"text={msg['text'][:60]!r}"
    )

    # Ignora mensagens enviadas pelo próprio bot (evita loops de auto-resposta)
    if msg["from_me"]:
        return {"ok": True, "ignored": True, "reason": "from_me"}

    # Ignora eventos sem texto (stickers, chamadas, status etc.)
    if not msg["text"]:
        has_media = msg.get("has_media", False)
        reason = "media_not_supported_yet" if has_media else "empty_text"
        return {"ok": True, "ignored": True, "reason": reason}

    # ── Processa a mensagem e obtém a resposta do bot ─────────────
    try:
        response = handle_whatsapp_text(
            user_id=msg["user_id"],
            text=msg["text"],
        )
    except Exception as e:
        log.error(f"/webhook/evolution ERRO no roteador: {e}\n{traceback.format_exc()}")
        return {
            "ok": False,
            "error": str(e),
            "received": {"user_id": msg["user_id"], "text": msg["text"]},
        }

    log.info(
        f"/webhook/evolution resposta type={response.get('type')!r} "
        f"len={len(response.get('text', ''))}"
    )

    # ── Envia a resposta pelo WhatsApp ───────────────────────────
    send_result = None

    if response.get("type") == "background_task":
        task = response.get("task")
        wait_text = response.get("text", "⏳ Processando...")

        # Envia a mensagem de "aguarde" imediatamente para o usuário
        try:
            send_result = evo_send_text(user_id=msg["user_id"], text=wait_text)
        except Exception as e:
            send_result = {"ok": False, "error": str(e)}

        if task == "load_shop":
            background_tasks.add_task(
                _run_load_shop_bg,
                user_id=response["user_id"],
                shop_url=response["shop_url"],
                segmento=response["segmento"],
            )
            log.info(f"[BG] Carregamento de loja agendado para user={msg['user_id']!r}")

        elif task == "optimize_product":
            background_tasks.add_task(
                _run_optimization_bg,
                user_id=response["user_id"],
                product=response["product"],
                segmento=response["segmento"],
            )
            log.info(f"[BG] Otimização agendada para user={msg['user_id']!r}")

        else:
            log.warning(f"[BG] Tipo de background_task desconhecido: {task!r}")

    elif response.get("type") == "text" and response.get("text"):
        try:
            send_result = evo_send_text(
                user_id=msg["user_id"],
                text=response["text"],
            )
            if send_result.get("ok"):
                log.info("[EVO] Mensagem enviada com sucesso")
            else:
                log.warning(f"[EVO] Falha no envio: {send_result}")
        except Exception as e:
            log.error(f"[EVO] Exceção ao enviar mensagem: {e}")
            send_result = {"ok": False, "error": str(e)}

    return {
        "ok": True,
        "received": {
            "event": msg["event"],
            "user_id": msg["user_id"],
            "text": msg["text"],
        },
        "response": {k: v for k, v in response.items() if k != "product"},  # omite dados grandes
        "send_result": send_result,
    }


def _run_load_shop_bg(user_id: str, shop_url: str, segmento: str):
    """
    Background task: carrega produtos da loja e envia a lista pelo WhatsApp.
    Roda fora do ciclo de request/response do FastAPI.
    """
    log.info(f"[BG] Carregando loja: url={shop_url!r} user={user_id}")

    try:
        loaded = load_shop_from_url(shop_url)
    except Exception as e:
        log.error(f"[BG] Exceção ao carregar loja: {e}")
        loaded = {"ok": False, "message": str(e)}

    if not loaded.get("ok"):
        clear_session(user_id)
        msg = (
            f"❌ Não consegui carregar a loja.\n"
            f"Erro: {loaded.get('message', 'desconhecido')}\n\n"
            "Certifique-se de usar o formato: https://shopee.com.br/nome_da_loja\n"
            "Envie */auditar* para tentar novamente."
        )
        try:
            evo_send_text(user_id=user_id, text=msg)
        except Exception as e:
            log.error(f"[BG] Falha ao enviar erro de loja: {e}")
        return

    products = loaded["data"].get("products", [])
    username = loaded["data"].get("username", "loja")

    if not products:
        clear_session(user_id)
        try:
            evo_send_text(
                user_id=user_id,
                text=f"⚠️ A loja *{username}* foi encontrada, mas não há produtos visíveis no momento."
            )
        except Exception as e:
            log.error(f"[BG] Falha ao enviar aviso de loja vazia: {e}")
        return

    # Salva sessao com produtos carregados
    save_session(
        user_id,
        "awaiting_product_index",
        {
            "shop_url": shop_url,
            "username": username,
            "products": products,
            "segmento": segmento,
        },
    )
    log.info(f"[BG] Loja '{username}' carregada: {len(products)} produtos. user={user_id}")

    # Monta e envia a lista de produtos
    from shopee_core.whatsapp_service import _product_list_message, MAX_PRODUCTS_LISTED
    product_list = _product_list_message(products)
    total = len(products)
    shown = min(total, MAX_PRODUCTS_LISTED)
    suffix = f"(mostrando os primeiros {shown})" if total > shown else ""

    msg = (
        f"✅ Loja *{username}* carregada com *{total}* produto(s). {suffix}\n\n"
        f"{product_list}\n\n"
        "Escolha o número do produto que deseja otimizar. Ex: *0*"
    )
    try:
        send_result = evo_send_text(user_id=user_id, text=msg)
        log.info(f"[BG] Lista de produtos enviada: ok={send_result.get('ok')}")
    except Exception as e:
        log.error(f"[BG] Falha ao enviar lista de produtos: {e}")


def _run_optimization_bg(user_id: str, product: dict, segmento: str):
    """
    Background task: executa otimização completa e envia resultado pelo WhatsApp.
    Roda fora do ciclo de request/response do FastAPI.
    """
    product_name = product.get("name", "Produto")
    log.info(f"[BG] Iniciando otimização: '{product_name}' user={user_id}")

    try:
        result = generate_product_optimization(product, segmento=segmento)
        message = format_optimization_result(result, product_name)
    except Exception as e:
        log.error(f"[BG] Erro na otimização: {e}")
        message = (
            f"❌ Ocorreu um erro durante a otimização de *{product_name[:50]}*.\n"
            "Tente novamente com */auditar*."
        )
    finally:
        # Garante que a sessão sai do estado 'processing' mesmo com erro
        clear_session(user_id)
        log.info(f"[BG] Sessão 'processing' limpa para user={user_id}")

    # Envia o resultado de volta para o usuário
    try:
        send_result = evo_send_text(user_id=user_id, text=message)
        log.info(f"[BG] Resultado enviado: ok={send_result.get('ok')}")
    except Exception as e:
        log.error(f"[BG] Falha ao enviar resultado: {e}")


# ══════════════════════════════════════════════════════════════════
# MÍDIA — Operações de imagem via API
# ══════════════════════════════════════════════════════════════════

from fastapi import UploadFile, File, Form


@app.post("/media/remove-background", tags=["Mídia"])
async def media_remove_background(file: UploadFile = File(...)):
    """
    Remove o fundo de uma imagem.
    Retorna a imagem processada em base64 (PNG).
    """
    log.info(f"/media/remove-background filename={file.filename!r}")
    try:
        image_bytes = await file.read()
        return remove_background(image_bytes)
    except Exception as e:
        log.error(f"/media/remove-background ERRO: {e}")
        raise HTTPException(500, detail=str(e))


@app.post("/media/generate-scene", tags=["Mídia"])
async def media_generate_scene(
    file: UploadFile = File(...),
    segmento: str = Form(default="Escolar / Juvenil"),
):
    """
    Gera um cenário de e-commerce para o produto.
    Remove o fundo e compõe com background gerado por IA.
    """
    log.info(f"/media/generate-scene filename={file.filename!r} segmento={segmento!r}")
    try:
        image_bytes = await file.read()
        return generate_product_scene(image_bytes, segmento)
    except Exception as e:
        log.error(f"/media/generate-scene ERRO: {e}")
        raise HTTPException(500, detail=str(e))


@app.post("/media/creative-edit", tags=["Mídia"])
async def media_creative_edit(
    file: UploadFile = File(...),
    instruction: str = Form(...),
    segmento: str = Form(default=""),
    full_context: str = Form(default=""),
):
    """
    Aplica edição criativa guiada por instrução em linguagem natural.
    Exemplos: 'adicione um badge azul', 'mude para fundo branco', 'coloque sombra'.
    """
    log.info(
        f"/media/creative-edit filename={file.filename!r} "
        f"instruction={instruction[:60]!r}"
    )
    try:
        image_bytes = await file.read()
        return creative_edit(image_bytes, instruction, full_context, segmento)
    except Exception as e:
        log.error(f"/media/creative-edit ERRO: {e}")
        raise HTTPException(500, detail=str(e))


@app.post("/media/analyze", tags=["Mídia"])
async def media_analyze(
    file: UploadFile = File(...),
    question: str = Form(default="Analise esta imagem de produto."),
    segmento: str = Form(default=""),
    product_context: str = Form(default=""),
):
    """
    Analisa uma imagem de produto com Gemini Vision.
    Retorna feedback textual com nota, pontos fortes e melhorias sugeridas.
    """
    log.info(
        f"/media/analyze filename={file.filename!r} "
        f"question={question[:60]!r}"
    )
    try:
        image_bytes = await file.read()
        return analyze_image(image_bytes, question, product_context, segmento)
    except Exception as e:
        log.error(f"/media/analyze ERRO: {e}")
        raise HTTPException(500, detail=str(e))


# ══════════════════════════════════════════════════════════════════
# SESSÕES — Diagnóstico e monitoramento
# ══════════════════════════════════════════════════════════════════

@app.get("/sessions/active", tags=["Sessões"])
def sessions_active():
    """
    Lista todas as sessões WhatsApp ativas (state != 'idle').
    Útil para debug e monitoramento do bot.
    """
    sessions = get_all_active_sessions()
    return {
        "ok": True,
        "count": len(sessions),
        "sessions": sessions,
    }


# ══════════════════════════════════════════════════════════════════
# EVOLUTION API — Setup e diagnóstico
# ══════════════════════════════════════════════════════════════════

@app.post("/evolution/setup-webhook", tags=["WhatsApp"])
def evolution_setup_webhook():
    """
    Configura a Evolution API para enviar eventos de mensagem para este servidor.

    URL configurada: {SHOPEE_API_PUBLIC_URL}/webhook/evolution
    Padrão de desenvolvimento: http://host.docker.internal:8787/webhook/evolution

    Execute este endpoint UMA VEZ após subir o Docker da Evolution API.
    """
    cfg = load_app_config()
    public_base = (
        cfg.get("shopee_api_public_url")
        or "http://host.docker.internal:8787"
    )
    webhook_url = public_base.rstrip("/") + "/webhook/evolution"

    log.info(f"/evolution/setup-webhook → configurando para {webhook_url!r}")
    try:
        result = evo_set_webhook(webhook_url)
    except ValueError as e:
        return {"ok": False, "error": str(e), "hint": "Configure EVOLUTION_API_URL, EVOLUTION_API_KEY e WHATSAPP_INSTANCE no .shopee_config"}

    return {
        "ok": result.get("ok", False),
        "webhook_url": webhook_url,
        "result": result,
    }


@app.get("/evolution/instance-status", tags=["WhatsApp"])
def evolution_instance_status_endpoint():
    """
    Verifica o status de conexão da instância WhatsApp.
    Retorna 'open', 'connecting' ou 'close'.
    Retorna error amigável se a Evolution API não estiver configurada/rodando.
    """
    try:
        return evo_instance_status()
    except ValueError as e:
        return {"ok": False, "state": "not_configured", "error": str(e), "hint": "Configure EVOLUTION_API_URL, EVOLUTION_API_KEY e WHATSAPP_INSTANCE no .shopee_config"}


@app.post("/evolution/test-send", tags=["WhatsApp"])
def evolution_test_send(
    number: str,
    text: str = "Teste do ShopeeBooster — se você recebeu isso, está tudo funcionando! 🚀",
):
    """
    Envia uma mensagem de texto diretamente para um número.
    Use ANTES de testar o webhook completo, para confirmar que a
    Evolution API está acessível e a instância está conectada.

    Parâmetros (query string):
        number — número com DDI, ex: 5511999999999
        text   — texto a enviar (opcional)

    Exemplo:
        POST /evolution/test-send?number=5511999999999
    """
    log.info(f"/evolution/test-send number={number!r}")
    try:
        return evo_send_text(user_id=number, text=text)
    except ValueError as e:
        return {"ok": False, "error": str(e), "hint": "Configure EVOLUTION_API_URL, EVOLUTION_API_KEY e WHATSAPP_INSTANCE no .shopee_config"}
