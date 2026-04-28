@echo off
title ShopeeBooster - Desligar Bot
echo ========================================
echo   ShopeeBooster Bot - Desligando...
echo ========================================
echo.

cd /d "%~dp0"
powershell.exe -ExecutionPolicy Bypass -File "deploy\local\stop-bot.ps1"

echo.
echo Pressione qualquer tecla para fechar...
pause >nul