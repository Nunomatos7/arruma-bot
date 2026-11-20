"""Ponte para o iPhone através do WebDriverAgent (XCUITest), por cabo ou Wi-Fi.

O WebDriverAgent corre no iPhone como um teste de UI e expõe uma API HTTP (porta 8100):
screenshots e gestos de toque sintetizados pelo próprio iOS. Não usa o rato do Mac.

    python -m bot.wda start [TEAM_ID]   # compila (se preciso) e arranca o WDA no iPhone
    python -m bot.wda stop              # desliga o WDA (o iPhone fica livre)
    python -m bot.wda shot              # guarda um screenshot em shots/
    python -m bot.wda tap x y           # toca nesse ponto (píxeis do screenshot)

Antes da 1.ª vez: python -m tools.setup_wda (ver docs/instalar-mac-iphone.md).
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "vendor" / "WebDriverAgent" / "WebDriverAgent.xcodeproj"
DERIVED = ROOT / "vendor" / "wda-build"
URL_FILE = ROOT / "vendor" / "wda-url.txt"
LOG = ROOT / "vendor" / "wda-run.log"
TAP_MS = 40  # duração de cada toque


from .device import UserTookOver  # noqa: E402,F401  (interface comum)


class MjpegReader:
    """Lê o stream MJPEG do WebDriverAgent (porta 9100) numa thread e guarda o último frame.
    É muito mais rápido do que pedir um screenshot PNG de cada vez (~1 s)."""

    def __init__(self, url: str):
        import threading

        self.url = url
        self.frame: np.ndarray | None = None
        self.stamp = 0.0
        self.seq = 0
        self._stop = False
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def _run(self):
        while not self._stop:
            try:
                with urllib.request.urlopen(self.url, timeout=10) as r:
                    buf = b""
                    while not self._stop:
                        chunk = r.read(65536)
                        if not chunk:
                            break
                        buf += chunk
                        a = buf.find(b"\xff\xd8")
                        b = buf.find(b"\xff\xd9", a + 2)
                        while a != -1 and b != -1:
                            jpg = buf[a : b + 2]
                            buf = buf[b + 2 :]
                            img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                            if img is not None:
                                self.frame, self.stamp = img, time.time()
                                self.seq += 1
                            a = buf.find(b"\xff\xd8")
                            b = buf.find(b"\xff\xd9", a + 2)
            except Exception:
                time.sleep(0.5)

    def latest(self, newer_than: float = 0.0, timeout: float = 3.0) -> np.ndarray:
        t0 = time.time()
        while self.frame is None or self.stamp <= newer_than:
            if time.time() - t0 > timeout:
                raise TimeoutError("sem frames do stream MJPEG")
            time.sleep(0.01)
        return self.frame


class WDA:
    lat = 0.32  # s entre o frame chegar ao computador e o 1.º toque (stream + WebDriverAgent)
    tap_overhead = 0.0  # os toques de uma cadeia saem com as pausas pedidas
    def __init__(self, url: str | None = None):
        self.url = (url or (URL_FILE.read_text().strip() if URL_FILE.exists() else "http://127.0.0.1:8100")).rstrip("/")
        self.sid: str | None = None
        self.scale: float | None = None  # píxeis do screenshot por ponto do iOS
        self.stream: MjpegReader | None = None
        self.points_w: float | None = None

    # ---------- HTTP
    def _req(self, method: str, path: str, body=None, timeout=20):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")

    def status(self):
        return self._req("GET", "/status", timeout=5)

    def session(self) -> str:
        if self.sid is None:
            r = self._req("POST", "/session", {"capabilities": {"alwaysMatch": {}}})
            self.sid = r.get("sessionId") or r["value"]["sessionId"]
            # o jogo está sempre animado: não esperar que a app fique "parada"
            self._req("POST", f"/session/{self.sid}/appium/settings", {"settings": {
                "waitForIdleTimeout": 0, "animationCoolOffTimeout": 0, "snapshotMaxDepth": 1,
            }})
        return self.sid

    def start_stream(self, scale_pct: int = 100, quality: int = 92, fps: int = 15) -> None:
        """Liga o stream MJPEG: a partir daqui screenshot() devolve o frame mais recente."""
        self._req("POST", f"/session/{self.session()}/appium/settings", {"settings": {
            "mjpegScalingFactor": scale_pct, "mjpegServerScreenshotQuality": quality, "mjpegServerFramerate": fps,
        }})
        host = self.url.rsplit(":", 1)[0]
        self.stream = MjpegReader(f"{host}:9100")
        self.points_w = self._req("GET", f"/session/{self.session()}/window/size")["value"]["width"]
        self.stream.latest()

    # ---------- interface usada pelo bot (igual à de iphone.py)
    def screenshot(self, path: str | Path | None = None, newer_than: float = 0.0) -> np.ndarray:
        if self.stream is not None:
            img = self.stream.latest(newer_than)
            self.scale = img.shape[1] / self.points_w
            if path:
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(path), img)
            return img
        r = self._req("GET", "/screenshot")
        png = base64.b64decode(r["value"])
        img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        if self.scale is None:
            w = self._req("GET", f"/session/{self.session()}/window/size")["value"]["width"]
            self.scale = img.shape[1] / w
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(path), img)
        return img

    def drag(self, x1, y1, x2, y2, hold_ms: int = 60, move_ms: int = 180) -> None:
        if self.scale is None:
            self.screenshot()
        s = self.scale
        p = lambda v: int(round(v / s))
        actions = [
            {"type": "pointerMove", "duration": 0, "x": p(x1), "y": p(y1)},
            {"type": "pointerDown", "button": 0},
            {"type": "pause", "duration": hold_ms},
            {"type": "pointerMove", "duration": move_ms, "x": p(x2), "y": p(y2)},
            {"type": "pause", "duration": 30},
            {"type": "pointerUp", "button": 0},
        ]
        self._req("POST", f"/session/{self.session()}/actions", {"actions": [
            {"type": "pointer", "id": "finger1", "parameters": {"pointerType": "touch"}, "actions": actions}
        ]})

    def tap(self, x, y) -> None:
        self.drag(x, y, x, y, hold_ms=40, move_ms=0)

    def move(self, x1, y1, x2, y2, gap_ms: int = 120) -> None:
        """Tocar no produto (fica selecionado) e depois tocar no destino. Uma só chamada HTTP."""
        if self.scale is None:
            self.screenshot()
        p = lambda v: int(round(v / self.scale))
        acts = [
            {"type": "pointerMove", "duration": 0, "x": p(x1), "y": p(y1)},
            {"type": "pointerDown", "button": 0}, {"type": "pause", "duration": 40}, {"type": "pointerUp", "button": 0},
            {"type": "pause", "duration": gap_ms},
            {"type": "pointerMove", "duration": 0, "x": p(x2), "y": p(y2)},
            {"type": "pointerDown", "button": 0}, {"type": "pause", "duration": 40}, {"type": "pointerUp", "button": 0},
        ]
        self._req("POST", f"/session/{self.session()}/actions", {"actions": [
            {"type": "pointer", "id": "finger1", "parameters": {"pointerType": "touch"}, "actions": acts}
        ]})

    def chain(self, taps: list[tuple[float, float, int]]) -> None:
        """Vários toques numa só chamada HTTP: [(x, y, pausa_depois_ms), ...]. Cada pedido ao WDA
        custa ~0,4 s fixos, por isso juntar as jogadas de uma sequência poupa esse tempo."""
        if self.scale is None:
            self.screenshot()
        p = lambda v: int(round(v / self.scale))
        acts = []
        for x, y, pause in taps:
            acts += [{"type": "pointerMove", "duration": 0, "x": p(x), "y": p(y)},
                     {"type": "pointerDown", "button": 0}, {"type": "pause", "duration": TAP_MS},
                     {"type": "pointerUp", "button": 0}]
            if pause:
                acts.append({"type": "pause", "duration": pause})
        self._req("POST", f"/session/{self.session()}/actions", {"actions": [
            {"type": "pointer", "id": "finger1", "parameters": {"pointerType": "touch"}, "actions": acts}
        ]})

    def check_user(self) -> None:
        """Com o WDA o rato do Mac não é usado, por isso não há nada a verificar."""


def device_id() -> str:
    out = subprocess.run(["xcrun", "devicectl", "list", "devices"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if "physical" in line and ("available" in line or "connected" in line):
            m = re.search(r"([0-9A-F]{8}-[0-9A-F]{16})", line)
            if m:
                return m.group(1)
    raise RuntimeError("Não encontrei nenhum iPhone ligado. Liga-o por cabo e desbloqueia-o.")


def start(team: str = "", timeout: float = 240) -> str:
    """Arranca o WebDriverAgent no iPhone e devolve o URL da API.

    A 1.ª compilação tem de ser assinada pelo Xcode (cria o perfil de programador); depois
    disso `build-for-testing` + `test-without-building` correm sem precisar da conta.
    """
    udid = device_id()
    runs = sorted(DERIVED.glob("Build/Products/*.xctestrun"))
    if not runs:
        if not PROJECT.exists():
            raise RuntimeError("Falta o WebDriverAgent em vendor/. Corre primeiro: python -m tools.setup_wda --team ... --bundle-prefix ...")
        cmd = ["xcodebuild", "-project", str(PROJECT), "-scheme", "WebDriverAgentRunner",
               "-destination", f"id={udid}", "-derivedDataPath", str(DERIVED), "CODE_SIGN_STYLE=Automatic",
               "-allowProvisioningUpdates"]  # deixa o Xcode criar o perfil com a conta que tem configurada
        if team:
            cmd.append(f"DEVELOPMENT_TEAM={team}")
        print("A compilar o WebDriverAgent (1-3 minutos na primeira vez)...", flush=True)
        r = subprocess.run(cmd + ["build-for-testing"], capture_output=True, text=True)
        if r.returncode != 0:
            errs = [l.strip() for l in (r.stdout + r.stderr).splitlines() if "error" in l.lower()][:10]
            raise RuntimeError("A compilação falhou (ver docs/problemas.md, secção WebDriverAgent):\n" + "\n".join(errs))
        runs = sorted(DERIVED.glob("Build/Products/*.xctestrun"))
    log = open(LOG, "w")
    proc = subprocess.Popen(
        ["xcodebuild", "test-without-building", "-xctestrun", str(runs[-1]), "-destination", f"id={udid}"],
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
    )
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(2)
        text = LOG.read_text(errors="ignore")
        m = re.search(r"ServerURLHere->(http://[^<]+)<-ServerURLHere", text)
        if m:
            url = m.group(1).rstrip("/")
            URL_FILE.write_text(url)
            print(f"WebDriverAgent a correr em {url} (pid {proc.pid}). Log: {LOG}")
            return url
        if proc.poll() is not None:
            errs = [l for l in text.splitlines() if "error" in l.lower()][:8]
            raise RuntimeError("O xcodebuild terminou sem arrancar o WDA:\n" + "\n".join(errs))
    raise RuntimeError(f"O WDA não arrancou em {timeout:.0f} s. Vê {LOG}")


def stop() -> None:
    """Desliga o WebDriverAgent (termina o xcodebuild que o mantém a correr no iPhone)."""
    r = subprocess.run(["pkill", "-f", "xcodebuild test-without-building"], capture_output=True)
    print("WebDriverAgent desligado." if r.returncode == 0 else "O WebDriverAgent não estava a correr.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "shot"
    if cmd == "start":
        start(os.environ.get("WDA_TEAM", sys.argv[2] if len(sys.argv) > 2 else ""))
    elif cmd == "shot":
        d = WDA()
        t = time.time()
        p = Path("shots") / f"wda-{time.strftime('%H%M%S')}.png"
        img = d.screenshot(p)
        print(f"{p}  {img.shape[1]}x{img.shape[0]}  escala {d.scale:.2f}  ({time.time() - t:.2f}s)")
    elif cmd == "stop":
        stop()
    elif cmd == "tap":
        d = WDA()
        d.screenshot()
        d.tap(float(sys.argv[2]), float(sys.argv[3]))
    else:
        sys.exit(__doc__)
