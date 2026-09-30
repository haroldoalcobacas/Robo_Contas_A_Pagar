"""Testes das regras isoladas: extração, CNPJ, status, relatório."""

from datetime import date, timedelta

import pytest

from conftest import DATA_DESAFIO
from robo import config, planilha, relatorio, servico
from robo.extratores import (NaoECobranca, cnpj_valido, extrair_corpo,
                             extrair_nfe, valor_brasileiro)


# --- Extração -------------------------------------------------------------
@pytest.mark.parametrize("texto, esperado", [
    ("742,18", 742.18), ("1.200,00", 1200.0), ("12.345.678,90", 12345678.9),
])
def test_valor_brasileiro(texto, esperado):
    assert valor_brasileiro(texto) == esperado


@pytest.mark.parametrize("cnpj, esperado", [
    ("11.222.333/0001-81", True),     # CNPJ válido conhecido
    ("11222333000181", True),
    ("12.345.678/0001-90", False),    # fictício dos dados de exemplo
    ("11.111.111/1111-11", False),    # todos iguais
    ("123", False),
    (None, None),
])
def test_cnpj_valido(cnpj, esperado):
    assert cnpj_valido(cnpj) is esperado


def test_nfe_com_e_comercial_sem_escape():
    xml = b"""<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe>
    <infNFe><ide><nNF>7</nNF><dhEmi>2026-09-01T10:00:00-03:00</dhEmi></ide>
    <emit><CNPJ>11222333000181</CNPJ><xNome>Silva & Filhos</xNome></emit>
    <total><ICMSTot><vNF>10.50</vNF></ICMSTot></total></infNFe></NFe>
    </nfeProc>"""
    conta = extrair_nfe(xml)
    assert conta["Fornecedor"] == "Silva & Filhos"
    assert conta["Chave"] == "NFE-11222333000181-7"


def test_corpo_com_cobranca():
    texto = ("Identificamos a fatura TS-2026-0917 em aberto.\n"
             "Valor: R$ 349,00\nVencimento: 06/09/2026")
    conta = extrair_corpo(texto, "TechSoft", "billing@techsoft.com.br")
    assert conta["Documento"] == "TS-2026-0917"
    assert conta["Valor (R$)"] == 349.0
    assert conta["Vencimento"] == date(2026, 9, 6)


def test_corpo_sem_cobranca():
    with pytest.raises(NaoECobranca):
        extrair_corpo("Bora almoçar sexta?", "Joana", "joana@x.com")


# --- Status: fronteiras ---------------------------------------------------
@pytest.mark.parametrize("dias, status", [
    (-1, planilha.VENCIDA), (0, planilha.VENCE_7), (7, planilha.VENCE_7),
    (8, planilha.EM_DIA),
])
def test_status_nas_fronteiras(dias, status):
    venc = DATA_DESAFIO + timedelta(days=dias)
    assert planilha.calcular_status(venc, DATA_DESAFIO)[0] == status


def test_conta_paga_vence_qualquer_status():
    venc = DATA_DESAFIO - timedelta(days=30)
    assert planilha.calcular_status(venc, DATA_DESAFIO,
                                    DATA_DESAFIO)[0] == planilha.PAGA


# --- Relatório ------------------------------------------------------------
@pytest.mark.parametrize("freq, ultimo, hoje, devido", [
    ("diario", None, date(2026, 9, 21), True),
    ("diario", date(2026, 9, 21), date(2026, 9, 21), False),
    ("semanal", date(2026, 9, 21), date(2026, 9, 25), False),  # seg -> sex
    ("semanal", date(2026, 9, 25), date(2026, 9, 28), True),   # nova semana
    ("mensal", date(2026, 9, 1), date(2026, 9, 30), False),
    ("mensal", date(2026, 9, 30), date(2026, 10, 1), True),
])
def test_relatorio_devido(freq, ultimo, hoje, devido):
    assert servico.relatorio_devido(freq, ultimo, hoje) is devido


def test_relatorio_lista_vencidas_e_a_vencer():
    contas = [
        {"Status": planilha.VENCIDA, "Vencimento": date(2026, 9, 10),
         "Fornecedor": "A", "Documento": "1", "Valor (R$)": 100.0},
        {"Status": planilha.VENCE_7, "Vencimento": date(2026, 9, 22),
         "Fornecedor": "B", "Documento": "2", "Valor (R$)": 50.0},
        {"Status": planilha.PAGA, "Vencimento": date(2026, 9, 5),
         "Fornecedor": "C", "Documento": "3", "Valor (R$)": 999.0},
    ]
    rel = relatorio.montar(contas, DATA_DESAFIO, "semanal")
    assert "R$ 150,00" in rel.texto          # a paga não entra
    assert "Vencidas: 1" in rel.texto
    assert "C |" not in rel.texto


# --- Configuração ---------------------------------------------------------
def test_env_com_bom_do_bloco_de_notas(tmp_path):
    env = tmp_path / ".env"
    env.write_text("PASTA_SAIDA=minha_saida\n", encoding="utf-8-sig")
    assert config.carregar(env)["PASTA_SAIDA"] == "minha_saida"


def test_senha_vai_para_o_cofre_e_nao_para_o_env(tmp_path):
    env = tmp_path / ".env"
    cfg = dict(config.PADROES, SMTP_SENHA="segredo 123 ")
    config.salvar(cfg, env)
    assert "segredo" not in env.read_text(encoding="utf-8")
    if config._cofre():
        assert config.carregar(env)["SMTP_SENHA"] == "segredo 123 "
    config.salvar(dict(config.PADROES), env)   # limpa o cofre de testes
