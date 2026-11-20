"""Corre o bot ao vivo: lê o ecrã do telemóvel, planeia e (com --auto) joga.

Escolhe como falar com o telemóvel:
    python -m bot.run --wda --auto              # iPhone + Mac, pelo WebDriverAgent (testado)
    python -m bot.run --android --auto          # Android + Windows/Mac/Linux, pelo adb (experimental)
    python -m bot.run --mirror --auto           # iPhone pela Replicação do iPhone (macOS fora da UE)
    python -m bot.run --wda                     # modo assistente: mostra a jogada, tu tocas
    python -m bot.run --image screenshot.png    # analisa um screenshot e desenha o plano

Ciclo: esperar que o ecrã pare -> ler o tabuleiro -> planear -> tocar -> repetir.
Se alguma linha de prateleiras se mexer (nível com passadeiras), muda para bot/conveyor.py.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2
import numpy as np

from .board import find_shelves
from .device import UserTookOver
from .game import SLOTS, UNK, Move, Obs, remember_exhausted
from .powerups import buttons
from .solver import plan, to_moves
from .vision import Catalog, read_board

DEV = None  # dispositivo escolhido na linha de comandos (ver bot/device.py)
WIN = "Arrum'A Bot"


def to_obs(views) -> Obs:
    from .vision import SIL_VISIBLE

    def back(v):
        if v.front is not None:
            return None
        if v.back is not None:
            return v.back
        return UNK if v.sil_ratio >= SIL_VISIBLE else None  # há silhueta, mas não se reconheceu

    return Obs(
        front=[[v.front for v in row] for row in views],
        back=[[back(v) for v in row] for row in views],
    )


def describe(m: Move) -> str:
    r = lambda s: f"linha {s // 3 + 1}, coluna {s % 3 + 1}"
    return f"prateleira ({r(m.src)}) posição {m.src_slot + 1}  ->  prateleira ({r(m.dst)}) posição {m.dst_slot + 1}"


def draw_moves(img, shelves, moves: list[Move]) -> np.ndarray:
    out = img.copy()
    t = max(2, img.shape[1] // 200)
    for i, m in enumerate(moves):
        a = shelves[m.src].slot_center(m.src_slot)
        b = shelves[m.dst].slot_center(m.dst_slot)
        col = (0, 0, 255) if i == 0 else (0, 140, 255)
        cv2.arrowedLine(out, a, b, col, t * 2, tipLength=0.12)
        cv2.circle(out, a, t * 6, col, t)
        cv2.putText(out, str(i + 1), (a[0] - t * 4, a[1] - t * 8), cv2.FONT_HERSHEY_SIMPLEX, t * 0.5, col, t)
    return out


def board_signature(img, shelves) -> np.ndarray:
    x0 = min(s.x for s in shelves); y0 = min(s.y for s in shelves)
    x1 = max(s.x + s.w for s in shelves); y1 = max(s.y + s.h for s in shelves)
    crop = img[y0:y1, x0:x1]
    return cv2.cvtColor(cv2.resize(crop, (90, 120), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.int16)


def wait_stable(timeout=6.0, interval=0.1, need=3):
    """Tira screenshots até o tabuleiro ficar igual em `need` capturas seguidas (~0,3 s parado)."""
    t0 = time.time()
    prev, same = None, 0
    while time.time() - t0 < timeout:
        img = DEV.screenshot()
        shelves = find_shelves(img)
        if len(shelves) == 12:
            sig = board_signature(img, shelves)
            if prev is not None and prev.shape == sig.shape and np.abs(sig - prev).mean() < 0.6:
                same += 1
                if same >= need - 1:
                    return img, shelves
            else:
                same = 0
            prev = sig
        else:
            prev, same = None, 0
        time.sleep(interval)
    return None, None


def analyse_image(path: str):
    img = cv2.imread(path)
    cat = Catalog()
    shelves, views = read_board(img, cat)
    if len(shelves) != 12:
        print(f"Encontrei {len(shelves)} prateleiras (esperava 12).")
        return
    obs = to_obs(views)
    for s, row in enumerate(obs.front):
        print(f"P{s:2d}: frente={row}  trás={obs.back[s]}")
    moves = to_moves(obs, plan(obs))
    for m in moves:
        print("  ", describe(m))
    out = draw_moves(img, shelves, moves)
    dst = Path(path).with_name(Path(path).stem + "_plano.png")
    cv2.imwrite(str(dst), out)
    print("Imagem com o plano:", dst)


def live(auto: bool, max_moves: int, show: bool, log_dir: Path | None = None, use_hammer: bool = True):
    from tools.overlay import overlay

    cat = Catalog()
    done = 0
    t_start = time.time()
    shots = Path("shots"); shots.mkdir(exist_ok=True)
    log_dir = log_dir or Path("runs") / time.strftime("%Y%m%d-%H%M%S")
    log_dir.mkdir(parents=True, exist_ok=True)
    lost_since = None
    no_effect = 0
    prev_front = None
    reads = 0
    exhausted: set[int] = set()  # prateleiras que já se viram vazias (não têm mais camadas)
    waits = 0
    hammer_used = not use_hammer
    btn = None  # posições dos power-ups, detetadas no primeiro frame
    while done < max_moves:
        img, shelves = wait_stable()
        if img is None:
            lost_since = lost_since or time.time()
            if time.time() - lost_since > 8:
                print("Não vejo o tabuleiro há 8 s (nível acabou, pop-up ou ecrã diferente). A parar.")
                cv2.imwrite(str(log_dir / "fim.png"), DEV.screenshot())
                break
            continue
        lost_since = None
        btn = btn or buttons(img)
        _, views = read_board(img, cat, shelves)
        obs = to_obs(views)
        if prev_front is not None and obs.front == prev_front:
            no_effect += 1
            print(f"  (o tabuleiro não mudou; {no_effect}x seguidas)", flush=True)
            if no_effect >= 4:
                print("As jogadas não estão a ter efeito. A parar.")
                break
        else:
            no_effect = 0
        prev_front = obs.front
        remember_exhausted(exhausted, obs)
        trio = [i for i, r in enumerate(obs.front) if r[0] is not None and r[0] != UNK and r.count(r[0]) == SLOTS]
        if trio and waits < 2:
            waits += 1  # um trio ainda a desaparecer: esperar e voltar a ler
            time.sleep(0.3)
            prev_front = None
            continue
        for i in trio:  # "trio" que não desaparece = leitura errada: não usar esses produtos
            obs.front[i] = [UNK] * SLOTS
        waits = 0
        moves = to_moves(obs, plan(obs))
        reads += 1
        cv2.imwrite(str(log_dir / f"{reads:03d}.png"), draw_moves(overlay(img, shelves, views), shelves, moves))
        cv2.imwrite(str(log_dir / f"raw_{reads:03d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        with open(log_dir / "log.txt", "a") as fh:
            fh.write(f"{reads} t={time.time() - t_start:.1f} front={obs.front} back={obs.back} moves={[str(m) for m in moves]}\n")
        if not moves:
            if all(v is None for r in obs.front for v in r):
                print("Tabuleiro vazio: nível concluído!")
            else:
                print("Sem jogadas possíveis: tabuleiro cheio. (Aqui um power-up ajudava.)")
            break
        # martelo: faz um trio sem gastar jogadas. Usa-se quando o próximo trio sairia caro (3+ jogadas)
        if auto and not hammer_used and len(moves) >= 3 and done >= 6:
            print(f"[martelo] o próximo trio custava {len(moves)} jogadas: a usar o martelo", flush=True)
            DEV.tap(*btn["martelo"])
            hammer_used = True
            time.sleep(0.6)
            continue
        if show:
            cv2.imshow(WIN, cv2.resize(draw_moves(img, shelves, moves), None, fx=0.6, fy=0.6))
            cv2.waitKey(1)
        if not auto:
            print("Próxima jogada:", describe(moves[0]))
            # espera que o jogador faça a jogada (o tabuleiro muda) antes de voltar a planear
            sig = board_signature(img, shelves)
            while True:
                time.sleep(0.3)
                im2 = DEV.screenshot()
                sh2 = find_shelves(im2)
                if len(sh2) != 12 or np.abs(board_signature(im2, sh2) - sig).mean() > 2:
                    break
                if show:
                    cv2.waitKey(1)
            continue
        sig = board_signature(img, shelves)
        try:
            for m in moves:
                a = shelves[m.src].slot_center(m.src_slot)
                b = shelves[m.dst].slot_center(m.dst_slot)
                el = time.time() - t_start
                print(f"[{done + 1:3d} | {el:5.1f}s] {describe(m)}", flush=True)
                if hasattr(DEV, "move"):
                    DEV.move(*a, *b)
                else:
                    DEV.drag(*a, *b)
                done += 1
                time.sleep(0.12)
                DEV.check_user()
        except (UserTookOver, KeyboardInterrupt):
            print("Mexeste no rato: o bot parou. Volta a corrê-lo para continuar.")
            break
    print(f"Fim: {done} jogadas em {time.time() - t_start:.0f} s. Leituras guardadas em {log_dir}")


def connect(a) -> object:
    """Cria a ponte para o telemóvel escolhida na linha de comandos."""
    if a.wda is not None:
        from .wda import WDA

        dev = WDA(a.wda or None)
        dev.start_stream()
        return dev
    if a.android is not None:
        from .android import Android

        return Android(a.android or None, adb=a.adb)
    from . import iphone  # Replicação do iPhone (só macOS)

    return iphone


def main() -> None:
    global DEV
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--auto", action="store_true", help="joga sozinho (sem isto, só mostra a jogada)")
    ap.add_argument("--image", help="analisa um screenshot em vez do telemóvel")
    ap.add_argument("--wda", nargs="?", const="", metavar="URL", help="iPhone pelo WebDriverAgent (URL opcional)")
    ap.add_argument("--android", nargs="?", const="", metavar="SERIAL", help="Android pelo adb (serial opcional)")
    ap.add_argument("--adb", help="caminho para o adb, se não estiver no PATH")
    ap.add_argument("--mirror", action="store_true", help="iPhone pela Replicação do iPhone (macOS)")
    ap.add_argument("--max-moves", type=int, default=245, help="jogadas do nível (aparece no topo do jogo)")
    ap.add_argument("--time-limit", type=float, default=0, help="tempo do nível em segundos (passadeiras)")
    ap.add_argument("--no-window", action="store_true", help="não abrir a janela com as setas")
    ap.add_argument("--lat", type=float, help="passadeiras: s entre o frame e o 1.º toque (WDA 0.32, Android 0.6)")
    ap.add_argument("--tap-overhead", type=float, help="passadeiras: s a mais por toque numa cadeia (WDA 0, Android 0.3)")
    a = ap.parse_args()
    if a.image:
        analyse_image(a.image)
        return
    if a.wda is None and a.android is None and not a.mirror:
        ap.error("escolhe o telemóvel: --wda (iPhone + Mac), --android (Android) ou --mirror (Replicação do iPhone)")
    DEV = connect(a)
    if a.lat is not None:
        DEV.lat = a.lat
    if a.tap_overhead is not None:
        DEV.tap_overhead = a.tap_overhead
    if hasattr(DEV, "stream"):
        # nível com passadeiras? mede o movimento de cada linha e muda de modo se preciso
        from .conveyor import bands_from, detect_full, live_conveyor, measure_speeds

        bands = bands_from(detect_full(DEV.screenshot()))
        if bands and any(v != 0.0 for v in measure_speeds(DEV, bands, window=0.5)):
            print("Nível com passadeiras: modo passadeiras.", flush=True)
            live_conveyor(DEV, auto=a.auto, max_moves=a.max_moves, time_limit=a.time_limit or 459.0)
            return
    live(a.auto, a.max_moves, not a.no_window)


if __name__ == "__main__":
    main()
