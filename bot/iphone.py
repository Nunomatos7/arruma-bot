"""Ponte para o iPhone através da janela do Espelhamento do iPhone (macOS).

- screenshot(): captura só a janela do Espelhamento e devolve a imagem (BGR, numpy).
- tap(x, y):   toca no iPhone, em coordenadas da imagem devolvida por screenshot().

Uso rápido:
    .venv/bin/python -m bot.iphone shot            # guarda shots/<timestamp>.png
    .venv/bin/python -m bot.iphone tap 300 900     # toca nesse ponto da imagem
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
try:
    import Quartz
except ImportError as e:  # só existe no macOS
    raise ImportError("A Replicação do iPhone só funciona no macOS (precisa do pacote pyobjc-framework-Quartz).") from e

OWNER = "iPhone Mirroring"


@dataclass
class Window:
    wid: int
    x: float  # origem e tamanho em pontos do ecrã do Mac
    y: float
    w: float
    h: float


def find_window() -> Window:
    infos = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )
    best = None
    for info in infos or []:
        if info.get("kCGWindowOwnerName") != OWNER or info.get("kCGWindowLayer", 0) != 0:
            continue
        b = info["kCGWindowBounds"]
        win = Window(int(info["kCGWindowNumber"]), b["X"], b["Y"], b["Width"], b["Height"])
        if best is None or win.w * win.h > best.w * best.h:
            best = win
    if best is None:
        raise RuntimeError(
            "Janela do Espelhamento do iPhone não encontrada. Abre a app 'Espelhamento do iPhone' "
            "e deixa-a visível (não minimizada)."
        )
    return best


_last: tuple[Window, float] | None = None  # janela + escala (px da imagem por ponto) da última captura


def screenshot(path: str | Path | None = None) -> np.ndarray:
    global _last
    win = find_window()
    out = Path(path) if path else Path(tempfile.mkstemp(suffix=".png")[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    # -x sem som, -o sem sombra, -l captura só esta janela
    subprocess.run(["screencapture", "-x", "-o", f"-l{win.wid}", str(out)], check=True)
    img = cv2.imread(str(out))
    if img is None:
        raise RuntimeError(
            "A captura veio vazia. Dá permissão de 'Gravação de ecrã' à app que corre este script "
            "(Definições do Sistema > Privacidade e Segurança)."
        )
    _last = (win, img.shape[1] / win.w)
    if path is None:
        out.unlink(missing_ok=True)
    return img


_bot_cursor: tuple[float, float] | None = None  # onde o bot deixou o rato da última vez


from .device import UserTookOver  # noqa: E402


def _cursor() -> tuple[float, float]:
    p = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    return p.x, p.y


def check_user() -> None:
    """Trava de segurança: se o rato não está onde o bot o deixou, foi o utilizador que o mexeu."""
    if _bot_cursor is None:
        return
    x, y = _cursor()
    if abs(x - _bot_cursor[0]) + abs(y - _bot_cursor[1]) > 25:
        raise UserTookOver()


def _post_click(px: float, py: float) -> None:
    pt = Quartz.CGPointMake(px, py)
    for kind in (Quartz.kCGEventMouseMoved, Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
        ev = Quartz.CGEventCreateMouseEvent(None, kind, pt, Quartz.kCGMouseButtonLeft)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
        time.sleep(0.03)


def tap(x: float, y: float) -> None:
    """Toca no ponto (x, y) em píxeis da última imagem de screenshot()."""
    if _last is None:
        screenshot()
    win, scale = _last
    _post_click(win.x + x / scale, win.y + y / scale)


def drag(x1: float, y1: float, x2: float, y2: float, steps: int = 12) -> None:
    """Arrasta de (x1,y1) para (x2,y2), em píxeis da última imagem."""
    check_user()
    if _last is None:
        screenshot()
    win, scale = _last
    a = (win.x + x1 / scale, win.y + y1 / scale)
    b = (win.x + x2 / scale, win.y + y2 / scale)
    def ev(kind, p):
        e = Quartz.CGEventCreateMouseEvent(None, kind, Quartz.CGPointMake(*p), Quartz.kCGMouseButtonLeft)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, e)
    ev(Quartz.kCGEventMouseMoved, a)
    ev(Quartz.kCGEventLeftMouseDown, a)
    for i in range(1, steps + 1):
        t = i / steps
        ev(Quartz.kCGEventLeftMouseDragged, (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        time.sleep(0.015)
    ev(Quartz.kCGEventLeftMouseUp, b)
    global _bot_cursor
    _bot_cursor = b


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "shot"
    if cmd == "shot":
        p = Path("shots") / f"{time.strftime('%Y%m%d-%H%M%S')}.png"
        img = screenshot(p)
        w = find_window()
        print(f"{p}  {img.shape[1]}x{img.shape[0]} px  (janela {w.w:.0f}x{w.h:.0f} pt em {w.x:.0f},{w.y:.0f})")
    elif cmd == "tap":
        screenshot()
        tap(float(sys.argv[2]), float(sys.argv[3]))
    else:
        sys.exit(__doc__)
