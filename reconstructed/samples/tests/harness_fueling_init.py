#!/usr/bin/env python3
"""
harness_fueling_init.py — equivalence of rx8_fueling_init @0x753C.

Reconstructed source: samples/src/rx8_fueling_init.c
Verified lift   : c/fuelingInit.c (fuelingInit @ 0x753C, 80 bytes)

The function is a `void f(void)` initialiser with NO ABI return value: its whole
effect is on the MTU timer registers and the crank control/state RAM bank, so
the equivalence check compares RAM/hardware side-effects, not a return value
(Track-A RAM pattern, cf. harness_immo_state_ready_to_drive_engine_off.py):

  - emulator side: seed the 49 observed cells in the sparse `ram` overlay,
    drive the ROM entry @0x753C with cpu.call() — the REAL ROM bytes of the
    whole chain run, including the eight internal callees (crank_timer_hw_reset
    @0x076DC, crank_vars_init @0x07748 + its 0x07B7C leaf, crank_mode_write
    @0x07C00, crank_state_bytes_clear @0x07BA8, crankSensorInit @0x07C30,
    crank_flags_enable @0x07ED8, crank_counters_reset @0x07FB4) and the
    TAIL-CALL target crank_output_update @0x0808E (which ends in `rts` and
    returns through PR = the 0xEEEE0000 sentinel, terminating the call) — then
    read the 49 cells back;
  - host side: the oracle mmap()s the pages backing the cells AND the
    mmap-able ROM calibration page (0x0006C000), seeds the same bytes, runs the
    reconstructed C (whose inlined callee net effects are the sample) and
    prints the same 49 cells.

Each "vector" is a full initial state for the 49 observed cells (see LOCS);
the harness compares every one of them after the call.

HARNESS CONSTRAINT (why the emulator cannot run away)
-----------------------------------------------------
crankSensorInit @0x07C30 tail-jumps into crank_mode_switch @0x0768C whenever
the engine-running flag 0xFFFF9F96 == 1, and crank_mode_switch ends in a
computed `jmp @u32@0x0000DB60` (mode-function pointer kept in RAM) that would
execute arbitrary seeded bytes.  That path is reachable from crank_vars_init
when 0xFFFF9FC0 == 1 AND 0xFFFF9FA3 != 2 (its internal bsr to 0x07C30 runs
before fuelingInit clears 0xFFFF9F96).  The vector generator therefore never
seeds (0xFFFF9FC0 == 1 AND 0xFFFF9FA3 != 2 AND 0xFFFF9F96 == 1) — either the
sensor init is skipped (0xFFFF9FA3 == 2) or the run flag is != 1.  The direct
fuelingInit call to crankSensorInit is always safe: 0xFFFF9F96 is written to 0
at 0x7576 right before the bsr at 0x757A.

ROM constants: the four calibration/constant cells are pinned by check_cal
(0x0006CF64 u32 = 0x000FA000, 0x0006CF68 u8 = 0x00, u8@0x0000DA4D = 0x00,
f32@0x000080FC = 10.0f) so the host-C values can never drift from the ROM.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge initial-state vectors (branch-cell boundaries, MTU RMW boundaries,
     saturated pre-states) + N random vectors (35% on the 0xFFFF9FC0==1
     vars-init branch, rest on the common path),
  3. run the ROM bytes @0x753C in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare all 49 cells bit-exactly — 0 mismatches required.

Usage:  python3 harness_fueling_init.py [N]  (default N = 20000; 5000 if slow)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x753C
N_DEFAULT = 20000

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-fueling_init'

# ---- the 49 observed cells, in vector order (mirror of the oracle LOCS) -----
# (name, address, width-in-bytes)
LOCS = (
    ('f42a', 0xFFFFF42A, 1),   # MTU timer control (RMW)
    ('f42c', 0xFFFFF42C, 1),   # sentinel (never written)
    ('f42e', 0xFFFFF42E, 2),   # MTU timer word (RMW)
    ('f6c4', 0xFFFFF6C4, 1),   # leaf clear cell
    ('f6d4', 0xFFFFF6D4, 4),   # period register (u32 cal)
    ('f6d8', 0xFFFFF6D8, 1),   # leaf result cell
    ('f6e0', 0xFFFFF6E0, 1),   # timer value = 0xC8
    ('f6e2', 0xFFFFF6E2, 1),   # sentinel (never written)
    ('f6e4', 0xFFFFF6E4, 1),   # timer control 2 (RMW)
    ('f6ea', 0xFFFFF6EA, 2),   # fuel timing control (RMW x4)
    ('f6ec', 0xFFFFF6EC, 1),   # sentinel (never written)
    ('9f80', 0xFFFF9F80, 4),   # f32 = 0.0 (counters reset)
    ('9f84', 0xFFFF9F84, 4),   # u32 = 0x7FFFFFFF
    ('9f88', 0xFFFF9F88, 4),   # u32 = 0x7FFFFFFF
    ('9f8c', 0xFFFF9F8C, 1),   # flag = 1 (flags enable)
    ('9f90', 0xFFFF9F90, 4),   # f32 = 0.0 (counters reset)
    ('9f94', 0xFFFF9F94, 1),   # = 0 (counters reset)
    ('9f95', 0xFFFF9F95, 1),   # leaf table index (vars init = 0x24)
    ('9f96', 0xFFFF9F96, 1),   # engine-running flag (sensor branch)
    ('9f97', 0xFFFF9F97, 1),   # sentinel (never written)
    ('9fa0', 0xFFFF9FA0, 1),   # flag = 1 (flags enable)
    ('9fa1', 0xFFFF9FA1, 1),   # clear (leaf bsr delay)
    ('9fa2', 0xFFFF9FA2, 1),   # clear (vars-init bsr delay)
    ('9fa3', 0xFFFF9FA3, 1),   # flag A = 1 / vars-init sensor skip flag
    ('9fa4', 0xFFFF9FA4, 1),   # flag B = 0
    ('9fa5', 0xFFFF9FA5, 1),   # flag C = 0
    ('9fb0', 0xFFFF9FB0, 4),   # u32 = 0xFFFFFFFF (mov #0xFF sign-extended)
    ('9fb4', 0xFFFF9FB4, 4),   # sentinel (never written)
    ('9fbc', 0xFFFF9FBC, 4),   # f32 = 0.0 (vars init)
    ('9fc0', 0xFFFF9FC0, 1),   # flag D = 0 / vars-init branch cell
    ('9fc1', 0xFFFF9FC1, 1),   # clear (vars init)
    ('9fc2', 0xFFFF9FC2, 1),   # clear (vars init)
    ('9fc3', 0xFFFF9FC3, 1),   # leaf result copy
    ('9fc4', 0xFFFF9FC4, 1),   # flag E = 0
    ('9fc5', 0xFFFF9FC5, 1),   # clear (vars init)
    ('9fc6', 0xFFFF9FC6, 1),   # sensor control reg C = 0xFF (mode write)
    ('9fc7', 0xFFFF9FC7, 1),   # state byte clear
    ('9fc8', 0xFFFF9FC8, 1),   # state byte clear
    ('9fc9', 0xFFFF9FC9, 1),   # sensor control reg A = 0x00
    ('9fca', 0xFFFF9FCA, 1),   # sensor control reg B = 0xFF
    ('9fcb', 0xFFFF9FCB, 1),   # clear (sensor bsr delay)
    ('9fcc', 0xFFFF9FCC, 2),   # u16 = 0xFFFF (flags enable)
    ('9fce', 0xFFFF9FCE, 1),   # flag = 1 (flags enable)
    ('9fe8', 0xFFFF9FE8, 1),   # = 0 (counters reset)
    ('9ff0', 0xFFFF9FF0, 4),   # f32 = 10.0 (output update)
    ('9ff4', 0xFFFF9FF4, 4),   # f32 = 10.0 (output update)
    ('9ff8', 0xFFFF9FF8, 4),   # f32 = 0.0  (output update)
    ('9ffc', 0xFFFF9FFC, 4),   # f32 = 0.0  (output update)
    ('9fec', 0xFFFF9FEC, 4),   # f32 = 1.0  (output update)
)
IND = {name: i for i, (name, _, _) in enumerate(LOCS)}

# indices of the commonly overridden control-flow cells
I_FC0, I_FA3, I_F96 = IND['9fc0'], IND['9fa3'], IND['9f96']

# ---- ROM calibration / constant pins (see the sample header) ----------------
ROM_CAL_PERIOD  = 0x0006CF64   # u32 = 0x000FA000  (crank_timer_hw_reset)
ROM_CAL_LEAF    = 0x0006CF68   # u8  = 0x00         (crank_vars_leaf switch)
ROM_CAL_ENTRY   = 0x0000DA4D   # u8  = 0x00         (leaf table entry idx 0x48)
ROM_OUT_F32     = 0x000080FC   # f32 = 10.0f        (crank_output_update)


def check_cal(cpu):
    """Pin the four ROM constant cells; refuse to run if any ever change so the
    host-C values stay meaningful (the two low pages cannot be mmap'd)."""
    rom = cpu.rom
    if struct.unpack_from('>I', rom, ROM_CAL_PERIOD)[0] != 0x000FA000 \
            or rom[ROM_CAL_LEAF] != 0x00 \
            or rom[ROM_CAL_ENTRY] != 0x00 \
            or struct.unpack_from('>f', rom, ROM_OUT_F32)[0] != 10.0:
        raise RuntimeError('unexpected fuel-init ROM constants @0x%X/0x%X/0x%X/0x%X'
                           % (ROM_CAL_PERIOD, ROM_CAL_LEAF, ROM_CAL_ENTRY,
                              ROM_OUT_F32))


# ---- vector helpers ---------------------------------------------------------
# Short aliases for the control-flow cells (full names are the LOCS keys).
ALIAS = {'fc0': '9fc0', 'fa3': '9fa3', 'f96': '9f96'}


def mk(fill=None, **kw):
    v = list(fill if fill is not None else [0] * len(LOCS))
    for name, val in kw.items():
        key = ALIAS.get(name, name)
        if key not in IND:
            raise KeyError('unknown cell: %s' % name)
        v[IND[key]] = val
    return tuple(v)


def gen_edges():
    """Edge initial states: every branch of the crank_vars_init dispatch, the
    MTU RMW boundary pre-states, saturated patterns, and the sensor-init
    boundary (run flag != 1 whenever the internal sensor call can run)."""
    e = []
    # (a) degenerate full patterns on the common path.
    e.append(mk())                                   # all zeros
    e.append(mk(fill=[0xFF] * len(LOCS)))            # all ones
    e.append(mk(fill=[0x55 if i % 2 else 0xAA for i in range(len(LOCS))]))
    # (b) crank_vars_init branch: 0xFFFF9FC0 == 1.
    #     FA3 == 2 -> sensor skipped, tail state-clear (safe for any 9F96).
    e.append(mk(fc0=1, fa3=2))
    e.append(mk(fc0=1, fa3=2, f96=1))
    e.append(mk(fc0=1, fa3=2, f96=0xFF, f6ea=0xFFFF, f6e4=0xFF))
    #     FA3 != 2 -> internal crankSensorInit runs; keep 9F96 != 1.
    for fa3, f96 in ((0, 0), (0, 2), (1, 0), (3, 0x7F), (0x40, 0xFE),
                     (0x80, 0xFF), (0xFE, 0x00), (0xFF, 0x00)):
        e.append(mk(fc0=1, fa3=fa3, f96=f96))
    #     saturated everything around the branch.
    e.append(mk(fc0=1, fa3=0, f96=0, f6ea=0xFFFF, f6e4=0xFF,
                f42a=0xFF, f42e=0xFFFF, f6d4=0xFFFFFFFF,
                f6d8=0xFF, f6c4=0xFF, f6e0=0xFF, f6ec=0xFF, f6e2=0xFF))
    e.append(mk(fc0=1, fa3=0x40, f96=0, f6ea=0x0000, f6e4=0x00,
                f42a=0x00, f42e=0x0000))
    # (c) common path: 0xFFFF9FC0 != 1.
    for fc0 in (0, 2, 0x7F, 0x80, 0xFE, 0xFF):
        e.append(mk(fc0=fc0))
        e.append(mk(fc0=fc0, fa3=2, f96=1))          # sensor still skipped later
    # (d) MTU RMW boundary pre-states (fuel timing control 0xFFFFF6EA).
    for f6ea in (0x0000, 0x0001, 0x0003, 0x0004, 0x0008, 0x000C, 0x8000,
                 0xFFFF, 0xFFF7, 0xFFFB, 0xFFFD, 0xFFFE, 0x5555, 0xAAAA):
        e.append(mk(f6ea=f6ea))
        e.append(mk(fc0=1, fa3=2, f6ea=f6ea))
    # (e) timer-control 2 (0xFFFFF6E4) single-bit / mask boundaries.
    for f6e4 in (0x00, 0x01, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x84,
                 0x7F, 0xFB, 0xF7, 0xEF, 0xBF, 0xDF, 0xFF):
        e.append(mk(f6e4=f6e4))
    # (f) 0xFFFFF42A byte and 0xFFFFF42E word boundaries.
    for f42a in (0x00, 0x01, 0x03, 0xFC, 0xFD, 0xFE, 0xFF):
        e.append(mk(f42a=f42a))
    for f42e in (0x0000, 0x0001, 0x0002, 0x7FFE, 0x8000, 0xFFFE, 0xFFFF):
        e.append(mk(f42e=f42e))
    # (g) distinguishable stale pre-states on every unconditionally-written
    #     RAM cell (sentinel coverage for store width/neighbour effects).
    e.append(mk(**{'9f95': 0xDE, '9fa1': 0xAD, '9fa2': 0xBE, '9fc1': 0xEF,
                   '9fc2': 0x00, '9fc5': 0xFE, '9fc3': 0xED, '9fc6': 0xF0,
                   '9fc7': 0x0D, '9fc8': 0xCA, '9fc9': 0xFE, '9fca': 0xBA,
                   '9fcb': 0xBE, '9fce': 0x01, '9fa0': 0x02, '9f8c': 0x04,
                   '9fe8': 0x08, '9f94': 0x10, '9f80': 0x11111111,
                   '9f84': 0x22222222, '9f88': 0x33333333, '9f90': 0x44444444,
                   '9fb0': 0x55555555, '9fbc': 0x66666666, '9ff0': 0x77777777,
                   '9ff4': 0x88888888, '9ff8': 0x99999999, '9ffc': 0xAAAAAAAA,
                   '9fec': 0xBBBBBBBB, '9fcc': 0xCCCC}))
    return e


def gen_random(rng, n):
    """n random vectors over the full byte/word range of every cell, biased
    onto the crank_vars_init branch (35%) and constrained so the emulator can
    never tail into crank_mode_switch (see harness header)."""
    v = []
    for _ in range(n):
        r = [rng.getrandbits(w * 8) for _, _, w in LOCS]
        if rng.random() < 0.35:
            r[I_FC0] = 1
        else:
            r[I_FC0] = rng.randrange(0, 256)
            while r[I_FC0] == 1:
                r[I_FC0] = rng.randrange(0, 256)
        if r[I_FC0] == 1:
            if rng.random() < 0.5:
                r[I_FA3] = 2
            else:
                r[I_FA3] = rng.randrange(0, 256)
                while r[I_FA3] == 2:
                    r[I_FA3] = rng.randrange(0, 256)
            if r[I_FA3] != 2:
                r[I_F96] = rng.choice((0, 2, 0x7F, 0xFE, 0xFF))
        v.append(tuple(r))
    return v


# ---- emulator / oracle glue -------------------------------------------------
def seed_ram(vec):
    """Vector -> big-endian sparse-RAM overlay for the emulator."""
    ram = {}
    for (name, addr, width), val in zip(LOCS, vec):
        for i in range(width):
            ram[(addr + i) & 0xFFFFFFFF] = (val >> (8 * (width - 1 - i))) & 0xFF
    return ram


def call_rom(cpu, vec):
    """Run the ROM bytes @0x753C (all callees + the tail-call target included)
    over one vector; return the 49 cells."""
    cpu.call(ADDR, ram=seed_ram(vec))
    return tuple(cpu.rd(addr, width) for _, addr, width in LOCS)


def fmt_vec(vec):
    """Vector -> oracle stdin line."""
    return 'fuel ' + ' '.join('%X' % val for val in vec)


def fmt_res(vals):
    """49 ints -> oracle output line (width-aligned hex)."""
    return ' '.join('%0*X' % (w * 2, val)
                    for val, (_, _, w) in zip(vals, LOCS))


def build_oracle(cc='cc'):
    """Compile this harness' own oracle into the task-mandated build dir."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_fueling_init.c'),
           os.path.join(SAMPLES, 'src', 'rx8_fueling_init.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)
    check_cal(cpu)
    # The oracle maps the ROM page straight from the file — point it there.
    os.environ['RX8_ROM_PATH'] = ROM_PATH

    vectors = gen_edges() + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (real bytes incl. all callees).
    emu = []
    for v in vectors:
        try:
            emu.append(call_rom(cpu, v))
        except (NotImplementedError, RuntimeError) as exc:
            print('EMULATOR ERROR on vec#%d: %s' % (len(emu), exc))
            sys.exit(1)

    # (b) host-C on the same vectors (net effects inlined in the sample).
    host = [fmt_res(tuple(int(x, 16) for x in ln.split()))
            for ln in run_oracle(oracle, [fmt_vec(v) for v in vectors])]

    # (c) compare all 49 side-effected/observed cells bit-exactly.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if fmt_res(e) != h:
            mismatches.append('vec#%d init=%s ROM=%s C=%s'
                              % (i, fmt_vec(v).replace('fuel ', ''), fmt_res(e), h))
            if len(mismatches) >= 5:
                break

    report('fueling_init', ADDR, n, mismatches, edges=len(gen_edges()))


if __name__ == '__main__':
    main()
