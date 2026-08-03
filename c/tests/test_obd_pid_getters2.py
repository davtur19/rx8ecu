#!/usr/bin/env python3
"""
Verify the two remaining OBD-mode-01 getters against the ACTUAL ROM bytes,
run in the SH-2E emulator (tools/sh2emu.py):

  0x55F64  getThrottleOBD    [0xFFFFAA88] float cell -> conv @0x2490 (0xFFFF clamp)
  0x0D478  getRearO2Voltage  [0xFFFF9EF2] u16 A/D    -> scale pool @0x0D498, store @0xFFFFA3E4

getThrottleOBD:
   fldi0 fr6                    ; offset = 0.0
   mov.w 0x56088,r3             ; r3 = 0xAA88 -> RAM float cell 0xFFFFAA88
   mov.l 0x560A4,r2             ; r2 = 0x2490 (floatToInt, 0xFFFF clamp)
   fmov.s @r3,fr4               ; fr4 = raw sensor float
   jsr @r2
   fmov.s @r0,fr5               ; (delay) fr5 = pool @0x560A0 = 0x3C23D70A = 0.01f
   => clamp(trunc((v - 0.0)/0.01 + 0.5), 0, 0xFFFF)
   NOTE: unlike the five getters verified by test_obd_pid_getters.py (which
   use floatToInt @0x24D0 with a 0xFF clamp), this one calls @0x2490 — the
   identical helper but with the upper clamp loaded as 0x0000FFFF (mov.l
   0x24BC), so the result is 0..65535.

getRearO2Voltage:
   mov.l 0x0D490,r4             ; r4 = 0xFFFF9EF2 (raw 16-bit A/D count)
   mov.w @r4,r4                 ; sign-ext word
   mov.l 0x0D494,r3             ; r3 = 0xFFFFA3E4 (output float cell)
   extu.w r4,r4                 ; 0..65535
   mova 0x0D498,r0              ; r0 = &pool
   lds r4,fpul ; float fpul,fr3 ; fr3 = (float)raw
   fmov.s @r0,fr2               ; fr2 = pool @0x0D498 = 0x38A00000 = 5/65536
   fmul fr2,fr3                 ; fr3 = raw * (5/65536)  -> 0..5 V
   rts / fmov.s fr3,@r3         ; (delay) store voltage to 0xFFFFA3E4
   => no integer return; the result is the float written to RAM @0xFFFFA3E4
   (r0 at return is the mova constant 0x0D498, not the voltage).

Every FP op is single-precision (ts).  The raw A/D is a big-endian 16-bit
word seeded in the RAM overlay.

Run: python3 c/tests/test_obd_pid_getters2.py [N]
"""
import os, sys, random, struct

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')

# ---- pool constants decoded from the ROM literal pools ----
SCALE_THROTTLE = struct.unpack('>f', bytes.fromhex('3c23d70a'))[0]  # @0x560A0 = 0.01f
SCALE_O2       = struct.unpack('>f', bytes.fromhex('38a00000'))[0]  # @0x0D498 = 5/65536


def _ftrc(f):
    """Mirror the emulator's ftrc (FRn -> FPUL): NaN -> 0x80000000,
    overflow saturates to 0x7FFFFFFF / 0x80000000, else trunc toward zero."""
    if f != f:
        return -0x80000000
    if f >= 2147483648.0:
        return 0x7FFFFFFF
    if f < -2147483648.0:
        return -0x80000000
    return int(f)


def _tofp(num, sca, off, hi):
    i = _ftrc(ts(ts(ts(num - off) / sca) + 0.5))
    return 0 if i < 0 else (hi if i > hi else i)


# ---- pure-Python references (bit-exact against the ROM math) ----
def getThrottleOBD(v):
    return _tofp(v, SCALE_THROTTLE, 0.0, 0xFFFF)


def getRearO2Voltage(raw):
    return ts(float(raw & 0xFFFF) * SCALE_O2)


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    random.seed(0x20260803)
    cpu = SH2(open(ROM, 'rb').read())
    fails = {'0x55F64': 0, '0x0D478': 0}

    def run_throttle(v):
        b = struct.pack('>f', ts(v))
        ram = {0xFFFFAA88 + i: b[i] for i in range(4)}
        return cpu.call(0x55F64, ram=ram) & 0xFFFFFFFF

    def run_o2(raw):
        raw &= 0xFFFF
        ram = {0xFFFF9EF2: (raw >> 8) & 0xFF, 0xFFFF9EF3: raw & 0xFF}
        cpu.call(0x0D478, ram=ram)
        # result is the float stored to the output cell
        return struct.unpack('>f', bytes(cpu.rd(0xFFFFA3E4 + i, 1) for i in range(4)))[0]

    for _ in range(N):
        v = ts(random.choice([random.uniform(-100.0, 1000.0),
                              random.uniform(0.0, 1.0),
                              random.uniform(0.0, 100.0),
                              random.uniform(-1e-3, 1e-3)]))
        if run_throttle(v) != getThrottleOBD(v):
            fails['0x55F64'] += 1

        raw = random.choice([random.randint(0, 65535),
                             random.randint(0, 4096),
                             random.randint(0, 32768)])
        got = run_o2(raw)
        exp = getRearO2Voltage(raw)
        if struct.unpack('>I', struct.pack('>f', got))[0] != struct.unpack('>I', struct.pack('>f', exp))[0]:
            fails['0x0D478'] += 1

    # targeted edges
    for v in [0.0, 1.0, 0.01, 100.0, 655.35, 655.36, 1000.0, -0.01, -0.1, 300.0]:
        v = ts(v)
        if run_throttle(v) != getThrottleOBD(v):
            fails['0x55F64'] += 1

    for raw in [0, 1, 255, 1000, 4096, 6553, 32768, 65535, 65536, 5000]:
        raw &= 0xFFFF
        got = run_o2(raw)
        exp = getRearO2Voltage(raw)
        if struct.unpack('>I', struct.pack('>f', got))[0] != struct.unpack('>I', struct.pack('>f', exp))[0]:
            fails['0x0D478'] += 1

    names = ['0x55F64 getThrottleOBD', '0x0D478 getRearO2Voltage']
    print('inputs/function: %d + 10 targeted (seed 0x20260803)' % N)
    for n in names:
        e = n.split()[0][2:]
        print('  %-28s %s (%d)' % (n, "OK" if not fails['0x' + e] else "FAIL",
                                   fails['0x' + e]))
    sys.exit(1 if fails['0x55F64'] or fails['0x0D478'] else 0)


if __name__ == '__main__':
    main()
