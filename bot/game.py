"""Modelo do jogo (regras) + simulador para testar o solver sem o telemóvel.

Regras (observadas na gravação do nível 23):
- 12 prateleiras, cada uma com 3 posições à frente e várias camadas atrás;
- uma jogada = arrastar um produto da frente para uma posição vazia de outra prateleira;
- 3 produtos iguais na frente de uma prateleira desaparecem (1 estrela);
- quando a frente de uma prateleira fica vazia, avança a camada seguinte;
- da camada de trás só se vê a silhueta, e só onde a posição da frente está vazia;
- limite de jogadas (245) e de tempo (7:25).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

SLOTS = 3
UNK = -1  # produto que existe mas não sabemos qual é


@dataclass
class Obs:
    """O que o bot vê: frente de cada prateleira e, onde der, a camada de trás."""

    front: list[list[int | None]]
    # camada de trás, só nas posições da frente vazias: tipo, UNK (há silhueta mas não se
    # reconheceu) ou None (não se vê nada atrás)
    back: list[list[int | None]] = field(default_factory=list)
    # prateleiras que já se viram completamente vazias: não têm mais camadas (memória entre leituras)
    exhausted: set[int] = field(default_factory=set)


def remember_exhausted(mem: set[int], obs: "Obs") -> "Obs":
    """Atualiza a memória de prateleiras esgotadas e anexa-a à observação."""
    for s, row in enumerate(obs.front):
        if all(v is None for v in row):
            mem.add(s)
    obs.exhausted = set(mem)
    return obs


@dataclass
class Move:
    src: int
    src_slot: int
    dst: int
    dst_slot: int

    def __str__(self):
        return f"P{self.src}[{self.src_slot}] -> P{self.dst}[{self.dst_slot}]"


class Sim:
    """Simulador com as mesmas regras do jogo (só para testes)."""

    def __init__(self, layers: list[list[list[int | None]]]):
        # layers[s][0] é a frente; o resto são as camadas de trás
        self.layers = [[list(l) for l in sh] for sh in layers]
        self.moves = 0
        self.triples = 0

    @staticmethod
    def random_level(n_shelves=12, n_types=12, triples_per_type=8, empty_frac=0.06, seed=None):
        rnd = random.Random(seed)
        items = [t for t in range(n_types) for _ in range(3 * triples_per_type)]
        rnd.shuffle(items)
        shelves: list[list[list[int | None]]] = [[] for _ in range(n_shelves)]
        s = 0
        while items:
            layer = []
            for _ in range(SLOTS):
                layer.append(None if (rnd.random() < empty_frac or not items) else items.pop())
            if any(x is not None for x in layer):
                shelves[s].append(layer)
            s = (s + 1) % n_shelves
        # como no jogo real, a frente começa com pelo menos 2 posições vazias
        fronts = [(i, k) for i in range(n_shelves) for k in range(SLOTS) if shelves[i] and shelves[i][0][k] is not None]
        empties = sum(1 for i in range(n_shelves) for k in range(SLOTS) if shelves[i] and shelves[i][0][k] is None)
        for i, k in rnd.sample(fronts, max(0, 2 - empties)):
            shelves[i].append([shelves[i][0][k], None, None])
            shelves[i][0][k] = None
        sim = Sim(shelves)
        for i in range(n_shelves):
            sim._settle(i)
        return sim

    def front(self, s):
        return self.layers[s][0] if self.layers[s] else [None] * SLOTS

    def obs(self) -> Obs:
        front = [list(self.front(s)) for s in range(len(self.layers))]
        back = []
        for s in range(len(self.layers)):
            nxt = self.layers[s][1] if len(self.layers[s]) > 1 else [None] * SLOTS
            back.append([nxt[k] if front[s][k] is None else None for k in range(SLOTS)])
        return Obs(front, back)

    def done(self):
        return all(not sh for sh in self.layers)

    def _settle(self, s):
        sh = self.layers[s]
        while sh:
            f = sh[0]
            if all(x is None for x in f):
                sh.pop(0)
            elif f[0] is not None and f.count(f[0]) == SLOTS:  # camada que já vem com trio
                sh[0] = [None] * SLOTS
                self.triples += 1
            else:
                break

    def apply(self, m: Move):
        a, b = self.front(m.src), self.front(m.dst)
        assert m.src != m.dst and a[m.src_slot] is not None and b[m.dst_slot] is None, m
        b[m.dst_slot], a[m.src_slot] = a[m.src_slot], None
        self.moves += 1
        if b[0] is not None and b.count(b[0]) == SLOTS:
            self.layers[m.dst][0] = [None] * SLOTS
            self.triples += 1
        self._settle(m.src)
        self._settle(m.dst)
