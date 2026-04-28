@echo off
title ShopeeBooster - Status do Bot
echo ========================================
echo   ShopeeBooster Bot - Status
echo ========================================
echo.

cd /d "%~dp0"
powershell.exe -ExecutionPolicy Bypass -File "deploy\local\status-bot.ps1"

echo.
echo Pressione qualquer tecla para fechar...
pause >nul