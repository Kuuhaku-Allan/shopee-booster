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
def render_chatbot():
    # ── Cabeçalho ─────────────────────────────────────────────
    st.markdown("""
    <div class="page-header">
        <div class="page-header-icon">🤖</div>
        <div>
            <div class="page-header-title">Chatbot Concierge</div>
            <div class="page-header-sub">Assistente virtual inteligente treinado com o catálogo da sua loja</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if not st.session_state.shop_data or not st.session_state.shop_produtos:
        st.info("👈 Carregue uma loja primeiro na partição **Auditoria Pro** (menu lateral).")
        st.markdown("""
        <div style="text-align:center; padding:3rem; opacity:0.4;">
            <div style="font-size:64px;">🏪</div>
            <div style="font-size:14px; margin-top:0.5rem;">Nenhuma loja conectada</div>
        </div>
        """, unsafe_allow_html=True)
        return

    shop_name = st.session_state.shop_data.get("name", "Loja")
    produtos = st.session_state.shop_produtos
    catalog_context = build_catalog_context(produtos, shop_name)

    if not st.session_state.chatbot_active:
        # ── Tela de boas-vindas do chatbot ────────────────────
        col_l, col_r = st.columns([3, 2])

        with col_l:
            st.markdown(f"### 🤖 Chatbot da loja **{shop_name}**")
            st.markdown(f"O assistente vai conhecer todos os **{len(produtos)} produtos** e responder clientes em tempo real com linguagem natural.")

            c1, c2 = st.columns(2)
            with c1:
                st.success(f"✅ {len(produtos)} produtos carregados")
            with c2:
                st.info("💬 Multi-turn · Recomendações · FAQs")

            st.markdown("---")

            if st.button("🚀 Ativar Chatbot", type="primary", width='stretch'):
                st.session_state.chatbot_active = True
                st.session_state.chat_history = []
                st.rerun()

        with col_r:
            # ── Gerador de FAQ ─────────────────────────────────
            st.markdown('<p class="section-label">Gerar FAQ para Seller Centre</p>', unsafe_allow_html=True)

            if st.button("📋 Gerar FAQ Automático", type="secondary", width='stretch', key="btn_gerar_faq"):
                with st.spinner("Gerando FAQ com IA..."):
                    faq_prompt = f"""Você é especialista em e-commerce Shopee Brasil.

Com base neste catálogo da loja '{shop_name}':
{chr(10).join(f"- {p['name']} | R$ {p['price']:.2f}" for p in produtos)}

Gere EXATAMENTE 9 perguntas divididas em 3 categorias, com 3 perguntas cada.
Categorias: "📦 Produtos e Modelos", "🚚 Entrega e Frete", "🔄 Trocas e Pagamento"
Regras OBRIGATÓRIAS:
- Cada pergunta: máximo 80 caracteres
- Cada resposta: máximo 500 caracteres
- Respostas curtas, simpáticas, em português brasileiro
- As perguntas devem ser GENÉRICAS, sem citar nomes específicos de produtos

Formato EXATO:

CATEGORIA 1: 📦 Produtos e Modelos
PERGUNTA 1: [pergunta]
RESPOSTA 1: [resposta]
PERGUNTA 2: [pergunta]
RESPOSTA 2: [resposta]
PERGUNTA 3: [pergunta]
RESPOSTA 3: [resposta]

CATEGORIA 2: 🚚 Entrega e Frete
PERGUNTA 4: [pergunta]
RESPOSTA 4: [resposta]
PERGUNTA 5: [pergunta]
RESPOSTA 5: [resposta]
PERGUNTA 6: [pergunta]
RESPOSTA 6: [resposta]

CATEGORIA 3: 🔄 Trocas e Pagamento
PERGUNTA 7: [pergunta]
RESPOSTA 7: [resposta]
PERGUNTA 8: [pergunta]
RESPOSTA 8: [resposta]
PERGUNTA 9: [pergunta]
RESPOSTA 9: [resposta]"""

                    from backend_core import MODELOS_TEXTO, client
                    faq_result = ""
                    for m in MODELOS_TEXTO:
                        try:
                            from backend_core import client as bc_client
                            config = {"thinking_config": {"thinking_budget": 0}} if "3.1" in m or "2.5" in m else {}
                            response = bc_client().models.generate_content(
                                model=m,
                                contents=[faq_prompt],
                                config=config if config else None
                            )
                            faq_result = response.text.strip()
                            break
                        except Exception:
                            import time; time.sleep(2)
                            continue

                    if faq_result:
                        st.session_state["faq_ia_geral"] = faq_result
                    else:
                        st.error("❌ Não foi possível gerar o FAQ. Tente novamente.")

            if st.session_state.get("faq_ia_geral"):
                faq_result = st.session_state["faq_ia_geral"]
                avisos = []
                for linha in faq_result.split("\n"):
                    if linha.startswith("PERGUNTA") and ":" in linha:
                        texto = linha.split(":", 1)[1].strip()
                        if len(texto) > 80:
                            avisos.append(f"⚠️ Pergunta longa ({len(texto)} chars): '{texto[:50]}...'")
                    elif linha.startswith("RESPOSTA") and ":" in linha:
                        texto = linha.split(":", 1)[1].strip()
                        if len(texto) > 500:
                            avisos.append(f"⚠️ Resposta longa ({len(texto)} chars): '{texto[:50]}...'")

                st.markdown("---")
                st.markdown("### 📋 FAQ Gerado")

                if avisos:
                    with st.expander("⚠️ Avisos de limite"):
                        for a in avisos:
                            st.warning(a)

                st.info("📌 **Como usar:** Seller Centre → Atendimento → Assistente de IA → Adicionar Categoria")
                st.success("💡 Use 'Otimização Completa' para melhorar as descrições — o Assistente nativo da Shopee aprende automaticamente.")

                categorias = faq_result.split("\n\n")
                for bloco in categorias:
                    if bloco.strip():
                        st.code(bloco.strip(), language=None)

                faq_clean = faq_result.replace("**", "")
                salvar_ou_baixar(
                    "Baixar FAQ completo (.txt)",
                    data=faq_clean,
                    file_name=f"faq_{shop_name}.txt",
                    mime="text/plain",
                    key="dl_faq"
                )

    else:
        # ── Interface de Chat ──────────────────────────────────
        col_titulo, col_reset = st.columns([4, 1])
        with col_titulo:
            st.markdown(f"### 💬 {shop_name} — Assistente Virtual")
        with col_reset:
            if st.button("🔄 Reiniciar", key="btn_reset_chat"):
                st.session_state.chat_history = []
                st.session_state.chatbot_active = False
                st.rerun()

        # Construtor de FAQ personalizado
        with st.expander("📋 Construtor de FAQ Personalizado"):
            st.markdown("Use o chat para montar seu FAQ. Quando terminar, exporte abaixo.")

            if st.session_state.faq_personalizado:
                st.markdown("**FAQ atual:**")
                for i, item in enumerate(st.session_state.faq_personalizado):
                    col_faq, col_del = st.columns([10, 1])
                    with col_faq:
                        st.markdown(f"**P{i+1}:** {item['pergunta']}")
                        st.markdown(f"**R{i+1}:** {item['resposta']}")
                        st.divider()
                    with col_del:
                        if st.button("🗑️", key=f"del_faq_{i}"):
                            st.session_state.faq_personalizado.pop(i)
                            st.rerun()

            st.markdown("**Adicionar pergunta:**")
            col_p, col_r = st.columns(2)
            with col_p:
                nova_pergunta = st.text_input(
                    "Pergunta",
                    placeholder="Ex: Vocês têm mochila azul?",
                    key="nova_pergunta", max_chars=80
                )
            with col_r:
                nova_resposta = st.text_area(
                    "Resposta",
                    placeholder="Ex: Sim! Temos modelos em azul disponíveis.",
                    key="nova_resposta", max_chars=500, height=80
                )

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("➕ Adicionar par", key="btn_add_faq") and nova_pergunta and nova_resposta:
                    st.session_state.faq_personalizado.append({"pergunta": nova_pergunta, "resposta": nova_resposta})
                    st.rerun()
            with col_btn2:
                if st.button("🤖 Sugerir resposta com IA", key="btn_sugerir_ia") and nova_pergunta:
                    with st.spinner("Gerando resposta..."):
                        sugestao = chat_with_gemini(
                            f"Gere uma resposta curta e simpática (máx 500 chars) para: '{nova_pergunta}'",
                            [], catalog_context
                        )
                    st.session_state.faq_personalizado.append({"pergunta": nova_pergunta, "resposta": sugestao[:500]})
                    st.rerun()

            if st.session_state.faq_personalizado:
                n = len(st.session_state.faq_personalizado)
                faq_txt = "\n\n".join([
                    f"PERGUNTA {i+1}: {item['pergunta']}\nRESPOSTA {i+1}: {item['resposta']}"
                    for i, item in enumerate(st.session_state.faq_personalizado)
                ])
                faq_txt = faq_txt.replace("**", "")
                salvar_ou_baixar(
                    f"Exportar FAQ ({n} pares)",
                    data=faq_txt,
                    file_name=f"faq_personalizado_{shop_name}.txt",
                    mime="text/plain",
                    key="dl_faq_perso"
                )
                if st.button("🗑️ Limpar FAQ", key="btn_limpar_faq"):
                    st.session_state.faq_personalizado = []
                    st.rerun()

        # Exibir histórico de chat
        for turn in st.session_state.chat_history:
            with st.chat_message("user"):
                st.write(turn["user"])
            with st.chat_message("assistant"):
                st.write(turn["assistant"])

        # Sugestões iniciais
        if not st.session_state.chat_history:
            st.markdown('<p class="section-label">Sugestões para começar</p>', unsafe_allow_html=True)
            sugestoes = [
                "Quais mochilas vocês têm disponíveis?",
                "Tem mochila rosa ou lilás?",
                "Qual mochila é ideal para escola?",
                "Qual o produto mais barato?",
            ]
            cols_s = st.columns(2)
            for idx, sug in enumerate(sugestoes):
                with cols_s[idx % 2]:
                    if st.button(sug, key=f"sug_{idx}"):
                        with st.spinner("Respondendo..."):
                            resposta = chat_with_gemini(sug, st.session_state.chat_history, catalog_context)
                        st.session_state.chat_history.append({"user": sug, "assistant": resposta})
                        st.rerun()

        # Input do usuário
        user_input = st.chat_input("Digite sua pergunta sobre os produtos...")
        if user_input:
            with st.spinner("Respondendo..."):
                resposta = chat_with_gemini(user_input, st.session_state.chat_history, catalog_context)
            st.session_state.chat_history.append({"user": user_input, "assistant": resposta})
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════
# ROTEAMENTO DE PARTIÇÕES
# ══════════════════════════════════════════════════════════════════════════
if st.session_state.nav_partition == "auditoria":
    render_auditoria()
else:
    render_chatbot()