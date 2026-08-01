#!/usr/bin/env python3
"""
Verify os_context_switch (0x3DB0) against the ACTUAL ROM bytes, run in the
SH-2E emulator (tools/sh2emu.py).

0x3DB0 is the RTOS context-switch helper reached from setSR(0) (0x3934) when the
CPU is NOT running inside a task (the TCB flag at RAM8[RAM32[0xFFFF72C8]+1] != 1).

ROM semantics (verified by disassembly):
    prologue: push r14, r13, pr;  r13 = SR (entry SR)
    0x3DBA:   SR = RAM32[0xFFFF72C0]      (restore the TCB's stored SR)
    skip A    RAM16[0xFFFF72B4] == RAM16[0xFFFF72B6]  -> 0x3DF0 (no switch)
    skip B    RAM32[0xFFFF72B8] & 0x1000  -> 0x3DF0 (no switch)
    0x3DF0:   SR = r13 (restore entry SR); r0 = 0; epilogue
    switch:   RAM32[0xFFFF72B8] = 0x0100
              if RAM32[0x4B10] != 0: call 0x35EE(2)
              call 0x3BF4(r4 = &0xFFFF72B0, r5 = entry SR, r6 = RAM32[0xFFFF72C8])
              (task_full_context_save: status byte = 4, SP saved at TCB+0xC, then
               its tail 0x3C68 jumps to 0x375C/0x3848 which launches the kernel —
               patched to rts;nop here, same pattern as test_task_full_context_save.py)
              r0 = 0; epilogue

Run: python3 c/tests/test_os_context_switch_3DB0.py
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x3DB0

TCB = 0xFFFF72B0      # current-task TCB base (kernel struct)
STORE_SR = 0xFFFF72C0 # TCB + 0x10
W_B4 = 0xFFFF72B4     # TCB + 0x04
W_B6 = 0xFFFF72B6     # TCB + 0x06
D_B8 = 0xFFFF72B8     # TCB + 0x08
PTR_C8 = 0xFFFF72C8   # TCB + 0x18 -> task-desc ptr
CB_4B10 = 0x4B10      # optional callback slot (0 = disabled)


def build_ram(flag_skip_a=False, flag_skip_b=False, status=0, cb=0):
    """RAM overlay for a 0x3DB0 scenario.  TCB fields live at 0xFFFF72B0."""
    task_desc = 0xFFFFA200
    status_addr = 0xFFFFA300
    ram = {}
    # TCB stored SR (restored at 0x3DBA)
    for i in range(4):
        ram[STORE_SR + i] = (0x000000F0 >> (24 - 8 * i)) & 0xFF
    # skip-A control: word equality at TCB+4 / TCB+6
    va = 0x1234 if flag_skip_a else 0x1234
    vb = 0x1234 if flag_skip_a else 0x5678
    ram[W_B4] = (va >> 8) & 0xFF; ram[W_B4 + 1] = va & 0xFF
    ram[W_B6] = (vb >> 8) & 0xFF; ram[W_B6 + 1] = vb & 0xFF
    # skip-B control: bit 0x1000 of TCB+8
    d = 0x00001000 if flag_skip_b else 0x00000000
    for i in range(4):
        ram[D_B8 + i] = (d >> (24 - 8 * i)) & 0xFF
    # TCB+0x18 -> task descriptor pointer
    for i in range(4):
        ram[PTR_C8 + i] = (task_desc >> (24 - 8 * i)) & 0xFF
    # task descriptor: [0] type byte, [4..8] pointer to status byte
    ram[task_desc] = 1   # non-FPU task
    for i in range(4):
        ram[task_desc + 4 + i] = (status_addr >> (24 - 8 * i)) & 0xFF
    ram[status_addr] = status
    # optional callback (0x35EE(2)) disabled unless cb != 0
    for i in range(4):
        ram[CB_4B10 + i] = ((cb >> (24 - 8 * i)) & 0xFF) if cb else 0
    # patch task_full_context_save's tail @0x3C68 (jmp 0x375C) to rts;nop so the
    # switch path terminates cleanly (same pattern as test_task_full_context_save.py)
    ram[0x3C68] = 0x00; ram[0x3C69] = 0x0B
    ram[0x3C6A] = 0x00; ram[0x3C6B] = 0x09
    return ram, task_desc, status_addr


def test_skip_a():
    """RAM16[72B4] == RAM16[72B6] -> no switch, r0 = 0, no RAM side effects."""
    ram, _, _ = build_ram(flag_skip_a=True)
    cpu = SH2(open(ROM, 'rb').read())
    r0 = cpu.call(ENTRY, r4=0, sr=0x00000000, ram=ram)
    assert r0 == 0, "r0 = 0x%X" % r0
    assert cpu.sr == 0, "SR should be restored to entry SR (0), got 0x%X" % cpu.sr
    assert cpu.rd(D_B8, 4) == 0, "RAM32[72B8] should be untouched, got 0x%X" % cpu.rd(D_B8, 4)
    print("OK  0x3DB0 skip-A (word-equality)  r0=0 SR restored no-RAM-change")


def test_skip_b():
    """RAM32[72B8] & 0x1000 -> no switch, r0 = 0, no RAM side effects."""
    ram, _, _ = build_ram(flag_skip_b=True)
    cpu = SH2(open(ROM, 'rb').read())
    r0 = cpu.call(ENTRY, r4=0, sr=0x00000000, ram=ram)
    assert r0 == 0, "r0 = 0x%X" % r0
    assert cpu.sr == 0, "SR should be restored to entry SR (0), got 0x%X" % cpu.sr
    assert cpu.rd(D_B8, 4) == 0x00001000, "RAM32[72B8] should keep 0x1000"
    print("OK  0x3DB0 skip-B (0x1000 bit set)  r0=0 SR restored no-RAM-change")


def test_switch():
    """Both skip conditions clear -> RAM32[72B8]=0x0100, status=4, SP saved, r0=0.

    The switch path is "enter the kernel": 0x3BF4 saves the full context then its
    tail (0x3C68, patched to rts;nop) returns to 0x3DB0, but 0x3BF4 never unwinds
    its own 52-byte stack frame before the tail (the real kernel rebuilds r15 from
    the saved context), so 0x3DB0's epilogue pops the wrong slots and the emulator
    crashes at pc=0.  All deterministic switch effects are applied BEFORE that
    crash, so we assert them after tolerating it (kernel launch = out of scope)."""
    ram, _, status_addr = build_ram(flag_skip_a=False, flag_skip_b=False)
    cpu = SH2(open(ROM, 'rb').read())
    try:
        cpu.call(ENTRY, r4=0, sr=0x00000000, ram=ram)
        terminated_cleanly = True
    except NotImplementedError:
        terminated_cleanly = False   # expected: epilogue pops garbage after the switch
    assert cpu.rd(D_B8, 4) == 0x00000100, "RAM32[72B8] should be 0x100, got 0x%X" % cpu.rd(D_B8, 4)
    # 0x3BF4 effects: status byte = 4, saved SP at TCB + 0xC
    assert cpu.rd(status_addr, 1) == 4, "task status should be 4, got %d" % cpu.rd(status_addr, 1)
    saved_sp = cpu.rd(TCB + 0xC, 4)
    # 0x3BF4 saved r15 with 0x3DB0's own 3 prologue pushes (r14, r13, pr) still on
    # the stack: (3 + 13) * 4 = 64 bytes below the initial 0xFFFFDF00.
    assert saved_sp == (0xFFFFDF00 - 64) & 0xFFFFFFFF, "saved SP 0x%X" % saved_sp
    # SR restored at 0x3DBA from TCB+0x10 (0xF0) and never touched again before the
    # epilogue crash, so final SR is the TCB-stored 0xF0.
    assert cpu.sr == 0x000000F0, "SR should be 0xF0 (TCB stored), got 0x%X" % cpu.sr
    state = "clean" if terminated_cleanly else "crash-after-effects (kernel entry, out of scope)"
    print("OK  0x3DB0 switch   RAM32[72B8]=0x100 status=4 SP=0x%X SR=0xF0 [%s]" % (saved_sp, state))


def main():
    test_skip_a()
    test_skip_b()
    test_switch()
    print("\nAll os_context_switch (0x3DB0) tests passed.")


if __name__ == '__main__':
    main()
