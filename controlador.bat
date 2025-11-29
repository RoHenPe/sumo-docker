@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title FLUXUS MANAGER [Safe Generation]
color 0F

:: =========================================================
::  1. CONFIGURAÇÕES
:: =========================================================
set "BASE_DIR=%~dp0"
if "%BASE_DIR:~-1%"=="\" set "BASE_DIR=%BASE_DIR:~0,-1%"

set "VENV_PYTHON=%BASE_DIR%\sumo-backend\venv\Scripts\python.exe"
set "BOOT_LOGGER=%BASE_DIR%\boot_logger.py"
set "DB_PATCHER=%BASE_DIR%\db_patcher.py"
set "DOCKER_EXE=C:\Program Files\Docker\Docker\Docker Desktop.exe"

set "LOG_DIR=%BASE_DIR%\scenarios\logs"
set "LOCAL_LOG=%LOG_DIR%\controlador.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
echo [INIT] Sessao iniciada > "%LOCAL_LOG%"

:: =========================================================
::  2. GERAR FERRAMENTAS (SEM BLOCOS - EVITA ERRO DE SINTAXE)
:: =========================================================

:: --- Gerando Patcher ---
echo import os > "%DB_PATCHER%"
echo def patch_file(fp, old, new): >> "%DB_PATCHER%"
echo     if not os.path.exists(fp): return >> "%DB_PATCHER%"
echo     with open(fp, 'r', encoding='utf-8') as f: c = f.read() >> "%DB_PATCHER%"
echo     if old in c: >> "%DB_PATCHER%"
echo         with open(fp, 'w', encoding='utf-8') as f: f.write(c.replace(old, new)) >> "%DB_PATCHER%"
echo if __name__ == "__main__": >> "%DB_PATCHER%"
echo     patch_file(r"%BASE_DIR%\sumo-backend\logger_utils.py", "application_logs", "simulation_logs") >> "%DB_PATCHER%"

:: Executa Patcher
if exist "%VENV_PYTHON%" "%VENV_PYTHON%" "%DB_PATCHER%" >> "%LOCAL_LOG%" 2>&1

:: --- Gerando Logger ---
echo import os, sys, datetime > "%BOOT_LOGGER%"
echo from dotenv import load_dotenv >> "%BOOT_LOGGER%"
echo from supabase import create_client >> "%BOOT_LOGGER%"
echo try: load_dotenv() >> "%BOOT_LOGGER%"
echo except: pass >> "%BOOT_LOGGER%"
echo url = os.getenv("SUPABASE_URL") >> "%BOOT_LOGGER%"
echo key = os.getenv("SUPABASE_KEY") >> "%BOOT_LOGGER%"
echo def log(lvl, msg): >> "%BOOT_LOGGER%"
echo     if not url or not key: return >> "%BOOT_LOGGER%"
echo     try: >> "%BOOT_LOGGER%"
echo         sb = create_client(url, key) >> "%BOOT_LOGGER%"
echo         data = {"nivel": lvl, "modulo": "CONTROLLER", "mensagem": msg, "timestamp": datetime.datetime.now().isoformat()} >> "%BOOT_LOGGER%"
echo         sb.table("simulation_logs").insert(data).execute() >> "%BOOT_LOGGER%"
echo     except: pass >> "%BOOT_LOGGER%"
echo if __name__ == "__main__": >> "%BOOT_LOGGER%"
echo     if len(sys.argv) ^> 2: log(sys.argv[1], sys.argv[2]) >> "%BOOT_LOGGER%"

:MAIN_MENU
:: Icones
set "st_wait=[ ]"
set "st_work=[..]"
set "st_ok=[OK]"
set "st_err=[X]"
set "st_warn=[!]"

cls
echo.
echo    =========================================
echo           FLUXUS MANAGER
echo    =========================================
echo.
echo    1. INICIAR (Validacao + Docker)
echo    2. PARAR TUDO
echo    3. SAIR
echo.
set /p "opt= > Opcao: "

if "%opt%"=="1" goto SEQ_START
if "%opt%"=="2" goto SEQ_STOP
if "%opt%"=="3" exit
goto MAIN_MENU

:: =========================================================
::  FUNÇÃO LOG
:: =========================================================
:REGISTER_LOG
echo [%TIME%] [%~1] %~2 >> "%LOCAL_LOG%"
if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" "%BOOT_LOGGER%" "%~1" "%~2" >nul 2>&1
)
exit /b

:: =========================================================
::  INICIAR
:: =========================================================
:SEQ_START
set "s1=%st_wait%" & set "s2=%st_wait%" & set "s3=%st_wait%" & set "s4=%st_wait%" & set "s5=%st_wait%"
call :REGISTER_LOG "INFO" "--- START ---"

:: PASSO 1: GIT/VENV
set "s1=%st_work%"
set "msg=Verificando Ambiente..."
call :DRAW_START

if exist "%BASE_DIR%\sumo-backend\venv\Scripts\activate.bat" (
    call "%BASE_DIR%\sumo-backend\venv\Scripts\activate.bat"
    
    git --version >nul 2>&1
    if !errorlevel! neq 0 (
        set "s1=%st_warn%"
        call :REGISTER_LOG "WARNING" "Git nao encontrado (Seguindo sem)."
    ) else (
        set "s1=%st_ok%"
    )
) else (
    set "s1=%st_err%" & set "msg=Erro: Venv nao existe"
    call :REGISTER_LOG "CRITICAL" "Venv ausente."
    goto START_FAIL
)

:: PASSO 2: CONEXÃO
set "s2=%st_work%"
set "msg=Testando Conexao..."
call :DRAW_START

curl -s --head https://supabase.com >nul
if %errorlevel% neq 0 (
    set "s2=%st_err%" & set "msg=Sem Internet"
    call :REGISTER_LOG "CRITICAL" "Sem conexao."
    goto START_FAIL
)
set "s2=%st_ok%"

:: PASSO 3: DOCKER
set "s3=%st_work%"
set "msg=Motor Docker..."
call :DRAW_START

docker info >nul 2>&1
if %errorlevel% neq 0 (
    set "msg=Iniciando Docker..."
    call :DRAW_START
    start "" "%DOCKER_EXE%"
    :WAIT_DOCKER
    timeout /t 3 /nobreak >nul
    docker info >nul 2>&1
    if %errorlevel% neq 0 goto WAIT_DOCKER
)
set "s3=%st_ok%"

:: PASSO 4: CONTAINERS
set "s4=%st_work%"
set "msg=Subindo Containers (Build)..."
call :DRAW_START

docker-compose up -d --build >> "%LOCAL_LOG%" 2>&1
if %errorlevel% neq 0 (
    set "s4=%st_err%" & set "msg=Erro Docker (Veja Log)"
    call :REGISTER_LOG "CRITICAL" "Falha no build."
    goto START_FAIL
)
set "s4=%st_ok%"

:: PASSO 5: API
set "s5=%st_work%"
set "msg=Aguardando API..."
call :DRAW_START

set /a try=0
:CHECK_API
set /a try+=1
set "msg=Carregando (%try%/40)..."
call :DRAW_START

timeout /t 3 /nobreak >nul
curl -s http://localhost:5000/ >nul
if %errorlevel% equ 0 goto SUCCESS

if %try% geq 40 (
    set "s5=%st_err%" & set "msg=TIMEOUT API"
    call :REGISTER_LOG "ERROR" "Timeout 5000."
    goto START_FAIL
)
goto CHECK_API

:SUCCESS
set "s5=%st_ok%"
set "msg=SISTEMA ONLINE."
call :DRAW_START
call :REGISTER_LOG "INFO" "Sistema Online."
echo.
echo    [ENTER] Voltar ao Menu
pause >nul
goto MAIN_MENU

:START_FAIL
call :DRAW_START
echo.
echo    [ERRO] Detalhes em: %LOCAL_LOG%
echo.
echo    LOG DE ERRO:
echo    ------------
powershell -command "Get-Content '%LOCAL_LOG%' -Tail 10"
pause
goto MAIN_MENU

:DRAW_START
cls
echo.
echo    [1] INICIALIZACAO
echo    ------------------------------
echo    %s1%  1. Venv / Git
echo    %s2%  2. Conexao Nuvem
echo    %s3%  3. Motor Docker
echo    %s4%  4. Containers Backend
echo    %s5%  5. API Python (Porta 5000)
echo    ------------------------------
echo    Status: %msg%
exit /b

:: =========================================================
::  PARAR
:: =========================================================
:SEQ_STOP
cls
echo.
echo    PARANDO SISTEMA...
echo.
call :REGISTER_LOG "WARNING" "--- STOP ---"

echo    [..] Parando containers...
docker-compose stop >> "%LOCAL_LOG%" 2>&1
echo    [..] Removendo rede...
docker-compose down >> "%LOCAL_LOG%" 2>&1

echo    [OK] Finalizado.
call :REGISTER_LOG "INFO" "Parado."
timeout /t 2 >nul
goto MAIN_MENU