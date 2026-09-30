"""
Configuração dos testes.

Isola TUDO antes de importar o robô: pasta de dados temporária (nada de
.env, log ou planilha do projeto) e cofre de senhas separado (as senhas
reais do Gerenciador de Credenciais nunca são tocadas).
"""

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ["ROBO_DADOS"] = tempfile.mkdtemp(prefix="robo_testes_")

from robo import config  # noqa: E402
from robo.fontes import da_pasta  # noqa: E402

config.SERVICO_COFRE = "RoboContasAPagar_testes"

DATA_DESAFIO = date(2026, 9, 20)
PASTA_EXEMPLOS = RAIZ / "dados" / "caixa_de_entrada"


@pytest.fixture
def emails():
    """Os 14 e-mails de exemplo do desafio."""
    return da_pasta(PASTA_EXEMPLOS)


@pytest.fixture
def planilha_tmp(tmp_path) -> Path:
    return tmp_path / "contas_a_pagar.xlsx"
