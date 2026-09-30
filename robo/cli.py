"""
Execução sem tela, usando as configurações salvas.
É o que o Agendador de Tarefas chama (via main.py --executar).

Códigos de saída: 0 = ok, 1 = erro, 2 = varreu, mas algum envio falhou.
"""

from .planilha import PlanilhaBloqueada
from .servico import RoboOcupado, rodar


def executar(relatorio_modo: str = "auto",
             frequencia: str | None = None) -> int:
    """
    relatorio_modo: "auto" (envia se devido), "forcar" (envia agora)
    ou "nao" (só varre). Mensagens vão para o terminal e para logs/robo.log.
    """
    try:
        execucao = rodar(relatorio_modo=relatorio_modo, frequencia=frequencia)
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
