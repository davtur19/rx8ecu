#!/usr/bin/env python3
"""
harness_immo_state_ready_to_drive_engine_off.py — equivalence of
rx8_immo_state_ready_to_drive_engine_off @0x364D8.

Reconstructed source: samples/src/rx8_immo_state_ready_to_drive_engine_off.c
Verified lift   : c/ImmoStateReadyToDriveEngineOff.c (same address 0x364D8)

The ROM function is a `void f(void)` state handler: it branches on the immo
state byte 0xFFFFC28E.

  - state != 1: writes state = 5, decrements the countdown 0xFFFFC282 (only
    while positive as signed 16-bit) and, when it reaches 0, runs
    ImmoBadStateSet() + CAN TX message 0xC8 and reloads the countdown to 500.
  - state == 1: re-runs Immo_Keygen_related_ADC (0x36AFC) until the rolling
    code at 0xFFFFC278 changes, arms the 500-tick timer 0xFFFFC27C = 0x01F4
    and tail-jumps into ImmoStateMachine_360E8 (0x360E8).

The emulator therefore executes the REAL bytes of the keygen, adc_read,
ImmoBadStateSet, the CAN TX dispatcher and the state machine; the host sample
inlines their net effects (see the sample header).  The substate-2 seed path
of the state machine is deliberately not exercised (the harness only uses
substates 0/1/3/4/0x7F/0xFF), so the host sample does not need ImmoGetSeed.

Each "vector" is a full initial-RAM state for the 26 observed cells (see
LOCS); the harness compares every one of them after the call.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge initial-RAM-state vectors (state/countdown/lamp/CAN-buf boundaries
     for the else branch; mixer/ADC/rolling edges + substate dispatch for the
     state==1 branch) + N random vectors (25% state==1, 75% state!=1),
  3. run the ROM bytes @0x364D8 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare all 26 cells bit-exactly — 0 mismatches required.

Usage:  python3 harness_immo_state_ready_to_drive_engine_off.py [N]
        (default N = 20000; reduce to 5000 if slow)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x364D8
N_DEFAULT = 20000

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-immo_state_ready_to_drive_engine_off'

# The 26 observed cells, in vector order (mirror of the oracle LOCS table).
# (name, address, width-in-bytes)
LOCS = (
    ('c28e', 0xFFFFC28E, 1),   # immo state byte
    ('c282', 0xFFFFC282, 2),   # general countdown (IMMO_TIMER)
    ('c278', 0xFFFFC278, 4),   # rolling code / keygen out
    ('c27c', 0xFFFFC27C, 2),   # 500-tick timer
    ('c288', 0xFFFFC288, 2),   # mixer word
    ('c28a', 0xFFFFC28A, 2),   # mixer word 2
    ('c293', 0xFFFFC293, 1),   # mixer counter
    ('c291', 0xFFFFC291, 1),   # substate
    ('f754', 0xFFFFF754, 2),   # lamp status word
    ('c240', 0xFFFFC240, 1),   # CAN TX data flag
    ('c241', 0xFFFFC241, 1),   # CAN TX request
    ('c284', 0xFFFFC284, 2),   # bad-state timeout
    ('c28d', 0xFFFFC28D, 1),   # state/result code
    ('c238', 0xFFFFC238, 8),   # CAN TX buffer (8 bytes)
    ('c296', 0xFFFFC296, 1),   # CAN TX status
    ('c28f', 0xFFFFC28F, 1),   # CAN TX state
    ('c299', 0xFFFFC299, 1),   # TX pending flag
    ('c294', 0xFFFFC294, 1),   # response byte
    ('c29a', 0xFFFFC29A, 1),   # good-state flag
    ('c2dc', 0xFFFFC2DC, 4),   # pairing word 1 (keygen fallback)
    ('c2e0', 0xFFFFC2E0, 4),   # pairing word 2
    ('9f1c', 0xFFFF9F1C, 2),   # adc_a (keygen input)
    ('9f1e', 0xFFFF9F1E, 2),   # adc_b (keygen input)
    ('9f00', 0xFFFF9F00, 2),   # adc_c (keygen input)
    ('869c', 0xFFFF869C, 8),   # adc_read checksummed block
    ('c6ac', 0xFFFFC6AC, 1),   # adc_read checksum-fail flag
)

# Substates the state machine may hit with state==1 without entering the
# ImmoGetSeed_3664E (substate 2) path; sub 2 is left to the real ROM bytes.
SUB_ALLOWED = (0, 1, 3, 4, 0x7F, 0xFF)

# ---- vector helpers --------------------------------------------------------
# Indices of the commonly overridden cells (kept readable).
I_STATE, I_TIMER, I_ROLL, I_W288, I_W28A, I_CNT, I_SUB, I_LAMP, I_BUF, \
    I_C28D, I_PAIR1, I_PAIR2 = 0, 1, 2, 4, 5, 6, 7, 8, 13, 12, 19, 20


def mk(state=None, timer=None, rolling=None, w288=None, w28a=None, cnt=None,
       sub=None, lamp=None, buf=None, c28d=None, pair1=None, pair2=None,
       adca=None, adcb=None, adcc=None, fill=None):
    v = list(fill if fill is not None else [0] * len(LOCS))
    if state is not None:   v[I_STATE] = state
    if timer is not None:   v[I_TIMER] = timer
    if rolling is not None: v[I_ROLL] = rolling
    if w288 is not None:    v[I_W288] = w288
    if w28a is not None:    v[I_W28A] = w28a
    if cnt is not None:     v[I_CNT] = cnt
    if sub is not None:     v[I_SUB] = sub
    if lamp is not None:    v[I_LAMP] = lamp
    if buf is not None:     v[I_BUF] = buf
    if c28d is not None:    v[I_C28D] = c28d
    if pair1 is not None:   v[I_PAIR1] = pair1
    if pair2 is not None:   v[I_PAIR2] = pair2
    if adca is not None:    v[21] = adca
    if adcb is not None:    v[22] = adcb
    if adcc is not None:    v[23] = adcc
    return tuple(v)


# Edge vectors: state != 1 (else branch) countdown boundaries, lamp/CAN-buf
# patterns on the firing path, saturated states, plus state == 1 with each
# allowed substate and saturated mixer/rolling/ADC inputs.
def gen_edges():
    e = []
    for st in (0, 2, 5, 0x7F, 0x80, 0xFE):          # state != 1
        for t in (0x0000, 0x0001, 0x0002, 0x0003, 0x7FFF, 0x8000, 0xFFFF):
            e.append(mk(state=st, timer=t))
    for lamp in (0x0000, 0x0020, 0x0040, 0x0060, 0x7FFF, 0x8000, 0xFFFF):
        e.append(mk(state=5, timer=0, lamp=lamp))
        e.append(mk(state=5, timer=1, lamp=lamp))
    for buf in (0x0000000000000000, 0xFFFFFFFFFFFFFFFF, 0x1122334455667788,
                0xC8A5A5A5A5A5A5A5):
        e.append(mk(state=5, timer=0, buf=buf))
        e.append(mk(state=5, timer=1, buf=buf))
    e.append(mk(state=0xFF, timer=0xFFFF, lamp=0xFFFF,
                buf=0xFFFFFFFFFFFFFFFF, c28d=0xFF))
    e.append(mk(state=0x00, timer=0x0001, lamp=0x0060))
    for sub in SUB_ALLOWED:                          # state == 1, substates
        e.append(mk(state=1, sub=sub))
        e.append(mk(state=1, sub=sub, lamp=0xFFFF, buf=0xFFFFFFFFFFFFFFFF))
    # Saturated mixer/ADC state.  NOTE: the degenerate all-zeros ADC case
    # (w288=w28A=0xFFFF, adc=0, ret=0) is a genuine FIXED POINT of the ROM's
    # keygen (output stays 0xFFFFFFFF forever -> the ROM itself never exits the
    # caller's while loop), so it is deliberately NOT exercised here.  The
    # saturated variant below uses adc=0xFFFF so the keygen provably changes
    # state and the loop terminates.
    e.append(mk(state=1, sub=1, rolling=0xFFFFFFFF, w288=0xFFFF, w28a=0xFFFF,
                cnt=0xFF, pair1=0xFFFFFFFF, pair2=0xFFFFFFFF,
                adca=0xFFFF, adcb=0xFFFF, adcc=0xFFFF))
    e.append(mk(state=1, sub=3, rolling=0x00000000, w288=0x0000, w28a=0x0000,
                cnt=0x00))
    e.append(mk(state=1, sub=0xFF, rolling=0xDEADBEEF, w288=0x1111, w28a=0x2222,
                cnt=0x33, pair1=0x12345678, pair2=0x9ABCDEF0))
    # Keygen-fallback edge: adc_a/b/c = 0 with w288=0, w28A=0xFFFE makes the
    # keygen output 0 -> the ROM publishes PAIR1|PAIR2 instead of a fresh code.
    e.append(mk(state=1, sub=1, rolling=0xAAAAAAAA, w288=0x0000, w28a=0xFFFE,
                cnt=0x00, pair1=0x11111111, pair2=0x22222222))
    return e


def gen_random(rng, n):
    """n random vectors: 25% state==1 (allowed substate), 75% state!=1."""
    v = []
    for _ in range(n):
        r = list(rng.getrandbits(w * 8) for _, _, w in LOCS)
        if rng.random() < 0.25:
            r[I_STATE] = 1
            r[I_SUB] = rng.choice(SUB_ALLOWED)
        else:
            r[I_STATE] = rng.randrange(0, 256)
            while r[I_STATE] == 1:               # stay on the else branch
                r[I_STATE] = rng.randrange(0, 256)
        v.append(tuple(r))
    return v


# ---- emulator / oracle glue --------------------------------------------------
def seed_ram(vec):
    """Vector -> big-endian sparse-RAM overlay for the emulator."""
    ram = {}
    for (name, addr, width), val in zip(LOCS, vec):
        for i in range(width):
            ram[(addr + i) & 0xFFFFFFFF] = (val >> (8 * (width - 1 - i))) & 0xFF
    return ram


def call_rom(cpu, vec):
    """Run the ROM bytes @0x364D8 over one vector; return the 26 cells."""
    cpu.call(ADDR, ram=seed_ram(vec))
    return tuple(cpu.rd(addr, width) for _, addr, width in LOCS)


def fmt_vec(vec):
    """Vector -> oracle stdin line."""
    return 'immo ' + ' '.join('%X' % val for val in vec)


def fmt_res(vals):
    """26 ints -> oracle output line (width-aligned hex)."""
    return ' '.join('%0*X' % (w * 2, val)
                    for val, (_, _, w) in zip(vals, LOCS))


def build_oracle(cc='cc'):
    """Compile this harness' own oracle into the task-mandated build dir."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests',
                        'oracle_immo_state_ready_to_drive_engine_off.c'),
           os.path.join(SAMPLES, 'src',
                        'rx8_immo_state_ready_to_drive_engine_off.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x364D8)          # fixed seed = the ROM address

    vectors = gen_edges() + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (real bytes incl. all callees),
    # (b) host C on the same vectors (net effects inlined in the sample).
    emu = [call_rom(cpu, v) for v in vectors]
    host = [fmt_res(tuple(int(x, 16) for x in ln.split()))
            for ln in run_oracle(oracle, [fmt_vec(v) for v in vectors])]

    # (c) compare all 26 side-effected/observed cells bit-exactly.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if fmt_res(e) != h:
            mismatches.append('vec#%d init=%s ROM=%s C=%s'
                              % (i, fmt_vec(v).replace('immo ', ''), fmt_res(e), h))
            if len(mismatches) >= 5:
                break

    report('immo_state_ready_to_drive_engine_off', ADDR, n, mismatches,
           edges=len(gen_edges()))


if __name__ == '__main__':
    main()
