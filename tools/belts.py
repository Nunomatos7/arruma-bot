"""Analisa uma gravação de um nível com passadeiras: velocidade, comprimento da volta e
quantas prateleiras tem cada passadeira. Gera também um "panorama" de cada passadeira.

    .venv/bin/python -m tools.belts rec/l26_belts
"""
from __future__ import annotations

import glob
import re
import sys

import cv2
import numpy as np

BANDS = {"linha2": (1116, 1412), "linha3": (1511, 1807)}
PITCH = 345  # distância entre prateleiras (px, ecrã de 1178)


def main(folder: str):
    fs = sorted(glob.glob(f"{folder}/*.jpg"))
    ts = np.array([float(re.search(r"_(-?\d+\.\d+)\.jpg", f).group(1)) for f in fs])
    imgs = [cv2.imread(f) for f in fs]
    W = imgs[0].shape[1]
    for name, (y0, y1) in BANDS.items():
        strips = [cv2.cvtColor(im[y0:y1], cv2.COLOR_BGR2GRAY).astype(np.float32) for im in imgs]
        dx = [0.0]
        for a, b in zip(strips, strips[1:]):
            (d, _), _ = cv2.phaseCorrelate(a, b)
            dx.append(d)
        cum = np.cumsum(dx)
        v = np.polyfit(ts, cum, 1)[0]
        resid = cum - np.polyval(np.polyfit(ts, cum, 1), ts)
        # panorama: cada coluna do mundo da passadeira, vista no frame em que estava ao centro
        total = int(abs(cum[-1])) + W
        pano = np.zeros((y1 - y0, total, 3), np.uint8)
        for im, c in zip(imgs, cum):
            # o píxel x do ecrã está na posição (x - c) da passadeira
            shift = int(round(cum.max() - c))
            s = max(0, shift)
            e = min(total, shift + W)
            if e > s:
                pano[:, s:e] = im[y0:y1, s - shift : e - shift]
        cv2.imwrite(f"{folder}_{name}_panorama.jpg", cv2.resize(pano, None, fx=0.25, fy=0.25))
        # período: autocorrelação do perfil de colunas do panorama
        g = cv2.cvtColor(pano, cv2.COLOR_BGR2GRAY).astype(np.float32)
        prof = g.mean(axis=0) - g.mean()
        best, best_c = None, -1
        for P in range(PITCH * 3, min(len(prof) - 50, PITCH * 9)):
            a, b = prof[:-P], prof[P:]
            c = float(np.corrcoef(a, b)[0, 1]) if len(a) > 100 else -1
            if c > best_c:
                best, best_c = P, c
        print(f"{name}: velocidade {v:.1f} px/s (desvio máx. da reta {np.abs(resid).max():.0f}px), "
              f"deslocamento {cum[-1]:.0f}px em {ts[-1] - ts[0]:.1f}s; "
              f"volta ~{best}px (corr {best_c:.2f}) => ~{best / PITCH:.2f} prateleiras")


if __name__ == "__main__":
    main(sys.argv[1])
