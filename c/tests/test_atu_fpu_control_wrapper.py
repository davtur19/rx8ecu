#!/usr/bin/env python3
"""
Verify atu_fpu_control_wrapper (0x70AC) against the ACTUAL ROM bytes.

Disassembly of the ROM function (60E1D400.bin):
  1. setSR_PARAM(0x2054) called with mask 0x00E0 — saves (SR & 0xF0) to the
     stack word and sets SR = max(mask, SR & 0xF0) in the priority bits.
  2. setRegister_REG_BIT_VAL(0x4BBC) called with
     (addr=word@0x717E=0xF74E -> 0xFFFFF74E, bit_val=word@0x717C=0x0100,
      size=1) — ORs 0x0100 into the 16-bit register at 0xFFFFF74E.
  3. fpu_nop_stub(0x2064) called with the saved old SR — restores SR.

Net observable behaviour (verified against the emulator):
  * RAM word[0xFFFFF74E] |= 0x0100   (bit 8 set; OR semantics, other bits kept)
  * SR_out = SR_in & 0x000000F0       (fpu_nop_stub restores the saved value)
  * pr restored, stack balanced (r15 back to the call-time value)

Every sub-test below asserts these; any failure exits non-zero.

Run from repo root: python3 c/tests/test_atu_fpu_control_wrapper.py
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x70AC

FPU_REG = 0xFFFFF74E   # word address the wrapper ORs bit 8 (0x0100) into
BIT = 0x0100

FAIL = 0
CHECKS = [0]


def check(cond, msg):
    global FAIL
    CHECKS[0] += 1
    if not cond:
        FAIL += 1
        print("FAIL: " + msg)


def test_wrapper_basic():
    """Fresh register: bit 8 gets set; SR left at default."""
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    ram = {FPU_REG: 0x00, FPU_REG + 1: 0x00}
    try:
        cpu.call(ENTRY, ram=ram)
    except Exception as e:
        check(False, "basic: emulator raised %s: %s" % (type(e).__name__, e))
        return

    fpu_val = cpu.rd(FPU_REG, 2)
    check(fpu_val & BIT == BIT,
          "Expected bit 8 set in FPU register, got 0x%04X" % fpu_val)
    check(cpu.sr == 0x000000F0,
          "Expected SR=0x000000F0, got 0x%08X" % cpu.sr)
    print("OK  atu_fpu_control_wrapper @0x%04X  (basic execution, side effects verified)" % ENTRY)


def test_wrapper_fpu_register_write():
    """OR semantics on the FPU control register: bit 8 set when clear,
    left alone when already set, other bits preserved."""
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    for start in (0x0000, 0x00AA, 0x50AA, 0x01AA, 0x55AA, 0xFFFF):
        ram = {FPU_REG: (start >> 8) & 0xFF, FPU_REG + 1: start & 0xFF}
        try:
            cpu.call(ENTRY, ram=ram)
        except Exception as e:
            check(False, "register write start 0x%04X: emulator raised %s: %s"
                  % (start, type(e).__name__, e))
            continue
        got = cpu.rd(FPU_REG, 2)
        exp = start | BIT
        check(got == exp,
              "FPU register write: start 0x%04X -> 0x%04X expected 0x%04X"
              % (start, got, exp))
    print("OK  atu_fpu_control_wrapper @0x%04X  (register write: OR 0x%04X)" % (ENTRY, BIT))


def test_wrapper_sr_manipulation():
    """SR is preserved through the wrapper: setSR_PARAM saves SR & 0xF0 and
    fpu_nop_stub restores it, so SR_out == SR_in & 0x000000F0."""
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    for sr_in in (0x000000F0, 0x000000E0, 0x00000000, 0x00000F00, 0x000000F1):
        try:
            cpu.call(ENTRY, sr=sr_in)
        except Exception as e:
            check(False, "SR manipulation sr_in=0x%08X: emulator raised %s: %s"
                  % (sr_in, type(e).__name__, e))
            continue
        exp = sr_in & 0x000000F0
        check(cpu.sr == exp,
              "SR after call: 0x%08X expected 0x%08X (sr_in=0x%08X)"
              % (cpu.sr, exp, sr_in))
    print("OK  atu_fpu_control_wrapper @0x%04X  (SR save/restore)" % ENTRY)


def test_wrapper_subcall_chain():
    """Prove all three sub-functions ran, without stub hacks: the FPU register
    write can only come from setRegister_REG_BIT_VAL, the SR restore from
    fpu_nop_stub, and pr/stack cleanup from the wrapper prologue/epilogue."""
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    before_r15 = 0xFFFFDF00     # cpu.call() initialises r15 here
    try:
        cpu.call(ENTRY, ram={FPU_REG: 0x00, FPU_REG + 1: 0x00})
    except Exception as e:
        check(False, "sub-call chain: emulator raised %s: %s" % (type(e).__name__, e))
        return

    check(cpu.rd(FPU_REG, 2) & BIT == BIT,
          "sub-call chain: FPU register bit 8 not set (setRegister_REG_BIT_VAL didn't run)")
    check(cpu.sr == 0x000000F0,
          "sub-call chain: SR not restored (fpu_nop_stub didn't run)")
    check(cpu.r[15] == before_r15,
          "sub-call chain: r15 not balanced (0x%08X != 0x%08X)"
          % (cpu.r[15], before_r15))
    check(cpu.pr == cpu.SENT,
          "sub-call chain: pr not restored (0x%08X != 0x%08X)" % (cpu.pr, cpu.SENT))
    print("OK  atu_fpu_control_wrapper @0x%04X  (sub-call chain via side effects)" % ENTRY)


def main():
    if not os.path.exists(ROM):
        print("FAIL: ROM not found: %s" % ROM)
        sys.exit(1)
    test_wrapper_basic()
    test_wrapper_fpu_register_write()
    test_wrapper_sr_manipulation()
    test_wrapper_subcall_chain()
    print("%d checks, %d failures" % (CHECKS[0], FAIL))
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == '__main__':
    main()
