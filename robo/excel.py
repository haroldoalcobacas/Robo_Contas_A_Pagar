"""
Convivência com o Excel: saber se a planilha está aberta e, se o usuário
autorizar, salvar e fechar a planilha antes de o robô gravar nela.

Por que isso importa: o Excel trava o arquivo enquanto ele está aberto, e o
Windows recusa a gravação. Verificar ANTES de escanear evita processar tudo
para só no final descobrir que não dá para salvar.

Salvar e fechar usa a automação do próprio Excel (COM) via PowerShell, que
já vem no Windows: nenhuma biblioteca extra.
"""

import base64
import ctypes
import os
import subprocess
import time
from pathlib import Path

SEM_JANELA = 0x08000000   # CREATE_NO_WINDOW

# Localiza a pasta de trabalho aberta no Excel e a fecha salvando.
# O caminho chega pela variável de ambiente, sem problema com acentos.
#
# Como achar o Excel: o jeito comum (GetActiveObject) falha logo depois de
# o usuário abrir o Excel, porque ele só se registra para automação após
# perder o foco. Por isso também procuramos as janelas do Excel (classe
# XLMAIN > XLDESK > EXCEL7) e pegamos o objeto pela acessibilidade do
# Windows, que funciona sempre e acha todas as instâncias abertas.
_SCRIPT = r"""
$alvo = $env:ROBO_PLANILHA
$nome = [IO.Path]::GetFileName($alvo)
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class JanelasExcel {
    [DllImport("oleacc.dll")]
    static extern int AccessibleObjectFromWindow(IntPtr hwnd, uint id,
        ref Guid iid, [MarshalAs(UnmanagedType.IDispatch)] out object obj);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    static extern IntPtr FindWindowEx(IntPtr pai, IntPtr depois,
        string classe, string titulo);
    public static List<object> Janelas() {
        var lista = new List<object>();
        var iid = new Guid("00020400-0000-0000-C000-000000000046");
        IntPtr principal = IntPtr.Zero;
        while ((principal = FindWindowEx(IntPtr.Zero, principal, "XLMAIN",
                null)) != IntPtr.Zero) {
            IntPtr mesa = FindWindowEx(principal, IntPtr.Zero, "XLDESK", null);
            IntPtr janela = FindWindowEx(mesa, IntPtr.Zero, "EXCEL7", null);
            object obj;
            if (janela != IntPtr.Zero && AccessibleObjectFromWindow(
                    janela, 0xFFFFFFF0, ref iid, out obj) == 0 && obj != null)
                lista.Add(obj);
        }
        return lista;
    }
}
'@
$livros = @()
foreach ($janela in [JanelasExcel]::Janelas()) {
    try { $livros += @($janela.Application.Workbooks) } catch {}
}
if ($livros.Count -eq 0) {
    try {
        $xl = [Runtime.InteropServices.Marshal]::GetActiveObject('Excel.Application')
        $livros = @($xl.Workbooks)
    } catch { Write-Output 'SEM_EXCEL'; exit 3 }
}
$livro = $livros | Where-Object { $_.FullName -ieq $alvo } | Select-Object -First 1
if (-not $livro) {
    $mesmoNome = @($livros | Where-Object { $_.Name -ieq $nome })
    if ($mesmoNome.Count -eq 1) { $livro = $mesmoNome[0] }
}
if (-not $livro) { Write-Output 'NAO_ENCONTRADA'; exit 4 }
try { $livro.Close($true) } catch { Write-Output 'OCUPADO'; exit 5 }
Write-Output 'FECHADA'
"""

MENSAGENS = {
    "SEM_EXCEL": "o Excel não respondeu (a planilha pode estar aberta em "
                 "outro programa)",
    "NAO_ENCONTRADA": "a planilha não foi encontrada entre os arquivos "
                      "abertos no Excel",
    "OCUPADO": "o Excel está ocupado (há uma célula em edição ou uma janela "
               "de diálogo aberta)",
}


def planilha_aberta(arquivo: Path) -> bool:
    """True se outro programa (em geral o Excel) trava o arquivo."""
    if not arquivo.exists():
        return False
    try:
        with open(arquivo, "r+b"):
            return False
    except PermissionError:
        return True
    except OSError:
        return False


def salvar_e_fechar(arquivo: Path, espera: float = 5.0) -> tuple[bool, str]:
    """
    Pede ao Excel para salvar e fechar a planilha.
    Devolve (sucesso, mensagem para o usuário).
    """
    comando = base64.b64encode(_SCRIPT.encode("utf-16-le")).decode()
    ambiente = dict(os.environ, ROBO_PLANILHA=str(arquivo.resolve()))
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-EncodedCommand", comando],
            capture_output=True, text=True, timeout=30, env=ambiente,
            creationflags=SEM_JANELA)
        codigo = (r.stdout or "").strip().splitlines()[-1:] or [""]
        codigo = codigo[0]
    except (OSError, subprocess.TimeoutExpired) as erro:
        return False, f"não foi possível falar com o Excel ({erro})"

    if codigo != "FECHADA":
        return False, MENSAGENS.get(codigo, "o Excel não conseguiu fechar "
                                            "a planilha")

    # O Excel libera o arquivo logo após fechar; aguarda um instante
    limite = time.monotonic() + espera
    while planilha_aberta(arquivo) and time.monotonic() < limite:
        time.sleep(0.3)
    if planilha_aberta(arquivo):
        return False, "a planilha foi fechada, mas o arquivo continua travado"
    return True, "planilha salva e fechada"


# ---------------------------------------------------------------------------
# Pergunta ao usuário fora do tkinter (ícone da bandeja)
# ---------------------------------------------------------------------------
_MB_YESNO, _MB_ICONWARNING, _MB_ICONERROR = 0x04, 0x30, 0x10
_MB_TOPMOST, _MB_SETFOREGROUND, _IDYES = 0x40000, 0x10000, 6

TEXTO_PERGUNTA = (
    "A planilha {nome} está aberta no Excel.\n\n"
    "O robô precisa dela fechada para gravar as contas.\n\n"
    "Deseja que o robô SALVE suas alterações e FECHE a planilha agora?\n\n"
    "Sim: salva, fecha e começa a varredura.\n"
    "Não: você fecha a planilha e depois escaneia de novo.")
TEXTO_FECHE = "Feche a planilha {nome} no Excel e escaneie de novo."


def perguntar_nativo(titulo: str, texto: str) -> bool:
    """Caixa Sim/Não do Windows, sempre por cima das outras janelas."""
    estilo = _MB_YESNO | _MB_ICONWARNING | _MB_TOPMOST | _MB_SETFOREGROUND
    return ctypes.windll.user32.MessageBoxW(0, texto, titulo,
                                            estilo) == _IDYES


def avisar_nativo(titulo: str, texto: str, erro: bool = False) -> None:
    icone = _MB_ICONERROR if erro else _MB_ICONWARNING
    ctypes.windll.user32.MessageBoxW(0, texto, titulo,
                                     icone | _MB_TOPMOST | _MB_SETFOREGROUND)
