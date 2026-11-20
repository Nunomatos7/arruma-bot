# Instalar com Android (Windows, macOS ou Linux)

> **Estado: experimental.** O bot foi desenvolvido e testado num iPhone. A ponte Android
> ([bot/android.py](../bot/android.py)) segue a documentação oficial do `adb` e foi testada contra um `adb`
> simulado (screenshots no formato do Android e comandos de toque), mas **nunca num telemóvel Android real**.
> Os níveis normais devem funcionar. Nos níveis com passadeiras os atrasos têm de ser calibrados (ver
> [Passadeiras no Android](#passadeiras-no-android)). Se o experimentares, diz como correu!

O computador fala com o telemóvel pelo **adb** (Android Debug Bridge), a ferramenta oficial da Google:
- o bot vê o ecrã com `adb exec-out screencap` (imagem crua, sem compressão PNG, para ser mais rápido);
- toca com `adb shell input tap x y`, juntando as jogadas de uma sequência num só comando.

Não é preciso root nem instalar nada no telemóvel.

## O que é preciso

| | Notas |
|---|---|
| Computador | Windows 10/11, macOS ou Linux |
| Python | 3.11 ou mais recente (testado com 3.14) |
| Android | 8 ou mais recente; 11+ se quiseres ligar por Wi-Fi |
| Cabo USB | de dados (alguns cabos só carregam) |
| Android SDK Platform-Tools | traz o `adb` |

## 1. Instalar o Python

**Windows:** descarrega de <https://www.python.org/downloads/> e, no instalador, marca **"Add python.exe to PATH"**.
Ou, no PowerShell:

```powershell
winget install Python.Python.3.12
```

**macOS:** `brew install python` (ou o instalador do python.org).

**Linux (Debian/Ubuntu):** `sudo apt install python3 python3-venv python3-pip`

Confirma numa janela nova do terminal: `python --version` (Windows) ou `python3 --version`.

## 2. Instalar o adb (Platform-Tools)

**Windows**, uma de duas:
- `winget install Google.PlatformTools`, ou
- descarrega o zip de <https://developer.android.com/tools/releases/platform-tools>, extrai para
  `C:\platform-tools` e junta essa pasta ao PATH (*Definições › Sistema › Acerca de › Definições avançadas do
  sistema › Variáveis de ambiente › Path › Editar › Novo*).

**macOS:** `brew install android-platform-tools`

**Linux:** `sudo apt install adb` (ou o zip do link acima).

Confirma: `adb version`.

> Se não quiseres mexer no PATH, podes indicar o caminho ao bot: `--adb C:\platform-tools\adb.exe`.

## 3. Preparar o telemóvel

1. **Ativar as opções de programador:** *Definições › Acerca do telefone* › tocar **7 vezes** em *Número de
   compilação* (em alguns modelos está em *Informações do software*).
2. **Ativar a depuração USB:** *Definições › Sistema › Opções de programador › Depuração USB*.
   Recomendado nas mesmas opções:
   - **Manter ativo** (o ecrã não se desliga enquanto carrega);
   - desligar a rotação automática do ecrã.
   Em telemóveis Xiaomi/Redmi/POCO ativa também **Depuração USB (Definições de segurança)**, senão os toques
   não funcionam.
3. Liga o cabo e aceita o pedido **"Permitir depuração USB?"** no telemóvel (marca "Permitir sempre").
4. Confirma no computador:

   ```bash
   adb devices
   ```

   Tem de aparecer o telemóvel com o estado `device`. Se aparecer `unauthorized`, desbloqueia o telemóvel e aceita
   o pedido; se não aparecer nada, ver [problemas.md](problemas.md#android-e-adb).

### Opcional: sem cabo (Android 11+)

*Opções de programador › Depuração sem fios* › *Sincronizar dispositivo com código de sincronização*, e no
computador (mesma rede Wi-Fi):

```bash
adb pair 192.168.1.50:37123        # IP:porta e código que o telemóvel mostra
adb connect 192.168.1.50:41234     # IP:porta do ecrã "Depuração sem fios"
```

Por Wi-Fi os screenshots ficam mais lentos. Para os níveis com passadeiras usa o cabo.

## 4. Descarregar o bot

**Windows (PowerShell):**

```powershell
git clone https://github.com/Nunomatos7/arruma-bot.git
cd arruma-bot
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Se o PowerShell recusar ativar o ambiente ("execution of scripts is disabled"), corre uma vez
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, ou usa diretamente `.venv\Scripts\python.exe` em vez de
`python`. Sem git: no GitHub, *Code › Download ZIP*.

**macOS / Linux:**

```bash
git clone https://github.com/Nunomatos7/arruma-bot.git
cd arruma-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Daqui para a frente os comandos são iguais em todos os sistemas (com o ambiente ativado).

## 5. Verificar que o bot vê o jogo

1. No telemóvel, abre a app **Continente** › *Jogos da Poupança* › **Arrum'A Loja** e entra num nível.
2. No computador:

   ```bash
   python -m bot.android shot
   ```

   Guarda um screenshot em `shots/` e diz quanto demorou. Abaixo de ~1 s é bom.
3. Analisa esse screenshot:

   ```bash
   python -m bot.run --image shots/android-123456.png
   ```

   Deve listar as 12 prateleiras e guardar `..._plano.png` com setas. Se disser "Encontrei N prateleiras
   (esperava 12)", ver [problemas.md](problemas.md#visão).

## 6. Jogar

Começa pelo **modo assistente** (o bot mostra as setas numa janela e tu jogas):

```bash
python -m bot.run --android
```

Se as setas fizerem sentido, passa ao automático:

```bash
python -m bot.run --android --auto --max-moves 245
```

- `--max-moves`: as jogadas do nível (aparecem no topo do jogo, ex.: `0/245`);
- `--time-limit`: o tempo do nível em segundos, só para níveis com passadeiras;
- com vários telemóveis ligados: `--android SERIAL` (o serial vem de `adb devices`).

Não toques no telemóvel enquanto o bot joga. Para parar: `Ctrl+C`. O bot também para sozinho se 4 leituras
seguidas mostrarem que as jogadas não tiveram efeito (por exemplo, toques fora do sítio).

### Se os toques não acertarem

O `adb` toca em píxeis do ecrã físico, os mesmos do screenshot, por isso não deve haver desvio. Se houver:
- desliga o zoom do ecrã / "Tamanho de apresentação" fora do normal;
- desliga modos de uma mão / ecrã reduzido;
- confirma que o screenshot (`python -m bot.android shot`) tem a mesma orientação que o telemóvel.

## Passadeiras no Android

Nos níveis com passadeiras (como o 26) as prateleiras andam ~120 px/s, por isso o bot toca onde a prateleira **vai
estar**. Para isso precisa de saber dois atrasos, que dependem do telemóvel:

| Opção | O que é | Valor por omissão no Android | No iPhone (WDA) |
|---|---|---|---|
| `--lat` | segundos entre o screenshot e o 1.º toque | 0.6 | 0.32 |
| `--tap-overhead` | segundos a mais por cada `input tap` de uma sequência | 0.3 | 0 |

Cada `input tap` arranca um pequeno processo Java no telemóvel, o que custa 0,2 a 0,5 s conforme o modelo.

**Como calibrar:**
1. Joga um nível com passadeiras com `--auto` e olha para os toques nas passadeiras (podes gravar o ecrã do
   telemóvel e ver em câmara lenta).
2. Se o toque cai **atrás** do produto (do lado de onde a passadeira vem), aumenta `--lat`; se cai **à frente**,
   diminui.
3. Se só a 2.ª, 3.ª… jogada de cada sequência falha, ajusta `--tap-overhead` da mesma forma.

```bash
python -m bot.run --android --auto --max-moves 290 --time-limit 459 --lat 0.7 --tap-overhead 0.35
```

O ficheiro `runs/<data-hora>/taps.txt` regista, para cada toque, a posição prevista e quanto tempo passou desde o
frame: ajuda a perceber o padrão das falhas.

## Limitações conhecidas no Android

- Screenshots mais lentos (0,1–1 s) do que o stream do iPhone (~15 fps). Nos níveis normais só torna o bot mais
  lento a ler; nas passadeiras torna as previsões menos precisas.
- Os botões dos power-ups são procurados na imagem (círculos vermelhos em baixo). Se o teu ecrã tiver outra
  disposição e não os encontrar, o bot usa as posições do iPhone (que podem falhar). Ver
  [problemas.md](problemas.md#power-ups).
- Nunca testado num telemóvel real (ver o aviso no topo).
