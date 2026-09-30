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
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ABA_CONTAS = "Contas a Pagar"

VENCIDA = "VENCIDA"
VENCE_7 = "VENCE EM ATÉ 7 DIAS"
EM_DIA = "EM DIA"
SEM_VENC = "SEM VENCIMENTO"
PAGA = "PAGA"
ORDEM_STATUS = [VENCIDA, VENCE_7, EM_DIA, SEM_VENC, PAGA]
EM_ABERTO = [VENCIDA, VENCE_7, EM_DIA, SEM_VENC]

# (coluna, largura, formato)
COLUNAS = [
    ("Status", 21, None),
    ("Vencimento", 12, "DD/MM/YYYY"),
    ("Dias p/ Vencer", 9, "0"),
    ("Fornecedor", 30, None),
    ("CNPJ", 19, None),
    ("CNPJ Válido", 8, None),
    ("Tipo", 13, None),
    ("Documento", 13, None),
    ("Emissão", 12, "DD/MM/YYYY"),
    ("Valor (R$)", 14, '"R$" #,##0.00'),
    # Preenchida à mão no Excel: a conta vira PAGA e sai dos alertas
    ("Pago em", 12, "DD/MM/YYYY"),
    ("Linha Digitável", 56, None),
    ("Arquivo de Origem", 44, None),
    ("Lançado em", 12, "DD/MM/YYYY"),
    ("Chave", 40, None),
]
NOMES = [c[0] for c in COLUNAS]
CAMPOS_DATA = {"Vencimento", "Emissão", "Lançado em", "Pago em"}

AZUL = PatternFill("solid", fgColor="305496")
CORES_STATUS = {
    VENCIDA: PatternFill("solid", fgColor="F8CBAD"),
    VENCE_7: PatternFill("solid", fgColor="FFE699"),
    EM_DIA: PatternFill("solid", fgColor="C6EFCE"),
    SEM_VENC: PatternFill("solid", fgColor="D9D9D9"),
    PAGA: PatternFill("solid", fgColor="BDD7EE"),
}


class PlanilhaBloqueada(Exception):
    """A planilha está aberta em outro programa (ex.: Excel)."""


def calcular_status(vencimento: date | None, referencia: date,
                    pago_em=None) -> tuple[str, int | None]:
    if pago_em not in (None, ""):
        return PAGA, None
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

    # A tabela começa abaixo do painel de resumo: a linha de títulos é a
    # que tem "Status" na coluna A e "Chave" em alguma coluna. (Planilhas
    # antigas, sem painel, têm os títulos na linha 1 e também funcionam.)
    cabecalho = None
    contas = []
    for valores in wb[ABA_CONTAS].iter_rows(values_only=True):
        if cabecalho is None:
            if valores and valores[0] == "Status" and "Chave" in valores:
                cabecalho = list(valores)
            continue
        conta = dict(zip(cabecalho, valores))
        if not conta.get("Chave"):
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
def _cabecalho(ws, nomes: list[str]) -> int:
    """Linha de títulos azul, congelada. Devolve o número da linha."""
    ws.append(nomes)
    linha = ws.max_row
    for celula in ws[linha]:
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = AZUL
        celula.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = f"A{linha + 1}"
    return linha


def _larguras(ws, larguras: list[int]) -> None:
    for i, largura in enumerate(larguras, start=1):
        ws.column_dimensions[get_column_letter(i)].width = largura


def _painel(ws, info: dict, primeira: int, ultima: int) -> None:
    """
    Painel de resumo no topo da aba, acima da tabela.

    Os valores são FÓRMULAS sobre a tabela: se alguém preencher "Pago em"
    ou corrigir um valor no Excel, o painel se atualiza sozinho.
    "Total do filtro" usa SUBTOTAL, que soma só as linhas visíveis.
    """
    col_valor = get_column_letter(NOMES.index("Valor (R$)") + 1)
    status = f"$A${primeira}:$A${ultima}"
    valores = f"${col_valor}${primeira}:${col_valor}${ultima}"
    moeda = '"R$" #,##0.00'

    ws["A1"] = "CONTAS A PAGAR"
    ws["A1"].font = Font(bold=True, size=16, color="305496")
    ws["D1"] = (f"Referência: {info['data_referencia']:%d/%m/%Y}   |   "
                f"Atualizado em {info['gerado_em']:%d/%m/%Y %H:%M}")
    ws["D1"].font = Font(italic=True, color="666666")
    ws["D1"].alignment = Alignment(vertical="center")

    linhas = [
        ("TOTAL A PAGAR", f'=SUMIF({status},"<>{PAGA}",{valores})',
         f'=COUNTA({status})-COUNTIF({status},"{PAGA}")', AZUL, True),
        (VENCIDA, f'=SUMIF({status},"{VENCIDA}",{valores})',
         f'=COUNTIF({status},"{VENCIDA}")', CORES_STATUS[VENCIDA], False),
        (VENCE_7, f'=SUMIF({status},"{VENCE_7}",{valores})',
         f'=COUNTIF({status},"{VENCE_7}")', CORES_STATUS[VENCE_7], False),
        (EM_DIA, f'=SUMIF({status},"{EM_DIA}",{valores})',
         f'=COUNTIF({status},"{EM_DIA}")', CORES_STATUS[EM_DIA], False),
        (PAGA, f'=SUMIF({status},"{PAGA}",{valores})',
         f'=COUNTIF({status},"{PAGA}")', CORES_STATUS[PAGA], False),
        ("Total do filtro", f"=SUBTOTAL(109,{valores})",
         f"=SUBTOTAL(103,{status})", None, False),
    ]
    borda = Side(style="thin", color="BFBFBF")
    for i, (rotulo, soma, qtd, cor, destaque) in enumerate(linhas, start=3):
        ws.merge_cells(start_row=i, start_column=2, end_row=i, end_column=3)
        ws.cell(i, 1, rotulo)
        ws.cell(i, 2, soma).number_format = moeda
        ws.cell(i, 4, qtd).number_format = '0 "conta(s)"'
        for col in (1, 2, 3, 4):
            ws.cell(i, col).border = Border(top=borda, bottom=borda,
                                            left=borda, right=borda)
        ws.cell(i, 1).font = Font(bold=True,
                                  color="FFFFFF" if destaque else "000000")
        ws.cell(i, 2).font = Font(bold=True, size=12 if destaque else 11,
                                  color="FFFFFF" if destaque else "000000")
        ws.cell(i, 4).alignment = Alignment(horizontal="left", indent=1)
        if cor:
            ws.cell(i, 1).fill = cor
            if destaque:
                ws.cell(i, 2).fill = cor
                ws.cell(i, 3).fill = cor
        if rotulo == "Total do filtro":
            ws.cell(i, 1).font = Font(italic=True)
            ws.cell(i, 5, "soma só as linhas visíveis ao filtrar a tabela")
            ws.cell(i, 5).font = Font(italic=True, size=9, color="888888")


def _aba_contas(wb: Workbook, contas: list[dict], info: dict) -> None:
    ws = wb.active
    ws.title = ABA_CONTAS
    _larguras(ws, [c[1] for c in COLUNAS])

    # Linhas 1-8: painel de resumo | linha 10: títulos | 11 em diante: dados
    for _ in range(9):
        ws.append([])
    linha_titulos = _cabecalho(ws, NOMES)

    for conta in contas:
        ws.append([conta.get(nome) for nome in NOMES])
        linha = ws[ws.max_row]
        linha[0].fill = CORES_STATUS.get(conta["Status"], PatternFill())
        linha[0].font = Font(bold=True)
        for celula, (_, _, formato) in zip(linha, COLUNAS):
            if formato:
                celula.number_format = formato
        if conta.get("CNPJ Válido") == "NÃO":
            linha[NOMES.index("CNPJ Válido")].fill = CORES_STATUS[VENCIDA]

    primeira = linha_titulos + 1
    # Fórmulas cobrem uma folga de linhas: quem acrescentar contas à mão
    # logo abaixo da tabela também entra nos totais.
    ultima = max(ws.max_row, primeira) + 500
    ws.auto_filter.ref = (f"A{linha_titulos}:"
                          f"{get_column_letter(len(NOMES))}{ws.max_row}")
    _painel(ws, info, primeira, ultima)


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
        if not grupo and status in (SEM_VENC, PAGA):
            continue
        ws.append([status, len(grupo),
                   round(sum(c["Valor (R$)"] for c in grupo), 2)])
        ws.cell(ws.max_row, 1).fill = CORES_STATUS[status]
    abertas = [c for c in contas if c["Status"] in EM_ABERTO]
    ws.append(["TOTAL A PAGAR", len(abertas),
               round(sum(c["Valor (R$)"] for c in abertas), 2)])
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
    _aba_contas(wb, contas, info)
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
