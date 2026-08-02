#!/usr/bin/env python3
"""
harness_message_queue_state_dispatcher_369b8.py — equivalence of
rx8_message_queue_state_dispatcher_369b8 @0x369B8.

Reconstructed source: samples/src/rx8_message_queue_state_dispatcher_369b8.c
Verified lift   : c/message_queue_state_dispatcher_369B8.c  (same address)

The ROM function is the immobilizer CAN TX frame builder / dispatcher
("setImmoCANTXData"): it takes the message id in r4 (byte), builds the 8-byte
TX frame at 0xFFFFC238 and raises the TX request/pending flags.  It is a
LEAF (the disassembly of 0x369B8..0x36ABA contains no bsr/jsr/jmp and no
stack frame), so — unlike the state-machine/update_related rigs — NO handler
stubs are needed: the emulator executes the real bytes end to end.  Every
vector is a fresh INITIAL RAM state for every cell the frame layouts can
read (the 8 frame bytes + sentinels, the WAIT_STATE/slot selector, the
response byte, the rolling key and the four key-slot words), plus the cmd
argument:

  - emulator side: seed the cells as big-endian bytes in the sparse `ram`
    overlay, `cpu.call(0x369B8, r4=cmd, ram=ram)`, read back;
  - host side: the oracle mmap()s the 0xFFFFC000 page, seeds the same
    numeric values (u32 words via native uint32_t — the same NUMBER the
    big-endian emulator stores; byte extractions are written with shifts, cf.
    rx8_get_maf_sensor_value.c), runs the reconstructed C, reads them back.

The 21 byte cells and the 5 u32 words are all SEED cells AND compared cells,
so any extra/absent store of any width is caught (sentinels at 0xFFFFC237 /
0xFFFFC240 / 0xFFFFC28E / 0xFFFFC295 / 0xFFFFC297 / 0xFFFFC298 / 0xFFFFC29A
pin the store count/width of the frame, the TX request and the status block).
The edge set is the cross product of the message ids x slot selectors x
response bytes plus the word boundary values; the random set jams all 27
tokens.

Usage:  python3 harness_message_queue_state_dispatcher_369b8.py [N]
        (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402
from sh2emu import MASK  # noqa: E402

ADDR = 0x369B8
N_DEFAULT = 20000

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-message_queue_state_dispatcher_369b8'

# ---- Compared byte cells, in vector order (order matches the oracle's
# ---- CELL[]).  Every cell is seeded and compared: written cells change,
# ---- untouched cells (sentinels) must keep their seed value. ------------
CELLS = [
    0xFFFFC237,                              # sentinel left of the TX frame
    0xFFFFC238, 0xFFFFC239, 0xFFFFC23A,      # CAN TX frame buf[0..2]
    0xFFFFC23B, 0xFFFFC23C, 0xFFFFC23D,      # frame buf[3..5]
    0xFFFFC23E, 0xFFFFC23F,                  # frame buf[6..7]
    0xFFFFC240,                              # sentinel (CAN TX data flag)
    0xFFFFC241,                              # CAN TX request (= 1)
    0xFFFFC28E,                              # sentinel (immo state byte)
    0xFFFFC28F,                              # CAN TX state (= 0)
    0xFFFFC290,                              # WAIT_STATE / slot selector
    0xFFFFC294,                              # RESP_BYTE
    0xFFFFC295,                              # sentinel
    0xFFFFC296,                              # CAN TX status (= 0)
    0xFFFFC297,                              # sentinel
    0xFFFFC298,                              # sentinel
    0xFFFFC299,                              # CAN TX pending (= 1)
    0xFFFFC29A,                              # sentinel
]
# ---- Compared 32-bit words (order matches the oracle's WORD[]): the
# ---- rolling key (id 0x07) and the four key slots (id 0x09, sel 1..4). ---
WORDS = [
    0xFFFFC278,                              # rolling key
    0xFFFFC24C, 0xFFFFC250,                  # key slots 0..1
    0xFFFFC254, 0xFFFFC258,                  # key slots 2..3
]
I_SEL = CELLS.index(0xFFFFC290)              # control: slot selector
I_RESP = CELLS.index(0xFFFFC294)             # control: response byte

# ---- Edge vectors --------------------------------------------------------
CMD_EDGES  = [0x00, 0x01, 0x07, 0x09, 0x81, 0xC6, 0xC8, 0xFF]
SEL_EDGES  = [0x00, 0x01, 0x02, 0x03, 0x04, 0xFF]
RESP_EDGES = [0x00, 0xFF, 0x5A]
WORD_EDGES = [0x00000000, 0xFFFFFFFF, 0x80000000, 0x00000001, 0x12345678]


def make_vec(cmd, fill=0x5A, sel=0x00, resp=0x00, key=0x12345678,
             slots=(0x89ABCDEF, 0x12345678, 0x5555AAAA, 0xDEADBEEF)):
    """27-token vector: (cmd, 21 byte cells, 5 words)."""
    b = [fill] * 21
    b[I_SEL] = sel
    b[I_RESP] = resp
    return (cmd, tuple(b), (key,) + tuple(slots))


def edges():
    e = []
    # Cross product of cmd x sel x resp (all frame layouts + unknown ids).
    for cmd in CMD_EDGES:
        for sel in SEL_EDGES:
            for resp in RESP_EDGES:
                e.append(make_vec(cmd, sel=sel, resp=resp))
    # All-ones background for every message id (buf/sentinel cells 0xFF).
    for cmd in CMD_EDGES:
        e.append(make_vec(cmd, fill=0xFF))
    # Word boundary values through the id-0x07 layout (rolling key).
    for x in WORD_EDGES:
        e.append(make_vec(0x07, key=x))
    # Word boundary values through each key slot (id 0x09, sel 1..4).
    for sel in (1, 2, 3, 4):
        for x in WORD_EDGES:
            e.append(make_vec(0x09, sel=sel, slots=(x, x, x, x)))
    return e


EDGES = edges()


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_message_queue_state_dispatcher_
    369b8.c + the reconstructed source) into /tmp/rx8-recon-message_queue_state
    _dispatcher_369b8/oracle."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests',
                        'oracle_message_queue_state_dispatcher_369b8.c'),
           os.path.join(SAMPLES, 'src',
                        'rx8_message_queue_state_dispatcher_369b8.c'),
           '-lm', '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def run_emu(cpu, vec):
    """Drive the ROM bytes @0x369B8 with the given pre-state (cmd + 21 byte
    cells + 5 words); return the final (cells, words)."""
    cmd, b, w = vec
    ram = {}
    for a, val in zip(CELLS, b):
        ram[a & MASK] = val
    for a, val in zip(WORDS, w):
        for i in range(4):
            ram[(a + i) & MASK] = (val >> (24 - 8 * i)) & 0xFF
    cpu.call(ADDR, r4=cmd, ram=ram)
    cells = tuple(cpu.ram.get(a & MASK, 0) for a in CELLS)
    words = tuple(cpu.rd(a, 4) for a in WORDS)
    return cells, words


def fmt_vec(vec):
    cmd, b, w = vec
    return 'imsg %02X %s %s' % (cmd,
                                ' '.join('%02X' % x for x in b),
                                ' '.join('%08X' % x for x in w))


def fmt_res(cells, words):
    return (' '.join('%02X' % c for c in cells)
            + ' ' + ' '.join('%08X' % x for x in words))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)   # fixed seed (same as the siblings' rigs)

    vectors = list(EDGES)
    for _ in range(n):
        vectors.append((rng.getrandbits(8),
                        tuple(rng.getrandbits(8) for _ in CELLS),
                        tuple(rng.getrandbits(32) for _ in WORDS)))

    # (a) ROM behaviour via the emulator (real bytes, no stubs needed).
    emu = []
    for v in vectors:
        cells, words = run_emu(cpu, v)
        emu.append(fmt_res(cells, words))

    # (b) host C on the same inputs (raw hex tokens).
    host = list(run_oracle(oracle, [fmt_vec(v) for v in vectors]))

    # (c) compare the 21 byte cells + 5 words bit-exactly.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append('vec#%d init=%s ROM=%s C=%s'
                              % (i, fmt_vec(v).replace('imsg ', ''), e, h))
            if len(mismatches) >= 5:
                break

    report('MsgQueueDispatcher', ADDR, n, mismatches, edges=len(EDGES))


if __name__ == '__main__':
    main()
