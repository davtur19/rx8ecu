#!/usr/bin/env python3
"""
Verify the dispatch logic of dtc_handler_610FA (0x0610FA) against the
ACTUAL ROM bytes, run in the SH-2E emulator.

The function reads the current DTC index (word @ 0xFFFF8928) and indexes
the DTC handler byte-code opcode table at 0xFFFF87DE (16-byte stride,
first byte of the entry = opcode).  If the opcode is 0x50 or 0x00 the
service chain runs: can_encode_handler_62FAC(8), obd_service_handler_64258()
(which marks the "pending" entry: byte entry+7 = 1, entry+8 = 7, and bumps
the pending counter at entry+0x32), then tail-calls obd_service_handler_63312().
Any other opcode returns immediately with no side effects.

Test cases (per random entry index):
  opcode 0x00 / 0x50  -> entry+7 == 1, entry+8 == 7, entry+0x32 changed
  opcode 0x01 / 0x02  -> no RAM writes at all
The 0xFFFF87D0 dispatch flag is forced to 0 so the 63312 tail-call stays
inert; the 0xFFFF8D74 entry selector word is forced to 0 so the marker
entry is 0xFFFF8930.

Run from repo root:  python3 c/tests/test_dtc_handler_610FA.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RE = os.path.join(ROOT, 'tools')
sys.path.insert(0, RE)
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x0610FA

CUR_IDX   = 0xFFFF8928   # word: current DTC index
OPCODES   = 0xFFFF87DE   # byte: handler byte-code opcodes (stride 16)
DISP_FLAG = 0xFFFF87D0   # byte: 63312 dispatch flag (0 = inert)
SEL_WORD  = 0xFFFF8D74   # word: 64258 entry selector (0 = entry 0xFFFF8930)
SVC_BASE  = 0xFFFF8930   # base of 64258 service-entry array (stride 0x34)
WATCH     = None          # set per iteration (marker bytes)


def snapshot(ram, addrs):
    return {a: ram.get(a, -1) for a in addrs}


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    rng = random.Random(0x610FA)

    for it in range(N):
        idx = rng.randrange(0, 21)
        opcode = rng.choice([0x00, 0x50, 0x01, 0x02, 0x03, 0xFF])

        ram = {DISP_FLAG: 0, SEL_WORD: 0, SEL_WORD + 1: 0}
        ram[CUR_IDX] = (idx >> 8) & 0xFF
        ram[CUR_IDX + 1] = idx & 0xFF
        # randomize all opcode bytes (so only the target entry matters)
        for e in range(21):
            ram[OPCODES + e * 16] = rng.randrange(0x100)
        ram[OPCODES + idx * 16] = opcode

        marker = SVC_BASE + 0x34 * 0
        watch = [marker + 7, marker + 8, marker + 0x32]
        before = snapshot(ram, watch)

        try:
            cpu.call(ENTRY, ram=dict(ram))
        except Exception as e:
            print("FAIL iter %d opcode=0x%02X idx=%d: emulator raised %s: %s"
                  % (it, opcode, idx, type(e).__name__, e))
            sys.exit(1)

        after = snapshot(cpu.ram, watch)
        if opcode in (0x00, 0x50):
            if after[marker + 7] != 1 or after[marker + 8] != 7:
                print("FAIL iter %d opcode=0x%02X idx=%d: expected pending marker "
                      "(+7=1,+8=7) got (+7=0x%02X,+8=0x%02X)"
                      % (it, opcode, idx, after[marker + 7], after[marker + 8]))
                sys.exit(1)
            if after[marker + 0x32] == before[marker + 0x32]:
                print("FAIL iter %d opcode=0x%02X idx=%d: pending counter +0x32 "
                      "unchanged (0x%02X)"
                      % (it, opcode, idx, before[marker + 0x32]))
                sys.exit(1)
        else:
            if after != before:
                diff = [a for a in watch if after[a] != before[a]]
                print("FAIL iter %d opcode=0x%02X idx=%d: no writes expected, "
                      "changed %s" % (it, opcode, idx, [hex(a) for a in diff]))
                sys.exit(1)

    print("OK  dtc_handler_610FA @0x%04X dispatch (%d random states; opcode 0x00/0x50 -> chain, else inert)"
          % (ENTRY, N))
    sys.exit(0)


if __name__ == '__main__':
    main()
