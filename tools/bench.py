"""Testa o solver em muitos níveis aleatórios do simulador."""
import statistics, sys
from bot.game import Sim, remember_exhausted
from bot.solver import choose_move

def run(seed, limit=245, **kw):
    sim = Sim.random_level(seed=seed, **kw)
    total = sum(1 for sh in sim.layers for l in sh for x in l if x is not None) // 3
    mem = set()
    while not sim.done() and sim.moves < 2000:
        m = choose_move(remember_exhausted(mem, sim.obs()))
        if m is None:
            break
        sim.apply(m)
    return sim.done(), sim.moves, total

if __name__ == "__main__":
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    S = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    res = [run(i) for i in range(S, S + N)]
    solved = [r for r in res if r[0]]
    within = [r for r in solved if r[1] <= 245]
    print(f"resolvidos: {len(solved)}/{N}  dentro de 245 jogadas: {len(within)}/{N}")
    if solved:
        print("jogadas: média %.1f  mediana %d  máx %d  (trios: %d)  jogadas/trio %.2f" % (
            statistics.mean(r[1] for r in solved), statistics.median(r[1] for r in solved),
            max(r[1] for r in solved), res[0][2], statistics.mean(r[1]/r[2] for r in solved)))
    stuck = [i for i, r in enumerate(res) if not r[0]]
    print("encravados (seeds):", stuck[:15])
