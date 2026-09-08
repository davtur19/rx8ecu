#!/usr/bin/env python3
"""
Verify c/getFaultStatus.c logic against the actual ROM function @0x6743C
by running the ROM bytes in the SH-2E emulator.

The function checks a fault channel index and returns 0/1 status.

Note: The function calls getFaultEvalState @0x67494 as a secondary check.
The emulator will attempt to execute that function too, which may have
its own sub-calls. This test catches emulation crashes as known limitations.

Run from repo root:  python3 c/tests/test_getFaultStatus.py
"""
import os, sys, struct
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM  = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x6743C   # getFaultStatus

FAULT_ENABLE_MASK = 0xFFFFD96C   # uint32_t

rom = open(ROM, 'rb').read()


def ram_u32(base, val):
    """Return dict of 4 byte entries for a big-endian uint32 at base."""
    return {base + i: (val >> (24 - i * 8)) & 0xFF for i in range(4)}


def c_lift(channel, enable_mask):
    """Python version of getFaultStatus logic (primary check only)."""
    FAULT_TABLE_BASE = 0x0007E4DC
    off = (channel & 0xFFFF) * 4
    entry = struct.unpack('>I', rom[FAULT_TABLE_BASE + off: FAULT_TABLE_BASE + off + 4])[0]
    
    # Immediate check: low 16 bits
    if (entry & enable_mask) & 0xFFFF:
        return 1
    # Secondary check (via getFaultEvalState) is not modeled here.
    # The emulated ROM will execute it; if it crashes, that's a known limitation.
    return 0


def main():
    cpu = SH2(rom)
    
    test_channels = [0, 1, 2, 3, 4, 5, 10, 20, 50]
    
    bad = 0
    tested = 0
    for ch in test_channels:
        for mask in [0x00000000, 0x00000001, 0x0000FFFF, 0xFFFF0000, 0xFFFFFFFF]:
            ram_init = ram_u32(FAULT_ENABLE_MASK, mask)
            tested += 1
            
            try:
                cpu.call(ADDR, ram=ram_init, r4=ch)
                emu_result = cpu.r[0] & 0xFF
            except (RuntimeError, NotImplementedError, Exception) as e:
                # Emulation must be honest: an unimplemented opcode means this
                # vector is UNVERIFIED, not silently passing. Count it so the
                # suite fails closed instead of hiding gaps as skips.
                print(f"  FAIL ch={ch} mask=0x{mask:08X}: emu raised {e}")
                bad += 1
                continue
            
            c_result = c_lift(ch, mask)
            
            if emu_result != c_result:
                # Any divergence (including the secondary-eval path the
                # simplified model does not cover) is a hard failure: the
                # suite must be able to fail, never silently PASS.
                print(f"  FAIL ch={ch} mask=0x{mask:08X}: emu={emu_result} c={c_result}")
                bad += 1
    
    print(f"getFaultStatus: tested={tested} channels, {bad} hard failures")
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
