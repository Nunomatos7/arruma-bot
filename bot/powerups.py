"""Botões dos power-ups: três círculos vermelhos em baixo (martelo, relógio, baralhar).

Em vez de posições fixas (que só serviam para o ecrã do iPhone), procura os círculos na imagem.
Assim funciona em telemóveis com outras proporções ou com a barra de navegação do Android.
"""
from __future__ import annotations

import cv2
import numpy as np

# posições no iPhone (fração da largura/altura), usadas se a deteção falhar
DEFAULT = {"martelo": (0.245, 0.925), "relogio": (0.5, 0.925), "baralhar": (0.755, 0.925)}


def find_powerups(img: np.ndarray) -> list[tuple[int, int]]:
    """Centros dos botões vermelhos redondos no quarto de baixo do ecrã, da esquerda para a direita."""
    H, W = img.shape[:2]
    y0 = int(H * 0.75)
    hsv = cv2.cvtColor(img[y0:], cv2.COLOR_BGR2HSV)
    red = cv2.inRange(hsv, np.array((0, 140, 120)), np.array((10, 255, 255)))
    red |= cv2.inRange(hsv, np.array((170, 140, 120)), np.array((180, 255, 255)))
    red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _, st, cent = cv2.connectedComponentsWithStats(red, 8)
    found = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if w < W * 0.08 or h < W * 0.08 or not (0.75 < w / h < 1.33) or a < 0.4 * w * h:
            continue
        found.append((int(cent[i][0]), int(cent[i][1]) + y0))
    return sorted(found)


def buttons(img: np.ndarray) -> dict[str, tuple[int, int]]:
    """{'martelo': (x, y), 'relogio': ..., 'baralhar': ...}: detetados, ou as posições do iPhone."""
    H, W = img.shape[:2]
    f = find_powerups(img)
    if len(f) == 3:
        return dict(zip(("martelo", "relogio", "baralhar"), f))
    return {k: (int(W * fx), int(H * fy)) for k, (fx, fy) in DEFAULT.items()}
