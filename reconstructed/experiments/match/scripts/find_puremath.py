#!/usr/bin/env python3
"""
find_puremath.py — scan the stock 60E1D400 ROM for small pure-math helper
candidates using the merged symbol map (symbols/symbols_60E1D400_merged.csv).

Method
------
For every named function with body size in [4, 90] bytes, disassemble the ROM
bytes (capstone, SH-2 big-endian) and classify it as a PURE-MATH candidate when:
  * the last instruction is `rts`;
  * there are NO calls (jsr/bsr), no indirect control flow (jmp/rte/trapa),
    no FPU instructions, no mac/mac.l/mac.w;
  * every memory operand references only the allowed base registers
    (r0..r7 for args, r15 for stack) or the PC (constant pool via @(disp,pc));
  * every general register operand is in {r0..r7} (+ r15 stack / r14 if it is
    a pure frame-pointer push/pop pair);
  * the instruction mix is pure arithmetic/logic/shift/compare/branch.

Read-only on the repo.  Output: sorted candidate list with disassembly.
"""
import csv, os, sys
from capstone import Cs, CS_ARCH_SH, CS_MODE_SH2, CS_MODE_BIG_ENDIAN

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
ROMF = os.path.join(ROOT, "roms", "stock", "60E1D400.bin")
SYMS = os.path.join(ROOT, "symbols", "symbols_60E1D400_merged.csv")

ALLOW = {
    "mov", "mov.b", "mov.w", "mov.l", "mova",
    "add", "addc", "addv", "sub", "subc", "subv",
    "cmp", "cmp/eq", "cmp/hs", "cmp/ge", "cmp/hi", "cmp/gt",
    "cmp/pz", "cmp/pl", "cmp/str", "tst",
    "and", "or", "xor", "not", "neg", "negc",
    "extu.b", "extu.w", "exts.b", "exts.w",
    "shll", "shll2", "shll8", "shll16", "shal",
    "shar", "shlr", "shlr2", "shlr8", "shlr16",
    "rotl", "rotr", "rotcl", "rotcr",
    "mul.l", "muls.w", "mulu.w", "dmul.s", "dmul.l",
    "div0s", "div0u", "div1",
    "clrt", "sett", "movt",
    "bf", "bf/s", "bt", "bt/s", "bra", "nop",
    "rts", "sts", "lds", "clrmac",
}

BAD_MNEM = {"jsr", "jsr/n", "bsr", "jmp", "rte", "trapa", "sleep", "pref",
            "tas.b", "mac.l", "mac.w", "fadd", "fsub", "fmul", "fdiv", "fmov",
            "fmov.s", "fcmp", "float", "ftrc", "fneg", "fabs", "fsqrt", "fldi",
            "flds", "fsts", "fmac", "ldc", "stc"}

R_ALLOWED = {"r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "r15", "r14", "pc", "pr"}


def regs_in(op_str):
    """Set of register names mentioned in an operand string (raw tokens)."""
    s = set()
    for tok in op_str.replace(",", " ").replace("[", " ").replace("]", " ").split():
        if tok.startswith("r") and tok[1:].isdigit() and len(tok) <= 4:
            s.add(tok)
        elif tok in ("pr", "sr", "gbr", "vbr", "ssr", "spc", "mach", "macl",
                     "fpul", "fpscr"):
            s.add(tok)
    return s


def main():
    rom = open(ROMF, "rb").read()
    md = Cs(CS_ARCH_SH, CS_MODE_SH2 | CS_MODE_BIG_ENDIAN)
    md.detail = False

    cands = []
    for r in csv.DictReader(open(SYMS)):
        a = int(r["addr"], 16)
        e = int(r["end"], 16)
        name = r["name"]
        size = e - a
        if not (4 <= size <= 90):
            continue
        body = rom[a:e]
        ins = list(md.disasm(body, 0x60000000 + a))
        if not ins or ins[-1].mnemonic != "rts":
            continue
        # quick pre-filter on bytes: must contain rts (0x000B)
        if body.rfind(b"\x00\x0b") < 0:
            continue
        ok = True
        reasons = []
        for i in ins:
            m = i.mnemonic
            if m in BAD_MNEM:
                ok, reasons = False, [f"{m} @+0x{i.address-a:02X}"]; break
            if m not in ALLOW:
                ok, reasons = False, [f"{m} (unknown) @+0x{i.address-a:02X}"]; break
            rs = regs_in(i.op_str)
            bad = rs - R_ALLOWED
            if bad:
                ok, reasons = False, [f"{sorted(bad)} @+0x{i.address-a:02X} ({m} {i.op_str})"]; break
        if ok:
            cands.append((size, a, e, name, ins))
    cands.sort()
    print(f"# {len(cands)} pure-math candidates (size 4..90, no calls, r0-r7+r14/15+pc only)\n")
    for size, a, e, name, ins in cands:
        print(f"== {name}  0x{a:05X}..0x{e:05X}  {size}B")
        for i in ins:
            print(f"   +0x{i.address-a:02X}  {int.from_bytes(i.bytes,'big'):04X}  {i.mnemonic:8s} {i.op_str}")
        print()


if __name__ == "__main__":
    main()
