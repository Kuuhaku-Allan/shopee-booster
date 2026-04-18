@echo off
title Shopee Booster â€” Build .exe
color 0B

echo.
echo  ============================================
echo   SHOPEE BOOSTER â€” GERANDO EXECUTAVEL
echo  ============================================
echo.

REM â”€â”€ Ativar virtualenv â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM â”€â”€ Instalar PyInstaller se necessÃ¡rio â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
pip show pyinstaller >nul 2>nul
if %errorlevel% neq 0 (
    echo  Instalando PyInstaller...
    pip install pyinstaller
)

REM â”€â”€ Instalar Playwright (browsers) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo  Verificando Playwright...
python -m playwright install chromium

REM â”€â”€ Build â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
    --add-data "backend_core.py;." ^
    --add-data "ui_theme.py;." ^
    --add-data "updater.py;." ^
    --add-data "version.txt;." ^
    --add-data "assets;assets" ^
    --add-data "models;models" ^
    --add-data "%LOCALAPPDATA%\ms-playwright;pw-browsers" ^
    --copy-metadata pymatting ^
    --copy-metadata rembg ^
    --copy-metadata onnxruntime ^
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
