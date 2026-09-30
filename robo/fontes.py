"""
De onde vêm os e-mails: pasta com arquivos .eml ou caixa real via IMAP.

As duas fontes entregam a mesma coisa, uma lista de EmailBruto (nome +
bytes do e-mail), e o processador não precisa saber qual foi usada.
"""

import imaplib
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .conexoes import TIMEOUT


@dataclass
class EmailBruto:
    nome: str       # identificação no log (nome do arquivo ou UID)
    conteudo: bytes


def da_pasta(pasta: Path) -> list[EmailBruto]:
    return [EmailBruto(arq.name, arq.read_bytes())
            for arq in sorted(pasta.glob("*.eml"))]


def do_imap(host: str, porta: int, usuario: str, senha: str,
            pasta: str = "INBOX", dias: int = 30) -> list[EmailBruto]:
    """
    Baixa os e-mails dos últimos `dias` dias, em modo SOMENTE LEITURA:
    nada é apagado, movido ou marcado como lido na caixa.
    """
    # strftime("%b") depende do idioma do sistema; o IMAP exige inglês
    meses = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    d = date.today() - timedelta(days=dias)
    desde = f"{d.day:02d}-{meses[d.month - 1]}-{d.year}"

    emails = []
    with imaplib.IMAP4_SSL(host, porta, timeout=TIMEOUT) as imap:
        imap.login(usuario, senha)
        status, _ = imap.select(f'"{pasta}"', readonly=True)
        if status != "OK":
            raise RuntimeError(f"pasta IMAP '{pasta}' não encontrada")
        status, dados = imap.uid("SEARCH", None, "SINCE", desde)
        if status != "OK":
            raise RuntimeError("falha ao pesquisar e-mails na caixa")
        for uid in dados[0].split():
            # BODY.PEEK[] baixa o e-mail inteiro sem marcá-lo como lido
            status, partes = imap.uid("FETCH", uid, "(BODY.PEEK[])")
            if status != "OK" or not partes or partes[0] is None:
                continue
            conteudo = partes[0][1]
            emails.append(EmailBruto(f"imap_uid_{uid.decode()}.eml",
                                     conteudo))
    return emails


def nome_seguro(texto: str, limite: int = 60) -> str:
    """Transforma um texto em nome de pasta/arquivo válido no Windows."""
    limpo = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", texto).strip(" .")
    return limpo[:limite] or "sem_nome"
