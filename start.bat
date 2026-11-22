@echo off
title AI Bridge Server
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    pause
    exit /b 1
)

python -c "import fastapi, uvicorn, pydantic, pyautogui, PIL" >nul 2>&1
if errorlevel 1 (
    echo [*] Installing missing dependencies from requirements.txt...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
)

echo [*] Starting AI Bridge on http://127.0.0.1:8000 ...
python bridge.py
pause
