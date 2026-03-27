@echo off
title Shopee Booster — Build .exe
color 0B

echo.
echo  ============================================
echo   SHOPEE BOOSTER — GERANDO EXECUTAVEL
echo  ============================================
echo.

REM ── Ativar virtualenv ────────────────────────────────────────
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM ── Instalar PyInstaller se necessário ───────────────────────
pip show pyinstaller >nul 2>nul
if %errorlevel% neq 0 (
    echo  Instalando PyInstaller...
    pip install pyinstaller
)

REM ── Instalar Playwright (browsers) ───────────────────────────
echo  Verificando Playwright...
python -m playwright install chromium

REM ── Build ────────────────────────────────────────────────────
echo.
echo  Gerando .exe...
echo.

pyinstaller ^
    --noconfirm ^
    --onedir ^
    --windowed ^
    --name "ShopeeBooster" ^
    --icon "assets\icon.ico" ^
    --add-data "app.py;." ^
    --add-data "updater.py;." ^
    --add-data "version.txt;." ^
    --add-data "models;models" ^
    --collect-all streamlit ^
    --collect-all pystray ^
    --collect-all webview ^
    --collect-all rembg ^
    --collect-all onnxruntime ^
    --collect-all opentelemetry ^
    --collect-all google ^
    --collect-all nest_asyncio ^
    --collect-all playwright ^
    --collect-all Pillow ^
    --hidden-import "PIL.ImageEnhance" ^
    --hidden-import "PIL.ImageFilter" ^
    --hidden-import "PIL.ImageDraw" ^
    --hidden-import "google.genai" ^
    --hidden-import "onnxruntime" ^
    --hidden-import "PIL._tkinter_finder" ^
    --hidden-import "pystray._win32" ^
    --hidden-import "nest_asyncio" ^
    launcher.py

if %errorlevel% == 0 (
    echo.
    echo  ============================================
    echo   BUILD CONCLUIDO! Arquivo em dist\ShopeeBooster\
echo  ============================================
) else (
    echo.
    echo  ERRO no build. Veja a saida acima.
)
