"""Gera dist/GerenciadorPerifericos.exe (um arquivo só, sem console) com o PyInstaller.

Uso:  py construir.py            (precisa de: py -m pip install -r requirements-dev.txt)
"""
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from app import NOME, VERSAO  # noqa: E402
from app.__main__ import imagem_icone  # noqa: E402

BUILD = RAIZ / "build"
ICONE = BUILD / "icone.ico"
VERSAO_TXT = BUILD / "versao.txt"


def gerar_icone():
    BUILD.mkdir(exist_ok=True)
    imagem_icone(256).save(ICONE, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def gerar_versao():
    """Informações que aparecem em Propriedades > Detalhes do .exe."""
    n = [int("".join(c for c in p if c.isdigit()) or 0) for p in VERSAO.replace("b", ".").split(".")][:4]
    n += [0] * (4 - len(n))
    VERSAO_TXT.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={tuple(n)}, prodvers={tuple(n)}),
  kids=[StringFileInfo([StringTable('041604b0', [
    StringStruct('ProductName', '{NOME}'),
    StringStruct('FileDescription', '{NOME}'),
    StringStruct('ProductVersion', '{VERSAO} (build beta 1.0)'),
    StringStruct('FileVersion', '{VERSAO}'),
    StringStruct('OriginalFilename', 'GerenciadorPerifericos.exe')])]),
    VarFileInfo([VarStruct('Translation', [0x0416, 1200])])]
)""", encoding="utf-8")


def main():
    gerar_icone()
    gerar_versao()
    sep = ";"  # separador do --add-data no Windows
    comando = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "GerenciadorPerifericos", "--icon", str(ICONE), "--version-file", str(VERSAO_TXT),
        "--add-data", f"{RAIZ / 'app' / 'ui'}{sep}app/ui",
        "--add-data", f"{RAIZ / 'perifericos' / 'dados'}{sep}perifericos/dados",
        "--hidden-import", "pystray._win32",
        "--collect-data", "soundcard",  # os .h que o soundcard carrega com cffi (efeito Música)
        "--distpath", str(RAIZ / "dist"), "--workpath", str(BUILD / "pyinstaller"), "--specpath", str(BUILD),
        str(RAIZ / "iniciar.py"),
    ]
    subprocess.run(comando, check=True)
    exe = RAIZ / "dist" / "GerenciadorPerifericos.exe"
    print(f"\nPronto: {exe} ({exe.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    if not shutil.which("pyinstaller") and subprocess.run([sys.executable, "-m", "PyInstaller", "--version"],
                                                          capture_output=True).returncode:
        sys.exit("PyInstaller não instalado: py -m pip install -r requirements-dev.txt")
    main()
