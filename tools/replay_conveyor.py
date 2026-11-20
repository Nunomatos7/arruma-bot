"""Corre o modo passadeiras contra uma gravação (frames com o instante no nome), sem telemóvel.
O tabuleiro não reage aos toques: serve para testar a visão, o seguimento das passadeiras,
a memória e a decisão de esperar.

    .venv/bin/python -m tools.replay_conveyor rec/l26_belts 20
"""
from __future__ import annotations

import glob
import re
import sys
import time
from pathlib import Path

import cv2


class _Stream:
    stamp = 0.0


class FakeDev:
    def __init__(self, folder: str, skip: float = 1.0):
        fs = sorted(glob.glob(f"{folder}/*.jpg"))
        self.ts = [float(re.search(r"_(-?\d+\.\d+)\.jpg", f).group(1)) for f in fs]
        self.fs = fs
        self.t0 = time.time() - skip
        self.stream = _Stream()
        self.taps = []

    def screenshot(self, path=None, newer_than: float = 0.0):
        while True:
            el = time.time() - self.t0
            i = max(j for j, t in enumerate(self.ts) if t <= el) if el >= self.ts[0] else 0
            stamp = self.t0 + self.ts[i]
            if stamp > newer_than or i == len(self.ts) - 1:
                break
            time.sleep(0.01)
        if i == len(self.ts) - 1 and el > self.ts[-1] + 1:
            raise SystemExit("fim da gravação")
        self.stream.stamp = stamp
        return cv2.imread(self.fs[i])

    def tap(self, x, y):
        self.taps.append(("tap", x, y))

    def chain(self, taps):
        time.sleep(0.25 + 0.45 * len(taps) / 2)
        self.taps.append(("chain", taps))


if __name__ == "__main__":
    from bot.conveyor import live_conveyor

    dev = FakeDev(sys.argv[1])
    try:
        live_conveyor(dev, log_dir=Path("runs/replay"), max_moves=int(sys.argv[2]) if len(sys.argv) > 2 else 290)
    except SystemExit as e:
        print(e)
    print("cadeias:", sum(1 for t in dev.taps if t[0] == "chain"))
