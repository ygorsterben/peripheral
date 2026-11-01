"""Extrai o contorno do mouse da imagem de referência (fundo azul-marinho) e imprime um path SVG.

Uso: python tools/contorno_mouse.py IMAGEM
Mouse = pixels neutros (R≈G≈B); fundo = azulado. Ignora as etiquetas (fora da faixa de x do mouse).
"""
import sys
from PIL import Image

img = Image.open(sys.argv[1]).convert('RGB')
W, H = img.size
px = img.load()


def neutro(x, y):
    r, g, b = px[x, y]
    return b - r < 18 and max(r, g, b) < 200


X0, X1 = 230, 515  # faixa do mouse (etiquetas ficam fora)
rows = []
for y in range(H):
    xs = [x for x in range(X0, X1) if neutro(x, y)]
    if len(xs) > 20:
        rows.append((y, xs[0], xs[-1]))

top, bot = rows[0][0], rows[-1][0]
print('topo', top, 'base', bot, 'altura', bot - top)
print('largura máx', max(r - l for _, l, r in rows))
# amostras a cada 8 px para conferência
for y, l, r in rows[::8]:
    print(y, l, r)
