#!/usr/bin/env python3
"""
Test calc_fuel_pump_duty_trim (0x135F6) against the emulator.

The function reads a calibration "mode" byte and picks one of three trim
strategies, all operating on global RAM (floats) rather than integer args, so
we seed the RAM overlay before each call and verify the output floats:

  mode 0 (default): base_duty @0xFFFFA6F4 = float @0xFFFFA63C
  mode 1 (active):  front @0xFFFFA6E4 = ts(base + A + B)
                    rear  @0xFFFFA6E8 = ts(base + C + D)
  mode 2 (safe):    front @0xFFFFA6E4 = float @0x0006E438
                    rear  @0xFFFFA6E8 = float @0x0006E43C
  any other mode:   no writes at all

Every address below is extracted from the ROM's own literal pool by
get_ram_addrs() — nothing is hardcoded from the C lift, so this test does NOT
depend on c/calc_fuel_pump_duty_trim.c (which is being edited in parallel).
The mode byte is stored in ROM at 0x0006E430 (stock value 0x00); the test
overrides it via the emulator's RAM overlay to reach modes 1/2/3.

Float arithmetic: the emulator rounds every fadd to IEEE single precision
(ts()), so the model rounds identically at each step.

Run from repo root:  python3 c/tests/test_calc_fuel_pump_duty_trim.py [N]
"""
import os, random, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
RE = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(RE, 'tools'))
from sh2emu import SH2, ts

ROM = os.path.join(RE, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x135F6

# Literal-pool offsets inside calc_fuel_pump_duty_trim (mov.w / mov.l targets).
W16_LITS = {  # symbolic name -> word literal address (0xFFFFxxxx)
    'BASE_DUTY': 0x136B2,   # r5: base duty cycle (input / mode-0 output)
    'MODE0_SRC': 0x136B4,   # r2: mode-0 calibration source float
    'OUT_FRONT': 0x136B6,   # r7: front channel duty output
    'COMP_A':    0x136B8,   # r3: mode-1 front comp 1
    'COMP_B':    0x136BA,   # r2: mode-1 front comp 2
    'COMP_C':    0x136BC,   # r1: mode-1 rear comp 1
    'COMP_D':    0x136BE,   # r3: mode-1 rear comp 2
    'OUT_REAR':  0x136C0,   # r2: rear channel duty output
}
W32_LITS = {  # symbolic name -> dword literal address (ROM/32-bit addr)
    'MODE_BYTE': 0x136D8,   # r6: mode selector byte address (0x0006E430)
    'SAFE_FRONT': 0x136DC,  # r3: mode-2 safe front float address
    'SAFE_REAR':  0x136E0,  # r2: mode-2 safe rear float address
}

FAIL = 0
CHECKS = [0]


def check(cond, msg):
    global FAIL
    CHECKS[0] += 1
    if not cond:
        FAIL += 1
        print("FAIL: " + msg)


def get_ram_addrs(rom):
    """Extract every address the function uses straight from the ROM literal
    pool (the 16-bit RAM offsets are all in the 0xFFFF???? high-RAM space; the
    32-bit literals point at ROM calibration bytes/floats).  Returns a dict of
    symbolic name -> full address."""
    addrs = {}
    for name, lit in W16_LITS.items():
        addrs[name] = 0xFFFF0000 | int.from_bytes(rom[lit:lit + 2], 'big')
    for name, lit in W32_LITS.items():
        addrs[name] = int.from_bytes(rom[lit:lit + 4], 'big')
    return addrs


def put_f(ram, a, v):
    for i, b in enumerate(struct.pack('>f', v)):
        ram[a + i] = b


def model(mode, base, comp, mode0_src, safe_front, safe_rear):
    """Python port of the ROM behaviour.  Returns a dict of
    {name: ('write', value)} for every float the mode writes.  All inputs are
    single-precision floats in RAM (the emulator rounds them on read), so the
    model rounds each operand and each fadd with ts() to match bit-for-bit."""
    # inputs arrive as doubles from rng.uniform() but are stored/read as
    # single-precision floats, so round them first
    base = ts(base)
    comp = {k: ts(v) for k, v in comp.items()}
    out = {}
    if mode == 0:
        out['BASE_DUTY'] = ('write', ts(mode0_src))
    if mode == 1:
        front = ts(ts(base + comp['A']) + comp['B'])
        rear = ts(ts(base + comp['C']) + comp['D'])
        out['OUT_FRONT'] = ('write', front)
        out['OUT_REAR'] = ('write', rear)
    if mode == 2:
        out['OUT_FRONT'] = ('write', ts(safe_front))
        out['OUT_REAR'] = ('write', ts(safe_rear))
    return out


def run_case(cpu, addrs, mode, base, comp, mode0_src, safe_front, safe_rear):
    """Seed the RAM overlay (mode byte + all inputs incl. the safe floats,
    which live in ROM but are overridable via the overlay) and run the
    function.  Returns {addr: float} of the three watched floats."""
    ram = {addrs['MODE_BYTE']: mode}
    put_f(ram, addrs['BASE_DUTY'], base)
    put_f(ram, addrs['COMP_A'], comp['A'])
    put_f(ram, addrs['COMP_B'], comp['B'])
    put_f(ram, addrs['COMP_C'], comp['C'])
    put_f(ram, addrs['COMP_D'], comp['D'])
    put_f(ram, addrs['MODE0_SRC'], mode0_src)
    put_f(ram, addrs['SAFE_FRONT'], safe_front)
    put_f(ram, addrs['SAFE_REAR'], safe_rear)
    # pre-seed the outputs too, so "untouched" cases can be detected
    put_f(ram, addrs['OUT_FRONT'], 99.0)
    put_f(ram, addrs['OUT_REAR'], 98.0)
    cpu.call(ENTRY, ram=ram)
    return {
        'BASE_DUTY': cpu.rdf(addrs['BASE_DUTY']),
        'OUT_FRONT': cpu.rdf(addrs['OUT_FRONT']),
        'OUT_REAR': cpu.rdf(addrs['OUT_REAR']),
    }


def test_mode_0_default(cpu, addrs, rng, N):
    """Mode 0: base duty becomes the mode-0 source float; outputs untouched."""
    for _ in range(N):
        mode0_src = rng.uniform(-50, 150)
        got = run_case(cpu, addrs, 0, base=rng.uniform(0, 100),
                       comp={k: 0.0 for k in 'ABCD'}, mode0_src=mode0_src,
                       safe_front=0.0, safe_rear=0.0)
        check(got['BASE_DUTY'] == ts(mode0_src),
              "mode 0: base duty 0x%X = %.6g expected %.6g"
              % (addrs['BASE_DUTY'], got['BASE_DUTY'], ts(mode0_src)))
        check(got['OUT_FRONT'] == 99.0 and got['OUT_REAR'] == 98.0,
              "mode 0: outputs must be untouched (front=%.6g rear=%.6g)"
              % (got['OUT_FRONT'], got['OUT_REAR']))
    print("OK  mode 0 (default): base duty copied, outputs untouched (%d random)" % N)


def test_mode_1_active_trim(cpu, addrs, rng, N):
    """Mode 1: front = ts(ts(ts(base)+ts(A))+ts(B)), rear likewise with C/D."""
    for _ in range(N):
        base = rng.uniform(0, 100)
        comp = {k: rng.uniform(-20, 40) for k in 'ABCD'}
        got = run_case(cpu, addrs, 1, base=base, comp=comp,
                       mode0_src=0.0, safe_front=0.0, safe_rear=0.0)
        exp = model(1, base, comp, 0.0, 0.0, 0.0)
        check(got['OUT_FRONT'] == exp['OUT_FRONT'][1],
              "mode 1: front = %.6g expected %.6g (base=%.6g A=%.6g B=%.6g)"
              % (got['OUT_FRONT'], exp['OUT_FRONT'][1], ts(base), ts(comp['A']), ts(comp['B'])))
        check(got['OUT_REAR'] == exp['OUT_REAR'][1],
              "mode 1: rear = %.6g expected %.6g (base=%.6g C=%.6g D=%.6g)"
              % (got['OUT_REAR'], exp['OUT_REAR'][1], ts(base), ts(comp['C']), ts(comp['D'])))
    print("OK  mode 1 (active trim): front/rear = base + comps (%d random)" % N)


def test_mode_2_safe(cpu, addrs, rng, N):
    """Mode 2: front/rear outputs become the safe calibration floats."""
    for _ in range(N):
        safe_front = rng.uniform(0, 100)
        safe_rear = rng.uniform(0, 100)
        got = run_case(cpu, addrs, 2, base=rng.uniform(0, 100),
                       comp={k: 0.0 for k in 'ABCD'}, mode0_src=0.0,
                       safe_front=safe_front, safe_rear=safe_rear)
        check(got['OUT_FRONT'] == ts(safe_front),
              "mode 2: front = %.6g expected %.6g" % (got['OUT_FRONT'], ts(safe_front)))
        check(got['OUT_REAR'] == ts(safe_rear),
              "mode 2: rear = %.6g expected %.6g" % (got['OUT_REAR'], ts(safe_rear))
              )
    print("OK  mode 2 (safe): ROM defaults loaded to both outputs (%d random)" % N)


def test_mode_other_no_writes(cpu, addrs, rng, N):
    """Any mode byte outside {0,1,2} performs no writes at all."""
    for _ in range(N):
        mode = rng.choice([3, 0x7F, 0xFE, 0xFF])
        got = run_case(cpu, addrs, mode, base=10.0,
                       comp={k: 5.0 for k in 'ABCD'}, mode0_src=7.0,
                       safe_front=11.0, safe_rear=22.0)
        check(got['BASE_DUTY'] == 10.0 and got['OUT_FRONT'] == 99.0
              and got['OUT_REAR'] == 98.0,
              "mode 0x%02X: expected no writes (base=%.6g front=%.6g rear=%.6g)"
              % (mode, got['BASE_DUTY'], got['OUT_FRONT'], got['OUT_REAR']))
    print("OK  mode other: no writes (%d random)" % N)


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    if not os.path.exists(ROM):
        print("FAIL: ROM not found: %s" % ROM)
        sys.exit(1)
    rom = open(ROM, 'rb').read()
    addrs = get_ram_addrs(rom)
    cpu = SH2(rom)
    rng = random.Random(0x135F6)

    print("calc_fuel_pump_duty_trim (0x135F6) — emulator vs ROM-derived model")
    print("  addresses from ROM literal pool: %s"
          % {k: '0x%08X' % v for k, v in sorted(addrs.items())})

    test_mode_0_default(cpu, addrs, rng, N)
    test_mode_1_active_trim(cpu, addrs, rng, N)
    test_mode_2_safe(cpu, addrs, rng, N)
    test_mode_other_no_writes(cpu, addrs, rng, N)

    print("%d checks, %d failures" % (CHECKS[0], FAIL))
    print("Coverage: modes 0/1/2 + non-standard mode byte, %d random states each."
          % N)
    # NOTE: this suite verifies the emulated ROM directly against a model
    # derived from the ROM bytes.  It does not compile c/calc_fuel_pump_duty_trim.c
    # (owned by another agent being edited in parallel), so it cannot be blocked
    # by the state of that file.  Cross-checking the C lift is done elsewhere
    # (c/tests/verify_emu.py / make c-test).
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == '__main__':
    main()
