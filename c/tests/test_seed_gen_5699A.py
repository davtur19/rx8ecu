#!/usr/bin/env python3
"""
test_seed_gen_5699A.py — Verify seed_gen @0x05699A against the ACTUAL ROM bytes,
run in the SH-2E emulator.

Semantics (documented in docs/notes/UDS_SECURITY_MAPPING.md §2, verified below
against the ROM disassembly 0x5699A-0x56ABE):

  entry 0x5699A, arg r4 = level.  RAM: seed -> 0xFFFFD211..213, level ->
  0xFFFFD214, state sentinel -> 0xFFFFD20B.

  level == 3  (cmp/eq #0x03 @0x569B6):  r13=r12=r14=0xFF, jump to write-back
    0x56A8C: jsr @0x3920 (getSR), write [D214]=level, [D211..213]=FF FF FF,
    jsr @0x3934 (setSR).  -> seed = FF FF FF (independent of state/counter).

  level != 3  (entropy path 0x569C4..0x56A8A):
    read 32-bit counter @0xFFFFF430 (mov.l @r2,r6), copy to 4 stack bytes
    b0..b3 (little-endian, b0 = low byte), bsr @0x5687A(r4=4) -> returns 0 iff
    byte @0xFFFFD20B == 4.
    - state != 4:  r14 = b2^b0, r12 = b1^b0, r13 = b3^b0
    - state == 4:  r14 = 0x55, r12 = 0xAA, r13 = 0x55
    retry loop max 0x10 (16) on all-0 / all-FF seed -> fallback FF FF FF;
    after 16 retries (17th recompute) forces r14=r12=r13=0xFF.
    write-back as above -> [D211]=r14, [D212]=r12, [D213]=r13, [D214]=level.

Note: 0xFFFFF430 is normal RAM in the emulator -> randomized to exercise the
entropy path.  The byte at 0xFFFFD20B drives which path runs (4 -> fixed,
!= 4 -> XOR).  jsr @0x3920/0x3934 are real ROM and run natively.

Run from repo root:  python3 c/tests/test_seed_gen_5699A.py [N]
"""
import os
import sys
import random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x05699A

COUNTER_ADDR = 0xFFFFF430
STATE_ADDR   = 0xFFFFD20B
SEED_BASE    = 0xFFFFD211   # ..213 (3 bytes)
LEVEL_ADDR   = 0xFFFFD214


def make_ram(counter, state):
    """Build the RAM overlay: counter as a big-endian u32 at 0xFFFFF430 (the
    emulator's mov.l @Rn,Rd reads MSB-first) + sentinel byte."""
    return {
        COUNTER_ADDR + 0: (counter >> 24) & 0xFF,
        COUNTER_ADDR + 1: (counter >> 16) & 0xFF,
        COUNTER_ADDR + 2: (counter >> 8) & 0xFF,
        COUNTER_ADDR + 3: counter & 0xFF,
        STATE_ADDR: state,
    }


def model_seed_gen(level, counter, state):
    """Reference model derived from docs/notes/UDS_SECURITY_MAPPING.md §2 and the
    ROM disassembly 0x5699A-0x56ABE.  Returns the 3 seed bytes (b0,b1,b2) written
    to D211..D213; the level written to D214 is always the (byte-masked) level."""
    if level == 3:
        return (0xFF, 0xFF, 0xFF)

    b0 = counter & 0xFF
    b1 = (counter >> 8) & 0xFF
    b2 = (counter >> 16) & 0xFF
    b3 = (counter >> 24) & 0xFF

    # Loop reads counter (static in the emulator -> same value each retry).
    for attempt in range(1, 17 + 1):          # count stored at [r15], max 16 retries
        if state == 4:
            r14, r12, r13 = 0x55, 0xAA, 0x55
        else:
            r14 = b2 ^ b0
            r12 = b1 ^ b0
            r13 = b3 ^ b0
        if attempt > 16:                       # 17th recompute -> fallback
            return (0xFF, 0xFF, 0xFF)
        # retry when all-zero or all-FF; otherwise accept the seed
        if r14 == 0 and r12 == 0 and r13 == 0:
            continue
        if r14 == 0xFF and r12 == 0xFF and r13 == 0xFF:
            continue
        return (r14, r12, r13)


def run_case(cpu, level, counter, state):
    """Emulate seed_gen with the given inputs; return the observed RAM seed/level
    and output registers."""
    ram = make_ram(counter, state)
    _ = cpu.call(ENTRY, r4=level, ram=ram)
    b0 = cpu.rd(SEED_BASE + 0, 1)
    b1 = cpu.rd(SEED_BASE + 1, 1)
    b2 = cpu.rd(SEED_BASE + 2, 1)
    lvl = cpu.rd(LEVEL_ADDR, 1)
    return b0, b1, b2, lvl, cpu.r[0], cpu.r[1]


def check_case(cpu, level, counter, state, label=""):
    """Compare one emulated case against the model; return error tuple or None."""
    got = run_case(cpu, level, counter, state)
    b0, b1, b2, lvl, r0, r1 = got
    exp = model_seed_gen(level, counter, state)

    if (b0, b1, b2) != exp:
        return ("seed mismatch", label, level, counter, state,
                (b0, b1, b2), exp)
    if lvl != (level & 0xFF):
        return ("level mismatch", label, level, counter, state, lvl, level)
    if r0 != (level & 0xFF):
        # output register r0 mirrors the level written to D214
        return ("r0 mismatch", label, level, counter, state, r0, level)
    if r1 != 0xFFFFD212:
        # r1 holds 0xFFFFD212 (seed byte 1 pointer) on the common write-back
        return ("r1 mismatch", label, level, counter, state, r1, 0xFFFFD212)
    return None


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    rng = random.Random(0x5699A)   # deterministic

    mismatches = 0
    total = 0

    # ---- Directed cases: retry-loop boundaries (seed all-0 / all-FF) ----
    # all-zero seed: 0x00000000 (b all 0), 0xFFFFFFFF (xor of equal bytes -> 0)
    # all-FF seed:   0xFFFFFF00 (b0=0, b1=b2=b3=0xFF -> all 0xFF)
    retry_counters = [0x00000000, 0xFFFFFFFF, 0xFFFFFF00]
    dir_states = [4, 0, 1, 2, 3, 5, 0x7F, 0xFE, 0xFF]
    for level in [0, 1, 2, 4, 5]:
        for st in dir_states:
            for cnt in retry_counters:
                total += 1
                err = check_case(cpu, level, cnt, st, label="directed")
                if err:
                    mismatches += 1
                    print("FAIL %s" % (err,))

    # level == 3 must be FF FF FF regardless of state/counter
    for st in dir_states:
        for cnt in retry_counters + [0x12345678, 0xDEADBEEF]:
            total += 1
            err = check_case(cpu, 3, cnt, st, label="level3")
            if err:
                mismatches += 1
                print("FAIL %s" % (err,))

    # ---- Random randomized stream: all levels, both state classes ----
    for _ in range(N):
        level = rng.randrange(6)               # 0..5 (3 -> fast path, else entropy)
        # state == 4 (fixed) half the time, otherwise any other byte
        if rng.random() < 0.5:
            state = 4
        else:
            state = rng.randrange(256)
            while state == 4:
                state = rng.randrange(256)
        counter = rng.getrandbits(32)         # random 32-bit counter
        # occasionally seed a counter that forces the retry loop
        if rng.random() < 0.02:
            counter = rng.choice(retry_counters)

        total += 1
        err = check_case(cpu, level, counter, state, label="random")
        if err:
            mismatches += 1
            print("FAIL %s" % (err,))

    print("OK  seed_gen_5699A @0x%06X  cases=%d mismatches=%d" % (ENTRY, total, mismatches))
    sys.exit(1 if mismatches else 0)


if __name__ == '__main__':
    main()