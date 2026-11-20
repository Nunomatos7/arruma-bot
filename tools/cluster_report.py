"""Corre a visão sobre frames e gera uma folha com exemplos de cada tipo aprendido.

Serve para verificar a olho que cada linha da folha tem um único tipo de produto.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

from bot.board import find_shelves
from bot.vision import Catalog, _canon, _slot_range, read_board


def main(frames_dir: str, out: str, thr: float | None = None):
    cat = Catalog() if thr is None else Catalog(thr=thr)
    samples: dict[int, list[np.ndarray]] = {}
    dists = []
    files = sorted(Path(frames_dir).glob("*.png"))
    for p in files:
        img = cv2.imread(str(p))
        shelves = find_shelves(img)
        if len(shelves) != 12:
            continue
        _, views = read_board(img, cat, shelves)
        for s, row in zip(shelves, views):
            for v in row:
                if v.front is None:
                    continue
                cc = _canon(img, s); a, b = _slot_range(v.slot); c = cv2.resize(cc[:, a:b], (60, 90))
                samples.setdefault(v.front, []).append(c)
    print(f"{len(files)} frames, {len(cat.protos)} tipos")
    # distâncias mínimas entre protótipos (quanto maior, mais separados)
    P = np.stack([np.zeros(1)] * len(cat.protos))
    D = np.linalg.norm(P[:, None] - P[None], axis=2) + np.eye(len(P)) * 99
    print("distância mínima entre tipos:", np.round(np.sort(D.min(1))[:8], 2).tolist())
    rows = []
    for t in sorted(samples):
        ss = samples[t]
        pick = [ss[i] for i in np.linspace(0, len(ss) - 1, min(12, len(ss))).astype(int)]
        row = np.full((90, 60 * 13, 3), 255, np.uint8)
        cv2.putText(row, f"{t}", (5, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        cv2.putText(row, f"n{len(ss)}", (2, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        for i, c in enumerate(pick):
            row[:, 60 * (i + 1) : 60 * (i + 2)] = c
        rows.append(row)
    cv2.imwrite(out, np.vstack(rows))
    return cat


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else None)
