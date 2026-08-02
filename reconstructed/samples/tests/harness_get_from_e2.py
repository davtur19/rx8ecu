#!/usr/bin/env python3
"""
harness_get_from_e2.py — equivalence of rx8_get_from_e2 @0x39170.

Reconstructed source: samples/src/rx8_get_from_e2.c
Verified lift   : c/getFromE2.c (getFromE2_E2ADDR_RAMADDR_LEN @ 0x39170)

CALLING CONVENTION (SH-2E, full ABI — NOT a leaf):
    in  r4 = e2addr (u16), r5 = ramaddr, r6 = len (u8 in the loop test)
    out r0 = error flag (0 = all valid/recovered, 1 = a corrupt pair whose
                         SPI retry also failed — that byte is NOT copied)
The function makes four `jsr` calls (getSR@0x3920, setSR@0x3934, e2_retry@
0xC0A8, e2_flash_read@0xBFCA), so it needs the stack and PR; it is a normal
ABI function and is entered through the plain `cpu.call()` API (same choice as
harness_get_data_from_e2_ram.py for getDataFromE2RAM and harness_add_saturate_
8bit.py for addSaturate8Bit — no call_leaf driver required).

HARDWARE ABSTRACTION (why 0x3920/0x3934/0xC0A8/0xBFCA are stubbed):
getFromE2 saves/restores SR via getSR@0x3920/setSR@0x3934, polls the SPI
retry hook 0xC0A8 on a corrupt (value,~value) pair and, on retry success,
re-reads the byte from the FLASH backup through the SPI bit-bang reader
0xBFCA.  The real 0xBFCA busy-waits on peripheral status bits of 0xFFFFF024
that sh2emu cannot model, so it can never terminate there; following the
repo-established pattern (c/tests/test_getFromE2.py,
harness_get_data_from_e2_ram.py) the harness stubs all four helper addresses
in the RAM overlay, then executes the REAL getFromE2 bytes + validation/copy/
recovery loops.  getFromE2's retry test is `exts.b r0,r0; tst r0,r0`, so ANY
nonzero stub return means "retry failed" (error flag set, destination byte
left untouched); 0 means "recovered" and the byte is rebuilt from the FLASH
stub and copied.  The flash stub is `mov #imm,r0` (8-bit imm SIGN-extended),
so e.g. flash=0x80 yields the 16-bit word 0xFF80: even offsets take the high
byte (0xFF), odd offsets the low byte (0x80).

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (len=0, all-valid shadows at boundary fills, single corrupt
     pair at every E2 index with retry 0 and flash 0x00/0x7F/0x80/0xFF across
     the sign-extension split, single corrupt pair with retry 1, fully corrupt
     shadow) + N random vectors (retry 0/1, random flash, random shadow with
     15% corrupt pairs, random dest pre-fill seed),
  3. run the ROM bytes @0x39170 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare r0, the 256 destination bytes @0xFFFFA000 and the 256-byte
     primary+complement E2 shadows — 0 mismatches required.

Usage:  python3 harness_get_from_e2.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2  # noqa: E402

ADDR = 0x39170
N_DEFAULT = 20000

E2_PRIM = 0xFFFFC2FE          # primary   EEPROM shadow base (256 bytes)
E2_COMP = 0xFFFFC3FE          # complement EEPROM shadow base (256 bytes)
DEST_BASE = 0xFFFFA000        # destination window (256 bytes, pre-filled)
DEST_LO = DEST_BASE
DEST_HI = DEST_BASE + 256     # exclusive

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-get_from_e2')


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


def run_vector(cpu, e2addr, length, retry, flash, seed, p, c):
    """Execute the REAL ROM bytes @0x39170 on one vector; return the full
    observable result tuple (r0, dest[256], primary[256], complement[256])."""
    ram = {}
    ram.update(stub_mov(0x3920, 0xF0))   # getSR -> 0xF0 (SR & 0xF0 default)
    ram.update(stub_rts(0x3934))         # setSR: no observable RAM effect
    ram.update(stub_mov(0xC0A8, retry))  # e2_retry: 0 = recover, !=0 = fail
    ram.update(stub_mov(0xBFCA, flash))  # e2_flash_read: 8-bit imm, sign-ext
    for i in range(256):                 # E2 shadow for E2[0x00..0xFF]
        ram[E2_PRIM + i] = p[i] & 0xFF
        ram[E2_COMP + i] = c[i] & 0xFF
    for k in range(DEST_LO, DEST_HI):    # dest pre-fill
        ram[k] = (seed + 3 * (k - DEST_LO)) & 0xFF

    r0 = cpu.call(ADDR, r4=e2addr, r5=DEST_BASE, r6=length, ram=ram)
    dest = bytes(cpu.ram.get(DEST_LO + i, 0) for i in range(256))
    prim = bytes(cpu.ram.get(E2_PRIM + i, 0) for i in range(256))
    comp = bytes(cpu.ram.get(E2_COMP + i, 0) for i in range(256))
    return (r0 & 0xFF, dest, prim, comp)


# ---------------------------------------------------------------------------
# vectors
# ---------------------------------------------------------------------------
def gen_edges():
    """Edge vectors: len=0, all-valid shadows at boundary fills, single corrupt
    pair at every E2 index (both data-side and complement-side corruption) with
    retry 0 across flash sign-extension boundaries, single corrupt pair with
    retry 1 (error flag path), and a fully corrupt shadow."""
    v = []

    # len == 0: nothing read, nothing written, return 0.
    p = [(0xAA + 3 * i) & 0xFF for i in range(256)]
    c = [~x & 0xFF for x in p]
    v.append((0x00, 0, 0, 0x00, 0xAA, p, c))

    # All-valid shadows; retry/flash are irrelevant but exercised anyway.
    for fill in (0x00, 0xFF, 0x55, 0xAA, 0x7F, 0x80):
        p = [(fill + 3 * i) & 0xFF for i in range(256)]
        c = [~x & 0xFF for x in p]
        for retry in (0, 1):
            v.append((0x00, 16, retry, 0x00, 0xAA, p, c))

    # Single corrupt pair at every index; retry 0 (recovery path), flash at
    # the sign-extension boundaries; both data- and complement-side corruption.
    for i in range(256):
        for flash in (0x00, 0x7F, 0x80, 0xFF):
            p = [(0x11 + 5 * j) & 0xFF for j in range(256)]
            c = [~x & 0xFF for x in p]
            c[i] = (c[i] + 1) & 0xFF               # corrupt complement side
            v.append((i, 1, 0, flash, 0x55, p, c))
            p2 = list(p)
            p2[i] = (p2[i] + 1) & 0xFF             # corrupt data side
            v.append((i, 1, 0, flash, 0x55, p2, c))

    # Single corrupt pair, retry 1 (error flag: byte not copied, pair kept).
    for i in range(256):
        p = [(0x33 + 5 * j) & 0xFF for j in range(256)]
        c = [~x & 0xFF for x in p]
        c[i] = (c[i] ^ 0x5A) & 0xFF
        v.append((i, 1, 1, 0x00, 0x77, p, c))

    # Fully corrupt shadow; retry 0 (everything rebuilt from FLASH).  Each
    # vector keeps e2addr+len within the 256-byte EEPROM array (see gen_random:
    # the ROM indexes 0xFFFFC2FE + idx, which beyond idx 0xFF aliases un-arrayed
    # RAM; the harness pins those phantom reads at 0 on both sides).
    p = [(0x10 + 3 * j) & 0xFF for j in range(256)]
    c = [(0xE0 + 5 * j) & 0xFF for j in range(256)]
    for flash in (0x00, 0x80, 0xFF):
        for addr in (0x00, 0x01, 0xFE, 0xFF):
            v.append((addr, 1, 0, flash, 0xAA, p, c))

    return v


def gen_random(rng, n):
    """N random vectors: random 256-byte shadow with ~15% corrupt pairs,
    random e2addr, len 1..32 (clamped so e2addr+len stays inside the 256-byte
    EEPROM array — the ROM reads 0xFFFFC2FE + idx, and beyond idx 0xFF it
    aliases adjacent RAM which the harness pins at 0 on both sides), random
    retry 0/1, random flash byte, random dest pre-fill seed."""
    v = []
    for _ in range(n):
        p = [rng.randrange(256) for _ in range(256)]
        c = []
        for j in range(256):
            if rng.random() < 0.85:
                c.append((~p[j]) & 0xFF)
            else:
                c.append(rng.randrange(256))
        e2addr = rng.randrange(256)
        maxlen = min(32, 256 - e2addr)
        v.append((e2addr, rng.randrange(1, maxlen + 1), rng.randrange(2),
                  rng.randrange(256), rng.randrange(256), p, c))
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
           os.path.join(SAMPLES, 'tests', 'oracle_get_from_e2.c'),
           os.path.join(SAMPLES, 'src', 'rx8_get_from_e2.c'),
           '-lm', '-o', oracle]
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

    # (a) ROM behaviour via the emulator (real bytes @0x39170).
    emu = [run_vector(cpu, e2addr, length, retry, flash, seed, p, c)
           for e2addr, length, retry, flash, seed, p, c in vectors]

    # (b) host C on the same inputs (shadow shipped inline as hex).
    lines = ['e2 %02X %02X %d %02X %02X %s %s'
             % (e2addr, length, retry, flash, seed, bytes(p).hex(),
                bytes(c).hex())
             for e2addr, length, retry, flash, seed, p, c in vectors]
    host = [parse_oracle(l) for l in run_oracle(oracle, lines)]

    # (c) compare the full observable state bit-exactly.
    mismatches = []
    for i, (vec, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            e2addr, length, retry, flash, seed = vec[:5]
            mismatches.append(
                'vec#%d e2addr=%02X len=%d retry=%d flash=%02X seed=%02X '
                'ROM(r0=%02X dest=%s.. prim=%s.. comp=%s..) '
                'C(r0=%02X dest=%s.. prim=%s.. comp=%s..)'
                % (i, e2addr, length, retry, flash, seed,
                   e[0], e[1][:4].hex(), e[2][:4].hex(), e[3][:4].hex(),
                   h[0], h[1][:4].hex(), h[2][:4].hex(), h[3][:4].hex()))
            if len(mismatches) >= 5:
                break

    report('getFromE2', ADDR, n, mismatches, edges=len(gen_edges()))


if __name__ == '__main__':
    main()
