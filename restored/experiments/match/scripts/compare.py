#!/usr/bin/env python3
"""
compare.py — assemble a predicted-GCC .s with the real sh-elf binutils and
compare the resulting bytes, offset-by-offset, against the ROM function body.

Usage: python3 compare.py
Relies on tools/toolchain/usr/bin (sh-elf-as / sh-elf-objcopy) and the ROM
roms/stock/60E1D400.bin.  Read-only on the repo; outputs go to stdout.
"""
import os, subprocess, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROMF  = os.path.join(HERE, "..", "..", "..", "..", "roms", "stock", "60E1D400.bin")
EXPD  = os.path.join(HERE, "..", "expected_gcc_sh2e")
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "tools"))
from disasm_sh2e import disasm_one

# Resolve the sh-elf binutils: canonical repo location, the .bak fallback
# (created by another session mid-flight), then PATH.
def _find(prog):
    cands = []
    for base in (os.path.join(HERE, "..", "..", "..", "..", "tools", "toolchain", "usr", "bin"),
                 os.path.join(HERE, "..", "..", "..", "..", "tools", "toolchain.bak", "usr", "bin")):
        p = os.path.join(base, prog)
        if os.path.exists(p):
            cands.append(p)
    for d in os.environ.get("PATH", "").split(os.pathsep):
        p = os.path.join(d, prog)
        if os.path.exists(p):
            cands.append(p)
    if not cands:
        raise SystemExit(f"sh-elf binutils not found (need {prog})")
    return cands[0]

AS  = _find("sh-elf-as")
OBJ = _find("sh-elf-objcopy")

# name: (rom_offset, compare_len, notes)
CASES = [
    ("add16bitSaturate.O2.s",          0x2460, 24, "body20+lit4"),
    ("addSaturate8Bit.O2.s",           0x2478, 24, "body22+lit2"),
    ("addS32Saturate.addv.s",          0x2304, 24, "body18+nop+lit4 (addv idiom)"),
    ("addS32Saturate.plain.s",         0x2304, 24, "plain-C reference (expect non-match)"),
    ("seed_mixer.reconstruction.s",    0x366B8, 164, "164B body only (pool outside)"),
]

rom = open(ROMF, "rb").read()

def asm_bytes(sfile):
    s = os.path.join(EXPD, sfile)
    o = s + ".o"
    b = s + ".bin"
    subprocess.run([AS, "-isa=sh2e", "-o", o, s], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([OBJ, "-O", "binary", "--only-section=.text", o, b], check=True)
    return open(b, "rb").read()

def ins_of(data, base=0):
    """Decode bytes into a list of (offset, opcode, mnemonic, operands)."""
    out = []
    for i in range(0, len(data) - 1, 2):
        op = struct.unpack(">H", data[i:i+2])[0]
        mne, ops, _ = disasm_one(op, base + i)
        out.append((i, op, mne, ops))
    return out

def fmt_diff(got, exp, got_ins, exp_ins):
    lines = []
    # instruction-level diff: align by instruction index
    for (go, gop, gm, gops), (eo, eop, em, eops) in zip(got_ins, exp_ins):
        if gop != eop:
            lines.append(f"    @+0x{go:03X}  ROM {eop:04X} {em:10s} {eops:12s} | asm {gop:04X} {gm:10s} {gops}")
    return lines

for sfile, roff, clen, note in CASES:
    got = asm_bytes(sfile)
    exp = rom[roff:roff + clen]
    n = min(len(got), len(exp), clen)
    same = sum(1 for i in range(n) if got[i] == exp[i])
    # allow trailing assembler padding (e.g. .size / alignment artifacts)
    body_got = got[:n]
    print(f"== {sfile}  [{note}]  ROM@0x{roff:05X} len={clen}")
    print(f"   assembled: {len(got)} bytes | compare window: {n} bytes | equal: {same}/{n} "
          f"({100*same/n:.1f}%)")
    if same == n:
        print(f"   => MATCH: assembled body byte-identical to ROM (0x{roff:05X}+{n})")
    else:
        # find first diff
        fd = next((i for i in range(n) if got[i] != exp[i]), None)
        print(f"   => DIFF: first difference at +0x{fd:03X} (ROM {exp[fd]:02X} vs asm {got[fd]:02X})")
        gi = ins_of(body_got[:len(body_got) - (len(body_got) % 2)], roff)
        ei = ins_of(exp[:len(exp) - (len(exp) % 2)], roff)
        d = fmt_diff(gi, ei, gi, ei)
        for l in d[:12]:
            print(l)
        if len(d) > 12:
            print(f"   ... ({len(d)} differing instructions)")
    print()
