#!/usr/bin/env python3
"""make_elf.py - build the big-endian SH-2E analysis ELF for the 60E1D400 bank.

WHAT
----
Wraps the stock ROM ``roms/stock/60E1D400.bin`` (512 KiB, raw bytes, big-endian)
in a minimal 32-bit big-endian ELF (``e_machine = EM_SH = 42``) with three
``PT_LOAD`` segments:

  PH1  vaddr 0x00000000  filesz 0x80000  memsz 0x80000  R+X  file-off 0x1000 (ROM)
  PH2  vaddr 0xFFFF6000  filesz 0x00000  memsz 0x08000  R+W                  (32 KiB RAM)
  PH3  vaddr 0xFFFFF000  filesz 0x00000  memsz 0x01000  R+W                  (peripheral regs)

This is the original baseline (``tmp/ida/make_elf.py`` scratch); the 60E0FC00
sibling (``tools/make_elf_fc00.py``) shares the same proven layout.
Before writing, the ROM's verified preconditions are checked: size 0x80000,
reset vector 0x8B8 (``e_entry``), initial SP 0xFFFFDFA0.

WHY
---
IDA cannot map a raw ROM dump on its own: it needs an ELF container carrying
the load addresses, entry point, and RAM/peripheral mappings so that code,
vectors, and data land at the addresses the SH-2E CPU actually uses. This
tool produces that container deterministically from the stock ROM.

USAGE
-----
  python3 tools/make_elf.py
  python3 tools/make_elf.py --out /tmp/60E1D400_be.elf
  python3 tools/make_elf.py --rom roms/stock/60E1D400.bin --dry-run

INPUT
-----
  --rom : stock ROM image (default: <repo>/roms/stock/60E1D400.bin)

OUTPUT
------
  --out : ELF image written (default: <repo>/tmp/ida/60E1D400_be.elf);
          parent directories are created as needed.
  --dry-run : validate the ROM and report what would be written; write nothing.

Only the standard library is used (argparse, pathlib, struct, sys).
Deterministic: identical ROM bytes always yield an identical ELF.
"""

import argparse
import struct
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROM = REPO_ROOT / "roms" / "stock" / "60E1D400.bin"
DEFAULT_OUT = REPO_ROOT / "tmp" / "ida" / "60E1D400_be.elf"

ROM_SIZE = 0x80000        # 524288
PH1_OFF = 0x1000          # file offset of ROM segment
TOTAL = 0x81000           # 528384 = 0x1000 + 0x80000
EXPECTED_ENTRY = 0x8B8
EXPECTED_SP = 0xFFFFDFA0


def build_elf(rom: bytes) -> bytearray:
    """Assemble the ELF image for validated ROM bytes."""
    # ---- ELF header (52 bytes) -------------------------------------------
    e_ident = b"\x7fELF" + bytes([1, 2, 1, 0]) + bytes(8)  # 32-bit, big-endian, ver1
    e_header = (
        e_ident
        + struct.pack(
            ">HHIIIIIHHHHHH",
            2,                # e_type     = ET_EXEC
            42,               # e_machine  = EM_SH (SuperH)
            1,                # e_version
            EXPECTED_ENTRY,   # e_entry (reset vector)
            52,               # e_phoff    = right after header
            0,                # e_shoff    = 0 (no section headers)
            0,                # e_flags
            52,               # e_ehsize
            32,               # e_phentsize
            3,                # e_phnum
            0,                # e_shentsize
            0,                # e_shnum
            0,                # e_shstrndx
        )
    )
    assert len(e_header) == 52

    # ---- Program headers (3 x 32 = 96 bytes) -------------------------------
    def ph(p_offset, p_vaddr, p_filesz, p_memsz, p_flags):
        return struct.pack(
            ">IIIIIIII",
            1,           # p_type  = PT_LOAD
            p_offset,
            p_vaddr,
            p_vaddr,     # p_paddr = p_vaddr
            p_filesz,
            p_memsz,
            p_flags,     # 5 = R+X, 6 = R+W
            0x1000,      # p_align
        )

    p_headers = (
        ph(0x1000, 0x00000000, 0x80000, 0x80000, 5)  # ROM R+X
        + ph(0, 0xFFFF6000, 0x00000, 0x08000, 6)     # RAM  R+W
        + ph(0, 0xFFFFF000, 0x00000, 0x01000, 6)     # periph regs R+W
    )
    assert len(p_headers) == 96

    out = bytearray(TOTAL)
    out[0:52] = e_header
    out[52:52 + 96] = p_headers
    out[PH1_OFF:PH1_OFF + ROM_SIZE] = rom
    return out


def check_rom(rom: bytes, rom_path: Path):
    """Return an error string when the ROM fails preconditions, else None."""
    if len(rom) != ROM_SIZE:
        return (f"ROM size {len(rom):#x}, expected {ROM_SIZE:#x}: {rom_path}")
    entry = struct.unpack_from(">I", rom, 0)[0]
    if entry != EXPECTED_ENTRY:
        return f"reset vector {entry:#x}, expected {EXPECTED_ENTRY:#x}: {rom_path}"
    sp = struct.unpack_from(">I", rom, 4)[0]
    if sp != EXPECTED_SP:
        return f"initial SP {sp:#x}, expected {EXPECTED_SP:#x}: {rom_path}"
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Build the big-endian SH-2E analysis ELF for the 60E1D400 ROM bank."
    )
    ap.add_argument("--rom", type=Path, default=DEFAULT_ROM, help="input stock ROM")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output ELF path")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate the ROM and report; write nothing")
    args = ap.parse_args(argv)

    try:
        rom = args.rom.read_bytes()
    except FileNotFoundError:
        print(f"Error: ROM not found: {args.rom}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Error: cannot read ROM {args.rom}: {e}", file=sys.stderr)
        return 1

    err = check_rom(rom, args.rom)
    if err is not None:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    out = build_elf(rom)

    if args.dry_run:
        print(f"dry-run: ROM {args.rom} OK "
              f"(size {len(rom):#x}, entry {EXPECTED_ENTRY:#x}, sp {EXPECTED_SP:#x})")
        print(f"dry-run: would write {len(out)} bytes to {args.out}")
        return 0

    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(out)
    except OSError as e:
        print(f"Error: cannot write output {args.out}: {e}", file=sys.stderr)
        return 1

    print(f"wrote {args.out}")
    print(f"  size      : {len(out):#x} ({len(out)} bytes)")
    print(f"  e_entry   : {struct.unpack_from('>I', out, 24)[0]:#x}")
    print(f"  phnum     : {struct.unpack_from('>H', out, 44)[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
