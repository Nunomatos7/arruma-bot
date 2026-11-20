"""Interface comum aos dispositivos (iPhone por WebDriverAgent, iPhone por Replicação, Android por adb).

Cada ponte implementa:
- screenshot(path=None, newer_than=0.0) -> imagem BGR (numpy) do ecrã inteiro do telemóvel;
- tap(x, y): um toque, em píxeis da imagem;
- move(x1, y1, x2, y2): uma jogada (tocar no produto e depois no destino);
- chain([(x, y, pausa_ms), ...]): vários toques seguidos, o mais juntos possível (modo passadeiras);
- check_user(): trava de segurança (levanta UserTookOver se o utilizador mexer no rato);
- stream.stamp: instante (time.time()) em que o último frame foi capturado (modo passadeiras).

E estes atributos, usados para acertar os toques nas passadeiras:
- lat: segundos entre o frame chegar ao computador e o primeiro toque acontecer no ecrã;
- tap_overhead: segundos que cada toque de uma cadeia demora a mais do que as pausas pedidas.
"""
from __future__ import annotations


class UserTookOver(Exception):
    """O utilizador mexeu no rato ou no telemóvel: o bot para."""
