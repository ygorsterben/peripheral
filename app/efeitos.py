"""Efeitos de luz feitos pelo app (cor ao vivo): o Carteiro pede um quadro por vez e manda ao teclado.

Cada efeito tem `quadro()` → 378 bytes (126 × R G B na ordem de INDICE_TECLA) e `parar()`. Só funcionam com o app
aberto; ao desligar, o Carteiro regrava o bloco de configuração e o teclado volta ao efeito gravado nele.
"""
import colorsys
import threading
import time
import warnings

from perifericos.teclado import INDICE_TECLA, QUADRO_AO_VIVO

# ---------- layout (o mesmo de desenharTeclado em app/ui/app.js): nome → (x do centro, fileira) ----------
_NAV, _NUM, LARGURA, FILEIRAS = 15.25, 16.5, 20.5, 6


def _layout():
    L = {}

    def put(n, x, r, w=1.0):
        L[n] = (x + w / 2, r)
    put("esc", 0, 0)
    for i, k in enumerate(["f1", "f2", "f3", "f4"]):
        put(k, 2 + i, 0)
    for i, k in enumerate(["f5", "f6", "f7", "f8"]):
        put(k, 6.5 + i, 0)
    for i, k in enumerate(["f9", "f10", "f11", "f12"]):
        put(k, 11 + i, 0)
    put("del", _NAV, 0); put("scroll", _NUM, 0); put("calc", _NUM + 1, 0)
    for i, k in enumerate(["`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "="]):
        put(k, i, 1)
    put("back", 13, 1, 2); put("home", _NAV, 1)
    for i, k in enumerate(["numlock", "num/", "num*", "num-"]):
        put(k, _NUM + i, 1)
    put("tab", 0, 2, 1.5)
    for i, k in enumerate(["q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "[", "]"]):
        put(k, 1.5 + i, 2)
    put("\\", 13.5, 2, 1.5); put("pgup", _NAV, 2)
    for i, k in enumerate(["num7", "num8", "num9"]):
        put(k, _NUM + i, 2)
    put("num+", _NUM + 3, 2)
    put("caps", 0, 3, 1.75)
    for i, k in enumerate(["a", "s", "d", "f", "g", "h", "j", "k", "l", ";", "'"]):
        put(k, 1.75 + i, 3)
    put("enter", 12.75, 3, 2.25); put("pgdn", _NAV, 3)
    for i, k in enumerate(["num4", "num5", "num6"]):
        put(k, _NUM + i, 3)
    put("shift", 0, 4, 2.25)
    for i, k in enumerate(["z", "x", "c", "v", "b", "n", "m", ",", ".", "/"]):
        put(k, 2.25 + i, 4)
    put("rshift", 12.25, 4, 1.75); put("up", 14.25, 4)
    for i, k in enumerate(["num1", "num2", "num3"]):
        put(k, _NUM + i, 4)
    put("numenter", _NUM + 3, 4)
    put("ctrl", 0, 5, 1.25); put("win", 1.25, 5, 1.25); put("alt", 2.5, 5, 1.25); put("space", 3.75, 5, 6.25)
    put("ralt", 10, 5); put("fn", 11, 5, 1.25)
    put("left", 13.25, 5); put("down", 14.25, 5); put("right", _NAV, 5); put("num0", _NUM, 5, 2); put("num.", _NUM + 2, 5)
    return L


LAYOUT = _layout()
# (índice da matriz, x do centro, fileira) das teclas que existem no desenho e na matriz de luz
TECLAS = [(INDICE_TECLA[n], x, r) for n, (x, r) in LAYOUT.items() if n in INDICE_TECLA and INDICE_TECLA[n] < 126]
NOME_DO_INDICE = {INDICE_TECLA[n]: n for n in LAYOUT if n in INDICE_TECLA}


def _rgb(h, s=1.0, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, max(0.0, min(1.0, v)))
    return bytes((round(r * 255), round(g * 255), round(b * 255)))


def _quantizar(c, passo=32):
    """Arredonda as cores: no receptor cada cor diferente custa um grupo a mais no pacote."""
    return bytes(min(255, round(v / passo) * passo) for v in c)


def teclas_acesas(quadro):
    """Quadro → {nome: "RRGGBB"} só das teclas acesas (para a prévia na tela)."""
    return {NOME_DO_INDICE[i]: quadro[3 * i:3 * i + 3].hex().upper()
            for i in NOME_DO_INDICE if i < 126 and any(quadro[3 * i:3 * i + 3])}


# ---------- som do PC ----------
class Ouvido(threading.Thread):
    """Ouve o que sai pelo alto-falante/fone padrão (loopback do Windows, sem microfone) e mantém o nível de
    BANDAS faixas de frequência (0..1, com ganho automático). Se o aparelho de som muda, reabre sozinho."""
    BANDAS = 20
    TAXA, BLOCO = 48000, 1024

    def __init__(self):
        super().__init__(name="ouvido", daemon=True)
        self.niveis = [0.0] * self.BANDAS
        self.grave = 0.0
        self.erro = None
        self._parar = threading.Event()
        self._teto = 1e-3

    def parar(self):
        self._parar.set()

    def run(self):
        try:
            import numpy as np
            import soundcard as sc
        except ImportError as e:  # .exe sem a biblioteca, por exemplo: a tela mostra o motivo
            self.erro = f"sem a biblioteca de áudio ({e.name})"
            return
        warnings.filterwarnings("ignore", module="soundcard")
        n = self.BLOCO * 2
        janela = np.hanning(n)
        freqs = np.fft.rfftfreq(n, 1 / self.TAXA)
        limites = np.geomspace(40, 16000, self.BANDAS + 1)
        faixas = [np.where((freqs >= a) & (freqs < b))[0] for a, b in zip(limites[:-1], limites[1:])]
        faixas = [f if len(f) else np.array([np.argmin(abs(freqs - a))]) for f, a in zip(faixas, limites[:-1])]
        buf = np.zeros(n)
        while not self._parar.is_set():
            try:
                saida = sc.default_speaker()
                mic = sc.get_microphone(id=str(saida.name), include_loopback=True)
                with mic.recorder(samplerate=self.TAXA, blocksize=self.BLOCO) as rec:
                    self.erro = None
                    conferido = time.monotonic()
                    while not self._parar.is_set():
                        if time.monotonic() - conferido > 1:
                            conferido = time.monotonic()
                            if str(sc.default_speaker().name) != str(saida.name):
                                break  # trocou o aparelho de som padrão: reabre
                        d = rec.record(numframes=self.BLOCO)
                        mono = d.mean(axis=1) if d.ndim > 1 else d
                        buf = np.concatenate([buf[len(mono):], mono])[-n:]
                        esp = np.abs(np.fft.rfft(buf * janela))
                        bruto = np.array([esp[f].mean() for f in faixas]) * np.linspace(1, 3, self.BANDAS)
                        self._teto = max(self._teto * 0.995, float(bruto.max()), 1e-3)  # ganho automático
                        alvo = np.clip(bruto / self._teto, 0, 1) ** 0.8
                        for i, v in enumerate(alvo):  # sobe rápido, desce devagar
                            self.niveis[i] = v if v > self.niveis[i] else self.niveis[i] * 0.82 + v * 0.18
                        self.grave = max(self.niveis[:4])
            except Exception as e:  # sem aparelho de som, driver ocupado…: tenta de novo daqui a pouco
                self.erro = str(e)
                self.niveis = [0.0] * self.BANDAS
                self._parar.wait(2)


class Musica:
    """Efeito Música. modo: "barras" (espectro em colunas) ou "pulso" (o teclado inteiro pulsa com o grave).
    sensibilidade 1..5; cor "RRGGBB" ou None = colorido."""
    MODOS = ("barras", "pulso")

    def __init__(self, modo="barras", sensibilidade=3, cor=None):
        self.ajustar(modo, sensibilidade, cor)
        self._ouvido = Ouvido()
        self._ouvido.start()
        self._t0 = time.monotonic()

    @classmethod
    def validar(cls, modo="barras", sensibilidade=3, cor=None):
        """Erro (ValueError) se alguma opção for inválida — antes de mexer no efeito que está rodando."""
        if modo not in cls.MODOS:
            raise ValueError(f"modo desconhecido: {modo}")
        if not 1 <= int(sensibilidade) <= 5:
            raise ValueError("sensibilidade de 1 a 5")
        if cor and len(bytes.fromhex(cor)) != 3:
            raise ValueError(f"cor inválida: {cor}")

    def ajustar(self, modo="barras", sensibilidade=3, cor=None):
        self.validar(modo, sensibilidade, cor)
        self.modo = modo
        self.ganho = 0.55 + 0.25 * int(sensibilidade)
        self.cor = bytes.fromhex(cor) if cor else None

    @property
    def erro(self):
        return self._ouvido.erro

    def parar(self):
        self._ouvido.parar()

    def quadro(self):
        q = bytearray(QUADRO_AO_VIVO)
        niveis = [min(1.0, v * self.ganho) for v in self._ouvido.niveis]
        t = time.monotonic() - self._t0
        if self.modo == "barras":
            nb = len(niveis)
            for i, x, r in TECLAS:
                banda = min(nb - 1, int(x / LARGURA * nb))
                altura = niveis[banda] * FILEIRAS          # quantas fileiras acendem, de baixo para cima
                degrau = FILEIRAS - 1 - r                   # 0 = fileira de baixo
                if altura <= degrau:
                    continue
                v = min(1.0, altura - degrau)               # a fileira do topo da barra acende em parte
                if self.cor:
                    c = bytes(round(ch * v) for ch in self.cor)
                else:                                       # verde embaixo → amarelo → vermelho no alto
                    c = _rgb(0.33 - 0.33 * degrau / (FILEIRAS - 1), 1, v)
                q[3 * i:3 * i + 3] = _quantizar(c)
        else:  # pulso
            g = min(1.0, self._ouvido.grave * self.ganho)
            for i, x, r in TECLAS:
                if self.cor:
                    c = bytes(round(ch * g) for ch in self.cor)
                else:
                    c = _rgb(t / 12 + x / LARGURA * 0.35, 1, g)
                q[3 * i:3 * i + 3] = _quantizar(c, 48)
        return bytes(q)


EFEITOS = {"musica": Musica}
