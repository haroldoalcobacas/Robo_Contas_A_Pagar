"""
Integração com o Windows:
- Iniciar o ícone da bandeja junto com o Windows (registro, chave Run).
- Agendador de Tarefas: varredura ao fazer login e todo dia num horário.

Nada aqui exige administrador: tudo é criado para o usuário atual.
"""

import os
import subprocess
import sys
import tempfile
import winreg
from pathlib import Path
from xml.sax.saxutils import escape

from . import config

NOME_APP = "RoboContasAPagar"
CHAVE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
SEM_JANELA = 0x08000000   # CREATE_NO_WINDOW: schtasks sem piscar console


def comando_base() -> list[str]:
    """Como chamar o próprio programa, sem abrir janela de console."""
    if config.CONGELADO:
        return [sys.executable]
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    interpretador = pythonw if pythonw.exists() else Path(sys.executable)
    return [str(interpretador), str(config.RAIZ / "main.py")]


def abrir_processo(*args: str) -> None:
    """Abre outra instância do programa (ex.: a janela de configurações)."""
    subprocess.Popen(comando_base() + list(args), cwd=config.RAIZ,
                     creationflags=SEM_JANELA)


# ---------------------------------------------------------------------------
# Iniciar com o Windows
# ---------------------------------------------------------------------------
def inicio_automatico_ativo() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_RUN) as chave:
            winreg.QueryValueEx(chave, NOME_APP)
            return True
    except FileNotFoundError:
        return False


def definir_inicio_automatico(ativo: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_RUN, 0,
                        winreg.KEY_SET_VALUE) as chave:
        if ativo:
            winreg.SetValueEx(chave, NOME_APP, 0, winreg.REG_SZ,
                              subprocess.list2cmdline(comando_base()))
        else:
            try:
                winreg.DeleteValue(chave, NOME_APP)
            except FileNotFoundError:
                pass


# ---------------------------------------------------------------------------
# Agendador de Tarefas
# ---------------------------------------------------------------------------
def _schtasks(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks", *args], capture_output=True,
                          text=True, creationflags=SEM_JANELA)


def agendamento_ativo() -> bool:
    return _schtasks("/Query", "/TN", NOME_APP).returncode == 0


def _xml_tarefa(hora: str) -> str:
    usuario = f"{os.environ.get('USERDOMAIN', '')}\\" \
              f"{os.environ.get('USERNAME', '')}"
    cmd = comando_base()
    programa, argumentos = cmd[0], cmd[1:] + ["--executar"]
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Robô de Contas a Pagar: varre os e-mails, atualiza a planilha e envia o relatório quando devido.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{escape(usuario)}</UserId>
      <Delay>PT2M</Delay>
    </LogonTrigger>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T{hora}:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{escape(usuario)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(programa)}</Command>
      <Arguments>{escape(subprocess.list2cmdline(argumentos))}</Arguments>
      <WorkingDirectory>{escape(str(config.RAIZ))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def agendar(hora: str = "08:00") -> None:
    """Cria (ou substitui) a tarefa: ao fazer login + todo dia às `hora`.
    StartWhenAvailable: se o PC estava desligado no horário, roda ao ligar."""
    hh, mm = (int(x) for x in hora.split(":"))
    if not (0 <= hh < 24 and 0 <= mm < 60):
        raise ValueError("horário inválido (use HH:MM)")
    hora = f"{hh:02d}:{mm:02d}"
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False,
                                     encoding="utf-16") as f:
        f.write(_xml_tarefa(hora))
        caminho = f.name
    try:
        r = _schtasks("/Create", "/TN", NOME_APP, "/XML", caminho, "/F")
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout).strip())
    finally:
        os.unlink(caminho)


def desagendar() -> None:
    if agendamento_ativo():
        r = _schtasks("/Delete", "/TN", NOME_APP, "/F")
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout).strip())
