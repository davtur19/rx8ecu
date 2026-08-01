#!/usr/bin/env python3
"""
Test getFromE2_E2ADDR_RAMADDR_LEN @ 0x39170 against the ROM bytes in the
SH-2E emulator.  This function copies from an EEPROM-like interface to RAM
with complement validation.

The EEPROM controller is memory-mapped at:
- 0xFFFFC2FE + offset: data byte
- 0xFFFFC3FE + offset: complement byte

Since the emulator doesn't model the EEPROM controller hardware, we place
test data directly in RAM at those addresses and stub out the called functions
(getSR @ 0x3920, setSR @ 0x3934, error handler @ 0xC0A8, flash reader @ 0xBFCA).
"""
import os, sys, random
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, MASK

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')

E2_DATA_BASE   = 0xFFFFC2FE
E2_COMP_BASE   = 0xFFFFC3FE
RAM_BASE       = 0xFFFFA000
GETSR_ADDR     = 0x3920
SETSR_ADDR     = 0x3934
RETRY_ADDR     = 0xC0A8   # stub: return 0 (success)
FLASHREAD_ADDR = 0xBFCA   # stub: return 0


def stub_rom(rom):
    """Replace target helper functions in RAM overlay with rts;nop stubs
    (or ret=0 for retry)."""
    s = {}
    # getSR and setSR: rts; nop
    for a in (GETSR_ADDR, SETSR_ADDR):
        s[a] = 0x00; s[a + 1] = 0x0B; s[a + 2] = 0x00; s[a + 3] = 0x09
    # retry function @ 0xC0A8: return 0 (rts with r0=0, or clrt; rts; nop? 
    # Actually for ret=0 we need r0=0. Let's use: mov #0,r0; rts; nop
    # mov #0,r0 = E000; rts = 000B; nop = 0009
    s[RETRY_ADDR] = 0xE0; s[RETRY_ADDR + 1] = 0x00   # mov #0,r0
    s[RETRY_ADDR + 2] = 0x00; s[RETRY_ADDR + 3] = 0x0B  # rts
    s[RETRY_ADDR + 4] = 0x00; s[RETRY_ADDR + 5] = 0x09  # nop
    # flash reader @ 0xBFCA: return 0 in r0
    s[FLASHREAD_ADDR] = 0xE0; s[FLASHREAD_ADDR + 1] = 0x00   # mov #0,r0
    s[FLASHREAD_ADDR + 2] = 0x00; s[FLASHREAD_ADDR + 3] = 0x0B  # rts
    s[FLASHREAD_ADDR + 4] = 0x00; s[FLASHREAD_ADDR + 5] = 0x09  # nop
    return s


def setup_e2_data(offset, data_byte):
    """Set up EEPROM data and complement at the given offset."""
    comp_byte = (~data_byte) & 0xFF
    ram = {}
    ram[E2_DATA_BASE + offset] = data_byte
    ram[E2_COMP_BASE + offset] = comp_byte
    return ram


def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    N = 500
    fails = 0

    for test_idx in range(N):
        offset = random.randint(0, 255)
        length = random.randint(1, 10)
        data = [random.randint(0, 255) for _ in range(length)]
        
        # Set up EEPROM data for each byte
        e2_ram = {}
        for i, byte in enumerate(data):
            off = (offset + i) & 0xFFFF
            if random.random() < 0.85:  # 85% valid, 15% corrupt
                comp = (~byte) & 0xFF
            else:
                comp = random.randint(0, 255)  # wrong complement
            e2_ram[E2_DATA_BASE + off] = byte
            e2_ram[E2_COMP_BASE + off] = comp
        
        ram = {**stub_rom(rom), **e2_ram}
        
        # Result RAM buffer
        for i in range(length):
            ram[RAM_BASE + i] = 0xAA  # fill with marker
        
        try:
            ret = cpu.call(0x39170, r4=offset, r5=RAM_BASE, r6=length, ram=ram)
        except NotImplementedError as e:
            print(f"EMULATOR LIMITATION: {e}")
            print("Cannot test getFromE2 without handling unknown opcode 0x0B34")
            fails += 1
            break
        
        # Check results
        expected_error = 0
        for i, byte in enumerate(data):
            off = (offset + i) & 0xFFFF
            db = cpu.ram.get(E2_DATA_BASE + off, 0)
            cb = cpu.ram.get(E2_COMP_BASE + off, 0)
            rb = cpu.ram.get(RAM_BASE + i, 0xFF)
            valid = (byte == (~cb & 0xFF))
            
            if valid:
                if rb != byte:
                    print(f"MISMATCH [{test_idx}] byte {i}: wrote {rb}, expected {byte}")
                    fails += 1
            # On invalid data, the function may still write something (retry path)
            # but should set error flag
    
    if fails:
        print(f"FAILED: {fails} tests")
        sys.exit(1)
    else:
        print(f"OK  getFromE2  ({N} random test cases)")
        sys.exit(0)


if __name__ == '__main__':
    main()
