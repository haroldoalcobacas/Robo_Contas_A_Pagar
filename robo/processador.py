"""
Orquestração do robô: lê os e-mails, extrai as contas, aplica as regras
(duplicidade, status, exceções) e grava a planilha.

Regras de ouro:
1. Nenhum e-mail some sem explicação: todo e-mail gera ao menos uma linha
   no log (OK, JÁ LANÇADA, DUPLICADA, IGNORADO ou EXCEÇÃO).
2. Um arquivo com problema nunca derruba o robô.
3. Rodar de novo não duplica linhas: a planilha existente é a memória.
"""

import email
import email.policy
import email.utils
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from . import planilha
from .extratores import (ErroExtracao, NaoECobranca, extrair_nfe,
                         extrair_pdf)

OK = "OK"
JA_LANCADA = "JÁ LANÇADA"
DUPLICADA = "DUPLICADA"
IGNORADO = "IGNORADO"
EXCECAO = "EXCEÇÃO"


@dataclass
class Resultado:
    arquivo_saida: Path
    data_referencia: date
    contas: list[dict] = field(default_factory=list)   # todas na planilha
    novas: list[dict] = field(default_factory=list)
    excecoes: list[dict] = field(default_factory=list)
    log: list[dict] = field(default_factory=list)
    emails_lidos: int = 0

    def contar(self, resultado: str) -> int:
        return sum(1 for item in self.log if item["Resultado"] == resultado)

    @property
    def total(self) -> float:
        return round(sum(c["Valor (R$)"] for c in self.contas), 2)

    def por_status(self, status: str) -> list[dict]:
        return [c for c in self.contas if c["Status"] == status]


def brl(valor: float) -> str:
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",")
    return "R$ " + texto.replace("X", ".")


def _tipo_anexo(parte) -> str | None:
    nome = (parte.get_filename() or "").lower()
    tipo = parte.get_content_type()
    if nome.endswith(".xml") or tipo in ("application/xml", "text/xml"):
        return "xml"
    if nome.endswith(".pdf") or tipo == "application/pdf":
        return "pdf"
    return None


EXTRATORES = {"xml": extrair_nfe, "pdf": extrair_pdf}


def _normalizar(nome: str) -> str:
    """'Limpa Bem Serviços' -> 'limpabemservios' (só letras ASCII e números)"""
    ascii_ = nome.encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", ascii_)


def _nome_com_acentos(nome_pdf: str, remetente: str) -> str:
    """
    PDFs simples costumam perder acentos ("Limpa Bem Servios"). Se o nome
    de exibição do remetente for o mesmo fornecedor, usamos a grafia dele.
    """
    nome_remetente = email.utils.parseaddr(remetente or "")[0]
    if nome_remetente and _normalizar(nome_remetente) == _normalizar(nome_pdf):
        return nome_remetente
    return nome_pdf


def processar(pasta_emails: Path, arquivo_saida: Path,
              data_referencia: date,
              log: Callable[[str], None] = print) -> Resultado:
    res = Resultado(arquivo_saida, data_referencia)

    # Memória: o que já está na planilha de execuções anteriores
    existentes = {c["Chave"]: c for c in planilha.ler_contas(arquivo_saida)}
    vistas: set[str] = set()   # chaves encontradas NESTA execução
    hoje = date.today()

    def registrar(arquivo, msg, resultado, detalhe, anexo=None):
        res.log.append({
            "Arquivo": arquivo.name,
            "Remetente": str(msg["From"]) if msg else None,
            "Assunto": str(msg["Subject"]) if msg else None,
            "Resultado": resultado,
            "Detalhe": detalhe,
        })
        if resultado == EXCECAO:
            res.excecoes.append({"Arquivo": arquivo.name, "Anexo": anexo,
                                 "Motivo": detalhe})
        log(f"[{resultado:<10}] {arquivo.name}: {detalhe}")

    arquivos = sorted(pasta_emails.glob("*.eml"))
    log(f"Data de referência: {data_referencia:%d/%m/%Y}")
    log(f"{len(arquivos)} e-mails em {pasta_emails}")
    log(f"{len(existentes)} contas já lançadas na planilha\n")

    for arquivo in arquivos:
        res.emails_lidos += 1
        msg = None
        try:
            with open(arquivo, "rb") as f:
                msg = email.message_from_binary_file(
                    f, policy=email.policy.default)

            anexos = [(p, _tipo_anexo(p)) for p in msg.iter_attachments()]
            anexos = [(p, t) for p, t in anexos if t]
            if not anexos:
                registrar(arquivo, msg, IGNORADO,
                          "sem anexo de cobrança (XML/PDF)")
                continue

            motivos_ignorado = []
            for parte, tipo in anexos:
                nome = parte.get_filename()
                try:
                    conta = EXTRATORES[tipo](parte.get_payload(decode=True))
                except NaoECobranca as motivo:
                    motivos_ignorado.append(f"{nome}: {motivo}")
                    continue
                except ErroExtracao as erro:
                    registrar(arquivo, msg, EXCECAO, str(erro), nome)
                    continue

                if tipo == "pdf":
                    conta["Fornecedor"] = _nome_com_acentos(
                        conta["Fornecedor"], str(msg["From"]))

                chave = conta["Chave"]
                desc = (f"{conta['Fornecedor']} - {conta['Documento'] or ''}"
                        f" - {brl(conta['Valor (R$)'])}")
                if chave in vistas:
                    registrar(arquivo, msg, DUPLICADA,
                              f"{desc} (reenvio da mesma cobrança)")
                    continue
                vistas.add(chave)
                if chave in existentes:
                    registrar(arquivo, msg, JA_LANCADA, desc)
                    continue

                conta["Arquivo de Origem"] = arquivo.name
                conta["Lançado em"] = hoje
                existentes[chave] = conta
                res.novas.append(conta)
                registrar(arquivo, msg, OK, desc)

            # Todos os anexos foram lidos e nenhum era cobrança
            if motivos_ignorado and len(motivos_ignorado) == len(anexos):
                registrar(arquivo, msg, IGNORADO, "; ".join(motivos_ignorado))

        except Exception as erro:  # rede de segurança: nunca derrubar
            registrar(arquivo, msg, EXCECAO,
                      f"erro inesperado: {type(erro).__name__}: {erro}")

    # Status recalculado para TODAS as contas (as antigas também envelhecem)
    for conta in existentes.values():
        conta["Status"], conta["Dias p/ Vencer"] = planilha.calcular_status(
            conta.get("Vencimento"), data_referencia)
    res.contas = sorted(
        existentes.values(),
        key=lambda c: (c["Vencimento"] or date.max, c["Fornecedor"] or ""))

    planilha.salvar(arquivo_saida, res.contas, res.excecoes, res.log, {
        "data_referencia": data_referencia,
        "gerado_em": datetime.now(),
        "emails": res.emails_lidos,
        "novas": len(res.novas),
        "ja_lancadas": res.contar(JA_LANCADA),
        "duplicadas": res.contar(DUPLICADA),
        "excecoes": res.contar(EXCECAO),
        "ignorados": res.contar(IGNORADO),
    })

    log("")
    log(resumo_texto(res))
    log(f"\nPlanilha: {arquivo_saida}")
    return res


def resumo_texto(res: Resultado) -> str:
    linhas = [
        f"{len(res.contas)} contas na planilha | Total a pagar: "
        f"{brl(res.total)}",
        f"Novas: {len(res.novas)} | Já lançadas: {res.contar(JA_LANCADA)} | "
        f"Duplicidades: {res.contar(DUPLICADA)} | "
        f"Exceções: {res.contar(EXCECAO)} | "
        f"Ignorados: {res.contar(IGNORADO)}",
    ]
    for status in planilha.ORDEM_STATUS:
        grupo = res.por_status(status)
        if grupo:
            soma = brl(sum(c["Valor (R$)"] for c in grupo))
            linhas.append(f"  {status}: {len(grupo)} ({soma})")
    return "\n".join(linhas)
