#!/usr/bin/env python3
"""
tools/tests/test_decode_families.py — regression tests for the SH-2E disassembler
(tools/disasm_sh2e.py): the 9 decode-gap families (opcodes that a vanilla
disassembler leaves undecoded) plus the control-register/selector forms they
pull in.

Two levels of verification, all cross-checked against GNU-as 2.46 (sh-elf-as -big,
from tools/get_toolchain.sh):

  1. DECODE TABLES — exact (opcode -> mnemonic, operands) expectations. Every
     text form in the tables was assembled with GNU-as and its bytes compared,
     so the text is the canonical GNU-as spelling (round-trip by construction).
  2. WHOLE-ROM ROUND-TRIP — every word in both stock ROMs that disasm_one
     decodes is re-emitted and assembled in ONE batch; the emitted bytes must
     equal the ROM bytes at that address. Known documented exception: the
     0x82xx/0x86xx mov.l forms, which GNU-as has NO syntax for — it re-encodes
     them as the equivalent 0x1nmC/0x5nmC group forms (that re-encoding is
     asserted, proving the decode text is right), and rom_rebuild.py forces
     them back to `.word` (the accepted fallback).

Run from repo root (sh-elf-as must be on PATH, e.g. after tools/get_toolchain.sh):
    python3 tools/tests/test_decode_families.py          # full (both ROMs, bulk round-trip)
    python3 tools/tests/test_decode_families.py --quick   # tables + coverage only
"""
import os, re, struct, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import disasm_sh2e as D

ROM1 = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ROM2 = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ROMS = [ROM1, ROM2]

FAILS = []
CHECKS = [0]


def check(cond, msg):
    CHECKS[0] += 1
    if not cond:
        FAILS.append(msg)
        print("FAIL: " + msg)


def have_toolchain():
    try:
        r = subprocess.run(['sh-elf-as', '--version'], capture_output=True, text=True)
    except FileNotFoundError:
        return False                       # not on PATH -> caller skips gracefully
    return r.returncode == 0


# --------------------------------------------------------------------------
# 1. Decode tables (opcode, pc, mnemonic, operands). Text forms GNU-as-verified.
# --------------------------------------------------------------------------
PC = 0x1000  # arbitrary pc used for PC-relative cases

DECODE_TABLE = [
    # ---- GBR-relative MOV (family: 0xC0-0xC6) ----
    (0xC02C, 'mov.b', 'r0,@(0x2C,gbr)'),
    (0xC116, 'mov.w', 'r0,@(0x2C,gbr)'),
    (0xC20B, 'mov.l', 'r0,@(0x2C,gbr)'),
    (0xC0FF, 'mov.b', 'r0,@(0xFF,gbr)'),
    (0xC1FF, 'mov.w', 'r0,@(0x1FE,gbr)'),
    (0xC2FF, 'mov.l', 'r0,@(0x3FC,gbr)'),
    (0xC42C, 'mov.b', '@(0x2C,gbr),r0'),
    (0xC516, 'mov.w', '@(0x2C,gbr),r0'),
    (0xC60B, 'mov.l', '@(0x2C,gbr),r0'),
    (0xC400, 'mov.b', '@(0x00,gbr),r0'),
    # ---- 0x82xx / 0x86xx mov.l r0 forms ----
    (0x828C, 'mov.l', 'r0,@(0x30,r8)'),
    (0x8214, 'mov.l', 'r0,@(0x10,r1)'),
    (0x8200, 'mov.l', 'r0,@(0x00,r0)'),
    (0x82FF, 'mov.l', 'r0,@(0x3C,r15)'),
    (0x861C, 'mov.l', '@(0x30,r1),r0'),
    (0x86AC, 'mov.l', '@(0x30,r10),r0'),
    (0x8648, 'mov.l', '@(0x20,r4),r0'),
    (0x8666, 'mov.l', '@(0x18,r6),r0'),
    (0x8684, 'mov.l', '@(0x10,r8),r0'),
    (0x8600, 'mov.l', '@(0x00,r0),r0'),
    # ---- 0x2-group: div0s / cmp/str / xtrct / muls.w / mulu.w ----
    (0x2407, 'div0s', 'r0,r4'),
    (0x2437, 'div0s', 'r3,r4'),
    (0x240C, 'cmp/str', 'r0,r4'),
    (0x240D, 'xtrct', 'r0,r4'),
    (0x240F, 'muls.w', 'r0,r4'),
    (0x240E, 'mulu.w', 'r0,r4'),
    # ---- 0x3-group: div1 / cmp / addc / subc / addv / subv ----
    (0x3404, 'div1', 'r0,r4'),
    (0x3402, 'cmp/hs', 'r0,r4'),
    (0x3403, 'cmp/ge', 'r0,r4'),
    (0x3406, 'cmp/hi', 'r0,r4'),
    (0x3407, 'cmp/gt', 'r0,r4'),
    (0x340E, 'addc', 'r0,r4'),
    (0x340A, 'subc', 'r0,r4'),
    (0x340F, 'addv', 'r0,r4'),
    (0x340B, 'subv', 'r0,r4'),
    # ---- 0x0/0x4-group: mac.l / mac.w / mul.l / movt / tas.b ----
    (0x004F, 'mac.l', '@r4+,@r0+'),
    (0x404F, 'mac.w', '@r4+,@r0+'),
    (0x0407, 'mul.l', 'r0,r4'),
    (0x0429, 'movt', 'r4'),
    (0x441B, 'tas.b', '@r4'),
    # ---- specials ----
    (0x0019, 'div0u', ''),
    (0x001B, 'sleep', ''),
    # ---- negc ----
    (0x640A, 'negc', 'r0,r4'),
    # ---- 0x0-group indexed mov @(r0,Rn) (syntax fixed to GNU-as form) ----
    (0x08B4, 'mov.b', 'r11,@(r0,r8)'),
    (0x08B5, 'mov.w', 'r11,@(r0,r8)'),
    (0x08B6, 'mov.l', 'r11,@(r0,r8)'),
    (0x08BC, 'mov.b', '@(r0,r11),r8'),
    (0x08BD, 'mov.w', '@(r0,r11),r8'),
    (0x08BE, 'mov.l', '@(r0,r11),r8'),
    # ---- fmov.s indexed forms ----
    (0xF217, 'fmov.s', 'fr1,@(r0,r2)'),
    (0xF126, 'fmov.s', '@(r0,r2),fr1'),
    (0xFF17, 'fmov.s', 'fr1,@(r0,r15)'),
    # ---- control registers: stc/stc.l (uppercase names, GNU-as accepts) ----
    (0x0802, 'stc', 'SR,r8'),
    (0x0812, 'stc', 'GBR,r8'),
    (0x0822, 'stc', 'VBR,r8'),
    (0x0832, 'stc', 'SSR,r8'),
    (0x0842, 'stc', 'SPC,r8'),
    (0x4803, 'stc.l', 'SR,@-r8'),
    (0x4813, 'stc.l', 'GBR,@-r8'),
    (0x4823, 'stc.l', 'VBR,@-r8'),
    (0x4833, 'stc.l', 'SSR,@-r8'),
    (0x4843, 'stc.l', 'SPC,@-r8'),
    (0x480E, 'ldc', 'r8,SR'),
    (0x481E, 'ldc', 'r8,GBR'),
    (0x482E, 'ldc', 'r8,VBR'),
    (0x483E, 'ldc', 'r8,SSR'),
    (0x484E, 'ldc', 'r8,SPC'),
    (0x4807, 'ldc.l', '@r8+,SR'),
    (0x4817, 'ldc.l', '@r8+,GBR'),
    (0x4827, 'ldc.l', '@r8+,VBR'),
    (0x4837, 'ldc.l', '@r8+,SSR'),
    (0x4847, 'ldc.l', '@r8+,SPC'),
    # ---- system registers: sts/sts.l/lds/lds.l ----
    (0x080A, 'sts', 'mach,r8'),
    (0x081A, 'sts', 'macl,r8'),
    (0x082A, 'sts', 'pr,r8'),
    (0x085A, 'sts', 'fpul,r8'),
    (0x086A, 'sts', 'fpscr,r8'),
    (0x485A, 'lds', 'r8,fpul'),
    (0x486A, 'lds', 'r8,fpscr'),
    (0x4856, 'lds.l', '@r8+,fpul'),
    (0x4866, 'lds.l', '@r8+,fpscr'),
    (0x4852, 'sts.l', 'fpul,@-r8'),
    (0x4862, 'sts.l', 'fpscr,@-r8'),
    (0x4802, 'sts.l', 'mach,@-r8'),
    (0x4812, 'sts.l', 'macl,@-r8'),
    (0x4822, 'sts.l', 'pr,@-r8'),
    # ---- branches (register forms) ----
    (0x0403, 'bsrf', 'r4'),
    (0x0423, 'braf', 'r4'),
    # ---- 0xC0-family immediate/bit ops ----
    (0xC830, 'tst', '#0x30,r0'),
    (0xC930, 'and', '#0x30,r0'),
    (0xCA30, 'xor', '#0x30,r0'),
    (0xCB30, 'or', '#0x30,r0'),
    (0xCC30, 'tst.b', '#0x30,@(r0,gbr)'),
    (0xCD30, 'and.b', '#0x30,@(r0,gbr)'),
    (0xCE30, 'xor.b', '#0x30,@(r0,gbr)'),
    (0xCF30, 'or.b', '#0x30,@(r0,gbr)'),
    (0xC330, 'trapa', '#0x30'),
]

# PC-relative / branch decode: (opcode, expected mnemonic, expected operands)
PCREL_TABLE = [
    (0xA123, 'bra', '0x0124A'),      # 0x1000+4+0x123*2
    (0xB123, 'bsr', '0x0124A'),
    (0x89FC, 'bt', '0x00FFC'),       # s8(0xFC)=-4 -> 0x1000+4-8
    (0x8BFC, 'bf', '0x00FFC'),
    (0x8D00, 'bt/s', '0x01004'),
    (0x8F00, 'bf/s', '0x01004'),
    (0x937F, 'mov.w', '0x01102,r3'),  # 0x1000+4+0x7F*2
    (0xD144, 'mov.l', '0x01114,r1'),  # (0x1004&~3)+0x44*4 = 0x1004+0x110
    (0xC720, 'mova', '0x01084,r0'),   # (0x1004&~3)+0x20*4 = 0x1004+0x80
]

HEXRE = re.compile(r'0x[0-9a-fA-F]{5,8}')


def test_decode_tables():
    for op, mne, ops in DECODE_TABLE:
        m, o, _ = D.disasm_one(op, PC)
        check(m == mne, f"0x{op:04X}: mnemonic {m!r} != {mne!r}")
        check(o == ops, f"0x{op:04X}: operands {o!r} != {ops!r}")
    for op, mne, ops in PCREL_TABLE:
        m, o, _ = D.disasm_one(op, PC)
        check(m == mne, f"0x{op:04X} @pc=0x{PC:05X}: mnemonic {m!r} != {mne!r}")
        check(o == ops, f"0x{op:04X} @pc=0x{PC:05X}: operands {o!r} != {ops!r}")


# --------------------------------------------------------------------------
# Whole-ROM checks
# --------------------------------------------------------------------------
# family pattern -> name (every word matching one of these MUST decode)
FAMILY_PATTERNS = [
    ((0xFF00, 0xC000), 'gbr'), ((0xFF00, 0xC100), 'gbr'), ((0xFF00, 0xC200), 'gbr'),
    ((0xFF00, 0xC400), 'gbr'), ((0xFF00, 0xC500), 'gbr'), ((0xFF00, 0xC600), 'gbr'),
    ((0xFF00, 0x8200), 'mov.l 82xx'), ((0xFF00, 0x8600), 'mov.l 86xx'),
    ((0xF00F, 0x3004), 'div1'), ((0xF00F, 0x2007), 'div0s'),
    ((0xFFFF, 0x0019), 'div0u'), ((0xF00F, 0x200C), 'cmp/str'),
    ((0xF00F, 0x3002), 'cmp/hs'), ((0xF00F, 0x3003), 'cmp/ge'),
    ((0xF00F, 0x3006), 'cmp/hi'), ((0xF00F, 0x3007), 'cmp/gt'),
    ((0xF00F, 0x000F), 'mac.l'), ((0xF00F, 0x400F), 'mac.w'),
    ((0xF0FF, 0x0002), 'stc'), ((0xF0FF, 0x0012), 'stc'), ((0xF0FF, 0x0022), 'stc'),
    ((0xF0FF, 0x0032), 'stc'), ((0xF0FF, 0x0042), 'stc'),
    ((0xF0FF, 0x4003), 'stc.l'), ((0xF0FF, 0x4013), 'stc.l'), ((0xF0FF, 0x4023), 'stc.l'),
    ((0xF0FF, 0x4033), 'stc.l'), ((0xF0FF, 0x4043), 'stc.l'),
    ((0xF0FF, 0x400E), 'ldc'), ((0xF0FF, 0x401E), 'ldc'), ((0xF0FF, 0x402E), 'ldc'),
    ((0xF0FF, 0x403E), 'ldc'), ((0xF0FF, 0x404E), 'ldc'),
    ((0xF0FF, 0x4007), 'ldc.l'), ((0xF0FF, 0x4017), 'ldc.l'), ((0xF0FF, 0x4027), 'ldc.l'),
    ((0xF0FF, 0x4037), 'ldc.l'), ((0xF0FF, 0x4047), 'ldc.l'),
    ((0xF0FF, 0x405A), 'lds'), ((0xF0FF, 0x406A), 'lds'),
    ((0xF0FF, 0x4056), 'lds.l'), ((0xF0FF, 0x4066), 'lds.l'),
    ((0xF0FF, 0x4052), 'sts.l'), ((0xF0FF, 0x4062), 'sts.l'),
    ((0xF0FF, 0x000A), 'sts'), ((0xF0FF, 0x001A), 'sts'), ((0xF0FF, 0x002A), 'sts'),
    ((0xF0FF, 0x005A), 'sts'), ((0xF0FF, 0x006A), 'sts'),
    ((0xF00F, 0x600A), 'negc'), ((0xF00F, 0x200D), 'xtrct'),
    ((0xF00F, 0x300E), 'addc'), ((0xF00F, 0x300A), 'subc'),
    ((0xF00F, 0x300F), 'addv'), ((0xF00F, 0x300B), 'subv'),
    ((0xF00F, 0x0007), 'mul.l'), ((0xF00F, 0x200F), 'muls.w'), ((0xF00F, 0x200E), 'mulu.w'),
    ((0xFFFF, 0x001B), 'sleep'), ((0xF0FF, 0x401B), 'tas.b'),
    ((0xF0FF, 0x0029), 'movt'), ((0xF0FF, 0x0003), 'bsrf'), ((0xF0FF, 0x0023), 'braf'),
    ((0xFF00, 0xC900), 'and#'), ((0xFF00, 0xCB00), 'or#'), ((0xFF00, 0xCA00), 'xor#'),
    ((0xFF00, 0xCC00), 'tst.b'), ((0xFF00, 0xCD00), 'and.b'),
    ((0xFF00, 0xCE00), 'xor.b'), ((0xFF00, 0xCF00), 'or.b'),
]


def family_matches(w):
    for (m, v), name in FAMILY_PATTERNS:
        if w & m == v:
            return True
    return False


def test_rom_coverage():
    for rom in ROMS:
        d = open(rom, 'rb').read()
        for a in range(0, len(d), 2):
            w = int.from_bytes(d[a:a + 2], 'big')
            if family_matches(w):
                mne, _, _ = D.disasm_one(w, a)
                check(mne not in ('unknown', 'fpu_unknown'),
                      f"{os.path.basename(rom)} 0x{a:05X} 0x{w:04X}: family word undecoded -> {mne}")


def _bulk_roundtrip(d, lo, hi):
    """Assemble every decoded word in [lo,hi) with GNU-as; return list of
    (addr, opcode, mne, ops, assembled_word). Labels are emitted at every
    branch/PC-relative target (same L_xxxxxx convention as rom_rebuild.py)."""
    instrs = []
    targets = set()
    for a in range(lo, min(hi, len(d)), 2):
        w = int.from_bytes(d[a:a + 2], 'big')
        mne, ops, _ = D.disasm_one(w, a)
        if mne in ('unknown', 'fpu_unknown'):
            continue
        ops2 = ops
        if mne in ('bra', 'bsr', 'bt', 'bf', 'bt/s', 'bf/s', 'mov.w', 'mov.l', 'mova'):
            m = HEXRE.search(ops)
            if m:
                t = int(m.group(0)[2:], 16)
                ops2 = HEXRE.sub('L_%06x' % t, ops, count=1)
                targets.add(t)
        instrs.append((a, w, mne, ops2))

    lines = ['\t.text']
    tgt = set(targets)
    by = {a: (w, m, o) for a, w, m, o in instrs}
    for a in range(lo, min(hi, len(d)), 2):
        if a in tgt or a in by:
            lines.append('.org 0x%x' % a)
        if a in tgt:
            lines.append('L_%06x:' % a)
            tgt.discard(a)
        if a in by:
            w, m, o = by[a]
            lines.append('\t%s %s' % (m, o))
    for t in sorted(tgt):
        lines.append('.org 0x%x' % t)
        lines.append('L_%06x:' % t)

    with tempfile.TemporaryDirectory() as td:
        sp = os.path.join(td, 't.s')
        open(sp, 'w').write('\n'.join(lines) + '\n')
        r = subprocess.run(['sh-elf-as', '-big', sp, '-o', os.path.join(td, 't.o')],
                           capture_output=True, text=True)
        if r.returncode:
            open('/tmp/rt_test_fail.s', 'w').write('\n'.join(lines))
            check(False, f"assembly error (see /tmp/rt_test_fail.s): {r.stderr[:400]}")
            return instrs, {}
        subprocess.run(['sh-elf-ld', '-Ttext=0x0', '-e', '0x0', '-o', os.path.join(td, 't.elf'),
                        os.path.join(td, 't.o')], check=True, capture_output=True)
        subprocess.run(['sh-elf-objcopy', '-O', 'binary', '-j', '.text',
                        os.path.join(td, 't.elf'), os.path.join(td, 't.bin')],
                       check=True, capture_output=True)
        got = open(os.path.join(td, 't.bin'), 'rb').read()
    return instrs, got


def test_rom_roundtrip():
    for rom in ROMS:
        d = open(rom, 'rb').read()
        instrs, got = _bulk_roundtrip(d, 0, len(d))
        if not got:
            return
        ndec = nok = n82 = n82ok = 0
        for a, w, mne, ops2 in instrs:
            g = int.from_bytes(got[a:a + 2], 'big')
            ndec += 1
            if w & 0xFF00 in (0x8200, 0x8600):
                n82 += 1
                # documented: GNU-as re-encodes to the 0x1nmC / 0x5nmC group forms
                reg = (w >> 4) & 0xF
                if w & 0xFF00 == 0x8200:
                    canon = 0x1000 | (reg << 8) | (w & 0xF)
                else:
                    canon = 0x5000 | (reg << 4) | (w & 0xF)
                if g == canon:
                    n82ok += 1
                else:
                    check(False, f"{os.path.basename(rom)} 0x{a:05X} 0x{w:04X} {mne} {ops2}: "
                                 f"canonical {g:04X} != expected {canon:04X}")
                continue
            if g == w:
                nok += 1
            else:
                check(False, f"{os.path.basename(rom)} 0x{a:05X} 0x{w:04X} {mne} {ops2}: "
                             f"assembled {g:04X} != ROM {w:04X}")
        print(f"  {os.path.basename(rom)}: {ndec} decoded, {nok} byte-exact, "
              f"{n82ok}/{n82} 82xx/86xx canonicalized (documented)")


def main():
    quick = '--quick' in sys.argv
    print("disasm_sh2e decode-family regression tests")
    print(f"  roms: {[os.path.basename(r) for r in ROMS]}")
    test_decode_tables()
    test_rom_coverage()
    if not quick:
        if have_toolchain():
            print("  GNU-as 2.46 bulk round-trip:")
            test_rom_roundtrip()
        else:
            print("  SKIP bulk round-trip: sh-elf-as not on PATH")
    print(f"\n{CHECKS[0]} checks, {len(FAILS)} failures")
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main()
