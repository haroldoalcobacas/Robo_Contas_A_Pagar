"""
Regras do robô: lê os e-mails, extrai as contas, aplica as regras
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
from typing import Callable, Iterable

from . import planilha
from .extratores import (ErroExtracao, NaoECobranca, cnpj_valido,
                         extrair_corpo, extrair_nfe, extrair_pdf)
from .fontes import EmailBruto, nome_seguro

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
    anexos_salvos: int = 0

    def contar(self, resultado: str) -> int:
        return sum(1 for item in self.log if item["Resultado"] == resultado)

    @property
    def abertas(self) -> list[dict]:
        return [c for c in self.contas if c["Status"] in planilha.EM_ABERTO]

    @property
    def total(self) -> float:
        """Total A PAGAR (não inclui as contas marcadas como pagas)."""
        return round(sum(c["Valor (R$)"] for c in self.abertas), 2)

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


def _nome_com_acentos(nome_pdf: str, nome_remetente: str) -> str:
    """
    PDFs simples costumam perder acentos ("Limpa Bem Servios"). Se o nome
    de exibição do remetente for o mesmo fornecedor, usamos a grafia dele.
    """
    if nome_remetente and _normalizar(nome_remetente) == _normalizar(nome_pdf):
        return nome_remetente
    return nome_pdf


def _texto_do_corpo(msg) -> str:
    corpo = msg.get_body(preferencelist=("plain", "html"))
    if corpo is None:
        return ""
    texto = corpo.get_content()
    if corpo.get_content_type() == "text/html":
        texto = re.sub(r"<[^>]+>", " ", texto)   # HTML -> texto simples
    return texto


def _salvar_anexo(pasta_anexos: Path, conta: dict, nome: str,
                  conteudo: bytes) -> bool:
    """Guarda em anexos/<fornecedor>/<ano-mes>/. Não sobrescreve."""
    data_ref = conta.get("Emissão") or conta.get("Vencimento") or date.today()
    destino = (pasta_anexos / nome_seguro(conta["Fornecedor"] or "sem_nome")
               / f"{data_ref:%Y-%m}" / nome_seguro(nome, 120))
    if destino.exists():
        return False
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(conteudo)
    return True


def processar(emails: Iterable[EmailBruto], arquivo_saida: Path,
              data_referencia: date, pasta_anexos: Path | None = None,
              log: Callable[[str], None] = print) -> Resultado:
    res = Resultado(arquivo_saida, data_referencia)
    emails = list(emails)

    # Memória: o que já está na planilha de execuções anteriores
    existentes = {c["Chave"]: c for c in planilha.ler_contas(arquivo_saida)}
    vistas: dict[str, dict] = {}   # chave -> conta, encontradas NESTA execução
    hoje = date.today()

    def registrar(nome, msg, resultado, detalhe, anexo=None):
        res.log.append({
            "Arquivo": nome,
            "Remetente": str(msg["From"]) if msg else None,
            "Assunto": str(msg["Subject"]) if msg else None,
            "Resultado": resultado,
            "Detalhe": detalhe,
        })
        if resultado == EXCECAO:
            res.excecoes.append({"Arquivo": nome, "Anexo": anexo,
                                 "Motivo": detalhe})
        log(f"[{resultado:<10}] {nome}: {detalhe}")

    def mesma_cobranca(conta) -> dict | None:
        """Outra conta (desta ou de outra execução) com mesmo fornecedor,
        valor e vencimento."""
        for outra in [*vistas.values(), *existentes.values()]:
            if outra["Chave"] == conta["Chave"]:
                continue
            if (outra["Valor (R$)"] == conta["Valor (R$)"]
                    and outra["Vencimento"] == conta["Vencimento"]
                    and _normalizar(outra["Fornecedor"] or "")
                    == _normalizar(conta["Fornecedor"] or "")):
                return outra
        return None

    def lancar(nome, msg, conta, anexo_nome, anexo_bytes):
        """Aplica duplicidade/memória e, se for nova, guarda a conta."""
        chave = conta["Chave"]
        desc = (f"{conta['Fornecedor']} - {conta['Documento'] or ''}"
                f" - {brl(conta['Valor (R$)'])}")
        if chave in vistas:
            registrar(nome, msg, DUPLICADA,
                      f"{desc} (reenvio da mesma cobrança)")
            return
        # Cobrança no corpo é a fonte menos confiável: se já existe a mesma
        # cobrança vinda de XML/PDF, é lembrete e não conta nova.
        if conta["Tipo"] == "Corpo e-mail" and (outra := mesma_cobranca(conta)):
            registrar(nome, msg, DUPLICADA,
                      f"{desc} (mesma cobrança de {outra['Tipo']})")
            return
        vistas[chave] = existentes.get(chave, conta)

        if pasta_anexos is not None and _salvar_anexo(
                pasta_anexos, vistas[chave], anexo_nome, anexo_bytes):
            res.anexos_salvos += 1

        if chave in existentes:
            registrar(nome, msg, JA_LANCADA, desc)
            return
        valido = cnpj_valido(conta["CNPJ"])
        conta["CNPJ Válido"] = {True: "SIM", False: "NÃO"}.get(valido)
        conta["Arquivo de Origem"] = nome
        conta["Lançado em"] = hoje
        existentes[chave] = conta
        res.novas.append(conta)
        aviso = " [CNPJ com dígito verificador inválido]" if valido is False \
            else ""
        registrar(nome, msg, OK, desc + aviso)

    log(f"Data de referência: {data_referencia:%d/%m/%Y}")
    log(f"{len(emails)} e-mails para analisar")
    log(f"{len(existentes)} contas já lançadas na planilha\n")

    for bruto in emails:
        res.emails_lidos += 1
        nome = bruto.nome
        msg = None
        try:
            msg = email.message_from_bytes(bruto.conteudo,
                                           policy=email.policy.default)
            nome_rem, email_rem = email.utils.parseaddr(str(msg["From"] or ""))

            anexos = [(p, _tipo_anexo(p)) for p in msg.iter_attachments()]
            anexos = [(p, t) for p, t in anexos if t]

            motivos_ignorado = []
            achou_cobranca = False
            for parte, tipo in anexos:
                anexo_nome = parte.get_filename() or f"anexo.{tipo}"
                conteudo = parte.get_payload(decode=True)
                try:
                    conta = EXTRATORES[tipo](conteudo)
                except NaoECobranca as motivo:
                    motivos_ignorado.append(f"{anexo_nome}: {motivo}")
                    continue
                except ErroExtracao as erro:
                    achou_cobranca = True
                    registrar(nome, msg, EXCECAO, str(erro), anexo_nome)
                    continue
                achou_cobranca = True
                if tipo == "pdf":
                    conta["Fornecedor"] = _nome_com_acentos(
                        conta["Fornecedor"], nome_rem)
                lancar(nome, msg, conta, anexo_nome, conteudo)

            if achou_cobranca:
                continue

            # Sem anexo de cobrança: a cobrança pode estar no próprio texto
            try:
                conta = extrair_corpo(_texto_do_corpo(msg), nome_rem,
                                      email_rem)
            except NaoECobranca:
                motivo = ("; ".join(motivos_ignorado)
                          or "sem cobrança no anexo nem no corpo")
                registrar(nome, msg, IGNORADO, motivo)
                continue
            lancar(nome, msg, conta, nome, bruto.conteudo)

        except Exception as erro:  # rede de segurança: nunca derrubar
            registrar(nome, msg, EXCECAO,
                      f"erro inesperado: {type(erro).__name__}: {erro}")

    # Status recalculado para TODAS as contas (as antigas também envelhecem)
    for conta in existentes.values():
        conta["Status"], conta["Dias p/ Vencer"] = planilha.calcular_status(
            conta.get("Vencimento"), data_referencia, conta.get("Pago em"))
    res.contas = sorted(
        existentes.values(),
        key=lambda c: (c["Status"] == planilha.PAGA,
                       c["Vencimento"] or date.max, c["Fornecedor"] or ""))

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
    if pasta_anexos is not None and res.anexos_salvos:
        log(f"{res.anexos_salvos} anexos novos salvos em {pasta_anexos}")
    log(f"\nPlanilha: {arquivo_saida}")
    return res


def resumo_texto(res: Resultado) -> str:
    linhas = [
        f"{len(res.abertas)} contas em aberto | Total a pagar: "
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
