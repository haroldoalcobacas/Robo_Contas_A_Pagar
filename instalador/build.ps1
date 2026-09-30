# Gera o executável (PyInstaller) e o instalador (Inno Setup).
# Uso, na raiz do projeto:  powershell -ExecutionPolicy Bypass -File instalador\build.ps1

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
$inst = $PSScriptRoot
Set-Location $raiz

Write-Host "1/3 Instalando dependencias..."
python -m pip install -q -r requirements.txt pyinstaller

Write-Host "2/3 Gerando RoboContas.exe..."
python "$inst\gerar_icone.py"
python -m PyInstaller --noconfirm --clean --windowed `
    --name RoboContas `
    --icon "$inst\robo.ico" `
    --add-data "$raiz\dados\caixa_de_entrada;exemplos\caixa_de_entrada" `
    --hidden-import pystray._win32 `
    --hidden-import keyring.backends.Windows `
    --distpath "$inst\dist" `
    --workpath "$inst\build" `
    --specpath "$inst" `
    "$raiz\main.py"

Write-Host "3/3 Gerando o instalador..."
$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    Write-Warning "Inno Setup 6 nao encontrado. Instale com:"
    Write-Warning "  winget install JRSoftware.InnoSetup"
    Write-Warning "O programa ja esta pronto em instalador\dist\RoboContas\"
    exit 1
}
# Versao: unico lugar e robo/__init__.py. Build: data/hora desta geracao.
$versao = (python -c "import robo; print(robo.__version__)").Trim()
$build = Get-Date -Format "yyyyMMdd-HHmm"
& $iscc /Q "/DVersao=$versao" "/DBuild=$build" "$inst\RoboContas.iss"
if ($LASTEXITCODE -ne 0) { Write-Error "Falha ao gerar o instalador."; exit 1 }

$setup = Get-ChildItem "$inst\saida\Setup_RoboContas_*.exe" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host ""
Write-Host "Pronto! Versao $versao (build $build):"
Write-Host "  $($setup.FullName)"
