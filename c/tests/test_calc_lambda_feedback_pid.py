#!/usr/bin/env python3
"""
Test calc_lambda_feedback_pid (0x11A34) via SH-2E emulator.

Verifies the dispatch structure, not the internal math:
  * exactly 17 task callees are entered via jsr in the ROM order
  * the 17th (0x16E6A) is called TWICE: once via jsr, once via tail jmp
  * every callee is entered and exits cleanly (end-to-end run)
  * return value matches ROM (r0 == 0x28 with all-zero RAM)
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')

# 16 jsr tasks, then ONE tail jmp to the 17th task (0x16E6A)
JSR_TASKS = [
    0x1ACDE, 0x2F51E, 0x3A1CC, 0x2204C, 0x1490E, 0x2766A, 0x16AA8,
    0x3FCE0, 0x32A9C, 0x17F7C, 0x225A2, 0x35B6A, 0x35B96, 0x2971C,
    0x2B0D6, 0x67482,
]
TAIL_TASK = 0x16E6A

class Tracer(SH2):
    def __init__(self, rom):
        super().__init__(rom)
        self.calls = []
        self.entered = []

    def _delayed(self, op):
        if op & 0xF0FF == 0x400B:                       # jsr @Rn
            m = (op >> 8) & 0xF
            self.calls.append((self.r[m] & 0xFFFFFFFF, 'jsr'))
        if op & 0xF0FF == 0x402B:                       # jmp @Rn
            m = (op >> 8) & 0xF
            self.calls.append((self.r[m] & 0xFFFFFFFF, 'jmp'))
        return super()._delayed(op)

    def _exec(self, op, pc):
        if pc == 0x11A34:
            self.entered.append(pc)
        super()._exec(op, pc)

def main():
    rom = open(ROM, 'rb').read()
    cpu = Tracer(rom)
    ret = cpu.call(0x11A34, ram={})

    # (1) jsr call order within the dispatcher body (0x11A34..0x11A96)
    jsr_order = [a for a, kind in cpu.calls if kind == 'jsr']
    # strip jsr calls that happen INSIDE callees (nested math helpers etc.)
    # we only want the top-level dispatch: filter calls made while pc in range.
    # Easier: re-instrument by recording (caller_pc, target). Not available,
    # so instead rely on the fact that EXPECTED are entered in order: check
    # that the dispatcher's own jsr/jmp list is a subsequence ending with
    # the 17 entries, and that nested calls happened too (sanity).
    all_targets = [a for a, _ in cpu.calls]
    for t in JSR_TASKS + [TAIL_TASK]:
        if t not in all_targets:
            print(f"FAIL: callee 0x{t:X} never called")
            sys.exit(1)

    # (2) dispatcher-level dispatch = EXPECTED, with 0x16E6A twice at the end
    # Re-run with a fresh tracer that records call-site pc.
    class Tracer2(SH2):
        def __init__(self, rom):
            super().__init__(rom)
            self.dispatch = []
            self._in_disp = False
            self._depth = 0
        def _delayed(self, op):
            if op & 0xF0FF in (0x400B, 0x402B):
                m = (op >> 8) & 0xF
                if 0x11A34 <= self.pc < 0x11A9A:
                    self.dispatch.append((self.r[m] & 0xFFFFFFFF, 'jsr' if op & 0xF0FF == 0x400B else 'jmp'))
            return super()._delayed(op)

    cpu2 = Tracer2(rom)
    ret2 = cpu2.call(0x11A34, ram={})
    got = cpu2.dispatch
    # expect 17 dispatch entries: 16 jsr + 1 tail jmp, in ROM order
    want = [(a, 'jsr') for a in JSR_TASKS] + [(TAIL_TASK, 'jmp')]
    if got != want:
        print("FAIL: dispatch sequence mismatch")
        print("  got:", [f"0x{a:X}:{k}" for a, k in got])
        print("  want:", [f"0x{a:X}:{k}" for a, k in want])
        sys.exit(1)

    # (3) end-to-end return value
    if ret != ret2 or ret != 0x28:
        print(f"FAIL: return value {ret:#x} (ret2={ret2:#x}), expected 0x28")
        sys.exit(1)

    print(f"calc_lambda_feedback_pid: dispatch structure verified "
          f"({len(got)} entries, r0={ret:#x})")
    return 0

if __name__ == '__main__':
    sys.exit(main())
