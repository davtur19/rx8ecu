#!/usr/bin/env python3
"""
test_readECMVoltage_735C.py — differential test of readECMVoltage @0x735C
(lift: c/coolant_temperature_sensor.c).  The real ROM bytes execute in the
SH-2E emulator (the delta-limit helper @0x2510 runs natively); the resulting
f32 at 0xFFFF9F68 and u16 at 0xFFFF9F6C are compared bit-exactly against a
pure-Python model from the disassembly.

Disasm (`python3 tools/disasm_sh2e.py 0x735C 70 60E1D400.bin`):

    curr = u16[0xFFFF9F00] ; prev = u16[0xFFFF9F6C] ; th = u16[0x6CF50]=256
    clamped = helper2510(r4=curr, r5=prev, r6=th)
    helper2510 @0x2510:  fr2=2^-8 ; fr3=float(th)*fr2 ; fr1=1-fr3
                        fr3=float(prev)-float(curr) ; fr1=fr3*fr1
                        r3=ftrc(fr1) (trunc->0) ; r0 = curr+r3
    voltage = (clamped&0xFFFF) / 65536.0 * f32[0x6CF4C]  (single-precision each step)
    f32[0xFFFF9F68] = voltage ; u16[0xFFFF9F6C] = clamped&0xFFFF

Run from repo root:  python3 c/tests/test_readECMVoltage_735C.py [N]
"""
import os, random, struct, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, ts  # noqa: E402

rom = open(os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin'), 'rb').read()
cpu = SH2(rom)

ADDR = 0x735C
CUR = 0xFFFF9F00   # u16 current ADC
PRV = 0xFFFF9F6C   # u16 previous ADC (in/out)
OUT = 0xFFFF9F68   # f32 voltage

TH  = int.from_bytes(rom[0x6CF50:0x6CF52], 'big')          # 256
DIV = struct.unpack('>f', rom[0x6CF4C:0x6CF50])[0]         # 20.0
INV = struct.unpack('>f', rom[0x73B0:0x73B4])[0]           # 65536.0
K   = struct.unpack('>f', rom[0x2538:0x253C])[0]           # 0.00390625


def helper2510(curr, prev, th):
    """Model of @0x2510 delta limiter, single-precision steps."""
    f1 = ts(1.0 - ts(float(th) * K))
    f3 = ts(float(prev) - float(curr))
    r = ts(f3 * f1)
    tr = int(r)               # ftrc: truncate toward zero
    return curr + tr


def ref(curr, prev):
    clamped = helper2510(curr, prev, TH) & 0xFFFF
    v = ts(ts(clamped / INV) * DIV)
    return (v, clamped)


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rng = random.Random(0x735C)
    tests = fails = 0
    edges = (0, 1, 0x7FFF, 0x8000, 0xFFFE, 0xFFFF)
    vals = list(edges)
    vals += [TH - 1, TH, TH + 1, 2 * TH, 65535 - TH, 32767, 32768, 100, 40000]
    pairs = []
    for a in vals:
        for b in vals:
            pairs.append((a, b))
    rng.shuffle(pairs)
    if len(pairs) > 1500:
        pairs = pairs[:1500]

    def run(curr, prev):
        cpu.call(ADDR, ram={
            CUR: (curr >> 8) & 0xFF, CUR + 1: curr & 0xFF,
            PRV: (prev >> 8) & 0xFF, PRV + 1: prev & 0xFF,
        })
        vb = bytes(cpu.ram.get(OUT + i, 0) for i in range(4))
        got_v = struct.unpack('>I', vb)[0]
        got_p = (cpu.ram.get(PRV, 0) << 8) | cpu.ram.get(PRV + 1, 0)
        return got_v, got_p

    for (curr, prev) in pairs:
        got_v, got_p = run(curr, prev)
        v, c = ref(curr, prev)
        want_v = struct.unpack('>I', struct.pack('>f', ts(v)))[0]
        tests += 1
        if got_v != want_v or got_p != c:
            fails += 1
            if fails <= 10:
                print("FAIL curr=%d prev=%d got=(%08X,%04X) want=(%08X,%04X)"
                      % (curr, prev, got_v, got_p, want_v, c))
    for _ in range(N):
        curr = rng.getrandbits(16)
        prev = rng.getrandbits(16)
        got_v, got_p = run(curr, prev)
        v, c = ref(curr, prev)
        want_v = struct.unpack('>I', struct.pack('>f', ts(v)))[0]
        tests += 1
        if got_v != want_v or got_p != c:
            fails += 1
            if fails <= 10:
                print("FAIL curr=%d prev=%d got=(%08X,%04X) want=(%08X,%04X)"
                      % (curr, prev, got_v, got_p, want_v, c))
    print("readECMVoltage @0x735C: %d tests, %d failures" % (tests, fails))
    if fails == 0:
        print("OK  readECMVoltage @0x735C (%d inputs, 0 mismatches)" % tests)
        return 0
    print("FAIL readECMVoltage @0x735C (%d mismatches)" % fails)
    return 1


if __name__ == '__main__':
    sys.exit(main())