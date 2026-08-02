#!/usr/bin/env python3
"""
harness_leading_trailing_spark_control_2100A.py — equivalence of
rx8_leading_trailing_spark_control_2100A @0x2100A.

Reconstructed source: samples/src/rx8_leading_trailing_spark_control_2100A.c
Verified lift   : c/leading_trailing_spark_control_2100A.c (same address,
                  committed 4e52ec6 together with
                  docs/subsystems/IGNITION_SUBSYSTEM.md; the cold-validity /
                  decay semantics documented there are re-verified here against
                  the ACTUAL ROM bytes, which the emulator always executes).

The function is a `void` controller with NO ABI return value: its whole effect
is on three RAM cells — the cold/validity byte u8@0xFFFFB240 and the two
lead/trail state floats f32@0xFFFFB18C / f32@0xFFFFB188 — so the equivalence
check compares RAM side-effects, not a return value:

  - emulator side: seed the ten input cells in the sparse ram overlay (f32
    coolant @0xFFFFAA10, f32 compare input @0xFFFFC6B4, u16 gate word
    @0xFFFFB1B2, the four u8 gate flags @0xFFFFB1C7/B1C9/B1C4/B1C2, engine-off
    @0xFFFFC600, enable @0xFFFFCCE1, AC gate @0xFFFFCDA0, allow-decay
    @0xFFFFB19C) plus the three output-cell pre-states (@0xFFFFB240, f32
    @0xFFFFB18C, f32 @0xFFFFB188), call the ROM entry @0x2100A (which
    internally jsr's the REAL ROM bytes of the shared max helper @0x23E4 in the
    decay path), read the three cells back;
  - host side: the dedicated oracle mmap()s the pages backing the cells AND
    the ROM calibration page (u8 @0x71BD0, f32 @0x71C54/-40.0, @0x71C58/3.0,
    @0x71C74 & @0x71C78/0.0667, @0x71C7C/1000.0) straight from the ROM file,
    seeds the same bytes, runs the reconstructed C and prints the same three
    cells.  Floats travel as raw IEEE-754 single-precision BITS end to end, so
    the comparison is bit-exact (f2bits on the emulator side == %08X from the
    oracle), including NaN / +-inf / denormals / -0.0.

EDGE vectors cover the coolant hysteresis boundaries (-40.0 / -43.0 +/- 1 ulp,
NaN / +-inf / +-0.0 / denormals), every hard gate, the set-1.0 conjunction
(B1C2==1 && B1B2>0) / (B1C9==1 && B1C4==1) / B1C7==1, the fc() re-checks
(B19C, B1B2==0, B1C7==0, B1C9==0, C6B4 around 1000.0, B1C4!=0), the decay step
(state floats around 0.0667, 1.0, negative, NaN, huge) and distinguishable
stale pre-states for every written cell; N random pre-states follow (fixed seed
= the ROM address).

Usage:  python3 harness_leading_trailing_spark_control_2100A.py [N]
        (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, load_cpu, make_rng, report, run_oracle  # noqa: E402
# common.py already put <repo>/tools on sys.path; sh2emu is importable here.
from sh2emu import f2bits  # noqa: E402

ADDR = 0x2100A
N_DEFAULT = 20000
SEED = 0x60E1D400

# ---- cell addresses (see rx8_leading_trailing_spark_control_2100A.c) -------
AA10 = 0xFFFFAA10              # f32 coolant-temp input
C6B4 = 0xFFFFC6B4              # f32 compare input
B1B2 = 0xFFFFB1B2              # u16 gate word
B1C7 = 0xFFFFB1C7              # u8 gate flag
B1C9 = 0xFFFFB1C9              # u8 gate flag
B1C4 = 0xFFFFB1C4              # u8 gate flag
B1C2 = 0xFFFFB1C2              # u8 gate flag
C600 = 0xFFFFC600              # u8 engine-off flag
CCE1 = 0xFFFFCCE1              # u8 enable gate
CDA0 = 0xFFFFCDA0              # u8 AC/extra gate
B19C = 0xFFFFB19C              # u8 allow-decay gate
B240 = 0xFFFFB240              # u8 cold/validity flag (output)
B18C = 0xFFFFB18C              # f32 leading state word (output)
B188 = 0xFFFFB188              # f32 trailing state word (output)

# ---- ROM calibration cells (see the sample header) ----
ROM_CAL_ENABLE = 0x71BD0       # u8  (= 1)
ROM_COLD_HI    = 0x71C54       # f32 (= -40.0)
ROM_HYST       = 0x71C58       # f32 (= 3.0)
ROM_DECAY_L    = 0x71C74       # f32 (= 0.0667)
ROM_DECAY_T    = 0x71C78       # f32 (= 0.0667)
ROM_CAL_1000   = 0x71C7C       # f32 (= 1000.0)

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-leading_trailing_spark_control_2100A'

# f32 bits of the interesting boundary values used by the edge vectors.
F = {}
F['NEG40']  = f2bits(-40.0)
F['NEG43']  = f2bits(-43.0)
F['NEG42']  = f2bits(-42.0)
F['NEG44']  = f2bits(-44.0)
F['NEG39']  = f2bits(-39.0)
F['ZERO']   = 0x00000000
F['NZERO']  = 0x80000000
F['ONE']    = f2bits(1.0)
F['DECAY']  = f2bits(0.0667)             # 0x3D888889
F['FIVE']   = f2bits(0.5)
F['NEGONE'] = f2bits(-1.0)
F['PINF']   = 0x7F800000
F['NINF']   = 0xFF800000
F['QNAN']   = 0x7FC00000
F['SNAN']   = 0x7FA00000
F['BIGNAN'] = 0xFFFFFFFF
F['HUGE']   = f2bits(1e30)


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_leading_trailing_spark_control_2100A.c'),
           os.path.join(SAMPLES, 'src', 'rx8_leading_trailing_spark_control_2100A.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def seed(init, addr, n, val):
    """Byte-exact big-endian store of a width-`n` value in the ram overlay."""
    for i in range(n):
        init[addr + i] = (val >> (8 * (n - 1 - i))) & 0xFF


def run_emu(cpu, v):
    """Seed every input cell (floats as raw bits), run the ROM bytes @0x2100A
    (the max helper @0x23E4 included) and return the 3-tuple of post-state
    cells: (B240 byte, B18C float bits, B188 float bits)."""
    (coolant, c6b4, b1b2, b1c7, b1c9, b1c4, b1c2, c600, cce1, cda0,
     b19c, b240, lead0, trail0) = v
    init = {}
    seed(init, AA10, 4, coolant & 0xFFFFFFFF)
    seed(init, C6B4, 4, c6b4 & 0xFFFFFFFF)
    seed(init, B1B2, 2, b1b2 & 0xFFFF)
    init[B1C7] = b1c7 & 0xFF
    init[B1C9] = b1c9 & 0xFF
    init[B1C4] = b1c4 & 0xFF
    init[B1C2] = b1c2 & 0xFF
    init[C600] = c600 & 0xFF
    init[CCE1] = cce1 & 0xFF
    init[CDA0] = cda0 & 0xFF
    init[B19C] = b19c & 0xFF
    init[B240] = b240 & 0xFF
    seed(init, B18C, 4, lead0 & 0xFFFFFFFF)
    seed(init, B188, 4, trail0 & 0xFFFFFFFF)
    cpu.call(ADDR, ram=init)
    return (cpu.rd(B240, 1), f2bits(cpu.rdf(B18C)), f2bits(cpu.rdf(B188)))


def gen_edges():
    """Edge pre-states (coolant, c6b4, b1b2, b1c7, b1c9, b1c4, b1c2, c600,
    cce1, cda0, b19c, b240, lead0, trail0) targeting every branch."""
    v = []
    # Baseline gate configs: A = everything open (set-1.0 path reachable),
    # B = soft-gate path (B240=0), C = hard-gate, D = fc() via C6B4.
    A = dict(c6b4=F['FIVE'], b1b2=1, b1c7=1, b1c9=1, b1c4=1, b1c2=1,
             c600=0, cce1=0, cda0=0, b19c=1, b240=1)
    B = dict(c6b4=F['FIVE'], b1b2=1, b1c7=1, b1c9=1, b1c4=1, b1c2=1,
             c600=0, cce1=0, cda0=0, b19c=1, b240=0)
    D = dict(c6b4=F['HUGE'], b1b2=1, b1c7=1, b1c9=1, b1c4=1, b1c2=1,
             c600=0, cce1=0, cda0=0, b19c=1, b240=1)

    def mk(cfg, **kw):
        base = dict(coolant=F['ZERO'], lead0=F['FIVE'], trail0=F['NEGONE'],
                    **cfg)
        base.update(kw)
        return (base['coolant'], base['c6b4'], base['b1b2'], base['b1c7'],
                base['b1c9'], base['b1c4'], base['b1c2'], base['c600'],
                base['cce1'], base['cda0'], base['b19c'], base['b240'],
                base['lead0'], base['trail0'])

    # (a) coolant hysteresis: boundaries +/- 1 ulp, -0, denormals, NaN, inf.
    n40, n43 = F['NEG40'], F['NEG43']
    for t in (n40 - 1, n40, n40 + 1, n43 - 1, n43, n43 + 1,
              F['NEG39'], F['NEG42'], F['NEG44'],
              0x00000000, 0x00000001, 0x007FFFFF, 0x00800000,
              0x80000000, 0xC3480000,
              0x7F800000, 0xFF800000, 0x7FC00000, 0x7FA00000, 0xFFFFFFFF):
        v.append(mk(A, coolant=t))
        v.append(mk(B, coolant=t))
        v.append(mk(D, coolant=t))
    # (b) hard gates: engine-off / enable / cal-byte(!=1 never in stock ROM).
    for g, gv in ((C600, 1), (C600, 0xFF), (CCE1, 1), (CCE1, 0xFF)):
        v.append(mk(A, **{'c600' if g == C600 else 'cce1': gv}))
    # (c) soft gates from block B: B240 around its ==1 test, CDA0, C6B4 1000.0.
    for b240 in (0x00, 0x01, 0xFF):
        v.append(mk(A, b240=b240))
    for cda0 in (0x00, 0x01, 0xFF):
        v.append(mk(A, cda0=cda0))
    th = f2bits(1000.0)
    for c6b4 in (th - 1, th, th + 1, 0x3D888889, 0x7F800000, 0xFF800000,
                 0x7FC00000, 0xFFFFFFFF):
        v.append(mk(A, c6b4=c6b4))
        v.append(mk(B, c6b4=c6b4))
    # (d) set-1.0 conjunction, each factor around its ==1 / >0 test.
    for b1c2 in (0x00, 0x01, 0xFF):
        for b1b2 in (0x0000, 0x0001, 0x0002, 0x8000, 0xFFFF):
            v.append(mk(A, b1c2=b1c2, b1b2=b1b2))
    for b1c9 in (0x00, 0x01, 0xFF):
        for b1c4 in (0x00, 0x01, 0xFF):
            v.append(mk(A, b1c9=b1c9, b1c4=b1c4))
    for b1c7 in (0x00, 0x01, 0xFF):
        v.append(mk(A, b1c7=b1c7))
    # (e) fc() re-checks (reached via B240=0 or C6B4>1000 or failed set-1.0).
    for b19c in (0x00, 0x01, 0xFF):
        v.append(mk(B, b19c=b19c))
        v.append(mk(D, b19c=b19c))
        v.append(mk(A, b19c=b19c, b1c7=0, b1c2=0, b1c9=0, b1c4=0))
    # r4/r7/r5 == 0 -> decay; B1C4 != 0 (after all others pass) -> clear.
    for b1b2 in (0x0000, 0x0001):
        v.append(mk(D, b1b2=b1b2, b1c7=1, b1c9=1, b1c4=1, b1c2=0))
    for name in ('b1c7', 'b1c9', 'b1c4'):
        for fv in (0x00, 0x01):
            cfg = dict(b1b2=1, b1c7=1, b1c9=1, b1c4=1, b1c2=0)
            cfg[name] = fv
            v.append(mk(D, **cfg))
    # (f) decay: state floats around the 0.0667 step, 1.0, negatives, NaN.
    dec = F['DECAY']
    for st in (dec - 1, dec, dec + 1, F['ZERO'], F['NZERO'], F['ONE'],
               F['NEGONE'], F['HUGE'], 0x7F800000, 0xFF800000,
               0x7FC00000, 0x7FA00000, 0xFFFFFFFF):
        v.append(mk(B, b1b2=1, b1c7=1, b1c9=1, b1c4=1, b1c2=0,
                    lead0=st, trail0=st))
        v.append(mk(D, b1b2=1, b1c7=1, b1c9=1, b1c4=1, b1c2=0,
                    lead0=st, trail0=st))
    # (g) stale pre-states: every output cell pre-distinct to catch a cell the
    #     function forgets to (re)write on each branch.
    for (b240, lead0, trail0) in ((0x00, 0x3FAAAAAB, 0xBFAAAAAB),
                                  (0x55, 0x3F800000, 0x7FC00000),
                                  (0xFF, 0x00000001, 0xFFFFFFFF)):
        v.append(mk(A, b240=b240, lead0=lead0, trail0=trail0))
        v.append(mk(B, b240=b240, lead0=lead0, trail0=trail0))
        v.append(mk(D, b240=b240, lead0=lead0, trail0=trail0))
        v.append(mk(dict(c6b4=F['FIVE'], b1b2=1, b1c7=1, b1c9=1, b1c4=1,
                         b1c2=1, c600=0, cce1=0, cda0=0, b19c=1, b240=b240),
                    lead0=lead0, trail0=trail0))
    return v


def gen_random(rng, k):
    """k random pre-states over the full byte/word/float-bit range of every
    input, with the coolant/C6B4 biased toward the hysteresis and 1000.0
    boundaries and the gate flags biased toward their ==0/==1 hot values."""
    v = []
    th = f2bits(1000.0)
    for _ in range(k):
        # coolant: half raw bits, half near the hysteresis band.
        if rng.random() < 0.5:
            coolant = struct.unpack('>I', struct.pack(
                '>f', rng.uniform(-50.0, -30.0)))[0]
        else:
            coolant = rng.getrandbits(32)
        # C6B4: half raw bits, half near the 1000.0 threshold.
        if rng.random() < 0.5:
            c6b4 = th + rng.randrange(-3, 4)
        else:
            c6b4 = rng.getrandbits(32)
        v.append((coolant, c6b4,
                  rng.getrandbits(16),                 # b1b2
                  rng.choice((0, 1, rng.getrandbits(8))),
                  rng.choice((0, 1, rng.getrandbits(8))),
                  rng.choice((0, 1, rng.getrandbits(8))),
                  rng.choice((0, 1, rng.getrandbits(8))),
                  rng.choice((0, 1, 0xFF)),
                  rng.choice((0, 1, 0xFF)),
                  rng.choice((0, 1, 0xFF)),
                  rng.choice((0, 1, 0xFF)),
                  rng.choice((0, 1, 0xFF)),
                  rng.getrandbits(32),                 # lead0 state bits
                  rng.getrandbits(32)))                # trail0 state bits
    return v


def check_cal(cpu):
    """The stock-ROM calibration constants are fixed; refuse to run if they
    ever change so the ROM-page mapping stays meaningful."""
    def f32(x):                          # round a Python double to f32 value
        return struct.unpack('>f', struct.pack('>f', x))[0]
    def rom_f32(a):
        return struct.unpack('>f', cpu.rom[a:a + 4])[0]
    if (cpu.rom[ROM_CAL_ENABLE] != 1
            or rom_f32(ROM_COLD_HI) != f32(-40.0)
            or rom_f32(ROM_HYST) != f32(3.0)
            or rom_f32(ROM_DECAY_L) != f32(0.0667)
            or rom_f32(ROM_DECAY_T) != f32(0.0667)
            or rom_f32(ROM_CAL_1000) != f32(1000.0)):
        raise RuntimeError(
            'unexpected spark-control calibration bytes @0x%X/0x%X/0x%X/0x%X/0x%X/0x%X'
            % (ROM_CAL_ENABLE, ROM_COLD_HI, ROM_HYST, ROM_DECAY_L,
               ROM_DECAY_T, ROM_CAL_1000))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)
    check_cal(cpu)
    # The oracle maps the ROM cal page straight from the file — point it there.
    os.environ['RX8_ROM_PATH'] = ROM_PATH

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM side-effects; the 0x23E4 max
    # helper runs as real ROM bytes).
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host-C on the same pre-states (cal constants from the mapped ROM).
    lines = ['ltsp %08X %08X %04X %02X %02X %02X %02X %02X %02X %02X %02X '
             '%02X %08X %08X' % v for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the post-state triples bit-for-bit.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d coolant=%08X c6b4=%08X b1b2=%04X gates=%02X/%02X/%02X/'
                '%02X hw=%02X/%02X/%02X/%02X pre=(%02X,%08X,%08X) '
                'ROM=(%02X,%08X,%08X) C=(%02X,%08X,%08X)'
                % (i, v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8],
                   v[9], v[10], v[11], v[12], v[13], e[0], e[1], e[2],
                   h[0], h[1], h[2]))
            if len(mismatches) >= 5:
                break

    report('leading_trailing_spark_control', ADDR, n, mismatches,
           edges=len(EDGE))


if __name__ == '__main__':
    main()
