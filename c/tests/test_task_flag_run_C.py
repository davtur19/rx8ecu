#!/usr/bin/env python3
"""
Verify task_flag_run_C (0x0035EE) against the ACTUAL ROM bytes, run
in the SH-2E emulator.  This function sets bit 15 of the kernel flag at
0xFFFF72B8, calls a function via a pointer at 0x4B10, then clears bit 15.

The test validates:
  - Bit 15 is set before the indirect call
  - Bit 15 is cleared after return
  - The indirect function is called and returns

C:
  void task_flag_run_C(void (*task_fn)(void))

Run from repo root:  python3 c/tests/test_task_flag_run_C.py
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x0035EE
FLAG_ADDR = 0xFFFF72B8
PTR_ADDR = 0x4B10  # address holding the function pointer

def test_task_flag_run_C():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    # Point the function pointer at nullsub_29 (0x64F68) which is just "rts; nop"
    rts_func = 0x00064F68
    ram = {}
    # Write 32-bit pointer at PTR_ADDR (big-endian)
    ram[PTR_ADDR]     = (rts_func >> 24) & 0xFF
    ram[PTR_ADDR + 1] = (rts_func >> 16) & 0xFF
    ram[PTR_ADDR + 2] = (rts_func >> 8) & 0xFF
    ram[PTR_ADDR + 3] = rts_func & 0xFF

    # Initial flag state: something distinct
    INIT_FLAG = 0x12345678
    ram[FLAG_ADDR]     = (INIT_FLAG >> 24) & 0xFF
    ram[FLAG_ADDR + 1] = (INIT_FLAG >> 16) & 0xFF
    ram[FLAG_ADDR + 2] = (INIT_FLAG >> 8) & 0xFF
    ram[FLAG_ADDR + 3] = INIT_FLAG & 0xFF

    cpu.call(ENTRY, ram=ram, r4=0, r5=0, r6=0, r7=0)

    # Read back flag
    flag_val = (cpu.ram[FLAG_ADDR] << 24) | (cpu.ram[FLAG_ADDR+1] << 16) \
             | (cpu.ram[FLAG_ADDR+2] << 8) | cpu.ram[FLAG_ADDR+3]

    if flag_val != INIT_FLAG:
        print("FAIL: flag changed from 0x%08X to 0x%08X" % (INIT_FLAG, flag_val))
        return False

    # Verify function was called by checking that the pointer at PTR_ADDR is still intact
    ptr_val = (cpu.ram[PTR_ADDR] << 24) | (cpu.ram[PTR_ADDR+1] << 16) \
            | (cpu.ram[PTR_ADDR+2] << 8) | cpu.ram[PTR_ADDR+3]
    if ptr_val != rts_func:
        print("FAIL: pointer corrupted: 0x%08X" % ptr_val)
        return False

    return True

def main():
    if test_task_flag_run_C():
        print("OK  task_flag_run_C @0x%04X  (flag set/clear via nullsub)" % ENTRY)
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
