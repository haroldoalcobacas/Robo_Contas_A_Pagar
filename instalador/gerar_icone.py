"""Gera instalador/robo.ico a partir do desenho usado na bandeja."""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from robo.bandeja import desenhar_icone  # noqa: E402

destino = Path(__file__).with_name("robo.ico")
imagem = desenhar_icone("verde", 256)
imagem.save(destino, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                            (64, 64), (128, 128), (256, 256)])
print(f"Ícone gerado: {destino}")
