@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title FLUXUS MANAGER
color 0F

set "BASE_DIR=%~dp0"
if "%BASE_DIR:~-1%"=="\" set "BASE_DIR=%BASE_DIR:~0,-1%"

set "VENV_DIR=%BASE_DIR%\sumo-backend\venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
set "REQUIREMENTS_PATH=%BASE_DIR%\sumo-backend\requirements.txt"
set "BOOT_LOGGER=%BASE_DIR%\boot_logger.py"
set "DB_PATCHER=%BASE_DIR%\db_patcher.py"
set "SYNC_SCRIPT=%BASE_DIR%\vercel_sync.py"
set "DOCKER_EXE=C:\Program Files\Docker\Docker\Docker Desktop.exe"
set "LOG_DIR=%BASE_DIR%\scenarios\logs"
set "LOCAL_LOG=%LOG_DIR%\controlador.log"
set "FRONT_PATH=%BASE_DIR%\site-web"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
echo [INIT] Started > "%LOCAL_LOG%"

python --version >nul 2>&1
if %errorlevel% neq 0 (
    cls
    echo [ERRO] Python nao encontrado.
    pause
    exit
)

if not exist "%VENV_DIR%" (
    python -m venv "%VENV_DIR%" >> "%LOCAL_LOG%" 2>&1
    if errorlevel 1 (
        echo [ERRO] Falha ao criar Venv.
        pause
        exit
    )
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
set "st_wait=[ ]"
set "st_work=[..]"
set "st_ok=[OK]"
set "st_err=[X]"

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
set "s1=%st_wait%" & set "s2=%st_wait%" & set "s3=%st_wait%" & set "s4=%st_wait%" & set "s5=%st_wait%" & set "s6=%st_wait%"
call :REGISTER_LOG "INFO" "START BACKEND SEQUENCE"

set "s1=%st_work%" & set "msg=Verificando Venv..."
call :DRAW_START
if exist "%VENV_PYTHON%" (
    set "s1=%st_ok%"
) else (
    set "s1=%st_err%" & set "msg=Erro Venv"
    goto START_FAIL
)

set "s2=%st_work%" & set "msg=Verificando Conexao..."
call :DRAW_START
curl -s --head https://supabase.com >nul
if %errorlevel% neq 0 (
    set "s2=%st_err%" & set "msg=Sem Internet"
    goto START_FAIL
)
set "s2=%st_ok%"

set "s3=%st_work%" & set "msg=Verificando Docker..."
call :DRAW_START
docker info >nul 2>&1
if %errorlevel% equ 0 goto DOCKER_RUNNING

set "msg=Iniciando Docker Desktop..."
call :DRAW_START
start "" "%DOCKER_EXE%"
:WAIT_DOCKER_LOOP
timeout /t 3 /nobreak >nul
docker info >nul 2>&1
if %errorlevel% neq 0 goto WAIT_DOCKER_LOOP

:DOCKER_RUNNING
set "s3=%st_ok%"

set "s4=%st_work%" & set "msg=Subindo Containers..."
call :DRAW_START
docker-compose -f "%BASE_DIR%\docker-compose.yml" up -d --build >> "%LOCAL_LOG%" 2>&1
if %errorlevel% neq 0 (
    set "s4=%st_err%" & set "msg=Erro Docker Build"
    goto START_FAIL
)
set "s4=%st_ok%"

set "s5=%st_work%" & set "msg=Aguardando API..."
call :DRAW_START
set /a try=0
:CHECK_API
set /a try+=1
set "msg=Aguardando API (%try%/40)..."
call :DRAW_START
timeout /t 3 /nobreak >nul
curl -s http://localhost:5000/ >nul
if %errorlevel% equ 0 goto API_OK
if %try% geq 40 (
    set "s5=%st_err%" & set "msg=TIMEOUT API"
    goto START_FAIL
)
goto CHECK_API
:API_OK
set "s5=%st_ok%"

set "s6=%st_work%" & set "msg=Iniciando Tunel..."
call :DRAW_START
taskkill /FI "WINDOWTITLE eq FLUXUS TUNNEL" /F >nul 2>&1
if not exist "%SYNC_SCRIPT%" (
    set "s6=%st_err%" & set "msg=Script Sync Ausente"
    goto START_FAIL
)
start "FLUXUS TUNNEL" /min "%VENV_PYTHON%" "%SYNC_SCRIPT%"
set "s6=%st_ok%"
set "msg=SISTEMA ONLINE."
call :DRAW_START
call :REGISTER_LOG "INFO" "Sistema Online"

echo.
echo [ENTER] Voltar ao Menu
pause >nul
goto MAIN_MENU

:SEQ_FRONT_START
cls
echo.
echo [2] INICIANDO FRONT-END...
call :REGISTER_LOG "INFO" "Start Frontend"
if not exist "%FRONT_PATH%" (
    echo [ERRO] Pasta nao encontrada
    pause
    goto MAIN_MENU
)
taskkill /FI "WINDOWTITLE eq FRONT-END SERVER" /F >nul 2>&1
cd /d "%FRONT_PATH%"
if not exist "node_modules" call npm install
start "FRONT-END SERVER" cmd /k npm run dev
cd /d "%BASE_DIR%"
echo [OK] Front-end iniciado.
pause
goto MAIN_MENU

:SEQ_STOP
cls
echo.
echo PARANDO TUDO...
call :REGISTER_LOG "WARNING" "Stop All"
docker-compose stop >> "%LOCAL_LOG%" 2>&1
docker-compose down >> "%LOCAL_LOG%" 2>&1
taskkill /F /IM "Docker Desktop.exe" >nul 2>&1
taskkill /F /IM "com.docker.backend.exe" >nul 2>&1
taskkill /F /IM "dockerd.exe" >nul 2>&1
taskkill /FI "WINDOWTITLE eq FLUXUS TUNNEL" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq FRONT-END SERVER" /F >nul 2>&1
taskkill /f /im node.exe >nul 2>&1
echo [OK] Parado.
timeout /t 2 >nul
goto MAIN_MENU

:START_FAIL
call :DRAW_START
echo.
echo [ERRO] Falha. Verifique %LOCAL_LOG%
powershell -command "Get-Content '%LOCAL_LOG%' -Tail 10"
pause
goto MAIN_MENU

:DRAW_START
cls
echo.
echo      [1] INICIALIZACAO BACKEND
echo      ------------------------------
echo      %s1%  1. Venv
echo      %s2%  2. Internet
echo      %s3%  3. Docker
echo      %s4%  4. Containers
echo      %s5%  5. API Local
echo      %s6%  6. Tunel Remoto
echo      ------------------------------
echo Status: %msg%
exit /b

:REGISTER_LOG
echo [%TIME%] [%~1] %~2 >> "%LOCAL_LOG%"
if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" "%BOOT_LOGGER%" "%~1" "%~2" >nul 2>&1
)
exit /b