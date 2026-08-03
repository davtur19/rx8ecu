#!/usr/bin/env python3
"""
Differential tests for the three OBD CAN-TX / PID-vector leaves against the
ACTUAL ROM bytes, run in the SH-2E emulator (tools/sh2emu.py):

  0x4C8C2  getOBDCANTXVars1   writes 8 bytes @0xFFFFCEAC-0xFFFFCEB3
  0x4C9C0  getOBDCANTXVars2   writes 8 bytes @0xFFFFCEC0-0xFFFFCEC7
  0x670B4  Vector             returns r0 (OBD PID support probe)

===================================================================
getOBDCANTXVars1 @0x4C8C2  (8-byte CAN TX buffer @0xFFFFCEAC)
===================================================================
   The getters are chained with the classic SH-2 delay-slot idiom: the
   `mov.b r0,@Rdisp` that follows each `jsr` runs BEFORE the call, so each
   store captures the PREVIOUS getter's return value:

     jsr @getEngineLoadOBD   ; 0x55D9A  (first call, result kept in r0)
     nop
     r2 = 0xFFFFCEAC; r3 = 0x55E14 (return-0 stub)
     jsr @r3 / mov.b r0,@r2  ; CEAC = getEngineLoadOBD()
     ...                     ; sub_55E14 runs -> r0 = 0
     r1 = 0xFFFFCEAD; r3 = 0x55E18 (getIATOBD)
     jsr @r3 / mov.b r0,@r1  ; CEAD = 0
     r2 = 0xFFFFCEAE; r3 = 0x55E66 (getMAFOBD)
     jsr @r3 / mov.b r0,@r2  ; CEAE = getIATOBD()
     r1 = 0xFFFFCEAF; r3 = 0x55E7C (getRPMOBD)
     jsr @r3 / mov.b r0,@r1  ; CEAF = getMAFOBD()
     r2 = 0xFFFFCEB0; r3 = 0x55EA2 (getSpeedOBD)
     jsr @r3 / mov.b r0,@r2  ; CEB0 = getRPMOBD()
     r1 = 0xFFFFCEB1 ...     ; CEB1 = getSpeedOBD()   (r0 still holds it)
     r3 = 0xFFFFCEB2, r2 = 0xFFFFCEB3, r4 = 0
     mov.b r0,@r1            ; CEB1 = getSpeedOBD()
     mov.b r4,@r3 / rts / mov.b r4,@r2   ; CEB2 = 0, CEB3 = 0

  Buffer layout (model):
     [0] = getEngineLoadOBD()   [1] = 0 (stub 0x55E14)
     [2] = getIATOBD()          [3] = getMAFOBD()
     [4] = getRPMOBD()          [5] = getSpeedOBD()
     [6] = 0                    [7] = 0

===================================================================
getOBDCANTXVars2 @0x4C9C0  (8-byte CAN TX buffer @0xFFFFCEC0)
===================================================================
   Same delay-slot pipeline:

     CEC0 = 0 (mov.b r4,@r3)
     r2 = 0xFFFFCEC1; r1 = 0x55EEA (getSTFTOBD)
     jsr @r1 / mov.b r4,@r2   ; CEC1 = 0 (STFT result discarded)
     r3 = 0xFFFFCEC2; r2 = 0x55F02 (getLTFTOBD)
     jsr @r2 / mov.b r0,@r3   ; CEC2 = getSTFTOBD()
     r1 = 0xFFFFCEC3; r3 = 0x55F64 (getThrottleOBD)
     jsr @r3 / mov.b r0,@r1   ; CEC3 = getLTFTOBD()
     r2 = 0xFFFFCEC4; r3 = 0x55F7A (getCommandedLambdaOBD)
     jsr @r3 / mov.w r0,@r2   ; CEC4..CEC5 = getThrottleOBD() u16 BE
     r1 = 0xFFFFCEC6; r3 = 0x55FA6 (O2-sensor status)
     jsr @r3 / mov.b r0,@r1   ; CEC6 = getCommandedLambdaOBD()
     r2 = 0xFFFFCEC7; rts / mov.b r0,@r2 ; CEC7 = sub_55FA6()

  Buffer layout (model):
     [0] = 0                     [1] = 0
     [2] = getSTFTOBD()          [3] = getLTFTOBD()
     [4:6] = getThrottleOBD() u16 BE
     [6] = getCommandedLambdaOBD()   [7] = sub_55FA6()
   sub_55FA6 @0x55FA6: RAM[0xFFFFA9E4] == 1 -> 1, else 4.

===================================================================
Vector @0x670B4  (OBD PID support probe, returns r0)
===================================================================
   if ((y & 0xFF) == 0) return 0
   t  = (y + 0xFF) & 0xE0                       ; column selector 0..7
   v  = (y & 0x1F) or 0x20;  idx = v - 1        ; bit index 0..31
   row = (x & 0xFF) - 1
   a  = u32@(0x5F6D8 + row*32 + (t>>5)*4)       ; support bitmask (ROM table)
   bit = 0x80000000 >> idx                      ; 0x44E0 bit probe
   return 0 if (bit & a) else 1                 ; 0 = supported, 1 = not

   sub_670E6 @0x670E6 computes the table address (row=(x-1), col=(t>>5));
   sub_673FA @0x673FA probes bit idx of the mask via 0x44E0 (verified:
   0x44E0(idx, 0x80000000) == 0x80000000 >> idx for 0..31, 0x80000000 for
   idx<0, 0 for idx>=0x20).  add #0xFF is SIGN-EXTENDED on SH-2 (=-1).

   The five getters referenced above (0x55D9A/0x55E18/0x55E66/0x55E7C/
   0x55EA2/0x55EEA/0x55F02/0x55F64/0x55F7A) are already verified bit-exact
   by test_obd_pid_getters.py / _2 / _3; their models are reused here.

Run: python3 c/tests/test_obd_vars_vector.py [N]
"""
import os, sys, random, struct

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')

# ---- pool constants decoded from the ROM literal pools ----
DELTA_IAT    = struct.unpack('>f', bytes.fromhex('3727c5ac'))[0]  # @0x55F2C  = 1e-5
IAT_GAIN     = struct.unpack('>f', bytes.fromhex('42c80000'))[0]  # @0x55F34  = 100.0
IAT_SCALE    = struct.unpack('>f', bytes.fromhex('3ec8c8c8'))[0]  # @0x55F38  = 100/255
LAMBDA_V2V   = struct.unpack('>f', bytes.fromhex('38a00000'))[0]  # @0x560A8  = 5/65536
LAMBDA_GAIN  = struct.unpack('>f', bytes.fromhex('41a00000'))[0]  # @0x560B0  = 20.0
LAMBDA_SCALE = struct.unpack('>f', bytes.fromhex('3ec8c8c8'))[0]  # @0x560B4  = 100/255
LOAD_LIMIT   = struct.unpack('>f', bytes.fromhex('420c0000'))[0]  # @0x00070138 = 35.0
SCALE_THRO   = struct.unpack('>f', bytes.fromhex('3c23d70a'))[0]  # @0x560A0  = 0.01
VEC_TABLE    = 0x5F6D8                                            # OBD PID support table
ROM_LEN      = os.path.getsize(ROM)


def _ftrc(f):
    """Mirror the emulator's ftrc (FRn -> FPUL): NaN -> 0x80000000,
    overflow saturates to 0x7FFFFFFF / 0x80000000, else trunc toward zero."""
    if f != f:
        return -0x80000000
    if f >= 2147483648.0:
        return 0x7FFFFFFF
    if f < -2147483648.0:
        return -0x80000000
    return int(f)


def _tofp(num, sca, off, hi):
    i = _ftrc(ts(ts(ts(num - off) / sca) + 0.5))
    return 0 if i < 0 else (hi if i > hi else i)


def _floatToInt(n, s, o):
    return _tofp(n, s, o, 0xFF)


# ---- pure-Python references (bit-exact against the ROM math) ----
def getEngineLoadOBD(v, fl, st, st2):
    v = ts(v)
    if (fl & 0xFF) == 1:
        return 0x10 if (st & 0xFF) == 0 else 0x02
    if (st2 & 0xFF) == 0:
        return 0x04
    return 0x01 if v < LOAD_LIMIT else 0x08


def getIATOBD(A, B):
    A, B = ts(A), ts(B)
    if not (B < -DELTA_IAT or B > DELTA_IAT):      # helper 0x2440 == 0
        return 0xFF
    return _tofp(ts(ts(A * IAT_GAIN) / B), IAT_SCALE, 0.0, 0xFF)


def getMAFOBD(v):
    return _floatToInt(v, 1.0, -40.0)


def getRPMOBD(v):
    return _floatToInt(ts(ts(v - 1.0) * 100.0), 0.78125, -100.0)


def getSpeedOBD(v):
    return _floatToInt(ts(v * 100.0), 0.78125, -100.0)


def getSTFTOBD(v):
    return _floatToInt(v, 0.5, -64.0)


def getLTFTOBD(v):
    return _floatToInt(v, 1.0, -40.0)


def getThrottleOBD(v):
    return _tofp(v, SCALE_THRO, 0.0, 0xFFFF)


def getCommandedLambdaOBD(raw):
    raw &= 0xFFFF
    v1 = ts(ts(LAMBDA_V2V * float(raw)) + 0.0)     # 0x24C0 fmac
    return _tofp(ts(v1 * LAMBDA_GAIN), LAMBDA_SCALE, 0.0, 0xFF)


def sub55FA6(b):
    """@0x55FA6: RAM[0xFFFFA9E4] == 1 -> 1 else 4."""
    return 1 if (b & 0xFF) == 1 else 4


def getOBDCANTXVars1(load, fl, st, st2, iatA, iatB, maf, rpm, spd):
    """Model @0x4C8C2 — delay-slot stores capture the PREVIOUS call's r0."""
    o = [0] * 8
    o[0] = getEngineLoadOBD(load, fl, st, st2)     # 0x55D9A result
    o[1] = 0                                       # sub_55E14 return-0 stub
    o[2] = getIATOBD(iatA, iatB)                   # 0x55E18
    o[3] = getMAFOBD(maf)                          # 0x55E66
    o[4] = getRPMOBD(rpm)                          # 0x55E7C
    o[5] = getSpeedOBD(spd)                        # 0x55EA2
    o[6] = 0
    o[7] = 0
    return bytes(o)


def getOBDCANTXVars2(stft, ltft, thr, lam, b9e4):
    """Model @0x4C9C0 — same delay-slot pipeline."""
    o = [0] * 8
    o[0] = 0
    o[1] = 0
    o[2] = getSTFTOBD(stft)                        # stored in LTFT-call delay
    o[3] = getLTFTOBD(ltft)                        # stored in throttle delay
    t = getThrottleOBD(thr)
    o[4] = (t >> 8) & 0xFF                         # u16 BE stored in lambda delay
    o[5] = t & 0xFF
    o[6] = getCommandedLambdaOBD(lam)              # stored in 55FA6 delay
    o[7] = sub55FA6(b9e4)
    return bytes(o)


def vector(x, y, rom):
    """Model @0x670B4 — OBD PID support probe."""
    y &= 0xFFFFFFFF
    if (y & 0xFF) == 0:
        return 0
    t = (y + 0xFF) & 0xE0                          # add #0xFF sign-ext = -1
    v = y & 0x1F
    if v == 0:
        v = 0x20
    idx = v - 1
    bit = (0x80000000 >> idx) & 0xFFFFFFFF         # 0x44E0 probe
    row = ((x & 0xFF) - 1) & 0xFFFFFFFF
    addr = (VEC_TABLE + ((row << 5) & 0xFFFFFFFF) + ((t >> 5) << 2)) & 0xFFFFFFFF
    if addr + 4 > ROM_LEN:
        a = 0                                      # emulator reads 0 past ROM
    else:
        a = struct.unpack('>I', rom[addr:addr + 4])[0]
    return 0 if (bit & a) else 1


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    random.seed(0x20260803)
    cpu = SH2(open(ROM, 'rb').read())
    rom = cpu.rom
    fails = {'0x4C8C2': 0, '0x4C9C0': 0, '0x670B4': 0}

    def seed_f32(ram, addr, v):
        b = struct.pack('>f', ts(v))
        for i in range(4):
            ram[addr + i] = b[i]

    for _ in range(N):
        # ---- getOBDCANTXVars1: engine-load flags + 4 f32 cells ----
        load = ts(random.choice([random.uniform(-40.0, 120.0),
                                 random.uniform(0.0, 40.0),
                                 random.uniform(35.0, 100.0)]))
        fl  = random.choice([0, 1, 1, 1, 2, 0xFF])
        st  = random.choice([0, 0, 0, 1, 2, 0xFF])
        st2 = random.choice([0, 0, 0, 1, 2, 0xFF])
        iatA = ts(random.uniform(-40.0, 215.0))
        iatB = ts(random.choice([random.uniform(-2e-5, 2e-5),
                                 random.uniform(0.3, 5.0),
                                 random.uniform(-10.0, 10.0)]))
        maf = ts(random.uniform(-10.0, 200.0))
        rpm = ts(random.uniform(0.0, 8000.0))
        spd = ts(random.uniform(0.0, 300.0))
        ram = {}
        seed_f32(ram, 0xFFFFAA10, load)
        ram[0xFFFFAE97] = fl & 0xFF
        ram[0xFFFFAD9C] = st & 0xFF
        ram[0xFFFFAE96] = st2 & 0xFF
        seed_f32(ram, 0xFFFFC12C, iatA)
        seed_f32(ram, 0xFFFFC130, iatB)
        seed_f32(ram, 0xFFFF9F70, maf)
        seed_f32(ram, 0xFFFFAE64, rpm)
        seed_f32(ram, 0xFFFFB140, spd)
        cpu.call(0x4C8C2, ram=ram)
        got = bytes(cpu.rd(0xFFFFCEAC + i, 1) for i in range(8))
        exp = getOBDCANTXVars1(load, fl, st, st2, iatA, iatB, maf, rpm, spd)
        if got != exp:
            fails['0x4C8C2'] += 1

        # ---- getOBDCANTXVars2: STFT/LTFT/throttle f32 + lambda u16 + status ----
        stft = ts(random.uniform(-50.0, 50.0))
        ltft = ts(random.uniform(-50.0, 50.0))
        thr  = ts(random.choice([random.uniform(0.0, 100.0),
                                 random.uniform(-5.0, 105.0)]))
        lam  = random.choice([random.randint(0, 65535),
                              random.randint(0, 4096),
                              random.randint(32768, 65535)])
        b9e4 = random.choice([0, 1, 1, 2, 0xFF])
        ram = {}
        seed_f32(ram, 0xFFFFA63C, stft)
        seed_f32(ram, 0xFFFF9F60, ltft)
        seed_f32(ram, 0xFFFFAA88, thr)
        ram[0xFFFFADD4] = (lam >> 8) & 0xFF
        ram[0xFFFFADD5] = lam & 0xFF
        ram[0xFFFFA9E4] = b9e4 & 0xFF
        cpu.call(0x4C9C0, ram=ram)
        got = bytes(cpu.rd(0xFFFFCEC0 + i, 1) for i in range(8))
        exp = getOBDCANTXVars2(stft, ltft, thr, lam, b9e4)
        if got != exp:
            fails['0x4C9C0'] += 1

        # ---- Vector: PID x (0..255) vs byte-selector y ----
        x = random.choice([0, 1, 2, 3, 4, 5, 6, 7, 0x0C, 0x0D, 0x0E, 0x0F,
                           0x10, 0x11, 0x14, 0x20, 0x40, 0x60, 0x80, 0xA0,
                           0xC0, 0xE0, 0xFE, 0xFF, random.randint(0, 255)])
        y = random.choice([0, 0, 0, 0x01, 0x1F, 0x20, 0x21, 0x40, 0x60,
                           0x7F, 0x80, 0xA0, 0xC0, 0xE0, 0xFF,
                           random.randint(0, 255)])
        if cpu.call(0x670B4, r4=x, r5=y) & 0xFFFFFFFF != vector(x, y, rom):
            fails['0x670B4'] += 1

    # ---- targeted edges (path + boundary coverage) ----
    # vars1: every engine-load output, all flag combos, 8-byte layout pin
    for load, fl, st, st2, iatA, iatB, maf, rpm, spd in [
        (0.0,   1, 0, 0, 25.0, 2.0, 0.0,   0.0,   0.0),   # 0x10 engine load
        (50.0,  1, 1, 0, 25.0, 2.0, 0.0,   0.0,   0.0),   # 0x02
        (50.0,  0, 1, 0, 25.0, 2.0, 0.0,   0.0,   0.0),   # 0x04
        (20.0,  0, 1, 1, 25.0, 2.0, 0.0,   0.0,   0.0),   # 0x01
        (50.0,  0, 1, 1, 25.0, 2.0, 0.0,   0.0,   0.0),   # 0x08
        (35.0,  0, 1, 1, 25.0, 2.0, 0.0,   0.0,   0.0),   # load == 35.0 -> 0x08
        (0.0,   0, 1, 1, 25.0, 1e-6, 0.0,  0.0,   0.0),   # IAT band -> 0xFF
        (0.0,   0, 1, 1, 25.0, 2.0, 0.0,   0.0,   0.0),   # IAT ratio -> 0x4F
        (0.0,   0, 1, 1, 25.0, 2.0, 200.0, 0.0,   0.0),   # MAF clamp -> 0xFF
        (0.0,   0, 1, 1, 25.0, 2.0, 0.0,   100.0, 0.0),   # RPM path
        (0.0,   0, 1, 1, 25.0, 2.0, 0.0,   0.0,   100.0), # Speed path
        (float('nan'), 0, 1, 1, 25.0, 2.0, 0.0, 0.0, 0.0), # NaN load -> 0x08
    ]:
        ram = {}
        seed_f32(ram, 0xFFFFAA10, load)
        ram[0xFFFFAE97] = fl & 0xFF
        ram[0xFFFFAD9C] = st & 0xFF
        ram[0xFFFFAE96] = st2 & 0xFF
        seed_f32(ram, 0xFFFFC12C, iatA)
        seed_f32(ram, 0xFFFFC130, iatB)
        seed_f32(ram, 0xFFFF9F70, maf)
        seed_f32(ram, 0xFFFFAE64, rpm)
        seed_f32(ram, 0xFFFFB140, spd)
        cpu.call(0x4C8C2, ram=ram)
        got = bytes(cpu.rd(0xFFFFCEAC + i, 1) for i in range(8))
        exp = getOBDCANTXVars1(load, fl, st, st2, iatA, iatB, maf, rpm, spd)
        if got != exp:
            fails['0x4C8C2'] += 1

    # vars2: each buffer slot pinned to its source getter
    for stft, ltft, thr, lam, b9e4 in [
        (0.0,   0.0,   0.0,   0,     0),    # all-zero path
        (-10.0, -10.0, 50.0,  4096,  1),    # STFT/LTFT center-ish, status 1
        (0.0,   0.0,   100.0, 65535, 0xFF), # throttle clamp, lambda clamp
        (-40.0, -40.0, 0.0,   32768, 2),    # negatives, mid lambda
        (50.0,  50.0,  0.5,   1,     1),    # throttle -> 0x0032, status 1
    ]:
        ram = {}
        seed_f32(ram, 0xFFFFA63C, stft)
        seed_f32(ram, 0xFFFF9F60, ltft)
        seed_f32(ram, 0xFFFFAA88, thr)
        ram[0xFFFFADD4] = (lam >> 8) & 0xFF
        ram[0xFFFFADD5] = lam & 0xFF
        ram[0xFFFFA9E4] = b9e4 & 0xFF
        cpu.call(0x4C9C0, ram=ram)
        got = bytes(cpu.rd(0xFFFFCEC0 + i, 1) for i in range(8))
        exp = getOBDCANTXVars2(stft, ltft, thr, lam, b9e4)
        if got != exp:
            fails['0x4C9C0'] += 1

    # Vector: y==0 gate, all 8 columns, all 32 bit indices, x edges
    for x, y in [
        (0x0C, 0),                          # y==0 -> return 0
        (0x0D, 0),                          # y==0 -> return 0
        (0x00, 0x01),                       # x=0 -> row -1 (wraps into ROM)
        (0xFF, 0xFF),                       # x=255 row 254, y col 7
        (0x01, 0x01), (0x01, 0x20), (0x01, 0x40), (0x01, 0x60),
        (0x01, 0x80), (0x01, 0xA0), (0x01, 0xC0), (0x01, 0xE0),  # all cols
        (0x0C, 0x1F), (0x0C, 0x20), (0x0C, 0x21), (0x0C, 0x3F),  # idx edges
        (0x0D, 0x40), (0x0E, 0x40), (0x0F, 0x40),
        (0x10, 0xE0), (0x14, 0xE0), (0x20, 0xE0), (0x40, 0xE0),
        (0x0C, 0x80000001),                 # high bits flow into t, &0xFF == 1
        (0x0C, 0x81000021),                 # high bits + non-trivial idx/col
        (0x0C, 0x101), (0x0C, 0xFFFF),      # y above 0xFF
    ]:
        y &= 0xFFFFFFFF
        if cpu.call(0x670B4, r4=x, r5=y) & 0xFFFFFFFF != vector(x, y, rom):
            fails['0x670B4'] += 1

    names = ['0x4C8C2 getOBDCANTXVars1', '0x4C9C0 getOBDCANTXVars2',
             '0x670B4 Vector']
    print('inputs/function: %d + targeted (seed 0x20260803)' % N)
    for n in names:
        e = n.split()[0][2:]
        print('  %-28s %s (%d)' % (n, "OK" if not fails['0x' + e] else "FAIL",
                                   fails['0x' + e]))
    sys.exit(1 if any(fails.values()) else 0)


if __name__ == '__main__':
    main()
