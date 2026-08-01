#!/usr/bin/env python3
"""
harness_calc_rotor_sync_idle_gate_b.py — equivalence of
rx8_calc_rotor_sync_idle_gate_b @0x12BC8.

Reconstructed source: samples/src/rx8_calc_rotor_sync_idle_gate_b.c
Verified lift   : c/calc_rotor_sync_idle_gate_B.c (same address; the ROM
                  bytes are executed for real here via tools/sh2emu.py).

The function is a void control gate with NO ABI return value: its whole effect
is on RAM.  The equivalence check therefore compares the four side-effect
cells, not a return value:

  - RAM[0xFFFFA690] u8    control flag (set to 1 only when the gate fires,
                          ALWAYS (re)stored — both branches write it)
  - RAM[0xFFFFA694] f32   prev-RPM sample (always := current rpm)
  - RAM[0xFFFFA6A3] u8    rotor-A status latch (always := rotor-A status)
  - RAM[0xFFFFA6A4] u8    rotor-B status latch (always := rotor-B status)

The two calibration thresholds (ROM[0x72BC4]=40.0, ROM[0x72BC8]=2000.0) are
read by BOTH sides from the same stock ROM bytes: the emulator reads them from
the ROM image, and the host oracle mmap()s the ROM page 0x72000 (at the actual
file offset) so the reconstructed C dereferences the identical constants.

  - emulator side: seed the ten input cells in the sparse ram overlay
    (rotor status @0xFFFFA444/A445, rpm @0xFFFFB5B8, prev @0xFFFFA694, flag
    sentinel @0xFFFFA690, cl-enable @0xFFFFB5A4, cl-active @0xFFFFAADA,
    warmup @0xFFFFCABC, enable @0xFFFFA6A3/A6A4), call the ROM entry @0x12BC8
    with the stock SH2.call() and read the four cells back;
  - host side: the dedicated oracle mmap()s the same pages, seeds the same
    bytes (floats shipped as raw IEEE-754 bits so no rounding crosses the
    pipe) and prints the same four cells.

EDGE vectors exercise every gate condition and both flag outcomes with
distinguishable pre-states (flag sentinels, rotor-select branch matrix, the
drop==40 / rpm==2000 boundaries in both directions, NaN/+-inf floats), plus N
random pre-states (fixed seed 0x12BC8).

Usage:  python3 harness_calc_rotor_sync_idle_gate_b.py [N]  (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, load_cpu, make_rng, report  # noqa: E402
# common.py already put <repo>/tools on sys.path (its sh2emu import); fetch the
# float-bit helpers from the same module.
from sh2emu import f2bits  # noqa: E402

ADDR = 0x12BC8
ROTOR_A_ADDR = 0xFFFFA444
ROTOR_B_ADDR = 0xFFFFA445
ENGINE_RPM_ADDR = 0xFFFFB5B8      # f32 current RPM
PREV_RPM_ADDR = 0xFFFFA694        # f32 previous RPM sample (side effect)
GATE_FLAG_ADDR = 0xFFFFA690       # u8 control flag (side effect)
CL_ENABLE_ADDR = 0xFFFFB5A4
CL_ACTIVE_ADDR = 0xFFFFAADA
WARMUP_ADDR = 0xFFFFCABC
ENABLE_A_ADDR = 0xFFFFA6A3       # u8 enable-A / rotor-A latch (side effect)
ENABLE_B_ADDR = 0xFFFFA6A4       # u8 enable-B / rotor-B latch (side effect)
ROM_CAL_ADDR = 0x00072BC4        # f32 40.0 (drop min)
ROM_CAL_ADDR2 = 0x00072BC8       # f32 2000.0 (rpm max)

N_DEFAULT = 20000
SEED = 0x12BC8

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-calc_rotor_sync_idle_gate_b'


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_calc_rotor_sync_idle_gate_b.c'),
           os.path.join(SAMPLES, 'src', 'rx8_calc_rotor_sync_idle_gate_b.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def run_oracle_rom(oracle, vectors):
    """Feed vectors to the oracle (which maps the ROM cal page from the ROM
    file given as argv[1]); return the output lines."""
    proc = subprocess.run([oracle, ROM_PATH], input='\n'.join(vectors) + '\n',
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError('host oracle failed:\n' + proc.stderr)
    lines = proc.stdout.splitlines()
    if len(lines) != len(vectors):
        raise RuntimeError(
            'oracle produced %d outputs for %d vectors' % (len(lines), len(vectors)))
    return lines


def fbits(v):
    """Raw IEEE-754 bits of a Python float, as a u32."""
    return f2bits(v)


def seed_float(ram, addr, bits):
    """Store a f32 as big-endian bytes (the emulator's RAM overlay layout)."""
    ram[addr] = (bits >> 24) & 0xFF
    ram[addr + 1] = (bits >> 16) & 0xFF
    ram[addr + 2] = (bits >> 8) & 0xFF
    ram[addr + 3] = bits & 0xFF


def gen_edges():
    """Edge pre-states (rpm, prev, flag0, clen, clac, warm, enA, enB, rA, rB)."""
    v = []

    # --- flag sentinels on both outcomes: proves the flag write always happens
    for flag0 in (0x00, 0xFF, 0xA5, 0x5A):
        v.append((fbits(1500.0), fbits(1800.0), flag0, 1, 1, 0, 1, 0, 0, 1))   # set
        v.append((fbits(1500.0), fbits(1800.0), flag0, 1, 0, 0, 1, 0, 0, 1))   # clear

    # --- rotor-select branch matrix (gate otherwise enabled)
    # (enA, enB, rA, rB) -> expect: A-arm, B-arm, or fail
    for (enA, enB, rA, rB) in [
        (1, 0, 0, 0xFF),   # A arm
        (1, 1, 0, 0xAA),   # A arm (B irrelevant)
        (0, 1, 0xAA, 0),   # B arm
        (1, 1, 0xAA, 0),   # B arm
        (1, 0, 0xAA, 0xFF),  # fail (A runs, B disabled)
        (0, 0, 0, 0),      # fail (nothing enabled)
        (0, 1, 0xAA, 0xAA),  # fail (B runs)
        (1, 1, 0xAA, 0xAA),  # fail (both rotors run)
        (0xFF, 0xFF, 0, 0),  # 0xFF enable == 1 on the ROM's cmp/eq
        (0, 0, 0xFF, 0xFF),
    ]:
        v.append((fbits(1500.0), fbits(1800.0), 0xAA, 1, 1, 0, enA, enB, rA, rB))

    # --- cl-enable / warmup / cl-active matrix (rotor A armed)
    for (clen, warm, clac) in [
        (1, 0, 1), (0, 1, 1), (1, 1, 1),      # enabled
        (0, 0, 1), (0, 0, 0), (1, 1, 0),      # disabled
        (2, 0, 1), (0xFF, 0, 1), (0, 2, 1),   # !=1 around the ==1 tests
        (0, 1, 2), (0, 1, 0xFF),
    ]:
        v.append((fbits(1500.0), fbits(1800.0), 0xAA, clen, clac, warm, 1, 0, 0, 1))

    # --- drop and rpm float boundaries (clen=clac=1, rotor A armed)
    f40 = fbits(40.0)
    f2000 = fbits(2000.0)
    f40_below = fbits(40.0 - 4e-6)            # next float below 40.0
    f40_above = fbits(40.0 + 4e-6)
    f2000_below = fbits(2000.0 - 4e-6)
    f2000_above = fbits(2000.0 + 4e-6)
    # (rpm, prev) pairs exercising drop and rpm thresholds in both directions
    for (rpm, prev) in [
        (fbits(2000.0),  fbits(2040.0)),       # drop == 40.0 exactly -> set
        (fbits(2000.0),  fbits(2039.99999)),   # drop just below 40.0  -> clear
        (fbits(2000.0),  fbits(2040.00001)),   # drop just above 40.0  -> set
        (fbits(2000.0),  fbits(2000.0)),       # drop == 0             -> clear
        (fbits(1999.0),  fbits(2039.0)),       # drop == 40, rpm<2000  -> set
        (fbits(2000.0 + 4e-6), fbits(2050.0)), # rpm just above 2000   -> clear
        (fbits(2000.0 - 4e-6), fbits(2050.0)), # rpm just below 2000   -> set
        (fbits(0.0),     fbits(0.0)),          # zero rpm, zero drop   -> clear
        (fbits(-1000.0), fbits(0.0)),          # negative rpm
        (fbits(0.0),     fbits(-1000.0)),      # negative drop
        (fbits(3.4e38),  fbits(3.4e38)),       # near max float
        (fbits(1e-30),   fbits(1e-30)),        # denormal-ish tiny
        (fbits(float('nan')), fbits(2000.0)),  # NaN rpm  -> passes fcmp/gt
        (fbits(2000.0),  fbits(float('nan'))), # NaN prev -> drop NaN -> passes
        (fbits(float('inf')),  fbits(float('inf'))),   # inf drop -> passes
        (fbits(float('-inf')), fbits(float('-inf'))),  # -inf drop -> clears
        (fbits(float('-inf')), fbits(2000.0)),          # rpm -inf -> passes
        (fbits(2000.0),  fbits(float('-inf'))),         # drop -inf -> clears
        (fbits(2000.0),  fbits(float('inf'))),          # drop inf -> passes
    ]:
        v.append((rpm, prev, 0xAA, 1, 1, 0, 1, 0, 0, 1))
    # keep the helper constants referenced (used above) -- silence linters
    del f40, f40_below, f40_above, f2000_below, f2000_above

    # --- boundary sweep with all gate bytes at their extremes
    for (rpm, prev) in [(fbits(2040.0), fbits(2080.0)), (fbits(0.0), fbits(0.0))]:
        for (clen, clac, warm) in [(0xFF, 0xFF, 0xFF), (0x00, 0x00, 0x00)]:
            v.append((rpm, prev, 0xAA, clen, clac, warm, 0xFF, 0xFF, 0, 0))
    return v


def gen_random(rng, n):
    """n random pre-states: bytes uniform over 0..255, floats half random-bit
    (NaN/inf/denormals hit the fcmp/gt NaN semantics) half finite RPM values."""
    v = []
    for _ in range(n):
        if rng.random() < 0.5:
            rpm_bits, prev_bits = rng.getrandbits(32), rng.getrandbits(32)
        else:
            rpm_bits = fbits(rng.uniform(-5000.0, 10000.0))
            prev_bits = fbits(rng.uniform(-5000.0, 10000.0))
        v.append((rpm_bits, prev_bits,
                  rng.randrange(256), rng.randrange(256), rng.randrange(256),
                  rng.randrange(256), rng.randrange(256), rng.randrange(256),
                  rng.randrange(256), rng.randrange(256)))
    return v


def call_fn(cpu, rpm_bits, prev_bits, flag0, clen, clac, warm, enA, enB, rA, rB):
    """Run the ROM bytes @0x12BC8 with the given pre-state; return the four
    side-effect cells (flag u8, prev f32 bits, latch A u8, latch B u8)."""
    ram = {
        ROTOR_A_ADDR: rA & 0xFF,
        ROTOR_B_ADDR: rB & 0xFF,
        GATE_FLAG_ADDR: flag0 & 0xFF,
        CL_ENABLE_ADDR: clen & 0xFF,
        CL_ACTIVE_ADDR: clac & 0xFF,
        WARMUP_ADDR: warm & 0xFF,
        ENABLE_A_ADDR: enA & 0xFF,
        ENABLE_B_ADDR: enB & 0xFF,
    }
    seed_float(ram, ENGINE_RPM_ADDR, rpm_bits)
    seed_float(ram, PREV_RPM_ADDR, prev_bits)
    cpu.call(ADDR, ram=ram)
    return (cpu.rd(GATE_FLAG_ADDR, 1), cpu.rd(PREV_RPM_ADDR, 4),
            cpu.rd(ENABLE_A_ADDR, 1), cpu.rd(ENABLE_B_ADDR, 1))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)

    # The two f32 calibration constants the ROM reads at 0x72BC4 / 0x72BC8.
    cal = cpu.rom[ROM_CAL_ADDR:ROM_CAL_ADDR + 8]
    if bytes(cal) != bytes([0x42, 0x20, 0x00, 0x00,   # 40.0
                            0x44, 0xFA, 0x00, 0x00]):  # 2000.0
        raise RuntimeError('unexpected ROM calibration @0x%X: %s'
                           % (ROM_CAL_ADDR, ' '.join('%02X' % b for b in cal)))

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM side-effects).
    emu = [call_fn(cpu, rpm, prev, f0, clen, clac, warm, enA, enB, rA, rB)
           for (rpm, prev, f0, clen, clac, warm, enA, enB, rA, rB) in vectors]

    # (b) host C on the same pre-states (floats shipped as raw bits).
    lines = ['gate %08X %08X %02X %02X %02X %02X %02X %02X %02X %02X'
             % (rpm, prev, f0, clen, clac, warm, enA, enB, rA, rB)
             for (rpm, prev, f0, clen, clac, warm, enA, enB, rA, rB) in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle_rom(oracle, lines)]

    # (c) compare the four side-effect cells bit-exactly.
    mismatches = []
    for k, ((rpm, prev, f0, clen, clac, warm, enA, enB, rA, rB), e, h) in enumerate(
            zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d rpm=0x%08X prev=0x%08X flag0=%02X clen=%02X clac=%02X '
                'warm=%02X enA=%02X enB=%02X rA=%02X rB=%02X '
                'ROM=(%02X,%08X,%02X,%02X) C=(%02X,%08X,%02X,%02X)'
                % (k, rpm, prev, f0, clen, clac, warm, enA, enB, rA, rB,
                   e[0], e[1], e[2], e[3], h[0], h[1], h[2], h[3]))
            if len(mismatches) >= 5:
                break

    report('calc_rotor_sync_idle_gate_B', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
