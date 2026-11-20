# Instalar no Mac com iPhone (caminho testado)

Foi assim que o bot passou os níveis 23 a 26. O Mac fala com o iPhone através do
[WebDriverAgent](https://github.com/appium/WebDriverAgent) (WDA), um "teste de interface" da Apple que corre no
iPhone e expõe uma API HTTP: o bot vê o ecrã por um stream de vídeo (MJPEG) e toca com gestos sintetizados pelo
próprio iOS. Não é preciso jailbreak nem nenhuma app de terceiros na App Store.

> Porquê não a "Replicação do iPhone" do macOS? Não está disponível na União Europeia. Fora da UE pode usar-se
> (`--mirror`), mas esse caminho não foi testado. Ver [README](../README.md#compatibilidade).

**Tempo estimado:** 30–60 minutos na primeira vez (a maior parte é descarregar o Xcode).

## O que é preciso

| | Versão testada | Mínimo provável |
|---|---|---|
| Mac | macOS 27.2 (Apple Silicon) | macOS que corra um Xcode compatível com o teu iOS |
| Xcode | 26.6 | o que suporte a versão de iOS do iPhone |
| iPhone | iPhone 16, iOS 26 | iOS 16 ou mais recente (tem o "Modo de programador") |
| Python | 3.14 | 3.11 |
| Conta Apple | conta grátis (Personal Team) | qualquer conta Apple |
| Cabo | USB-C | qualquer cabo de dados (só é obrigatório na 1.ª vez) |

A conta grátis funciona, mas a assinatura das apps de programador **expira ao fim de 7 dias**: depois disso é
preciso recompilar o WDA (ver [Uma semana depois](#uma-semana-depois)). Com uma conta paga dura um ano.

## 1. Instalar o Xcode

1. Instala o **Xcode** a partir da App Store (são ~10 GB).
2. Abre-o uma vez, aceita a licença e deixa-o instalar os componentes que pedir.
3. Em **Xcode › Settings › Components** (ou *Platforms*), instala a plataforma **iOS** se não estiver instalada.
4. No Terminal, confirma que a linha de comandos aponta para o Xcode:

   ```bash
   xcode-select -p
   ```

   Deve mostrar `/Applications/Xcode.app/Contents/Developer`. Se mostrar `CommandLineTools`, corre
   `sudo xcode-select -s /Applications/Xcode.app` (pede a tua palavra-passe).

## 2. Entrar com a conta Apple no Xcode

1. **Xcode › Settings › Accounts › +** › *Apple ID*, e entra com a tua conta.
2. Fica criada uma equipa com o teu nome e "(Personal Team)".
3. Descobre o **Team ID** (10 letras/números, ex.: `ABCDE12345`). A forma mais simples é no Terminal:

   ```bash
   defaults read com.apple.dt.Xcode IDEProvisioningTeamByIdentifier
   ```

   Procura `teamID = ...` na equipa que diz `isFreeProvisioningTeam = 1` (conta grátis) ou na tua equipa paga.
   Também aparece em <https://developer.apple.com/account> (*Membership details*), se tiveres conta paga.

> Se tiveres várias equipas (ex.: a da empresa), usa a tua pessoal. Com a equipa errada a compilação falha com
> "login details rejected" ou "No profiles for ... were found".

## 3. Preparar o iPhone

1. Liga o iPhone ao Mac por cabo, desbloqueia-o e toca em **Confiar** neste computador.
2. Ativa o **Modo de programador**: *Definições › Privacidade e segurança › Modo de programador* › ligar.
   O iPhone reinicia e pede confirmação. (Esta opção só aparece depois de o iPhone ter sido ligado a um Mac com Xcode.)
3. Confirma que o Mac o vê:

   ```bash
   xcrun devicectl list devices
   ```

   O iPhone deve aparecer como `available (paired)` ou `connected`.

## 4. Descarregar o bot

```bash
git clone https://github.com/Nunomatos7/arruma-bot.git
cd arruma-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Se `python3 --version` for anterior a 3.11, instala um Python recente (`brew install python` ou o instalador de
<https://www.python.org/downloads/>).

## 5. Preparar o WebDriverAgent

```bash
.venv/bin/python -m tools.setup_wda --team ABCDE12345 --bundle-prefix com.oteunome.arrumabot
```

- `--team`: o Team ID do passo 2.
- `--bundle-prefix`: um prefixo **só teu** (a Apple não deixa duas contas assinarem o mesmo identificador).
  Usa algo como `com.<o-teu-nome>.arrumabot`.

O script descarrega o WDA (versão 16.15.3, a testada) para `vendor/WebDriverAgent`, troca os identificadores das
duas apps (`WebDriverAgentLib` e `WebDriverAgentRunner`) e põe a tua equipa nas configurações de assinatura.

## 6. Arrancar o WebDriverAgent no iPhone

```bash
.venv/bin/python -m bot.wda start ABCDE12345
```

Na primeira vez compila o WDA (1–3 minutos) e instala no iPhone uma app chamada **WebDriverAgentRunner**.

**A primeira vez falha quase sempre** com um erro de confiança. É normal:

1. No iPhone: *Definições › Geral › VPN e gestão de dispositivos* › o teu e-mail/equipa em *App de programador*
   › **Confiar**.
2. Corre outra vez `.venv/bin/python -m bot.wda start ABCDE12345`.

Quando arrancar, aparece:

```
WebDriverAgent a correr em http://192.168.1.50:8100 (pid 12345). Log: vendor/wda-run.log
```

O URL fica guardado em `vendor/wda-url.txt` e o bot usa-o sozinho. Para testar:

```bash
.venv/bin/python -m bot.wda shot
```

Guarda um screenshot do iPhone em `shots/`. Se demorar menos de 1 s e a imagem estiver certa, está tudo pronto.

### Se a compilação pela linha de comandos falhar

Às vezes o Xcode precisa de criar o perfil de assinatura pela interface gráfica (sobretudo com contas novas):

1. `open vendor/WebDriverAgent/WebDriverAgent.xcodeproj`
2. No topo, escolhe o esquema **WebDriverAgentRunner** e o teu iPhone como destino.
3. No painel da esquerda, projeto *WebDriverAgent* › alvo **WebDriverAgentRunner** › *Signing & Capabilities*:
   confirma *Automatically manage signing* e a tua equipa. Faz o mesmo no alvo **WebDriverAgentLib**.
4. **Product › Test** (⌘U). Quando aparecer `ServerURLHere->http://...` na consola, pára (⌘.).
5. Volta ao Terminal e corre `.venv/bin/python -m bot.wda start ABCDE12345`.

Mais erros e soluções em [problemas.md](problemas.md#webdriveragent-e-xcode).

### Por cabo ou por Wi-Fi

Depois de emparelhado, o Xcode também fala com o iPhone por Wi-Fi (mesma rede que o Mac). O stream e os toques vão
sempre por Wi-Fi (o URL é o IP do iPhone). Funcionou bem assim nos testes. Se a rede for instável, liga o cabo.

## 7. Jogar

1. No iPhone, abre a app **Continente** › *Jogos da Poupança* › **Arrum'A Loja** e entra no nível (carrega em
   *Jogar*). O bot precisa de ver as 12 prateleiras.
2. Lê no topo do jogo o número de jogadas (ex.: `0/290`) e o tempo (ex.: `07:39`).
3. No Mac:

   ```bash
   .venv/bin/python -m bot.run --wda --auto --max-moves 290 --time-limit 459
   ```

   - `--max-moves`: as jogadas do nível;
   - `--time-limit`: o tempo do nível em segundos (7:39 = 459). Só é usado nos níveis com passadeiras, para gerir as
     esperas;
   - sem `--auto` fica em **modo assistente**: abre uma janela com setas e tu jogas no telemóvel;
   - `--no-window` não abre a janela (útil com `--auto`).

4. **Não toques no iPhone** enquanto o bot joga: ele não sabe das tuas jogadas e pode baralhar-se.
5. O bot para sozinho quando o nível acaba ("Não vejo o tabuleiro há 8 s"). Se quiseres parar antes: `Ctrl+C`.

O bot deteta sozinho se o nível tem passadeiras e muda de modo. Cada jogo fica registado em `runs/<data-hora>/`:
uma imagem por leitura com o que a visão leu e as jogadas planeadas, `log.txt` e (passadeiras) `taps.txt`.
Ver [desenvolvimento.md](desenvolvimento.md#registos-de-cada-jogo).

## 8. No fim

```bash
.venv/bin/python -m bot.wda stop
```

O iPhone fica livre. A app *WebDriverAgentRunner* pode ficar instalada (não faz nada sozinha) ou ser apagada como
outra app qualquer.

## Uma semana depois

Com conta grátis, ao fim de 7 dias o iPhone deixa de abrir o WDA (erro de perfil expirado). Recompila:

```bash
rm -rf vendor/wda-build
.venv/bin/python -m bot.wda start ABCDE12345
```

## Resumo dos comandos

```bash
.venv/bin/python -m tools.setup_wda --team ABCDE12345 --bundle-prefix com.oteunome.arrumabot   # uma vez
.venv/bin/python -m bot.wda start ABCDE12345     # cada sessão
.venv/bin/python -m bot.wda shot                 # testar
.venv/bin/python -m bot.run --wda --auto --max-moves 290 --time-limit 459
.venv/bin/python -m bot.wda stop                 # no fim
```
