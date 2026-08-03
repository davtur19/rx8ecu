#!/usr/bin/env python3
"""
test_o2_lambda_more.py — differential bit-exact tests for the 6 uncovered
O2/lambda functions in c/o2_lambda_subsystem.c (addr_cov.tsv rows SCOPERTO):

    0x012B54  write_o2_sensor_trim         (copies 0xFFFFB5AC -> 0xFFFFA6A2)
    0x01412A  read_o2_sensor_voltage_trim  (warm-up counter, inc-sat, skip>=21)
    0x01418C  calc_lambda_integration_time (u16 timer: reload 7 / countdown)
    0x0141B8  calc_closed_loop_fuel_status (front/rear idx + voltage->STFT)
    0x01437C  calc_engine_temp_fuel_trim   (table1D_lookup @0x2068, 2 tables)
    0x01E794  getRearO2FilteredValue       (slew-filter @0x23B0 + rich/lean)

NOTE on the address table: addr_cov.tsv lists `01E794 getRearO2FilteredValue`
for o2_lambda_subsystem.c.  The task brief said 0x1E812, but 0x1E812 is DATA
inside the literal pool of 0x1E794 (it holds the 0x2404 function pointer), not
a function.  The real function is 0x1E794, so that is what is tested here.

Method (repo Track-A pattern): the REAL ROM bytes of each function are executed
in the SH-2E emulator (tools/sh2emu.py) with a seeded random RAM overlay — all
callee helpers (0x2500 fmac, 0x2478 inc-sat, 0x14220/0x142E8 index searches,
0x3ED0C div/edge-values, 0x2404 clamp, 0x2068 table1D_lookup, 0x23B0 filter)
run for real — and the resulting RAM overlay + r0 are compared bit-exactly
against a pure-Python model derived from the disassembly.

IMPORTANT emulator-semantics notes (all verified against emulator probes):
  * fcmp/gt Fm,Fn sets T = (FRn > FRm) in sh2emu (reversed w.r.t. the usual
    disasm text).  Every model below uses the VERIFIED direction.
  * table1D_lookup: data_lookup (0x2624) returns i + fraction, but the
    above-max path (x >= axis[n-1] or NaN) returns fraction 0.0 with i = n-1
    (fr0 is zeroed in the rts delay slot), and the below-min path returns
    (0, 0.0).  The mode-4 handler reads vals[i] (r0 = vals[i]) when the
    fraction is 0, else vals[i+1].  All FMAC/FSUB/FDIV results are
    single-precision rounded via ts().
  * calc_closed_loop_fuel_status: STFT_A/B = clamp((V-5)/55, 0, 1) * idx_val
    where idx_val = -50 + 0.5*lookup[idx] (20.0 for idx<=8, 0.0 for idx>=9;
    lookup byte is 140/100).  r0 at exit = 0x72E40 (rear lookup base, left by
    the last helper call).
  * getRearO2FilteredValue: filtered = filter_23B0(raw, prev, 0.25, 1e-5);
    flag = 1 (lean) when ref <= filtered, else 0 (rich) — the second-stage
    dead-band collapses because thresh_hi @0x71588 == 0.0.  r0 = bits(prev)
    & 0x7F800000 on the lean path, 0 on the rich path.
  * calc_engine_temp_fuel_trim: open-loop branch is "0.5 > coolant" -> 0
    (fcmp/gt fr2,fr3 with fr3=0.5); closed-loop flag byte @0x72E58 is 0x40
    (always take the lookup).  Table @0x6A8E0 (open loop, scale 0.5 / off
    -40) vs @0x6A8F4 (closed loop, flat 80 -> always 0).

Exit code 0 only when every function reports 0 mismatches over all vectors.

Run from repo root:  python3 c/tests/test_o2_lambda_more.py [N]
                     (N = random vectors per seed; default 500 x 6 =
                      3000 random + directed vectors per function)
"""
import math, os, random, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2, ts  # noqa: E402

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')

# ---------------- helper cell constants ----------------
B5AC = 0xFFFFB5AC   # u8  o2 status B (source)
A6A2 = 0xFFFFA6A2   # u8  trim output
A768 = 0xFFFFA768   # u8  o2 readiness counter
ADC8 = 0xFFFFADC8   # f32 engine speed signal (lam integration timer)
A772 = 0xFFFFA772   # u16 integration timer
AA10 = 0xFFFFAA10   # f32 front O2 voltage (STFT)
A784 = 0xFFFFA784   # u8  front O2 lookup idx
A785 = 0xFFFFA785   # u8  rear  O2 lookup idx
A77C = 0xFFFFA77C   # f32 front trim idx result
A780 = 0xFFFFA780   # f32 rear  trim idx result
A760 = 0xFFFFA760   # f32 STFT bank A
A764 = 0xFFFFA764   # f32 STFT bank B
AADA = 0xFFFFAADA   # u8  closed-loop active flag
AE54 = 0xFFFFAE54   # f32 engine-temp-trim lookup input
C12C = 0xFFFFC12C   # f32 coolant temp
A788 = 0xFFFFA788   # f32 engine-temp-trim output
A78C = 0xFFFFA78C   # f32 engine-temp-trim output duplicate
B0F0 = 0xFFFFB0F0   # f32 rear O2 filtered
AD98 = 0xFFFFAD98   # f32 rear O2 raw
B0E8 = 0xFFFFB0E8   # f32 rear O2 reference
B0EC = 0xFFFFB0EC   # u8  rear O2 rich/lean flag

STACK_LO = 0xFFFFDEE0
STACK_HI = 0xFFFFDF00

f32bits = lambda x: struct.unpack('>I', struct.pack('>f', ts(x)))[0]


def getf(ram, a):
    return ts(struct.unpack('>f', bytes(ram.get(a + i, 0) for i in range(4)))[0])


def putf(ram, a, v):
    b = struct.pack('>f', ts(v))
    for i in range(4):
        ram[a + i] = b[i]


def put16(ram, a, v):
    ram[a] = (v >> 8) & 0xFF
    ram[a + 1] = v & 0xFF


def get16(ram, a):
    return (ram.get(a, 0) << 8) | ram.get(a + 1, 0)


# ---------------- ROM table reader (mirrors table1D_lookup @0x2068) --------
class Tables:
    """ROM 1-D tables read straight from the binary (mode-4 = u8 cells)."""
    def __init__(self, rom):
        self.d = rom

    def data_lookup(self, n, axis, x):
        """0x2624: returns (i, frac).  Above-max and below-min give frac 0.0
        (fr0 zeroed in the rts delay slot), above-max gives i = n-1."""
        if not (x < axis[n - 1]):          # x >= axis[n-1] or NaN -> above-max
            return (n - 1, 0.0)
        if n == 1:
            return (0, 0.0)
        i = n - 2
        while axis[i] > x:
            i -= 1
            if i < 0:
                return (0, 0.0)            # below-min
        frac = ts(ts(x - axis[i]) / ts(axis[i + 1] - axis[i]))
        return (i, frac)

    def lookup1(self, desc, x):
        """(result, r0) — mirrors ROM 0x2068 + 0x26B0 + 0x2624 exactly."""
        d = self.d
        n = struct.unpack('>H', d[desc:desc + 2])[0]
        mode = d[desc + 2]
        axis_a = struct.unpack('>I', d[desc + 4:desc + 8])[0]
        vals_a = struct.unpack('>I', d[desc + 8:desc + 12])[0]
        scale = struct.unpack('>f', d[desc + 12:desc + 16])[0]
        off = struct.unpack('>f', d[desc + 16:desc + 20])[0]
        axis = [struct.unpack('>f', d[axis_a + 4 * i:axis_a + 4 * i + 4])[0]
                for i in range(n)]
        vals = list(d[vals_a:vals_a + n])   # u8 cells
        i, frac = self.data_lookup(n, axis, ts(x))
        # handler 0x26B0 (mode 4)
        v0 = float(vals[i])
        if frac == 0.0:                     # fcmp/eq fr0,fr2 -> (0 == frac)
            interp = v0
            r0 = vals[i]
        else:
            v1 = float(vals[i + 1])
            interp = ts(frac * ts(v1 - v0) + v0)    # fmac: ts(f0*fm+fn)
            r0 = vals[i + 1]
        # 0x2068 tail (mode != 0): fmac fr0=scale, fr2=interp, fr1=off
        result = ts(scale * interp + off)
        return result, r0


# ---------------- small ROM helpers used by the models ----------------
def clamp_sel(x, lo, hi):
    """ROM 0x2404: result = lo if NOT(x>lo) else (hi if hi>x else x)."""
    if not (x > lo):
        return lo
    return x if hi > x else hi


def func_3ED0C(x, rng):
    """ROM 0x3ED0C: if rng==0 -> (x==0 ? 0 : sign*3.4028228579130005e+38),
    else x/rng."""
    if rng == 0.0:
        if x == 0.0:
            return 0.0
        return 3.4028228579130005e+38 if x > 0.0 else -3.4028228579130005e+38
    return ts(x / rng)


def filter23B0(raw, prev, alpha, eps):
    """ROM 0x23B0 slew filter.  prev Inf/NaN -> raw; new =
    (1-alpha)*(prev-raw)+raw; result = raw if eps > |raw-new| else new."""
    if (f32bits(prev) & 0x7F800000) == 0x7F800000:      # prev Inf/NaN
        return raw
    d = ts(prev - raw)                                  # fsub fr4,fr5
    one_minus = ts(1.0 - alpha)                         # fsub fr6,fr0
    new = ts(one_minus * d + raw)                       # fmac
    diff = ts(raw - new)                                # fsub fr6,fr5
    if eps > abs(diff):                                 # fcmp/gt fr5,fr7
        return raw
    return new


def o2_idx(o2_state, thresh, max_idx):
    """sub_014220/0142E8 index search (emulator fcmp/gt semantics)."""
    if not (thresh[0] > o2_state):                      # o2_state >= thresh[0]
        if not (thresh[max_idx] > o2_state):            # o2_state >= thresh[max]
            return max_idx
        i = 0
        while i < max_idx:
            if not (thresh[i] > o2_state) and (thresh[i + 1] > o2_state):
                return i
            i += 1
        return max_idx
    return 0                                            # o2_state < thresh[0]


def o2_map(o2_state, thresh_base, size_addr, lookup_base, rom):
    """Full sub_0142xx: (stored_idx, result_float = 0.5*lookup[idx] - 50)."""
    size = rom[size_addr]
    max_idx = (size + 0xFF) & 0xFF
    thresh = [struct.unpack('>f', rom[thresh_base + 4 * i:thresh_base + 4 * i + 4])[0]
              for i in range(max_idx + 2)]
    idx = o2_idx(o2_state, thresh, max_idx)
    byte = rom[lookup_base + idx]
    return idx, ts(0.5 * byte + (-50.0))                # fmac helper 0x2500


# ---------------- models per function ----------------
def ref_write_trim(t):
    return (t['src'] & 0xFF, 0)                          # (A6A2, r0)


def ref_read_trim(t):
    counter = t['counter'] & 0xFF
    if counter >= 21:                                    # cmp/ge 21 -> skip
        return (counter, 0)
    new = min(counter + 1, 255)                          # inc_sat(0x2478)
    return (new, new)


def ref_lam_time(t):
    speed = ts(t['speed'])
    timer = t['timer'] & 0xFFFF
    if 2.5 > speed:                                      # fcmp/gt fr2,fr3
        if timer > 0:                                    # cmp/pl
            return (timer - 1, 0)
        return (0, 0)
    return (7, 7)                                        # reload, r0 = 7


def ref_closed_loop(t, rom):
    counter = t['counter'] & 0xFF
    volt = ts(t['volt'])
    o2_state = float(counter)
    idxF, resF = o2_map(o2_state, 0x72D78, 0x6A8B9, 0x72DD0, rom)
    idxR, resR = o2_map(o2_state, 0x72DE8, 0x6A8CD, 0x72E40, rom)
    x = ts(volt - 5.0)                                   # fsub fr3,fr4
    rng = ts(60.0 - 5.0)                                 # fsub fr3,fr5 -> 55
    tri = func_3ED0C(x, rng)
    c = clamp_sel(tri, 0.0, 1.0)
    stft_a = ts(resF * c)
    stft_b = ts(resR * c)
    return (idxF, idxR, resF, resR, stft_a, stft_b, 0x72E40)


def ref_engine_temp(t, tb):
    cla = t['cla'] & 0xFF
    x = ts(t['x'])
    cool = ts(t['cool'])
    if cla == 1:
        if tb.d[0x72E58] != 0:                           # tst [0x72E58] (0x40)
            res, r0 = tb.lookup1(0x6A8F4, x)
            return (res, res, r0)
        return (0.0, 0.0, tb.d[0x72E58])                 # r0 = [0x72E58] == 0
    if 0.5 > cool:                                       # fcmp/gt fr2,fr3
        return (0.0, 0.0, cla)                           # cold -> 0, r0 = cla
    res, r0 = tb.lookup1(0x6A8E0, x)
    return (res, res, r0)


def ref_rear_filtered(t):
    prev, raw, ref = ts(t['prev']), ts(t['raw']), ts(t['ref'])
    filtered = filter23B0(raw, prev, 0.25, 9.999999747378752e-06)
    if ref > filtered:                                   # fcmp/gt fr3,fr4
        return (filtered, 0, 0)                          # rich: flag 0, r0 0
    return (filtered, 1, f32bits(prev) & 0x7F800000)     # lean


# ---------------- generic differential runner ----------------
def run_suite(name, addr, writes, ref, gen, rom, N, directed):
    """writes: list of (kind, addr) kinds 'u8'/'u16'/'f32'.  gen(rng)->dict
    with '_ram' overlay + scalar keys used by the ref model."""
    tests = fails = 0
    rng = random.Random(0x5EED)
    vectors = [dict(d) for d in directed]
    for _ in range(N):
        vectors.append(gen(rng))
    cpu = SH2(rom)
    write_addrs = set()
    for k, a in writes:
        n = 1 if k == 'u8' else (2 if k == 'u16' else 4)
        for i in range(n):
            write_addrs.add(a + i)
    for t in vectors:
        ram = t['_ram']
        r0 = cpu.call(addr, ram=ram)
        got = []
        for k, a in writes:
            if k == 'u8':
                got.append(cpu.ram.get(a, 0))
            elif k == 'u16':
                got.append(get16(cpu.ram, a))
            else:
                got.append(f32bits(getf(cpu.ram, a)))
        got.append(cpu.r[0])
        m = list(ref(t))
        exp = []
        for k, a in writes:
            if k == 'u8':
                exp.append(m.pop(0) & 0xFF)
            elif k == 'u16':
                exp.append(m.pop(0) & 0xFFFF)
            else:
                exp.append(f32bits(m.pop(0)))
        exp.append(m.pop(0))
        bad = got != exp
        if not bad:
            for a in cpu.ram:
                if a in ram or a in write_addrs or STACK_LO <= a <= STACK_HI:
                    continue
                bad = True
                break
        tests += 1
        if bad:
            fails += 1
            if fails <= 8:
                print('FAIL %s %s' % (name, t))
                print('  emu: %s' % (tuple(got),))
                print('  mod: %s' % (tuple(exp),))
        if fails >= 10:
            break
    return tests, fails


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    rom = open(ROM, 'rb').read()
    tb = Tables(rom)
    results = []
    total = 0

    # 1) write_o2_sensor_trim
    def gen_write(rng):
        src = rng.getrandbits(8)
        return {'_ram': {B5AC: src}, 'src': src}
    directed = [{'src': v, '_ram': {B5AC: v}}
                for v in (0x00, 0x01, 0x7F, 0x80, 0x42, 0xFF)]
    t, f = run_suite('write_o2_sensor_trim', 0x12B54, [('u8', A6A2)],
                     ref_write_trim, gen_write, rom, N, directed)
    results.append(('write_o2_sensor_trim', t, f)); total += f

    # 2) read_o2_sensor_voltage_trim
    def gen_read(rng):
        c = rng.getrandbits(8)
        return {'_ram': {A768: c}, 'counter': c}
    directed = [{'counter': v, '_ram': {A768: v}}
                for v in (0, 1, 20, 21, 22, 100, 254, 255)]
    t, f = run_suite('read_o2_sensor_voltage_trim', 0x1412A, [('u8', A768)],
                     ref_read_trim, gen_read, rom, N, directed)
    results.append(('read_o2_sensor_voltage_trim', t, f)); total += f

    # 3) calc_lambda_integration_time
    def gen_lam(rng):
        def rf():
            r = rng.random()
            if r < 0.12:
                return rng.choice((-1.0, 0.0, 2.49, 2.5, 2.51, 100.0, 8000.0))
            if r < 0.15:
                return float('nan')
            return rng.uniform(-10, 100)
        ram = {}
        putf(ram, ADC8, rf())
        put16(ram, A772, rng.getrandbits(16))
        return {'_ram': ram, 'speed': getf(ram, ADC8), 'timer': get16(ram, A772)}
    directed = []
    for s in (-1.0, 0.0, 2.49, 2.5, 2.51, 3.0, 100.0, float('nan')):
        for tv in (0, 1, 7, 65535):
            ram = {}
            putf(ram, ADC8, s)
            put16(ram, A772, tv)
            directed.append({'_ram': ram, 'speed': s, 'timer': tv})
    t, f = run_suite('calc_lambda_integration_time', 0x1418C, [('u16', A772)],
                     ref_lam_time, gen_lam, rom, N, directed)
    results.append(('calc_lambda_integration_time', t, f)); total += f

    # 4) calc_closed_loop_fuel_status
    def gen_cl(rng):
        counter = rng.getrandbits(8)
        r = rng.random()
        if r < 0.15:
            volt = rng.choice((-5.0, 0.0, 2.5, 5.0, 10.0, 55.0, 60.0, 100.0))
        elif r < 0.18:
            volt = float('nan')
        else:
            volt = rng.uniform(-20, 100)
        ram = {A768: counter}
        putf(ram, AA10, volt)
        return {'_ram': ram, 'counter': counter, 'volt': volt}
    directed = []
    for counter in (0, 1, 5, 8, 9, 21, 22, 255):
        for volt in (-5.0, 0.0, 2.5, 5.0, 10.0, 60.0, 100.0, float('nan')):
            ram = {A768: counter}
            putf(ram, AA10, volt)
            directed.append({'_ram': ram, 'counter': counter, 'volt': volt})
    t, f = run_suite('calc_closed_loop_fuel_status', 0x141B8,
                     [('u8', A784), ('u8', A785), ('f32', A77C), ('f32', A780),
                      ('f32', A760), ('f32', A764)],
                     (lambda t: ref_closed_loop(t, rom)), gen_cl, rom, N, directed)
    results.append(('calc_closed_loop_fuel_status', t, f)); total += f

    # 5) calc_engine_temp_fuel_trim
    def gen_et(rng):
        def rf():
            r = rng.random()
            if r < 0.12:
                return rng.choice((-100.0, 0.0, 20.0, 30.0, 50.0, 80.0, 100.0, 1000.0))
            if r < 0.15:
                return float('nan')
            return rng.uniform(-200, 2000)
        ram = {AADA: rng.getrandbits(8)}
        putf(ram, AE54, rf())
        if rng.random() < 0.1:
            cool = rng.choice((-10.0, 0.4, 0.5, 0.6, 100.0))
        else:
            cool = rng.uniform(-40, 150)
        putf(ram, C12C, cool)
        return {'_ram': ram, 'cla': ram[AADA], 'x': getf(ram, AE54),
                'cool': cool}
    directed = []
    for cla in (0, 1):
        for x in (-100.0, 0.0, 20.0, 30.0, 50.0, 100.0, 1000.0, float('nan')):
            for cool in (-10.0, 0.4, 0.5, 0.6, 100.0):
                ram = {AADA: cla}
                putf(ram, AE54, x)
                putf(ram, C12C, cool)
                directed.append({'_ram': ram, 'cla': cla,
                                 'x': ts(x), 'cool': cool})
    t, f = run_suite('calc_engine_temp_fuel_trim', 0x1437C,
                     [('f32', A788), ('f32', A78C)],
                     (lambda t: ref_engine_temp(t, tb)), gen_et, rom, N, directed)
    results.append(('calc_engine_temp_fuel_trim', t, f)); total += f

    # 6) getRearO2FilteredValue
    def gen_rf(rng):
        def ff():
            r = rng.random()
            if r < 0.10:
                return rng.choice((-1.0, 0.0, 0.5, 1.0, 5.0))
            if r < 0.14:
                return rng.choice((float('inf'), float('-inf'), float('nan')))
            return rng.uniform(-2, 8)
        ram = {}
        putf(ram, B0F0, ff())
        putf(ram, AD98, ff())
        putf(ram, B0E8, ff())
        return {'_ram': ram,
                'prev': getf(ram, B0F0), 'raw': getf(ram, AD98),
                'ref': getf(ram, B0E8)}
    directed = []
    for prev in (0.0, 0.5, 1.0, float('inf'), float('-inf'), float('nan')):
        for raw in (0.0, 0.5, 0.51, 1.0, 5.0):
            for ref in (0.0, 0.55, 1.0, 5.0):
                ram = {}
                putf(ram, B0F0, prev)
                putf(ram, AD98, raw)
                putf(ram, B0E8, ref)
                directed.append({'_ram': ram,
                                 'prev': ts(prev), 'raw': ts(raw), 'ref': ts(ref)})
    t, f = run_suite('getRearO2FilteredValue', 0x1E794,
                     [('f32', B0F0), ('u8', B0EC)],
                     ref_rear_filtered, gen_rf, rom, N, directed)
    results.append(('getRearO2FilteredValue', t, f)); total += f

    print('=' * 66)
    print('test_o2_lambda_more — differential O2/lambda tests')
    print('=' * 66)
    for name, t, f in results:
        print('  %s %s: %d tests, %d mismatches' % ('OK ' if f == 0 else 'FAIL',
                                                     name, t, f))
    print('=' * 66)
    if total == 0:
        print('OK  all 6 functions (%d inputs, 0 mismatches)'
              % sum(r[1] for r in results))
        return 0
    print('FAIL total %d mismatches' % total)
    return 1


if __name__ == '__main__':
    sys.exit(main())
