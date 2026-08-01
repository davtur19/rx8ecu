#!/usr/bin/env python3
"""
Verify c/2DLookup.c's TwoDLookup_FP_16bit against the ACTUAL ROM bytes of the function
@0x20C4, run in the SH-2E emulator (tools/sh2emu.py), fed with a REAL calibration-map
descriptor found in the ROM by tools/mapscan.py (not a synthetic one) — a 16-point u16 table
at 0x67870 (breakpoints -40..110 step 10; values 1400..2500, likely a temp-indexed
target-idle-RPM-style curve). This wrapper is hardwired to u16 cells with NO scale/offset
(confirmed from asm: it never reads the descriptor's type/scale/offset fields, only
count@+0, axis@+4, values@+8), unlike the generic TwoDLookup @0x2068.

Run from repo root:  python3 c/tests/test_2DLookup_FP_16bit.py [N]
"""
import os, sys, random, struct
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
random.seed(0x20C4)   # seed the ONLY RNG source (the stdlib `random` module) at
                      # module level: deterministic, reproducible runs (flake-free)
from sh2emu import SH2, ts, s32


class SH2E(SH2):
    """SH-2E + cmp/pz, cmp/pl — self-contained so this test runs even against an older
    emulator build; the base sh2emu.py also defines these opcodes."""
    def _exec(self, op, pc):
        if op & 0xF0FF == 0x4011:  # cmp/pz
            self.T = 1 if s32(self.r[(op >> 8) & 0xF]) >= 0 else 0; return
        if op & 0xF0FF == 0x4015:  # cmp/pl
            self.T = 1 if s32(self.r[(op >> 8) & 0xF]) > 0 else 0; return
        return super()._exec(op, pc)


ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
rom = open(ROM, 'rb').read()
cpu = SH2E(rom)

DESC = 0x67870   # real Map1D descriptor found by `python3 tools/mapscan.py roms/stock/60E0FC00.bin`


def u16(p): return int.from_bytes(rom[p:p + 2], 'big')
def u32(p): return int.from_bytes(rom[p:p + 4], 'big')
def f32(p): return struct.unpack('>f', rom[p:p + 4])[0]


COUNT = u16(DESC)
AXP = u32(DESC + 4)
VP = u32(DESC + 8)
AXIS = [f32(AXP + i * 4) for i in range(COUNT)]
VALS = [u16(VP + i * 2) for i in range(COUNT)]


def ref(x):
    n = COUNT
    x = ts(x)
    if not (x < AXIS[n - 1]):
        i, t = n - 1, ts(0.0)
    elif x < AXIS[0]:
        i, t = 0, ts(0.0)
    else:
        i = 0
        while i + 1 < n and not (AXIS[i] <= x < AXIS[i + 1]):
            i += 1
        t = ts(ts(x - AXIS[i]) / ts(AXIS[i + 1] - AXIS[i]))
    v0 = float(VALS[i])
    v1 = float(VALS[i + 1]) if i + 1 < n else float(VALS[i])
    # ROM @0x26E8-0x26EC computes this as fsub (fr1 = v1-v0) then
    # fmac fr0,fr1,fr2  (fr2 = fr2 + fr0*fr1) — a FUSED multiply-add that
    # rounds ONLY ONCE.  Rounding the product and/or the sum separately
    # (ts(v0 + ts(t*ts(v1-v0)))) differs by 1 ULP at truncation boundaries,
    # which used to make this test fail intermittently (got=2078 want=2079).
    # Single-rounding semantics match the hardware exactly:
    interp = ts(v0 + t * ts(v1 - v0))
    return int(interp) & 0xFFFF   # ftrc: trunc toward zero, then zero-extend 16 bits


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    fails = 0
    xs = list(AXIS) + [a - 0.001 for a in AXIS] + [a + 0.001 for a in AXIS]
    xs += [-1000.0, 1000.0, AXIS[0], AXIS[-1]]
    xs += [random.uniform(-60, 130) for _ in range(N)]
    tested = 0
    for x in xs:
        r0 = cpu.call(0x20C4, r4=DESC, fr={4: x})
        got = r0 & 0xFFFF
        want = ref(x)
        tested += 1
        if got != want:
            fails += 1
            if fails <= 8:
                print("MISMATCH x=%r got=%d want=%d" % (x, got, want))
    print("TwoDLookup_FP_16bit  tested=%d fails=%d  %s" % (tested, fails, "OK" if not fails else "FAIL"))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
