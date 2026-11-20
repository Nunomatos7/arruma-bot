"""Prepara o WebDriverAgent (Appium) para o teu iPhone. Só macOS, precisa do Xcode.

    python -m tools.setup_wda --team ABCDE12345 --bundle-prefix com.oteunome.arrumabot

1. descarrega o WebDriverAgent (versão testada, ver WDA_VERSION) para vendor/WebDriverAgent;
2. troca o identificador das apps (com.facebook.WebDriverAgent...) por um teu: a Apple não deixa
   duas contas assinarem o mesmo identificador;
3. põe a tua equipa de programador (Team ID) nos alvos que vão para o iPhone.

O Team ID vê-se no Xcode (Settings > Accounts > a tua conta > Team) ou em
https://developer.apple.com/account (Membership). Com uma conta Apple grátis aparece como
"O teu nome (Personal Team)". Ver docs/instalar-mac-iphone.md.
"""
from __future__ import annotations

import argparse
import io
import re
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "vendor" / "WebDriverAgent"
WDA_VERSION = "16.15.3"  # versão com que o bot foi testado (novembro de 2026)
TARGETS = ("WebDriverAgentLib", "WebDriverAgentRunner")


def download(version: str = WDA_VERSION, dest: Path = DEST) -> None:
    url = f"https://github.com/appium/WebDriverAgent/archive/refs/tags/v{version}.tar.gz"
    print(f"A descarregar {url} ...")
    data = urllib.request.urlopen(url, timeout=120).read()
    tmp = dest.parent / f"_wda_{version}"
    shutil.rmtree(tmp, ignore_errors=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        tf.extractall(tmp, filter="data")
    inner = next(tmp.iterdir())
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(inner), dest)
    shutil.rmtree(tmp, ignore_errors=True)


def patch_project(pbxproj: Path, team: str, prefix: str) -> int:
    """Muda os identificadores e a equipa nos blocos de configuração dos dois alvos. Devolve quantos blocos mudou."""
    text = pbxproj.read_text()
    for t in TARGETS:
        text = re.sub(rf"PRODUCT_BUNDLE_IDENTIFIER = [\w.\-]*\.{t};", f"PRODUCT_BUNDLE_IDENTIFIER = {prefix}.{t};", text)
    changed = 0

    def fix_block(m: re.Match) -> str:
        nonlocal changed
        block = m.group(0)
        if not any(f"PRODUCT_BUNDLE_IDENTIFIER = {prefix}.{t};" in block for t in TARGETS):
            return block
        changed += 1
        block = re.sub(r"\n\s*DEVELOPMENT_TEAM = [^;]*;", "", block)
        return re.sub(r"(\n(\s*)PRODUCT_BUNDLE_IDENTIFIER = )", rf"\n\2DEVELOPMENT_TEAM = {team};\1", block, count=1)

    text = re.sub(r"buildSettings = \{.*?\n\t\t\t\};", fix_block, text, flags=re.S)
    pbxproj.write_text(text)
    return changed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--team", required=True, help="Team ID da tua conta de programador Apple (10 caracteres)")
    ap.add_argument("--bundle-prefix", required=True, help="prefixo único para as apps, ex.: com.oteunome.arrumabot")
    ap.add_argument("--version", default=WDA_VERSION, help=f"versão do WebDriverAgent (testada: {WDA_VERSION})")
    ap.add_argument("--dest", default=str(DEST), help=argparse.SUPPRESS)
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Z0-9]{10}", a.team):
        sys.exit("O Team ID tem 10 letras maiúsculas/números (ex.: ABCDE12345).")
    if not re.fullmatch(r"[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+", a.bundle_prefix):
        sys.exit("O prefixo tem de ser do tipo com.oteunome.arrumabot (letras, números, hífens e pontos).")
    dest = Path(a.dest)
    if not dest.exists():
        download(a.version, dest)
    n = patch_project(dest / "WebDriverAgent.xcodeproj" / "project.pbxproj", a.team, a.bundle_prefix)
    print(f"Projeto preparado: {n} configurações com a equipa {a.team} e o prefixo {a.bundle_prefix}.")
    print("Próximo passo: abrir o projeto no Xcode e correr o esquema WebDriverAgentRunner uma vez (⌘U),\n"
          "ou simplesmente: python -m bot.wda start   (ver docs/instalar-mac-iphone.md)")


if __name__ == "__main__":
    main()
