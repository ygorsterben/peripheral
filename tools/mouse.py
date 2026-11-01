"""Lê e altera o BK-R6X pelo cabo ou pelo dongle (protocolo em perifericos/mouse.py e docs/protocolo_mouse.md).

Uso:
    python tools/mouse.py ler                          # estado completo
    python tools/mouse.py polling 1000                 # 125 / 250 / 500 / 1000 Hz
    python tools/mouse.py dpi 4                        # só troca o nível ativo (índice 0-5)
    python tools/mouse.py tabela 800 1600 2400 3200 4800 12000 --ativo 4 --niveis 6
    python tools/mouse.py sono 15                      # 1 / 2 / 5 / 6 / 10 / 15 / 20 / 30 min
    python tools/mouse.py botao 3 tecla B              # índice 3 (= "Key 5", lateral de trás) digita B
    python tools/mouse.py botao 3 desativar | padrao
    python tools/mouse.py botao 3 midia E9             # código consumer HID em hex (E9 = Volume +, 6F = Brilho +)
    python tools/mouse.py cor 4 FFFFFF                 # cor do LED do nível de DPI 4; 'padrao' restaura
Toda alteração é conferida relendo o mouse. Pelo dongle, mexa o mouse se ele pedir (parado ele não responde).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from perifericos import ErroPeriferico  # noqa: E402
from perifericos.mouse import (BOTAO_DESATIVADO, BOTOES_PADRAO, CORES_PADRAO, POLLING, SONO_MIN,  # noqa: E402
                               Mouse, botao_midia, botao_tecla, descrever_botao)


def codigo_tecla(nome):
    """Código HID de A-Z e 0-9 (o suficiente para testes)."""
    nome = nome.upper()
    if len(nome) == 1 and "A" <= nome <= "Z":
        return 0x04 + ord(nome) - ord("A")
    if len(nome) == 1 and "1" <= nome <= "9":
        return 0x1E + ord(nome) - ord("1")
    if nome == "0":
        return 0x27
    raise SystemExit(f"tecla não suportada (por enquanto só A-Z e 0-9): {nome}")


def mostrar(m):
    info = m.info()
    print(f"info (0x10):  {info.hex(' ')}  | modelo {info[0:4].decode('ascii', 'replace')!r}, bateria {info[9]} %")
    for i, b in enumerate(m.botoes()):
        print(f"botão {i}:      {b.hex(' ')}  | {descrever_botao(b)}")
    print(f"polling:      {m.polling()} Hz")
    t = m.dpi()
    print(f"DPI:          {t.niveis} níveis, ativo = índice {t.ativo} | " + " / ".join(map(str, t.dpis)))
    print("cores LED:    " + " ".join(c.hex().upper() for c in m.cores()))
    print(f"sono:         {m.sono_min():g} min")
    for cmd in (0x15, 0x16):
        print(f"0x{cmd:02x} (?):     {m.ler(cmd).hex(' ')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="acao", required=True)
    sub.add_parser("ler")
    sub.add_parser("polling").add_argument("hz", type=int, choices=sorted(POLLING))
    sub.add_parser("dpi").add_argument("ativo", type=int, choices=range(6))
    t = sub.add_parser("tabela")
    t.add_argument("dpis", type=int, nargs=6)
    t.add_argument("--ativo", type=int)
    t.add_argument("--niveis", type=int, choices=range(1, 7))
    sub.add_parser("sono").add_argument("minutos", type=int, choices=SONO_MIN)
    b = sub.add_parser("botao")
    b.add_argument("indice", type=int, choices=range(1, 6), help="1-5 (o 0, clique esquerdo, é travado)")
    b.add_argument("funcao", choices=["tecla", "midia", "desativar", "padrao"])
    b.add_argument("tecla", nargs="?", help="tecla (A-Z, 0-9) ou código de mídia em hex")
    c = sub.add_parser("cor")
    c.add_argument("nivel", type=int, choices=range(6))
    c.add_argument("rgb", help="RRGGBB, ex.: FFFFFF, ou 'padrao'")
    args = ap.parse_args()

    try:
        with Mouse.abrir(ao_esperar=lambda: print("Mexa o mouse: parado, ele não responde pelo dongle...")) as m:
            print(f"(BK-R6X pelo {m.conexao})")
            if args.acao == "ler":
                mostrar(m)
                return
            if args.acao == "polling":
                m.gravar_polling(args.hz)
            elif args.acao == "dpi":
                m.gravar_dpi(ativo=args.ativo)
            elif args.acao == "tabela":
                m.gravar_dpi(args.dpis, args.ativo, args.niveis)
            elif args.acao == "sono":
                m.gravar_sono(args.minutos)
            elif args.acao == "botao":
                if args.funcao == "padrao":
                    funcao = BOTOES_PADRAO[args.indice]
                elif args.funcao == "desativar":
                    funcao = BOTAO_DESATIVADO
                elif not args.tecla:
                    raise SystemExit("informe a tecla ou o código, ex.: botao 3 tecla B / botao 3 midia E9")
                elif args.funcao == "midia":
                    funcao = botao_midia(int(args.tecla, 16))
                else:
                    funcao = botao_tecla(codigo_tecla(args.tecla))
                m.gravar_botao(args.indice, funcao)
            elif args.acao == "cor":
                rgb = CORES_PADRAO[args.nivel] if args.rgb.lower() == "padrao" else bytes.fromhex(args.rgb)
                if len(rgb) != 3:
                    raise SystemExit("a cor deve ter 6 dígitos hexadecimais, ex.: FFFFFF")
                m.gravar_cor(args.nivel, rgb)
            print(f"{args.acao}: OK, o mouse confirmou.")
    except (ErroPeriferico, ValueError) as e:
        raise SystemExit(f"ERRO: {e}")


if __name__ == "__main__":
    main()
