#!/usr/bin/env python3
"""
Verify loadStatusRegister_ADDR (0x2064) against the ACTUAL ROM bytes, run in the SH-2E
emulator with SR support (SRCPU subclass).

loadStatusRegister_ADDR is an unconditional ldc r4,sr / rts — it writes r4 into the
Status Register with no side effects or conditionals.  Called from 78 sites.

The SRCPU subclass (from test_setSR_getSR.py) adds stc sr,Rn / ldc Rn,SR
support to the base emulator.

Run from repo root:  python3 c/tests/test_loadStatusRegister_ADDR.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

# Reuse SRCPU from the setSR test
from test_setSR_getSR import SRCPU

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x2064

def test_loadStatusRegister_ADDR(cpu, N):
    """Verify loadStatusRegister_ADDR @0x2064 writes r4 to SR."""
    for _ in range(N):
        # Random SR value (keep IPL in valid range, but any 32-bit value works)
        sr_val = random.randint(0, 0xFFFFFFFF)
        # Set CPU SR to something else first
        cpu.sr = 0x000000F0
        # Call loadStatusRegister_ADDR with sr_val
        cpu.call(ENTRY, r4=sr_val)
        # Verify SR was written
        if cpu.sr != (sr_val & 0xFFFFFFFF):
            return ("loadStatusRegister_ADDR", sr_val, cpu.sr)
    return None

def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 50000
    rom = open(ROM, 'rb').read()
    fails = []

    cpu = SRCPU(rom)
    err = test_loadStatusRegister_ADDR(cpu, N)
    if err:
        fails.append(err)
    else:
        print("OK  loadStatusRegister_ADDR @0x%04X  (%d random SR values)" % (ENTRY, N))

    if fails:
        print("\n%d FAILURE(S):" % len(fails))
        for f in fails:
            print("  %s: expected SR=0x%08X, got SR=0x%08X" % f)
        sys.exit(1)
    else:
        print("\nAll tests passed.")
        sys.exit(0)

if __name__ == '__main__':
    main()
