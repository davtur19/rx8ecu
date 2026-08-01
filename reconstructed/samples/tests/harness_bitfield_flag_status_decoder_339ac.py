#!/usr/bin/env python3
"""
harness_bitfield_flag_status_decoder_339ac.py — equivalence of
rx8_bitfield_flag_status_decoder_339ac @0x339AC.

Reconstructed source: samples/src/rx8_bitfield_flag_status_decoder_339ac.c
Verified lift   : c/bitfield_flag_status_decoder_339AC.c

The ROM function is a plain ABI-clean void leaf: no arguments are passed and
nothing is returned through a register.  It loads its own input/output
addresses from the PC-relative literal pool (mov.w @(0x2F,PC),r5 -> 0xFFFFCD4E;
mov.l @(0x1C,PC),r4 -> 0xFFFFC04D), reads the flag/status byte RAM[0xFFFFCD4E]
and writes the decoded status-code byte RAM[0xFFFFC04D]:

    RAM[0xFFFFC04D] = (b & 0x40) || (b & 0x20) ? 0x08
                    : (b & 0x80)              ? 0x02 : 0x00

The observable effect is the RAM write, so the harness drives the emulator
with the standard `cpu.call()` (seeding the status byte via the ram= overlay)
and compares the side-effected code byte against the host C's mmap-backed RAM
(same MAP_FIXED trick as tests/host_oracle.c).

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (0, max, bit flips of 0x20/0x40/0x80 and their combos,
     sign-flip boundaries 0x7F/0x80) + N random 8-bit status bytes,
  3. run the ROM bytes @0x339AC in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the code byte AND assert the function wrote no other RAM byte —
     0 mismatches required.

Usage:  python3 harness_bitfield_flag_status_decoder_339ac.py [N]
                                                            (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x339AC
INP = 0xFFFFCD4E                    # flag/status input byte
OUT = 0xFFFFC04D                    # decoded status-code output byte
N_DEFAULT = 20000

# Edge vectors: 0, max, the three decoded flag bits and every pairwise/combo
# mask, plus the sign-flip boundaries (bit 7 set/clear) and neighbours.
EDGE = [
    0x00, 0x01, 0x7F, 0x80, 0xFF,
    0x20,                       # bit 5            -> 0x08
    0x40,                       # bit 6            -> 0x08
    0x60,                       # bits 5|6         -> 0x08
    0x80,                       # bit 7            -> 0x02
    0xA0,                       # bits 5|7         -> 0x08 (0x40 path wins)
    0xC0,                       # bits 6|7         -> 0x08 (0x40 path wins)
    0xE0,                       # bits 5|6|7       -> 0x08 (0x40 path wins)
    0x21, 0x41, 0x61, 0x81, 0xA1, 0xC1, 0xE1,
    0x1F, 0x3F, 0x5F, 0x7F, 0x9F, 0xBF, 0xDF, 0xFE,
]

# This harness' own build dir (kept separate from the shared host_oracle build).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-bitfield_flag_status_decoder_339ac'


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_...339ac.c + the source)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests',
                        'oracle_bitfield_flag_status_decoder_339ac.c'),
           os.path.join(SAMPLES, 'src',
                        'rx8_bitfield_flag_status_decoder_339ac.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + [rng.randrange(0, 256) for _ in range(n)]

    # (a) ROM behaviour via the emulator: seed the status byte in the RAM
    # overlay, then read back the code byte the function wrote.  Also assert
    # the leaf's ONLY RAM side effect is the OUT byte (the pre-seeded input
    # byte must not even be modified).
    emu = []
    for s in vectors:
        cpu.call(ADDR, ram={INP: s})
        if cpu.ram.get(INP) != s:
            raise RuntimeError(
                'ROM modified its input byte @0x%X for status=0x%02X'
                % (INP, s))
        extra = {k: v for k, v in cpu.ram.items() if k not in (INP, OUT)}
        if extra:
            raise RuntimeError(
                'ROM wrote unexpected RAM %s for status=0x%02X'
                % ({hex(k): hex(v) for k, v in extra.items()}, s))
        emu.append(cpu.ram[OUT])

    # (b) host C on the same inputs (status shipped as a raw byte).
    lines = ['bfs %02X' % s for s in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare the code byte.
    mismatches = []
    for k, (s, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d status=0x%02X ROM=0x%02X C=0x%02X' % (k, s, e, h))
            if len(mismatches) >= 5:
                break

    report('bitfield_flag_status_decoder_339ac', ADDR, n, mismatches,
           edges=len(EDGE))


if __name__ == '__main__':
    main()
