"""Visão: lê o estado do tabuleiro a partir de um screenshot.

Para cada posição de cada prateleira devolve:
- front: o tipo do produto da frente, ou None se a posição estiver vazia;
- back:  o tipo da silhueta escura da camada de trás, se der para ver, senão None.

Os tipos não estão pré-definidos: o Catalog aprende-os sozinho. Produtos iguais são o
mesmo sprite, por isso usamos template matching (com deslocamento) contra protótipos.
Tudo é feito numa escala canónica (prateleira com CANON_W píxeis de largura), para que
a gravação do iPhone e a janela do Espelhamento deem o mesmo resultado.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .board import SLOTS, Shelf, find_shelves

CANON_W = 150  # largura canónica do interior de uma prateleira (px)


def pixel_masks(bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(front, silhouette): fundo claro é ignorado; silhueta = escuro e pouco saturado."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    s, v = hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    bg = (v > 190) & (s < 28)
    sil = (v < 84) & (s < 125)
    return ~bg & ~sil, sil


@dataclass
class Proto:
    img: np.ndarray  # recorte BGR float32 do produto
    mask: np.ndarray  # píxeis que pertencem mesmo ao produto (float32 0/1)
    shape: np.ndarray  # silhueta cheia (uint8 0/255), para reconhecer a camada de trás
    n: int = 1


@dataclass
class SlotView:
    shelf: int
    slot: int
    front_ratio: float
    sil_ratio: float
    front: int | None = None
    back: int | None = None
    score: float = 0.0


def _canon(img: np.ndarray, shelf: Shelf):
    """Recorta a prateleira e põe-na na escala canónica."""
    crop = img[shelf.y : shelf.y + shelf.h, shelf.x : shelf.x + shelf.w]
    f = CANON_W / shelf.w
    return cv2.resize(crop, (CANON_W, int(round(shelf.h * f))), interpolation=cv2.INTER_AREA)


def _slot_range(k: int, margin: float = 0.0) -> tuple[int, int]:
    sw = CANON_W / SLOTS
    return max(0, int(k * sw - margin * sw)), min(CANON_W, int((k + 1) * sw + margin * sw))


def _object(front: np.ndarray, k: int):
    """Máscara do objeto da posição k.

    1.º: componentes ligados cujo centro cai na posição (limpo quando os produtos não se tocam);
    se isso apanhar pouco (produtos colados formam um só componente), usa os píxeis da coluna.
    """
    x0, x1 = _slot_range(k)
    m = cv2.morphologyEx(front.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(m, 8)
    keep = np.zeros(m.shape, bool)
    for i in range(1, n):
        if stats[i, 4] >= 25 and x0 <= cent[i, 0] < x1:
            keep |= lab == i
    lo, hi = _slot_range(k, 0.12)
    keep[:, :lo] = False
    keep[:, hi:] = False
    col = np.zeros(m.shape, bool)
    clo, chi = _slot_range(k, 0.05)
    col[:, clo:chi] = m[:, clo:chi] > 0
    if keep[:, x0:x1].sum() < 0.5 * col[:, x0:x1].sum():
        return col
    return keep


DARK_V = 120  # brilho e croma (máx - mín dos canais) abaixo dos quais um píxel parece silhueta
DARK_CHROMA = 45


def _trim_dark_top(region: np.ndarray, obj: np.ndarray) -> np.ndarray:
    """Tira ao objeto as linhas de cima que são quase todas escuras.

    Uma silhueta da camada de trás encostada ao produto junta-se-lhe na máscara e torna-o mais
    alto do que é. Sem este corte o mesmo produto, com e sem silhueta atrás, dava dois tipos."""
    rows = np.nonzero(obj.any(axis=1))[0]
    if len(rows) == 0:
        return obj
    y0, y1 = rows[0], rows[-1] + 1
    mx, mn = region.max(axis=2), region.min(axis=2)
    gray_dark = (mx < DARK_V) & (mx - mn < DARK_CHROMA)  # silhueta: escura e quase sem cor
    cut, stop = y0, y1 - max(12, int(0.4 * (y1 - y0)))
    while cut < stop:
        m = obj[cut]
        if m.sum() >= 2 and gray_dark[cut][m].mean() > 0.6:
            cut += 1
        else:
            break
    if cut - y0 < 4:
        return obj
    obj = obj.copy()
    obj[:cut] = False
    return obj


def _bbox(mask: np.ndarray):
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def _fill(mask: np.ndarray) -> np.ndarray:
    m = mask.astype(np.uint8) * 255
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = np.zeros_like(m)
    cv2.drawContours(out, [c for c in cnts if cv2.contourArea(c) > 15], -1, 255, -1)
    return out


PAD = 12  # píxeis (escala canónica) de margem à volta da região ao comparar com os protótipos


@dataclass
class Catalog:
    """Protótipos de produto aprendidos.

    Mesmo tipo se a diferença de cor < thr; ou, na zona cinzenta (< thr_loose), se a
    textura também bater (correlação normalizada >= ncc_min). Embalagens de cartão
    diferentes têm cores parecidas mas texturas diferentes (nível 26)."""

    thr: float = 0.06
    thr_loose: float = 0.10
    ncc_min: float = 0.65
    protos: list[Proto] = field(default_factory=list)

    def _score(self, region: np.ndarray, p: Proto, h: int | None = None) -> tuple[float, tuple[int, int]]:
        """Diferença média (0..1) do melhor encaixe do protótipo dentro da região.

        Os produtos estão sempre assentes na prateleira e o que "suja" um recorte é a
        silhueta da camada de trás, que fica por cima. Por isso compara-se só a parte de
        baixo do protótipo, com a altura do mais baixo dos dois."""
        pimg, pmask = p.img, p.mask
        if h is not None and h < pimg.shape[0]:
            pimg, pmask = pimg[-h:], pmask[-h:]
        ph, pw = pmask.shape
        rh, rw = region.shape[:2]
        if ph > rh or pw > rw or pmask.sum() < 30:
            return 9.0, (0, 0)
        res = cv2.matchTemplate(region, pimg, cv2.TM_SQDIFF, mask=np.repeat(pmask[..., None], 3, 2))
        _, _, loc, _ = cv2.minMaxLoc(res)
        x, y = loc
        win = region[y : y + ph, x : x + pw]
        diff = np.abs(win - pimg).mean(axis=2) / 255.0
        d = np.sort(diff[pmask > 0])
        # média aparada: ignora os 20% piores píxeis (bordas, silhuetas atrás, vizinhos)
        return float(d[: max(1, int(len(d) * 0.8))].mean()), loc

    def _ncc(self, region: np.ndarray, p: Proto, h: int | None = None) -> float:
        pimg, pmask = p.img, p.mask
        if h is not None and h < pimg.shape[0]:
            pimg, pmask = pimg[-h:], pmask[-h:]
        if pimg.shape[0] > region.shape[0] or pimg.shape[1] > region.shape[1] or pmask.sum() < 30:
            return -1.0
        r = cv2.matchTemplate(region, pimg, cv2.TM_CCOEFF_NORMED, mask=np.repeat(pmask[..., None], 3, 2))
        r[~np.isfinite(r)] = -1
        return float(r.max())

    def classify(self, region: np.ndarray, obj: np.ndarray, learn: bool):
        obj = _trim_dark_top(region, obj)
        bb = _bbox(obj)
        if bb is None:
            return None, 9.0
        x0, y0, x1, y1 = bb
        h, w = y1 - y0, x1 - x0
        crop_region = region
        # margem à volta da região: um produto encostado à borda da posição tem de poder alinhar com
        # um protótipo cujo recorte seja um pouco mais largo (senão nasce um tipo duplicado)
        region = cv2.copyMakeBorder(region, PAD, PAD, PAD, PAD, cv2.BORDER_REPLICATE)
        best, best_s = None, 9.0
        cands = []
        for t, p in enumerate(self.protos):
            ph, pw = p.mask.shape
            if min(ph, h) < 0.45 * max(ph, h):  # alturas muito diferentes: outro produto
                continue
            s, _ = self._score(region, p, min(ph, h))
            cands.append((s, t, min(ph, h)))
            if s < best_s:
                best, best_s = t, s
        if best is not None and best_s < self.thr:
            self.protos[best].n += 1
            return best, best_s
        # zona cinzenta: só aceita se a textura também bater
        for s, t, hh in sorted(cands):
            if s >= self.thr_loose:
                break
            if self._ncc(region, self.protos[t], hh) >= self.ncc_min:
                self.protos[t].n += 1
                return t, s
        if not learn or h < 12 or w < 10:
            return None, best_s
        crop = crop_region[y0:y1, x0:x1].copy()
        mask = obj[y0:y1, x0:x1].astype(np.float32)
        self.protos.append(Proto(crop, mask, _fill(mask > 0)))
        return len(self.protos) - 1, 0.0

    def match_back(self, sil: np.ndarray, min_iou: float = 0.72) -> tuple[int | None, float]:
        """A camada de trás aparece como silhueta escura quase uniforme: compara-se a
        forma (IoU no melhor deslocamento) com o contorno de cada produto conhecido."""
        silf = sil.astype(np.float32)
        best, best_iou = None, min_iou
        for t, p in enumerate(self.protos):
            if p.n < 3:  # protótipos raros podem ser lixo de animação
                continue
            shp = (p.shape > 0).astype(np.float32)
            if shp.shape[0] > silf.shape[0] or shp.shape[1] > silf.shape[1]:
                continue
            inter = cv2.matchTemplate(silf, shp, cv2.TM_CCORR)
            win = cv2.matchTemplate(silf, np.ones_like(shp), cv2.TM_CCORR)
            iou = inter / (shp.sum() + win - inter + 1e-6)
            v = float(iou.max())
            if v > best_iou:
                best, best_iou = t, v
        return best, best_iou


EMPTY_FRONT = 0.025  # fração mínima de píxeis com cor viva para haver produto
SIL_VISIBLE = 0.08  # fração mínima de silhueta para tentar identificar a camada de trás


def read_board(img: np.ndarray, catalog: Catalog, shelves: list[Shelf] | None = None, learn: bool = True):
    shelves = shelves or find_shelves(img)
    views: list[list[SlotView]] = []
    for s in shelves:
        c = _canon(img, s)
        H = c.shape[0]
        top = int(H * 0.15)  # o topo da prateleira está sempre vazio
        c = c[top : H - 2]
        cf = c.astype(np.float32)
        front, sil = pixel_masks(c)
        hsv = cv2.cvtColor(c, cv2.COLOR_BGR2HSV)
        # "há produto à frente" = há píxeis com cor viva; silhuetas e o chão cinzento não têm
        colorful = (hsv[..., 1] > 70) & (hsv[..., 2] > 95)
        row = []
        for k in range(SLOTS):
            x0, x1 = _slot_range(k)
            area = (x1 - x0) * c.shape[0]
            obj = _object(front & ~(sil), k)
            v = SlotView(s.idx, k, colorful[:, x0 + 3 : x1 - 3].sum() / area, sil[:, x0:x1].sum() / area)
            if v.front_ratio >= EMPTY_FRONT:
                lo, hi = _slot_range(k, 0.3)
                region = cf[:, lo:hi]
                v.front, v.score = catalog.classify(region, obj[:, lo:hi], learn)
            elif v.sil_ratio >= SIL_VISIBLE:
                lo, hi = _slot_range(k, 0.3)
                sm = sil[:, lo:hi].astype(np.uint8)
                sm = cv2.morphologyEx(sm, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
                v.back, v.score = catalog.match_back(_fill(sm > 0) > 0)
            row.append(v)
        views.append(row)
    return shelves, views
