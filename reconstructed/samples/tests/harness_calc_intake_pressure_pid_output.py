#!/usr/bin/env python3
"""
harness_calc_intake_pressure_pid_output.py — equivalence of
rx8_calc_intake_pressure_pid_output @0x1252C.

Reconstructed source: samples/src/rx8_calc_intake_pressure_pid_output.c
Verified lift   : c/calc_intake_pressure_pid_output_1252C.c (same address; the
                  ROM bytes are executed for real here via tools/sh2emu.py).

The function is a void state machine with NO ABI return value: its whole effect
is a single float write, RAM[0xFFFFA63C] = clamp(correction, RAM[0xFFFFA658],
65.0), where `correction` is selected from three references (see the .c header).
The equivalence check therefore compares RAM side-effects (the written float,
bit-for-bit), not a return value:

  - emulator side: seed the ten RAM inputs in the sparse ram overlay (rpm
    @0xFFFFB5B8, target @0xFFFFA790, error @0xFFFFBCE4, closed-loop @0xFFFFAADA,
    idle flag @0xFFFFCE58, fuel cut @0xFFFFBC36, lambda @0xFFFFA9B8,
    alt ref @0xFFFFA9A8, default ref @0xFFFFA640, clamp low @0xFFFFA658), call
    the ROM entry @0x1252C, read the output float @0xFFFFA63C back;
  - host side: the dedicated oracle mmap()s the pages backing the RAM cells AND
    the two ROM calibration pages (0x12600/0x12608 and 0x6E3D4/0x6E3D8/0x6E3F0),
    seeds the same bytes (calibration values shipped inline, taken from the
    stock 60E1D400.bin) and prints the written float bits.

The ROM internally jsr's two non-ABI leaves (0x2440 deadband test, 0x2404 clamp)
whose REAL ROM bytes the emulator executes; the reconstructed source inlines
their semantics as static helpers (see the .c header).

NOTE on calibration: the stock enable byte @0x6E3D4 is 0, so in the real ROM
the `(enable == 0 || r2 == 0)` gate is always taken and the |error|-deadband
(`r2`) arm is never the deciding factor — the harness therefore ships the stock
calibration values verbatim (as oracle_purge_control_state_update.py does) so
emulator and oracle read byte-identical constants.  The |target|-deadband (`r1`)
IS independently exercised because it gates the closed-loop idle path.

EDGE vectors cover: the idle path around every boundary (target at +/-1e-5 and
1 ulp around it, rpm around 2000.0, the two mode flags around their ==1 tests),
the cruise path with lambda around 0.0 and clamp window boundaries (clamp low at
64.0/65.0, references above/below the window), non-bool mode bytes (any nonzero
tests as true via tst), and NaN/Inf everywhere (SH-2 fcmp/gt reports unordered
like C `>`); N random vectors follow (fixed seed).

Usage:  python3 harness_calc_intake_pressure_pid_output.py [N]  (default N = 20000)
"""
import math
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402
from sh2emu import f2bits, bits2f, ts  # noqa: E402

ADDR = 0x1252C
N_DEFAULT = 20000
SEED = 0x1252C

# RAM inputs / output (float inputs big-endian, byte inputs single bytes).
RPM_ADDR = 0xFFFFB5B8
TARGET_ADDR = 0xFFFFA790
ERROR_ADDR = 0xFFFFBCE4
CL_ACTIVE_ADDR = 0xFFFFAADA
IDLE_FLAG_ADDR = 0xFFFFCE58
FUEL_CUT_ADDR = 0xFFFFBC36
LAMBDA_ADDR = 0xFFFFA9B8
ALT_REF_ADDR = 0xFFFFA9A8
DEFAULT_REF_ADDR = 0xFFFFA640
CLAMP_LO_ADDR = 0xFFFFA658
PID_OUT_ADDR = 0xFFFFA63C

# ROM calibration addresses.
CAL_DB_ADDR = 0x00012600     # float deadband (1e-5)
CAL_RT_ADDR = 0x00012608     # float rpm threshold (2000.0)
CAL_EN_ADDR = 0x0006E3D4     # u8 enable flag (0)
CAL_CORR_ADDR = 0x0006E3D8   # float -5.0 correction
CAL_CHI_ADDR = 0x0006E3F0    # float 65.0 clamp high

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-calc_intake_pressure_pid_output'


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests',
                        'oracle_calc_intake_pressure_pid_output.c'),
           os.path.join(SAMPLES, 'src',
                        'rx8_calc_intake_pressure_pid_output.c'),
           '-lm',
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def load_cal(cpu):
    """The five calibration constants straight from the stock ROM bytes."""
    db = struct.unpack_from('>f', cpu.rom, CAL_DB_ADDR)[0]
    rt = struct.unpack_from('>f', cpu.rom, CAL_RT_ADDR)[0]
    en = cpu.rom[CAL_EN_ADDR]
    corr = struct.unpack_from('>f', cpu.rom, CAL_CORR_ADDR)[0]
    chi = struct.unpack_from('>f', cpu.rom, CAL_CHI_ADDR)[0]
    if (db, rt, en, corr, chi) != (ts(1e-5), ts(2000.0), 0, ts(-5.0), ts(65.0)):
        raise RuntimeError('unexpected ROM calibration @0x%X/0x%X/0x%X/0x%X/0x%X: '
                           '%r %r %r %r %r' % (CAL_DB_ADDR, CAL_RT_ADDR,
                                               CAL_EN_ADDR, CAL_CORR_ADDR,
                                               CAL_CHI_ADDR,
                                               db, rt, en, corr, chi))
    return (f2bits(db), f2bits(rt), f2bits(corr), f2bits(chi), en)


def gen_edges():
    """EDGE vectors.  Vector tuple: (rpm, target, error, cl, idle, fc,
    lambda, alt_ref, default_ref, clamp_lo)."""
    db = 1e-5
    v = []
    # Idle path boundaries: target around +/-deadband, rpm around 2000.0.
    tgt_edges = [0.0, db, -db,
                 math.nextafter(db, 0.0), math.nextafter(db, math.inf),
                 math.nextafter(-db, 0.0), math.nextafter(-db, -math.inf),
                 0.5, -0.5, float('nan')]
    rpm_edges = [1500.0, 1999.0, 2000.0, 2001.0, 2500.0, 0.0,
                 math.nextafter(2000.0, -math.inf),
                 math.nextafter(2000.0, math.inf), float('nan')]
    for rpm in rpm_edges:
        for tgt in tgt_edges:
            for cl, idle, fc in ((1, 1, 0), (1, 1, 1), (1, 0, 0),
                                 (0, 1, 0), (0, 0, 1)):
                v.append((rpm, tgt, 0.0, cl, idle, fc, 1.0, 10.0, 5.0, -10.0))
    # Cruise path: lambda around 0.0, references around the clamp window.
    lam_edges = [-1.0, -1e-30, -0.0, 0.0, 1e-30, 1.0, float('nan')]
    ref_edges = [-50.0, -10.0, 0.0, 10.0, 64.0, 64.9999, 65.0, 65.0001,
                 100.0, float('nan')]
    for lam in lam_edges:
        for alt in ref_edges:
            for dflt, clo in ((-5.0, 0.0), (100.0, -50.0), (64.0, 64.0),
                              (float('nan'), -10.0)):
                for cl, idle, fc in ((1, 1, 0), (0, 0, 1), (1, 0, 0)):
                    v.append((2500.0, 0.0, 0.0, cl, idle, fc,
                              lam, alt, dflt, clo))
    # error deadband is computed but gated off (stock enable == 0); still poke
    # it so the fsub/fadd path in leaf 0x2440 is executed with non-trivial data.
    for err in (-0.5, 0.0, 0.5, float('nan')):
        v.append((2500.0, 0.0, err, 1, 0, 0, 1.0, 10.0, 5.0, -10.0))
    # Non-bool mode bytes: tst treats any nonzero byte as true.
    for cl, idle, fc in ((2, 1, 0), (0xFF, 1, 0), (1, 2, 0), (1, 0xFF, 0),
                         (1, 1, 2), (1, 1, 0xFF), (0x80, 0x80, 0x80)):
        v.append((1500.0, 0.0, 0.0, cl, idle, fc, 1.0, 10.0, 5.0, -10.0))
    # clamp low as NaN (the clamp leaf must hand NaN back through to the write).
    v.append((2500.0, 0.0, 0.0, 1, 0, 0, 1.0, 10.0, 5.0, float('nan')))
    return v


def gen_random(rng, n):
    """n random vectors: floats uniform in-range (15% raw bits to hit NaN/Inf/
    denormals), mode bytes uniform over the full byte range."""

    def pick(lo, hi):
        if rng.random() < 0.15:
            return bits2f(rng.getrandbits(32))
        return ts(rng.uniform(lo, hi))

    return [(pick(0.0, 9000.0), pick(-20.0, 20.0), pick(-20.0, 20.0),
             rng.randrange(256), rng.randrange(256), rng.randrange(256),
             pick(-5.0, 5.0), pick(-50.0, 50.0), pick(-50.0, 50.0),
             pick(-50.0, 50.0))
            for _ in range(n)]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)
    db, rt, corr, chi, en = load_cal(cpu)

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM side-effect at 0xFFFFA63C).
    emu = []
    for (rpm, tgt, err, cl, idle, fc, lam, alt, dflt, clo) in vectors:
        ram = {}
        for a, x in ((RPM_ADDR, rpm), (TARGET_ADDR, tgt), (ERROR_ADDR, err),
                     (LAMBDA_ADDR, lam), (ALT_REF_ADDR, alt),
                     (DEFAULT_REF_ADDR, dflt), (CLAMP_LO_ADDR, clo)):
            b = struct.pack('>f', x)
            for i in range(4):
                ram[a + i] = b[i]
        ram[CL_ACTIVE_ADDR] = cl & 0xFF
        ram[IDLE_FLAG_ADDR] = idle & 0xFF
        ram[FUEL_CUT_ADDR] = fc & 0xFF
        cpu.call(ADDR, ram=ram)
        emu.append(cpu.rdf(PID_OUT_ADDR))

    # (b) host-C on the same inputs (floats as raw bits; stock cal inline).
    caltok = ' '.join('%08X' % b for b in (db, rt, corr, chi)) + ' %02X' % en
    lines = ['pid %s %08X %08X %08X %02X %02X %02X %08X %08X %08X %08X'
             % (caltok, f2bits(rpm), f2bits(tgt), f2bits(err), cl, idle, fc,
                f2bits(lam), f2bits(alt), f2bits(dflt), f2bits(clo))
             for (rpm, tgt, err, cl, idle, fc, lam, alt, dflt, clo) in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare the written float bits bit-for-bit.
    mismatches = []
    for i, (vec, e, h) in enumerate(zip(vectors, emu, host)):
        if f2bits(e) != h:
            rpm, tgt, err, cl, idle, fc, lam, alt, dflt, clo = vec
            mismatches.append(
                'vec#%d rpm=%08X tgt=%08X err=%08X cl=%02X idle=%02X fc=%02X '
                'lam=%08X alt=%08X dflt=%08X clo=%08X ROM=%08X C=%08X'
                % (i, f2bits(rpm), f2bits(tgt), f2bits(err), cl, idle, fc,
                   f2bits(lam), f2bits(alt), f2bits(dflt), f2bits(clo),
                   f2bits(e), h))
            if len(mismatches) >= 5:
                break

    report('calc_intake_pressure_pid_output', ADDR, n, mismatches,
           edges=len(EDGE))


if __name__ == '__main__':
    main()
