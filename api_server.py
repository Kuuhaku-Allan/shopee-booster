"""
api_server.py — FastAPI do Shopee Booster Bot
==============================================
Servidor HTTP que expõe o shopee_core como API REST.

Interfaces que vão consumir esta API:
  - Future WhatsApp Bot (Evolution API / Baileys webhook)
  - Opcionalmente: o .exe para sincronização de locks e histórico

Como iniciar (desenvolvimento):
    uvicorn api_server:app --reload --port 8787

Como iniciar (produção):
    uvicorn api_server:app --host 0.0.0.0 --port 8787 --workers 2
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
    version="0.1.0",
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
        "version": "0.1.0",
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
