#!/usr/bin/env python3
"""
harness_req_queue_69602.py — equivalence of rx8_req_queue_69602
                              store @0x69602 / clear @0x69694.

Reconstructed source: samples/src/rx8_req_queue_69602.c
Verified lift   : c/req_queue_69602.c (two packed request-queue leaves over
                  the byte-flag array 0xFFFFDE38 and the parallel u32 value
                  array 0xFFFFDE40; verified in c/tests/test_req_queue_69602.py).

Both ROM leaves are plain-ABI entry points (r4 = index masked to 8 bits,
r5 = value for store; void return) so this harness uses `cpu.call()` directly.
They are NOT pure: store reads the u32 base at 0xFFFFF430, writes the u32 slot
at 0xFFFFDE40 + b*4 and sets the flag byte at 0xFFFFDE38 + b; clear writes the
flag byte only.  The harness therefore compares the FULL request-queue RAM
state (slot value + flag after store + flag after clear), and the host oracle
mirrors the side effects via MAP_FIXED pages (same trick as host_oracle.c).

Each vector exercises BOTH leaves in sequence:
    vec <b> <base> <r5> <preflag>
    1. base := long@0xFFFFF430, flag := preflag,
    2. call store(b, r5)  -> read v1 = slot value, f1 = flag (must be 1),
    3. call clear(b)      -> read f2 = flag (must be 0).

Procedure (Track-A pattern):
   1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
   2. edge vectors (indices 0/0x7F/0x80/0xFF, base/r5 at 0/max/sign flips,
      preflag 0/1/0xFF) + N random (index, base, r5, preflag) tuples,
   3. run the ROM bytes @0x69602 and @0x69694 in tools/sh2emu.py on the same
      vectors (emulated call side effects kept live across the two calls),
   4. run the host C on the same vectors,
   5. compare the queue RAM (slot + flag states) — 0 mismatches required.

Usage:  python3 harness_req_queue_69602.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2  # noqa: E402

STORE = 0x69602
CLEAR = 0x69694
N_DEFAULT = 20000

FLAGS = 0xFFFFDE38
VALUES = 0xFFFFDE40
BASE = 0xFFFFF430

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-req_queue_69602')

# Edge vectors (b, base, r5, preflag): index/flag boundaries, 0/max, sign
# flips, and values around the 0x0FA0 multiplier (both carry directions).
EDGE = []
for b in (0x00, 0x01, 0x7F, 0x80, 0xFE, 0xFF):          # index + flag boundaries
    for base in (0x00000000, 0x00000FA0, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF):
        for r5 in (0x00000000, 0x00000001, 0x00000FA0, 0x00000FA1,
                   0x7FFFFFFF, 0x80000000, 0xFFFFFFFF):
            for preflag in (0x00, 0x01, 0xFF):
                EDGE.append((b, base, r5, preflag))


def wr32(ram, addr, v):
    """Big-endian u32 store into the emulator's sparse RAM dict."""
    for i in range(4):
        ram[addr + i] = (v >> (24 - 8 * i)) & 0xFF


def rd32(ram, addr):
    """Big-endian u32 load from the emulator's sparse RAM dict."""
    return ((ram.get(addr, 0) << 24) | (ram.get(addr + 1, 0) << 16) |
            (ram.get(addr + 2, 0) << 8) | ram.get(addr + 3, 0)) & 0xFFFFFFFF


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a host binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_req_queue_69602.c'),
           os.path.join(SAMPLES, 'src', 'rx8_req_queue_69602.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2(f.read())
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = EDGE + [(rng.randrange(0, 256), rng.getrandbits(32),
                       rng.getrandbits(32), rng.getrandbits(8))
                      for _ in range(n)]

    # (a) ROM behaviour via the emulator: store then clear, RAM kept live.
    emu = []
    for b, base, r5, preflag in vectors:
        ram = {}
        wr32(ram, BASE, base)
        ram[FLAGS + b] = preflag & 0xFF
        cpu.call(STORE, r4=b, r5=r5, ram=ram)
        v1 = rd32(cpu.ram, VALUES + b * 4)
        f1 = cpu.ram.get(FLAGS + b, 0) & 0xFF
        cpu.call(CLEAR, r4=b, ram=dict(cpu.ram))     # keep slot/base state live
        f2 = cpu.ram.get(FLAGS + b, 0) & 0xFF
        emu.append('%08X %02X %02X' % (v1, f1, f2))

    # (b) host C on the same vectors.
    lines = ['vec %X %08X %08X %02X' % (b, base, r5, preflag)
             for b, base, r5, preflag in vectors]
    host = run_oracle(oracle, lines)

    # (c) compare the whole request-queue RAM state bit-exactly.
    mismatches = []
    for k, ((b, base, r5, preflag), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d b=%02X base=%08X r5=%08X preflag=%02X ROM=%s C=%s'
                % (k, b, base, r5, preflag, e, h))
            if len(mismatches) >= 5:
                break

    report('req_queue_69602', STORE, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
