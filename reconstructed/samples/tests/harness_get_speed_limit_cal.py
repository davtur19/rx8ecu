#!/usr/bin/env python3
"""
harness_get_speed_limit_cal.py — equivalence of rx8_get_speed_limit_cal @0x49EFC.

Reconstructed source: samples/src/rx8_get_speed_limit_cal.c
Verified lift   : c/getSpeedLimitCal.c (getSpeedLimitCal @ 0x49EFC; the lift
                  modelled the speed-limit table getter more simply, see the
                  sample header's DISCREPANCIES section).

The ROM function is a `void f(void)` calibration getter: reading a set of
fixed RAM keys (variant selectors) it looks them up against fixed calibration
tables in ROM and writes three speed-limit threshold registers and four status
flags.  It takes NO ABI argument - the "limit id" is derived at runtime by the
inlined callee 0x49FC4 from RAM[0xFFFFD3D4].

All RAM cells live in the sign-extended on-chip window 0xFFFFxxxx (the ROM
reaches them with `mov.w` literals - same convention as the temperature-gauge
sample).  Each "vector" is {k0 (u32 config-B key), k34 (u16 lookup-id key),
k36 (u8 config-C key), k37 (u8 config-D key)}; the harness compares the seven
committed cells RAM[0xFFFFCD4C/0xFFFFCD4D/0xFFFFCD4E/0xFFFFCD4F/0xFFFFCD50/
0xFFFFCD51/0xFFFFCD52] after the call.

The four callees of the ROM (0x49FC4, 0x4A020, 0x4A07E, 0x4A106) are REAL
`bsr` subroutines whose bytes the emulator always executes.  The host C sample
inlines their net RAM effects (see the sample header); this harness runs the
REAL ROM bytes on the emulator and the inlined host sample on /tmp.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (every table key, every switch value, fallback/sentinel
     selectors) + N random (seeded) key vectors,
  3. run the ROM bytes @0x49EFC in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare all 7 committed cells byte-exactly — 0 mismatches required.

Usage:  python3 harness_get_speed_limit_cal.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x49EFC

# (name, addr, width-bytes) — output cells compared after the call.
LOCS = (
    ('cd4c', 0xFFFFCD4C, 1),   # threshold A
    ('cd4d', 0xFFFFCD4D, 1),   # threshold B
    ('cd4e', 0xFFFFCD4E, 1),   # threshold C
    ('cd4f', 0xFFFFCD4F, 1),   # flag - lookup 0x49FC4
    ('cd50', 0xFFFFCD50, 1),   # flag - configB
    ('cd51', 0xFFFFCD51, 1),   # flag - configC
    ('cd52', 0xFFFFCD52, 1),   # flag - configD
)
N_DEFAULT = 20000

# Valid table keys (drives the branches).
ID_KEYS   = [0x3041, 0x3031, 0x3032, 0x3036, 0x4631, 0x4630, 0x3035]
B_KEYS    = [0x31334820, 0x31335320]
C_KEYS    = [0x4E, 0x35, 0x36]
D_KEYS    = [0x30]

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-get_speed_limit_cal'


def build_oracle(cc='cc'):
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_get_speed_limit_cal.c'),
           os.path.join(SAMPLES, 'src', 'rx8_get_speed_limit_cal.c'),
           '-lm', '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def seed_ram(k0, k34, k36, k37):
    """Four selector words -> big-endian sparse-RAM overlay."""
    return {
        0xFFFFD3D0: (k0 >> 24) & 0xFF, 0xFFFFD3D1: (k0 >> 16) & 0xFF,
        0xFFFFD3D2: (k0 >> 8) & 0xFF, 0xFFFFD3D3: k0 & 0xFF,
        0xFFFFD3D4: (k34 >> 8) & 0xFF, 0xFFFFD3D5: k34 & 0xFF,
        0xFFFFD3D6: k36 & 0xFF,
        0xFFFFD3D7: k37 & 0xFF,
    }


def call_rom(cpu, k0, k34, k36, k37):
    cpu.call(ADDR, ram=seed_ram(k0, k34, k36, k37))
    return tuple(cpu.rd(addr, width) for _, addr, width in LOCS)


def fmt_vec(k0, k34, k36, k37):
    return 'spl %X %X %X %X' % (k0, k34, k36, k37)


def fmt_res(vals):
    return ' '.join('%0*X' % (w * 2, v) for v, (_, _, w) in zip(vals, LOCS))


def gen_edges():
    e = []
    # every branch of every lookup table ordering, plus fall-through selectors
    for k0 in [0x31334820, 0x31335320, 0x00000000, 0xFFFFFFFF, 0x12345678]:
        for k34 in ID_KEYS + [0x0000, 0xFFFF, 0x1234]:
            for k36 in C_KEYS + [0x00, 0xFF, 0x7E]:
                for k37 in D_KEYS + [0x00, 0xFF]:
                    e.append((k0, k34, k36, k37))
    return e


def gen_random(rng, n):
    v = []
    for _ in range(n):
        # mix valid table keys and arbitrary noise, per field
        k34 = rng.randrange(0x10000)
        k0  = rng.randrange(0x100000000)
        # bias selections toward the valid key sets
        if rng.random() < 0.6:
            k34 = rng.choice(ID_KEYS)
        if rng.random() < 0.6:
            k0 = rng.choice(B_KEYS)
        k36 = rng.choice(C_KEYS + [rng.randrange(0x100)])
        k37 = rng.choice(D_KEYS + [rng.randrange(0x100)])
        v.append((k0, k34, k36, k37))
    return v


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(ADDR)          # fixed seed = the ROM address

    vectors = gen_edges() + gen_random(rng, n)

    # (a) ROM bytes via the emulator (real callee bytes incl. all cases)
    emu = [call_rom(cpu, *v) for v in vectors]
    # (b) host C on the same vectors
    host = [fmt_res(tuple(int(x, 16) for x in ln.split()))
            for ln in run_oracle(oracle, [fmt_vec(*v) for v in vectors])]

    # (c) compare all 7 output cells.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if fmt_res(e) != h:
            mismatches.append('vec#%d init=%s ROM=%s C=%s'
                              % (i, fmt_vec(*v).replace('spl ', ''), fmt_res(e), h))
            if len(mismatches) >= 5:
                break

    report('getSpeedLimitCal', ADDR, n, mismatches, edges=len(gen_edges()))


if __name__ == '__main__':
    main()