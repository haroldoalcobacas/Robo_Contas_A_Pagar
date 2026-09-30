"""
Planilha aberta no Excel: o robô deve perceber ANTES de processar.

O Excel trava o arquivo abrindo-o sem compartilhar a escrita. Aqui o mesmo
efeito é simulado abrindo o arquivo com acesso exclusivo pela API do Windows.
"""

import ctypes
from contextlib import contextmanager

import pytest

from robo import config, excel, servico
from robo.planilha import PlanilhaBloqueada

GENERIC_READ, OPEN_EXISTING, SEM_COMPARTILHAR = 0x80000000, 3, 0


@contextmanager
def travado(arquivo):
    """Segura o arquivo como o Excel faz enquanto ele está aberto."""
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateFileW.restype = ctypes.c_void_p
    handle = kernel32.CreateFileW(str(arquivo), GENERIC_READ,
                                  SEM_COMPARTILHAR, None, OPEN_EXISTING,
                                  0, None)
    assert handle not in (None, ctypes.c_void_p(-1).value)
    try:
        yield
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))


def test_detecta_planilha_aberta(tmp_path):
    arquivo = tmp_path / "contas.xlsx"
    arquivo.write_bytes(b"conteudo")
    assert excel.planilha_aberta(arquivo) is False
    with travado(arquivo):
        assert excel.planilha_aberta(arquivo) is True
    assert excel.planilha_aberta(arquivo) is False


def test_planilha_inexistente_nao_esta_aberta(tmp_path):
    assert excel.planilha_aberta(tmp_path / "nao_existe.xlsx") is False


def test_varredura_para_antes_de_processar(tmp_path):
    """Com a planilha aberta, nada é processado e o erro sai no início."""
    from conftest import PASTA_EXEMPLOS

    cfg = dict(config.PADROES, PASTA_EMAILS=str(PASTA_EXEMPLOS),
               PASTA_SAIDA=str(tmp_path), SALVAR_ANEXOS="nao",
               DATA_REFERENCIA="2026-09-20")
    servico.rodar(cfg, relatorio_modo="nao", log=lambda _: None)
    arquivo = config.arquivo_planilha(cfg)
    antes = arquivo.stat().st_mtime

    mensagens = []
    with travado(arquivo), pytest.raises(PlanilhaBloqueada):
        servico.rodar(cfg, relatorio_modo="nao", log=mensagens.append)

    assert arquivo.stat().st_mtime == antes          # não foi regravada
    assert any("está aberta no Excel" in m for m in mensagens)
    assert not any("e-mails para analisar" in m for m in mensagens)
