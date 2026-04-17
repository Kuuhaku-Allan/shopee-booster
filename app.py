"""
app.py — Orquestrador do Shopee Booster 2.0
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

from streamlit_drawable_canvas import st_canvas
import pandas as pd
import sys
import os
import io
import time

import nest_asyncio
from dotenv import load_dotenv

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
    page_title="Shopee Booster 2.0",
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
}

for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ══════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    # Brand
    st.markdown("""
    <div class="brand-logo">
        <div class="brand-logo-icon">🛍️</div>
        <div>
            <div class="brand-logo-text">Shopee Booster</div>
            <div class="brand-logo-sub">v2.0 · Suite Pro</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Navegação principal via radio estilizado
    st.markdown('<div class="nav-section-label">Partições</div>', unsafe_allow_html=True)

    nav = st.radio(
        "nav",
        options=["auditoria", "chatbot", "sentinela"],
        format_func=lambda x: (
            "🕵️  Auditoria Pro" if x == "auditoria"
            else "🤖  Chatbot Concierge" if x == "chatbot"
            else "📡  Sentinela"
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
            with st.spinner("Abrindo Shopee e interceptando dados... (30-60s)"):
                shop_raw = fetch_shop_info(username)

            d = shop_raw.get("data", shop_raw)
            if d:
                st.session_state.shop_data = d
                shopid = d.get("shopid") or d.get("shop_id")
                with st.spinner("Carregando catálogo de produtos..."):
                    st.session_state.shop_produtos = fetch_shop_products_intercept(username, shopid)
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

        if st.button("🤖 Gerar Otimização Completa", type="primary"):
            with st.spinner("IA analisando concorrentes + avaliações e gerando listing..."):
                st.session_state.optimization_result = generate_full_optimization(
                    prod, df_comp, reviews_opt or [], segmento
                )

        if st.session_state.optimization_result:
            st.markdown("---")
            st.markdown("### 📈 Listing Otimizado pela IA")
            st.markdown(st.session_state.optimization_result)
            salvar_ou_baixar(
                "Baixar otimização (.txt)",
                data=st.session_state.optimization_result,
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


def _render_canvas_area(full_context: str, segmento: str):
    """Renderiza a área do Canvas Interativo (ROI Visual)."""
    from backend_core import composite_layers, apply_region_edit_with_vision
    import io as _io
    import time as _time
    from PIL import Image, ImageDraw
    from streamlit_drawable_canvas import st_canvas
    
    with st.container(border=True):
        st.markdown('<p class="section-label">🎨 Direção Criativa</p>', unsafe_allow_html=True)
        
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
        if not composite:
            return

        # ── Barra de Ferramentas ROI ────────────────────────
        st.markdown("""
            <style>
            .canvas-toolbar { display: flex; gap: 8px; margin-bottom: 12px; }
            .tool-btn { 
                padding: 6px 12px; border-radius: 6px; border: 1px solid #444; 
                cursor: pointer; background: #262730; color: white;
                font-size: 13px; transition: 0.2s;
            }
            .tool-btn.active { background: #FF4B4B; border-color: #FF4B4B; }
            </style>
        """, unsafe_allow_html=True)

        col_t1, col_t2, col_t3, col_t4 = st.columns([1,1,1,1])
        
        def toggle_tool(tool_name):
            if st.session_state.canvas_tool == tool_name and st.session_state.canvas_mode == "draw":
                st.session_state.canvas_mode = "transform"
            else:
                st.session_state.canvas_tool = tool_name
                st.session_state.canvas_mode = "draw"

        with col_t1:
            if st.button("⬜ Retângulo", use_container_width=True, type="primary" if st.session_state.canvas_tool == "rect" and st.session_state.canvas_mode == "draw" else "secondary"):
                toggle_tool("rect")
                st.rerun()
        with col_t2:
            if st.button("⭕ Círculo", use_container_width=True, type="primary" if st.session_state.canvas_tool == "circle" and st.session_state.canvas_mode == "draw" else "secondary"):
                toggle_tool("circle")
                st.rerun()
        with col_t3:
            if st.button("✏️ Livre", use_container_width=True, type="primary" if st.session_state.canvas_tool == "freeline" and st.session_state.canvas_mode == "draw" else "secondary"):
                toggle_tool("freeline")
                st.rerun()
        with col_t4:
            if st.button("🔄 Reset", use_container_width=True):
                st.session_state.chat_canvas_roi = {"x": 25, "y": 25, "w": 50, "h": 50, "shape": "rect"}
                st.session_state.chat_canvas_freehand_mask = None
                st.session_state.canvas_mode = "transform"
                st.rerun()

        # ── Renderização do Canvas ──────────────────────────
        w, h = composite.size
        # Limita largura visual mantendo proporção
        display_width = 500 
        display_height = int(h * (display_width / w))

        drawing_mode = "transform"
        if st.session_state.canvas_mode == "draw":
            if st.session_state.canvas_tool == "rect": drawing_mode = "rect"
            elif st.session_state.canvas_tool == "circle": drawing_mode = "circle"
            elif st.session_state.canvas_tool == "freeline": drawing_mode = "freedraw"

        # Converte para RGBA para garantir compatibilidade com a URL do Streamlit
        canvas_bg = composite.convert("RGBA")

        canvas_result = st_canvas(
            fill_color="rgba(255, 75, 75, 0.3)",
            stroke_width=3,
            stroke_color="#FF4B4B",
            background_image=canvas_bg,
            update_streamlit=True,
            height=display_height,
            width=display_width,
            drawing_mode=drawing_mode,
            key="canvas_roi",
        )

        # Diagnóstico discreto (se precisar remover depois, só avisar)
        st.caption(f"📏 Resolução real: {w}x{h} | 🖥️ Canvas: {display_width}x{display_height}")

        # ── Processamento da Seleção ────────────────────────
        if canvas_result.json_data is not None:
            objects = canvas_result.json_data["objects"]
            if objects:
                obj = objects[-1] # Pega o último objeto desenhado
                
                # Coordenadas em %
                if obj["type"] in ["rect", "circle"]:
                    st.session_state.chat_canvas_roi = {
                        "x": (obj["left"] / display_width) * 100,
                        "y": (obj["top"] / display_height) * 100,
                        "w": (obj["width"] * obj["scaleX"] / display_width) * 100,
                        "h": (obj["height"] * obj["scaleY"] / display_height) * 100,
                        "shape": "rect" if obj["type"] == "rect" else "circle"
                    }
                    st.session_state.chat_canvas_freehand_mask = None
                elif obj["type"] == "path":
                    # Para freehand, precisamos da imagem do canvas (mask)
                        # O streamlit-drawable-canvas retorna image_data como array numpy RGBA
                    if canvas_result.image_data is not None:
                        # Extrai bbox dos pixels não-transparentes
                        import numpy as np
                        mask_arr = canvas_result.image_data[:, :, 3] # Alpha channel
                        coords = np.argwhere(mask_arr > 0)
                        if coords.size > 0:
                            y_min, x_min = coords.min(axis=0)
                            y_max, x_max = coords.max(axis=0)
                            
                            st.session_state.chat_canvas_roi = {
                                "x": (x_min / display_width) * 100,
                                "y": (y_min / display_height) * 100,
                                "w": ((x_max - x_min) / display_width) * 100,
                                "h": ((y_max - y_min) / display_height) * 100,
                                "shape": "freehand"
                            }
                            # Salva a máscara recortada pela bbox (binária)
                            full_mask = Image.fromarray(mask_arr).convert("L")
                            crop_box = (x_min, y_min, x_max, y_max)
                            st.session_state.chat_canvas_freehand_mask = full_mask.crop(crop_box)

        # ── Ações ──────────────────────────────────────────
        c1, c2 = st.columns(2)
        if c1.button("📥 Usar no Chat", use_container_width=True):
            buf = _io.BytesIO()
            composite.convert("RGB").save(buf, format="JPEG", quality=92)
            st.session_state.chat_active_edit_image = composite
            st.session_state.chat_attachments = [buf.getvalue()]
            st.session_state.chat_attachment_types = ["image"]
            st.session_state.chat_attachment_previews = [composite.convert("RGB")]
            st.session_state.show_attach_panel = True
            st.success("✅ Composição enviada!")
            _time.sleep(0.5)
            st.rerun()
        
        if c2.button("📌 Fixar como Base", use_container_width=True):
            st.session_state.chat_canvas_layers = [{
                "name": "Base Mesclada",
                "img": composite,
                "visible": True,
                "type": "base"
            }]
            st.session_state.chat_active_edit_image = composite
            st.rerun()

        # ── Gerenciador de Camadas (Compacto) ───────────────
        st.markdown("---")
        with st.expander("📂 Camadas", expanded=False):
            for i, layer in enumerate(reversed(layers)):
                idx = len(layers) - 1 - i
                col_vis, col_name, col_del = st.columns([1, 4, 1])
                with col_vis:
                    vis = st.checkbox("", value=layer["visible"], key=f"vis_{idx}_{len(layers)}")
                    if vis != layer["visible"]:
                        st.session_state.chat_canvas_layers[idx]["visible"] = vis
                        st.rerun()
                with col_name:
                    st.markdown(f"<span style='font-size:12px'>{layer['name']}</span>", unsafe_allow_html=True)
                with col_del:
                    if layer["type"] != "base" and st.button("🗑️", key=f"del_lay_{idx}"):
                        st.session_state.chat_canvas_layers.pop(idx)
                        st.rerun()
        
        # ── Aplicação ROI ──────────────────────────────────
        st.markdown("---")
        instrucao = st.text_input("Comando para área selecionada:", placeholder="Ex: mude a cor para azul...")
        if st.button("✨ Aplicar na Região", type="primary", use_container_width=True):
            if instrucao and composite:
                with st.spinner("IA processando região..."):
                    # Passa a máscara se for freehand
                    mask = st.session_state.chat_canvas_freehand_mask
                    roi = st.session_state.chat_canvas_roi
                    
                    new_layer_img, desc = apply_region_edit_with_vision(
                        composite, roi, instrucao, full_context, segmento,
                        freehand_mask=mask
                    )
                    st.session_state.chat_canvas_layers.append({
                        "name": f"Edição: {instrucao[:15]}",
                        "img": new_layer_img,
                        "visible": True,
                        "type": "edit"
                    })
                    st.success(f"✅ {desc}")
                    _time.sleep(1)
                    st.rerun()
        
        # ── Exportação ──────────────────────────────────────
        st.markdown("---")
        if composite:
            buf = _io.BytesIO()
            composite.convert("RGB").save(buf, format="JPEG", quality=95)
            salvar_ou_baixar(
                "💾 Exportar Imagem Final",
                data=buf.getvalue(),
                file_name="composicao_final.jpg",
                mime="image/jpeg",
                key="btn_export_canvas"
            )


def render_chatbot():
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
        # Essas operações devem substituir a base do canvas para evitar achatamento e desalinhamento
        GLOBAL_INTENTS = {"generate_scene", "recolor", "remove_bg", "generate_variants", "upscale"}
        current_intent = result.get("intent")
        
        # Se for a primeira imagem OU uma operação global/final
        if not st.session_state.get("chat_canvas_layers") or current_intent in GLOBAL_INTENTS:
            # Substitui tudo pela nova base (preserva proporção visual)
            st.session_state.chat_canvas_layers = [{
                "name": f"Base: {result.get('captions', [''])[0]}",
                "img": result["images"][0],
                "visible": True,
                "type": "base"
            }]
            # Se houver variantes, adiciona como desativadas
            if len(result["images"]) > 1:
                for idx_var, var_img in enumerate(result["images"][1:]):
                    st.session_state.chat_canvas_layers.append({
                        "name": f"Variante {idx_var+1}",
                        "img": var_img,
                        "visible": False,
                        "type": "edit"
                    })
        else:
            # Operação aditiva (badge, texto, ROI local)
            for idx_res, res_img in enumerate(result["images"]):
                st.session_state.chat_canvas_layers.append({
                    "name": f"Chat T{len(st.session_state.chat_history)}: {result.get('captions', [''])[idx_res]}",
                    "img": res_img,
                    "visible": True,
                    "type": "edit"
                })

    # ── Salva última imagem processada como "em edição" ───────
    if result.get("images"):
        st.session_state.chat_active_edit_image = result["images"][-1]
        st.session_state.chat_active_edit_label = "última processada"

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
                st.line_chart(df_trend.set_index("dia")["preco_medio"], width="stretch")
            except Exception:
                st.warning("Não foi possível renderizar o gráfico nesta build. Exibindo tabela de tendência.")
                st.dataframe(df_trend, width="stretch", hide_index=True)

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
            st.dataframe(df_display, width="stretch", hide_index=True)

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
# ROTEAMENTO DE PARTIÇÕES
# ══════════════════════════════════════════════════════════════════════════
if st.session_state.nav_partition == "auditoria":
    render_auditoria()
elif st.session_state.nav_partition == "chatbot":
    render_chatbot()
else:
    render_sentinela()