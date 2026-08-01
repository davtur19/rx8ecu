#!/usr/bin/env python3
"""
harness_vfad_control_35bbc.py — equivalence of rx8_vfad_control_35bbc @0x35BBC.

Reconstructed source: samples/src/rx8_vfad_control_35bbc.c
Verified lift   : c/vfad_control_35BBC.c (same address; the ROM bytes are
                  executed for real here via tools/sh2emu.py, including the
                  jsr'd callees 0x5D800 and 0x4BBC).

The function is a void control task with NO ABI return value: its whole effect
is on RAM (the VFAD command byte @0xFFFFC234, bit 0x0400 of the hardware word
@0xFFFFF754, and the 0x5D800 alternating-sensor SM cells — state @0xFFFFD355,
latch @0xFFFFD38F and the output byte behind the stored pointer @0x60260,
pinned to 0xFFFFD500), so the equivalence check compares RAM side-effects,
not a return value:

  - emulator side: seed the boost f32, the SM descriptor (mask @0x6025C,
    output pointer @0x60260 -> 0xFFFFD500) and the on-chip RAM cells (VFAD
    command @0xFFFFC234, state @0xFFFFD355, magic @0xFFFFD350, source
    @0xFFFFD352, count @0xFFFFD354, input @0xFFFFD3A8, latch @0xFFFFD38F,
    output byte @0xFFFFD500, hardware word @0xFFFFF754), call the ROM entry
    @0x35BBC, read the five side-effected cells back;
  - host side: the dedicated oracle mmap()s the pages backing the same cells
    AND the ROM calibration table @0x7A5AC/@0x7A5B0, seeds the same bytes
    (the two f32 cal constants shipped inline from the ROM), runs the
    reconstructed C and prints the same five cells.

EDGE vectors cover the hysteresis band (both thresholds, 1 ulp around them,
0, max, sign flips, NaN, +/-inf) and every branch of the 0x5D800 SM (ST 0/1/2,
magic match/mismatch, masked 0/nonzero, CNT 7/other, out 0/5/7/other); N
random pre-states follow (fixed seed).  The stock ROM constants @0x7A5AC
(5250.0) and @0x7A5B0 (188.0) are asserted before the run.

Usage:  python3 harness_vfad_control_35bbc.py [N]  (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle, SAMPLES  # noqa: E402
from sh2emu import f2bits, bits2f  # noqa: E402

ADDR = 0x35BBC
N_DEFAULT = 20000
SEED = 0x35BBC
BUILD_DIR = '/tmp/rx8-recon-vfad_control_35bbc'

BOOST_ADDR = 0xFFFFB5B8       # f32 boost pressure
CMD_ADDR = 0xFFFFC234         # u8 VFAD command
F754_ADDR = 0xFFFFF754        # u16 hardware word, bit 0x0400
SM_MASK_ADDR = 0x6025C        # u8 sensor mask  (SM_BASE + 8)
SM_PTR_ADDR = 0x60260         # u32 stored output pointer (SM_BASE + 0xC)
ST_ADDR = 0xFFFFD355          # u8 state byte
MAGIC_ADDR = 0xFFFFD350       # u16 magic word (0x17C8)
INP_ADDR = 0xFFFFD3A8         # u8 sensor input byte
CNT_ADDR = 0xFFFFD354         # u8 count byte
SRC_ADDR = 0xFFFFD352         # u16 source word
LATCH_ADDR = 0xFFFFD38F       # u8 output latch
PTR_CELL = 0xFFFFD500         # u8 output byte behind SM_PTR
ROM_ON_ADDR = 0x7A5AC         # f32 on-threshold (5250.0)
ROM_HYST_ADDR = 0x7A5B0       # f32 hysteresis width (188.0)

ON_BITS = 0x45A41000          # 5250.0
HYST_BITS = 0x433C0000        # 188.0


def seed_ram(init, addr, n, val):
    """Byte-exact big-endian store of a width-`n` value in the ram overlay."""
    for i in range(n):
        init[addr + i] = (val >> (8 * (n - 1 - i))) & 0xFF


def run_emu(cpu, vec):
    """Seed boost + SM descriptor + RAM cells, run the ROM bytes @0x35BBC and
    return (cmd, f754, st, latch, ptrcell) with the side effects visible."""
    boost, cmd0, mask, st, magic, src, cnt, inp, latch, ptrcell, f754 = vec
    init = {CMD_ADDR: cmd0 & 0xFF, SM_MASK_ADDR: mask & 0xFF}
    seed_ram(init, BOOST_ADDR, 4, boost & 0xFFFFFFFF)
    seed_ram(init, SM_PTR_ADDR, 4, PTR_CELL)
    seed_ram(init, MAGIC_ADDR, 2, magic & 0xFFFF)
    seed_ram(init, SRC_ADDR, 2, src & 0xFFFF)
    init[CNT_ADDR] = cnt & 0xFF
    init[ST_ADDR] = st & 0xFF
    init[INP_ADDR] = inp & 0xFF
    init[LATCH_ADDR] = latch & 0xFF
    init[PTR_CELL] = ptrcell & 0xFF
    seed_ram(init, F754_ADDR, 2, f754 & 0xFFFF)
    cpu.call(ADDR, ram=init)
    return (cpu.rd(CMD_ADDR, 1),
            cpu.rd(F754_ADDR, 2),
            cpu.rd(ST_ADDR, 1),
            cpu.rd(LATCH_ADDR, 1),
            cpu.rd(PTR_CELL, 1))


def gen_edges():
    """Edge vectors: (boost_bits, cmd0, mask, st, magic, src, cnt, inp,
    latch, ptrcell, f754).  Covers the hysteresis band on both sides of both
    thresholds (0/+/-, NaN, infinities, sign flips) and every branch of the
    0x5D800 SM with a few distinguishable stale pre-states."""
    v = []
    boosts = [0.0, -0.0, 1.0, 5061.0, 5062.0, 5063.0, 5249.0, 5250.0, 5251.0,
              6000.0, 1e30, -1e30, -100.0]
    for b in boosts:
        for prev in (0, 1):
            v.append((f2bits(b), prev, 0xC0, 0x00, 0x17C8, 0x0000, 0x00,
                      0x00, 0x00, 0x33, 0x1234))
    # raw bit edges: NaN, +/-inf, max finite, min subnormal, sign flip
    for bits in (0x7FC00000, 0x7F800000, 0xFF800000, 0x7F7FFFFF, 0xFF7FFFFF,
                 0x00000001, 0x80000000):
        for prev in (0, 1):
            v.append((bits, prev, 0xC0, 0x01, 0x17C8, 0x0000, 0x07, 0xFF,
                      0x00, 0x00, 0x0000))
    # SM: ST 0/1/2/FF, magic match/mismatch, masked 0/nonzero, CNT 7/other
    for st in (0, 1, 2, 0xFF):
        for magic in (0x17C8, 0x0000, 0x17C9):
            v.append((f2bits(5200.0), 0, 0xFF, st, magic, 0xABCD, 0x07,
                      0x01, 0x11, 0x22, 0x0000))
            v.append((f2bits(5200.0), 0, 0x0F, st, magic, 0xABCD, 0x06,
                      0x40, 0x11, 0x22, 0xFFFF))
    # second-block outcomes: out (ptr cell) 0/1/5/7/other after the SM store
    for pc in (0, 1, 5, 7, 8, 0xFF):
        v.append((f2bits(5200.0), 1, 0xFF, 0x00, 0x17C8, 0x1234, 0x07, 0x01,
                  0x00, pc, 0x0000))
    return v


def gen_random(rng, k):
    """k random pre-states.  Magic is biased to the 0x17C8 match so the SM
    first block gets covered; boost is drawn from in-range values plus raw
    float bits (so NaN/inf paths appear too)."""
    v = []
    for _ in range(k):
        if rng.random() < 0.5:
            boost = f2bits(rng.uniform(-2000.0, 14000.0))
        else:
            boost = rng.getrandbits(32)
        magic = rng.choice((0x17C8, 0x17C8, rng.getrandbits(16)))
        v.append((boost,
                  rng.getrandbits(8),    # cmd0
                  rng.getrandbits(8),    # mask
                  rng.getrandbits(8),    # st
                  magic,
                  rng.getrandbits(16),   # src
                  rng.getrandbits(8),    # cnt
                  rng.getrandbits(8),    # inp
                  rng.getrandbits(8),    # latch
                  rng.getrandbits(8),    # ptrcell
                  rng.getrandbits(16)))  # f754
    return v


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a host binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_vfad_control_35bbc.c'),
           os.path.join(SAMPLES, 'src', 'rx8_vfad_control_35bbc.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)

    # The two f32 calibration constants the ROM reads at 0x7A5AC/0x7A5B0.
    on = struct.unpack('>I', bytes(cpu.rom[ROM_ON_ADDR:ROM_ON_ADDR + 4]))[0]
    hyst = struct.unpack('>I', bytes(cpu.rom[ROM_HYST_ADDR:ROM_HYST_ADDR + 4]))[0]
    if (on, hyst) != (ON_BITS, HYST_BITS):
        raise RuntimeError(
            'unexpected ROM calibration @0x7A5AC: on=0x%08X hyst=0x%08X'
            % (on, hyst))

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM side-effects).
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host-C on the same pre-states (ROM calibration bytes shipped inline).
    lines = ['vfad %08X %02X %02X %02X %04X %04X %02X %02X %02X %02X %04X %08X %08X'
             % (v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8], v[9],
                v[10], on, hyst) for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the post-state tuples byte-for-byte.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d boost=0x%08X(%.9g) cmd0=%02X st=%02X magic=%04X '
                'cell0=%02X f7540=%04X ROM=(%02X,%04X,%02X,%02X,%02X) '
                'C=(%02X,%04X,%02X,%02X,%02X)'
                % (i, v[0], bits2f(v[0]), v[1], v[3], v[4], v[9], v[10],
                   e[0], e[1], e[2], e[3], e[4],
                   h[0], h[1], h[2], h[3], h[4]))
            if len(mismatches) >= 5:
                break

    report('vfad_control_35bbc', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
