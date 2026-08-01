#!/usr/bin/env python3
"""
Verify setRegister_REG_BIT_VAL (0x4BBC) against the ACTUAL ROM bytes, run
in the SH-2E emulator.  This function sets or clears bits in a 16-bit
register given a mask and enable flag.

C signature:
  void setRegister_REG_BIT_VAL(uint16_t *reg, uint16_t mask, int enable)

ROM: set bits:   *reg |= mask
     clear bits: *reg &= ~mask

Run from repo root:  python3 c/tests/test_setRegister_REG_BIT_VAL.py [N]
"""
import os, sys, random, struct

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x4BBC

def ref(reg_val, mask, enable):
    """Pure-Python reference for setRegister_REG_BIT_VAL."""
    if enable:
        return (reg_val | mask) & 0xFFFF
    else:
        return (reg_val & ~mask) & 0xFFFF

def test_setRegister_REG_BIT_VAL(cpu, N):
    """Verify setRegister_REG_BIT_VAL @0x4BBC against Python reference."""
    # We'll use a scratch RAM address to hold the register
    REG_ADDR = 0xFFFF8000
    for _ in range(N):
        reg_val = random.randint(0, 0xFFFF)
        mask    = random.randint(0, 0xFFFF)
        enable  = random.randint(0, 1)
        
        # Set up RAM with initial register value (big-endian)
        ram = {}
        for i in range(2):
            ram[REG_ADDR + i] = (reg_val >> (8 * (1 - i))) & 0xFF
        
        # Call the ROM function
        cpu.call(ENTRY, r4=REG_ADDR, r5=mask, r6=enable, ram=ram)
        
        # Read back the register value from RAM
        result = ((cpu.ram.get(REG_ADDR, 0) << 8) |
                  cpu.ram.get(REG_ADDR + 1, 0))
        
        expected = ref(reg_val, mask, enable)
        if result != expected:
            return (reg_val, mask, enable, result, expected)
    return None

def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    
    err = test_setRegister_REG_BIT_VAL(cpu, N)
    if err:
        reg_val, mask, enable, result, expected = err
        print("FAIL: reg=0x%04X mask=0x%04X enable=%d → result=0x%04X expected=0x%04X" % err)
        sys.exit(1)
    else:
        print("OK  setRegister_REG_BIT_VAL @0x%04X  (%d random inputs)" % (ENTRY, N))
        sys.exit(0)

if __name__ == '__main__':
    main()
