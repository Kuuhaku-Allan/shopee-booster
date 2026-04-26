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

    # ── Extração de sub-objetos de mídia ─────────────────────────
    image_msg    = message.get("imageMessage") or {}
    video_msg    = message.get("videoMessage") or {}
    document_msg = message.get("documentMessage") or {}
    audio_msg    = message.get("audioMessage") or {}

    # Caption vem DENTRO do imageMessage, não em message.conversation
    caption = (
        image_msg.get("caption")
        or video_msg.get("caption")
        or document_msg.get("caption")
        or ""
    )

    # Texto: tenta múltiplos campos em ordem de prioridade; caption como fallback
    text = (
        message.get("conversation")
        or (message.get("extendedTextMessage") or {}).get("text")
        or caption
        or data.get("messageBody")
        or ""
    )

    # Detecta mídia — lista dos tipos mais comuns da Evolution API
    MEDIA_TYPES = {
        "imageMessage", "videoMessage", "documentMessage",
        "audioMessage", "stickerMessage",
    }
    has_media = any(k in message for k in MEDIA_TYPES)

    # Tenta extrair message_id para deduplicação (v2: data.key.id)
    message_id = key.get("id", "")

    # base64: busca em múltiplos locais (tolerante a variações de versão)
    base64_data = (
        data.get("base64")
        or message.get("base64")
        or image_msg.get("base64")
        or video_msg.get("base64")
        or document_msg.get("base64")
        or ""
    )

    mimetype = (
        image_msg.get("mimetype")
        or video_msg.get("mimetype")
        or document_msg.get("mimetype")
        or audio_msg.get("mimetype")
        or ""
    )

    # media_type como string simples (image/video/document/audio/sticker)
    if "imageMessage" in message:
        media_type = "image"
    elif "videoMessage" in message:
        media_type = "video"
    elif "documentMessage" in message:
        media_type = "document"
    elif "audioMessage" in message:
        media_type = "audio"
    elif "stickerMessage" in message:
        media_type = "sticker"
    else:
        media_type = ""

    return {
        "event": event,
        "from_me": from_me,
        "user_id": user_id,
        "text": text.strip(),
        "has_media": has_media,
        "media_type": media_type,
        "mimetype": mimetype,
        "base64_data": base64_data,
        "caption": caption.strip(),
        "message_id": message_id,
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
        "🛡️ */sentinela* — Monitorar concorrentes automaticamente\n"
        "📋 */status* — Ver sessão atual\n"
        "🔄 */cancelar* — Cancelar e recomeçar\n\n"
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

def normalize_intent_text(text: str) -> str:
    """
    Normaliza texto para classificação de intenção.
    Remove acentos, converte para minúsculas e remove espaços extras.
    
    Exemplo:
        "Análise esta imagem" → "analise esta imagem"
    """
    import unicodedata
    
    text = text.lower().strip()
    # Normaliza para NFD (decompõe caracteres acentuados)
    text = unicodedata.normalize("NFD", text)
    # Remove marcas diacríticas (acentos)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text


def extract_scene_prompt(caption: str) -> str:
    """
    Extrai o prompt de estilo do cenário da legenda.
    
    Exemplos:
        "gere um cenário clean" → "gere um cenário clean"
        "cenário delicado" → "cenário delicado"
    """
    text = caption.strip()
    
    trigger_words = [
        "gere um cenário",
        "gerar um cenário",
        "crie um cenário",
        "gere um cenario",
        "gerar um cenario",
        "crie um cenario",
        "cenário",
        "cenario",
    ]
    
    lower = text.lower()
    for trigger in trigger_words:
        idx = lower.find(trigger)
        if idx != -1:
            # Retorna a partir do trigger até o final ou próxima vírgula
            rest = text[idx:].split(",")[0].strip()
            return rest
    
    return "Gere um cenário clean e profissional para este produto."


def extract_media_plan(caption: str) -> list[dict]:
    """
    Extrai um plano de ações ordenadas da legenda.
    
    Suporta comandos compostos como:
        "Remova o fundo e gere um cenário clean"
        "Analise esta imagem e remova o fundo"
    
    Returns:
        Lista de dicts com {"action": str, ...params}
        
    Exemplos:
        "Remova o fundo" → [{"action": "remove_background"}]
        "Remova o fundo e gere um cenário clean" → [
            {"action": "remove_background"},
            {"action": "generate_scene", "style_prompt": "gere um cenário clean"}
        ]
        "Analise esta imagem e remova o fundo" → [
            {"action": "analyze_image"},
            {"action": "remove_background"}
        ]
    """
    text = normalize_intent_text(caption)
    plan = []
    
    # Detecta intenções
    wants_remove_bg = ("remov" in text and "fundo" in text)
    wants_scene = any(term in text for term in [
        "gere um cenario",
        "gerar cenario",
        "crie um cenario",
        "cenario clean",
        "cenario",
        "fundo clean",
        "fundo profissional",
        "fundo bonito",
        "ambiente",
        "backdrop",
    ])
    wants_analysis = any(term in text for term in [
        "analise",
        "analisar",
        "avalie",
        "avaliar",
        "feedback",
        "opiniao",
        "o que acha",
        "imagem esta boa",
        "ta boa",
        "esta boa",
    ])
    
    # Detecta conectores que indicam sequência
    has_sequence_words = any(connector in text for connector in [
        " e ",
        " depois ",
        " entao ",
        " então ",
        " apos ",
        " após ",
        " em seguida",
        " tambem ",
        " também ",
    ])
    
    # Regra: análise + edição SEM conectores = ambíguo
    # Mas análise + edição COM conectores = sequência válida
    if wants_analysis and (wants_remove_bg or wants_scene) and not has_sequence_words:
        plan.append({
            "action": "clarify",
            "message": (
                "🤔 Posso fazer uma destas opções:\n\n"
                "1️⃣ *Analisar* a imagem (retorna texto)\n"
                "2️⃣ *Editar* a imagem (retorna imagem processada)\n\n"
                "Para fazer ambos em sequência, use conectores como:\n"
                "_\"Analise esta imagem e depois remova o fundo\"_\n"
                "_\"Remova o fundo e então gere um cenário clean\"_"
            )
        })
        return plan
    
    # Sequência válida: análise primeiro, depois edição
    if wants_analysis:
        plan.append({"action": "analyze_image"})
    
    # Cadeia de edição
    if wants_remove_bg:
        plan.append({"action": "remove_background"})
    
    if wants_scene:
        style_prompt = extract_scene_prompt(caption)
        plan.append({
            "action": "generate_scene",
            "style_prompt": style_prompt,
        })
    
    # Fallback: edição criativa (só se não há outras ações)
    if not plan:
        plan.append({
            "action": "creative_edit",
            "instruction": caption,
        })
    
    return plan


def format_plan_steps(plan: list[dict]) -> str:
    """Formata as etapas do plano para exibir ao usuário."""
    step_names = {
        "remove_background": "remover fundo",
        "generate_scene": "gerar cenário",
        "creative_edit": "editar imagem",
        "analyze_image": "analisar imagem",
    }
    
    steps = []
    for step in plan:
        action = step.get("action", "")
        name = step_names.get(action, action)
        steps.append(f"• {name}")
    
    return "\n".join(steps)

def handle_whatsapp_message(msg: dict) -> dict:
    """
    Roteador principal de mensagens do WhatsApp (suporta texto e mídia).

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
    user_id = msg.get("user_id", "")
    text = msg.get("text", "")
    lower = text.lower().strip()
    
    session = get_session(user_id)
    state = session["state"]
    data = session["data"]

    log.info(f"[WA] user={user_id} state={state!r} has_media={msg.get('has_media')} text={text[:60]!r}")

    try:
        if msg.get("has_media"):
            return _handle_media_message(user_id, msg, state, data)
        return _route(user_id, text, lower, state, data)
    except Exception as e:
        log.error(f"[WA] Erro no roteador: {e}\n{traceback.format_exc()}")
        return _txt(
            "⚠️ Ocorreu um erro interno. Tente novamente ou envie */cancelar* para recomeçar."
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
        # Cancela job de mídia se existir
        job_id = data.get("job_id") if data else None
        if job_id:
            from shopee_core.media_jobs import cancel_media_job
            cancel_media_job(job_id)
            log.info(f"[WA] Job cancelado: job_id={job_id} user={user_id}")
        
        clear_session(user_id)
        return _txt("✅ Operação cancelada e sessão reiniciada com segurança. Pode me mandar uma nova tarefa quando quiser!")

    if lower in {"/start", "start", "menu", "/menu", "oi", "olá", "ola"}:
        return _menu_message()

    if lower in {"ajuda", "/ajuda"}:
        return _txt(
            "💡 *Como usar o ShopeeBooster no WhatsApp*\n\n"
            "Eu sou um assistente treinado para te ajudar a vender mais.\n\n"
            "🔹 *Comandos Principais:*\n"
            "*/auditar* — Analisa concorrentes e reescreve títulos/descrições\n"
            "*/chat* — Conversa livre para tirar dúvidas de e-commerce\n"
            "*/sentinela* — Monitora concorrentes automaticamente\n"
            "*/status* — Veja o que estou processando no momento\n"
            "*/cancelar* — Interrompe qualquer análise travada\n\n"
            "🔹 *Dica rápida:*\n"
            "Basta me perguntar 'qual o melhor título para um vestido?' que eu te respondo na hora!"
        )

    # ── Comandos do Sentinela ─────────────────────────────────────

    if lower.startswith("/sentinela"):
        return _handle_sentinel_command(user_id, text, lower, state, data)

    if lower in {"/status"}:
        if state == "idle":
            return _txt("Você não tem nenhum fluxo ativo no momento. Tudo livre! Envie */menu* para ver o que fazer.")
        
        status_map = {
            "awaiting_shop_url": "Aguardando você me enviar o link da sua loja.",
            "processing_load_shop": "Carregando a sua loja e listando os produtos... ⏳",
            "awaiting_product_index": "Aguardando você escolher o número do produto da lista.",
            "processing": "Estou processando dados com IA neste momento (pode levar até 2 min)... ⏳"
        }
        human_state = status_map.get(state, state)
        
        return _txt(
            f"📌 *Status da sua sessão:*\n"
            f"_{human_state}_\n\n"
            f"Se algo parece travado, envie */cancelar*."
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

    # ── Guard: bloqueia nova mensagem enquanto carregando loja ──────────

    if state == "processing_load_shop":
        return _txt(
            "⏳ Ainda estou carregando os produtos da sua loja.\n"
            "Aguarde um instante! Envio a lista assim que terminar.\n\n"
            "_Se quiser cancelar, envie_ */cancelar*"
        )

    # ── Guard: bloqueia nova mensagem enquanto otimizando produto ───

    if state == "processing":
        return _txt(
            "⏳ Ainda estou processando a auditoria anterior.\n"
            "Por favor, aguarde. Envio o resultado assim que terminar.\n\n"
            "_Se quiser cancelar, envie_ */cancelar*"
        )

    # ── Estados do fluxo de auditoria ────────────────────────────

    if state == "awaiting_shop_url":
        return _handle_shop_url(user_id, text)

    if state == "awaiting_product_index":
        return _handle_product_selection(user_id, lower, data)

    # ── Estados do fluxo do Sentinela ─────────────────────────────

    if state == "awaiting_sentinel_shop_url":
        return _handle_sentinel_shop_url(user_id, text)

    if state == "awaiting_sentinel_confirmation":
        return _handle_sentinel_confirmation(user_id, lower, data)

    if state == "awaiting_sentinel_keywords_manual":
        return _handle_sentinel_keywords_manual(user_id, text, data)

    if state == "awaiting_sentinel_keywords_update":
        return _handle_sentinel_keywords_update(user_id, text, data)

    # ── Fallback: conversa geral com o chatbot ────────────────────

    return _handle_general_chat(user_id, text, data)


# ══════════════════════════════════════════════════════════════════
# HANDLERS DO SENTINELA
# ══════════════════════════════════════════════════════════════════

def _handle_sentinel_command(user_id: str, text: str, lower: str, state: str, data: dict) -> dict:
    """Roteador de comandos do Sentinela."""
    from shopee_core.sentinel_whatsapp_service import (
        get_sentinel_config,
        format_sentinel_menu,
        format_sentinel_status,
        delete_sentinel_config,
    )
    
    # Comando base: /sentinela
    if lower == "/sentinela":
        return _txt(format_sentinel_menu())
    
    # /sentinela status
    if lower in {"/sentinela status", "/sentinela ver"}:
        config = get_sentinel_config(user_id)
        return _txt(format_sentinel_status(config))
    
    # /sentinela configurar
    if lower in {"/sentinela configurar", "/sentinela config"}:
        clear_session(user_id)  # Limpa qualquer sessão anterior
        save_session(user_id, "awaiting_sentinel_shop_url", {})
        return _txt(
            "🛡️ *Configuração do Sentinela*\n\n"
            "Me envie a URL da sua loja na Shopee.\n\n"
            "Exemplo: https://shopee.com.br/nome_da_loja\n\n"
            "_Vou analisar seus produtos e gerar keywords automaticamente para monitoramento._"
        )
    
    # /sentinela rodar
    if lower in {"/sentinela rodar", "/sentinela executar", "/sentinela agora"}:
        config = get_sentinel_config(user_id)
        if not config:
            return _txt(
                "❌ Sentinela não configurado.\n\n"
                "Use */sentinela configurar* primeiro para cadastrar sua loja."
            )
        
        if not config["is_active"]:
            return _txt(
                "⏸️ Sentinela está pausado.\n\n"
                "Use */sentinela ativar* para reativar o monitoramento."
            )
        
        # Agenda execução em background
        return {
            "type": "background_task",
            "task": "run_sentinel",
            "text": (
                "⏳ *Rodando o Sentinela agora...*\n\n"
                "Vou buscar concorrentes, comparar com o histórico e te avisar se encontrar novidades.\n\n"
                "_Isso pode levar alguns minutos._"
            ),
            "user_id": user_id,
            "config": config,
        }
    
    # /sentinela pausar
    if lower in {"/sentinela pausar", "/sentinela parar"}:
        config = get_sentinel_config(user_id)
        if not config:
            return _txt("❌ Sentinela não configurado.")
        
        from shopee_core.sentinel_whatsapp_service import save_sentinel_config
        save_sentinel_config(
            user_id=user_id,
            shop_url=config["shop_url"],
            username=config["username"],
            shop_id=config["shop_id"],
            keywords=config["keywords"],
            is_active=False,
            interval_minutes=config["interval_minutes"],
        )
        
        return _txt(
            "⏸️ *Sentinela pausado*\n\n"
            "O monitoramento automático foi desativado.\n"
            "Use */sentinela ativar* para reativar."
        )
    
    # /sentinela ativar
    if lower in {"/sentinela ativar", "/sentinela ativo"}:
        config = get_sentinel_config(user_id)
        if not config:
            return _txt("❌ Sentinela não configurado.")
        
        from shopee_core.sentinel_whatsapp_service import save_sentinel_config
        save_sentinel_config(
            user_id=user_id,
            shop_url=config["shop_url"],
            username=config["username"],
            shop_id=config["shop_id"],
            keywords=config["keywords"],
            is_active=True,
            interval_minutes=config["interval_minutes"],
        )
        
        return _txt(
            "🟢 *Sentinela ativado*\n\n"
            "O monitoramento automático foi reativado.\n"
            "Use */sentinela rodar* para fazer uma checagem agora."
        )
    
    # /sentinela cancelar
    if lower in {"/sentinela cancelar", "/sentinela remover", "/sentinela deletar"}:
        config = get_sentinel_config(user_id)
        if not config:
            return _txt("❌ Sentinela não configurado.")
        
        delete_sentinel_config(user_id)
        return _txt(
            "🗑️ *Configuração removida*\n\n"
            "O Sentinela foi desconfigurado.\n"
            "Use */sentinela configurar* para configurar novamente."
        )

    # /sentinela keywords
    if lower in {"/sentinela keywords", "/sentinela palavras"}:
        config = get_sentinel_config(user_id)
        if not config:
            return _txt("❌ Sentinela não configurado.")
        
        clear_session(user_id)  # Limpa qualquer sessão anterior
        save_session(user_id, "awaiting_sentinel_keywords_update", {
            "config": config
        })
        
        current_keywords = config.get("keywords", [])
        current_text = "\n".join(f"• {kw}" for kw in current_keywords[:10])
        if len(current_keywords) > 10:
            current_text += f"\n• ... e mais {len(current_keywords) - 10} keywords"
        
        return _txt(
            f"🔍 *Atualizar Keywords*\n\n"
            f"Keywords atuais ({len(current_keywords)}):\n{current_text}\n\n"
            f"Envie as novas keywords, uma por linha:\n\n"
            f"*Exemplo:*\n"
            f"mochila infantil princesa\n"
            f"mochila escolar rosa\n"
            f"mochila infantil feminina\n\n"
            f"_Ou envie */cancelar* para manter as atuais._"
        )
    
    # Comando não reconhecido
    return _txt(
        "❓ Comando não reconhecido.\n\n"
        "Use */sentinela* para ver os comandos disponíveis."
    )

def _handle_sentinel_shop_url(user_id: str, url: str) -> dict:
    """
    Valida a URL da loja para configuração do Sentinela.
    """
    url = url.strip()

    # Validação rápida de URL
    if not url.startswith("http") or "shopee.com.br" not in url:
        return _txt(
            "❌ URL inválida. Use o formato:\n"
            "https://shopee.com.br/nome_da_loja"
        )

    # Agenda carregamento da loja em background
    save_session(user_id, "processing_sentinel_load_shop", {"shop_url": url})

    log.info(f"[WA] Agendando carregamento de loja para Sentinela: url={url!r} user={user_id}")

    return {
        "type": "background_task",
        "task": "load_shop_for_sentinel",
        "text": (
            "⏳ *Carregando sua loja...*\n\n"
            "Estou analisando os produtos para gerar keywords de monitoramento.\n"
            "Vou te mostrar as keywords em instantes!"
        ),
        "shop_url": url,
        "user_id": user_id,
    }


def _handle_sentinel_keywords_manual(user_id: str, text: str, data: dict) -> dict:
    """
    Processa keywords manuais enviadas pelo usuário.
    """
    text = text.strip()
    
    if text.lower() in {"cancelar", "/cancelar", "sair", "parar"}:
        clear_session(user_id)
        return _txt(
            "❌ Configuração do Sentinela cancelada.\n\n"
            "Use */sentinela configurar* para tentar novamente."
        )
    
    # Processa keywords enviadas
    keywords = _parse_manual_keywords(text)
    
    if len(keywords) < 1:
        return _txt(
            "⚠️ Por favor, envie pelo menos *1 keyword* para monitoramento.\n\n"
            "*Exemplo:*\n"
            "mochila infantil princesa\n"
            "mochila escolar rosa\n\n"
            "_Ou envie */cancelar* para interromper._"
        )
    
    if len(keywords) > 20:
        return _txt(
            f"⚠️ Muitas keywords ({len(keywords)}). Máximo permitido: *20*.\n\n"
            "Envie de 3 a 5 keywords mais específicas."
        )
    
    # Salva configuração final
    from shopee_core.sentinel_whatsapp_service import save_sentinel_config
    
    shop_url = data.get("shop_url", "")
    username = data.get("username", "")
    shop_id = data.get("shop_id", "")
    
    save_sentinel_config(
        user_id=user_id,
        shop_url=shop_url,
        username=username,
        shop_id=shop_id,
        keywords=keywords,
        is_active=True,
        interval_minutes=360,  # 6 horas padrão
    )
    
    clear_session(user_id)
    
    keywords_text = "\n".join(f"• {kw}" for kw in keywords)
    
    return _txt(
        f"✅ *Sentinela configurado!*\n\n"
        f"🏪 Loja: *{username}*\n"
        f"🔍 Keywords manuais ({len(keywords)}):\n{keywords_text}\n\n"
        f"Use */sentinela rodar* para fazer a primeira checagem agora.\n"
        f"Use */sentinela status* para ver o status completo.\n\n"
        f"_💡 Dica: Use */sentinela keywords* para atualizar as keywords depois._"
    )


def _handle_sentinel_keywords_update(user_id: str, text: str, data: dict) -> dict:
    """
    Processa atualização de keywords existentes.
    """
    text = text.strip()
    
    if text.lower() in {"cancelar", "/cancelar", "sair", "parar"}:
        clear_session(user_id)
        return _txt(
            "❌ Atualização cancelada.\n\n"
            "Keywords mantidas como estavam."
        )
    
    # Processa novas keywords
    keywords = _parse_manual_keywords(text)
    
    if len(keywords) < 1:
        return _txt(
            "⚠️ Por favor, envie pelo menos *1 keyword*.\n\n"
            "_Ou envie */cancelar* para manter as atuais._"
        )
    
    if len(keywords) > 20:
        return _txt(
            f"⚠️ Muitas keywords ({len(keywords)}). Máximo: *20*.\n\n"
            "Envie keywords mais específicas."
        )
    
    # Atualiza configuração
    config = data.get("config", {})
    
    from shopee_core.sentinel_whatsapp_service import save_sentinel_config
    save_sentinel_config(
        user_id=user_id,
        shop_url=config.get("shop_url", ""),
        username=config.get("username", ""),
        shop_id=config.get("shop_id", ""),
        keywords=keywords,
        is_active=config.get("is_active", True),
        interval_minutes=config.get("interval_minutes", 360),
    )
    
    clear_session(user_id)
    
    keywords_text = "\n".join(f"• {kw}" for kw in keywords)
    
    return _txt(
        f"✅ *Keywords atualizadas!*\n\n"
        f"🔍 Novas keywords ({len(keywords)}):\n{keywords_text}\n\n"
        f"Use */sentinela rodar* para testar com as novas keywords."
    )


def _parse_manual_keywords(text: str) -> list[str]:
    """
    Processa texto de keywords manuais.
    Aceita separação por linhas ou vírgulas.
    """
    keywords = []
    
    # Tenta separar por linhas primeiro
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    if len(lines) > 1:
        # Múltiplas linhas - usa cada linha como keyword
        keywords = lines
    else:
        # Uma linha - tenta separar por vírgulas
        parts = [part.strip() for part in text.split(',') if part.strip()]
        keywords = parts
    
    # Limpa e valida keywords
    cleaned_keywords = []
    for kw in keywords:
        kw = kw.strip().lower()
        # Remove caracteres especiais, mantém apenas letras, números e espaços
        import re
        kw = re.sub(r'[^\w\s]', '', kw)
        kw = re.sub(r'\s+', ' ', kw)  # Remove espaços múltiplos
        
        # Filtra keywords válidas (mínimo 3 caracteres)
        if len(kw) >= 3 and kw not in cleaned_keywords:
            cleaned_keywords.append(kw)
    
    return cleaned_keywords[:20]  # Limita a 20 keywords


def _handle_sentinel_confirmation(user_id: str, text: str, data: dict) -> dict:
    """
    Processa a confirmação das keywords do Sentinela.
    """
    lower = text.lower().strip()
    
    if lower in {"confirmar", "sim", "ok", "confirma", "aceitar"}:
        # Salva configuração final
        from shopee_core.sentinel_whatsapp_service import save_sentinel_config
        
        shop_url = data.get("shop_url", "")
        username = data.get("username", "")
        shop_id = data.get("shop_id", "")
        keywords = data.get("keywords", [])
        
        save_sentinel_config(
            user_id=user_id,
            shop_url=shop_url,
            username=username,
            shop_id=shop_id,
            keywords=keywords,
            is_active=True,
            interval_minutes=360,  # 6 horas padrão
        )
        
        clear_session(user_id)
        
        keywords_text = "\n".join(f"• {kw}" for kw in keywords[:10])
        if len(keywords) > 10:
            keywords_text += f"\n• ... e mais {len(keywords) - 10} keywords"
        
        return _txt(
            f"✅ *Sentinela configurado!*\n\n"
            f"🏪 Loja: *{username}*\n"
            f"🔍 Keywords monitoradas ({len(keywords)}):\n{keywords_text}\n\n"
            f"Use */sentinela rodar* para fazer a primeira checagem agora.\n"
            f"Use */sentinela status* para ver o status completo."
        )
    
    elif lower in {"cancelar", "não", "nao", "recusar"}:
        clear_session(user_id)
        return _txt(
            "❌ Configuração cancelada.\n\n"
            "Use */sentinela configurar* para tentar novamente."
        )
    
    else:
        return _txt(
            "Por favor, responda:\n"
            "• *Confirmar* - para aceitar as keywords\n"
            "• *Cancelar* - para cancelar a configuração"
        )


def _handle_shop_url(user_id: str, url: str) -> dict:
    """
    Valida a URL e delega o carregamento da loja para background (Fase 3D).

    Retorna type="background_task", task="load_shop" para que o api_server.py:
      1. Envie "\u23f3 Carregando sua loja..." imediatamente
      2. Agende _run_load_shop_bg() via BackgroundTasks
      3. Ao terminar: salve sessao awaiting_product_index e envie a lista
    """
    url = url.strip()

    # Validacao rapida de URL antes de ocupar background
    if not url.startswith("http") or "shopee.com.br" not in url:
        return _txt(
            "❌ URL inválida. Use o formato:\n"
            "https://shopee.com.br/nome_da_loja"
        )

    # Transita para 'processing_load_shop' — guard bloqueia duplicatas
    save_session(user_id, "processing_load_shop", {"shop_url": url})

    log.info(f"[WA] Agendando carregamento de loja background: url={url!r} user={user_id}")

    return {
        "type": "background_task",
        "task": "load_shop",
        "text": (
            "⏳ *Carregando sua loja...*\n\n"
            "Estou buscando os produtos na Shopee. Isso pode levar até 1 minuto.\n"
            "Vou te enviar a lista assim que terminar!"
        ),
        "shop_url": url,
        "user_id": user_id,
        "segmento": DEFAULT_SEGMENTO,
    }


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
            "Envie */cancelar* para interromper."
        )

    products = data.get("products", [])
    segmento = data.get("segmento", DEFAULT_SEGMENTO)

    if index < 0 or index >= len(products):
        return _txt(
            f"❌ Número inválido. Escolha entre *0* e *{len(products) - 1}*.\n"
            "Envie */cancelar* para interromper."
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
        channel="whatsapp",
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
    body = optimization
    footer = (
        "\n\n━━━━━━━━━━━━━━━━━━━━━━\n"
        "Quer otimizar outro produto? Envie */auditar*"
    )
    return header + body + footer

def handle_whatsapp_text(user_id: str, text: str) -> dict:
    return handle_whatsapp_message({"user_id": user_id, "text": text, "has_media": False})

def _handle_media_message(user_id: str, msg: dict, state: str, data: dict) -> dict:
    media_type = msg.get("media_type", "")

    if media_type != "image":
        return _txt(
            "🔴 Ainda só aceito *imagens* para editar.\n\n"
            "Vídeos, áudios e documentos chegam em breve!\n\n"
            "Envie uma foto com uma legenda como:\n"
            "• remova o fundo\n"
            "• gere um cenário de estúdio\n"
            "• analise a imagem"
        )

    caption = msg.get("caption", "").strip()
    if not caption:
        return _txt(
            "🖼️ Recebi sua imagem! O que você quer fazer com ela?\n\n"
            "Exemplos de legenda:\n"
            "• remova o fundo\n"
            "• gere um cenário de estúdio\n"
            "• analise a imagem\n"
            "• remova o fundo e gere um cenário clean"
        )

    # Extrai plano de ações
    plan = extract_media_plan(caption)
    
    # Se for pedido de esclarecimento, responde imediatamente
    if plan and plan[0].get("action") == "clarify":
        return _txt(plan[0].get("message", "Por favor, esclareça sua solicitação."))
    
    log.info(f"[WA] Mídia: media_type={media_type} plan={plan} caption={caption[:60]!r} base64_len={len(msg.get('base64_data', ''))}")

    # Cria job_id para controle de cancelamento
    from shopee_core.media_jobs import create_media_job
    
    # Usa a primeira ação como identificador do job
    first_action = plan[0].get("action", "unknown") if plan else "unknown"
    job_id = create_media_job(user_id, first_action)
    log.info(f"[WA] Job criado: job_id={job_id} user={user_id} plan={plan}")

    save_session(user_id, "processing_media", {
        "plan": plan,
        "caption": caption,
        "job_id": job_id,
    })

    # Monta mensagem de processamento
    if len(plan) > 1:
        steps_text = format_plan_steps(plan)
        wait_text = (
            f"⏳ *Processando sua imagem...*\n\n"
            f"Etapas detectadas:\n{steps_text}\n\n"
            f"Isso pode levar alguns segundos.\n"
            f"_Envie /cancelar para interromper._"
        )
    else:
        wait_text = (
            "⏳ *Processando sua imagem...*\n\n"
            "Isso pode levar alguns segundos.\n\n"
            "_Envie /cancelar para interromper._"
        )

    return {
        "type": "background_task",
        "task": "process_media",
        "text": wait_text,
        "user_id": user_id,
        "msg": msg,
        "plan": plan,
        "job_id": job_id,
    }
