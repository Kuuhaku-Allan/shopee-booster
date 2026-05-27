"""
app.py — Orquestrador do Shopee Booster 4.0.0
============================================
Este arquivo controla APENAS:
  - Configuração da página e API key
  - Navegação entre partições (via sidebar)
  - Renderização das partições de UI

Para alterar lógica de scraping/IA → backend_core.py
Para alterar cores/tipografia/CSS → ui_theme.py
"""

import streamlit as st
import streamlit.elements.image as st_image
import json

# ── Monkeypatch para st_canvas (Correção de compatibilidade Streamlit 1.55) ──
if not hasattr(st_image, "image_to_url"):
    try:
        from streamlit.elements.lib.image_utils import image_to_url as _image_to_url
        from types import SimpleNamespace
        
        def image_to_url_wrapper(data, width_or_config, *args, **kwargs):
            # args na ordem do st_canvas (formato antigo):
            # (use_container_width, clamp, channels, output_format, image_id)
            
            if isinstance(width_or_config, int):
                # Extrai os valores passados pelo st_canvas
                use_container_width = args[0] if len(args) > 0 else True
                clamp               = args[1] if len(args) > 1 else False
                channels            = args[2] if len(args) > 2 else "RGB"
                output_format       = args[3] if len(args) > 3 else "PNG"
                image_id            = args[4] if len(args) > 4 else ""
                
                # Monta o objeto de configuração que o Streamlit 1.55 espera
                layout_config = SimpleNamespace(
                    width=width_or_config,
                    use_container_width=use_container_width
                )
                
                # Chama a função real com a NOVA ORDEM de argumentos do Streamlit 1.55:
                # (image, layout_config, clamp, channels, output_format, image_id)
                return _image_to_url(data, layout_config, clamp, channels, output_format, image_id, **kwargs)
            
            return _image_to_url(data, width_or_config, *args, **kwargs)
            
        st_image.image_to_url = image_to_url_wrapper
    except ImportError:
        try:
            from streamlit.runtime.image_util import image_to_url as _image_to_url # type: ignore
            st_image.image_to_url = _image_to_url
        except ImportError:
            st_image.image_to_url = lambda *args, **kwargs: ""

import pandas as pd
import sys
import os
import io
import time

import nest_asyncio
from dotenv import load_dotenv
from release_meta import VERSAO_ATUAL

nest_asyncio.apply()

# ── Configuração de ambiente (deve rodar ANTES de qualquer import pesado) ──
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["ORT_LOGGING_LEVEL"] = "3"
os.environ["ONNXRUNTIME_PROVIDERS"] = "CPUExecutionProvider"

if getattr(sys, "frozen", False):
    CONFIG_DIR = os.path.dirname(sys.executable)
else:
    CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_ENV = os.path.join(CONFIG_DIR, ".shopee_config")
load_dotenv(CONFIG_ENV)
API_KEY = os.getenv("GOOGLE_API_KEY")

# ── Configuração da página (deve ser a PRIMEIRA chamada st.*) ──────────────
st.set_page_config(
    page_title=f"Shopee Booster {VERSAO_ATUAL}",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Tela de configuração da API Key (se não tiver) ────────────────────────
if not API_KEY:
    from ui_theme import init_theme, apply_theme
    init_theme()
    apply_theme()

    st.markdown("""
    <div style="max-width:480px; margin:4rem auto; text-align:center;">
        <div style="font-size:48px; margin-bottom:1rem;">🔑</div>
        <h1 style="font-size:24px; font-weight:800; margin-bottom:0.5rem;">Configurar API Key</h1>
        <p style="color:var(--text-secondary); font-size:14px; margin-bottom:2rem;">
            O Shopee Booster usa o Google Gemini para análise com IA.<br>
            Insira sua chave abaixo — ela será salva localmente.
        </p>
    </div>
    """, unsafe_allow_html=True)

    col_center = st.columns([1, 2, 1])[1]
    with col_center:
        nova_chave = st.text_input(
            "GOOGLE_API_KEY",
            type="password",
            placeholder="AIzaSy...",
            help="Obtenha gratuitamente em aistudio.google.com"
        )
        st.info("💡 Chave salva em `.shopee_config` — não precisa inserir novamente.")

        if st.button("🚀 Salvar e Iniciar", type="primary", width='stretch'):
            if nova_chave.strip().startswith("AIza"):
                try:
                    with open(CONFIG_ENV, "w", encoding="utf-8") as f:
                        f.write(f"GOOGLE_API_KEY={nova_chave.strip()}\n")
                    st.success("✅ Chave configurada! Reiniciando...")
                    time.sleep(1.5)
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")
            else:
                st.error("⚠️ Chave inválida. Deve começar com 'AIza'.")

    st.stop()

# ── Imports do backend e UI (apenas depois de confirmar API key) ───────────
from backend_core import (
    salvar_ou_baixar, resolve_shopee_url,
    fetch_shop_info, fetch_shop_products_intercept,
    fetch_competitors_intercept, fetch_reviews_intercept,
    generate_full_optimization, build_catalog_context,
    chat_with_gemini, analyze_reviews_with_gemini,
    generate_ai_scenario, generate_gradient_background,
    apply_contact_shadow, improve_image_quality, upscale_image,
    MODELOS_VISION, client,
    build_full_chat_context, detect_chat_intent,
    analyze_product_image_vision, process_chat_turn,
    suggest_faq_from_history, MODELOS_TEXTO, get_client,
)
from PIL import Image
from ui_theme import init_theme, apply_theme, render_theme_toggle

# ── Inicialização ─────────────────────────────────────────────────────────
init_theme()
apply_theme()

# Session state
_DEFAULTS = {
    "nav_partition":           "auditoria",
    "selected_product":        None,
    "selected_kw":             None,
    "shop_data":               None,
    "shop_produtos":           None,
    "df_competitors":          None,
    "auto_search_competitors": False,
    "optimization_reviews":    None,
    "optimization_result":     None,
    "auto_fetch_opt_reviews":  False,
    # Chatbot
    "chat_history":            [],
    "chatbot_active":          False,
    "faq_personalizado":       [],
    "chat_attachments":        [],
    "chat_attachment_types":   [],
    "chat_attachment_previews":[],
    "show_attach_panel":       False,
    "chat_preview_images":     [],
    "chat_preview_captions":   [],
    "faq_ia_geral":            None,
    "chat_active_edit_image":  None,   # PIL.Image em edição persistente
    "chat_active_edit_label":  "",     # legenda da imagem em edição
    "chat_last_post_actions":  [],     # ações pós-resposta do último turno
    "chat_edit_history":       [],     # Histórico de edições para desfazer
    "chat_canvas_layers":      [],     # [{ "name": str, "img": PIL, "visible": bool, "type": str }]
    "chat_canvas_roi":         {"x": 25, "y": 25, "w": 50, "h": 50, "shape": "rect"}, # ROI em %
    "chat_canvas_freehand_mask": None,
    "canvas_tool":             "rect",
    "canvas_mode":             "draw",
    "canvas_undo_stack":        [],     # Pilha para desfazer ações no canvas
    "canvas_redo_stack":        [],     # Pilha para refazer ações no canvas
    "canvas_pending_layer":     None,   # { "img": PIL, "name": str, "intent": str }
    "canvas_compare_mode":      False,  # Modo comparação original vs atual
    "canvas_moving_layer":      None,   # Index da camada sendo movida manualmente
    "canvas_move_snapshot":     None,   # Snapshot da camada antes de mover
    "canvas_move_temp":         None,   # Posição temporária durante movimento
}

for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


def _escape_markdown_currency(text):
    """Avoid Streamlit Markdown treating BRL dollar signs as math delimiters."""
    return str(text).replace("$", r"\$")


def _is_force_fallback_app() -> bool:
    """R7.0A: Verifica se SHOPEE_FORCE_RADAR_STORE_FALLBACK esta ativo.

    Aceita (case insensitive): true, 1, yes, sim
    Por padrao e False. Apenas para teste/debug.
    """
    raw = os.environ.get("SHOPEE_FORCE_RADAR_STORE_FALLBACK", "").strip().lower()
    return raw in {"true", "1", "yes", "sim"}


def _save_audit_store_mirror(username, shop_data, products, source_url):
    """Salva snapshot no espelho local. Nunca chamado em modo force-fallback."""
    if not products:
        return
    try:
        from shopee_core.radar_store_service import save_store_snapshot

        shopid = (shop_data or {}).get("shopid") or (shop_data or {}).get("shop_id")
        summary = save_store_snapshot(
            {
                "shop_uid": str(shopid) if shopid else None,
                "shop_slug": username,
                "shop_name": (shop_data or {}).get("name") or username,
                "marketplace": "shopee",
                "source_url": source_url,
            },
            products,
            source="auditoria_pro",
        )
        store_uid = summary.get("store_uid", "?")
        total = summary.get("total_received", 0)
        print(f"[R7.0] Espelho da loja atualizado: store_uid={store_uid} produtos={total}")
        st.caption(f"[R7.0] Espelho da loja atualizado: store_uid={store_uid} produtos={total}")
    except Exception as exc:
        print(f"[R7.0] Falha ao atualizar espelho da loja: {exc}")


def _load_audit_store_mirror(username, shop_data=None):
    """Carrega produtos do espelho local (leitura apenas)."""
    try:
        from shopee_core.radar_store_service import get_cached_store_products

        shopid = (shop_data or {}).get("shopid") or (shop_data or {}).get("shop_id")
        cached = get_cached_store_products(
            shop_uid=str(shopid) if shopid else None,
            shop_slug=username,
        )
        if not cached:
            print(f"[R7.0] Nenhum espelho local encontrado para shop_slug={username} shop_uid={shopid or '?'}")
        return cached
    except Exception as exc:
        print(f"[R7.0] Falha ao ler espelho local do Radar: {exc}")
        return []


# ══════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    # Brand
    st.markdown(f"""
    <div class="brand-logo">
        <div class="brand-logo-icon">🛍️</div>
        <div>
            <div class="brand-logo-text">Shopee Booster</div>
            <div class="brand-logo-sub">v{VERSAO_ATUAL} · Suite Pro</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Navegação principal via radio estilizado
    st.markdown('<div class="nav-section-label">Partições</div>', unsafe_allow_html=True)

    nav = st.radio(
        "nav",
        options=["auditoria", "chatbot", "sentinela", "espelho_loja", "radar_workflow"],
        format_func=lambda x: (
            "🕵️  Auditoria Pro" if x == "auditoria"
            else "🤖  Chatbot Concierge" if x == "chatbot"
            else "📡  Sentinela" if x == "sentinela"
            else "🏪  Espelho da Loja" if x == "espelho_loja"
        else "🎯  Radar Assistido"
        ),
        key="nav_partition",
        label_visibility="collapsed",
    )

    st.markdown("---")

    # Configurações
    st.markdown('<div class="nav-section-label">Configurações</div>', unsafe_allow_html=True)
    segmento = st.selectbox(
        "Nicho do Produto",
        ["Escolar / Juvenil", "Profissional / Tech", "Viagem", "Moda"],
        help="Define o perfil de análise e geração de cenários IA"
    )

    st.markdown("---")

    # Status da loja carregada (se houver)
    if st.session_state.shop_data:
        shop_name = st.session_state.shop_data.get("name", "Loja")
        st.markdown(f"""
        <div class="loja-status-bar">
            🏪 {shop_name}
        </div>
        """, unsafe_allow_html=True)
        n_prod = len(st.session_state.shop_produtos or [])
        st.caption(f"📦 {n_prod} produtos carregados")
    else:
        st.caption("Nenhuma loja carregada")

    st.markdown("---")
    render_theme_toggle()

    # ── Reconfigurar API Key ───────────────────────────────────
    st.markdown("---")
    with st.expander("🔑 Reconfigurar API Key"):
        nova_chave = st.text_input(
            "Nova GOOGLE_API_KEY",
            type="password",
            placeholder="AIzaSy...",
            key="sidebar_new_key"
        )
        if st.button("💾 Salvar chave", key="btn_salvar_chave", width='stretch'):
            if nova_chave.strip().startswith("AIza"):
                try:
                    with open(CONFIG_ENV, "w", encoding="utf-8") as f:
                        f.write(f"GOOGLE_API_KEY={nova_chave.strip()}\n")
                    st.success("✅ Chave salva! Reiniciando...")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")
            else:
                st.error("Chave inválida (deve começar com 'AIza')")



# ══════════════════════════════════════════════════════════════════════════
# PARTIÇÃO I — AUDITORIA PRO
# ══════════════════════════════════════════════════════════════════════════
def render_auditoria():
    from backend_core import (
        salvar_ou_baixar, resolve_shopee_url, fetch_shop_info, fetch_shop_products_intercept, fetch_competitors_intercept, fetch_reviews_intercept, generate_full_optimization, build_catalog_context, chat_with_gemini, analyze_reviews_with_gemini, generate_ai_scenario, generate_gradient_background, apply_contact_shadow, improve_image_quality, upscale_image, MODELOS_VISION, client, build_full_chat_context, detect_chat_intent, analyze_product_image_vision, process_chat_turn, suggest_faq_from_history, MODELOS_TEXTO, get_client
    )
    from PIL import Image
    # ── Cabeçalho ─────────────────────────────────────────────
    st.markdown("""
    <div class="page-header">
        <div class="page-header-icon">🕵️</div>
        <div>
            <div class="page-header-title">Auditoria Pro</div>
            <div class="page-header-sub">Análise completa da loja, concorrentes e estúdio de mídia</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Input URL da loja ──────────────────────────────────────
    col_url, col_btn = st.columns([5, 1])
    with col_url:
        url_loja = st.text_input(
            "URL da Loja",
            placeholder="https://shopee.com.br/nome_da_loja",
            label_visibility="collapsed"
        )
    with col_btn:
        btn_analisar = st.button("🔍 Analisar", type="primary", width='stretch')

    if url_loja and btn_analisar:
        resolved = resolve_shopee_url(url_loja)
        if not resolved or resolved["type"] != "shop":
            st.error("URL inválida. Use o formato: shopee.com.br/nome_da_loja")
        else:
            username = resolved["username"]

            # -- R7.0A: modo de teste — força espelho local, sem chamar Shopee --
            if _is_force_fallback_app():
                print(f"[R7.0] SHOPEE_FORCE_RADAR_STORE_FALLBACK ativo — pulando Shopee (shop_slug={username})")
                st.warning("⚠️ **Modo debug:** SHOPEE_FORCE_RADAR_STORE_FALLBACK ativo — usando espelho local.")
                cached_products = _load_audit_store_mirror(username)
                if cached_products:
                    print(f"[R7.0] Usando espelho local do Radar como fallback: shop_slug={username} produtos={len(cached_products)}")
                    st.session_state.shop_data = {
                        "name": username,
                        "username": username,
                        "source": "espelho local do Radar",
                    }
                    st.session_state.shop_produtos = cached_products
                    st.info(f"✅ Espelho local do Radar: {len(cached_products)} produto(s) carregados para '{username}'.")
                    st.rerun()
                else:
                    print(f"[R7.0] Nenhum espelho local encontrado para shop_slug={username} (fallback forçado ativo)")
                    st.error(
                        f"Nenhum espelho local encontrado para '{username}'. "
                        "Execute uma auditoria normal primeiro para criar o espelho."
                    )
            else:
                # -- Fluxo normal: carrega dados da loja via Shopee/Playwright --
                with st.spinner("Abrindo Shopee e interceptando dados... (30-60s)"):
                    shop_raw = fetch_shop_info(username)

                d = shop_raw.get("data", shop_raw)
                if d:
                    st.session_state.shop_data = d
                    shopid = d.get("shopid") or d.get("shop_id")
                    with st.spinner("Carregando catálogo de produtos..."):
                        produtos_loja = fetch_shop_products_intercept(username, shopid)
                    if produtos_loja:
                        _save_audit_store_mirror(username, d, produtos_loja, url_loja)
                    else:
                        produtos_loja = _load_audit_store_mirror(username, d)
                        if produtos_loja:
                            st.info("Usando espelho local do Radar como fonte do catálogo da loja.")
                    st.session_state.shop_produtos = produtos_loja
                    st.rerun()
                else:
                    cached_products = _load_audit_store_mirror(username)
                    if cached_products:
                        st.session_state.shop_data = {
                            "name": username,
                            "username": username,
                            "source": "espelho local do Radar",
                        }
                        st.session_state.shop_produtos = cached_products
                        st.info("Shopee indisponível agora. Usando espelho local do Radar.")
                        st.rerun()
                    else:
                        st.error("Não foi possível carregar os dados da loja.")

    # ── Métricas da loja (se carregada) ────────────────────────
    if st.session_state.shop_data:
        d = st.session_state.shop_data
        shop_name = d.get("name", "Loja")

        st.markdown(f'<div class="loja-status-bar">🏪 {shop_name} — dados carregados com sucesso</div>',
                    unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🏪 Nome", d.get("name", "—"))
        c2.metric("👥 Seguidores", f"{d.get('follower_count', 'N/D'):,}" if isinstance(d.get('follower_count'), int) else d.get('follower_count', 'N/D'))
        c3.metric("📦 Produtos", d.get("item_count", "N/D"))
        c4.metric("⭐ Avaliação", d.get("rating_star", "N/D"))

        rr = d.get("chat_response_rate") or d.get("response_rate")
        if rr:
            st.metric("💬 Taxa de Resposta", f"{rr}%")
            if rr < 95:
                st.warning("⚠️ Taxa de resposta abaixo de 95% prejudica o ranking.")

    # ── Painel de Otimização Completa ──────────────────────────
    if st.session_state.selected_product:
        prod = st.session_state.selected_product
        st.markdown("---")
        st.markdown(f"""
        <div class="page-header" style="margin-bottom:1rem;">
            <div class="page-header-icon">⚡</div>
            <div>
                <div class="page-header-title" style="font-size:18px;">Otimização: {prod['name'][:45]}</div>
                <div class="page-header-sub">Análise completa de concorrentes + avaliações + IA</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        col_img, col_info = st.columns([1, 3])
        with col_img:
            img_url = prod["image"] if prod["image"].startswith("http") else f"https://down-br.img.susercontent.com/file/{prod['image']}"
            st.image(img_url, width='stretch')
        with col_info:
            st.markdown(f"**Nome atual:** {prod['name']}")
            st.markdown(f"**Preço atual:** R$ {prod['price']:.2f}")
            st.markdown(f"**Item ID:** `{prod['itemid']}`")
            if st.button("✕ Desselecionar produto"):
                st.session_state.selected_product = None
                st.session_state.optimization_result = None
                st.session_state.optimization_reviews = None
                st.rerun()

        if st.session_state.auto_fetch_opt_reviews:
            st.session_state.auto_fetch_opt_reviews = False
            with st.spinner(f"🔍 Buscando avaliações do mercado... (30-60s)"):
                reviews_opt, _ = fetch_reviews_intercept(
                    str(prod["itemid"]), str(prod["shopid"]),
                    product_url="", product_name_override=prod["name"]
                )
                st.session_state.optimization_reviews = reviews_opt

        df_comp = st.session_state.df_competitors
        reviews_opt = st.session_state.optimization_reviews

        c1, c2 = st.columns(2)
        with c1:
            if df_comp is not None and not df_comp.empty:
                st.success(f"✅ {len(df_comp)} concorrentes coletados")
            else:
                st.warning("⏳ Concorrentes ainda não carregados — use a aba Radar abaixo")
        with c2:
            if reviews_opt:
                st.success(f"✅ {len(reviews_opt)} avaliações do mercado coletadas")
            else:
                st.warning("⚠️ Sem avaliações — a IA usará só os dados de concorrentes")

        # ── R7.5: Base de Mercado automática ──────────────────
        st.markdown("##### 📊 Base de Mercado")

        market_source_info = st.empty()
        radar_cache_key = f"_radar_status_{prod.get('itemid', '')}"

        # Auto-detect radar if we have a product
        if prod and prod.get("name"):
            import os as _os
            try:
                from shopee_core.audit_market_source_service import get_radar_market_status_for_audit
                _rs = get_radar_market_status_for_audit(prod)
                st.session_state[radar_cache_key] = _rs
            except Exception:
                _rs = {"has_radar": False, "confidence_level": None, "warnings": []}
                st.session_state[radar_cache_key] = _rs

            _rs = st.session_state.get(radar_cache_key, {})
            if _rs.get("has_radar"):
                _cl = _rs.get("confidence_level", "N/A")
                _dc = _rs.get("effective_competitor_count") or _rs.get("direct_count", 0)
                _icon = "🟢" if _cl == "high" else "🟡" if _cl == "medium" else "🟠"
                market_source_info.success(
                    f"{_icon} **Radar disponível:** confiança **{_cl}**, "
                    f"**{_dc}** concorrentes efetivos. "
                    "A fonte será escolhida automaticamente."
                )
                if _rs.get("warnings"):
                    for _w in _rs["warnings"]:
                        st.caption(f"⚠️ {_w}")
            else:
                market_source_info.info(
                    "ℹ️ Este produto não possui base Radar. "
                    "A auditoria usará dados de scraping em tempo real."
                )
                if df_comp is None or df_comp.empty:
                    st.caption("⚠️ Nenhum scraping disponível ainda. Use a aba '📡 Radar de Concorrentes' abaixo para buscar.")

        # Debug behind env var
        import os as _os2
        debug_radar_mode = False
        if _os2.environ.get("SHOPEE_DEV_DEBUG_RADAR", "").strip().lower() in ("true", "1", "yes"):
            debug_radar_mode = st.checkbox(
                "🐛 Debug: mostrar contexto do Radar sem chamar IA",
                value=False,
                key="debug_radar_mode",
                help="Mostra o contexto que seria enviado ao Gemini sem fazer a chamada real"
            )

        if st.button("🤖 Gerar Otimização Completa", type="primary"):
            try:
                if debug_radar_mode:
                    from shopee_core.audit_market_source_service import choose_audit_market_source

                    _rs_cache = st.session_state.get(radar_cache_key, {})
                    market_source_result = choose_audit_market_source(
                        prod, df_comp, _rs_cache if _rs_cache.get("has_radar") else None
                    )
                    st.info("🐛 **Modo Debug**")
                    st.json(market_source_result)
                    st.info("ℹ️ Modo debug ativo - IA não foi chamada.")
                    st.session_state.optimization_result = None
                    st.session_state["_market_source_result"] = market_source_result
                else:
                    from shopee_core.audit_service import generate_product_optimization

                    with st.spinner("IA analisando concorrentes + avaliações e gerando listing..."):
                        audit_result = generate_product_optimization(
                            product=prod,
                            segmento=segmento,
                            api_key=API_KEY,
                        )
                    if not audit_result.get("ok"):
                        st.error(audit_result.get("message", "Não foi possível gerar a otimização."))
                        st.session_state.optimization_result = None
                    else:
                        data = audit_result.get("data", {})
                        st.session_state.optimization_result = data.get("optimization")
                        st.session_state["_market_source_result"] = data.get("market_source_details") or {
                            "source": data.get("market_source"),
                            "reason": data.get("market_source_reason"),
                            "radar_used": data.get("radar_used"),
                            "scraping_used": data.get("scraping_used"),
                            "confidence_level": data.get("radar_confidence"),
                            "radar_report_uid": data.get("radar_report_uid"),
                            "warnings": data.get("warnings", []),
                            "radar_status": data.get("radar_status"),
                        }

            except Exception as e:
                st.error(f"Erro ao gerar otimização automática: {e}")
                print(f"[R7.5A] Erro: {e}")
                import traceback; traceback.print_exc()

        if st.session_state.optimization_result:
            st.markdown("---")

            # R7.5: Badge da base usada
            market_source_result = st.session_state.get("_market_source_result", {})
            source = market_source_result.get("source", "")
            reason = market_source_result.get("reason", "")
            radar_used = market_source_result.get("radar_used", False)

            if source == "radar" or source == "hybrid":
                source_label = "Radar + Scraping" if source == "hybrid" else "Radar"
                st.success(f"📡 **Base usada: {source_label}** — {reason}")
                _rs_cache = st.session_state.get(radar_cache_key, {})
                _radar_uid = (
                    market_source_result.get("radar_product_uid")
                    or _rs_cache.get("radar_product_uid")
                    or _rs_cache.get("product_uid")
                )
                if _radar_uid:
                    with st.expander("📊 Ver detalhes da base usada"):
                        try:
                            from shopee_core.radar_ui_service import get_radar_preview_for_ui
                            from shopee_core.audit_output_formatter import format_brl
                            preview = get_radar_preview_for_ui(_radar_uid)
                            if preview["ok"]:
                                col_r1, col_r2 = st.columns(2)
                                with col_r1:
                                    st.markdown(f"**Confiança:** {preview['confidence']}")
                                    st.markdown(f"**Concorrentes diretos:** {preview['direct_count']}")
                                    st.markdown(f"**Faixa de preço:** " + _escape_markdown_currency(
                                        f"{format_brl(preview['price_min'])} - {format_brl(preview['price_max'])}"
                                    ))
                                    st.markdown(f"**Preço médio:** {format_brl(preview['price_avg'])}")
                                    if preview["strong_terms"]:
                                        st.markdown(f"**Termos fortes:** " + ", ".join(preview["strong_terms"][:5]))
                                with col_r2:
                                    if preview["recommended_features"]:
                                        st.markdown(f"**Features recomendadas:**")
                                        st.caption(", ".join(preview["recommended_features"][:5]))
                                    if preview["off_niche_features"]:
                                        st.markdown(f"**⚠️ Features evitadas (off-niche):**")
                                        st.caption(", ".join(preview["off_niche_features"]))
                            if market_source_result.get("warnings"):
                                for _w in market_source_result["warnings"]:
                                    st.warning(f"⚠️ {_w}")
                        except Exception as e:
                            st.caption(f"Detalhes indisponíveis: {e}")
            elif source == "scraping":
                st.info(f"🌐 **Base usada: Scraping em tempo real** — {reason}")
                if market_source_result.get("warnings"):
                    for _w in market_source_result["warnings"]:
                        st.warning(f"⚠️ {_w}")
            elif source == "none":
                st.warning(f"⚠️ **Nenhuma base de mercado disponível.** {reason}")
            else:
                st.caption(f"Base usada: {source} — {reason}")

            st.markdown("### 📈 Listing Otimizado pela IA")
            from shopee_core.audit_output_formatter import clean_audit_output
            _clean_result = clean_audit_output(st.session_state.optimization_result)
            st.markdown(_clean_result)
            salvar_ou_baixar(
                "Baixar otimização (.txt)",
                data=_clean_result,
                file_name=f"otimizacao_{prod['itemid']}.txt",
                mime="text/plain",
                key=f"dl_full_opt_{prod['itemid']}"
            )

    # ── Tabs de funcionalidades ────────────────────────────────
    st.markdown("---")
    tab_radar, tab_avaliacoes, tab_studio = st.tabs([
        "📡 Radar de Concorrentes",
        "💬 Mineração de Avaliações",
        "🏛️ Estúdio de Mídia"
    ])

    # ── Tab 1: Radar de Concorrentes ──────────────────────────
    with tab_radar:
        st.markdown('<p class="section-label">Busca por Palavra-chave</p>', unsafe_allow_html=True)
        kw = st.text_input(
            "kw",
            value=st.session_state.get("selected_kw") or "mochila escolar",
            placeholder="Ex: mochila escolar, tênis feminino...",
            label_visibility="collapsed",
            key="kw_radar"
        )

        buscar_agora = st.button("🔍 Buscar Concorrentes", key="btn_buscar_concorrentes")

        if st.session_state.auto_search_competitors:
            st.session_state.auto_search_competitors = False
            buscar_agora = True

        if buscar_agora:
            with st.spinner("Navegando na Shopee e interceptando resultados... (30-60s)"):
                rows = fetch_competitors_intercept(kw)

            if rows:
                df = pd.DataFrame(rows)
                df["avaliações"] = pd.to_numeric(df["avaliações"], errors="coerce").fillna(0).astype(int)
                df["curtidas"] = pd.to_numeric(df["curtidas"], errors="coerce").fillna(0).astype(int)
                df["preco"] = pd.to_numeric(df["preco"], errors="coerce").fillna(0)
                st.session_state.df_competitors = df
            else:
                st.session_state.df_competitors = None
                st.error("Nenhum resultado. Verifique os logs de debug acima.")

        df = st.session_state.df_competitors
        if df is not None and not df.empty:
            # Cria cópia formatada para exibição (sem expor IDs internos)
            df_display = pd.DataFrame({
                "Nome":       df["nome"],
                "Preço":      df["preco"].apply(lambda x: f"R$ {x:.2f}"),
                "Avaliações": df["avaliações"].apply(lambda x: f"{int(x):,}".replace(",", ".")),
                "Curtidas":   df["curtidas"].apply(lambda x: f"{int(x):,}".replace(",", ".")),
                "⭐ Estrelas": df["estrelas"].apply(lambda x: f"{x:.1f}"),
            })
            st.table(df_display.reset_index(drop=True))

            c1, c2, c3 = st.columns(3)
            c1.metric("💰 Preço Médio", f"R$ {df['preco'].mean():.2f}")
            c2.metric("📉 Mínimo", f"R$ {df['preco'].min():.2f}")
            c3.metric("📈 Máximo", f"R$ {df['preco'].max():.2f}")
            st.warning(f"💡 Preço de lançamento sugerido: R$ {df['preco'].mean()*0.95:.2f}")

            if df["avaliações"].max() > 0:
                top = df.loc[df["avaliações"].idxmax()]
                st.info(f"🏆 Líder: **{top['nome']}** — {int(top['avaliações'])} avaliações · {int(top['curtidas'])} curtidas")
            else:
                st.info("Produtos novos — sem avaliações ainda. Use curtidas como referência.")

            if st.button("🤖 Analisar padrões com IA", key="btn_analisar_padroes"):
                titulos = "\n".join(df["nome"].tolist())
                insight = analyze_reviews_with_gemini(
                    [f"Títulos dos top sellers:\n{titulos}\n\nIdentifique padrões, keywords mais usadas e sugira um título otimizado."],
                    segmento
                )
                st.write(insight)

    # ── Tab 2: Mineração de Avaliações ────────────────────────
    with tab_avaliacoes:
        st.markdown('<p class="section-label">Extração de Avaliações do Mercado Livre</p>', unsafe_allow_html=True)

        url_comp = ""
        iid = ""
        sid = ""

        url_comp_input = st.text_input(
            "URL do produto concorrente",
            placeholder="https://shopee.com.br/produto-i.123.456",
            key="url_comp_input"
        )
        if url_comp_input:
            res = resolve_shopee_url(url_comp_input)
            if res and res["type"] == "product":
                st.info(f"Item: `{res['itemid']}` | Shop: `{res['shopid']}`")
                iid = res["itemid"]
                sid = res["shopid"]
                url_comp = url_comp_input
            else:
                iid = st.text_input("Item ID", "", key="iid_manual")
                sid = st.text_input("Shop ID", "", key="sid_manual")
        else:
            col_iid, col_sid = st.columns(2)
            with col_iid:
                iid = st.text_input("Item ID", "", key="iid_fallback")
            with col_sid:
                sid = st.text_input("Shop ID", "", key="sid_fallback")

        if st.button("📚 Extrair Avaliações", key="btn_extrair_avaliacoes") and iid and sid:
            with st.spinner("Buscando avaliações no Mercado Livre... (30-60s)"):
                reviews, debug_logs = fetch_reviews_intercept(iid, sid, product_url=url_comp if url_comp else "")

            with st.expander("🔍 Log de execução", expanded=not reviews):
                for line in debug_logs:
                    st.markdown(line)

            if reviews:
                st.success(f"✅ {len(reviews)} avaliações encontradas")
                for i, r in enumerate(reviews, 1):
                    st.write(f"{i}. {r}")
                insight = analyze_reviews_with_gemini(reviews, segmento)
                st.success("🚀 Argumentos de Venda:")
                st.write(insight)
            else:
                st.warning(
                    "⚠️ Sem avaliações encontradas. Veja o log acima. "
                    "**Dica:** Use o Radar de Concorrentes → 'Analisar padrões com IA' para insights equivalentes."
                )

    # ── Tab 3: Estúdio de Mídia ───────────────────────────────
    with tab_studio:
        st.markdown('<p class="section-label">Otimização de Imagens de Produto</p>', unsafe_allow_html=True)

        uploaded_files = st.file_uploader(
            "Arraste as fotos do produto (pode selecionar várias)",
            type=["jpg", "png", "jpeg"],
            accept_multiple_files=True,
            key="studio_uploader"
        )

        if uploaded_files:
            for idx, uploaded_file in enumerate(uploaded_files):
                st.markdown(f"#### 🖼️ Imagem {idx+1}: `{uploaded_file.name}`")
                col1, col2 = st.columns(2)
                img_bytes = uploaded_file.getvalue()
                img_original = Image.open(io.BytesIO(img_bytes))

                with col1:
                    st.markdown('<p class="section-label">Original</p>', unsafe_allow_html=True)
                    st.image(img_original, width='stretch')
                    st.caption(f"Resolução: {img_original.width}×{img_original.height}px")

                with col2:
                    st.markdown('<p class="section-label">✨ Resultado</p>', unsafe_allow_html=True)

                    op_upscale = st.checkbox("🔍 Aumentar qualidade (2×)", key=f"upscale_{idx}")
                    op_rembg = st.checkbox("✂️ Remover fundo", key=f"rembg_{idx}", value=True)
                    op_cenario = st.checkbox("🎨 Gerar cenário IA", key=f"cenario_{idx}")

                    if op_cenario and not op_rembg:
                        st.warning("⚠️ Gerar cenário requer remoção de fundo ativada.")
                        op_cenario = False

                    if st.button(f"▶️ Processar imagem", key=f"proc_{idx}"):
                        with st.spinner("Processando..."):
                            try:
                                img_work = img_original.copy()

                                if op_upscale:
                                    st.write("🔍 Aumentando qualidade...")
                                    img_work = upscale_image(img_work, scale=2)
                                    img_work = improve_image_quality(img_work)
                                    st.caption(f"📐 {img_work.width}×{img_work.height}px — qualidade melhorada")

                                if op_rembg:
                                    with st.status("✂️ Removendo fundo...", expanded=True) as status:
                                        try:
                                            st.write("Conectando ao motor de IA local...")
                                            # Garante que as vars de CPU estejam definidas antes do import
                                            os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
                                            os.environ["ORT_LOGGING_LEVEL"] = "3"
                                            # Usar remove() direto — evita o hang do new_session ao probing CUDA
                                            from rembg import remove as rembg_remove
                                            buf = io.BytesIO()
                                            img_work.save(buf, format="PNG")
                                            st.write("Processando pixels e aplicando máscaras...")
                                            no_bg_bytes = rembg_remove(buf.getvalue())
                                            img_work = Image.open(io.BytesIO(no_bg_bytes)).convert("RGBA")
                                            status.update(label="✅ Fundo removido!", state="complete")
                                        except Exception as e:
                                            import traceback
                                            err_detail = traceback.format_exc()
                                            st.error(f"Falha no Motor de IA: {type(e).__name__} - {str(e)}")
                                            with st.expander("Ver detalhes técnicos do erro"):
                                                st.code(err_detail)
                                            st.info("Dica: verifique se o onnxruntime.dll não foi bloqueado pelo antivírus.")
                                            st.stop()


                                final_img = img_work

                                if op_cenario:
                                    st.write("🎨 Gerando cenário (até 90s)...")
                                    prompt_cenario = "product photography studio white background soft lighting"
                                    if segmento == "Escolar / Juvenil":
                                        prompt_cenario = "minimalist white geometric podium soft lavender background"
                                    elif segmento == "Viagem":
                                        prompt_cenario = "stone platform outdoors golden hour soft focus"
                                    elif segmento == "Profissional / Tech":
                                        prompt_cenario = "sleek white desk surface modern office lighting"
                                    elif segmento == "Moda":
                                        prompt_cenario = "white marble floor fashion studio aesthetic"

                                    bg_img = generate_ai_scenario(prompt_cenario, segmento)
                                    if not bg_img:
                                        bg_img = generate_gradient_background(segmento)
                                    else:
                                        st.success("✅ Cenário IA gerado!")

                                    bg_img = bg_img.resize((1024, 1024))
                                    fg = img_work.copy()
                                    fg.thumbnail((800, 800))
                                    offset = (
                                        (bg_img.width - fg.width) // 2,
                                        int((bg_img.height - fg.height) * 0.6)
                                    )
                                    bg_img = apply_contact_shadow(bg_img, fg, offset)
                                    bg_img.paste(fg, offset, fg)
                                    final_img = bg_img

                                st.session_state[f"img_proc_result_{idx}"] = final_img
                            except Exception as e:
                                st.error(f"❌ Erro no processamento: {str(e)}")

                            # Análise SEO com Gemini (só na primeira imagem)
                            if idx == 0:
                                prompt_seo = f"Analise esta imagem de produto ({segmento}) e gere Título (60-70 chars), 20 Tags LSI e Descrição CR para Shopee 2026."
                                response = None
                                
                                # Otimização: redimensionar a imagem para não estourar o limite de payload REST do Gemini
                                img_vision = img_original.copy()
                                img_vision.thumbnail((1024, 1024))
                                
                                ultimo_erro_seo = ""
                                for m in MODELOS_VISION:
                                    try:
                                        response = client().models.generate_content(model=m, contents=[prompt_seo, img_vision])
                                        break
                                    except Exception as e:
                                        ultimo_erro_seo = f"{type(e).__name__}: {str(e)}"
                                        import traceback
                                        print(f"Erro SEO Gemini: {traceback.format_exc()}", flush=True)
                                        continue
                                if response:
                                    st.session_state[f"seo_result_{idx}"] = response.text
                                else:
                                    st.error(f"❌ Falha técnica ao classificar imagem. Erro IA: {ultimo_erro_seo}")

                    if f"img_proc_result_{idx}" in st.session_state:
                        final_img = st.session_state[f"img_proc_result_{idx}"]
                        st.image(final_img, width='stretch')

                        buf_out = io.BytesIO()
                        final_img.convert("RGB").save(buf_out, format="JPEG", quality=95)
                        salvar_ou_baixar(
                            "Baixar imagem processada",
                            data=buf_out.getvalue(),
                            file_name=f"processada_{idx+1}_{uploaded_file.name}",
                            mime="image/jpeg",
                            key=f"dl_{idx}"
                        )

                    if f"seo_result_{idx}" in st.session_state:
                        st.markdown("---")
                        st.markdown("### 📈 Diagnóstico de Listing")
                        st.write(st.session_state[f"seo_result_{idx}"])

                st.markdown("---")

        # ── Sub-seção: catálogo de produtos da loja ────────────
        if st.session_state.shop_data:
            st.markdown("---")
            st.markdown('<p class="section-label">Catálogo da Loja — Selecione para Otimizar</p>',
                        unsafe_allow_html=True)
            produtos = st.session_state.shop_produtos or []

            if produtos:
                cols = st.columns(4)
                for i, prod in enumerate(produtos):
                    with cols[i % 4]:
                        img_url = prod["image"] if prod["image"].startswith("http") else f"https://down-br.img.susercontent.com/file/{prod['image']}"
                        st.image(img_url, caption=f"{prod['name'][:28]}\nR$ {prod['price']:.2f}", width='stretch')
                        if st.button("⚡ Otimizar", key=f"opt_{prod['itemid']}"):
                            st.session_state.selected_product = prod
                            st.session_state.selected_kw = prod["name"][:40]
                            st.session_state.auto_search_competitors = True
                            st.session_state.auto_fetch_opt_reviews = True
                            st.session_state.optimization_result = None
                            st.session_state.optimization_reviews = None
                            st.rerun()
            else:
                st.warning("Galeria não carregou. Verifique os logs de debug acima.")


# ══════════════════════════════════════════════════════════════════════════
# PARTIÇÃO II — CHATBOT CONCIERGE
# ══════════════════════════════════════════════════════════════════════════
@st.dialog("Vincular Produto", width="large")
def show_product_linking_dialog():
    st.write("Não consegui identificar com certeza qual produto é este. Selecione um abaixo para vincular à imagem:")
    shop_prods = st.session_state.get("shop_produtos", [])
    
    if not shop_prods:
        st.info("Nenhum produto cadastrado na loja.")
        if st.button("Enviar sem vincular", key="btn_send_sem_vincular_dlg", width="stretch"):
            _do_pending_chat_send()
            st.rerun()
        return

    # Usamos grid de colunas para exibir os produtos de forma visual
    cols = st.columns(4)
    for i, prod in enumerate(shop_prods[:20]):
        with cols[i % 4]:
            img_id = prod.get("image", "")
            if img_id:
                img_url = img_id if img_id.startswith("http") else f"https://down-br.img.susercontent.com/file/{img_id}"
                st.image(img_url, width="stretch")
            st.caption(prod["name"][:35] + "..." if len(prod["name"]) > 35 else prod["name"])
            if st.button("Selecionar", key=f"btn_vinc_prod_{i}"):
                st.session_state.selected_product = prod
                _do_pending_chat_send()
                st.rerun()
                
    st.markdown("---")
    if st.button("❌ Nenhum / Imagem Externa", key="btn_vinc_nenhum_dlg", width="stretch"):
        _do_pending_chat_send()
        st.rerun()

def _do_pending_chat_send():
    msg = st.session_state.get("pending_chat_msg")
    atts = st.session_state.get("pending_chat_atts", [])
    attyps = st.session_state.get("pending_chat_attyps", [])
    prevs = st.session_state.get("pending_chat_prevs", [])
    ctx = st.session_state.get("pending_chat_ctx", "")
    seg = st.session_state.get("pending_chat_seg", "")
    _send_message(msg, atts, attyps, prevs, ctx, seg)

def _handle_chat_input_with_vision(user_input, attachments, att_types, att_previews, full_context, segmento):
    """
    Tenta mapear imagens enviadas no chat para produtos da loja.
    Se conseguir identificar certinho via API Vision, anexa e envia.
    Caso contrário, chama o Modal do Streamlit para o usuário clicar.
    """
    has_image = any(t == "image" for t in att_types)
    
    # Se não tem imagem na mensagem atual, vai direto
    if not has_image:
        _send_message(user_input, attachments, att_types, att_previews, full_context, segmento)
        return

    # Se já tem um produto selecionado, por ora assume que é ele e vai direto pra não encher o saco
    # Se quisermos que TODA nova imagem pergunte, tirar essa linha:
    if st.session_state.get("selected_product"):
        _send_message(user_input, attachments, att_types, att_previews, full_context, segmento)
        return

    shop_prods = st.session_state.get("shop_produtos", [])
    if not shop_prods:
        _send_message(user_input, attachments, att_types, att_previews, full_context, segmento)
        return

    # Guarda o estado para caso precise de dialog
    st.session_state.pending_chat_msg = user_input
    st.session_state.pending_chat_atts = attachments
    st.session_state.pending_chat_attyps = att_types
    st.session_state.pending_chat_prevs = att_previews
    st.session_state.pending_chat_ctx = full_context
    st.session_state.pending_chat_seg = segmento

    with st.status("Identificando seu produto na loja...", expanded=True) as status:
        import time
        from PIL import Image
        import io
        from backend_core import get_client, MODELOS_VISION
        
        # Monta a lista formatada para a IA ler
        catalog_str = "CATÁLOGO DE PRODUTOS:\n"
        for i, p in enumerate(shop_prods[:20]):
            catalog_str += f"[{i}] {p['name']}\n"
            
        schema_prompt = f"""Analise a imagem enviada pelo usuário. Qual ID do catálogo abaixo MÁIS se assemelha e representa o produto da imagem?
Retorne APENAS UM NÚMERO (0, 1, 2...), e NADA MAIS. Se a imagem não for definitivamente de NENHUM deles ou se for genérica, retorne -1.

{catalog_str}"""

        class_id = -1
        try:
            # Pega o primeiro anexo de imagem
            idx_img = att_types.index("image")
            att_img = attachments[idx_img]
            if isinstance(att_img, bytes):
                img_to_check = Image.open(io.BytesIO(att_img)).convert("RGB")
            else:
                img_to_check = att_img.convert("RGB")

            for m in MODELOS_VISION:
                try:
                    resp = get_client().models.generate_content(
                        model=m,
                        contents=[schema_prompt, img_to_check]
                    )
                    text_id = resp.text.strip().replace("`", "").replace("[", "").replace("]", "").strip()
                    if text_id.lstrip("-").isdigit():
                        class_id = int(text_id)
                        break
                except Exception:
                    time.sleep(1)
        except Exception:
            class_id = -1

        if 0 <= class_id < len(shop_prods):
            status.update(label=f"Produto identificado: {shop_prods[class_id]['name'][:20]}...", state="complete", expanded=False)
            st.session_state.selected_product = shop_prods[class_id]
            time.sleep(0.5)
            _send_message(user_input, attachments, att_types, att_previews, full_context, segmento)
            st.rerun()
        else:
            status.update(label="Precisamos da sua ajuda para vincular o produto.", state="error", expanded=False)
            time.sleep(0.5)
            # Aciona o dialog do streamlit (que por si só obriga a interface do usuário fluir para o modal)
            show_product_linking_dialog()


@st.dialog("Vincular loja ao Chatbot", width="large")
def _show_store_url_dialog():
    """Popup para digitar URL da loja antes de ativar o chatbot."""
    st.markdown(
        "Para que o chatbot conheça seus produtos, concorrentes e avaliações, "
        "carregue sua loja da Shopee. Você pode pular esta etapa — o chatbot "
        "funcionará como atendente geral."
    )
    st.markdown("---")

    url_input = st.text_input(
        "URL da sua loja",
        placeholder="https://shopee.com.br/nome_da_loja",
        key="dialog_store_url_input",
    )

    col_carregar, col_pular = st.columns(2)
    with col_carregar:
        if st.button("🔍 Carregar loja e ativar", type="primary",
                     width="stretch", key="btn_dialog_carregar"):
            if url_input.strip():
                from backend_core import resolve_shopee_url, fetch_shop_info, fetch_shop_products_intercept
                resolved = resolve_shopee_url(url_input.strip())
                if not resolved or resolved["type"] != "shop":
                    st.error("URL inválida. Use: shopee.com.br/nome_da_loja")
                else:
                    username = resolved["username"]
                    with st.spinner("Carregando loja... (30-60s)"):
                        shop_raw = fetch_shop_info(username)
                    d = shop_raw.get("data", shop_raw)
                    if d:
                        st.session_state.shop_data = d
                        shopid = d.get("shopid") or d.get("shop_id")
                        with st.spinner("Carregando catálogo..."):
                            st.session_state.shop_produtos = (
                                fetch_shop_products_intercept(username, shopid)
                            )
                        st.success(f"✅ Loja **{d.get('name', username)}** carregada!")
                        _activate_chatbot()
                    else:
                        st.error("Não foi possível carregar a loja. Verifique a URL.")
            else:
                st.warning("Digite a URL da sua loja.")

    with col_pular:
        if st.button("💬 Usar sem loja", width="stretch", key="btn_dialog_pular"):
            _activate_chatbot()


def _activate_chatbot():
    """Inicializa o estado do chatbot e faz rerun."""
    st.session_state.chatbot_active           = True
    st.session_state.chat_history             = []
    st.session_state.chat_attachments         = []
    st.session_state.chat_attachment_types    = []
    st.session_state.chat_attachment_previews = []
    st.session_state.chat_preview_images      = []
    st.session_state.chat_preview_captions    = []
    st.rerun()

# ── Helper: copiar/baixar mensagens do assistente ───────────────────
def _render_copy_button(text: str, turn_idx: int):
    """
    Exibe um expander colapsado com st.code(language=None) — o Streamlit já
    injeta nativamente um botão de copiar (ícone no canto superior direito)
    em todo bloco de código, sem depender de JS ou iframe.

    Botão de download .txt fica visível diretamente para respostas longas.
    """
    # st.code tem botão nativo de copiar — sem JS, sem iframe, 100% confiável
    with st.expander("📋 Copiar resposta", expanded=False):
        st.code(text, language=None, wrap_lines=True)

    # Botão de download para respostas longas (> 300 chars)
    if len(text) > 300:
        salvar_ou_baixar(
            "⬇️ Baixar .txt",
            data=text,
            file_name=f"resposta_chatbot_{turn_idx+1}.txt",
            mime="text/plain",
            key=f"dl_turn_{turn_idx}",

        )


def _push_undo():
    """Salva snapshot das camadas para desfazer (limite 10)."""
    import copy
    if "canvas_undo_stack" not in st.session_state:
        st.session_state.canvas_undo_stack = []
    
    # Snapshot profundo das camadas atuais
    snapshot = copy.deepcopy(st.session_state.chat_canvas_layers)
    st.session_state.canvas_undo_stack.append(snapshot)
    
    # Mantém apenas as últimas 10 ações
    if len(st.session_state.canvas_undo_stack) > 10:
        st.session_state.canvas_undo_stack.pop(0)

def _push_redo():
    """Recupera estados desfeitos na pilha."""
    import copy
    if "canvas_redo_stack" in st.session_state and st.session_state.canvas_redo_stack:
        st.session_state.canvas_undo_stack.append(copy.deepcopy(st.session_state.chat_canvas_layers))
        st.session_state.chat_canvas_layers = st.session_state.canvas_redo_stack.pop()

@st.dialog("Nova Versão da Imagem", width="large")
def _render_layer_decision_dialog():
    """Diálogo para decidir se substitui a base ou adiciona como camada."""
    pending = st.session_state.get("canvas_pending_layer")
    if not pending:
        st.rerun()
        return

    st.markdown(
        "### ✨ IA gerou uma nova versão!\n"
        "Como você deseja aplicar esta alteração no editor?"
    )
    
    col_pre, col_opt = st.columns([1, 1])
    with col_pre:
        st.image(pending["img"], caption=f"Preview: {pending['name']}", use_container_width=True)
    
    with col_opt:
        st.info(
            "💡 **Substituir Base:** Descarta as edições atuais e define esta como a imagem principal.\n\n"
            "💡 **Nova Camada:** Mantém o que você já fez e adiciona esta por cima (ótimo para badges e stickers)."
        )
        
        if st.button("🖼️ Substituir Base", type="primary", use_container_width=True):
            _push_undo()
            st.session_state.chat_canvas_layers = [{
                "name": pending["name"],
                "img": pending["img"],
                "visible": True,
                "type": "base",
                "offset_x": 0.0,
                "offset_y": 0.0,
                "width_pct": 100.0,
                "height_pct": 100.0
            }]
            st.session_state.canvas_pending_layer = None
            st.success("✅ Base atualizada!")
            st.rerun()
            
        if st.button("➕ Adicionar como Camada", use_container_width=True):
            _push_undo()
            st.session_state.chat_canvas_layers.append({
                "name": pending["name"],
                "img": pending["img"],
                "visible": True,
                "type": "edit",
                "offset_x": 25.0,
                "offset_y": 25.0,
                "width_pct": 30.0,
                "height_pct": 30.0
            })
            st.session_state.canvas_pending_layer = None
            st.success("✅ Adicionado ao topo!")
            st.rerun()
            
        if st.button("❌ Descartar", use_container_width=True):
            st.session_state.canvas_pending_layer = None
            st.rerun()

def _render_canvas_area(full_context: str, segmento: str):
    """Renderiza a área do Canvas Interativo (ROI Visual e Transformação de Camadas)."""
    from backend_core import composite_layers, apply_region_edit_with_vision, salvar_ou_baixar
    import io as _io
    import time as _time
    import hashlib
    from PIL import Image
    from streamlit_drawable_canvas import st_canvas
    
    # CSS suplementar para garantir centralização dos ícones de camada
    st.markdown("""
        <style>
        /* Remove CSS genérico conflitante - usar apenas .layer-icon-btn do ui_theme.py */
        </style>
    """, unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown('<p class="section-label">🎨 Direção Criativa</p>', unsafe_allow_html=True)
        
        # ── Diálogo de Decisão (se houver pendência) ──────────
        if st.session_state.get("canvas_pending_layer"):
            if not st.session_state.get("chat_canvas_layers"):
                p = st.session_state.canvas_pending_layer
                st.session_state.chat_canvas_layers = [{
                    "name": p["name"], "img": p["img"], "visible": True, "type": "base"
                }]
                st.session_state.canvas_pending_layer = None
            else:
                st.warning("✨ Nova imagem recebida via chat!")
                if st.button("🤔 Abrir Opções de Aplicação", type="primary", use_container_width=True):
                    _render_layer_decision_dialog()

        layers = st.session_state.get("chat_canvas_layers", [])
        if not layers:
            active_img = st.session_state.get("chat_active_edit_image")
            if active_img:
                layers = [{"name": "Original", "img": active_img, "visible": True, "type": "base"}]
                st.session_state.chat_canvas_layers = layers
            else:
                st.markdown(
                    "<div style='text-align:center;padding:4rem 0;opacity:0.35;font-size:14px'>"
                    "🖌️ Anexe ou processe uma imagem<br>para abrir o Canvas</div>",
                    unsafe_allow_html=True
                )
                return

        composite = composite_layers(layers)
        if not composite: return

        # ── Lógica de Movimentação de Camada ─────────────────
        moving_idx = st.session_state.get("canvas_moving_layer")
        
        # ── Barra de Ferramentas ROI ────────────────────────
        col_t1, col_t2, col_t3, col_t4 = st.columns([1,1,1,1])
        def toggle_tool(tool_name):
            if st.session_state.canvas_tool == tool_name and st.session_state.canvas_mode == "draw":
                st.session_state.canvas_mode = "transform"
            else:
                st.session_state.canvas_tool = tool_name
                st.session_state.canvas_mode = "draw"

        with col_t1:
            if st.button("⬜ Retângulo", use_container_width=True, type="primary" if st.session_state.canvas_tool == "rect" and st.session_state.canvas_mode == "draw" else "secondary"):
                toggle_tool("rect"); st.rerun()
        with col_t2:
            if st.button("⭕ Círculo", use_container_width=True, type="primary" if st.session_state.canvas_tool == "circle" and st.session_state.canvas_mode == "draw" else "secondary"):
                toggle_tool("circle"); st.rerun()
        with col_t3:
            if st.button("✏️ Livre", use_container_width=True, type="primary" if st.session_state.canvas_tool == "freeline" and st.session_state.canvas_mode == "draw" else "secondary"):
                toggle_tool("freeline"); st.rerun()
        with col_t4:
            if st.button("🔄 Reset", use_container_width=True):
                st.session_state.chat_canvas_roi = {"x": 25, "y": 25, "w": 50, "h": 50, "shape": "rect"}
                st.session_state.chat_canvas_freehand_mask = None
                st.session_state.canvas_mode = "transform"
                st.rerun()

        # ── Visualização (Normal ou Comparação) ──────────────
        if st.session_state.get("canvas_compare_mode") and layers:
            col_orig, col_edit = st.columns(2)
            with col_orig:
                st.markdown('<p style="text-align:center;font-size:12px;color:gray">📷 ORIGINAL (Base)</p>', unsafe_allow_html=True)
                base_only = [l for l in layers if l["type"] == "base"]
                if base_only: st.image(composite_layers(base_only), use_container_width=True)
            with col_edit:
                st.markdown('<p style="text-align:center;font-size:12px;color:#FF4B4B">✨ COM EDIÇÕES</p>', unsafe_allow_html=True)
                st.image(composite, use_container_width=True)
        else:
            # ── Renderização do Canvas ───────────────────────────
            w, h = composite.size
            display_width = 500 
            display_height = int(h * (display_width / w))
            
            initial_drawing = None
            drawing_mode = "transform"
            
            if moving_idx is not None and moving_idx < len(layers):
                # MODO MOVER CAMADA
                l_move = layers[moving_idx]
                others = [l for i, l in enumerate(layers) if i != moving_idx]
                
                # Preview: colamos a camada real sobre o fundo das outras para não "sumir"
                base_preview = composite_layers(others).convert("RGBA")
                m_img = l_move["img"].convert("RGBA")
                
                # Redimensiona para posição atual para o background_image do canvas
                tw = int((l_move.get("width_pct", 30.0) / 100.0) * w)
                th = int((l_move.get("height_pct", 30.0) / 100.0) * h)
                if tw > 0 and th > 0:
                    m_img = m_img.resize((tw, th), Image.LANCZOS)
                
                px = int((l_move.get("offset_x", 25.0) / 100.0) * w)
                py = int((l_move.get("offset_y", 25.0) / 100.0) * h)
                
                canvas_bg = base_preview.copy()
                canvas_bg.paste(m_img, (px, py), m_img)
                
                # Rectangle handle
                rx = (l_move.get("offset_x", 25.0) / 100.0) * display_width
                ry = (l_move.get("offset_y", 25.0) / 100.0) * display_height
                rw = (l_move.get("width_pct", 30.0) / 100.0) * display_width
                rh = (l_move.get("height_pct", 30.0) / 100.0) * display_height
                
                initial_drawing = {
                    "objects": [{
                        "type": "rect", "left": rx, "top": ry, "width": rw, "height": rh,
                        "fill": "rgba(255, 75, 75, 0.2)", "stroke": "#FF4B4B", "strokeWidth": 2
                    }]
                }
                drawing_mode = "transform"
                st.info(f"🎯 Movendo: **{l_move['name']}** (Confirme abaixo ao finalizar)")
            else:
                # MODO NORMAL (ROI)
                canvas_bg = composite.convert("RGBA")
                if st.session_state.canvas_mode == "draw":
                    if st.session_state.canvas_tool == "rect": drawing_mode = "rect"
                    elif st.session_state.canvas_tool == "circle": drawing_mode = "circle"
                    elif st.session_state.canvas_tool == "freeline": drawing_mode = "freedraw"

            img_hash = hashlib.md5(canvas_bg.tobytes()).hexdigest()[:8]
            canvas_result = st_canvas(
                fill_color="rgba(255, 75, 75, 0.3)",
                stroke_width=3, stroke_color="#FF4B4B",
                background_image=canvas_bg,
                initial_drawing=initial_drawing,
                update_streamlit=True,
                height=display_height, width=display_width,
                drawing_mode=drawing_mode,
                key=f"canvas_roi_{img_hash}_{moving_idx}",
            )

            # Processamento de dados do canvas
            if canvas_result.json_data is not None:
                objects = canvas_result.json_data["objects"]
                if objects:
                    obj = objects[-1]
                    if moving_idx is not None:
                        # Guarda em estado temporário para não dar "glitch" em tempo real
                        new_x = (obj["left"] / display_width) * 100
                        new_y = (obj["top"] / display_height) * 100
                        new_w = (obj["width"] * obj["scaleX"] / display_width) * 100
                        new_h = (obj["height"] * obj["scaleY"] / display_height) * 100
                        st.session_state.canvas_move_temp = {
                            "idx": moving_idx, "x": float(new_x), "y": float(new_y),
                            "w": float(new_w), "h": float(new_h)
                        }
                    else:
                        if obj["type"] in ["rect", "circle"]:
                            st.session_state.chat_canvas_roi = {
                                "x": (obj["left"] / display_width) * 100, "y": (obj["top"] / display_height) * 100,
                                "w": (obj["width"] * obj["scaleX"] / display_width) * 100, "h": (obj["height" ] * obj["scaleY"] / display_height) * 100,
                                "shape": "rect" if obj["type"] == "rect" else "circle"
                            }

        # ── Botões de Ação do Canvas ───────────────────────
        if moving_idx is not None:
            c_move1, c_move2 = st.columns(2)
            if c_move1.button("✅ Confirmar Posição", use_container_width=True, type="primary"):
                temp = st.session_state.get("canvas_move_temp")
                if temp and temp["idx"] == moving_idx:
                    _push_undo()
                    st.session_state.chat_canvas_layers[moving_idx]["offset_x"] = temp["x"]
                    st.session_state.chat_canvas_layers[moving_idx]["offset_y"] = temp["y"]
                    st.session_state.chat_canvas_layers[moving_idx]["width_pct"] = temp["w"]
                    st.session_state.chat_canvas_layers[moving_idx]["height_pct"] = temp["h"]
                st.session_state.canvas_moving_layer = None
                st.session_state.canvas_move_temp = None
                st.session_state.canvas_move_snapshot = None
                st.rerun()
            if c_move2.button("✕ Cancelar", use_container_width=True):
                # Restaurar snapshot da camada
                snapshot = st.session_state.get("canvas_move_snapshot")
                if snapshot and moving_idx is not None and moving_idx < len(st.session_state.chat_canvas_layers):
                    st.session_state.chat_canvas_layers[moving_idx] = snapshot
                st.session_state.canvas_moving_layer = None
                st.session_state.canvas_move_temp = None
                st.session_state.canvas_move_snapshot = None
                st.rerun()
        else:
            c1, c2, c3 = st.columns([1, 1, 1])
            if c1.button("📥 Usar no Chat", use_container_width=True):
                buf = _io.BytesIO()
                composite.convert("RGB").save(buf, format="JPEG", quality=92)
                st.session_state.chat_active_edit_image = composite
                st.session_state.chat_attachments = [buf.getvalue()]
                st.session_state.chat_attachment_types = ["image"]
                st.session_state.chat_attachment_previews = [composite.convert("RGB")]
                st.session_state.show_attach_panel = True
                st.success("✅ Composição enviada!"); st.rerun()
            if c2.button("📌 Fixar como Base", use_container_width=True):
                _push_undo()
                st.session_state.chat_canvas_layers = [{
                    "name": "Base Mesclada",
                    "img": composite,
                    "visible": True,
                    "type": "base",
                    "offset_x": 0.0,
                    "offset_y": 0.0,
                    "width_pct": 100.0,
                    "height_pct": 100.0
                }]
                st.session_state.chat_active_edit_image = composite; st.rerun()
            with c3:
                comp_label = "🖼️ Sair Comparar" if st.session_state.canvas_compare_mode else "🌓 Comparar Original"
                if st.button(comp_label, use_container_width=True):
                    st.session_state.canvas_compare_mode = not st.session_state.canvas_compare_mode; st.rerun()

        # ── Gerenciador de Camadas ─────────────────────────
        st.markdown("---")
        with st.expander("📂 Camadas & Histórico", expanded=False):
            col_undo, col_redo = st.columns(2)
            undo_s = st.session_state.get("canvas_undo_stack", [])
            redo_s = st.session_state.get("canvas_redo_stack", [])
            if col_undo.button(f"↶ Desfazer ({len(undo_s)})", use_container_width=True, disabled=not undo_s):
                import copy
                st.session_state.canvas_redo_stack.append(copy.deepcopy(st.session_state.chat_canvas_layers))
                st.session_state.chat_canvas_layers = st.session_state.canvas_undo_stack.pop(); st.rerun()
            if col_redo.button(f"↷ Refazer ({len(redo_s)})", use_container_width=True, disabled=not redo_s):
                _push_redo(); st.rerun()
            
            st.markdown("---")
            for i, layer in enumerate(reversed(layers)):
                idx = len(layers) - 1 - i
                col_vis, col_name, col_move, col_up, col_down, col_del = st.columns([1, 3, 1, 1, 1, 1])
                with col_vis:
                    vis = st.checkbox(
                        f"Mostrar camada {idx + 1}",
                        value=layer["visible"],
                        key=f"vis_{idx}_{len(layers)}",
                        label_visibility="collapsed",
                    )
                    if vis != layer["visible"]: st.session_state.chat_canvas_layers[idx]["visible"] = vis; st.rerun()
                with col_name:
                    color = "#FF4B4B" if moving_idx == idx else "white"
                    st.markdown(f"<span style='font-size:11px;color:{color}'>{layer['name'][:20]}</span>", unsafe_allow_html=True)
                # Botões de Camada com Centralização Forçada via CSS class
                with col_move:
                    if layer["type"] != "base":
                        st.markdown('<div class="layer-icon-btn">', unsafe_allow_html=True)
                        m_icon = "✓" if moving_idx == idx else "↔"
                        if st.button(m_icon, key=f"move_btn_{idx}", use_container_width=True):
                            if moving_idx == idx:
                                # Já está selecionado → desselecionar
                                st.session_state.canvas_moving_layer = None
                                st.session_state.canvas_move_temp = None
                            else:
                                # Salvar snapshot da camada antes de entrar em modo mover
                                import copy
                                st.session_state.canvas_move_snapshot = copy.deepcopy(st.session_state.chat_canvas_layers[idx])
                                st.session_state.canvas_moving_layer = idx
                                st.session_state.canvas_move_temp = None
                            st.rerun()
                        st.markdown('</div>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div class="layer-icon-btn" style="opacity:0.3">—</div>', unsafe_allow_html=True)
                with col_up:
                    st.markdown('<div class="layer-icon-btn">', unsafe_allow_html=True)
                    if idx < len(layers) - 1:
                        if st.button("↑", key=f"up_{idx}", use_container_width=True):
                            _push_undo(); l = st.session_state.chat_canvas_layers.pop(idx)
                            st.session_state.chat_canvas_layers.insert(idx + 1, l); st.rerun()
                    else:
                        st.markdown('<span style="opacity:0.3">—</span>', unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                with col_down:
                    st.markdown('<div class="layer-icon-btn">', unsafe_allow_html=True)
                    if idx > 0:
                        if st.button("↓", key=f"down_{idx}", use_container_width=True):
                            _push_undo(); l = st.session_state.chat_canvas_layers.pop(idx)
                            st.session_state.chat_canvas_layers.insert(idx - 1, l); st.rerun()
                    else:
                        st.markdown('<span style="opacity:0.3">—</span>', unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                with col_del:
                    st.markdown('<div class="layer-icon-btn">', unsafe_allow_html=True)
                    if layer["type"] != "base":
                        if st.button("🗑️", key=f"del_lay_{idx}", use_container_width=True):
                            _push_undo(); st.session_state.chat_canvas_layers.pop(idx); st.rerun()
                    else:
                        st.markdown('<span style="opacity:0.3">—</span>', unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)

        # ── Aplicação ROI ──────────────────────────────────
        st.markdown("---")
        instrucao = st.text_input("Comando para área selecionada:", placeholder="Ex: mude a cor para azul...")
        if st.button("✨ Aplicar na Região", type="primary", use_container_width=True):
            if instrucao and composite:
                with st.spinner("IA processando região..."):
                    mask = st.session_state.chat_canvas_freehand_mask
                    roi = st.session_state.chat_canvas_roi
                    new_layer_img, desc = apply_region_edit_with_vision(
                        composite, roi, instrucao, full_context, segmento, freehand_mask=mask
                    )
                    _push_undo()
                    st.session_state.chat_canvas_layers.append({
                        "name": f"Edição: {instrucao[:15]}",
                        "img": new_layer_img,
                        "visible": True,
                        "type": "edit",
                        "offset_x": float(roi["x"]),
                        "offset_y": float(roi["y"]),
                        "width_pct": float(roi["w"]),
                        "height_pct": float(roi["h"])
                    })
                    st.success(f"✅ {desc}"); _time.sleep(1); st.rerun()
        
        st.markdown("---")
        if composite:
            buf = _io.BytesIO()
            composite.convert("RGB").save(buf, format="JPEG", quality=95)
            salvar_ou_baixar("💾 Exportar Imagem Final", data=buf.getvalue(), file_name="composicao_final.jpg", mime="image/jpeg", key="btn_export_canvas")


def render_chatbot():
    from backend_core import (
        salvar_ou_baixar, resolve_shopee_url, fetch_shop_info, fetch_shop_products_intercept, fetch_competitors_intercept, fetch_reviews_intercept, generate_full_optimization, build_catalog_context, chat_with_gemini, analyze_reviews_with_gemini, generate_ai_scenario, generate_gradient_background, apply_contact_shadow, improve_image_quality, upscale_image, MODELOS_VISION, client, build_full_chat_context, detect_chat_intent, analyze_product_image_vision, process_chat_turn, suggest_faq_from_history, MODELOS_TEXTO, get_client
    )
    from PIL import Image
    st.markdown("""
    <div class="page-header">
        <div class="page-header-icon">🤖</div>
        <div>
            <div class="page-header-title">Chatbot Concierge</div>
            <div class="page-header-sub">Assistente multimodal — texto, imagens e vídeos</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Banner de contexto ativo da Auditoria ─────────────────
    has_shop   = bool(st.session_state.shop_data)
    has_prod   = bool(st.session_state.selected_product)
    has_comp   = (st.session_state.df_competitors is not None
                  and not st.session_state.df_competitors.empty)
    has_rev    = bool(st.session_state.optimization_reviews)

    if has_shop or has_prod or has_comp or has_rev:
        shop_name = (st.session_state.shop_data or {}).get("name", "Loja")
        badges = []
        if has_shop:    badges.append(f"🏪 {shop_name}")
        if has_comp:    badges.append(f"📡 {len(st.session_state.df_competitors)} concorrentes")
        if has_rev:     badges.append(f"💬 {len(st.session_state.optimization_reviews)} avaliações")
        if has_prod:    badges.append(f"⚡ {st.session_state.selected_product['name'][:30]}")
        st.markdown(
            f'<div class="loja-status-bar">🔗 Contexto da Auditoria: {" · ".join(badges)}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.info(
            "💡 Carregue sua loja na **Auditoria** para enriquecer o chatbot com dados de produtos, "
            "concorrentes e avaliações. Sem isso, ele ainda funciona como atendente geral.",
            icon=None,
        )

    # ── Monta o contexto completo ─────────────────────────────
    shop_name_ctx  = (st.session_state.shop_data or {}).get("name", "Loja")
    full_context   = build_full_chat_context(
        shop_data            = st.session_state.shop_data,
        produtos             = st.session_state.shop_produtos,
        selected_product     = st.session_state.selected_product,
        df_competitors       = st.session_state.df_competitors,
        optimization_reviews = st.session_state.optimization_reviews,
        shop_name            = shop_name_ctx,
    )

    # ── Tela de boas-vindas (chatbot não ativo) ───────────────
    if not st.session_state.chatbot_active:
        with st.container(border=True):
            st.markdown(f"### 🤖 Chatbot — {shop_name_ctx}")
            n_prod = len(st.session_state.shop_produtos or [])
            c1, c2, c3 = st.columns(3)
            with c1:
                if n_prod:
                    st.success(f"✅ {n_prod} produtos no catálogo")
                else:
                    st.warning("⚠️ Sem catálogo carregado")
            with c2:
                st.info("📎 Imagens e vídeos via botão +")
            with c3:
                st.info("💬 Texto · Análise · Processamento")

            st.markdown(
                "O chatbot responde perguntas de clientes, analisa imagens de produtos, "
                "remove fundos, gera cenários e otimiza listings — tudo pelo chat."
            )
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("🚀 Ativar Chatbot", type="primary", width='stretch', key="btn_ativar_chat"):
                    if not st.session_state.shop_data:
                        # Sem loja vinculada → abre popup para digitar URL
                        _show_store_url_dialog()
                    else:
                        _activate_chatbot()
            with col_b:
                if st.button("📋 Gerar FAQ para Seller Centre", width='stretch', key="btn_gerar_faq_welcome"):
                    _gerar_faq(full_context, shop_name_ctx)

        _render_faq_output(shop_name_ctx)
        return

    # ══════════════════════════════════════════════════════════
    # CHAT ATIVO — Layout: painel esquerdo (chat) + direito (canvas)
    # ══════════════════════════════════════════════════════════
    col_chat, col_canvas = st.columns([1, 1])

    # ── PAINEL DIREITO: Canvas de Direção Criativa ────────────
    with col_canvas:
        _render_canvas_area(full_context, segmento)

    # ── PAINEL ESQUERDO: Chat ─────────────────────────────────
    with col_chat:
        # Cabeçalho do chat
        ch1, ch2, ch3 = st.columns([4, 1, 1])
        with ch1:
            st.markdown(f"### 💬 {shop_name_ctx}")
        with ch2:
            if st.button("📋 FAQ", key="btn_faq_chat", width='stretch', help="Gerar FAQ para Seller Centre"):
                _gerar_faq(full_context, shop_name_ctx)
                st.rerun()
        with ch3:
            if st.button("🔄", key="btn_reset_chat", width='stretch', help="Reiniciar conversa"):
                st.session_state.chat_history             = []
                st.session_state.chat_attachments         = []
                st.session_state.chat_attachment_types    = []
                st.session_state.chat_attachment_previews = []
                st.session_state.chatbot_active           = False
                st.rerun()

        # Histórico de mensagens
        chat_container = st.container(height=420)
        with chat_container:
            if not st.session_state.chat_history:
                st.markdown(
                    "<div style='text-align:center;padding:3rem 0;opacity:0.35;font-size:13px'>"
                    "💬<br>Comece uma conversa abaixo</div>",
                    unsafe_allow_html=True,
                )
            else:
                for i, turn in enumerate(st.session_state.chat_history):
                    with st.chat_message("user"):
                        # Mostra prévia de anexos se houver
                        if turn.get("attachment_previews"):
                            att_cols = st.columns(min(len(turn["attachment_previews"]), 4))
                            for ai, aprev in enumerate(turn["attachment_previews"]):
                                with att_cols[ai]:
                                    st.image(aprev, width=350)
                        st.write(turn["user"])
                    with st.chat_message("assistant"):
                        st.write(turn["assistant"])
                        if turn.get("market_context_used"):
                            source_label = "Radar" if turn.get("market_context_source") == "radar" else turn.get("market_context_source", "Radar")
                            confidence_label = turn.get("radar_confidence")
                            suffix = f" | Confianca: {str(confidence_label).upper()}" if confidence_label else ""
                            st.caption(f"Base usada: {source_label}{suffix}")
                        for warning in (turn.get("warnings") or [])[:2]:
                            st.caption(f"Aviso: {warning}")
                        # Imagens inline na bolha de resposta
                        if turn.get("result_images"):
                            n_imgs = len(turn["result_images"])
                            num_cols = min(n_imgs, 2)
                            ri_cols = st.columns(num_cols)
                            for ri, rimg in enumerate(turn["result_images"]):
                                with ri_cols[ri % num_cols]:
                                    rcap = ""
                                    if turn.get("result_captions") and ri < len(turn["result_captions"]):
                                        rcap = turn["result_captions"][ri]
                                    st.image(rimg, caption=rcap, width=350)
                        # Botões de copiar / baixar para toda resposta do assistente
                        _render_copy_button(turn["assistant"], i)

        # ── Sugestões iniciais ────────────────────────────────
        if not st.session_state.chat_history:
            st.markdown(
                '<p class="section-label" style="margin-top:0.5rem">Sugestões</p>',
                unsafe_allow_html=True,
            )
            sugestoes_base = [
                "Quais produtos vocês têm disponíveis?",
                "Qual o produto mais barato?",
            ]
            sugestoes_media = [
                "📎 Analise a imagem que vou enviar",
                "📎 Remova o fundo desta foto",
            ]
            sugestoes_audit = []
            if has_prod:
                prod_name = st.session_state.selected_product["name"][:25]
                sugestoes_audit = [
                    f"Otimize o listing da {prod_name}",
                    f"Compare a {prod_name} com os concorrentes",
                ]

            all_sugs = (sugestoes_audit or sugestoes_base) + sugestoes_media
            sug_cols = st.columns(2)
            for idx_s, sug in enumerate(all_sugs[:4]):
                with sug_cols[idx_s % 2]:
                    if st.button(sug, key=f"sug_{idx_s}", width='stretch'):
                        _send_message(sug, [], [], [], full_context, segmento)

        # ── Ações pós-resposta (último turno) ─────────────────
        # Renderiza embaixo do histórico, antes do input
        if st.session_state.chat_history:
            last_turn = st.session_state.chat_history[-1]
            last_idx  = len(st.session_state.chat_history) - 1
            if last_turn.get("post_actions"):
                _render_post_response_actions(
                    last_turn, last_idx, full_context, segmento
                )

        # ── Área de anexo (toggle "+") ────────────────────────
        _render_attachment_area(full_context=full_context, segmento=segmento)

        # ── Campo de texto + enviar ───────────────────────────
        user_input = st.chat_input("Mensagem, pergunta ou comando de imagem...")
        if user_input:
            attachments  = st.session_state.get("chat_attachments",         [])
            att_types    = st.session_state.get("chat_attachment_types",    [])
            att_previews = st.session_state.get("chat_attachment_previews", [])
            _handle_chat_input_with_vision(user_input, attachments, att_types, att_previews, full_context, segmento)

    # ── Construtor de FAQ personalizado ──────────────────────
    with st.expander("📋 Construtor de FAQ Personalizado", expanded=False):
        st.markdown(
            "Adicione pares manualmente, gere respostas com IA ou deixe o chatbot "
            "sugerir automaticamente a partir do histórico da conversa."
        )

        faq_pers = st.session_state.get("faq_personalizado", [])

        # Lista atual
        if faq_pers:
            st.markdown("**Pares adicionados:**")
            for _i, _item in enumerate(faq_pers):
                _c1, _c2 = st.columns([10, 1])
                with _c1:
                    st.markdown(f"**P{_i+1}:** {_item['pergunta']}")
                    st.markdown(f"**R{_i+1}:** {_item['resposta']}")
                    st.divider()
                with _c2:
                    if st.button("🗑️", key=f"del_faq_{_i}"):
                        st.session_state.faq_personalizado.pop(_i)
                        st.rerun()
        else:
            st.caption("Nenhum par adicionado ainda.")

        # Campos para novo par
        st.markdown("**Adicionar pergunta:**")
        _cp, _cr = st.columns(2)
        with _cp:
            _nova_p = st.text_input(
                "Pergunta", placeholder="Ex: Têm mochila azul?",
                key="faq_nova_p", max_chars=80
            )
        with _cr:
            _nova_r = st.text_area(
                "Resposta", placeholder="Ex: Sim! Temos em azul.",
                key="faq_nova_r", max_chars=500, height=80
            )

        _b1, _b2, _b3 = st.columns(3)
        with _b1:
            if st.button("➕ Adicionar", key="btn_faq_add",
                         width="stretch") and _nova_p and _nova_r:
                st.session_state.faq_personalizado.append(
                    {"pergunta": _nova_p, "resposta": _nova_r}
                )
                st.rerun()
        with _b2:
            if st.button("🤖 Sugerir resposta", key="btn_faq_resp",
                         width="stretch") and _nova_p:
                with st.spinner("Gerando resposta..."):
                    _sugestao = chat_with_gemini(
                        f"Gere uma resposta curta e simpática (máx 500 chars) para: '{_nova_p}'",
                        [], full_context
                    )
                st.session_state.faq_personalizado.append(
                    {"pergunta": _nova_p, "resposta": _sugestao[:500]}
                )
                st.rerun()
        with _b3:
            _n_turns = len(st.session_state.chat_history)
            if st.button(
                f"✨ Sugerir do histórico ({_n_turns}t)",
                key="btn_faq_historico",
                width="stretch",
                disabled=not st.session_state.chat_history,
            ):
                with st.spinner("Analisando histórico..."):
                    _sugestoes = suggest_faq_from_history(
                        st.session_state.chat_history,
                        shop_name_ctx,
                        segmento,
                    )
                if _sugestoes:
                    _ja_tem = [x["pergunta"] for x in st.session_state.faq_personalizado]
                    _added = sum(
                        1 for s in _sugestoes
                        if s["pergunta"] not in _ja_tem
                        and not st.session_state.faq_personalizado.append(s)
                    )
                    if _added:
                        st.success(f"✅ {_added} par(es) sugerido(s) adicionado(s)!")
                        st.rerun()
                    else:
                        st.info("Todos os pares sugeridos já estavam no FAQ.")
                else:
                    st.warning(
                        "Não encontrei perguntas de clientes úteis no histórico. "
                        "Continue a conversa e tente novamente."
                    )

        # Exportar
        if faq_pers:
            _faq_txt = "\n\n".join(
                f"PERGUNTA {_i+1}: {_item['pergunta']}\nRESPOSTA {_i+1}: {_item['resposta']}"
                for _i, _item in enumerate(faq_pers)
            ).replace("**", "")
            salvar_ou_baixar(
                f"Exportar FAQ ({len(faq_pers)} pares)",
                data=_faq_txt,
                file_name=f"faq_personalizado_{shop_name_ctx}.txt",
                mime="text/plain",
                key="dl_faq_perso",
            )
            if st.button("🗑️ Limpar FAQ", key="btn_faq_limpar"):
                st.session_state.faq_personalizado = []
                st.rerun()

    # ── FAQ gerado automaticamente ─────────────────────────────
    _render_faq_output(shop_name_ctx)


# ══════════════════════════════════════════════════════════════
# FUNÇÕES AUXILIARES DO CHATBOT
# ══════════════════════════════════════════════════════════════

def _render_quick_actions(att_types: list, full_context: str, segmento: str):
    from backend_core import (
        salvar_ou_baixar, resolve_shopee_url, fetch_shop_info, fetch_shop_products_intercept, fetch_competitors_intercept, fetch_reviews_intercept, generate_full_optimization, build_catalog_context, chat_with_gemini, analyze_reviews_with_gemini, generate_ai_scenario, generate_gradient_background, apply_contact_shadow, improve_image_quality, upscale_image, MODELOS_VISION, client, build_full_chat_context, detect_chat_intent, analyze_product_image_vision, process_chat_turn, suggest_faq_from_history, MODELOS_TEXTO, get_client
    )
    from PIL import Image
    """
    Mostra chips de ação rápida contextuais quando há anexo pendente.
    Imagem → ações de edição. Vídeo → ações de análise consultiva.
    """
    has_image = any(t == "image" for t in att_types)
    has_video = any(t == "video" for t in att_types)

    if not has_image and not has_video:
        return

    st.markdown(
        '<p class="section-label" style="margin:1rem 0 0.5rem 0">'
        '⚡ Ações Rápidas</p>',
        unsafe_allow_html=True,
    )

    if has_image:
        # Labels mais curtos para caber no chip
        acoes = [
            ("🧼", "Fundo",      "remova o fundo desta imagem"),
            ("🎨", "Cenário",    "remova o fundo e gere um cenário clean para este produto"),
            ("🌈", "Variantes",  "gere 3 variações desta imagem com estilos diferentes"),
            ("🏷️", "Benefício",  "ADICIONAR_BENEFICIO_AUTO"), # Flag para lógica especial
            ("📱", "Capa",       "optimize esta imagem para ser a capa principal do anúncio"),
            ("🔍", "Análise",    "analise esta imagem de produto e me dê feedback detalhado"),
        ]
    else:  # vídeo
        acoes = [
            ("📊", "Retenção",   "analise este vídeo e avalie a retenção e o gancho"),
            ("🎬", "Gancho",      "avaliie o gancho dos primeiros 3 segundos e dê recomendações"),
            ("📋", "Checklist",   "analise o vídeo e gere um checklist de melhorias prioritárias"),
            ("✏️", "Roteiro",    "analise o vídeo e crie um roteiro melhorado para este produto"),
        ]

    atts      = st.session_state.get("chat_attachments", [])
    att_types_s = st.session_state.get("chat_attachment_types", [])
    att_prev  = st.session_state.get("chat_attachment_previews", [])

    # Grid de 3 colunas para evitar esmagamento
    n_cols = 3
    for i in range(0, len(acoes), n_cols):
        cols = st.columns(n_cols)
        for j in range(n_cols):
            idx = i + j
            if idx < len(acoes):
                icon, label, prompt = acoes[idx]
                with cols[j]:
                    st.markdown('<div class="action-card-btn">', unsafe_allow_html=True)
                    if st.button(
                        f"{icon}\n{label}",
                        key=f"qa_{idx}_{len(atts)}",
                        use_container_width=True,
                    ):
                        _handle_chat_input_with_vision(
                            prompt, atts, att_types_s, att_prev, full_context, segmento
                        )
                    st.markdown('</div>', unsafe_allow_html=True)


def _render_post_response_actions(
    turn: dict,
    turn_idx: int,
    full_context: str,
    segmento: str,
):
    from backend_core import (
        salvar_ou_baixar, resolve_shopee_url, fetch_shop_info, fetch_shop_products_intercept, fetch_competitors_intercept, fetch_reviews_intercept, generate_full_optimization, build_catalog_context, chat_with_gemini, analyze_reviews_with_gemini, generate_ai_scenario, generate_gradient_background, apply_contact_shadow, improve_image_quality, upscale_image, MODELOS_VISION, client, build_full_chat_context, detect_chat_intent, analyze_product_image_vision, process_chat_turn, suggest_faq_from_history, MODELOS_TEXTO, get_client
    )
    from PIL import Image
    """
    Renderiza ações de follow-up embaixo de cada resposta do assistente.
    Depende de 'post_actions' registrado no histórico.
    """
    actions = turn.get("post_actions", [])
    if not actions:
        return

    # Mostra imagens do turno se houver variantes
    result_imgs = turn.get("result_images", [])
    if result_imgs and len(result_imgs) > 1:
        st.markdown(
            f'<p class="section-label" style="font-size:10px;margin-bottom:4px">'
            f'🖼️ {len(result_imgs)} variantes geradas</p>',
            unsafe_allow_html=True,
        )
        # Botão de baixar todas
        salvar_ou_baixar(
            f"Baixar todas ({len(result_imgs)})",
            data=_pack_images_zip(result_imgs),
            file_name=f"variantes_{turn_idx+1}.zip",
            mime="application/zip",
            key=f"dl_all_variants_{turn_idx}",
        )

    st.markdown(
        '<p class="section-label" style="font-size:10px;margin:4px 0 2px 0">'
        '↩ Próximos passos</p>',
        unsafe_allow_html=True,
    )
    n_cols = min(len(actions), 4)
    cols = st.columns(n_cols)
    for i, act in enumerate(actions[:n_cols]):
        with cols[i]:
            if st.button(
                f"{act['icon']} {act['label']}",
                key=f"post_{turn_idx}_{i}",
                width="stretch",
                use_container_width=True,
            ):
                # Se o turno gerou imagens, reutiliza a última como contexto
                last_imgs = turn.get("result_images", [])
                if last_imgs:
                    # Serializa PIL → bytes para _send_message
                    import io as _io
                    buf = _io.BytesIO()
                    last_imgs[-1].convert("RGB").save(buf, format="JPEG", quality=92)
                    img_bytes = buf.getvalue()
                    _send_message(
                        act["prompt"],
                        [img_bytes], ["image"], [],
                        full_context, segmento,
                    )
                else:
                    _send_message(
                        act["prompt"],
                        [], [], [],
                        full_context, segmento,
                    )


def _pack_images_zip(images: list) -> bytes:
    """Empacota lista de PIL.Image em ZIP em memória."""
    import zipfile
    import io as _io
    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, img in enumerate(images):
            img_buf = _io.BytesIO()
            img.convert("RGB").save(img_buf, format="JPEG", quality=92)
            zf.writestr(f"variante_{i+1}.jpg", img_buf.getvalue())
    return buf.getvalue()


def _render_attachment_area(full_context: str = "", segmento: str = ""):
    """Renderiza painel de anexo + ações rápidas contextuais."""
    is_open = st.session_state.get("show_attach_panel", False)
    label   = "📎 Fechar anexos" if is_open else "📎 Anexar imagem / vídeo"

    if st.button(label, key="btn_toggle_attach", width="stretch"):
        st.session_state.show_attach_panel = not is_open
        if not st.session_state.show_attach_panel:
            st.session_state.chat_attachments         = []
            st.session_state.chat_attachment_types    = []
            st.session_state.chat_attachment_previews = []
        st.rerun()

    if st.session_state.get("show_attach_panel"):
        with st.container(border=True):
            st.markdown(
                '<p class="section-label" style="margin:0 0 0.5rem 0">Arquivos</p>',
                unsafe_allow_html=True,
            )
            uploaded = st.file_uploader(
                "Selecione imagens ou vídeo",
                type=["jpg", "jpeg", "png", "mp4"],
                accept_multiple_files=True,
                key="chat_file_uploader",
                label_visibility="collapsed",
            )
            if uploaded:
                attachments  = []
                att_types    = []
                att_previews = []
                for f in uploaded:
                    ftype = "video" if f.name.lower().endswith(".mp4") else "image"
                    att_types.append(ftype)
                    raw = f.read()
                    attachments.append(raw)
                    if ftype == "image":
                        from PIL import Image
                        pimg = Image.open(io.BytesIO(raw)).convert("RGB")
                        att_previews.append(pimg)

                        # ── Sessão ativa de edição ────────────────────
                        # Ao anexar imagem, salva como imagem ativa de edição
                        st.session_state.chat_active_edit_image = pimg.copy()
                        st.session_state.chat_active_edit_label = f.name
                    else:
                        att_previews.append(None)

                st.session_state.chat_attachments         = attachments
                st.session_state.chat_attachment_types    = att_types
                st.session_state.chat_attachment_previews = [p for p in att_previews if p is not None]

                # Preview compacto
                valid_prev = [p for p in att_previews if p is not None]
                if valid_prev:
                    prev_cols = st.columns(min(len(valid_prev), 4))
                    pi = 0
                    for fi, fp in enumerate(att_previews):
                        if fp is not None:
                            with prev_cols[pi % 4]:
                                st.image(fp, width=160,
                                         caption=f"🖼️ {uploaded[fi].name[:18]}")
                            pi += 1

                has_video_att = any(t == "video" for t in att_types)
                tipo_hint = (" | 🎬 Vídeo pronto — use ação rápida abaixo"
                             if has_video_att else
                             " | 🖼️ Imagem pronta — use ação rápida abaixo")
                st.success(f"✅ {len(uploaded)} arquivo(s) carregado(s).{tipo_hint}")

            # ── Ações rápidas aparecem DENTRO do painel quando há anexo ──
            att_types_now = st.session_state.get("chat_attachment_types", [])
            if att_types_now and full_context:
                st.markdown("---")
                _render_quick_actions(att_types_now, full_context, segmento)


def _send_message(
    user_message: str,
    attachments:  list,
    att_types:    list,
    att_previews: list,
    full_context: str,
    segmento:     str,
):
    from backend_core import (
        salvar_ou_baixar, resolve_shopee_url, fetch_shop_info, fetch_shop_products_intercept, fetch_competitors_intercept, fetch_reviews_intercept, generate_full_optimization, build_catalog_context, chat_with_gemini, analyze_reviews_with_gemini, generate_ai_scenario, generate_gradient_background, apply_contact_shadow, improve_image_quality, upscale_image, MODELOS_VISION, client, build_full_chat_context, detect_chat_intent, analyze_product_image_vision, process_chat_turn, suggest_faq_from_history, MODELOS_TEXTO, get_client
    )
    from PIL import Image
    """
    Processa e registra um turno de chat.

    V4.2: spinner inteligente que mostra quais etapas serão executadas.
    A falha em uma etapa NÃO cancela as demais.
    """
    # Converte bytes → PIL para processamento
    pil_images = []
    for i, att in enumerate(attachments):
        if att_types[i] == "image" and isinstance(att, bytes):
            pil_images.append(Image.open(io.BytesIO(att)).convert("RGBA"))
        else:
            pil_images.append(att)  # bytes de vídeo ficam como bytes

    # ── Detecta etapas para mostrar status inteligente ─────────
    has_video   = any(t == "video" for t in att_types)
    has_media   = len(attachments) > 0
    msg_lower   = user_message.lower()
    has_rembg   = "remov" in msg_lower or "fundo" in msg_lower
    has_scene   = any(w in msg_lower for w in ["cenário", "cena", "fundo ia", "packshot"])
    has_upscale = any(w in msg_lower for w in ["qualidade", "upscale", "resolução"])
    multi_step  = sum([has_rembg, has_scene, has_upscale]) > 1

    # ── Status visual dinâmico ─────────────────────────────────
    if has_video:
        label_spinner = "🎬 Analisando vídeo... (pode levar até 90s)"
    elif multi_step:
        passos = []
        if has_upscale: passos.append("upscale")
        if has_rembg:   passos.append("rembg")
        if has_scene:   passos.append("cenário IA")
        label_spinner = f"⚙️ Executando: {' → '.join(passos)}..."
    elif has_media:
        label_spinner = "🖼️ Processando imagem..."
    else:
        label_spinner = "💬 Gerando resposta..."

    with st.spinner(label_spinner):
        result = process_chat_turn(
            user_message     = user_message,
            attachments      = pil_images,
            attachment_types = att_types,
            chat_history     = st.session_state.chat_history,
            full_context     = full_context,
            segmento         = segmento,
            # Contexto estruturado da Auditoria
            selected_product     = st.session_state.get("selected_product"),
            df_competitors       = st.session_state.get("df_competitors"),
            optimization_reviews = st.session_state.get("optimization_reviews"),
            active_image         = st.session_state.get("chat_active_edit_image"),
        )

    # Registra no histórico
    st.session_state.chat_history.append({
        "user":               user_message,
        "assistant":          result["text"],
        "attachment_previews": list(att_previews),
        "result_images":      list(result["images"]),
        "result_captions":    list(result["captions"]),
        "market_context_used": result.get("market_context_used", False),
        "market_context_source": result.get("market_context_source", "none"),
        "radar_confidence":   result.get("radar_confidence"),
        "warnings":           list(result.get("warnings") or []),
    })

    # Empurra imagens para o painel de preview
    if result["images"]:
        st.session_state.chat_preview_images = (
            st.session_state.get("chat_preview_images", []) + result["images"]
        )[-8:]
        st.session_state.chat_preview_captions = (
            st.session_state.get("chat_preview_captions", []) + result["captions"]
        )[-8:]

    # ── Atualiza Camadas do Canvas ────────────────────────────
    if result["images"]:
        # Lista de intents que representam uma nova "imagem completa/final"
        GLOBAL_INTENTS = {"generate_scene", "recolor", "remove_bg", "generate_variants", "upscale"}
        current_intent = result.get("intent")
        final_img = result["images"][0]
        caption = result.get("captions", [""])[0] or "Resultado"
        
        # Se for a primeira imagem, vira base direto
        if not st.session_state.get("chat_canvas_layers"):
             st.session_state.chat_canvas_layers = [{
                "name": f"Base: {caption}",
                "img": final_img,
                "visible": True,
                "type": "base",
                "offset_x": 0.0,
                "offset_y": 0.0,
                "width_pct": 100.0,
                "height_pct": 100.0
            }]
        elif current_intent in GLOBAL_INTENTS:
            # Operação Global -> Coloca em Pendente para o usuário decidir (Substituir vs Nova Camada)
            st.session_state.canvas_pending_layer = {
                "img": final_img,
                "name": f"IA: {caption}",
                "intent": current_intent
            }
        else:
            # Operação aditiva/local (badge, texto, ROI local) -> Adiciona como camada direto
            for idx_res, res_img in enumerate(result["images"]):
                st.session_state.chat_canvas_layers.append({
                    "name": f"Chat: {caption} ({idx_res+1})",
                    "img": res_img,
                    "visible": True,
                    "type": "edit",
                    "offset_x": st.session_state.chat_canvas_roi["x"],
                    "offset_y": st.session_state.chat_canvas_roi["y"],
                    "width_pct": st.session_state.chat_canvas_roi["w"],
                    "height_pct": st.session_state.chat_canvas_roi["h"]
                })

    # ── Sincroniza imagem ativa em edição ─────────────────────
    if result.get("images"):
        st.session_state.chat_active_edit_image = result["images"][-1]
        st.session_state.chat_active_edit_label = caption

    # ── Salva post_actions no turno do histórico ───────────────
    if st.session_state.chat_history and result.get("post_actions"):
        st.session_state.chat_history[-1]["post_actions"] = result["post_actions"]

    # Limpa anexos após envio
    st.session_state.chat_attachments         = []
    st.session_state.chat_attachment_types    = []
    st.session_state.chat_attachment_previews = []
    st.session_state.show_attach_panel        = False

    st.rerun()


def _gerar_faq(full_context: str, shop_name: str):
    from backend_core import (
        salvar_ou_baixar, resolve_shopee_url, fetch_shop_info, fetch_shop_products_intercept, fetch_competitors_intercept, fetch_reviews_intercept, generate_full_optimization, build_catalog_context, chat_with_gemini, analyze_reviews_with_gemini, generate_ai_scenario, generate_gradient_background, apply_contact_shadow, improve_image_quality, upscale_image, MODELOS_VISION, client, build_full_chat_context, detect_chat_intent, analyze_product_image_vision, process_chat_turn, suggest_faq_from_history, MODELOS_TEXTO, get_client
    )
    from PIL import Image
    """Gera o FAQ automático via Gemini e salva no session_state."""
    produtos = st.session_state.shop_produtos or []
    faq_prompt = f"""Você é especialista em e-commerce Shopee Brasil.

Com base neste catálogo da loja '{shop_name}':
{chr(10).join(f"- {p['name']} | R$ {p['price']:.2f}" for p in produtos[:30]) or "(catálogo não carregado)"}

Gere EXATAMENTE 9 perguntas divididas em 3 categorias, com 3 perguntas cada.
Categorias: "📦 Produtos e Modelos", "🚚 Entrega e Frete", "🔄 Trocas e Pagamento"
REGRAS OBRIGATÓRIAS:
- Cada pergunta: máximo 80 caracteres
- Cada resposta: máximo 500 caracteres
- Respostas simpáticas, em português brasileiro
- Perguntas GENÉRICAS, sem citar nomes específicos de produtos

Formato EXATO:

CATEGORIA 1: 📦 Produtos e Modelos
PERGUNTA 1: [texto]
RESPOSTA 1: [texto]
PERGUNTA 2: [texto]
RESPOSTA 2: [texto]
PERGUNTA 3: [texto]
RESPOSTA 3: [texto]

CATEGORIA 2: 🚚 Entrega e Frete
PERGUNTA 4: [texto]
RESPOSTA 4: [texto]
PERGUNTA 5: [texto]
RESPOSTA 5: [texto]
PERGUNTA 6: [texto]
RESPOSTA 6: [texto]

CATEGORIA 3: 🔄 Trocas e Pagamento
PERGUNTA 7: [texto]
RESPOSTA 7: [texto]
PERGUNTA 8: [texto]
RESPOSTA 8: [texto]
PERGUNTA 9: [texto]
RESPOSTA 9: [texto]"""

    with st.spinner("Gerando FAQ com IA..."):
        faq_result = ""
        for m in MODELOS_TEXTO:
            try:
                cfg = {"thinking_config": {"thinking_budget": 0}} if ("3.1" in m or "2.5" in m) else {}
                resp = get_client().models.generate_content(
                    model=m, contents=[faq_prompt], config=cfg if cfg else None
                )
                faq_result = resp.text.strip()
                break
            except Exception:
                import time; time.sleep(2)

    if faq_result:
        st.session_state.faq_ia_geral = faq_result
    else:
        st.error("❌ Não foi possível gerar o FAQ. Tente novamente.")


def _render_faq_output(shop_name: str):
    from backend_core import (
        salvar_ou_baixar, resolve_shopee_url, fetch_shop_info, fetch_shop_products_intercept, fetch_competitors_intercept, fetch_reviews_intercept, generate_full_optimization, build_catalog_context, chat_with_gemini, analyze_reviews_with_gemini, generate_ai_scenario, generate_gradient_background, apply_contact_shadow, improve_image_quality, upscale_image, MODELOS_VISION, client, build_full_chat_context, detect_chat_intent, analyze_product_image_vision, process_chat_turn, suggest_faq_from_history, MODELOS_TEXTO, get_client
    )
    from PIL import Image
    """Exibe o FAQ gerado se houver."""
    if not st.session_state.get("faq_ia_geral"):
        return

    faq_result = st.session_state.faq_ia_geral
    st.markdown("---")
    with st.expander("📋 FAQ para o Seller Centre — clique para expandir", expanded=False):
        st.info("""📌 **Como usar no Seller Centre:**
1. Acesse seller.shopee.com.br → Atendimento ao Cliente → Assistente de IA
2. Clique em "Adicionar Categoria" e crie as 3 categorias
3. Dentro de cada categoria, adicione as 3 perguntas e salve""")

        avisos = []
        for linha in faq_result.split("\\n"):
            if linha.startswith("PERGUNTA") and ":" in linha:
                txt = linha.split(":", 1)[1].strip()
                if len(txt) > 80:
                    avisos.append(f"⚠️ Pergunta longa ({len(txt)} chars): '{txt[:50]}...'")
            elif linha.startswith("RESPOSTA") and ":" in linha:
                txt = linha.split(":", 1)[1].strip()
                if len(txt) > 500:
                    avisos.append(f"⚠️ Resposta longa ({len(txt)} chars): '{txt[:50]}...'")
        if avisos:
            for a in avisos:
                st.warning(a)

        for bloco in faq_result.split("\\n\\n"):
            if bloco.strip():
                st.code(bloco.strip(), language=None)

        faq_clean = faq_result.replace("**", "")
        salvar_ou_baixar(
            "Baixar FAQ (.txt)",
            data=faq_clean,
            file_name=f"faq_{shop_name}.txt",
            mime="text/plain",
            key="dl_faq_final",
        )


# ══════════════════════════════════════════════════════════════════════════
# PARTIÇÃO III — SENTINELA (3.0.0)
# ══════════════════════════════════════════════════════════════════════════
def render_sentinela():
    from backend_core import (
        salvar_ou_baixar, resolve_shopee_url, fetch_shop_info, fetch_shop_products_intercept, fetch_competitors_intercept, fetch_reviews_intercept, generate_full_optimization, build_catalog_context, chat_with_gemini, analyze_reviews_with_gemini, generate_ai_scenario, generate_gradient_background, apply_contact_shadow, improve_image_quality, upscale_image, MODELOS_VISION, client, build_full_chat_context, detect_chat_intent, analyze_product_image_vision, process_chat_turn, suggest_faq_from_history, MODELOS_TEXTO, get_client
    )
    from PIL import Image
    st.markdown("""
    <div class="page-header">
        <div class="page-header-icon">📡</div>
        <div>
            <div class="page-header-title">Sentinela Tracker</div>
            <div class="page-header-sub">Monitoramento Automático e Alertas de Preços via Telegram</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    import sentinela_db
    from telegram_service import TelegramSentinela

    sentinela_db.init_db()

    # ── 4 abas: adicionamos "🔧 Status" ──────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        "⚙️ Bot Connection",
        "🎯 Nicho Monitorado",
        "🏆 Top Lojas",
        "🔧 Status & Diagnóstico",
    ])

    # ══════════════════════════════════════════════════════════
    # TAB 1 — Bot Connection
    # ══════════════════════════════════════════════════════════
    with tab1:
        # ── Loja Mestra ───────────────────────────────────────
        st.markdown("### 🔗 Minha Loja Principal")
        loja_atual = st.text_input(
            "URL da sua Shopee",
            value=sentinela_db.obter_loja_mestra() or "",
            placeholder="https://shopee.com.br/nome_da_loja",
        )
        if st.button("💾 Salvar Loja Mestra", type="primary", width="stretch"):
            if loja_atual.strip() and "shopee" in loja_atual.lower():
                sentinela_db.configurar_loja_mestre(loja_atual.strip())
                st.success("✅ Loja mestra configurada!")
            else:
                st.error("Insira uma URL válida da Shopee.")

        st.markdown("---")

        # ── Sincronizar keywords da Auditoria ─────────────────
        st.markdown("### 🔄 Sincronizar com Auditoria")
        st.caption("Extrai automaticamente as keywords dos produtos carregados na Auditoria.")

        if st.button("🔌 Sincronizar Produtos → Keywords", type="primary", width="stretch"):
            produtos = st.session_state.get("shop_produtos") or []
            if produtos:
                import unicodedata
                from collections import Counter

                # Blacklist estendida — adjetivos/genéricos que não devem
                # virar keywords independentes
                palavras_inuteis = {
                    "de","da","do","das","dos","com","e","ou","em","no","na",
                    "para","por","a","o","um","uma","que","ao","aos","à","às",
                    "kit","pro","nova","novo","2025","2026",
                    # adjetivos e qualificadores comuns
                    "infantil","juvenil","feminina","feminino",
                    "masculino","masculina","adulto","adulto",
                    "rosa","preto","preta","branco","branca",
                    "azul","verde","vermelho","amarelo","grande",
                    "pequeno","pequena","medio","media",
                    "reforçada","reforcado","reforcada",
                    "resistente","impermeavel","lisa",
                    "original","importado","importada",
                    "premium","luxo","barato","barata",
                    "novo","nova","usado","usada",
                    "promocao","oferta","frete","gratis",
                    "2024","2025","2026","2027",
                }

                def _clean(word: str) -> str:
                    return "".join(
                        c for c in unicodedata.normalize("NFD", word)
                        if unicodedata.category(c) != "Mn"
                    ).lower()

                # 1. Contar substantivos por produto
                contagem = Counter()
                for prod in produtos:
                    nome = prod.get("name", "").lower()
                    palavras = [_clean(w) for w in nome.split()]
                    for p in palavras:
                        if len(p) > 3 and p not in palavras_inuteis:
                            contagem[p] += 1

                if not contagem:
                    st.warning("Nenhum substantivo forte encontrado nos produtos.")
                    st.rerun()

                # 2. O substantivo mais frequente = núcleo do nicho
                nucleo, freq_nucleo = contagem.most_common(1)[0]

                # 3. Construir keywords: só o núcleo + combinações
                #    que contenham o nucleo (descarta palavras soltas sem sentido)
                kws = [nucleo]
                for prod in produtos:
                    nome = prod.get("name", "").lower()
                    palavras = [_clean(w) for w in nome.split()]
                    # Procura bigramas que contenham o nucleo
                    for i, p in enumerate(palavras):
                        if p == nucleo:
                            # palavra anterior
                            if i > 0 and len(palavras[i-1]) > 3 and palavras[i-1] not in palavras_inuteis:
                                kws.append(f"{palavras[i-1]} {nucleo}")
                            # palavra posterior
                            if i < len(palavras)-1 and len(palavras[i+1]) > 3 and palavras[i+1] not in palavras_inuteis:
                                kws.append(f"{nucleo} {palavras[i+1]}")

                # Deduplicar e limitar
                kws = list(dict.fromkeys(kws))[:8]

                for kw in kws:
                    sentinela_db.adicionar_keyword(kw)

                st.success(f"✅ {len(kws)} keywords extraídas (núcleo: **{nucleo}**, apareceu {freq_nucleo}x): {', '.join(kws)}")
                st.rerun()
            else:
                st.warning("⚠️ Nenhum produto carregado. Vá para Auditoria Pro primeiro.")

        st.markdown("---")

        # ── Guia de Configuração ──────────────────────────────
        with st.expander("❓ Como configurar o Bot Telegram"):
            st.markdown("""
## 🛰️ Guia de Configuração — Telegram

### 1️⃣ Crie o bot (@BotFather)
1. Abra o Telegram e busque **@BotFather** (selo verificado ✅).
2. Envie `/newbot` e siga as instruções.
3. Copie o **HTTP API Token** gerado.

### 2️⃣ Descubra seu Chat ID
1. Busque **@userinfobot** no Telegram.
2. Envie qualquer mensagem — ele responde com seu `Id`.

### 3️⃣ "Acorde" o bot
1. Acesse `t.me/seu_bot_username` e clique em **COMEÇAR**.
   Sem isso, o bot não consegue te mandar mensagens.

### 4️⃣ Teste
Preencha os campos abaixo, clique em **Salvar** e depois **Testar**.
Se receber um 🚀 no Telegram, a Sentinela está ativa!
""")

        # ── Credenciais Telegram ──────────────────────────────
        st.markdown("### 🔌 Conectar ao Telegram")
        col1, col2 = st.columns(2)
        with col1:
            token = st.text_input(
                "Bot API Token (@BotFather)",
                value=sentinela_db.obter_config("telegram_token") or "",
                type="password",
            )
        with col2:
            chatid = st.text_input(
                "Chat ID",
                value=sentinela_db.obter_config("telegram_chat_id") or "",
            )

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("💾 Salvar Credenciais", type="primary", width="stretch"):
                token_s  = token.strip()
                chatid_s = chatid.strip()
                if not token_s:
                    st.warning("⚠️ O token não pode estar vazio.")
                elif not chatid_s:
                    st.warning("⚠️ O Chat ID não pode estar vazio.")
                else:
                    sentinela_db.salvar_config("telegram_token",  token_s)
                    sentinela_db.salvar_config("telegram_chat_id", chatid_s)
                    st.success("✅ Credenciais salvas!")
                    # Acorda o heartbeat para ele reler agora
                    try:
                        from launcher import wake_sentinela
                        wake_sentinela()
                    except Exception:
                        pass
        with col_b2:
            if st.button("🔔 Testar Comunicação", width="stretch"):
                ts = TelegramSentinela(token, chatid)
                if ts.testar_conexao():
                    st.success("✅ Mensagem enviada! Verifique o Telegram.")
                else:
                    st.error("❌ Falha. Verifique token, Chat ID e se clicou /start no bot.")

        st.markdown("---")

        # ── ▶️ Rodar Sentinela Agora ───────────────────────────
        st.markdown("### ▶️ Executar Ciclo Agora")
        st.caption(
            "Roda um ciclo completo imediatamente — sem esperar as 4h. "
            "Útil para testar se tudo está funcionando."
        )

        if st.button("🚀 Rodar Sentinela Agora", type="primary", width="stretch",
                     key="btn_rodar_sentinela_agora"):
            keywords = sentinela_db.listar_keywords()
            if not keywords:
                st.warning("⚠️ Nenhuma keyword cadastrada. Adicione na aba **Nicho Monitorado** primeiro.")
            else:
                token_val  = sentinela_db.obter_config("telegram_token")
                chatid_val = sentinela_db.obter_config("telegram_chat_id")
                if not token_val or not chatid_val:
                    st.warning("⚠️ Configure e salve as credenciais do Telegram antes.")
                else:
                    telegram = TelegramSentinela(token_val, chatid_val)
                    from backend_core import fetch_competitors_intercept

                    resultados_total = 0
                    erros = []

                    for kw in keywords:
                        with st.spinner(f"🔍 Buscando concorrentes para '{kw}'... (30-60s)"):
                            try:
                                resultados = fetch_competitors_intercept(kw)
                                if resultados:
                                    sentinela_db.processar_mudancas_e_alertar(kw, resultados, telegram)
                                    resultados_total += len(resultados)
                                    st.success(f"✅ '{kw}' → {len(resultados)} concorrentes processados.")
                                else:
                                    erros.append(f"'{kw}': nenhum resultado retornado.")
                                    st.warning(f"⚠️ '{kw}': nenhum resultado encontrado.")
                            except Exception as e:
                                erros.append(f"'{kw}': {e}")
                                st.error(f"❌ '{kw}': {e}")

                    if resultados_total > 0:
                        st.success(
                            f"🎉 Ciclo concluído! {resultados_total} entradas salvas no banco. "
                            f"Veja a aba **Top Lojas** para o ranking atualizado."
                        )
                        telegram.enviar_alerta(
                            f"✅ Ciclo manual concluído!\n"
                            f"{resultados_total} entradas coletadas para {len(keywords)} keyword(s)."
                        )
                    elif erros:
                        st.error(
                            "O ciclo terminou sem dados. Verifique a aba **🔧 Status** "
                            "para ver o log detalhado."
                        )

        st.markdown("---")
        st.info("⚠️ O ciclo automático roda a cada **4 horas** em background. Deixe o app minimizado no Tray.")

    # ══════════════════════════════════════════════════════════
    # TAB 2 — Nicho Monitorado
    # ══════════════════════════════════════════════════════════
    with tab2:
        st.markdown("### 📈 Configurar Monitoramento de Nicho")

        add_kw = st.text_input(
            "Nova Keyword",
            placeholder="Ex: mochila impermeável notebook",
            key="input_add_kw",
        )
        if st.button("➕ Adicionar Rastreador", type="primary", key="btn_add_kw"):
            if add_kw.strip():
                sentinela_db.adicionar_keyword(add_kw.strip())
                st.rerun()
            else:
                st.warning("Digite uma keyword.")

        st.markdown("---")
        st.markdown("##### Keywords em Foco:")

        lista = sentinela_db.listar_keywords()
        if lista:
            if st.button("🗑️ Limpar todas as keywords", key="btn_clear_all_kw"):
                for k in lista:
                    sentinela_db.remover_keyword(k)
                st.rerun()

        if not lista:
            st.warning("Nenhuma keyword cadastrada.")
        else:
            for k in lista:
                col_k1, col_k2 = st.columns([10, 1])
                with col_k1:
                    st.markdown(f"**⚡ {k}**")
                with col_k2:
                    if st.button("🗑️", key=f"del_{k}"):
                        sentinela_db.remover_keyword(k)
                        st.rerun()

    # ══════════════════════════════════════════════════════════
    # TAB 3 — Top Lojas
    # ══════════════════════════════════════════════════════════
    with tab3:
        st.markdown("### 🏆 Top 100 Lojas do Nicho")
        st.caption(
            "Ranking baseado na presença das lojas nos resultados das suas keywords. "
            "Execute um ciclo na aba **⚙️ Bot Connection** para popular os dados."
        )

        # Gráfico de tendência
        st.markdown("---")
        st.markdown("### 📈 Tendência de Preço do Nicho (7 dias)")
        tendencia = sentinela_db.gerar_tendencia_precos_nicho(7)

        if tendencia:
            df_trend = pd.DataFrame(tendencia, columns=["dia", "preco_medio"])
            df_trend["dia"] = pd.to_datetime(df_trend["dia"])

            try:
                import altair as alt
                chart = (
                    alt.Chart(df_trend)
                    .mark_line(point=True, color="#ee4d2d")
                    .encode(
                        x=alt.X("dia:T", title=None, axis=alt.Axis(labelColor="#f1f1f1", titleColor="#f1f1f1", gridColor="rgba(255,255,255,0.08)")),
                        y=alt.Y("preco_medio:Q", title=None, axis=alt.Axis(labelColor="#f1f1f1", titleColor="#f1f1f1", gridColor="rgba(255,255,255,0.08)")),
                        tooltip=["dia:T", alt.Tooltip("preco_medio:Q", format=".2f")]
                    )
                    .properties(height=300)
                    .configure(background="#1e1e24")
                    .configure_view(stroke=None)
                )
                st.altair_chart(chart, use_container_width=True)
            except Exception:
                st.warning("Não foi possível renderizar o gráfico nesta build. Exibindo tabela de tendência.")
                st.table(df_trend.reset_index(drop=True))

            c1, c2, c3 = st.columns(3)
            preco_inicio = df_trend.iloc[0]["preco_medio"]
            preco_fim    = df_trend.iloc[-1]["preco_medio"]
            variacao     = ((preco_fim - preco_inicio) / preco_inicio) * 100 if preco_inicio else 0
            c1.metric("Preço no início", f"R$ {preco_inicio:.2f}")
            c2.metric("Preço agora", f"R$ {preco_fim:.2f}", f"{variacao:+.1f}%")
            c3.metric("Dias com dados", len(df_trend))
        else:
            st.info("📭 Sem dados ainda. Execute um ciclo para começar a coleta.")

        # Ranking
        st.markdown("---")
        ranking = sentinela_db.gerar_ranking_lojas_nicho()

        if not ranking:
            st.warning(
                "Nenhum dado coletado ainda. "
                "Vá para **⚙️ Bot Connection → ▶️ Rodar Sentinela Agora** para popular o banco."
            )
        else:
            emojis = {"SUBINDO": "📈", "Caindo": "📉", "ESTÁVEL": "➡️"}
            df_display = pd.DataFrame({
                "🏪 Rank":     range(1, len(ranking) + 1),
                "🆔 Shop ID":  [r["shop_id"]        for r in ranking],
                "🔥 Presenças": [r["presencas"]       for r in ranking],
                "🥇 Melhor Pos.": [r["melhor_posicao"] for r in ranking],
                "💰 Preço Médio": [f"R$ {r['preco_medio']:.2f}" for r in ranking],
                "📊 Tendência": [
                    f"{emojis.get(r['tendencia'],'')} {r['tendencia']}"
                    if r["preco_recente"] else "—"
                    for r in ranking
                ],
            })
            st.table(df_display.reset_index(drop=True))

    # ══════════════════════════════════════════════════════════
    # TAB 4 — Status & Diagnóstico  ← NOVO
    # ══════════════════════════════════════════════════════════
    with tab4:
        st.markdown("### 🔧 Diagnóstico do Sistema")
        st.caption(
            "Use esta aba para verificar se a Sentinela está lendo o banco correto "
            "e para inspecionar o log da última execução."
        )

        if st.button("🔄 Atualizar diagnóstico", key="btn_refresh_diag"):
            st.rerun()

        diag = sentinela_db.get_diagnostics()

        # ── Paths ──────────────────────────────────────────────
        st.markdown("#### 📂 Caminhos")
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Runtime Dir**")
            st.code(diag["runtime_dir"], language=None)
            st.markdown("**Banco de Dados (DB_PATH)**")
            db_label = "✅ Existe" if diag["db_existe"] else "❌ Não encontrado"
            st.code(diag["db_path"], language=None)
            st.caption(f"{db_label} | {diag['db_tamanho_kb']} KB")
        with col_b:
            st.markdown("**Log da Sentinela**")
            st.code(diag["log_path"], language=None)
            log_existe = "✅ Existe" if diag["ultimas_linhas_log"] else "📭 Vazio/não criado"
            st.caption(log_existe)

        # ── Credenciais Telegram ────────────────────────────────
        st.markdown("---")
        st.markdown("#### 🔑 Credenciais Telegram")
        cc1, cc2 = st.columns(2)
        with cc1:
            tok_ok = diag["telegram_token"]
            st.markdown(f"Bot API Token: {'✅ presente' if tok_ok else '❌ AUSENTE'}")
            if tok_ok:
                st.caption(f"Comprimento: {diag['telegram_token_len']} caracteres")
            else:
                st.caption("Token não definido ou vazio")
        with cc2:
            cid_ok = diag["telegram_chat_id"]
            st.markdown(f"Chat ID: {'✅ presente' if cid_ok else '❌ AUSENTE'}")
            if cid_ok:
                st.caption(f"ID: {diag['telegram_chat_id_masked']}")
            else:
                st.caption("Chat ID não definido ou vazio")

        if not tok_ok or not cid_ok:
            st.warning(
                "⚠️ Credenciais incompletas — o heartbeat está pulando os ciclos. "
                "Preencha e salve na aba **⚙️ Bot Connection**."
            )
        else:
            st.success("✅ Credenciais válidas — o heartbeat conseguirá enviar alertas.")

        # ── Contadores do DB ────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 🗄️ Estado do Banco")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Keywords ativas",  diag["n_keywords"])
        c2.metric("Registros histórico", diag["n_historico"])
        c3.metric("Configs salvas",    diag["n_configs"])
        c4.metric("Última coleta",     diag["ultima_coleta"] or "Nunca")

        if diag["n_historico"] == 0:
            st.warning(
                "⚠️ Banco vazio — a Sentinela ainda não salvou nenhum dado nesta instalação. "
                "Use **▶️ Rodar Sentinela Agora** na aba Bot Connection para popular este banco."
            )
        else:
            st.success(f"✅ {diag['n_historico']} registros encontrados neste banco.")

        # ── Log ─────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 📋 Últimas linhas do sentinela_log.txt")

        if diag.get("log_error"):
            st.error(f"Erro ao ler log: {diag['log_error']}")
        elif not diag["ultimas_linhas_log"]:
            st.info(
                "Log ainda não foi criado. Isso significa que o heartbeat automático "
                "ainda não rodou, ou que o app foi aberto diretamente pelo terminal "
                "(sem passar pelo launcher.py). "
                "Use **▶️ Rodar Sentinela Agora** para gerar a primeira entrada."
            )
        else:
            linhas = diag["ultimas_linhas_log"]
            # Colorização simples
            linhas_fmt = []
            for l in linhas:
                if "ERRO" in l or "FALHA" in l or "EXCEÇÃO" in l or "TIMEOUT" in l:
                    linhas_fmt.append(f"🔴 {l}")
                elif "OK " in l or "concluído" in l or "concorrentes" in l:
                    linhas_fmt.append(f"🟢 {l}")
                elif "Sem " in l or "aguardando" in l:
                    linhas_fmt.append(f"🟡 {l}")
                else:
                    linhas_fmt.append(f"   {l}")

            st.code("\n".join(linhas_fmt), language=None)

        # ── Ação: abrir log no Explorer ─────────────────────────
        import sys as _sys
        if getattr(_sys, "frozen", False):
            if st.button("📁 Abrir pasta do banco no Explorer", key="btn_open_folder"):
                import subprocess as _sp
                _sp.Popen(["explorer", diag["runtime_dir"]])

# ══════════════════════════════════════════════════════════════════════════
# ESPELHO DA LOJA
# ══════════════════════════════════════════════════════════════════════════

def _render_pattern_report_preview(report: dict):
    """R7.2L: Render a pattern report preview in the Radar Assistido UI."""
    from shopee_core.radar_patterns_service import format_brl_markdown

    _j = lambda items: "`, `".join(items) if items else ""
    _brl = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if v is not None else "N/A"
    _brl_md = format_brl_markdown

    st.markdown("---")
    st.markdown("##### :bar_chart: Preview do Relatório de Padrões")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Confiança", report.get("confidence", "N/A").upper())
    col2.metric("Concorrentes Usados", report.get("total_competitors", 0))
    col3.metric("Concorrentes Efetivos", report.get("effective_competitor_count", report.get("total_competitors", 0)))
    col4.metric("Variacoes Agrupadas", report.get("variants_grouped", 0))
    _pmin = report.get("price_min")
    _pmax = report.get("price_max")
    if _pmin is not None and _pmax is not None:
        col5.metric("Faixa de Preço", f"{_brl(_pmin)} — {_brl(_pmax)}")
    else:
        col5.metric("Faixa de Preço", "N/A")

    if report.get("warnings"):
        with st.expander(":warning: Avisos", expanded=True):
            for w in report["warnings"]:
                st.markdown(f"- {w}")

    strat_title = report.get("strategy_title", {})
    strat_features = report.get("strategy_features", {})
    strat_desc = report.get("strategy_description", {})
    strat_images = report.get("strategy_images", {})

    tabs = st.tabs(["Termos do Título", "Features", "Descrição", "Imagens", "Evidências"])

    with tabs[0]:
        strong = strat_title.get("strong_terms", [])
        secondary = strat_title.get("secondary_terms", [])
        if strong:
            st.markdown(f"**Termos fortes:** `{_j(strong)}`")
        if secondary:
            st.markdown(f"**Termos secundários:** `{_j(secondary)}`")
        if strat_title.get("avoid_terms"):
            st.markdown(f":warning: **Termos de baixa recorrência:** `{_j(strat_title['avoid_terms'])}`")

    with tabs[1]:
        rec = strat_features.get("recommended", [])
        if rec:
            st.markdown(f"**Features recomendadas:** `{_j(rec)}`")
        off = strat_features.get("off_niche", [])
        if off:
            off_labels = [f.get("feature") if isinstance(f, dict) else f for f in off]
            st.markdown(f":warning: **Features off-niche:** `{_j(off_labels)}`")
        for w in strat_features.get("warnings", []):
            if w:
                st.markdown(f":warning: {w}")

    with tabs[2]:
        comm = strat_desc.get("commercial_arguments", [])
        if comm:
            st.markdown(f"**Argumentos comerciais recorrentes:** `{_j(comm)}`")
        for obs in strat_desc.get("observations", []):
            if obs:
                st.markdown(f":bulb: {obs}")

    with tabs[3]:
        avg_imgs = strat_images.get("avg_image_count", 0)
        avg_str = f"{avg_imgs:.1f}".replace(".", ",")
        st.markdown(f"**Média de imagens:** {avg_str}")
        for rec_text in strat_images.get("recommendations", []):
            st.markdown(f":bulb: {rec_text}")

    with tabs[4]:
        evidence = report.get("evidence_list", [])
        if evidence:
            for e in evidence:
                score = e.get("match_relevance_score") or "N/A"
                verdict_label = e.get("match_verdict", "N/A").replace("competitor_", "")
                price_str = _brl(e.get("price"))
                st.markdown(
                    f"- **{e.get('title', 'Sem título')}** — "
                    f"*{verdict_label}* (score: {score}) — "
                    f"{_escape_markdown_currency(price_str)} — {e.get('marketplace', '')}"
                )
                if int(e.get("variants_count") or 1) > 1:
                    st.caption(
                        f"{e.get('variants_count')} variacoes agrupadas: "
                        f"{e.get('cluster_reason') or 'titulo/vendedor/preco semelhantes'}"
                    )

    # Price detail
    with st.expander(":moneybag: Detalhes de Preço", expanded=False):
        st.markdown(f"- **Mínimo:** {_brl_md(report.get('price_min'))}")
        st.markdown(f"- **Máximo:** {_brl_md(report.get('price_max'))}")
        st.markdown(f"- **Média:** {_brl_md(report.get('price_avg'))}")
        st.markdown(f"- **Mediana:** {_brl_md(report.get('price_median'))}")
        if _pmin is not None and _pmax is not None:
            p_med = report.get("price_median")
            if p_med:
                band_low = p_med * 0.85
                band_high = p_med * 1.15
                st.markdown(f"- :bar_chart: **Faixa competitiva observada:** {_brl_md(band_low)} — {_brl_md(band_high)}")
                st.caption("Use esta faixa como referência de mercado, não como preço final automático. A decisão deve considerar margem, qualidade, marca, frete e posicionamento.")


def render_radar_workflow():
    st.markdown('<div class="page-header-title">Radar Assistido de Concorrentes</div>', unsafe_allow_html=True)
    st.markdown("Cadastre URLs de produtos concorrentes, colete dados e gere uma análise de mercado para usar na Auditoria.")
    
    from shopee_core.radar_workflow_ui_service import (
        list_own_products_for_radar, format_own_product_label,
        add_competitor_urls_for_product, get_radar_queue_summary,
        get_competitor_table_for_product, classify_linked_candidates_for_product,
        run_pattern_analysis_for_product, run_linked_collection_for_product,
        ensure_collection_jobs_for_linked_candidates,
        run_automatic_radar_cycle,
        get_refresh_status, list_due_for_refresh, refresh_product,
    )
    import shopee_core.radar_collector as rc
    import time
    
    products = list_own_products_for_radar(200)
    if not products:
        st.info("Use a Auditoria ou o Espelho da Loja para salvar produtos próprios primeiro.")
        return
        
    selected_uid = st.selectbox(
        "Selecione o produto próprio base:",
        options=[p["product_uid"] for p in products],
        format_func=lambda uid: format_own_product_label(next(p for p in products if p["product_uid"] == uid))
    )
    
    if "last_selected_uid" not in st.session_state or st.session_state["last_selected_uid"] != selected_uid:
        st.session_state["last_selected_uid"] = selected_uid
        st.session_state.pop("radar_collection_result", None)
        
    prod = next(p for p in products if p["product_uid"] == selected_uid)
    
    st.divider()
    
    colA, colB = st.columns([1, 1])
    with colA:
        st.write("##### Sugestões de Busca")
        st.caption("Você pode copiar essas sugestões e pesquisar no Mercado Livre ou Shopee:")
        
        # Sugestões simples por token
        title = prod.get("title") or ""
        tokens = [t for t in title.lower().split() if len(t) > 3]
        if len(tokens) >= 2:
            st.code(" ".join(tokens[:3]))
            if len(tokens) >= 4:
                st.code(f"{tokens[0]} {tokens[1]} {tokens[-1]}")
    
    with colB:
        st.write("##### Cadastro de URLs")
        urls_text = st.text_area("Cole aqui URLs de concorrentes, uma por linha", height=120)
        if st.button("Adicionar URLs ao Radar"):
            if urls_text.strip():
                with st.spinner("Processando..."):
                    res = add_competitor_urls_for_product(selected_uid, urls_text)
                    st.success(f"Recebidas: {res['total_received']} | Criadas: {res['created']} | Duplicadas: {res['duplicates']} | Inválidas: {res['invalid']}")
                    time.sleep(1.5)
                    st.rerun()
            else:
                st.warning("Insira pelo menos uma URL.")
                
    st.divider()
    st.write("##### Fila de Coleta")
    ensure_collection_jobs_for_linked_candidates(selected_uid)
    summary = get_radar_queue_summary(selected_uid)
    
    if "radar_collection_result" in st.session_state:
        res_coleta = st.session_state["radar_collection_result"]
        if res_coleta.get("environment_error"):
            st.warning(f"⚠️ {res_coleta['message']}")
            with st.expander("💡 Como abrir o Chrome do Radar manualmente (Fallback)", expanded=True):
                st.markdown(
                    "Se o navegador não abrir automaticamente, você pode iniciar o Chrome DevTools Protocol manualmente:\n\n"
                    "**No Terminal / PowerShell:**\n"
                    "```powershell\n"
                    "cd \"C:\\Users\\Defal\\Documents\\Faculdade\\Projeto Shopee\"\n"
                    "powershell -ExecutionPolicy Bypass -File .\\deploy\\local\\start-radar-chrome.ps1\n"
                    "```\n\n"
                    "*Certifique-se de que não haja outras janelas do Chrome bloqueando a porta 9222 e tente coletar novamente.*"
                )
        else:
            st.info(
                f"Última Coleta Realizada: Processados: {res_coleta['processed']} | "
                f"Sucesso: {res_coleta['succeeded']} | "
                f"Falhas: {res_coleta['failed']} | "
                f"Ignorados: {res_coleta['skipped']}"
            )
            if res_coleta.get("errors"):
                with st.expander("⚠️ Detalhes das Falhas na Coleta", expanded=True):
                    for err in res_coleta["errors"]:
                        st.markdown(f"**URL:** {err['url']}")
                        if err.get("stage"):
                            st.markdown(f"**Etapa:** {err['stage']}")
                        st.markdown(f"**Erro:** `{err['error']}`")
                        ss_path = err.get("screenshot_path")
                        if ss_path:
                            from pathlib import Path
                            if Path(ss_path).exists():
                                st.markdown(f"**Screenshot de Depuração:**")
                                try:
                                    st.image(str(Path(ss_path).resolve()))
                                except Exception:
                                    pass
                        st.divider()
            if res_coleta.get("asset_warnings"):
                with st.expander("Avisos de imagens/assets", expanded=False):
                    for warn in res_coleta["asset_warnings"]:
                        st.markdown(f"**URL:** {warn.get('url', '')}")
                        st.markdown(f"**Status:** `{warn.get('status', 'warning')}`")
                        st.markdown(f"**Aviso:** `{warn.get('error', '')}`")
                        st.divider()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Jobs Pendentes", summary["jobs_pending"])
    col2.metric("Candidatos Vinculados", summary["candidates"])
    col3.metric("Concorrentes Diretos", summary["competitor_direct"])
    
    c_lim, c_mode, c_assets, c_btn = st.columns([1, 1, 2, 2])
    with c_lim:
        limit = st.selectbox("Limite de coleta:", [1, 3, 5, 10], index=2)
    with c_mode:
        browser_mode = st.selectbox("Modo do Navegador:", ["cdp", "persistent"], index=0)
    with c_assets:
        save_assets = st.checkbox("Baixar imagens/assets", value=False)
        st.caption("Recomendado deixar desmarcado durante a coleta inicial. Imagens podem ser baixadas depois.")
    with c_btn:
        st.write("")
        st.write("")
        if st.button("Coletar URLs Pendentes", use_container_width=True):
            if summary["jobs_pending"] == 0:
                st.info("Nenhum job pendente para este produto.")
            else:
                chrome_ok = True
                ready_res = {}
                
                if browser_mode == "cdp":
                    with st.spinner("Abrindo Chrome do Radar..."):
                        from shopee_core.radar_cdp_service import ensure_radar_chrome_ready
                        ready_res = ensure_radar_chrome_ready("http://127.0.0.1:9222")
                        chrome_ok = ready_res["ok"]
                        
                if not chrome_ok:
                    st.session_state["radar_collection_result"] = {
                        "processed": 0,
                        "succeeded": 0,
                        "failed": 0,
                        "skipped": 0,
                        "environment_error": True,
                        "message": ready_res.get("message", "Não foi possível abrir o Chrome do Radar automaticamente.")
                    }
                    st.rerun()
                else:
                    if browser_mode == "cdp":
                        if ready_res.get("started"):
                            st.success("Chrome do Radar foi aberto automaticamente. Iniciando a coleta...")
                        else:
                            st.success("Chrome do Radar já estava aberto. Iniciando a coleta...")
                        time.sleep(1.0)
                        
                    st.warning("A coleta pode abrir o navegador e demorar alguns minutos. Aguarde...")
                    
                    # Placeholders para progresso
                    p_info = st.empty()
                    p_log = st.empty()
                    p_bar = st.progress(0.0)
                    
                    # Limpa flag de cancelamento anterior
                    from pathlib import Path
                    flag_file = Path("data/radar_stop_collection.flag")
                    if flag_file.exists():
                        try:
                            flag_file.unlink()
                        except Exception:
                            pass
                            
                    total_jobs = min(limit, summary["jobs_pending"])
                    
                    def progress_cb(state_dict):
                        idx = state_dict.get("index", 0)
                        tot = state_dict.get("total", total_jobs)
                        url = state_dict.get("url", "")
                        stage = state_dict.get("stage", "")
                        msg = state_dict.get("message", "")
                        
                        stage_map = {
                            "START": "Iniciando",
                            "OPENING": "Abrindo página",
                            "LOADED": "Página carregada",
                            "SCROLLING": "Fazendo scroll",
                            "EXTRACTING_TITLE_PRICE": "Extraindo título e preço",
                            "EXTRACTING_DESC": "Extraindo descrição",
                            "EXTRACTING_IMAGE_URLS": "Coletando URLs de imagens",
                            "EXTRACTING_IMAGES": "Coletando URLs de imagens",
                            "EXTRACTING": "Extraindo dados",
                            "SAVING_MAIN_DATA": "Salvando dados principais",
                            "SAVING_DB": "Salvando dados principais",
                            "SAVING": "Salvando no banco",
                            "DOWNLOADING_ASSETS": "Baixando imagens opcionais",
                            "ASSETS_SKIPPED": "Download de imagens desativado",
                            "ASSETS_WARNING": "Aviso nos assets",
                            "SKIPPING_OPTIONAL_DETAILS": "Pulando detalhes opcionais",
                            "FAST_PRIMARY_READY": "Dados principais coletados",
                            "CDP_PAGE_RELEASED": "Navegador liberado",
                            "FINALIZING_URL": "Finalizando URL",
                            "DONE": "Coleta concluída",
                            "FAILED": "Falha na coleta"
                        }
                        display_stage = stage_map.get(stage, stage)
                        
                        if tot > 0:
                            p_bar.progress(min(1.0, idx / tot))
                        p_info.markdown(f"**Coletando {idx}/{tot}**\n\n**URL:** `{url}`")
                        p_log.text(f"Etapa: {display_stage} ({msg})")
                        
                    # Botão de cancelamento
                    if st.button("Cancelar após URL atual", key="cancel_collection_btn", use_container_width=True):
                        try:
                            Path("data/radar_stop_collection.flag").write_text("stop")
                        except Exception:
                            pass
                        st.info("Cancelamento solicitado. A coleta parará após concluir a URL atual.")
                        
                    try:
                        res_coleta = run_linked_collection_for_product(
                            own_product_uid=selected_uid,
                            limit=limit,
                            save_assets=save_assets,
                            browser_mode=browser_mode,
                            collect_image_urls=True,
                            progress_callback=progress_cb
                        )
                        st.session_state["radar_collection_result"] = res_coleta
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro na coleta: {e}")

    st.divider()
    st.write("##### Classificação e Relatório de Padrões")
    c_class, c_reclass = st.columns([1, 1])
    with c_class:
        if st.button("Classificar Concorrentes", use_container_width=True):
            if summary.get("jobs_pending", 0) > 0:
                st.warning(
                    f"Existem {summary['jobs_pending']} candidatos pendentes. "
                    "Eles precisam ser coletados antes de serem classificados."
                )
            with st.spinner("Classificando..."):
                res = classify_linked_candidates_for_product(selected_uid)
                if res["ok"]:
                    st.success(f"Classificados: {res['total']} (Diretos: {res['direct']} | Parciais: {res['partial']} | Rejeitados: {res['rejected']})")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error(res["error"])
    with c_reclass:
        if st.button("Reclassificar (forçar)", use_container_width=True, type="secondary"):
            with st.spinner("Reclassificando com limpeza..."):
                res = classify_linked_candidates_for_product(selected_uid, force_reclassify=True)
                if res["ok"]:
                    st.success(f"Reclassificados: {res['total']} (Diretos: {res['direct']} | Parciais: {res['partial']} | Rejeitados: {res['rejected']})")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error(res["error"])

    # ── R7.2L: Relatório de Padrões ──────────────────────
    st.write("##### :bar_chart: Relatório de Padrões")
    scope_col, btn_col = st.columns([1, 2])
    with scope_col:
        report_scope = st.selectbox(
            "Escopo do relatório:",
            options=["direct_only", "direct_plus_partial"],
            format_func=lambda s: "Diretos apenas" if s == "direct_only" else "Diretos + Parciais",
            key="report_scope_selector",
        )
    with btn_col:
        st.write("")
        st.write("")
        if st.button("Gerar/Atualizar Relatório de Padrões", use_container_width=True):
            with st.spinner("Analisando padrões de mercado..."):
                res = run_pattern_analysis_for_product(selected_uid, candidate_scope=report_scope)
                if res["ok"]:
                    st.session_state["last_pattern_report"] = res["report"]
                    st.success("Relatório gerado com sucesso!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"Não foi possível gerar: {res['error']}")

    # Preview do relatório se existir
    last_report = st.session_state.get("last_pattern_report")
    if not last_report:
        from shopee_core.radar_patterns_service import get_latest_pattern_report as _get_latest
        _cached = _get_latest(selected_uid)
        if _cached:
            last_report = _cached
            st.session_state["last_pattern_report"] = _cached

    if last_report and last_report.get("own_product_uid") == selected_uid:
        _render_pattern_report_preview(last_report)
    else:
        st.info("Nenhum relatório gerado ainda. Selecione o escopo e clique em 'Gerar/Atualizar Relatório de Padrões'.")

    st.divider()
    # ── R7.3: Radar Automático ──────────────────────────────
    st.write("##### 🤖 Radar Automático")
    st.caption("Busca concorrentes no Mercado Livre, coleta dados, classifica e gera relatório automaticamente.")

    auto_col1, auto_col2, auto_col3 = st.columns(3)
    with auto_col1:
        auto_mkt = st.selectbox("Marketplace:", ["mercadolivre", "shopee (experimental)"], index=0,
                                key="auto_marketplace")
        auto_max_q = st.number_input("Máx. buscas:", min_value=1, max_value=12, value=6, key="auto_max_queries")
        auto_max_u = st.number_input("Máx. URLs por busca:", min_value=1, max_value=20, value=10, key="auto_max_urls")
    with auto_col2:
        auto_max_c = st.number_input("Coletas por ciclo:", min_value=1, max_value=30, value=10, key="auto_max_collect")
        auto_max_cycles = st.number_input("Máx. ciclos:", min_value=1, max_value=5, value=3, key="auto_max_cycles")
        auto_max_total = st.number_input(
            "Máx. candidatos:",
            min_value=10,
            max_value=100,
            value=60,
            step=5,
            key="auto_max_total_candidates",
            help="Limita a descoberta de novos candidatos. Pendentes ja existentes continuam sendo coletados.",
        )
    with auto_col3:
        auto_scope = st.selectbox("Escopo do relatório:",
                                  options=["direct_only", "direct_plus_partial"],
                                  format_func=lambda s: "Diretos apenas" if s == "direct_only" else "Diretos + Parciais",
                                  key="auto_scope")
        auto_target = st.selectbox("Confiança alvo:",
                                   options=["high", "medium", "low"],
                                   index=1, key="auto_target_conf")
        auto_runtime = st.number_input("Tempo limite (min):", min_value=5, max_value=60, value=20, key="auto_runtime_minutes")

    # Botões auxiliares: reconectar / reiniciar Chrome
    aux_a, aux_b = st.columns(2)
    with aux_a:
        if st.button("Reconectar ao Chrome aberto", use_container_width=True, key="btn_radar_reconnect"):
            from shopee_core.radar_cdp_service import is_cdp_available, _fetch_json_version
            if is_cdp_available():
                v = _fetch_json_version()
                browser = (v or {}).get("Browser", "Chrome")
                st.success(f"Chrome CDP ativo: {browser}")
            else:
                st.error("Chrome CDP nao responde em http://127.0.0.1:9222/json/version")
    with aux_b:
        if st.button("Reiniciar Chrome do Radar", use_container_width=True, key="btn_radar_restart"):
            from shopee_core.radar_cdp_service import kill_managed_radar_chrome, start_radar_chrome, ensure_radar_chrome_ready
            kill_res = kill_managed_radar_chrome()
            if kill_res.get("killed"):
                st.info(f"Chrome do Radar encerrado (PID {kill_res.get('pids', [])}).")
            start_res = ensure_radar_chrome_ready()
            if start_res.get("ok"):
                st.success(f"Chrome do Radar pronto: {start_res.get('message')}")
            else:
                diag = start_res.get("diagnostics", {})
                with st.expander("Diagnostico do Chrome", expanded=True):
                    st.code(json.dumps(diag, indent=2, default=str))
                st.error(f"Falha ao reiniciar Chrome: {start_res.get('message')}")

    auto_run_col, auto_continue_col = st.columns(2)
    with auto_run_col:
        run_auto_clicked = st.button("Rodar Radar Automático", use_container_width=True, type="primary")
    with auto_continue_col:
        continue_auto_clicked = st.button("Continuar ciclo automático", use_container_width=True)

    if run_auto_clicked or continue_auto_clicked:
        mkt_val = "mercadolivre" if "mercadolivre" in auto_mkt else "shopee"
        if mkt_val == "shopee":
            st.warning("Shopee esta em modo experimental. Pode haver bloqueios. Preferencia: Mercado Livre.")

        p_info = st.empty()
        p_log = st.empty()
        p_bar = st.progress(0.0)

        def auto_progress(state_dict):
            stage = state_dict.get("stage", "")
            msg = state_dict.get("message", "")
            stage_map = {
                "chrome": "Abrindo Chrome",
                "chrome_check": "Procurando Chrome/Edge",
                "chrome_validate": "Validando CDP",
                "cycle": "Executando ciclo",
                "queries": "Gerando buscas",
                "discover": "Buscando URLs no ML",
                "jobs": "Preparando coletas",
                "collect": "Coletando candidatos",
                "classify": "Classificando concorrentes",
                "report": "Gerando relatório",
                "confidence": "Calculando confiança",
                "done": "Concluído",
            }
            display = stage_map.get(stage, stage)
            p_info.markdown(f"**Etapa:** {display}")
            p_log.text(msg)

        def chrome_progress(state_dict):
            stage = state_dict.get("stage", "")
            msg = state_dict.get("message", "")
            stage_map = {
                "chrome_check": "Procurando Chrome/Edge",
                "chrome_start": "Abrindo Chrome do Radar",
                "chrome_wait": "Aguardando porta 9222",
                "chrome_validate": "Validando CDP",
                "chrome_occupied": "Porta ocupada - analisando",
                "chrome_kill_stale": "Limpando Chrome travado",
                "done": "OK",
                "error": "Falha",
            }
            display = stage_map.get(stage, stage)
            p_info.markdown(f"**Etapa:** {display}")
            p_log.text(msg)

        with st.spinner("Executando ciclo do Radar Automático..."):
            auto_res = run_automatic_radar_cycle(
                own_product_uid=selected_uid,
                marketplace=mkt_val,
                target_confidence=auto_target,
                max_queries=int(auto_max_q),
                max_urls_per_query=int(auto_max_u),
                max_collect=int(auto_max_c),
                max_collect_per_cycle=int(auto_max_c),
                max_cycles=int(auto_max_cycles),
                max_total_candidates=int(auto_max_total),
                max_total_runtime_minutes=int(auto_runtime),
                candidate_scope=auto_scope,
                discover_new_urls=not continue_auto_clicked,
                progress_callback=auto_progress,
            )

        if auto_res.get("ok"):
            status = auto_res.get("status", "unknown")
            status_label = {
                "success": "confianca alvo atingida",
                "needs_more_collection": "ainda precisa coletar mais",
                "limit_reached": "limite configurado atingido",
                "exhausted": "fila esgotada",
            }.get(status, status)
            if status == "success":
                st.success(f"Ciclo automatico concluido: {status_label}.")
            else:
                st.warning(f"Ciclo automatico parou: {status_label}.")
                if auto_res.get("stop_reason"):
                    st.info(auto_res["stop_reason"])
            disc = auto_res.get("discovery") or {}
            coll = auto_res.get("collection") or {}
            clas = auto_res.get("classification") or {}
            conf = auto_res.get("confidence") or {}

            st.json({
                "Status": status,
                "Motivo de parada": auto_res.get("stop_reason", ""),
                "Ciclos executados": auto_res.get("cycles_run", 0),
                "URLs encontradas": disc.get("urls_found", 0),
                "Novos candidatos": auto_res.get("candidates_inserted", disc.get("urls_inserted", 0)),
                "Coletados nesta rodada": auto_res.get("collected", coll.get("succeeded", 0)),
                "Pendentes restantes": auto_res.get("pending", 0),
                "Falhas coleta": auto_res.get("failed", coll.get("failed", 0)),
                "Direct": auto_res.get("direct", clas.get("direct", 0)),
                "Partial": auto_res.get("partial", clas.get("partial", 0)),
                "Rejected": auto_res.get("rejected", clas.get("rejected", 0)),
                "Concorrentes efetivos": conf.get("effective_competitor_count", "N/A"),
                "Variações agrupadas": conf.get("variants_grouped", 0),
                "Confianca alvo": auto_res.get("target_confidence", auto_target).upper(),
                "Confiança": f"{conf.get('level', 'N/A').upper()} ({conf.get('score', 0)} pts)",
            })

            warnings_auto = list(auto_res.get("warnings") or []) + list(conf.get("warnings") or [])
            if warnings_auto:
                with st.expander("Avisos de confiança", expanded=False):
                    for w in warnings_auto:
                        st.markdown(f"- {w}")

            # Refresh report preview in session state
            from shopee_core.radar_patterns_service import get_latest_pattern_report
            fresh_report = get_latest_pattern_report(selected_uid)
            if fresh_report:
                st.session_state["last_pattern_report"] = fresh_report

            st.session_state["last_auto_radar_result"] = auto_res
        else:
            error_step = auto_res.get("step", "?")
            errors_msg = "; ".join(auto_res.get("errors", []))
            st.error(f"Erro na etapa '{error_step}': {errors_msg}")

            # Show detailed diagnostics if Chrome failed
            if error_step == "chrome":
                diag = auto_res.get("diagnostics") or {}
                if diag:
                    with st.expander("Diagnostico do Chrome", expanded=True):
                        st.code(json.dumps(diag, indent=2, default=str))

                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("Tentar reconectar", key="retry_reconnect"):
                        from shopee_core.radar_cdp_service import is_cdp_available
                        if is_cdp_available():
                            st.success("Chome CDP ativo!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Chrome CDP ainda nao responde.")
                with col_b:
                    if st.button("Reiniciar Chrome do Radar", key="retry_restart"):
                        from shopee_core.radar_cdp_service import kill_managed_radar_chrome, ensure_radar_chrome_ready
                        kill_managed_radar_chrome()
                        st.info("Chrome antigo encerrado. Tentando abrir novo...")
                        time.sleep(2)
                        st.rerun()

    st.divider()
    # ── R7.4: Renovação do Radar ──────────────────────────────────
    st.write("##### 🔄 Renovação do Radar")

    def _run_refresh(uid: str, target_confidence: str = "medium"):
        p_info = st.empty()
        p_log = st.empty()

        def rf_progress(state_dict):
            stage = state_dict.get("stage", "")
            msg = state_dict.get("message", "")
            stage_map = {
                "chrome": "Verificando Chrome",
                "recheck": "Rechecando concorrentes",
                "classify": "Reclassificando",
                "report": "Gerando relatorio",
                "confidence": "Calculando confianca",
                "discover": "Buscando novos concorrentes",
            }
            display = stage_map.get(stage, stage)
            p_info.markdown(f"**Etapa:** {display}")
            p_log.text(msg)

        with st.spinner(f"Renovando Radar para {uid[:12]}..."):
            result = refresh_product(
                own_product_uid=uid,
                target_confidence=target_confidence,
                progress_callback=rf_progress,
            )

        if result.get("ok"):
            st.success("Renovação concluída!")
            st.json({
                "Rechecados": result.get("recheck", {}).get("checked", 0),
                "Atualizados": result.get("recheck", {}).get("updated", 0),
                "Indisponiveis": result.get("recheck", {}).get("unavailable", 0),
                "Direct before": result.get("direct_before"),
                "Direct after": result.get("direct_after"),
                "Confianca": result.get("confidence", {}).get("level", "N/A"),
                "Novos descobertos": result.get("discovered_new"),
            })
            from shopee_core.radar_patterns_service import get_latest_pattern_report
            fresh_report = get_latest_pattern_report(selected_uid)
            if fresh_report:
                st.session_state["last_pattern_report"] = fresh_report
        else:
            st.error(f"Falha na renovacao: {result.get('error', 'Erro desconhecido')}")

    st.caption("Mantem concorrentes, precos e relatorio atualizados.")

    refresh_status = get_refresh_status(selected_uid)
    rf_col1, rf_col2, rf_col3, rf_col4 = st.columns(4)
    with rf_col1:
        st.metric("Status", refresh_status.get("status", "N/A").replace("_", " ").title())
    with rf_col2:
        sd = refresh_status.get("days_since_refresh")
        st.metric("Dias desde ultima", f"{sd}" if sd is not None else "N/A")
    with rf_col3:
        st.metric("Confianca", (refresh_status.get("last_confidence_level") or "N/A").upper())
    with rf_col4:
        is_due = refresh_status.get("is_due", True)
        st.metric("Vencido", "Sim" if is_due else "Nao")

    if refresh_status.get("warnings"):
        st.caption("; ".join(refresh_status["warnings"]))

    # Due products alert
    due_products = list_due_for_refresh()
    if due_products and len(due_products) > 0:
        st.info(f":bell: Existem {len(due_products)} produto(s) com Radar vencido.")  # noqa: F541

    refresh_col1, refresh_col2, refresh_col3 = st.columns(3)
    with refresh_col1:
        if st.button("Renovar agora", use_container_width=True, type="primary", key="btn_refresh_now"):
            _run_refresh(selected_uid)
    with refresh_col2:
        if st.button("Renovar vencidos", use_container_width=True, key="btn_refresh_due"):
            for dp in due_products:
                _run_refresh(dp["product_uid"])
            st.rerun()
    with refresh_col3:
        if st.button("Forçar renovacao completa", use_container_width=True, key="btn_refresh_force"):
            _run_refresh(selected_uid, target_confidence="high")

    st.divider()
    st.write("##### Tabela de Concorrentes Vinculados")
    
    table_data = get_competitor_table_for_product(selected_uid)
    if not table_data:
        st.info("Nenhum concorrente vinculado a este produto ainda.")
    else:
        # Traduz os status de inglês (do backend) para português (da UI) de forma transparente
        STATUS_TRANSLATIONS = {
            "pending": "coleta_pendente",
            "failed": "falha_coleta",
            "collected": "aguardando_classificacao",
            "competitor_direct": "competitor_direct",
            "competitor_partial": "competitor_partial",
            "rejected": "rejected"
        }
        for r in table_data:
            r["status"] = STATUS_TRANSLATIONS.get(r["status"], r["status"])

        import pandas as pd
        show_cols = ["status", "relevance_score", "title", "price", "marketplace", "shop_name", "canonical_url", "product_uid"]

        classified_rows = [r for r in table_data if r["status"] in ["competitor_direct", "competitor_partial", "rejected"]]
        pending_rows = [r for r in table_data if r["status"] == "coleta_pendente"]
        other_rows = [r for r in table_data if r["status"] in ["aguardando_classificacao", "falha_coleta"]]

        tab_classified, tab_pending, tab_other = st.tabs([
            "Classificados",
            f"Fila pendente de coleta ({len(pending_rows)})",
            f"Outros ({len(other_rows)})",
        ])

        def _render_rows(rows, empty_msg):
            if rows:
                df = pd.DataFrame(rows)
                exist_cols = [c for c in show_cols if c in df.columns]
                st.dataframe(df[exist_cols], hide_index=True)
            else:
                st.info(empty_msg)

        with tab_classified:
            _render_rows(classified_rows, "Nenhum concorrente classificado ainda.")
        with tab_pending:
            _render_rows(pending_rows, "Nenhum candidato pendente de coleta.")
        with tab_other:
            _render_rows(other_rows, "Nenhum item aguardando classificacao ou com falha.")

def render_espelho_loja():

    from shopee_core.radar_store_ui_service import (
        get_db_diagnostic, list_store_mirrors, format_store_label,
        get_store_mirror_summary, list_store_mirror_products
    )
    import pandas as pd
    
    st.markdown("""
    <div class="page-header">
        <div class="page-header-icon">🏪</div>
        <div>
            <div class="page-header-title">Espelho da Loja</div>
            <div class="page-header-sub">Produtos próprios salvos localmente no Radar. Use este espelho como fallback quando a Shopee bloquear ou falhar.</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    diag = get_db_diagnostic()
    
    st.markdown("### 📊 Diagnóstico do Banco")
    with st.expander("Ver detalhes do radar.db", expanded=False):
        st.write(f"**Caminho Absoluto:** `{diag['db_path']}`")
        st.write(f"**Existe:** {'✅ Sim' if diag['db_exists'] else '❌ Não'}")
        if diag['db_exists']:
            st.write(f"**Tamanho:** {diag['db_size_bytes'] / 1024:.2f} KB")
            st.write(f"**Lojas (`radar_stores`):** {diag['total_stores']}")
            st.write(f"**Produtos (`radar_store_products`):** {diag['total_store_products']}")
            st.write(f"**Próprios (`radar_products`):** {diag['total_own_products']}")

    st.markdown("---")
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🔄 Recarregar espelho", use_container_width=True):
            st.rerun()
    with col_btn2:
        if st.button("🧪 Ativar instrução de fallback", use_container_width=True):
            st.info('Para forçar fallback temporariamente:\n\n`$env:SHOPEE_FORCE_RADAR_STORE_FALLBACK="true"`\n\n`streamlit run app.py`')

    st.markdown("---")
    
    stores = list_store_mirrors()
    if not stores:
        st.info("Nenhuma loja salva no espelho.")
        return

    # Selectbox de loja
    store_options = {s["store_uid"]: format_store_label(s) for s in stores}
    selected_store_uid = st.selectbox(
        "Selecione uma Loja",
        options=list(store_options.keys()),
        format_func=lambda x: store_options[x]
    )

    if not selected_store_uid:
        return

    summary = get_store_mirror_summary(selected_store_uid)
    if not summary.get("ok"):
        st.error("Erro ao carregar detalhes da loja.")
        return

    if summary.get("is_outdated"):
        st.warning("⚠️ **Espelho pode estar desatualizado** (Mais de 7 dias desde o último snapshot). Considere fazer uma nova auditoria normal sem fallback forçado.")
    else:
        st.success("✅ Espelho recente (menos de 7 dias).")

    st.markdown("### 📈 Métricas da Loja")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Produtos", summary.get("total_products", 0))
    c2.metric("Ativos", summary.get("active", 0))
    c3.metric("Alterados", summary.get("changed", 0))
    c4.metric("Ausentes/Removidos", summary.get("missing", 0) + summary.get("removed", 0))
    
    st.markdown("---")
    st.markdown("### 📦 Produtos do Espelho")
    
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        status_filter = st.selectbox("Status", ["Todos", "active", "changed", "missing", "removed", "unknown"])
    with col_f2:
        text_filter = st.text_input("Buscar no título")

    products = list_store_mirror_products(
        selected_store_uid, 
        status_filter=status_filter if status_filter != "Todos" else None
    )

    if text_filter:
        products = [p for p in products if text_filter.lower() in (p.get("title") or "").lower()]

    if not products:
        st.info("Nenhum produto encontrado para este filtro.")
    else:
        df_data = []
        for p in products:
            df_data.append({
                "Status": p.get("cache_status"),
                "Título": p.get("title"),
                "Preço": f"R$ {p.get('price', 0):.2f}",
                "Fonte/Origem": p.get("display_source"),
                "Marketplace ID": p.get("marketplace_product_id"),
                "Radar UID": p.get("radar_product_uid"),
                "Last Seen": str(p.get("last_seen_at", ""))[:16],
                "Last Changed": str(p.get("last_changed_at", ""))[:16],
            })
        st.dataframe(pd.DataFrame(df_data), use_container_width=True)

        st.markdown("### 🔎 Detalhe do Produto")
        product_options = {p["store_product_uid"]: f"[{p.get('cache_status')}] {p.get('title')}" for p in products}
        selected_prod_uid = st.selectbox(
            "Selecione um produto para inspecionar",
            options=list(product_options.keys()),
            format_func=lambda x: product_options[x]
        )

        if selected_prod_uid:
            prod = next((p for p in products if p["store_product_uid"] == selected_prod_uid), None)
            if prod:
                c_img, c_info = st.columns([1, 2])
                with c_img:
                    img_url = prod.get("image_url")
                    if img_url and str(img_url).startswith(("http://", "https://", "data:image")):
                        st.image(img_url, width="stretch")
                    else:
                        st.caption("Sem imagem válida")
                with c_info:
                    st.write(f"**Título:** {prod.get('title')}")
                    st.write(f"**Preço:** R$ {prod.get('price', 0):.2f}")
                    st.text_input("store_product_uid", prod.get("store_product_uid") or "", disabled=False)
                    st.text_input("radar_product_uid", prod.get("radar_product_uid") or "", disabled=False)
                    st.text_input("canonical_url", prod.get("canonical_url") or "", disabled=False)
                
                with st.expander("JSON Bruto (raw_json)"):
                    st.json(prod.get("raw_json_parsed", {}))

# ══════════════════════════════════════════════════════════════════════════
# ROTEAMENTO DE PARTIÇÕES
# ══════════════════════════════════════════════════════════════════════════
if st.session_state.nav_partition == "auditoria":
    render_auditoria()
elif st.session_state.nav_partition == "chatbot":
    render_chatbot()
elif st.session_state.nav_partition == "espelho_loja":
    render_espelho_loja()
elif st.session_state.nav_partition == "radar_workflow":
    render_radar_workflow()
else:
    render_sentinela()
