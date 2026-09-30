"""
Leitura e gravação da planilha contas_a_pagar.xlsx.

Abas:
- Contas a Pagar: uma linha por cobrança, com status e total.
- Resumo: totais por status e contadores da última execução.
- Exceções: arquivos que não puderam ser lidos, com o motivo.
- Log: o destino de cada e-mail na última execução.

A aba "Contas a Pagar" também é a MEMÓRIA do robô: ao rodar de novo, ele lê
as chaves que já estão nela e só acrescenta o que for novo (idempotência).
"""

from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ABA_CONTAS = "Contas a Pagar"

VENCIDA = "VENCIDA"
VENCE_7 = "VENCE EM ATÉ 7 DIAS"
EM_DIA = "EM DIA"
SEM_VENC = "SEM VENCIMENTO"
ORDEM_STATUS = [VENCIDA, VENCE_7, EM_DIA, SEM_VENC]

# (coluna, largura, formato)
COLUNAS = [
    ("Status", 21, None),
    ("Vencimento", 12, "DD/MM/YYYY"),
    ("Dias p/ Vencer", 9, "0"),
    ("Fornecedor", 30, None),
    ("CNPJ", 19, None),
    ("Tipo", 11, None),
    ("Documento", 13, None),
    ("Emissão", 12, "DD/MM/YYYY"),
    ("Valor (R$)", 14, '"R$" #,##0.00'),
    ("Linha Digitável", 56, None),
    ("Arquivo de Origem", 44, None),
    ("Lançado em", 12, "DD/MM/YYYY"),
    ("Chave", 40, None),
]
NOMES = [c[0] for c in COLUNAS]
CAMPOS_DATA = {"Vencimento", "Emissão", "Lançado em"}

AZUL = PatternFill("solid", fgColor="305496")
CORES_STATUS = {
    VENCIDA: PatternFill("solid", fgColor="F8CBAD"),
    VENCE_7: PatternFill("solid", fgColor="FFE699"),
    EM_DIA: PatternFill("solid", fgColor="C6EFCE"),
    SEM_VENC: PatternFill("solid", fgColor="D9D9D9"),
}


class PlanilhaBloqueada(Exception):
    """A planilha está aberta em outro programa (ex.: Excel)."""


def calcular_status(vencimento: date | None,
                    referencia: date) -> tuple[str, int | None]:
    if vencimento is None:
        return SEM_VENC, None
    dias = (vencimento - referencia).days
    if dias < 0:
        return VENCIDA, dias
    if dias <= 7:
        return VENCE_7, dias
    return EM_DIA, dias


# ---------------------------------------------------------------------------
# Leitura (memória das execuções anteriores)
# ---------------------------------------------------------------------------
def ler_contas(arquivo: Path) -> list[dict]:
    """Devolve as contas já lançadas na planilha (lista vazia se não há)."""
    if not arquivo.exists():
        return []
    try:
        wb = load_workbook(arquivo, read_only=True)
    except PermissionError:
        raise PlanilhaBloqueada(arquivo)
    if ABA_CONTAS not in wb.sheetnames:
        return []

    linhas = wb[ABA_CONTAS].iter_rows(values_only=True)
    cabecalho = list(next(linhas, []))
    contas = []
    for valores in linhas:
        conta = dict(zip(cabecalho, valores))
        if conta.get("Status") == "TOTAL" or not conta.get("Chave"):
            continue
        for campo in CAMPOS_DATA:
            if isinstance(conta.get(campo), datetime):
                conta[campo] = conta[campo].date()
        contas.append(conta)
    wb.close()
    return contas


# ---------------------------------------------------------------------------
# Gravação
# ---------------------------------------------------------------------------
def _cabecalho(ws, nomes: list[str]) -> None:
    ws.append(nomes)
    for celula in ws[1]:
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = AZUL
        celula.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"


def _larguras(ws, larguras: list[int]) -> None:
    for i, largura in enumerate(larguras, start=1):
        ws.column_dimensions[get_column_letter(i)].width = largura


def _aba_contas(wb: Workbook, contas: list[dict]) -> None:
    ws = wb.active
    ws.title = ABA_CONTAS
    _cabecalho(ws, NOMES)
    _larguras(ws, [c[1] for c in COLUNAS])

    for conta in contas:
        ws.append([conta.get(nome) for nome in NOMES])
        linha = ws[ws.max_row]
        linha[0].fill = CORES_STATUS.get(conta["Status"], PatternFill())
        linha[0].font = Font(bold=True)
        for celula, (_, _, formato) in zip(linha, COLUNAS):
            if formato:
                celula.number_format = formato

    ultima = ws.max_row
    col_valor = get_column_letter(NOMES.index("Valor (R$)") + 1)
    ws.auto_filter.ref = f"A1:{get_column_letter(len(NOMES))}{ultima}"
    ws.append([])
    total = [None] * len(NOMES)
    total[0] = "TOTAL"
    total[NOMES.index("Valor (R$)")] = f"=SUM({col_valor}2:{col_valor}{ultima})"
    ws.append(total)
    for celula in ws[ws.max_row]:
        celula.font = Font(bold=True)
    ws[f"{col_valor}{ws.max_row}"].number_format = '"R$" #,##0.00'


def _aba_resumo(wb: Workbook, contas: list[dict], info: dict) -> None:
    ws = wb.create_sheet("Resumo", 0)
    ws["A1"] = "Resumo de Contas a Pagar"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Data de referência: {info['data_referencia']:%d/%m/%Y}"
    ws["A3"] = f"Gerado em: {info['gerado_em']:%d/%m/%Y %H:%M}"

    ws.append([])
    ws.append(["Status", "Quantidade", "Valor (R$)"])
    for celula in ws[ws.max_row]:
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = AZUL

    for status in ORDEM_STATUS:
        grupo = [c for c in contas if c["Status"] == status]
        if not grupo and status == SEM_VENC:
            continue
        ws.append([status, len(grupo),
                   round(sum(c["Valor (R$)"] for c in grupo), 2)])
        ws.cell(ws.max_row, 1).fill = CORES_STATUS[status]
    ws.append(["TOTAL", len(contas),
               round(sum(c["Valor (R$)"] for c in contas), 2)])
    for celula in ws[ws.max_row]:
        celula.font = Font(bold=True)
    for linha in ws.iter_rows(min_row=6, min_col=3, max_col=3):
        linha[0].number_format = '"R$" #,##0.00'

    ws.append([])
    ws.append(["Última execução", "Quantidade"])
    for celula in ws[ws.max_row]:
        celula.font = Font(bold=True)
    for rotulo, chave in [("E-mails lidos", "emails"),
                          ("Contas novas", "novas"),
                          ("Já lançadas antes", "ja_lancadas"),
                          ("Duplicidades descartadas", "duplicadas"),
                          ("Exceções", "excecoes"),
                          ("Ignorados (não são cobrança)", "ignorados")]:
        ws.append([rotulo, info[chave]])
    _larguras(ws, [30, 12, 16])


def _aba_simples(wb: Workbook, titulo: str, nomes: list[str],
                 linhas: list[dict], larguras: list[int]) -> None:
    ws = wb.create_sheet(titulo)
    _cabecalho(ws, nomes)
    _larguras(ws, larguras)
    for item in linhas:
        ws.append([item.get(n) for n in nomes])
    if not linhas:
        ws.append(["(nenhum)"])


def salvar(arquivo: Path, contas: list[dict], excecoes: list[dict],
           log: list[dict], info: dict) -> None:
    wb = Workbook()
    _aba_contas(wb, contas)
    _aba_resumo(wb, contas, info)
    _aba_simples(wb, "Exceções", ["Arquivo", "Anexo", "Motivo"],
                 excecoes, [44, 20, 70])
    _aba_simples(wb, "Log", ["Arquivo", "Remetente", "Assunto",
                             "Resultado", "Detalhe"],
                 log, [44, 36, 40, 14, 60])
    wb.active = 0

    arquivo.parent.mkdir(parents=True, exist_ok=True)
    try:
        wb.save(arquivo)
    except PermissionError:
        raise PlanilhaBloqueada(arquivo)
