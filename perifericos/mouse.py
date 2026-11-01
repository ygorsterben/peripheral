"""Mouse Fire Phoenix BK-R6X pelo cabo ou pelo dongle 2.4G (protocolo em docs/protocolo_mouse.md).

Pacotes de 32 bytes na interface 2 (sem report ID): `CMD 00 01 TAM dados... CK`, CK = soma dos bytes 4..30.
Leitura = comando de escrita | 0x10. O mouse ecoa cada escrita.

Uso:
    with Mouse.abrir() as m:
        print(m.conexao, m.bateria(), m.dpi())
        m.gravar_polling(1000)
"""
import time
from dataclasses import dataclass

import hid

from . import Dessincronizado, NaoEncontrado, RespostaInvalida, SemResposta

MODOS = (("cabo", 0x248A, 0x5D2E), ("dongle", 0x249A, 0x5C2F))
INTERFACE = 2  # endpoints 0x05 (OUT) / 0x84 (IN)
TAMANHO = 32

POLLING = {125: 8, 250: 4, 500: 2, 1000: 1}  # Hz → valor (1000 / Hz)
SONO_MIN = (1, 2, 5, 6, 10, 15, 20, 30)  # opções do software; valor = minutos × 6 (unidades de 10 s)
TABELA_PADRAO = (800, 1600, 2400, 3200, 4800, 12000)
CORES_PADRAO = tuple(bytes.fromhex(c) for c in ("ff0000", "00ff00", "0000ff", "ff00ff", "ff8800", "00ffff"))
# Botões na ordem da tabela do mouse (Key 1, 2, 3, 5, 4, 6 do software; ver device/mouse_bk-r6x.xml).
BOTOES_PADRAO = (b"\x10\x01\x00", b"\x10\x02\x00", b"\x10\x04\x00", b"\x10\x08\x00", b"\x10\x10\x00", b"\x40\x01\x00")
BOTAO_TRAVADO = 0  # clique esquerdo: travado como no software oficial
CLIQUES = {1: "esquerdo", 2: "direito", 4: "meio", 8: "voltar", 0x10: "avançar"}

ESPERA_MAX = 12.0  # segundos repetindo o pedido enquanto o dongle diz "esperando o mouse" (mouse parado)


# --- codificação -------------------------------------------------------------------------------------------------

def pacote(cmd, tam, dados=b""):
    p = bytearray(TAMANHO)
    p[0:4] = bytes([cmd, 0x00, 0x01, tam])
    p[4:4 + len(dados)] = dados
    p[31] = sum(p[4:31]) & 0xFF
    return bytes(p)


def codigo_dpi(dpi):
    """DPI → código de 1 byte, em 3 faixas: passo 50 até 10000, 100 até 12000, 1000 até 18000."""
    if not 50 <= dpi <= 18000:
        raise ValueError(f"DPI fora da faixa 50..18000: {dpi}")
    if dpi <= 10000:
        passo, base, inicio = 50, 0, 0
    elif dpi <= 12000:
        passo, base, inicio = 100, 200, 10000
    else:
        passo, base, inicio = 1000, 220, 12000
    if (dpi - inicio) % passo:
        raise ValueError(f"nessa faixa o DPI vai de {passo} em {passo}: {dpi}")
    return base + (dpi - inicio) // passo


def dpi_do_codigo(c):
    if c <= 200:
        return c * 50
    if c <= 220:
        return 10000 + (c - 200) * 100
    return 12000 + (c - 220) * 1000


def arredondar_dpi(dpi):
    """Valor válido mais próximo (o app arredonda o que o usuário digita)."""
    dpi = max(50, min(18000, round(dpi)))
    passo = 50 if dpi <= 10000 else 100 if dpi <= 12000 else 1000
    return round(dpi / passo) * passo


def descrever_botao(b):
    tipo, p1, p2 = b
    if tipo == 0x10:
        return f"clique {CLIQUES.get(p1, hex(p1))}"
    if tipo == 0x30:
        return f"disparo rápido ({p1})"
    if tipo == 0x40:
        return "ciclo de DPI" if p1 == 1 else f"sensibilidade ({p1})"
    if tipo == 0x60:
        return "desativado"
    if tipo == 0x70:
        return f"tecla HID 0x{p2:02x}" + (f" + modificadores 0x{p1:02x}" if p1 else "")
    if tipo == 0x80:
        return f"multimídia 0x{p1 | p2 << 8:04x}"
    if tipo == 0x90:
        return f"macro ({p1}, {p2})"
    return f"desconhecido {b.hex()}"


def botao_tecla(codigo_hid, modificadores=0):
    return bytes([0x70, modificadores, codigo_hid])


def botao_midia(codigo_consumer):
    """Código 'consumer' HID de 16 bits (little-endian): 0x00E9 = Volume +, 0x006F = Brilho da tela +."""
    return bytes([0x80, codigo_consumer & 0xFF, codigo_consumer >> 8])


BOTAO_DESATIVADO = b"\x60\x00\x00"
BOTAO_CICLO_DPI = b"\x40\x01\x00"

# Funções que já se sabe gravar. Cliques: máscara do botão (tipo 0x10). Mídia e atalhos: códigos "consumer" HID
# (tipo 0x80); Volume + (0xE9) e Brilho + (0x6F) confirmados pelo usuário, os outros são os códigos padrão do HID.
FUNCOES_CLIQUE = {"esquerdo": 0x01, "direito": 0x02, "meio": 0x04, "voltar": 0x08, "avancar": 0x10}
FUNCOES_MIDIA = {"volume_mais": 0xE9, "volume_menos": 0xEA, "mudo": 0xE2, "player": 0x183, "tocar_pausar": 0xCD,
                 "anterior": 0xB6, "proxima": 0xB5, "parar": 0xB7}
FUNCOES_ATALHO = {"brilho_mais": 0x6F, "brilho_menos": 0x70, "calculadora": 0x192, "meu_computador": 0x194,
                  "email": 0x18A, "navegador": 0x196}


def montar_funcao(tipo, valor=None, modificadores=0):
    """Função de botão (3 bytes) a partir de uma descrição simples, usada pelo app."""
    if tipo == "clique":
        return bytes([0x10, FUNCOES_CLIQUE[valor], 0x00])
    if tipo == "midia":
        return botao_midia(FUNCOES_MIDIA[valor])
    if tipo == "atalho":
        return botao_midia(FUNCOES_ATALHO[valor])
    if tipo == "tecla":
        if not 0x04 <= int(valor) <= 0xE7:
            raise ValueError(f"código de tecla HID inválido: {valor}")
        return botao_tecla(int(valor), int(modificadores) & 0xFF)
    if tipo == "dpi":
        return BOTAO_CICLO_DPI
    if tipo == "desativar":
        return BOTAO_DESATIVADO
    raise ValueError(f"tipo de função desconhecido: {tipo}")


def ler_funcao(b):
    """Descrição simples (para o app) dos 3 bytes de uma função de botão."""
    tipo, p1, p2 = b
    if tipo == 0x10:
        nome = next((k for k, v in FUNCOES_CLIQUE.items() if v == p1), None)
        return {"tipo": "clique", "valor": nome} if nome else {"tipo": "outro", "bytes": b.hex()}
    if tipo == 0x80:
        codigo = p1 | p2 << 8
        for grupo, tabela in (("midia", FUNCOES_MIDIA), ("atalho", FUNCOES_ATALHO)):
            nome = next((k for k, v in tabela.items() if v == codigo), None)
            if nome:
                return {"tipo": grupo, "valor": nome}
        return {"tipo": "outro", "bytes": b.hex()}
    if tipo == 0x70:
        return {"tipo": "tecla", "valor": p2, "modificadores": p1}
    if tipo == 0x40 and p1 == 1:
        return {"tipo": "dpi"}
    if tipo == 0x60:
        return {"tipo": "desativar"}
    if tipo == 0x90:
        return {"tipo": "macro", "bytes": b.hex()}
    if tipo == 0x30:
        return {"tipo": "disparo", "bytes": b.hex()}
    return {"tipo": "outro", "bytes": b.hex()}


@dataclass
class TabelaDpi:
    niveis: int        # quantos níveis o botão de DPI percorre (1..6)
    ativo: int         # índice do nível em uso
    dpis: list         # 6 valores em DPI


# --- aparelho ----------------------------------------------------------------------------------------------------

class Mouse:
    def __init__(self, dev, conexao, ao_esperar=None, espera_max=ESPERA_MAX):
        self.dev = dev
        self.conexao = conexao        # "cabo" ou "dongle"
        self.ao_esperar = ao_esperar  # chamado (uma vez por pedido) quando o mouse parado não responde pelo dongle
        self.espera_max = espera_max  # o app usa menos (não pode ficar travado esperando o usuário mexer o mouse)

    @classmethod
    def abrir(cls, ao_esperar=None, espera_max=ESPERA_MAX):
        """Cabo primeiro (o software oficial também prefere o cabo); senão, o dongle."""
        for conexao, vid, pid in MODOS:
            for d in hid.enumerate(vid, pid):
                if d["interface_number"] == INTERFACE:
                    dev = hid.device()
                    dev.open_path(d["path"])
                    return cls(dev, conexao, ao_esperar, espera_max)
        raise NaoEncontrado("BK-R6X não encontrado nem no cabo nem no dongle.")

    def fechar(self):
        self.dev.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.fechar()

    # -- transporte

    def trocar(self, p, tentativas=2):
        """Envia 32 bytes e devolve a resposta ao mesmo comando.

        Pelo dongle: a resposta pode atrasar (há pausa e descarte antes de cada pedido); o mouse parado não responde
        configuração (o dongle só diz "esperando", status 01) e volta a responder quando é mexido, então o pedido é
        repetido por até `espera_max` s.
        """
        fim = time.monotonic() + self.espera_max
        falhas, esperando = 0, False
        while True:
            r = self._trocar_uma_vez(p)
            if r not in (None, "espera"):
                return r
            if r == "espera":
                if not esperando and self.ao_esperar:
                    self.ao_esperar()
                esperando = True
            elif not esperando:  # depois de um "esperando", o dongle às vezes fica mudo até o mouse acordar
                falhas += 1
                if falhas >= tentativas:
                    raise SemResposta(f"o mouse não respondeu ao comando 0x{p[0]:02x} ({self.conexao}).")
            if time.monotonic() > fim:
                raise SemResposta("o mouse não respondeu: mexa o mouse (parado, ele não responde pelo dongle).")

    def _trocar_uma_vez(self, p):
        time.sleep(0.05)
        while self.dev.read(64, 10):  # descarta respostas atrasadas (timeout 0 no hidapi = esperar para sempre)
            pass
        if self.dev.write(b"\x00" + p) < 0:
            raise SemResposta(f"falha ao escrever: {self.dev.error()}")
        limite = time.monotonic() + 0.8
        esperando = False
        while time.monotonic() < limite:
            r = bytes(self.dev.read(64, 100))
            if len(r) == TAMANHO + 1 and r[0] == 0:
                r = r[1:]
            if len(r) != TAMANHO:
                continue
            if r[0] == p[0]:
                if r[1] == 0x01:  # dongle: esperando o mouse
                    esperando = True
                    continue
                if r[1] == 0x02:  # dongle: não alcançou o mouse
                    raise SemResposta("o dongle não alcança o mouse (desligado, dormindo ou fora de alcance).")
                return r
            if r[24] == p[0]:  # [bytes 12..31 da anterior][00 x4][bytes 0..7 da atual]
                raise Dessincronizado("o dongle do mouse saiu de sincronia: tire o dongle da USB e recoloque.")
        return "espera" if esperando else None

    def ler(self, cmd):
        """Dados da leitura `cmd` (0x10..0x17), sem cabeçalho nem checksum."""
        r = self.trocar(bytes([cmd]) + bytes(TAMANHO - 1))
        if r[0] != cmd:
            raise RespostaInvalida(f"resposta inesperada à leitura 0x{cmd:02x}: {r.hex()}")
        if sum(r[4:31]) & 0xFF != r[31] and cmd != 0x15:  # a 0x15 sempre vem com CK 01 (igual no software)
            raise RespostaInvalida(f"checksum errado na leitura 0x{cmd:02x}: {r.hex()}")
        return r[4:4 + r[3]]

    def escrever(self, p):
        eco = self.trocar(p)
        if eco != p:
            raise RespostaInvalida(f"o eco não bate.\n enviado: {p.hex()}\n eco:     {eco.hex()}")

    # -- leituras

    def info(self):
        """0x10: modelo 'M110', versão, conexão e bateria (byte 9, em %)."""
        return self.ler(0x10)

    def bateria(self):
        return self.info()[9]

    def botoes(self):
        d = self.ler(0x11)
        return [bytes(d[i:i + 3]) for i in range(0, 18, 3)]

    def polling(self):
        return {v: k for k, v in POLLING.items()}.get(self.ler(0x12)[0])

    def dpi(self):
        d = self.ler(0x13)  # S + 6 × (X 00 Y 00)
        return TabelaDpi(d[0] & 0x0F, d[0] >> 4, [dpi_do_codigo(d[1 + 4 * i]) for i in range(6)])

    def cores(self):
        """Cor do LED de cada nível de DPI (6 × RGB)."""
        d = self.ler(0x14)
        return [bytes(d[i:i + 3]) for i in range(0, 18, 3)]

    def sono_min(self):
        return self.ler(0x17)[0] / 6

    # -- gravações (cada uma relê e confere)

    def _conferir(self, ok, o_que):
        if not ok:
            raise RespostaInvalida(f"{o_que}: a leitura depois de gravar não confere.")

    def gravar_polling(self, hz):
        self.escrever(pacote(0x02, 0x01, bytes([POLLING[hz]])))
        self._conferir(self.polling() == hz, "polling")

    def gravar_dpi(self, dpis=None, ativo=None, niveis=None):
        """Tabela de DPI completa; o que não for passado mantém o valor atual do mouse."""
        atual = self.dpi()
        dpis = list(dpis or atual.dpis)
        ativo = atual.ativo if ativo is None else ativo
        niveis = atual.niveis if niveis is None else niveis
        if len(dpis) != 6 or not 1 <= niveis <= 6 or not 0 <= ativo < niveis:
            raise ValueError("a tabela tem 6 valores, 1..6 níveis e o nível ativo dentro deles")
        dados = bytearray([(ativo << 4) | niveis])
        for d in dpis:
            c = codigo_dpi(d)
            dados += bytes([c, 0, c, 0])  # X e Y iguais
        self.escrever(pacote(0x03, 0x25, bytes(dados)))  # 0x25 é o que o software usa
        lido = self.dpi()
        self._conferir((lido.dpis, lido.ativo, lido.niveis) == (dpis, ativo, niveis), "DPI")

    def gravar_sono(self, minutos):
        if minutos not in SONO_MIN:
            raise ValueError(f"sono deve ser um de {SONO_MIN}")
        atual = self.ler(0x17)  # tempo + 3 bytes desconhecidos (01 00 08), preservados
        self.escrever(pacote(0x07, 0x04, bytes([minutos * 6]) + bytes(atual[1:4])))
        self._conferir(self.ler(0x17)[0] == minutos * 6, "sono")

    def gravar_botao(self, indice, funcao):
        """funcao = 3 bytes (TIPO P1 P2), ex.: botao_tecla(0x05), BOTAO_DESATIVADO ou BOTOES_PADRAO[i]."""
        if indice == BOTAO_TRAVADO:
            raise ValueError("o clique esquerdo é travado (igual ao software oficial)")
        botoes = self.botoes()
        botoes[indice] = bytes(funcao)
        self.escrever(pacote(0x09, 0x0F, b"".join(botoes)))  # 0x0f é o que o software usa
        self._conferir(self.botoes()[indice] == bytes(funcao), f"botão {indice}")

    def gravar_cor(self, nivel, rgb):
        """Cor do LED do nível de DPI `nivel` (cmd 0x04)."""
        cores = self.cores()
        cores[nivel] = bytes(rgb)
        self.gravar_cores(cores)

    def gravar_cores(self, cores):
        """As 6 cores do LED de uma vez (lista de 6 × 3 bytes)."""
        cores = [bytes(c) for c in cores]
        if len(cores) != 6 or any(len(c) != 3 for c in cores):
            raise ValueError("são 6 cores de 3 bytes (RGB)")
        self.escrever(pacote(0x04, 0x12, b"".join(cores)))
        self._conferir(self.cores() == cores, "cores do LED")
