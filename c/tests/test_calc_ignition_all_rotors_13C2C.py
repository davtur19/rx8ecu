#!/usr/bin/env python3
"""
Regression test for calc_ignition_all_rotors_13C2C (ROM 0x13C2C, 60E1D400.bin).

The C lift at c/calc_ignition_all_rotors_13C2C.c is a BEHAVIORAL reconstruction:
the ROM routine operates on absolute on-chip RAM (0xFFFFA7xx), which cannot be
dereferenced by an x86 ctypes build.  Following the repo convention for RAM-
global lifts (see test_calc_fan1_control.py), this test:

  1. runs the ACTUAL ROM bytes of 0x13C2C — including helpers 0x13E6C,
     0x13ED2, 0x13EE6, the 1-D lookup 0x2068 and the saturate 0x2404 — in
     tools/sh2emu.py over seeded RAM states (the oracle), and
  2. compares the emulator's 8 output RAM words against a Python reference
     model that mirrors the rewritten C lift line-for-line.

The reference model encodes the five behavioral divergences that were fixed in
the C lift (see the NOTES block in the .c file):

  D1  Knock-active path compares BYTE@0xFFFFC0C7 >= BYTE@0x7983B (==1) and
      subtracts 2.5 from the CLAMP INPUT (fr4 = fr6 - 2.5, fr6 = f32@A73C),
      NOT from the correction.  (Old lift: compared float RPM, set corr=2.5.)
  D2  ECT block OVERWRITES correction = previous_timing - 1.0 when
      byte@C0C4 == 1; it does not accumulate.  Both corr_enable branches use
      1.0 (0x79880 and 0x79888 are both 1.0f), so C0C5 never changes the value.
  D3  A744 = 0x13E6C result = saturate(correction, table(RPM), 0.0@0x79878),
      with the table selected from status bytes B5A4/BCA9/BB55.
  D4  A73C = 0x13ED2 result = saturate(clamp_input, -10.0@0x7989C, 0.0@0x798A0)
      (stored back over the engine-speed word).
  D5  A734 = A738 = 0x13EE6(A744_result + A73C_result) =
      saturate(sum, t1(0x6B6A0,RPM), t2(0x6B6B4,RPM)); 0x13EE6 also stores the
      two lookups to A750/A754.  A75C = ignition-enable byte (r14).

The 1-D lookup reference reproduces ROM 0x2068 for the u8 (type=4) tables used
by this function, with single-precision rounding at every FP op (ts()).

Run from repo root:   python3 c/tests/test_calc_ignition_all_rotors_13C2C.py
"""
import os, random, struct, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2, ts

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')
ADDR = 0x13C2C

# ---- RAM addresses used by the ROM function (big-endian overlay) ----
A73C = 0xFFFFA73C   # f32 engine speed (fr6 in) / 0x13ED2 clamp result (out)
A740 = 0xFFFFA740   # u8 ignition enable (r14) -> output to A75C
A744 = 0xFFFFA744   # f32 previous timing (fr5 in) / 0x13E6C result (out)
A748 = 0xFFFFA748   # u8 knock sensor fault
A749 = 0xFFFFA749   # u8 knock detected
A75C = 0xFFFFA75C   # u8 knock control active (in) / output (r14 copy)
A734 = 0xFFFFA734   # f32 leading-rotor timing output (0x13EE6 result)
A738 = 0xFFFFA738   # f32 trailing-rotor timing output (0x13EE6 result)
A750 = 0xFFFFA750   # f32 0x13EE6 lookup 1 scratch
A754 = 0xFFFFA754   # f32 0x13EE6 lookup 2 scratch
A74C = 0xFFFFA74C   # f32 detected==0 lookup scratch (written only in that path)
B5B8 = 0xFFFFB5B8   # f32 RPM
B5A4 = 0xFFFFB5A4   # u8 0x13E6C table-select status
BB55 = 0xFFFFBB55   # u8 0x13E6C table-select status
BCA9 = 0xFFFFBCA9   # u8 0x13E6C table-select status
C0C4 = 0xFFFFC0C4   # u8 ECT status
C0C5 = 0xFFFFC0C5   # u8 ECT corr enable (value never changes the result)
C0C7 = 0xFFFFC0C7   # u8 knock counter (byte-vs-byte threshold check)

# ---- ROM 1-D lookup descriptors ----
DESC_MAIN = 0x0006B68C   # detected==0 path (5-pt u8)
DESC_A    = 0x0006B678   # 0x13E6C table A (4-pt u8)
DESC_B    = 0x0006B664   # 0x13E6C table B (5-pt u8)
DESC_T1   = 0x0006B6A0   # 0x13EE6 lookup 1 (12-pt u8)
DESC_T2   = 0x0006B6B4   # 0x13EE6 lookup 2 (12-pt u8)


# =====================================================================
# Reference model (mirrors c/calc_ignition_all_rotors_13C2C.c)
# =====================================================================

def f32_at(rom, a):
    return struct.unpack('>f', rom[a:a + 4])[0]


def u8_at(rom, a):
    return rom[a]


def gf(ram, a):
    """Read big-endian f32 from the seeded RAM overlay (missing bytes = 0)."""
    return struct.unpack('>f', bytes(ram.get(a + i, 0) for i in range(4)))[0]


def gb(ram, a):
    return ram.get(a, 0)


def table1d_lookup(rom, desc, x):
    """Mirror of ROM 0x2068 for the u8 (type=4) tables used by this function.

    Segment search: x >= axis[n-1] -> i = n-1, t = 0 (clamp top);
    x < axis[0] -> i = 0, t = 0 (clamp bottom); else find i with
    axis[i] <= x < axis[i+1] and t = ts(ts(x-axis[i]) / ts(axis[i+1]-axis[i])).
    u8 handler 0x26B0 zero-extends cells; interp = ts(t * ts(v1-v0) + v0)
    (fmac), then result = ts(scale * interp + off) (fmac in 0x208E).
    """
    cnt = struct.unpack('>H', rom[desc:desc + 2])[0]
    typ = rom[desc + 2]
    axis = struct.unpack('>I', rom[desc + 4:desc + 8])[0]
    vals = struct.unpack('>I', rom[desc + 8:desc + 12])[0]
    assert typ == 4, "test covers only u8 (type=4) tables"
    axis_pts = [struct.unpack('>f', rom[axis + 4 * i:axis + 4 * i + 4])[0]
                for i in range(cnt)]
    if x >= axis_pts[cnt - 1]:
        i, t = cnt - 1, 0.0
    elif x < axis_pts[0]:
        i, t = 0, 0.0
    else:
        for j in range(cnt - 1):
            if axis_pts[j] <= x < axis_pts[j + 1]:
                break
        i = j
        t = ts(ts(x - axis_pts[j]) / ts(axis_pts[j + 1] - axis_pts[j]))
    v0 = float(rom[vals + i])
    if t == 0.0:
        interp = v0
    else:
        v1 = float(rom[vals + i + 1])
        interp = ts(t * ts(v1 - v0) + v0)
    scale = struct.unpack('>f', rom[desc + 12:desc + 16])[0]
    off = struct.unpack('>f', rom[desc + 16:desc + 20])[0]
    return ts(scale * interp + off)


def saturate(v, lo, hi):
    """Mirror of ROM 0x2404: v < lo -> lo; v > hi -> hi; else v."""
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def clamp_correction_0x13ED2(v, rom):
    """Helper 0x13ED2: saturate(v, -10.0@0x7989C, 0.0@0x798A0)."""
    return saturate(v, f32_at(rom, 0x7989C), f32_at(rom, 0x798A0))


def select_13E6C_table(rom, ram):
    """ROM 0x13E76..0x13EB6 table selection for 0x13E6C."""
    b5a4 = gb(ram, B5A4)
    bca9 = gb(ram, BCA9)
    bb55 = gb(ram, BB55)
    thr = u8_at(rom, 0x79838)          # 5
    if b5a4 == 1 and bca9 >= thr:
        return DESC_A
    if b5a4 != 0:
        return DESC_B
    if bb55 > thr or bb55 == 0:
        return DESC_B
    return DESC_A


def correction_final_clamp_0x13E6C(corr, rom, ram):
    """Helper 0x13E6C: saturate(corr, table(RPM), 0.0@0x79878)."""
    rpm = gf(ram, B5B8)
    lower = table1d_lookup(rom, select_13E6C_table(rom, ram), rpm)
    upper = f32_at(rom, 0x79878)
    return saturate(corr, lower, upper)


def rotor_output_clamp_0x13EE6(v, rom, ram):
    """Helper 0x13EE6: saturate(v, t1(0x6B6A0,RPM), t2(0x6B6B4,RPM)).

    Also stores the two lookups to A750/A754 (returns them).
    """
    rpm = gf(ram, B5B8)
    l1 = table1d_lookup(rom, DESC_T1, rpm)
    l2 = table1d_lookup(rom, DESC_T2, rpm)
    return saturate(v, l1, l2), l1, l2


def ref(ram, rom):
    """Line-for-line mirror of calc_ignition_all_rotors_13C2C() in the C lift.

    Returns (A73C, A744, A734, A738, A750, A754, A74C, A75C).
    """
    prev = gf(ram, A744)               # fr5 = f32@A744
    eng = gf(ram, A73C)                # fr6 = f32@A73C
    ign = gb(ram, A740)                # r14 = u8@A740
    fault = gb(ram, A748)              # r2  = u8@A748
    corr = prev                        # fr15 = fr5
    clamp_in = eng                     # fr4  = fr6
    wrote_a74c = False
    a74c = None

    if fault == 0:
        corr = 0.0                     # fr15 = 0.0 (f32@0x7987C)
        clamp_in = 0.0                 # fr4  = fr14 = 0.0
    else:
        detected = gb(ram, A749)       # u8@A749
        if detected == 0:
            # 0x13C60: RPM-based table lookup, stored to A74C
            rpm = gf(ram, B5B8)
            corr = table1d_lookup(rom, DESC_MAIN, rpm)
            a74c = corr
            wrote_a74c = True
            clamp_in = 0.0
        else:
            active = gb(ram, A75C)     # u8@A75C
            if active == 0:
                # 0x13C7E: no knock control active
                if ign == 1:
                    corr = 0.0
                    clamp_in = 0.0
                # else: keep fr15 = previous_timing, fr4 = A73C
            else:
                # 0x13C8E: knock control active
                if ign == 1:
                    # 0x13C96: BYTE-vs-BYTE threshold (C0C7 >= 0x7983B)
                    if gb(ram, C0C7) >= u8_at(rom, 0x7983B):
                        clamp_in = ts(eng - f32_at(rom, 0x79890))   # eng - 2.5
                    else:
                        clamp_in = eng
                    # 0x13CAC ECT block: OVERWRITES correction
                    if gb(ram, C0C4) == 1:
                        corr = ts(prev - f32_at(rom, 0x79880))      # prev - 1.0
                # else: keep fr15 = previous_timing, fr4 = A73C

    # ---- Phase 3: final dispatch (0x13CCE..0x13CEC) ----
    a73c = clamp_correction_0x13ED2(clamp_in, rom)     # -> A73C
    a744 = correction_final_clamp_0x13E6C(corr, rom, ram)  # -> A744
    rotor, a750, a754 = rotor_output_clamp_0x13EE6(ts(a744 + a73c), rom, ram)
    a734 = a738 = rotor                                # -> A734, A738
    if not wrote_a74c:
        a74c = gf(ram, A74C)                           # untouched scratch
    return (a73c, a744, a734, a738, a750, a754, a74c, ign)


# =====================================================================
# Emulator harness
# =====================================================================

def run_one(cpu, ram):
    """Run ROM 0x13C2C on the emulator with the seeded overlay; read outputs."""
    cpu.call(ADDR, ram=ram)          # call() copies the dict; read cpu.ram

    def rf(a):
        return struct.unpack('>f', bytes(cpu.ram.get(a + i, 0) for i in range(4)))[0]

    return (rf(A73C), rf(A744), rf(A734), rf(A738), rf(A750), rf(A754),
            rf(A74C), cpu.ram.get(A75C, 0))


def seed_f32(ram, a, v):
    b = struct.pack('>f', ts(v))
    for i, x in enumerate(b):
        ram[a + i] = x


def gen_state(rng):
    """Random seeded RAM state hitting every branch combination."""
    ram = {}
    seed_f32(ram, A73C, rng.uniform(-40, 40))
    seed_f32(ram, A744, rng.uniform(-40, 40))
    seed_f32(ram, B5B8, rng.uniform(500, 9000))
    seed_f32(ram, A74C, rng.uniform(-40, 40))
    seed_f32(ram, A750, rng.uniform(-40, 40))
    seed_f32(ram, A754, rng.uniform(-40, 40))
    ram[A740] = rng.randrange(0, 2)
    ram[A748] = rng.randrange(0, 2)
    ram[A749] = rng.randrange(0, 2)
    ram[A75C] = rng.randrange(0, 2)
    ram[C0C7] = rng.randrange(0, 4)
    ram[C0C4] = rng.randrange(0, 2)
    ram[C0C5] = rng.randrange(0, 2)
    ram[B5A4] = rng.randrange(0, 3)
    ram[BB55] = rng.randrange(0, 8)
    ram[BCA9] = rng.randrange(0, 8)
    return ram


# =====================================================================
# Explicit deterministic anchors (each documents one fixed divergence)
# =====================================================================

def base_state():
    """Nominal state: faulted, knock detected, knock active, ign enabled,
    C0C7 >= threshold, ECT off, RPM 3000, prev timing +20.0, A73C 0.0."""
    ram = {}
    seed_f32(ram, A73C, 0.0)
    seed_f32(ram, A744, 20.0)
    seed_f32(ram, B5B8, 3000.0)
    seed_f32(ram, A74C, 0.0)
    seed_f32(ram, A750, 0.0)
    seed_f32(ram, A754, 0.0)
    ram[A740] = 1
    ram[A748] = 1
    ram[A749] = 1
    ram[A75C] = 1
    ram[C0C7] = 1
    ram[C0C4] = 0
    ram[C0C5] = 0
    ram[B5A4] = 0
    ram[BB55] = 0
    ram[BCA9] = 0
    return ram


def c_eng(v):    # knock-active path, varying engine speed (A73C seed)
    r = base_state(); seed_f32(r, A73C, v); return r

def c_prev(v):   # varying previous timing (A744 seed)
    r = base_state(); seed_f32(r, A744, v); return r

def c_rpm(v):    # varying RPM
    r = base_state(); seed_f32(r, B5B8, v); return r

def c_ect(prev):  # ECT status on (overwrite path)
    r = base_state(); seed_f32(r, A744, prev); r[C0C4] = 1; return r

def c_tab(prev, b5a4, bca9):  # 0x13E6C table-select combos
    r = base_state(); seed_f32(r, A744, prev)
    r[B5A4] = b5a4; r[BCA9] = bca9; return r

EXPLICIT_CASES = [
    # Each case's expected values are verified LIVE against the emulator.
    ("D1 knock-active C0C7>=1: 2.5 subtracted from CLAMP INPUT (eng 10.0 -> 0.0)",
     lambda: c_eng(10.0)),
    ("D1 knock-active, eng -5.0 -> clamp input -7.5 -> A73C -7.5",
     lambda: c_eng(-5.0)),
    ("D1 byte threshold NOT met (C0C7=0): clamp input stays -5.0 (no -2.5)",
     lambda: (r := c_eng(-5.0), r.__setitem__(C0C7, 0), r)[-1]),
    ("D2 ECT OVERWRITE: prev -9.5 -> corr -10.5 -> A744 -10.0 (not -9.5)",
     lambda: c_ect(-9.5)),
    ("D2 ECT on, prev 20.0 -> corr 19.0 -> A744 0.0 (upper clamp)",
     lambda: c_ect(20.0)),
    ("D3/D4/D5 detected==0 lookup path: A744=-10.0, A74C=-10.0, A73C=0.0",
     lambda: (r := base_state(), r.__setitem__(A749, 0), r)[-1]),
    ("fault=0 -> correction and clamp input zeroed",
     lambda: (r := base_state(), r.__setitem__(A748, 0), r)[-1]),
    ("active=0, ign=1 -> both zeroed, A75C=1",
     lambda: (r := base_state(), r.__setitem__(A75C, 0), r)[-1]),
    ("ign=0 keeps fr15/fr4: A73C stays -5.0, A75C=0",
     lambda: (r := c_eng(-5.0), r.__setitem__(A740, 0), r)[-1]),
    ("D3 table A select (B5A4=1, BCA9>=5): 4-pt table lower at 3000 = -5.0",
     lambda: c_tab(-7.0, 1, 7)),
    ("D3 B5A4=1 but BCA9<5 -> table B (5-pt, lower -10.0)",
     lambda: c_tab(-7.0, 1, 0)),
    ("RPM above table top (6000): all lookups -> 0.0",
     lambda: c_rpm(6000.0)),
    ("RPM below table bottom (1000): clamped to first point",
     lambda: c_rpm(1000.0)),
]


def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    fails = tests = 0

    # Explicit divergence anchors
    for name, make in EXPLICIT_CASES:
        ram = make()
        out = run_one(cpu, dict(ram))
        exp = ref(ram, rom)
        tests += 1
        if out != exp:
            fails += 1
            print(f"  FAIL [{name}]\n    emu={out}\n    ref={exp}")

    # Random state sweep
    rng = random.Random(20260731)
    for n in range(1500):
        ram = gen_state(rng)
        out = run_one(cpu, dict(ram))
        exp = ref(ram, rom)
        tests += 1
        if out != exp:
            fails += 1
            print(f"  FAIL random #{n}: emu={out} ref={exp}")
            if fails >= 5:
                break

    print(f"calc_ignition_all_rotors_13C2C: {tests} tests, {fails} failures")
    print("CALC_IGNITION_ALL_ROTORS_13C2C:", "PASS" if fails == 0 else "FAIL")
    return 0 if fails == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
