@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo  INSTALACAO DO ROBO DE FICHAS DA JUCESC (uma vez por computador)
echo ============================================================
python --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo O Python nao foi encontrado.
  echo Instale pelo site python.org e MARQUE a opcao "Add python.exe to PATH".
  echo Depois rode este instalar.bat de novo.
  pause
  exit /b 1
)
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo Instalando o navegador de reserva (usado so se o Google Chrome nao estiver instalado)...
python -m playwright install chromium
echo.
echo Instalacao concluida. Para iniciar a API, use iniciar_api.bat.
echo O CLI legado continua disponivel em rodar.bat.
pause
