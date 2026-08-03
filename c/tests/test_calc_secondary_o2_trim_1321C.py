#!/usr/bin/env python3
"""
test_calc_secondary_o2_trim_1321C.py — differential bit-exact test of
calc_secondary_o2_trim @0x1321C (lift: c/calc_secondary_o2_trim_1321C.c).

Method (repo Track-A pattern): the REAL ROM bytes of 0x1321C are executed in
the SH-2E emulator (tools/sh2emu.py) with a seeded random RAM overlay — the
ROM's own TwoDLookup/ThreeDLookup callees (0x2068/0x20DC) run for real — and
the resulting RAM overlay is compared bit-exactly against a pure-Python model
derived from the disassembly (see header of the C lift).

RAM footprint (from the disasm):

  read:  0xFFFFAA10 f32 in_x,  0xFFFFAD8C f32 in_y1, 0xFFFFC12C f32 in_y2,
         0xFFFFAA1C f32 in_x0, 0xFFFFA428 u8 ctl,   0xFFFFA6DF u8 latch,
         0xFFFFAADA u8 gain-sel, 0xFFFFA6B9/0xFFFFA6B7/0xFFFFA6B8 u8 modes,
         0xFFFFA6C4 f32 filt_a (in/out), 0xFFFFA6C8 f32 filt_b (in/out)
  write: 0xFFFFA6C4, 0xFFFFA6C8 (filter), 0xFFFFA6BC/0xFFFFA6C0 (outputs),
         0xFFFFA6DF (latch := ctl)
  cal:   ROM 1-D maps @0x6A000/0x6A014/0x69F60/0x69F74/0x69F88/0x69F9C/
         0x69FB0/0x69FC4/0x69FD8/0x69FEC (u8 cells, scale .5 offset -50),
         2-D maps @0x6A028/0x6A044/0x6A060/0x6A07C (1x1),
         gains @0x6F70C/0x6F710/0x6F714/0x6F718 (= 0.0)

Semantics (2 lines): recursive secondary-O2 trim accumulator — either a
one-shot bootstrap (ctl==1 and latch==0) initializes the two filter words from
1-point maps, or the words are nudged by a (stock-zero) gain and clamped at 0;
then a mode flag selects 3-D maps (zeroed), the two 12-point 1-D O2 trim maps,
1-point zero maps, or the filter words themselves to publish A6BC/A6C0; the
latch A6DF is refreshed with ctl every call.

Run from repo root:  python3 c/tests/test_calc_secondary_o2_trim_1321C.py [N]
                     (N = random vectors per seed; default 20000)
"""
import math, os, random, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2, ts  # noqa: E402

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')
ADDR = 0x1321C

# ---- RAM cells ----
A6C4 = 0xFFFFA6C4   # f32 filter word A (in/out)
A6C8 = 0xFFFFA6C8   # f32 filter word B (in/out)
A6BC = 0xFFFFA6BC   # f32 output A
A6C0 = 0xFFFFA6C0   # f32 output B
AA10 = 0xFFFFAA10   # f32 in_x
AD8C = 0xFFFFAD8C   # f32 in_y1
C12C = 0xFFFFC12C   # f32 in_y2
AA1C = 0xFFFFAA1C   # f32 in_x0
A428 = 0xFFFFA428   # u8 ctl
A6DF = 0xFFFFA6DF   # u8 latch (in/out)
AADA = 0xFFFFAADA   # u8 gain-sel
A6B9 = 0xFFFFA6B9   # u8 mode 3-D
A6B7 = 0xFFFFA6B7   # u8 mode 1-D
A6B8 = 0xFFFFA6B8   # u8 mode 1-D-zero

FOOTPRINT = set()
for _a in (A6C4, A6C8, A6BC, A6C0):
    for _i in range(4):
        FOOTPRINT.add(_a + _i)
FOOTPRINT.add(A6DF)

f32bits = lambda x: struct.unpack('>I', struct.pack('>f', ts(x)))[0]


def getf(ram, a):
    return ts(struct.unpack('>f', bytes(ram.get(a + i, 0) for i in range(4)))[0])


def putf(ram, a, v):
    b = struct.pack('>f', ts(v))
    for i in range(4):
        ram[a + i] = b[i]


class Tables:
    """ROM calibration tables read straight from the binary."""
    def __init__(self, rom):
        self.d = rom
        self.gain = {0x6F70C: self.f32(0x6F70C), 0x6F710: self.f32(0x6F710),
                     0x6F714: self.f32(0x6F714), 0x6F718: self.f32(0x6F718)}
        self.desc = {}
        for a in (0x6A000, 0x6A014, 0x69F60, 0x69F74, 0x69F88, 0x69F9C,
                  0x69FB0, 0x69FC4, 0x69FD8, 0x69FEC):
            n = struct.unpack('>H', self.d[a:a + 2])[0]
            ax = struct.unpack('>I', self.d[a + 4:a + 8])[0]
            vl = struct.unpack('>I', self.d[a + 8:a + 12])[0]
            sc = self.f32(a + 12)
            of = self.f32(a + 16)
            self.desc[a] = (n, [self.f32(ax + 4 * i) for i in range(n)],
                            [self.d[vl + i] for i in range(n)], sc, of)
        for a in (0x6A028, 0x6A044, 0x6A060, 0x6A07C):
            cx, cy = struct.unpack('>HH', self.d[a:a + 4])
            axx = struct.unpack('>I', self.d[a + 4:a + 8])[0]
            axy = struct.unpack('>I', self.d[a + 8:a + 12])[0]
            vl = struct.unpack('>I', self.d[a + 12:a + 16])[0]
            sc = self.f32(a + 20)
            of = self.f32(a + 24)
            self.desc[a] = (cx, cy,
                            [self.f32(axx + 4 * i) for i in range(cx)],
                            [self.f32(axy + 4 * i) for i in range(cy)],
                            [[self.d[vl + r * cx + c] for c in range(cx)]
                             for r in range(cy)], sc, of)

    def f32(self, a):
        return struct.unpack('>f', self.d[a:a + 4])[0]

    def data_lookup(self, n, axis, x):
        if not (x < axis[n - 1]):
            return n - 1, 0.0
        if x < axis[0]:
            return 0, 0.0
        i = 0
        while i + 1 < n and not (axis[i] <= x and x < axis[i + 1]):
            i += 1
        return i, ts((x - axis[i]) / (axis[i + 1] - axis[i]))

    def lookup1(self, addr, x):
        n, axis, vals, scale, off = self.desc[addr]
        i, t = self.data_lookup(n, axis, ts(x))
        v0 = float(vals[i])
        v1 = float(vals[i + 1 if i + 1 < n else i])
        interp = ts(math.fma(t, ts(v1 - v0), v0))
        return ts(math.fma(scale, interp, off))

    def lookup2(self, addr, x, y):
        cx, cy, axx, axy, rows, scale, off = self.desc[addr]
        ix, tx = self.data_lookup(cx, axx, ts(x))
        iy, ty = self.data_lookup(cy, axy, ts(y))
        ix1 = ix + 1 if ix + 1 < cx else ix
        iy1 = iy + 1 if iy + 1 < cy else iy
        c00 = float(rows[iy][ix]); c10 = float(rows[iy][ix1])
        c01 = float(rows[iy1][ix]); c11 = float(rows[iy1][ix1])
        row0 = ts(math.fma(tx, ts(c10 - c00), c00))
        row1 = ts(math.fma(tx, ts(c11 - c01), c01))
        interp = ts(math.fma(ty, ts(row1 - row0), row0))
        return ts(math.fma(scale, interp, off))


def build_ram(t, rom):
    ram = {}
    putf(ram, AA10, t['x']); putf(ram, AD8C, t['y1'])
    putf(ram, C12C, t['y2']); putf(ram, AA1C, t['x0'])
    putf(ram, A6C4, t['fa']); putf(ram, A6C8, t['fb'])
    for k, a in (('ctl', A428), ('latch', A6DF), ('gsel', AADA),
                 ('b9', A6B9), ('b7', A6B7), ('b8', A6B8)):
        ram[a] = t[k] & 0xFF
    return ram


def ref(t, tb):
    """Pure-Python model of 0x1321C — mirrors the C lift exactly."""
    x, y1, y2, x0 = ts(t['x']), ts(t['y1']), ts(t['y2']), ts(t['x0'])
    fa, fb = ts(t['fa']), ts(t['fb'])
    ctl, latch = t['ctl'] & 0xFF, t['latch'] & 0xFF
    gsel, b9, b7, b8 = t['gsel'] & 0xFF, t['b9'] & 0xFF, \
                       t['b7'] & 0xFF, t['b8'] & 0xFF

    # stage 1: filter update
    if latch == 0 and ctl == 1:
        fa = tb.lookup1(0x6A000, x0)
        fb = tb.lookup1(0x6A014, x0)
    else:
        ga = tb.gain[0x6F70C] if gsel == 1 else tb.gain[0x6F714]
        gb = tb.gain[0x6F710] if gsel == 1 else tb.gain[0x6F718]
        va = ts(ga + fa)
        vb = ts(gb + fb)
        # 0x23F4 minValue: result = (0.0 > v) ? v : 0.0 (NaN -> 0)
        fa = va if 0.0 > va else 0.0
        fb = vb if 0.0 > vb else 0.0

    # stage 2: map / mode select
    if b9 == 1:
        out_a = ts(tb.lookup2(0x6A028, x, y2) + tb.lookup2(0x6A044, y1, y2))
        out_b = ts(tb.lookup2(0x6A060, x, y2) + tb.lookup2(0x6A07C, y1, y2))
    elif b7 == 1:
        out_a = ts(tb.lookup1(0x69F60, x) + tb.lookup1(0x69F74, y1))
        out_b = ts(tb.lookup1(0x69F88, x) + tb.lookup1(0x69F9C, y1))
    elif b8 == 1:
        out_a = ts(tb.lookup1(0x69FB0, x) + tb.lookup1(0x69FC4, y1))
        out_b = ts(tb.lookup1(0x69FD8, x) + tb.lookup1(0x69FEC, y1))
    else:
        out_a, out_b = fa, fb

    return (fa, fb, out_a, out_b, ctl)


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    tb = Tables(rom)
    seeds = (0x1321C, 0x6F710, 0xA6BC, 0x1234, 0x5EED)
    tests = fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        vectors = []
        # structured: mode bytes + threshold-crossing inputs + filter states
        modes = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1),
                 (0, 1, 1), (1, 1, 0), (1, 0, 1), (1, 1, 1)]
        xv = [-16.0, -10.0, 4.999, 5.0, 20.0, 40.0, 41.0, float('nan')]
        fv = [-10.0, -1.0, -0.0, 0.0, 5.0, float('nan')]
        for b9, b7, b8 in modes:
            for ctl in (0, 1, 0xFF):
                for latch in (0, 1, 0xFF):
                    for gsel in (0, 1):
                        for x in xv:
                            for fa in fv:
                                for fb in fv:
                                    vectors.append(dict(
                                        x=x, y1=rng.uniform(-60, 60),
                                        y2=rng.uniform(-60, 60),
                                        x0=rng.uniform(-60, 60),
                                        fa=fa, fb=fb, ctl=ctl, latch=latch,
                                        gsel=gsel, b9=b9, b7=b7, b8=b8))
        for _ in range(N):
            def rf():  # random float with edge hits
                r = rng.random()
                if r < 0.10:
                    return rng.choice((-16.0, -15.0, -10.0, 4.999, 5.0,
                                       15.0, 35.0, 40.0, 41.0))
                if r < 0.15:
                    return float('nan')
                return rng.uniform(-60, 60)
            b9, b7, b8 = rng.choice(modes)
            vectors.append(dict(x=rf(), y1=rf(), y2=rf(), x0=rf(),
                                fa=rf(), fb=rf(),
                                ctl=rng.getrandbits(8), latch=rng.getrandbits(8),
                                gsel=rng.getrandbits(8),
                                b9=b9, b7=b7, b8=b8))

        for t in vectors:
            ram = build_ram(t, rom)
            cpu.call(ADDR, ram=ram)
            got = (tuple(struct.unpack('>I', bytes(cpu.ram.get(a + i, 0)
                                                   for i in range(4)))[0]
                         for a in (A6C4, A6C8, A6BC, A6C0))
                   + (cpu.ram.get(A6DF, 0),))
            r = ref(t, tb)
            exp = tuple(f32bits(v) for v in r[:4]) + (r[4],)
            tests += 1
            if got != exp:
                fails += 1
                if fails <= 10:
                    print("FAIL seed=0x%X %s" % (seed, t))
                    print("  emu: %s" % ' '.join('%08X' % x for x in got[:4])
                          + "  A6DF=%02X" % got[4])
                    print("  mod: %s" % ' '.join('%08X' % x for x in exp[:4])
                          + "  A6DF=%02X" % exp[4])
            # no writes outside footprint (+ stack: 6 regs + 4 floats + pr)
            for a in cpu.ram:
                if a in FOOTPRINT or a in ram or a in range(0xFFFFDEB0, 0xFFFFDF00):
                    continue
                fails += 1
                if fails <= 10:
                    print("FAIL(unexpected write) 0x%08X = %d" % (a, cpu.ram[a]))
            if fails >= 10:
                break
        if fails:
            break

    print(f"calc_secondary_o2_trim_1321C @0x1321C: {tests} tests, {fails} failures")
    if fails == 0:
        print(f"OK  calc_secondary_o2_trim_1321C @0x1321C  ({tests} inputs, 0 mismatches)")
        return 0
    print(f"FAIL calc_secondary_o2_trim_1321C @0x1321C  ({fails} mismatches)")
    return 1


if __name__ == '__main__':
    sys.exit(main())
