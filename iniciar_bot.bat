@echo off
chcp 65001 >nul
title Bot de Futuros SMC v5

echo ════════════════════════════════════════════════════════════
echo    BOT DE FUTUROS SMC v3 - INICIANDO
echo    Capital: $600 ^| Leverage: 10x ^| Max pos: 2
echo ════════════════════════════════════════════════════════════
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python no esta instalado
    pause
    exit /b 1
)

if not exist "venv\" (
    echo Creando entorno virtual...
    python -m venv venv
)

call venv\Scripts\activate
echo Verificando dependencias...
pip install -q -r requirements.txt

echo.
echo ════════════════════════════════════════════════════════════
echo    INICIANDO - Ctrl+C para detener
echo ════════════════════════════════════════════════════════════
echo.

python main.py
pause
