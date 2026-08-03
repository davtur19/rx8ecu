#!/usr/bin/env python3
"""
Normalize mangled RomRaider / ECUFlash RX-8 ROM codes in the extracted table CSV.

Context (from rx8_webdata/02_calibration definitions, verified):
  * The real ROM code is the 8-hex-char internal ID stored in the ROM itself at
    0x2000. Verified against fork_RE/Stock_ROMs/60E0E500.bin -> b"60E0E500".
  * The RomRaider defs use <romid><xmlid>CODE + <internalidstring>CODE; the
    ECUFlash defs use the same <xmlid> convention (file 60E0G500.xml).
  * "60E0G500" and "60E09L0N" contain non-hex chars (G/L/N) -> mangled spellings
    of the real 60E0E500 (JDM 6-port MT, internal ID "60E0E500"). 60E0E500 is
    otherwise absent from the extracted CSV (its sibling 60E0E600/60E0E700 are
    present with their real codes).

Behaviour:
  * Reads  symbols/romraider_rx8_tables.csv
  * Normalizes rom_code (and def_file) through the fixed maps below
  * Writes symbols/romraider_rx8_tables_fixed.csv ONLY IF the rom_code Counter
    changes (>0); otherwise prints "nochange" and leaves no file behind
  * Prints the new Counter for rom_code

Usage: python3 tools/fix_romcodes.py
"""
import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "symbols" / "romraider_rx8_tables.csv"
DST = ROOT / "symbols" / "romraider_rx8_tables_fixed.csv"

# ---- Fixed mapping: mangled code -> real code (verified, see module docstring).
# Codes not listed here are left unchanged.
ROMCODE_MAP = {
    "60E0G500": "60E0E500",  # 'G' non-hex; real internal ID of 60E0E500.bin @0x2000
    "60E09L0N": "60E0E500",  # 'L'/'N' non-hex; JDM E5-family sibling of 60E0E500
}

# def_file normalization (same mangled-name family). Unlisted files unchanged.
DEF_FILE_MAP = {
    "60E0G500.xml": "60E0E500.xml",
}


def main() -> int:
    if not SRC.exists():
        print(f"error: {SRC} not found")
        return 1

    with SRC.open(newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if fieldnames is None:
        print("error: empty CSV")
        return 1

    old_counter = Counter(r["rom_code"] for r in rows)

    changed = 0
    for row in rows:
        new_rom = ROMCODE_MAP.get(row["rom_code"])
        if new_rom is not None:
            if new_rom != row["rom_code"]:
                changed += 1
            row["rom_code"] = new_rom
        new_def = DEF_FILE_MAP.get(row["def_file"])
        if new_def is not None and new_def != row["def_file"]:
            row["def_file"] = new_def

    new_counter = Counter(r["rom_code"] for r in rows)

    if new_counter == old_counter:
        print("nochange")
        return 0

    with DST.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {DST} ({len(rows)} rows, {changed} rom_code rewrites)")
    for code, n in new_counter.most_common():
        print(f"{n:6d}  {code}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
