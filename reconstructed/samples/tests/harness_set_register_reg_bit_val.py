#!/usr/bin/env python3
"""
harness_set_register_reg_bit_val.py — equivalence of
rx8_set_register_reg_bit_val @0x4BBC.

Reconstructed source: samples/src/rx8_set_register_reg_bit_val.c
Verified lift   : c/setRegister_REG_BIT_VAL.c (setRegister_REG_BIT_VAL @ 0x4BBC)

CALLING CONVENTION: standard SH-2 ABI — r4 = register pointer (uint16_t *),
r5 = mask, r6 = enable flag; no return value.  The function has a RAM
side-effect (it writes the modified 16-bit word back through r4), so the
equivalence compares RAM, not a return register:

  - emulator side: seed the sparse ram overlay with the initial register
    value as big-endian bytes at `addr`, call the ROM entry via cpu.call()
    with r4=addr / r5=mask / r6=enable, read the word back;
  - host side: the oracle mmap()s the same page (MAP_FIXED), seeds the same
    initial word, runs the reconstructed C, prints the word back.

Both sides therefore compare the numeric 16-bit value written to the
register.  `enable` is shipped as a full 32-bit word so the ROM's
`extu.w r6,r6` is exercised too (a flag with bit >= 16 set must still mean
"clear" once truncated — see the source header).

Procedure (Track-A pattern):
  1. build the host oracle (system gcc),
  2. edge vectors (register/mask extremes and boundary patterns x enable
     edges incl. 0x10000 and sign bits) + N random (init, mask, 32-bit
     enable) triples,
  3. run the ROM bytes @0x4BBC in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare — 0 mismatches required.

This harness compiles its OWN oracle binary (tests/oracle_set_register_reg_bit_val.c
+ src/rx8_set_register_reg_bit_val.c) into /tmp/rx8-recon-set_register_reg_bit_val/.

Usage:  python3 harness_set_register_reg_bit_val.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x4BBC
N_DEFAULT = 20000

# Register window addresses: page-aligned bases above mmap_min_addr so the
# host oracle can MAP_FIXED them; the emulator overlay uses the same numbers.
REG_BASES = (0x00020000, 0x00030000)

BUILD_DIR = '/tmp/rx8-recon-set_register_reg_bit_val'
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Edge vectors: register/mask extremes and boundary patterns x enable edges.
REGVALS = (0x0000, 0x0001, 0x7FFF, 0x8000, 0xFFFE, 0xFFFF, 0x5555, 0xAAAA)
MASKS   = (0x0000, 0x0001, 0x7FFF, 0x8000, 0xFFFE, 0xFFFF, 0x5555, 0xAAAA)
ENABLES = (0x00000000, 0x00000001, 0x0000FFFF, 0x00008000,
           0x00010000, 0x80000000, 0xFFFFFFFF)


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_...c + the source)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_set_register_reg_bit_val.c'),
           os.path.join(SAMPLES, 'src', 'rx8_set_register_reg_bit_val.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def seed_reg(addr, init):
    """Initial register value as big-endian bytes (matches the ROM's mov.w)."""
    return {addr: (init >> 8) & 0xFF, addr + 1: init & 0xFF}


def read_reg(cpu, addr):
    return (cpu.ram.get(addr, 0) << 8) | cpu.ram.get(addr + 1, 0)


def build_vectors(n):
    """Edge vectors (cross-product of register/mask/enable boundaries) plus
    `n` random (init, mask, 32-bit enable) triples."""
    rng = make_rng(0x4BBC)
    vecs = [(REG_BASES[0], r, m, e)
            for r in REGVALS for m in MASKS for e in ENABLES]
    vecs += [(REG_BASES[1], r, m, 0) for r in REGVALS for m in MASKS]
    for _ in range(n):
        vecs.append((rng.choice(REG_BASES), rng.getrandbits(16),
                     rng.getrandbits(16), rng.getrandbits(32)))
    return vecs


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    vecs = build_vectors(n)
    n_edges = len(vecs) - n

    # (a) ROM behaviour via the emulator (RAM side-effect).
    emu = []
    for addr, init, mask, enable in vecs:
        cpu.call(ADDR, r4=addr, r5=mask, r6=enable, ram=seed_reg(addr, init))
        emu.append(read_reg(cpu, addr))

    # (b) host-C on the same inputs.
    lines = ['reg %08X %04X %04X %08X' % (addr, init, mask, enable)
             for addr, init, mask, enable in vecs]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, ((addr, init, mask, enable), e, h) in enumerate(zip(vecs, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d addr=%08X init=%04X mask=%04X enable=%08X '
                'ROM=%04X C=%04X' % (i, addr, init, mask, enable, e, h))
            if len(mismatches) >= 5:
                break

    report('setRegister_REG_BIT_VAL', ADDR, n, mismatches, edges=n_edges)


if __name__ == '__main__':
    main()
