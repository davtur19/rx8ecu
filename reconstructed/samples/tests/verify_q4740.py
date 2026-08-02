#!/usr/bin/env python3
"""
verify_q4740.py — bit-exact equivalence of the ROM soft-float helper @0x4740
against a Python reference model (validated instruction-for-instruction).

WHAT 0x4740 REALLY IS (finding — do NOT trust the "Q15 saturating mul" label)
---------------------------------------------------------------------------
Disassembly + emulator probing of 60E1D400.bin show that the disassembler's
name on 0x4740 ("q15 saturating mul") is WRONG.  The routine is a FIXED-POINT
SQRT / normaliser helper, the middle stage of the soft-float chain

    frexp @0x48C8  ->  this routine @0x4740  ->  ldexp @0x481C

called only from 0x46CC (float validity/normalisation path).  It is not a Q15
multiply and not a plain division: it implements an integer-restoring
square-root loop on the mantissa-like second argument (29-iteration shift-sub
loop, then a two-bit remainder phase, then sticky round-half-up), together
with sign/saturation handling of the first argument.

CALLING CONVENTION (non-ABI-clean, stack-passed — the harness drives it as the
ROM does):

    [r15+0] = out  :  pointer to a 2 x 32-bit result buffer
    [r15+4] = a0   :  32-bit word; low 16 bits are the fixed-point argument
    [r15+8] = a1   :  32-bit mantissa-like second word

    result[0] = low word  (r3 after extu.w / shll / rotcr folding)
    result[1] = high word (r1, the sqrt/normaliser result)

Behaviour summary (bit-exact):
  * bit31 of a0 set              -> result = 0x00007FFF / 0xFFFFFFFF (saturate)
  * sext16(a0) >= 0x7FFF (i.e. a0 low16 == 0x7FFF) -> result = 0x00007FFF /
                                       (0xFFFFFFFF if a1 != 0 else 0x00000000)
  * sext16(a0) <= -0x7FFF        -> result = 0x80008001 / 0x00000000
                                     (rotcr path; the low word keeps the sign
                                     bit folded in, so result[0] == 0x80008001
                                     for a0 with bit31 set, else 0x00008001)
  * otherwise (main path)        -> 29-iteration restoring-sqrt loop on a1
                                     building r1 (with sticky round-up), the
                                     low word is (sext16(a0) >> 1) & 0xFFFF.

WHY PYTHON MODEL, NOT A C LIFT
------------------------------
The task allows a C lift in /tmp/4740.c ONLY if the semantics are 100% clear.
Here the *closed form* (fixed-point sqrt) only matches ~37% of vectors — the
bit-level loop is what the ROM really does, and the C reconstruction is NOT
available in samples/src.  So instead of inventing a C lift, this harness
validates the ROM bytes against the bit-exact Python model derived from the
disassembly (which reproduces the SH-2E state machine 1:1, including the
delay-slot and sign-extension subtleties).  This is the same "ROM vs model"
pattern used by the other verify_*.py harnesses, just with the model being a
Python reference instead of host-C.

Usage:  python3 verify_q4740.py [N]    (default N = 3000 random vectors)
Exit:  0 all vectors match; 1 any mismatch (first few printed); 2 env error.
Read-only w.r.t. the repo: only the stock ROM is read, everything else is
computed in-process.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng  # noqa: E402

ADDR = 0x4740
N_DEFAULT = 3000
M = 0xFFFFFFFF

STACK = 0xFFFFDF00   # caller r15 (same as the other harnesses)
OUT = 0x1000         # result buffer (safe, away from stack)


# ---------------------------------------------------------------------------
# Bit-exact Python model of the ROM routine (mirrors the disassembly 1:1).
# ---------------------------------------------------------------------------
def s32(x):
    x &= M
    return x - (1 << 32) if x & 0x80000000 else x


def s16(x):
    x &= 0xFFFF
    return x - (1 << 16) if x & 0x8000 else x


def ref_4740(a0, a1):
    """Return (result0, result1) as the ROM writes them to [out]/[out+4]."""
    r4 = a0 & M
    r3 = s16(r4)                 # exts.w on the low 16 bits
    r2 = a1 & M
    T = 0

    # 4748: cmp/ge R3,R5 (R5=0xFFFF8001) -> T = (-32767 >= r3) i.e. r3 <= -32767
    T = 1 if s32(0xFFFF8001) >= s32(r3) else 0
    if T:                         # 474A bt 0x47F8  (r3 <= -32767)
        # 47F8 mov.l @(0x4818),r3 (=0xFFFF8001); 47FA extu.w r3; 47FC shll r3
        r3 = (0xFFFF8001 & 0xFFFF)
        r3 = (r3 << 1) & M
        # 47FE shll r4 -> T = bit31(a0); 4800 rotcr r3 (delay slot handled)
        T = (r4 >> 31) & 1
        r4 = (r4 << 1) & M
        t = r3 & 1
        r3 = ((r3 >> 1) | (T << 31)) & M
        T = t
        r1 = 0                    # 4804 mov #0,r1
        return (r3, r1)           # bra 47E8: NO extu.w before the store

    # 474C shll r4 -> T = bit31(a0)
    T = (r4 >> 31) & 1
    r4 = (r4 << 1) & M
    if T:                         # 474E bt 0x480C  (bit31 saturate path)
        r3 = 0x7FFF
        r1 = 0xFFFFFFFF           # E1FF = mov #-1 (sign-extended!)
        r3 &= 0xFFFF              # 47E6 extu.w
        return (r3, r1)

    # 4752: cmp/ge R5,R3 (R5=0x7FFF) -> T = (r3 >= 0x7FFF) i.e. r3 == 0x7FFF
    T = 1 if s32(r3) >= s32(0x7FFF) else 0
    if T:                         # 4754 bt 0x47F0  (r3 == 0x7FFF)
        if r2 != 0:
            r3, r1 = 0x7FFF, 0xFFFFFFFF   # 47F2 bf 0x480C (r1=-1)
        else:
            r3, r1 = 0x7FFF, 0             # 4806
        r3 &= 0xFFFF
        return (r3, r1)

    # ---- main path: r3 in [-32766, 32766] -------------------------------
    r5 = 0
    r1 = 0
    r0 = 0
    r6 = 0x1D
    # 475E shlr r3 ; 4760 bf 4766   (bit0 of r3 selects the extra pre-shift)
    T = r3 & 1
    r3 = (r3 >> 1) & M
    if T:                         # extra shift pair (r2,r5)
        T = (r2 >> 31) & 1; r2 = (r2 << 1) & M
        t = (r5 >> 31) & 1; r5 = ((r5 << 1) | T) & M; T = t
    # regular shift pair (r2,r5)
    T = (r2 >> 31) & 1; r2 = (r2 << 1) & M
    t = (r5 >> 31) & 1; r5 = ((r5 << 1) | T) & M; T = t

    # 29-iteration restoring-sqrt loop (r6 = 29..1)
    for _ in range(29):
        t = (r0 >> 31) & 1
        r0 = ((r0 << 1) | 1) & M          # 476C rotcl r0 (T=1 from cmp/pl r6)
        T = t
        T = 1 if (r5 & M) >= (r0 & M) else 0   # 476E cmp/hs r0,r5
        if T:                             # subtract path (4770 bt)
            t = (r1 >> 31) & 1
            r1 = ((r1 << 1) | 1) & M      # 4772 rotcl r1 (T=1)
            T = t
            r5 = (r5 - r0) & M            # 4774 sub r0,r5
            r0 = (r0 + 1) & M             # 4778 add #1,r0
        else:
            r0 = (r0 ^ 1) & M             # 477A xor #1,r0
            t = (r1 >> 31) & 1
            r1 = ((r1 << 1) | 0) & M      # 477C rotcl r1 (T=0)
            T = t
        # shift pair x2 (shll r2; rotcl r5) each iteration
        for _ in range(2):
            T = (r2 >> 31) & 1; r2 = (r2 << 1) & M
            t = (r5 >> 31) & 1; r5 = ((r5 << 1) | T) & M; T = t

    # ---- phase 2 (two-bit remainder + sticky round) ----------------------
    r6 = 0
    r7 = 0
    # 4790 sett ; 4792 rotcl r0 ; 4794 cmp/hs r0,r5
    t = (r0 >> 31) & 1; r0 = ((r0 << 1) | 1) & M; T = t
    T = 1 if (r5 & M) >= (r0 & M) else 0
    if T:
        t = (r1 >> 31) & 1; r1 = ((r1 << 1) | 1) & M; T = t   # 4798
        r5 = (r5 - r0) & M                # 479A sub
        r0 = (r0 + 1) & M                 # 479E add #1,r0
    else:
        r0 = (r0 ^ 1) & M                 # 47A0 xor #1,r0
        t = (r1 >> 31) & 1; r1 = ((r1 << 1) | 0) & M; T = t   # 47A2
    # 47A4/47A6/47A8: shll r2 ; rotcl r5 ; rotcl r6  (x2)
    for _ in range(2):
        T = (r2 >> 31) & 1; r2 = (r2 << 1) & M
        t = (r5 >> 31) & 1; r5 = ((r5 << 1) | T) & M; T = t
        t = (r6 >> 31) & 1; r6 = ((r6 << 1) | T) & M; T = t
    # 47B0 sett ; 47B2 rotcl r0 ; 47B4 rotcl r7
    t = (r0 >> 31) & 1; r0 = ((r0 << 1) | 1) & M; T = t
    t = (r7 >> 31) & 1; r7 = ((r7 << 1) | T) & M; T = t
    # 47B6 cmp/hi r6,r7 -> T = (r6 > r7)
    T = 1 if (r6 & M) > (r7 & M) else 0
    if T:                                # 47B8 bt 47C2  (subtract block)
        t = (r1 >> 31) & 1; r1 = ((r1 << 1) | 1) & M; T = t
        borrow = T
        lo = r5 - r0 - borrow; r5 = lo & M
        r6 = (r6 - r7 - (1 if lo < 0 else 0)) & M
    else:
        T = 1 if (r6 & M) >= (r7 & M) else 0      # 47BA cmp/hs r6,r7
        if not T:                                 # 47BC bf 47CA  (append 0)
            t = (r1 >> 31) & 1; r1 = ((r1 << 1) | 0) & M; T = t
        else:
            TT = 1 if (r5 & M) >= (r0 & M) else 0 # 47BE cmp/hs r5,r0
            if TT:                                # 47C0 bt 47C2 (subtract)
                t = (r1 >> 31) & 1; r1 = ((r1 << 1) | 1) & M; T = t
                borrow = T
                lo = r5 - r0 - borrow; r5 = lo & M
                r6 = (r6 - r7 - (1 if lo < 0 else 0)) & M
            else:                                 # append 0 (47CA)
                t = (r1 >> 31) & 1; r1 = ((r1 << 1) | 0) & M; T = t
    # 47CC..47D6: shll r2; rotcl r5; rotcl r6 (x4)
    for _ in range(4):
        T = (r2 >> 31) & 1; r2 = (r2 << 1) & M
        t = (r5 >> 31) & 1; r5 = ((r5 << 1) | T) & M; T = t
        t = (r6 >> 31) & 1; r6 = ((r6 << 1) | T) & M; T = t
    # 47D8 shll r1 ; rounding: sticky round-up if remainder != 0
    r1 = (r1 << 1) & M
    if r6 != 0 or r5 != 0:
        r1 = (r1 | 1) & M
    r3 &= 0xFFFF                  # 47E6 extu.w
    return (r3, r1)


# ---------------------------------------------------------------------------
# Emulator driver — sets the stack exactly as caller 0x46CC does.
# ---------------------------------------------------------------------------
def run_rom(cpu, a0, a1):
    """Execute the ROM bytes @0x4740 with (a0, a1) on the stack; return the
    two 32-bit words the routine stores at [out] / [out+4]."""
    ram = {}
    for ad, val in ((STACK, OUT), (STACK + 4, a0), (STACK + 8, a1)):
        for k in range(4):
            ram[ad + k] = (val >> (8 * (3 - k))) & 0xFF
    cpu.call(ADDR, ram=ram)
    return (cpu.rd(OUT, 4), cpu.rd(OUT + 4, 4))


EDGE = [
    # (a0, a1) — low 16 bits of a0 are the argument; bit31 selects saturate.
    (0x00000000, 0x00000000),
    (0x00000000, 0x00000001),
    (0x00000000, 0xFFFFFFFF),
    (0x00000001, 0x00000001),     # odd a0 -> extra pre-shift of a1
    (0x00000002, 0x00000001),     # even a0
    (0x00000003, 0x00000001),
    (0x0000007F, 0x12345678),
    (0x00000080, 0x7FFFFFFF),
    (0x00000081, 0x80000000),
    (0x000000FF, 0xFFFFFFFF),
    (0x00007FFF, 0x00000000),     # r3 == 0x7FFF, a1 == 0  -> (0x7FFF, 0)
    (0x00007FFF, 0x00000001),     # r3 == 0x7FFF, a1 != 0  -> (0x7FFF, -1)
    (0x00007FFF, 0x7FFFFFFF),
    (0x00008000, 0x00000000),     # r3 == -32768 -> 47F8 path, bit31 clear
    (0x00008000, 0x00000001),
    (0x00008000, 0xFFFFFFFF),
    (0x00008001, 0x00000000),     # r3 == -32767 -> 47F8 path
    (0x00008001, 0x7FFFFFFF),
    (0x0000FFFE, 0x00000001),     # r3 == -2
    (0x0000FFFF, 0x00000001),     # r3 == -1
    (0x0000FFFF, 0xFFFFFFFF),
    (0x80000000, 0x00000000),     # bit31 saturate, a1 == 0 -> (0x7FFF, 0)
    (0x80000000, 0xFFFFFFFF),     # bit31 saturate, a1 != 0 -> (0x7FFF, -1)
    (0x80008000, 0x00000000),     # 47F8 path WITH bit31 set (sign folded)
    (0x80008000, 0x00000001),
    (0x80008000, 0xFFFFFFFF),
    (0x80007FFF, 0x12345678),     # bit31 set on the 0x7FFF edge
    (0x7FFFFFFF, 0xFFFFFFFF),
    (0x00001000, 0x00001000),
    (0x00001001, 0x00001000),
    (0x00010000, 0xDEADBEEF),     # a0 low16 == 0
    (0x00030000, 0xCAFEBABE),
]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    if n < 0:
        n = N_DEFAULT

    try:
        cpu = load_cpu()
    except Exception as exc:            # noqa: BLE001
        print('FATAL: cannot load ROM/emulator: %s' % exc, file=sys.stderr)
        return 2

    rng = make_rng(0x4740)
    vectors = list(EDGE) + [(rng.getrandbits(32) & 0xFFFFFFFF,
                             rng.getrandbits(32) & 0xFFFFFFFF)
                            for _ in range(n)]

    mismatches = []
    for i, (a0, a1) in enumerate(vectors):
        rom = run_rom(cpu, a0, a1)
        model = ref_4740(a0, a1)
        if rom != model:
            mismatches.append(
                'vec#%d a0=0x%08X a1=0x%08X ROM=(0x%08X,0x%08X) '
                'MODEL=(0x%08X,0x%08X)'
                % (i, a0, a1, rom[0], rom[1], model[0], model[1]))
            if len(mismatches) >= 5:
                break

    if mismatches:
        print('FAIL verify_q4740 @0x%X  %d mismatch(es) on %d vectors'
              % (ADDR, len(mismatches), len(vectors)))
        for m in mismatches:
            print('    ' + m)
        return 1

    print('OK  verify_q4740  bit-exact Python model == emulated ROM @0x%X  '
          '(%d random + %d edge)' % (ADDR, n, len(EDGE)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
