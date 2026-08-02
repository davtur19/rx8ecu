#!/usr/bin/env python3
"""
harness_omp_task_0x1825E.py — equivalence of rx8_omp_task_0x1825E @0x1825E.

Reconstructed source: samples/src/rx8_omp_task_0x1825E.c
Verified lift   : c/omp_task_0x1825E.c (same address, in c/verified_addrs.txt;
                  verified there by c/tests/test_omp_task_0x1825E.py over
                  150000+ random inputs across 5 seeds; the ROM bytes are
                  executed for real here via tools/sh2emu.py, including all
                  six jsr leaves 0x3ED3C / 0x3EE58 / 0x2478 / 0x18552 /
                  0x18860 / 0x189EE and the three inlined task leaves
                  0x18C6C / 0x18C5C / 0x18C08).

The ROM function is the OMP RTOS task (top of the stepper-motor control
chain).  void, no ABI args / no return value: its whole effect is on RAM, so
equivalence is judged on RAM side-effects, not a return value:

  - emulator side: seed the A968..A999 RAM block (dispatch flags + state
    cells), A8F1, the C6AC fault flag, the ECD hardware-fault register, the
    CD06 gate, the three complement-encoded port pairs 0x8078/0x807A/0x807C,
    the u16 F746 stepper port and the f32 coolant temp @0xFFFFAA10 in the
    sparse ram overlay, call the ROM entry @0x1825E (sr=0xF0, matching the
    RTOS) and read the 34 writable side-effect cells back;
  - host side: the dedicated oracle mmap()s the pages backing the same cells
    AND the ROM calibration page @0x78000 (stock bytes CAL35/36/37 @0x78E35..
    0x78E37, the 0x18860-leaf cal bytes @0x78E33/0x78E34 and the f32 -40.0
    @0x78E68), seeds the same bytes, runs the reconstructed C and prints the
    same 34 cells.

EDGE vectors cover every branch: the hardware fault gate (ECD bit1 x A976 x
A987, incl. the 0->1 A976 edge), the engine-on accumulation, the idle reset,
the countdown boundaries (0/1/2/3/0x80/0xFF), the purge block (A977/A978 x
P8078 valid/broken), all five dispatch arms (A998 wave-reload x A974, A968
waveform-SM x A985/A981/temp/port-validity, A96A diag+rotor x CD06/A980/A8F1
vs A974, A96B purge-wave, A969 rotor-sync x A984/A98B/A97C/A974), the common
tail (P807A write on A96C&&A987, ramp thresholds around CAL36=0x34 /
CAL37=0x3C, sat8 up / decrement down, A975 0/4/other, broken P7A pair) and
the epilogue stores; N random pre-states follow (fixed seed = the ROM
address), with the dispatch flags / ramp cells biased toward 0/1 exactly
like c/tests edge_bias.

Usage:  python3 harness_omp_task_0x1825E.py [N]  (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x1825E
N_DEFAULT = 20000
SEED = 0x60E1D400
BUILD_DIR = '/tmp/rx8-recon-omp_task_0x1825E'

# ---- cell addresses (see rx8_omp_task_0x1825E.c) ----
A968 = 0xFFFFA968   # idle-state / dispatch flag (snapshotted at entry)
A969 = 0xFFFFA969   # rotor-sync dispatch flag
A96A = 0xFFFFA96A   # diag/rotor dispatch flag
A96B = 0xFFFFA96B   # purge-wave dispatch flag
A96C = 0xFFFFA96C   # engine-running flag
A974 = 0xFFFFA974   # position target / ramp condition
A975 = 0xFFFFA975   # ramp value
A976 = 0xFFFFA976   # OMP fault-inoperative flag
A977 = 0xFFFFA977   # warm-cal latch
A978 = 0xFFFFA978   # cold-cal latch
A979 = 0xFFFFA979   # purge-active latch
A97B = 0xFFFFA97B   # task countdown
A97C = 0xFFFFA97C   # wave step
A97D = 0xFFFFA97D   # rotor-sync step source
A97E = 0xFFFFA97E   # cal discriminator
A97F = 0xFFFFA97F   # wave position output
A980 = 0xFFFFA980   # 0x18C08 diag state
A981 = 0xFFFFA981   # 0x18860 state machine
A982 = 0xFFFFA982   # purge-enable latch
A983 = 0xFFFFA983   # cal-A purge latch
A984 = 0xFFFFA984   # rotor mode
A985 = 0xFFFFA985   # wave-SM mode
A986 = 0xFFFFA986
A987 = 0xFFFFA987   # fault-latched flag
A988 = 0xFFFFA988
A989 = 0xFFFFA989   # ramp-enable flag
A98A = 0xFFFFA98A   # wave discriminator
A98B = 0xFFFFA98B   # rotor state
A98D = 0xFFFFA98D   # wave mode latch
A998 = 0xFFFFA998   # wave-reload dispatch flag
A8F1 = 0xFFFFA8F1   # rotor-sync compare target
ECD  = 0xFFFF9ECD   # hardware fault register, bit1 = OMP fault
CD06 = 0xFFFFCD06   # 0x18C08 gate
C6AC = 0xFFFFC6AC   # ADDRESS_VAL fault flag (leaf 0x3F050)
B5F3 = 0xFFFFB5F3   # 0x9668 diag-table footprint
AA10 = 0xFFFFAA10   # f32 coolant temp (read by the 0x18860 leaf)
P78  = 0xFFFF8078   # ramp output port (complementary u16)
P7A  = 0xFFFF807A   # idle/off port (complementary u16)
P7C  = 0xFFFF807C   # purge port (complementary u16)
F746 = 0xFFFFF746   # stepper drive port (u16)

# ---- ROM calibration bytes (page 0x78000, verified below) ----
CAL_A_ADDR = 0x00078E33   # u8 0x3C (0x18860 leaf)
CAL_B_ADDR = 0x00078E34   # u8 0x3C (0x18860 leaf)
CAL35_ADDR = 0x00078E35   # u8 0x02 (P8078 write value)
CAL36_ADDR = 0x00078E36   # u8 0x34 (ramp r7 threshold)
CAL37_ADDR = 0x00078E37   # u8 0x3C (ramp A974 threshold)
CAL_T_ADDR = 0x00078E68   # f32 -40.0 (0x18860 leaf)

# ---- the 34 writable side-effect cells both sides compare ----
OUT = (A974, A975, A976, A977, A978, A979, A97B, A97C, A97D, A97E, A97F,
       A980, A981, A982, A983, A984, A985, A986, A987, A988, A989,
       A98A, A98B, A98D,
       C6AC, B5F3,
       P78, P78 + 1, P7A, P7A + 1, P7C, P7C + 1,
       F746, F746 + 1)

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- vector layout: 6 cal tokens, 50 A9xx bytes, 16 loose cells/temp ----
IDX_A8F1 = 56
IDX_C6AC = 57
IDX_ECD = 58
IDX_CD06 = 59
IDX_P78 = 60
IDX_P7A = 62
IDX_P7C = 64
IDX_F746 = 66
IDX_T = 68


def o(a):
    """Vector index of an A9xx-block byte (A968..A999)."""
    return 6 + (a - A968)


def base_vec():
    """Quiescent pre-state: all zeros except the cal tokens and valid
    complementary port pairs."""
    v = [0] * 72
    v[0:5] = [0x02, 0x34, 0x3C, 0x3C, 0x3C]     # CAL35 CAL36 CAL37 CAL_A CAL_B
    v[5] = 0xC2200000                            # f32 -40.0 bits
    v[IDX_P78] = 0x37; v[IDX_P78 + 1] = 0xC8    # valid pair 0x37
    v[IDX_P7A] = 0x37; v[IDX_P7A + 1] = 0xC8    # valid pair 0x37
    v[IDX_P7C] = 0x00; v[IDX_P7C + 1] = 0xFF    # valid pair 0x00
    return v


def f32_bytes(t):
    b = struct.unpack('>I', struct.pack('>f', t))[0]
    return [(b >> 24) & 0xFF, (b >> 16) & 0xFF, (b >> 8) & 0xFF, b & 0xFF]


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_omp_task_0x1825E.c'),
           os.path.join(SAMPLES, 'src', 'rx8_omp_task_0x1825E.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def fmt(v):
    """72 tokens: `omp` + 6 cal (calt as 8 hex digits) + 66 bytes."""
    return ' '.join(['omp'] + ['%02X' % x for x in v])


def run_emu(cpu, v):
    """Seed every input cell, run the ROM bytes @0x1825E (callees included)
    and return the 34-tuple of post-state cells with side effects visible."""
    init = {}
    for i in range(50):
        init[A968 + i] = v[6 + i]
    init[A8F1] = v[IDX_A8F1]
    init[C6AC] = v[IDX_C6AC]
    init[ECD] = v[IDX_ECD]
    init[CD06] = v[IDX_CD06]
    init[P78] = v[IDX_P78]; init[P78 + 1] = v[IDX_P78 + 1]
    init[P7A] = v[IDX_P7A]; init[P7A + 1] = v[IDX_P7A + 1]
    init[P7C] = v[IDX_P7C]; init[P7C + 1] = v[IDX_P7C + 1]
    init[F746] = v[IDX_F746]; init[F746 + 1] = v[IDX_F746 + 1]
    for i in range(4):
        init[AA10 + i] = v[IDX_T + i]
    cpu.call(ADDR, ram=init, sr=0xF0)
    return tuple(cpu.rd(c, 1) for c in OUT)


def gen_edges():
    """Edge pre-states targeting every branch of the task (see module doc)."""
    v = []

    # (1) hardware fault gate: ECD bit1 x A976 pre x A987 pre.
    for ecd in (0, 1, 2, 3, 6, 0x80):
        for a976 in (0, 1, 0xFF):
            for a987 in (0, 1, 0xFF):
                vec = base_vec()
                vec[IDX_ECD] = ecd
                vec[o(A976)] = a976
                vec[o(A987)] = a987
                vec[o(A988)] = 1
                v.append(vec)

    # (2) engine-on accumulation: A988 x A96C.
    for a988 in (0, 1, 0xFF):
        for a96c in (0, 1, 0xFF):
            vec = base_vec()
            vec[o(A988)] = a988
            vec[o(A96C)] = a96c
            v.append(vec)

    # (3) idle reset: A968 x A977 x A978.
    for a968 in (0, 1):
        for a977 in (0, 1):
            for a978 in (0, 1):
                vec = base_vec()
                vec[o(A968)] = a968
                vec[o(A977)] = a977
                vec[o(A978)] = a978
                v.append(vec)

    # (4) countdown boundaries: A97B x A96C (partial-epilogue store).
    for a97b in (0, 1, 2, 3, 0x80, 0xFF):
        for a96c in (0, 1):
            vec = base_vec()
            vec[o(A97B)] = a97b
            vec[o(A96C)] = a96c
            v.append(vec)

    # (5) purge block: A97B=2 -> 1, A968=1, A982=1; A977/A978 x P8078 pair.
    for a977 in (0, 1):
        for a978 in (0, 1):
            for p78v in (0x00, 0x01, 0x40, 0xFF):
                for broken in (0, 1):
                    vec = base_vec()
                    vec[o(A97B)] = 2
                    vec[o(A968)] = 1
                    vec[o(A982)] = 1
                    vec[o(A977)] = a977
                    vec[o(A978)] = a978
                    if broken:
                        vec[IDX_P78], vec[IDX_P78 + 1] = p78v, 0x5A
                    else:
                        vec[IDX_P78], vec[IDX_P78 + 1] = p78v, (~p78v) & 0xFF
                    v.append(vec)

    # (6) dispatch: A998 wave-reload leaf x A974.
    for a974 in (0, 6, 7, 8, 9, 0xFF):
        vec = base_vec()
        vec[o(A998)] = 1
        vec[o(A974)] = a974
        vec[o(A97B)] = 0
        v.append(vec)

    # (7) dispatch: A968 waveform-SM leaf x A985/A981/temp/port-validity.
    temps = (0xC2200000, 0xC21FFFFF, 0xC2480000, 0x41F00000, 0x7FC00000,
             0x00000000)                       # -40, -39.999, -50, 30, NaN, 0
    ports = ((0x00, 0xFF, 0x01, 0xFE),         # 8078=0 -> 8078!=0 gate fails
             (0x40, 0xBF, 0x01, 0xFE),         # valid, 807C==1 -> temp split
             (0x40, 0xBF, 0x02, 0xFD),         # valid, 807C==2 -> cal A
             (0x40, 0x5A, 0x01, 0xFE),         # 8078 broken -> cal A
             (0x40, 0xBF, 0x01, 0x00))         # 807C broken -> cal A
    for a985 in (0, 1, 2, 0xFF):
        for a981 in (0, 1, 2, 3):
            for tb in temps:
                for (b, bc, c, cc) in ports:
                    vec = base_vec()
                    vec[o(A968)] = 1
                    vec[o(A985)] = a985
                    vec[o(A981)] = a981
                    vec[o(A97B)] = 0
                    vec[IDX_T:IDX_T + 4] = [(tb >> 24) & 0xFF,
                                            (tb >> 16) & 0xFF,
                                            (tb >> 8) & 0xFF, tb & 0xFF]
                    vec[IDX_P78] = b; vec[IDX_P78 + 1] = bc
                    vec[IDX_P7C] = c; vec[IDX_P7C + 1] = cc
                    v.append(vec)

    # (8) dispatch: A96A && !CD06 -> 0x18C08 diag+rotor leaf.
    for cd06 in (0, 1):
        for a980 in (0, 1, 2, 0xFF):
            for eq in (0, 1):
                vec = base_vec()
                vec[o(A96A)] = 1
                vec[IDX_CD06] = cd06
                vec[o(A980)] = a980
                vec[o(A974)] = 0x55
                vec[IDX_A8F1] = 0x55 if eq else 0xAA
                vec[o(A984)] = 3
                v.append(vec)

    # (9) dispatch: A96B purge-wave leaf (incl. the CD06-gated A96A case).
    vec = base_vec(); vec[o(A96B)] = 1; v.append(vec)
    vec = base_vec(); vec[o(A96B)] = 1; vec[o(A96A)] = 1; vec[IDX_CD06] = 1
    v.append(vec)

    # (10) dispatch: A969 rotor-sync detector x A984/A98B/A97C/A974.
    for a984 in (0, 1, 0xFF):
        for a98b in (0, 1, 2, 3, 4, 5, 0xFF):
            for a97c in (0, 1, 4, 5, 8):
                for a974 in (0, 4, 5, 0xFF):
                    vec = base_vec()
                    vec[o(A969)] = 1
                    vec[o(A984)] = a984
                    vec[o(A98B)] = a98b
                    vec[o(A97C)] = a97c
                    vec[o(A974)] = a974
                    vec[IDX_A8F1] = 0x40
                    v.append(vec)

    # (11) common tail: A96C/A987 gated P807A write + A975 ramp around the
    # CAL36=0x34 / CAL37=0x3C thresholds (P807A always rewritten here).
    for a974 in (0, 0x3B, 0x3C, 0x3D, 0xFF):
        for a976 in (0, 1, 0xFF):
            for a975 in (0, 1, 4, 5, 0xFF):
                for p7a in (0x00, 0x33, 0x34, 0x35, 0x80, 0xFF):
                    vec = base_vec()
                    vec[o(A96C)] = 1
                    vec[o(A987)] = 1
                    vec[o(A989)] = 1
                    vec[o(A974)] = a974
                    vec[o(A976)] = a976
                    vec[o(A975)] = a975
                    vec[IDX_P7A] = p7a
                    vec[IDX_P7A + 1] = (~p7a) & 0xFF
                    v.append(vec)

    # (12) ramp read with no P807A write (A96C=0 or A987=0): valid P7A
    # boundary values + a broken pair (fault flag + default 0x37).
    for a96c in (0, 1):
        for a987 in (0, 1):
            for p7a in (0x33, 0x34, 0x35, 0x80):
                vec = base_vec()
                vec[o(A96C)] = a96c
                vec[o(A987)] = a987
                vec[o(A989)] = 1
                vec[o(A974)] = 0x3C
                vec[o(A976)] = 1
                vec[o(A975)] = 4
                vec[IDX_P7A] = p7a
                vec[IDX_P7A + 1] = (~p7a) & 0xFF
                v.append(vec)
    for a989 in (0, 1):
        vec = base_vec()
        vec[o(A989)] = a989
        vec[IDX_P7A] = 0x37
        vec[IDX_P7A + 1] = 0x00                  # broken pair
        v.append(vec)

    return v


def gen_random(rng, n):
    """n random pre-states over the full byte range, with the dispatch
    flags / ramp cells biased toward their interesting values (mirrors
    c/tests edge_bias)."""
    v = []
    for _ in range(n):
        vec = base_vec()
        for i in range(50):
            vec[6 + i] = rng.randrange(256)
        vec[IDX_A8F1] = rng.randrange(256)
        vec[IDX_C6AC] = rng.choice((0, 1, rng.randrange(256)))
        vec[IDX_ECD] = rng.choice((0, 1, 2, 3, 6, 0x80))
        vec[IDX_CD06] = rng.randrange(256)
        for base in (IDX_P78, IDX_P7A, IDX_P7C):
            if rng.random() < 0.7:
                val = rng.randrange(256)
                vec[base] = val
                vec[base + 1] = (~val) & 0xFF
            else:
                vec[base] = rng.randrange(256)
                vec[base + 1] = rng.randrange(256)
        vec[IDX_F746] = rng.randrange(256)
        vec[IDX_F746 + 1] = rng.randrange(256)
        r = rng.random()
        if r < 0.3:
            t = rng.choice((-40.0, -39.999, -50.0, 30.0, 0.0))
        else:
            t = rng.uniform(-100.0, 150.0)
        vec[IDX_T:IDX_T + 4] = f32_bytes(t)
        # bias the dispatch flags / ramp cells toward 0/1 like the c-test
        vec[o(A968)] = rng.choice((0, 1, 0, 1, rng.randrange(256)))
        vec[o(A969)] = rng.choice((0, 1, 0, 1, rng.randrange(256)))
        vec[o(A96A)] = rng.choice((0, 1, 0, 1, rng.randrange(256)))
        vec[o(A96B)] = rng.choice((0, 1, 0, 1, rng.randrange(256)))
        vec[o(A998)] = rng.choice((0, 1, 0, rng.randrange(256)))
        vec[o(A988)] = rng.choice((0, 1, rng.randrange(256)))
        vec[o(A96C)] = rng.choice((0, 1, rng.randrange(256)))
        vec[o(A982)] = rng.choice((0, 1, rng.randrange(256)))
        vec[o(A987)] = rng.choice((0, 1, rng.randrange(256)))
        vec[o(A989)] = rng.choice((0, 1, rng.randrange(256)))
        vec[o(A980)] = rng.choice((0, 1, 2, rng.randrange(256)))
        vec[o(A981)] = rng.choice((0, 1, 2, rng.randrange(256)))
        vec[o(A97B)] = rng.choice((1, 0, 2, 0xFF, rng.randrange(256)))
        vec[o(A975)] = rng.choice((0, 4, 255, rng.randrange(256)))
        vec[o(A974)] = rng.choice((0, 59, 60, 0x3B, 0x3C, 0x3D, 0xFF,
                                   rng.randrange(256)))
        vec[o(A976)] = rng.choice((0, 1, 0xFF, rng.randrange(256)))
        v.append(vec)
    return v


def check_cal(cpu):
    """The stock-Rom calibration constants are fixed; refuse to run if they
    ever change so the ROM-page mapping stays meaningful."""
    cal = list(cpu.rom[0x78E33:0x78E38])
    if cal != [0x3C, 0x3C, 0x02, 0x34, 0x3C]:
        raise RuntimeError('unexpected ROM calibration @0x78E33: %s'
                           % ' '.join('%02X' % b for b in cal))
    if struct.unpack_from('>f', cpu.rom, CAL_T_ADDR)[0] != -40.0:
        raise RuntimeError('unexpected ROM cal temp @0x%X' % CAL_T_ADDR)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)
    check_cal(cpu)

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM side-effects; the 0x3ED3C /
    # 0x3EE58 / 0x2478 / 0x18552 / 0x18860 / 0x189EE callees and the three
    # inlined task leaves run as real ROM bytes).
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host-C on the same pre-states (cal bytes shipped inline).
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, [fmt(v) for v in vectors])]

    # (c) compare the post-state 34-tuples byte-for-byte.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d ECD=%02X A97B=%02X A968=%02X A969=%02X A96A=%02X '
                'A96B=%02X A998=%02X A988=%02X A96C=%02X A982=%02X '
                'ROM=(%s) C=(%s)'
                % (i, v[IDX_ECD], v[o(A97B)], v[o(A968)], v[o(A969)],
                   v[o(A96A)], v[o(A96B)], v[o(A998)], v[o(A988)],
                   v[o(A96C)], v[o(A982)],
                   ' '.join('%02X' % x for x in e),
                   ' '.join('%02X' % x for x in h)))
            if len(mismatches) >= 5:
                break

    report('omp_task_0x1825E', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
