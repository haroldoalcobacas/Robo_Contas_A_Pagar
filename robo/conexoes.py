"""
Testes de conexão usados pela tela de configurações.

Só fazem login e saem: nada é lido, apagado ou enviado.
"""

import imaplib
import smtplib
import ssl

TIMEOUT = 15  # segundos


def testar_imap(host: str, porta: int, usuario: str, senha: str,
                pasta: str = "INBOX") -> str:
    """Faz login no IMAP e conta as mensagens da pasta. Lança em caso de erro."""
    with imaplib.IMAP4_SSL(host, porta, timeout=TIMEOUT) as imap:
        imap.login(usuario, senha)
        status, dados = imap.select(pasta, readonly=True)
        if status != "OK":
            raise RuntimeError(f"pasta '{pasta}' não encontrada")
        return f"Conectado. {int(dados[0])} mensagens em '{pasta}'."


def testar_smtp(host: str, porta: int, usuario: str, senha: str) -> str:
    """Faz login no SMTP (SSL na 465, STARTTLS nas demais)."""
    contexto = ssl.create_default_context()
    if porta == 465:
        servidor = smtplib.SMTP_SSL(host, porta, timeout=TIMEOUT,
                                    context=contexto)
    else:
        servidor = smtplib.SMTP(host, porta, timeout=TIMEOUT)
        servidor.starttls(context=contexto)
    with servidor:
        servidor.login(usuario, senha)
    return "Conectado. Login SMTP aceito."
