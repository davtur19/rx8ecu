#!/usr/bin/env python3
"""
denso_ck.py — DENSO SH7055 checksum tool

Verifica o corregge il checksum di una ROM Mazda RX-8 (60Exxxxx).

  Algoritmo: sum_dwords(ROM, lo, hi, step=4) + diff = 0x5AA5A55A
  Descriptor a 0x7FB80: [lo:4][hi:4][diff:4]

Utilizzo:
  python denso_ck.py <rom.bin>              # solo verifica
  python denso_ck.py <rom.bin> -f           # fix in-place
  python denso_ck.py <rom.bin> -o out.bin   # fix su copia
"""

import sys
import struct
import argparse
from pathlib import Path

TARGET   = 0x5AA5A55A
DESC_OFF = 0x7FB80
DIFF_OFF = 0x7FB88


def compute(rom):
    lo  = struct.unpack_from(">I", rom, DESC_OFF)[0]
    hi  = struct.unpack_from(">I", rom, DESC_OFF + 4)[0]
    s   = sum(struct.unpack_from(">I", rom, j)[0] for j in range(lo, hi, 4)) & 0xFFFFFFFF
    return lo, hi, s, (TARGET - s) & 0xFFFFFFFF


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("-f", "--fix",    action="store_true", help="fix in-place")
    ap.add_argument("-o", "--output", metavar="FILE",      help="fix su copia")
    args = ap.parse_args()

    rom = bytearray(Path(args.rom).read_bytes())
    lo, hi, s, correct = compute(rom)
    stored = struct.unpack_from(">I", rom, DIFF_OFF)[0]

    print(f"Range  : 0x{lo:05X} – 0x{hi:05X}")
    print(f"Sum    : 0x{s:08X}")
    print(f"Stored : 0x{stored:08X}")
    print(f"Correct: 0x{correct:08X}")

    if stored == correct:
        print("OK — checksum corretto")
        return 0

    print("ERRATO")

    dst = args.output or (args.rom if args.fix else None)
    if not dst:
        print("Usa -f per fix in-place o -o <file> per fix su copia.")
        return 1

    struct.pack_into(">I", rom, DIFF_OFF, correct)
    Path(dst).write_bytes(rom)
    print(f"Fixato -> {dst}  (0x{stored:08X} -> 0x{correct:08X})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
