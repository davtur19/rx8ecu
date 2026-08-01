#!/usr/bin/env python3
"""
Verify dtc_code_set (0x046780) and dtc_code_clear (0x0467AA) against the
ACTUAL ROM bytes, run in the SH-2E emulator, over many random RAM states.

Checksum convention (backup-RAM fault area): every byte is stored with its
bitwise complement in the adjacent byte.  The reader
readValue_8bit_ADDRESS_VAL (0x3ED3C) returns byte[addr] when
byte[addr] == ~byte[addr+1], else the passed-in default (1 for
dtc_code_set).  The writer updateMemoryAtAddress_8bit_ADDR_VAL (0x3EE58)
stores val<<8|(~val&0xFF) as a 16-bit word at the address.

  dtc_code_set:  if readValue(F8788, def=1) == 1, write 0 to 0xFFFF875C
                 and 0xFFFF875E (checksum-encoded: 0x00 0xFF pairs).
  dtc_code_clear: unconditional write of 0 to both words.

Model + emulator must agree on the final bytes of 0xFFFF875C..0xFFFF875F
and the read-back of the flag pair for 500 random states each.

Run from repo root:  python3 c/tests/test_dtc_code_set_clear.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RE = os.path.join(ROOT, 'tools')
sys.path.insert(0, RE)
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')

W0 = 0xFFFF875C   # DTC state word 0
W1 = 0xFFFF875E   # DTC state word 1
FL = 0xFFFF8788   # DTC-present flag byte (checksummed pair FL, FL+1)

WRITES = [W0, W0 + 1, W1, W1 + 1]


def model(ram, do_gate):
    """Python port of the C lift. Returns dict of final bytes at WRITES."""
    out = dict(ram)
    valid = out.get(FL, 0) == ((~out.get(FL + 1, 0)) & 0xFF)
    val = out.get(FL, 0) if valid else 1
    if (not do_gate) or val == 1:
        for a in WRITES:
            out[a] = 0 if (a in (W0, W1)) else 0xFF
    return out


def random_state(rng):
    ram = {}
    for a in WRITES + [FL, FL + 1]:
        ram[a] = rng.randrange(0x100)
    return ram


def check(cpu, entry, ram, do_gate, label, it, N):
    cpu.call(entry, ram=dict(ram))
    exp = model(ram, do_gate)
    for a in WRITES:
        got = cpu.ram.get(a, -1)
        if got != exp[a]:
            print("FAIL %s iter %d @0x%04X: got 0x%02X expected 0x%02X (ram=%s)"
                  % (label, it, a, got, exp[a],
                     {hex(k): hex(v) for k, v in sorted(ram.items())}))
            return False
    return True


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    rng = random.Random(0x46780)

    for it in range(N):
        ram = random_state(rng)
        if not check(cpu, 0x046780, ram, True, 'dtc_code_set', it, N):
            sys.exit(1)
        if not check(cpu, 0x0467AA, ram, False, 'dtc_code_clear', it, N):
            sys.exit(1)

    print("OK  dtc_code_set (0x046780) / dtc_code_clear (0x0467AA) (%d random states)"
          % N)
    sys.exit(0)


if __name__ == '__main__':
    main()
