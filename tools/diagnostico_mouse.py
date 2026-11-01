"""Diagnóstico do dongle do mouse: mostra os pacotes crus e acompanha a sincronia. Só leituras (nada é gravado).

Uso:
    python tools/diagnostico_mouse.py sonda                         # 0x10..0x17, um a um, com todos os pacotes
    python tools/diagnostico_mouse.py sonda --cmds 11,12 --pausa 0 --rodadas 5
    python tools/diagnostico_mouse.py monitor 90                    # 1 leitura por segundo durante 90 s

Classificação: OK (alinhado), ESPERA (status 01, mouse parado), SEM_MOUSE (status 02), DESLOCADO (dessincronia).
No monitor, o número depois da barra é o deslocamento do anel de 36 bytes (0 = alinhado; 6, 12, ... = deslocado).
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from perifericos import ErroPeriferico  # noqa: E402
from perifericos.mouse import TAMANHO, Mouse  # noqa: E402

STATUS = {0: "OK", 1: "ESPERA", 2: "SEM_MOUSE"}


def ler_pacote(dev, timeout_ms):
    r = bytes(dev.read(64, timeout_ms))
    if len(r) == TAMANHO + 1 and r[0] == 0:
        r = r[1:]
    return r


def classificar(r, cmd):
    """(rótulo, deslocamento) de um pacote em resposta ao pedido `cmd`."""
    if len(r) != TAMANHO:
        return f"tamanho {len(r)}", None
    if r[0] == cmd and r[1] in STATUS:
        return STATUS[r[1]], 0
    for k in range(1, TAMANHO - 1):  # início da resposta atual depois de 4 zeros = anel deslocado
        if r[k] == cmd and r[k + 1] in STATUS and all(b == 0 for b in r[max(0, k - 4):k]):
            return "DESLOCADO", 36 - k
    return f"outro (cmd {r[0]:02x})", None


def pedir(dev, cmd):
    dev.write(b"\x00" + bytes([cmd]) + bytes(TAMANHO - 1))


def sonda(dev, args):
    cmds = [int(c, 16) for c in args.cmds.split(",")]
    t0, resumo = time.monotonic(), {}
    for _ in range(args.rodadas):
        for cmd in cmds:
            time.sleep(args.pausa)
            pedir(dev, cmd)
            print(f"{time.monotonic() - t0:7.3f}  -> {cmd:02x}")
            fim, achou = time.monotonic() + args.espera, None
            while time.monotonic() < fim:
                r = ler_pacote(dev, 50)
                if not r:
                    if achou in ("OK", "SEM_MOUSE", "DESLOCADO"):
                        break
                    continue
                rotulo, _ = classificar(r, cmd)
                print(f"{time.monotonic() - t0:7.3f}  <- {rotulo:10s} {r.hex(' ')}")
                if rotulo != "ESPERA":
                    achou = rotulo
            resumo.setdefault(cmd, []).append(achou or "NADA")
    print("\nresumo:")
    for cmd, rs in resumo.items():
        print(f"  {cmd:02x}: {' '.join(rs)}")


def monitor(dev, args):
    t0, ultimo = time.monotonic(), None
    while time.monotonic() - t0 < args.segundos:
        pedir(dev, 0x12)
        fim, estados = time.monotonic() + 1.0, []
        while time.monotonic() < fim:
            r = ler_pacote(dev, 50)
            if r:
                rotulo, d = classificar(r, 0x12)
                estados.append(f"{rotulo.lower()}/{d}")
        txt = " ".join(estados) or "nada"
        if txt != ultimo:
            print(f"{time.monotonic() - t0:6.1f}s  {txt}", flush=True)
            ultimo = txt
    print("fim")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="acao", required=True)
    s = sub.add_parser("sonda")
    s.add_argument("--cmds", default="10,11,12,13,14,15,16,17")
    s.add_argument("--pausa", type=float, default=0.3, help="segundos entre pedidos")
    s.add_argument("--espera", type=float, default=1.5, help="segundos lendo pacotes depois de cada pedido")
    s.add_argument("--rodadas", type=int, default=1)
    sub.add_parser("monitor").add_argument("segundos", type=float, nargs="?", default=90)
    args = ap.parse_args()
    try:
        with Mouse.abrir() as m:
            print(f"(BK-R6X pelo {m.conexao})")
            while m.dev.read(64, 10):
                pass
            (sonda if args.acao == "sonda" else monitor)(m.dev, args)
    except ErroPeriferico as e:
        raise SystemExit(f"ERRO: {e}")


if __name__ == "__main__":
    main()
