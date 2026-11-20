"""Desenha por cima do screenshot o que a visão leu (tipo da frente / tipo de trás)."""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

from bot.board import find_shelves
from bot.vision import Catalog, read_board


def overlay(img: np.ndarray, shelves, views) -> np.ndarray:
    out = img.copy()
    sc = img.shape[1] / 1180
    for s, row in zip(shelves, views):
        for v in row:
            x, y, w, h = s.slot_box(v.slot)
            cx = x + w // 2
            if v.front is not None:
                txt, col = str(v.front), (0, 160, 0)
            elif v.back is not None:
                txt, col = f"b{v.back}", (120, 120, 120)
            else:
                txt, col = "-", (0, 0, 255)
            cv2.rectangle(out, (cx - int(34 * sc), y + 4), (cx + int(34 * sc), y + int(52 * sc)), (255, 255, 255), -1)
            cv2.putText(out, txt, (cx - int(30 * sc), y + int(44 * sc)), cv2.FONT_HERSHEY_SIMPLEX, 1.3 * sc, col, max(1, int(3 * sc)))
    return out


if __name__ == "__main__":
    frames = sorted(Path(sys.argv[1]).glob("*.png"))
    cat = Catalog()
    for p in frames:  # 1.ª passagem: aprender os tipos
        img = cv2.imread(str(p))
        sh = find_shelves(img)
        if len(sh) == 12:
            read_board(img, cat, sh)
    print("tipos:", len(cat.protos), "vistos 2+ vezes:", sum(p.n >= 2 for p in cat.protos))
    for name in sys.argv[2:]:
        img = cv2.imread(name)
        sh, views = read_board(img, cat, learn=False)
        out = overlay(img, sh, views)
        dst = Path(name).with_name(Path(name).stem + "_overlay.png")
        cv2.imwrite(str(dst), cv2.resize(out[650:2250], None, fx=0.5, fy=0.5))
        print(dst)
