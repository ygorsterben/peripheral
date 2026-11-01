"""Teclado Aula F99 Pro pelo cabo, dongle 2.4G ou Bluetooth (protocolo em docs/protocolo_teclado.md).

- Cabo: feature report 6 de 520 bytes (cabeçalho de 8 bytes + dados) na coleção 0xFF00.
- Dongle e Bluetooth: relatórios de 20 bytes `13 CMD TOTAL ÍNDICE TAM dados[14] CK` na coleção 0xFF02, com o mesmo
  conteúdo dividido em pacotes de 14 bytes.
A configuração fica num bloco de 128 bytes: ler → mudar → gravar, como o software oficial.

Uso:
    with Teclado.abrir() as t:
        b = t.ler_bloco()
        t.alterar(brilho=3)
"""
import ctypes
import ctypes.wintypes as w
import os
import time
from pathlib import Path

import hid

from . import ErroPeriferico, NaoEncontrado, RespostaInvalida, SemResposta

VID_CABO, PID_CABO = 0x258A, 0x010C
CAMINHOS_SEM_FIO = (  # mesma coleção 0xFF02 de 20 bytes nos três
    ("dongle", 0x3554, 0xFA09),
    ("bluetooth 3.0", 0x3554, 0xFA08),  # clássico: perde ainda mais pacotes
    ("bluetooth 5.0", 0x3554, 0xFA07),  # LE: funciona, mas leva ~16-20 s por leitura/gravação
)
REPORT_ID = 6
TAMANHO_CABO = 520

EFEITOS = ("Fixed_on", "Respire", "Rainbow", "Flash_away", "Raindrops", "Rainbow_wheel", "Ripples_shining",
           "Stars_twinkle", "Shadow_disappear", "Retro_snake", "Neon_stream", "Reaction", "Sine_wave",
           "Retinue scanning", "Rotating windmill", "Colorful waterfall", "Blossoming", "Rotating storm")
EFEITO_POR_TECLA = 0x15  # Self-define
IDX_POR_TECLA = 9  # 1 enquanto a luz por tecla está ativa (o software volta para 0 ao sair)

# Nome da tecla (como o app chama) → índice na matriz do teclado (último número de cada Kn do KB.ini do F99 Pro).
# O mesmo índice vale para a luz por tecla (planos R/G/B de 126) e para a tabela de teclas (cmd 0x03).
INDICE_TECLA = {
    "esc": 0, "f1": 12, "f2": 18, "f3": 24, "f4": 30, "f5": 36, "f6": 42, "f7": 48, "f8": 54, "f9": 60, "f10": 66,
    "f11": 72, "f12": 78, "`": 1, "1": 7, "2": 13, "3": 19, "4": 25, "5": 31, "6": 37, "7": 43, "8": 49, "9": 55,
    "0": 61, "-": 67, "=": 73, "back": 79, "del": 84, "scroll": 90, "numlock": 91, "num/": 97, "num*": 103,
    "num-": 109, "tab": 2, "q": 8, "w": 14, "e": 20, "r": 26, "t": 32, "y": 38, "u": 44, "i": 50, "o": 56, "p": 62,
    "[": 68, "]": 74, "\\": 80, "calc": 96, "home": 85, "num7": 92, "num8": 98, "num9": 104, "num+": 110, "caps": 3,
    "a": 9, "s": 15, "d": 21, "f": 27, "g": 33, "h": 39, "j": 45, "k": 51, "l": 57, ";": 63, "'": 69, "enter": 81,
    "num4": 93, "num5": 99, "num6": 105, "shift": 4, "z": 10, "x": 16, "c": 22, "v": 28, "b": 34, "n": 40, "m": 46,
    ",": 52, ".": 58, "/": 64, "rshift": 82, "up": 88, "num1": 94, "num2": 100, "num3": 106, "ctrl": 5, "win": 11,
    "alt": 17, "space": 35, "ralt": 53, "fn": 59, "pgdn": 87, "left": 83, "down": 89, "right": 95, "num0": 101,
    "num.": 107, "numenter": 112, "pgup": 86, "roda": 108,
}


# Tabela de teclas (cmd 0x03 no cabo, 0x01 no receptor): 128 entradas × 4 bytes na ordem de INDICE_TECLA.
#   00 MOD 00 HID  tecla comum (MOD = Ctrl 01, Shift 02, Alt 04, Win 08 — os da direita: ×16)
#   02 00 HH LL    multimídia: código "consumer" HID em big-endian (Calc = 02 00 01 92)
#   0d 00 00 00    Fn · 07 .. roda de volume · 00 00 00 00 = sem função
# O teclado não devolve a tabela: a padrão veio do software oficial (capturas/teclado_remap_dongle.pcap).
TECLAS_PADRAO = Path(__file__).with_name("dados") / "teclado_teclas_padrao.bin"
TECLAS_TRAVADAS = ("fn", "roda")  # trocar a Fn tiraria o acesso aos atalhos do teclado


def entrada_tecla(codigo_hid, modificadores=0):
    return bytes([0x00, modificadores & 0xFF, 0x00, codigo_hid])


def entrada_midia(codigo_consumer):
    return bytes([0x02, 0x00, codigo_consumer >> 8, codigo_consumer & 0xFF])


ENTRADA_SEM_FUNCAO = bytes(4)

# Macros no aparelho (receptor; capturas/teclado_macro_dongle*.pcap, docs/protocolo_teclado.md).
# A tecla leva `03 01 01 IDX`; IDX = posição da macro no conjunto, que é gravado inteiro (cmd 0x03 no receptor).
MACROS_MAX = 16
EVENTOS_MAX = 30  # limite do software oficial
ESPERA_MAX = 0xFFFF


VEZES_MAX = 99
QUADRO_AO_VIVO = 126 * 3  # cor ao vivo: R G B de cada índice da matriz


# Modo de repetição (2º byte da tecla): capturas/teclado_macro_repeticao.pcap (3x = 03 01 03 00),
# teclado_macro_segurar.pcap (até outra tecla = 03 02 01 00) e teclado_macro_modo3.pcap (enquanto segurar = 03 04 01 00).
MODOS_MACRO = {"vezes": 0x01, "ate_outra": 0x02, "segurar": 0x04}


def entrada_macro(indice, vezes=1, modo="vezes"):
    """`03 MODO VEZES IDX`. VEZES só conta no modo "vezes" (nos outros o software manda 1)."""
    if modo not in MODOS_MACRO:
        raise ValueError(f"modo de repetição desconhecido: {modo}")
    if modo != "vezes":
        vezes = 1
    if not 1 <= vezes <= VEZES_MAX:
        raise ValueError(f"repetição de 1 a {VEZES_MAX} vezes")
    return bytes([0x03, MODOS_MACRO[modo], vezes, indice])


def montar_macros(macros):
    """[(nome, [(solta, espera_ms, tecla_hid), ...]), ...] → bloco do cmd 0x03: tabela de (deslocamento, tamanho)
    de cada macro, seguida dos corpos `tam_nome nome(UTF-16LE) eventos`. Evento = FLAG(00 aperta/80 solta) ESPERA(2,
    big-endian) TECLA."""
    if not 0 < len(macros) <= MACROS_MAX:
        raise ValueError(f"o conjunto de macros precisa ter de 1 a {MACROS_MAX}")
    corpos = []
    for nome, eventos in macros:
        n = nome.encode("utf-16-le")
        if not 0 < len(n) <= 2 * 16 or not 0 < len(eventos) <= EVENTOS_MAX:
            raise ValueError(f"macro {nome!r}: nome de 1 a 16 letras e de 1 a {EVENTOS_MAX} eventos")
        corpo = bytearray([len(n)]) + n
        for solta, espera, tecla in eventos:
            if not 0 <= espera <= ESPERA_MAX or not 0 < tecla < 0xE8:
                raise ValueError(f"macro {nome!r}: evento inválido ({espera} ms, tecla {tecla})")
            # flag: 0x80 = solta; 0x10 = modificador (Ctrl/Shift/Alt/Win, HID E0–E7) — capturas/teclado_macro_shift.pcap
            flag = (0x80 if solta else 0x00) | (0x10 if 0xE0 <= tecla <= 0xE7 else 0x00)
            corpo += bytes([flag, espera >> 8, espera & 0xFF, tecla])
        corpos.append(bytes(corpo))
    tabela, deslocamento = bytearray(), 4 * len(corpos)
    for corpo in corpos:
        tabela += deslocamento.to_bytes(2, "little") + len(corpo).to_bytes(2, "little")
        deslocamento += len(corpo)
    return bytes(tabela) + b"".join(corpos)


def montar_tabela_teclas(trocas):
    """Tabela completa (512 bytes): a padrão com as trocas {nome da tecla: 4 bytes} por cima."""
    tabela = bytearray(TECLAS_PADRAO.read_bytes())
    for nome, entrada in trocas.items():
        if nome in TECLAS_TRAVADAS:
            raise ValueError(f"a tecla {nome} é travada")
        i = INDICE_TECLA[nome]
        tabela[4 * i:4 * i + 4] = bytes(entrada)
    return bytes(tabela)


def planos_por_tecla(cores):
    """{nome da tecla: "RRGGBB"} → 384 bytes (planos R, G e B de 126 bytes, um byte por índice da matriz)."""
    dados = bytearray(384)
    for nome, cor in cores.items():
        i = INDICE_TECLA.get(nome)
        if i is None or i >= 126:
            continue
        r, g, b = bytes.fromhex(cor)
        dados[i], dados[126 + i], dados[252 + i] = r, g, b
    return bytes(dados)
IDX_DEBOUNCE, IDX_EFEITO, IDX_SONO = 3, 10, 24
SONO_MIN = (1, 1.5, 2, 3, 4, 5, 10, 15, 20)  # opções do software (KB.ini SleepUI); valor = minutos × 2 (30 s)
MARCA_FIM = b"\x5a\xa5"  # últimos 2 bytes de um bloco válido
COLORIDO = 7  # nibble baixo do 2º byte do par do efeito (captura: Fixed_on 40 → 47 ao marcar Colourful)

# Bloco de cores dos efeitos (cmd 0x0a, 512 bytes): 21 bytes por efeito a partir do byte 21 × hw (7 cores RGB, a 1ª é
# a escolhida). O software manda depois de trocar de efeito e o teclado NÃO devolve; sem ele, trocar para Neon_stream
# deixou a luz apagada (2026-10-31). Base: último bloco enviado pelo software (capturas/teclado_cor.pcap); por cima,
# as cores que o usuário escolheu no software oficial, lidas do perfil dele.
CORES_PADRAO = Path(__file__).with_name("dados") / "teclado_cores.bin"
PERFIL_OFICIAL = Path(os.environ.get("LOCALAPPDATA", "")) / "BYCOMBO4" / "AULA F99 Pro" / "profile.dct"
PERFIL_INICIO, PERFIL_REGISTRO = 12172, 36  # 1 registro por efeito: brilho vel colorido 00 + 8 × (R G B 00)


def cor_do_efeito(cores, hw, indice=0):
    """Cor `indice` (0 = escolhida, 1..6 = paleta) do efeito `hw` no bloco de cores."""
    return bytes(cores[21 * hw + 3 * indice:21 * hw + 3 * indice + 3])


def mudar_cor(cores, hw, rgb):
    """Bloco de cores com a cor escolhida do efeito `hw` trocada."""
    novo = bytearray(cores)
    novo[21 * hw:21 * hw + 3] = bytes(rgb)
    return bytes(novo)


def cores_atuais(perfil=PERFIL_OFICIAL):
    """Melhor estimativa das cores que estão no teclado: bloco base + cores do perfil do software oficial (se houver).
    Conferido em 2026-10-31: o perfil bate byte a byte com o bloco que o software manda."""
    cores = bytearray(CORES_PADRAO.read_bytes())
    if perfil.is_file():
        d = perfil.read_bytes()
        for hw in range(1, 22):
            r = d[PERFIL_INICIO + PERFIL_REGISTRO * (hw - 1):PERFIL_INICIO + PERFIL_REGISTRO * hw]
            sete = b"".join(r[4 + 4 * k:7 + 4 * k] for k in range(7))
            if len(r) == PERFIL_REGISTRO and any(sete):
                cores[21 * hw:21 * hw + 21] = sete
    return bytes(cores)


def tamanho_feature(caminho):
    """Tamanho do feature report da coleção (HidP_GetCaps), para achar a de 520 bytes no cabo."""
    k32, hd = ctypes.WinDLL("kernel32"), ctypes.WinDLL("hid")
    k32.CreateFileW.restype = w.HANDLE

    class Caps(ctypes.Structure):
        _fields_ = [("Usage", w.USHORT), ("UsagePage", w.USHORT), ("In", w.USHORT), ("Out", w.USHORT),
                    ("Feat", w.USHORT), ("resto", w.USHORT * 27)]

    h = k32.CreateFileW(caminho.decode(), 0, 3, None, 3, 0, None)
    pp, caps = ctypes.c_void_p(), Caps()
    try:
        if not hd.HidD_GetPreparsedData(h, ctypes.byref(pp)):
            return 0
        hd.HidP_GetCaps(pp, ctypes.byref(caps))
        hd.HidD_FreePreparsedData(pp)
        return caps.Feat
    finally:
        k32.CloseHandle(h)


class Teclado:
    """Base comum; `abrir()` devolve a variante do caminho encontrado."""
    conexao = "?"
    bateria = None  # no cabo o teclado não manda aviso de bateria (está carregando)

    def __init__(self, dev):
        self.dev = dev

    @staticmethod
    def abrir():
        """Cabo primeiro; senão, o primeiro caminho sem fio em que o teclado responde."""
        for d in hid.enumerate(VID_CABO, PID_CABO):
            if d["usage_page"] == 0xFF00 and tamanho_feature(d["path"]) == TAMANHO_CABO:
                dev = hid.device()
                dev.open_path(d["path"])
                return TecladoCabo(dev)
        erros = []
        for conexao, vid, pid in CAMINHOS_SEM_FIO:
            for d in hid.enumerate(vid, pid):
                if d["usage_page"] != 0xFF02:
                    continue
                dev = hid.device()
                dev.open_path(d["path"])
                t = TecladoSemFio(dev, conexao)
                try:
                    t.acordar()
                    return t
                except SemResposta as e:
                    erros.append(str(e))
                    dev.close()
        raise NaoEncontrado("Aula F99 Pro não encontrado (cabo, dongle ou Bluetooth). " + " / ".join(erros))

    def fechar(self):
        self.dev.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.fechar()

    # -- operações de alto nível (iguais em todos os caminhos)

    def versao(self):
        v = self.firmware()
        return f"{v[0]}.{v[1]}.{v[2]}"

    def ler_bloco(self):
        bloco = self._ler_bloco()
        if bloco[126:128] != MARCA_FIM:
            raise RespostaInvalida(f"bloco sem a marca 5a a5 no fim (não gravar nada): {bloco.hex(' ')}")
        return bytearray(bloco)

    def aplicar_por_tecla(self, cores):
        """Liga a luz por tecla com {nome: "RRGGBB"}: bloco com efeito 0x15 e marca ligada, depois os planos de cor
        (sequência do software: cabo 0x04 → 0x06; receptor/Bluetooth 0x04 → 0x02). O teclado não devolve as cores."""
        b = self.ler_bloco()
        b[IDX_EFEITO], b[IDX_POR_TECLA] = EFEITO_POR_TECLA, 1
        self.gravar_bloco(b)
        self.gravar_por_tecla(planos_por_tecla(cores))
        relido = self.ler_bloco()
        if (relido[IDX_EFEITO], relido[IDX_POR_TECLA]) != (EFEITO_POR_TECLA, 1):
            raise RespostaInvalida("o teclado não ficou na luz por tecla.")
        return relido

    def gravar_teclas(self, tabela):
        """Grava a tabela de teclas inteira (o software também manda a tabela toda a cada mudança)."""
        if len(tabela) != 512:
            raise ValueError("a tabela de teclas tem 512 bytes")
        self._gravar_tabela_teclas(bytes(tabela))

    def ler_cores(self):
        """Bloco de cores dos efeitos (o mesmo que gravar_cores manda): cabo 0x8a = 512 bytes, receptor/Bluetooth
        0x49 = 490 bytes (o resto do bloco de 512 não volta)."""
        return self._ler_cores()

    def quadro_ao_vivo(self, quadro):
        """Cor ao vivo (só enquanto o app manda; o efeito gravado volta ao regravar o bloco com gravar_bloco).
        `quadro` = 126 × (R G B) na ordem de INDICE_TECLA. Cabo = cmd 0x08 (quadro inteiro); receptor = cmd 0x88
        (lista de grupos `R G B N idx…`, teclas fora da lista apagadas). Ver docs/protocolo_teclado.md."""
        if len(quadro) != QUADRO_AO_VIVO:
            raise ValueError(f"o quadro tem {QUADRO_AO_VIVO} bytes")
        self._quadro_ao_vivo(bytes(quadro))

    def gravar_macros(self, bloco):
        """Grava o conjunto de macros (montar_macros). Antes, a tabela de teclas com `entrada_macro`."""
        self._gravar_macros(bytes(bloco))

    @staticmethod
    def par_do_efeito(bloco):
        """Índice do par (brilho, velocidade<<4 | colorido) do efeito atual: 56 + 2 × efeito."""
        return 56 + 2 * bloco[IDX_EFEITO]

    def alterar(self, efeito=None, brilho=None, velocidade=None, colorido=None, sono_min=None, debounce=None,
                cores=None):
        """Lê o bloco, muda o que foi pedido, grava e relê para conferir. Brilho/velocidade/colorido valem para o
        efeito (novo, se `efeito` também for passado). Ao trocar de efeito manda também o bloco de cores (`cores`, ou
        as cores atuais do perfil do software oficial); passar só `cores` muda as cores sem trocar o efeito."""
        b = self.ler_bloco()
        antes = bytes(b)
        if efeito is not None:
            b[IDX_EFEITO] = efeito
            if efeito != EFEITO_POR_TECLA:
                b[IDX_POR_TECLA] = 0  # sai da luz por tecla, como o software
        par = self.par_do_efeito(b)
        if brilho is not None:
            b[par] = brilho
        if velocidade is not None:
            b[par + 1] = (velocidade << 4) | (b[par + 1] & 0x0F)
        if colorido is not None:  # nibble baixo: 0 = cor escolhida, 1..6 = cor da paleta, 7 = colorido (aleatório)
            b[par + 1] = (b[par + 1] & 0xF0) | (COLORIDO if colorido else 0)
        if sono_min is not None:
            b[IDX_SONO] = round(sono_min * 2)
        if debounce is not None:
            b[IDX_DEBOUNCE] = debounce - 1  # o teclado guarda estágio - 1
        mudados = [i for i in range(128) if b[i] != antes[i]]
        self.gravar_bloco(b)
        if efeito is not None or cores is not None:
            self.gravar_cores(cores if cores is not None else cores_atuais())
        relido = self.ler_bloco()
        if any(relido[i] != b[i] for i in mudados):  # só os bytes mudados, como o software confere
            raise RespostaInvalida("o bloco relido depois de gravar não confere.")
        return relido


class TecladoCabo(Teclado):
    conexao = "cabo"

    def _pedir(self, cabecalho, dados=b""):
        p = bytearray(TAMANHO_CABO)
        p[0:8] = cabecalho
        p[8:8 + len(dados)] = dados
        if self.dev.send_feature_report(bytes(p)) < 0:
            raise SemResposta(f"falha ao enviar: {self.dev.error()}")

    def _resposta(self, cmd):
        r = bytes(self.dev.get_feature_report(REPORT_ID, TAMANHO_CABO))
        if len(r) < 8 or r[0] != REPORT_ID or r[1] != cmd:
            raise RespostaInvalida(f"resposta inesperada ao comando 0x{cmd:02x}: {r[:16].hex(' ')}")
        return r[8:]

    def firmware(self):
        self._pedir(bytes([0x06, 0x82, 0x01, 0x00, 0x01, 0x00, 0x06, 0x00]))
        return self._resposta(0x82)[:6]

    def _ler_bloco(self):
        self._pedir(bytes([0x06, 0x84, 0x00, 0x00, 0x01, 0x00, 0x80, 0x00]))
        return self._resposta(0x84)[:128]

    def gravar_bloco(self, bloco):
        self._pedir(bytes([0x06, 0x04, 0x00, 0x00, 0x01, 0x00, 0x80, 0x00]), bytes(bloco))

    def gravar_cores(self, cores):
        self._pedir(bytes([0x06, 0x0A, 0x00, 0x00, 0x01, 0x00, 0x00, 0x02]), cores)

    def _ler_cores(self):
        self._pedir(bytes([0x06, 0x8A, 0x00, 0x00, 0x01, 0x00, 0x00, 0x02]))
        return self._resposta(0x8A)[:512]

    def _quadro_ao_vivo(self, quadro):  # capturas/teclado_musica_cabo.pcap
        self._pedir(bytes([0x06, 0x08, 0x00, 0x00, 0x01, 0x00, QUADRO_AO_VIVO & 0xFF, QUADRO_AO_VIVO >> 8]), quadro)

    def gravar_por_tecla(self, planos):
        self._pedir(bytes([0x06, 0x06, 0x00, 0x00, 0x01, 0x00, 0x80, 0x01]), planos)

    def _gravar_tabela_teclas(self, tabela):
        self._pedir(bytes([0x06, 0x03, 0x00, 0x00, 0x01, 0x00, 0x00, 0x02]), tabela)  # página 0 = camada padrão

    def _gravar_macros(self, bloco):
        # mesmo bloco do receptor num pedido só: 06 05 00 00 01 00 TAM(2, little-endian) (capturas/teclado_macro_cabo.pcap)
        if len(bloco) > TAMANHO_CABO - 8:
            raise ErroPeriferico(f"macros grandes demais para o cabo ({len(bloco)} bytes; máximo {TAMANHO_CABO - 8})")
        self._pedir(bytes([0x06, 0x05, 0x00, 0x00, 0x01, 0x00, len(bloco) & 0xFF, len(bloco) >> 8]), bloco)


class TecladoSemFio(Teclado):
    """Dongle ou Bluetooth. O dongle (e o teclado) ecoa cada pacote de escrita."""

    def __init__(self, dev, conexao):
        super().__init__(dev)
        self.conexao = conexao
        self.bateria = None  # % do último aviso espontâneo `13 0a .. 04 05 PCT ..` (dongle e Bluetooth)

    @staticmethod
    def _pacote(cmd, total, indice, dados):
        p = bytearray(20)
        p[0:5] = bytes([0x13, cmd, total, indice, len(dados)])
        p[5:5 + len(dados)] = dados
        p[19] = sum(p[:19]) & 0xFF
        return bytes(p)

    def acordar(self):
        """O software sempre começa com 0x07 (o dongle responde sozinho; sem ele o 1º pedido às vezes se perdia).
        Quem prova que o teclado está do outro lado é o 0x05 (firmware). No Bluetooth o 0x07 não tem resposta."""
        self._descartar()
        self._enviar(self._pacote(0x07, 1, 0, b""))
        self._ler(0x07, 0.5)
        self._pedir_varios(0x05)

    def _descartar(self):
        while r := self.dev.read(64, 10):  # timeout 0 no hidapi = esperar para sempre
            self._aviso(bytes(r))

    def _enviar(self, p):
        if self.dev.write(p) < 0:
            raise SemResposta(f"falha ao enviar: {self.dev.error()}")

    def _ler(self, cmd, limite=1.0):
        """Próximo pacote do comando; None se não vier. Avisos espontâneos (0x0a) no meio são guardados."""
        fim = time.monotonic() + limite
        while time.monotonic() < fim:
            r = bytes(self.dev.read(64, 100))
            self._aviso(r)
            if len(r) >= 20 and r[0] == 0x13 and r[1] == cmd:
                if sum(r[:19]) & 0xFF != r[19]:
                    raise RespostaInvalida(f"checksum errado: {r[:20].hex(' ')}")
                return r[:20]
        return None

    def _aviso(self, r):
        if len(r) >= 20 and r[0] == 0x13 and r[1] == 0x0A and r[4] >= 2 and r[5] == 0x05 and r[6] <= 100:
            self.bateria = r[6]

    def escutar(self, segundos):
        """Só lê os avisos espontâneos por um tempo (a bateria chega assim)."""
        fim = time.monotonic() + segundos
        while time.monotonic() < fim:
            self._aviso(bytes(self.dev.read(64, 100)))

    def _sem_resposta(self, cmd):
        return SemResposta(f"o teclado não respondeu ao comando 0x{cmd:02x} pelo {self.conexao} "
                           "(dormindo, fora de alcance ou ligado por outro caminho?)")

    def _pedir_varios(self, cmd):
        """Leitura em vários pacotes, juntados pelo índice. No Bluetooth o Windows perde pacotes quando chegam vários
        de uma vez; como a resposta é sempre a mesma, o pedido é repetido e as partes vão sendo juntadas."""
        partes = {}
        for tentativa in range(20):
            if tentativa:
                time.sleep(0.2)
            self._descartar()
            self._enviar(self._pacote(cmd, 1, 0, b""))
            while (r := self._ler(cmd, 0.4)) is not None:
                partes[r[3]] = r[5:5 + r[4]]
                if len(partes) == r[2]:
                    return b"".join(partes[i] for i in range(r[2]))
        raise self._sem_resposta(cmd)

    def _gravar_varios(self, cmd, dados):
        pedacos = [dados[i:i + 14] for i in range(0, len(dados), 14)]
        self._descartar()
        for i, pedaco in enumerate(pedacos):
            p = self._pacote(cmd, len(pedacos), i, pedaco)
            for _ in range(3):  # no Bluetooth o eco pode se perder: reenviar o mesmo pacote
                self._enviar(p)
                if (eco := self._ler(cmd, 0.5)) is not None:
                    break
            else:
                raise self._sem_resposta(cmd)
            if eco != p:
                raise RespostaInvalida(f"o teclado não ecoou o pacote {i} do comando 0x{cmd:02x}: {eco.hex(' ')}")

    def firmware(self):
        return self._pedir_varios(0x05)[:6]

    def _ler_bloco(self):
        return self._pedir_varios(0x44)[:128]

    def gravar_bloco(self, bloco):
        self._gravar_varios(0x04, bytes(bloco))

    def gravar_cores(self, cores):
        self._gravar_varios(0x09, cores)

    def _ler_cores(self):
        return self._pedir_varios(0x49)  # 35 pacotes = 490 bytes (testado no receptor em 2026-11-01)

    def _quadro_ao_vivo(self, quadro):  # capturas/teclado_musica_dongle.pcap
        if self.conexao == "bluetooth":
            raise ErroPeriferico("a cor ao vivo não funciona pelo Bluetooth (os pacotes se perdem); use o cabo ou o receptor")
        grupos = {}
        for i in range(126):
            rgb = quadro[3 * i:3 * i + 3]
            if any(rgb):
                grupos.setdefault(rgb, []).append(i)
        dados = b"".join(rgb + bytes([len(idx)]) + bytes(idx) for rgb, idx in grupos.items())
        if not dados:  # tudo apagado: o pacote que o software manda no silêncio
            pacotes = [(0x23, b"\0\0\0")]
        else:
            pacotes = [(0x10 + len(dados[i:i + 14]), dados[i:i + 14]) for i in range(0, len(dados), 14)]
        for n, (tipo, pedaco) in enumerate(pacotes):
            p = bytearray(20)
            p[0:5] = bytes([0x13, 0x88, len(pacotes), n, tipo])
            p[5:5 + len(pedaco)] = pedaco
            p[19] = sum(p[:19]) & 0xFF
            self._enviar(bytes(p))
            time.sleep(0.006)  # o software espaça ~12 ms; sem pausa o receptor pode perder pacotes
        self._ao_vivo_n = getattr(self, "_ao_vivo_n", 0) + 1
        if self._ao_vivo_n % 30 == 0:
            self._descartar()  # esvazia os ecos acumulados

    def gravar_por_tecla(self, planos):
        self._gravar_varios(0x02, planos)  # 28 pacotes (capturas/teclado_selfdefine_dongle.pcap)

    def _gravar_tabela_teclas(self, tabela):
        self._gravar_varios(0x01, tabela)  # 37 pacotes (capturas/teclado_remap_dongle.pcap)

    def _gravar_macros(self, bloco):
        self._gravar_varios(0x03, bloco)  # capturas/teclado_macro_dongle*.pcap
