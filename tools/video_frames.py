"""Extrai os frames "parados" (sem animação) de uma gravação de ecrã do jogo."""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np


def stable_frames(video: str, step_s: float = 0.1, thr: float = 1.2):
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    step = max(1, int(round(fps * step_s)))
    frames, i = [], 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if i % step == 0:
            frames.append((i / fps, f))
        i += 1
    out = []
    for j in range(1, len(frames) - 1):
        t, f = frames[j]
        g = lambda k: cv2.cvtColor(cv2.resize(frames[k][1], None, fx=0.25, fy=0.25), cv2.COLOR_BGR2GRAY).astype(int)
        d1 = np.abs(g(j) - g(j - 1)).mean()
        d2 = np.abs(g(j) - g(j + 1)).mean()
        if d1 < thr and d2 < thr:
            out.append((t, f))
    return out


if __name__ == "__main__":
    video, outdir = sys.argv[1], Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)
    fr = stable_frames(video)
    last = None
    n = 0
    for t, f in fr:
        small = cv2.resize(f, None, fx=0.25, fy=0.25).astype(int)
        if last is not None and np.abs(small - last).mean() < 0.8:
            continue  # igual ao anterior guardado
        last = small
        cv2.imwrite(str(outdir / f"t{t:06.2f}.png"), f)
        n += 1
    print(f"{n} frames estáveis distintos guardados em {outdir}")
