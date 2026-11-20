"""Deteção do tabuleiro: encontra as prateleiras e recorta as 3 posições de cada uma."""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

SLOTS = 3


@dataclass
class Shelf:
    idx: int
    x: int
    y: int
    w: int
    h: int

    def slot_box(self, k: int) -> tuple[int, int, int, int]:
        """(x, y, w, h) da posição k (0..2) dentro da prateleira."""
        sw = self.w / SLOTS
        return int(self.x + k * sw), self.y, int(sw), self.h

    def slot_center(self, k: int) -> tuple[int, int]:
        x, y, w, h = self.slot_box(k)
        return x + w // 2, y + int(h * 0.68)


def find_shelves(img: np.ndarray) -> list[Shelf]:
    """Os interiores das prateleiras são zonas quase brancas, quase quadradas e grandes."""
    H, W = img.shape[:2]
    m = (img.min(axis=2) > 235).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    min_area = (W * 0.2) ** 2 * 0.45
    boxes = []
    for x, y, w, h, area in stats[1:]:
        if area < min_area or not (0.8 < w / h < 1.25) or w < W * 0.2:
            continue
        boxes.append((x, y, w, h))
    if not boxes:
        return []
    # alinhar numa grelha: agrupar por linha (y) e ordenar por coluna (x)
    boxes.sort(key=lambda b: b[1])
    rows, cur = [], [boxes[0]]
    for b in boxes[1:]:
        if abs(b[1] - cur[0][1]) < b[3] * 0.3:
            cur.append(b)
        else:
            rows.append(cur)
            cur = [b]
    rows.append(cur)
    shelves = []
    for row in rows:
        for b in sorted(row, key=lambda b: b[0]):
            shelves.append(Shelf(len(shelves), *map(int, b)))
    return shelves


def draw(img: np.ndarray, shelves: list[Shelf]) -> np.ndarray:
    out = img.copy()
    for s in shelves:
        cv2.rectangle(out, (s.x, s.y), (s.x + s.w, s.y + s.h), (0, 0, 255), 3)
        for k in range(1, SLOTS):
            x = s.x + int(k * s.w / SLOTS)
            cv2.line(out, (x, s.y), (x, s.y + s.h), (255, 0, 0), 2)
        cv2.putText(out, str(s.idx), (s.x + 8, s.y + 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
    return out
