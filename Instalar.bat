@echo off
rem ==========================================================================
rem  Robo de Contas a Pagar - INSTALAR no Windows
rem
rem  1. Gera o programa (RoboContas.exe) e o instalador com o codigo atual.
rem  2. Abre o instalador: escolha as opcoes e clique em Instalar.
rem  Ao final, o painel abre sozinho e o icone fica ao lado do relogio.
rem
rem  Nao pede senha de administrador. Para desinstalar: Configuracoes do
rem  Windows > Aplicativos > Robo de Contas a Pagar.
rem ==========================================================================
cd /d "%~dp0"

echo Gerando o instalador com a versao atual do codigo (1 a 3 minutos)...
powershell -NoProfile -ExecutionPolicy Bypass -File "instalador\build.ps1"
if errorlevel 1 (
    echo.
    echo Nao foi possivel gerar o instalador. Veja as mensagens acima.
    pause
    exit /b 1
)

rem O mais recente primeiro (/o-d): cada geracao tem nome com data e hora
for /f "delims=" %%F in ('dir /b /o-d "instalador\saida\Setup_RoboContas_*.exe" 2^>nul') do (
    set "SETUP=instalador\saida\%%F"
    goto :achou
)
:achou
if not defined SETUP (
    echo Instalador nao encontrado em instalador\saida\
    pause
    exit /b 1
)

echo Abrindo o instalador: %SETUP%
start "" "%SETUP%"
