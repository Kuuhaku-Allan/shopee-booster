@echo off
title Shopee Booster - Build Completo
color 0B

echo.
echo  ============================================
echo   SHOPEE BOOSTER - BUILD COMPLETO
echo  ============================================
echo.

REM -- Ativar virtualenv --
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM -- Verificar PyInstaller --
pip show pyinstaller >nul 2>nul
if %errorlevel% neq 0 (
    echo  Instalando PyInstaller...
    pip install pyinstaller
)

REM -- Build do ShopeeBooster --
echo.
echo  [1/2] Compilando ShopeeBooster.exe...
echo.

pyinstaller --noconfirm ShopeeBooster.spec

if %errorlevel% neq 0 (
    echo.
    echo  ERRO ao compilar ShopeeBooster.exe
    pause
    exit /b 1
)

REM -- Build do install_browsers --
echo.
echo  [2/2] Compilando install_browsers.exe...
echo.

pyinstaller --noconfirm --onefile --console --name "install_browsers" install_browsers.py

if %errorlevel% neq 0 (
    echo.
    echo  ERRO ao compilar install_browsers.exe
    pause
    exit /b 1
)

REM -- Copiar install_browsers.exe para a pasta do ShopeeBooster --
echo.
echo  Copiando install_browsers.exe para dist\ShopeeBooster...
copy /Y "dist\install_browsers.exe" "dist\ShopeeBooster\install_browsers.exe" >nul

if %errorlevel% == 0 (
    echo.
    echo  ============================================
    echo   BUILD COMPLETO COM SUCESSO!
    echo  ============================================
    echo.
    echo   Arquivos gerados:
    echo   - dist\ShopeeBooster\ShopeeBooster.exe
    echo   - dist\ShopeeBooster\install_browsers.exe
    echo.
    echo  ============================================
) else (
    echo  Aviso: Falha ao copiar install_browsers.exe
)

pause
