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

from .efeitos import EFEITOS as EFEITOS_APP

INTERVALO = 60          # segundos entre leituras automáticas
QUADROS_POR_S = 20      # cor ao vivo (efeitos do app); o software oficial manda ~20 quadros/s pelo cabo
REABRIR_VIVO = 2        # efeito do app ligado sem teclado: tenta de novo a cada tantos segundos
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
        self._trava_pedidos = threading.Lock()  # pedido "começou" × "abandonado" (ver _esperar)
        self._mouse = None
        self._teclado = None
        self._parar = False
        self.estado = self._carregar()
        # efeito do app (cor ao vivo): fica "ligado" mesmo sem teclado; manda quadros quando dá
        self._efeito = None          # objeto de app/efeitos.py
        self._efeito_info = None     # {"nome", "opcoes", "situacao": "ligado"|"esperando", "erro"}
        self.ultimo_quadro = None
        self._enviou_quadro = False  # algum quadro chegou ao teclado desde que o efeito ligou

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
            e = json.loads(json.dumps(self.estado))
            e.setdefault("teclado", {})["efeito_app"] = dict(self._efeito_info) if self._efeito_info else None
            return e

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
        return self._esperar(pronto, resultado, limite, "O aparelho demorou demais para responder.")

    def _esperar(self, pronto, resultado, limite, erro, descartavel=True):
        """Espera o carteiro. Se o limite estoura e o pedido ainda não começou, ele é abandonado e não roda mais
        (senão a tela mostraria erro e a mudança aconteceria depois, sem ninguém saber). Se já começou, espera
        terminar e devolve o resultado de verdade. `descartavel=False` (desligar) espera sempre."""
        if pronto.wait(limite):
            return resultado
        with self._trava_pedidos:
            if descartavel and not resultado.get("comecou"):
                resultado["abandonado"] = True
                return {"ok": False, "erro": erro}
        pronto.wait()  # já começou (ou não pode ser descartado): o resultado é o que conta
        return resultado if "ok" in resultado else {"ok": False, "erro": erro}

    def parar(self, esperar=5):
        """Encerra o laço. Com um efeito do app ligado, devolve antes o teclado ao efeito gravado nele."""
        self._parar = True
        self._pedidos.put("parar")
        if esperar and self.is_alive() and threading.current_thread() is not self:
            self.join(esperar)

    def ligar_efeito(self, nome, opcoes, limite=15):
        """Liga (ou ajusta, se já é o mesmo) um efeito do app. {"ok", "erro"}."""
        pronto, resultado = threading.Event(), {}
        self._pedidos.put(("vivo", nome, dict(opcoes or {}), pronto, resultado))
        return self._esperar(pronto, resultado, limite, "O app demorou demais para ligar o efeito.")

    def desligar_efeito(self, limite=30):
        pronto, resultado = threading.Event(), {}
        self._pedidos.put(("desligar", None, None, pronto, resultado))
        return self._esperar(pronto, resultado, limite, "O teclado demorou demais para responder.", descartavel=False)

    def run(self):
        """Laço principal: a cada PULSO s confere se algum aparelho entrou ou saiu (só lista a USB, sem falar
        com eles) e relê quando muda, quando a interface pede, a cada INTERVALO s, ou de tempos em tempos enquanto
        o mouse está parado / o teclado dormindo. Com um efeito do app ligado, manda QUADROS_POR_S quadros/s."""
        assinatura, ultima = None, {"mouse": 0.0, "teclado": 0.0}
        proximo_pulso = proximo_quadro = 0.0
        while not self._parar:
            agora = time.monotonic()
            if agora >= proximo_pulso:
                proximo_pulso = agora + PULSO
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
            espera = proximo_pulso - time.monotonic()
            if self._efeito:
                espera = min(espera, proximo_quadro - time.monotonic())
            try:
                pedido = self._pedidos.get(timeout=max(0.0, espera))
            except queue.Empty:
                pedido = None
            if pedido == "parar":
                break
            if isinstance(pedido, tuple):
                with self._trava_pedidos:  # junto com _esperar: ou começa aqui, ou foi abandonado lá
                    abandonado = pedido[-1].get("abandonado")
                    pedido[-1]["comecou"] = not abandonado
            if isinstance(pedido, tuple) and abandonado:
                pedido[-2].set()  # a tela já desistiu de esperar: não roda
            elif isinstance(pedido, tuple):
                tipo = pedido[0]
                if tipo == "op":
                    self._operar(*pedido[1:])
                    ultima[pedido[1]] = time.monotonic()
                elif tipo == "vivo":
                    self._ligar_efeito(*pedido[1:])
                elif tipo == "desligar":
                    self._desligar_efeito(*pedido[3:])
            elif pedido == "atualizar":
                ultima = {"mouse": 0.0, "teclado": 0.0}
                proximo_pulso = 0.0
            if self._efeito and time.monotonic() >= proximo_quadro:
                proximo_quadro = time.monotonic() + self._mandar_quadro()
        self._desligar_efeito(None, {})
        for aparelho in (self._mouse, self._teclado):
            if aparelho:
                aparelho.fechar()

    # -- efeitos do app (cor ao vivo)

    def _ligar_efeito(self, nome, opcoes, pronto, resultado):
        try:
            classe = EFEITOS_APP.get(nome)
            if classe is None:
                raise ValueError(f"efeito desconhecido: {nome}")
            classe.validar(**opcoes)  # antes de mexer no efeito que está rodando
            if self._efeito and self._efeito_info["nome"] == nome:
                self._efeito.ajustar(**opcoes)
            else:
                novo = classe(**opcoes)
                if self._efeito:
                    self._efeito.parar()
                self._efeito = novo
            with self._trava:
                self._efeito_info = {"nome": nome, "opcoes": opcoes, "situacao": "esperando", "erro": None}
            resultado["ok"] = True
        except (ValueError, TypeError) as e:
            resultado.update(ok=False, erro=str(e))
        finally:
            pronto.set()

    def _desligar_efeito(self, pronto, resultado):
        """Para o efeito e devolve o teclado ao efeito gravado: relê o bloco de configuração e regrava (como o
        software oficial ao sair do modo música). Relê na hora para não desfazer o que mudou enquanto estava ligado."""
        efeito, self._efeito = self._efeito, None
        enviou, self._enviou_quadro = self._enviou_quadro, False
        with self._trava:
            self._efeito_info = None
        self.ultimo_quadro = None
        try:
            if efeito:
                efeito.parar()
            if enviou:  # só regrava se algum quadro chegou ao teclado (no Bluetooth nunca chega)
                if self._teclado is None:
                    self._teclado = Teclado.abrir()
                self._teclado.gravar_bloco(self._teclado.ler_bloco())
            resultado["ok"] = True
        except (ErroPeriferico, OSError) as e:
            resultado.update(ok=False, erro=str(e))
            self._fechar_teclado()
        finally:
            if pronto:
                pronto.set()

    def _mandar_quadro(self):
        """Manda um quadro; devolve quantos segundos esperar até o próximo."""
        def marcar(situacao, erro=None):
            with self._trava:
                if self._efeito_info:
                    self._efeito_info.update(situacao=situacao, erro=erro)
        inicio = time.monotonic()
        try:
            quadro = self._efeito.quadro()
            self.ultimo_quadro = quadro
            if self._teclado is None:
                self._teclado = Teclado.abrir()
            self._teclado.quadro_ao_vivo(quadro)
            self._enviou_quadro = True
            marcar("ligado", getattr(self._efeito, "erro", None))
            # o receptor leva ~6 ms por pacote: desconta o tempo gasto para não pedir mais do que ele dá conta
            return max(0.01, 1 / QUADROS_POR_S - (time.monotonic() - inicio))
        except ErroPeriferico as e:
            marcar("esperando", str(e))
            if "Bluetooth" in str(e):
                return REABRIR_VIVO * 5
            self._fechar_teclado()
            return REABRIR_VIVO
        except OSError as e:
            marcar("esperando", str(e))
            self._fechar_teclado()
            return REABRIR_VIVO
        except Exception as e:  # erro do próprio efeito: não pode derrubar a thread do carteiro
            marcar("esperando", f"erro no efeito: {e}")
            return REABRIR_VIVO

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
