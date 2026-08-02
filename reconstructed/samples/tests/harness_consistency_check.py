#!/usr/bin/env python3
"""
harness_consistency_check.py — equivalence of rx8_consistency_check @0x3A28.

Reconstructed source: samples/src/rx8_consistency_check.c
Verified lift   : c/consistencyCheck.c  (consistencyCheck @ 0x3A28,
                  ghidra-hand-xmap; docs/functions/consistencyCheck.md).

LIFT-LABEL CHECK (hypothesis -> verified): the "consistencyCheck" label was
NOT trusted blind — the ROM bytes at 0x3A28 were disassembled first and the
task-health-check model (per-task counter vs expected, bitmap clear, shadow
restore/bump, diag lookup, HUDI callee) matched instruction-for-instruction
(see the source header).  No label mismatch this time (contrast
baro_sensor_value, where the IDA-AI label was wrong for this ROM).

The ROM routine is the scheduler's per-task "I'm alive" watchdog, called from
taskEndRoutine (0x3D58) and FUN_00003490 (0x3490) with r4 = 0xFFFF72B0:

  r4 = ctx  (kernel context block @0xFFFF72B0: +0 current-task u8, +6 diag
             u16, +0x10 SR shadow, +0x20 entry-table ptr, +0x24 diag-table
             ptr),  r5 = task id (sign-extended byte).
  returns 1 if the task id == ctx current-task byte, else 0.

The observable state (compared bit-exactly, numeric values so the LE host
and BE emulator agree):
  ret    ABI return value
  cnt    *counter  (u16 @0xFFFF7800 — the buffer every entry points at)
  exp    *(counter+2)  (u16; must be untouched by the call)
  ctx0   ctx+0 (u8; written by the HUDI callee on the healthy+match path)
  ctx6   ctx+6 (u16 diagnostic field)
  bmp0   pending-flags byte @0xFFFF72E0 (bitmap; index task_id>>3)
  bmp1   @0xFFFF72E1  (bitmap boundary for task ids 8..15)
  snt    @0xFFFF72E2  (sentinel; must be untouched)

The healthy+match path jsr's the REAL ROM bytes of handleHUDIException
(0x3C80) on the emulator side.  That callee is bounded (no loops) but indexes
a diag table with the counter value the parent has just reset to 0xFFFF —
unbounded for arbitrary vectors.  This harness therefore drives the callee
only in its "no exception pending" state (the 16-byte block @0xFFFF72E0 all
zero -> ctx[0]=0xFF, ctx[6]=0xFFFF), the normal-case invocation, and keeps
every mismatch-path diag index within the 16-entry table by bounding cur/save
<= 0x0F.  The full callee scan model in the oracle was additionally validated
over 50000 isolated random vectors before this rig was written.

Vector layout (27 hex ints): task, ctx0, sr, cur, exp, save, shadow,
w0 w1 w2 w3 (the 16-byte exception block), d0..d15 (16 x u16 diag table).

Usage:  python3 harness_consistency_check.py [N]   (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x3A28
N_DEFAULT = 20000
SEED = 0x60E1D400
BUILD_DIR = '/tmp/rx8-recon-consistency_check'

# ---- fixed addresses (see rx8_consistency_check.c) ----
CTX = 0xFFFF72B0
DIAG = 0xFFFF7234
REG = 0xFFFF72E0
ENTRY_TABLE = 0xFFFF7300
CSCRATCH = 0xFFFF7800


def put16(ram, a, v):
    ram[a & 0xFFFFFFFF] = (v >> 8) & 0xFF
    ram[(a + 1) & 0xFFFFFFFF] = v & 0xFF


def put32(ram, a, v):
    for i in range(4):
        ram[(a + i) & 0xFFFFFFFF] = (v >> (8 * (3 - i))) & 0xFF


def run_emu(cpu, v):
    """Seed every cell, run the ROM bytes @0x3A28 (HUDI callee included as
    real ROM bytes) and return the 8-tuple of post-state cells + return."""
    task, ctx0, sr, cur, exp, save, shadow = v[:7]
    w = v[7:11]
    diag = v[11:27]

    ram = {}
    put32(ram, CTX + 0x20, ENTRY_TABLE)
    put32(ram, CTX + 0x24, DIAG)
    put32(ram, CTX + 0x10, sr)
    ram[CTX] = ctx0 & 0xFF
    put16(ram, CTX + 6, 0x1234)                 # diag pre-state
    for e in range(0x80):                        # every entry -> one buffer
        put32(ram, ENTRY_TABLE + e * 8 + 4, CSCRATCH)
    put16(ram, ENTRY_TABLE + task * 8, save)
    put16(ram, ENTRY_TABLE + task * 8 + 2, shadow)
    put16(ram, CSCRATCH, cur)
    put16(ram, CSCRATCH + 2, exp)
    for i in range(4):
        put32(ram, REG + i * 4, w[i])
    for i in range(16):
        put16(ram, DIAG + i * 2, diag[i])

    r0 = cpu.call(ADDR, r4=CTX, r5=task, ram=ram)
    return (r0, cpu.rd(CSCRATCH, 2), cpu.rd(CSCRATCH + 2, 2),
            cpu.rd(CTX, 1), cpu.rd(CTX + 6, 2),
            cpu.rd(REG, 1), cpu.rd(REG + 1, 1), cpu.rd(REG + 2, 1))


def build_oracle():
    """Compile the reconstructed source + its dedicated oracle into /tmp."""
    samples = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(samples, 'include'),
           '-I', os.path.join(samples, 'src'),
           os.path.join(samples, 'tests', 'oracle_consistency_check.c'),
           os.path.join(samples, 'src', 'rx8_consistency_check.c'),
           '-lm', '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def diag_ramp():
    return tuple((i * 0x123 + 5) & 0xFFFF for i in range(16))


def diag_rand(rng):
    return tuple(rng.getrandbits(16) for _ in range(16))


def gen_edges():
    """Valid (bounded) edge vectors targeting every parent branch.  Any
    healthy+match vector MUST have w0..w3 == 0 (see header); all mismatch
    diag indices are bounded by cur/save <= 0x0F."""
    v = []
    D = diag_ramp()

    # (a) mismatch + current-task match: restore (cur==shadow) and inc paths
    v.append((2, 2, 0xF0, 5, 0xFFFF, 7, 5, 0xDEADBEEF, 0x12345678,
              0x00FF00FF, 0x0F0F0F0F) + D)
    v.append((2, 2, 0xF0, 5, 0x1234, 3, 9, 0xAAAAAAAA, 0x55555555,
              0xFFFFFFFF, 0x00000000) + D)
    v.append((0, 0, 0xF0, 14, 0, 2, 0xFF, 0x01010101, 0x02020202,
              0x03030303, 0x04040404) + D)          # inc -> diag[15]
    v.append((0, 0, 0xF0, 0, 0xFFFF, 0x0F, 0, 0, 0, 0, 0) + D)
    v.append((0, 0, 0xF0, 0x0E, 0xFFFF, 0x07, 0x0E, 0, 0, 0, 0) + D)

    # (b) mismatch + no current-task match: return 0, ctx untouched
    v.append((2, 3, 0xF0, 5, 0xFFFF, 7, 5, 0x80000000, 0x40000000,
              0x20000000, 0x10000000) + D)
    v.append((9, 0xFF, 0xF0, 7, 3, 4, 11, 0xFFFFFFFF, 0xFFFFFFFF,
              0xFFFFFFFF, 0xFFFFFFFF) + D)
    v.append((15, 0, 0xF0, 0, 0xFFFF, 0, 0, 0x80402010, 0x08040201,
              0x80808080, 0x01010101) + D)

    # (c) healthy + no match: counter reset, bitmap clear, return 0
    v.append((3, 1, 0xF0, 0, 0, 0, 0, 0, 0, 0, 0) + D)
    v.append((3, 1, 0xF0, 0xFFFF, 0xFFFF, 0, 0, 0xFFFFFFFF, 0xFFFFFFFF,
              0xFFFFFFFF, 0xFFFFFFFF) + D)
    v.append((3, 1, 0xF0, 0x8000, 0x8000, 0, 0, 0x7FFFFFFF, 0x80000000,
              0x00000001, 0xFFFFFFFF) + D)
    v.append((0, 0xFE, 0xF0, 0x1234, 0x1234, 0, 0, 0xFF000000, 0x00FF0000,
              0x0000FF00, 0x000000FF) + D)          # bitmap bit 0 of REG[0]
    v.append((7, 0xFE, 0xF0, 1, 1, 0, 0, 0x000000FF, 0x00000000,
              0x00000000, 0x00000000) + D)          # bitmap bit 7 of REG[0]
    v.append((8, 0xFE, 0xF0, 2, 2, 0, 0, 0x00000000, 0xFF000000,
              0x00000000, 0x00000000) + D)          # bitmap bit 0 of REG[1]
    v.append((15, 0xFE, 0xF0, 3, 3, 0, 0, 0x00000000, 0x000000FF,
              0x00000000, 0x00000000) + D)          # bitmap bit 7 of REG[1]
    v.append((15, 0xFD, 0xF0, 0xFFFF, 0xFFFF, 0, 0, 0xCAFEBABE, 0xDEADBEEF,
              0x01234567, 0x89ABCDEF) + D)

    # (d) healthy + current-task match: HUDI callee fires.  MUST be REG=0.
    v.append((2, 2, 0xF0, 5, 5, 0, 0, 0, 0, 0, 0) + D)
    v.append((2, 2, 0xF0, 0xFFFF, 0xFFFF, 0, 0, 0, 0, 0, 0) + D)
    v.append((0, 0, 0xF0, 0, 0, 0, 0, 0, 0, 0, 0) + D)
    v.append((8, 8, 0xF0, 0x8000, 0x8000, 0, 0, 0, 0, 0, 0) + D)
    v.append((15, 15, 0xF0, 0x1234, 0x1234, 0, 0, 0, 0, 0, 0) + D)
    v.append((7, 7, 0xF0, 0xFFFF, 0xFFFF, 0, 0, 0, 0, 0, 0) + D)

    return v


def gen_random(rng, k):
    """k random pre-states, structured so every generated vector is valid
    (bounded) while still covering all four parent branches."""
    v = []
    for _ in range(k):
        task = rng.randint(0, 15)
        sr = rng.getrandbits(32)
        roll = rng.random()
        if roll < 0.45:
            # ---- mismatch branch ----
            cur = rng.randint(0, 0x0E)
            exp = rng.getrandbits(16)
            while exp == cur:
                exp = rng.getrandbits(16)
            if rng.random() < 0.5:
                shadow = cur                    # restore path
            else:
                shadow = rng.choice([x for x in range(16) if x != cur] or [1])
            save = rng.randint(0, 0x0F)
            ctx0 = rng.choice([task, (task + 1) & 0xFF, rng.randint(0, 15),
                               0xFF])
            w = tuple(rng.getrandbits(32) for _ in range(4))
        elif roll < 0.80:
            # ---- healthy, no current-task match (no callee) ----
            cur = rng.choice([rng.getrandbits(16), 0xFFFF, 0, 0x8000,
                              0x7FFF, 0x0001])
            exp = cur
            save = rng.randint(0, 0x0F)
            shadow = rng.randint(0, 0x0F)
            ctx0 = (task + 1) & 0xFF
            if ctx0 == task:
                ctx0 = (task + 2) & 0xFF
            w = tuple(rng.getrandbits(32) for _ in range(4))
        else:
            # ---- healthy + current-task match: HUDI callee, REG must be 0
            cur = rng.choice([rng.getrandbits(16), 0xFFFF, 0, 0x8000])
            exp = cur
            save = rng.randint(0, 0x0F)
            shadow = rng.randint(0, 0x0F)
            ctx0 = task
            w = (0, 0, 0, 0)
        diag = diag_rand(rng)
        v.append((task, ctx0, sr, cur, exp, save, shadow) + w + diag)
    return v


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)

    edges = gen_edges()
    vectors = list(edges) + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (callee runs as real ROM bytes).
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host-C on the same pre-states.
    lines = ['cc %02X %02X %08X %04X %04X %04X %04X %08X %08X %08X %08X %s'
             % (v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8], v[9],
                v[10], ' '.join('%04X' % d for d in v[11:27]))
             for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the 8-field post-state tuples bit-exactly.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d task=%02X ctx0=%02X cur=%04X exp=%04X save=%04X '
                'shadow=%04X w0=%08X ROM=(%08X,%04X,%04X,%02X,%04X,%02X,'
                '%02X,%02X) C=(%08X,%04X,%04X,%02X,%04X,%02X,%02X,%02X)'
                % (i, v[0], v[1], v[3], v[4], v[5], v[6], v[7],
                   e[0], e[1], e[2], e[3], e[4], e[5], e[6], e[7],
                   h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7]))
            if len(mismatches) >= 5:
                break

    report('consistency_check', ADDR, n, mismatches, edges=len(edges))


if __name__ == '__main__':
    main()
