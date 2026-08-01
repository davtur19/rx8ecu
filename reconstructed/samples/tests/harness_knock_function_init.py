#!/usr/bin/env python3
"""
harness_knock_function_init.py — equivalence of rx8_knock_function_init @0xC31C.

Reconstructed source: samples/src/rx8_knock_function_init.c
Verified lift   : c/knockFunctionInit.c (knock detection subsystem init)

The function is a fixed RAM side effect: it arms the two 16-bit knock
thresholds (0xFFFFA378 / 0xFFFFA37A = 0xAC08), installs the knock-scale float
(0xFFFFA374 = 44040.0f — NOT 0.0f as the lift's comment claims), and clears
the two knock-flag bytes (0xFFFFA38C / 0xFFFFA325).  Equivalence therefore
compares the RAM bytes after the call, not a return value (Track-A RAM
pattern, cf. harness_rev_limit_fuel_cut_init.py):

  - emulator side: seed pre-state bytes + sentinels in the sparse `ram`
    overlay, call the ROM entry @0xC31C (the two BSR sub-functions @0xC346 /
    @0xC3C8 run real ROM bytes inside the emulator), read the cells back;
  - host side: the oracle mmap()s the backing page (MAP_FIXED, same trick as
    host_oracle.c), seeds the same pre-state, runs the reconstructed C (with
    the two sub-functions stubbed — the function under test depends on none
    of their writes), reads the cells back.

The 16-bit thresholds and the 32-bit float are compared as NUMERIC values so
the little-endian host and the big-endian SH-2E agree bit-for-bit; the flag
bytes and the two sentinels (0xFFFFA373 left of the float, 0xFFFFA38D right
of flag A) are compared byte-for-byte.  The sentinels must survive untouched
— they pin the store count and the write boundaries (e.g. a byte-store
mistake for the float would leave 0xFFFFA376/0xFFFFA377 at pre-state).

The critical property this harness pins is the float VALUE: the lift's
`*knock_scale = 0.0f` fails every single vector (ROM writes 0x472C0800 =
44040.0f from its own literal pool at 0xC3B0), which is what forced the
correction documented in the source header.

Usage:  python3 harness_knock_function_init.py [N]  (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0xC31C
N_DEFAULT = 20000

# Cells written by the function plus the store-width sentinels around them.
A_325 = 0xFFFFA325   # knock flag B (u8) — overwritten
A_373 = 0xFFFFA373   # sentinel: left of the scale float
A_FLT = 0xFFFFA374   # knock scale float (4 bytes) — overwritten
A_W378 = 0xFFFFA378  # threshold word A (u16) — overwritten
A_W37A = 0xFFFFA37A  # threshold word B (u16) — overwritten
A_38C = 0xFFFFA38C   # knock flag A (u8) — overwritten
A_38D = 0xFFFFA38D   # sentinel: right of flag A

# Pre-state byte order in a vector:
#   (a325, a373, flt0, flt1, flt2, flt3, w378_lo, w378_hi, w37a_lo, w37a_hi,
#    a38c, a38d)
VEC_ADDRS = (A_325, A_373, A_FLT, A_FLT + 1, A_FLT + 2, A_FLT + 3,
             A_W378, A_W378 + 1, A_W37A, A_W37A + 1, A_38C, A_38D)

EDGE = [
    (0x00,) * 12,                                  # all zero
    (0xFF,) * 12,                                  # all ones
    (0x55, 0xAA, 0x00, 0x00, 0x00, 0x00,           # float all zero, others 0x55/0xAA
     0x55, 0xAA, 0x55, 0xAA, 0x55, 0xAA),
    (0x00, 0xFF, 0x47, 0x2C, 0x08, 0x00,           # float already = ROM const
     0xAC, 0x08, 0xAC, 0x08, 0x00, 0xFF),
    (0xDE, 0xAD, 0xBE, 0xEF, 0x00, 0x00,           # bit patterns incl. sentinels
     0xFF, 0xFF, 0xFF, 0xFF, 0xDE, 0xAD),
    (0x80, 0x7F, 0x00, 0x00, 0x80, 0x00,           # sign bits set
     0x00, 0x80, 0x00, 0x80, 0x7F, 0x80),
    (0xFF, 0x00, 0xFF, 0x00, 0xFF, 0x00,           # alternating, float mid 0x00FF00FF
     0xFF, 0x00, 0xFF, 0x00, 0x00, 0xFF),
    (0x01, 0xFE, 0x00, 0x00, 0x00, 0x00,           # small values around the flags
     0x01, 0x02, 0x03, 0x04, 0x01, 0xFE),
]


def build_oracle():
    """Compile the reconstructed source + its own oracle into /tmp.

    (Recipe: this harness compiles its OWN oracle — only the file under test,
    not common.build_oracle's shared SRC_FILES bundle.)"""
    samples = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = '/tmp/rx8-recon-knock_function_init'
    os.makedirs(out, exist_ok=True)
    oracle = os.path.join(out, 'oracle')
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(samples, 'include'),
           '-I', os.path.join(samples, 'src'),
           os.path.join(samples, 'tests', 'oracle_knock_function_init.c'),
           os.path.join(samples, 'src', 'rx8_knock_function_init.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + [tuple(rng.randint(0, 255) for _ in range(12))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator: seed the pre-state + sentinels,
    #     call the actual ROM bytes @0xC31C, read the cells back.
    emu = []
    for v in vectors:
        ram = dict(zip(VEC_ADDRS, v))
        cpu.call(ADDR, ram=ram)
        fbits = struct.unpack(
            '>I', bytes(cpu.ram.get(A_FLT + i, 0) for i in range(4)))[0]
        w378 = (cpu.ram.get(A_W378, 0) << 8) | cpu.ram.get(A_W378 + 1, 0)
        w37a = (cpu.ram.get(A_W37A, 0) << 8) | cpu.ram.get(A_W37A + 1, 0)
        emu.append((fbits, w378, w37a,
                    cpu.ram.get(A_325, 0), cpu.ram.get(A_38C, 0),
                    cpu.ram.get(A_373, 0), cpu.ram.get(A_38D, 0)))

    # (b) host-C on the same vectors (oracle mmap-seeds and reads back).
    lines = ['knk %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X'
             % v for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare.  Expected post-state: float = 0x472C0800 (44040.0f), both
    #     thresholds = 0xAC08, both flag bytes = 0, and the a373/a38d
    #     sentinels survive their pre-state.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d pre=(%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X,'
                '%02X,%02X,%02X,%02X) ROM=(%08X,%04X,%04X,%02X,%02X,%02X,%02X) '
                'C=(%08X,%04X,%04X,%02X,%02X,%02X,%02X)'
                % (i, v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8],
                   v[9], v[10], v[11],
                   e[0], e[1], e[2], e[3], e[4], e[5], e[6],
                   h[0], h[1], h[2], h[3], h[4], h[5], h[6]))
            if len(mismatches) >= 5:
                break

    report('knock_function_init', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
