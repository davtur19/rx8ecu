#!/usr/bin/env python3
"""
harness_calc_fuel_pump_duty_trim.py — equivalence of
rx8_calc_fuel_pump_duty_trim @0x135F6.

Reconstructed source: samples/src/rx8_calc_fuel_pump_duty_trim.c
Verified lift   : c/calc_fuel_pump_duty_trim.c (same address; the ROM bytes
                  are executed for real here via tools/sh2emu.py — the
                  function is a leaf, so no jsr'd callees exist).

The function is a void routine with NO ABI return value: its whole effect is
three RAM float cells (the base duty RAM[0xFFFFA6F4] — rewritten only in
mode 0 — and the front/rear channel duties RAM[0xFFFFA6E4/0xFFFFA6E8] —
rewritten in modes 1 and 2), so the equivalence check compares RAM
side-effects, not a return value:

  - emulator side: seed the mode byte at 0x6E430 in the sparse ram overlay
    (which takes precedence over ROM in sh2emu.py, so all three branches are
    exercised) plus the six input f32 cells and the two output pre-states,
    call the ROM entry @0x135F6, read the three cells back;
  - host side: the dedicated oracle mmap()s the pages backing the same cells
    AND the ROM calibration page 0x6E000 (mode @0x6E430, safe-mode f32s
    @0x6E438/@0x6E43C seeded once from the ROM file), re-seeds the mode byte
    from the vector on every line, runs the reconstructed C and prints the
    same three cells (as raw f32 bits).

The mode byte in the stock 60E1D400.bin is 0x00 (mode 0 — flat copy), so
modes 1 and 2 are dead in production unless the cal byte is reflashed; the
harness overrides it on both sides (exactly how the lift was verified) to
cover all three branches plus the "any other value does nothing" case.

EDGE vectors cover: every mode class (0/1/2/3/0x80/0xFF), float bit-edge
operands (0, +/-0, denormals, 1 ulp around 0, +/-inf, NaN payloads, large
finite magnitudes) in the mode-0 source, the mode-1 fadd operands and the
mode-1 base, and distinguishable stale pre-states for every written cell to
catch any cell the function forgets to (re)write; N random pre-states follow
(fixed seed = 0x60E1D400, like the other harnesses).  Random finite floats
are bounded to |x| <= 1e30 so every mode-1 fadd stays inside the f32 finite
range (a finite+finite fadd that overflows f32 is the one input class where
the emulator's struct.pack('>f', ...) raises OverflowError instead of
rounding to inf — a real emulator limitation, avoided by construction here).

EMULATOR NaN-PAYLOAD LIMITATION (why some mode-1 fadd vectors are excluded):
the emulator (tools/sh2emu.py) computes every FPU op as a Python *double*
`f[n] +/-/*// f[m]` and then rounds through struct.pack('>f', ...) (`ts()`).
For finite operands double-then-round is correctly rounded and bit-identical
to the host C SSE single-precision fadd.  For NaN results it is NOT: the
double NaN produced by `NaN + x` carries a *double* payload, and ts()'s
double->single narrowing yields a different single NaN than the host C fadd
returns.  The reconstructed C is the CORRECT side — its x86-64 SSE fadd
performs the operation in true single precision and propagates the IEEE
single-precision NaN (second operand, quieted if signaling), e.g.
`0x7FC12345 + 0x7FA00000 -> 0x7FC12345`, `0x7FC12345 + 0x7F800001 ->
0x7FC00001`.  A canonical-NaN ts() fix would NOT help: the C payload is
operand-specific, so a single canonical value still mismatches.  The emulator
can therefore never be made to agree with the host C on the exact NaN *bits*
of a mode-1 fadd.  The harness handles this honestly: any mode-1 vector whose
fadd operand chain (base,va,vb) or (base,vc,vd) produces a NaN — i.e. any
chain containing a NaN operand, or a +inf and a -inf at any step — is
EXCLUDED (regenerated for the random part) and documented here, while every
remaining vector (including ALL mode-0/mode-2 bit-pattern copies, which are
pure fmov.s moves and round-trip NaN/Inf/denormal bits exactly) is still
compared bit-for-bit.  Mode-1 chains that produce a well-defined finite or
infinite result (Inf + finite, +Inf + +Inf, finite-only) are NOT excluded.

Usage:  python3 harness_calc_fuel_pump_duty_trim.py [N]  (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle, ROM_PATH  # noqa: E402
from sh2emu import bits2f, f2bits, ts  # noqa: E402

ADDR = 0x135F6
N_DEFAULT = 20000
SEED = 0x60E1D400
BUILD_DIR = '/tmp/rx8-recon-calc_fuel_pump_duty_trim'

# ---- RAM cells (see rx8_calc_fuel_pump_duty_trim.c) ----
MODE_ADDR = 0x0006E430          # u8 mode selector (ROM cal; overridden)
SRC_ADDR = 0xFFFFA63C           # f32 mode-0 flat-copy source
FRONT_ADDR = 0xFFFFA6E4         # f32 front channel duty out
REAR_ADDR = 0xFFFFA6E8          # f32 rear channel duty out
BASE_ADDR = 0xFFFFA6F4          # f32 base duty (in / mode-0 out)
COMP_A_ADDR = 0xFFFFA6FC        # f32 mode-1 front comp 1
COMP_B_ADDR = 0xFFFFA70C        # f32 mode-1 front comp 2
COMP_C_ADDR = 0xFFFFA700        # f32 mode-1 rear comp 1
COMP_D_ADDR = 0xFFFFA710        # f32 mode-1 rear comp 2

# ---- ROM calibration constants ----
ROM_SAFE_FRONT = 0x6E438        # f32 safe front duty (0.0 stock)
ROM_SAFE_REAR = 0x6E43C         # f32 safe rear duty  (0.0 stock)

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Special single-precision bit patterns for the raw-bits bucket (never a
# finite+finitite f32 overflow in mode 1, so the emulator's ts() is safe).
_RAW_BITS = [
    0x00000000, 0x80000000,                     # +0 / -0
    0x00000001, 0x007FFFFF, 0x00800000,         # denormals / min normal
    0x3F800000, 0xBF800000,                     # 1.0 / -1.0
    0x3F000000, 0x3FC00000,                     # 0.5 / 1.5
    0x42C80000, 0x43480000, 0xC3480000,         # 100.0 / 200.0 / -200.0
    0x38D1B717, 0xB8D1B717,                     # ~1e-4 / ~-1e-4
    0x49742400, 0xC9742400,                     # 1e6 / -1e6
    0x4E6E6B28, 0xCE6E6B28,                     # 1e9 / -1e9
    0x7F800000, 0xFF800000,                     # +inf / -inf
    0x7FC00000, 0xFFC00000,                     # quiet NaN / -quiet NaN
    0x7F800001, 0x7FA00000, 0x7FC12345,         # sNaN / NaN payloads
]


def seed_ram(init, addr, n, val):
    """Byte-exact big-endian store of a width-`n` value in the ram overlay."""
    for i in range(n):
        init[addr + i] = (val >> (8 * (n - 1 - i))) & 0xFF


def _is_nan_bits(b):
    """True iff f32 bit-pattern `b` is a NaN (any signaling/quiet payload)."""
    return (b & 0x7F800000) == 0x7F800000 and (b & 0x007FFFFF) != 0


def _is_inf_bits(b):
    """True iff f32 bit-pattern `b` is +/-infinity (zero payload)."""
    return (b & 0x7FFFFFFF) == 0x7F800000


def _fadd_chain_is_nan(seq):
    """True iff adding the f32 bit-patterns in `seq` one-by-one (with an IEEE
    single rounding after every step, as the ROM mode-1 fadd does) yields a
    NaN.  NaN operand -> NaN result; +inf + -inf at any step -> NaN.  This is
    the exact input class where the emulator's double-then-ts() NaN payload
    cannot reproduce the host-C single-precision result (see module doc)."""
    inf_sign = None
    for b in seq:
        if _is_nan_bits(b):
            return True
        if _is_inf_bits(b):
            s = (b >> 31) & 1
            if inf_sign is None:
                inf_sign = s
            elif inf_sign != s:
                return True          # +inf + -inf -> NaN
    return False


def _mode1_fadds_make_nan(v):
    """True iff vector `v` is a mode-1 case whose front ((base+va)+vb) or rear
    ((base+vc)+vd) fadd chain produces a NaN — the emulator-limited class."""
    mode, src, base, va, vb, vc, vd, front0, rear0 = v
    if mode != 1:
        return False
    return (_fadd_chain_is_nan((base, va, vb))
            or _fadd_chain_is_nan((base, vc, vd)))


def _edge_ok(v):
    """Edge vectors must stay deterministic (fixed seed); a vector whose mode-1
    fadd would emit a NaN payload is dropped instead of being regenerated."""
    return not _mode1_fadds_make_nan(v)


def run_emu(cpu, vec):
    """Seed mode + the six input f32 cells + the two output pre-states, run
    the ROM bytes @0x135F6 and return (base, front, rear) f32 bits."""
    mode, src, base, va, vb, vc, vd, front0, rear0 = vec
    init = {MODE_ADDR: mode & 0xFF}
    for a, b in ((SRC_ADDR, src), (BASE_ADDR, base), (COMP_A_ADDR, va),
                 (COMP_B_ADDR, vb), (COMP_C_ADDR, vc), (COMP_D_ADDR, vd),
                 (FRONT_ADDR, front0), (REAR_ADDR, rear0)):
        seed_ram(init, a, 4, b & 0xFFFFFFFF)
    cpu.call(ADDR, ram=init)
    return (f2bits(cpu.rdf(BASE_ADDR)),
            f2bits(cpu.rdf(FRONT_ADDR)),
            f2bits(cpu.rdf(REAR_ADDR)))


def gen_edges():
    """Edge pre-states (mode, src, base, va, vb, vc, vd, front0, rear0)."""
    v = []
    # mode classes with distinguishable stale pre-states for every cell
    for mode in (0, 1, 2, 3, 0x80, 0xFF):
        v.append((mode, 0x3F800000, 0x42480000, 0x41200000, 0x40A00000,
                  0x41000000, 0x40400000, 0xDEADBEEF, 0xCAFEBABE))
    # float bit-edges in the mode-1 operands (arithmetic path).  Vectors whose
    # fadd chain would emit a NaN (NaN operand, or +inf + -inf) are skipped:
    # the emulator cannot reproduce the host-C single-precision NaN payload
    # (module doc); the remaining mode-1 vectors are still bit-compared.
    for bits in _RAW_BITS:
        if _edge_ok((1, 0x3F800000, bits, 0x3F000000, 0xBF800000,
                     0x3FC00000, 0x38D1B717, 0xDEADBEEF, 0xCAFEBABE)):
            v.append((1, 0x3F800000, bits, 0x3F000000, 0xBF800000,
                      0x3FC00000, 0x38D1B717, 0xDEADBEEF, 0xCAFEBABE))
        if _edge_ok((1, 0x3F800000, 0x3F800000, bits, 0x3F000000,
                     0xBF800000, 0x3FC00000, 0xDEADBEEF, 0xCAFEBABE)):
            v.append((1, 0x3F800000, 0x3F800000, bits, 0x3F000000,
                      0xBF800000, 0x3FC00000, 0xDEADBEEF, 0xCAFEBABE))
        if _edge_ok((1, 0x3F800000, 0x3F800000, 0x3F000000, bits,
                     0xBF800000, 0x3FC00000, 0xDEADBEEF, 0xCAFEBABE)):
            v.append((1, 0x3F800000, 0x3F800000, 0x3F000000, bits,
                      0xBF800000, 0x3FC00000, 0xDEADBEEF, 0xCAFEBABE))
    # float bit-edges in the mode-0 copy source and the mode-2 pre-states
    for bits in _RAW_BITS:
        v.append((0, bits, 0x42480000, 0, 0, 0, 0, 0xDEADBEEF, 0xCAFEBABE))
        v.append((2, 0x3F800000, 0x42480000, 0, 0, 0, 0, bits, 0xCAFEBABE))
        v.append((2, 0x3F800000, 0x42480000, 0, 0, 0, 0, 0xDEADBEEF, bits))
    # same-bit operands / large-but-finite (no f32 overflow by construction)
    for bits in (0x7F7FFFFF, 0xFF7FFFFF, 0x6E6E6B28, 0xEE6E6B28):
        v.append((1, 0, bits, 0, 0, 0, 0, 0, 0))
        v.append((1, 0, 0, 0, 0, bits, 0, 0xDEADBEEF, 0xCAFEBABE))
    # distinct stale pre-states to catch any cell left unwritten
    for pre in (0x00000000, 0xFFFFFFFF, 0x80000000, 0x3F800000):
        v.append((0, pre, 0x42480000, 0, 0, 0, 0, pre, 0xCAFEBABE))
        v.append((1, 0x3F800000, 0x42480000, 0, 0, 0, 0, pre, pre))
        v.append((2, 0x3F800000, 0x42480000, 0, 0, 0, 0, pre, pre))
    return v


def gen_random(rng, k):
    """k random pre-states.  Mode biased to the live classes 0/1/2 plus a
    range of non-live values (any other byte -> no writes).  Floats: 50%
    realistic in-range magnitudes, 50% raw bit patterns from the safe bucket
    plus bounded magnitudes (|x| <= 1e30) so no mode-1 fadd ever overflows
    the f32 finite range inside the emulator's ts().  Vectors whose mode-1
    fadd chain would emit a NaN are rejected and re-drawn (emulator NaN-payload
    limitation, see module doc); mode 0/1/2 copies still exercise every
    NaN/Inf/denormal bit pattern bit-exactly."""
    out = []
    while len(out) < k:
        mode = rng.choice((0, 0, 0, 1, 1, 2, 2, 3, 0x80, 0xFF))
        v = (mode,
             pick(rng, -100.0, 100.0), pick(rng, -100.0, 100.0),
             pick(rng, -50.0, 50.0), pick(rng, -50.0, 50.0),
             pick(rng, -50.0, 50.0), pick(rng, -50.0, 50.0),
             rng.choice(_RAW_BITS), rng.choice(_RAW_BITS))
        if _mode1_fadds_make_nan(v):
            continue
        out.append(v)
    return out


def pick(rng, lo, hi):
    if rng.random() < 0.5:
        return rng.choice(_RAW_BITS)
    return f2bits(ts(rng.uniform(lo, hi)))


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests',
                        'oracle_calc_fuel_pump_duty_trim.c'),
           os.path.join(SAMPLES, 'src',
                        'rx8_calc_fuel_pump_duty_trim.c'),
           '-lm',
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def check_cal(cpu):
    """The stock-Rom calibration bytes are fixed; refuse to run if they ever
    change so the ROM-page mapping stays meaningful."""
    if (cpu.rom[MODE_ADDR] != 0
            or struct.unpack_from('>f', cpu.rom, ROM_SAFE_FRONT)[0] != 0.0
            or struct.unpack_from('>f', cpu.rom, ROM_SAFE_REAR)[0] != 0.0):
        raise RuntimeError('unexpected ROM calibration @0x%X/0x%X/0x%X'
                           % (MODE_ADDR, ROM_SAFE_FRONT, ROM_SAFE_REAR))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)
    check_cal(cpu)
    # The oracle maps the ROM page straight from the file — point it there.
    os.environ['RX8_ROM_PATH'] = ROM_PATH

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM side-effects; the function is
    #     a leaf, so the whole 0x135F6..0x13650 body runs as real ROM bytes).
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host-C on the same pre-states (mode + safe f32s on the mapped ROM
    #     page; the mode byte is overridden per vector on both sides).
    lines = ['fpd %02X %08X %08X %08X %08X %08X %08X %08X %08X'
             % v for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the post-state f32 bits byte-for-byte.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mode, src, base, va, vb, vc, vd, f0, r0 = v
            mismatches.append(
                'vec#%d mode=%02X src=%08X base=%08X va=%08X vb=%08X '
                'vc=%08X vd=%08X front0=%08X rear0=%08X '
                'ROM=(%08X,%08X,%08X) C=(%08X,%08X,%08X)'
                % (i, mode, src, base, va, vb, vc, vd, f0, r0,
                   e[0], e[1], e[2], h[0], h[1], h[2]))
            if len(mismatches) >= 5:
                break

    report('calc_fuel_pump_duty_trim', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
