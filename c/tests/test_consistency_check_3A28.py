#!/usr/bin/env python3
"""test_consistency_check_3A28.py

Differential test for ROM 0x3A28 (60E1D400.bin) — lift c/consistencyCheck.c.

Runs the ACTUAL ROM bytes of 0x3A28 in tools/sh2emu.py over seeded random RAM
states (the oracle) and compares the post-call RAM overlay + return value
against a Python reference model that mirrors the C lift / disassembly.

Confirmed semantics from the disassembly (0x3A28..0x3AA2, 60E1D400):
  * r4 = exception control block (ctrl), r5 = exception number (byte).
  * table_ptr = u32@(ctrl+0x20); entry = table_ptr + s8(exc)*8.
  * buf = u32@(entry+4); c0 = u16@buf; c1 = u16@(buf+2).
  * Path A (c0 == c1): buf[0] = 0xFFFF; flags byte @(0xFFFF72E0 + (s8(exc)>>3))
    &= ROM-mask @(0x3D50 + (exc&7)); then if ctrl[0] != (exc&0xFF) -> ret 0,
    else call handleHUDIException @0x3C80 (stubbed, no RAM effect) -> ret 1.
  * Path B (c0 != c1): if c0 == u16@(entry+2): buf[0] = u16@entry, else
    buf[0] = (c0+1)&0xFFFF; then if ctrl[0] != (exc&0xFF) -> ret 0, else
    u16@(ctrl+6) = u16@(0xFFFF7234 + buf[0]*2) -> ret 1.

Run: python3 c/tests/test_consistency_check_3A28.py [N]
     (N = random inputs per seed; default 5000 -> 25000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, s8

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x3A28
ROMLEN = 0x80000
MASK = 0xFFFFFFFF

# ROM literal / table constants (verified from 60E1D400.bin)
FLAGS_BASE = 0xFFFF72E0          # pending exception flags
ERROR_TABLE = 0xFFFF7234         # u16 error-code table (word index)
MASK_TABLE = 0x3D50              # 8 one-hot bit-clear masks in ROM
# masks read from ROM (0xFE 0xFD 0xFB 0xF7 0xEF 0xDF 0xBF 0x7F) - verified bytes

# ---- fixed RAM regions (>= 0x80000: fully overlay-owned, no ROM fallback) ----
TABLE = 0x00100000               # exception table base (entry = table + s8(exc)*8)
CTRL_BASE = 0x00200000           # control-block region
BUF_BASE = 0x00300000            # counter-buffer region


def rb(m, a, rom):
    a &= MASK
    v = m.get(a)
    if v is not None:
        return v
    return rom[a] if a < ROMLEN else 0


def rd(m, a, n, rom):
    v = 0
    for i in range(n):
        v = (v << 8) | rb(m, a + i, rom)
    return v


def wr(m, a, n, v):
    for i in range(n):
        m[(a + i) & MASK] = (v >> (8 * (n - 1 - i))) & 0xFF


def ref(ram, rom, ctrl, exc):
    """Line-for-line mirror of consistencyCheck() (C lift / disasm verified)."""
    m = dict(ram)
    exc_s = s8(exc)                        # sign-extended exception number
    table = rd(m, ctrl + 0x20, 4, rom)
    entry = (table + (exc_s * 8)) & MASK   # 32-bit wrap for negative exc
    buf = rd(m, entry + 4, 4, rom)
    c0 = rd(m, buf, 2, rom)
    c1 = rd(m, buf + 2, 2, rom)

    if c0 == c1:                           # Path A
        wr(m, buf, 2, 0xFFFF)
        faddr = (FLAGS_BASE + (exc_s >> 3)) & MASK   # shar x3 on sign-extended
        mask = rom[(MASK_TABLE + (exc & 7)) & 0xFFFFFFFF] if (MASK_TABLE + (exc & 7)) < ROMLEN else 0
        wr(m, faddr, 1, rb(m, faddr, rom) & mask)
        if (rd(m, ctrl, 1, rom) & 0xFF) != (exc & 0xFF):
            return m, 0
        return m, 1                        # handler stub has no RAM effect

    # Path B
    e0 = rd(m, entry, 2, rom)
    e1 = rd(m, entry + 2, 2, rom)
    if c0 == e1:
        wr(m, buf, 2, e0)
    else:
        wr(m, buf, 2, (c0 + 1) & 0xFFFF)
    if (rd(m, ctrl, 1, rom) & 0xFF) != (exc & 0xFF):
        return m, 0
    wr(m, ctrl + 6, 2, rd(m, ERROR_TABLE + rd(m, buf, 2, rom) * 2, 2, rom))
    return m, 1


def gen_state(rng):
    """Seeded random environment.  Every memory read the function can make is
    pre-defined in the overlay, so the oracle and the model read identically."""
    ctrl = CTRL_BASE + ((rng.getrandbits(10)) << 4)          # 0x00200000..0x0020FF00
    buf = BUF_BASE + ((rng.getrandbits(10)) << 4)            # 0x00300000..0x0030FF00
    ram = {}

    # control block region: random junk, then the 3 live fields
    for i in range(0x40):
        ram[ctrl + i] = rng.getrandbits(8)
    ram[ctrl] = rng.getrandbits(8)                           # current exception
    ram[ctrl + 6] = rng.getrandbits(8)                       # error-code out (hi)
    ram[ctrl + 7] = rng.getrandbits(8)                       # error-code out (lo)
    for i in range(4):
        ram[ctrl + 0x20 + i] = (TABLE >> (24 - 8 * i)) & 0xFF

    # exception table region incl. the s8 wrap window (±1024 bytes)
    for a in range(TABLE - 0x2000, TABLE + 0x2000):
        ram[a] = rng.getrandbits(8)
    entry = (TABLE + (s8(rng.getrandbits(8)) * 8)) & MASK
    ram[entry] = rng.getrandbits(8); ram[entry + 1] = rng.getrandbits(8)     # e0
    ram[entry + 2] = rng.getrandbits(8); ram[entry + 3] = rng.getrandbits(8) # e1
    for i in range(4):
        ram[entry + 4 + i] = (buf >> (24 - 8 * i)) & 0xFF

    # counter buffer
    for i in range(8):
        ram[buf + i] = rng.getrandbits(8)
    ram[buf] = rng.getrandbits(8); ram[buf + 1] = rng.getrandbits(8)         # c0
    ram[buf + 2] = rng.getrandbits(8); ram[buf + 3] = rng.getrandbits(8)     # c1

    # pending-flag window (covers all s8(exc)>>3 offsets for exc 0..0xFF)
    for a in range(0xFFFF72C0, 0xFFFF7300):
        ram[a] = rng.getrandbits(8)

    # error-code table (word index -> covers most in-range lookups; wrapped
    # indexes fall back to ROM/0 identically in oracle and model)
    for i in range(0x200):
        ram[ERROR_TABLE + 2 * i] = rng.getrandbits(8)
        ram[ERROR_TABLE + 2 * i + 1] = rng.getrandbits(8)

    # handleHUDIException stub @0x3C80: mov #0,r0 ; rts ; nop
    ram[0x3C80] = 0xE0; ram[0x3C81] = 0x00
    ram[0x3C82] = 0x00; ram[0x3C83] = 0x0B
    ram[0x3C84] = 0x00; ram[0x3C85] = 0x09

    exc = rng.getrandbits(8)
    return ram, ctrl, exc


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x3A28, 0x3D50, 0x7234, 0x72E0, 0x3C80)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram, ctrl, exc = gen_state(rng)
            want, want_ret = ref(ram, rom, ctrl, exc)
            try:
                got_ret = cpu.call(ADDR, r4=ctrl, r5=exc, ram=ram)
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            got = cpu.ram
            if got_ret != want_ret:
                print('RET MISMATCH seed=0x%X iter=%d exc=%02X want=%d got=%d'
                      % (seed, it, exc, want_ret, got_ret))
                fails += 1
                if fails >= 3:
                    break
                continue
            bad = []
            for k in set(k for k in want if isinstance(k, int)) | set(got.keys()):
                if 0xFFFFDE00 <= k <= 0xFFFFDF00:      # task stack area
                    continue
                if got.get(k, 0) != want.get(k, 0):
                    bad.append((k, got.get(k, 0), want.get(k, 0)))
            if bad:
                print('MISMATCH seed=0x%X iter=%d exc=%02X: %s' %
                      (seed, it, exc,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:12]}))
                fails += 1
                if fails >= 3:
                    break
        print('  seed 0x%X: %d inputs, fails=%d' % (seed, N, fails))
        total_fails += fails
        if total_fails:
            break

    if total_fails:
        print('\n%d FAILURE(S)' % total_fails)
        sys.exit(1)
    print('OK  0x3A28 consistencyCheck  (%d random inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    sys.exit(0)


if __name__ == '__main__':
    main()
