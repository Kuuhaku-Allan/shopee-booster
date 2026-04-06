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
        options=["auditoria", "chatbot"],
        format_func=lambda x: (
            "🕵️  Auditoria Pro" if x == "auditoria"
            else "🤖  Chatbot Concierge"
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

        # ── Sub-seção: Vídeo (Módulo Beta) ────────────────────
        st.markdown("---")
        st.markdown("""
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:1rem;">
            <span class="section-label" style="margin:0;">Análise de Vídeo</span>
            <span class="badge badge-beta">BETA</span>
        </div>
        """, unsafe_allow_html=True)

        video_file = st.file_uploader(
            "Upload do vídeo do produto (MP4)",
            type=["mp4"],
            key="video_uploader"
        )

        if video_file:
            if st.button("🎬 Analisar Retenção do Vídeo", key="btn_analisar_video"):
                with st.spinner("IA analisando hook e iluminação..."):
                    st.info("🔧 **Módulo em desenvolvimento.** Em breve: análise automática de hook, ritmo de edição e qualidade de iluminação via Gemini Vision.")
                    st.warning("⚠️ Insight preliminar: mostre o produto em uso nos primeiros 3 segundos para maximizar a retenção.")


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
            if prod.get("image"):
                st.image(prod["image"], use_container_width=True)
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
                    st.session_state.chatbot_active           = True
                    st.session_state.chat_history             = []
                    st.session_state.chat_attachments         = []
                    st.session_state.chat_attachment_types    = []
                    st.session_state.chat_attachment_previews = []
                    st.session_state.chat_preview_images      = []
                    st.session_state.chat_preview_captions    = []
                    st.rerun()
            with col_b:
                if st.button("📋 Gerar FAQ para Seller Centre", width='stretch', key="btn_gerar_faq_welcome"):
                    _gerar_faq(full_context, shop_name_ctx)

        _render_faq_output(shop_name_ctx)
        return

    # ══════════════════════════════════════════════════════════
    # CHAT ATIVO — Layout: painel esquerdo (chat) + direito (preview)
    # ══════════════════════════════════════════════════════════
    col_chat, col_preview = st.columns([2, 1])

    # ── PAINEL DIREITO: Preview de imagens processadas ────────
    with col_preview:
        with st.container(border=True):
            col_title, col_reset = st.columns([3, 1])
            with col_title:
                st.markdown(
                    '<p class="section-label" style="margin:0">🖼️ Preview</p>',
                    unsafe_allow_html=True,
                )
            with col_reset:
                if st.button("✕", key="btn_clear_preview", help="Limpar preview"):
                    st.session_state.chat_preview_images  = []
                    st.session_state.chat_preview_captions = []
                    st.rerun()

            preview_imgs = st.session_state.get("chat_preview_images", [])
            if preview_imgs:
                for i, pimg in enumerate(reversed(preview_imgs[-4:])):  # até 4 últimas
                    cap = ""
                    caps = st.session_state.get("chat_preview_captions", [])
                    if caps:
                        idx_rev = len(preview_imgs) - 1 - i
                        cap = caps[idx_rev] if idx_rev < len(caps) else ""

                    st.image(pimg, caption=cap, width='stretch')

                    # Botão de download para cada imagem
                    buf_dl = io.BytesIO()
                    if hasattr(pimg, "mode"):
                        save_img = pimg.convert("RGB") if pimg.mode == "RGBA" else pimg
                        save_img.save(buf_dl, format="JPEG", quality=95)
                    salvar_ou_baixar(
                        "Baixar",
                        data=buf_dl.getvalue(),
                        file_name=f"resultado_{i+1}.jpg",
                        mime="image/jpeg",
                        key=f"dl_preview_{i}_{len(preview_imgs)}",
                    )

                    if i < len(preview_imgs) - 1:
                        st.markdown("---")
            else:
                st.markdown(
                    "<div style='text-align:center;padding:2rem 0;opacity:0.35;font-size:13px'>"
                    "📷<br>Imagens processadas<br>aparecerão aqui</div>",
                    unsafe_allow_html=True,
                )

            # ── Contexto ativo compacto ────────────────────
            if has_prod:
                st.markdown("---")
                prod = st.session_state.selected_product
                img_url = (prod["image"] if prod["image"].startswith("http")
                           else f"https://down-br.img.susercontent.com/file/{prod['image']}")
                st.image(img_url, caption=f"⚡ {prod['name'][:28]}", width='stretch')

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
                for turn in st.session_state.chat_history:
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
                            ri_cols = st.columns(min(len(turn["result_images"]), 2))
                            for ri, rimg in enumerate(turn["result_images"]):
                                with ri_cols[ri]:
                                    rcap = ""
                                    if turn.get("result_captions") and ri < len(turn["result_captions"]):
                                        rcap = turn["result_captions"][ri]
                                    st.image(rimg, caption=rcap, width=350)

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

        # ── Área de anexo (toggle "+") ────────────────────────
        _render_attachment_area()

        # ── Campo de texto + enviar ───────────────────────────
        user_input = st.chat_input("Mensagem, pergunta ou comando de imagem...")
        if user_input:
            attachments  = st.session_state.get("chat_attachments",         [])
            att_types    = st.session_state.get("chat_attachment_types",    [])
            att_previews = st.session_state.get("chat_attachment_previews", [])
            _handle_chat_input_with_vision(user_input, attachments, att_types, att_previews, full_context, segmento)

    # ── FAQ em expander abaixo do layout ─────────────────────
    _render_faq_output(shop_name_ctx)


# ══════════════════════════════════════════════════════════════
# FUNÇÕES AUXILIARES DO CHATBOT
# ══════════════════════════════════════════════════════════════

def _render_attachment_area():
    """Renderiza o painel de anexo com botão + e uploader toggleável."""
    is_open = st.session_state.get("show_attach_panel", False)
    label   = "📎 Fechar anexos" if is_open else "📎 Anexar imagem / vídeo"

    if st.button(label, key="btn_toggle_attach", width='stretch'):
        st.session_state.show_attach_panel = not is_open
        if not st.session_state.show_attach_panel:
            # Fecha o painel E limpa os anexos pendentes
            st.session_state.chat_attachments         = []
            st.session_state.chat_attachment_types    = []
            st.session_state.chat_attachment_previews = []
        st.rerun()

    if st.session_state.get("show_attach_panel"):
        with st.container(border=True):
            st.markdown(
                '<p class="section-label" style="margin:0 0 0.5rem 0">Arquivos anexados</p>',
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
                        pimg = Image.open(io.BytesIO(raw)).convert("RGB")
                        att_previews.append(pimg)
                    else:
                        att_previews.append(None)

                st.session_state.chat_attachments         = attachments
                st.session_state.chat_attachment_types    = att_types
                st.session_state.chat_attachment_previews = [p for p in att_previews if p is not None]

                # Preview dos arquivos selecionados
                if att_previews:
                    prev_cols = st.columns(min(len([p for p in att_previews if p]), 4))
                    pi = 0
                    for fi, fp in enumerate(att_previews):
                        if fp is not None:
                            with prev_cols[pi % len(prev_cols)]:
                                st.image(fp, width='stretch',
                                         caption=f"{'🎬' if att_types[fi]=='video' else '🖼️'} {uploaded[fi].name[:20]}")
                            pi += 1

                st.success(f"✅ {len(uploaded)} arquivo(s) prontos para envio — escreva sua mensagem acima.")


def _send_message(
    user_message: str,
    attachments:  list,
    att_types:    list,
    att_previews: list,
    full_context: str,
    segmento:     str,
):
    """Processa e registra um turno de chat."""
    # Converte bytes → PIL para processamento
    pil_images = []
    for i, att in enumerate(attachments):
        if att_types[i] == "image" and isinstance(att, bytes):
            pil_images.append(Image.open(io.BytesIO(att)).convert("RGBA"))
        else:
            pil_images.append(att)  # bytes de vídeo ficam como bytes

    with st.spinner("Processando..."):
        result = process_chat_turn(
            user_message     = user_message,
            attachments      = pil_images,
            attachment_types = att_types,
            chat_history     = st.session_state.chat_history,
            full_context     = full_context,
            segmento         = segmento,
            # Contexto estruturado da Auditoria — permite otimização direta pelo chat
            selected_product     = st.session_state.get("selected_product"),
            df_competitors       = st.session_state.get("df_competitors"),
            optimization_reviews = st.session_state.get("optimization_reviews"),
        )

    # Registra no histórico
    turn_entry = {
        "user":               user_message,
        "assistant":          result["text"],
        "attachment_previews": list(att_previews),
        "result_images":      list(result["images"]),
        "result_captions":    list(result["captions"]),
    }
    st.session_state.chat_history.append(turn_entry)

    # Empurra imagens para o painel de preview
    if result["images"]:
        st.session_state.chat_preview_images  = (
            st.session_state.get("chat_preview_images", []) + result["images"]
        )[-8:]  # Mantém apenas as 8 últimas para não pesar a sessão
        st.session_state.chat_preview_captions = (
            st.session_state.get("chat_preview_captions", []) + result["captions"]
        )[-8:]

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
# ROTEAMENTO DE PARTIÇÕES
# ══════════════════════════════════════════════════════════════════════════
if st.session_state.nav_partition == "auditoria":
    render_auditoria()
else:
    render_chatbot()