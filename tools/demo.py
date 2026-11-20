"""Gera um GIF de demonstração a partir de uma gravação: o que o bot lê + a jogada que escolhe."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import cv2

from bot.board import find_shelves
from bot.run import draw_moves, to_obs
from bot.solver import plan, to_moves
from bot.vision import Catalog, read_board
from tools.overlay import overlay


def main(frames_dir: str, out_gif: str):
    files = sorted(Path(frames_dir).glob("*.png"))
    cat = Catalog()
    for p in files:  # aprender os tipos primeiro
        img = cv2.imread(str(p))
        sh = find_shelves(img)
        if len(sh) == 12:
            read_board(img, cat, sh)
    tmp = Path(tempfile.mkdtemp())
    n = 0
    for p in files:
        img = cv2.imread(str(p))
        sh = find_shelves(img)
        if len(sh) != 12:
            continue
        _, views = read_board(img, cat, sh, learn=False)
        moves = to_moves(to_obs(views), plan(to_obs(views)))
        frame = draw_moves(overlay(img, sh, views), sh, moves)
        y0, y1 = sh[0].y - 60, sh[-1].y + sh[-1].h + 40
        frame = cv2.resize(frame[y0:y1], (420, int((y1 - y0) * 420 / img.shape[1])))
        cv2.imwrite(str(tmp / f"{n:03d}.png"), frame)
        n += 1
    from PIL import Image

    imgs = [Image.open(f).convert("RGB") for f in sorted(tmp.glob("*.png"))]
    imgs[0].save(out_gif, save_all=True, append_images=imgs[1:], duration=700, loop=0, optimize=True)
    print(f"{n} frames -> {out_gif}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
