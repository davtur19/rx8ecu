#!/usr/bin/env python3
"""
test_maf_limits.py — mini differential test of the MAF plausibility LIMITS in
getMAFSensorValue @0x745C (lift: c/maf_sensor_value.c).

Scope: pin the raw-ADC plausibility thresholds and the status-byte mapping
that the lift historically got wrong (addresses 0x6D402/0x6D404 + swapped
normal/low branches).  The REAL ROM bytes of 0x745C run in the SH-2E emulator
(tools/sh2emu.py), including the ROM's own TwoDLookup @0x2068; the status byte
at 0xFFFF9F7C and the f32 at 0xFFFF9F78 are compared bit-exactly against a
pure-Python model derived from the disasm.

Disasm evidence (`python3 tools/disasm_sh2e.py 0x745C 90 60E1D400.bin`):
  adc   = u16[0xFFFF9EEA]
  fr4   = float(adc) * f32[0x74B4]           # 7.62939453125e-5 ADC->V scale
  fr0   = TwoDLookup(desc=0x6A0E4, x=fr4)    # FP32 48-pt curve (no scale/off)
  f32[0xFFFF9F78] = fr0
  thr1  = u16[0x6CF02] = 64225 (0xFAE1)      # mov.l 0x74C8,r1 ; mov.w @r1,r3
  thr2  = u16[0x6CF04] =  2752 (0x0AC0)      # mov.l 0x74CC,r0 ; mov.w @r0,r3
  status: adc>=thr1 -> 1 ; adc>=thr2 -> 0 ; else -> 2   (cmp/ge; @0xFFFF9F7C)

Run from repo root:  python3 c/tests/test_maf_limits.py [N]
                     (N = random vectors, default 3000)
"""
import os, random, struct, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, ts  # noqa: E402

rom = open(os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin'), 'rb').read()
cpu = SH2(rom)

ADDR = 0x745C
ADC = 0xFFFF9EEA   # u16 raw MAF ADC
OUTF = 0xFFFF9F78  # f32 mass air flow
OUTS = 0xFFFF9F7C  # u8 status

SCALE = struct.unpack('>f', rom[0x74B4:0x74B8])[0]
THR1 = int.from_bytes(rom[0x6CF02:0x6CF04], 'big')   # 64225 upper
THR2 = int.from_bytes(rom[0x6CF04:0x6CF06], 'big')   # 2752  lower

# ---- TwoDLookup type-0 (FP32 cells) @0x2068 for map desc 0x6A0E4 ----
DESC = 0x6A0E4
N = int.from_bytes(rom[DESC:DESC + 2], 'big')           # 48
AXP = struct.unpack('>I', rom[DESC + 4:DESC + 8])[0]    # 0x6FB18
VP = struct.unpack('>I', rom[DESC + 8:DESC + 12])[0]    # 0x6FBD8
AXIS = [struct.unpack('>f', rom[AXP + 4 * i:AXP + 4 * i + 4])[0]
        for i in range(N)]
VALS = [struct.unpack('>f', rom[VP + 4 * i:VP + 4 * i + 4])[0]
        for i in range(N)]


def twod_fp32(x):
    x = ts(x)
    if not (x < AXIS[N - 1]):
        i, t = N - 1, ts(0.0)
    elif x < AXIS[0]:
        i, t = 0, ts(0.0)
    else:
        i = 0
        while i + 1 < N and not (AXIS[i] <= x < AXIS[i + 1]):
            i += 1
        t = ts(ts(x - AXIS[i]) / ts(AXIS[i + 1] - AXIS[i]))
    v0 = VALS[i]
    v1 = VALS[i + 1] if i + 1 < N else VALS[i]
    if t == 0.0:
        interp = v0
    else:
        interp = ts(t * ts(v1 - v0) + v0)   # fmac: one rounding
    return interp


def ref(adc):
    """Pure-Python model of 0x745C — mirrors the disasm exactly."""
    x = ts(ts(float(adc)) * SCALE)          # fmul in jsr delay slot
    maf = twod_fp32(x)
    if adc >= THR1:                         # cmp/ge r3(thr1),r5(adc)
        status = 1                          # over-range high
    elif adc >= THR2:
        status = 0                          # normal
    else:
        status = 2                          # over-range low
    return maf, status


def main():
    Nc = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    rng = random.Random(0x6CF02)
    tests = fails = 0

    # threshold edges + sign/unsigned boundary + extremes
    edge = {0, 1, 2, THR2 - 1, THR2, THR2 + 1, THR1 - 1, THR1, THR1 + 1,
            0x7FFF, 0x8000, 0xFFFE, 0xFFFF}

    def run(adc):
        cpu.call(ADDR, ram={ADC: (adc >> 8) & 0xFF, ADC + 1: adc & 0xFF})
        vb = bytes(cpu.ram.get(OUTF + i, 0) for i in range(4))
        return struct.unpack('>I', vb)[0], cpu.ram.get(OUTS, 0)

    def check(adc):
        nonlocal tests, fails
        gotf, gots = run(adc)
        maf, status = ref(adc)
        wantf = struct.unpack('>I', struct.pack('>f', ts(maf)))[0]
        tests += 1
        if gotf != wantf or gots != status:
            fails += 1
            if fails <= 10:
                print("FAIL adc=%d got=(%08X,%d) want=(%08X,%d)"
                      % (adc, gotf, gots, wantf, status))

    for adc in sorted(edge):
        check(adc)
    # seeded random sweep across the full u16 range
    for _ in range(Nc):
        check(rng.getrandbits(16))

    print("test_maf_limits @0x745C: %d tests, %d failures" % (tests, fails))
    if fails == 0:
        print("OK  MAF limits (thr1=%d, thr2=%d, status map "
              "adc>=thr1->1/adc>=thr2->0/else->2): %d inputs, 0 mismatches"
              % (THR1, THR2, tests))
        return 0
    print("FAIL MAF limits (%d mismatches)" % fails)
    return 1


if __name__ == '__main__':
    sys.exit(main())
