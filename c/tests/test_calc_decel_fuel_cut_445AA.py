#!/usr/bin/env python3
"""
Test calc_decel_fuel_cut_445AA (0x445AA) via SH-2E emulator.

The C lift (c/calc_decel_fuel_cut_445AA.c) is a BEHAVIORAL model with
"partially decoded" conditions (see NOTES at the end of the lift).  The model
below is derived from the ACTUAL disassembly of 0x445AA in 60E1D400.bin, so the
differential comparison is honest: every input is run in the emulator against
the real ROM bytes and compared with this Python model.

RAM footprint (from the disasm):

  Read:
    0xFFFFCA30  f32   throttle position                     (fr4 = [CA30])
    0xFFFFCABB  u8    override flag                         (==1 -> force no cut)
    0xFFFFCAB9  u8    decel-fuel-cut enable                 (den)
    0xFFFFCAB4  u8    fuel-cut mode                         (must be 1 to decide)
    0xFFFFCA38  f32   engine speed / over-run input         (spd)
    0xFFFFCA88  f32   throttle-position threshold           (thr88)
    0xFFFFCAAC  u8    accumulator (hysteresis)              (in/out)
    0xFFFFCAB8  u8    decel enable #2 (fuel-cut permission) (cab8)
    0xFFFFCAB6  u8    secondary-cut flag                    (sc)
    0x0007B3DC  u8    cal: feature enable                   (f_en)
    0x0007B3DD  u8    cal: feature disable                  (cdis)
    0x0007B418  f32   cal: "throttle closed" threshold      (tclosed)
    0x0007B41C  f32   cal: secondary RPM threshold          (t50)

  Write:
    0xFFFFCAB5  u8    fuel-cut flag (1 = cut, 0 = normal)
    0xFFFFCAAC  u8    accumulator:
                         sc == 0      -> 0
                         fuel_cut==1  -> min(acc+1, 255)   (addSaturate8Bit @0x2478)
                         else         -> unchanged

Control flow (from disasm; note SH-2 fcmp/gt FRm,FRn sets T = (FRn > FRm)):

  fuel_cut = 0
  if override == 1 or (den == 1 and f_en == 1):  -> 0          (0x445D8/0x4466A)
  elif mode != 1:                                -> 0          (0x44608->0x44668)
  elif tclosed > spd:                            -> 0          (0x44614: fcmp/gt)
  else:
      caldec = 1 if (cdis != 0 or cab8 == 1) else 0
      # throttle-position comparison vs thr88 (0xFFFFCA88)
      if thr88 > th:                                        # -> 0x44636
          if t50 > th or acc <= 0:                          # 0x44636 checks
              fuel_cut = 0
          else:
              fuel_cut = caldec
      else:                                                 # th >= thr88
          if acc == 0:                                      # -> 0x4464C
              fuel_cut = caldec
          else:                                             # -> 0x44636
              if t50 > th:                                  # fcmp/gt fr3,fr4
                  fuel_cut = 0
              elif acc > 0:
                  fuel_cut = caldec
              else:
                  fuel_cut = 0

  Equivalently: fuel_cut = caldec iff
      (th >= thr88 and acc == 0) or (th >= t50 and acc > 0)
  (all ">=" via IEEE: not (b > a)).

Run from repo root:  python3 c/tests/test_calc_decel_fuel_cut_445AA.py
"""
import os, sys, struct, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2, ts

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')
ADDR = 0x445AA

CA30  = 0xFFFFCA30      # f32 throttle position
CABB  = 0xFFFFCABB      # u8 override flag
CAB9  = 0xFFFFCAB9      # u8 decel enable
CAB4  = 0xFFFFCAB4      # u8 fuel-cut mode
CA38  = 0xFFFFCA38      # f32 speed
CA88  = 0xFFFFCA88      # f32 throttle threshold
CAAC  = 0xFFFFCAAC      # u8 accumulator (in/out)
CAB8  = 0xFFFFCAB8      # u8 decel permission flag
CAB6  = 0xFFFFCAB6      # u8 secondary-cut flag
CAB5  = 0xFFFFCAB5      # u8 fuel-cut flag (output)
C_FEN   = 0x0007B3DC    # u8 cal feature enable
C_CDIS  = 0x0007B3DD    # u8 cal feature disable
C_TCLOSE = 0x0007B418   # f32 cal throttle-closed threshold
C_T50   = 0x0007B41C    # f32 cal secondary RPM threshold


def putf(ram, a, v):
    b = struct.pack('>f', ts(v))
    for i in range(4):
        ram[a + i] = b[i]


def getf(init, rom, a):
    b = bytes(init.get(a + i, rom[a + i] if a + i < len(rom) else 0) for i in range(4))
    return struct.unpack('>f', b)[0]


def build_ram(t):
    ram = {}
    putf(ram, CA30, t['th'])
    putf(ram, CA38, t['spd'])
    putf(ram, CA88, t['thr88'])
    for key, a in (('ovr', CABB), ('den', CAB9), ('mode', CAB4),
                   ('acc', CAAC), ('cab8', CAB8), ('sc', CAB6)):
        ram[a] = t[key] & 0xFF
    if 'f_en' in t:
        ram[C_FEN] = t['f_en'] & 0xFF
    if 'cdis' in t:
        ram[C_CDIS] = t['cdis'] & 0xFF
    if 'tclosed' in t:
        putf(ram, C_TCLOSE, t['tclosed'])
    if 't50' in t:
        putf(ram, C_T50, t['t50'])
    return ram


def ref(t, rom):
    """Pure-Python model of 0x445AA (see header).  Returns final (flag, acc)."""
    th = getf(t, rom, CA30)
    ovr = t.get(CABB, 0) & 0xFF
    den = t.get(CAB9, 0) & 0xFF
    f_en = t.get(C_FEN, rom[C_FEN]) & 0xFF
    mode = t.get(CAB4, 0) & 0xFF
    spd = getf(t, rom, CA38)
    thr88 = getf(t, rom, CA88)
    acc = t.get(CAAC, 0) & 0xFF
    cab8 = t.get(CAB8, 0) & 0xFF
    sc = t.get(CAB6, 0) & 0xFF
    cdis = t.get(C_CDIS, rom[C_CDIS]) & 0xFF
    tclosed = getf(t, rom, C_TCLOSE)
    t50 = getf(t, rom, C_T50)

    fuel_cut = 0
    if not (ovr == 1 or (den == 1 and f_en == 1)):
        if mode == 1:
            if not (tclosed > spd):                      # spd >= tclosed
                caldec = 1 if (cdis != 0 or cab8 == 1) else 0
                if (not (thr88 > th) and acc == 0) or (not (t50 > th) and acc > 0):
                    fuel_cut = caldec

    if sc == 0:
        acc_new = 0
    elif fuel_cut == 1:
        acc_new = min(acc + 1, 255)
    else:
        acc_new = acc
    return fuel_cut, acc_new


def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    random.seed(20260801)
    tests = fails = 0

    # ---- structured sweep: byte flags x float thresholds x accumulator ----
    th_vals = [0.0, 0.005, 0.01, 0.02, 49.9, 50.0, 50.1, 89.9, 90.0, 100.0,
               float('nan'), float('inf'), float('-inf')]
    spd_vals = [0.0, 0.005, 0.01, 0.02, 60.0, float('nan')]
    thr_vals = [0.0, 20.0, 49.99, 60.0, float('nan')]
    acc_vals = [0, 1, 127, 128, 254, 255]
    for ovr in (0, 1):
        for den in (0, 1):
            for mode in (0, 1):
                for cab8 in (0, 1):
                    for sc in (0, 1):
                        for th in th_vals:
                            for spd in spd_vals:
                                for thr88 in thr_vals:
                                    for acc in acc_vals:
                                        t = dict(th=th, spd=spd, thr88=thr88,
                                                 ovr=ovr, den=den, mode=mode,
                                                 cab8=cab8, sc=sc, acc=acc)
                                        ram = build_ram(t)
                                        cpu.call(ADDR, ram=ram)
                                        got = (cpu.ram.get(CAB5, 0),
                                               cpu.ram.get(CAAC, 0))
                                        exp = ref(ram, rom)
                                        tests += 1
                                        if got != exp:
                                            fails += 1
                                            if fails <= 8:
                                                print("FAIL(structured) %r got %r exp %r"
                                                      % (t, got, exp))

    # ---- random inputs incl. full byte range + cal-byte / threshold overlays ----
    allowed = {CAB5, CAAC}
    stack = set(range(0xFFFFDEF8, 0xFFFFDF00))
    for _ in range(10000):
        t = dict(th=random.uniform(-20, 120), spd=random.uniform(-5, 100),
                 thr88=random.uniform(-5, 120),
                 ovr=random.randint(0, 255), den=random.randint(0, 255),
                 mode=random.randint(0, 255), cab8=random.randint(0, 255),
                 sc=random.randint(0, 255), acc=random.randint(0, 255))
        if random.random() < 0.25:
            t['f_en'] = random.choice([0, 1, 0x80, 0xFF])
        if random.random() < 0.25:
            t['cdis'] = random.choice([0, 1, 0x7F, 0xFF])
        if random.random() < 0.15:
            t['tclosed'] = random.choice([0.0, 0.01, 50.0, 90.0, -5.0])
        if random.random() < 0.15:
            t['t50'] = random.choice([0.0, 10.0, 50.0, 120.0, 200.0])
        ram = build_ram(t)
        cpu.call(ADDR, ram=ram)
        got = (cpu.ram.get(CAB5, 0), cpu.ram.get(CAAC, 0))
        exp = ref(ram, rom)
        tests += 1
        if got != exp:
            fails += 1
            if fails <= 8:
                print("FAIL(random) %r got %r exp %r" % (t, got, exp))
        # full relevant RAM diff: no writes outside the two outputs (+ stack)
        for a in cpu.ram:
            if a in allowed or a in stack or a in ram:
                continue
            fails += 1
            if fails <= 8:
                print("FAIL(unexpected write) 0x%08X = %d" % (a, cpu.ram[a]))
        if fails >= 8:
            break

    print(f"calc_decel_fuel_cut_445AA @0x445AA: {tests} tests, {fails} failures")
    print(f"OK  calc_decel_fuel_cut_445AA @0x445AA  ({tests} inputs, 0 mismatches)"
          if fails == 0 else
          f"FAIL calc_decel_fuel_cut_445AA @0x445AA  ({fails} mismatches)")
    return 0 if fails == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
