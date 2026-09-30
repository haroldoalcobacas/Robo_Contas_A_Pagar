"""
Ponto de entrada do Robô de Contas a Pagar (é o que vira RoboContas.exe).

    main.py                    ícone na bandeja (se já estiver aberto,
                               abre o painel)
    main.py --config           painel de configurações
    main.py --executar         varre e envia o relatório se devido
                               (usado pelo Agendador de Tarefas)
    main.py --relatorio semanal  varre e envia o relatório agora
    main.py --agendar 08:00    cria a tarefa agendada
    main.py --desagendar       remove a tarefa agendada
    main.py --inicio sim|nao   liga/desliga o ícone ao iniciar o Windows
"""

import argparse
import ctypes
import sys

ERRO_JA_EXISTE = 183


def instancia_unica(nome: str) -> bool:
    """True se esta é a única instância com esse nome (mutex do Windows)."""
    instancia_unica.mutex = ctypes.windll.kernel32.CreateMutexW(
        None, False, nome)
    return ctypes.windll.kernel32.GetLastError() != ERRO_JA_EXISTE


def main() -> int:
    p = argparse.ArgumentParser(prog="RoboContas")
    grupo = p.add_mutually_exclusive_group()
    grupo.add_argument("--config", action="store_true")
    grupo.add_argument("--executar", action="store_true")
    grupo.add_argument("--relatorio", choices=["diario", "semanal", "mensal"])
    grupo.add_argument("--agendar", metavar="HH:MM")
    grupo.add_argument("--desagendar", action="store_true")
    grupo.add_argument("--inicio", choices=["sim", "nao"])
    args = p.parse_args()

    if args.executar or args.relatorio:
        import executar
        argv = ["--relatorio", args.relatorio] if args.relatorio else []
        return executar.main(argv)

    from robo import sistema
    if args.agendar:
        sistema.agendar(args.agendar)
        return 0
    if args.desagendar:
        sistema.desagendar()
        return 0
    if args.inicio:
        sistema.definir_inicio_automatico(args.inicio == "sim")
        return 0

    if args.config:
        if not instancia_unica("Local\\RoboContasAPagar_Painel"):
            return 0   # painel já aberto
        import app
        app.App().mainloop()
        return 0

    # Sem argumentos: ícone na bandeja. Se já existe, abre o painel.
    if not instancia_unica("Local\\RoboContasAPagar_Bandeja"):
        sistema.abrir_processo("--config")
        return 0
    from robo.bandeja import Bandeja
    Bandeja().executar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
