@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title FLUXUS MANAGER
color 0F

set "BASE_DIR=%~dp0"
if "%BASE_DIR:~-1%"=="\" set "BASE_DIR=%BASE_DIR:~0,-1%"

:: --- CAMINHOS ---
set "VENV_DIR=%BASE_DIR%\sumo-backend\venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
set "REQUIREMENTS_PATH=%BASE_DIR%\sumo-backend\requirements.txt"
set "BOOT_LOGGER=%BASE_DIR%\boot_logger.py"
set "DB_PATCHER=%BASE_DIR%\db_patcher.py"
set "SYNC_SCRIPT=%BASE_DIR%\sumo-backend\vercel_sync.py"
set "DOCKER_EXE=C:\Program Files\Docker\Docker\Docker Desktop.exe"
set "LOG_DIR=%BASE_DIR%\scenarios\logs"
set "LOCAL_LOG=%LOG_DIR%\controlador.log"
set "URL_FILE=%BASE_DIR%\ngrok_url.txt"

:: Caminho do Frontend fixo
set "FRONT_PATH=C:\UNIP\site-web"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
echo [INIT] Started > "%LOCAL_LOG%"
if exist "%URL_FILE%" del "%URL_FILE%"

:: --- CHECAGENS ---
python --version >nul 2>&1
if %errorlevel% neq 0 (
    cls
    echo [ERRO] Python nao encontrado.
    pause
    exit
)

if not exist "%VENV_DIR%" (
    python -m venv "%VENV_DIR%" >> "%LOCAL_LOG%" 2>&1
)

"%VENV_PYTHON%" -m pip install --upgrade pip pyngrok supabase python-dotenv >> "%LOCAL_LOG%" 2>&1

if exist "%REQUIREMENTS_PATH%" (
    "%VENV_PIP%" install -r "%REQUIREMENTS_PATH%" >> "%LOCAL_LOG%" 2>&1
)

echo import os, sys, datetime > "%BOOT_LOGGER%"
echo from dotenv import load_dotenv >> "%BOOT_LOGGER%"
echo from supabase import create_client >> "%BOOT_LOGGER%"
echo try: load_dotenv() >> "%BOOT_LOGGER%"
echo except: pass >> "%BOOT_LOGGER%"
echo url = os.getenv("SUPABASE_URL") >> "%BOOT_LOGGER%"
echo key = os.getenv("SUPABASE_KEY") >> "%BOOT_LOGGER%"
echo def log(lvl, msg): >> "%BOOT_LOGGER%"
echo      if not url or not key: return >> "%BOOT_LOGGER%"
echo      try: >> "%BOOT_LOGGER%"
echo          sb = create_client(url, key) >> "%BOOT_LOGGER%"
echo          data = {"nivel": lvl, "modulo": "CONTROLLER", "mensagem": msg, "timestamp": datetime.datetime.now().isoformat()} >> "%BOOT_LOGGER%"
echo          sb.table("simulation_logs").insert(data).execute() >> "%BOOT_LOGGER%"
echo      except: pass >> "%BOOT_LOGGER%"
echo if __name__ == "__main__": >> "%BOOT_LOGGER%"
echo      if len(sys.argv) ^> 2: log(sys.argv[1], sys.argv[2]) >> "%BOOT_LOGGER%"

echo import os > "%DB_PATCHER%"
echo def patch_file(fp, old, new): >> "%DB_PATCHER%"
echo      if not os.path.exists(fp): return >> "%DB_PATCHER%"
echo      with open(fp, 'r', encoding='utf-8') as f: c = f.read() >> "%DB_PATCHER%"
echo      if old in c: >> "%DB_PATCHER%"
echo          with open(fp, 'w', encoding='utf-8') as f: f.write(c.replace(old, new)) >> "%DB_PATCHER%"
echo if __name__ == "__main__": >> "%DB_PATCHER%"
echo      patch_file(r"%BASE_DIR%\sumo-backend\logger_utils.py", "application_logs", "simulation_logs") >> "%DB_PATCHER%"

if exist "%VENV_PYTHON%" "%VENV_PYTHON%" "%DB_PATCHER%" >> "%LOCAL_LOG%" 2>&1

:MAIN_MENU
cls
echo.
echo =========================================
echo            FLUXUS MANAGER
echo =========================================
echo.
echo       1. INICIAR (API + Docker + Vercel)
echo       2. INICIAR FRONT-END (npm run dev)
echo       3. PARAR TUDO
echo       4. SAIR
echo.
set /p "opt= > Opcao: "

if "%opt%"=="1" goto SEQ_START
if "%opt%"=="2" goto SEQ_FRONT_START
if "%opt%"=="3" goto SEQ_STOP
if "%opt%"=="4" exit
goto MAIN_MENU

:SEQ_START
call :REGISTER_LOG "INFO" "START BACKEND SEQUENCE"

if not exist "%VENV_PYTHON%" (
    echo [ERRO] Venv nao encontrado.
    pause
    goto MAIN_MENU
)

docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Iniciando Docker...
    start "" "%DOCKER_EXE%"
    :WAIT_DOCKER
    timeout /t 5 /nobreak >nul
    docker info >nul 2>&1
    if %errorlevel% neq 0 goto WAIT_DOCKER
)

echo [INFO] Limpando processos antigos...
docker-compose -f "%BASE_DIR%\docker-compose.yml" down --remove-orphans >> "%LOCAL_LOG%" 2>&1
taskkill /F /IM ngrok.exe >nul 2>&1
if exist "%URL_FILE%" del "%URL_FILE%"

echo [INFO] Subindo containers...
docker-compose -f "%BASE_DIR%\docker-compose.yml" up -d --build >> "%LOCAL_LOG%" 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Falha no Docker.
    pause
    goto MAIN_MENU
)

echo [INFO] Aguardando API...
set /a try=0
:CHECK_API
set /a try+=1
timeout /t 3 /nobreak >nul
curl -s http://127.0.0.1:5000/ >nul
if %errorlevel% equ 0 goto API_OK
if %try% geq 60 (
    echo [ERRO] Timeout API.
    docker logs sumo-backend
    pause
    goto MAIN_MENU
)
goto CHECK_API

:API_OK
echo [INFO] API Online. Iniciando Tunel...
taskkill /FI "WINDOWTITLE eq FLUXUS TUNNEL" /F >nul 2>&1

if not exist "%SYNC_SCRIPT%" (
    echo [ERRO] Script de sync nao encontrado.
    pause
    goto MAIN_MENU
)

:: Inicia o Tunel (Janela Visível)
start "FLUXUS TUNNEL" "%VENV_PYTHON%" "%SYNC_SCRIPT%"
call :REGISTER_LOG "INFO" "Sistema Online"

echo.
echo [AGUARDE] Obtendo Link Publico...
:WAIT_URL
timeout /t 2 /nobreak >nul
if exist "%URL_FILE%" goto SHOW_URL
goto WAIT_URL

:SHOW_URL
set /p PUBLIC_URL=<"%URL_FILE%"
echo.
echo ==================================================
echo  SISTEMA ONLINE!
echo ==================================================
echo.
echo  Link Publico: %PUBLIC_URL%
echo  (O Supabase foi atualizado automaticamente)
echo.
echo ==================================================
echo.
echo [ENTER] Voltar ao Menu.
pause >nul
goto MAIN_MENU

:SEQ_FRONT_START
call :REGISTER_LOG "INFO" "Start Frontend"

if not exist "%FRONT_PATH%" (
    echo [ERRO] Pasta nao encontrada: %FRONT_PATH%
    pause
    goto MAIN_MENU
)

taskkill /FI "WINDOWTITLE eq FRONT-END SERVER" /F >nul 2>&1
echo [INFO] Abrindo novo terminal para o Frontend...
cd /d "%FRONT_PATH%"

:: CORREÇÃO: Removidos parenteses do echo para evitar erro de sintaxe
if not exist "node_modules" (
    echo [INFO] Instalando dependencias do Node...
    call npm install
)

start "FRONT-END SERVER" cmd /k npm run dev

cd /d "%BASE_DIR%"
echo [OK] Front-end iniciado.
pause
goto MAIN_MENU

:SEQ_STOP
call :REGISTER_LOG "WARNING" "Stop All"
docker-compose stop >> "%LOCAL_LOG%" 2>&1
docker-compose down --remove-orphans >> "%LOCAL_LOG%" 2>&1
taskkill /F /IM "Docker Desktop.exe" >nul 2>&1
taskkill /F /IM "com.docker.backend.exe" >nul 2>&1
taskkill /F /IM "dockerd.exe" >nul 2>&1
taskkill /F /IM ngrok.exe >nul 2>&1
taskkill /FI "WINDOWTITLE eq FLUXUS TUNNEL" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq FRONT-END SERVER" /F >nul 2>&1
taskkill /f /im node.exe >nul 2>&1
if exist "%URL_FILE%" del "%URL_FILE%"
echo [OK] Parado.
timeout /t 2 >nul
goto MAIN_MENU

:REGISTER_LOG
echo [%TIME%] [%~1] %~2 >> "%LOCAL_LOG%"
if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" "%BOOT_LOGGER%" "%~1" "%~2" >nul 2>&1
)
exit /b