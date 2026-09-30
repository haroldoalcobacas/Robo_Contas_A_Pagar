"""
Configuração do robô: onde ficam os arquivos, e leitura/gravação do .env.

Dois modos:
- Desenvolvimento (python main.py): tudo fica na pasta do projeto.
- Instalado (RoboContas.exe): o programa fica na pasta de instalação,
  que não deve receber gravações; configuração, log e estado vão para
  %APPDATA%\\RoboContasAPagar e a planilha para Documentos\\Contas a Pagar.

Senhas NÃO ficam no .env: vão para o Gerenciador de Credenciais do Windows
(biblioteca keyring). Sem keyring disponível, caem no .env como antes.
"""

import ctypes
import os
import sys
from datetime import date
from pathlib import Path

CONGELADO = getattr(sys, "frozen", False)   # True dentro do .exe

# Onde está o programa
RAIZ = (Path(sys.executable).parent if CONGELADO
        else Path(__file__).resolve().parent.parent)
# Arquivos embutidos no .exe (e-mails de exemplo)
RECURSOS = Path(getattr(sys, "_MEIPASS", RAIZ))


def _pasta_documentos() -> Path:
    """Pasta Documentos real (pode estar no OneDrive)."""
    try:
        buf = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)
        if buf.value:
            return Path(buf.value)
    except (AttributeError, OSError):
        pass
    return Path.home() / "Documents"


if "ROBO_DADOS" in os.environ:
    DADOS_APP = Path(os.environ["ROBO_DADOS"])
elif CONGELADO:
    DADOS_APP = Path(os.environ.get("APPDATA", Path.home())) / \
        "RoboContasAPagar"
else:
    DADOS_APP = RAIZ

ARQUIVO_ENV = DADOS_APP / ".env"
PASTA_LOGS = DADOS_APP / "logs"
ARQUIVO_ESTADO = DADOS_APP / "estado.json"
ARQUIVO_TRAVA = DADOS_APP / "robo.lock"

if CONGELADO:
    _EMAILS = str(RECURSOS / "exemplos" / "caixa_de_entrada")
    _SAIDA = str(_pasta_documentos() / "Contas a Pagar")
    _DATA = ""                     # instalado: data de hoje
else:
    _EMAILS = "dados/caixa_de_entrada"
    _SAIDA = "saida"
    _DATA = "2026-09-20"           # testes: data fixa do desafio

# Todas as chaves conhecidas, agrupadas por seção, com o valor padrão.
SECOES: dict[str, dict[str, str]] = {
    "Execução": {
        "PASTA_EMAILS": _EMAILS,
        "PASTA_SAIDA": _SAIDA,
        "NOME_PLANILHA": "contas_a_pagar.xlsx",
        "DATA_REFERENCIA": _DATA,         # vazio = hoje (AAAA-MM-DD)
        "SALVAR_ANEXOS": "sim",           # anexos/<fornecedor>/<ano-mes>/
    },
    "Leitura de e-mail": {
        "ORIGEM_EMAILS": "pasta",          # pasta | imap
        "IMAP_HOST": "imap.gmail.com",
        "IMAP_PORTA": "993",
        "IMAP_USUARIO": "",
        "IMAP_SENHA": "",
        "IMAP_PASTA": "INBOX",
        "IMAP_DIAS": "30",                 # quantos dias para trás ler
    },
    "Relatório": {
        "RELATORIO_EMAIL": "nao",          # sim | nao
        "RELATORIO_WHATSAPP": "nao",       # sim | nao
        "RELATORIO_FREQUENCIA": "diario",  # diario | semanal | mensal
        "SMTP_HOST": "smtp.gmail.com",
        "SMTP_PORTA": "587",
        "SMTP_USUARIO": "",
        "SMTP_SENHA": "",
        "EMAIL_DESTINATARIOS": "",
        "WHATSAPP_NUMERO": "",             # com DDI, ex.: 5511999998888
        "WHATSAPP_APIKEY": "",             # chave do CallMeBot
    },
    "Automação": {
        "AGENDA_HORA": "08:00",            # varredura diária
    },
}

PADROES = {k: v for secao in SECOES.values() for k, v in secao.items()}

# Guardados no Gerenciador de Credenciais do Windows
SEGREDOS = ("IMAP_SENHA", "SMTP_SENHA", "WHATSAPP_APIKEY")
SERVICO_COFRE = "RoboContasAPagar"


def _cofre():
    """Módulo keyring, ou None se indisponível."""
    try:
        import keyring
        keyring.get_keyring()
        return keyring
    except Exception:
        return None


def _tirar_aspas(valor: str) -> str:
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
        return valor[1:-1]
    return valor


def carregar(caminho: Path = ARQUIVO_ENV) -> dict[str, str]:
    """Padrões, sobrescritos pelo .env, com as senhas vindas do cofre."""
    cfg = dict(PADROES)
    if caminho.exists():
        # utf-8-sig: aceita o BOM que o Bloco de Notas às vezes grava
        for linha in caminho.read_text(encoding="utf-8-sig").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            cfg[chave.strip()] = _tirar_aspas(valor.strip())

    cofre = _cofre()
    if cofre:
        for chave in SEGREDOS:
            if not cfg.get(chave):   # .env antigo com senha ainda vale
                try:
                    cfg[chave] = cofre.get_password(SERVICO_COFRE,
                                                    chave) or ""
                except Exception:
                    pass
    return cfg


def salvar(cfg: dict[str, str], caminho: Path = ARQUIVO_ENV) -> None:
    """Grava o .env por seção; senhas vão para o cofre do Windows."""
    cofre = _cofre()
    linhas = [
        "# Configuração do Robô de Contas a Pagar",
        "# Gerado pela tela de configurações. NÃO vai para o Git.",
    ]
    if cofre:
        linhas.append("# Senhas: Gerenciador de Credenciais do Windows "
                      f"('{SERVICO_COFRE}').")
    for secao, chaves in SECOES.items():
        linhas += ["", f"# --- {secao} ---"]
        for chave in chaves:
            valor = str(cfg.get(chave, ""))
            if chave in SEGREDOS and cofre:
                _guardar_segredo(cofre, chave, valor)
                valor = ""
            # Aspas protegem espaços nas pontas e aspas no próprio valor
            if valor != valor.strip() or valor.startswith(("\"", "'")):
                valor = f'"{valor}"'
            linhas.append(f"{chave}={valor}")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def _guardar_segredo(cofre, chave: str, valor: str) -> None:
    if valor:
        cofre.set_password(SERVICO_COFRE, chave, valor)
    else:
        try:
            cofre.delete_password(SERVICO_COFRE, chave)
        except Exception:
            pass   # não existia


def caminho(cfg: dict[str, str], chave: str) -> Path:
    """Converte um caminho do .env em Path absoluto."""
    p = Path(cfg[chave]).expanduser()
    return p if p.is_absolute() else DADOS_APP / p


def arquivo_planilha(cfg: dict[str, str]) -> Path:
    return caminho(cfg, "PASTA_SAIDA") / cfg["NOME_PLANILHA"]


def pasta_anexos(cfg: dict[str, str]) -> Path | None:
    if cfg.get("SALVAR_ANEXOS", "sim") != "sim":
        return None
    return caminho(cfg, "PASTA_SAIDA") / "anexos"


def data_referencia(cfg: dict[str, str]) -> date:
    """Data usada nos alertas. Vazia no .env = hoje."""
    valor = cfg.get("DATA_REFERENCIA", "").strip()
    return date.fromisoformat(valor) if valor else date.today()
