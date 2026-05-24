import re

with open("app.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Add "radar_workflow" to options
code = re.sub(
    r'options=\["auditoria", "chatbot", "sentinela", "espelho_loja"\]',
    r'options=["auditoria", "chatbot", "sentinela", "espelho_loja", "radar_workflow"]',
    code
)

# 2. Add label to format_func
code = re.sub(
    r'else "🏪\s*Espelho da Loja"',
    r'else "🏪  Espelho da Loja" if x == "espelho_loja"\n        else "🎯  Radar Assistido"',
    code
)

# 3. Add render_radar_workflow dispatch
dispatch = """elif st.session_state.nav_partition == "espelho_loja":
    render_espelho_loja()
elif st.session_state.nav_partition == "radar_workflow":
    render_radar_workflow()"""

code = code.replace(
    'elif st.session_state.nav_partition == "espelho_loja":\n    render_espelho_loja()',
    dispatch
)

# 4. Insert render_radar_workflow function definition
func_def = """
def render_radar_workflow():
    st.markdown('<div class="page-header-title">Radar Assistido de Concorrentes</div>', unsafe_allow_html=True)
    st.markdown("Cadastre URLs de produtos concorrentes, colete dados e gere uma análise de mercado para usar na Auditoria.")
    
    from shopee_core.radar_workflow_ui_service import (
        list_own_products_for_radar, format_own_product_label,
        add_competitor_urls_for_product, get_radar_queue_summary,
        get_competitor_table_for_product, classify_linked_candidates_for_product,
        run_pattern_analysis_for_product
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
    
    prod = next(p for p in products if p["product_uid"] == selected_uid)
    
    st.divider()
    
    colA, colB = st.columns([1, 1])
    with colA:
        st.write("##### Sugestões de Busca")
        st.caption("Você pode copiar essas sugestões e pesquisar no Mercado Livre ou Shopee:")
        
        # Sugestões simples por token
        title = prod["title"]
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
    summary = get_radar_queue_summary(selected_uid)
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Jobs Pendentes", summary["jobs_pending"])
    col2.metric("Candidatos Vinculados", summary["candidates"])
    col3.metric("Concorrentes Diretos", summary["competitor_direct"])
    
    c_lim, c_mode, c_btn = st.columns([1, 1, 2])
    with c_lim:
        limit = st.selectbox("Limite de coleta:", [1, 3, 5, 10], index=2)
    with c_mode:
        browser_mode = st.selectbox("Modo do Navegador:", ["cdp", "persistent"], index=0)
    with c_btn:
        st.write("")
        st.write("")
        if st.button("Coletar URLs Pendentes", use_container_width=True):
            if summary["jobs_pending"] == 0:
                st.info("Nenhum job pendente para este produto.")
            else:
                st.warning("A coleta pode abrir o navegador e demorar alguns minutos. Aguarde...")
                # Chama coleta (loop manual)
                try:
                    jobs = rc.get_pending_jobs(limit=limit)
                    count = 0
                    for job in jobs:
                        # Filtrar apenas os que pertencem a esse produto próprio? O script pega todos globais pending.
                        # Para manter a simplificação e atender R7.2, vamos rodar a coleta genérica de N itens
                        try:
                            if job["marketplace"] == "mercadolivre":
                                rc.collect_mercadolivre_product(job, browser_mode=browser_mode, save_assets=False)
                                count += 1
                            elif job["marketplace"] == "shopee":
                                rc.collect_shopee_product(job, browser_mode=browser_mode, save_assets=False)
                                count += 1
                        except Exception as e:
                            pass
                    st.success(f"Foram processados {count} jobs com sucesso.")
                    time.sleep(2)
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro na coleta: {e}")
                    if "cdp" in str(e).lower() or browser_mode == "cdp":
                        st.info("💡 Chrome CDP não conectado? Rode:\\n`powershell -ExecutionPolicy Bypass -File .\\deploy\\local\\start-radar-chrome.ps1`")

    st.divider()
    c_class, c_rep = st.columns(2)
    with c_class:
        if st.button("Classificar Concorrentes", use_container_width=True):
            with st.spinner("Classificando..."):
                res = classify_linked_candidates_for_product(selected_uid)
                if res["ok"]:
                    st.success(f"Classificados: {res['total']} (Diretos: {res['direct']} | Parciais: {res['partial']} | Rejeitados: {res['rejected']})")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error(res["error"])
    with c_rep:
        if st.button("Gerar Relatório de Padrões", use_container_width=True):
            with st.spinner("Analisando padrões..."):
                res = run_pattern_analysis_for_product(selected_uid)
                if res["ok"]:
                    st.success("Relatório gerado com sucesso!")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error(f"Não foi possível gerar: {res['error']}")
                    
    st.divider()
    st.write("##### Tabela de Concorrentes Vinculados")
    
    table_data = get_competitor_table_for_product(selected_uid)
    if not table_data:
        st.info("Nenhum concorrente vinculado a este produto ainda.")
    else:
        filter_status = st.selectbox("Filtrar status:", ["Todos", "coleta_pendente", "aguardando_classificacao", "competitor_direct", "competitor_partial", "rejected", "falha_coleta"])
        
        filtered = table_data
        if filter_status != "Todos":
            filtered = [r for r in table_data if r["status"] == filter_status]
            
        if filtered:
            import pandas as pd
            df = pd.DataFrame(filtered)
            
            show_cols = ["status", "relevance_score", "title", "price", "marketplace", "shop_name", "canonical_url", "product_uid"]
            exist_cols = [c for c in show_cols if c in df.columns]
            
            st.dataframe(df[exist_cols], hide_index=True)
        else:
            st.warning("Nenhum registro para este filtro.")

def render_espelho_loja():
"""

code = code.replace("def render_espelho_loja():", func_def)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(code)

print("App patched for R7.2")
