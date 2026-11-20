"""Ponte para Android através do adb (Android Debug Bridge). Funciona em Windows, macOS e Linux.

- screenshot(): `adb exec-out screencap` em formato cru (sem PNG), o que é bem mais rápido;
- tap / move / chain: `adb shell input tap`, com vários toques num só comando shell.

ATENÇÃO: esta ponte foi escrita seguindo a documentação do Android, mas NÃO foi testada num telemóvel
real (o bot só foi testado no iPhone). Os níveis normais devem funcionar; nos níveis com passadeiras os
atrasos (`lat`, `tap_overhead`) têm de ser calibrados no teu telemóvel (ver docs/instalar-android.md).

    python -m bot.android devices          # lista os telemóveis ligados
    python -m bot.android shot             # guarda um screenshot em shots/
    python -m bot.android tap 500 1200     # toca nesse ponto (píxeis do screenshot)
"""
from __future__ import annotations

import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np


class _Stamp:
    stamp = 0.0


class Android:
    # cada `input tap` arranca um processo Java no telemóvel: ~0,2-0,5 s conforme o modelo
    lat = 0.6
    tap_overhead = 0.3

    def __init__(self, serial: str | None = None, adb: str | None = None):
        adb = adb or shutil.which("adb") or shutil.which("adb.exe")
        if not adb:
            raise RuntimeError("Não encontrei o adb. Instala as 'Android SDK Platform-Tools' e põe a pasta no PATH "
                               "(ou indica o caminho com --adb). Ver docs/instalar-android.md.")
        self.base = [adb] + (["-s", serial] if serial else [])
        self.stream = _Stamp()
        devs = devices(adb)
        if not devs:
            raise RuntimeError("Nenhum telemóvel Android autorizado. Liga-o por USB, ativa a 'Depuração USB' e "
                               "aceita o pedido de autorização no ecrã do telemóvel.")
        if serial is None and len(devs) > 1:
            raise RuntimeError(f"Há vários telemóveis ligados ({', '.join(devs)}): escolhe um com --android SERIAL.")

    # ---------- comandos
    def _run(self, args: list[str], timeout: float = 15) -> bytes:
        r = subprocess.run(self.base + args, capture_output=True, timeout=timeout)
        if r.returncode != 0:
            raise RuntimeError(f"adb {' '.join(args)} falhou: {r.stderr.decode(errors='ignore').strip()}")
        return r.stdout

    def _shell(self, cmd: str) -> None:
        self._run(["shell", cmd])

    # ---------- interface do bot (ver bot/device.py)
    def screenshot(self, path: str | Path | None = None, newer_than: float = 0.0) -> np.ndarray:
        t0 = time.time()
        raw = self._run(["exec-out", "screencap"])
        t1 = time.time()
        img = _decode_screencap(raw)
        if img is None:  # formato inesperado: pedir PNG (mais lento, mas universal)
            png = self._run(["exec-out", "screencap", "-p"])
            img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        # a captura acontece logo no início do comando; o resto é transferência pelo cabo
        self.stream.stamp = t0 + min(0.15, (t1 - t0) / 2)
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(path), img)
        return img

    def tap(self, x: float, y: float) -> None:
        self._shell(f"input tap {int(x)} {int(y)}")

    def move(self, x1, y1, x2, y2, gap_ms: int = 120) -> None:
        self.chain([(x1, y1, gap_ms), (x2, y2, 0)])

    def chain(self, taps: list[tuple[float, float, int]]) -> None:
        parts = []
        for x, y, pause in taps:
            parts.append(f"input tap {int(x)} {int(y)}")
            if pause:
                parts.append(f"sleep {pause / 1000:.3f}")
        self._shell("; ".join(parts))

    def check_user(self) -> None:
        """Com o adb o rato do computador não é usado, por isso não há nada a verificar."""


def _decode_screencap(raw: bytes) -> np.ndarray | None:
    """Formato cru do screencap: cabeçalho (largura, altura, formato[, espaço de cor]) + RGBA."""
    if len(raw) < 16:
        return None
    w, h, fmt = struct.unpack_from("<III", raw, 0)
    n = w * h * 4
    hdr = len(raw) - n
    if fmt != 1 or hdr not in (12, 16) or w == 0 or h == 0:  # 1 = RGBA_8888
        return None
    rgba = np.frombuffer(raw, np.uint8, count=n, offset=hdr).reshape(h, w, 4)
    return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)


def devices(adb: str = "adb") -> list[str]:
    out = subprocess.run([adb, "devices"], capture_output=True, text=True).stdout
    return [ln.split()[0] for ln in out.splitlines()[1:] if ln.strip().endswith("device")]


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "shot"
    if cmd == "devices":
        print("\n".join(devices(shutil.which("adb") or "adb")) or "nenhum telemóvel autorizado")
    elif cmd == "shot":
        d = Android()
        p = Path("shots") / f"android-{time.strftime('%H%M%S')}.png"
        t0 = time.time()
        img = d.screenshot(p)
        print(f"{p}  {img.shape[1]}x{img.shape[0]}  ({time.time() - t0:.2f}s)")
    elif cmd == "tap":
        Android().tap(float(sys.argv[2]), float(sys.argv[3]))
    else:
        sys.exit(__doc__)
