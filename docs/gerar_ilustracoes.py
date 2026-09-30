"""
Gera as ilustrações da documentação (docs/img e docs/exemplos) a partir do
sistema rodando de verdade com a base de exemplo.

Uso, na raiz do projeto:
    python docs/gerar_ilustracoes.py

Precisa de Windows, Excel (para fotografar a planilha) e Microsoft Edge
(para fotografar o e-mail do relatório). O que faltar é pulado com aviso.
"""

import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

IMG = RAIZ / "docs" / "img"
EXEMPLOS = RAIZ / "docs" / "exemplos"

# Dados isolados, numa pasta neutra (sem nome de usuário nas imagens):
# não mexe no .env, na planilha nem no log do projeto.
DADOS = Path(os.environ.get("PUBLIC", tempfile.gettempdir())) / \
    "RoboContas_docs"
shutil.rmtree(DADOS, ignore_errors=True)
shutil.copytree(RAIZ / "dados" / "caixa_de_entrada",
                DADOS / "dados" / "caixa_de_entrada")
os.environ["ROBO_DADOS"] = str(DADOS)
ctypes.windll.shcore.SetProcessDpiAwareness(1)   # capturas nítidas

from PIL import Image, ImageGrab  # noqa: E402

from robo import config, relatorio, servico  # noqa: E402
from robo.bandeja import desenhar_icone  # noqa: E402

# Cofre separado: salvar a configuração de exemplo (sem senhas) não pode
# apagar as senhas reais guardadas no Gerenciador de Credenciais.
config.SERVICO_COFRE = "RoboContasAPagar_docs"

# Caminhos relativos à pasta de dados, como no uso pelo código-fonte
CFG = dict(config.PADROES,
           PASTA_EMAILS="dados/caixa_de_entrada",
           PASTA_SAIDA="saida",
           DATA_REFERENCIA="2026-09-20")


def passo(texto: str) -> None:
    print(f"- {texto}")


def rodar_robo():
    config.salvar(CFG)
    return servico.rodar(CFG, relatorio_modo="nao", log=lambda s: None)


def icones() -> None:
    faixa = Image.new("RGBA", (3 * 96 + 40, 96), (0, 0, 0, 0))
    for i, cor in enumerate(["verde", "amarelo", "vermelho"]):
        faixa.paste(desenhar_icone(cor, 96), (i * 116, 0))
    faixa.save(IMG / "icones.png")
    desenhar_icone("vermelho", 128).save(IMG / "icone.png")
    passo("ícones")


def paineis() -> None:
    from robo.painel import App
    janela = App()
    janela.geometry("940x720+60+40")
    janela.attributes("-topmost", True)
    janela.update()
    janela.executar()
    fim = time.time() + 60
    while janela.executando and time.time() < fim:
        janela.update()
        time.sleep(0.05)

    abas = janela.nametowidget(janela.winfo_children()[1])
    nomes = ["1_executar", "2_leitura_email", "3_relatorio", "4_automacao"]
    for i, nome in enumerate(nomes):
        abas.select(i)
        for _ in range(10):
            janela.update()
            time.sleep(0.05)
        x, y = janela.winfo_rootx(), janela.winfo_rooty()
        w, h = janela.winfo_width(), janela.winfo_height()
        ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(
            IMG / f"painel_{nome}.png")
    janela.destroy()
    passo("painel (4 abas)")


def exemplos_relatorio(execucao) -> None:
    res = execucao.resultado
    rel = relatorio.montar(res.contas, res.data_referencia, "semanal")
    html = ("<!doctype html><meta charset='utf-8'>"
            "<body style='margin:24px;background:#fff'>"
            f"<p style='font-family:Segoe UI,Arial;color:#555'>"
            f"<b>Assunto:</b> {rel.assunto}</p><hr>{rel.html}</body>")
    (EXEMPLOS / "relatorio_email.html").write_text(html, encoding="utf-8")
    (EXEMPLOS / "relatorio_whatsapp.txt").write_text(
        rel.texto, encoding="utf-8")
    passo("exemplos do relatório (HTML e WhatsApp)")

    edge = next((p for p in [
        Path(os.environ.get("ProgramFiles(x86)", "")) /
        "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("ProgramFiles", "")) /
        "Microsoft/Edge/Application/msedge.exe"] if p.exists()), None)
    if not edge:
        passo("AVISO: Edge não encontrado, sem imagem do e-mail")
        return
    destino = IMG / "relatorio_email.png"
    subprocess.run([str(edge), "--headless", "--disable-gpu",
                    "--hide-scrollbars", "--window-size=820,900",
                    f"--screenshot={destino}",
                    (EXEMPLOS / "relatorio_email.html").as_uri()],
                   capture_output=True, timeout=60)
    _recortar_branco(destino)
    passo("imagem do e-mail do relatório")


def _recortar_branco(arquivo: Path) -> None:
    """Tira a sobra branca embaixo da captura do navegador."""
    img = Image.open(arquivo).convert("RGB")
    fundo = Image.new("RGB", img.size, (255, 255, 255))
    from PIL import ImageChops
    caixa = ImageChops.difference(img, fundo).getbbox()
    if caixa:
        img.crop((0, 0, img.width, min(img.height, caixa[3] + 24))).save(
            arquivo)


def planilha() -> None:
    arquivo = config.arquivo_planilha(CFG)
    script = f"""
$ErrorActionPreference = 'Stop'
$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false; $xl.DisplayAlerts = $false
try {{
  $wb = $xl.Workbooks.Open('{arquivo}', 0, $true)
  foreach ($p in @(@('Contas a Pagar','A1:J19','planilha_contas.png'),
                   @('Resumo','A1:C17','planilha_resumo.png'))) {{
    $wb.Worksheets.Item($p[0]).Range($p[1]).CopyPicture(1, 2)
    Start-Sleep -Milliseconds 500
    & '{sys.executable}' -c "from PIL import ImageGrab; ImageGrab.grabclipboard().save(r'{IMG}\\$($p[2])')"
  }}
  $wb.Close($false)
}} finally {{ $xl.Quit() }}
"""
    ps1 = DADOS / "capturar.ps1"
    ps1.write_text(script, encoding="utf-8-sig")
    r = subprocess.run(["powershell", "-STA", "-NoProfile",
                        "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        passo(f"AVISO: planilha não capturada (Excel?): {r.stderr[:200]}")
        return
    passo("planilha (Contas a Pagar e Resumo)")


def main() -> None:
    IMG.mkdir(parents=True, exist_ok=True)
    EXEMPLOS.mkdir(parents=True, exist_ok=True)
    print(f"Gerando ilustrações em {IMG.parent}")
    execucao = rodar_robo()
    icones()
    exemplos_relatorio(execucao)
    planilha()
    paineis()
    # Fecha o log em arquivo antes de apagar a pasta temporária
    for handler in servico.logger().handlers:
        handler.close()
    shutil.rmtree(DADOS, ignore_errors=True)
    print("Pronto.")


if __name__ == "__main__":
    main()
