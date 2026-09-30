"""
Extração de dados das cobranças: NF-e em XML e faturas/boletos em PDF.

As duas funções devolvem um dicionário com o MESMO formato, para que o
resto do robô (duplicidade, status, planilha) não precise saber de onde a
conta veio.

Dois tipos de "não deu":
- NaoECobranca: o anexo foi lido, mas não é cobrança (ex.: PDF do RH).
  O e-mail vai para o log como IGNORADO.
- ErroExtracao: parece cobrança, mas não foi possível ler (arquivo
  corrompido, campo faltando). Vai para a aba de EXCEÇÕES.
"""

import io
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime

from pypdf import PdfReader

NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}


class NaoECobranca(Exception):
    """Anexo legível, mas que não representa uma cobrança."""


class ErroExtracao(Exception):
    """Anexo que parece cobrança, mas não pôde ser lido."""


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------
def so_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def formatar_cnpj(cnpj: str) -> str:
    c = so_digitos(cnpj)
    if len(c) != 14:
        return cnpj
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def cnpj_valido(cnpj: str | None) -> bool | None:
    """
    Confere os 2 dígitos verificadores do CNPJ.
    Devolve None quando não há CNPJ para validar.
    """
    c = so_digitos(cnpj or "")
    if not c:
        return None
    if len(c) != 14 or c == c[0] * 14:
        return False

    def digito(base: str) -> str:
        pesos = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2][-len(base):]
        resto = sum(int(n) * p for n, p in zip(base, pesos)) % 11
        return "0" if resto < 2 else str(11 - resto)

    d1 = digito(c[:12])
    d2 = digito(c[:12] + d1)
    return c[12:] == d1 + d2


def valor_brasileiro(texto: str) -> float:
    """'1.200,00' -> 1200.0"""
    return float(texto.replace(".", "").replace(",", "."))


def _conta(**campos) -> dict:
    """Monta o dicionário padrão de uma conta."""
    base = {
        "Tipo": None,
        "Fornecedor": None,
        "CNPJ": None,
        "Documento": None,
        "Emissão": None,
        "Vencimento": None,
        "Valor (R$)": None,
        "Linha Digitável": None,
        "Chave": None,
    }
    base.update(campos)
    return base


# ---------------------------------------------------------------------------
# NF-e em XML
# ---------------------------------------------------------------------------
def _texto(raiz: ET.Element, caminho: str) -> str | None:
    el = raiz.find(caminho, NS)
    return el.text.strip() if el is not None and el.text else None


def extrair_nfe(conteudo: bytes) -> dict:
    # "&" cru (ex.: "Silva & Filhos") é XML inválido: escapamos todo "&"
    # que ainda não inicia uma entidade (&amp; &#38; &#x26; ...).
    conteudo = re.sub(rb"&(?!(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);)",
                      b"&amp;", conteudo)
    try:
        raiz = ET.fromstring(conteudo)
    except ET.ParseError as erro:
        raise ErroExtracao(f"XML inválido/corrompido ({erro})")

    inf = raiz.find(".//nfe:infNFe", NS)
    if inf is None:
        raise NaoECobranca("XML não é uma NF-e")

    cnpj = _texto(inf, "nfe:emit/nfe:CNPJ")
    fornecedor = _texto(inf, "nfe:emit/nfe:xNome")
    numero = _texto(inf, "nfe:ide/nfe:nNF")
    emissao = _texto(inf, "nfe:ide/nfe:dhEmi")
    valor = _texto(inf, "nfe:total/nfe:ICMSTot/nfe:vNF")
    vencimento = _texto(inf, "nfe:cobr/nfe:dup/nfe:dVenc")

    obrigatorios = {"CNPJ": cnpj, "fornecedor": fornecedor,
                    "número": numero, "valor": valor}
    faltando = [nome for nome, v in obrigatorios.items() if not v]
    if faltando:
        raise ErroExtracao(f"NF-e sem {', '.join(faltando)}")

    try:
        return _conta(
            Tipo="NF-e",
            Fornecedor=fornecedor,
            CNPJ=formatar_cnpj(cnpj),
            Documento=f"NF-e {int(numero)}",
            Emissão=(datetime.fromisoformat(emissao).date()
                     if emissao else None),
            Vencimento=date.fromisoformat(vencimento) if vencimento else None,
            **{"Valor (R$)": float(valor)},
            # Número de nota só é único dentro do mesmo emissor
            Chave=f"NFE-{so_digitos(cnpj)}-{int(numero)}",
        )
    except ValueError as erro:
        raise ErroExtracao(f"campo com formato inválido na NF-e ({erro})")


# ---------------------------------------------------------------------------
# Fatura / boleto em PDF
# ---------------------------------------------------------------------------
PADROES_PDF = {
    "cnpj": r"CNPJ:?\s*(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})",
    "vencimento": r"Vencimento:?\s*(\d{2}/\d{2}/\d{4})",
    "valor": r"Valor(?: do documento| total| a pagar)?:?\s*R\$\s*"
             r"(\d{1,3}(?:\.\d{3})*,\d{2})",
    "linha": r"Linha digit[aá]vel:?\s*([\d.\- ]{40,})",
    "referencia": r"Refer[eê]ncia:?\s*(\d{2}/\d{4})",
}


def texto_pdf(conteudo: bytes) -> str:
    try:
        leitor = PdfReader(io.BytesIO(conteudo))
        return "\n".join(p.extract_text() or "" for p in leitor.pages)
    except Exception as erro:
        raise ErroExtracao(f"PDF ilegível ({erro})")


def extrair_pdf(conteudo: bytes) -> dict:
    texto = texto_pdf(conteudo)
    if not texto.strip():
        raise ErroExtracao("PDF sem texto (documento escaneado?)")

    achados = {}
    for campo, padrao in PADROES_PDF.items():
        m = re.search(padrao, texto, re.IGNORECASE)
        achados[campo] = m.group(1).strip() if m else None

    tem_valor, tem_venc = achados["valor"], achados["vencimento"]
    if not tem_valor and not tem_venc:
        raise NaoECobranca("PDF sem valor e vencimento")
    if not (tem_valor and tem_venc):
        falta = "vencimento" if tem_valor else "valor"
        raise ErroExtracao(f"PDF de cobrança sem {falta}")

    valor = valor_brasileiro(achados["valor"])
    vencimento = datetime.strptime(achados["vencimento"], "%d/%m/%Y").date()
    cnpj = achados["cnpj"]
    linha = achados["linha"]
    fornecedor = texto.strip().splitlines()[0].strip()

    # Chave: a linha digitável identifica um boleto de forma única.
    # Sem ela, o melhor que temos é CNPJ + vencimento + valor.
    if linha:
        chave = f"BOLETO-{so_digitos(linha)}"
    else:
        chave = (f"FATURA-{so_digitos(cnpj) or fornecedor}-"
                 f"{vencimento.isoformat()}-{valor:.2f}")

    ref = achados["referencia"]
    return _conta(
        Tipo="Fatura PDF",
        Fornecedor=fornecedor,
        CNPJ=formatar_cnpj(cnpj) if cnpj else None,
        Documento=f"Ref. {ref}" if ref else None,
        Vencimento=vencimento,
        **{"Valor (R$)": valor},
        **{"Linha Digitável": linha},
        Chave=chave,
    )


# ---------------------------------------------------------------------------
# Cobrança só no corpo do e-mail (sem anexo)
# ---------------------------------------------------------------------------
PADROES_CORPO = {
    "valor": PADROES_PDF["valor"],
    "vencimento": PADROES_PDF["vencimento"],
    "linha": PADROES_PDF["linha"],
}
# Identificador da fatura: "fatura TS-2026-0917", "fatura nº 12345/2026".
# Exige ao menos um separador ou dígito para não capturar palavras soltas.
PADRAO_DOC_CORPO = (r"(?i:fatura|boleto|cobran[çc]a)\s+(?:(?i:n[º°o.]?)\s*)?"
                    r"([A-Z0-9]+(?:[-./][A-Z0-9]+)+|\d{3,})")


def extrair_corpo(texto: str, remetente_nome: str,
                  remetente_email: str) -> dict:
    """
    Procura uma cobrança no texto do e-mail. Só é chamada quando o e-mail
    não trouxe anexo de cobrança, para não lançar duas vezes a mesma fatura
    (quem manda PDF costuma repetir valor e vencimento no corpo).

    O corpo é "conversa", então aqui somos conservadores: sem valor E
    vencimento, não é cobrança (NaoECobranca, nunca ErroExtracao).
    """
    achados = {}
    for campo, padrao in PADROES_CORPO.items():
        m = re.search(padrao, texto, re.IGNORECASE)
        achados[campo] = m.group(1).strip() if m else None
    if not (achados["valor"] and achados["vencimento"]):
        raise NaoECobranca("corpo sem valor e vencimento")

    m = re.search(PADRAO_DOC_CORPO, texto)
    documento = m.group(1) if m else None
    valor = valor_brasileiro(achados["valor"])
    vencimento = datetime.strptime(achados["vencimento"], "%d/%m/%Y").date()
    linha = achados["linha"]
    fornecedor = remetente_nome or remetente_email

    if linha:
        chave = f"BOLETO-{so_digitos(linha)}"
    elif documento:
        chave = f"CORPO-{remetente_email.lower()}-{documento}"
    else:
        chave = (f"CORPO-{remetente_email.lower()}-"
                 f"{vencimento.isoformat()}-{valor:.2f}")

    return _conta(
        Tipo="Corpo e-mail",
        Fornecedor=fornecedor,
        Documento=documento,
        Vencimento=vencimento,
        **{"Valor (R$)": valor},
        **{"Linha Digitável": linha},
        Chave=chave,
    )