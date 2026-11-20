"""Simulador de um nível com passadeiras (como o 26) para comparar estratégias, sem telemóvel.

Modelo (medido na gravação do nível 26):
- 6 prateleiras paradas (linhas 1 e 4) + 2 passadeiras com 6 prateleiras cada;
- cada passadeira anda ~119 px/s; espaçamento 345 px; volta de 2070 px (~17 s);
- o ecrã mostra 1178 px: uma prateleira de passadeira está "utilizável" se estiver inteira no
  ecrã e continuar inteira durante HORIZON segundos;
- cada jogada demora ~1,2 s (medido ao vivo); 290 jogadas e 459 s (7:39).

    .venv/bin/python -m tools.conveyor_sim 6
"""
from __future__ import annotations

import random
import statistics
import sys
import time as _time

from bot.game import SLOTS, Obs, Sim, remember_exhausted
from bot.solver import plan, to_moves, triple_cost

PITCH, LOOP, SCREEN, SHELF_W = 345.0, 2070.0, 1178.0, 306.0
SPEED = 119.0
MOVE_T = 1.2
N_STATIC, N_BELT = 6, 6


def belt_x(j: int, direction: int, t: float) -> float:
    """Posição x (no ecrã) da prateleira j da passadeira no instante t (pode estar fora do ecrã)."""
    x = (j * PITCH + direction * SPEED * t) % LOOP
    return x - (LOOP - SCREEN) / 2  # centra a janela do ecrã na volta


def usable(x: float, direction: int, horizon: float) -> bool:
    x2 = x + direction * SPEED * horizon
    return 6 <= x <= SCREEN - SHELF_W - 6 and 6 <= x2 <= SCREEN - SHELF_W - 6


def make_level(seed: int, n_types=13, triples=153, gap=0.04) -> Sim:
    rnd = random.Random(seed)
    n = N_STATIC + 2 * N_BELT
    items = [t for t in range(n_types) for _ in range(3 * (triples // n_types))]
    items += [rnd.randrange(n_types)] * 0
    rnd.shuffle(items)
    shelves = [[] for _ in range(n)]
    s = 0
    while items:
        layer = [items.pop() if items and rnd.random() > gap else None for _ in range(SLOTS)]
        if any(x is not None for x in layer):
            shelves[s].append(layer)
        s = (s + 1) % n
    sim = Sim(shelves)
    for i in range(n):
        sim._settle(i)
    return sim


def visible(t: float, horizon: float) -> list[int]:
    ids = list(range(N_STATIC))
    for b, direction in ((0, +1), (1, -1)):
        for j in range(N_BELT):
            if usable(belt_x(j, direction, t), direction, horizon):
                ids.append(N_STATIC + b * N_BELT + j)
    return ids


def run(seed: int, wait_long=(3, 2.6), wait_short=(2, 1.2), wait_budget=110.0, horizon=1.6,
        max_moves=290, time_limit=459.0, gap=0.25, adaptive=False):
    sim = make_level(seed, gap=gap)
    total = sum(1 for sh in sim.layers for l in sh for x in l if x is not None) // 3
    t, waited, waiting_since = 0.0, 0.0, None
    mem: set[int] = set()
    full = sim.obs()
    while not sim.done() and sim.moves < max_moves and t < time_limit:
        ids = visible(t, horizon)
        full = sim.obs()
        obs = Obs([full.front[i] for i in ids], [full.back[i] for i in ids])
        for k, i in enumerate(ids):  # memória só das paradas
            if i < N_STATIC and all(v is None for v in full.front[i]):
                mem.add(i)
        obs.exhausted = {k for k, i in enumerate(ids) if i in mem}
        moves = to_moves(obs, plan(obs))
        if not moves:
            t += 0.5
            continue
        L = len(moves)
        if adaptive:
            from bot.conveyor import SAFETY, wait_limit

            spare = (time_limit - SAFETY - t) - (max_moves - sim.moves) * MOVE_T
            limit = wait_limit(L, spare)
        else:
            limit = wait_long[1] if L >= wait_long[0] else (wait_short[1] if L >= wait_short[0] and waited < wait_budget / 2 else 0.0)
            limit = limit if waited < wait_budget else 0.0
        if limit:
            waiting_since = t if waiting_since is None else waiting_since
            if t - waiting_since < limit:
                t += 0.3
                waited += 0.3
                continue
        waiting_since = None
        for m in moves:
            src, dst = ids[m.src], ids[m.dst]
            # a prateleira ainda está utilizável quando o toque acontece?
            ok = all(i < N_STATIC or usable(belt_x((i - N_STATIC) % N_BELT, +1 if i < N_STATIC + N_BELT else -1, t), +1 if i < N_STATIC + N_BELT else -1, 0.3)
                     for i in (src, dst))
            if not ok:
                break
            from bot.game import Move

            if sim.front(src)[m.src_slot] is None or sim.front(dst)[m.dst_slot] is not None:
                break
            sim.apply(Move(src, m.src_slot, dst, m.dst_slot))
            t += MOVE_T
        t += 0.45
    return sim.done(), sim.moves, sim.triples, total, t, waited


def main(n: int):
    configs = {
        "adaptativa": dict(adaptive=True),
        "sem espera": dict(wait_long=(99, 0), wait_short=(99, 0), horizon=2.2),
        "sem espera, horizon 1.6": dict(wait_long=(99, 0), wait_short=(99, 0), horizon=1.6),
        "espera 3+:2.6s": dict(wait_short=(99, 0)),
        "espera 3+:2.6s, 2:1.2s": dict(),
        "espera 2+:3.0s": dict(wait_long=(2, 3.0), wait_short=(99, 0), wait_budget=200),
    }
    for name, kw in configs.items():
        t0 = _time.time()
        res = [run(s, **kw) for s in range(500, 500 + n)]
        won = sum(r[0] for r in res)
        mpt = statistics.mean(r[1] / max(1, r[2]) for r in res)
        print(f"{name:26s} ganhos {won}/{n}  jogadas/trio {mpt:.3f}  trios {statistics.mean(r[2] for r in res):.0f}/{res[0][3]}"
              f"  tempo {statistics.mean(r[4] for r in res):.0f}s  espera {statistics.mean(r[5] for r in res):.0f}s  ({_time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 6)


def run_memory(seed: int, c: float = 2.0, step: float = 0.5, horizon=1.6, max_moves=290, time_limit=469.0,
               move_t=0.76, seg_t=0.95, gap=0.25, max_tau=17.4, belt_exhausted=True):
    """Política com memória das passadeiras: o conteúdo das prateleiras fora do ecrã é conhecido
    (viu-se na última passagem e só o jogador o muda). Para cada instante futuro t+τ calcula-se o
    plano com as prateleiras utilizáveis nesse instante e escolhe-se o que minimiza
    jogadas + λ·τ, com λ dado pela folga de tempo."""
    sim = make_level(seed, gap=gap)
    total = sum(1 for sh in sim.layers for l in sh for x in l if x is not None) // 3
    t, waited = 0.0, 0.0
    mem: set[int] = set()
    from bot.game import Move

    def obs_for(ids):
        full = sim.obs()
        o = Obs([full.front[i] for i in ids], [full.back[i] for i in ids])
        o.exhausted = {k for k, i in enumerate(ids) if i in mem}
        return o

    while not sim.done() and sim.moves < max_moves and t < time_limit:
        full = sim.obs()
        for i in range(len(full.front)):
            if (belt_exhausted or i < N_STATIC) and all(v is None for v in full.front[i]):
                mem.add(i)
        left = total - sim.triples
        spare = (time_limit - SAFETY_SIM - t) - (max_moves - sim.moves) * (move_t + seg_t / 2)
        per_triple = max(0.0, spare) / max(1, left)
        lam = 1.0 / (c * per_triple) if per_triple > 0.05 else 1e9
        best, cache = None, {}
        tau = 0.0
        while tau <= max_tau + 1e-9:
            if lam * tau > 3:  # nunca compensa
                break
            ids = tuple(visible(t + tau, horizon))
            if ids not in cache:
                o = obs_for(ids)
                cache[ids] = triple_cost(o)
            score = cache[ids] + lam * tau
            if cache[ids] < 99 and (best is None or score < best[0] - 1e-9):
                best = (score, tau)
            tau += step
        if best is None:
            best = (0, 0.0)  # nenhum trio ao alcance: cavar já (plano de revelação)
        if best[1] > 0:
            t += best[1]
            waited += best[1]
        ids = visible(t, horizon)
        o = obs_for(ids)
        moves = to_moves(o, plan(o))
        for m in moves:
            src, dst = ids[m.src], ids[m.dst]
            ok = all(i < N_STATIC or usable(belt_x((i - N_STATIC) % N_BELT, +1 if i < N_STATIC + N_BELT else -1, t),
                                            +1 if i < N_STATIC + N_BELT else -1, 0.3) for i in (src, dst))
            if not ok or sim.front(src)[m.src_slot] is None or sim.front(dst)[m.dst_slot] is not None:
                break
            sim.apply(Move(src, m.src_slot, dst, m.dst_slot))
            t += move_t
        if not moves:
            t += 0.5
            waited += 0.5
        t += seg_t
    return sim.done(), sim.moves, sim.triples, total, t, waited


SAFETY_SIM = 10.0


def main_memory(n: int):
    cfgs = {
        "sem espera (tempo real)": dict(c=1e-9),
        "memória c=1": dict(c=1.0),
        "memória c=2": dict(c=2.0),
        "memória c=4": dict(c=4.0),
    }
    for name, kw in cfgs.items():
        t0 = _time.time()
        res = [run_memory(s, **kw) for s in range(500, 500 + n)]
        won = sum(r[0] for r in res)
        mpt = statistics.mean(r[1] / max(1, r[2]) for r in res)
        print(f"{name:26s} ganhos {won}/{n}  jogadas/trio {mpt:.3f}  trios {statistics.mean(r[2] for r in res):.0f}/{res[0][3]}"
              f"  tempo {statistics.mean(r[4] for r in res):.0f}s  espera {statistics.mean(r[5] for r in res):.0f}s  ({_time.time() - t0:.0f}s)", flush=True)


def run_decide(seed: int, use_global=True, c: float = 1.0, horizon=1.6, max_moves=290, time_limit=469.0,
               move_t=0.5, seg_t=0.9, gap=0.25, verbose=False):
    """A política do bot ao vivo (bot.conveyor.decide), com ou sem a opção "global"."""
    from bot import conveyor as cv
    from bot.game import Move

    sim = make_level(seed, gap=gap)
    total = sum(1 for sh in sim.layers for l in sh for x in l if x is not None) // 3
    t, waited = 0.0, 0.0
    mem: set[int] = set()
    kinds = {}
    n = N_STATIC + 2 * N_BELT

    def belt_of(i):
        return (i - N_STATIC) % N_BELT, (+1 if i < N_STATIC + N_BELT else -1)

    while not sim.done() and sim.moves < max_moves and t < time_limit:
        full = sim.obs()
        for i in range(n):
            if all(v is None for v in full.front[i]):
                mem.add(i)
        full.exhausted = set(mem)
        now_ids = visible(t, horizon)
        t_now = t

        def avail(i, dt):
            if i < N_STATIC:
                return True
            j, dr = belt_of(i)
            return usable(belt_x(j, dr, t_now + dt), dr, horizon)

        left = total - sim.triples
        spare = (time_limit - SAFETY_SIM - t) - (max_moves - sim.moves) * (move_t + seg_t / 2)
        per_triple = max(0.0, spare) / max(1, left)
        lam = 1.0 / (c * per_triple) if per_triple > 0.05 else 1e9
        if use_global:
            kind, steps, wait, cost = cv.decide(full, avail, now_ids, lam)
        else:
            gp = cv.triple_path
            cv.triple_path = lambda o: None
            try:
                kind, steps, wait, cost = cv.decide(full, avail, now_ids, lam)
            finally:
                cv.triple_path = gp
        kinds[kind] = kinds.get(kind, 0) + 1
        if wait > 0 and not steps:
            w = min(wait, 2.5)
            t += w
            waited += w
            continue
        moves = to_moves(full, [(s, x, d) for s, x, d, _ in steps])
        for m in moves:
            ok = all(i < N_STATIC or usable(belt_x(*belt_of(i), t), belt_of(i)[1], 0.3) for i in (m.src, m.dst))
            if not ok or sim.front(m.src)[m.src_slot] is None or sim.front(m.dst)[m.dst_slot] is not None:
                break
            sim.apply(Move(m.src, m.src_slot, m.dst, m.dst_slot))
            t += move_t
        t += seg_t
    if verbose:
        print(kinds)
    return sim.done(), sim.moves, sim.triples, total, t, waited


def main_decide(n: int):
    for name, kw in {"sem global (4.ª tentativa)": dict(use_global=False), "com global": dict(use_global=True)}.items():
        t0 = _time.time()
        res = [run_decide(s, **kw) for s in range(500, 500 + n)]
        won = sum(r[0] for r in res)
        mpt = statistics.mean(r[1] / max(1, r[2]) for r in res)
        print(f"{name:28s} ganhos {won}/{n}  jogadas/trio {mpt:.3f}  trios {statistics.mean(r[2] for r in res):.0f}/{res[0][3]}"
              f"  tempo {statistics.mean(r[4] for r in res):.0f}s  espera {statistics.mean(r[5] for r in res):.0f}s  ({_time.time() - t0:.0f}s)", flush=True)
