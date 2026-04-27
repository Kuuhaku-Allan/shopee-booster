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
from datetime import datetime

from fastapi import FastAPI, BackgroundTasks, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from shopee_core.types import (
    ChatRequest,
    AuditRequest,
    SentinelLockRequest,
    SentinelFinishRequest,
)
from shopee_core.chatbot_service import run_chatbot_turn
# ── Funções de Auditoria e Mídia importadas sob demanda ──────────
from shopee_core.sentinel_service import (
    request_sentinel_execution,
    mark_sentinel_finished,
    check_sentinel_status,
)
from shopee_core.session_service import get_all_active_sessions, save_session, clear_session
from shopee_core.evolution_client import (
    send_text as evo_send_text,
    send_media as evo_send_media,
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
        from shopee_core.audit_service import load_shop_from_url, list_products_summary
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
        from shopee_core.audit_service import load_shop_from_url, list_products_summary, generate_product_optimization
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
        f"/sentinel/lock loja={req.loja_id!r} user={req.user_id!r} shop_uid={req.shop_uid!r} kw={req.keyword!r} "
        f"janela={req.janela_execucao!r} executor={req.executor!r}"
    )
    return request_sentinel_execution(
        loja_id=req.loja_id,
        user_id=req.user_id,
        shop_uid=req.shop_uid,
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
        f"/sentinel/finish loja={req.loja_id!r} user={req.user_id!r} shop_uid={req.shop_uid!r} kw={req.keyword!r} "
        f"janela={req.janela_execucao!r} status={req.status!r}"
    )
    return mark_sentinel_finished(
        loja_id=req.loja_id,
        user_id=req.user_id,
        shop_uid=req.shop_uid,
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
    from shopee_core.whatsapp_service import extract_evolution_message
    msg = extract_evolution_message(payload)

    log.info(
        f"/webhook/evolution event={msg['event']!r} "
        f"user={msg['user_id']!r} from_me={msg['from_me']} "
        f"has_media={msg['has_media']} media_type={msg.get('media_type')!r} "
        f"mimetype={msg.get('mimetype')!r} base64_len={len(msg.get('base64_data', ''))} "
        f"text={msg['text'][:60]!r}"
    )

    # Ignora mensagens enviadas pelo próprio bot (evita loops de auto-resposta)
    if msg["from_me"]:
        return {"ok": True, "ignored": True, "reason": "from_me"}

    # Ignora eventos sem texto E sem mídia (stickers, chamadas, status etc.)
    if not msg["text"] and not msg.get("has_media"):
        return {"ok": True, "ignored": True, "reason": "empty_text"}

    # ── Deduplicação de Mensagens (Fase 3E) ───────────────────────
    message_id = msg.get("message_id")
    if message_id:
        from shopee_core.session_service import is_message_processed, mark_message_processed
        if is_message_processed(message_id):
            log.info(f"/webhook/evolution IGNORADO duplicado: msg_id={message_id}")
            return {"ok": True, "ignored": True, "reason": "already_processed"}
        mark_message_processed(message_id, msg["user_id"])

    # ── Processa a mensagem e obtém a resposta do bot ─────────────
    try:
        from shopee_core.whatsapp_service import handle_whatsapp_message
        response = handle_whatsapp_message(msg)
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
                from_active_shop=response.get("from_active_shop", False),
                shop_name=response.get("shop_name", ""),
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

        elif task == "load_shop_for_sentinel":
            background_tasks.add_task(
                _run_load_shop_for_sentinel_bg,
                user_id=response["user_id"],
                shop_uid=response.get("shop_uid", ""),
                shop_url=response["shop_url"],
            )
            log.info(f"[BG] Carregamento de loja para Sentinela agendado: user={msg['user_id']!r}")

        elif task == "run_sentinel":
            background_tasks.add_task(
                _run_sentinel_bg,
                user_id=response["user_id"],
                config=response["config"],
            )
            log.info(f"[BG] Execução do Sentinela agendada: user={msg['user_id']!r}")

        elif task == "process_media":
            job_id = response.get("job_id", "")
            plan = response.get("plan", [])
            background_tasks.add_task(
                _run_media_bg,
                user_id=response["user_id"],
                msg=response["msg"],
                plan=plan,
                job_id=job_id,
            )
            log.info(f"[BG] Processamento de mídia agendado para user={msg['user_id']!r} plan={plan} job_id={job_id!r}")

        elif task == "import_catalog":
            background_tasks.add_task(
                _run_import_catalog_bg,
                user_id=response["user_id"],
                shop_uid=response["shop_uid"],
                shop_url=response["shop_url"],
                username=response["username"],
                base64_data=response["base64_data"],
                mimetype=response["mimetype"],
            )
            log.info(f"[BG] Importação de catálogo agendada: user={msg['user_id']!r} shop={response['username']}")

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


def _run_load_shop_bg(user_id: str, shop_url: str, segmento: str, from_active_shop: bool = False, shop_name: str = ""):
    """
    Background task: carrega produtos da loja e envia a lista pelo WhatsApp.
    Roda fora do ciclo de request/response do FastAPI.
    
    Estratégia (U6):
    1. Tentar scraping público
    2. Se falhar, buscar catálogo importado da loja ativa
    3. Se não houver catálogo, orientar importação
    """
    from shopee_core.audit_service import load_shop_from_url
    from shopee_core.user_config_service import get_active_shop
    from shopee_core.catalog_service import get_catalog, get_catalog_products
    
    log.info(f"[BG] Carregando loja: url={shop_url!r} user={user_id} from_active={from_active_shop}")

    try:
        loaded = load_shop_from_url(shop_url)
    except Exception as e:
        log.error(f"[BG] Exceção ao carregar loja: {e}")
        loaded = {"ok": False, "message": str(e)}

    products = []
    username = ""
    source = ""
    shop_uid = ""
    
    # Tenta scraping primeiro
    if loaded.get("ok"):
        products = loaded["data"].get("products", [])
        username = loaded["data"].get("username", "loja")
        shop_data = loaded["data"].get("shop", {})
        shop_uid = shop_data.get("shopid") or shop_data.get("shop_id") or ""
        
        if products:
            source = "scraping"
            log.info(f"[BG] Scraping bem-sucedido: {len(products)} produtos")
    
    # Se scraping falhou ou não retornou produtos, tenta catálogo
    if not products and from_active_shop:
        log.info(f"[BG] Scraping falhou, tentando catálogo da loja ativa...")
        
        active_shop = get_active_shop(user_id)
        
        if active_shop:
            shop_uid = active_shop.get("shop_uid")
            username = active_shop.get("display_name") or active_shop.get("username")
            
            catalog = get_catalog(user_id, shop_uid)
            
            if catalog:
                catalog_id = catalog["catalog_id"]
                products = get_catalog_products(catalog_id)
                source = "catalog"
                log.info(f"[BG] Catálogo encontrado: {len(products)} produtos")
    
    # Se ainda não tem produtos, falha
    if not products:
        clear_session(user_id)
        
        if from_active_shop:
            # Orienta importar catálogo
            msg = (
                f"⚠️ A loja *{shop_name or username}* foi encontrada, mas não consegui carregar os produtos.\n\n"
                f"💡 *Solução:* Importe o catálogo do Seller Center:\n"
                f"1. Use */catalogo importar*\n"
                f"2. Envie o arquivo XLSX/CSV da sua loja\n"
                f"3. Depois use */auditar* novamente\n\n"
                f"_Ou tente novamente mais tarde (pode ser instabilidade da Shopee)._"
            )
        else:
            # URL inline - não tem catálogo disponível
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

    # Salva sessao com produtos carregados
    save_session(
        user_id,
        "awaiting_product_index",
        {
            "shop_url": shop_url,
            "username": username,
            "products": products,
            "segmento": segmento,
            "source": source,
            "shop_uid": shop_uid,
        },
    )
    log.info(f"[BG] Loja '{username}' carregada: {len(products)} produtos source={source} user={user_id}")

    # Monta e envia a lista de produtos
    from shopee_core.audit_service import list_products_summary
    from shopee_core.whatsapp_service import _product_list_message, MAX_PRODUCTS_LISTED
    product_list = _product_list_message(products)
    total = len(products)
    shown = min(total, MAX_PRODUCTS_LISTED)
    suffix = f"(mostrando os primeiros {shown})" if total > shown else ""
    
    # Indica a fonte dos produtos
    source_emoji = {
        "scraping": "🌐",
        "catalog": "📦",
    }
    source_text = {
        "scraping": "scraping público",
        "catalog": "catálogo importado",
    }
    
    emoji = source_emoji.get(source, "✅")
    source_label = source_text.get(source, "")
    source_line = f"\n📄 Fonte: {source_label}" if source_label else ""

    msg = (
        f"✅ Loja *{username}* carregada com *{total}* produto(s). {suffix}{source_line}\n\n"
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
    Usa a Gemini API Key do usuário quando disponível.
    """
    product_name = product.get("name", "Produto")
    log.info(f"[BG] Iniciando otimização: '{product_name}' user={user_id}")

    # Obtém chave de IA do usuário
    from shopee_core.whatsapp_service import get_user_gemini_api_key
    
    api_key = get_user_gemini_api_key(user_id)
    
    if not api_key:
        # Sem chave de IA disponível
        clear_session(user_id)
        message = (
            "🤖 *IA não configurada*\n\n"
            "Para gerar a otimização, configure sua chave com:\n"
            "*/ia configurar*"
        )
        try:
            evo_send_text(user_id=user_id, text=message)
            log.info(f"[BG] Otimização cancelada: sem API Key para user={user_id}")
        except Exception as e:
            log.error(f"[BG] Falha ao enviar aviso de IA: {e}")
        return

    try:
        from shopee_core.audit_service import generate_product_optimization
        from shopee_core.whatsapp_service import format_optimization_result
        
        # Passa api_key para a função de otimização
        result = generate_product_optimization(product, segmento=segmento, api_key=api_key)
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


def _run_import_catalog_bg(
    user_id: str,
    shop_uid: str,
    shop_url: str,
    username: str,
    base64_data: str,
    mimetype: str
):
    """
    Background task: importa catálogo de arquivo XLSX/XLS/CSV.
    Processa o arquivo, extrai produtos e salva no banco vinculado à loja.
    """
    import base64
    import io
    from shopee_core.catalog_service import save_catalog
    
    log.info(f"[CATALOG] Iniciando importação: user={user_id} shop={username} mimetype={mimetype}")
    
    try:
        # Decodifica base64
        if "," in base64_data:
            base64_data = base64_data.split(",", 1)[1]
        
        file_bytes = base64.b64decode(base64_data)
        log.info(f"[CATALOG] Arquivo decodificado: {len(file_bytes)} bytes")
        
        # Processa arquivo baseado no mimetype
        products = []
        
        if mimetype in ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel"]:
            # Excel (.xlsx ou .xls)
            try:
                import pandas as pd
                
                df = pd.read_excel(io.BytesIO(file_bytes))
                log.info(f"[CATALOG] Excel lido: {len(df)} linhas")
                
                # Normaliza nomes de colunas (case-insensitive)
                df.columns = df.columns.str.strip().str.lower()
                
                # Mapeia colunas comuns do Seller Center
                column_mapping = {
                    "nome do produto": "name",
                    "product name": "name",
                    "nome": "name",
                    "name": "name",
                    "preço": "price",
                    "preco": "price",
                    "price": "price",
                    "estoque": "stock",
                    "stock": "stock",
                    "quantidade": "stock",
                    "categoria": "category",
                    "category": "category",
                    "descrição": "description",
                    "descricao": "description",
                    "description": "description",
                    "sku": "sku",
                    "item id": "itemid",
                    "itemid": "itemid",
                }
                
                # Renomeia colunas
                df = df.rename(columns=column_mapping)
                
                # Extrai produtos
                for _, row in df.iterrows():
                    product = {
                        "name": str(row.get("name", "")).strip(),
                        "price": float(row.get("price", 0)) if pd.notna(row.get("price")) else 0,
                        "stock": int(row.get("stock", 0)) if pd.notna(row.get("stock")) else 0,
                        "category": str(row.get("category", "")).strip() if pd.notna(row.get("category")) else "",
                        "description": str(row.get("description", "")).strip() if pd.notna(row.get("description")) else "",
                        "sku": str(row.get("sku", "")).strip() if pd.notna(row.get("sku")) else "",
                        "itemid": str(row.get("itemid", "")).strip() if pd.notna(row.get("itemid")) else "",
                    }
                    
                    # Filtra produtos válidos (precisa ter nome)
                    if product["name"] and product["name"] != "nan":
                        products.append(product)
                
                log.info(f"[CATALOG] Produtos extraídos do Excel: {len(products)}")
                
            except Exception as e:
                log.error(f"[CATALOG] Erro ao processar Excel: {e}")
                clear_session(user_id)
                evo_send_text(user_id=user_id, text=(
                    f"❌ Erro ao processar arquivo Excel:\n{str(e)}\n\n"
                    "Certifique-se de que o arquivo está no formato correto."
                ))
                return
        
        elif mimetype in ["text/csv", "application/csv"]:
            # CSV
            try:
                import pandas as pd
                
                # Tenta múltiplos delimitadores
                for delimiter in [",", ";", "\t"]:
                    try:
                        df = pd.read_csv(io.BytesIO(file_bytes), delimiter=delimiter, encoding="utf-8")
                        if len(df.columns) > 1:
                            break
                    except:
                        continue
                
                log.info(f"[CATALOG] CSV lido: {len(df)} linhas")
                
                # Normaliza e processa igual ao Excel
                df.columns = df.columns.str.strip().str.lower()
                
                column_mapping = {
                    "nome do produto": "name",
                    "product name": "name",
                    "nome": "name",
                    "name": "name",
                    "preço": "price",
                    "preco": "price",
                    "price": "price",
                    "estoque": "stock",
                    "stock": "stock",
                    "quantidade": "stock",
                    "categoria": "category",
                    "category": "category",
                    "descrição": "description",
                    "descricao": "description",
                    "description": "description",
                    "sku": "sku",
                    "item id": "itemid",
                    "itemid": "itemid",
                }
                
                df = df.rename(columns=column_mapping)
                
                for _, row in df.iterrows():
                    product = {
                        "name": str(row.get("name", "")).strip(),
                        "price": float(row.get("price", 0)) if pd.notna(row.get("price")) else 0,
                        "stock": int(row.get("stock", 0)) if pd.notna(row.get("stock")) else 0,
                        "category": str(row.get("category", "")).strip() if pd.notna(row.get("category")) else "",
                        "description": str(row.get("description", "")).strip() if pd.notna(row.get("description")) else "",
                        "sku": str(row.get("sku", "")).strip() if pd.notna(row.get("sku")) else "",
                        "itemid": str(row.get("itemid", "")).strip() if pd.notna(row.get("itemid")) else "",
                    }
                    
                    if product["name"] and product["name"] != "nan":
                        products.append(product)
                
                log.info(f"[CATALOG] Produtos extraídos do CSV: {len(products)}")
                
            except Exception as e:
                log.error(f"[CATALOG] Erro ao processar CSV: {e}")
                clear_session(user_id)
                evo_send_text(user_id=user_id, text=(
                    f"❌ Erro ao processar arquivo CSV:\n{str(e)}\n\n"
                    "Certifique-se de que o arquivo está no formato correto."
                ))
                return
        
        # Valida se encontrou produtos
        if not products:
            clear_session(user_id)
            evo_send_text(user_id=user_id, text=(
                "⚠️ Nenhum produto válido encontrado no arquivo.\n\n"
                "Certifique-se de que o arquivo contém:\n"
                "• Coluna com nome do produto\n"
                "• Pelo menos 1 produto com nome preenchido\n\n"
                "Use */catalogo importar* para tentar novamente."
            ))
            return
        
        # Salva catálogo no banco
        result = save_catalog(
            user_id=user_id,
            shop_uid=shop_uid,
            shop_url=shop_url,
            username=username,
            products=products,
            source_type="seller_center"
        )
        
        log.info(f"[CATALOG] Catálogo salvo: catalog_id={result['catalog_id']} products={result['products_count']}")
        
        # Limpa sessão
        clear_session(user_id)
        
        # Monta preview dos primeiros produtos
        preview_products = products[:5]
        preview_lines = []
        for i, p in enumerate(preview_products, 1):
            name = p["name"][:40] + "..." if len(p["name"]) > 40 else p["name"]
            price = p.get("price", 0)
            preview_lines.append(f"{i}. {name} - R$ {price:.2f}")
        
        preview_text = "\n".join(preview_lines)
        if len(products) > 5:
            preview_text += f"\n... e mais {len(products) - 5} produtos"
        
        # Envia confirmação
        message = (
            f"✅ *Catálogo importado com sucesso!*\n\n"
            f"🏪 Loja: *{username}*\n"
            f"📦 Produtos salvos: *{len(products)}*\n\n"
            f"*Preview:*\n{preview_text}\n\n"
            f"Use */catalogo status* para ver detalhes ou */auditar* para usar o catálogo."
        )
        
        evo_send_text(user_id=user_id, text=message)
        log.info(f"[CATALOG] Importação concluída com sucesso: user={user_id} shop={username}")
        
    except Exception as e:
        log.error(f"[CATALOG] Erro crítico na importação: {e}\n{traceback.format_exc()}")
        clear_session(user_id)
        
        try:
            evo_send_text(user_id=user_id, text=(
                "❌ Ocorreu um erro ao importar o catálogo.\n\n"
                "Tente novamente com */catalogo importar*."
            ))
        except:
            pass


# ══════════════════════════════════════════════════════════════════
# BACKGROUND TASK — Processamento de Mídia
# ══════════════════════════════════════════════════════════════════

def _run_load_shop_for_sentinel_bg(user_id: str, shop_uid: str, shop_url: str):
    """
    Background task: carrega loja para configuração do Sentinela com fallback conversacional.
    
    Estratégia (Ordem de Prioridade):
    1. Tentar intercept via Playwright (método principal)
    2. Se falhar, usar catálogo cacheado (importado anteriormente)
    3. Se não houver cache, usar APIs diretas da Shopee (fallback)
    4. Se tudo falhar, solicitar keywords manuais
    """
    from shopee_core.shop_loader_service import load_shop_with_fallback
    from shopee_core.sentinel_whatsapp_service import (
        generate_keywords_from_shop,
        extract_shop_id_from_url,
    )
    
    log.info(f"[BG] Carregando loja para Sentinela com fallback: url={shop_url!r} user={user_id} shop_uid={shop_uid}")

    try:
        # Passa user_id para buscar catálogo cacheado se necessário
        loaded = load_shop_with_fallback(shop_url=shop_url, user_id=user_id)
    except Exception as e:
        log.error(f"[BG] Exceção ao carregar loja para Sentinela: {e}")
        loaded = {"ok": False, "message": str(e)}

    if not loaded.get("ok"):
        clear_session(user_id)
        msg = (
            f"❌ Não consegui carregar a loja.\n"
            f"Erro: {loaded.get('message', 'desconhecido')}\n\n"
            "Certifique-se de usar o formato: https://shopee.com.br/nome_da_loja\n"
            "Use */sentinela configurar* para tentar novamente."
        )
        try:
            evo_send_text(user_id=user_id, text=msg)
        except Exception as e:
            log.error(f"[BG] Falha ao enviar erro de loja para Sentinela: {e}")
        return

    shop_data = loaded["data"]
    username = shop_data.get("username", "loja")
    products = shop_data.get("products", [])
    method_used = shop_data.get("method_used", "unknown")
    shop_info = shop_data.get("shop", {})
    shopid = shop_info.get("shopid") or shop_info.get("shop_id") or extract_shop_id_from_url(shop_url)

    log.info(f"[BG] Loja carregada: username={username}, products={len(products)}, method={method_used}, shopid={shopid}")

    # ── Se conseguiu produtos, gera keywords automaticamente ──────────
    if products:
        keywords = generate_keywords_from_shop(shop_data)
        
        if not keywords:
            # Produtos existem mas não geraram keywords válidas
            _fallback_to_manual_keywords(user_id, shop_uid, shop_url, username, shopid,
                                       f"Encontrei {len(products)} produtos na loja *{username}*, mas não consegui gerar keywords automáticas.\n\nOs produtos podem ter nomes muito genéricos.")
            return

        # Salva dados na sessão para confirmação automática
        save_session(
            user_id,
            "awaiting_sentinel_confirmation",
            {
                "shop_uid": shop_uid,
                "shop_url": shop_url,
                "username": username,
                "shop_id": shopid,
                "keywords": keywords,
                "keyword_source": "catalog" if method_used in ["catalog_cache", "catalog_import"] else "scraping",
            },
        )
        
        log.info(f"[BG] Keywords automáticas geradas: {len(keywords)} para {username}")

        # Monta mensagem de confirmação automática
        keywords_preview = keywords[:10]
        keywords_text = "\n".join(f"• {kw}" for kw in keywords_preview)
        if len(keywords) > 10:
            keywords_text += f"\n• ... e mais {len(keywords) - 10} keywords"

        # Indica a fonte dos produtos
        method_info = ""
        if method_used == "catalog_cache":
            method_info = "\n\n_📦 Produtos carregados do catálogo importado_"
        elif method_used == "catalog_import":
            method_info = "\n\n_📦 Produtos carregados do catálogo recém-importado_"
        elif method_used == "fallback":
            method_info = "\n\n_ℹ️ Produtos carregados via API alternativa_"
        elif method_used == "intercept":
            method_info = "\n\n_✅ Produtos carregados via scraping público_"

        msg = (
            f"✅ *Loja analisada!*\n\n"
            f"🏪 Loja: *{username}*\n"
            f"📦 Produtos encontrados: *{len(products)}*\n\n"
            f"🔍 *Keywords geradas automaticamente ({len(keywords)}):*\n{keywords_text}\n\n"
            f"Essas keywords serão usadas para monitorar concorrentes.\n\n"
            f"*Confirmar* essa configuração?"
            f"{method_info}"
        )
        
        try:
            send_result = evo_send_text(user_id=user_id, text=msg)
            log.info(f"[BG] Confirmação automática de Sentinela enviada: ok={send_result.get('ok')}")
        except Exception as e:
            log.error(f"[BG] Falha ao enviar confirmação automática: {e}")
        return

    # ── Se não conseguiu produtos, fallback para keywords manuais ─────
    log.warning(f"[BG] Nenhum produto encontrado para {username}. Iniciando fallback manual.")
    
    _fallback_to_manual_keywords(
        user_id, shop_uid, shop_url, username, shopid,
        f"⚠️ Encontrei a loja *{username}*, mas a Shopee não retornou os produtos nesta tentativa.\n\nIsso pode acontecer por instabilidade ou bloqueio temporário."
    )


def _fallback_to_manual_keywords(user_id: str, shop_uid: str, shop_url: str, username: str, shopid: str, reason: str):
    """Helper para iniciar fallback de keywords manuais com sugestão de catálogo."""
    # Salva dados na sessão para input manual
    save_session(
        user_id,
        "awaiting_sentinel_keywords_manual",
        {
            "shop_uid": shop_uid,
            "shop_url": shop_url,
            "username": username,
            "shop_id": shopid,
        },
    )
    
    log.info(f"[BG] Fallback manual iniciado para {username}")

    msg = (
        f"{reason}\n\n"
        f"💡 *Você tem 2 opções:*\n\n"
        f"*1️⃣ Importar catálogo (recomendado)*\n"
        f"Use */catalogo* para importar seus produtos do Shopee Seller Center.\n"
        f"Depois volte e configure o Sentinela novamente.\n\n"
        f"*2️⃣ Usar keywords manuais*\n"
        f"Me envie de *3 a 5 keywords* para monitorar, uma por linha.\n\n"
        f"*Exemplo:*\n"
        f"mochila infantil princesa\n"
        f"mochila escolar rosa\n"
        f"mochila infantil feminina\n\n"
        f"_Ou envie */cancelar* para interromper._"
    )
    
    try:
        send_result = evo_send_text(user_id=user_id, text=msg)
        log.info(f"[BG] Solicitação de keywords manuais enviada: ok={send_result.get('ok')}")
    except Exception as e:
        log.error(f"[BG] Falha ao enviar solicitação de keywords manuais: {e}")


def _run_sentinel_bg(user_id: str, config: dict):
    """
    Background task: executa o Sentinela e envia resultado.
    
    U7.1 — Observabilidade e estabilidade:
      - Salva sessão como processing_sentinel
      - Atualiza progresso durante execução
      - Limita a 3 keywords por execução (MVP)
      - Timeout de 90s por keyword
      - Sempre envia mensagem final
      - Garante clear_session no finally
    """
    from shopee_core.sentinel_service import request_sentinel_execution, mark_sentinel_finished
    from shopee_core.sentinel_whatsapp_service import generate_janela_execucao
    
    log.info("[SENTINELA] ════════════════════════════════════════════════════")
    log.info(f"[SENTINELA] Início da execução: user={user_id}")

    # ── Constantes de controle ────────────────────────────────────
    MAX_SENTINEL_KEYWORDS_PER_RUN = 3
    TIMEOUT_PER_KEYWORD = 90  # segundos

    try:
        from backend_core import fetch_competitors_intercept
        import signal
        from contextlib import contextmanager

        shop_uid = config.get("shop_uid") or ""
        shop_id = config.get("shop_id", "unknown")  # legado / compat
        username = config.get("username", "loja")
        keywords_raw = [k.strip() for k in (config.get("keywords") or []) if isinstance(k, str) and k.strip()]

        if not shop_uid:
            evo_send_text(
                user_id=user_id,
                text="❌ Erro: não encontrei a loja ativa (shop_uid) para executar o Sentinela.",
            )
            return

        if not keywords_raw:
            evo_send_text(user_id=user_id, text="❌ Nenhuma keyword configurada para monitoramento.")
            return

        # ── Limita a 3 keywords por execução (MVP) ─────────────────
        keywords = keywords_raw[:MAX_SENTINEL_KEYWORDS_PER_RUN]
        total_keywords = len(keywords)
        
        if len(keywords_raw) > MAX_SENTINEL_KEYWORDS_PER_RUN:
            log.info(f"[SENTINELA] Limitando execução: {len(keywords_raw)} → {MAX_SENTINEL_KEYWORDS_PER_RUN} keywords")

        janela_execucao = generate_janela_execucao()

        # ── 1. Salva sessão como processing_sentinel ───────────────
        save_session(
            user_id,
            "processing_sentinel",
            {
                "shop_uid": shop_uid,
                "username": username,
                "keywords": keywords,
                "started_at": datetime.utcnow().isoformat(),
                "status": "running",
                "current_keyword": "",
                "completed_keywords": 0,
                "total_keywords": total_keywords,
                "janela_execucao": janela_execucao,
            },
        )
        log.info(f"[SENTINELA] Sessão salva: processing_sentinel")

        keywords_executadas: list[str] = []
        keywords_com_erro: list[str] = []
        keywords_timeout: list[str] = []
        all_concorrentes: list[dict] = []
        first_lock_block: dict | None = None

        # ── Timeout handler (Windows-compatible) ───────────────────
        @contextmanager
        def timeout_context(seconds):
            """Context manager para timeout (fallback sem signal no Windows)."""
            import threading
            
            timer = None
            timed_out = [False]
            
            def timeout_handler():
                timed_out[0] = True
            
            try:
                timer = threading.Timer(seconds, timeout_handler)
                timer.start()
                yield timed_out
            finally:
                if timer:
                    timer.cancel()

        # ── 2. Processa cada keyword com timeout ───────────────────
        for idx, kw in enumerate(keywords, 1):
            # ── Atualiza progresso antes de cada keyword ───────────
            save_session(
                user_id,
                "processing_sentinel",
                {
                    "shop_uid": shop_uid,
                    "username": username,
                    "keywords": keywords,
                    "started_at": datetime.utcnow().isoformat(),
                    "status": "running",
                    "current_keyword": kw,
                    "completed_keywords": idx - 1,
                    "total_keywords": total_keywords,
                    "janela_execucao": janela_execucao,
                },
            )
            log.info(f"[SENTINELA] Keyword {idx}/{total_keywords}: {kw!r}")

            lock_result = request_sentinel_execution(
                loja_id=shop_id,
                user_id=user_id,
                shop_uid=shop_uid,
                keyword=kw,
                janela_execucao=janela_execucao,
                executor="whatsapp",
            )

            if not lock_result.get("ok"):
                log.warning(f"[SENTINELA] Lock bloqueado para keyword={kw!r}")
                if not first_lock_block:
                    first_lock_block = lock_result
                continue

            # ── Executa scraping com timeout ───────────────────────
            try:
                with timeout_context(TIMEOUT_PER_KEYWORD) as timed_out:
                    concorrentes_raw = fetch_competitors_intercept(kw) or []
                    
                    if timed_out[0]:
                        raise TimeoutError(f"Timeout de {TIMEOUT_PER_KEYWORD}s excedido")
                
                concorrentes = []
                for i, c in enumerate(concorrentes_raw[:10]):
                    concorrentes.append(
                        {
                            "ranking": i + 1,
                            "titulo": c.get("nome", ""),
                            "preco": float(c.get("preco", 0) or 0),
                            "loja": str(c.get("shop_id") or ""),
                            "is_new": False,
                            "keyword": kw,
                            "item_id": c.get("item_id"),
                            "shop_id": c.get("shop_id"),
                        }
                    )

                all_concorrentes.extend(concorrentes)
                keywords_executadas.append(kw)
                
                log.info(f"[SENTINELA] Concorrentes encontrados: {len(concorrentes)}")

                # ── Atualiza progresso após keyword ────────────────
                save_session(
                    user_id,
                    "processing_sentinel",
                    {
                        "shop_uid": shop_uid,
                        "username": username,
                        "keywords": keywords,
                        "started_at": datetime.utcnow().isoformat(),
                        "status": "running",
                        "current_keyword": kw,
                        "completed_keywords": idx,
                        "total_keywords": total_keywords,
                        "janela_execucao": janela_execucao,
                    },
                )

                mark_sentinel_finished(
                    loja_id=shop_id,
                    user_id=user_id,
                    shop_uid=shop_uid,
                    keyword=kw,
                    janela_execucao=janela_execucao,
                    status="done",
                )
                
            except TimeoutError as e:
                log.error(f"[SENTINELA] Timeout na keyword={kw!r}: {e}")
                keywords_timeout.append(kw)
                try:
                    mark_sentinel_finished(
                        loja_id=shop_id,
                        user_id=user_id,
                        shop_uid=shop_uid,
                        keyword=kw,
                        janela_execucao=janela_execucao,
                        status="timeout",
                    )
                except Exception:
                    pass
                    
            except Exception as e:
                log.error(f"[SENTINELA] Erro ao executar keyword={kw!r}: {e}")
                keywords_com_erro.append(kw)
                try:
                    mark_sentinel_finished(
                        loja_id=shop_id,
                        user_id=user_id,
                        shop_uid=shop_uid,
                        keyword=kw,
                        janela_execucao=janela_execucao,
                        status="error",
                    )
                except Exception:
                    pass

        # ── 3. Sempre envia mensagem final ─────────────────────────
        
        # Caso 1: Nenhuma keyword executada (todas bloqueadas)
        if not keywords_executadas and not keywords_com_erro and not keywords_timeout:
            if first_lock_block:
                evo_send_text(
                    user_id=user_id,
                    text=(
                        "⚠️ O Sentinela já foi executado ou está em execução nesta janela.\n\n"
                        f"Executor: {first_lock_block.get('executor', 'desconhecido')}\n"
                        f"Status: {first_lock_block.get('status', 'running')}"
                    ),
                )
            else:
                evo_send_text(user_id=user_id, text="⚠️ Não consegui executar o Sentinela nesta janela.")
            log.info("[SENTINELA] Fim: nenhuma keyword executada (lock bloqueado)")
            return

        # Caso 2: Todas deram erro/timeout
        if not keywords_executadas and (keywords_com_erro or keywords_timeout):
            msg_parts = ["❌ *O Sentinela não conseguiu buscar concorrentes nesta tentativa.*\n"]
            
            if keywords_com_erro:
                msg_parts.append(f"❌ Erro: {', '.join(keywords_com_erro)}")
            if keywords_timeout:
                msg_parts.append(f"⏱️ Timeout: {', '.join(keywords_timeout)}")
            
            msg_parts.append("\nTente novamente com */sentinela rodar*.")
            
            evo_send_text(user_id=user_id, text="\n".join(msg_parts))
            log.info("[SENTINELA] Fim: todas as keywords falharam")
            return

        # Caso 3: Nenhum concorrente encontrado (mas keywords rodaram)
        if not all_concorrentes:
            msg = (
                "⚠️ *O Sentinela rodou, mas não conseguiu coletar concorrentes agora.*\n\n"
                f"Keywords analisadas: {', '.join(keywords_executadas)}\n\n"
                "Isso pode acontecer se:\n"
                "• A Shopee está com instabilidade\n"
                "• As keywords não retornaram resultados\n\n"
                "Tente novamente em alguns minutos."
            )
            evo_send_text(user_id=user_id, text=msg)
            log.info("[SENTINELA] Fim: nenhum concorrente coletado")
            return

        # Caso 4: Sucesso — gera relatório ──────────────────────────
        precos = [
            c.get("preco", 0)
            for c in all_concorrentes
            if isinstance(c.get("preco", None), (int, float))
        ]
        preco_medio = sum(precos) / len(precos) if precos else 0
        menor_preco = min(precos) if precos else 0
        maior_preco = max(precos) if precos else 0

        resultado = {
            "loja": username,
            "keyword": keywords_executadas[0],
            "keywords": keywords_executadas,
            "total_analisado": len(all_concorrentes),
            "concorrentes": all_concorrentes,
            "novos_concorrentes": [],
            "preco_medio": preco_medio,
            "menor_preco": menor_preco,
            "maior_preco": maior_preco,
        }

        # ── Telegram (por usuário) ─────────────────────────────────
        telegram_note = "Relatório completo não enviado. Use /telegram configurar."
        sent_to_telegram = False

        try:
            from shopee_core.whatsapp_service import get_user_telegram_config
            tg_cfg = get_user_telegram_config(user_id)
        except Exception:
            tg_cfg = None

        if tg_cfg:
            try:
                from telegram_service import TelegramSentinela
                from shopee_core.sentinel_report_service import generate_sentinel_report

                log.info("[SENTINELA] Gerando relatório para Telegram...")
                report = generate_sentinel_report(
                    resultado,
                    include_chart=True,
                    include_csv=True,
                    include_table_png=False,
                )

                log.info("[SENTINELA] Enviando relatório ao Telegram...")
                telegram = TelegramSentinela(token=tg_cfg["token"], chat_id=tg_cfg["chat_id"])
                telegram.enviar_relatorio_sentinela(
                    resultado=resultado,
                    chart_path=report.get("chart_path") or None,
                    table_path=report.get("csv_path") or None,
                )
                sent_to_telegram = True
                log.info("[SENTINELA] Relatório enviado ao Telegram com sucesso")
            except Exception as e:
                log.error(f"[SENTINELA] Falha ao enviar relatório ao Telegram: {e}")

        if sent_to_telegram:
            telegram_note = "📢 Relatório completo enviado ao Telegram."

        # ── Monta mensagem de resumo para WhatsApp ─────────────────
        msg_parts = [
            "🛡️ *Sentinela concluído!*\n",
            f"🏪 Loja: *{username}*",
            f"🔍 Keywords analisadas: *{len(keywords_executadas)}*",
        ]
        
        if len(keywords_raw) > MAX_SENTINEL_KEYWORDS_PER_RUN:
            msg_parts.append(f"_Rodadas as {MAX_SENTINEL_KEYWORDS_PER_RUN} primeiras keywords nesta checagem._")
        
        msg_parts.extend([
            f"📊 Concorrentes analisados: *{len(all_concorrentes)}*",
            f"🏷️ Menor preço encontrado: *R$ {menor_preco:.2f}*",
            f"💰 Preço médio: *R$ {preco_medio:.2f}*",
            "",
            telegram_note,
        ])
        
        if keywords_com_erro:
            msg_parts.append(f"\n⚠️ Erro em: {', '.join(keywords_com_erro)}")
        if keywords_timeout:
            msg_parts.append(f"⏱️ Timeout em: {', '.join(keywords_timeout)}")
        
        msg_parts.append(f"\n_Janela: {janela_execucao}_")

        msg = "\n".join(msg_parts)
        evo_send_text(user_id=user_id, text=msg)
        
        log.info("[SENTINELA] Resumo enviado ao WhatsApp")
        log.info(f"[SENTINELA] Concluído: user={user_id} shop_uid={shop_uid} kws={len(keywords_executadas)}")
        log.info("[SENTINELA] ════════════════════════════════════════════════════")

    except Exception as e:
        log.error(f"[SENTINELA] Erro crítico: {e}\n{traceback.format_exc()}")
        try:
            evo_send_text(
                user_id=user_id,
                text=(
                    "❌ Ocorreu um erro durante o monitoramento.\n"
                    "Tente novamente com */sentinela rodar*."
                ),
            )
        except Exception:
            pass
    
    finally:
        # ── 4. Garante limpeza da sessão ───────────────────────────
        try:
            clear_session(user_id)
            log.info(f"[SENTINELA] Sessão limpa: user={user_id}")
        except Exception as e:
            log.error(f"[SENTINELA] Erro ao limpar sessão: {e}")


def _run_media_bg(user_id: str, msg: dict, plan: list[dict], job_id: str = ""):
    """
    Background task: processa imagem recebida pelo WhatsApp executando plano de ações.
    Roda fora do ciclo de request/response do FastAPI.

    Fase 4A.2:
      - Suporte a múltiplas ações em sequência
      - Pipeline: remove_background → generate_scene → etc
      - Imagem intermediária passa de uma etapa para outra
    """
    import base64
    import time
    from shopee_core.session_service import clear_session, get_session
    from shopee_core.media_jobs import is_media_job_canceled, finish_media_job, timeout_media_job
    from shopee_core.media_worker import process_media_with_timeout

    start_time = time.time()

    log.info(f"[MEDIA] ════════════════════════════════════════════════════")
    log.info(f"[MEDIA] Iniciando processamento de mídia")
    log.info(f"[MEDIA] user_id={user_id}")
    log.info(f"[MEDIA] plan={plan}")
    log.info(f"[MEDIA] job_id={job_id!r}")
    log.info(f"[MEDIA] ════════════════════════════════════════════════════")

    try:
        # ── Extrai dados da mensagem ───────────────────────────────
        base64_str = msg.get("base64_data", "")
        media_type = msg.get("media_type", "")
        mimetype = msg.get("mimetype", "")
        caption = msg.get("caption", "")

        log.info(f"[MEDIA] Dados recebidos:")
        log.info(f"[MEDIA]   media_type={media_type!r}")
        log.info(f"[MEDIA]   mimetype={mimetype!r}")
        caption_preview = caption[:60] if caption else "None"
        log.info(f"[MEDIA]   caption={caption_preview!r}")
        log.info(f"[MEDIA]   base64_len={len(base64_str)}")

        if not base64_str:
            log.error("[MEDIA] ERRO: base64_data vazio — Evolution API não enviou a imagem")
            evo_send_text(user_id=user_id, text=(
                "❌ Não consegui receber a imagem. Isso pode ser um problema temporário.\n"
                "Tente reenviar a foto ou use */cancelar* para recomeçar."
            ))
            return

        # ── Decodifica base64 ─────────────────────────────────────
        log.info("[MEDIA] Decodificando base64...")
        decode_start = time.time()

        # Evolution API as vezes manda com prefixo "data:image/jpeg;base64,"
        if "," in base64_str:
            base64_str = base64_str.split(",", 1)[1]

        try:
            image_bytes = base64.b64decode(base64_str)
        except Exception as e:
            log.error(f"[MEDIA] ERRO ao decodificar base64: {e}")
            evo_send_text(user_id=user_id, text=(
                "❌ A imagem veio corrompida ou em formato inválido.\n"
                "Tente enviar outra foto."
            ))
            return

        decode_elapsed = time.time() - decode_start
        log.info(f"[MEDIA] Base64 decodificado: {len(image_bytes)} bytes em {decode_elapsed:.2f}s")

        # ── Verifica se job foi cancelado antes de processar ───────
        if job_id and is_media_job_canceled(job_id):
            log.info(f"[MEDIA] Job {job_id} foi cancelado ANTES do processamento. Abortando.")
            return

        # ── Executa plano de ações em sequência ────────────────────
        current_image_bytes = image_bytes
        last_action = None
        
        log.info(f"[MEDIA] Executando plano com {len(plan)} etapa(s)...")

        for step_idx, step in enumerate(plan, start=1):
            action = step.get("action", "")
            last_action = action
            
            log.info(f"[MEDIA] ──────────────────────────────────────────────")
            log.info(f"[MEDIA] Etapa {step_idx}/{len(plan)}: {action}")
            log.info(f"[MEDIA] ──────────────────────────────────────────────")

            # Verifica cancelamento entre etapas
            if job_id and is_media_job_canceled(job_id):
                log.info(f"[MEDIA] Job {job_id} cancelado durante etapa {step_idx}. Abortando.")
                return

            # ── Análise de imagem ─────────────────────────────────────
            if action == "analyze_image":
                log.info(f"[MEDIA] Processando análise...")
                result = process_media_with_timeout(
                    action="analyze_image",
                    image_bytes=current_image_bytes,
                    caption=caption,
                    segmento="E-commerce",
                    timeout=90,
                )

                if result.get("timeout"):
                    log.warning(f"[MEDIA] Timeout na análise")
                    if job_id:
                        timeout_media_job(job_id)
                    evo_send_text(user_id=user_id, text=(
                        "❌ A análise demorou demais.\n"
                        "Tente uma imagem menor ou mais simples."
                    ))
                    return

                if not result.get("ok"):
                    log.error(f"[MEDIA] Erro na análise: {result.get('message')}")
                    if job_id:
                        finish_media_job(job_id, success=False)
                    evo_send_text(user_id=user_id, text=(
                        f"❌ Não consegui analisar a imagem.\n{result.get('message', '')}"
                    ))
                    return

                # Se análise é a ÚNICA ação, envia texto e termina
                if len(plan) == 1:
                    analysis = result.get("message", "")
                    log.info(f"[MEDIA] Enviando análise: {len(analysis)} chars")
                    evo_send_text(
                        user_id=user_id,
                        text=f"🔎 *Análise da Imagem:*\n\n{analysis}"
                    )
                    
                    if job_id:
                        finish_media_job(job_id, success=True)
                    
                    return  # Análise sozinha não continua o pipeline
                
                # Se há mais ações depois da análise, envia texto e continua
                else:
                    analysis = result.get("message", "")
                    log.info(f"[MEDIA] Enviando análise (etapa {step_idx}/{len(plan)}): {len(analysis)} chars")
                    evo_send_text(
                        user_id=user_id,
                        text=f"🔎 *Análise da Imagem:*\n\n{analysis}\n\n⏳ _Continuando com as próximas etapas..._"
                    )
                    # Continua para próxima etapa (não faz return)

            # ── Remover fundo ──────────────────────────────────────────
            elif action == "remove_background":
                log.info(f"[MEDIA] Processando remoção de fundo...")
                result = process_media_with_timeout(
                    action="remove_background",
                    image_bytes=current_image_bytes,
                    caption="",
                    segmento="E-commerce",
                    timeout=90,
                )

                if result.get("timeout"):
                    log.warning(f"[MEDIA] Timeout na remoção de fundo")
                    if job_id:
                        timeout_media_job(job_id)
                    evo_send_text(user_id=user_id, text=(
                        "❌ A remoção de fundo demorou demais.\n"
                        "Tente uma imagem menor."
                    ))
                    return

                if not result.get("ok"):
                    log.error(f"[MEDIA] Erro ao remover fundo: {result.get('message')}")
                    if job_id:
                        finish_media_job(job_id, success=False)
                    evo_send_text(user_id=user_id, text=(
                        f"❌ Não foi possível remover o fundo.\n{result.get('message', '')}"
                    ))
                    return

                # Atualiza imagem intermediária
                image_b64 = result.get("image_b64", "")
                if image_b64:
                    current_image_bytes = base64.b64decode(image_b64)
                    log.info(f"[MEDIA] Fundo removido. Nova imagem: {len(current_image_bytes)} bytes")
                else:
                    log.error("[MEDIA] remove_background não retornou image_b64")
                    evo_send_text(user_id=user_id, text="❌ Erro ao processar remoção de fundo.")
                    return

            # ── Gerar cenário ──────────────────────────────────────────
            elif action == "generate_scene":
                style_prompt = step.get("style_prompt", "Gere um cenário clean e profissional")
                log.info(f"[MEDIA] Processando geração de cenário: {style_prompt[:50]}...")
                
                result = process_media_with_timeout(
                    action="generate_scene",
                    image_bytes=current_image_bytes,
                    caption=style_prompt,
                    segmento="E-commerce",
                    timeout=90,
                )

                if result.get("timeout"):
                    log.warning(f"[MEDIA] Timeout na geração de cenário")
                    if job_id:
                        timeout_media_job(job_id)
                    evo_send_text(user_id=user_id, text=(
                        "❌ A geração de cenário demorou demais.\n"
                        "Tente novamente."
                    ))
                    return

                if not result.get("ok"):
                    log.error(f"[MEDIA] Erro ao gerar cenário: {result.get('message')}")
                    if job_id:
                        finish_media_job(job_id, success=False)
                    evo_send_text(user_id=user_id, text=(
                        f"❌ Não foi possível gerar o cenário.\n{result.get('message', '')}"
                    ))
                    return

                # Atualiza imagem intermediária
                image_b64 = result.get("image_b64", "")
                if image_b64:
                    current_image_bytes = base64.b64decode(image_b64)
                    log.info(f"[MEDIA] Cenário gerado. Nova imagem: {len(current_image_bytes)} bytes")
                else:
                    log.error("[MEDIA] generate_scene não retornou image_b64")
                    evo_send_text(user_id=user_id, text="❌ Erro ao gerar cenário.")
                    return

            # ── Edição criativa ────────────────────────────────────────
            elif action == "creative_edit":
                instruction = step.get("instruction", caption)
                log.info(f"[MEDIA] Processando edição criativa: {instruction[:50]}...")
                
                result = process_media_with_timeout(
                    action="creative_edit",
                    image_bytes=current_image_bytes,
                    caption=instruction,
                    segmento="E-commerce",
                    timeout=90,
                )

                if result.get("timeout"):
                    log.warning(f"[MEDIA] Timeout na edição criativa")
                    if job_id:
                        timeout_media_job(job_id)
                    evo_send_text(user_id=user_id, text=(
                        "❌ A edição demorou demais.\n"
                        "Tente uma instrução mais simples."
                    ))
                    return

                if not result.get("ok"):
                    log.error(f"[MEDIA] Erro na edição: {result.get('message')}")
                    if job_id:
                        finish_media_job(job_id, success=False)
                    evo_send_text(user_id=user_id, text=(
                        f"❌ Não foi possível editar a imagem.\n{result.get('message', '')}"
                    ))
                    return

                # Atualiza imagem intermediária
                image_b64 = result.get("image_b64", "")
                if image_b64:
                    current_image_bytes = base64.b64decode(image_b64)
                    log.info(f"[MEDIA] Edição aplicada. Nova imagem: {len(current_image_bytes)} bytes")
                else:
                    log.error("[MEDIA] creative_edit não retornou image_b64")
                    evo_send_text(user_id=user_id, text="❌ Erro ao editar imagem.")
                    return

        # ── Verifica cancelamento após todas as etapas ─────────────
        if job_id and is_media_job_canceled(job_id):
            log.info(f"[MEDIA] Job {job_id} foi cancelado DEPOIS do processamento. NÃO enviando resultado.")
            return

        # ── Envia imagem final ─────────────────────────────────────
        log.info(f"[MEDIA] Todas as etapas concluídas. Enviando imagem final...")
        
        final_image_b64 = base64.b64encode(current_image_bytes).decode("utf-8")
        
        # Caption baseada nas etapas executadas
        if len(plan) > 1:
            # Múltiplas etapas - lista o que foi feito
            completed_steps = []
            step_names = {
                "remove_background": "fundo removido",
                "generate_scene": "cenário gerado",
                "creative_edit": "imagem editada",
            }
            
            for step in plan:
                action = step.get("action", "")
                if action in step_names:
                    step_name = step_names[action]
                    if action == "generate_scene":
                        style = step.get("style_prompt", "")
                        if "clean" in style.lower():
                            step_name = "cenário clean gerado"
                        elif "delicado" in style.lower():
                            step_name = "cenário delicado gerado"
                        elif "premium" in style.lower() or "luxuoso" in style.lower():
                            step_name = "cenário premium gerado"
                    completed_steps.append(step_name)
            
            steps_text = "\n".join(f"• {step}" for step in completed_steps)
            final_caption = f"✅ *Imagem processada com sucesso!*\n\nEtapas concluídas:\n{steps_text}"
        else:
            # Uma única etapa
            action = plan[0].get("action", "") if plan else ""
            caption_map = {
                "remove_background": "✅ Fundo removido!",
                "generate_scene": "✅ Cenário gerado!",
                "creative_edit": "✅ Imagem editada!",
            }
            final_caption = caption_map.get(action, "✅ Imagem processada!")

        send_result = evo_send_media(
            user_id=user_id,
            base64_media=final_image_b64,
            mediatype="image",
            mimetype="image/png",
            caption=final_caption,
        )
        log.info(f"[MEDIA] send_media ok={send_result.get('ok')}")

        if not send_result.get("ok"):
            log.error(f"[MEDIA] Falha ao enviar mídia: {send_result}")
            evo_send_text(user_id=user_id, text=(
                "❌ Processei a imagem, mas não consegui enviar de volta.\n"
                "Tente novamente."
            ))

        # Marca job como finalizado
        if job_id:
            finish_media_job(job_id, success=True)

        total_elapsed = time.time() - start_time
        log.info(f"[MEDIA] ════════════════════════════════════════════════════")
        log.info(f"[MEDIA] Processamento concluído em {total_elapsed:.2f}s")
        log.info(f"[MEDIA] ════════════════════════════════════════════════════")

    except Exception as e:
        log.error(f"[MEDIA] ERRO CRÍTICO: {e}\n{traceback.format_exc()}")

        if job_id:
            finish_media_job(job_id, success=False)

        try:
            evo_send_text(user_id=user_id, text=(
                "❌ Ocorreu um erro ao processar sua imagem.\n"
                "Tente novamente ou use */cancelar*."
            ))
        except:
            pass

    finally:
        # Limpa sessão apenas se ainda for o mesmo job
        session = get_session(user_id)
        session_job_id = session.get("data", {}).get("job_id", "")

        if not job_id or session_job_id == job_id:
            clear_session(user_id)
            log.info(f"[MEDIA] Sessão limpa para user={user_id}")
        else:
            log.info(f"[MEDIA] Sessão NÃO limpa (job diferente: session={session_job_id}, current={job_id})")
    """
    Background task: processa imagem recebida pelo WhatsApp e envia de volta.
    Roda fora do ciclo de request/response do FastAPI.

    Fase 4A.1:
      - Logs detalhados
      - Timeout de 90s via media_worker
      - Verificação de cancelamento via job_id
    """
    import base64
    import time
    from shopee_core.session_service import clear_session, get_session
    from shopee_core.media_jobs import is_media_job_canceled, finish_media_job, timeout_media_job
    from shopee_core.media_worker import process_media_with_timeout

    start_time = time.time()

    log.info(f"[MEDIA] ════════════════════════════════════════════════════")
    log.info(f"[MEDIA] Iniciando processamento de mídia")
    log.info(f"[MEDIA] user_id={user_id}")
    log.info(f"[MEDIA] action={action!r}")
    log.info(f"[MEDIA] job_id={job_id!r}")
    log.info(f"[MEDIA] ════════════════════════════════════════════════════")

    try:
        # ── Extrai dados da mensagem ───────────────────────────────
        base64_str = msg.get("base64_data", "")
        media_type = msg.get("media_type", "")
        mimetype = msg.get("mimetype", "")
        caption = msg.get("caption", "")

        log.info(f"[MEDIA] Dados recebidos:")
        log.info(f"[MEDIA]   media_type={media_type!r}")
        log.info(f"[MEDIA]   mimetype={mimetype!r}")
        caption_preview = caption[:60] if caption else "None"
        log.info(f"[MEDIA]   caption={caption_preview!r}")
        log.info(f"[MEDIA]   base64_len={len(base64_str)}")

        if not base64_str:
            log.error("[MEDIA] ERRO: base64_data vazio — Evolution API não enviou a imagem")
            evo_send_text(user_id=user_id, text=(
                "❌ Não consegui receber a imagem. Isso pode ser um problema temporário.\n"
                "Tente reenviar a foto ou use */cancelar* para recomeçar."
            ))
            return

        # ── Decodifica base64 ─────────────────────────────────────
        log.info("[MEDIA] Decodificando base64...")
        decode_start = time.time()

        # Evolution API as vezes manda com prefixo "data:image/jpeg;base64,"
        if "," in base64_str:
            base64_str = base64_str.split(",", 1)[1]

        try:
            image_bytes = base64.b64decode(base64_str)
        except Exception as e:
            log.error(f"[MEDIA] ERRO ao decodificar base64: {e}")
            evo_send_text(user_id=user_id, text=(
                "❌ A imagem veio corrompida ou em formato inválido.\n"
                "Tente enviar outra foto."
            ))
            return

        decode_elapsed = time.time() - decode_start
        log.info(f"[MEDIA] Base64 decodificado: {len(image_bytes)} bytes em {decode_elapsed:.2f}s")

        # ── Verifica se job foi cancelado antes de processar ───────
        if job_id and is_media_job_canceled(job_id):
            log.info(f"[MEDIA] Job {job_id} foi cancelado ANTES do processamento. Abortando.")
            return

        # ── Processa com timeout ───────────────────────────────────
        log.info(f"[MEDIA] Iniciando processamento com timeout de 90s...")
        process_start = time.time()

        result = process_media_with_timeout(
            action=action,
            image_bytes=image_bytes,
            caption=caption,
            segmento="E-commerce",
            timeout=90,
        )

        process_elapsed = time.time() - process_start
        log.info(f"[MEDIA] Processamento finalizado em {process_elapsed:.2f}s")
        log.info(f"[MEDIA] Resultado: ok={result.get('ok')}, message={result.get('message', '')[:50]}")

        # ── Verifica se job foi cancelado DEPOIS do processamento ──
        if job_id and is_media_job_canceled(job_id):
            log.info(f"[MEDIA] Job {job_id} foi cancelado DEPOIS do processamento. NÃO enviando resultado.")
            return

        # ── Verifica timeout ───────────────────────────────────────
        if result.get("timeout"):
            log.warning(f"[MEDIA] Timeout detectado para job {job_id}")
            if job_id:
                timeout_media_job(job_id)
            evo_send_text(user_id=user_id, text=(
                "❌ O processamento demorou demais.\n"
                "Tente uma imagem menor ou mais simples."
            ))
            return

        # ── Envia resultado ────────────────────────────────────────
        if not result.get("ok"):
            # Erro no processamento
            error_msg = result.get("message", "Erro desconhecido")
            log.error(f"[MEDIA] Erro no processamento: {error_msg}")

            if job_id:
                finish_media_job(job_id, success=False)

            evo_send_text(user_id=user_id, text=f"❌ {error_msg}")
            return

        # ── Análise retorna TEXTO, não imagem ─────────────────────
        if action == "analyze_image":
            analysis = result.get("message", "")
            log.info(f"[MEDIA] Enviando análise: {len(analysis)} chars")
            
            if analysis:
                send_result = evo_send_text(
                    user_id=user_id,
                    text=f"🔎 *Análise da Imagem:*\n\n{analysis}"
                )
                log.info(f"[MEDIA] send_text ok={send_result.get('ok')}")
            else:
                evo_send_text(
                    user_id=user_id,
                    text="❌ Não consegui analisar a imagem agora. Tente novamente."
                )
            
            if job_id:
                finish_media_job(job_id, success=True)
            
            return

        # ── Outras ações retornam IMAGEM ──────────────────────────
        image_b64 = result.get("image_b64", "")

        if image_b64:
            # Ações que retornam imagem
            log.info(f"[MEDIA] Enviando imagem processada via Evolution API...")
            log.info(f"[MEDIA] image_b64 len={len(image_b64)}")

            caption_map = {
                "remove_background": "✅ Fundo removido!",
                "generate_scene": "✅ Cenário gerado!",
                "creative_edit": "✅ Imagem editada!",
            }
            send_caption = caption_map.get(action, "✅ Imagem processada!")

            send_result = evo_send_media(
                user_id=user_id,
                base64_media=image_b64,
                mediatype="image",
                mimetype="image/png",
                caption=send_caption,
            )
            log.info(f"[MEDIA] send_media ok={send_result.get('ok')}")

            if not send_result.get("ok"):
                log.error(f"[MEDIA] Falha ao enviar mídia: {send_result}")
                evo_send_text(user_id=user_id, text=(
                    "❌ Processei a imagem, mas não consegui enviar de volta.\n"
                    "Tente novamente."
                ))
        else:
            # Fallback
            log.warning(f"[MEDIA] Resultado sem image_b64 para action={action}")
            evo_send_text(user_id=user_id, text=result.get("message", "Processamento concluído."))

        # Marca job como finalizado
        if job_id:
            finish_media_job(job_id, success=True)

        total_elapsed = time.time() - start_time
        log.info(f"[MEDIA] ════════════════════════════════════════════════════")
        log.info(f"[MEDIA] Processamento concluído em {total_elapsed:.2f}s")
        log.info(f"[MEDIA] ════════════════════════════════════════════════════")

    except Exception as e:
        log.error(f"[MEDIA] ERRO CRÍTICO: {e}\n{traceback.format_exc()}")

        if job_id:
            finish_media_job(job_id, success=False)

        try:
            evo_send_text(user_id=user_id, text=(
                "❌ Ocorreu um erro ao processar sua imagem.\n"
                "Tente novamente ou use */cancelar*."
            ))
        except:
            pass

    finally:
        # Limpa sessão apenas se ainda for o mesmo job
        session = get_session(user_id)
        session_job_id = session.get("data", {}).get("job_id", "")

        if not job_id or session_job_id == job_id:
            clear_session(user_id)
            log.info(f"[MEDIA] Sessão limpa para user={user_id}")
        else:
            log.info(f"[MEDIA] Sessão NÃO limpa (job diferente: session={session_job_id}, current={job_id})")


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
    from shopee_core.media_service import remove_background, generate_product_scene, creative_edit, analyze_image
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
        from shopee_core.media_service import generate_product_scene
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
        from shopee_core.media_service import creative_edit
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
        from shopee_core.media_service import analyze_image
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
