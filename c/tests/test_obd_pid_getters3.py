#!/usr/bin/env python3
"""
Verify the three remaining OBD-mode-01 getters against the ACTUAL ROM bytes,
run in the SH-2E emulator (tools/sh2emu.py):

  0x55D9A  getEngineLoadOBD      [0xFFFFAA10] f32 cell + 3 sensor-flag bytes
  0x55E18  getIATOBD             [0xFFFFC12C/0xFFFFC130] dual f32 sensor cells
  0x55F7A  getCommandedLambdaOBD [0xFFFFADD4] u16 A/D word -> two-stage FPU chain

===================================================================
getEngineLoadOBD @0x55D9A  (NO floatToInt call — flag/threshold logic)
===================================================================
   mov.w 0x55DDC,r3   ; r3 = 0xAA10  -> RAM 0xFFFFAA10 f32 load cell
   mov.w 0x55DDE,r2   ; r2 = 0xAE97  -> RAM 0xFFFFAE97 u8 flags
   fmov.s @r3,fr4     ; fr4 = load f32
   mov.b @r2,r5       ; r5 = flags
   mov.w 0x55DE0,r1   ; r1 = 0xAD9C  -> RAM 0xFFFFAD9C u8 status
   mov.w 0x55DE2,r3   ; r3 = 0xAE96  -> RAM 0xFFFFAE96 u8 status2
   extu.b r5,r4
   mov.b @r1,r7       ; r7 = status
   cmp/eq #1,r0       ; (flags & 0xFF) == 1 ?
   bf/s 0x55DF4       ; flags != 1 -> status2 path
     mov.b @r3,r6     ; (delay) r6 = status2
   ; flags == 1:
   tst r7,r7          ; status == 0 ?
   bf/s 0x55DBE       ; status != 0 -> return 0x02
   ...
   bra 0x55E10 / mov #0x10,r4      ; return 0x10
   0x55DBE: (flags==1 confirmed) -> return 0x02
   0x55DF4: tst r6,r6 ; status2 == 0 ?
   bf/s 0x55E00       ; status2 != 0 -> threshold path
   ...
   bra 0x55E10 / mov #0x04,r4      ; return 0x04
   0x55E00: mov.l 0x55F28,r3 ; r3 = 0x00070138 (ROM f32 = 35.0)
   fmov.s @r3,fr3
   fcmp/gt fr4,fr3    ; emulator (FRn>FRm): T = (fr3 > fr4) = (35.0 > load)
   bf/s 0x55E0E       ; load >= 35.0 -> return 0x08
   ...
   bra 0x55E10 / mov #0x01,r4      ; return 0x01
   0x55E0E: mov #0x08,r4

  Model:
    flags==1  & status==0  -> 0x10
    flags==1  & status!=0  -> 0x02
    flags!=1  & status2==0 -> 0x04
    flags!=1  & status2!=0 & load<35.0  -> 0x01
    flags!=1  & status2!=0 & load>=35.0 -> 0x08
  (NaN load: fcmp/gt is false -> T=0 -> returns 0x08, matches Python NaN < x = False)

===================================================================
getIATOBD @0x55E18  (dual-sensor pick + ratio via FPU)
===================================================================
   fldi0 fr13                 ; fr13 = 0.0
   fmov fr13,fr5              ; fr5  = 0.0 (center for range check)
   mov.l 0x55F30,r1           ; r1 = 0x2440 (range/validity helper)
   mov.w 0x55F18,r3 ; fmov.s @r3,fr14  ; fr14 = A = RAM[0xFFFFC12C]
   mov.w 0x55F1A,r2 ; fmov.s @r2,fr15  ; fr15 = B = RAM[0xFFFFC130]
   fmov.s @r0,fr6             ; fr6 = pool @0x55F2C = 9.9999997e-06
   jsr @r1 / fmov fr15,fr4    ; call 0x2440(B, center=0.0, delta=1e-5)
   0x2440: T=(fr5-fr6 > fr4) = (-1e-5 > B)  -> return 1
           T=(fr4 > fr5+fr6) = (B > +1e-5)  -> return 1
           else return 0      => returns 1 iff |B| > 1e-5 (B not near zero)
   extu.b r0,r4
   tst r4,r4
   bt/s 0x55E58               ; helper==0 (|B|<=1e-5) -> return 255
   mov.w 0x55F1C,r4           ; r4 = 0x00FF
   ; B is a valid divisor:
   fmov.s @r0,fr3             ; fr3 = pool @0x55F34 = 100.0
   fmul fr3,fr14              ; fr14 = ts(A * 100.0)
   fmov fr14,fr4
   fdiv fr15,fr4              ; fr4 = ts((A*100.0)/B)
   fmov fr13,fr6              ; fr6 = 0.0 (offset)
   mov.l 0x55F3C,r3           ; r3 = 0x24D0 (floatToInt, 0xFF clamp)
   jsr @r3 / fmov.s @r0,fr5   ; fr5 = pool @0x55F38 = 0.39215687 (scale)
   bra 0x55E5A / mov r0,r4
   0x55E58: r4 = 0xFF
   rts / mov r4,r0

  Model:
    if |B| <= 1e-5  (f32): return 255
    else: floatToInt_FF((A*100.0)/B, offset 0, scale 0.39215687)  # 0..255

===================================================================
getCommandedLambdaOBD @0x55F7A  (multi-stage FPU chain)
===================================================================
   mova 0x560A8,r0 ; fmov.s @r0,fr4  ; fr4 = pool @0x560A8 = 7.6293945e-05
   mov.w 0x5608A,r3 ; mov.w @r3,r4   ; r4 = RAM[0xFFFFADD4] u16 A/D word
   mov.l 0x560AC,r2                 ; r2 = 0x24C0 (float-of-u16 helper)
   fmov fr15,fr5                    ; fr5 = 0.0 (offset)
   jsr @r2                          ; call 0x24C0(raw, scale, 0.0)
   0x24C0: extu.w r4,r4             ; raw &= 0xFFFF
           float fpul,fr3           ; fr3 = (float)raw
           fmac fr0,fr3,fr5         ; fr5 = ts(scale*(float)raw + 0.0)
           rts / fmov fr5,fr0       ; fr0 = result float
   fmov fr0,fr4                     ; fr4 = v1 = raw * 7.6293945e-05
   fmov fr15,fr6                    ; fr6 = 0.0 (offset)
   mov.l 0x560B8,r3                 ; r3 = 0x24D0
   fmov.s @r0,fr3                   ; fr3 = pool @0x560B0 = 20.0
   fmul fr3,fr4                     ; fr4 = ts(v1 * 20.0)
   jsr @r3 / fmov.s @r0,fr5         ; fr5 = pool @0x560B4 = 0.39215687 (scale)
   rts                              ; return r0 (0..255)

  Model:
    v1 = ts(7.6293945e-05 * (float)(raw & 0xFFFF))
    return floatToInt_FF(ts(v1 * 20.0), offset 0, scale 0.39215687)

Every FP op is single-precision (ts).  The f32 cells are seeded big-endian
in the RAM overlay; the lambda A/D is a big-endian u16 word.

Run: python3 c/tests/test_obd_pid_getters3.py [N]
"""
import os, sys, random, struct

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')

# ---- pool constants decoded from the ROM literal pools ----
DELTA_IAT    = struct.unpack('>f', bytes.fromhex('3727c5ac'))[0]  # @0x55F2C  = 1e-5 (IAT near-zero band)
IAT_GAIN     = struct.unpack('>f', bytes.fromhex('42c80000'))[0]  # @0x55F34  = 100.0
IAT_SCALE    = struct.unpack('>f', bytes.fromhex('3ec8c8c8'))[0]  # @0x55F38  = 100/255
LAMBDA_V2V   = struct.unpack('>f', bytes.fromhex('38a00000'))[0]  # @0x560A8  = 5/65536
LAMBDA_GAIN  = struct.unpack('>f', bytes.fromhex('41a00000'))[0]  # @0x560B0  = 20.0
LAMBDA_SCALE = struct.unpack('>f', bytes.fromhex('3ec8c8c8'))[0]  # @0x560B4  = 100/255
LOAD_LIMIT   = struct.unpack('>f', bytes.fromhex('420c0000'))[0]  # @0x00070138 = 35.0


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
    if not (B < -DELTA_IAT or B > DELTA_IAT):   # helper 0x2440 == 0 (B ~ 0)
        return 0xFF
    r = ts(ts(A * IAT_GAIN) / B)
    return _tofp(r, IAT_SCALE, 0.0, 0xFF)


def getCommandedLambdaOBD(raw):
    raw &= 0xFFFF
    v1 = ts(ts(LAMBDA_V2V * float(raw)) + 0.0)   # 0x24C0 fmac
    return _tofp(ts(v1 * LAMBDA_GAIN), LAMBDA_SCALE, 0.0, 0xFF)


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    random.seed(0x20260803)
    cpu = SH2(open(ROM, 'rb').read())
    fails = {'0x55D9A': 0, '0x55E18': 0, '0x55F7A': 0}

    def run_eng(v, fl, st, st2):
        ram = {}
        b = struct.pack('>f', ts(v))
        ram.update({0xFFFFAA10 + i: b[i] for i in range(4)})
        ram[0xFFFFAE97] = fl & 0xFF
        ram[0xFFFFAD9C] = st & 0xFF
        ram[0xFFFFAE96] = st2 & 0xFF
        return cpu.call(0x55D9A, ram=ram) & 0xFFFFFFFF

    def run_iat(A, B):
        ram = {}
        b = struct.pack('>f', ts(A))
        ram.update({0xFFFFC12C + i: b[i] for i in range(4)})
        b = struct.pack('>f', ts(B))
        ram.update({0xFFFFC130 + i: b[i] for i in range(4)})
        return cpu.call(0x55E18, ram=ram) & 0xFFFFFFFF

    def run_lambda(raw):
        raw &= 0xFFFF
        ram = {0xFFFFADD4: (raw >> 8) & 0xFF, 0xFFFFADD5: raw & 0xFF}
        return cpu.call(0x55F7A, ram=ram) & 0xFFFFFFFF

    for _ in range(N):
        # ---- engine load: cover all flag/status combinations ----
        v = ts(random.choice([random.uniform(-40.0, 120.0),
                              random.uniform(0.0, 40.0),
                              random.uniform(35.0, 100.0)]))
        fl  = random.choice([0, 1, 1, 1, 2, 0xFF])
        st  = random.choice([0, 0, 0, 1, 2, 0xFF])
        st2 = random.choice([0, 0, 0, 1, 2, 0xFF])
        if run_eng(v, fl, st, st2) != getEngineLoadOBD(v, fl, st, st2):
            fails['0x55D9A'] += 1

        # ---- IAT: dual sensor pick (B near zero -> 255, else ratio) ----
        A = ts(random.choice([random.uniform(-40.0, 215.0),
                              random.uniform(-100.0, 300.0),
                              random.uniform(-1e-3, 1e-3)]))
        B = ts(random.choice([random.uniform(-2e-5, 2e-5),      # near-zero band
                              random.uniform(0.3, 5.0),          # typical
                              random.uniform(-10.0, 10.0),
                              random.uniform(-1e-3, 1e-3)]))
        if run_iat(A, B) != getIATOBD(A, B):
            fails['0x55E18'] += 1

        # ---- commanded lambda: u16 A/D word through the FPU chain ----
        raw = random.choice([random.randint(0, 65535),
                             random.randint(0, 4096),
                             random.randint(0, 32768),
                             random.randint(32768, 65535)])
        if run_lambda(raw) != getCommandedLambdaOBD(raw):
            fails['0x55F7A'] += 1

    # ---- targeted edges (path + boundary coverage) ----
    # engine load: all five outputs, boundary v == 35.0, NaN load
    for v, fl, st, st2 in [
        (0.0,  1, 0, 0), (50.0, 1, 1, 0), (50.0, 0, 1, 0),   # 0x10 / 0x02 / 0x04
        (20.0, 0, 1, 1), (50.0, 0, 1, 1),                    # 0x01 / 0x08
        (35.0, 0, 1, 1), (34.999996, 0, 1, 1),               # v == / < 35.0
        (0.0,  2, 0xFF, 0), (100.0, 2, 5, 7),                # 0x04 / 0x08
        (float('nan'), 0, 1, 1),                              # NaN -> 0x08
    ]:
        v = ts(v)
        if run_eng(v, fl, st, st2) != getEngineLoadOBD(v, fl, st, st2):
            fails['0x55D9A'] += 1

    # IAT: near-zero band (incl. exact boundary), B==0 signs, ratio path
    for A, B in [
        (-40.0, 1.0), (25.0, 2.0), (100.0, 4.0), (0.0, 1.0),  # ratio path
        (25.0, 1e-6), (25.0, -1e-6), (25.0, 0.0),            # band -> 255 / B=0
        (25.0, 1e-5), (25.0, -1e-5),                         # exact band edge -> 255
        (-25.0, 0.0),                                        # B==0 inside band -> 255
        (float('nan'), 1.0),                                 # NaN A ratio -> -NaN -> 0
    ]:
        A, B = ts(A), ts(B)
        if run_iat(A, B) != getIATOBD(A, B):
            fails['0x55E18'] += 1

    # lambda: u16 edges
    for raw in [0, 1, 255, 1000, 4096, 6553, 32768, 65535, 65536, 5000]:
        if run_lambda(raw) != getCommandedLambdaOBD(raw):
            fails['0x55F7A'] += 1

    names = ['0x55D9A getEngineLoadOBD', '0x55E18 getIATOBD',
             '0x55F7A getCommandedLambdaOBD']
    print('inputs/function: %d + 10 targeted (seed 0x20260803)' % N)
    for n in names:
        e = n.split()[0][2:]
        print('  %-28s %s (%d)' % (n, "OK" if not fails['0x' + e] else "FAIL",
                                   fails['0x' + e]))
    sys.exit(1 if fails['0x55D9A'] or fails['0x55E18'] or fails['0x55F7A'] else 0)


if __name__ == '__main__':
    main()
