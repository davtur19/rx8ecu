#!/usr/bin/env python3
"""
harness_get_fault_status.py — equivalence of rx8_get_fault_status @0x6743C.

Reconstructed source: samples/src/rx8_get_fault_status.c
Verified lift   : c/getFaultStatus.c (getFaultStatus @ 0x6743C)

The ROM function is a plain ABI-clean leaf (channel in r4, 0/1 result in r0):
it ANDs the per-channel ROM fault-table entry @0x7E4DC with the runtime RAM
enable mask @0xFFFFD96C (primary, low 16 bits), and only if that misses does
it call the secondary evaluator rx8_get_fault_eval_state @0x67494 (whose
9-condition sub-check chain runs verbatim inside the emulator; the host model
lives in oracle_get_fault_status.c).  The function is read-only w.r.t. RAM.

Because the eval chain reads several backup-RAM windows, every vector seeds
them identically on both sides:
  0xFFFFD494[256] DTC enable/disable flags (dtc_data_read_60EB4, branch 0x20)
  0xFFFFD638[256] secondary DTC type flags (dtc_data_read_60EB4, branch 0xC0)
  0xFFFF8D7C[256] indirect table (check_cond_C)
  0xFFFFD3F0[ 2] eval word (dtc_data_read_60EFE / check_cond_E)
  0xFFFFD96C[ 4] fault enable mask (getFaultStatus primary check)
The oracle mirrors them through mmap(MAP_FIXED) pages (same trick as
tests/host_oracle.c) plus a MAP_FIXED mirror of the 0x7E4DC ROM span so the
sample's fixed-address ROM dereference faults-free on the host.

Procedure (Track-A pattern):
  1. build host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (channel/mask boundaries, DTC-list / eval-word structures)
     + N random (channel, mask, backup-RAM seeds),
  3. run the ROM bytes @0x6743C in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the 0/1 result — 0 mismatches required.  The post-call
     emulator RAM is also checked to contain nothing beyond the seeded
     windows and the function's own stack slots (no hidden RAM writes).

Usage:  python3 harness_get_fault_status.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, load_cpu, make_rng, report  # noqa: E402

ADDR = 0x6743C
N_DEFAULT = 20000

# Backup-RAM seed windows (base, byte count) mirrored by oracle_get_fault_status.c.
W_D494 = (0xFFFFD494, 256)
W_D638 = (0xFFFFD638, 256)
W_D8D7C = (0xFFFF8D7C, 256)
W_D3F0 = (0xFFFFD3F0, 2)
W_MASK = (0xFFFFD96C, 4)
WINDOWS = (W_D494, W_D638, W_D8D7C, W_D3F0, W_MASK)

# Stack area getFaultStatus + the eval chain may legitimately touch while
# running from r15 = 0xFFFFDF00 (the emulator's default SP).
STACK_LO = 0xFFFFDD00
STACK_HI = 0xFFFFDF04

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-get_fault_status'

# Channel / mask edges: real DTC-list carriers (9, 14), table/shape boundaries,
# 16-bit extremes, and masks hitting each eval bit plus the table-entry shapes.
EDGE_CH = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 14, 15, 22, 31,
           0x40, 0x80, 0xFF, 0x100, 0x3FF, 0x7FFF, 0x8000, 0xFFFF]
EDGE_MASK = [0x00000000, 0x00000001, 0x0000FFFF, 0xFFFF0000, 0xFFFFFFFF,
             0x40000000, 0x10000000, 0x08000000, 0x00800000, 0x48800004]


def zero_seeds(mask):
    """Backup-RAM all-zero except the enable mask."""
    seeds = {}
    for base, n in WINDOWS:
        for i in range(n):
            seeds[base + i] = 0
    for i in range(4):
        seeds[W_MASK[0] + i] = (mask >> (8 * (3 - i))) & 0xFF
    return seeds


def seeds_to_blob(seeds):
    """Serialize the seed dict in the oracle's fixed window layout."""
    blob = []
    for base, n in (W_D494, W_D638, W_D8D7C):
        blob += [seeds[base + i] for i in range(n)]
    blob += [seeds[W_D3F0[0]], seeds[W_D3F0[0] + 1]]
    blob += [seeds[W_MASK[0] + i] for i in range(4)]
    return ''.join('%02X' % b for b in blob)


def edge_vectors():
    """(channel, mask, seeds) list: all-zero seeds plus structured DTC-list
    and eval-word edges that force the secondary evaluator's branches."""
    v = []
    for ch in EDGE_CH:
        for m in EDGE_MASK:
            v.append((ch, m, zero_seeds(m)))
    # check_cond_B: real DTC lists for ch 9 (0x0A,0x0B) and 14 (0x11,0x12,
    # 0x0F,0x10); 0xFFFFD638+entry == 0xC0 validates dtc_data_read_60EB4.
    for ch, off in [(9, 0x0A), (9, 0x0B), (14, 0x11), (14, 0x12),
                    (14, 0x0F), (14, 0x10)]:
        for m in (0x00000000, 0x40000000, 0xFFFFFFFF):
            s = zero_seeds(m)
            s[W_D638[0] + off] = 0xC0
            v.append((ch, m, s))
    # check_cond_E: every interesting 0xFFFFD3F0 word on channels whose
    # byte table is 0x03 0xF8 (0,9) or 0xFF 0xFC (2).
    for w in (0x0000, 0x00FF, 0xFF00, 0xFFFF, 0x03F8, 0xFFFC):
        for ch in (0, 2, 9):
            s = zero_seeds(0)
            s[W_D3F0[0]] = (w >> 8) & 0xFF
            s[W_D3F0[0] + 1] = w & 0xFF
            v.append((ch, 0, s))
    return v


def random_seeds(rng, mask):
    """Random backup-RAM windows for one random vector."""
    seeds = {}
    for base, n in (W_D494, W_D638, W_D8D7C):
        for i in range(n):
            seeds[base + i] = rng.randrange(256)
    w = rng.getrandbits(16)
    seeds[W_D3F0[0]] = (w >> 8) & 0xFF
    seeds[W_D3F0[0] + 1] = w & 0xFF
    for i in range(4):
        seeds[W_MASK[0] + i] = (mask >> (8 * (3 - i))) & 0xFF
    return seeds


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a host binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_get_fault_status.c'),
           os.path.join(SAMPLES, 'src', 'rx8_get_fault_status.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def run_oracle_rom(oracle, vectors):
    """run_oracle() variant that also passes the ROM path (argv[1]) so the
    oracle can load the real 60E1D400.bin for its fault-table mirror."""
    proc = subprocess.run([oracle, ROM_PATH],
                          input='\n'.join(vectors) + '\n',
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError('host oracle failed:\n' + proc.stderr)
    lines = proc.stdout.splitlines()
    if len(lines) != len(vectors):
        raise RuntimeError(
            'oracle produced %d outputs for %d vectors' % (len(lines), len(vectors)))
    return lines


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x6743C)

    edges = edge_vectors()
    vectors = list(edges)
    for _ in range(n):
        ch = rng.randrange(0x10000)
        mask = rng.getrandbits(32)
        vectors.append((ch, mask, random_seeds(rng, mask)))

    # (a) ROM behaviour via the emulator (r4 = channel, seeded backup RAM).
    emu = []
    for ch, mask, seeds in vectors:
        emu.append(cpu.call(ADDR, r4=ch, ram=dict(seeds)) & 0xFF)
        # No hidden RAM writes: post-call ram must be seeds + stack slots only.
        for a in cpu.ram:
            if a in seeds:
                continue
            if STACK_LO <= a < STACK_HI:
                continue
            raise RuntimeError(
                'vec ch=0x%04X: emulator wrote RAM @0x%08X (unmodelled side '
                'effect)' % (ch, a))

    # (b) host C on the same inputs.
    lines = ['gs %04X %s' % (ch, seeds_to_blob(seeds)) for ch, m, seeds in vectors]
    host = [int(x, 16) for x in run_oracle_rom(oracle, lines)]

    # (c) compare the 0/1 results.
    mismatches = []
    for k, ((ch, m, seeds), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append('vec#%d ch=0x%04X mask=0x%08X ROM=%d C=%d'
                              % (k, ch, m, e, h))
            if len(mismatches) >= 5:
                break

    report('get_fault_status', ADDR, n, mismatches, edges=len(edges))


if __name__ == '__main__':
    main()
