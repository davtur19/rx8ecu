#!/usr/bin/env python3
"""
Test vfad_control_35BBC (0x35BBC) via SH-2E emulator.

Decoded behavior (see docs/functions/vfad_control_35BBC.md):

  x = RAM32[0xFFFFB5B8] (f32 boost)
  cmd hysteresis:
      boost >= 5250.0               -> cmd = 1      (fcmp/gt: FRn>FRm = 5250>boost)
      boost < 5062.0 (5250-188)     -> cmd = 0
      5062 <= boost < 5250          -> cmd = old RAM8[0xFFFFC234] (hold)
  sm  = alternating_sensor_sm @0x5D800 (cmd)     ; verified separately
  RAM8[0xFFFFC234] = sm
  setRegister_REG_BIT_VAL(0xFFFFF754, 0x0400, sm==1)   ; @0x4BBC
  ; scratch: 0x2054 writes 0x000000F0 (stc SR, and #0xF0) to the stack slot
  ; at r15+4 (if sm==1) or r15 (else); the value is read back and passed
  ; to the no-op 0x2064.  Not a real output.
"""
import os, sys, struct, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2, ts
import test_alt_sensor_sm_5D800 as SM

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')
ADDR = 0x35BBC

B5B8 = 0xFFFFB5B8
C234 = 0xFFFFC234
F754 = 0xFFFFF754
PTR_CELL = 0xFFFFD500          # the sm output pointer target

def rb(ram, a):
    return ram.get(a & 0xFFFFFFFF, 0)

def r32(ram, a):
    return struct.unpack('>f', bytes(rb(ram, a + i) for i in range(4)))[0]

def rd16(ram, a):
    return (rb(ram, a) << 8) | rb(ram, a + 1)

def ref(init, rom):
    x = r32(init, B5B8)
    # hysteresis: on >= 5250, off < 5062 (= 5250-188), hold in band
    if x >= 5250.0:
        cmd = 1
    elif x < 5062.0:
        cmd = 0
    else:
        cmd = rb(init, C234)
    ret, ram = SM.ref(init, cmd)          # sm model (verified 0x5D800)
    ram[C234] = ret & 0xFF
    u16 = rd16(ram, F754)
    if ret == 1:
        u16 |= 0x0400
    else:
        u16 &= ~0x0400
    for i, b in enumerate(struct.pack('>H', u16 & 0xFFFF)):
        ram[F754 + i] = b
    return ram

def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    random.seed(20260731)
    fails = tests = 0
    for _ in range(10000):
        init = {}
        for i, b in enumerate(struct.pack('>f', ts(random.uniform(0, 12000)))):
            init[B5B8 + i] = b
        init[0x6025C] = random.choice([0, 1, 0xFF, 0x0F, 0xC0])
        for i, b in enumerate(struct.pack('>I', PTR_CELL)):
            init[0x60260 + i] = b
        for a in (0xFFFFD355, 0xFFFFD354, 0xFFFFD3A8, 0xFFFFD38F, C234):
            init[a] = random.randrange(0, 256)
        init[0xFFFFD350] = random.randrange(0, 0x10000)
        init[0xFFFFD352] = random.randrange(0, 0x10000)
        init[PTR_CELL] = random.randrange(0, 256)
        init[F754] = random.randrange(0, 256)
        init[F754 + 1] = random.randrange(0, 256)
        tests += 1
        cpu.call(ADDR, ram=dict(init))
        exp = ref(init, rom)
        bad = []
        if rb(cpu.ram, C234) != rb(exp, C234):
            bad.append('C234 emu=%d ref=%d' % (rb(cpu.ram, C234), rb(exp, C234)))
        if (cpu.ram[F754], cpu.ram[F754 + 1]) != (exp[F754], exp[F754 + 1]):
            bad.append('F754 emu=%04X ref=%04X' % (rd16(cpu.ram, F754), rd16(exp, F754)))
        for cell in (0xFFFFD355, 0xFFFFD38F, PTR_CELL):
            if rb(cpu.ram, cell) != rb(exp, cell):
                bad.append('%s emu=%d ref=%d' % (hex(cell), rb(cpu.ram, cell), rb(exp, cell)))
        if bad:
            fails += 1
            print("  vfad_control_35BBC FAIL x=%g:" % r32(init, B5B8), bad[:4])
            if fails >= 5:
                break
    print(f"vfad_control_35BBC: {tests} tests, {fails} failures")
    print("VFAD_0x35BBC:", "PASS" if fails == 0 else "FAIL")
    return 0 if fails == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
