"""
Executa o robô sem tela, usando as configurações do .env.
Útil para rodar pelo terminal ou pelo Agendador de Tarefas do Windows.

Uso:
    python executar.py
"""

import sys

from robo import config
from robo.planilha import PlanilhaBloqueada
from robo.processador import processar


def main() -> int:
    cfg = config.carregar()
    if cfg["ORIGEM_EMAILS"] == "imap":
        print("[AVISO] Leitura via IMAP chega no Nível 3. "
              "Usando a pasta local.")
    pasta = config.caminho(cfg, "PASTA_EMAILS")
    if not pasta.is_dir():
        print(f"[ERRO] Pasta de e-mails não encontrada: {pasta}")
        return 1
    saida = config.caminho(cfg, "PASTA_SAIDA") / cfg["NOME_PLANILHA"]
    try:
        processar(pasta, saida, config.data_referencia(cfg))
    except PlanilhaBloqueada:
        print(f"\n[ERRO] Não foi possível gravar {saida.name}: "
              "feche a planilha no Excel e rode de novo.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
