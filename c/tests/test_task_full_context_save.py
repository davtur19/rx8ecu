#!/usr/bin/env python3
"""
Verify task_full_context_save (0x3BF4) against the ACTUAL ROM bytes.

This function saves the full CPU context during RTOS task switching.
It pushes all callee-save registers to the stack, conditionally saves
FPU registers, then branches to the scheduler dispatch.

Run: python3 c/tests/test_task_full_context_save.py
"""

import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x3BF4


def setup_environment(rom, task_type=1):
    """Build RAM environment for testing task_full_context_save.
    
    Returns (ram, tcb_addr, task_desc_addr, status_addr, expected_saved_sp).
    """
    ram = {}
    tcb = 0x4000
    task_desc = 0x5000
    status_addr = 0x6000

    # Task descriptor memory layout:
    #   [0]:   task type (1 byte)
    #   [4-7]: pointer to status byte (4 bytes, big-endian)
    ram[task_desc] = task_type
    for i in range(4):
        ram[task_desc + 4 + i] = (status_addr >> (24 - i * 8)) & 0xFF

    # Status byte initially 0
    ram[status_addr] = 0

    # Scheduler dispatch stub at 0x3C68:
    #   rts           (0x000B) — jump to PR (= SENT = 0xEEEE0000)
    #   nop           (0x0009) — delay slot
    ram[0x3C68] = 0x00;
    ram[0x3C68 + 1] = 0x0B
    ram[0x3C68 + 2] = 0x00;
    ram[0x3C68 + 3] = 0x09

    # Default SP in call() = 0xFFFFDF00
    # Stack pushes (all 4 bytes each):
    #   1. R5    @-R15   0xFFFFDEFC  (mov.l R5,@-R15)
    #   2. PR    @-R15   0xFFFFDEF8  (sts.l pr,@-R15)
    #   3. alloc #-4     0xFFFFDEF4  (add #0xFC,R15)
    #   4. R8    @-R15   0xFFFFDEF0  (mov.l R8,@-R15)
    #   5. R9    @-R15   0xFFFFDEEC  (mov.l R9,@-R15)
    #   6. R10   @-R15   0xFFFFDEE8  (mov.l R10,@-R15)
    #   7. R11   @-R15   0xFFFFDEE4  (mov.l R11,@-R15)
    #   8. R12   @-R15   0xFFFFDEE0  (mov.l R12,@-R15)
    #   9. GBR   @-R15   0xFFFFDEDC  (stc.l gbr,@-R15)
    #  10. R13   @-R15   0xFFFFDED8  (mov.l R13,@-R15)
    #  11. MACH  @-R15   0xFFFFDED4  (sts.l mach,@-R15)
    #  12. R14   @-R15   0xFFFFDED0  (mov.l R14,@-R15)
    #  13. MACL  @-R15   0xFFFFDECC  (sts.l macl,@-R15)  ← saved_sp for non-FPU
    #
    # Total: 13 * 4 = 52 bytes, saved_sp = 0xFFFFDF00 - 52 = 0xFFFFDECC
    # For FPU task (type=4), additional pushes:
    #  14. FR12  @-R15   0xFFFFDEC8  (fmov.s fr12,@-r15)
    #  15. FR13  @-R15   0xFFFFDEC4  (fmov.s fr13,@-r15)
    #  16. FR14  @-R15   0xFFFFDEC0  (fmov.s fr14,@-r15)
    #  17. FR15  @-R15   0xFFFFDEBC  (fmov.s fr15,@-r15)  ← saved_sp for FPU
    #
    # Total: 17 * 4 = 68 bytes, saved_sp = 0xFFFFDF00 - 68 = 0xFFFFDEBC

    non_fpu_saved_sp = (0xFFFFDF00 - 52) & 0xFFFFFFFF
    fpu_saved_sp = (0xFFFFDF00 - 68) & 0xFFFFFFFF
    expected = fpu_saved_sp if task_type == 4 else non_fpu_saved_sp

    return ram, tcb, task_desc, status_addr, expected


def test_context_save_non_fpu():
    """Verify non-FPU task: status set, SP saved, no FPU saves."""
    rom = open(ROM, 'rb').read()
    ram, tcb, task_desc, status_addr, exp_sp = \
        setup_environment(rom, task_type=1)

    cpu = SH2(rom)
    cpu.call(ENTRY, r4=tcb, r6=task_desc, ram=ram)

    # Status must be 4 (scheduled)
    assert cpu.rd(status_addr, 1) == 4, \
        f"Expected status=4, got {cpu.rd(status_addr, 1)}"

    # Saved SP must match non-FPU calculation
    saved_sp = cpu.rd(tcb + 0x0C, 4)
    assert saved_sp == exp_sp, \
        f"Expected saved SP=0x{exp_sp:08X}, got 0x{saved_sp:08X} (non-FPU)"

    # Saved SP should be consistent with current SP
    assert cpu.r[15] == saved_sp, \
        f"SP (0x{cpu.r[15]:08X}) != saved_sp (0x{saved_sp:08X})"

    print("OK  task_full_context_save @0x%04X  (non-FPU task)" % ENTRY)


def test_context_save_fpu():
    """Verify FPU task (type=4): status set, SP saved, FPU regs on stack."""
    rom = open(ROM, 'rb').read()
    ram, tcb, task_desc, status_addr, exp_sp = \
        setup_environment(rom, task_type=4)

    cpu = SH2(rom)
    # call() initializes fr to [0.0]*16, then overwrites from passed fr= dict
    fr_init = {12: 1200.0, 13: 1300.0, 14: 1400.0, 15: 1500.0}
    cpu.call(ENTRY, r4=tcb, r6=task_desc, ram=ram, fr=fr_init)

    # Status must be 4
    assert cpu.rd(status_addr, 1) == 4

    # Saved SP must match FPU calculation (more regs saved = lower SP)
    saved_sp = cpu.rd(tcb + 0x0C, 4)
    assert saved_sp == exp_sp, \
        f"Expected saved SP=0x{exp_sp:08X}, got 0x{saved_sp:08X} (FPU)"

    print("OK  task_full_context_save @0x%04X  (FPU task type=4)" % ENTRY)


def test_context_save_fpu_values():
    """Verify FPU register values are correctly saved to stack."""
    rom = open(ROM, 'rb').read()
    ram, tcb, task_desc, status_addr, exp_sp = \
        setup_environment(rom, task_type=4)

    fr_init = {12: 1200.0, 13: 1300.0, 14: 1400.0, 15: 1500.0}
    cpu = SH2(rom)
    cpu.call(ENTRY, r4=tcb, r6=task_desc, ram=ram, fr=fr_init)

    saved_sp = cpu.rd(tcb + 0x0C, 4)

    # FPU registers saved below regular registers:
    # saved_sp+0x00: FR15 (last pushed, at SP)
    # saved_sp+0x04: FR14
    # saved_sp+0x08: FR13
    # saved_sp+0x0C: FR12
    # saved_sp+0x10: MACL (first non-FPU save from bottom)
    import struct

    def read_float(cpu, addr):
        return struct.unpack('>f', bytes(cpu.rd(addr + i, 1) for i in range(4)))[0]

    assert abs(read_float(cpu, saved_sp + 0) - 1500.0) < 0.001, "FR15 mismatch"
    assert abs(read_float(cpu, saved_sp + 4) - 1400.0) < 0.001, "FR14 mismatch"
    assert abs(read_float(cpu, saved_sp + 8) - 1300.0) < 0.001, "FR13 mismatch"
    assert abs(read_float(cpu, saved_sp + 12) - 1200.0) < 0.001, "FR12 mismatch"

    print("OK  task_full_context_save @0x%04X  (FPU values verified)" % ENTRY)


def test_context_save_register_sequence():
    """Verify the order and values of saved integer registers."""
    rom = open(ROM, 'rb').read()
    ram, tcb, task_desc, status_addr, exp_sp = \
        setup_environment(rom, task_type=1)

    cpu = SH2(rom)

    # We can't pre-set registers directly in call(), but we can verify
    # that all 13 register pushes happened by examining the stack layout.
    cpu.call(ENTRY, r4=tcb, r6=task_desc, ram=ram)

    saved_sp = cpu.rd(tcb + 0x0C, 4)

    # call() sets:
    #   r[0..15] = all 0, except r4/r6 as passed
    #   pr = SENT = 0xEEEE0000
    #   gbr = 0, macl = 0, mach = 0
    # So PR should be 0xEEEE0000, everything else should be 0.
    expected_layout = {
        0x00: ('MACL', 0),
        0x04: ('R14', 0),
        0x08: ('MACH', 0),
        0x0C: ('R13', 0),
        0x10: ('GBR', 0),
        0x14: ('R12', 0),
        0x18: ('R11', 0),
        0x1C: ('R10', 0),
        0x20: ('R9', 0),
        0x24: ('R8', 0),
        0x28: ('PAD', 0),
        0x2C: ('PR', 0xEEEE0000),
        0x30: ('R5', 0),
    }

    for offset, (name, expected_val) in expected_layout.items():
        val = cpu.rd(saved_sp + offset, 4)
        assert val == expected_val, \
            f"Expected {name}=0x{expected_val:08X} at +0x{offset:02X}, got 0x{val:08X}"

    print("OK  task_full_context_save @0x%04X  (register layout verified)" % ENTRY)


def test_context_save_no_fpu_saves():
    """Verify that non-FPU task does NOT save FPU registers."""
    rom = open(ROM, 'rb').read()
    ram, tcb, task_desc, status_addr, exp_sp = \
        setup_environment(rom, task_type=2)  # type 2, not 4

    fr_init = {12: 9999.0, 13: 9999.0, 14: 9999.0, 15: 9999.0}
    cpu = SH2(rom)
    cpu.call(ENTRY, r4=tcb, r6=task_desc, ram=ram, fr=fr_init)

    saved_sp = cpu.rd(tcb + 0x0C, 4)

    # The non-FPU saved SP should be 0xFFFFDECC
    non_fpu_sp = (0xFFFFDF00 - 52) & 0xFFFFFFFF
    assert saved_sp == non_fpu_sp, \
        f"Expected non-FPU SP=0x{non_fpu_sp:08X}, got 0x{saved_sp:08X}"

    # FPU registers should NOT be on the stack.
    # The area below MACL (at saved_sp - 4 and below) should not have been
    # touched by this function. If we read it, it should be 0 (or whatever
    # was there before). Let's verify that the FPU area below SP is untouched.
    for off in range(-4, -20, -4):
        below = saved_sp + off
        val = cpu.rd(below, 4)
        assert val == 0, \
            f"FPU area unexpectedly non-zero at +0x{off:02X}: 0x{val:08X}"

    print("OK  task_full_context_save @0x%04X  (FPU not saved for non-FPU task)" % ENTRY)


def main():
    test_context_save_non_fpu()
    test_context_save_fpu()
    test_context_save_fpu_values()
    test_context_save_register_sequence()
    test_context_save_no_fpu_saves()
    print("Passed.")
    sys.exit(0)


if __name__ == '__main__':
    main()
