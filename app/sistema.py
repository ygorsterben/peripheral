"""Integração com o Windows: instância única, iniciar com o Windows e arquivo de registro.

Tudo no escopo do usuário (sem administrador): HKCU para o "iniciar com o Windows" e %APPDATA% para o registro.
"""
import ctypes
import ctypes.wintypes as w
import sys
import threading
import time
import winreg
from pathlib import Path

from .servico import PASTA_DADOS

NOME_MUTEX = "Local\\GerenciadorPerifericos.instancia"
NOME_EVENTO = "Local\\GerenciadorPerifericos.mostrar"
CHAVE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALOR_RUN = "GerenciadorPerifericos"
ARQUIVO_REGISTRO = PASTA_DADOS / "registro.txt"

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateMutexW.restype = w.HANDLE
_k32.CreateEventW.restype = w.HANDLE
_k32.OpenEventW.restype = w.HANDLE
ERRO_JA_EXISTE = 183
EVENTO_MODIFICAR = 0x0002


def registrar(texto):
    """Anota no %APPDATA%\\GerenciadorPerifericos\\registro.txt (o .exe não tem console)."""
    linha = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {texto}"
    if sys.stdout:
        print(linha, flush=True)
    try:
        PASTA_DADOS.mkdir(parents=True, exist_ok=True)
        if ARQUIVO_REGISTRO.exists() and ARQUIVO_REGISTRO.stat().st_size > 512_000:
            ARQUIVO_REGISTRO.replace(ARQUIVO_REGISTRO.with_suffix(".old.txt"))
        with ARQUIVO_REGISTRO.open("a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except OSError:
        pass


def instancia_unica(ao_pedir_janela):
    """True se esta é a primeira instância. Se já houver uma aberta, pede para ela mostrar a janela e devolve False.
    `ao_pedir_janela` é chamado (em outra thread) quando outra instância pedir para mostrar a janela."""
    _k32.CreateMutexW(None, False, NOME_MUTEX)
    if ctypes.get_last_error() == ERRO_JA_EXISTE:
        evento = _k32.OpenEventW(EVENTO_MODIFICAR, False, NOME_EVENTO)
        if evento:
            _k32.SetEvent(evento)
            _k32.CloseHandle(evento)
        return False
    evento = _k32.CreateEventW(None, False, False, NOME_EVENTO)

    def esperar():
        while True:
            if _k32.WaitForSingleObject(evento, 0xFFFFFFFF) == 0:
                ao_pedir_janela()

    threading.Thread(target=esperar, name="instancia", daemon=True).start()
    return True


def comando_inicio():
    """Linha de comando para iniciar com o Windows (minimizado na bandeja)."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --bandeja'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    raiz = Path(__file__).resolve().parent.parent
    return f'"{pythonw}" "{raiz / "iniciar.py"}" --bandeja'


def inicia_com_windows():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_RUN) as k:
            winreg.QueryValueEx(k, VALOR_RUN)
            return True
    except OSError:
        return False


def definir_inicio_com_windows(ligar):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_RUN, 0, winreg.KEY_SET_VALUE) as k:
        if ligar:
            winreg.SetValueEx(k, VALOR_RUN, 0, winreg.REG_SZ, comando_inicio())
        else:
            try:
                winreg.DeleteValue(k, VALOR_RUN)
            except FileNotFoundError:
                pass


# ---------- barra de tarefas, ícone e atalho ----------
ID_APP = "Peripheral.GerenciadorPerifericos"  # identidade própria na barra de tarefas (não agrupa com o Python)
ARQUIVO_ICONE = PASTA_DADOS / "icone.ico"


def definir_identidade():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(ID_APP)
    except (AttributeError, OSError):
        pass


def gerar_icone(imagem):
    """Grava o ícone (PIL.Image) em %APPDATA% como .ico, para a janela/barra de tarefas e o atalho."""
    try:
        PASTA_DADOS.mkdir(parents=True, exist_ok=True)
        imagem.save(ARQUIVO_ICONE, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        return str(ARQUIVO_ICONE)
    except OSError:
        return None


def pasta_area_de_trabalho():
    """A área de trabalho de verdade (pode estar no OneDrive), pelo Windows (SHGetKnownFolderPath)."""
    class GUID(ctypes.Structure):
        _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]
    desktop = GUID(0xB4BFCC3A, 0xDB2C, 0x424C, (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41))
    caminho = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(desktop), 0, None, ctypes.byref(caminho)) != 0:
        return Path.home() / "Desktop"
    try:
        return Path(caminho.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(caminho)


def criar_atalho_area_de_trabalho(nome="Gerenciador de Periféricos"):
    """Cria (ou atualiza) o atalho na área de trabalho apontando para o app que está rodando. True se deu certo."""
    import subprocess
    destino = pasta_area_de_trabalho() / f"{nome}.lnk"
    if getattr(sys, "frozen", False):
        alvo, args, icone, pasta = sys.executable, "", f"{sys.executable},0", str(Path(sys.executable).parent)
    else:
        raiz = Path(__file__).resolve().parent.parent
        alvo, args = str(Path(sys.executable).with_name("pythonw.exe")), f'"{raiz / "iniciar.py"}"'
        icone, pasta = str(ARQUIVO_ICONE), str(raiz)
    aspas = lambda s: s.replace("'", "''")  # noqa: E731  (texto entre aspas simples do PowerShell)
    script = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{aspas(str(destino))}');"
              f"$s.TargetPath='{aspas(alvo)}';$s.Arguments='{aspas(args)}';$s.WorkingDirectory='{aspas(pasta)}';"
              f"$s.IconLocation='{aspas(icone)}';$s.Description='Configura o mouse e o teclado';$s.Save()")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                       capture_output=True, creationflags=0x08000000)  # sem janela de console
    return r.returncode == 0 and destino.exists()


def primeira_vez(prefs, salvar):
    """Padrões da primeira execução: iniciar com o Windows (na bandeja) ligado; no .exe, atalho na área de trabalho.
    Cada um só uma vez (se o usuário desligar ou apagar o atalho, o app respeita). No .exe, mantém o "iniciar com o
    Windows" apontando para o .exe que está rodando (se ele foi movido de pasta)."""
    if not prefs.get("inicio_padrao_feito"):
        definir_inicio_com_windows(True)
        salvar("inicio_padrao_feito", True)
    elif getattr(sys, "frozen", False) and inicia_com_windows():
        definir_inicio_com_windows(True)
    if getattr(sys, "frozen", False) and not prefs.get("atalho_feito"):
        if criar_atalho_area_de_trabalho():
            salvar("atalho_feito", True)
