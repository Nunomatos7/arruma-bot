# Como funciona

Este documento explica o bot por dentro: o que cada módulo faz, os algoritmos e porquê, e os parâmetros que
se podem afinar. Para instalar, ver [instalar-mac-iphone.md](instalar-mac-iphone.md) ou
[instalar-android.md](instalar-android.md).

- [Visão geral](#visão-geral)
- [O jogo como problema](#o-jogo-como-problema)
- [Ligação ao telemóvel](#ligação-ao-telemóvel)
- [Visão: do screenshot ao estado](#visão-do-screenshot-ao-estado)
- [Solver: escolher as jogadas](#solver-escolher-as-jogadas)
- [Ciclo ao vivo (níveis normais)](#ciclo-ao-vivo-níveis-normais)
- [Modo passadeiras (nível 26)](#modo-passadeiras-nível-26)
- [Parâmetros](#parâmetros)

## Visão geral

```
                 ┌──────────────────────── telemóvel ─────────────────────────┐
                 │  iPhone: WebDriverAgent (stream MJPEG + toques W3C)        │
                 │  Android: adb (screencap + input tap)                      │
                 └───────────────┬───────────────────────────────▲────────────┘
                     screenshot  │                               │ toques
                                 ▼                               │
   board.py ──► vision.py ──► game.Obs ──► solver.py ──► run.py / conveyor.py
  prateleiras   tipos de      frente,      A* até ao     decide, compensa o
  (12 caixas    produto       trás,        próximo trio  movimento, toca, regista
   brancas)     aprendidos    esgotadas
```

| Módulo | Responsabilidade |
|---|---|
| [bot/device.py](../bot/device.py) | Interface comum às pontes (o que cada uma tem de implementar) |
| [bot/wda.py](../bot/wda.py) | iPhone por WebDriverAgent: arranque com `xcodebuild`, stream MJPEG, toques |
| [bot/android.py](../bot/android.py) | Android por adb: `screencap` cru, `input tap` |
| [bot/iphone.py](../bot/iphone.py) | iPhone pela Replicação do iPhone (macOS): captura da janela e cliques do rato |
| [bot/board.py](../bot/board.py) | Encontra as 12 prateleiras e as 3 posições de cada uma |
| [bot/vision.py](../bot/vision.py) | Diz o que está em cada posição (frente e silhueta de trás) |
| [bot/game.py](../bot/game.py) | Regras do jogo, estado observado (`Obs`) e um simulador |
| [bot/solver.py](../bot/solver.py) | A* pelo trio mais próximo, ou pela revelação mais barata |
| [bot/powerups.py](../bot/powerups.py) | Encontra os botões do martelo, relógio e baralhar |
| [bot/run.py](../bot/run.py) | Linha de comandos e ciclo ao vivo dos níveis normais |
| [bot/conveyor.py](../bot/conveyor.py) | Modo dos níveis com passadeiras |

## O jogo como problema

- 12 prateleiras (4 linhas × 3), cada uma com **3 posições à frente** e várias **camadas atrás**.
- Uma jogada: tocar num produto (fica selecionado) e tocar numa posição vazia de outra prateleira.
  **Arrastar não funciona**, só toques.
- 3 produtos iguais na mesma prateleira desaparecem (um **trio**).
- Quando a frente de uma prateleira fica vazia, a camada de trás avança. Das camadas de trás só se vê a
  **silhueta** escura, e só nas posições da frente que estão vazias.
- O nível acaba quando não há produtos (vitória) ou quando acabam as jogadas ou o tempo.

O que o torna difícil:
- **informação parcial:** não se sabe o que vem atrás;
- **pouco espaço:** no início há em média só 1–2 posições livres, por isso é fácil gastar jogadas a "arrumar"
  sem fazer trios;
- **orçamento apertado:** ~2,0–2,3 jogadas por trio (ex.: nível 23, 245 jogadas para ~100 trios).

## Ligação ao telemóvel

Todas as pontes têm a mesma interface ([bot/device.py](../bot/device.py)): `screenshot()`, `tap()`, `move()`
(produto → destino), `chain()` (vários toques seguidos) e `stream.stamp` (instante do último frame).

**iPhone / WebDriverAgent** ([bot/wda.py](../bot/wda.py)):
- O WDA é um "teste de interface" XCUITest que corre no iPhone e expõe uma API HTTP (porta 8100) e um stream MJPEG
  (porta 9100).
- O bot lê o stream numa thread (`MjpegReader`): ~15 frames/s à resolução total. É muito mais rápido do que pedir
  screenshots PNG (~1 s cada).
- Os toques são ações W3C (`/session/:id/actions`). Uma jogada é **uma só chamada HTTP** (toque, 120 ms, toque).
  Cada chamada custa ~0,4 s fixos, por isso no modo passadeiras as jogadas de uma sequência vão numa só cadeia.
- `waitForIdleTimeout = 0`: o jogo está sempre animado e, sem isto, o WDA esperaria que a app "parasse".
- `start()` compila com `xcodebuild build-for-testing` (uma vez) e arranca com `test-without-building`, apanhando
  o URL na linha `ServerURLHere->...<-ServerURLHere` do log.

**Android / adb** ([bot/android.py](../bot/android.py)): `adb exec-out screencap` sem `-p` devolve a imagem
crua (cabeçalho de 12 ou 16 bytes + RGBA), evitando a compressão PNG no telemóvel. Os toques são
`input tap x y; sleep ...; input tap ...` num só `adb shell`.

## Visão: do screenshot ao estado

### Prateleiras ([bot/board.py](../bot/board.py))

As prateleiras são caixas **brancas quase puras**. Um limiar (`min(B,G,R) > 235`) e componentes ligados dão
caixas com proporção ~1:1 e largura > 20% do ecrã. Agrupam-se por linhas (y parecido) e ordenam-se por x. Cada
prateleira divide-se em 3 posições; o centro de toque de cada posição fica a 68% da altura (onde estão os produtos).

### Escala canónica

Cada prateleira é recortada e reamostrada para **150 px de largura** (`CANON_W`). Assim a mesma visão funciona
com o stream do iPhone (1178 px de largura), uma gravação de ecrã ou um Android com outra resolução.

### Há produto? Frente, silhueta ou vazio

Por píxel (HSV):
- **fundo:** V > 190 e S < 28 (branco/cinzento claro);
- **silhueta** da camada de trás: V < 84 e S < 125 (escuro e pouco saturado);
- **produto à frente:** o resto.

Para decidir se uma posição tem produto à frente usa-se a fração de píxeis com **cor viva** (S > 70 e V > 95):
as silhuetas têm reflexos cinzentos e o chão da prateleira também é cinzento, mas só os produtos têm cor.
Abaixo de 2,5% (`EMPTY_FRONT`) a posição está vazia; se tiver mais de 8% de silhueta (`SIL_VISIBLE`), tenta-se
reconhecer o que está atrás.

O objeto de cada posição são os componentes ligados cujo centro cai nessa posição. Se dois produtos se tocam e
formam um só componente, usa-se a coluna da posição.

### Tipos aprendidos, não rotulados ([bot/vision.py](../bot/vision.py), `Catalog`)

Cada nível tem produtos diferentes, por isso não há catálogo pré-definido: **o primeiro produto de cada tipo
passa a protótipo** e os seguintes comparam-se com eles. Produtos iguais são o mesmo sprite, por isso basta
template matching com máscara (`cv2.matchTemplate`, `TM_SQDIFF`) e deslocamento.

Detalhes que fazem a diferença (cada um corrigiu um erro real):

| Problema observado | Solução |
|---|---|
| A silhueta de trás "suja" o topo do recorte | **Comparação ancorada em baixo:** os produtos assentam na prateleira; compara-se só a parte de baixo, com a altura do mais baixo dos dois, e **média aparada** (ignora os 20% piores píxeis) |
| Produtos muito diferentes em altura emparelhados | só se comparam alturas com razão ≥ 0,45 |
| Embalagens de cartão parecidas lidas como iguais (nível 26) | limiar estrito (diferença < 0,06) e, numa zona cinzenta (< 0,10), exige-se também **correlação normalizada** ≥ 0,65 (textura) |
| Produto encostado à borda da posição criava um tipo duplicado | **margem** de 12 px (replicada) à volta da região, para o protótipo poder alinhar |
| Produto com a silhueta de trás colada por cima criava outro tipo | **corte do topo escuro:** tiram-se as linhas de cima que são quase só píxeis escuros e sem cor (max < 120 e croma < 45) |

Com as duas últimas correções, o nível 26 passou de 22 para 13 tipos (o número real de produtos), sem partir
nenhum produto nos níveis 23–25.

### Silhuetas de trás

Uma silhueta é uma mancha escura quase uniforme: compara-se a **forma** (IoU no melhor deslocamento) com o
contorno de cada protótipo visto pelo menos 3 vezes. IoU ≥ 0,72 dá o tipo; abaixo disso fica "há qualquer coisa,
não sei o quê" (`UNK`).

## Solver: escolher as jogadas

[bot/solver.py](../bot/solver.py) recebe um `Obs` (frente de cada prateleira, silhuetas de trás, prateleiras
esgotadas) e devolve as jogadas até ao **próximo trio** (ou à próxima revelação de camada).

- **Estado:** a frente das prateleiras como **multiconjuntos** (a ordem dentro de uma prateleira não interessa),
  o que corta muito a pesquisa.
- **A\*** com heurística **admissível**: para fazer um trio de X na prateleira B são precisas pelo menos
  (X que faltam em B) + (intrusos a tirar de B) jogadas. Profundidade máxima 7, até 40 000 nós.
- **Camadas de trás, de forma pessimista:** se uma jogada esvazia uma prateleira, a camada seguinte entra como
  produtos desconhecidos (`UNK`), exceto as posições cuja silhueta foi reconhecida.
- **Desempate:** entre os caminhos mais curtos, escolhe o que deixa mais pares e mais espaço livre. No simulador
  isto passou de 84% para 100% de níveis resolvidos.
- **Escavar:** se não há trio ao alcance, procura a forma mais barata de esvaziar uma prateleira **com silhueta
  atrás** (prova de que há outra camada).
- **Prateleiras esgotadas, com memória:** uma prateleira que alguma vez se viu vazia já não tem camadas.
  Sem esta memória o bot "escavava" uma prateleira esgotada e andava com o mesmo produto para trás e para a frente
  (no nível 24, 7 vezes; depois da correção, 0).

Porquê planear só até ao próximo trio? Depois de um trio ou de uma revelação o tabuleiro muda de formas
imprevisíveis, por isso é melhor voltar a ler o ecrã. Antecipar 2 trios foi testado: no simulador não melhorou e
era 30× mais lento.

## Ciclo ao vivo (níveis normais)

[bot/run.py](../bot/run.py), função `live()`:

1. **Esperar que o ecrã pare:** tira screenshots até o tabuleiro ficar igual em 3 seguidos.
2. **Ler** as 12 prateleiras e montar o `Obs` (com a memória de esgotadas).
3. **Trio a desaparecer:** se a leitura apanha 3 iguais numa prateleira (animação), espera e relê, em vez de
   "planear" jogadas para os juntar. Se o "trio" não desaparece em 2 leituras, é uma leitura errada e esses
   produtos passam a `UNK`.
4. **Planear** e, com `--auto`, **tocar**. Sem `--auto` mostra as setas e espera que tu jogues.
5. **Martelo:** se o próximo trio custar 3 ou mais jogadas (e já houver 6 jogadas), usa o martelo, que faz um trio
   sem gastar jogadas.
6. **Trava de segurança:** se 4 leituras seguidas mostram o mesmo tabuleiro depois de jogar, os toques não estão a
   ter efeito e o bot para.

## Modo passadeiras (nível 26)

No nível 26, as linhas 2 e 3 são **passadeiras**: andam em sentidos opostos a ~120 px/s, com 6 prateleiras cada
(a volta mede 2070 px, ~17 s) e só ~3 cabem no ecrã. [bot/conveyor.py](../bot/conveyor.py) é ativado sozinho
quando o bot mede movimento numa linha.

### Medir as passadeiras

- `measure_speeds()`: correlação de fase (`cv2.phaseCorrelate`) entre duas faixas da mesma linha com 0,5 s de
  intervalo. |v| < 15 px/s conta como parada.
- `tools/belts.py`: mede numa gravação a velocidade, o comprimento da volta (autocorrelação de um "panorama" da
  passadeira) e quantas prateleiras tem.

### Ler e tocar com o tabuleiro em movimento

- A leitura espera só que as linhas **paradas** estabilizem.
- Frames com a **animação de trio** (um círculo verde grande por cima das prateleiras) são ignorados.
- Só entram no plano prateleiras **inteiras no ecrã** que lá vão continuar durante a jogada (1,6 s).
- **Compensação do movimento:** toca-se onde a prateleira vai estar:
  `x_toque = x_lido + v × (t_pedido − t_frame + lat + desvio_na_cadeia)`, com `lat` = 0,32 s no iPhone.

### Seguir e lembrar cada prateleira

Num referencial que anda com a passadeira (`u = x − v·t`) as prateleiras estão paradas e distam 345 px. A
identidade de uma prateleira é `round((u − ref) / 345) mod 6`. A velocidade medida tem ~10% de erro, por isso a
referência e a própria velocidade são **corrigidas a cada leitura** com o desvio das posições observadas.

Com a identidade, o bot **lembra-se do que está em cada prateleira** quando ela sai do ecrã (só o jogador muda o
conteúdo). Proteções:
- revendo uma prateleira, compara com a memória; se a memória falhar muito (`Belt.trusted()`), deixa de a usar;
- uma prateleira só conta como esgotada se se vir vazia em **2 leituras** (logo a seguir a um trio fica vazia por
  instantes);
- tipos novos e raros a meio do jogo são tratados como desconhecidos (costumam ser lixo de animações);
- as jogadas feitas atualizam a memória com o efeito previsto.

### Esperar só quando compensa

Esperar não gasta jogadas, e a passadeira traz uma prateleira nova a cada ~3 s. `decide()` compara:
- **agora:** o melhor trio com as prateleiras à vista;
- **esperar τ s:** o melhor trio com as prateleiras que estarão à vista daqui a τ (0,5 a 12 s), usando a memória;

e escolhe o mínimo de **jogadas + λ × segundos de espera**, onde λ vem da **folga de tempo**:

```
folga = tempo restante − margem − jogadas restantes × tempo por jogada
λ     = 1 / (folga por trio restante)
```

Com folga grande, esperar é barato; sem folga, nunca espera. Quando a folga acaba usa o **relógio** (congela o
tempo 10 s).

Também se testou um **plano global** (juntar numa prateleira parada vazia produtos de várias prateleiras da
passadeira, ao longo do tempo). No simulador não foi melhor e gerava esperas longas, por isso está desligado
(`USE_GLOBAL`).

### Jogadas em cadeia

As jogadas de uma sequência vão num só pedido (`chain`), com 120 ms entre produto e destino e 300 ms entre
jogadas, e cada toque é previsto para o instante exato em que acontece. Passou de ~1,6 s para ~1,1 s por jogada.

## Parâmetros

| Onde | Nome | Valor | O que controla |
|---|---|---|---|
| vision.py | `CANON_W` | 150 | largura canónica de uma prateleira |
| vision.py | `Catalog.thr` / `thr_loose` / `ncc_min` | 0.06 / 0.10 / 0.65 | quando dois recortes são o mesmo produto |
| vision.py | `PAD` | 12 | margem à volta da região ao comparar |
| vision.py | `DARK_V` / `DARK_CHROMA` | 120 / 45 | o que conta como silhueta colada ao produto |
| vision.py | `EMPTY_FRONT` / `SIL_VISIBLE` | 0.025 / 0.08 | posição vazia / há silhueta atrás |
| solver.py | `astar(max_depth, max_nodes)` | 7 / 40000 | profundidade e esforço da pesquisa |
| solver.py | `LOOKAHEAD` | False | antecipação de 2 trios (testada, desligada) |
| run.py | martelo | custo ≥ 3, depois de 6 jogadas | quando usar o martelo |
| conveyor.py | `LAT` (ou `dev.lat`, `--lat`) | 0.32 | atraso frame → toque |
| conveyor.py | `HORIZON` | 1.6 s | quanto tempo uma prateleira tem de continuar à vista |
| conveyor.py | `N_BELT` / `PITCH` | 6 / 345 px (em 1178) | prateleiras por passadeira / distância entre elas |
| conveyor.py | `MAX_TAU` / `STEP` / `C_WAIT` | 12 s / 0.5 s / 1.0 | espera máxima, passo e peso da folga |
| conveyor.py | `GAP_MS` / `MOVE_PAUSE_MS` | 120 / 300 | pausas dentro de uma cadeia de toques |
| conveyor.py | `SAFETY` | 15 s | margem no fim do relógio |
| conveyor.py | `EFFECT_AREA` | 0.006 | tamanho da mancha verde que conta como animação |
| conveyor.py | `USE_GLOBAL` | False | plano global (testado, desligado) |

Os valores de `N_BELT` e `PITCH` foram medidos no nível 26. Num nível com outras passadeiras, mede-os primeiro
com `tools/belts.py` (ver [desenvolvimento.md](desenvolvimento.md#um-nível-novo-com-passadeiras)).
