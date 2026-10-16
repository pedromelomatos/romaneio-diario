@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist "%~dp0_runtime\python.exe" (
    echo Extraia a pasta inteira do ZIP antes de abrir este atalho.
    echo Se estiver usando o codigo-fonte, execute app.py com Python.
    pause
    exit /b 1
)
"%~dp0_runtime\python.exe" -X utf8 "%~dp0app.py" %*
if errorlevel 1 (
    echo.
    echo Nao foi possivel abrir o programa. Extraia novamente o ZIP completo.
    pause
)
