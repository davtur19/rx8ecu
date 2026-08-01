#!/usr/bin/env python3
"""
harness_get_data_from_e2_ram.py — equivalence of rx8_get_data_from_e2_ram @0x36C1C.

Reconstructed source: samples/src/rx8_get_data_from_e2_ram.c
Verified lift   : c/getDataFromE2RAM.c (getDataFromE2RAM @ 0x36C1C)

The ROM function is an ABI-clean leaf: getDataFromE2RAM(void) performs 19
getFromE2_E2ADDR_RAMADDR_LEN(e2addr, dest, len) @0x39170 calls (one per
EEPROM region) and returns nothing; r0 is a side channel holding the LAST
call's return (the error flag of EEPROM[0x1E]).  It is entered through the
normal ABI with no arguments, so the plain `cpu.call()` API works.

HARDWARE ABSTRACTION (why 0x3920/0x3934/0xC0A8/0xBFCA are stubbed):
getFromE2 saves/restores SR via getSR@0x3920/setSR@0x3934, polls the SPI
retry hook 0xC0A8 on a corrupt (value,~value) pair and, on retry success,
re-reads the byte from the FLASH backup through the SPI bit-bang reader
0xBFCA.  The real 0xBFCA busy-waits on peripheral status bits of 0xFFFFF024
that sh2emu cannot model, so it can never terminate there; following the
repo-established pattern (c/tests/test_getFromE2.py,
harness_load_data_from_e2_into_ram.py) the harness stubs all four helper
addresses in the RAM overlay, then executes the REAL getDataFromE2RAM bytes
and the REAL getFromE2 control flow + validation/copy/recovery loops.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (all-valid shadows at 0x00/0xFF/0x55/0xAA/0x80/0x7F fills,
     single corrupt pair at every E2 index with retry 0 and flash 0x00/0x7F/
     0x80/0xFF, single corrupt pair with retry 1, fully corrupt shadow) + N
     random vectors (retry 0/1, random flash, random shadow with 15% corrupt
     pairs, random dest pre-fill seed),
  3. run the ROM bytes @0x36C1C in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare r0, the 30 destination bytes (CAN shadow C242..C244 + working
     copies C2D8..C2F2) and the 32-byte primary+complement E2 shadows —
     0 mismatches required.

Usage:  python3 harness_get_data_from_e2_ram.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2  # noqa: E402

ADDR = 0x36C1C
N_DEFAULT = 20000

E2_PRIM = 0xFFFFC2FE          # primary   EEPROM shadow base
E2_COMP = 0xFFFFC3FE          # complement EEPROM shadow base
DEST_PREFILL_LO = 0xFFFFC240  # destination pre-fill window (C240..C2FD)
DEST_PREFILL_HI = 0xFFFFC2FE  # exclusive
CAN_BASE = 0xFFFFC242         # CAN shadow bytes C242..C244 (mov.w sign-ext)
WORK_BASE = 0xFFFFC2D8        # E2 working-copy block C2D8..C2F2

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-get_data_from_e2_ram')


# ---------------------------------------------------------------------------
# ROM-side setup: RAM-overlay stubs (byte-exact with the ROM)
# ---------------------------------------------------------------------------
def stub_mov(addr, imm):
    """mov #imm,r0 ; rts ; nop — 8-bit imm SIGN-extended, like the real code."""
    return {addr: 0xE0, addr + 1: imm & 0xFF, addr + 2: 0x00, addr + 3: 0x0B,
            addr + 4: 0x00, addr + 5: 0x09}


def stub_rts(addr):
    """rts ; nop."""
    return {addr: 0x00, addr + 1: 0x0B, addr + 2: 0x00, addr + 3: 0x09}


def run_vector(cpu, retry, flash, seed, p, c):
    """Execute the REAL ROM bytes @0x36C1C on one vector; return the full
    observable result tuple (r0, dest[30], primary[32], complement[32])."""
    ram = {}
    ram.update(stub_mov(0x3920, 0xF0))   # getSR -> 0xF0 (SR & 0xF0 default)
    ram.update(stub_rts(0x3934))         # setSR: no observable RAM effect
    ram.update(stub_mov(0xC0A8, retry))  # e2_retry: 0 = recover, !=0 = fail
    ram.update(stub_mov(0xBFCA, flash))  # e2_flash_read: 8-bit imm, sign-ext
    for i in range(32):                  # E2 shadow for E2[0x00..0x1F]
        ram[E2_PRIM + i] = p[i] & 0xFF
        ram[E2_COMP + i] = c[i] & 0xFF
    for k in range(DEST_PREFILL_LO, DEST_PREFILL_HI):   # dest pre-fill
        ram[k] = (seed + 3 * (k - DEST_PREFILL_LO)) & 0xFF

    r0 = cpu.call(ADDR, ram=ram)
    dest = bytes(cpu.ram.get(CAN_BASE + i, 0) for i in range(3)) + \
           bytes(cpu.ram.get(WORK_BASE + i, 0) for i in range(0x1B))
    prim = bytes(cpu.ram.get(E2_PRIM + i, 0) for i in range(32))
    comp = bytes(cpu.ram.get(E2_COMP + i, 0) for i in range(32))
    return (r0 & 0xFF, dest, prim, comp)


# ---------------------------------------------------------------------------
# vectors
# ---------------------------------------------------------------------------
def gen_edges():
    """Edge vectors: all-valid shadows at boundary fills, single corrupt pair
    at every E2 index (both data-side and complement-side corruption) with
    retry 0 across flash-word boundaries, single corrupt pair with retry 1
    (error flag path), and a fully corrupt shadow."""
    v = []

    # All-valid shadows; retry/flash are irrelevant but exercised anyway.
    for fill in (0x00, 0xFF, 0x55, 0xAA, 0x80, 0x7F):
        p = [(fill + 3 * i) & 0xFF for i in range(32)]
        c = [~x & 0xFF for x in p]
        for retry in (0, 1):
            v.append((retry, 0x00, 0xAA, p, c))

    # Single corrupt pair at every index; retry 0 (recovery path), flash at
    # the sign-extension boundaries; both data- and complement-side corruption.
    for i in range(32):
        for flash in (0x00, 0x7F, 0x80, 0xFF):
            p = [(0x11 + 5 * j) & 0xFF for j in range(32)]
            c = [~x & 0xFF for x in p]
            c[i] = (c[i] + 1) & 0xFF               # corrupt complement side
            v.append((0, flash, 0x55, p, c))
            p2 = list(p)
            p2[i] = (p2[i] + 1) & 0xFF             # corrupt data side
            v.append((0, flash, 0x55, p2, c))

    # Single corrupt pair, retry 1 (error flag: byte not copied, pair kept).
    for i in range(32):
        p = [(0x33 + 5 * j) & 0xFF for j in range(32)]
        c = [~x & 0xFF for x in p]
        c[i] = (c[i] ^ 0x5A) & 0xFF
        v.append((1, 0x00, 0x77, p, c))

    # Fully corrupt shadow; retry 0 (everything rebuilt from FLASH).
    p = [(0x10 + 3 * j) & 0xFF for j in range(32)]
    c = [(0xE0 + 5 * j) & 0xFF for j in range(32)]
    for flash in (0x00, 0x80, 0xFF):
        v.append((0, flash, 0xAA, p, c))

    return v


def gen_random(rng, n):
    """N random vectors: random 32-byte shadow with ~15% corrupt pairs,
    random retry 0/1, random flash byte, random dest pre-fill seed."""
    v = []
    for _ in range(n):
        p = [rng.randrange(256) for _ in range(32)]
        c = []
        for j in range(32):
            if rng.random() < 0.85:
                c.append((~p[j]) & 0xFF)
            else:
                c.append(rng.randrange(256))
        v.append((rng.randrange(2), rng.randrange(256), rng.randrange(256),
                  p, c))
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
           os.path.join(SAMPLES, 'tests', 'oracle_get_data_from_e2_ram.c'),
           os.path.join(SAMPLES, 'src', 'rx8_get_data_from_e2_ram.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def parse_oracle(line):
    toks = line.split()
    return (int(toks[0], 16), bytes.fromhex(toks[1]), bytes.fromhex(toks[2]),
            bytes.fromhex(toks[3]))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2(f.read())
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = gen_edges() + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (real bytes @0x36C1C).
    emu = [run_vector(cpu, retry, flash, seed, p, c)
           for retry, flash, seed, p, c in vectors]

    # (b) host C on the same inputs (shadow shipped inline as hex).
    lines = ['e2 %d %02X %02X %s %s' % (retry, flash, seed, bytes(p).hex(),
                                        bytes(c).hex())
             for retry, flash, seed, p, c in vectors]
    host = [parse_oracle(l) for l in run_oracle(oracle, lines)]

    # (c) compare the full observable state bit-exactly.
    mismatches = []
    for i, ((retry, flash, seed, p, c), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d retry=%d flash=%02X seed=%02X ROM(r0=%02X dest=%s.. '
                'prim=%s.. comp=%s..) C(r0=%02X dest=%s.. prim=%s.. comp=%s..)'
                % (i, retry, flash, seed, e[0], e[1][:4].hex(), e[2][:4].hex(),
                   e[3][:4].hex(), h[0], h[1][:4].hex(), h[2][:4].hex(),
                   h[3][:4].hex()))
            if len(mismatches) >= 5:
                break

    report('get_data_from_e2_ram', ADDR, n, mismatches, edges=len(gen_edges()))


if __name__ == '__main__':
    main()
