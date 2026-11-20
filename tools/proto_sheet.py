"""Corre a visão sobre os frames de uma tentativa e desenha os protótipos aprendidos lado a lado,
com o número de vezes que cada um foi reconhecido. Serve para encontrar produtos partidos em dois tipos.

    .venv/bin/python -m tools.proto_sheet runs/20261120-135758 rec/protos.png
"""
from __future__ import annotations

import glob
import sys

import cv2
import numpy as np

from bot.board import Shelf
from bot.conveyor import detect_full
from bot.vision import Catalog, read_board


def learn(folder: str, cat: Catalog | None = None, limit: int = 400) -> Catalog:
    cat = cat or Catalog()
    for f in (sorted(glob.glob(f"{folder}/raw_*.jpg")) or sorted(glob.glob(f"{folder}/*.jpg")))[:limit]:
        img = cv2.imread(f)
        sh = detect_full(img)
        if len(sh) < 4:
            continue
        read_board(img, cat, [Shelf(i, s.x, s.y, s.w, s.h) for i, s in enumerate(sh)])
    return cat


def sheet(cat: Catalog, path: str, cell: int = 110) -> None:
    n = len(cat.protos)
    cols = 8
    rows = (n + cols - 1) // cols
    out = np.full((rows * (cell + 22), cols * cell, 3), 255, np.uint8)
    for t, p in enumerate(cat.protos):
        im = p.img.astype(np.uint8) if p.img.dtype != np.uint8 else p.img
        h, w = im.shape[:2]
        s = min((cell - 6) / w, (cell - 6) / h)
        im = cv2.resize(im, (max(1, int(w * s)), max(1, int(h * s))))
        r, c = divmod(t, cols)
        y0, x0 = r * (cell + 22) + 20, c * cell + 3
        out[y0 : y0 + im.shape[0], x0 : x0 + im.shape[1]] = im
        cv2.putText(out, f"{t}: n={p.n}", (x0, y0 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 200), 1)
    cv2.imwrite(path, out)


if __name__ == "__main__":
    cat = learn(sys.argv[1])
    sheet(cat, sys.argv[2])
    print(len(cat.protos), "protótipos;", [p.n for p in cat.protos])
