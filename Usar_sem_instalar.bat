@echo off
rem ==========================================================================
rem  Robo de Contas a Pagar - usar SEM instalar (direto do codigo-fonte)
rem
rem  Abre o icone ao lado do relogio e o painel de configuracoes.
rem  Tudo fica dentro desta pasta: saida\ (planilha e anexos), logs\, .env
rem  Precisa do Python 3.10+ instalado.
rem ==========================================================================
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python nao encontrado. Instale em https://www.python.org/downloads/
    echo e marque a opcao "Add python.exe to PATH".
    pause
    exit /b 1
)

python -c "import openpyxl, pypdf, pystray, PIL, keyring" >nul 2>nul
if errorlevel 1 (
    echo Instalando as bibliotecas necessarias ^(so na primeira vez^)...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Falha ao instalar as bibliotecas.
        pause
        exit /b 1
    )
)

rem pythonw roda sem janela preta de console
set "PY=pythonw"
where pythonw >nul 2>nul || set "PY=python"

rem 1) Icone na bandeja (se ja estiver aberto, nao abre outro)
start "" %PY% main.py
rem 2) Painel, depois que o icone subir
timeout /t 2 /nobreak >nul
start "" %PY% main.py --config
