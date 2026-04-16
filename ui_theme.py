"""
ui_theme.py — Sistema de Design do Shopee Booster
==================================================
Responsável por:
  - Paleta de cores (dark / light mode)
  - Tipografia (Inter via Google Fonts)
  - Injeção de CSS no Streamlit
  - Toggle de tema persistente via session_state

Para usar:
    from ui_theme import apply_theme, init_theme
    init_theme()   # inicializa session_state
    apply_theme()  # injeta o CSS correto
"""

import streamlit as st

# ── CSS base: tokens de design e estilos globais ─────────────────
_CSS_DARK = """
/* ═══════════════════ DARK MODE TOKENS ═══════════════════ */
:root {
    --bg-primary:      #0f0f10;
    --bg-surface:      #18181c;
    --bg-card:         #1e1e24;
    --bg-card-hover:   #25252d;
    --bg-input:        #1e1e24;
    --border-color:    rgba(255,255,255,0.07);
    --border-focus:    rgba(238,77,45,0.6);
    --accent:          #ee4d2d;
    --accent-hover:    #ff6b4a;
    --accent-dim:      rgba(238,77,45,0.15);
    --text-primary:    #f1f1f1;
    --text-secondary:  #9a9a9a;
    --text-muted:      #5a5a6a;
    --text-on-accent:  #ffffff;
    --success:         #22c55e;
    --warning:         #f59e0b;
    --error:           #ef4444;
    --info:            #3b82f6;
    --shadow-card:     0 4px 24px rgba(0,0,0,0.4);
    --shadow-hover:    0 8px 32px rgba(0,0,0,0.5);
    --sidebar-width:   240px;
    --radius-sm:       8px;
    --radius-md:       12px;
    --radius-lg:       20px;
    --radius-pill:     999px;
    --transition:      all 0.2s ease;
}

/* stWarning texto visível no dark */
.stWarning p,
.stWarning span,
.stWarning div {
    color: var(--warning) !important;
}

/* ===== FIX FORZADO PARA QUANDO O BASE-THEME É LIGHT (Como no .exe) ===== */
/* Chat Input Container e sua caixa interna */
.stChatInputContainer, 
[data-testid="stChatInput"],
[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] textarea {
    background-color: var(--bg-surface) !important;
    color: var(--text-primary) !important;
}

/* Fix para stCode (Resultados de programação / FAQ gerado) */
.stCode,
.stCode pre,
code[class*="language-"],
pre[class*="language-"] {
    background-color: var(--bg-card) !important;
    color: var(--text-primary) !important;
}

.stCode code {
    color: var(--text-primary) !important;
}

/* Expander - Cabeçalho do FAQ / Elementos drop-down */
[data-testid="stExpander"] > details > summary {
    background-color: var(--bg-card) !important;
    color: var(--text-primary) !important;
}

[data-testid="stExpander"] > details > div {
    background-color: var(--bg-primary) !important;
}

[data-baseweb="button"],
.stButton > button {
    background-color: var(--bg-card) !important;
    border-color: var(--border-color) !important;
    color: var(--text-primary) !important;
}
.stButton > button:hover {
    background-color: var(--bg-card-hover) !important;
    border-color: var(--accent) !important;
    color: var(--text-primary) !important;
}
.stButton > button[kind="primary"] {
    background-color: var(--accent) !important;
    color: var(--text-on-accent) !important;
    border-color: var(--accent) !important;
}
.stButton > button[kind="primary"]:hover {
    background-color: var(--accent-hover) !important;
}
"""

_CSS_LIGHT = """
/* ═══════════════════ LIGHT MODE TOKENS ═══════════════════ */
:root {
    --bg-primary:      #f5f7fa;
    --bg-surface:      #ffffff;
    --bg-card:         #ffffff;
    --bg-card-hover:   #f8f9fc;
    --bg-input:        #ffffff;
    --border-color:    rgba(0,0,0,0.07);
    --border-focus:    rgba(238,77,45,0.4);
    --accent:          #ee4d2d;
    --accent-hover:    #d63e20;
    --accent-dim:      rgba(238,77,45,0.1);
    --text-primary:    #1a1a2e;
    --text-secondary:  #6b7280;
    --text-muted:      #9ca3af;
    --text-on-accent:  #ffffff;
    --success:         #16a34a;
    --warning:         #92400e;
    --error:           #dc2626;
    --info:            #2563eb;
    --shadow-card:     0 2px 16px rgba(0,0,0,0.08);
    --shadow-hover:    0 6px 24px rgba(0,0,0,0.12);
    --sidebar-width:   240px;
    --radius-sm:       8px;
    --radius-md:       12px;
    --radius-lg:       20px;
    --radius-pill:     999px;
    --transition:      all 0.2s ease;
}

/* Fix de Contraste para Placeholders (Modo Claro) */
[data-testid="stTextInput"] input::placeholder,
input::placeholder,
textarea::placeholder {
    color: #5B5B5B !important; /* Cinza escuro para máxima legibilidade */
    opacity: 1 !important;     /* Remove a transparência que "apaga" o texto */
}

/* Inversão persistente para containers que permanecem escuros */
[data-testid="stSidebar"] *, 
.product-card-body *,
.st-key-auditoria-container * {
    color: var(--text-primary) !important;
}

/* Se houver algum componente que VOCÊ quer que continue preto com texto branco */
.dark-container-fix {
    background-color: #0f0f10 !important;
    color: #ffffff !important;
}

/* Alertas Acessíveis (WCAG Compliant) */
.stWarning {
    background: #FFF9E6 !important; /* Fundo Creme */
    border-color: #ffeeba !important;
}
.stWarning p, .stWarning span, .stWarning div {
    color: #856404 !important; /* Texto Marrom Escuro */
    font-weight: 600 !important;
}

/* Fix para st.code no Tema Claro — fundo claro + texto escuro */
.stCode,
.stCode pre,
code[class*="language-"],
pre[class*="language-"] {
    background-color: #f1f3f5 !important;
    color: #1a1a2e !important;
}
.stCode code {
    color: #1a1a2e !important;
}
"""

_CSS_COMMON = """
/* ═══════════════════ GOOGLE FONTS ════════════════════════ */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* ═══════════════════ GLOBAL RESET ════════════════════════ */
*, *::before, *::after { box-sizing: border-box; }

html, body, [data-testid="stAppViewContainer"], .main {
    background-color: var(--bg-primary) !important;
    color: var(--text-primary) !important;
    font-family: 'Inter', -apple-system, sans-serif !important;
}

/* Remove fundo branco padrão do Streamlit */
[data-testid="stAppViewContainer"] > .main {
    background-color: var(--bg-primary) !important;
}
[data-testid="block-container"] {
    padding-top: 1.5rem !important;
    padding-bottom: 3rem !important;
    max-width: 1200px !important;
}
/* Remove o gradiente azul do header do Streamlit */
[data-testid="stHeader"] {
    background-color: var(--bg-primary) !important;
    border-bottom: 1px solid var(--border-color) !important;
}
/* Garante background uniforme em toda a área main */
section.main > div {
    background-color: var(--bg-primary) !important;
}
.stApp > header {
    background-color: var(--bg-primary) !important;
}

/* ═══════════════════ SIDEBAR ══════════════════════════════ */
[data-testid="stSidebar"] {
    background-color: var(--bg-surface) !important;
    border-right: 1px solid var(--border-color) !important;
}
[data-testid="stSidebar"] > div:first-child {
    padding-top: 1.5rem;
}
/* Texto e labels do sidebar */
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] .stMarkdown {
    color: var(--text-primary) !important;
}

/* ═══════════════════ LOGO / BRAND (SIDEBAR) ══════════════ */
.brand-logo {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 0 1.5rem 0;
    border-bottom: 1px solid var(--border-color);
    margin-bottom: 1.5rem;
}
.brand-logo-icon {
    width: 36px; height: 36px;
    background: var(--accent);
    border-radius: var(--radius-sm);
    display: flex; align-items: center; justify-content: center;
    font-size: 18px;
    flex-shrink: 0;
}
.brand-logo-text {
    font-size: 15px;
    font-weight: 700;
    color: var(--text-primary) !important;
    line-height: 1.2;
}
.brand-logo-sub {
    font-size: 10px;
    color: var(--accent) !important;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-weight: 600;
}

/* ═══════════════════ NAVEGAÇÃO LATERAL ═══════════════════ */
.nav-section-label {
    font-size: 10px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    font-weight: 600;
    color: var(--text-muted) !important;
    padding: 0 0 0.5rem 0;
    margin-top: 0.5rem;
}
.nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    transition: var(--transition);
    margin-bottom: 4px;
    text-decoration: none;
    border: none;
    background: transparent;
    width: 100%;
    text-align: left;
    font-size: 14px;
    font-weight: 500;
    color: var(--text-secondary);
}
.nav-item:hover {
    background: var(--bg-card);
    color: var(--text-primary);
}
.nav-item.active {
    background: var(--accent-dim);
    color: var(--accent);
    font-weight: 600;
}
.nav-item-icon { font-size: 16px; }

/* ═══════════════════ BOTÕES ═══════════════════════════════ */
.stButton > button {
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    font-size: 13.5px !important;
    border-radius: var(--radius-sm) !important;
    transition: var(--transition) !important;
    border: 1px solid var(--border-color) !important;
    background: var(--bg-card) !important;
    color: var(--text-primary) !important;
    padding: 0.45rem 1rem !important;
}
.stButton > button:hover {
    background: var(--bg-card-hover) !important;
    border-color: var(--accent) !important;
    color: var(--accent) !important;
    transform: translateY(-1px);
    box-shadow: var(--shadow-hover) !important;
}

/* Botão primário */
.stButton > button[kind="primary"],
[data-testid="baseButton-primary"] {
    background: var(--accent) !important;
    color: var(--text-on-accent) !important;
    border-color: var(--accent) !important;
}
.stButton > button[kind="primary"]:hover,
[data-testid="baseButton-primary"]:hover {
    background: var(--accent-hover) !important;
    border-color: var(--accent-hover) !important;
    color: white !important;
}

/* ═══════════════════ INPUTS ═══════════════════════════════ */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div,
.stMultiSelect > div > div {
    background-color: var(--bg-input) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text-primary) !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 14px !important;
    transition: var(--transition) !important;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: var(--border-focus) !important;
    box-shadow: 0 0 0 3px rgba(238,77,45,0.1) !important;
}
.stTextInput label, .stTextArea label, .stSelectbox label, .stFileUploader label {
    color: var(--text-secondary) !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    font-family: 'Inter', sans-serif !important;
}

/* ═══════════════════ TABS ═════════════════════════════════ */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px !important;
    background: transparent !important;
    border-bottom: 1px solid var(--border-color) !important;
    padding-bottom: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    border: none !important;
    color: var(--text-secondary) !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 13.5px !important;
    font-weight: 500 !important;
    padding: 0.5rem 1rem !important;
    border-radius: var(--radius-sm) var(--radius-sm) 0 0 !important;
    transition: var(--transition) !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: var(--text-primary) !important;
    background: var(--bg-card) !important;
}
.stTabs [aria-selected="true"] {
    color: var(--accent) !important;
    font-weight: 600 !important;
    border-bottom: 2px solid var(--accent) !important;
    background: transparent !important;
}
[data-testid="stTabsContent"] {
    background: transparent !important;
    padding: 1.5rem 0 !important;
}

/* ═══════════════════ MÉTRICAS ═════════════════════════════ */
[data-testid="stMetric"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    padding: 1.1rem 1.2rem !important;
    transition: var(--transition) !important;
}
[data-testid="stMetric"]:hover {
    border-color: var(--accent) !important;
    box-shadow: var(--shadow-hover) !important;
    transform: translateY(-2px);
}
[data-testid="stMetricLabel"] {
    font-size: 11px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
    color: var(--text-muted) !important;
    font-weight: 600 !important;
}
[data-testid="stMetricValue"] {
    font-size: 22px !important;
    font-weight: 700 !important;
    color: var(--text-primary) !important;
}

/* ═══════════════════ DATAFRAME / TABELA ══════════════════ */
/*
 * st.dataframe usa glide-data-grid (canvas) — não responsivo a CSS de cor.
 * Usamos st.table (HTML real) no lugar, que é totalmente estilizável.
 */
[data-testid="stDataFrame"] {
    border-radius: var(--radius-md) !important;
    overflow: hidden !important;
    border: 1px solid var(--border-color) !important;
}

/* ═══════════════════ ST.TABLE (HTML real, totalmente estilizável) ═══ */
[data-testid="stTable"] table,
.stTable table {
    width: 100% !important;
    border-collapse: collapse !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 13px !important;
    background: var(--bg-card) !important;
    border-radius: var(--radius-md) !important;
    overflow: hidden !important;
    border: 1px solid var(--border-color) !important;
}
[data-testid="stTable"] thead th,
.stTable thead th {
    background: var(--bg-surface) !important;
    color: var(--text-muted) !important;
    font-size: 10.5px !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.07em !important;
    padding: 10px 14px !important;
    border-bottom: 1px solid var(--border-color) !important;
    text-align: left !important;
    white-space: nowrap !important;
}
[data-testid="stTable"] tbody td,
.stTable tbody td {
    color: var(--text-primary) !important;
    padding: 10px 14px !important;
    border-bottom: 1px solid var(--border-color) !important;
    background: var(--bg-card) !important;
    vertical-align: middle !important;
}
[data-testid="stTable"] tbody tr:last-child td,
.stTable tbody tr:last-child td {
    border-bottom: none !important;
}
[data-testid="stTable"] tbody tr:hover td,
.stTable tbody tr:hover td {
    background: var(--bg-card-hover) !important;
    transition: var(--transition) !important;
}
/* Índice da tabela (coluna de número) */
[data-testid="stTable"] tbody th,
.stTable tbody th {
    color: var(--text-muted) !important;
    font-size: 11px !important;
    font-weight: 400 !important;
    padding: 10px 14px !important;
    border-bottom: 1px solid var(--border-color) !important;
    background: var(--bg-surface) !important;
    border-right: 1px solid var(--border-color) !important;
}


/* ═══════════════════ CARDS DE PRODUTO ═══════════════════ */
.product-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    overflow: hidden;
    transition: var(--transition);
    cursor: pointer;
    height: 100%;
}
.product-card:hover {
    border-color: var(--accent);
    box-shadow: var(--shadow-hover);
    transform: translateY(-3px);
}
.product-card img {
    width: 100%;
    aspect-ratio: 1 / 1;
    object-fit: cover;
}
.product-card-body {
    padding: 0.75rem;
}
.product-card-name {
    font-size: 12.5px;
    font-weight: 500;
    color: var(--text-primary);
    margin-bottom: 4px;
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.product-card-price {
    font-size: 14px;
    font-weight: 700;
    color: var(--accent);
}

/* ═══════════════════ CHAT ═════════════════════════════════ */
[data-testid="stChatMessage"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    margin-bottom: 0.75rem !important;
    padding: 0.85rem 1rem !important;
}
[data-testid="stChatMessageContent"] p {
    color: var(--text-primary) !important;
    font-family: 'Inter', sans-serif !important;
}
[data-testid="stChatInputTextArea"] textarea {
    background: var(--bg-input) !important;
    color: var(--text-primary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-sm) !important;
}

/* ═══════════════════ ALERTAS / INFO BOXES ════════════════ */
[data-testid="stAlert"] {
    border-radius: var(--radius-sm) !important;
    border-width: 1px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 13.5px !important;
}
.stSuccess {
    background: rgba(34,197,94,0.08) !important;
    border-color: rgba(34,197,94,0.3) !important;
    color: var(--success) !important;
}
.stWarning {
    background: rgba(245,158,11,0.08) !important;
    border-color: rgba(245,158,11,0.3) !important;
}
.stInfo {
    background: rgba(59,130,246,0.08) !important;
    border-color: rgba(59,130,246,0.3) !important;
}
.stError {
    background: rgba(239,68,68,0.08) !important;
    border-color: rgba(239,68,68,0.3) !important;
}

/* ═══════════════════ EXPANDERS ════════════════════════════ */
[data-testid="stExpander"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    margin-bottom: 0.75rem !important;
}
[data-testid="stExpander"] summary {
    color: var(--text-primary) !important;
    font-weight: 500 !important;
    font-family: 'Inter', sans-serif !important;
}

/* ═══════════════════ QUICK ACTION CHIPS ═══════════════════ */
/* Estilização para botões dentro de colunas de ações rápidas */
.stButton > button {
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    font-size: 13.5px !important;
    border-radius: var(--radius-sm) !important;
    transition: var(--transition) !important;
    border: 1px solid var(--border-color) !important;
    background: var(--bg-card) !important;
    color: var(--text-primary) !important;
    padding: 0.45rem 1rem !important;
}

/* Estilo específico para botões que devem parecer cards de ação */
.action-card-btn > div > [data-testid="stButton"] > button {
    height: 80px !important;
    width: 100% !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 8px !important;
    padding: 10px !important;
    border-radius: var(--radius-md) !important;
    line-height: 1.1 !important;
    font-size: 11px !important;
    text-align: center !important;
}

/* ═══════════════════ CANVAS & LAYERS ═════════════════════ */
.canvas-container {
    border: 2px dashed var(--border-color);
    border-radius: var(--radius-md);
    padding: 10px;
    background: #000;
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 400px;
}

.layer-item {
    padding: 8px 12px;
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    margin-bottom: 6px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
}

.roi-preview {
    position: absolute;
    border: 2px solid #FF4B4B;
    background: rgba(255, 75, 75, 0.1);
    pointer-events: none;
}

/* ═══════════════════ TIPOGRAFIA GLOBAL ═══════════════════ */
h1, h2, h3, h4, h5, h6,
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
    color: var(--text-primary) !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em;
}
/* Aplica Inter em elementos de texto — NUNCA em spans (quebra ícones Material) */
p, li { font-family: 'Inter', sans-serif !important; }
div:not([data-testid*="Icon"]):not([class*="material"]):not([class*="icon"]) {
    font-family: 'Inter', sans-serif;
}


/* ═══════════════════ PAGE HEADER CUSTOMIZADO ═════════════ */
.page-header {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 2rem;
    padding-bottom: 1.5rem;
    border-bottom: 1px solid var(--border-color);
}
.page-header-icon {
    width: 48px; height: 48px;
    background: var(--accent-dim);
    border-radius: var(--radius-md);
    display: flex; align-items: center; justify-content: center;
    font-size: 24px;
    border: 1px solid rgba(238,77,45,0.2);
    flex-shrink: 0;
}
.page-header-title {
    font-size: 24px;
    font-weight: 800;
    color: var(--text-primary) !important;
    letter-spacing: -0.03em;
    line-height: 1.2;
    margin: 0;
}
.page-header-sub {
    font-size: 13px;
    color: var(--text-secondary) !important;
    margin-top: 3px;
}

/* ═══════════════════ SEÇÃO / SECTION DIVIDER ════════════ */
.section-label {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-muted) !important;
    margin: 0 0 0.75rem 0;
}

/* ═══════════════════ FILE UPLOADER ════════════════════════ */
[data-testid="stFileUploader"] {
    background: var(--bg-card) !important;
    border: 1px dashed var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    transition: var(--transition) !important;
}
[data-testid="stFileUploader"]:hover {
    border-color: var(--accent) !important;
    background: var(--accent-dim) !important;
}

/* ═══════════════════ STATUS / SPINNER ════════════════════ */
[data-testid="stStatusWidget"],
[data-testid="stStatus"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
}

/* ═══════════════════ CÓDIGO / CODE BLOCK ═════════════════ */
.stCodeBlock pre, code {
    background: var(--bg-surface) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-sm) !important;
    font-size: 12px !important;
    color: var(--text-primary) !important;
}

/* ═══════════════════ SCROLLBAR CUSTOM ════════════════════ */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
    background: var(--text-muted);
    border-radius: var(--radius-pill);
}
::-webkit-scrollbar-thumb:hover { background: var(--text-secondary); }

/* ═══════════════════ CHECKBOX ════════════════════════════ */
[data-testid="stCheckbox"] label {
    color: var(--text-primary) !important;
    font-size: 14px !important;
}

/* ═══════════════════ RADIO BUTTON NAV ═══════════════════ */
[data-testid="stRadio"] > label {
    display: none !important;
}
[data-testid="stRadio"] > div {
    display: flex !important;
    flex-direction: column !important;
    gap: 4px !important;
}
[data-testid="stRadio"] [data-testid="stMarkdownContainer"] p {
    font-size: 14px !important;
    font-weight: 500 !important;
}

/* ═══════════════════ DIVIDER ══════════════════════════════ */
hr {
    border: none !important;
    border-top: 1px solid var(--border-color) !important;
    margin: 1.5rem 0 !important;
}

/* ═══════════════════ THEME TOGGLE BTN ═══════════════════ */
.theme-toggle-wrapper .stButton > button {
    background: var(--bg-card) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-pill) !important;
    padding: 0.3rem 0.8rem !important;
    font-size: 12px !important;
    color: var(--text-secondary) !important;
    font-weight: 500 !important;
}
.theme-toggle-wrapper .stButton > button:hover {
    border-color: var(--accent) !important;
    color: var(--accent) !important;
}

/* ═══════════════════ BADGE / TAG ══════════════════════════ */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: var(--radius-pill);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.04em;
}
.badge-accent { background: var(--accent-dim); color: var(--accent); }
.badge-success { background: rgba(34,197,94,0.12); color: var(--success); }
.badge-beta { background: rgba(245,158,11,0.12); color: var(--warning); }

/* ═══════════════════ LOJA STATUS CARD ═══════════════════ */
.loja-status-bar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    background: var(--accent-dim);
    border: 1px solid rgba(238,77,45,0.2);
    border-radius: var(--radius-sm);
    margin-bottom: 1.5rem;
    font-size: 13px;
    color: var(--accent);
    font-weight: 600;
}

/* ═══════════════════ PRODUCT GRID ════════════════════════ */
.product-grid-header {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 8px;
}

/* ═══════════════════ CAPTION / CAPTION TEXT ══════════════ */
[data-testid="stCaptionContainer"] {
    color: var(--text-muted) !important;
    font-size: 12px !important;
}

/* ═══════════════════ SELECT / DROPDOWN ═══════════════════ */
[data-baseweb="select"] {
    background: var(--bg-input) !important;
}
[data-baseweb="select"] > div {
    background: var(--bg-input) !important;
    border-color: var(--border-color) !important;
    color: var(--text-primary) !important;
}
[data-baseweb="popover"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
}
[data-baseweb="menu"] li {
    background: var(--bg-card) !important;
    color: var(--text-primary) !important;
}
[data-baseweb="menu"] li:hover {
    background: var(--bg-card-hover) !important;
}
"""


def init_theme():
    """Inicializa o session_state do tema. Deve ser chamado antes de apply_theme()."""
    if "dark_mode" not in st.session_state:
        st.session_state.dark_mode = True  # Dark por padrão


def apply_theme():
    """Aplica o CSS do tema atual (dark ou light) via injeção no HTML."""
    tokens = _CSS_DARK if st.session_state.get("dark_mode", True) else _CSS_LIGHT
    st.markdown(
        f"<style>{tokens}{_CSS_COMMON}</style>",
        unsafe_allow_html=True
    )


def render_theme_toggle():
    """Renderiza o botão de alternância de tema no sidebar."""
    is_dark = st.session_state.get("dark_mode", True)
    label = "☀️ Modo Claro" if is_dark else "🌙 Modo Escuro"

    st.markdown('<div class="theme-toggle-wrapper">', unsafe_allow_html=True)
    if st.button(label, key="theme_toggle_btn", width='stretch'):
        st.session_state.dark_mode = not st.session_state.dark_mode
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
