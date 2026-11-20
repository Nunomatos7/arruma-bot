# Desenvolvimento

Ferramentas para testar e melhorar o bot **sem telemóvel**, e como adaptá-lo a níveis ou dispositivos novos.

## Estrutura do projeto

```
bot/
  run.py          linha de comandos e ciclo ao vivo dos níveis normais
  conveyor.py     modo passadeiras (nível 26)
  board.py        deteção das prateleiras
  vision.py       reconhecimento dos produtos (catálogo aprendido)
  solver.py       A* pelo próximo trio
  game.py         regras, estado observado (Obs) e simulador
  powerups.py     botões do martelo / relógio / baralhar
  device.py       interface comum às pontes
  wda.py          iPhone (WebDriverAgent)
  android.py      Android (adb)
  iphone.py       iPhone (Replicação do iPhone, macOS)
tools/
  setup_wda.py    prepara o WebDriverAgent para a tua conta Apple
  bench.py        benchmark do solver em níveis aleatórios
  bench_cmp.py    compara variantes do solver
  conveyor_sim.py simulador de níveis com passadeiras
  replay_conveyor.py  corre o modo passadeiras contra uma gravação
  belts.py        mede velocidade e volta das passadeiras numa gravação
  proto_sheet.py  desenha os tipos de produto aprendidos
  overlay.py      desenha o que a visão leu
  record_frames.py grava frames com o instante no nome (telemóvel ou vídeo)
  video_frames.py extrai só os frames parados de uma gravação de ecrã
  cluster_report.py   relatório de agrupamento de produtos (diagnóstico)
  demo.py         gera um GIF a partir de uma gravação
docs/             documentação e imagens
```

Pastas criadas ao usar (não vão para o git): `runs/` (registos de cada jogo), `shots/` (screenshots), `rec/`
(gravações), `vendor/` (WebDriverAgent e compilação).

## Registos de cada jogo

Cada execução de `bot.run` cria `runs/<data-hora>/`:

| Ficheiro | Conteúdo |
|---|---|
| `NNN.png` | o frame da leitura N com os tipos lidos (números verdes), silhuetas de trás (`b#`) e as jogadas planeadas (setas) |
| `raw_NNN.jpg` | o mesmo frame sem desenhos (para reproduzir a visão offline) |
| `log.txt` | uma linha por leitura: tempo, frente de cada prateleira, jogadas; nas passadeiras também a decisão (`agora`/`esperar`/`cavar`), o custo, a folga, a velocidade medida e o estado da memória |
| `taps.txt` | (passadeiras) cada toque: posição prevista, velocidade, tempo desde o frame, duração do pedido |
| `fim.png` | o ecrã quando o bot parou (normalmente o resultado do nível) |

Exemplos de análise feitos com estes registos durante o desenvolvimento:
- comparar o contador de jogadas do jogo (`raw_*.jpg`, topo do ecrã) com o do bot revela toques falhados;
- `tools/proto_sheet.py` sobre `raw_*.jpg` revelou produtos partidos em dois tipos;
- as linhas `memória != leitura` revelaram as animações de trio por cima das passadeiras.

## Testar sem telemóvel

**Analisar um screenshot:**

```bash
python -m bot.run --image runs/<pasta>/raw_050.jpg
```

**Benchmark do solver** (níveis aleatórios do tamanho do nível 23, com o simulador de `bot/game.py`):

```bash
python -m tools.bench 100
```

Resultado de referência: 100/100 resolvidos, ~2,02–2,14 jogadas por trio.

**Simulador de passadeiras** (6 prateleiras paradas + 2 passadeiras de 6, tempos medidos no nível 26):

```bash
python -c "from tools.conveyor_sim import main_decide; main_decide(5)"
```

Compara a política usada ao vivo (`bot.conveyor.decide`) com e sem plano global. Os níveis do simulador são mais
difíceis do que o real (servem para comparar estratégias, não para prever vitórias). Com 5 níveis há bastante ruído:
diferenças de ±10 trios podem ser sorte.

**Modo passadeiras contra uma gravação** (o tabuleiro não reage aos toques; testa visão, seguimento, memória e
decisões):

```bash
python -m tools.replay_conveyor rec/<pasta-com-frames> 290
```

Os frames têm de ter o instante no nome, `f0001_12.345.jpg`, como os gerados por `tools/record_frames.py`.

**Simular um telemóvel Android** sem o ter: cria um `adb` falso que responde a `devices`, devolve um screenshot no
formato cru (`struct.pack("<IIII", w, h, 1, 0) + RGBA`) e regista os `shell input tap`, e passa-o com `--adb`.
Foi assim que a ponte Android foi testada.

## Verificar a visão numa tentativa

```bash
python -m tools.proto_sheet runs/<pasta> tipos.png
```

Desenha cada tipo aprendido com o número de vezes que foi reconhecido. Num nível com N produtos devem aparecer
~N tipos frequentes; tipos raros (n < 10) costumam ser lixo de animações (círculos verdes, estrelas, ecrã final).

Antes de mudar `bot/vision.py`, compara o antes e o depois nos frames de vários níveis: cada tipo antigo deve
corresponder a um só tipo novo (senão partiste um produto) e cada tipo novo a produtos iguais (senão misturaste).

## Um nível novo com passadeiras

1. Grava ~25 s do nível em frames com o instante no nome:

   ```bash
   python -m tools.record_frames --wda 25 rec/nivel27        # iPhone (com o WDA a correr)
   python -m tools.record_frames --android 25 rec/nivel27    # Android
   python -m tools.record_frames --video gravacao.mp4 rec/nivel27   # ou a partir de uma gravação de ecrã
   ```
2. Mede as passadeiras:

   ```bash
   python -m tools.belts rec/<pasta>
   ```

   Dá a velocidade de cada passadeira, a volta e quantas prateleiras tem (`~6.00 prateleiras`). Ajusta as faixas
   `BANDS` no topo do ficheiro às linhas do teu nível.
3. Se for diferente de 6 prateleiras / 345 px, ajusta `N_BELT` e `PITCH` em `bot/conveyor.py`.
4. Testa com `tools/replay_conveyor.py` e confirma no `log.txt` que as linhas `memória != leitura` são raras.

## Uma ponte para outro dispositivo

Implementa a interface de [bot/device.py](../bot/device.py) (`screenshot`, `tap`, `move`, `chain`, `check_user`,
`stream.stamp`, `lat`, `tap_overhead`) e junta uma opção em `connect()` de [bot/run.py](../bot/run.py).
[bot/android.py](../bot/android.py) é o exemplo mais simples (~100 linhas).

Ideias para pontes mais rápidas no Android: `scrcpy` (stream de vídeo e controlo por socket) evitaria os
screenshots e o arranque de um processo Java por toque.

## História do desenvolvimento

O [README](../README.md#resultados) tem as tentativas de cada nível e o que cada falha ensinou. Em resumo:
- arrastos não funcionam, só toques;
- a memória de prateleiras esgotadas acabou com o vaivém do mesmo produto;
- um falso alarme de "jogada sem efeito" que atrasava os toques custou uma tentativa por tempo;
- no nível 26: textura (NCC) para embalagens parecidas, espera informada, produtos partidos em dois tipos (margem e
  corte do topo escuro), animações de trio e memória das passadeiras.
