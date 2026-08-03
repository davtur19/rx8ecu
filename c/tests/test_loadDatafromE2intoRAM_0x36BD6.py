#!/usr/bin/env python3
"""test_loadDatafromE2intoRAM_0x36BD6.py

Differential test for ROM 0x36BD6 (60E1D400.bin) — lift c/loadDatafromE2intoRAM.c.

The function is a boot stub whose entire body is:
     mov  #0x20,r5 ; mov.l 0x36C18,r3 ; sts.l pr,@-r15 ; jsr @r3 ; mov #0x00,r4
   -> calls E2IntoRAM(0, 32)  (r4=0, r5=32) and returns.

The test runs the ACTUAL ROM bytes of 0x36BD6 in tools/sh2emu.py (with the same
stub set as test_E2IntoRAM_0x38F58) and compares the RAM effect + r0 against the
model for E2IntoRAM(0, 32) — i.e. the reference is the independently-tested
E2IntoRAM semantics reproduced here in Python.

Run: python3 c/tests/test_loadDatafromE2intoRAM_0x36BD6.py [N]
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x36BD6
E2_PRI = 0xFFFFC2FE
E2_COM = 0xFFFFC3FE
SCR_START = 0xFFFFC502
SCR_END = 0xFFFFC504
FLASH_BASE = 0x06000000


def stub(retry_val):
    s = {}
    for a in (0x3920, 0x3934):
        s[a] = 0x00; s[a + 1] = 0x0B; s[a + 2] = 0x00; s[a + 3] = 0x09
    s[0xC0A8] = 0xE0; s[0xC0A8 + 1] = 0x00
    s[0xC0A8 + 2] = 0x00; s[0xC0A8 + 3] = 0x0B
    s[0xC0A8 + 4] = 0x00; s[0xC0A8 + 5] = 0x09
    s[0xBFCA] = 0x60; s[0xBFCA + 1] = 0x42
    s[0xBFCA + 2] = 0x00; s[0xBFCA + 3] = 0x0B
    s[0xBFCA + 4] = 0x00; s[0xBFCA + 5] = 0x09
    return s


def e2intoram_model(e2_addr, length, flash):
    """Mirror of E2IntoRAM(0,32) main path (retry stub returns 0)."""
    writes = {}
    half_start = (e2_addr & 0xFFFF) >> 1
    end_raw = ((length & 0xFF) + (e2_addr & 0xFFFF) - 1) & 0xFFFFFFFF
    t = 1 if (end_raw - (1 << 32) if end_raw & 0x80000000 else end_raw) < 0 else 0
    half_end = (((end_raw + t) & 0xFFFFFFFF) >> 1) & 0xFFFF

    def w(addr, n, v):
        for i in range(n):
            writes[(addr + i) & 0xFFFFFFFF] = (v >> (8 * (n - 1 - i))) & 0xFF

    w(SCR_START, 2, half_start)
    w(SCR_END, 2, half_end)
    half = half_start
    while True:
        word = flash.get(FLASH_BASE + ((half & 0xFF) << 16), 0) & 0xFFFF
        high, low = (word >> 8) & 0xFF, word & 0xFF
        b = (half << 1) & 0xFFFF
        w(E2_PRI + b, 1, high)
        w(E2_COM + b, 1, (~high) & 0xFF)
        w(E2_PRI + b + 1, 1, low)
        w(E2_COM + b + 1, 1, (~low) & 0xFF)
        half = (half + 1) & 0xFFFFFFFF
        if half > half_end:
            break
    return 0, writes


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    rng = random.Random(0x36BD6)
    fails = 0

    for it in range(N):
        flash = {}
        for page in range(16):              # E2IntoRAM(0,32) touches halves 0..15 -> pages 0..15
            flash[FLASH_BASE + (page << 16)] = rng.randint(0, 0xFFFF)
        ram = {**stub(0)}
        for k, wd in flash.items():
            ram[k] = (wd >> 24) & 0xFF
            ram[k + 1] = (wd >> 16) & 0xFF
            ram[k + 2] = (wd >> 8) & 0xFF
            ram[k + 3] = wd & 0xFF
        input_keys = set(ram.keys())
        want_ret, want = e2intoram_model(0, 32, flash)
        cpu.call(ADDR, ram=dict(ram))
        got_ret = cpu.r[0] & 0xFF
        bad = []
        for k, e in want.items():
            if cpu.ram.get(k, 0) != e:
                bad.append((k, cpu.ram.get(k, 0), e))
        for k in cpu.ram:
            if k in want or k in input_keys:
                continue
            if 0xFFFFDE00 <= k <= 0xFFFFDF00:
                continue
            bad.append((k, cpu.ram.get(k, 0), '<none>'))
        if got_ret != want_ret:
            bad.append(('r0', got_ret, want_ret))
        if bad:
            print('MISMATCH iter=%d: %s' %
                  (it, {hex(k): (hex(g), hex(e)) for k, g, e in bad[:10]}))
            fails += 1
            if fails >= 3:
                break

    if fails:
        print('%d FAILURE(S) loadDatafromE2intoRAM' % fails)
        sys.exit(1)
    print('OK  0x36BD6 loadDatafromE2intoRAM  (%d inputs)' % N)
    sys.exit(0)


if __name__ == '__main__':
    main()