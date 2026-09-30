"""
Executa o robô sem tela, usando as configurações salvas.
É o que o Agendador de Tarefas chama.

Uso:
    python executar.py                     varre e envia o relatório se devido
    python executar.py --relatorio semanal varre e envia o relatório agora
    python executar.py --sem-relatorio     só varre
"""

import argparse
import sys

from robo.planilha import PlanilhaBloqueada
from robo.servico import RoboOcupado, rodar


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Robô de Contas a Pagar")
    p.add_argument("--relatorio", choices=["diario", "semanal", "mensal"],
                   help="envia o relatório agora, nesta frequência")
    p.add_argument("--sem-relatorio", action="store_true",
                   help="só varre e atualiza a planilha")
    args = p.parse_args(argv)

    modo = "nao" if args.sem_relatorio else (
        "forcar" if args.relatorio else "auto")
    try:
        execucao = rodar(relatorio_modo=modo, frequencia=args.relatorio)
    except RoboOcupado:
        print("[AVISO] O robô já está em execução. Nada a fazer.")
        return 0
    except PlanilhaBloqueada as erro:
        print(f"\n[ERRO] Não foi possível gravar {erro}: feche a planilha "
              "no Excel e rode de novo.")
        return 1
    except Exception as erro:
        print(f"\n[ERRO] {type(erro).__name__}: {erro}")
        return 1
    return 2 if execucao.houve_erro_envio else 0


if __name__ == "__main__":
    sys.exit(main())
