#!/usr/bin/env python3
"""
Verify that type-0 (f32-cell) 1-D maps are read as FLOATS by TwoDLookup (ROM 0x2068).

Regression test for the c/2DLookup.c bug: map1d_cell had no `case 0`, so type-0 maps
fell into the s16 `default` and read wrong values (an f32 cell's bits reinterpreted as
int16). The ROM dispatch @0x2068 (jump table @0x2098) sends type 0 to the f32 handler
@0x2678 (`shll2 r0` = 4-byte fmov.s cells), NOT to the s16 handler @0x2690 (or its
0x269A interior); the C lift mirrors 3dLookup.c's cell2() by treating type 0 as float.

Checks, all against the ACTUAL ROM bytes run in the SH-2E emulator (tools/sh2emu.py),
fed with a REAL type-0 descriptor found in the ROM (60E0FC00.bin @0x68E8C — an
11-point f32 table, axis -40..110, values 0.125..0.875, no scale/offset):

  1. ROM @0x2068 returns the FLOAT-cell interpolation, bit-exact vs an fmac-faithful
     reference (the f32 handler @0x2678 combines with `fmac` single rounding; same
     model as test_2DLookup_FP_8bit.py).
  2. The C lift c/2DLookup.c's TwoDLookup (compiled with the host cc, called through
     ctypes) returns the same float values, bit-exact vs a double-rounding reference
     that mirrors the lift's `v0 + t*(v1-v0)` exactly (same model as
     test_2DLookup_FP_16bit.py).
  3. Regression guard: the s16 reinterpretation of the same cells is asserted to be
     WRONG (differs by orders of magnitude) — that is the bug being fixed.

Run from repo root:  python3 c/tests/test_2DLookup_type0.py [N]
"""
import ctypes, os, random, struct, subprocess, sys

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

DESC = 0x68E8C   # real type-0 (f32-cell) Map1D descriptor found by mapscan.py


def u16(p): return int.from_bytes(rom[p:p + 2], 'big')
def u32(p): return int.from_bytes(rom[p:p + 4], 'big')
def f32(p): return struct.unpack('>f', rom[p:p + 4])[0]


COUNT = u16(DESC)
AXP = u32(DESC + 4)
VP = u32(DESC + 8)
AXIS = [f32(AXP + i * 4) for i in range(COUNT)]
VALS = [f32(VP + i * 4) for i in range(COUNT)]


def s16at(p):
    v = int.from_bytes(rom[p:p + 2], 'big')
    return v - (1 << 16) if v & 0x8000 else v


def _interp(get, x):
    """Shared piecewise-linear frame; get(i) reads cell i per the type model."""
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
    j = i + 1 if i + 1 < n else i
    return i, j, t


def ref_fmac(x):
    """ROM-faithful reference for the f32 handler @0x2678: fsub then fmac (single
    rounding), with the t==0 fast path (bt/s skips straight to rts, fr2=cell[i])."""
    i, j, t = _interp(lambda k: VALS[k], x)
    v0, v1 = VALS[i], VALS[j]
    if t == 0.0:
        return v0
    diff = ts(v1 - v0)          # fsub: single rounding
    return ts(t * diff + v0)    # fmac: single rounding


def ref_double(x):
    """C-lift-faithful reference mirroring TwoDLookup's `v0 + t * (v1 - v0)`
    (each op single-precision rounded, same model as test_2DLookup_FP_16bit.py)."""
    i, j, t = _interp(lambda k: VALS[k], x)
    v0, v1 = VALS[i], VALS[j]
    return ts(v0 + ts(t * ts(v1 - v0)))


def ref_s16(x):
    """The OLD (buggy) model: type-0 cells read as int16."""
    i, j, t = _interp(lambda k: float(s16at(VP + 2 * k)), x)
    v0 = float(s16at(VP + 2 * i))
    v1 = float(s16at(VP + 2 * j))
    return ts(v0 + ts(t * ts(v1 - v0)))


def sample_inputs(N):
    xs = list(AXIS) + [a - 0.001 for a in AXIS] + [a + 0.001 for a in AXIS]
    xs += [-1000.0, 1000.0, AXIS[0], AXIS[-1], float('nan')]
    xs += [random.uniform(-60, 130) for _ in range(N)]
    return xs


def check_rom(xs):
    fails = 0
    s16_wrong = 0
    for x in xs:
        cpu.call(0x2068, r4=DESC, fr={4: x})
        got = ts(cpu.fr[0])
        if struct.pack('>f', got) != struct.pack('>f', ts(ref_fmac(x))):
            fails += 1
            if fails <= 5:
                print("ROM MISMATCH x=%r got=%r want=%r" % (x, got, ref_fmac(x)))
        if struct.pack('>f', got) != struct.pack('>f', ts(ref_s16(x))):
            s16_wrong += 1
    return fails, s16_wrong


class Map1D(ctypes.Structure):
    """Host-ABI copy of 2DLookup.c's Map1D (identical field types => identical
    layout; the +4/+8 offsets in the source comments are the SH-2E's, not the host's)."""
    _fields_ = [("count", ctypes.c_uint16), ("type", ctypes.c_uint8), ("_pad", ctypes.c_uint8),
                ("axis", ctypes.POINTER(ctypes.c_float)), ("values", ctypes.c_void_p),
                ("scale", ctypes.c_float), ("offset", ctypes.c_float)]


def check_c_lift(xs):
    so = '/tmp/twodlookup_type0.so'
    subprocess.run(['cc', '-O2', '-shared', '-fPIC',
                    os.path.join(ROOT, 'c', '2DLookup.c'), '-lm', '-o', so], check=True)
    lib = ctypes.CDLL(so)
    lib.TwoDLookup.argtypes = [ctypes.POINTER(Map1D), ctypes.c_float]
    lib.TwoDLookup.restype = ctypes.c_float
    axis_arr = (ctypes.c_float * COUNT)(*AXIS)
    vals_arr = (ctypes.c_float * COUNT)(*VALS)
    desc = Map1D(COUNT, 0, 0, axis_arr, ctypes.cast(vals_arr, ctypes.c_void_p), 0.0, 0.0)
    fails = 0
    for x in xs:
        got = ts(lib.TwoDLookup(ctypes.byref(desc), ts(x)))
        if struct.pack('>f', got) != struct.pack('>f', ts(ref_double(x))):
            fails += 1
            if fails <= 5:
                print("C MISMATCH x=%r got=%r want=%r" % (x, got, ref_double(x)))
    return fails, lib, desc


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    random.seed(20260731)
    xs = sample_inputs(N)
    tested = len(xs)

    rom_fails, s16_wrong = check_rom(xs)
    print("ROM @0x2068 (type-0 f32 map): tested=%d fails=%d (s16 model wrong on %d/%d)"
          % (tested, rom_fails, s16_wrong, tested))

    # regression guard: the s16 interpretation must NOT be what the ROM produces
    if s16_wrong == 0:
        print("FAIL: s16 interpretation matched the ROM everywhere — bug not exercised")
        sys.exit(1)

    c_fails, lib, desc = check_c_lift(xs)
    print("C  TwoDLookup (type-0 f32 map): tested=%d fails=%d" % (tested, c_fails))

    # hard assertions on fixed inputs that the old lift demonstrably misread
    # (axis 0x68E8C = -40,-20,0,20,... so x=-40->i0, x=0->i2, x=110->clamp i10)
    spot = {AXIS[0]: VALS[0], 0.0: VALS[2], AXIS[-1]: VALS[-1]}
    for x, want in spot.items():
        got = ts(lib.TwoDLookup(ctypes.byref(desc), ts(x)))
        s16v = ref_s16(x)
        if abs(s16v - want) < 1.0:
            print("FAIL: spot input x=%r s16 model %r too close to float want %r" % (x, s16v, want))
            sys.exit(1)
        if struct.pack('>f', got) != struct.pack('>f', ts(want)):
            print("FAIL: spot input x=%r C got %r want %r" % (x, got, want))
            sys.exit(1)

    ok = rom_fails == 0 and c_fails == 0
    print("test_2DLookup_type0: %s" % ("OK" if ok else "FAIL"))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
