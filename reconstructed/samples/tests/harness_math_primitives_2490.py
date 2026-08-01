#!/usr/bin/env python3
"""
harness_math_primitives_2490.py — equivalence of the three remaining scalar
math leaves of c/math_primitives.c: 0x2490 (float->u16 fixed point),
0x2500 (u8 fixed point -> float) and 0x2510 (int inverse-weighted blend).

Reconstructed source: samples/src/rx8_math_primitives_2490.c
Verified lift   : c/math_primitives.c
                  floatToFP_16bit      @ 0x2490
                  fixedPointToFloat_8bit @ 0x2500
                  fixedPointScaling    @ 0x2510

CALLING CONVENTIONS (all three are pure register-level leaves — no RAM
side-effects, so only registers are compared):
  0x2490  in fr4=number, fr5=scalar, fr6=offset; out r0 (u16, clamped)
  0x2500  in r4=raw (u8, extu.b), fr4=mult, fr5=off; out fr0 (float bits)
  0x2510  in r4=a (int32), r5=b (int32), r6=frac (u16, extu.w); out r0

FP EXACTNESS:
  * 0x2490: fsub/fdiv/fadd are separate single-precision roundings; the C
    keeps every intermediate `float` and truncates with `(int32_t)` (matches
    `ftrc`'s truncation toward zero).  The +0.5 before ftrc makes it round-
    to-nearest for the non-negative results the clamp keeps.
  * 0x2500: one fused `fmac` = single rounding; the C mirrors it by keeping
    the exact product/add in double and rounding once to float.
  * 0x2510: each FP op (float fpul, fmul, fsub, fsub, fmul) is a separate
    single rounding; the C uses `float` intermediates throughout.
  Comparison is on raw bit patterns (r0/result, fr0 bits), not values.

TEST DOMAINS (chosen to keep every `ftrc` operand inside the int32 range, so
the C `(int32_t)` casts are well-defined AND match the emulator):
  * 0x2490: |number|,|offset| <= 1e6, 2e-3 <= |scalar| <= 1e4
            -> |(n-off)/scalar| + 0.5 <= ~1e9 < 2^31
  * 0x2500: |mult|*255 + |off| < FLT_MAX (emulator ts() raises OverflowError
            on f32 overflow; magnitudes kept well below it)
  * 0x2510: |a|,|b| <= 2^30 and 0 <= frac <= 256 (so t = 1-frac/256 in
            [0,1] and |t*(b-a)| <= 2^31).  frac beyond 256 makes t < 0 with
            |t|>1, which can push the ftrc operand out of int32 range where
            the emulator's int()&MASK wrap and a host (int32_t) cast
            (cvttss2si -> INT32_MIN) would differ — the ROM's ftrc is
            hardware-undefined there and firmware never goes there (frac is a
            0..255 ramp counter).

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; own binary, common.build_oracle
     untouched),
  2. edge vectors + N random (seeded) vectors per function,
  3. run the ROM bytes @0x2490/@0x2500/@0x2510 in tools/sh2emu.py,
  4. run the host C on the same vectors,
  5. compare bit-exact — 0 mismatches required.

Usage:  python3 harness_math_primitives_2490.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402
# common() puts ROOT/tools on sys.path, so sh2emu is importable here.
from sh2emu import bits2f, f2bits  # noqa: E402

ADDR_F16 = 0x2490            # float -> u16 fixed point
ADDR_F8F = 0x2500            # u8 fixed point -> float
ADDR_FPS = 0x2510            # int blend
N_DEFAULT = 20000

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-math_primitives_2490')
ORACLE = os.path.join(BUILD_DIR, 'oracle')


def build_oracle():
    """Compile THIS sample + its own oracle (do NOT touch common.build_oracle)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_math_primitives_2490.c'),
           os.path.join(SAMPLES, 'src', 'rx8_math_primitives_2490.c'),
           '-lm', '-o', ORACLE]
    subprocess.run(cmd, check=True)
    return ORACLE


# --- IEEE-754 single-precision bit patterns used by the edge sets ------------
_ZERO = 0x00000000
_NZERO = 0x80000000
_ONE = 0x3F800000
_NEGONE = 0xBF800000
_HALF = 0x3F000000
_QTR = 0x3E800000
_P10000 = 0x461C4000             # 1.0e4
_N10000 = 0xC61C4000             # -1.0e4
_P1E30 = 0x731D254A              # ~1.0e30 (|mult|*255 ~ 2.5e32 < FLT_MAX)
_N1E30 = 0xF31D254A              # ~-1.0e30
_DEN = 0x00000001                # min denormal
_SMALL = 0x15A92A40              # ~1.0e-30
_P1EM3 = 0x3A83126F              # ~1.0e-3  (0x2490 scalar floor)
_P1E5 = 0x47C35000               # 1.0e5
_PINF = 0x7F800000
_NINF = 0xFF800000
_QNAN = 0x7FC00000

# --- 0x2490 edge set ---------------------------------------------------------
# number/offset patterns stay moderate (<= 1e6 in magnitude) so the quotient
# stays inside int32 (see header); scalar patterns avoid zero and stay
# >= 1e-3 in magnitude.
_F16_NUMS = [_ZERO, _NZERO, _ONE, _NEGONE, _HALF, _P10000, _N10000,
             0x41A00000,   # 20.0
             0xC1A00000,   # -20.0
             0x49A5E354]   # ~1.3e6
_F16_SCALS = [_ONE, _NEGONE, _HALF, _QTR, 0x40000000,  # 2.0
              _P1EM3, _P1E5, 0x42C80000,  # 100.0
              -0x42C80000, 0x431E0000,    # 158.0
              _P10000, _N10000]
_F16_OFFS = [_ZERO, _NZERO, _ONE, _NEGONE, _P10000, _N10000, _HALF,
             0xC1200000,   # -10.0
             0x49742400]   # ~1.0e6
# Full sweep: every number x every scalar x every offset.
EDGE_F16 = [(nb, sb, ob) for nb in _F16_NUMS for sb in _F16_SCALS
            for ob in _F16_OFFS]

# --- 0x2500 edge set ---------------------------------------------------------
_MVALS = [_ZERO, _NZERO, _ONE, _NEGONE, _HALF, _P10000, _P1E30, _N1E30,
          _SMALL, _DEN, _PINF, _NINF, _QNAN]
_OVALS = [_ZERO, _NZERO, _ONE, _NEGONE, _P1E30, _N1E30, _SMALL, _PINF,
          _NINF, _QNAN]
_RAWS = [0x00, 0x01, 0x7F, 0x80, 0xFF, 0x10, 0xEF]
EDGE_F8F = [(m, o, r) for m in _MVALS for o in _OVALS for r in _RAWS]

# --- 0x2510 edge set ---------------------------------------------------------
# a/b within [-2^30, 2^30]; frac within [0, 256] (see header for why).
_AB = [0x00000000, 0x00000001, 0xFFFFFFFF, 0x3FFFFFFF, 0xC0000000,
       0x20000000, 0xE0000000, 0x00008000, 0xFFFF8000, 0x40000000,
       0xC0000000, 0x12345678, 0xEDCBA987]
_FRACS = [0x0000, 0x0001, 0x007F, 0x0080, 0x00FF, 0x0100]
EDGE_FPS = [(a, b, f) for a in _AB for b in _AB for f in _FRACS]


def rflt(rng):
    """Random single-precision value with realistic firmware magnitudes."""
    return f2bits(rng.choice([rng.uniform(-1e4, 1e4), rng.uniform(-2, 2),
                              rng.uniform(0, 300), rng.uniform(-300, 0)]))


def rflt16(rng):
    """Random single-precision for 0x2490: number/offset in [-1e6,1e6]."""
    return f2bits(rng.uniform(-1e6, 1e6))


def rscalar(rng):
    """Random 0x2490 scalar: magnitude in [2e-3, 1e4], random sign, never 0."""
    mag = rng.uniform(2e-3, 1e4)
    return f2bits(-mag if rng.random() < 0.5 else mag)


def ri32_30(rng):
    """Random int32 with |v| <= 2^30 (keeps 0x2510 ftrc in int32 range)."""
    v = rng.getrandbits(30)          # 0 .. 2^30-1
    return v if rng.random() < 0.5 else -v


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x2490)

    f16_vec = list(EDGE_F16) + [(rflt16(rng), rscalar(rng), rflt16(rng))
                                for _ in range(n)]
    f8f_vec = list(EDGE_F8F) + [(rflt(rng), rflt(rng), rng.getrandbits(8))
                                for _ in range(n)]
    fps_vec = list(EDGE_FPS) + [(ri32_30(rng), ri32_30(rng),
                                 rng.getrandbits(8)) for _ in range(n)]

    # (a) ROM behaviour via the emulator.
    emu_f16 = []
    for nb, sb, ob in f16_vec:
        emu_f16.append(cpu.call(ADDR_F16, fr={4: bits2f(nb), 5: bits2f(sb),
                                              6: bits2f(ob)}))

    emu_f8f = []
    for mb, ob, raw in f8f_vec:
        cpu.call(ADDR_F8F, r4=raw, fr={4: bits2f(mb), 5: bits2f(ob)})
        emu_f8f.append(f2bits(cpu.fr[0]))

    emu_fps = []
    for a, b, f in fps_vec:
        emu_fps.append(cpu.call(ADDR_FPS, r4=a, r5=b, r6=f))

    # (b) host C on the same inputs (bit patterns round-trip exactly).
    lines = (['f16 %08X %08X %08X' % (nb, sb, ob) for nb, sb, ob in f16_vec] +
             ['f8f %08X %08X %02X' % (mb, ob, raw) for mb, ob, raw in f8f_vec] +
             ['fps %08X %08X %04X' % (a, b, f) for a, b, f in fps_vec])
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    off = 0
    host_f16 = host[off:off + len(f16_vec)]; off += len(f16_vec)
    host_f8f = host[off:off + len(f8f_vec)]; off += len(f8f_vec)
    host_fps = host[off:off + len(fps_vec)]

    # (c) compare bit-exact.
    mismatches = []
    for i, ((nb, sb, ob), e, h) in enumerate(zip(f16_vec, emu_f16, host_f16)):
        if e != h:
            mismatches.append('vec#%d number=%08X scalar=%08X offset=%08X '
                              'ROM=%04X C=%04X' % (i, nb, sb, ob, e, h))
            if len(mismatches) >= 5:
                break
    report('floatToFP_16bit', ADDR_F16, n, mismatches, edges=len(EDGE_F16))
    if mismatches:
        return

    mismatches = []
    for i, ((mb, ob, raw), e, h) in enumerate(zip(f8f_vec, emu_f8f, host_f8f)):
        if e != h:
            mismatches.append('vec#%d mult=%08X off=%08X raw=%02X '
                              'ROM=%08X C=%08X' % (i, mb, ob, raw, e, h))
            if len(mismatches) >= 5:
                break
    report('fixedPointToFloat_8bit', ADDR_F8F, n, mismatches, edges=len(EDGE_F8F))
    if mismatches:
        return

    mismatches = []
    for i, ((a, b, f), e, h) in enumerate(zip(fps_vec, emu_fps, host_fps)):
        if e != h:
            mismatches.append('vec#%d a=%08X b=%08X frac=%04X '
                              'ROM=%08X C=%08X' % (i, a, b, f, e, h))
            if len(mismatches) >= 5:
                break
    report('fixedPointScaling', ADDR_FPS, n, mismatches, edges=len(EDGE_FPS))


if __name__ == '__main__':
    main()
