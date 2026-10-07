@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m uvicorn src.api:app --host 127.0.0.1 --port 8000
