#!/usr/bin/env python3
"""test_eeprom_commit_dispatcher_37000.py

Differential test for ROM 0x37000 (60E1D400.bin) — lift
c/eeprom_commit_dispatcher_37000.c.

Runs the ACTUAL ROM bytes of 0x37000 — including its callee 0x38B5C
(eeprom_write_sched, the SPI EEPROM write-queue scheduler) — in
tools/sh2emu.py over seeded RAM states (the oracle), and compares the full
post-call RAM overlay plus the result register (r5) against a Python
reference model that mirrors the C lift line-for-line.

Callee strategy (see the C lift header): the dispatcher's only side-effecting
callee is 0x38B5C, which sets up the SPI write-queue state (busy flag
0xFFFFC511, index/length words, per-code done flags).  The reference model
calls it through a SECOND emulator instance (cpu2) so its RAM effect comes
from the real ROM bytes — the same bytes the main emulator executes — which
keeps the comparison exact without transcribing 0x38B5C by hand.

Return convention: 0x37000 puts its result in r5 (r0 is 0 in the skip path
while r5 is 1), so the test compares cpu.r[5] & 0xFF, not the emulator's r0
return value.

Run: python3 c/tests/test_eeprom_commit_dispatcher_37000.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x37000           # eeprom_commit_dispatcher
SCHED = 0x38B5C          # eeprom_write_sched(index, len, flag) callee

WQ_FLAG   = 0xFFFFC2D2   # write-queue busy flag (dispatcher input/output)
SCHED_BUSY = 0xFFFFC511  # scheduler busy byte (read by 0x38B5C)

# (index, length) selected by each code byte (see C lift header)
TABLE = {
    0x01: (0x0A, 0x02), 0x02: (0x02, 0x08), 0x03: (0x00, 0x02),
    0x04: (0x0C, 0x06), 0x05: (0x12, 0x02), 0x06: (0x0E, 0x02),
    0x07: (0x16, 0x04), 0x08: (0x14, 0x02), 0x09: (0x0C, 0x08),
    0x0A: (0x1A, 0x04), 0x0B: (0x02, 0x0A), 0x0C: (0x0C, 0x14),
    0x0D: (0x1E, 0x02), 0x0E: (0x0C, 0x02), 0x0F: (0x0E, 0x02),
    0xFF: (0x00, 0x20),
}


def model(cpu2, ram, code):
    """Mirror of eeprom_commit_dispatcher_37000(): returns (result, ram_effect).

    The callee 0x38B5C is executed on cpu2 (the real ROM bytes), so its full
    RAM overlay is captured exactly.
    """
    m = dict(ram)
    result = 1
    if m.get(WQ_FLAG, 0) == 0:
        entry = TABLE.get(code)
        if entry is not None:
            index, length = entry
            ret = cpu2.call(SCHED, r4=index, r5=length, r6=1, ram=m)
            m = dict(cpu2.ram)
            result = ret & 0xFF
            if result == 0:
                m[WQ_FLAG] = 1          # 0x37114..0x37118
    return result, m


def gen_state(rng):
    """Random seeded RAM: the two bytes 0x37000/0x38B5C actually read."""
    return {WQ_FLAG: rng.randint(0, 1), SCHED_BUSY: rng.randint(0, 1)}


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)          # dedicated instance for the 0x38B5C callee
    seeds = (0x37000, 0x38B5C, 0xC2D2, 0x37114, 0x3700E)
    total_fails = 0

    # Deterministic sweep: every code byte with both flag values, both
    # scheduler-busy values -> guarantees every switch case is hit.
    cpu2_dummy = SH2(rom)
    for code in sorted(TABLE) + [0x00, 0x10, 0xFE]:
        for flag in (0, 1):
            for busy in (0, 1):
                ram = {WQ_FLAG: flag, SCHED_BUSY: busy}
                want_ret, want = model(cpu2_dummy, dict(ram), code)
                cpu.call(ADDR, r4=code, ram=dict(ram))
                got_ret = cpu.r[5] & 0xFF
                bad = []
                allk = set(k for k in want if isinstance(k, int)) | set(cpu.ram.keys())
                for k in allk:
                    if 0xFFFFDE00 <= k <= 0xFFFFDF00:
                        continue
                    if cpu.ram.get(k, 0) != want.get(k, 0):
                        bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
                if got_ret != want_ret:
                    bad.append(('r5', got_ret, want_ret))
                if bad:
                    print('SWEEP FAIL code=0x%02X flag=%d busy=%d: %s' %
                          (code, flag, busy,
                           {hex(k): (hex(g), hex(e)) for k, g, e in bad[:12]}))
                    total_fails += 1
                    if total_fails >= 5:
                        sys.exit(1)

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            code = rng.randint(0, 255)
            ram = gen_state(rng)
            want_ret, want = model(cpu2, dict(ram), code)
            try:
                cpu.call(ADDR, r4=code, ram=dict(ram))
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            got_ret = cpu.r[5] & 0xFF
            bad = []
            allk = set(k for k in want if isinstance(k, int)) | set(cpu.ram.keys())
            for k in allk:
                if 0xFFFFDE00 <= k <= 0xFFFFDF00:   # task stack area
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if got_ret != want_ret:
                bad.append(('r5', got_ret, want_ret))
            if bad:
                print('MISMATCH seed=0x%X iter=%d: %s' %
                      (seed, it, {hex(k): (hex(g), hex(e)) for k, g, e in bad[:12]}))
                print('  code=0x%02X flag=%d busy=%d' %
                      (code, ram[WQ_FLAG], ram[SCHED_BUSY]))
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
    print('OK  0x37000 eeprom_commit_dispatcher  (%d random + %d sweep inputs)'
          % (N * len(seeds), 3 * 2 * 2))
    print('\nAll eeprom_commit_dispatcher_37000 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
