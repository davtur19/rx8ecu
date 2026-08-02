#!/usr/bin/env python3
"""
harness_can_setup.py — equivalence of rx8_can_setup @0xDC8C.

Reconstructed source: samples/src/rx8_can_setup.c
Verified lift   : c/canSetup.c  (canSetup @ 0xDC8C, 160 bytes)

The ROM routine initialises the CAN controller with retry logic: it resets a
retry counter byte @0xFFFFA40E, selects a channel-0 base from config byte
@0xB5A4 (== 1 -> 0x4EA60, else 0x4EB60), then performs two paired
(CANControllerSetup @0x9878, canMessageSetup @0x2B320) rounds — channel 0 in
mode 0x10 and channel 1 in mode 6 with the fixed base 0x4EC60 — ORing the two
canMessageSetup returns.  On any error it increments the retry counter and
tries again (max 2 attempts); after the loop it sets byte @0xFFFFA410 = 1 iff
the counter reached 2 and always clears byte @0xFFFFA411.

The three caller cells are the only locations the function itself writes:
    0xFFFFA40E  retry counter
    0xFFFFA410  persistent error flag
    0xFFFFA411  secondary error flag

Why the callees are stubbed (see the C header, discrepancy 5): canMessageSetup
verifies the mailbox contents against the controller configuration that
CANControllerSetup derives from those SAME mailboxes, and the two derivations
never agree, so the ROM's canMessageSetup always reports failure and the caller
cells are invariant — (2, 1, 0) — for every state the harness can seed.  The
oracle's stubs (no-op CANControllerSetup, always-fail canMessageSetup) produce
the exact same invariant, so the harness validates the caller's retry / flag
logic bit-exactly over a broad input sweep.

Each vector is:
    setup <cfg> <a40e> <a410> <a411>
  cfg  : config byte @0xB5A4 (emulator RAM seed; oracle `config` parameter)
  a40e : pre-call retry counter byte  (proves the ROM resets it to 0)
  a410 : pre-call error-flag A byte   (proves overwrite on failure)
  a411 : pre-call error-flag B byte   (proves it is always cleared)

The emulator additionally gets a per-vector "environment" (the three CAN
mailbox bases 0x4EA60/0x4EB60/0x4EC60, the on-chip MMIO page 0xFFFFE400..0x
FFFFE640 that CANControllerSetup writes, and the 0x4E958 u32s) — zero,
all-0xFF and random — to sweep the callee behaviour; the oracle's stubs are
independent of it by construction.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors + N random (cfg, cells, environment) triples,
  3. run the ROM bytes @0xDC8C in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the three caller cells bit-exactly — 0 mismatches required.

Usage:  python3 harness_can_setup.py [N]   (default N = 20000)
"""
import os
import random
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report, run_oracle  # noqa: E402
# common.py already put <repo>/tools on sys.path (its sh2emu import).
from sh2emu import SH2, MASK  # noqa: E402

ADDR = 0xDC8C
N_DEFAULT = 20000

CFG_ADDR = 0x0000B5A4
RETRY_ADDR = 0xFFFFA40E
ERR_A_ADDR = 0xFFFFA410
ERR_B_ADDR = 0xFFFFA411

CAN_BASES = (0x4EA60, 0x4EB60, 0x4EC60)
MMIO_HI_LO, MMIO_HI_HI = 0xFFFFE400, 0xFFFFE640
E958_LO, E958_HI = 0x4E958, 0x4E960

# Edge vectors: (config byte, retry-cell, errA-cell, errB-cell).
EDGE_CFG = [0x00, 0x01, 0xFF, 0x80]
EDGE_CELLS = [(0x00, 0x00, 0x00), (0xFF, 0xFF, 0xFF), (0x01, 0x01, 0x00),
              (0x02, 0x05, 0x07), (0xFE, 0xFE, 0xFE)]
EDGE_ENV = ['zero', 'ff', 'rand']
EDGE = [(c, a, b, d, e) for c in EDGE_CFG for (a, b, d) in EDGE_CELLS
        for e in EDGE_ENV]
EDGE += [  # sign-ish / boundary specials
    (0x01, 0x00, 0x00, 0x00, 'zero'),
    (0x00, 0xFF, 0xFF, 0xFF, 'ff'),
    (0x81, 0x7F, 0x7F, 0x7F, 'rand'),
    (0x01, 0x00, 0xFF, 0x00, 'zero'),
    (0xFE, 0x01, 0x00, 0x00, 'ff'),
]

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-can_setup')


def make_env(kind, rng):
    """Emulator-side 'environment': mailbox bytes, on-chip MMIO page and the
    two 0x4E958 u32s the CAN subsystem reads.  Random environments are derived
    per-call from `rng` so every vector is reproducible."""
    env = {}
    if kind == 'zero':
        val = 0
    elif kind == 'ff':
        val = 0xFF
    else:
        val = None
    for base in CAN_BASES:
        for off in range(0x100):
            env[base + off] = val if val is not None else rng.getrandbits(8)
    for a in range(MMIO_HI_LO, MMIO_HI_HI):
        env[a] = val if val is not None else rng.getrandbits(8)
    for a in range(E958_LO, E958_HI):
        env[a] = val if val is not None else rng.getrandbits(8)
    return env


def run_setup(cpu, cfg, a40e, a410, a411, env):
    """Execute the ROM @0xDC8C with the given config byte, caller-cell seeds
    and environment; return the three caller cells read back."""
    ram = dict(env)
    ram[CFG_ADDR] = cfg
    ram[RETRY_ADDR] = a40e
    ram[ERR_A_ADDR] = a410
    ram[ERR_B_ADDR] = a411
    cpu.call(ADDR, ram=ram)
    return (cpu.rd(RETRY_ADDR, 1), cpu.rd(ERR_A_ADDR, 1), cpu.rd(ERR_B_ADDR, 1))


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a host binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_can_setup.c'),
           os.path.join(SAMPLES, 'src', 'rx8_can_setup.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2(f.read())
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + [(rng.getrandbits(8), rng.getrandbits(8),
                             rng.getrandbits(8), rng.getrandbits(8), 'rand')
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator, (b) host C on the same inputs.
    emu = []
    for k, (c, a, b, d, e) in enumerate(vectors):
        env = make_env(e, make_rng(0x60E1D400 + k))
        emu.append(run_setup(cpu, c, a, b, d, env))
    lines = ['setup %02X %02X %02X %02X' % (c, a, b, d)
             for (c, a, b, d, _) in vectors]
    host = [tuple(x.split()) for x in run_oracle(oracle, lines)]

    # (c) compare all three caller cells bit-exactly.
    mismatches = []
    for k, ((c, a, b, d, e), romcells, hostcells) in enumerate(
            zip(vectors, emu, host)):
        if tuple('%02X' % w for w in romcells) != hostcells:
            mismatches.append(
                'vec#%d cfg=0x%02X seed=(%02X,%02X,%02X) env=%s ROM=(%s) C=(%s)'
                % (k, c, a, b, d, e,
                   ' '.join('%02X' % w for w in romcells), ' '.join(hostcells)))
            if len(mismatches) >= 5:
                break

    report('can_setup', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
