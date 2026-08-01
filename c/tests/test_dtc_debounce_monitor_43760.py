#!/usr/bin/env python3
"""
Verify dtc_debounce_monitor_43760 (0x043760) against the ACTUAL ROM bytes,
run in the SH-2E emulator, over many random RAM states (including the two
single-precision float gates).

Logic (as executed by the ROM, fcmp/gt Fm,Fn -> T = (FRn > FRm)):
  if (reset)                         -> zero flags + counters; return
  if (enable && cond && ctrA >= 157) {
      if (17000.0 > accum)           -> ctrB = 0; ctrC = 0
      else if (500.0 > runtime)      -> path C: if (ctrC >= 4) flag2 = 1;
                                           ctrC = satadd(ctrC,1); ctrB = 0
      else                           -> path B: if (ctrB >= 16) flag1 = 1;
                                           ctrB = satadd(ctrB,1); ctrC = 0
  } else                             -> ctrB = 0; ctrC = 0
  if (cond) ctrA = satadd(ctrA,1) else ctrA = 0

This test compares the emulator output against a Python port of the C
lift (c/dtc_debounce_monitor_43760.c) for N random states.

Run from repo root:  python3 c/tests/test_dtc_debounce_monitor_43760.py [N]
"""
import os, sys, random, struct

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RE = os.path.join(ROOT, 'tools')
sys.path.insert(0, RE)
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x043760

COND     = 0xFFFFB3C8   # byte  condition under test
ENABLE   = 0xFFFFC9E8   # byte  monitor enable
RESET    = 0xFFFFD201   # byte  reset request
FLAG1    = 0xFFFFC9EF   # byte  output flag 1
FLAG2    = 0xFFFFC9F0   # byte  output flag 2
CTR_A    = 0xFFFFC9FE   # word  primary counter
CTR_B    = 0xFFFFCA00   # word  secondary counter B
CTR_C    = 0xFFFFCA02   # word  secondary counter C
ACCUM    = 0xFFFFC9E4   # float accumulated value
RUNTIME  = 0xFFFFAAF0   # float runtime value

ROM_TH_A  = 0x0007D97C  # word  157
ROM_TH_B  = 0x0007D978  # word   16
ROM_TH_C  = 0x0007D97A  # word    4
ROM_GATE_HI = 0x0007D984  # float 17000.0
ROM_GATE_LO = 0x0007D988  # float 500.0

WATCH = [FLAG1, FLAG2, CTR_A, CTR_A + 1, CTR_B, CTR_B + 1,
         CTR_C, CTR_C + 1]


def satadd(a, b):
    s = a + b
    return s if s < 0xFFFF else 0xFFFF


def model(rom, ram):
    """Python port of c/dtc_debounce_monitor_43760.c.
    Returns dict of final bytes at the watched addresses (and only those).
    Words are big-endian (mov.w semantics); ROM constants are read from
    the rom bytes, RAM from the state dict."""
    out = dict(ram)
    def r8(a):  return out.get(a, 0)
    def r16(a): return (out.get(a, 0) << 8) | out.get(a + 1, 0)
    def w16(a, v):
        out[a] = (v >> 8) & 0xFF; out[a + 1] = v & 0xFF
    def w8(a, v): out[a] = v & 0xFF
    def rf(a):  return struct.unpack('>f', bytes(out.get(a + i, 0) for i in range(4)))[0]
    def rrom16(a): return (rom[a] << 8) | rom[a + 1]
    def rromf(a):  return struct.unpack('>f', bytes(rom[a + i] for i in range(4)))[0]

    cond = r8(COND)

    if r8(RESET) == 1:
        w8(FLAG1, 0); w8(FLAG2, 0)
        w16(CTR_A, 0); w16(CTR_B, 0); w16(CTR_C, 0)
        return {a: out[a] for a in WATCH}

    th_a = rrom16(ROM_TH_A)
    if r8(ENABLE) == 1 and cond == 1 and r16(CTR_A) >= th_a:
        if rromf(ROM_GATE_HI) > rf(ACCUM):
            w16(CTR_B, 0); w16(CTR_C, 0)
        elif rromf(ROM_GATE_LO) > rf(RUNTIME):
            if r16(CTR_C) >= rrom16(ROM_TH_C):
                w8(FLAG2, 1)
            w16(CTR_C, satadd(r16(CTR_C), 1))
            w16(CTR_B, 0)
        else:
            if r16(CTR_B) >= rrom16(ROM_TH_B):
                w8(FLAG1, 1)
            w16(CTR_B, satadd(r16(CTR_B), 1))
            w16(CTR_C, 0)
    else:
        w16(CTR_B, 0); w16(CTR_C, 0)

    if cond == 1:
        w16(CTR_A, satadd(r16(CTR_A), 1))
    else:
        w16(CTR_A, 0)

    return {a: out[a] for a in WATCH}


def random_state(rng):
    """Biased random state that exercises every branch of the monitor:
    reset on/off, enable on/off, condition on/off, counters at/around their
    thresholds, and floats at/around the two calibration gates."""
    ram = {}
    # enable / condition / reset: mostly valid, sometimes off
    ram[ENABLE] = 1 if rng.random() < 0.7 else rng.randrange(0x100)
    ram[COND] = rng.choice([0, 1, 1, 1, rng.randrange(0x100)])
    ram[RESET] = 1 if rng.random() < 0.1 else 0

    def pick_near(lo, hi):
        return rng.choice([lo - 1, lo, hi, hi + 1, 0, 0xFFFF,
                           rng.randrange(0x10000)]) & 0xFFFF

    w16b = lambda a, v: (ram.__setitem__(a, (v >> 8) & 0xFF),
                         ram.__setitem__(a + 1, v & 0xFF))
    w16b(CTR_A, pick_near(156, 157))
    w16b(CTR_B, pick_near(15, 16))
    w16b(CTR_C, pick_near(3, 4))
    ram[FLAG1] = rng.randrange(0x100)
    ram[FLAG2] = rng.randrange(0x100)

    # floats: exactly at / just below / just above / random vs the gates
    for a, g in ((ACCUM, 17000.0), (RUNTIME, 500.0)):
        ch = rng.randrange(6)
        if ch == 0:   v = g
        elif ch == 1: v = g - 1.0
        elif ch == 2: v = g + 1.0
        elif ch == 3: v = 0.0
        elif ch == 4: v = 40000.0
        else:         v = rng.uniform(-1000, 50000)
        ram.update(zip(range(a, a + 4), struct.pack('>f', v)))
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    rng = random.Random(0x43760)

    for it in range(N):
        ram = random_state(rng)
        try:
            cpu.call(ENTRY, ram=dict(ram))
        except Exception as e:
            print("FAIL iter %d: emulator raised %s: %s" % (it, type(e).__name__, e))
            sys.exit(1)
        exp = model(rom, ram)
        for a in WATCH:
            got = cpu.ram.get(a, -1)
            if got != exp[a]:
                print("FAIL iter %d @0x%04X: got 0x%02X expected 0x%02X"
                      % (it, a, got, exp[a]))
                print("  ram=%s" % {hex(k): hex(v) for k, v in sorted(ram.items())})
                sys.exit(1)

    print("OK  dtc_debounce_monitor_43760 @0x%04X (%d random states incl. float gates)"
          % (ENTRY, N))
    sys.exit(0)


if __name__ == '__main__':
    main()
