@echo off
title Shopee Booster — Ambiente de Desenvolvimento
color 0A

echo.
echo  ============================================
echo   SHOPEE BOOSTER — MODO DESENVOLVIMENTO
echo   Alteracoes em app.py recarregam automatico
echo  ============================================
echo.

REM ── Ativar virtualenv ────────────────────────────────────────
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

REM ── Garantir que o .shopee_config existe para dev ─────────────
if not exist ".shopee_config" (
    echo  AVISO: Arquivo .shopee_config nao encontrado.
    echo  Crie o arquivo .shopee_config com: GOOGLE_API_KEY=sua_chave
    echo.
)

REM ── Iniciar Streamlit em modo dev (auto-reload ativo) ─────────
python -m streamlit run app.py ^
    --server.port 8501 ^
    --server.runOnSave true ^
    --server.headless false ^
    --theme.base light
