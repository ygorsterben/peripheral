"""Lê e altera o Aula F99 Pro pelo cabo, dongle ou Bluetooth (protocolo em perifericos/teclado.py).

Uso:
    python tools/teclado.py ler                  # conexão, firmware e bloco de configuração
    python tools/teclado.py efeito 11            # 1 = Fixed_on ... 11 = Neon_stream ... 18 = Rotating storm
    python tools/teclado.py brilho 2             # 0..4, do efeito atual
    python tools/teclado.py velocidade 2         # 0..4, do efeito atual
    python tools/teclado.py sono 5               # 1 / 1.5 / 2 / 3 / 4 / 5 / 10 / 15 / 20 min
    python tools/teclado.py debounce 2           # estágio 1..4
    python tools/teclado.py cor FF00FF           # cor do efeito atual (efeitos com cor única)
    python tools/teclado.py colorido sim         # sim / nao: cores aleatórias no efeito atual
Ao trocar de efeito ou de cor, as outras cores vêm do perfil do software oficial (as que o usuário escolheu).
Cada alteração lê o bloco, muda o valor, grava e relê para conferir (como o software oficial).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from perifericos import ErroPeriferico  # noqa: E402
from perifericos.teclado import (EFEITOS, IDX_DEBOUNCE, IDX_EFEITO, IDX_SONO, SONO_MIN, Teclado,  # noqa: E402
                                 cor_do_efeito, cores_atuais, mudar_cor)


def mostrar(t):
    print(f"firmware:   V{t.versao()}")
    b = t.ler_bloco()
    ef, par = b[IDX_EFEITO], t.par_do_efeito(b)
    nome = EFEITOS[ef - 1] if 1 <= ef <= len(EFEITOS) else ("Self-define" if ef == 0x15 else "?")
    print(f"efeito:     {ef} ({nome})  brilho {b[par]}  velocidade {b[par + 1] >> 4}  "
          f"{'colorido' if b[par + 1] & 0x0F else 'cor única'}")
    print(f"cor:        #{cor_do_efeito(cores_atuais(), ef).hex().upper()} (do perfil do software oficial)")
    print(f"sono:       {b[IDX_SONO] / 2:g} min")
    print(f"debounce:   estágio {b[IDX_DEBOUNCE] + 1}")
    for i in range(0, 128, 32):
        print(f"bloco[{i:3}]: {b[i:i + 32].hex(' ')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="acao", required=True)
    sub.add_parser("ler")
    sub.add_parser("efeito").add_argument("numero", type=int, choices=range(1, len(EFEITOS) + 1))
    sub.add_parser("brilho").add_argument("valor", type=int, choices=range(5))
    sub.add_parser("velocidade").add_argument("valor", type=int, choices=range(5))
    sub.add_parser("sono").add_argument("minutos", type=float, choices=SONO_MIN)
    sub.add_parser("debounce").add_argument("estagio", type=int, choices=range(1, 5))
    sub.add_parser("cor").add_argument("rgb", help="RRGGBB")
    sub.add_parser("colorido").add_argument("ligar", choices=["sim", "nao"])
    args = ap.parse_args()

    try:
        with Teclado.abrir() as t:
            print(f"(F99 Pro pelo {t.conexao})")
            if args.acao == "ler":
                mostrar(t)
                return
            if args.acao == "cor":
                rgb = bytes.fromhex(args.rgb)
                if len(rgb) != 3:
                    raise SystemExit("a cor deve ter 6 dígitos hexadecimais, ex.: FF00FF")
                t.alterar(cores=mudar_cor(cores_atuais(), t.ler_bloco()[IDX_EFEITO], rgb))
                print("cor: OK, o teclado recebeu (o teclado não devolve as cores; confira olhando).")
                return
            if args.acao == "colorido":
                t.alterar(colorido=args.ligar == "sim")
                print("colorido: OK, o teclado confirmou.")
                return
            mudanca = {"efeito": {"efeito": getattr(args, "numero", None)},
                       "brilho": {"brilho": getattr(args, "valor", None)},
                       "velocidade": {"velocidade": getattr(args, "valor", None)},
                       "sono": {"sono_min": getattr(args, "minutos", None)},
                       "debounce": {"debounce": getattr(args, "estagio", None)}}[args.acao]
            t.alterar(**mudanca)
            print(f"{args.acao}: OK, o teclado confirmou.")
    except (ErroPeriferico, ValueError) as e:
        raise SystemExit(f"ERRO: {e}")


if __name__ == "__main__":
    main()
