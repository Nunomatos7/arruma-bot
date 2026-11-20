"""Solver: escolhe as próximas jogadas a partir do que se vê no tabuleiro.

1. Pesquisa A* pelo trio mais próximo (menor número de jogadas). O estado é a frente
   das 12 prateleiras; a ordem dentro de uma prateleira não interessa, por isso cada
   prateleira é guardada como multiconjunto (tuplo ordenado), o que corta muito a
   pesquisa. Heurística admissível: para fazer um trio de X na prateleira B é preciso
   pelo menos (X que faltam) + (intrusos a tirar de B) jogadas.
2. Quando uma prateleira fica vazia, a camada seguinte avança. Dentro da pesquisa isso
   é modelado de forma pessimista: as posições ficam ocupadas por produtos
   desconhecidos (UNK), exceto as que já se viram em silhueta.
3. Se não há trio ao alcance, "escava": procura a forma mais barata de esvaziar uma
   prateleira para revelar a camada seguinte.

Como a camada de trás só se conhece quando aparece, o bot executa a 1.ª jogada (ou as
jogadas até à próxima revelação), volta a ler o ecrã e repete.
"""
from __future__ import annotations

import heapq
import itertools
from collections import Counter

from .game import SLOTS, UNK, Move, Obs

E = None  # posição vazia
_ORDER = lambda x: (x is None, -2 if x is None else x)  # vazias no fim


def _canon(row) -> tuple:
    return tuple(sorted(row, key=_ORDER))


class _Search:
    def __init__(self, obs: Obs):
        self.n = len(obs.front)
        self.back = [
            tuple(UNK if b is None else b for b in (obs.back[s] if obs.back else [None] * SLOTS))
            for s in range(self.n)
        ]
        # prateleira com a frente toda vazia já não tem camadas atrás (senão teriam avançado):
        # esvaziá-la outra vez não revela nada. A memória (obs.exhausted) guarda as que já se
        # viram vazias em leituras anteriores, mesmo que agora tenham lá um produto.
        ex = set(getattr(obs, "exhausted", set()) or set())
        ex |= {s for s in range(self.n) if all(v is None for v in obs.front[s])}
        self.exhausted = sum(1 << s for s in ex)
        # onde escavar: prateleiras com silhueta visível atrás (prova de que há outra camada).
        # Uma posição vazia sem nada atrás é sinal de que a prateleira está a acabar.
        back = obs.back or [[None] * SLOTS for _ in range(self.n)]
        evidence = {s for s in range(self.n) if s not in ex and any(b is not None for b in back[s])}
        doubtful = {s for s in range(self.n) if s not in ex and s not in evidence
                    and any(obs.front[s][k] is None for k in range(SLOTS))}
        self.dig_ok = evidence if evidence else {s for s in range(self.n) if s not in ex and s not in doubtful}
        if not self.dig_ok:
            self.dig_ok = {s for s in range(self.n) if s not in ex}

    # ---- estado: tuplo de prateleiras (multiconjuntos) + quais já revelaram a camada de trás
    def moves(self, state):
        shelves, revealed = state
        for s in range(self.n):
            seen = set()
            for x in shelves[s]:
                if x is E or x in seen:
                    continue
                seen.add(x)
                for d in range(self.n):
                    if d != s and E in shelves[d]:
                        yield s, x, d

    def apply(self, state, s, x, d):
        """Devolve (novo_estado, fez_trio, revelou)."""
        shelves, revealed = state
        sh = list(shelves)
        a = list(sh[s]); a[a.index(x)] = E
        b = list(sh[d]); b[b.index(E)] = x
        triple = x != UNK and b.count(x) == SLOTS
        rev = revealed
        if triple:
            if (self.exhausted >> d) & 1:
                b = [E] * SLOTS  # prateleira esgotada: fica vazia
            else:
                # a camada de trás avança para a frente desta prateleira
                b = list(self.back[d]) if not (revealed >> d) & 1 else [UNK] * SLOTS
                rev = rev | (1 << d)
        reveal = False
        if all(v is E for v in a) and not (self.exhausted >> s) & 1:
            reveal = True
            # pessimista: o que vem atrás ocupa as 3 posições (o que se viu em silhueta fica com o tipo)
            a = list(self.back[s]) if not (rev >> s) & 1 else [UNK] * SLOTS
            rev = rev | (1 << s)
        sh[s], sh[d] = _canon(a), _canon(b)
        return (tuple(sh), rev), triple, reveal

    @staticmethod
    def h_triple(state):
        shelves, _ = state
        cnt = Counter(x for row in shelves for x in row if x is not E and x != UNK)
        best = 99
        for x, c in cnt.items():
            if c < SLOTS:
                continue
            for row in shelves:
                nx = row.count(x)
                others = sum(1 for v in row if v is not E and v != x)
                best = min(best, SLOTS - nx + others)
        return best

    @staticmethod
    def h_reveal(state):
        shelves, _ = state
        return min((sum(v is not E for v in row) for row in shelves if any(v is not E for v in row)), default=99)

    def value(self, state) -> tuple:
        """Qualidade de um estado (menor = melhor): custo até ao próximo trio, depois espaço livre."""
        shelves, _ = state
        empties = sum(v is E for row in shelves for v in row)
        pairs = sum(1 for row in shelves for x in set(row) if x is not E and x != UNK and row.count(x) == 2)
        return (self.h_triple(state), -pairs, -empties)

    def astar(self, start, goal: str, max_depth=7, max_nodes=40000, slack=0, all_paths=False):
        """A* pelo evento mais próximo; entre os caminhos mais curtos escolhe o que deixa o melhor estado.
        Com all_paths=True devolve todos os caminhos encontrados até (mais curto + slack)."""
        h = self.h_triple if goal == "triple" else self.h_reveal
        tie = itertools.count()
        h0 = h(start)
        if h0 >= 99:
            return None
        frontier = [(h0, 0, next(tie), start, [])]
        best_g = {start: 0}
        nodes = 0
        found, found_len = [], None
        while frontier and nodes < max_nodes:
            f, g, _, st, path = heapq.heappop(frontier)
            if found_len is not None and f > found_len + slack:
                break
            nodes += 1
            if g >= max_depth:
                continue
            for s, x, d in self.moves(st):
                nst, triple, reveal = self.apply(st, s, x, d)
                npath = path + [(s, x, d, triple, reveal)]
                if (goal == "triple" and triple) or (goal == "reveal" and reveal and s in self.dig_ok):
                    if found_len is None or g + 1 <= found_len + slack:
                        found_len = g + 1 if found_len is None else min(found_len, g + 1)
                        found.append((self.value(nst), next(tie), npath, nst))
                    continue
                ng = g + 1
                if best_g.get(nst, 99) <= ng:
                    continue
                best_g[nst] = ng
                hv = h(nst)
                if hv >= 99:
                    continue
                heapq.heappush(frontier, (ng + hv, ng, next(tie), nst, npath))
        if not found:
            return None
        if all_paths:
            return [(x[2], x[3]) for x in found if len(x[2]) <= found_len + slack]
        found = [x for x in found if len(x[2]) == found_len]
        return min(found)[2]


LOOKAHEAD = False  # antecipação de 2 trios ("cheap" ou True): melhor em teoria, mas lenta demais em Python


def _two_step(srch: _Search, start):
    """Escolhe, entre os caminhos curtos até um trio, o que deixa o trio seguinte mais barato."""
    cands = srch.astar(start, "triple", slack=1, all_paths=True, max_nodes=6000)
    if not cands:
        return None
    # limitar o número de candidatos avaliados (os de melhor valor primeiro)
    cands.sort(key=lambda c: (len(c[0]), srch.value(c[1])))
    best, best_key = None, None
    for path, st in cands[:8]:
        nxt = srch.astar(st, "triple", max_depth=4, max_nodes=800)
        n2 = len(nxt) if nxt else 6
        key = (len(path) + n2, len(path), srch.value(st))
        if best_key is None or key < best_key:
            best, best_key = path, key
    return best


def _cheap_two_step(srch: _Search, start):
    """Antecipação barata: entre os caminhos até (mais curto + 1), escolhe o que minimiza
    jogadas até este trio + estimativa (h) até ao trio seguinte."""
    cands = srch.astar(start, "triple", slack=1, all_paths=True, max_nodes=20000)
    if not cands:
        return None
    return min(cands, key=lambda c: (len(c[0]) + srch.h_triple(c[1]), len(c[0]), srch.value(c[1])))[0]


def plan(obs: Obs) -> list[tuple[int, int, int]]:
    """Lista de jogadas (shelf_origem, tipo, shelf_destino) até ao próximo evento."""
    if any(r[0] is not None and r[0] != UNK and r.count(r[0]) == SLOTS for r in obs.front):
        return []  # há um trio ainda a desaparecer: esperar pela próxima leitura
    srch = _Search(obs)
    start = (tuple(_canon(r) for r in obs.front), 0)
    if all(E not in r for r in start[0]):
        return []
    if LOOKAHEAD == "cheap":
        path = _cheap_two_step(srch, start)
    elif LOOKAHEAD:
        path = _two_step(srch, start)
    else:
        path = srch.astar(start, "triple")
    if path is None:
        path = srch.astar(start, "reveal")
    if not path:
        return []
    # executar até (e incluindo) o primeiro trio ou revelação: daí para a frente o ecrã muda
    out = []
    for s, x, d, triple, reveal in path:
        out.append((s, x, d))
        if triple or reveal:
            break
    return out


def to_moves(obs: Obs, steps: list[tuple[int, int, int]]) -> list[Move]:
    """Converte (origem, tipo, destino) em posições concretas, seguindo o tabuleiro real."""
    F = [list(r) for r in obs.front]
    out = []
    for s, x, d in steps:
        k = F[s].index(x)
        e = F[d].index(None)
        out.append(Move(s, k, d, e))
        F[d][e], F[s][k] = x, None
        if x != UNK and F[d].count(x) == SLOTS:
            F[d] = [None] * SLOTS
    return out


def choose_move(obs: Obs) -> Move | None:
    mv = to_moves(obs, plan(obs)[:1])
    return mv[0] if mv else None


def triple_path(obs: Obs) -> list[tuple[int, int, int, bool]] | None:
    """Caminho completo (origem, tipo, destino, revela?) até ao próximo trio, mesmo que passe por revelações."""
    srch = _Search(obs)
    start = (tuple(_canon(r) for r in obs.front), 0)
    if all(E not in r for r in start[0]):
        return None
    path = srch.astar(start, "triple")
    return [(s, x, d, reveal) for s, x, d, _, reveal in path] if path else None


def triple_cost(obs: Obs) -> int:
    """Jogadas até ao próximo trio (caminho completo, mesmo que passe por revelações); 99 se não houver."""
    if any(r[0] is not None and r[0] != UNK and r.count(r[0]) == SLOTS for r in obs.front):
        return 0
    path = triple_path(obs)
    return len(path) if path else 99
