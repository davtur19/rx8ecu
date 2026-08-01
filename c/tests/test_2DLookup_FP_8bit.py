#!/usr/bin/env python3
"""
Verify c/2DLookup.c's TwoDLookup_FP_8bit against the ACTUAL ROM bytes of the function
@0x20AC, run in the SH-2E emulator (tools/sh2emu.py), fed with a REAL calibration-map descriptor
found in the ROM by tools/mapscan.py (not a synthetic one) — a 16-point u8 table at 0x677E8
(breakpoints 800..6800 step 400; values 120/80/60, likely an RPM-indexed knock/limiter-style
curve). Same shape as test_2DLookup_FP_16bit.py (u16 sibling), but this wrapper is hardwired
to u8 cells (jumps to the leaf @0x26B0, interpolate_uint8Table, instead of @0x26D0).

The reference model uses the ROM's actual `fmac fr0,fr1,fr2` combine (t*(v1-v0)+v0, ONE
rounding) rather than `ts(v0)+ts(t*ts(v1-v0))` (two roundings) — the latter measurably
diverges from the emulated ROM over ~1% of random continuous-t inputs (see
test_interp_leaves.py's header for the same finding on the underlying leaf).

Run from repo root:  python3 c/tests/test_2DLookup_FP_8bit.py [N]
"""
import os, sys, random, struct
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
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

DESC = 0x677E8   # real Map1D descriptor found by `python3 tools/mapscan.py roms/stock/60E0FC00.bin`


def u16(p): return int.from_bytes(rom[p:p + 2], 'big')
def u32(p): return int.from_bytes(rom[p:p + 4], 'big')
def f32(p): return struct.unpack('>f', rom[p:p + 4])[0]


COUNT = u16(DESC)
AXP = u32(DESC + 4)
VP = u32(DESC + 8)
AXIS = [f32(AXP + i * 4) for i in range(COUNT)]
VALS = [rom[VP + i] for i in range(COUNT)]


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
    if t == 0.0:
        interp = v0
    else:
        diff = ts(v1 - v0)          # fsub: single rounding
        interp = ts(t * diff + v0)  # fmac: double intermediate, ONE final rounding
    return int(interp) & 0xFF   # ftrc: trunc toward zero, then zero-extend 8 bits


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    fails = 0
    xs = list(AXIS) + [a - 0.001 for a in AXIS] + [a + 0.001 for a in AXIS]
    xs += [-1000.0, 1000.0, AXIS[0], AXIS[-1]]
    xs += [random.uniform(0, 7000) for _ in range(N)]
    tested = 0
    for x in xs:
        r0 = cpu.call(0x20AC, r4=DESC, fr={4: x})
        got = r0 & 0xFF
        want = ref(x)
        tested += 1
        if got != want:
            fails += 1
            if fails <= 8:
                print("MISMATCH x=%r got=%d want=%d" % (x, got, want))
    print("TwoDLookup_FP_8bit  tested=%d fails=%d  %s" % (tested, fails, "OK" if not fails else "FAIL"))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
