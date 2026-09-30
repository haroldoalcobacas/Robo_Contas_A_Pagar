"""
Ponto único de execução, usado pela tela, pelo ícone da bandeja e pelo
Agendador de Tarefas. Cuida do que está EM VOLTA do processador:

- trava: só um robô por vez (agendador e clique não brigam pela planilha)
- fonte: pasta local ou caixa IMAP, conforme a configuração
- log em arquivo (logs/robo.log), já que o agendador roda sem janela
- estado.json: quando foi o último relatório, para saber se está "devido"
"""

import json
import logging
import logging.handlers
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable

from . import config, relatorio
from .fontes import da_pasta, do_imap
from .processador import Resultado, processar

if sys.platform == "win32":
    import msvcrt


class RoboOcupado(Exception):
    """Outra execução do robô está em andamento."""


# ---------------------------------------------------------------------------
# Trava de execução única
# ---------------------------------------------------------------------------
class Trava:
    """
    Trava por arquivo. O Windows libera o lock sozinho se o processo morrer,
    então não sobra trava "presa" depois de uma queda.
    """

    def __enter__(self):
        config.ARQUIVO_TRAVA.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo = open(config.ARQUIVO_TRAVA, "a+")
        if sys.platform == "win32":
            try:
                self.arquivo.seek(0)
                msvcrt.locking(self.arquivo.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                self.arquivo.close()
                raise RoboOcupado("o robô já está em execução")
        return self

    def __exit__(self, *_):
        if sys.platform == "win32":
            try:
                self.arquivo.seek(0)
                msvcrt.locking(self.arquivo.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        self.arquivo.close()


# ---------------------------------------------------------------------------
# Log em arquivo
# ---------------------------------------------------------------------------
def logger() -> logging.Logger:
    log = logging.getLogger("robo")
    if not log.handlers:
        config.PASTA_LOGS.mkdir(parents=True, exist_ok=True)
        arquivo = logging.handlers.RotatingFileHandler(
            config.PASTA_LOGS / "robo.log", maxBytes=1_000_000,
            backupCount=3, encoding="utf-8")
        arquivo.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s", "%d/%m/%Y %H:%M:%S"))
        log.addHandler(arquivo)
        log.setLevel(logging.INFO)
    return log


# ---------------------------------------------------------------------------
# Estado entre execuções
# ---------------------------------------------------------------------------
def ler_estado() -> dict:
    try:
        return json.loads(config.ARQUIVO_ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def gravar_estado(estado: dict) -> None:
    config.ARQUIVO_ESTADO.parent.mkdir(parents=True, exist_ok=True)
    config.ARQUIVO_ESTADO.write_text(
        json.dumps(estado, indent=2, ensure_ascii=False), encoding="utf-8")


def relatorio_devido(frequencia: str, ultimo: date | None,
                     hoje: date) -> bool:
    """
    Devido se ainda não foi enviado NESTE dia/semana/mês. Assim, se o PC
    ficou desligado no dia marcado, o relatório sai na próxima execução.
    """
    if ultimo is None:
        return True
    if frequencia == "semanal":
        return ultimo.isocalendar()[:2] != hoje.isocalendar()[:2]
    if frequencia == "mensal":
        return (ultimo.year, ultimo.month) != (hoje.year, hoje.month)
    return ultimo != hoje


def algum_canal(cfg: dict) -> bool:
    return "sim" in (cfg.get("RELATORIO_EMAIL"), cfg.get("RELATORIO_WHATSAPP"))


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------
@dataclass
class Execucao:
    resultado: Resultado | None = None
    envios: list[str] = field(default_factory=list)

    @property
    def houve_erro_envio(self) -> bool:
        return any(m.startswith("ERRO") for m in self.envios)


def buscar_emails(cfg: dict, log: Callable[[str], None]):
    if cfg["ORIGEM_EMAILS"] == "imap":
        log(f"Lendo a caixa {cfg['IMAP_USUARIO']} ({cfg['IMAP_PASTA']}, "
            f"últimos {cfg['IMAP_DIAS']} dias)...")
        return do_imap(cfg["IMAP_HOST"], int(cfg["IMAP_PORTA"]),
                       cfg["IMAP_USUARIO"], cfg["IMAP_SENHA"],
                       cfg["IMAP_PASTA"] or "INBOX",
                       int(cfg["IMAP_DIAS"] or 30))
    pasta = config.caminho(cfg, "PASTA_EMAILS")
    if not pasta.is_dir():
        raise FileNotFoundError(f"pasta de e-mails não encontrada: {pasta}")
    log(f"Lendo a pasta {pasta}")
    return da_pasta(pasta)


def rodar(cfg: dict | None = None, relatorio_modo: str = "auto",
          frequencia: str | None = None,
          log: Callable[[str], None] = print) -> Execucao:
    """
    relatorio_modo:
      "auto"   envia se estiver devido e houver canal ligado (agendador)
      "forcar" envia agora, na frequência pedida (botão "Gerar relatório")
      "nao"    só varre e atualiza a planilha
    """
    cfg = cfg or config.carregar()
    arq_log = logger()

    def registrar(texto: str) -> None:
        log(texto)
        if texto.strip():
            arq_log.info(texto.strip())

    execucao = Execucao()
    with Trava():
        registrar(f"=== Execução iniciada ({datetime.now():%d/%m/%Y %H:%M})"
                  " ===")
        emails = buscar_emails(cfg, registrar)
        res = processar(emails, config.arquivo_planilha(cfg),
                        config.data_referencia(cfg),
                        config.pasta_anexos(cfg), log=registrar)
        execucao.resultado = res

        estado = ler_estado()
        estado["ultima_execucao"] = datetime.now().isoformat(
            timespec="seconds")
        freq = frequencia or cfg["RELATORIO_FREQUENCIA"]
        ultimo = (date.fromisoformat(estado["ultimo_relatorio"])
                  if estado.get("ultimo_relatorio") else None)

        enviar = relatorio_modo == "forcar" or (
            relatorio_modo == "auto" and algum_canal(cfg)
            and relatorio_devido(freq, ultimo, date.today()))
        if enviar:
            rel = relatorio.montar(res.contas, res.data_referencia, freq,
                                   desde=ultimo)
            registrar(f"\nEnviando relatório {relatorio.NOME_FREQ[freq]}...")
            execucao.envios = relatorio.enviar(cfg, rel, res.arquivo_saida)
            for msg in execucao.envios:
                registrar(f"  {msg}")
            if not execucao.houve_erro_envio:
                estado["ultimo_relatorio"] = date.today().isoformat()
        gravar_estado(estado)
    return execucao
