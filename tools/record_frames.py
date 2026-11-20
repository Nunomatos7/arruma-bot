"""Grava frames com o instante no nome (f0001_12.345.jpg), para tools/belts.py e tools/replay_conveyor.py.

    python -m tools.record_frames --wda 25 rec/nivel27            # 25 s do iPhone (WebDriverAgent a correr)
    python -m tools.record_frames --android 25 rec/nivel27        # 25 s de um Android (adb)
    python -m tools.record_frames --video gravacao.mp4 rec/nivel27  # todos os frames de uma gravação de ecrã
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2


def from_device(dev, seconds: float, out: Path) -> int:
    t0, n = time.time(), 0
    last = 0.0
    while time.time() - t0 < seconds:
        img = dev.screenshot(newer_than=last)
        last = dev.stream.stamp
        cv2.imwrite(str(out / f"f{n:04d}_{last - t0:06.3f}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        n += 1
    return n


def from_video(path: str, out: Path) -> int:
    cap = cv2.VideoCapture(path)
    n = 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        cv2.imwrite(str(out / f"f{n:04d}_{t:06.3f}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--wda", type=float, metavar="SEGUNDOS")
    src.add_argument("--android", type=float, metavar="SEGUNDOS")
    src.add_argument("--video")
    ap.add_argument("out")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.video:
        n = from_video(a.video, out)
    elif a.wda:
        from bot.wda import WDA

        dev = WDA()
        dev.start_stream()
        n = from_device(dev, a.wda, out)
    else:
        from bot.android import Android

        n = from_device(Android(), a.android, out)
    print(f"{n} frames em {out}")


if __name__ == "__main__":
    main()
