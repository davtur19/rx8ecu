#!/usr/bin/env python3
"""test_E2IntoRAM_0x38F58.py

Differential test for ROM 0x38F58 (60E1D400.bin) — lift c/E2IntoRAM.c.

Runs the ACTUAL ROM bytes of 0x38F58 in tools/sh2emu.py over seeded inputs and
compares the post-call RAM effect + returned r0 against a Python model that
mirrors the C lift (and the verified disassembly) exactly.

Verified disassembly highlights:
   - getSR (0x3920) / setSR (0x3934) : SR not observable -> stubbed rts;nop.
   - SPI retry hook 0xC0A8 polled twice; if both return 1 -> result=1, EARLY
     return (no shadow writes).  Swept with a stub returning 0 (main load path)
     and a stub returning 1 (early-abort path).
   - half_start = e2_addr >> 1 ; end_raw = (length+e2_addr-1) as u32 ;
     t = (end_raw signed < 0) ; half_end = (end_raw + t) >> 1 (u16).
     0xFFFFC502 (w)=half_start ; 0xFFFFC504 (w)=half_end.
   - do-while loop over half (body runs at least once, works while half<=half_end
     because the exit test compares the incremented counter):
       flash  = u32 @ 0x06000000 + ((half & 0xFF) << 16)   [stub mov.l @r4,r0]
       word   = flash & 0xFFFF
       high,low = word>>8, word&0xFF
       byte_idx = (half << 1) & 0xFFFF
       primary[2k]=high; complement[2k]=~high;
       primary[2k+1]=low; complement[2k+1]=~low     (primary=0xFFFFC2FE, compl=0xFFFFC3FE)
   - returns r0 = result (0 normal, 1 retry-abort).

Inputs restricted so the shadow writes stay inside the 256-byte primary region
(index+length <= 256) => no primary/complement aliasing.

Run: python3 c/tests/test_E2IntoROM_0x38F58.py [N]
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, s32

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x38F58
E2_PRI = 0xFFFFC2FE
E2_COM = 0xFFFFC3FE
SCR_START = 0xFFFFC502
SCR_END = 0xFFFFC504


def rtsnop():
    return {0x00: 0x0B, 0x00: 0x09}  # rts; nop


def stub(retry_val):
    s = {}
    for a in (0x3920, 0x3934):
        s[a] = 0x00; s[a + 1] = 0x0B; s[a + 2] = 0x00; s[a + 3] = 0x09
    if retry_val == 0:
        s[0xC0A8] = 0xE0; s[0xC0A8 + 1] = 0x00            # mov #0,r0
    else:
        s[0xC0A8] = 0xE0; s[0xC0A8 + 1] = 0x01            # mov #1,r0
    s[0xC0A8 + 2] = 0x00; s[0xC0A8 + 3] = 0x0B           # rts
    s[0xC0A8 + 4] = 0x00; s[0xC0A8 + 5] = 0x09           # nop
    # flash reader @0xBFCA: mov.l @r4,r0 (read u32 from the image at r4); rts; nop
    s[0xBFCA] = 0x60; s[0xBFCA + 1] = 0x42               # mov.l @r4,r0  (nib 2)
    s[0xBFCA + 2] = 0x00; s[0xBFCA + 3] = 0x0B
    s[0xBFCA + 4] = 0x00; s[0xBFCA + 5] = 0x09
    return s


def model(e2_addr, length, flash):
    """flash: dict {u32_flash_addr: byte}. Returns (retval, writes_dict)."""
    writes = {}
    half_start = (e2_addr & 0xFFFF) >> 1
    end_raw = ((length & 0xFF) + (e2_addr & 0xFFFF) - 1) & 0xFFFFFFFF
    t = 1 if (end_raw - (1 << 32) if end_raw & 0x80000000 else end_raw) < 0 else 0
    half_end = ((end_raw + t) & 0xFFFFFFFF) >> 1
    half_end &= 0xFFFF

    def w(addr, n, v):
        for i in range(n):
            writes[(addr + i) & 0xFFFFFFFF] = (v >> (8 * (n - 1 - i))) & 0xFF

    w(SCR_START, 2, half_start)
    w(SCR_END, 2, half_end)

    half = half_start
    while True:
        flash_addr = 0x06000000 + (((half & 0xFF) << 16) & 0xFFFFFFFF)
        word = flash.get(flash_addr, 0) & 0xFFFF
        high = (word >> 8) & 0xFF
        low = word & 0xFF
        byte_idx = (half << 1) & 0xFFFF
        w(E2_PRI + byte_idx, 1, high)
        w(E2_COM + byte_idx, 1, (~high) & 0xFF)
        w(E2_PRI + byte_idx + 1, 1, low)
        w(E2_COM + byte_idx + 1, 1, (~low) & 0xFF)
        half = (half + 1) & 0xFFFFFFFF
        if half > half_end:
            break
    return 0, writes


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    rng = random.Random(0x38F58)
    total_fails = 0

    def run_case(retry_val, e2_addr, length, flash_words):
        ram = {**stub(retry_val)}
        for k, wd in flash_words.items():
            ram[k] = (wd >> 24) & 0xFF
            ram[k + 1] = (wd >> 16) & 0xFF
            ram[k + 2] = (wd >> 8) & 0xFF
            ram[k + 3] = wd & 0xFF
        input_keys = set(ram.keys())          # stub + flash image: allowed input bytes
        # model
        want_ret, want = model(e2_addr, length, flash_words)
        if retry_val == 1:
            # both retry calls return 1 -> early abort, no shadow writes
            want_ret, want = 1, {}
        cpu.call(ADDR, r4=e2_addr, r5=length, ram=dict(ram))
        got_ret = cpu.r[0] & 0xFF
        bad = []
        # 1) every model-expected write must match the emulator RAM
        for k, e in want.items():
            if cpu.ram.get(k, 0) != e:
                bad.append((k, cpu.ram.get(k, 0), e))
        # 2) no write outside the model output (excluding stub/flash/stack inputs)
        for k in cpu.ram:
            if k in want or k in input_keys:
                continue
            if 0xFFFFDE00 <= k <= 0xFFFFDF00:  # task stack region
                continue
            bad.append((k, cpu.ram.get(k, 0), '<none>'))
        if got_ret != want_ret:
            bad.append(('r0', got_ret, want_ret))
        return bad

    for it in range(N):
        retry_val = rng.choice([0, 1])
        e2_addr = rng.randint(0, 0x80)
        maxlen = 0x100 - e2_addr
        length = rng.randint(1, min(64, maxlen))
        # touched pages (half & 0xFF) for all halves we will access
        half_start = e2_addr >> 1
        end_raw = ((length & 0xFF) + e2_addr - 1) & 0xFFFFFFFF
        t = 1 if (end_raw - (1 << 32) if end_raw & 0x80000000 else end_raw) < 0 else 0
        half_end = ((end_raw + t) & 0xFFFFFFFF) >> 1
        flash_words = {}
        half = half_start
        while True:
            fa = 0x06000000 + ((half & 0xFF) << 16)
            flash_words[fa] = rng.randint(0, 0xFFFF)
            if half > half_end:
                break
            half += 1
        bad = run_case(retry_val, e2_addr, length, flash_words)
        if bad:
            print('MISMATCH iter=%d retry=%d e2_addr=0x%X len=%d: %s' %
                  (it, retry_val, e2_addr, length,
                   {hex(k): (hex(g), hex(e)) for k, g, e in bad[:10]}))
            total_fails += 1
            if total_fails >= 3:
                break

    if total_fails:
        print('%d FAILURE(S) E2IntoRAM' % total_fails)
        sys.exit(1)
    print('OK  0x38F58 E2IntoRAM  (%d inputs)' % N)
    sys.exit(0)


if __name__ == '__main__':
    main()