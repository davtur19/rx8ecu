#!/usr/bin/env python3
"""
Verify task_execute_by_index (0x3854) against the ACTUAL ROM bytes in the
SH-2E emulator with SR support.

This function reads/writes kernel structures in RAM (task table at 0x4990,
OS control block at 0xFFFF72B0).  The test sets up a minimal RAM overlay
and stubs the called sub-functions.

Run from repo root:  python3 c/tests/test_task_execute_by_index.py
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from test_setSR_getSR import SRCPU

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x3854

# RAM addresses
OS_CTRL_BASE = 0xFFFF72B0
TASK_TABLE   = 0x4990
FLAG_ADDR    = 0x4B10
FLAG2_ADDR   = 0x4B08

def build_ram_overlay():
    """Build minimal OS state for task_execute_by_index."""
    # Task state block (one task)
    TASK_BLOCK = 0xFFFFA000
    
    ram = {}
    
    # OS control block (simplified)
    # +8: status (used by interrupt_priority_dispatch call)
    for i in range(4):
        ram[OS_CTRL_BASE + 8 + i] = 0x00
    # +16: saved_sr
    for i in range(4):
        ram[OS_CTRL_BASE + 16 + i] = (0x000000F0 >> (24 - 8 * i)) & 0xFF
    # +20: current_task (not used in this function)
    for i in range(4):
        ram[OS_CTRL_BASE + 20 + i] = (TASK_BLOCK >> (24 - 8 * i)) & 0xFF
    # +24: state block ptr (used in context save path)
    for i in range(4):
        ram[OS_CTRL_BASE + 24 + i] = 0x00
    
    # Task table entry for index 0 (16 bytes at 0x4990):
    # Entry size = 16 bytes. Each entry:
    #   +0: flags (uint16_t)
    #   +2: priority (uint16_t)
    #   +4: state_ptr (uint32_t)
    #   +8: padding (8 bytes)
    # Task index 0 entry at 0x4990
    TE_BASE = TASK_TABLE
    ram[TE_BASE + 0] = 0x00; ram[TE_BASE + 1] = 0x01  # flags = 1
    ram[TE_BASE + 2] = 0x00; ram[TE_BASE + 3] = 0x05  # priority = 5
    for i in range(4):
        ram[TE_BASE + 4 + i] = (TASK_BLOCK >> (24 - 8 * i)) & 0xFF  # state ptr
    
    # Task state block
    ram[TASK_BLOCK + 0] = 0x01  # active flag
    ram[TASK_BLOCK + 1] = 0x03  # type
    ram[TASK_BLOCK + 2] = 0x00  # reserved
    ram[TASK_BLOCK + 3] = 0x02  # counter (must be non-zero for runnable)
    for i in range(4):
        ram[TASK_BLOCK + 4 + i] = (0x12345678 >> (24 - 8 * i)) & 0xFF  # saved_sp
    
    # Flags
    for i in range(4):
        ram[FLAG_ADDR + i] = 0x00  # flag1 = 0 (skip task_flag_run_C)
        ram[FLAG2_ADDR + i] = 0x00  # flag2 = 0 (skip interrupt dispatch)
    
    return ram, TASK_BLOCK

def create_stub_rom(rom):
    """Create stubs for called sub-functions."""
    s = {}
    # task_execute_helper (0x39BA) - stub: return 0 (success)
    # mov #0,r0; rts; nop
    s[0x39BA] = 0xE0; s[0x39BA + 1] = 0x00
    s[0x39BA + 2] = 0x00; s[0x39BA + 3] = 0x0B
    s[0x39BA + 4] = 0x00; s[0x39BA + 5] = 0x09
    # task_flag_run_C (0x35EE) - stub
    s[0x35EE] = 0x00; s[0x35EE + 1] = 0x0B
    s[0x35EE + 2] = 0x00; s[0x35EE + 3] = 0x09
    # task_full_context_save (0x3BF4) - stub: rts; nop
    s[0x3BF4] = 0x00; s[0x3BF4 + 1] = 0x0B
    s[0x3BF4 + 2] = 0x00; s[0x3BF4 + 3] = 0x09
    # interrupt_priority_dispatch (0x3610) - stub: mov #0,r0; rts; nop
    s[0x3610] = 0xE0; s[0x3610 + 1] = 0x00
    s[0x3610 + 2] = 0x00; s[0x3610 + 3] = 0x0B
    s[0x3610 + 4] = 0x00; s[0x3610 + 5] = 0x09
    return s

def test_task_execute_index_0():
    """Test task_execute_by_index with index 0 (runnable task)."""
    rom = open(ROM, 'rb').read()
    ram_overlay, TASK_BLOCK = build_ram_overlay()
    stubs = create_stub_rom(rom)
    for addr, val in stubs.items():
        ram_overlay[addr] = val
    
    cpu = SRCPU(rom)
    result = cpu.call(ENTRY, r4=0, ram=ram_overlay)
    
    # With our stubs, helper returns 0 => success path => result should be 0
    assert result == 0, f"Expected return 0 (success), got {result}"
    
    # Counter should be decremented from 2 to 1
    counter = cpu.ram.get(TASK_BLOCK + 3, 0)
    assert counter == 1, f"Counter not decremented: got {counter}"
    
    print("OK  task_execute_by_index @0x%04X  (index=0, runnable)" % ENTRY)

def test_task_execute_index_not_runnable():
    """Test task_execute_by_index with a task that has counter=0."""
    rom = open(ROM, 'rb').read()
    ram_overlay, TASK_BLOCK = build_ram_overlay()
    stubs = create_stub_rom(rom)
    for addr, val in stubs.items():
        ram_overlay[addr] = val
    
    # Set counter to 0 to make task not runnable
    ram_overlay[TASK_BLOCK + 3] = 0x00
    
    cpu = SRCPU(rom)
    result = cpu.call(ENTRY, r4=0, ram=ram_overlay)
    
    # Should return 4 (ERROR: not runnable)
    assert result == 4, f"Expected return 4 (not runnable), got {result}"
    
    print("OK  task_execute_by_index @0x%04X  (index=0, not runnable → ret=4)" % ENTRY)

def main():
    test_task_execute_index_0()
    test_task_execute_index_not_runnable()
    print("Passed.")
    sys.exit(0)

if __name__ == '__main__':
    main()
