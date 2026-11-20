"""Níveis com passadeiras: algumas linhas de prateleiras andam na horizontal e dão a volta.

Observado no nível 26: as linhas 1 e 4 estão paradas; a linha 2 anda para a direita e a 3 para a
esquerda, a ~120 px/s (num ecrã de 1178 px), com mais prateleiras do que as que cabem no ecrã.

Diferenças em relação ao modo normal (bot/run.py):
- o tabuleiro nunca pára, por isso a leitura só espera que as linhas *paradas* estejam estáveis;
- só entram no plano prateleiras inteiras no ecrã e que lá vão continuar durante a jogada;
- os toques são feitos onde a prateleira *vai estar*: posição lida + velocidade × atraso;
- cada passadeira tem um número fixo de prateleiras que dão a volta (6 no nível 26). O bot segue
  cada uma (posição no referencial da passadeira) e lembra-se do que lá está quando sai do ecrã.
  Assim sabe o que vem aí e só espera quando há uma combinação mais barata a chegar.
"""
from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

from .board import Shelf
from .game import SLOTS, UNK, Obs
from .solver import plan, to_moves, triple_cost, triple_path
from .vision import Catalog, read_board
from .wda import TAP_MS

LAT = 0.32  # s entre o frame (chegada) e o toque: atraso do stream + do WebDriverAgent
TAP_GAP = 0.16  # s entre o toque na origem e o toque no destino (ver WDA.move)
HORIZON = 1.6  # s durante os quais uma prateleira das passadeiras tem de continuar no ecrã
# Esperar não gasta jogadas: as passadeiras trazem uma prateleira nova a cada ~3 s. Se o
# próximo trio sair caro, vale a pena esperar um pouco por uma combinação melhor.
SAFETY = 15.0  # s de margem no fim do relógio
N_BELT = 6  # prateleiras por passadeira (nível 26: volta de 2070 px = 6 × 345 px)
PITCH = 345 / 1178  # distância entre prateleiras da passadeira, em fração da largura do ecrã
STEP = 0.5  # s entre os instantes futuros que se avaliam
MAX_TAU = 12.0  # s: espera máxima considerada
C_WAIT = 1.0  # quanto da folga de tempo se pode gastar a esperar (1 = folga por trio)
GAP_MS = 120  # ms entre tocar no produto e tocar no destino
MOVE_PAUSE_MS = 300  # ms entre jogadas seguidas da mesma cadeia


def wait_limit(L: int, spare: float) -> float:
    """Quanto tempo vale a pena esperar por uma combinação melhor.

    `spare` = tempo restante - jogadas restantes x tempo por jogada: é o tempo que sobra se
    jogarmos todas as jogadas que faltam sem parar. Enquanto sobrar, esperar é "de graça"."""
    if spare <= 0:
        return 0.0
    if L >= 3:
        return min(3.0, spare)
    if L == 2 and spare > 40:
        return min(1.8, spare - 40)
    return 0.0


def detect_full(img: np.ndarray) -> list[Shelf]:
    """Prateleiras inteiras no ecrã (as cortadas na borda ficam de fora), por linhas e colunas."""
    H, W = img.shape[:2]
    m = (img.min(axis=2) > 235).astype(np.uint8)
    _, _, st, _ = cv2.connectedComponentsWithStats(m, 8)
    boxes = []
    for x, y, w, h, a in st[1:]:
        if w < W * 0.2 or a < (W * 0.2) ** 2 * 0.45 or not (0.8 < w / h < 1.25):
            continue
        if x <= 3 or x + w >= W - 3:  # cortada pela borda do ecrã
            continue
        boxes.append((int(x), int(y), int(w), int(h)))
    # agrupar por linha (o y varia uns píxeis entre prateleiras da mesma linha) e ordenar por x
    boxes.sort(key=lambda b: b[1])
    rows: list[list] = []
    for b in boxes:
        if rows and abs(b[1] - rows[-1][0][1]) < b[3] * 0.3:
            rows[-1].append(b)
        else:
            rows.append([b])
    ordered = [b for row in rows for b in sorted(row, key=lambda b: b[0])]
    return [Shelf(i, *b) for i, b in enumerate(ordered)]


def bands_from(shelves: list[Shelf]) -> list[tuple[int, int]]:
    """Faixas verticais (y0, y1) de cada linha de prateleiras."""
    out: list[tuple[int, int]] = []
    for s in sorted(shelves, key=lambda s: s.y):
        if out and abs(s.y - out[-1][0]) < s.h * 0.3:
            continue
        out.append((s.y, s.y + s.h))
    return out


def measure_speeds(dev, bands, window: float = 0.6) -> list[float]:
    """Velocidade horizontal (px/s) de cada linha, por correlação de fase entre dois frames."""
    a = dev.screenshot(newer_than=time.time())
    ta = dev.stream.stamp
    time.sleep(window)
    b = dev.screenshot(newer_than=time.time())
    tb = dev.stream.stamp
    out = []
    for y0, y1 in bands:
        ga = cv2.cvtColor(a[y0:y1], cv2.COLOR_BGR2GRAY).astype(np.float32)
        gb = cv2.cvtColor(b[y0:y1], cv2.COLOR_BGR2GRAY).astype(np.float32)
        (dx, _), _ = cv2.phaseCorrelate(ga, gb)
        v = dx / (tb - ta)
        out.append(0.0 if abs(v) < 15 else v)
    return out


def row_of(shelf: Shelf, bands) -> int:
    return min(range(len(bands)), key=lambda i: abs(bands[i][0] - shelf.y))


def read_frame(dev, bands, speeds, timeout=4.0):
    """Espera que as linhas paradas estejam estáveis e devolve (img, t_frame)."""
    static = [b for b, v in zip(bands, speeds) if v == 0.0]
    t0 = time.time()
    prev = None
    while time.time() - t0 < timeout:
        img = dev.screenshot(newer_than=time.time())
        t = dev.stream.stamp
        sig = np.concatenate([
            cv2.resize(cv2.cvtColor(img[y0:y1], cv2.COLOR_BGR2GRAY), (60, 15)).ravel().astype(np.int16)
            for y0, y1 in static
        ]) if static else np.zeros(1, np.int16)
        if prev is not None and np.abs(sig - prev).mean() < 0.8:
            return img, t
        prev = sig
        time.sleep(0.08)
    return None, None


class Belt:
    """Segue as prateleiras de uma passadeira.

    No referencial da passadeira (u = x - v·t) cada prateleira está parada, e prateleiras
    vizinhas distam `pitch`. A identidade de uma prateleira é a sua posição nesse referencial,
    módulo o número de prateleiras. Como a velocidade medida tem um pequeno erro (~1 px/s), a
    referência é corrigida a cada leitura com as posições observadas."""

    def __init__(self, v: float, pitch: float, n: int = N_BELT):
        self.v, self.pitch, self.n = v, pitch, n
        self.t0: float | None = None
        self.ref: float | None = None  # u da prateleira 0 (u = x - v·(t - t0))
        self.hist: list[tuple[float, float]] = []  # (t, ref) para corrigir a velocidade
        self.mem: dict[int, tuple[list, list]] = {}  # k -> (frente, trás) da última vez que se viu
        self.exhausted: set[int] = set()
        self.dirty: set[int] = set()  # mudadas por nós desde a última vez que se viram
        self.same = self.diff = 0  # ao rever uma prateleira não mexida: igual ao que se lembrava?
        self.empty_seen: dict[int, int] = {}  # leituras seguidas em que se viu vazia

    def recalibrate(self, xs: list[float], t: float) -> None:
        """Corrige a referência com as posições observadas e, com o desvio acumulado ao longo
        de alguns segundos, a própria velocidade (a medição inicial tem ~10% de erro)."""
        if not xs:
            return
        if self.t0 is None:
            self.t0, self.ref = t, xs[0]
        tt = t - self.t0
        res = []
        for x in xs:
            d = (x - self.v * tt - self.ref) / self.pitch
            res.append((d - round(d)) * self.pitch)
        self.ref += float(np.mean(res))
        old = [h for h in self.hist if 3.0 <= tt - h[0] <= 20.0]
        if old:
            t_a, r_a = old[0]  # o mais antigo até 20 s: base longa = menos ruído
            dv = (self.ref - r_a) / (tt - t_a)
            self.v += dv
            self.ref -= dv * tt
            self.hist = [(th, rh - dv * th) for th, rh in self.hist]
        self.hist.append((tt, self.ref))
        self.hist = self.hist[-30:]

    def ident(self, x: float, t: float) -> int:
        return int(round((x - self.v * (t - self.t0) - self.ref) / self.pitch)) % self.n

    def x_at(self, k: int, t: float, W: int, w: float) -> float:
        """x (esquerda) da prateleira k no instante t, na volta mais próxima do ecrã."""
        L = self.n * self.pitch
        c = (W - w) / 2
        x = self.ref + k * self.pitch + self.v * (t - self.t0)
        return (x - c + L / 2) % L - L / 2 + c

    def trusted(self) -> bool:
        """A memória bate certo com o que se revê? (protege contra um N_BELT errado)"""
        return self.diff <= max(2, self.same // 2)


def _usable(x: float, w: float, v: float, W: int, horizon: float = HORIZON) -> bool:
    x2 = x + v * horizon
    return 6 <= x and x + w <= W - 6 and 6 <= x2 and x2 + w <= W - 6


MOVE_T = 0.5  # s por jogada dentro de uma cadeia de toques
READ_T = 0.9  # s de uma leitura nova (frame + visão + plano + pausa para as animações)
# Plano global (juntar produtos de várias prateleiras da passadeira ao longo do tempo): no simulador
# não foi melhor (520 vs 536 trios em 5 níveis) porque quase só gerava esperas longas. Fica desligado.
USE_GLOBAL = False
EFFECT_AREA = 0.006  # fração do ecrã: mancha verde maior do que isto = animação de trio a passar


def has_effect(img: np.ndarray) -> bool:
    """Animação de trio (círculo verde grande) por cima das prateleiras: o frame não serve para ler."""
    H, W = img.shape[:2]
    hsv = cv2.cvtColor(img[int(H * 0.25) : int(H * 0.88)], cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, np.array((55, 150, 120)), np.array((85, 255, 255)))
    n, _, st, _ = cv2.connectedComponentsWithStats(m, 8)
    return bool(n > 1 and st[1:, 4].max() > EFFECT_AREA * H * W)


def _sub(full: Obs, ids) -> Obs:
    o = Obs([full.front[i] for i in ids], [full.back[i] for i in ids])
    o.exhausted = {j for j, i in enumerate(ids) if i in full.exhausted}
    return o


def schedule(path, avail, horizon: float = 20.0, dt: float = 0.25):
    """Simula a execução de um caminho ao longo do tempo: cada passo espera até as duas prateleiras
    estarem utilizáveis. Devolve (tempo total à espera, espera até ao 1.º passo) ou None."""
    t, waited, first = 0.0, 0.0, None
    for s, x, d, _ in path:
        t0 = t
        while not (avail(s, t) and avail(d, t)):
            t += dt
            if t - t0 > horizon:
                return None
        w = t - t0
        if first is None:
            first = w
        if w > 0:
            waited += w + READ_T  # depois de esperar é preciso voltar a ler
            t += READ_T
        t += MOVE_T
    return waited, first or 0.0


def decide(full: Obs, avail, now_ids: list[int], lam: float, max_tau: float = MAX_TAU, step: float = STEP):
    """Escolhe o que fazer. `full` é o tabuleiro inteiro (paradas + passadeiras de memória),
    `avail(i, t)` diz se a prateleira i está utilizável daqui a t s e `now_ids` são as que se
    podem usar já. Opções, comparadas por jogadas + lam × segundos de espera:
    - "agora": o melhor trio só com as prateleiras à vista;
    - "esperar": o melhor trio com as prateleiras que estarão à vista daqui a τ s;
    - "global": o melhor trio no tabuleiro inteiro, jogando cada passo quando as suas prateleiras
      passarem (ex.: juntar numa prateleira parada vazia produtos de 3 prateleiras da passadeira).
    Devolve (tipo, passos em índices de full, segundos a esperar, custo)."""
    now_set = set(now_ids)
    obs_now = _sub(full, now_ids)
    cost_now = triple_cost(obs_now)
    opts = []
    if cost_now < 99:
        opts.append((cost_now, 0, "agora", 0.0, cost_now))
    if lam < 1e8:
        cache: dict[tuple, int] = {}
        tau = step
        while tau <= min(max_tau, 3.0 / lam) + 1e-9:
            ids = tuple(i for i in range(len(full.front)) if avail(i, tau))
            if ids not in cache:
                cache[ids] = triple_cost(_sub(full, ids))
            c = cache[ids]
            if 0 < c < 99:
                opts.append((c + lam * tau, 2, "esperar", tau, c))
            tau += step
    gpath = triple_path(full) if USE_GLOBAL and cost_now >= 99 else None
    if gpath:
        sch = schedule(gpath, avail)
        if sch is not None and (sch[0] == 0 or lam < 1e8):
            opts.append((len(gpath) + lam * sch[0], 1, "global", sch[1], len(gpath)))
    if not opts:  # nenhum trio ao alcance: cavar com o que está à vista
        steps = [(now_ids[s], x, now_ids[d], False) for s, x, d in plan(obs_now)]
        return ("cavar" if steps else "nada"), steps, (0.0 if steps else 0.5), 99
    score, _, kind, wait, cost = min(opts)
    if kind == "agora":
        return kind, [(now_ids[s], x, now_ids[d], False) for s, x, d in plan(obs_now)], 0.0, cost
    if kind == "esperar":
        return kind, [], wait, cost
    if wait > 0:
        return kind, [], wait, cost
    steps = []
    for st in gpath:  # passos que já se podem jogar, até à primeira revelação
        if st[0] not in now_set or st[2] not in now_set:
            break
        steps.append(st)
        if st[3]:
            break
    return kind, steps, (0.0 if steps else 0.3), cost


def live_conveyor(dev, auto=True, max_moves=290, time_limit=459.0, log_dir: Path | None = None, use_hammer=True):
    """max_moves e time_limit são os limites do nível (para gerir a espera); o fim real é
    quando o jogo mostra o resultado."""
    from tools.overlay import overlay

    from .powerups import buttons
    from .run import draw_moves, to_obs

    lat = getattr(dev, "lat", LAT)  # atrasos próprios de cada ponte (ver bot/device.py)
    ovh = getattr(dev, "tap_overhead", 0.0)

    log_dir = log_dir or Path("runs") / time.strftime("%Y%m%d-%H%M%S")
    log_dir.mkdir(parents=True, exist_ok=True)
    img = dev.screenshot()
    W = img.shape[1]
    shelves0 = detect_full(img)
    bands = bands_from(shelves0)
    speeds = measure_speeds(dev, bands)
    print("linhas:", [(y0, round(v)) for (y0, _), v in zip(bands, speeds)], flush=True)
    belts = {r: Belt(v, PITCH * W) for r, v in enumerate(speeds) if v != 0.0}
    sw = float(np.median([s.w for s in shelves0])) if shelves0 else W * 0.26
    btn = buttons(img)  # martelo, relógio e baralhar (detetados no ecrã)

    cat = Catalog()
    mem: set[tuple[int, int]] = set()  # (linha, coluna) das prateleiras paradas esgotadas
    static_empty: dict[tuple[int, int], int] = {}
    done, reads, waits, effect_waits, board_reads = 0, 0, 0, 0, 0
    n_warm: int | None = None  # tipos aprendidos nas primeiras leituras (os "de confiança")
    hammer_used = freeze_used = not use_hammer
    lost_since = None
    t_start = time.time()
    wait_used = 0.0
    fh_log = open(log_dir / "log.txt", "a")
    fh_taps = open(log_dir / "taps.txt", "a")
    while done < max_moves + 15:  # o jogo pode contar menos (toques falhados)
        t_loop = time.time()
        img, t_f = read_frame(dev, bands, speeds)
        found = detect_full(img) if img is not None else []
        if img is None or len(found) < 4:
            lost_since = lost_since or time.time()
            if time.time() - lost_since > 8:
                print("Não vejo o tabuleiro há 8 s (nível acabou ou pop-up). A parar.")
                cv2.imwrite(str(log_dir / "fim.png"), dev.screenshot())
                break
            time.sleep(0.3)
            continue
        lost_since = None
        # animação de trio por cima das prateleiras: este frame não serve para ler
        if has_effect(img) and effect_waits < 5:
            effect_waits += 1
            time.sleep(0.15)
            continue
        effect_waits = 0
        board_reads += 1
        # 1) passadeiras: corrigir a referência e dar identidade às prateleiras inteiras à vista
        rows_all = [row_of(s, bands) for s in found]
        for r, b in belts.items():
            b.recalibrate([s.x for s, rr in zip(found, rows_all) if rr == r], t_f)
            speeds[r] = b.v
        keys_all = []
        for s, r in zip(found, rows_all):
            if r in belts:
                keys_all.append(("b", r, belts[r].ident(s.x, t_f)))
            else:
                keys_all.append(("s", r, int(round((s.x + s.w / 2) / (W / 3) - 0.5))))
        shelves_all = [Shelf(i, s.x, s.y, s.w, s.h) for i, s in enumerate(found)]
        _, views = read_board(img, cat, shelves_all)
        if board_reads == 3:
            n_warm = len(cat.protos)
        obs_all = to_obs(views)
        # tipos novos e raros a meio do jogo são quase sempre lixo de animação: tratar como desconhecidos
        def suspicious(x):
            return x is not None and x != UNK and n_warm is not None and x >= n_warm and cat.protos[x].n < 4

        for rr in obs_all.front + obs_all.back:
            for j, x in enumerate(rr):
                if suspicious(x):
                    rr[j] = UNK
        trio = [i for i, r_ in enumerate(obs_all.front) if r_[0] is not None and r_[0] != UNK and r_.count(r_[0]) == SLOTS]
        if trio and waits < 2:
            waits += 1  # um trio ainda a desaparecer: esperar e voltar a ler
            time.sleep(0.3)
            continue
        for i in trio:  # "trio" que não desaparece = leitura errada: não usar esses produtos
            obs_all.front[i] = [UNK] * SLOTS
        waits = 0
        # 2) memória (uma prateleira só conta como esgotada se se vir vazia em 2 leituras)
        for i, k in enumerate(keys_all):
            fr = obs_all.front[i]
            empty = all(x is None for x in fr)
            if k[0] == "s":
                static_empty[k[1:]] = static_empty.get(k[1:], 0) + 1 if empty else 0
                if static_empty[k[1:]] >= 2:
                    mem.add(k[1:])
                continue
            b, kk = belts[k[1]], k[2]
            prev = b.mem.get(kk)
            clean = kk not in b.dirty
            if prev is not None and clean and UNK not in fr:
                if prev[0] == fr:
                    b.same += 1
                else:
                    b.diff += 1
                    fh_log.write(f"  memória != leitura: passadeira {k[1]} prateleira {kk}: {prev[0]} vs {fr} (x={found[i].x})\n")
                # apareceram produtos que não pusemos lá: afinal não estava esgotada
                if kk in b.exhausted and all(x is None for x in prev[0]) and not empty:
                    b.exhausted.discard(kk)
            if UNK in fr and prev is not None and clean:
                continue  # leitura com dúvidas: manter o que se sabia
            b.mem[kk] = (list(fr), list(obs_all.back[i]))
            b.dirty.discard(kk)
            b.empty_seen[kk] = b.empty_seen.get(kk, 0) + 1 if empty else 0
            if b.empty_seen[kk] >= 2:
                b.exhausted.add(kk)

        # 3) tabuleiro inteiro (paradas + memória das passadeiras) e o que se pode usar já
        now = time.time()
        now_found = [i for i, (s, r) in enumerate(zip(found, rows_all))
                     if r not in belts or _usable(s.x + speeds[r] * (now - t_f + lat), s.w, speeds[r], W)]
        full_keys = [k for k in keys_all if k[0] == "s"] + [("b", r, kk) for r, b in belts.items() for kk in sorted(b.mem)]
        pos = {k: j for j, k in enumerate(full_keys)}
        cur = {k: i for i, k in enumerate(keys_all)}
        full = Obs([], [])
        for k in full_keys:
            if k in cur and (k[0] == "s" or cur[k] in now_found):
                full.front.append(list(obs_all.front[cur[k]]))
                full.back.append(list(obs_all.back[cur[k]]))
            else:
                fr, bk = belts[k[1]].mem[k[2]]
                full.front.append(list(fr))
                full.back.append(list(bk))
        full.exhausted = {j for j, k in enumerate(full_keys)
                          if (k[1:] in mem if k[0] == "s" else k[2] in belts[k[1]].exhausted)}
        now_ids = [pos[keys_all[i]] for i in now_found if keys_all[i] in pos]
        now_set = set(now_ids)
        trust = all(b.trusted() for b in belts.values())

        def avail(j, t):
            k = full_keys[j]
            if k[0] == "s":
                return True
            if t <= 0:
                return j in now_set
            if not trust:
                return False
            b = belts[k[1]]
            return _usable(b.x_at(k[2], now + t + lat, W, sw), sw, b.v, W)

        busy = now - t_start - wait_used
        per_move = busy / done if done >= 10 else 1.1
        moves_left = max(1, max_moves - done)
        spare = (time_limit - SAFETY - (now - t_start)) - moves_left * per_move
        per_triple = max(0.0, spare) / max(1.0, moves_left / 2.2)
        lam = 1.0 / (C_WAIT * per_triple) if per_triple > 0.05 else 1e9
        kind, steps, wait, cost = decide(full, avail, now_ids, lam)
        reads += 1
        obs = _sub(full, now_ids)
        inv = {pos[keys_all[i]]: i for i in now_found if keys_all[i] in pos}
        idx_found = [inv[j] for j in now_ids]
        shelves = [Shelf(n, found[i].x, found[i].y, found[i].w, found[i].h) for n, i in enumerate(idx_found)]
        rows = [rows_all[i] for i in idx_found]
        keys = [keys_all[i] for i in idx_found]
        steps_now = []
        for s_, x, d, _ in steps:
            if s_ not in now_set or d not in now_set:
                break
            steps_now.append((now_ids.index(s_), x, now_ids.index(d)))
        moves = []
        for n in range(len(steps_now), 0, -1):  # se a memória enganou, jogar só o que bate certo
            try:
                moves = to_moves(obs, steps_now[:n])
                break
            except (ValueError, IndexError):
                continue
        cv2.imwrite(str(log_dir / f"{reads:03d}.png"), draw_moves(overlay(img, shelves, [views[i] for i in idx_found]), shelves, moves))
        cv2.imwrite(str(log_dir / f"raw_{reads:03d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        fh_log.write(f"{reads} t={now - t_start:.1f} keys={keys} front={obs.front} moves={[str(m) for m in moves]} "
                     f"decisao={kind} custo={cost} espera={wait:.1f} lam={lam:.2f} spare={spare:.0f} "
                     f"v={[round(b.v, 1) for b in belts.values()]} mem={[(r, sorted(b.mem), sorted(b.exhausted), b.same, b.diff) for r, b in belts.items()]}\n")
        fh_log.flush()
        if not moves:
            if kind == "esperar":
                print(f"  à espera {wait:.1f}s: com as prateleiras que vêm aí o trio custa {cost}", flush=True)
            time.sleep(min(max(wait, 0.3), 2.5))
            wait_used += time.time() - t_loop
            continue
        # 4) power-ups
        if auto and not freeze_used and done >= 20 and spare < 10:
            print("[relógio] a congelar o tempo 10 s", flush=True)
            dev.tap(*btn["relogio"])
            freeze_used = True
            time_limit += 10.0
            time.sleep(0.4)
            continue
        if auto and not hammer_used and len(moves) >= 3 and done >= 6:
            print(f"[martelo] o próximo trio custava {len(moves)} jogadas: a usar o martelo", flush=True)
            dev.tap(*btn["martelo"])
            hammer_used = True
            time.sleep(0.6)
            continue
        # 5) jogar a sequência numa só cadeia de toques, tocando onde as prateleiras vão estar
        t_req = time.time()
        taps, off, ok_moves = [], 0.0, []
        for m in moves:
            pts = []
            for i, slot, extra in ((m.src, m.src_slot, 0.0), (m.dst, m.dst_slot, (TAP_MS + GAP_MS) / 1000 + ovh)):
                x, y = shelves[i].slot_center(slot)
                x += speeds[rows[i]] * (t_req + lat + off + extra - t_f)
                pts.append((x, y))
            if not all(40 < x < W - 40 for x, _ in pts):
                print("  (prateleira a sair do ecrã: o resto fica para a próxima leitura)", flush=True)
                break
            taps += [(pts[0][0], pts[0][1], GAP_MS), (pts[1][0], pts[1][1], MOVE_PAUSE_MS)]
            off += (2 * TAP_MS + GAP_MS + MOVE_PAUSE_MS) / 1000 + 2 * ovh
            ok_moves.append(m)
        if not ok_moves:
            time.sleep(0.2)
            continue
        tag = lambda i, k: f"linha {rows[i] + 1}{' (passadeira)' if speeds[rows[i]] else ''} pos {k + 1}"
        for j, m in enumerate(ok_moves):
            print(f"[{done + j + 1:3d} | {t_req - t_start:5.1f}s] {tag(m.src, m.src_slot)} -> {tag(m.dst, m.dst_slot)}"
                  f"{'  (' + kind + ')' if kind != 'agora' else ''}", flush=True)
        taps[-1] = (taps[-1][0], taps[-1][1], 0)
        dev.chain(taps)
        dur = time.time() - t_req
        for m, (a, b_) in zip(ok_moves, zip(taps[::2], taps[1::2])):
            fh_taps.write(f"{reads} {m} t_req-t_f={t_req - t_f:.3f} va={speeds[rows[m.src]]:.0f} vb={speeds[rows[m.dst]]:.0f} "
                          f"xa={a[0]:.0f} ya={a[1]:.0f} xb={b_[0]:.0f} yb={b_[1]:.0f} dur={dur:.3f} n={len(ok_moves)}\n")
        fh_taps.flush()
        done += len(ok_moves)
        # memória das passadeiras: aplicar o efeito previsto das jogadas
        F = [list(r) for r in obs.front]
        for m in ok_moves:
            x = F[m.src][m.src_slot]
            F[m.src][m.src_slot], F[m.dst][m.dst_slot] = None, x
            if x != UNK and F[m.dst].count(x) == SLOTS:
                F[m.dst] = [None] * SLOTS
        for i in {m.src for m in ok_moves} | {m.dst for m in ok_moves}:
            k = keys[i]
            if k[0] != "b":
                continue
            b, kk = belts[k[1]], k[2]
            b.dirty.add(kk)
            if all(x is None for x in F[i]) and kk not in b.exhausted:
                b.mem.pop(kk, None)  # vai aparecer a camada de trás: não se sabe o que é
            else:
                b.mem[kk] = (F[i], [None] * SLOTS)
        time.sleep(0.35)  # deixar acabar as animações (trio a desaparecer, camada a avançar)
    fh_log.close()
    fh_taps.close()
    print(f"Fim: {done} jogadas em {time.time() - t_start:.0f} s (espera total {wait_used:.0f} s). Leituras guardadas em {log_dir}")
