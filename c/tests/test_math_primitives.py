#!/usr/bin/env python3
"""
Verify c/math_primitives.c against the ACTUAL ROM bytes of each function, run in the
SH-2E emulator (tools/sh2emu.py) over many single-precision random inputs.

The references below mirror each lift; inputs are rounded to single precision (ts) first,
exactly as the hardware does when it loads the FP argument registers, so the comparison is
bit-exact on the IEEE-754 result.

Batch 2 (invertAndReturn_8bit_ADDR @0x2044, multiply32Bit_saturating @0x231C,
fixedPointScaling @0x2510) uses integer args/results (masked comparisons); the emulator
subclass below adds dmuls.l/rotcr, which multiply32Bit_saturating needs and the base
sh2emu.py doesn't implement.

Run from repo root:  python3 c/tests/test_math_primitives.py [N]
"""
import os, sys, random
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, ts, f2bits, s32, MASK


class SH2E(SH2):
    """SH-2E + cmp/pz, cmp/pl, dmuls.l, rotcr — self-contained so this test runs even
    against an older emulator build; the base sh2emu.py doesn't implement dmuls.l/rotcr
    (needed for multiply32Bit_saturating @0x231C)."""
    def _exec(self, op, pc):
        if op & 0xF0FF == 0x4011:  # cmp/pz
            self.T = 1 if s32(self.r[(op >> 8) & 0xF]) >= 0 else 0; return
        if op & 0xF0FF == 0x4015:  # cmp/pl
            self.T = 1 if s32(self.r[(op >> 8) & 0xF]) > 0 else 0; return
        if op & 0xF00F == 0x300D:  # dmuls.l Rm,Rn -> signed 64-bit product in MACH:MACL
            n = (op >> 8) & 0xF; m = (op >> 4) & 0xF
            prod = (s32(self.r[n]) * s32(self.r[m])) & 0xFFFFFFFFFFFFFFFF
            self.mach = (prod >> 32) & MASK; self.macl = prod & MASK; return
        if op & 0xF0FF == 0x4025:  # rotcr Rn
            n = (op >> 8) & 0xF; oldT = self.T; newT = self.r[n] & 1
            self.r[n] = ((self.r[n] >> 1) | (oldT << 31)) & MASK; self.T = newT; return
        return super()._exec(op, pc)


ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
cpu = SH2E(open(ROM, 'rb').read())
b = f2bits

# references (fr result unless noted)
def subtractAbsolute(a, b_):            return ts(abs(ts(a - b_)))
def saturateLow(s, l):                  return s if s > l else l
def minValue(a, b_):                    return a if b_ > a else b_
def saturate(s, lo, hi):
    if not (s > lo): return lo
    return s if hi > s else hi
def encode(x):                          x &= 0xFF; return ((x << 8) | ((~x) & 0xFF)) & 0xFFFF
def isNotZero(x, c, t):                 return 1 if (ts(c - t) > x or x > ts(c + t)) else 0
def _tofp(num, sca, off, hi):
    i = int(ts(ts(ts(num - off) / sca) + 0.5))
    return 0 if i < 0 else (hi if i > hi else i)
def floatToFP_16bit(n, s, o):           return _tofp(n, s, o, 0xFFFF)
def floatToInt(n, s, o):                return _tofp(n, s, o, 0xFF)
def fixedPointToFloat_16bit(m, o, raw): return ts(m * float(raw & 0xFFFF) + o)
def fixedPointToFloat_8bit(m, o, raw):  return ts(m * float(raw & 0xFF) + o)

def invertAndReturn_8bit_ADDR(hi, lo):  return (~((hi + lo) & 0xFF)) & 0xFF
def multiply32Bit_saturating(a, b):
    p = a * b               # python ints: exact signed product, no overflow
    s = p >> 16              # floor == arithmetic shift for two's-complement semantics
    if s > 0x7FFFFFFF:  return 0x7FFFFFFF
    if s < -0x80000000: return -0x80000000
    return s
def fixedPointScaling(a, b, frac):
    # each int->float cast is single-precision (rounds a,b individually before the
    # subtract) -- matters once |a| or |b| exceeds 2**24, so don't collapse the casts.
    w    = ts(0.00390625 * ts(float(frac & 0xFFFF)))     # frac/256, ROM constant is exact
    t    = ts(1.0 - w)
    diff = ts(ts(float(b)) - ts(float(a)))
    v    = ts(diff * t)
    if v >= 2147483648.0:    d = 0x7FFFFFFF   # ftrc +overflow saturates
    elif v < -2147483648.0:  d = 0x80000000   # ftrc -overflow saturates
    else:                    d = int(v)       # ftrc: trunc toward zero
    return s32((a + d) & 0xFFFFFFFF)

def rf():
    return ts(random.choice([random.uniform(-1e4, 1e4), random.uniform(-2, 2),
                             random.uniform(0, 300), random.uniform(-300, 0)]))

IR_ADDR = 0xFFFF9000  # scratch RAM cell for invertAndReturn_8bit_ADDR's (hi,lo) pair

def ri32():
    return random.choice([random.randint(-100000, 100000), random.randint(-(1 << 31), (1 << 31) - 1),
                           random.randint(-(1 << 20), 1 << 20)])

def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 30000
    fails = {}
    def chk(name, cond):
        if not cond: fails[name] = fails.get(name, 0) + 1
    for _ in range(N):
        a, c, d = rf(), rf(), rf()
        cpu.call(0x23DC, fr={4: a, 5: c}); chk('subtractAbsolute', b(cpu.fr[0]) == b(subtractAbsolute(a, c)))
        cpu.call(0x23E4, fr={4: a, 5: c}); chk('saturateLow', b(cpu.fr[0]) == b(saturateLow(a, c)))
        cpu.call(0x23F4, fr={4: a, 5: c}); chk('minValue',    b(cpu.fr[0]) == b(minValue(a, c)))
        lo, hi = min(c, d), max(c, d)
        cpu.call(0x2404, fr={4: a, 5: lo, 6: hi}); chk('saturate', b(cpu.fr[0]) == b(saturate(a, lo, hi)))
        xi = random.randint(0, 255)
        chk('encode', (cpu.call(0x2420, r4=xi) & 0xFFFF) == encode(xi))
        tol = ts(abs(d) % 50)
        chk('isNotZero_wDivideByZeroProtect', (cpu.call(0x2440, fr={4: a, 5: c, 6: tol}) & 0xFF) == isNotZero(a, c, tol))
        sca = c if abs(c) > 1e-3 else ts(1.0)
        chk('floatToFP_16bit', (cpu.call(0x2490, fr={4: a, 5: sca, 6: d}) & 0xFFFFFFFF) == (floatToFP_16bit(a, sca, d) & 0xFFFFFFFF))
        chk('floatToInt',      (cpu.call(0x24D0, fr={4: a, 5: sca, 6: d}) & 0xFFFFFFFF) == (floatToInt(a, sca, d) & 0xFFFFFFFF))
        raw = random.randint(0, 0xFFFF)
        cpu.call(0x24C0, r4=raw, fr={4: a, 5: c}); chk('fixedPointToFloat_16bit', b(cpu.fr[0]) == b(fixedPointToFloat_16bit(a, c, raw)))
        raw8 = random.randint(0, 0xFF)
        cpu.call(0x2500, r4=raw8, fr={4: a, 5: c}); chk('fixedPointToFloat_8bit', b(cpu.fr[0]) == b(fixedPointToFloat_8bit(a, c, raw8)))

        hi, lo = random.randint(0, 255), random.randint(0, 255)
        r0 = cpu.call(0x2044, r4=IR_ADDR, ram={IR_ADDR: hi, IR_ADDR + 1: lo})
        chk('invertAndReturn_8bit_ADDR', (r0 & 0xFF) == invertAndReturn_8bit_ADDR(hi, lo))

        ia, ib = ri32(), ri32()
        r0 = cpu.call(0x231C, r4=ia & MASK, r5=ib & MASK)
        chk('multiply32Bit_saturating', s32(r0) == multiply32Bit_saturating(ia, ib))

        fa, fb = ri32(), ri32()
        frac = random.choice([random.randint(0, 255), random.randint(0, 0xFFFF)])
        r0 = cpu.call(0x2510, r4=fa & MASK, r5=fb & MASK, r6=frac & MASK)
        chk('fixedPointScaling', s32(r0) == fixedPointScaling(fa, fb, frac))
    # exact-complement edge cases for invertAndReturn_8bit_ADDR (should all be 0)
    for hi in range(0, 256, 7):
        lo = (~hi) & 0xFF
        r0 = cpu.call(0x2044, r4=IR_ADDR, ram={IR_ADDR: hi, IR_ADDR + 1: lo})
        chk('invertAndReturn_8bit_ADDR', (r0 & 0xFF) == 0)
    names = ['subtractAbsolute', 'saturateLow', 'minValue', 'saturate', 'encode',
             'isNotZero_wDivideByZeroProtect', 'floatToFP_16bit', 'floatToInt',
             'fixedPointToFloat_16bit', 'fixedPointToFloat_8bit',
             'invertAndReturn_8bit_ADDR', 'multiply32Bit_saturating', 'fixedPointScaling']
    print("inputs/function: %d" % N)
    for n in names:
        print("  %-32s %s (%d)" % (n, "OK" if not fails.get(n) else "FAIL", fails.get(n, 0)))
    sys.exit(1 if any(fails.get(n) for n in names) else 0)


if __name__ == '__main__':
    main()
