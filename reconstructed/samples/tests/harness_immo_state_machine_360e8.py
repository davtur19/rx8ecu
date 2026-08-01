#!/usr/bin/env python3
"""
harness_immo_state_machine_360e8.py — equivalence of
rx8_immo_state_machine_360e8 @0x360E8.

Reconstructed source: samples/src/rx8_immo_state_machine_360e8.c
Verified lift   : c/ImmoStateMachine.c (ImmoStateMachine_360E8 @ 0x360E8)

The ROM routine is the immobilizer state-machine dispatcher: a `void f(void)`
leaf that reads the state byte 0xFFFFC28E and routes to the per-state
handlers.  Its OWN side effects are the RAM cells it writes directly; the
handler bodies (0x365B8 / 0x369B8 / 0x263C8 / 0x3664E / 0x35F92) are separate
verified lifts, so — exactly like harness_crank_sensor_init.py pins the
tail-call boundary — this rig stubs their ROM bodies at the dispatch boundary
by overlaying 4-word/5-word SH-2 stubs in the emulator's sparse `ram` (the
ram overlay shadows the ROM at those addresses in sh2emu).  Each stub records
its dispatch into a marker cell; the host oracle's handler stubs record the
same markers.  Both sides are therefore compared on:

  - the 26 dispatcher-relevant byte cells + the 16-bit seed-timer word (the
    CAN TX byte, the seed timer, the immo state block and the E2[0x1E]
    working copy, plus sentinels pinning store count/width) — bit-exact;
  - the 5 handler-dispatch markers (sentinel 0x5A = handler never ran).

Call-argument pinning (the ROM's delay-slot values, mirrored by the C call
sites): rx8_immo_msg_queue is called with r4 = 0x01 (sub==1) or 0x07 (sub==2)
and rx8_immo_set_light with r4 = 1/0 — both stubs record the actual r4, and
the harness pins those values against the ground truth on the emulator side.
The remaining three handlers are `void f(void)` (no ABI argument); their
stubs record fixed constants (1 / 4 / 5) proving the dispatch happened.  The
state==3 boundary is the tail `bra 0x35F92` (r4 = state = 3, PR untouched),
pinned as a fixed marker like the others.

Usage:  python3 harness_immo_state_machine_360e8.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402
from sh2emu import MASK  # noqa: E402

ADDR = 0x360E8
N_DEFAULT = 20000

# ---- Compared on-chip RAM cells (order matches oracle_immo_state_machine_
# ---- 360e8.c CELL[] and the vector layout: 26 byte cells + 1 word cell).
# The 16-bit seed timer (0xFFFFC286) is compared NUMERICALLY (big-endian on
# the emulator side, native uint16 on the host — same number, cf. the bad-
# state-set oracle's 16-bit timeout), so it is not in the byte list.
CELLS = [
    0xFFFFC23F, 0xFFFFC240, 0xFFFFC241,     # CAN TX data byte + sentinels
    0xFFFFC285,                             # sentinel left of the seed timer
    0xFFFFC28C, 0xFFFFC28D, 0xFFFFC28E, 0xFFFFC28F,
    0xFFFFC290, 0xFFFFC291, 0xFFFFC292, 0xFFFFC293, 0xFFFFC294,
    0xFFFFC295, 0xFFFFC296, 0xFFFFC297, 0xFFFFC298, 0xFFFFC299,
    0xFFFFC29A, 0xFFFFC29B,
    0xFFFFC29E, 0xFFFFC29F, 0xFFFFC2A0,     # seed active byte + sentinels
    0xFFFFC2F1, 0xFFFFC2F2, 0xFFFFC2F3,     # E2[0x1E] working copy + sentinels
]
WORD_SEED = 0xFFFFC286                      # 16-bit seed-refresh timer
I_STATE = CELLS.index(0xFFFFC28E)          # control: state byte
I_SUB   = CELLS.index(0xFFFFC291)          # control: challenge substate
I_V     = CELLS.index(0xFFFFC2F2)          # control: E2[0x1E] working copy

# ---- Handlers whose ROM bodies are stubbed at the dispatch boundary. ----
CALLEES = {
    0x365B8: ('bad',   1),      # rx8_immo_bad_state_set  (fixed const 1)
    0x369B8: ('msg',   'r4'),   # rx8_immo_msg_queue       (records r4 = 1/7)
    0x263C8: ('light', 'r4'),   # rx8_immo_set_light       (records r4 = 1/0)
    0x3664E: ('seed',  4),      # rx8_immo_get_seed        (fixed const 4)
    0x35F92: ('wait',  5),      # rx8_immo_wait_for_key    (fixed const 5)
}
# Marker cells (sparse RAM, seeded with the sentinel; stubs overwrite them).
M_BAD, M_MSG, M_LIGHT, M_SEED, M_WAIT = (0x00100020 + 4 * i for i in range(5))
MARKER_CELL = {'bad': M_BAD, 'msg': M_MSG, 'light': M_LIGHT,
               'seed': M_SEED, 'wait': M_WAIT}
MARKERS = (M_BAD, M_MSG, M_LIGHT, M_SEED, M_WAIT)
SENT = 0x5A

# ---- Edge vectors: systematic coverage of the three control bytes. -------
STATE_EDGES = [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x7F, 0x80, 0xFF]
SUB_EDGES   = [0x00, 0x01, 0x02, 0x03, 0x04, 0x7F, 0x80, 0xFF]
V_EDGES     = [0x00, 0x01, 0x02, 0x03, 0x7F, 0x80, 0xFF]


def make_vec(state, sub, v, fill=0x00, word=0x0000):
    """26-byte cell vector with the three control bytes placed at their cells,
    plus the 16-bit seed-timer pre-state."""
    vec = [fill] * 26
    vec[I_STATE] = state
    vec[I_SUB] = sub
    vec[I_V] = v
    return vec + [word]


EDGES = []
for s in STATE_EDGES:
    for sub in SUB_EDGES:
        for v in V_EDGES:
            EDGES.append(make_vec(s, sub, v))
# All-ones background (every other cell 0xFF) for each state, plus a couple
# of sign-flip specials (word extremes included).
for s in STATE_EDGES:
    EDGES.append(make_vec(s, 0x00, 0x00, fill=0xFF, word=0xFFFF))
EDGES += [
    make_vec(0x01, 0x01, 0xFF, fill=0x5A, word=0x8000),
    make_vec(0x03, 0x02, 0x02, fill=0xA5, word=0x02EE),
    make_vec(0x05, 0xFF, 0x80, fill=0x55, word=0x0001),
]

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-immo_state_machine_360e8'


def put16(ram, addr, word):
    ram[addr & MASK] = (word >> 8) & 0xFF
    ram[(addr + 1) & MASK] = word & 0xFF


def put32(ram, addr, val):
    for i in range(4):
        ram[(addr + i) & MASK] = (val >> (8 * (3 - i))) & 0xFF


def make_stub(ram, addr, marker, const=None, record_r4=False):
    """Overlay a tiny SH-2 stub over the ROM code at `addr` in the sparse ram
    dict: loads the marker address into r0, records either r4 (record_r4) or a
    fixed constant into the marker cell, then rts.  Ops (all big-endian):
      D0kk   mov.l @(kk*4,pc),r0      ; r0 = marker address
      E1cc   mov   #0xcc,r1           ; (fixed-const stubs only)
      2010   mov.b r1,@r0             ;   / 2040  mov.b r4,@r0
      000B   rts                      ; return (PR was set by bsr/jsr/bra)
      0009   nop                      ; delay slot
    The constant pool (4 bytes) is placed at the first address >= end of the
    body reachable from the mov.l's (PC&~3)+4 base (disp k in 0..255)."""
    if record_r4:
        body = [0xD000, 0x2040, 0x000B, 0x0009]          # 4 words
    else:
        body = [0xD000, 0xE100 | (const & 0xFF), 0x2010,
                0x000B, 0x0009]                           # 5 words
    base = (addr + 4) & ~3
    end = addr + 2 * len(body)
    pool = base + 4 * ((end - base + 3) // 4)
    k = (pool - base) // 4
    assert 0 <= k <= 255, 'stub disp overflow at 0x%X' % addr
    body[0] = 0xD000 | k
    for i, w in enumerate(body):
        put16(ram, addr + 2 * i, w)
    put32(ram, pool, marker)


def run_emu(cpu, vec):
    """Drive the ROM bytes @0x360E8 with the given pre-state (26 bytes + one
    16-bit word); the five handler bodies are stubbed in the ram overlay.
    Returns (cells, word, markers)."""
    ram = {}
    for a, (name, kind) in CALLEES.items():
        marker = MARKER_CELL[name]
        if kind == 'r4':
            make_stub(ram, a, marker, record_r4=True)
        else:
            make_stub(ram, a, marker, const=kind)
    for m in MARKERS:
        ram[m & MASK] = SENT
    for a, b in zip(CELLS, vec[:26]):
        ram[a & MASK] = b
    w = vec[26]
    ram[WORD_SEED & MASK] = (w >> 8) & 0xFF
    ram[(WORD_SEED + 1) & MASK] = w & 0xFF
    cpu.call(ADDR, ram=ram)
    cells = tuple(cpu.ram.get(a & MASK, 0) for a in CELLS)
    word = (cpu.ram.get(WORD_SEED & MASK, 0) << 8) \
        | cpu.ram.get((WORD_SEED + 1) & MASK, 0)
    markers = tuple(cpu.ram.get(m & MASK, 0) for m in MARKERS)
    return cells, word, markers


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_immo_state_machine_360e8.c +
    the reconstructed source) into the task-mandated build dir."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_immo_state_machine_360e8.c'),
           os.path.join(SAMPLES, 'src', 'rx8_immo_state_machine_360e8.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x360E8)   # fixed seed == the function's own address

    vectors = list(EDGES)
    vectors += [make_vec(rng.getrandbits(8), rng.getrandbits(8),
                         rng.getrandbits(8)) for _ in range(n)]

    # (a) ROM behaviour via the emulator (handler bodies stubbed).
    emu = []
    for vec in vectors:
        cells, word, markers = run_emu(cpu, vec)
        # Sanity pin: ROM delay-slot arguments, checked on the ground truth.
        msg, light = markers[1], markers[2]
        if msg != SENT and msg not in (0x01, 0x07):
            raise RuntimeError('emulator: unexpected msg_queue r4=0x%02X' % msg)
        if light != SENT and light not in (0x00, 0x01):
            raise RuntimeError('emulator: unexpected setImmoLight r4=0x%02X'
                               % light)
        emu.append((cells, word, markers))

    # (b) host C on the same inputs (initial cell bytes + word as raw hex).
    lines = ['imsm %s %04X'
             % (' '.join('%02X' % b for b in vec[:26]), vec[26])
             for vec in vectors]
    host = []
    for out in run_oracle(oracle, lines):
        toks = out.split()
        host.append((tuple(int(x, 16) for x in toks[:26]),
                     int(toks[26], 16),
                     tuple(int(x, 16) for x in toks[27:32])))

    # (c) compare the 26 RAM cells, the seed-timer word and the 5 dispatch
    #     markers bit-exactly.
    mismatches = []
    for k, (vec, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d state=0x%02X sub=0x%02X v=0x%02X timer=0x%04X '
                'ROM=(%s | %04X | %s) C=(%s | %04X | %s)'
                % (k, vec[I_STATE], vec[I_SUB], vec[I_V], vec[26],
                   ' '.join('%02X' % c for c in e[0]), e[1],
                   ' '.join('%02X' % c for c in e[2]),
                   ' '.join('%02X' % c for c in h[0]), h[1],
                   ' '.join('%02X' % c for c in h[2])))
            if len(mismatches) >= 5:
                break

    report('ImmoStateMachine', ADDR, n, mismatches, edges=len(EDGES))


if __name__ == '__main__':
    main()
