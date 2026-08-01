#!/usr/bin/env python3
"""
harness_rev_limit_fuel_cut_init.py — equivalence of
rx8_rev_limit_fuel_cut_init @0xF0FC.

Reconstructed source: samples/src/rx8_rev_limit_fuel_cut_init.c
Verified lift   : c/revLimitFuelCutInit.c (rev-limit fuel-cut counter init)

The function is a conditional RAM side effect: if the rev-limit enable byte
at 0xFFFF9F8C == 1, it zeroes counter cells 0xFFFFA4A4 (byte), 0xFFFFA4A5
(byte) and 0xFFFFA4A8..0xFFFFA4A9 (16-bit word); otherwise it is a no-op.
Equivalence therefore compares the RAM bytes after the call, not a return
value (Track-A RAM pattern, cf. harness_purge_flow_counter_init.py):

  - emulator side: seed the flag + the cells plus sentinel bytes in the
    sparse `ram` overlay, call the ROM entry @0xF0FC, read the seven bytes
    back;
  - host side: the oracle mmap()s the backing pages (MAP_FIXED, same trick
    as host_oracle.c), seeds the same bytes, runs the reconstructed C, reads
    them back.

The sentinels must behave exactly as the ROM does: 0xFFFFA4A3 / 0xFFFFA4A6 /
0xFFFFA4A7 are never written (they pin the store count), while 0xFFFFA4A9 is
the high byte of the 16-bit cell C and MUST be cleared when the flag is set —
the ROM's third store is `mov.w r4,@r3` (word), not a byte.  This is the
subtlety verified by this harness: an earlier byte-store reading of 0x2341
failed exactly here, and the reconstruction now matches the lift's uint16_t.

Usage:  python3 harness_rev_limit_fuel_cut_init.py [N]  (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0xF0FC
N_DEFAULT = 20000

# Flag byte plus the counter cells and the sentinels around them.
A_FLAG = 0xFFFF9F8C
A_FRONT = 0xFFFFA4A3   # sentinel: left of cell A
A_CNTA  = 0xFFFFA4A4   # counter cell A (u8)
A_CNTB  = 0xFFFFA4A5   # counter cell B (u8)
A_PAD1  = 0xFFFFA4A6   # sentinel: between cell B and cell C
A_PAD2  = 0xFFFFA4A7   # sentinel: between cell B and cell C
A_ACC   = 0xFFFFA4A8   # counter cell C (u16 low byte)
A_BACK  = 0xFFFFA4A9   # counter cell C (u16 hi byte — cleared by mov.w)
ADDRS = (A_FRONT, A_CNTA, A_CNTB, A_PAD1, A_PAD2, A_ACC, A_BACK)

EDGE = [
    # (flag, a4a3, a4a4, a4a5, a4a6, a4a7, a4a8, a4a9)
    (0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00),   # flag off, all zero
    (0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF),   # flag off, all ones
    (0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00),   # flag on, already zero
    (0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF),   # flag on, all ones
    (0x01, 0x55, 0xAA, 0x55, 0xAA, 0x55, 0xAA, 0x55),   # flag on, bit patterns
    (0x01, 0x00, 0x80, 0x00, 0x80, 0x00, 0x80, 0x00),   # sign bits set
    (0x01, 0xDE, 0xAD, 0xBE, 0xEF, 0x00, 0x00, 0xFF),   # sentinels non-zero
    (0x02, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF),   # flag == 2 -> no-op
    (0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF),   # flag == 0xFF -> no-op
    (0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01),   # flag on, all 0x01
    (0x01, 0xA5, 0x00, 0x00, 0x00, 0x00, 0x00, 0xA5),   # a4a9 cleared (word!)
    (0x00, 0x7F, 0x7F, 0x7F, 0x7F, 0x7F, 0x7F, 0x7F),   # flag off, 0x7F
]


def build_oracle():
    """Compile the reconstructed source + its own oracle into /tmp.

    (Recipe: this harness compiles its OWN oracle — only the file under test,
    not common.build_oracle's shared SRC_FILES bundle.)"""
    samples = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = '/tmp/rx8-recon-rev_limit_fuel_cut_init'
    os.makedirs(out, exist_ok=True)
    oracle = os.path.join(out, 'oracle')
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(samples, 'include'),
           '-I', os.path.join(samples, 'src'),
           os.path.join(samples, 'tests', 'oracle_rev_limit_fuel_cut_init.c'),
           os.path.join(samples, 'src', 'rx8_rev_limit_fuel_cut_init.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + [tuple(rng.randint(0, 255) for _ in range(8))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator: seed the flag + cells + sentinels,
    #     call the actual ROM bytes @0xF0FC, read the seven bytes back.
    emu = []
    for v in vectors:
        ram = {A_FLAG: v[0]}
        ram.update(dict(zip(ADDRS, v[1:])))
        cpu.call(ADDR, ram=ram)
        emu.append(tuple(cpu.ram.get(a, 0) for a in ADDRS))

    # (b) host-C on the same vectors (oracle mmap-seeds and reads back).
    lines = ['rlim %02X %02X %02X %02X %02X %02X %02X %02X' % v
             for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare.  Expected: with flag==1 cells A/B are zeroed, the 16-bit
    #     cell C is zeroed (a4a9 too), and the a4a3/a4a6/a4a7 sentinels
    #     survive; with flag!=1 nothing changes.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d pre=(flag=%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X) '
                'ROM=(%02X,%02X,%02X,%02X,%02X,%02X,%02X) '
                'C=(%02X,%02X,%02X,%02X,%02X,%02X,%02X)'
                % (i, v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7],
                   e[0], e[1], e[2], e[3], e[4], e[5], e[6],
                   h[0], h[1], h[2], h[3], h[4], h[5], h[6]))
            if len(mismatches) >= 5:
                break

    report('rev_limit_fuel_cut_init', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
