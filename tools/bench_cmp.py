"""Compara o solver com e sem antecipação de 2 trios, nos mesmos níveis."""
import statistics, sys, time
import bot.solver as S
from tools.bench import run
N, S0 = int(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 0
for la in (False, True):
    S.LOOKAHEAD = la
    t = time.time()
    res = [run(i) for i in range(S0, S0 + N)]
    ok = [r for r in res if r[0]]
    print(f"lookahead={la}: resolvidos {len(ok)}/{N}, dentro de 245: {sum(r[1] <= 245 for r in ok)}, "
          f"jogadas/trio {statistics.mean(r[1]/r[2] for r in ok):.3f}, máx {max(r[1] for r in ok)}, {time.time()-t:.0f}s", flush=True)
