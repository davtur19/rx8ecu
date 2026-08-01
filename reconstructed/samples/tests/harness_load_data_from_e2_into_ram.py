#!/usr/bin/env python3
"""
harness_load_data_from_e2_into_ram.py — equivalence of
rx8_load_data_from_e2_into_ram @0x36BD6.

Reconstructed source: samples/src/rx8_load_data_from_e2_into_ram.c
Verified lift   : c/loadDatafromE2intoRAM.c (loadDatafromE2intoRAM @ 0x36BD6)

The ROM function is an ABI-clean leaf wrapper: loadDatafromE2intoRAM(void)
calls E2IntoRAM(0, 32) @0x38F58 and returns nothing (r0 is a side-channel
holding E2IntoRAM's return: 1 = SPI-retry busy -> early abort, 0 = copy done).
It is entered through the normal ABI with no arguments, so the plain
`cpu.call()` API works (like c/tests/test_getFromE2.py).

HARDWARE ABSTRACTION (why 0xBFCA / 0xC0A8 are stubbed):
E2IntoRAM polls the SPI-retry hook 0xC0A8; in the default emulator state
(GPIO data-in 0xFFFFF738 bit 0x0800 clear) it returns 1 and the loader aborts
with no side effects.  Mode-0 vectors therefore run the REAL retry hook with a
controlled 0xFFFFF738 word.  The real flash reader 0xBFCA bit-bangs the on-chip
SPI and busy-waits on peripheral status bits of 0xFFFFF024 that sh2emu cannot
model, so it can never terminate there; following the repo-established pattern
(c/tests/test_getFromE2.py) mode-1/2 vectors stub 0xBFCA (and mode 1 also
0xC0A8) in the RAM overlay, then execute the REAL wrapper bytes and the REAL
E2IntoRAM control flow + copy loop.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (retry busy/ready boundaries, flash word boundaries 0x00,
     0x7F/0x80 sign-extension split, 0xFF, half-index loop) + N random
     (mode 0: real retry with random 16-bit GPIO word; mode 1: stub retry;
      mode 2: half-varying flash word),
  3. run the ROM bytes @0x36BD6 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare r0, the scratch half-window 0xFFFFC502/0xFFFFC504 and the full
     256-byte primary+complement shadows — 0 mismatches required.

Usage:  python3 harness_load_data_from_e2_into_ram.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2  # noqa: E402

ADDR = 0x36BD6
N_DEFAULT = 20000

E2_PRIM = 0xFFFFC2FE          # primary   EEPROM shadow base
E2_COMP = 0xFFFFC3FE          # complement EEPROM shadow base
E2_C502 = 0xFFFFC502          # scratch: half_start
E2_C503 = E2_C502 + 1
E2_C504 = 0xFFFFC504          # scratch: half_end
E2_C505 = E2_C504 + 1
GPIO_RDY = 0xFFFFF738         # SPI data-in register word (e2_retry source)

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-load_data_from_e2_into_ram')


# ---------------------------------------------------------------------------
# ROM-side setup: RAM-overlay stubs + GPIO injection (byte-exact with the ROM)
# ---------------------------------------------------------------------------
def word16(addr, val):
    """Big-endian 16-bit value injected into the sparse-RAM overlay."""
    return {addr: (val >> 8) & 0xFF, addr + 1: val & 0xFF}


def stub_retry(val):
    """mov #val,r0 ; rts ; nop  @0xC0A8 (e2_retry) — 6 bytes, like the real code."""
    return {0xC0A8: 0xE0, 0xC0A9: val & 0xFF, 0xC0AA: 0x00, 0xC0AB: 0x0B,
            0xC0AC: 0x00, 0xC0AD: 0x09}


def stub_flash_const(v):
    """mov #v,r0 ; rts ; nop  @0xBFCA (e2_flash_read) — 8-bit imm sign-extended."""
    return {0xBFCA: 0xE0, 0xBFCB: v & 0xFF, 0xBFCC: 0x00, 0xBFCD: 0x0B,
            0xBFCE: 0x00, 0xBFCF: 0x09}


def stub_flash_half():
    """mov r4,r0 ; shlr16 r0 ; rts ; nop  @0xBFCA — word = 0x0600 + half idx."""
    return {0xBFCA: 0x60, 0xBFCB: 0x43, 0xBFCC: 0x40, 0xBFCD: 0x29,
            0xBFCE: 0x00, 0xBFCF: 0x0B, 0xBFD0: 0x00, 0xBFD1: 0x09}


def run_vector(cpu, mode, a, b):
    """Execute the REAL ROM bytes @0x36BD6 on one vector; return the full
    observable result tuple (ret, c502, c504, primary[256], complement[256])."""
    ram = {}
    if mode == 0:                       # real retry hook (0xC0A8), stubbed flash
        ram.update(word16(GPIO_RDY, a & 0xFFFF))
        ram.update(stub_flash_const(b))
    elif mode == 1:                     # stubbed retry + stubbed flash
        ram.update(stub_retry(0 if a == 0 else 1))
        ram.update(stub_flash_const(b))
    else:                               # mode 2: retry=0, half-varying flash
        ram.update(stub_retry(0))
        ram.update(stub_flash_half())
    for i in range(256):                # initial shadow (deterministic, seed b)
        v = (b + 7 * i) & 0xFF
        ram[E2_PRIM + i] = v
        ram[E2_COMP + i] = (~v) & 0xFF

    r0 = cpu.call(ADDR, ram=ram)
    prim = bytes(cpu.ram.get(E2_PRIM + i, 0) for i in range(256))
    comp = bytes(cpu.ram.get(E2_COMP + i, 0) for i in range(256))
    c502 = (cpu.ram.get(E2_C502, 0) << 8) | cpu.ram.get(E2_C503, 0)
    c504 = (cpu.ram.get(E2_C504, 0) << 8) | cpu.ram.get(E2_C505, 0)
    return ((r0 & 0xFF), c502, c504, prim, comp)


# ---------------------------------------------------------------------------
# vectors
# ---------------------------------------------------------------------------
def gen_edges():
    """Edge vectors: retry busy/ready boundaries (bit 0x0800 of 0xFFFFF738),
    flash-word boundaries (0x00, 0x7F/0x80 sign-extension split, 0xFF) and the
    half-index loop."""
    v = []
    for a in (0x0000, 0x07FF, 0x0800, 0x0801, 0x0FFF, 0xF7FF, 0xF800, 0xFFFF):
        for b in (0x00, 0x7F, 0x80, 0xFF):
            v.append((0, a, b))                 # real retry
    for a in (0, 1):
        for b in (0x00, 0x01, 0x7F, 0x80, 0x81, 0xFF):
            v.append((1, a, b))                 # stub retry
    v.append((2, 0, 0x00))
    v.append((2, 0, 0x80))
    return v


def gen_random(rng, n):
    """N random vectors: 50% real retry (random 16-bit GPIO), 45% stub retry,
    5% half-index loop."""
    v = []
    for _ in range(n):
        r = rng.random()
        if r < 0.50:
            v.append((0, rng.getrandbits(16), rng.getrandbits(8)))
        elif r < 0.95:
            v.append((1, rng.getrandbits(1), rng.getrandbits(8)))
        else:
            v.append((2, 0, rng.getrandbits(8)))
    return v


# ---------------------------------------------------------------------------
# oracle
# ---------------------------------------------------------------------------
def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a host binary.
    (common.build_oracle is not reusable: it hardcodes the sample .c list.)"""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_load_data_from_e2_into_ram.c'),
           os.path.join(SAMPLES, 'src', 'rx8_load_data_from_e2_into_ram.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def parse_oracle(line):
    toks = line.split()
    return (int(toks[0], 16), int(toks[1], 16), int(toks[2], 16),
            bytes.fromhex(toks[3]), bytes.fromhex(toks[4]))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2(f.read())
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = gen_edges() + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (real bytes @0x36BD6).
    emu = [run_vector(cpu, mode, a, b) for mode, a, b in vectors]

    # (b) host C on the same inputs.
    lines = ['e2 %d %X %02X' % (mode, a, b) for mode, a, b in vectors]
    host = [parse_oracle(l) for l in run_oracle(oracle, lines)]

    # (c) compare the full observable state bit-exactly.
    mismatches = []
    for i, ((mode, a, b), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d mode=%d a=%04X b=%02X ROM(ret=%02X c502=%04X c504=%04X '
                'prim=%s.. comp=%s..) C(ret=%02X c502=%04X c504=%04X prim=%s.. '
                'comp=%s..)' % (i, mode, a, b, e[0], e[1], e[2],
                                e[3][:4].hex(), e[4][:4].hex(),
                                h[0], h[1], h[2], h[3][:4].hex(), h[4][:4].hex()))
            if len(mismatches) >= 5:
                break

    report('load_data_from_e2_into_ram', ADDR, n, mismatches, edges=len(gen_edges()))


if __name__ == '__main__':
    main()
