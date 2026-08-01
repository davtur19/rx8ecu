#!/usr/bin/env python3
"""
Test store_knock_learn_buffer via SH-2E emulator.

The lift (c/store_knock_learn_buffer.c) covers two identical function bodies:
  0xC0F0  in roms/stock/60E0FC00.bin
  0xC2C0  in roms/stock/60E1D400.bin
Both read the SH-2 status register, store two u16 parameters to the knock
buffer, and tail-call setSR to restore the SR.  (0xC0F0 in 60E1D400.bin is a
DIFFERENT function — the lift's two addresses live in two different ROMs.)

Verified behavior (from the actual ROM bytes):

  store_knock_learn_buffer(r4, r5):
      getSR(0x10)                      ; @0x3920, returns SR & 0xF0 in r0
      KNOCK_COPY1 (0xFFFFA37E) = r4    ; u16
      KNOCK_COPY2 (0xFFFFA37C) = r5    ; u16
      tail call setSR(r0)              ; @0x3934  (jmp, pr popped in delay slot)

  getSR @0x3920: r0 = SR & 0xF0; if 0x10 > (SR & 0xF0): SR = 0x10.
  setSR @0x3934: SR = r4, except r4 == 0 -> pointer-chain flag check:
      flag = *(*(ANCHOR + 0x18) + 1) where ANCHOR is 0xFFFF7638 (60E0FC00)
      or 0xFFFF72B0 (60E1D400).  flag == 1 -> fast path (SR = 0).
      flag != 1   -> tail-call OS handler 0x3DB0 (with delay ldc r4,SR so
                     SR = 0 on entry); early-exit path taken when
                     word@(ANCHOR+4) == word@(ANCHOR+6): SR = 0, r0 = 0.

  Net effect (this test's reference model):
      c1 = r4 & 0xFFFF, c2 = r5 & 0xFFFF
      old_ipl = SR & 0xF0
      final SR = old_ipl            (all paths; the temporary SR=0x10 from
                                      getSR is always undone by setSR)
      r0 = s16(c1)                  (old_ipl != 0)  -- mov.w sign-extends
         = 1                        (old_ipl == 0, setSR fast path, flag==1)
         = 0                        (old_ipl == 0, OS early-exit, flag!=1)

Scope / SR handling:
  - The base sh2emu implements stc/ldc SR, so SR state is traced for real.
  - The setSR(0) OS-handler tail call is bounded ONLY via the early-exit path
    (word@ANCHOR+4 == word@ANCHOR+6).  The full scheduler path of 0x3DB0 is
    out of scope; the fast path (flag==1) is the overwhelmingly common case
    (setSR is called with r4==0 only when the current IPL is 0).
  - We compare: both u16 knock copies, the final SR, and the r0 return value,
    plus assert no RAM writes outside the knock copies + stack scratch.

Run from repo root:  python3 c/tests/test_store_knock_learn_buffer.py
"""
import os, sys, struct, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2, ts

ROM0 = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E0FC00.bin')
ROM1 = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')

# (rom_path, entry, setSR pointer-chain anchor)
TARGETS = [
    ('60E0FC00.bin', 0xC0F0, 0xFFFF7638),
    ('60E1D400.bin', 0xC2C0, 0xFFFF72B0),
]

A37E = 0xFFFFA37E      # u16 first knock copy (output)
A37C = 0xFFFFA37C      # u16 second knock copy (output)


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def ref(r4, r5, init_sr, flag):
    """Reference model: returns (c1, c2, final_sr, r0)."""
    c1 = r4 & 0xFFFF
    c2 = r5 & 0xFFFF
    old_ipl = init_sr & 0xF0
    if old_ipl == 0:
        if flag == 1:            # setSR fast path
            final_sr, ret = 0, 1
        else:                    # OS early-exit path via 0x3DB0
            final_sr, ret = 0, 0
    else:
        final_sr = old_ipl
        ret = s16(c1)            # r0 sign-extended by mov.w @(4,r15),r0
    return c1, c2, final_sr, ret


def build_ram(anchor, flag, os_early):
    PTR1 = 0xFFFFA000
    PTR2 = 0xFFFFA100
    ram = {}
    # setSR(0) pointer chain: r5 = ANCHOR, r6 = *(ANCHOR+0x18), flag = *(r6+1)
    for i in range(4):
        ram[anchor + 0x18 + i] = (PTR2 >> (24 - 8 * i)) & 0xFF
    ram[PTR2 + 1] = flag
    # poison the knock copies so an overwrite is verified
    ram[A37E] = 0xAA; ram[A37E + 1] = 0xBB
    ram[A37C] = 0xCC; ram[A37C + 1] = 0xDD
    if os_early:
        # 0x3DB0 early exit: word@(ANCHOR+4) == word@(ANCHOR+6), SR preload 0
        ram[anchor + 4] = 0; ram[anchor + 5] = 0
        ram[anchor + 6] = 0; ram[anchor + 7] = 0
        for i in range(4):
            ram[anchor + 0x10 + i] = 0
    return ram


def run(cpu, rom, entry, anchor, r4, r5, init_sr, flag, os_early):
    ram = build_ram(anchor, flag, os_early)
    ret = cpu.call(entry, r4=r4, r5=r5, sr=init_sr, ram=ram)
    c1 = (cpu.ram.get(A37E, 0) << 8) | cpu.ram.get(A37E + 1, 0)
    c2 = (cpu.ram.get(A37C, 0) << 8) | cpu.ram.get(A37C + 1, 0)
    # unexpected writes: knock copies + stack scratch (0xFFFFDEF4..0xFFFFDF00;
    # the function parks r4/r5 params and pr on the stack at 0xFFFFDEF4-DF)
    allowed = {A37E, A37E + 1, A37C, A37C + 1}
    extra = [a for a in cpu.ram
             if a not in allowed and a not in ram
             and not (0xFFFFDEF4 <= a < 0xFFFFDF00)]
    return c1, c2, cpu.sr, ret, extra


def main():
    random.seed(20260801)
    ipls = [0x00, 0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70,
            0x80, 0x90, 0xA0, 0xB0, 0xC0, 0xD0, 0xE0, 0xF0]
    tests = fails = 0
    for name, entry, anchor in TARGETS:
        rom = open(ROM0 if name.startswith('60E0FC00') else ROM1, 'rb').read()
        cpu = SH2(rom)
        n = 10000
        for _ in range(n):
            r4 = random.randint(0, 0xFFFF)
            r5 = random.randint(0, 0xFFFF)
            if random.random() < 0.5:
                init_sr = random.choice(ipls) | random.choice([0, 1, 2, 3])
            else:
                init_sr = random.randint(0, 0xFFFFFFFF)
            exp = ref(r4, r5, init_sr, 1)
            got = run(cpu, rom, entry, anchor, r4, r5, init_sr, 1, False)
            tests += 1
            if (got[0], got[1], got[2] & 0xFFFFFFFF, got[3] & 0xFFFFFFFF, got[4]) \
                    != (exp[0], exp[1], exp[2], exp[3] & 0xFFFFFFFF, []):
                fails += 1
                if fails <= 8:
                    print("FAIL(%s@0x%X) r4=%04X r5=%04X sr=%08X got=%s exp=%s"
                          % (name, entry, r4, r5, init_sr, got, exp))
            if fails >= 8:
                break

        # explicit OS early-exit cases: old_ipl == 0, setSR flag != 1
        for r4, r5, init_sr in [(0x1234, 0x5678, 0x00000000),
                                (0x0000, 0x0000, 0x00000003),
                                (0xFFFF, 0x0001, 0x00000000)]:
            exp = ref(r4, r5, init_sr, 2)
            got = run(cpu, rom, entry, anchor, r4, r5, init_sr, 2, True)
            tests += 1
            if (got[0], got[1], got[2] & 0xFFFFFFFF, got[3] & 0xFFFFFFFF, got[4]) \
                    != (exp[0], exp[1], exp[2], exp[3] & 0xFFFFFFFF, []):
                fails += 1
                if fails <= 8:
                    print("FAIL(%s@0x%X OS) r4=%04X r5=%04X sr=%08X got=%s exp=%s"
                          % (name, entry, r4, r5, init_sr, got, exp))

    print(f"store_knock_learn_buffer @0xC0F0/0xC2C0: {tests} tests, {fails} failures")
    print(f"OK  store_knock_learn_buffer @0xC0F0 (60E0FC00) + 0xC2C0 (60E1D400)  "
          f"({tests} inputs, 0 mismatches)" if fails == 0 else
          f"FAIL store_knock_learn_buffer  ({fails} mismatches)")
    return 0 if fails == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
