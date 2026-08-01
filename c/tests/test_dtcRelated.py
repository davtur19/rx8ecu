#!/usr/bin/env python3
"""
Verify dtcRelated (0x062002) against the ACTUAL ROM bytes, run in the
SH-2E emulator, over many random RAM states.

The function scans the 21-entry DTC context table at 0xFFFF87D8 (16 bytes
per entry) and appends the 16-bit DTC code of every entry whose "type"
byte (entry+6) matches the requested type selector to a caller-supplied
word array at r6.  The matches are written CONSECUTIVELY (packed:
out[0], out[1], ... in scan order -- r12 = out + 2*running-count).  The entry
whose index equals the current-DTC-index word at 0xFFFF8928 is skipped.
An optional enable gate (r5) checks tableA[code]@0x7E220 (enable==1) or
tableB[code]@0x7E2AC (enable==2) for the value 1.

This test compares the emulator output (r0 = match count, out buffer
contents) against a Python model of the C lift (c/dtcRelated.c) for
500 random DTC table / index / selector states.

Run from repo root:  python3 c/tests/test_dtcRelated.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RE = os.path.join(ROOT, 'tools')
sys.path.insert(0, RE)
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x062002

DTC_TABLE  = 0xFFFF87D8   # 21 entries x 16 bytes
DTC_CUR    = 0xFFFF8928   # word: DTC index being serviced
TABLE_A    = 0x0007E220   # ROM: DTC property byte table
TABLE_B    = 0x0007E2AC   # ROM: DTC enable byte table
OUT_BUF    = 0xFFFFA000   # caller-supplied word array (RAM)
NENT = 21
STRIDE = 16


def rom_byte(rom, a):
    return rom[a] if a < len(rom) else 0


def model(rom, ram, dtype, enable):
    """Python port of c/dtcRelated.c. Returns (count, out_list).
    Note: words in RAM/out are stored big-endian (mov.w semantics)."""
    cur = (ram.get(DTC_CUR, 0) << 8) | ram.get(DTC_CUR + 1, 0)
    count = 0
    out = [0] * NENT
    for i in range(NENT):
        if i == cur:
            continue
        entry = DTC_TABLE + i * STRIDE
        flag = ram.get(entry + 6, 0)
        code = (ram.get(entry, 0) << 8) | ram.get(entry + 1, 0)

        ok = True
        if enable:
            if enable == 1:
                ok = rom_byte(rom, TABLE_A + code) == 1
            elif enable == 2:
                ok = rom_byte(rom, TABLE_B + code) == 1
            else:
                ok = False                # ROM only accepts 0, 1, 2
            if not ok:
                continue

        if dtype == 0x00:   ok = (flag == 0x00)
        elif dtype == 0x60: ok = (1 <= flag <= 0x3F)
        elif dtype == 0x80: ok = ((flag & 0x80) == 0x80)
        elif dtype == 0xC0: ok = (flag == 0xC0)
        elif dtype == 0xC1: ok = (flag == 0xC1)
        elif dtype == 0x50: ok = (flag == 0x50)
        elif dtype == 0xF0: ok = (1 <= flag <= 0x3F) or ((flag & 0x80) == 0x80)
        elif dtype == 0x70: ok = (0x81 <= flag <= 0xBF)
        else:               ok = False
        if ok:
            out[count] = code      # packed: out[0], out[1], ... scan order
            count += 1
    return count, out


def random_state(rng):
    ram = {}
    for i in range(NENT):
        e = DTC_TABLE + i * STRIDE
        ram[e] = rng.randrange(0x100)        # code low
        ram[e + 1] = rng.randrange(0x100)    # code high
        # sprinkle unrelated entry bytes (0x02..0x0F offsets)
        for o in range(2, STRIDE):
            if o == 6:
                ram[e + o] = rng.randrange(0x100)   # type byte
            else:
                ram[e + o] = rng.randrange(0x100)
    cur = rng.randrange(0, NENT)
    ram[DTC_CUR] = (cur >> 8) & 0xFF
    ram[DTC_CUR + 1] = cur & 0xFF
    return ram, cur


def run(cpu, ram, dtype, enable):
    cpu.call(ENTRY, r4=dtype, r5=enable, r6=OUT_BUF, ram=ram)
    count = cpu.r[0]
    out = []
    for i in range(NENT):
        hi = cpu.ram.get(OUT_BUF + 2 * i, 0)
        lo = cpu.ram.get(OUT_BUF + 2 * i + 1, 0)
        out.append((hi << 8) | lo)
    return count, out


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    rng = random.Random(0x60E1D400)

    types = [0x00, 0x60, 0x80, 0xC0, 0xC1, 0x50, 0xF0, 0x70, 0x01, 0xFF]
    enables = [0, 1, 2, 3]

    for it in range(N):
        ram, cur = random_state(rng)
        dtype = rng.choice(types)
        enable = rng.choice(enables)
        try:
            got_cnt, got_out = run(cpu, dict(ram), dtype, enable)
        except Exception as e:
            print("FAIL iter %d (type=0x%02X enable=%d): emulator raised %s: %s"
                  % (it, dtype, enable, type(e).__name__, e))
            sys.exit(1)
        exp_cnt, exp_out = model(rom, ram, dtype, enable)
        if got_cnt != exp_cnt or got_out != exp_out:
            # find first mismatch for a useful message
            for i in range(NENT):
                if got_out[i] != exp_out[i]:
                    print("FAIL iter %d type=0x%02X enable=%d cur=%d entry=%d: "
                          "out 0x%04X expected 0x%04X (count %d vs %d)"
                          % (it, dtype, enable, cur, i, got_out[i], exp_out[i],
                             got_cnt, exp_cnt))
                    sys.exit(1)
            print("FAIL iter %d type=0x%02X enable=%d cur=%d: count %d vs %d"
                  % (it, dtype, enable, cur, got_cnt, exp_cnt))
            sys.exit(1)

    print("OK  dtcRelated @0x%04X (%d random states x 8 type selectors x 4 enable modes)"
          % (ENTRY, N))
    sys.exit(0)


if __name__ == '__main__':
    main()
