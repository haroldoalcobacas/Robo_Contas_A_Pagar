"""
Relatório consolidado: monta o texto e envia por e-mail e/ou WhatsApp.

Frequência:
- diário:  vencidas + o que vence nos próximos 7 dias
- semanal: vencidas + o que vence nos próximos 7 dias
- mensal:  vencidas + o que vence nos próximos 30 dias
Em todos: total em aberto e contas lançadas desde o último relatório.
"""

import html
import smtplib
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path

from . import planilha
from .conexoes import TIMEOUT

HORIZONTE = {"diario": 7, "semanal": 7, "mensal": 30}
NOME_FREQ = {"diario": "diário", "semanal": "semanal", "mensal": "mensal"}
MAX_ITENS_WHATSAPP = 10


def brl(valor: float) -> str:
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",")
    return "R$ " + texto.replace("X", ".")


@dataclass
class Relatorio:
    assunto: str
    texto: str      # e-mail em texto simples e WhatsApp
    html: str       # e-mail formatado


def _soma(contas) -> float:
    return round(sum(c["Valor (R$)"] for c in contas), 2)


def montar(contas: list[dict], data_ref: date, frequencia: str,
           desde: date | None = None) -> Relatorio:
    abertas = [c for c in contas if c["Status"] in planilha.EM_ABERTO]
    vencidas = [c for c in abertas if c["Status"] == planilha.VENCIDA]
    limite = data_ref + timedelta(days=HORIZONTE.get(frequencia, 7))
    a_vencer = [c for c in abertas if c["Status"] != planilha.VENCIDA
                and c["Vencimento"] and c["Vencimento"] <= limite]
    novas = [c for c in contas
             if desde and c.get("Lançado em") and c["Lançado em"] > desde]

    nome = NOME_FREQ.get(frequencia, frequencia)
    assunto = (f"Contas a pagar - resumo {nome} ({data_ref:%d/%m/%Y}): "
               f"{brl(_soma(abertas))}"
               + (f", {len(vencidas)} vencida(s)" if vencidas else ""))

    def linha(c):
        return (f"{c['Vencimento']:%d/%m} | {c['Fornecedor']} | "
                f"{brl(c['Valor (R$)'])}")

    blocos = [
        ("Vencidas", vencidas),
        (f"Vencem até {limite:%d/%m}", a_vencer),
    ]
    if desde:
        blocos.append((f"Lançadas desde {desde:%d/%m}", novas))

    # --- texto simples (e-mail alternativo e WhatsApp) ---
    t = [f"*Contas a pagar - resumo {nome}*",
         f"Referência: {data_ref:%d/%m/%Y}",
         f"Total em aberto: *{brl(_soma(abertas))}* ({len(abertas)} contas)",
         ""]
    for titulo, grupo in blocos:
        t.append(f"*{titulo}: {len(grupo)} ({brl(_soma(grupo))})*")
        for c in grupo[:MAX_ITENS_WHATSAPP]:
            t.append(f"- {linha(c)}")
        if len(grupo) > MAX_ITENS_WHATSAPP:
            t.append(f"- ... e mais {len(grupo) - MAX_ITENS_WHATSAPP}")
        if not grupo:
            t.append("- nenhuma")
        t.append("")
    texto = "\n".join(t).strip()

    # --- HTML (e-mail) ---
    def tabela(grupo):
        if not grupo:
            return "<p style='color:#666'>Nenhuma.</p>"
        linhas = "".join(
            f"<tr><td>{c['Vencimento']:%d/%m/%Y}</td>"
            f"<td>{html.escape(c['Fornecedor'] or '')}</td>"
            f"<td>{html.escape(c.get('Documento') or '')}</td>"
            f"<td style='text-align:right'>{brl(c['Valor (R$)'])}</td></tr>"
            for c in grupo)
        return ("<table cellpadding='6' style='border-collapse:collapse;"
                "font-family:Segoe UI,Arial;font-size:14px' border='1'>"
                "<tr style='background:#305496;color:#fff'><th>Vencimento"
                "</th><th>Fornecedor</th><th>Documento</th><th>Valor</th>"
                f"</tr>{linhas}</table>")

    corpo = [f"<h2 style='font-family:Segoe UI,Arial'>Contas a pagar - "
             f"resumo {nome}</h2>",
             f"<p style='font-family:Segoe UI,Arial'>Referência: "
             f"{data_ref:%d/%m/%Y}<br>Total em aberto: <b>"
             f"{brl(_soma(abertas))}</b> ({len(abertas)} contas)</p>"]
    for titulo, grupo in blocos:
        corpo.append(f"<h3 style='font-family:Segoe UI,Arial'>{titulo}: "
                     f"{len(grupo)} ({brl(_soma(grupo))})</h3>")
        corpo.append(tabela(grupo))
    corpo.append("<p style='color:#888;font-size:12px'>Planilha completa "
                 "em anexo. Enviado pelo Robô de Contas a Pagar.</p>")
    return Relatorio(assunto, texto, "\n".join(corpo))


# ---------------------------------------------------------------------------
# Envio
# ---------------------------------------------------------------------------
def enviar_email(cfg: dict, rel: Relatorio, anexo: Path | None) -> str:
    destinatarios = [d.strip() for d in cfg["EMAIL_DESTINATARIOS"].split(",")
                     if d.strip()]
    if not destinatarios:
        raise ValueError("nenhum destinatário configurado")

    msg = EmailMessage()
    msg["Subject"] = rel.assunto
    msg["From"] = cfg["SMTP_USUARIO"]
    msg["To"] = ", ".join(destinatarios)
    msg.set_content(rel.texto.replace("*", ""))
    msg.add_alternative(rel.html, subtype="html")
    if anexo and anexo.exists():
        msg.add_attachment(
            anexo.read_bytes(), maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=anexo.name)

    porta = int(cfg["SMTP_PORTA"])
    contexto = ssl.create_default_context()
    if porta == 465:
        servidor = smtplib.SMTP_SSL(cfg["SMTP_HOST"], porta,
                                    timeout=TIMEOUT, context=contexto)
    else:
        servidor = smtplib.SMTP(cfg["SMTP_HOST"], porta, timeout=TIMEOUT)
        servidor.starttls(context=contexto)
    with servidor:
        servidor.login(cfg["SMTP_USUARIO"], cfg["SMTP_SENHA"])
        servidor.send_message(msg)
    return f"e-mail enviado para {', '.join(destinatarios)}"


def enviar_whatsapp(cfg: dict, rel: Relatorio) -> str:
    """CallMeBot: envia para o próprio número cadastrado na API key."""
    params = urllib.parse.urlencode({
        "phone": cfg["WHATSAPP_NUMERO"],
        "text": rel.texto,
        "apikey": cfg["WHATSAPP_APIKEY"],
    })
    url = f"https://api.callmebot.com/whatsapp.php?{params}"
    with urllib.request.urlopen(url, timeout=TIMEOUT) as resposta:
        corpo = resposta.read().decode("utf-8", "replace")
    if resposta.status != 200 or "error" in corpo.lower() \
            or "invalid" in corpo.lower():
        raise RuntimeError(f"CallMeBot recusou: {corpo[:200]}")
    return f"WhatsApp enviado para +{cfg['WHATSAPP_NUMERO']}"


def enviar(cfg: dict, rel: Relatorio, anexo: Path | None) -> list[str]:
    """Envia pelos canais ligados. Uma falha num canal não impede o outro.
    Devolve mensagens; as de erro começam com 'ERRO'."""
    resultados = []
    canais = []
    if cfg.get("RELATORIO_EMAIL") == "sim":
        canais.append(("E-mail", lambda: enviar_email(cfg, rel, anexo)))
    if cfg.get("RELATORIO_WHATSAPP") == "sim":
        canais.append(("WhatsApp", lambda: enviar_whatsapp(cfg, rel)))
    if not canais:
        return ["ERRO: nenhum canal de relatório ligado (e-mail/WhatsApp)"]
    for nome, funcao in canais:
        try:
            resultados.append(funcao())
        except Exception as erro:
            resultados.append(f"ERRO no {nome}: {erro}")
    return resultados
