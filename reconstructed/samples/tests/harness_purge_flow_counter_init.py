#!/usr/bin/env python3
"""
harness_purge_flow_counter_init.py — equivalence of
rx8_purge_flow_counter_init @0xF534.

Reconstructed source: samples/src/rx8_purge_flow_counter_init.c
Verified lift   : c/purge_flow_counter_init.c

This leaf is a pure RAM side-effect: it zeroes the three-byte EVAP purge-flow
cell (0xFFFFA4B0..0xFFFFA4B2) unconditionally, regardless of the pre-state.
Equivalence therefore compares the RAM bytes after the call, not a return
value (Track-A RAM pattern, cf. harness_idx_table.py):

  - emulator side: seed the cell plus a sentinel byte on each side in the
    sparse `ram` overlay, call the ROM entry @0xF534, read the bytes back;
  - host side: the oracle mmap()s the backing page (MAP_FIXED, same trick as
    host_oracle.c), seeds the same bytes, runs the reconstructed C, reads
    them back.

The sentinels must survive untouched: that pins the store width/count exactly
and catches any over/under-run.

Usage:  python3 harness_purge_flow_counter_init.py [N]  (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0xF534
N_DEFAULT = 20000

# Three-byte purge cell plus one sentinel byte on each side.
A_FRONT = 0xFFFFA4AF
A_FLOW  = 0xFFFFA4B0
A_STATE = 0xFFFFA4B1
A_DECEN = 0xFFFFA4B2
A_BACK  = 0xFFFFA4B3
ADDRS = (A_FRONT, A_FLOW, A_STATE, A_DECEN, A_BACK)

EDGE = [
    (0x00, 0x00, 0x00, 0x00, 0x00),   # already zero
    (0xFF, 0xFF, 0xFF, 0xFF, 0xFF),   # all ones
    (0x00, 0xFF, 0x00, 0xFF, 0x00),   # alternate
    (0x00, 0x00, 0x00, 0xFF, 0xFF),   # only cell set
    (0xFF, 0xFF, 0xFF, 0x00, 0x00),   # only cell zero
    (0x01, 0x01, 0x01, 0x01, 0x01),
    (0x55, 0xAA, 0x55, 0xAA, 0x55),   # bit patterns
    (0x00, 0x80, 0x00, 0x80, 0x00),   # sign bit
    (0xDE, 0xAD, 0xBE, 0xEF, 0x00),
]


def build_oracle():
    """Compile the reconstructed source + its own oracle into /tmp.

    (Recipe: this harness compiles its OWN oracle — only the file under test,
    not common.build_oracle's shared SRC_FILES bundle.)"""
    samples = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = '/tmp/rx8-recon-purge_flow_counter_init'
    os.makedirs(out, exist_ok=True)
    oracle = os.path.join(out, 'oracle')
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(samples, 'include'),
           '-I', os.path.join(samples, 'src'),
           os.path.join(samples, 'tests', 'oracle_purge_flow_counter_init.c'),
           os.path.join(samples, 'src', 'rx8_purge_flow_counter_init.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(ADDR)

    vectors = list(EDGE) + [tuple(rng.randint(0, 255) for _ in range(5))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator: seed the cell + sentinels, call the
    #     actual ROM bytes @0xF534, read the five bytes back.
    emu = []
    for v in vectors:
        ram = dict(zip(ADDRS, v))
        cpu.call(ADDR, ram=ram)
        emu.append(tuple(cpu.ram.get(a, 0) for a in ADDRS))

    # (b) host-C on the same vectors (oracle mmap-seeds and reads back).
    lines = ['purge %02X %02X %02X %02X %02X' % v for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare.  Expected: front/back sentinels untouched, the three cell
    #     bytes zeroed — on BOTH sides.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d pre=(%02X,%02X,%02X,%02X,%02X) '
                'ROM=(%02X,%02X,%02X,%02X,%02X) C=(%02X,%02X,%02X,%02X,%02X)'
                % (i, v[0], v[1], v[2], v[3], v[4],
                   e[0], e[1], e[2], e[3], e[4],
                   h[0], h[1], h[2], h[3], h[4]))
            if len(mismatches) >= 5:
                break

    report('purge_flow_counter_init', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
