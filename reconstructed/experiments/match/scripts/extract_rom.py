#!/usr/bin/env python3
"""
extract_rom.py — dump the exact ROM bytes of the 5 target functions from
roms/stock/60E1D400.bin into rom_hex/*.txt (read-only on the ROM).

Function boundaries were taken from hand-verified disassembly (see c/*.c headers).
Body = executable instructions; literals = PC-relative pool words that follow.
"""
import os, struct

HERE = os.path.dirname(os.path.abspath(__file__))
ROM = os.path.join(HERE, "..", "..", "..", "..", "roms", "stock", "60E1D400.bin")
OUT = os.path.join(HERE, "..", "rom_hex")

# (name, start, body_len_bytes, literal_start, literal_len_bytes)
FUNCS = [
    ("add16bitSaturate_2460",  0x2460, 20, 0x2474, 4),
    ("addSaturate8Bit_2478",   0x2478, 22, 0x248E, 2),
    ("addS32Saturate_2304",    0x2304, 18, 0x2318, 4),
    ("seed_mixer_366B8",       0x366B8, 164, None, 0),
    ("calculateImmoSeed_3675C",0x3675C, 276, None, 0),
]

rom = open(ROM, "rb").read()
os.makedirs(OUT, exist_ok=True)

for name, start, blen, lstart, llen in FUNCS:
    body = rom[start:start+blen]
    lit = rom[lstart:lstart+llen] if lstart is not None else b""
    assert len(body) == blen, (name, len(body))
    txt = []
    txt.append(f"# {name}  ROM offset 0x{start:05X}, base 0x{start+0x60000000:08X}")
    txt.append(f"# body: {blen} bytes")
    txt.append(body.hex())
    if lit:
        txt.append(f"replacement ; regex: prefix supported. pool @0x{lstart:05X}: {llen} bytes")
        txt.append(lit.hex())
    txt.append(f"# total span: {blen+llen} bytes (0x{start:05X}..0x{start+blen+llen:05X})")
    with open(os.path.join(OUT, name + ".txt"), "w") as f:
        f.write("\n".join(txt) + "\n")
    print(f"{name}: body={blen}B{' +lit='+str(llen)+'B' if lit else ''}  total={blen+llen}B")
print("done")
