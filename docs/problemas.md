# Problemas e soluções

Organizado por sintoma. Muitos destes aconteceram mesmo durante o desenvolvimento.

- [Instalação do Python](#instalação-do-python)
- [WebDriverAgent e Xcode](#webdriveragent-e-xcode)
- [Android e adb](#android-e-adb)
- [Visão](#visão)
- [Durante o jogo](#durante-o-jogo)
- [Power-ups](#power-ups)
- [Passadeiras](#passadeiras)

## Instalação do Python

**`pip install` falha no `pyobjc-framework-Quartz` (Windows/Linux).** Esse pacote só é necessário no macOS; o
`requirements.txt` já o limita ao macOS. Se usas uma cópia antiga, apaga essa linha.

**`ModuleNotFoundError: No module named 'bot'`.** Corre os comandos a partir da pasta do projeto (a que tem o
`README.md`) e com `python -m bot.run ...`, não `python bot/run.py`.

**Windows: `python` abre a Microsoft Store.** Instala o Python do python.org (com "Add to PATH") ou usa `py`.

## WebDriverAgent e Xcode

**`Não encontrei nenhum iPhone ligado`.** Liga o cabo, desbloqueia o iPhone, aceita "Confiar" e confirma com
`xcrun devicectl list devices`. Se usas Wi-Fi, o iPhone tem de ter sido emparelhado por cabo antes e estar na
mesma rede.

**`Falta o WebDriverAgent em vendor/`.** Corre `python -m tools.setup_wda --team ... --bundle-prefix ...`.

**A compilação falha com `No profiles for '...WebDriverAgentRunner' were found` ou `Signing requires a development
team`.**
- O Team ID está errado ou não é de uma conta com sessão iniciada no Xcode (*Settings › Accounts*).
- Faz a primeira compilação pela interface do Xcode (ver
  [instalar-mac-iphone.md](instalar-mac-iphone.md#se-a-compilação-pela-linha-de-comandos-falhar)).

**`login details rejected` / `Your session has expired`.** Volta a entrar na conta em *Xcode › Settings ›
Accounts*. Com várias equipas, confirma que usas a pessoal.

**`Failed to register bundle identifier` / `The app identifier cannot be registered to your development team`.**
O prefixo já está em uso por outra conta. Escolhe outro `--bundle-prefix` (ex.: junta o teu nome e um número) e
corre outra vez o `setup_wda` e `rm -rf vendor/wda-build`.

**O WDA instala mas não abre: `Untrusted Developer` / `invalid code signature`.** No iPhone: *Definições › Geral ›
VPN e gestão de dispositivos* › a tua conta › **Confiar**. Depois `python -m bot.wda start` outra vez.

**`Developer Mode disabled`.** *Definições › Privacidade e segurança › Modo de programador* › ligar e reiniciar.

**Funcionava e passados dias deixou de funcionar.** Com conta grátis a assinatura dura 7 dias:
`rm -rf vendor/wda-build` e `python -m bot.wda start TEAM_ID`.

**`O WDA não arrancou em 240 s`.** Vê o fim de `vendor/wda-run.log`. Causas comuns: iPhone bloqueado (desbloqueia
e deixa-o assim), outro processo do Xcode a usar o iPhone (fecha o Xcode), versão do iOS mais recente do que o
Xcode suporta (atualiza o Xcode).

**`python -m bot.wda shot` dá `Connection refused` ou demora.** O WDA não está a correr ou o IP mudou (o iPhone
mudou de rede): `python -m bot.wda start` outra vez. Se o Mac e o iPhone estão em redes diferentes (ex.: rede de
convidados com isolamento), liga ambos à mesma rede.

**Os toques não fazem nada (o bot joga mas nada mexe).** O jogo só aceita **toques**, não arrastos: usa sempre
`bot.run`, que toca. Se mesmo assim nada acontece, confirma que nenhuma janela/pop-up do jogo está por cima e que o
iPhone não está em modo de baixo consumo agressivo.

## Android e adb

**`adb devices` não mostra nada.**
- Cabo só de carga: experimenta outro.
- Windows: pode faltar o driver USB do fabricante (Samsung, Xiaomi, ...) ou o "Google USB Driver".
- Muda o modo USB do telemóvel para "Transferência de ficheiros".

**Aparece `unauthorized`.** Desbloqueia o telemóvel e aceita "Permitir depuração USB". Se o pedido não aparecer:
*Opções de programador › Revogar autorizações de depuração USB*, desliga e volta a ligar o cabo.

**Xiaomi/Redmi/POCO: os toques são ignorados (`INJECT_EVENTS permission`).** Ativa *Depuração USB (Definições de
segurança)* nas opções de programador (pode pedir sessão na conta Mi).

**`Há vários telemóveis ligados`.** Escolhe um: `--android SERIAL` (o serial vem de `adb devices`).

**Screenshots muito lentos (> 1 s).** Usa cabo (não Wi-Fi) e uma porta USB 3. Ecrãs de resolução muito alta
transferem mais dados; não há forma de baixar a resolução do screencap sem root.

## Visão

**`Encontrei N prateleiras (esperava 12)`.**
- Ainda não estás dentro do nível, ou há um pop-up por cima.
- Tema escuro forçado ("Forçar modo escuro" do Android) muda o branco das prateleiras: desliga-o para a app.
- Filtros de cor, luz noturna ou "conforto ocular" alteram as cores: desliga-os.

**O bot confunde produtos (setas sem sentido).** Corre `python -m tools.proto_sheet runs/<pasta-do-jogo> tipos.png`
e abre `tipos.png`: mostra os tipos aprendidos. Dois tipos com o mesmo produto = produto partido (o bot não vê os
pares); um tipo com produtos diferentes = produtos misturados. Ver os limiares em
[como-funciona.md](como-funciona.md#tipos-aprendidos-não-rotulados-botvisionpy-catalog).

## Durante o jogo

**`As jogadas não estão a ter efeito. A parar.`** 4 leituras seguidas iguais depois de jogar: os toques não estão a
chegar ao jogo (ver as secções acima) ou há um pop-up. O bot para de propósito para não gastar jogadas.

**`Não vejo o tabuleiro há 8 s`.** Normal no fim do nível (aparece o resultado). A meio, é um pop-up: fecha-o e volta
a correr o bot (ele recomeça a partir do estado atual).

**O bot anda com o mesmo produto para trás e para a frente.** Era um problema das primeiras versões (prateleiras
esgotadas). Se voltar a acontecer, guarda a pasta `runs/<data-hora>` e vê o `log.txt`.

**Tocaste no telemóvel a meio.** O bot não sabe das tuas jogadas; nos níveis normais recupera na leitura seguinte,
nas passadeiras a memória das prateleiras fica errada até elas voltarem a passar.

## Power-ups

O bot procura os três botões vermelhos redondos no quarto de baixo do ecrã (martelo, relógio, baralhar). Se não os
encontrar (ex.: outro tema ou disposição), usa as posições do iPhone. Para verificar:

```bash
python -c "import cv2; from bot.powerups import find_powerups; print(find_powerups(cv2.imread('shots/o-teu-screenshot.png')))"
```

Deve mostrar 3 posições (x, y). Se não, o bot simplesmente não usa os power-ups com fiabilidade.

## Passadeiras

**Toques nas passadeiras falham (mas nas prateleiras paradas funcionam).** O atraso entre o frame e o toque não
está certo para o teu equipamento: ajusta `--lat` (e no Android `--tap-overhead`). Ver
[instalar-android.md](instalar-android.md#passadeiras-no-android). O ficheiro `runs/<data-hora>/taps.txt` mostra as
posições previstas.

**`memória != leitura` muitas vezes no `log.txt`.** A memória das passadeiras não está a bater certo. Se o nível tiver
um número de prateleiras por passadeira diferente de 6, ajusta `N_BELT` (mede-o com `tools/belts.py`).

**O bot espera muito.** É de propósito quando há folga de tempo (esperar não gasta jogadas). Se o tempo do nível não
é 7:39, passa o certo em `--time-limit` (em segundos), senão as contas da folga ficam erradas.
