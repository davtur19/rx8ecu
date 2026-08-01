#!/usr/bin/env python3
"""
Verify taskEndRoutine (0x3D58) against the ACTUAL ROM bytes in the
SH-2E emulator with SR support.

This function reads/writes kernel structures in RAM at 0xFFFF72B0.
The test sets up a minimal RAM overlay representing the OS control
block and a task state block, and stubs out the called sub-functions.

Run from repo root:  python3 c/tests/test_taskEndRoutine.py
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

# Reuse SRCPU from setSR test
from test_setSR_getSR import SRCPU

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x3D58

# RAM addresses used by the function
OS_CTRL_BASE = 0xFFFF72B0

# Offsets within OS control block
OS_SAVED_SR     = 16   # uint32_t
OS_CURRENT_TASK = 20   # uint32_t (pointer)

# Offsets within task state block
TS_ACTIVE   = 0   # uint8_t
TS_TYPE     = 1   # uint8_t
TS_COUNTER  = 3   # uint8_t
TS_SAVED_SP = 4   # uint32_t

def build_ram_overlay():
    """Build a minimal RAM state for testing taskEndRoutine."""
    # Task state block in a safe scratch area
    TASK_BLOCK = 0xFFFFA000
    # Dummy data for the control block
    PTR1 = 0xFFFFA100  # intermediate pointer
    
    ram = {}
    
    # OS control block at 0xFFFF72B0:
    # +16: saved_sr = 0x000000F0
    for i in range(4):
        ram[OS_CTRL_BASE + OS_SAVED_SR + i] = (0x000000F0 >> (24 - 8 * i)) & 0xFF
    # +20: current_task = TASK_BLOCK
    for i in range(4):
        ram[OS_CTRL_BASE + OS_CURRENT_TASK + i] = (TASK_BLOCK >> (24 - 8 * i)) & 0xFF
    # +8: status (written by function)
    for i in range(4):
        ram[OS_CTRL_BASE + 8 + i] = 0x00
    # +12: result (written by function)
    for i in range(4):
        ram[OS_CTRL_BASE + 12 + i] = 0x00
    
    # Task state block at TASK_BLOCK:
    # +0: active flag (will be cleared by function)
    ram[TASK_BLOCK + TS_ACTIVE] = 0x01
    # +1: type = 3
    ram[TASK_BLOCK + TS_TYPE] = 3
    # +3: refcount (will be incremented)
    ram[TASK_BLOCK + TS_COUNTER] = 0
    # +4: saved_sp / result
    for i in range(4):
        ram[TASK_BLOCK + TS_SAVED_SP + i] = (0xDEADBEEF >> (24 - 8 * i)) & 0xFF
    
    # Flag at 0x4B10 (used by function) - set to 0 to skip task_flag_run_C
    for i in range(4):
        ram[0x4B10 + i] = 0x00
    
    # Flag at 0x4B08 (not used in this path)
    for i in range(4):
        ram[0x4B08 + i] = 0x00
    
    return ram, TASK_BLOCK

def create_stub_rom(rom):
    """Create a ROM overlay with stubs for called sub-functions."""
    s = {}
    # task_flag_run_C (0x35EE) - stub: rts; nop
    s[0x35EE] = 0x00; s[0x35EE + 1] = 0x0B  # rts
    s[0x35EE + 2] = 0x00; s[0x35EE + 3] = 0x09  # nop
    # consistencyCheck (0x3A28) - stub: rts; nop
    s[0x3A28] = 0x00; s[0x3A28 + 1] = 0x0B  # rts
    s[0x3A28 + 2] = 0x00; s[0x3A28 + 3] = 0x09  # nop
    # task_dispatcher (0x3C2A) - stub: rts; nop
    # But this is a jmp, not a call, so we need it to work.
    # Make it do: mov #0,r0; rts; nop
    s[0x3C2A] = 0xE0; s[0x3C2A + 1] = 0x00   # mov #0,r0
    s[0x3C2A + 2] = 0x00; s[0x3C2A + 3] = 0x0B  # rts
    s[0x3C2A + 4] = 0x00; s[0x3C2A + 5] = 0x09  # nop
    return s

def test_taskEndRoutine():
    """Verify taskEndRoutine @0x3D58 modifies RAM as expected."""
    rom = open(ROM, 'rb').read()
    ram_overlay, TASK_BLOCK = build_ram_overlay()
    stubs = create_stub_rom(rom)
    
    # Merge stubs into ram overlay
    for addr, val in stubs.items():
        ram_overlay[addr] = val
    
    cpu = SRCPU(rom)
    
    # Initial checks
    initial_active = ram_overlay.get(TASK_BLOCK + TS_ACTIVE, 0)
    initial_count  = ram_overlay.get(TASK_BLOCK + TS_COUNTER, 0)
    
    # Call the function with the RAM overlay
    cpu.call(ENTRY, ram=ram_overlay)
    
    # The function's final instruction is jmp to dispatcher, which we stubbed
    # to rts, so the call should return.
    
    # Check that active flag was cleared
    active = cpu.ram.get(TASK_BLOCK + TS_ACTIVE, 0xFF)
    assert active == 0, f"Active flag not cleared: got {active}"
    
    # Check that refcount was incremented
    count = cpu.ram.get(TASK_BLOCK + TS_COUNTER, 0xFF)
    assert count == initial_count + 1, f"Refcount not incremented: {count} vs {initial_count + 1}"
    
    # Check that status was set to 0x0100
    status = ((cpu.ram.get(OS_CTRL_BASE + 8, 0) << 24) |
              (cpu.ram.get(OS_CTRL_BASE + 9, 0) << 16) |
              (cpu.ram.get(OS_CTRL_BASE + 10, 0) << 8) |
              cpu.ram.get(OS_CTRL_BASE + 11, 0))
    assert status == 0x0100, f"Status not set: got 0x{status:08X}"
    
    print("OK  taskEndRoutine @0x%04X  (structural RAM verification)" % ENTRY)

def main():
    test_taskEndRoutine()
    print("Passed.")
    sys.exit(0)

if __name__ == '__main__':
    main()
