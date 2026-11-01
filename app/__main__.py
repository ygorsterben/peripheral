"""Inicia o Gerenciador de Periféricos: janela (pywebview) + ícone na bandeja (pystray) + carteiro (aparelhos).

Uso:  py -m app            (a partir da pasta do projeto)
Fechar a janela só a esconde: o app continua na bandeja. "Sair" no menu da bandeja encerra.
"""
import json
import sys
import threading
from pathlib import Path

import pystray
import webview
from PIL import Image, ImageDraw

from perifericos.mouse import FUNCOES_ATALHO, FUNCOES_MIDIA, BOTOES_PADRAO, arredondar_dpi, montar_funcao

from . import NOME, VERSAO
from perifericos.teclado import (ENTRADA_SEM_FUNCAO, entrada_macro, entrada_midia, entrada_tecla, montar_macros,
                                 montar_tabela_teclas, mudar_cor)

from .servico import (PASTA_DADOS, Carteiro, cores_por_tecla, cores_teclado, guardar_cores_por_tecla,
                      guardar_cores_teclado, guardar_macros, guardar_teclas_trocadas, macros_guardadas)

ARQUIVO_PREFERENCIAS = PASTA_DADOS / "preferencias.json"
from .sistema import definir_inicio_com_windows, inicia_com_windows, instancia_unica, registrar


def pasta_ui():
    """Pasta da interface, também dentro do .exe do PyInstaller (sys._MEIPASS)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "app" / "ui"


def imagem_icone(tamanho=64):
    """Ícone do app (proposta A, "Central"): um centro cobalto ligado a quatro aparelhos, sobre grafite.
    Desenhado em 4x e reduzido, para bordas lisas até em 16 px."""
    g = 4 * max(tamanho, 64)
    s = g / 64
    img = Image.new("RGBA", (g, g), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # fundo: quadrado arredondado grafite com leve degradê
    fundo = Image.new("RGBA", (g, g))
    fd = ImageDraw.Draw(fundo)
    for y in range(g):
        f = y / g
        fd.line((0, y, g, y), fill=(round(43 - 21 * f), round(48 - 24 * f), round(54 - 27 * f), 255))
    mascara = Image.new("L", (g, g), 0)
    ImageDraw.Draw(mascara).rounded_rectangle((2 * s, 2 * s, 62 * s, 62 * s), radius=14 * s, fill=255)
    img.paste(fundo, (0, 0), mascara)
    # ligações, aparelhos (pontos alumínio) e o centro (cobalto com anel)
    for x, y in ((17, 17), (47, 17), (17, 47), (47, 47)):
        d.line((32 * s, 32 * s, x * s, y * s), fill=(143, 163, 240, 255), width=round(3.2 * s))
    for x, y in ((17, 17), (47, 17), (17, 47), (47, 47)):
        d.ellipse(((x - 5.5) * s, (y - 5.5) * s, (x + 5.5) * s, (y + 5.5) * s), fill=(228, 230, 227, 255))
    d.ellipse((20.3 * s, 20.3 * s, 43.7 * s, 43.7 * s), fill=(228, 230, 227, 255))
    d.ellipse((22.5 * s, 22.5 * s, 41.5 * s, 41.5 * s), fill=(38, 71, 201, 255))
    return img.resize((tamanho, tamanho), Image.LANCZOS)


class Api:
    """Funções que a interface (JavaScript) chama: window.pywebview.api.<nome>()."""

    def __init__(self, carteiro):
        self._carteiro = carteiro

    def estado(self):
        return self._carteiro.ler_estado()

    def atualizar(self):
        self._carteiro.atualizar()
        return True

    def versao(self):
        return {"nome": NOME, "versao": VERSAO}

    def registrar(self, texto):
        """Erros e avisos da interface vão para o arquivo de registro do app (ver sistema.registrar)."""
        registrar(f"[interface] {texto}")
        return True

    # -- preferências da interface (%APPDATA%, porque a janela não guarda nada entre aberturas)

    def preferencias(self):
        try:
            return json.loads(ARQUIVO_PREFERENCIAS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def salvar_preferencia(self, chave, valor):
        prefs = self.preferencias()
        prefs[str(chave)] = valor
        ARQUIVO_PREFERENCIAS.parent.mkdir(parents=True, exist_ok=True)
        ARQUIVO_PREFERENCIAS.write_text(json.dumps(prefs, ensure_ascii=False, indent=1), encoding="utf-8")
        return True

    # -- mouse (cada função grava, relê e devolve {"ok": bool, "erro": str})

    def mouse_dpi_ativo(self, indice):
        return self._carteiro.executar("mouse", lambda m: m.gravar_dpi(ativo=int(indice)))

    def mouse_tabela(self, dpis, niveis, ativo, cores):
        def gravar(m):
            m.gravar_dpi([arredondar_dpi(int(d)) for d in dpis], int(ativo), int(niveis))
            novas = [bytes.fromhex(c) for c in cores]
            if novas != m.cores():
                m.gravar_cores(novas)
        return self._carteiro.executar("mouse", gravar)

    def mouse_polling(self, hz):
        return self._carteiro.executar("mouse", lambda m: m.gravar_polling(int(hz)))

    def mouse_sono(self, minutos):
        return self._carteiro.executar("mouse", lambda m: m.gravar_sono(int(minutos)))

    # -- teclado

    def teclado_luz(self, efeito, brilho, velocidade, colorido, cor):
        """Aplica efeito + brilho/velocidade/colorido + cor de uma vez (como o software: bloco e depois cores)."""
        efeito = int(efeito)
        if not 1 <= efeito <= 18:
            return {"ok": False, "erro": "efeito ainda não suportado pelo app"}

        def gravar(t):
            cores = cores_teclado()
            if cor:
                cores = mudar_cor(cores, efeito, bytes.fromhex(cor))
            t.alterar(efeito=efeito, brilho=int(brilho), velocidade=int(velocidade), colorido=bool(colorido),
                      cores=cores)
            guardar_cores_teclado(cores)
        return self._carteiro.executar("teclado", gravar, limite=60)

    def teclado_por_tecla(self, cores=None):
        """Liga a luz por tecla com {tecla: "RRGGBB"} (sem cores = a cópia guardada) e guarda a cópia."""
        cores = {str(k): str(v).upper() for k, v in (cores or cores_por_tecla()).items() if len(str(v)) == 6}

        def gravar(t):
            t.aplicar_por_tecla(cores)
            guardar_cores_por_tecla(cores)
        return self._carteiro.executar("teclado", gravar, limite=90)

    def teclado_teclas(self, trocas, macros=None):
        """Grava a tabela de teclas: {tecla: {"tipo": "tecla"|"midia"|"atalho"|"macro"|"desativar", "valor": ...}}.
        Teclas fora de `trocas` ficam no padrão. `macros` = [{"nome", "eventos": [[solta, ms, tecla], ...]}] (sem
        ele, vale a cópia guardada); tipo "macro" tem valor = posição na lista."""
        try:
            macros = macros_guardadas() if macros is None else [
                {"nome": str(m["nome"]), "eventos": [[bool(e[0]), int(e[1]), int(e[2])] for e in m["eventos"]]}
                for m in macros]
            bloco_macros = montar_macros([(m["nome"], m["eventos"]) for m in macros]) if macros else None
            entradas = {}
            for nome, f in (trocas or {}).items():
                if f["tipo"] == "macro":
                    if not 0 <= int(f["valor"]) < len(macros):
                        raise ValueError(f"a tecla {nome} aponta para uma macro que não existe")
                    entradas[nome] = entrada_macro(int(f["valor"]), int(f.get("vezes", 1)), str(f.get("modo", "vezes")))
                elif f["tipo"] == "tecla":
                    entradas[nome] = entrada_tecla(int(f["valor"]), int(f.get("modificadores", 0)))
                elif f["tipo"] in ("midia", "atalho"):
                    tabela = FUNCOES_MIDIA if f["tipo"] == "midia" else FUNCOES_ATALHO
                    entradas[nome] = entrada_midia(tabela[f["valor"]])
                elif f["tipo"] == "desativar":
                    entradas[nome] = ENTRADA_SEM_FUNCAO
                else:
                    raise ValueError(f"tipo desconhecido: {f['tipo']}")
            tabela_bytes = montar_tabela_teclas(entradas)
        except (KeyError, ValueError, TypeError) as e:
            return {"ok": False, "erro": f"troca inválida: {e}"}

        usa_macro = bool(bloco_macros) and any(f["tipo"] == "macro" for f in (trocas or {}).values())

        def gravar(t):
            if usa_macro:
                t.gravar_macros(bloco_macros)  # macros antes da tabela: se falhar, nenhuma tecla aponta para macro ausente
            t.gravar_teclas(tabela_bytes)
            guardar_teclas_trocadas(trocas or {})
            guardar_macros(macros)
        return self._carteiro.executar("teclado", gravar, limite=90)

    def teclado_sono(self, minutos):
        return self._carteiro.executar("teclado", lambda t: t.alterar(sono_min=float(minutos)), limite=60)

    def teclado_debounce(self, estagio):
        return self._carteiro.executar("teclado", lambda t: t.alterar(debounce=int(estagio)), limite=60)

    def mouse_botao(self, indice, funcao):
        """funcao = {"tipo": "clique"|"tecla"|"midia"|"atalho"|"dpi"|"desativar"|"padrao", "valor": ..., ...}"""
        try:
            indice = int(indice)
            if funcao.get("tipo") == "padrao":
                dados = BOTOES_PADRAO[indice]
            else:
                dados = montar_funcao(funcao["tipo"], funcao.get("valor"), funcao.get("modificadores", 0))
        except (KeyError, ValueError, IndexError) as e:
            return {"ok": False, "erro": f"função inválida: {e}"}
        return self._carteiro.executar("mouse", lambda m: m.gravar_botao(indice, dados))


def main():
    no_inicio = "--bandeja" in sys.argv  # iniciado com o Windows: só o ícone, sem abrir a janela
    pedidos = {"mostrar": False}
    if not instancia_unica(lambda: mostrar_janela()):
        return  # já estava aberto: a outra instância mostra a janela
    sys.excepthook = lambda tipo, valor, tb: registrar(f"ERRO {tipo.__name__}: {valor}")
    threading.excepthook = lambda a: registrar(f"ERRO na thread {a.thread.name}: {a.exc_type.__name__}: {a.exc_value}")
    registrar(f"{NOME} {VERSAO} iniciado{' (bandeja)' if no_inicio else ''}")

    carteiro = Carteiro()
    carteiro.start()
    saindo = {"sim": False}

    janela = webview.create_window(
        f"{NOME} — beta {VERSAO}", url=str(pasta_ui() / "index.html"), js_api=Api(carteiro),
        width=1180, height=820, min_size=(1000, 700), background_color="#E4E6E3", hidden=no_inicio)

    def ao_fechar():
        if saindo["sim"]:
            return True
        janela.hide()  # fica na bandeja
        return False

    janela.events.closing += ao_fechar

    def mostrar_janela(icone=None, item=None):
        janela.show()
        janela.restore()

    def sair(icone, item):
        saindo["sim"] = True
        carteiro.parar()
        icone.stop()
        janela.destroy()

    def texto(nome, rotulo):
        def gerar(item):
            e = carteiro.ler_estado().get(nome, {})
            if not e.get("conectado"):
                return f"{rotulo}: desconectado"
            bat = e.get("bateria")
            return f"{rotulo}: {bat} %" if bat is not None else f"{rotulo}: conectado"
        return gerar

    # --- atalhos rápidos (gravam em segundo plano pelo carteiro) ---
    def em_fundo(funcao):
        threading.Thread(target=funcao, daemon=True).start()

    def itens_dpi():
        m = carteiro.ler_estado().get("mouse", {})
        if not m.get("dpi"):
            return [pystray.MenuItem("Mouse desconectado", None, enabled=False)]
        def item(i):
            return pystray.MenuItem(f"{m['dpi'][i]:,}".replace(",", ".") + " DPI",
                                    lambda: em_fundo(lambda: carteiro.executar("mouse", lambda x: x.gravar_dpi(ativo=i))),
                                    checked=lambda _: carteiro.ler_estado().get("mouse", {}).get("ativo") == i, radio=True)
        return [item(i) for i in range(m.get("niveis", 6))]

    def itens_brilho():
        t = carteiro.ler_estado().get("teclado", {})
        if t.get("brilho") is None:
            return [pystray.MenuItem("Teclado desconectado", None, enabled=False)]
        def item(v):
            return pystray.MenuItem("Desligada" if v == 0 else f"Brilho {v}",
                                    lambda: em_fundo(lambda: carteiro.executar("teclado", lambda x: x.alterar(brilho=v), limite=60)),
                                    checked=lambda _: carteiro.ler_estado().get("teclado", {}).get("brilho") == v, radio=True)
        return [item(v) for v in range(5)]

    def alternar_inicio(icone, item):
        definir_inicio_com_windows(not inicia_com_windows())

    menu = pystray.Menu(
        pystray.MenuItem("Abrir", mostrar_janela, default=True),
        pystray.MenuItem(texto("mouse", "Mouse"), None, enabled=False),
        pystray.MenuItem(texto("teclado", "Teclado"), None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("DPI do mouse", pystray.Menu(itens_dpi)),
        pystray.MenuItem("Luz do teclado", pystray.Menu(itens_brilho)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Iniciar com o Windows", alternar_inicio, checked=lambda _: inicia_com_windows()),
        pystray.MenuItem("Sair", sair),
    )
    icone = pystray.Icon("gerenciador_perifericos", imagem_icone(), f"{NOME} (beta {VERSAO})", menu)
    icone.run_detached()
    webview.start()
    carteiro.parar()
    if not saindo["sim"]:
        icone.stop()
    registrar("encerrado")


if __name__ == "__main__":
    main()
