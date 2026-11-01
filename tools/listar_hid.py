"""Lista as interfaces HID do teclado Aula F99 Pro e do mouse BK-R6X em todos os modos de conexão."""
import sys
from pathlib import Path

import hid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from perifericos import mouse, teclado  # noqa: E402

DISPOSITIVOS = {(vid, pid): f"BK-R6X ({nome})" for nome, vid, pid in mouse.MODOS}
DISPOSITIVOS[(teclado.VID_CABO, teclado.PID_CABO)] = "F99 Pro (cabo)"
DISPOSITIVOS.update({(vid, pid): f"F99 Pro ({nome})" for nome, vid, pid in teclado.CAMINHOS_SEM_FIO})
DISPOSITIVOS[(0x17EF, 0x61DC)] = "BK-R6X (bluetooth, 'GM-2')"

for d in sorted(hid.enumerate(), key=lambda d: (d["vendor_id"], d["product_id"], d["interface_number"], d["usage_page"])):
    nome = DISPOSITIVOS.get((d["vendor_id"], d["product_id"]))
    if nome:
        vendor = " <-- fornecedor" if d["usage_page"] >= 0xFF00 else ""
        print(f"{nome:30} if={d['interface_number']} usage_page=0x{d['usage_page']:04X} usage=0x{d['usage']:04X} "
              f"prod={d['product_string']!r}{vendor}")
