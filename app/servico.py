"""Carteiro: a única thread que fala com os aparelhos (um pedido de cada vez) e mantém o estado para a interface.

- Mantém a conexão aberta e reabre quando o aparelho some/volta (cabo, dongle, Bluetooth).
- Lê os aparelhos ao abrir, a cada `INTERVALO` s e quando a interface pede.
- Pelo dongle, o mouse parado não responde: nesse caso o estado fica marcado como "parado" e os últimos valores
  conhecidos continuam valendo (vêm da cópia salva no PC, em %APPDATA%).
Gravações (fase 2): `executar()` põe a operação na mesma fila e espera o resultado; enquanto o mouse parado não
responde pelo dongle, o estado ganha `esperando_mouse` para a interface pedir "mexa o mouse".
"""
import json
import os
import queue
import threading
import time
from pathlib import Path

import hid

from perifericos import ErroPeriferico, SemResposta, mouse as _m, teclado as _t
from perifericos.mouse import ESPERA_MAX, Mouse, ler_funcao
from perifericos.teclado import (COLORIDO, EFEITOS, IDX_DEBOUNCE, IDX_EFEITO, IDX_SONO, Teclado, cor_do_efeito,
                                 cores_atuais)

INTERVALO = 60          # segundos entre leituras automáticas
PULSO = 3               # segundos entre conferências de aparelho conectado/desconectado
REPETIR_MOUSE = 5       # mouse parado/dormindo: tenta de novo a cada tantos segundos
REPETIR_TECLADO = 15    # teclado dormindo: idem
ESPERA_MOUSE = 2.5      # no app não esperamos 12 s o usuário mexer o mouse
PASTA_DADOS = Path(os.environ.get("APPDATA", Path.home())) / "GerenciadorPerifericos"
ARQUIVO_ESTADO = PASTA_DADOS / "estado.json"
# Cópia das cores dos efeitos do teclado (o teclado não as devolve). Na primeira vez, importa as do software oficial.
ARQUIVO_CORES = PASTA_DADOS / "teclado_cores.bin"


def cores_teclado():
    try:
        dados = ARQUIVO_CORES.read_bytes()
        if len(dados) == 512:
            return dados
    except OSError:
        pass
    dados = cores_atuais()
    guardar_cores_teclado(dados)
    return dados


# Luz por tecla: o teclado não devolve as cores, então o app guarda a própria cópia {tecla: "RRGGBB"}.
# Padrão = o desenho que estava no teclado do usuário (capturas/teclado_selfdefine_dongle.pcap).
ARQUIVO_POR_TECLA = PASTA_DADOS / "teclado_por_tecla.json"
POR_TECLA_PADRAO = {**{k: "FFFFFF" for k in ("q", "w", "e", "r", "a", "s", "d", "f", "left", "up", "down", "right")},
                    "f1": "00FF00"}


def cores_por_tecla():
    try:
        dados = json.loads(ARQUIVO_POR_TECLA.read_text(encoding="utf-8"))
        if isinstance(dados, dict):
            return dados
    except (OSError, ValueError):
        pass
    return dict(POR_TECLA_PADRAO)


def guardar_cores_por_tecla(cores):
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    ARQUIVO_POR_TECLA.write_text(json.dumps(cores, ensure_ascii=False, indent=1), encoding="utf-8")


# Teclas trocadas: o teclado não devolve a tabela, então o app guarda {tecla: função} (vazio = tudo padrão).
ARQUIVO_TECLAS = PASTA_DADOS / "teclado_teclas.json"


def teclas_trocadas():
    try:
        dados = json.loads(ARQUIVO_TECLAS.read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def guardar_teclas_trocadas(trocas):
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    ARQUIVO_TECLAS.write_text(json.dumps(trocas, ensure_ascii=False, indent=1), encoding="utf-8")


# Macros do teclado: o aparelho não devolve, então o app guarda a lista [{"nome", "eventos": [[solta, ms, tecla], ...]}].
# A posição na lista é o número da macro que a tecla aponta (`03 01 01 IDX`).
ARQUIVO_MACROS = PASTA_DADOS / "teclado_macros.json"


def macros_guardadas():
    try:
        dados = json.loads(ARQUIVO_MACROS.read_text(encoding="utf-8"))
        return dados if isinstance(dados, list) else []
    except (OSError, ValueError):
        return []


def guardar_macros(macros):
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    ARQUIVO_MACROS.write_text(json.dumps(macros, ensure_ascii=False, indent=1), encoding="utf-8")


def guardar_cores_teclado(dados):
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    ARQUIVO_CORES.write_bytes(bytes(dados))



def presenca():
    """Quais caminhos dos aparelhos estão na USB agora (barato: só enumera, não abre nada)."""
    achados = set()
    for nome, vid, pid in _m.MODOS:
        if any(d["interface_number"] == _m.INTERFACE for d in hid.enumerate(vid, pid)):
            achados.add(f"mouse:{nome}")
    if any(d["usage_page"] == 0xFF00 for d in hid.enumerate(_t.VID_CABO, _t.PID_CABO)):
        achados.add("teclado:cabo")
    for nome, vid, pid in _t.CAMINHOS_SEM_FIO:
        if any(d["usage_page"] == 0xFF02 for d in hid.enumerate(vid, pid)):
            achados.add(f"teclado:{nome}")
    return frozenset(achados)


def _agora():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class Carteiro(threading.Thread):
    def __init__(self):
        super().__init__(name="carteiro", daemon=True)
        self._pedidos = queue.Queue()
        self._trava = threading.Lock()
        self._mouse = None
        self._teclado = None
        self._parar = False
        self.estado = self._carregar()

    # -- estado (lido pela interface em outra thread)

    def _carregar(self):
        base = {"mouse": {"conectado": False}, "teclado": {"conectado": False}}
        try:
            salvo = json.loads(ARQUIVO_ESTADO.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return base
        for nome in base:  # o que foi salvo vira "último conhecido" até a próxima leitura
            if isinstance(salvo.get(nome), dict):
                base[nome] = {**salvo[nome], "conectado": False, "da_copia": True}
        return base

    def _salvar(self):
        try:
            PASTA_DADOS.mkdir(parents=True, exist_ok=True)
            ARQUIVO_ESTADO.write_text(json.dumps(self.estado, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

    def ler_estado(self):
        with self._trava:
            return json.loads(json.dumps(self.estado))

    def _publicar(self, nome, valores):
        with self._trava:
            self.estado[nome] = valores
        self._salvar()

    # -- pedidos

    def atualizar(self):
        self._pedidos.put("atualizar")

    def executar(self, aparelho, operacao, limite=40):
        """Roda `operacao(aparelho_aberto)` na thread do carteiro e devolve {"ok": bool, "erro": str}."""
        pronto, resultado = threading.Event(), {}
        self._pedidos.put(("op", aparelho, operacao, pronto, resultado))
        if not pronto.wait(limite):
            return {"ok": False, "erro": "O aparelho demorou demais para responder."}
        return resultado

    def parar(self):
        self._parar = True
        self._pedidos.put("parar")

    def run(self):
        """Laço principal: a cada PULSO s confere se algum aparelho entrou ou saiu (só lista a USB, sem falar
        com eles) e relê quando muda, quando a interface pede, a cada INTERVALO s, ou de tempos em tempos enquanto
        o mouse está parado / o teclado dormindo."""
        assinatura, ultima = None, {"mouse": 0.0, "teclado": 0.0}
        while not self._parar:
            agora = time.monotonic()
            atual = presenca()
            mudou = atual != assinatura
            assinatura = atual
            for nome, ler, espera in (("mouse", self._ler_mouse, REPETIR_MOUSE), ("teclado", self._ler_teclado, REPETIR_TECLADO)):
                pendente = bool(self.estado.get(nome, {}).get("aviso"))
                if mudou or agora - ultima[nome] >= INTERVALO or (pendente and agora - ultima[nome] >= espera):
                    if mudou:  # aparelho trocou de caminho (cabo/dongle/BT) ou sumiu: reabre do zero
                        (self._fechar_mouse if nome == "mouse" else self._fechar_teclado)()
                    ler()
                    ultima[nome] = time.monotonic()
            try:
                pedido = self._pedidos.get(timeout=PULSO)
            except queue.Empty:
                continue
            if pedido == "parar":
                break
            if isinstance(pedido, tuple):
                self._operar(*pedido[1:])
                ultima[pedido[1]] = time.monotonic()
            else:
                ultima = {"mouse": 0.0, "teclado": 0.0}
        for aparelho in (self._mouse, self._teclado):
            if aparelho:
                aparelho.fechar()

    # -- gravações

    def _marcar(self, nome, **campos):
        with self._trava:
            self.estado[nome] = {**self.estado.get(nome, {}), **campos}

    def _operar(self, aparelho, operacao, pronto, resultado):
        try:
            if aparelho == "mouse":
                if self._mouse is None:
                    self._mouse = Mouse.abrir(espera_max=ESPERA_MOUSE)
                m = self._mouse
                m.espera_max, m.ao_esperar = ESPERA_MAX, lambda: self._marcar("mouse", esperando_mouse=True)
                try:
                    operacao(m)
                finally:
                    m.espera_max, m.ao_esperar = ESPERA_MOUSE, None
                    self._marcar("mouse", esperando_mouse=False)
                self._ler_mouse()
            else:
                if self._teclado is None:
                    self._teclado = Teclado.abrir()
                operacao(self._teclado)
                self._ler_teclado()
            resultado["ok"] = True
        except (ErroPeriferico, ValueError, OSError) as e:
            resultado.update(ok=False, erro=str(e))
            if isinstance(e, OSError):
                self._fechar_mouse() if aparelho == "mouse" else self._fechar_teclado()
        finally:
            pronto.set()

    # -- leituras

    def _ler_mouse(self):
        anterior = self.estado.get("mouse", {})
        try:
            if self._mouse is None:
                self._mouse = Mouse.abrir(espera_max=ESPERA_MOUSE)
            m = self._mouse
            info = m.info()
            t = m.dpi()
            valores = {
                "conectado": True, "conexao": m.conexao, "bateria": info[9],
                "dpi": t.dpis, "niveis": t.niveis, "ativo": t.ativo,
                "polling": m.polling(), "cores": [c.hex().upper() for c in m.cores()],
                "sono_min": m.sono_min(), "botoes": [ler_funcao(b) for b in m.botoes()], "lido_em": _agora(),
            }
        except SemResposta as e:
            # dongle sem o mouse (parado, dormindo ou desligado): mantém o último conhecido
            valores = {**anterior, "conectado": self._mouse is not None,
                       "conexao": self._mouse.conexao if self._mouse else None,
                       "aviso": "Mouse parado ou dormindo: mexa o mouse (o app tenta de novo sozinho)"
                       if not str(e).startswith("falha") else str(e)}
        except ErroPeriferico as e:
            self._fechar_mouse()
            valores = {**anterior, "conectado": False, "aviso": str(e)}
        except OSError as e:  # aparelho removido no meio da leitura
            self._fechar_mouse()
            valores = {**anterior, "conectado": False, "aviso": f"Conexão perdida ({e})"}
        self._publicar("mouse", valores)

    def _fechar_mouse(self):
        if self._mouse:
            try:
                self._mouse.fechar()
            except OSError:
                pass
        self._mouse = None

    def _ler_teclado(self):
        anterior = self.estado.get("teclado", {})
        try:
            if self._teclado is None:
                self._teclado = Teclado.abrir()
            t = self._teclado
            versao = t.versao()
            b = t.ler_bloco()
            if hasattr(t, "escutar") and t.bateria is None:
                t.escutar(1.5)  # o aviso de bateria chega sozinho pelo dongle/Bluetooth
            ef, par = b[IDX_EFEITO], t.par_do_efeito(b)
            # as cores dos efeitos podem ter mudado fora do app (software oficial): lê do teclado uma vez por conexão
            # e atualiza a cópia. No Bluetooth não (leitura lenta, ~35 pacotes que se perdem).
            if not getattr(t, "cores_lidas", False) and t.conexao != "bluetooth":
                try:
                    lidas = bytes(t.ler_cores())
                    copia = cores_teclado()
                    if 400 <= len(lidas) <= 512:
                        guardar_cores_teclado(lidas + copia[len(lidas):])
                    t.cores_lidas = True
                except (ErroPeriferico, OSError):
                    pass
            cores = cores_teclado()
            nome = EFEITOS[ef - 1] if 1 <= ef <= len(EFEITOS) else ("Self-define" if ef == 0x15 else "OFF")
            valores = {
                "conectado": True, "conexao": t.conexao, "firmware": versao,
                "bateria": t.bateria if t.bateria is not None else anterior.get("bateria"),
                "efeito": ef, "efeito_nome": nome, "brilho": b[par], "velocidade": b[par + 1] >> 4,
                "colorido": b[par + 1] & 0x0F == COLORIDO,
                "cor": cor_do_efeito(cores, ef, min(b[par + 1] & 0x0F, 6)).hex().upper(),
                "sono_min": b[IDX_SONO] / 2, "debounce": b[IDX_DEBOUNCE] + 1, "lido_em": _agora(),
                "por_tecla": cores_por_tecla(),
                "teclas": teclas_trocadas(),
                "macros": macros_guardadas(),
                # brilho/velocidade/colorido e cor de cada efeito (1..18), para a tela mostrar ao escolher outro efeito
                "efeitos": {str(hw): {"brilho": b[56 + 2 * hw], "velocidade": b[57 + 2 * hw] >> 4,
                                      "colorido": b[57 + 2 * hw] & 0x0F == COLORIDO,
                                      "cor": cor_do_efeito(cores, hw, min(b[57 + 2 * hw] & 0x0F, 6)).hex().upper()}
                            for hw in range(1, 19)},
            }
        except ErroPeriferico as e:
            self._fechar_teclado()
            valores = {**anterior, "conectado": False, "aviso": "Teclado dormindo ou desligado: aperte uma tecla"
                       if "não respondeu" in str(e) else str(e)}
        except OSError as e:
            self._fechar_teclado()
            valores = {**anterior, "conectado": False, "aviso": f"Conexão perdida ({e})"}
        self._publicar("teclado", valores)

    def _fechar_teclado(self):
        if self._teclado:
            try:
                self._teclado.fechar()
            except OSError:
                pass
        self._teclado = None
