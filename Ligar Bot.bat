@echo off
title ShopeeBooster - Ligar Bot
echo ========================================
echo   ShopeeBooster Bot - Iniciando...
echo ========================================
echo.

cd /d "%~dp0"
powershell.exe -ExecutionPolicy Bypass -File "deploy\local\start-bot.ps1"

echo.
echo Pressione qualquer tecla para fechar...
pause >nul