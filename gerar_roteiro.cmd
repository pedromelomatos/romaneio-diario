@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0_runtime\python.exe" (
    "%~dp0_runtime\python.exe" -X utf8 "%~dp0bling.py" gerar %*
    goto :fim
)
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
    "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" bling.py gerar %*
    goto :fim
)
py -3 --version >nul 2>&1
if not errorlevel 1 (
    py -3 bling.py gerar %*
) else (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo Instale o Python 3.10 ou superior e execute novamente.
    ) else (
        python bling.py gerar %*
    )
)
:fim
echo.
pause
