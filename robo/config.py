"""
Configuração do robô: leitura e gravação do arquivo .env.

O .env guarda caminhos, credenciais e preferências de relatório. Ele fica
fora do Git (ver .gitignore), então nenhuma senha vai parar no código.
"""

from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO_ENV = RAIZ / ".env"

# Todas as chaves conhecidas, agrupadas por seção, com o valor padrão.
# A ordem aqui é a ordem em que aparecem no .env salvo pela tela.
SECOES: dict[str, dict[str, str]] = {
    "Execução": {
        "PASTA_EMAILS": "dados/caixa_de_entrada",
        "PASTA_SAIDA": "saida",
        "NOME_PLANILHA": "contas_a_pagar.xlsx",
        # Vazio = usar a data de hoje. Formato AAAA-MM-DD.
        "DATA_REFERENCIA": "2026-09-20",
    },
    "Leitura de e-mail": {
        "ORIGEM_EMAILS": "pasta",          # pasta | imap
        "IMAP_HOST": "imap.gmail.com",
        "IMAP_PORTA": "993",
        "IMAP_USUARIO": "",
        "IMAP_SENHA": "",
        "IMAP_PASTA": "INBOX",
    },
    "Relatório": {
        "RELATORIO_EMAIL": "nao",          # sim | nao
        "RELATORIO_WHATSAPP": "nao",       # sim | nao
        "RELATORIO_FREQUENCIA": "diario",  # diario | semanal | mensal
        "SMTP_HOST": "smtp.gmail.com",
        "SMTP_PORTA": "587",
        "SMTP_USUARIO": "",
        "SMTP_SENHA": "",
        "EMAIL_DESTINATARIOS": "",
        "WHATSAPP_NUMERO": "",             # com DDI, ex.: 5511999998888
        "WHATSAPP_APIKEY": "",             # chave do CallMeBot
    },
}

PADROES = {k: v for secao in SECOES.values() for k, v in secao.items()}


def _tirar_aspas(valor: str) -> str:
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
        return valor[1:-1]
    return valor


def carregar(caminho: Path = ARQUIVO_ENV) -> dict[str, str]:
    """Devolve a configuração: padrões sobrescritos pelo que houver no .env."""
    cfg = dict(PADROES)
    if caminho.exists():
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            cfg[chave.strip()] = _tirar_aspas(valor.strip())
    return cfg


def salvar(cfg: dict[str, str], caminho: Path = ARQUIVO_ENV) -> None:
    """Grava a configuração no .env, organizada por seção."""
    linhas = [
        "# Configuração do Robô de Contas a Pagar",
        "# Gerado pela tela de configurações. NÃO vai para o Git.",
    ]
    for secao, chaves in SECOES.items():
        linhas += ["", f"# --- {secao} ---"]
        for chave in chaves:
            valor = str(cfg.get(chave, ""))
            # Aspas protegem espaços nas pontas e aspas no próprio valor
            if valor != valor.strip() or valor.startswith(("\"", "'")):
                valor = f'"{valor}"'
            linhas.append(f"{chave}={valor}")
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def caminho(cfg: dict[str, str], chave: str) -> Path:
    """Converte um caminho do .env em Path absoluto (relativo à raiz)."""
    p = Path(cfg[chave]).expanduser()
    return p if p.is_absolute() else RAIZ / p


def data_referencia(cfg: dict[str, str]) -> date:
    """Data usada nos alertas. Vazia no .env = hoje."""
    valor = cfg.get("DATA_REFERENCIA", "").strip()
    return date.fromisoformat(valor) if valor else date.today()
