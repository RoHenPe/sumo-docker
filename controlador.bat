@echo off
setlocal enabledelayedexpansion
:: Configura o terminal para UTF-8 para aceitar o V de Check (✓)
chcp 65001 >nul
title FLUXUS Manager [Diagnostico Ativo]
color 0F

:MAIN_MENU
cls
echo.
echo   =========================================
echo          PAINEL DE CONTROLE DOCKER
echo   =========================================
echo.
echo    [1] LIGAR SISTEMA  (Start + Validacao)
echo    [2] DESLIGAR TUDO  (Stop + Limpeza)
echo    [3] SAIR
echo.
set /p "opt= > Escolha uma opcao: "

if "%opt%"=="1" goto INIT_STARTUP
if "%opt%"=="2" goto STOP_SYSTEM
if "%opt%"=="3" exit
goto MAIN_MENU

:: =========================================================
::                 ROTINA DE INICIALIZAÇÃO
:: =========================================================
:INIT_STARTUP
:: Definição dos Simbolos (UTF-8)
set "icon_ok=[✓]"
set "icon_fail=[X]"
set "icon_wait=[...]"

:: Estados iniciais
set "step1=%icon_wait%"
set "step2=[ ]"
set "step3=[ ]"
set "status_msg=A preparar ambiente..."

:: Define o primeiro passo lógico
set "NEXT_STEP=START_DOCKER"
goto DRAW_CHECKLIST

:DRAW_CHECKLIST
cls
echo.
echo   =========================================
echo           INICIALIZANDO O SISTEMA
echo   =========================================
echo.
echo    %step1%  1. Iniciar Containers (Docker)
echo    %step2%  2. Conectar ao Backend (Python)
echo    %step3%  3. Validar API (Porta 5000)
echo.
echo   -----------------------------------------
echo   Status: %status_msg%
echo   =========================================
echo.
goto %NEXT_STEP%

:: --- PASSO 1: DOCKER UP ---
:START_DOCKER
set "status_msg=Levantando o Docker (Aguarde)..."
set "NEXT_STEP=RUN_DOCKER_CMD"
goto DRAW_CHECKLIST

:RUN_DOCKER_CMD
:: Tenta subir o docker. Se falhar, captura o erro.
docker-compose up -d >nul 2>&1
if %errorlevel% neq 0 (
    set "step1=%icon_fail%"
    set "status_msg=ERRO: O Docker nao iniciou!"
    goto ERROR_HANDLER
)

set "step1=%icon_ok%"
set "step2=%icon_wait%"
set "status_msg=Docker OK. A aguardar o Backend..."
set "NEXT_STEP=CHECK_API_LOOP"
goto DRAW_CHECKLIST

:: --- PASSO 2: AGUARDAR CONEXÃO (LOOP DE 10 TENTATIVAS) ---
:CHECK_API_LOOP
set /a attempts=0

:RETRY_LOOP
set /a attempts+=1
if %attempts% geq 15 (
    set "step2=%icon_fail%"
    set "status_msg=ERRO: O Backend nao respondeu a tempo."
    goto ERROR_HANDLER
)

timeout /t 2 /nobreak >nul
curl -s -f http://localhost:5000 >nul 2>&1
if %errorlevel% equ 0 goto API_SUCCESS

:: Animação visual enquanto espera
if "%step2%"=="%icon_wait%" (set "step2=[/]") else (set "step2=%icon_wait%")
:: Atualiza a tela sem perder o loop
cls
echo.
echo   =========================================
echo           INICIALIZANDO O SISTEMA
echo   =========================================
echo.
echo    %step1%  1. Iniciar Containers (Docker)
echo    %step2%  2. Conectar ao Backend (Python)
echo    %step3%  3. Validar API (Porta 5000)
echo.
echo   -----------------------------------------
echo   Status: Tentativa %attempts%/15... (O Python esta carregando)
echo   =========================================
goto RETRY_LOOP

:API_SUCCESS
set "step2=%icon_ok%"
set "step3=%icon_wait%"
set "status_msg=Conexao estabelecida!"
set "NEXT_STEP=FINALIZE"
goto DRAW_CHECKLIST

:: --- PASSO 3: SUCESSO FINAL ---
:FINALIZE
timeout /t 1 /nobreak >nul
set "step3=%icon_ok%"
set "status_msg=SISTEMA ONLINE! Pode abrir o navegador."
color 0A
set "NEXT_STEP=END_START"
goto DRAW_CHECKLIST

:END_START
echo.
echo   Pressione qualquer tecla para voltar ao menu...
pause >nul
goto MAIN_MENU

:: =========================================================
::              DIAGNÓSTICO DE ERROS (AUTO-LOG)
:: =========================================================
:ERROR_HANDLER
color 0C
cls
echo.
echo   =========================================
echo           FALHA NA INICIALIZACAO %icon_fail%
echo   =========================================
echo.
echo   O sistema nao conseguiu conectar.
echo   Abaixo estao os ultimos erros do container:
echo   -----------------------------------------
echo.
:: EXIBE O LOG REAL DO ERRO PARA O USUARIO VER
docker-compose logs --tail=20 sumo-backend
echo.
echo   -----------------------------------------
echo   DICA: Verifique se o arquivo .env existe e se os caminhos no docker-compose estao certos.
echo.
pause
goto MAIN_MENU

:: =========================================================
::                 ROTINA DE DESLIGAMENTO
:: =========================================================
:STOP_SYSTEM
cls
color 0E
echo.
echo   =========================================
echo           DESLIGANDO O SISTEMA
echo   =========================================
echo.
echo   [!] Parando containers...
docker-compose down
echo.
echo   %icon_ok% Containers parados e removidos.
echo   %icon_ok% Porta 5000 liberada.
echo.
pause
color 0F
goto MAIN_MENU