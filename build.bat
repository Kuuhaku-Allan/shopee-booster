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
echo  Pulando instalacao do Playwright (sera feita pelo install_browsers.exe)...

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
    --add-data "release_meta.py;." ^
    --add-data "telegram_service.py;." ^
    --add-data "sentinela_db.py;." ^
    --add-data "shopee_core;shopee_core" ^
    --add-data "version.txt;." ^
    --add-data "assets;assets" ^
    --add-data "models;models" ^
    --add-data "%LOCALAPPDATA%\ms-playwright;pw-browsers" ^
    --copy-metadata pymatting ^
    --copy-metadata rembg ^
    --copy-metadata onnxruntime ^
    --collect-all streamlit ^
    --collect-all streamlit_drawable_canvas ^
    --collect-all pystray ^
    --collect-all webview ^
    --collect-all rembg ^
    --collect-all onnxruntime ^
    --collect-all opentelemetry ^
    --collect-all google ^
    --collect-all nest_asyncio ^
    --collect-all playwright ^
    --collect-all Pillow ^
    --collect-all shopee_core ^
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
    echo   BUILD CONCLUIDO!
    echo  Gerando instalador de browsers...
    echo  ============================================
    echo.

    REM -- Build do instalador de browsers --
    pyinstaller --noconfirm --onefile --console --name "install_browsers" install_browsers.py

    if %errorlevel% == 0 (
        echo  Copiando install_browsers.exe para dist\ShopeeBooster...
        copy /Y "dist\install_browsers.exe" "dist\ShopeeBooster\install_browsers.exe" >nul

        echo.
        echo  ============================================
        echo   BUILD COMPLETO!
        echo   Arquivos em dist\ShopeeBooster\
        echo  ============================================
    ) else (
        echo  Aviso: Falha ao criar install_browsers.exe
        echo  O app ainda funcionara, mas precisara dos browsers instalados manualmente.
    )
) else (
    echo.
    echo  ERRO no build. Veja a saida acima.
)
