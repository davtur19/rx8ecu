#!/usr/bin/env python3
"""
Verify the OMP-chain memory accessors against the ACTUAL ROM bytes, run in the
SH-2E emulator (tools/sh2emu.py).

Functions:
  0x3F050  — fault-flag leaf: RAM8[0xFFFFC6AC] = 1, r0 untouched (returns 0 from
             the emulator's r0 init).  Called by the ADDRESS_VAL accessors when a
             redundant-memory complement check fails.
  0x3ED7C  — readValue_16bit_ADDRESS_VAL(addr, default):
               old = getSR(0x10);                 # r0 = SR & 0xF0, SR unchanged
               if RAM16[addr] == ~RAM16[addr+2]:  # 16-bit complement check
                   ret = s16(RAM16[addr])
               else:
                   0x3F050();                     # set fault flag C6AC
                   ret = s16(default)
               setSR(old);  return ret
  0x3ED3C  — readValue_8bit_ADDRESS_VAL(addr, default): same with bytes
             (RAM8[addr] == ~RAM8[addr+1])  [regression cross-check]

All values sign-extend (mov.w/mov.b reads), so the accessor returns a 32-bit
sign-extended word.  SR is preserved across the call (getSR/setSR pair).

Run: python3 c/tests/test_omp_accessors.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, s16, s8

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
FAULT = 0xFFFFC6AC


def s16b(x):  # sign-extend a 16-bit value to 32 bits (negative stays negative)
    return s16(x & 0xFFFF)


def model_16(ram, addr, default):
    a = addr & 0xFFFFFFFE  # 16-bit reads
    w0 = (ram.get(a, 0) << 8) | ram.get(a + 1, 0)
    w1 = (ram.get(a + 2, 0) << 8) | ram.get(a + 3, 0)
    if w0 == ((~w1) & 0xFFFF):
        return s16b(w0), ram.get(FAULT, 0), True
    return s16b(default), 1, False   # mismatch -> fault flag set


def model_8(ram, addr, default):
    b0 = ram.get(addr, 0)
    b1 = ram.get(addr + 1, 0)
    if b0 == ((~b1) & 0xFF):
        return s8(b0), ram.get(FAULT, 0), True
    return s8(default), 1, False


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    fails = 0

    # ---- 0x3F050 fault-flag leaf ----
    for _ in range(1000):
        ram = {FAULT: random.randint(0, 1)}
        r0 = cpu.call(0x3F050, ram=ram)
        if cpu.ram.get(FAULT) != 1 or r0 != 0:
            print("MISMATCH 0x3F050: fault=%d r0=0x%X" % (cpu.ram.get(FAULT), r0))
            fails += 1
            break
    else:
        print("OK  0x3F050 fault-flag leaf  RAM8[C6AC]=1 r0=0  (1000 tests)")

    # ---- 0x3ED7C 16-bit ADDRESS_VAL ----
    for _ in range(N):
        addr = random.randrange(0xFFFF8000, 0xFFFFD000, 2)  # below the emulator stack
        default = random.randint(0, 0xFFFF)
        val = random.randint(0, 0xFFFF)
        if random.random() < 0.5:
            ram = {addr: (val >> 8) & 0xFF, addr + 1: val & 0xFF,
                   addr + 2: ((~val) >> 8) & 0xFF, addr + 3: (~val) & 0xFF,
                   FAULT: 0}
            valid = True
        else:
            ram = {addr: (val >> 8) & 0xFF, addr + 1: val & 0xFF,
                   addr + 2: 0x12, addr + 3: 0x34,
                   FAULT: 0}
            valid = False
        r0 = cpu.call(0x3ED7C, r4=addr, r5=default, ram=ram)
        want, want_fault, _ = model_16(ram, addr, default)
        if r0 != (want & 0xFFFFFFFF) or cpu.ram.get(FAULT, 0) != want_fault:
            print("MISMATCH 0x3ED7C addr=0x%X def=0x%X valid=%s r0=0x%X want=0x%X fault=%d" %
                  (addr, default, valid, r0, want & 0xFFFFFFFF, cpu.ram.get(FAULT, 0)))
            fails += 1
            break
    else:
        print("OK  0x3ED7C readValue_16bit_ADDRESS_VAL  (%d random inputs)" % N)

    # ---- 0x3ED3C 8-bit ADDRESS_VAL (regression) ----
    for _ in range(N):
        addr = random.randrange(0xFFFF8000, 0xFFFFD000)  # below the emulator stack
        default = random.randint(0, 0xFF)
        val = random.randint(0, 0xFF)
        if random.random() < 0.5:
            ram = {addr: val, addr + 1: (~val) & 0xFF, FAULT: 0}
            valid = True
        else:
            ram = {addr: val, addr + 1: 0x5A, FAULT: 0}
            valid = False
        r0 = cpu.call(0x3ED3C, r4=addr, r5=default, ram=ram)
        want, want_fault, _ = model_8(ram, addr, default)
        if r0 != (want & 0xFFFFFFFF) or cpu.ram.get(FAULT, 0) != want_fault:
            print("MISMATCH 0x3ED3C addr=0x%X def=0x%X valid=%s r0=0x%X want=0x%X fault=%d" %
                  (addr, default, valid, r0, want & 0xFFFFFFFF, cpu.ram.get(FAULT, 0)))
            fails += 1
            break
    else:
        print("OK  0x3ED3C readValue_8bit_ADDRESS_VAL   (%d random inputs, regression)" % N)

    # ---- SR preservation through the accessors ----
    for entry in (0x3ED3C, 0x3ED7C):
        for sr in (0xF0, 0x80, 0x30, 0x00):
            r0 = cpu.call(entry, r4=0xFFFFA000, r5=0, sr=sr,
                          ram={0xFFFFA000: 0xAA, 0xFFFFA001: 0x55, FAULT: 0})
            if cpu.sr != sr:
                print("MISMATCH SR preservation 0x%X sr-in=0x%X sr-out=0x%X" % (entry, sr, cpu.sr))
                fails += 1
    print("OK  SR preserved through accessors (getSR/setSR pair)")

    if fails:
        print("\n%d FAILURE(S)" % fails)
        sys.exit(1)
    print("\nAll OMP accessor tests passed.")
    sys.exit(0)


if __name__ == '__main__':
    main()
