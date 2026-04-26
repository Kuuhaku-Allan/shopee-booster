"""
shopee_core/whatsapp_service.py — Adaptador de Mensagens do WhatsApp
=====================================================================
Camada que converte payloads da Evolution API em ações do ShopeeBooster
e devolve respostas prontas para serem enviadas ao usuário.

Responsabilidades:
  - Extrair texto/usuário de payloads da Evolution API (v1 e v2)
  - Rotear mensagens de texto para o fluxo correto (estado de sessão)
  - Montar respostas {"type": "text", "text": ...} para o webhook

Não conecta na Evolution API diretamente — isso fica no api_server.py.
Não importa streamlit.
"""

from __future__ import annotations

import logging
import traceback

from shopee_core.session_service import get_session, save_session, clear_session
from shopee_core.chatbot_service import run_chatbot_turn
from shopee_core.audit_service import (
    load_shop_from_url,
    generate_product_optimization,
    list_products_summary,
)

log = logging.getLogger("shopee_wa")

# ── Mapeamento de segmentos disponíveis ───────────────────────────
SEGMENTOS = [
    "Escolar / Juvenil",
    "Viagem",
    "Profissional / Tech",
    "Moda",
]

# Segmento padrão quando a sessão não guarda um específico
DEFAULT_SEGMENTO = "Escolar / Juvenil"

# Máximo de produtos exibidos na lista de seleção
MAX_PRODUCTS_LISTED = 10

# Limite de caracteres para otimização no WhatsApp (evitar mensagens gigantes)
OPTIMIZATION_MAX_CHARS = 3500


# ══════════════════════════════════════════════════════════════════
# EXTRAÇÃO DE PAYLOAD
# ══════════════════════════════════════════════════════════════════

def extract_evolution_message(payload: dict) -> dict:
    """
    Extrai os campos relevantes de um payload da Evolution API.

    Suporta variações de formato entre v1 e v2:
      - data.key.remoteJid + data.message.conversation
      - data.key.remoteJid + data.message.extendedTextMessage.text
      - data.messageBody (formato legado)

    Returns dict com:
        event    (str)  — tipo do evento (ex: "MESSAGES_UPSERT")
        from_me  (bool) — se foi o próprio bot que enviou
        user_id  (str)  — JID do remetente
        text     (str)  — texto da mensagem (vazio se não houver)
        has_media (bool) — se há mídia anexada (imageMessage, documentMessage, etc.)
        raw      (dict) — payload original completo
    """
    event = payload.get("event", "")
    data = payload.get("data", {})
    if not isinstance(data, dict):
        data = {}

    key = data.get("key", {})
    if not isinstance(key, dict):
        key = {}

    message = data.get("message", {})
    if not isinstance(message, dict):
        message = {}

    from_me = bool(key.get("fromMe", False))
    user_id = (
        key.get("remoteJid")
        or data.get("remoteJid")
        or ""
    )

    # Texto: tenta múltiplos campos em ordem de prioridade
    text = (
        message.get("conversation")
        or (message.get("extendedTextMessage") or {}).get("text")
        or data.get("messageBody")
        or ""
    )

    # Detecta mídia — lista dos tipos mais comuns da Evolution API
    MEDIA_TYPES = {
        "imageMessage", "videoMessage", "documentMessage",
        "audioMessage", "stickerMessage",
    }
    has_media = any(k in message for k in MEDIA_TYPES)

    return {
        "event": event,
        "from_me": from_me,
        "user_id": user_id,
        "text": text.strip(),
        "has_media": has_media,
        "raw": payload,
    }


# ══════════════════════════════════════════════════════════════════
# RESPOSTAS PRÉ-FORMATADAS
# ══════════════════════════════════════════════════════════════════

def _txt(text: str) -> dict:
    """Atalho para resposta de texto simples."""
    return {"type": "text", "text": text}


def _menu_message() -> dict:
    return _txt(
        "👋 Olá! Eu sou o *ShopeeBooster*, seu assistente de e-commerce.\n\n"
        "O que você quer fazer hoje?\n\n"
        "🔍 */auditar* — Auditar e otimizar um produto da sua loja\n"
        "💬 */chat* — Tirar dúvidas sobre e-commerce\n"
        "🖼️ */imagem* — Editar imagem de produto\n"
        "📋 */status* — Ver sessão atual\n"
        "🔄 */reset* — Cancelar e recomeçar\n\n"
        "_Ou me mande qualquer pergunta diretamente!_"
    )


def _product_list_message(products: list) -> str:
    """Gera lista numerada de produtos para o WhatsApp."""
    lines = []
    for i, p in enumerate(products[:MAX_PRODUCTS_LISTED]):
        name = p.get("name", f"Produto {i}")
        price = p.get("price", 0)
        # Trunca nomes longos para caber no WhatsApp
        name_short = name[:50] + "…" if len(name) > 50 else name
        lines.append(f"*{i}* — {name_short} | R$ {price:.2f}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# ROTEADOR PRINCIPAL
# ══════════════════════════════════════════════════════════════════

def handle_whatsapp_text(user_id: str, text: str) -> dict:
    """
    Roteador principal de mensagens de texto do WhatsApp.

    Carrega a sessão do usuário, decide qual ação executar com base
    no estado atual e no texto recebido, e retorna a resposta.

    Returns dict com:
        type  (str) — "text" ou "background_task"
        text  (str) — mensagem imediata a enviar

        Quando type="background_task", também inclui:
          task     (str)  — "optimize_product"
          product  (dict) — produto a otimizar
          segmento (str)  — segmento de mercado
          user_id  (str)  — JID para enviar o resultado depois
    """
    lower = text.lower().strip()
    session = get_session(user_id)
    state = session["state"]
    data = session["data"]

    log.info(f"[WA] user={user_id} state={state!r} text={text[:60]!r}")

    try:
        return _route(user_id, text, lower, state, data)
    except Exception as e:
        log.error(f"[WA] Erro no roteador: {e}\n{traceback.format_exc()}")
        return _txt(
            "⚠️ Ocorreu um erro interno. Tente novamente ou envie */reset* para recomeçar."
        )


def _route(
    user_id: str,
    text: str,
    lower: str,
    state: str,
    data: dict,
) -> dict:
    """Lógica de roteamento separada do try/except para clareza."""

    # ── Comandos globais (funcionam em qualquer estado) ───────────

    if lower in {"/reset", "resetar", "cancelar", "/cancelar"}:
        clear_session(user_id)
        return _txt("✅ Sessão reiniciada. Pode me mandar uma nova tarefa.")

    if lower in {"/start", "start", "menu", "/menu", "ajuda", "/ajuda", "oi", "olá", "ola"}:
        return _menu_message()

    if lower in {"/status"}:
        if state == "idle":
            return _txt("Você não tem nenhum fluxo ativo no momento.")
        return _txt(
            f"📌 *Estado atual:* `{state}`\n"
            f"Envie */reset* para cancelar ou continue o fluxo."
        )

    if lower in {"/chat"}:
        clear_session(user_id)
        return _txt(
            "💬 Modo chat ativado. Pode me fazer qualquer pergunta sobre e-commerce, "
            "Shopee, produtos ou marketing. Envie */menu* para ver outras opções."
        )

    if lower in {"/imagem"}:
        clear_session(user_id)
        return _txt(
            "🖼️ Para editar uma imagem, envie a foto diretamente com uma instrução, por exemplo:\n\n"
            "📸 _(imagem)_ remova o fundo\n"
            "📸 _(imagem)_ gere um cenário de estúdio\n"
            "📸 _(imagem)_ mude a cor para azul\n\n"
            "_Suporte a mídia chegará em breve!_"
        )

    # ── Comando /auditar ──────────────────────────────────────────

    if lower.startswith("/auditar"):
        # Extrai URL inline se houver: /auditar https://shopee.com.br/loja
        parts = text.split(maxsplit=1)
        inline_url = parts[1].strip() if len(parts) > 1 else ""

        if inline_url:
            return _handle_shop_url(user_id, inline_url)

        save_session(user_id, "awaiting_shop_url", {})
        return _txt(
            "🔍 *Auditoria iniciada.*\n\n"
            "Me envie a URL da loja na Shopee.\n"
            "Exemplo: https://shopee.com.br/nome_da_loja"
        )

    # ── Guard: bloqueia nova mensagem enquanto auditoria está em andamento ──

    if state == "processing":
        return _txt(
            "⏳ Ainda estou processando a auditoria anterior.\n"
            "Por favor, aguarde. Envio o resultado assim que terminar.\n\n"
            "_Se quiser cancelar, envie_ */reset*"
        )

    # ── Estados do fluxo de auditoria ────────────────────────────

    if state == "awaiting_shop_url":
        return _handle_shop_url(user_id, text)

    if state == "awaiting_product_index":
        return _handle_product_selection(user_id, lower, data)

    # ── Fallback: conversa geral com o chatbot ────────────────────

    return _handle_general_chat(user_id, text, data)


# ══════════════════════════════════════════════════════════════════
# HANDLERS DE FLUXO
# ══════════════════════════════════════════════════════════════════

def _handle_shop_url(user_id: str, url: str) -> dict:
    """Carrega uma loja a partir da URL e transita para seleção de produto."""
    loading_reply = (
        "⏳ Carregando os dados da loja... Isso pode levar até 1 minuto "
        "enquanto busco os produtos na Shopee."
    )
    # Nota: em produção, enviar loading_reply via Evolution API aqui antes de processar.

    loaded = load_shop_from_url(url)

    if not loaded["ok"]:
        return _txt(
            f"❌ {loaded['message']}\n\n"
            "Certifique-se de usar o formato:\n"
            "https://shopee.com.br/nome_da_loja"
        )

    products = loaded["data"].get("products", [])
    username = loaded["data"].get("username", "loja")

    if not products:
        return _txt(
            f"⚠️ A loja *{username}* foi encontrada, mas não há produtos visíveis no momento."
        )

    save_session(
        user_id,
        "awaiting_product_index",
        {
            "shop_url": url,
            "username": username,
            "products": products,
            "segmento": DEFAULT_SEGMENTO,
        },
    )

    product_list = _product_list_message(products)
    total = len(products)
    shown = min(total, MAX_PRODUCTS_LISTED)

    return _txt(
        f"✅ Loja *{username}* carregada com *{total}* produto(s).\n\n"
        f"Escolha o número do produto que deseja otimizar "
        f"{'(mostrando os primeiros ' + str(shown) + ')' if total > shown else ''}:\n\n"
        f"{product_list}\n\n"
        "Responda com o número. Ex: *0*"
    )


def _handle_product_selection(user_id: str, text: str, data: dict) -> dict:
    """
    Valida a seleção de produto e delega a otimização para background.

    Retorna type="background_task" para que o api_server.py:
      1. Envie a mensagem "aguarde" imediatamente via evo_send_text()
      2. Agende generate_product_optimization() via BackgroundTasks
      3. Ao finalizar, envie o resultado via evo_send_text()
    """
    try:
        index = int(text.strip())
    except ValueError:
        return _txt(
            "⚠️ Por favor, envie apenas o *número* do produto.\n"
            "Exemplo: *0*, *1*, *2*...\n\n"
            "Envie */reset* para cancelar."
        )

    products = data.get("products", [])
    segmento = data.get("segmento", DEFAULT_SEGMENTO)

    if index < 0 or index >= len(products):
        return _txt(
            f"❌ Número inválido. Escolha entre *0* e *{len(products) - 1}*.\n"
            "Envie */reset* para cancelar."
        )

    product = products[index]
    product_name = product.get("name", f"Produto {index}")

    # Transita para 'processing' — guard bloqueia mensagens duplicadas
    save_session(user_id, "processing", {
        "product_name": product_name,
        "product_index": index,
    })

    log.info(f"[WA] Agendando otimização background: '{product_name}' user={user_id}")

    return {
        "type": "background_task",
        "task": "optimize_product",
        "text": (
            f"⏳ *Otimizando: _{product_name[:50]}_*\n\n"
            "Estou buscando concorrentes, coletando avaliações e gerando o listing com IA.\n"
            "Isso pode levar de 1 a 3 minutos. Vou te avisar quando terminar!"
        ),
        "product": product,
        "segmento": segmento,
        "user_id": user_id,
    }


def _handle_general_chat(user_id: str, text: str, data: dict) -> dict:
    """Conversa geral com o chatbot do ShopeeBooster."""
    segmento = data.get("segmento", DEFAULT_SEGMENTO)

    result = run_chatbot_turn(
        user_message=text,
        segmento=segmento,
        chat_history=[],
        full_context="",
    )

    response_text = result.get("text", "")

    if not response_text:
        return _txt(
            "⏳ Não consegui gerar uma resposta agora. Tente novamente."
        )

    return _txt(response_text)


# ══════════════════════════════════════════════════════════════════
# FORMATAÇÃO DO RESULTADO (chamada pelo background task)
# ══════════════════════════════════════════════════════════════════

def format_optimization_result(result: dict, product_name: str) -> str:
    """
    Formata o resultado de generate_product_optimization() para WhatsApp.
    Chamado pelo api_server.py quando o BackgroundTask conclui.
    """
    if not result.get("ok"):
        return (
            f"❌ Não consegui gerar a otimização para *{product_name[:50]}*.\n"
            f"Erro: {result.get('message', 'desconhecido')}\n\n"
            "Tente novamente com */auditar*."
        )

    optimization = result["data"].get("optimization", "")
    competitors_count = len(result["data"].get("competitors", []))
    reviews_count = len(result["data"].get("reviews", []))

    header = (
        f"✅ *Otimização concluída!*\n"
        f"📦 Produto: _{product_name[:50]}_\n"
        f"🏪 Concorrentes analisados: *{competitors_count}*\n"
        f"💬 Avaliações coletadas: *{reviews_count}*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    body = optimization[:OPTIMIZATION_MAX_CHARS]
    if len(optimization) > OPTIMIZATION_MAX_CHARS:
        body += "\n\n_[Conteúdo truncado. Acesse o .exe para ver a versão completa.]_"
    footer = (
        "\n\n━━━━━━━━━━━━━━━━━━━━━━\n"
        "Quer otimizar outro produto? Envie */auditar*"
    )
    return header + body + footer
