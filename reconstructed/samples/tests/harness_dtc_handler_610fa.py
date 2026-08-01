#!/usr/bin/env python3
"""
harness_dtc_handler_610fa.py — equivalence of rx8_dtc_handler_610fa @0x610FA.

Reconstructed source: samples/src/rx8_dtc_handler_610fa.c
Verified lift   : c/dtc_handler_610FA.c (dtc_handler_610FA @0x610FA; dispatch
                  over the DTC handler byte-code opcode table).

CALLING CONVENTION: plain ABI leaf, NO register arguments, NO meaningful
return (r0 echoes the tail-called 63312 result) — the equivalence is over RAM
side effects, exactly like the obd_dtc_row_update_* / obd_dtc_find samples.
The dispatcher calls three REAL ROM helpers (executed by the emulator from ROM
bytes): can_encode_handler_62FAC(8) @0x62FAC, obd_service_handler_64258
@0x64258, obd_service_handler_63312 @0x63312 (tail-called).  The oracle
supplies side-effect models for them (see oracle_dtc_handler_610fa.c).

SCOPE NOTE (dispatch byte @0xFFFF87D0 != 2): can_encode_handler_62FAC's
flag==2 branch runs a deeper encoder sub-chain (0x640BC/0x42B0/0x6429E) that
is NOT modelled in the oracle — so the harness never generates flag == 2.
Every other flag value converges to the same net chain effect
(long@0xFFFF87BC = 0xFFFF0000, word@0xFFFF87D0 = 0x00FF, row update),
which the model reproduces bit-exactly.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (boundary flag/pad/idx/sel, opcode 0x50/0x00 -> chain vs
     every other opcode -> inert, row-byte corners) + N random vectors
     (40% force a chain-triggering opcode),
  3. run the ROM bytes @0x610FA in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the two value-cells (long@0xFFFF87BC, word@0xFFFF87D0), the
     three side-effected row bytes (p+0x07/0x08/0x32) and a byte-checksum of
     the whole byte-accessed DTC window (guards against ANY unexpected write)
     — 0 mismatches required.

Usage:  python3 harness_dtc_handler_610fa.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x610FA
N_DEFAULT = 20000

IDX_ADDR   = 0xFFFF8928   # word: current DTC index
OPCODES    = 0xFFFF87DE   # byte: handler byte-code opcode table
FLAG_CELL  = 0xFFFF87D0   # word: can_encode/63312 dispatch cell
LONG_CELL  = 0xFFFF87BC   # long: can_encode echo cell
SEL_WORD   = 0xFFFF8D74   # word: 64258 active-row index
TABLE_BASE = 0xFFFF8930   # byte: OBD DTC table base (0x34 stride)
ROW_STRIDE = 0x34
OPCODE_WIN = 22 * 16      # 22 opcode-table entries x 16 bytes
CKSUM_END  = 0xFFFFDEC0   # end of the byte-accessed DTC window

MAX_SEL = 0x1A4           # largest row whose p+0x32 stays < CKSUM_END
MAX_IDX = 0x100           # opcode read stays inside the mapped RAM pages

# This harness' own build dir (kept separate from the shared host_oracle build).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-dtc_handler_610fa'

# Never 2 (see SCOPE NOTE).  Everything else drives can_encode's flag!=2 path.
FLAGS = [0x00, 0x01, 0x03, 0x7F, 0xFE, 0xFF]
PADS = [0x00, 0x01, 0x7F, 0x80, 0xFF]
IDXS = [0x00, 0x01, 0x02, 0x15, 0x16, 0x21, 0x22, 0x7F, 0x80, 0x100]
OPCS = [0x00, 0x50, 0x01, 0x02, 0x7F, 0x80, 0xFF]   # 0x50/0x00 chain, rest inert
SELS = [0x00, 0x01, 0x02, 0x10, 0x1A3, 0x1A4]
BV = [0x00, 0x01, 0x7F, 0x80, 0xFF]


def gen_edges():
    """Chain-triggering opcodes x row/byte corners; inert opcodes must leave
    everything untouched; flag/pad boundaries and idx table-slot edges."""
    v = []
    # (a) chain path: opcode 0x50/0x00, boundary rows + byte corners
    for op in (0x00, 0x50):
        for sel in (0, 1, MAX_SEL):
            for fl in (0x00, 0x01, 0xFE):
                for b07 in (0x00, 0x7F, 0x80, 0xFF):
                    for b08 in (0x00, 0x80, 0xFF):
                        for b32 in (0x00, 0x01, 0x7F, 0x80, 0xFF):
                            v.append((fl, 0x00, 0x00, op, sel, b07, b08, b32))
    # (b) inert path: every non-service opcode -> no RAM writes at all
    for op in (0x01, 0x02, 0x7F, 0x80, 0xFF):
        for idx in (0x00, 0x15, 0x80):
            for sel in (0, MAX_SEL):
                v.append((0x01, 0x00, idx, op, sel, 0xC3, 0x3C, 0x5A))
    # (c) flag/pad cell boundaries (flag never 2), idx table-slot edges
    for fl in FLAGS:
        for pad in PADS:
            v.append((fl, pad, 0x80, 0x00, 0, 0x01, 0x01, 0x01))
            v.append((fl, pad, 0x80, 0x50, MAX_SEL, 0xFF, 0xFF, 0xFF))
    # (d) idx sweeps every opcode-table entry slot (0..21), opcode 0x50
    for idx in range(0, 22):
        v.append((0x01, 0x00, idx, 0x50, 0, 0x00, 0x00, 0x00))
    # (e) idx just below/above the seeded-entry window (opcode read returns 0)
    for idx in (0x1A, 0x1B, 0x1C, 0x20, 0x21):
        v.append((0x01, 0x00, idx, 0x00, 0, 0x00, 0x00, 0x00))
    return v


def gen_random(rng, n):
    """n random vectors: flag in the allowed set (never 2), full pad/idx/
    sel/byte ranges; 40% force a chain-triggering opcode."""
    v = []
    for _ in range(n):
        fl = rng.choice(FLAGS)
        pad = rng.randrange(256)
        idx = rng.randrange(MAX_IDX + 1)
        sel = rng.randrange(MAX_SEL + 1)
        op = rng.randrange(256)
        if rng.random() < 0.4:
            op = rng.choice((0x00, 0x50))
        v.append((fl, pad, idx, op, sel, rng.randrange(256),
                  rng.randrange(256), rng.randrange(256)))
    return v


def paddr(sel):
    """Effective row byte address, 32-bit wrapped like the SH-2's mulu.w+add."""
    return (TABLE_BASE + (sel & 0xFFFF) * ROW_STRIDE) & 0xFFFFFFFF


def cksum(ram):
    """Byte checksum over the two byte-accessed windows (matches the oracle)."""
    s = sum(ram.get(a, 0) for a in range(OPCODES, OPCODES + OPCODE_WIN))
    s += sum(ram.get(a, 0) for a in range(TABLE_BASE, CKSUM_END))
    return s & 0xFFFFFFFF


def run_emu(cpu, fl, pad, idx, op, sel, b07, b08, b32):
    """Seed the ROM state and call the actual ROM bytes @0x610FA.  Returns the
    six compared tokens: long@0xFFFF87BC, word@0xFFFF87D0, p+0x07/0x08/0x32,
    and the byte-window checksum."""
    p = paddr(sel)
    ram = {FLAG_CELL: fl & 0xFF, FLAG_CELL + 1: pad & 0xFF,
           IDX_ADDR: (idx >> 8) & 0xFF, IDX_ADDR + 1: idx & 0xFF,
           SEL_WORD: (sel >> 8) & 0xFF, SEL_WORD + 1: sel & 0xFF,
           OPCODES + (idx & 0xFFFF) * 16: op & 0xFF,
           p + 0x07: b07 & 0xFF, p + 0x08: b08 & 0xFF, p + 0x32: b32 & 0xFF}
    cpu.call(ADDR, ram=ram)
    return (cpu.rd(LONG_CELL, 4), cpu.rd(FLAG_CELL, 2),
            cpu.rd(p + 0x07, 1), cpu.rd(p + 0x08, 1), cpu.rd(p + 0x32, 1),
            cksum(cpu.ram))


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle + reconstructed source)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_dtc_handler_610fa.c'),
           os.path.join(SAMPLES, 'src', 'rx8_dtc_handler_610fa.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x610FA)

    vectors = gen_edges() + gen_random(rng, n)
    n_edges = len(vectors) - n

    # (a) ROM behaviour via the emulator (side-effect compare).
    emu = [run_emu(cpu, *v) for v in vectors]

    # (b) host C on the same pre-states.
    lines = ['dtc %02X %02X %04X %02X %04X %02X %02X %02X' % v for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare all six tokens.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            fl, pad, idx, op, sel, b07, b08, b32 = v
            mismatches.append(
                'vec#%d fl=%02X pad=%02X idx=%04X op=%02X sel=%04X (b07,b08,b32)'
                '=(%02X,%02X,%02X) ROM=(%08X,%04X,%02X,%02X,%02X,%08X)'
                ' C=(%08X,%04X,%02X,%02X,%02X,%08X)'
                % (i, fl, pad, idx, op, sel, b07, b08, b32,
                   e[0], e[1], e[2], e[3], e[4], e[5],
                   h[0], h[1], h[2], h[3], h[4], h[5]))
            if len(mismatches) >= 5:
                break

    report('dtc_handler_610fa', ADDR, n, mismatches, edges=n_edges)


if __name__ == '__main__':
    main()
