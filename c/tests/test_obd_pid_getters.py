#!/usr/bin/env python3
"""
Verify the OBD mode-01 PID getters against the ACTUAL ROM bytes, run in the
SH-2E emulator (tools/sh2emu.py).

All five getters follow one pattern: read a single-precision float from a RAM
sensor cell (16-bit PC-relative or 32-bit literal pointer) and feed it through
floatToInt @0x24D0 — the verified "clamp((num-off)/scale + 0.5, 0, 255)" helper
(see test_math_primitives.py).  The scale/offset constants come from the ROM
literal pool; they differ from the lift comments for MAF (lift claims
*100, 0xFFFF clamp — the ROM actually uses scale=1.0, offset=-40.0, 0xFF clamp
via floatToInt), which this test pins down:

  0x55E66  getMAFOBD   [0xFFFF9F70]  -> floatToInt(v, 1.0,    -40.0)
  0x55E7C  getRPMOBD   [0xFFFFAE64]  -> floatToInt((v-1)*100, 0.78125, -100.0)
  0x55EA2  getSpeedOBD [0xFFFFB140]  -> floatToInt(v*100,     0.78125, -100.0)
  0x55EEA  getSTFTOBD  [0xFFFFA63C]  -> floatToInt(v, 0.5,    -64.0)
  0x55F02  getLTFTOBD  [0xFFFF9F60]  -> floatToInt(v, 1.0,    -40.0)

The 0x24D0 converter clamps to 0x00FF (mov.w 0x24F8,r5 loads 255), so the
getters return 0..255.  Every intermediate FP op is single-precision (ts).

Run: python3 c/tests/test_obd_pid_getters.py [N]
"""
import os, sys, random, struct

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')


def _tofp(num, sca, off, hi):
    i = int(ts(ts(ts(num - off) / sca) + 0.5))
    return 0 if i < 0 else (hi if i > hi else i)


def floatToInt(n, s, o):
    return _tofp(n, s, o, 0xFF)


# ---- pure-Python references (bit-exact against the ROM math) ----
def getMAFOBD(v):   return floatToInt(v, 1.0, -40.0)
def getRPMOBD(v):   return floatToInt(ts(ts(v - 1.0) * 100.0), 0.78125, -100.0)
def getSpeedOBD(v): return floatToInt(ts(v * 100.0), 0.78125, -100.0)
def getSTFTOBD(v):  return floatToInt(v, 0.5, -64.0)
def getLTFTOBD(v):  return floatToInt(v, 1.0, -40.0)

# entry, sensor-cell pointer, reference
FNS = [
    (0x55E66, 0xFFFF9F70, getMAFOBD),
    (0x55E7C, 0xFFFFAE64, getRPMOBD),
    (0x55EA2, 0xFFFFB140, getSpeedOBD),
    (0x55EEA, 0xFFFFA63C, getSTFTOBD),
    (0x55F02, 0xFFFF9F60, getLTFTOBD),
]


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 30000
    cpu = SH2(open(ROM, 'rb').read())
    fails = {}

    def chk(name, cond):
        if not cond:
            fails[name] = fails.get(name, 0) + 1

    def run(entry, ptr, v):
        b = struct.pack('>f', ts(v))
        ram = {ptr + i: b[i] for i in range(4)}
        return cpu.call(entry, ram=ram) & 0xFFFFFFFF

    for _ in range(N):
        v = ts(random.choice([random.uniform(-80.0, 300.0),
                              random.uniform(0.0, 8.0),
                              random.uniform(0.0, 1.0),
                              random.uniform(-1e-4, 1e-4)]))
        for entry, ptr, ref in FNS:
            r0 = run(entry, ptr, v)
            chk('0x%X' % entry, r0 == ref(v))

    # targeted edges
    for v in [0.0, 1.0, 2.0, 100.0, 255.0, -1.0, -64.0, -40.0, 40.0, 64.0]:
        v = ts(v)
        for entry, ptr, ref in FNS:
            chk('0x%X' % entry, run(entry, ptr, v) == ref(v))

    names = ['0x55E66 getMAFOBD', '0x55E7C getRPMOBD', '0x55EA2 getSpeedOBD',
             '0x55EEA getSTFTOBD', '0x55F02 getLTFTOBD']
    print('inputs/function: %d + 10 targeted' % N)
    for n in names:
        e = int(n[2:8], 16)
        print('  %-24s %s (%d)' % (n, "OK" if not fails.get('0x%X' % e) else "FAIL",
                                   fails.get('0x%X' % e, 0)))
    sys.exit(1 if any(fails.get('0x%X' % e, 0) for e in (0x55E66, 0x55E7C, 0x55EA2, 0x55EEA, 0x55F02)) else 0)


if __name__ == '__main__':
    main()
