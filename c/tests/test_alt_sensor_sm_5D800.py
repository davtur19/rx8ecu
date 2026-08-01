#!/usr/bin/env python3
"""
Test alternating_sensor_sm (0x5D800) via SH-2E emulator — the second
instance of the alternating sensor state machine (sibling of 0x5D3E8),
reached from the VFAD control task (0x35BBC).

  r6 = 0x60254                 ; struct base
  ptr = RAM32[0x60260]         ; [r6+0xC] output target pointer
  mask = RAM8[0x6025C]         ; [r6+8]  sensor mask (ROM default 0xC0)

  if RAM8[0xFFFFD355] == 0:                    ; first block
      masked = RAM8[0xFFFFD3A8] & mask
      if RAM16[0xFFFFD350] == 0x17C8:
          if masked != 0:
              RAM8[@ptr] = RAM8[0xFFFFD354]
              if RAM8[0xFFFFD354] == 7:
                  RAM8[0xFFFFD38F] = (RAM16[0xFFFFD352] >> 8) & 0xFF
              RAM8[0xFFFFD355] = 1
          else:
              RAM8[@ptr] = 0
              RAM8[0xFFFFD355] = 2
      else:
          if masked == 0:
              RAM8[@ptr] = 0
          RAM8[0xFFFFD355] = 0
  ; second block (always runs)
  out = RAM8[@ptr]
  if out == 0:
      RAM8[0xFFFFD38F] = (r4 == 1) ? 1 : 0   ; r6+=0x1E delay executes in both branches
      return r4
  if out == 5 or out == 7:
      return (RAM8[0xFFFFD38F] == 1) ? 1 : 0
  return r4
"""
import os, sys, struct, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')
ADDR = 0x5D800

PTR_CELL = 0xFFFFD500          # scratch cell the output pointer points at

def rb(ram, a):
    return ram.get(a & 0xFFFFFFFF, 0)

def rd16(ram, a):
    return (rb(ram, a) << 8) | rb(ram, a + 1)

def rd32(ram, a):
    return (rb(ram, a) << 24) | (rb(ram, a + 1) << 16) | (rb(ram, a + 2) << 8) | rb(ram, a + 3)

def ref(ram_in, r4):
    ram = dict(ram_in)
    ptr = rd32(ram, 0x60260)
    mask = rb(ram, 0x6025C)
    if rb(ram, 0xFFFFD355) == 0:
        masked = rb(ram, 0xFFFFD3A8) & mask
        if rd16(ram, 0xFFFFD350) == 0x17C8:
            if masked != 0:
                ram[ptr & 0xFFFFFFFF] = rb(ram, 0xFFFFD354)
                if rb(ram, 0xFFFFD354) == 7:
                    ram[0xFFFFD38F] = (rd16(ram, 0xFFFFD352) >> 8) & 0xFF
                ram[0xFFFFD355] = 1
            else:
                ram[ptr & 0xFFFFFFFF] = 0
                ram[0xFFFFD355] = 2
        else:
            if masked == 0:
                ram[ptr & 0xFFFFFFFF] = 0
            ram[0xFFFFD355] = 0
    out = rb(ram, ptr)
    if out == 0:
        ram[0xFFFFD38F] = 1 if (r4 & 0xFF) == 1 else 0
        ret = r4 & 0xFF
    elif out in (5, 7):
        ret = 1 if rb(ram, 0xFFFFD38F) == 1 else 0
    else:
        ret = r4 & 0xFF
    return ret, ram

def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    random.seed(20260731)
    fails = tests = 0
    for _ in range(20000):
        init = {}
        init[0x6025C] = random.choice([0, 1, 0xFF, 0x0F, 0xC0])
        for i, b in enumerate(struct.pack('>I', PTR_CELL)):
            init[0x60260 + i] = b
        init[0xFFFFD355] = random.randrange(0, 256)
        init[0xFFFFD350] = random.randrange(0, 0x10000)
        init[0xFFFFD352] = random.randrange(0, 0x10000)
        init[0xFFFFD354] = random.randrange(0, 256)
        init[0xFFFFD3A8] = random.randrange(0, 256)
        init[0xFFFFD38F] = random.randrange(0, 256)
        init[PTR_CELL] = random.randrange(0, 256)
        r4 = random.choice([0, 1, 2, 3, 5, 7, 0x80, 0xFF])
        tests += 1
        got = cpu.call(ADDR, r4=r4, ram=dict(init))
        ref_ret, ref_ram = ref(init, r4)
        bad = []
        if (got & 0xFF) != ref_ret:
            bad.append('ret emu=%d ref=%d' % (got & 0xFF, ref_ret))
        for cell in (0xFFFFD355, 0xFFFFD38F, PTR_CELL):
            if rb(cpu.ram, cell) != rb(ref_ram, cell):
                bad.append('%s emu=%d ref=%d' % (hex(cell), rb(cpu.ram, cell), rb(ref_ram, cell)))
        if bad:
            fails += 1
            print("  0x5D800 FAIL r4=%d:" % r4, bad[:4])
            if fails >= 5:
                break
    print(f"alternating_sensor_sm_5D800: {tests} tests, {fails} failures")
    print("ALT_SENSOR_SM_5D800:", "PASS" if fails == 0 else "FAIL")
    return 0 if fails == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
