#!/usr/bin/env python3
"""
Verify div32_signed (0x003FE8) against the ACTUAL ROM bytes, run
in the SH-2E emulator with SH-2E DIV instructions added.

div32_signed implements 32-bit signed division using the SH-2E's
div0s/div1/rotcl step-by-step algorithm. The quotient is returned in r0.

C:
  int32_t div32_signed(int32_t divisor, int32_t dividend)

SH-2E register convention (broken — uses r0, r1 directly):
  r0 = divisor
  r1 = dividend

Run from repo root:  python3 c/tests/test_div32_signed.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, MASK

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x003FE8


class SH2Div(SH2):
    """SH-2E + div0s/div0u/div1/subc/rotcl instructions needed for 32-bit division.

    The ROM function @0x3FE8 is a fully unrolled 32x div1 loop:

        div32_signed(divisor in r0, dividend in r1):
          tst r0,r0 ; bt div_zero          ; divisor == 0 -> 0x4086
          mov #0,r2
          div0s r2,r1                      ; Q=MSB(r1) (dividend), M=MSB(r2)=0
          subc r3,r3                       ; r3 = -T (0xFFFFFFFF if dividend<0)
          subc r2,r1                       ; r1 = dividend - T   (adjusted)
          div0s r0,r3                      ; M=MSB(r0) (divisor), Q=MSB(r3) (dividend),
                                           ; T = Q^M = sign(quotient)
          {rotcl r1; div1 r0,r3} x32       ; r1 = quotient accumulator,
                                           ; r3 = partial remainder (Rn of div1)
          rotcl r1 ; addc r2,r1            ; final rotation + correction
          mov r1,r0 ; rts

      div_zero: [0xFFFF7304] = 0x44E ; r0 = 0 ; rts

    DIV1 semantics below match QEMU target/sh4/translate.c (div1 Rm,Rn):
    the partial remainder lives in Rn and the divisor in Rm.
    """

    def __init__(self, rom):
        super().__init__(rom)
        self._Q = 0  # internal Q flag for division
        self._M = 0  # internal M flag for division

    def _exec(self, op, pc):
        r = self.r
        n = (op >> 8) & 0xF
        m = (op >> 4) & 0xF
        n0 = op >> 12
        lo = op & 0xFF
        nib = op & 0xF

        # ---- div0s Rm,Rn (0x2nm7) ----
        # Q <- MSB(Rn), M <- MSB(Rm), T <- Q^M.  Per the ROM's usage the
        # DIVIDEND is in Rn and the DIVISOR in Rm (div0s r0,r3 at 0x3FF8:
        # Q=MSB(r3)=sign(dividend), M=MSB(r0)=sign(divisor)).
        if n0 == 2 and nib == 7:
            self._Q = (r[n] >> 31) & 1   # sign of Rn (dividend)
            self._M = (r[m] >> 31) & 1   # sign of Rm (divisor)
            self.T = self._Q ^ self._M   # T = predicted sign of quotient
            return

        # ---- div0u Rm,Rn (0x0nm9) ----
        if n0 == 0 and nib == 9:
            # Initialize unsigned division
            self._Q = 0
            self._M = 0
            self.T = 0
            return

        # ---- div1 Rm,Rn (0x3nm4) - one non-restoring division step ----
        # The dividend bit arrives in T (rotated out of the quotient
        # accumulator r1 by the preceding `rotcl r1`); the partial
        # remainder (Rn) is rotated left with that bit inserted at bit 0.
        if n0 == 3 and nib == 4:
            t0 = (r[n] >> 31) & 1                 # MSB of Rn, pushed out
            r[n] = ((r[n] << 1) | self.T) & MASK  # rotate left, insert old T
            t1 = (self._Q ^ self._M) & 1
            t1 = (t1 - 1) & MASK                  # 0xFFFFFFFF if Q==M else 0
            t2 = (-r[m]) & MASK                   # two's complement of Rm
            if t1 == 0:
                t2 = r[m]                         # Q==M: subtract Rm, else add Rm
            lo = r[n] + t2                        # low 32 bits of (Rn + t2)
            r[n] = lo & MASK
            carry = (lo >> 32) & 1                # carry into the high word
            t1 = (t1 + carry) & 1                 # high-word bit 0
            t1 ^= t0                              # combine with pushed-out bit
            self.T = t1 ^ 1
            self._Q = self._M ^ t1
            return

        # ---- subc Rm,Rn (0x3nmA): Rn = Rn - Rm - T; T = borrow ----
        if n0 == 3 and nib == 0xA:
            s = r[n] - r[m] - self.T
            self.T = 1 if s < 0 else 0
            r[n] = s & MASK
            return

        # ---- rotcl Rn (0x4n24): rotate left through carry (n, not m) ----
        if op & 0xF0FF == 0x4024:
            t = (r[n] >> 31) & 1
            r[n] = ((r[n] << 1) | self.T) & MASK
            self.T = t
            return

        return super()._exec(op, pc)


def call_div(cpu, entry, r0_val, r1_val):
    """Run a division function with r0 and r1 set."""
    cpu.ram = {}
    cpu.r = [0] * 16
    cpu.r[0] = r0_val & 0xFFFFFFFF
    cpu.r[1] = r1_val & 0xFFFFFFFF
    cpu.r[15] = 0xFFFFDF00
    cpu.fr = [0.0] * 16
    cpu.pr = cpu.SENT
    cpu.T = 0
    cpu._Q = 0
    cpu._M = 0
    cpu.macl = 0; cpu.mach = 0; cpu.gbr = 0
    cpu.fpul = 0; cpu.fpscr = 0
    cpu.pc = entry & 0xFFFFFFFF
    steps = 0
    while True:
        if cpu.pc == cpu.SENT:
            return cpu.r[0] & 0xFFFFFFFF
        steps += 1
        if steps > 500000:
            raise RuntimeError("runaway at 0x%X" % cpu.pc)
        op = cpu.rd(cpu.pc, 2)
        br = cpu._delayed(op)
        if br is None:
            cpu._exec(op, cpu.pc)
            cpu.pc = (cpu.pc + 2) & 0xFFFFFFFF
        else:
            target, take = br
            cpu._exec(cpu.rd(cpu.pc + 2, 2), cpu.pc + 2)
            cpu.pc = target if take else (cpu.pc + 4) & 0xFFFFFFFF


def ref_quot(divisor, dividend):
    """Reference: signed 32-bit truncating (C99-style) division.

    The ROM's div0s/div1 loop produces C99-style truncation toward zero,
    NOT Python's floor division (which differs for negative results).
    """
    s32 = lambda x: x - (1 << 32) if x & 0x80000000 else x
    d = s32(divisor)
    v = s32(dividend)
    if d == 0:
        return 0  # per ROM: div-by-zero returns 0
    q = abs(v) // abs(d)          # magnitude quotient, truncate toward zero
    if (v < 0) != (d < 0):
        q = -q
    return q & 0xFFFFFFFF


def test_div32_signed(cpu, N):
    """Verify div32_signed @0x3FE8 against Python reference."""
    for _ in range(N):
        divisor = random.randint(0, 0xFFFFFFFF)
        dividend = random.randint(0, 0xFFFFFFFF)
        # Skip divisor=0 (handled separately)
        if divisor == 0:
            continue
        result = call_div(cpu, ENTRY, divisor, dividend)
        expected = ref_quot(divisor, dividend)
        if result != expected:
            return (divisor, dividend, result, expected)
    return None


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    rom = open(ROM, 'rb').read()
    cpu = SH2Div(rom)

    # Edge cases
    edge_cases = [
        (1, 0, 0),
        (1, 1, 1),
        (2, 5, 2),
        (5, 17, 3),
        (7, 100, 14),               # 100 / 7 = 14
        (7, 0xFFFFFF9C, 0xFFFFFFF2),  # -100 / 7 = -14 (truncating, 0xFFFFFFF2)
        (0xFFFFFFFF, 0xFFFFFFFF, 1),  # -1 / -1 = 1
        (0xFFFFFFFF, 0x00000001, 0xFFFFFFFF),  # -1 / 1 = -1 (0xFFFFFFFF)
        (0x00000001, 0xFFFFFFFF, 0xFFFFFFFF),  # 1 / -1 = -1
        (0xFFFFFFFF, 0x80000000, 0x80000000),  # INT32_MIN / -1 = INT32_MIN (wraps)
        (0x80000000, 0x40000000, 0),  # 2^30 / -2^31 = 0 (|divisor| > |dividend|)
        (0x7FFFFFFF, 0x7FFFFFFF, 1),  # MAX_INT / MAX_INT = 1
        (0x80000000, 0x80000000, 1),  # MIN_INT / MIN_INT = 1
        (3, 0, 0),
        (10, 0, 0),
        (0x80000000, 1, 0),  # 1 / -2^31 = 0
    ]
    for divisor, dividend, expected in edge_cases:
        if divisor == 0:
            continue
        result = call_div(cpu, ENTRY, divisor, dividend)
        if result != expected:
            print("FAIL EDGE: %d / %d → 0x%08X(%d) expected 0x%08X(%d)" % (
                divisor if not (divisor & 0x80000000) else divisor - 0x100000000,
                dividend if not (dividend & 0x80000000) else dividend - 0x100000000,
                result, result if not (result & 0x80000000) else result - 0x100000000,
                expected, expected if not (expected & 0x80000000) else expected - 0x100000000))
            sys.exit(1)

    # Division by zero test: ROM writes diag code 0x44E to 0xFFFF7304,
    # returns 0.
    result = call_div(cpu, ENTRY, 0, 100)
    if result != 0:
        print("FAIL: division by zero returned 0x%08X (expected 0)" % result)
        sys.exit(1)
    diag = (cpu.ram.get(0xFFFF7304, 0) << 24) | (cpu.ram.get(0xFFFF7305, 0) << 16) \
         | (cpu.ram.get(0xFFFF7306, 0) << 8) | cpu.ram.get(0xFFFF7307, 0)
    if diag != 0x44E:
        print("FAIL: division by zero wrote 0x%08X to 0xFFFF7304 (expected 0x44E)" % diag)
        sys.exit(1)

    err = test_div32_signed(cpu, N)
    if err:
        divisor, dividend, result, expected = err
        s32 = lambda x: x - (1 << 32) if x & 0x80000000 else x
        print("FAIL: %d / %d → 0x%08X(%d) expected 0x%08X(%d)" % (
            s32(divisor), s32(dividend), result, s32(result), expected, s32(expected)))
        sys.exit(1)
    else:
        print("OK  div32_signed @0x%04X  (%d edge + %d random, excl div0)" % (ENTRY, len(edge_cases), N))
        sys.exit(0)

if __name__ == '__main__':
    main()
