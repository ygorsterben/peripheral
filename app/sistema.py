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
