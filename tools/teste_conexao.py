"""Mede a estabilidade dos dongles (mouse e teclado): pedidos sem resposta, tempo de resposta e pacotes perdidos.

Uso:
    python tools/teste_conexao.py            # 60 pedidos ao mouse e 60 ao teclado (só leituras)
Rodar com o mouse e o teclado no modo 2.4G, antes e depois de mudar os dongles de lugar, e comparar.
"""
import statistics
import sys
import time
from pathlib import Path

import hid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from perifericos import mouse, teclado  # noqa: E402

N = 60


def resumo(nome, tempos, falhas, extra=""):
    if tempos:
        t = sorted(tempos)
        print(f"{nome}: {len(tempos)}/{len(tempos) + falhas} responderam | sem resposta: {falhas} | "
              f"tempo médio {statistics.mean(t):.1f} ms, mediana {statistics.median(t):.1f} ms, "
              f"pior {t[-1]:.1f} ms {extra}")
    else:
        print(f"{nome}: nenhuma resposta ({falhas} pedidos) {extra}")


def testar_mouse():
    caminho = next((d["path"] for d in hid.enumerate(*mouse.MODOS[1][1:]) if d["interface_number"] == mouse.INTERFACE), None)
    if not caminho:
        print("mouse: dongle não encontrado")
        return
    dev = hid.device()
    dev.open_path(caminho)
    tempos, falhas, desalinhados = [], 0, 0
    for i in range(N):
        cmd = 0x10 + i % 8  # leituras 0x10..0x17, como o software ao abrir
        while dev.read(64, 5):
            pass
        time.sleep(0.05)
        t0 = time.perf_counter()
        dev.write(b"\x00" + bytes([cmd]) + bytes(31))
        ok = False
        while time.perf_counter() - t0 < 0.8:
            r = bytes(dev.read(64, 50))
            if len(r) == 33 and r[0] == 0:
                r = r[1:]
            if len(r) == 32 and r[0] == cmd and r[1] == 0x00:
                tempos.append((time.perf_counter() - t0) * 1000)
                ok = True
                break
            if len(r) == 32 and r[0] == cmd and r[1] == 0x02:
                break  # dongle não alcançou o mouse
            if len(r) == 32 and r[24] == cmd:
                desalinhados += 1
                break
        if not ok:
            falhas += 1
    dev.close()
    resumo("mouse  (dongle)", tempos, falhas, f"| desalinhadas: {desalinhados}")
    if desalinhados:
        print("   o dongle do mouse saiu de sincronia — tire e recoloque o dongle antes de medir de novo")


def pacote(cmd):
    p = bytearray(20)
    p[0:5] = bytes([0x13, cmd, 1, 0, 0])
    p[19] = sum(p[:19]) & 0xFF
    return bytes(p)


def testar_teclado():
    caminho = next((d["path"] for d in hid.enumerate(*teclado.CAMINHOS_SEM_FIO[0][1:]) if d["usage_page"] == 0xFF02), None)
    if not caminho:
        print("teclado: dongle não encontrado")
        return
    dev = hid.device()
    dev.open_path(caminho)
    tempos, falhas = [], 0
    blocos_ok, perdidos = 0, 0
    for i in range(N):
        cmd = 0x44 if i % 4 == 3 else 0x05  # 1 em cada 4 pede o bloco inteiro (10 pacotes)
        while dev.read(64, 5):
            pass
        time.sleep(0.05)
        t0 = time.perf_counter()
        dev.write(pacote(cmd))
        vistos, total = set(), None
        while time.perf_counter() - t0 < 0.8:
            r = bytes(dev.read(64, 50))
            if len(r) >= 20 and r[0] == 0x13 and r[1] == cmd:
                total = r[2]
                vistos.add(r[3])
                if len(vistos) == total:
                    break
        if total and len(vistos) == total:
            tempos.append((time.perf_counter() - t0) * 1000)
            blocos_ok += cmd == 0x44
        else:
            falhas += 1
        if cmd == 0x44:
            perdidos += (total or 10) - len(vistos)
    dev.close()
    resumo("teclado (dongle)", tempos, falhas, f"| blocos completos: {blocos_ok}/{N // 4}, pacotes perdidos: {perdidos}")


if __name__ == "__main__":
    print(f"{N} pedidos a cada aparelho...\n")
    testar_mouse()
    testar_teclado()
