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
import os
import shutil
import struct
import argparse
import tempfile
from pathlib import Path

TARGET   = 0x5AA5A55A
DESC_OFF = 0x7FB80
DIFF_OFF = 0x7FB88
ROM_LEN  = 512 * 1024  # 524288


def compute(rom):
    lo  = struct.unpack_from(">I", rom, DESC_OFF)[0]
    hi  = struct.unpack_from(">I", rom, DESC_OFF + 4)[0]
    s   = sum(struct.unpack_from(">I", rom, j)[0] for j in range(lo, hi, 4)) & 0xFFFFFFFF
    return lo, hi, s, (TARGET - s) & 0xFFFFFFFF


def check_bounds(lo, hi, length):
    """Return an error string when the descriptor is invalid, else None.

    The checksum loop is sum(struct.unpack_from(">I", rom, j) for j in
    range(lo, hi, 4)): only lo must be 4-byte aligned.  hi may be
    unaligned (stock ROMs use e.g. hi=0x7DAFF); range() simply stops at
    the last full dword, so no hi-alignment requirement is enforced.
    """
    if not (0 <= lo < hi <= length):
        return (f"Invalid descriptor range: lo=0x{lo:X} hi=0x{hi:X} "
                f"(need 0 <= lo < hi <= 0x{length:X})")
    if lo % 4 != 0:
        return f"Invalid descriptor: lo=0x{lo:X} is not 4-byte aligned"
    return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("-f", "--fix",    action="store_true", help="fix in-place")
    ap.add_argument("-o", "--output", metavar="FILE",      help="fix su copia")
    args = ap.parse_args(argv)

    if args.fix and args.output:
        print("Error: -f/--fix and -o/--output are mutually exclusive "
              "(in-place fix vs copy); use one or the other.",
              file=sys.stderr)
        return 2

    try:
        raw = Path(args.rom).read_bytes()
    except FileNotFoundError:
        print(f"Error: ROM not found: {args.rom}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Error: cannot read ROM {args.rom}: {e}", file=sys.stderr)
        return 1

    if len(raw) != ROM_LEN:
        print(f"Error: expected {ROM_LEN}-byte (512 KiB) ROM, "
              f"got {len(raw)} bytes: {args.rom}", file=sys.stderr)
        return 1

    rom = bytearray(raw)
    try:
        lo, hi, s, correct = compute(rom)
        stored = struct.unpack_from(">I", rom, DIFF_OFF)[0]
    except struct.error as e:
        print(f"Error: cannot parse checksum descriptor at 0x{DESC_OFF:X}: {e}",
              file=sys.stderr)
        return 1

    print(f"Range  : 0x{lo:05X} – 0x{hi:05X}")
    print(f"Sum    : 0x{s:08X}")
    print(f"Stored : 0x{stored:08X}")
    print(f"Correct: 0x{correct:08X}")

    bad = check_bounds(lo, hi, len(rom))
    if bad is not None:
        print(f"Error: {bad}; refusing to fix.", file=sys.stderr)
        return 1

    if stored == correct:
        print("OK — checksum corretto")
        return 0

    print("ERRATO")

    if not args.fix and not args.output:
        print("Usa -f per fix in-place o -o <file> per fix su copia.")
        return 1

    # Patch a COPY first, then re-compute and compare before touching disk.
    fixed = bytearray(rom)
    struct.pack_into(">I", fixed, DIFF_OFF, correct)
    try:
        _lo2, _hi2, s2, correct2 = compute(fixed)
        stored2 = struct.unpack_from(">I", fixed, DIFF_OFF)[0]
    except struct.error as e:
        print(f"Error: re-computation failed after patch: {e}", file=sys.stderr)
        return 1
    if stored2 != correct2 or (s2 + stored2) & 0xFFFFFFFF != TARGET:
        print("Error: patched image does not verify; refusing to write.",
              file=sys.stderr)
        return 1

    if args.output:
        try:
            Path(args.output).write_bytes(bytes(fixed))
        except OSError as e:
            print(f"Error: cannot write {args.output}: {e}", file=sys.stderr)
            return 1
        print(f"Fixato -> {args.output}  (0x{stored:08X} -> 0x{correct:08X})")
        return 0

    # In-place fix: keep a .bak of the original, stage via a temp file,
    # re-read and re-verify, then atomically replace.
    src = Path(args.rom)
    bak = Path(str(src) + ".bak")
    try:
        shutil.copyfile(src, bak)
    except OSError as e:
        print(f"Error: cannot write backup {bak}: {e}", file=sys.stderr)
        return 1
    try:
        fd, tmp = tempfile.mkstemp(dir=str(src.parent), prefix=".denso_ck_",
                                   suffix=".bin")
        with os.fdopen(fd, "wb") as fh:
            fh.write(bytes(fixed))
        back = bytearray(Path(tmp).read_bytes())
        _lo3, _hi3, s3, correct3 = compute(back)
        stored3 = struct.unpack_from(">I", back, DIFF_OFF)[0]
        if stored3 != correct3 or (s3 + stored3) & 0xFFFFFFFF != TARGET:
            os.unlink(tmp)
            print("Error: staged image does not verify; "
                  "original kept, backup at %s." % bak, file=sys.stderr)
            return 1
        os.replace(tmp, src)
    except OSError as e:
        print(f"Error: in-place fix failed: {e} (backup at {bak})",
              file=sys.stderr)
        return 1
    print(f"Fixato -> {src}  (0x{stored:08X} -> 0x{correct:08X}) [backup: {bak}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
