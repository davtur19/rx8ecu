#!/usr/bin/env python3
"""
test_calc_adaptive_fuel_trim_1379C.py — differential bit-exact test of
calc_adaptive_fuel_trim @0x1379C (lift: c/calc_adaptive_fuel_trim.c).

Method (repo Track-A pattern): the REAL ROM bytes of 0x1379C are executed in
the SH-2E emulator (tools/sh2emu.py) with a seeded random RAM overlay — the
ROM's own table1D_lookup @0x2068 and clamp-select @0x2404 run for real — and
the resulting RAM overlay + r0 are compared bit-exactly against a pure-Python
model derived from the disassembly.

RAM footprint (from the disasm, verified against the lift):

  read:  0xFFFFB5B8 f32 RPM, 0xFFFFB5C4 f32 lambda (fr3),
         0xFFFFC12C f32 "lambda2" (fr14, used by the A730 status band),
         0xFFFFB5A4 u8 enable, 0xFFFFB5AC u8 table-sel, 0xFFFFB5AA u8 flag2,
         0xFFFFAADA u8 flag3, 0xFFFFC084 f32 ect, 0xFFFFA424 u16 counter,
         0xFFFFA720 f32 (overwritten: A720 is written, then re-read as the
         "previous trim" — so the seeded value is dead),
         0xFFFFA730 u8 status (in/out)
  write: 0xFFFFA728 f32 dev, 0xFFFFA720 f32 lookup, 0xFFFFA730 u8 status,
         0xFFFFA718 f32 out
  cal:   table1D_lookup @0x2068 (ROM), clamp-select @0x2404 (ROM),
         tables @0x6A868/0x6A87C (9-pt u8, axis +/-100, scale 0.25 off -32),
         consts @0x72C5C (u16 375), 0x72C60 (1500.0), 0x72C64 (1/1024),
         0x72C68 (0.6), 0x72C6C (-2.8), 0x72C70 (0.7), 0x138B8 (-0.045)

Semantics (3 stages):
  * dev = RPM - lambda, stored to A728; table = (enable==0 ? sel==0 ? 0x6A868
    : 0x6A87C : flag2==1 ? 0x6A868 : 0x6A87C); lookup(dev) stored to A720.
  * gate (flag3@AADA): fr15 = A720 if (1500 > RPM) and (gain > ect or
    u16(A424) >= u16(0x72C5C) unsigned), else fr15 = 0.  (NOTE the inverted
    sense vs the lift's "RPM above threshold -> adapt": here adaptation is
    gated OFF above 1500 RPM.)
  * A730 status: =1 if lam2 >= 0.6; =0 if lam2 < 0.555 (0.6-0.045); unchanged
    if 0.555 <= lam2 < 0.6.  If final A730==1: fr15 = clamp(fr15,-2.8,0.7)
    (via 0x2404).  A718 = fr15.  r0 = final A730 byte.

Lift note: c/calc_adaptive_fuel_trim.c is a BEHAVIORAL sketch; several details
are wrong (dev = RPM - lambda, not RPM - prev-trim; the table-select/flag
logic; the A730 status band; the gate polarity; the clamp via 0x2404).  This
test pins the ACTUAL ROM behavior; the lift should be corrected from it.

Run from repo root:  python3 c/tests/test_calc_adaptive_fuel_trim_1379C.py [N]
                     (N = random vectors per seed; default 1000 x 5 seeds)
"""
import math, os, random, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2, ts  # noqa: E402

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')
ADDR = 0x1379C

# ---- RAM cells ----
B5B8 = 0xFFFFB5B8   # f32 RPM
B5C4 = 0xFFFFB5C4   # f32 lambda
C12C = 0xFFFFC12C   # f32 lambda2
B5A4 = 0xFFFFB5A4   # u8 enable
B5AC = 0xFFFFB5AC   # u8 table-select
B5AA = 0xFFFFB5AA   # u8 flag2
AADA = 0xFFFFAADA   # u8 flag3
C084 = 0xFFFFC084   # f32 ect
A424 = 0xFFFFA424   # u16 counter
A720 = 0xFFFFA720   # f32 lookup / prev-trim (written then read)
A730 = 0xFFFFA730   # u8 status (in/out)
A728 = 0xFFFFA728   # f32 dev (write)
A718 = 0xFFFFA718   # f32 out (write)

FOOTPRINT = set()
for _a in (A728, A720, A718):
    for _i in range(4):
        FOOTPRINT.add(_a + _i)
FOOTPRINT.add(A730)
STACK_LO = 0xFFFFDEE0   # emulator stack writes land in 0xFFFFDEE0..0xFFFFDF00
STACK_HI = 0xFFFFDF00

f32bits = lambda x: struct.unpack('>I', struct.pack('>f', ts(x)))[0]


def getf(ram, a):
    return ts(struct.unpack('>f', bytes(ram.get(a + i, 0) for i in range(4)))[0])


def putf(ram, a, v):
    b = struct.pack('>f', ts(v))
    for i in range(4):
        ram[a + i] = b[i]


class Tables:
    """ROM 1-D tables read straight from the binary (mode-4 = u8 cells)."""
    def __init__(self, rom):
        self.d = rom

    def data_lookup(self, n, axis, x):
        # mirrors ROM 0x2624: index of lower breakpoint + fraction (f32 steps)
        if not (x < axis[n - 1]):           # x >= axis[n-1] or NaN
            return n - 1, 0.0
        i = n - 2
        while i > 0 and axis[i] > x:
            i -= 1
        if i == 0 and axis[0] > x:
            return 0, 0.0
        t1 = ts(x - axis[i])
        t2 = ts(axis[i + 1] - axis[i])
        return i, ts(t1 / t2)

    def lookup1(self, desc, x):
        d = self.d
        n = struct.unpack('>H', d[desc:desc + 2])[0]
        mode = d[desc + 2]
        axis_a = struct.unpack('>I', d[desc + 4:desc + 8])[0]
        vals_a = struct.unpack('>I', d[desc + 8:desc + 12])[0]
        scale = struct.unpack('>f', d[desc + 12:desc + 16])[0]
        off = struct.unpack('>f', d[desc + 16:desc + 20])[0]
        if mode not in (1, 4):
            raise AssertionError('unexpected table mode %d @%X' % (mode, desc))
        axis = [struct.unpack('>f', d[axis_a + 4 * i:axis_a + 4 * i + 4])[0]
                for i in range(n)]
        vals = list(d[vals_a:vals_a + n])       # u8 cells
        i, t = self.data_lookup(n, axis, ts(x))
        v0 = float(vals[i])
        if t == 0.0:
            interp = v0                          # handler: frac==0 -> skip fmac
        else:
            v1 = float(vals[i + 1])
            interp = ts(t * ts(v1 - v0) + v0)    # fmac: f0*fm+fn
        return ts(scale * interp + off)          # mode!=0: scale*x+off


def clamp_sel(x, lo, hi):
    """ROM 0x2404: clamp x to [lo,hi]; NaN -> hi (fcmp NaN == False)."""
    return hi if not (hi > x) else (x if x > lo else lo)


def ref(t, tb, rom):
    """Pure-Python model of 0x1379C — mirrors the disasm exactly."""
    rpm, lam, lam2 = ts(t['rpm']), ts(t['lam']), ts(t['lam2'])
    ect = ts(t['ect'])
    enable, sel = t['enable'] & 0xFF, t['sel'] & 0xFF
    flag2, flag3 = t['flag2'] & 0xFF, t['flag3'] & 0xFF
    status = t['status'] & 0xFF

    # ---- stage 1: deviation + table lookup ----
    dev = ts(rpm - lam)                          # fsub fr3,fr2
    if enable == 0:
        desc = 0x6A868 if sel == 0 else 0x6A87C
    else:
        desc = 0x6A868 if flag2 == 1 else 0x6A87C
    v = tb.lookup1(desc, dev)

    # ---- stage 2: gate (flag3@AADA) ----
    fr15 = 0.0
    if flag3 == 1:
        if ts(1500.0) > rpm:                     # fcmp/gt fr15,fr3 -> 1500 > rpm
            gain = ts(0.009765625)               # ROM 0x72C64
            if gain > ect:                       # fcmp/gt fr1,fr2 -> gain > ect
                fr15 = v
            else:
                c16 = struct.unpack('>h', struct.pack('>H', t['cnt'] & 0xFFFF))[0]
                thr = struct.unpack('>h', rom[0x72C5C:0x72C5C + 2])[0]
                if (c16 & 0xFFFFFFFF) >= (thr & 0xFFFFFFFF):   # cmp/hs unsigned
                    fr15 = v
                else:
                    fr15 = 0.0
        # else fr15 stays 0.0

    # ---- stage 3: A730 status band + clamp ----
    c = struct.unpack('>f', rom[0x138B8:0x138B8 + 4])[0]   # -0.045
    ns = status
    if ts(0.6) > lam2:                           # fcmp/gt fr14,fr5 -> 0.6 > lam2
        fr4 = ts(ts(0.6) + c)                    # fadd fr3,fr4
        if fr4 > lam2:                           # fcmp/gt fr14,fr4
            ns = 0
        # else: A730 unchanged (no write)
    else:
        ns = 1
    if ns == 1:
        fr15 = clamp_sel(fr15, ts(-2.8), ts(0.7))
    return dev, v, ns, fr15


def build_ram(t):
    ram = {}
    putf(ram, B5B8, t['rpm']); putf(ram, B5C4, t['lam'])
    putf(ram, C12C, t['lam2']); putf(ram, C084, t['ect'])
    putf(ram, A720, t['prev'])                   # dead value (overwritten)
    for k, a in (('enable', B5A4), ('sel', B5AC), ('flag2', B5AA),
                 ('flag3', AADA), ('status', A730)):
        ram[a] = t[k] & 0xFF
    ram[A424] = (t['cnt'] >> 8) & 0xFF
    ram[A424 + 1] = t['cnt'] & 0xFF
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    tb = Tables(rom)
    seeds = (0x1379C, 0x6A868, 0xA720, 0x1234, 0x5EED)
    tests = fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        vectors = []
        lam2_band = (0.4, 0.5, 0.554, 0.555, 0.556, 0.599, 0.6, 0.601, 0.7)
        for _ in range(N):
            def rf(lo=-6000, hi=20000):
                r = rng.random()
                if r < 0.10:
                    return rng.choice((-5000.0, -100.0, 0.0, 1499.0, 1500.0,
                                       1501.0, 8000.0))
                if r < 0.13:
                    return float('nan')
                return rng.uniform(lo, hi)
            lam2 = rng.choice(lam2_band) if rng.random() < 0.30 \
                else rng.uniform(-2, 2)
            vectors.append(dict(
                rpm=rf(), lam=rf(-10, 10), lam2=lam2, ect=rf(-100, 300),
                enable=rng.getrandbits(8), sel=rng.getrandbits(8),
                flag2=rng.getrandbits(8), flag3=rng.getrandbits(8),
                status=rng.getrandbits(8), cnt=rng.getrandbits(16),
                prev=rng.uniform(-5, 5)))

        for t in vectors:
            ram = build_ram(t)
            r0 = cpu.call(ADDR, ram=ram)
            got = (tuple(struct.unpack('>I', bytes(cpu.ram.get(a + i, 0)
                                                   for i in range(4)))[0]
                         for a in (A728, A720, A718))
                   + (cpu.ram.get(A730, 0), r0))
            m = ref(t, tb, rom)
            exp = (f32bits(m[0]), f32bits(m[1]), f32bits(m[3]), m[2], m[2])
            tests += 1
            if got != exp:
                fails += 1
                if fails <= 10:
                    print("FAIL seed=0x%X %s" % (seed, t))
                    print("  emu: A728=%08X A720=%08X A718=%08X A730=%02X r0=%08X" % got)
                    print("  mod: A728=%08X A720=%08X A718=%08X A730=%02X r0=%08X" % exp)
            for a in cpu.ram:
                if a in FOOTPRINT or a in ram or STACK_LO <= a <= STACK_HI:
                    continue
                fails += 1
                if fails <= 10:
                    print("FAIL(unexpected write) 0x%08X = %d" % (a, cpu.ram[a]))
            if fails >= 10:
                break
        if fails:
            break

    print(f"calc_adaptive_fuel_trim_1379C @0x1379C: {tests} tests, {fails} failures")
    if fails == 0:
        print(f"OK  calc_adaptive_fuel_trim @0x1379C  ({tests} inputs, 0 mismatches)")
        return 0
    print(f"FAIL calc_adaptive_fuel_trim @0x1379C  ({fails} mismatches)")
    return 1


if __name__ == '__main__':
    sys.exit(main())
