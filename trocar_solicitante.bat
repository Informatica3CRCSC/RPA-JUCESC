@echo off
chcp 65001 >nul
cd /d "%~dp0"
python consulta_fichas_jucesc.py --trocar-solicitante
