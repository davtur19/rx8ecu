#!/usr/bin/env python3
"""
test_exhaust_oxygen_control_19480.py — differential bit-exact test of
exhaust_oxygen_control_19480 @0x19480 (lift: c/exhaust_oxygen_control_19480.c).

Method (repo Track-A pattern): the REAL ROM bytes of 0x19480 are executed in the
SH-2E emulator (tools/sh2emu.py) with a seeded random RAM overlay — the o2 sensor
read helper @0x5E016, the drive helper @0x197B8 and the saturating-add helper
@0x2478 all run for real — and the resulting RAM overlay is compared bit-exactly
against a pure-Python model derived from the disassembly (see header of the lift).

Facts from the disassembly that shape the model (see header of the C lift):

  * o2_sensor_read(@0x5E016) reads hardware-register cells (0xFFFFD3xx and the
    0x0602F4 region) that are NOT part of this function's RAM overlay; in the
    emulator those uninitialised cells read 0, so the helper deterministically
    returns 0 on every call and RAM_O2_RAW (0xFFFFA9D4) is always written 0.
    The Python model therefore uses raw = 0 (same value the emulator computes).
  * CAL_SENS_MODE (ROM u8 @0x6F6A6) is 0 in this stock ROM, so at runtime only
    the mode==0 dispatch (map-mode flags, then the f32 plausibility window) and
    the debounce/level-transition path are reachable; the ==1/==2 branches are
    kept in the model for completeness but are never exercised on this ROM.
  * The three f32 window thresholds come from ROM: f_a@B5B8 in [0,1200),
    f_b@AA10 in [-40,120), f_c@ADBC in [0,125).  The continue-into-window
    condition is lower <= input && input < upper (emulator fcmp/gt semantics).
  * Only modes {0,12} (channel 0) and {6,18} (channel 1) touch the output flags
    A9D5..A9D8; with raw==0 the level-change flag only arms for modes 0/12.

RAM in: 0xFFFFA41C u8 reset, 0xFFFFA6B7/6B8/6B9 u8 map-mode flags,
        0xFFFFB5B8 f32, 0xFFFFAA10 f32, 0xFFFFADBC f32 (window inputs),
        0xFFFFA9D5..E0 u8 state bytes (in/out).
RAM out: 0xFFFFA9D4 (raw, always 0), 0xFFFFA9D5/6/7/8 drive flags,
         0xFFFFA9D9 state-change, 0xFFFFA9DA level-chg, 0xFFFFA9DB prev_raw,
         0xFFFFA9DC debounce, 0xFFFFA9DD state, 0xFFFFA9DE mode-latch(=0),
         0xFFFFA9DF cnt, 0xFFFFA9E0 flag_e0.

Run from repo root:
    python3 c/tests/test_exhaust_oxygen_control_19480.py [N]
    (N = random vectors per seed; default 1000)
"""
import os, random, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2, ts  # noqa: E402

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')
ADDR = 0x19480

# ---- RAM cells ----
A41C = 0xFFFFA41C   # u8 global reset / inhibit (==1)
A9D4 = 0xFFFFA9D4   # u8 O2 raw value (written from o2_sensor_read, =0)
A9D5 = 0xFFFFA9D5   # u8 drive flag A (mode 0/12, mask bit0)
A9D6 = 0xFFFFA9D6   # u8 drive flag B (mode 6/18, mask bit1)
A9D7 = 0xFFFFA9D7   # u8 drive flag C (mode 0/12, mask bit2)
A9D8 = 0xFFFFA9D8   # u8 drive flag D (mode 6/18, mask bit3)
A9D9 = 0xFFFFA9D9   # u8 state-change notify flag
A9DA = 0xFFFFA9DA   # u8 input level-change flag
A9DB = 0xFFFFA9DB   # u8 previous O2 raw value
A9DC = 0xFFFFA9DC   # u8 debounce counter
A9DD = 0xFFFFA9DD   # u8 heater/sensor state
A9DE = 0xFFFFA9DE   # u8 latch of CAL_SENS_MODE
A9DF = 0xFFFFA9DF   # u8 state counter (limit 60)
A9E0 = 0xFFFFA9E0   # u8 sensor-mode-changed flag
A6B7 = 0xFFFFA6B7   # u8 map-mode flag
A6B8 = 0xFFFFA6B8   # u8 map-mode flag
A6B9 = 0xFFFFA6B9   # u8 map-mode flag
B5B8 = 0xFFFFB5B8   # f32 window input 1 (fr5)
AA10 = 0xFFFFAA10   # f32 window input 2 (fr6)
ADBC = 0xFFFFADBC   # f32 window input 3 (fr4)

STATE_CELLS = [A9D4, A9D5, A9D6, A9D7, A9D8, A9D9, A9DA, A9DB,
               A9DC, A9DD, A9DE, A9DF, A9E0]
FLOAT_CELLS = [B5B8, AA10, ADBC]
INPUT_CELLS = STATE_CELLS + [A41C, A6B7, A6B8, A6B9]
for _f in FLOAT_CELLS:
    for _i in range(4):
        INPUT_CELLS.append(_f + _i)

# hardware-register cells touched by o2_sensor_read (not part of the footprint);
# writes there are expected and excluded from the unexpected-write check.
HW_RANGE = range(0xFFFFD300, 0xFFFFD3FF)
STACK_RANGE = range(0xFFFFDDE0, 0xFFFFDF00)

FOOTPRINT = set(INPUT_CELLS)


def getf(ram, a):
    return ts(struct.unpack('>f', bytes(ram.get(a + i, 0) for i in range(4)))[0])


def putf(ram, a, v):
    b = struct.pack('>f', ts(v))
    for i in range(4):
        ram[a + i] = b[i]


def satadd_u8(a, b):
    s = (a & 0xFF) + (b & 0xFF)
    return 0xFF if s >= 0xFF else (s & 0xFF)


def drive_update(mask, mode, ram):
    """Faithful model of drive_update @0x197B8 (inlined in the lift)."""
    if mask >= 16:
        if mode in (0, 12):
            ram[A9D5] = 0; ram[A9D7] = 0
        if mode in (6, 18):
            ram[A9D6] = 0; ram[A9D8] = 0
    else:
        if mode in (0, 12):
            ram[A9D5] = 1 if (mask & 1) else 0
            ram[A9D7] = 1 if (mask & 4) else 0
        if mode in (6, 18):
            ram[A9D6] = 1 if (mask & 2) else 0
            ram[A9D8] = 1 if (mask & 8) else 0


class Cal:
    """ROM calibrations read straight from the binary (all stock values)."""
    def __init__(self, rom):
        self.d = rom
        self.sens_mode = self.u8(0x6F6A6)     # CAL_SENS_MODE (0 stock)
        self.mask_win = self.u8(0x6F6A4)      # CAL_DRV_MASK_WIN (0)
        self.mask_map = self.u8(0x6F6A5)      # CAL_DRV_MASK_MAP (0)
        self.cnt_tab = [self.u8(0x6F6A7 + i) for i in range(16)]
        self.deb0 = self.u8(0x6F66F)          # idx==0 -> ROM@0x6F66F

    def u8(self, a):
        return self.d[a]

    def debounce_limit(self, idx):
        if idx == 0:
            return self.deb0
        return self.u8(0x6F670 + (idx & 0xFF) - 1)


def ref(t, c):
    """Pure-Python model of 0x19480 — mirrors the C lift exactly.

    Returns the final values (as a dict {addr:byte}) of the footprint cells.
    """
    mode = t['mode'] & 0xFF
    raw = 0                       # o2_sensor_read() == 0 under this overlay
    old_state = t.get(A9DD, 0) & 0xFF

    ram = {a: t.get(a, 0) & 0xFF for a in STATE_CELLS}
    ram[A9D4] = raw                            # RAM_O2_RAW := raw (=0)

    # step 2: debounce index — derived from RAM_O2_RAW (r8=A9D4), NOT A9D8
    # (verified against the disasm: both branches read mov.b @r8,r6; the
    #  >=50 branch then adds 206).  raw==0 in this overlay -> idx==0 always.
    if raw >= 50:
        idx = (raw + 206) & 0xFF
    else:
        idx = raw

    # step 3: input level change
    if raw != ram[A9DB]:
        ram[A9DC] = 0
        ram[A9DA] = 0
        if idx != 0:
            if raw < 50:
                if mode in (0, 12):
                    ram[A9DA] = 1
            elif raw <= 100:
                if mode in (6, 18):
                    ram[A9DA] = 1

    # step 4: sensor-mode latch change
    if c.sens_mode != ram[A9DE]:
        ram[A9DF] = 0
        if c.sens_mode == 2:
            ram[A9E0] = 1

    # step 5: global reset (window inputs come in as floats)
    f_a = ts(t['fa']); f_b = ts(t['fb']); f_c = ts(t['fc'])
    if (t.get('rst', 0) & 0xFF) == 1:
        ram[A9D5] = 0; ram[A9D7] = 0
        ram[A9D6] = 0; ram[A9D8] = 0
        ram[A9DE] = 0
        ram[A9DF] = 0
        ram[A9E0] = 0
        ram[A9DC] = 0
        ram[A9DB] = 0
        ram[A9DA] = 0
        ram[A9DD] = 0
    elif ram[A9DA] == 1:
        # step 6: level-transition path
        if ram[A9DC] == 0:
            drive_update(0x0F, mode, ram)
        else:
            ram[A9D5] = 0; ram[A9D7] = 0
            ram[A9D6] = 0; ram[A9D8] = 0
        limit = c.debounce_limit(idx)
        if ram[A9DC] >= limit:
            ram[A9DC] = 0
        else:
            ram[A9DC] = satadd_u8(ram[A9DC], 1)
        ram[A9DB] = raw                        # prev_raw := raw (=0)
        ram[A9DD] = 5
    else:
        # step 7: dispatch on calibration sensor-mode byte
        if c.sens_mode == 1:
            drive_update(c.cnt_tab[ram[A9DF]], mode, ram)
            if mode in (6, 18):
                ram[A9DF] = satadd_u8(ram[A9DF], 1)
            if ram[A9DF] >= 60:
                ram[A9DF] = 0
            ram[A9DD] = 4
        elif c.sens_mode == 2:
            if ram[A9E0] == 1:
                drive_update(c.cnt_tab[ram[A9DF]], mode, ram)
                if mode in (6, 18):
                    ram[A9DF] = satadd_u8(ram[A9DF], 1)
                if ram[A9DF] >= 60:
                    ram[A9DF] = 0
                    ram[A9E0] = 0
                ram[A9DD] = 4
            else:
                ram[A9D5] = 0; ram[A9D7] = 0
                ram[A9D6] = 0; ram[A9D8] = 0
                ram[A9DD] = 0
        else:
            if (t.get('b7', 0) & 0xFF) == 1 or (t.get('b8', 0) & 0xFF) == 1 \
               or (t.get('b9', 0) & 0xFF) == 1:
                drive_update(c.mask_map, mode, ram)
                ram[A9DD] = 2
            elif (not (f_a < 0.0)) and f_a < 1200.0 and \
                 (not (f_b < -40.0)) and f_b < 120.0 and \
                 (not (f_c < 0.0)) and f_c < 125.0:
                drive_update(c.mask_win, mode, ram)
                ram[A9DD] = 1
            else:
                if mode in (0, 12):
                    ram[A9D5] = 0; ram[A9D7] = 0
                if mode in (6, 18):
                    ram[A9D6] = 0; ram[A9D8] = 0
                ram[A9DD] = 0

    # epilogue
    ram[A9DE] = c.sens_mode                    # mode_latch := CAL
    st = ram[A9DD]
    if st != old_state and st != 0:
        ram[A9D9] = 1
        ram[A9DF] = 0
    return ram


def build_ram(t):
    ram = {}
    putf(ram, B5B8, t['fa']); putf(ram, AA10, t['fb']); putf(ram, ADBC, t['fc'])
    for a in STATE_CELLS:
        ram[a] = t.get(a, 0) & 0xFF
    ram[A41C] = t.get('rst', 0) & 0xFF
    ram[A6B7] = t.get('b7', 0) & 0xFF
    ram[A6B8] = t.get('b8', 0) & 0xFF
    ram[A6B9] = t.get('b9', 0) & 0xFF
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    c = Cal(rom)
    seeds = (0x19480, 0x6F6A6, 0xB5B8, 0x5EED)
    tests = fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        vectors = []
        # structured: reset x mode x map-flags x window-threshold x debounce/state
        modes = [0, 6, 12, 18, 1, 13, 0xFF]
        mflags = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]
        fws = [-1000.0, -40.0, -1.0, -0.0, 0.0, 0.001, 119.999, 120.0,
               124.999, 125.0, 1199.999, 1200.0, float('nan')]
        for mode in modes:
            for (b7, b8, b9) in mflags:
                for fa in fws:
                    for fb in fws:
                        for fc in fws:
                            for rst in (0, 1):
                                d = dict(mode=mode, fa=fa, fb=fb, fc=fc,
                                         rst=rst, b7=b7, b8=b8, b9=b9)
                                d[A9D5] = rng.getrandbits(8)
                                d[A9D6] = rng.getrandbits(8)
                                d[A9D7] = rng.getrandbits(8)
                                d[A9D8] = rng.getrandbits(8)
                                d[A9D9] = rng.getrandbits(8)
                                d[A9DA] = rng.getrandbits(8)
                                d[A9DB] = rng.getrandbits(8)
                                d[A9DC] = rng.getrandbits(8)
                                d[A9DD] = rng.getrandbits(8)
                                d[A9DE] = rng.getrandbits(8)
                                d[A9DF] = rng.getrandbits(8)
                                d[A9E0] = rng.getrandbits(8)
                                vectors.append(d)
        # random vectors with edge-heavy distributions
        for _ in range(N):
            def rf():
                r = rng.random()
                if r < 0.12:
                    return rng.choice(fws)
                if r < 0.18:
                    return float('nan')
                return rng.uniform(-60, 1300)
            d = dict(mode=rng.choice(modes), fa=rf(), fb=rf(), fc=rf(),
                     rst=1 if rng.random() < 0.08 else 0,
                     b7=rng.getrandbits(8), b8=rng.getrandbits(8),
                     b9=rng.getrandbits(8))
            for a in (A9D5, A9D6, A9D7, A9D8, A9D9, A9DA, A9DB, A9DC, A9DD,
                      A9DE, A9DF, A9E0):
                d[a] = rng.getrandbits(8)
            vectors.append(d)

        for t in vectors:
            ram = build_ram(t)
            cpu.call(ADDR, r4=t['mode'], ram=ram)
            got = tuple(cpu.ram.get(a, 0) for a in STATE_CELLS)
            exp = tuple(ref(t, c)[a] for a in STATE_CELLS)
            tests += 1
            if got != exp:
                fails += 1
                if fails <= 10:
                    print("FAIL seed=0x%X %s" % (seed, {k: t[k] for k in t
                          if k in ('mode', 'fa', 'fb', 'fc', 'rst', 'b7',
                                   'b8', 'b9')}))
                    print("  emu: %s" % ' '.join('%02X' % g for g in got))
                    print("  mod: %s" % ' '.join('%02X' % e for e in exp))
                    for a, g, e in zip(STATE_CELLS, got, exp):
                        if g != e:
                            print("    @0x%X emu=%02X mod=%02X"
                                  % (a, g, e))
            # no writes outside footprint (+ o2-sensor hw + stack)
            for a in cpu.ram:
                if a in FOOTPRINT or a in HW_RANGE or a in STACK_RANGE:
                    continue
                fails += 1
                if fails <= 10:
                    print("FAIL(unexpected write) 0x%08X = %d" % (a, cpu.ram[a]))
            if fails >= 10:
                break
        if fails:
            break

    print(f"exhaust_oxygen_control_19480 @0x19480: {tests} tests, {fails} failures")
    if fails == 0:
        print(f"OK  exhaust_oxygen_control_19480 @0x19480  ({tests} inputs, 0 mismatches)")
        return 0
    print(f"FAIL exhaust_oxygen_control_19480 @0x19480  ({fails} mismatches)")
    return 1


if __name__ == '__main__':
    sys.exit(main())