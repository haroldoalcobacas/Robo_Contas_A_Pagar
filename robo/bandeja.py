"""
Ícone na bandeja do sistema (ao lado do relógio).

Clique esquerdo: abre o painel. Clique direito: menu com Escanear agora,
Gerar relatório, Abrir planilha, Configurações e Sair.

O ícone muda de cor conforme a situação das contas:
verde = em dia, amarelo = vence em até 7 dias, vermelho = há vencidas.
Quando o Agendador roda o robô em segundo plano, o ícone percebe (pelo
estado.json) e mostra uma notificação.
"""

import os
import threading
import time

import pystray
from PIL import Image, ImageDraw

from . import config, excel, planilha, servico, sistema
from .relatorio import NOME_FREQ, brl

CORES = {"verde": (46, 160, 67), "amarelo": (230, 170, 0),
         "vermelho": (210, 50, 50), "cinza": (120, 120, 120)}
INTERVALO_VERIFICACAO = 30   # segundos


def desenhar_icone(cor: str = "cinza", tamanho: int = 64) -> Image.Image:
    """Cabeça de robô desenhada em código (não precisa de arquivo)."""
    s = tamanho / 64
    img = Image.new("RGBA", (tamanho, tamanho), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rgb = CORES[cor]
    d.line([(32 * s, 4 * s), (32 * s, 14 * s)], fill=rgb, width=int(4 * s))
    d.ellipse([27 * s, 1 * s, 37 * s, 11 * s], fill=rgb)
    d.rounded_rectangle([6 * s, 14 * s, 58 * s, 60 * s], radius=12 * s,
                        fill=rgb)
    for x in (20, 44):
        d.ellipse([(x - 7) * s, 26 * s, (x + 7) * s, 40 * s], fill="white")
        d.ellipse([(x - 3) * s, 30 * s, (x + 3) * s, 36 * s],
                  fill=(30, 30, 30))
    d.rounded_rectangle([20 * s, 46 * s, 44 * s, 52 * s], radius=3 * s,
                        fill="white")
    return img


def situacao(cfg: dict) -> tuple[str, str]:
    """(cor, texto da dica) a partir da planilha atual."""
    try:
        contas = planilha.ler_contas(config.arquivo_planilha(cfg))
    except Exception:
        return "cinza", "Robô de Contas a Pagar"
    ref = config.data_referencia(cfg)
    abertas = []
    for c in contas:
        status, _ = planilha.calcular_status(c.get("Vencimento"), ref,
                                             c.get("Pago em"))
        if status in planilha.EM_ABERTO:
            abertas.append((status, c))
    if not contas:
        return "cinza", "Robô de Contas a Pagar: nenhuma conta ainda"
    vencidas = sum(1 for s, _ in abertas if s == planilha.VENCIDA)
    vencendo = sum(1 for s, _ in abertas if s == planilha.VENCE_7)
    total = brl(sum(c["Valor (R$)"] for _, c in abertas))
    cor = "vermelho" if vencidas else "amarelo" if vencendo else "verde"
    # A dica da bandeja do Windows aceita no máximo 127 caracteres
    dica = (f"Contas a Pagar: {total} em aberto\n"
            f"{vencidas} vencida(s), {vencendo} vencendo em 7 dias")
    return cor, dica[:127]


class Bandeja:
    def __init__(self) -> None:
        self.ocupado = threading.Lock()
        self.ultima_execucao = servico.ler_estado().get("ultima_execucao")
        self.ativo = True
        freq = pystray.Menu(*[
            pystray.MenuItem(NOME_FREQ[f].capitalize(),
                             self._acao_relatorio(f))
            for f in ("diario", "semanal", "mensal")])
        menu = pystray.Menu(
            pystray.MenuItem("Abrir painel", self.abrir_painel,
                             default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Escanear agora", self.escanear),
            pystray.MenuItem("Gerar e enviar relatório", freq),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Abrir planilha", self.abrir_planilha),
            pystray.MenuItem("Abrir pasta de anexos", self.abrir_anexos),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sair", self.sair),
        )
        self.icone = pystray.Icon(sistema.NOME_APP, desenhar_icone(),
                                  "Robô de Contas a Pagar", menu)

    # --- ciclo de vida -------------------------------------------------
    def executar(self) -> None:
        self.icone.run(setup=self._iniciar)

    def _iniciar(self, icone) -> None:
        icone.visible = True
        self.atualizar()
        threading.Thread(target=self._vigiar, daemon=True).start()

    def _vigiar(self) -> None:
        """Percebe execuções feitas pelo Agendador e atualiza o ícone."""
        while self.ativo:
            time.sleep(INTERVALO_VERIFICACAO)
            atual = servico.ler_estado().get("ultima_execucao")
            if atual and atual != self.ultima_execucao \
                    and not self.ocupado.locked():
                self.ultima_execucao = atual
                self.atualizar()
                self.notificar("Varredura automática concluída",
                               self.icone.title)
            else:
                self.atualizar()   # o dia vira: contas mudam de status

    def atualizar(self) -> None:
        cor, dica = situacao(config.carregar())
        self.icone.icon = desenhar_icone(cor)
        self.icone.title = dica

    def notificar(self, titulo: str, texto: str) -> None:
        try:
            self.icone.notify(texto[:250], titulo[:60])
        except Exception:
            pass

    def sair(self) -> None:
        self.ativo = False
        self.icone.stop()

    # --- ações do menu -------------------------------------------------
    @staticmethod
    def _liberar_planilha(titulo: str) -> bool:
        """Planilha aberta no Excel? Pergunta se deve salvar e fechar."""
        arquivo = config.arquivo_planilha(config.carregar())
        if not excel.planilha_aberta(arquivo):
            return True
        nome = arquivo.name
        if not excel.perguntar_nativo(
                titulo, excel.TEXTO_PERGUNTA.format(nome=nome)):
            excel.avisar_nativo(titulo, excel.TEXTO_FECHE.format(nome=nome))
            return False
        ok, mensagem = excel.salvar_e_fechar(arquivo)
        if not ok:
            excel.avisar_nativo(
                titulo, f"Não foi possível fechar a planilha: {mensagem}."
                f"\n\n" + excel.TEXTO_FECHE.format(nome=nome), erro=True)
        return ok

    def _em_segundo_plano(self, titulo: str, **kwargs) -> None:
        if not self.ocupado.acquire(blocking=False):
            self.notificar(titulo, "Já existe uma execução em andamento.")
            return

        def tarefa():
            try:
                if not self._liberar_planilha(titulo):
                    return
                self.icone.title = f"{titulo}..."
                execucao = servico.rodar(log=lambda s: None, **kwargs)
                res = execucao.resultado
                texto = (f"{len(res.abertas)} contas em aberto: "
                         f"{brl(res.total)}\n"
                         f"{len(res.por_status(planilha.VENCIDA))} "
                         f"vencida(s), {len(res.novas)} nova(s), "
                         f"{len(res.excecoes)} exceção(ões)")
                if execucao.envios:
                    texto += "\n" + "\n".join(execucao.envios)
                self.ultima_execucao = servico.ler_estado().get(
                    "ultima_execucao")
                self.notificar(titulo, texto)
            except servico.RoboOcupado:
                self.notificar(titulo, "O robô já está em execução "
                               "(agendador). Tente em instantes.")
            except planilha.PlanilhaBloqueada:
                self.notificar(titulo, "Feche a planilha no Excel e tente "
                               "de novo.")
            except Exception as erro:
                servico.logger().exception("erro na bandeja")
                self.notificar(f"{titulo}: erro", str(erro))
            finally:
                self.ocupado.release()
                self.atualizar()

        threading.Thread(target=tarefa, daemon=True).start()

    def escanear(self) -> None:
        self._em_segundo_plano("Escanear", relatorio_modo="nao")

    def _acao_relatorio(self, frequencia: str):
        def acao():
            self._em_segundo_plano(
                f"Relatório {NOME_FREQ[frequencia]}",
                relatorio_modo="forcar", frequencia=frequencia)
        return acao

    def abrir_painel(self) -> None:
        sistema.abrir_processo("--config")

    def abrir_planilha(self) -> None:
        arquivo = config.arquivo_planilha(config.carregar())
        if arquivo.exists():
            os.startfile(arquivo)
        else:
            self.notificar("Planilha", "Ainda não gerada. Use "
                           "'Escanear agora'.")

    def abrir_anexos(self) -> None:
        cfg = config.carregar()
        pasta = config.pasta_anexos(cfg) or config.caminho(cfg,
                                                           "PASTA_SAIDA")
        pasta.mkdir(parents=True, exist_ok=True)
        os.startfile(pasta)
