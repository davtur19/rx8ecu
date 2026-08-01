#!/usr/bin/env python3
"""
Verify c/mem_accessors.c against the ACTUAL ROM bytes of the accessor functions,
run in the SH-2E emulator (tools/sh2emu.py). The read/validate functions call getSR/setSR
(interrupt mask) and setMemInsideFUNCto1 / SetMemoryNotValid2 (error flags); those are
stubbed to `rts;nop` here because they don't affect the returned datum — the DATA behavior
(complement/checksum validation + default) is what we check.

Two storage schemes:
  - 8/16-bit cells:  value + bitwise complement (readValue_8bit/16bit, updateMemoryAtAddress_8bit/16bit,
    validateAddressCopy_8bit/16bit).
  - 32-bit/float cells: 8-byte cell = 4-byte value + a 16-bit checksum ~(hi16+lo16) stored
    TWICE (addr+4, addr+6); valid if the checksum matches EITHER copy (readValue_32bit,
    readValue_float, updateMemoryAtAddress_32bit, validateAddressCopy_float). Note
    validateAddressCopy_float has a side effect: on the valid path it rewrites BOTH checksum
    copies with the freshly computed checksum (self-heal of a stale/corrupted copy) — checked
    below via cpu.ram diffing.

Run from repo root:  python3 c/tests/test_mem_accessors.py [N]
"""
import os, sys, random, struct
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, MASK, s8, s16, s32, ts, f2bits


class SH2E(SH2):
    """Self-contained: mov.b/mov.w @(disp,Rm),R0 (correct 0xFF00 mask) + cmp/pz + cmp/pl,
    so the test runs regardless of the base emulator build."""
    def _exec(self, op, pc):
        r = self.r; m = (op >> 4) & 0xF
        if op & 0xFF00 == 0x8000: self.wr(r[m] + (op & 0xF), 1, r[0]); return
        if op & 0xFF00 == 0x8100: self.wr(r[m] + ((op & 0xF) * 2), 2, r[0]); return
        if op & 0xFF00 == 0x8400: r[0] = s8(self.rd(r[m] + (op & 0xF), 1)) & MASK; return
        if op & 0xFF00 == 0x8500: r[0] = s16(self.rd(r[m] + ((op & 0xF) * 2), 2)) & MASK; return
        if op & 0xF0FF == 0x4011: self.T = 1 if s32(r[(op >> 8) & 0xF]) >= 0 else 0; return
        if op & 0xF0FF == 0x4015: self.T = 1 if s32(r[(op >> 8) & 0xF]) > 0 else 0; return
        return super()._exec(op, pc)


ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
cpu = SH2E(open(ROM, 'rb').read())
A = 0xFFFF9000


def stub():
    s = {}
    for a in (0x3920, 0x3934, 0x3E3F0, 0x3E5A8):   # getSR, setSR, setMemInsideFUNCto1, SetMemoryNotValid2
        s[a] = 0x00; s[a + 1] = 0x0B; s[a + 2] = 0x00; s[a + 3] = 0x09   # rts; nop
    return s


def u16(d, a): return (d.get(a, 0) << 8) | d.get(a + 1, 0)
def u32(d, a): return (d.get(a, 0) << 24) | (d.get(a + 1, 0) << 16) | (d.get(a + 2, 0) << 8) | d.get(a + 3, 0)


def checksum32(val):
    hi = (val >> 16) & 0xFFFF
    lo = val & 0xFFFF
    return (~((hi + lo) & 0xFFFF)) & 0xFFFF


def rand_checksum_pair(checksum, mode):
    """mode: 'valid1' (copy1==checksum), 'valid2' (copy2==checksum), 'invalid' (neither)."""
    if mode == 'valid1':
        c1 = checksum; c2 = random.randint(0, 0xFFFF)
    elif mode == 'valid2':
        c1 = random.randint(0, 0xFFFF); c2 = checksum
    else:
        c1 = random.randint(0, 0xFFFF); c2 = random.randint(0, 0xFFFF)
        if c1 == checksum: c1 = (c1 + 1) & 0xFFFF
        if c2 == checksum: c2 = (c2 + 1) & 0xFFFF
    return c1, c2


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    f = {}
    def bad(k): f[k] = f.get(k, 0) + 1

    for _ in range(N):
        # ---- updateMemoryAtAddress_8bit / 16bit (existing) ----
        v = random.randint(0, 255)
        cpu.call(0x3E1F8, r4=A, r5=v, ram=stub())
        if u16(cpu.ram, A) != (((v & 0xFF) << 8) | ((~v) & 0xFF)): bad('updateMemoryAtAddress_8bit')
        v = random.randint(0, 0xFFFF)
        cpu.call(0x3E208, r4=A, r5=v, ram=stub())
        if u32(cpu.ram, A) != (((v & 0xFFFF) << 16) | ((~v) & 0xFFFF)): bad('updateMemoryAtAddress_16bit')

        # ---- readValue_8bit / 16bit (existing) ----
        hi = random.randint(0, 255); lo = random.choice([(~hi) & 0xFF, random.randint(0, 255)]); df = random.randint(0, 255)
        r = cpu.call(0x3E0DC, r4=A, r5=df, ram={**stub(), A: hi, A + 1: lo})
        if (r & 0xFF) != ((hi if hi == ((~lo) & 0xFF) else df) & 0xFF): bad('readValue_8bit')
        val = random.randint(0, 0xFFFF); comp = random.choice([(~val) & 0xFFFF, random.randint(0, 0xFFFF)]); df = random.randint(0, 0xFFFF)
        ram = {**stub(), A: (val >> 8) & 0xFF, A + 1: val & 0xFF, A + 2: (comp >> 8) & 0xFF, A + 3: comp & 0xFF}
        r = cpu.call(0x3E11C, r4=A, r5=df, ram=ram)
        if (r & 0xFFFF) != ((val if val == ((~comp) & 0xFFFF) else df) & 0xFFFF): bad('readValue_16bit')

        # ---- updateMemoryAtAddress_32bit_ADDR_VAL @ 0x3E218 ----
        val = random.randint(0, 0xFFFFFFFF)
        cpu.call(0x3E218, r4=A, r5=val, ram=stub())
        cs = checksum32(val)
        if u32(cpu.ram, A) != val: bad('updateMemoryAtAddress_32bit_value')
        if u16(cpu.ram, A + 4) != cs: bad('updateMemoryAtAddress_32bit_copy1')
        if u16(cpu.ram, A + 6) != cs: bad('updateMemoryAtAddress_32bit_copy2')

        # ---- readValue_32bit_ADDRESS_VAL @ 0x3E15C ----
        val = random.randint(0, 0xFFFFFFFF)
        hi = (val >> 16) & 0xFFFF; lo = val & 0xFFFF
        cs = checksum32(val)
        mode = random.choice(['valid1', 'valid2', 'invalid'])
        c1, c2 = rand_checksum_pair(cs, mode)
        dflt = random.randint(0, 0xFFFFFFFF)
        ram = {**stub(),
               A: (hi >> 8) & 0xFF, A + 1: hi & 0xFF, A + 2: (lo >> 8) & 0xFF, A + 3: lo & 0xFF,
               A + 4: (c1 >> 8) & 0xFF, A + 5: c1 & 0xFF, A + 6: (c2 >> 8) & 0xFF, A + 7: c2 & 0xFF}
        r = cpu.call(0x3E15C, r4=A, r5=dflt, ram=ram)
        expect = val if mode != 'invalid' else dflt
        if (r & 0xFFFFFFFF) != (expect & 0xFFFFFFFF): bad('readValue_32bit_ADDRESS_VAL')

        # ---- readValue_float_DEFAULTVAL_ADDRESS @ 0x3E1AA ----
        fval = ts(random.uniform(-1e6, 1e6))
        bits = struct.unpack('>I', struct.pack('>f', fval))[0]
        hi = (bits >> 16) & 0xFFFF; lo = bits & 0xFFFF
        cs = checksum32(bits)
        mode = random.choice(['valid1', 'valid2', 'invalid'])
        c1, c2 = rand_checksum_pair(cs, mode)
        dfltf = ts(random.uniform(-1e6, 1e6))
        ram = {**stub(),
               A: (hi >> 8) & 0xFF, A + 1: hi & 0xFF, A + 2: (lo >> 8) & 0xFF, A + 3: lo & 0xFF,
               A + 4: (c1 >> 8) & 0xFF, A + 5: c1 & 0xFF, A + 6: (c2 >> 8) & 0xFF, A + 7: c2 & 0xFF}
        cpu.call(0x3E1AA, r4=A, ram=ram, fr={4: dfltf})
        r = cpu.fr[0]
        expect = fval if mode != 'invalid' else dfltf
        if f2bits(r) != f2bits(expect): bad('readValue_float_DEFAULTVAL_ADDRESS')

        # ---- validateAddressCopy_8bit_ADDRESS @ 0x3E29E ----
        v = random.randint(0, 255)
        comp = random.choice([(~v) & 0xFF, random.randint(0, 255)])
        r = cpu.call(0x3E29E, r4=A, ram={**stub(), A: v, A + 1: comp})
        expect = 0 if v == ((~comp) & 0xFF) else 1
        if (r & 0xFF) != expect: bad('validateAddressCopy_8bit_ADDRESS')

        # ---- validateAddressCopy_16bit_ADDRESS @ 0x3E2DA ----
        v = random.randint(0, 0xFFFF)
        comp = random.choice([(~v) & 0xFFFF, random.randint(0, 0xFFFF)])
        ram = {**stub(), A: (v >> 8) & 0xFF, A + 1: v & 0xFF, A + 2: (comp >> 8) & 0xFF, A + 3: comp & 0xFF}
        r = cpu.call(0x3E2DA, r4=A, ram=ram)
        expect = 0 if v == ((~comp) & 0xFFFF) else 1
        if (r & 0xFF) != expect: bad('validateAddressCopy_16bit_ADDRESS')

        # ---- validateAddressCopy_float_ADDRESS @ 0x3E38A (+ checksum self-heal side effect) ----
        fval = ts(random.uniform(-1e6, 1e6))
        bits = struct.unpack('>I', struct.pack('>f', fval))[0]
        hi = (bits >> 16) & 0xFFFF; lo = bits & 0xFFFF
        cs = checksum32(bits)
        mode = random.choice(['valid1', 'valid2', 'invalid'])
        c1, c2 = rand_checksum_pair(cs, mode)
        ram = {**stub(),
               A: (hi >> 8) & 0xFF, A + 1: hi & 0xFF, A + 2: (lo >> 8) & 0xFF, A + 3: lo & 0xFF,
               A + 4: (c1 >> 8) & 0xFF, A + 5: c1 & 0xFF, A + 6: (c2 >> 8) & 0xFF, A + 7: c2 & 0xFF}
        r = cpu.call(0x3E38A, r4=A, ram=ram)
        expect = 0 if mode != 'invalid' else 1
        if (r & 0xFF) != expect: bad('validateAddressCopy_float_ADDRESS')
        if mode != 'invalid':
            if u16(cpu.ram, A + 4) != cs: bad('validateAddressCopy_float_ADDRESS_scrub_copy1')
            if u16(cpu.ram, A + 6) != cs: bad('validateAddressCopy_float_ADDRESS_scrub_copy2')
        else:
            if u16(cpu.ram, A + 4) != c1: bad('validateAddressCopy_float_ADDRESS_untouched_copy1')
            if u16(cpu.ram, A + 6) != c2: bad('validateAddressCopy_float_ADDRESS_untouched_copy2')

        # ---- validateAddressCopy_32bit_ADDRESS @ 0x3E330 (raw u32 value + checksum self-heal) ----
        val = random.randint(0, 0xFFFFFFFF)
        hi = (val >> 16) & 0xFFFF; lo = val & 0xFFFF
        cs = checksum32(val)
        mode = random.choice(['valid1', 'valid2', 'invalid'])
        c1, c2 = rand_checksum_pair(cs, mode)
        ram = {**stub(),
               A: (hi >> 8) & 0xFF, A + 1: hi & 0xFF, A + 2: (lo >> 8) & 0xFF, A + 3: lo & 0xFF,
               A + 4: (c1 >> 8) & 0xFF, A + 5: c1 & 0xFF, A + 6: (c2 >> 8) & 0xFF, A + 7: c2 & 0xFF}
        r = cpu.call(0x3E330, r4=A, ram=ram)
        expect = 0 if mode != 'invalid' else 1
        if (r & 0xFF) != expect: bad('validateAddressCopy_32bit_ADDRESS')
        if mode != 'invalid':
            if u16(cpu.ram, A + 4) != cs: bad('validateAddressCopy_32bit_ADDRESS_scrub_copy1')
            if u16(cpu.ram, A + 6) != cs: bad('validateAddressCopy_32bit_ADDRESS_scrub_copy2')
        else:
            if u16(cpu.ram, A + 4) != c1: bad('validateAddressCopy_32bit_ADDRESS_untouched_copy1')
            if u16(cpu.ram, A + 6) != c2: bad('validateAddressCopy_32bit_ADDRESS_untouched_copy2')

    names = ['updateMemoryAtAddress_8bit', 'updateMemoryAtAddress_16bit', 'readValue_8bit', 'readValue_16bit',
             'updateMemoryAtAddress_32bit_value', 'updateMemoryAtAddress_32bit_copy1', 'updateMemoryAtAddress_32bit_copy2',
             'readValue_32bit_ADDRESS_VAL', 'readValue_float_DEFAULTVAL_ADDRESS',
             'validateAddressCopy_8bit_ADDRESS', 'validateAddressCopy_16bit_ADDRESS',
             'validateAddressCopy_float_ADDRESS',
             'validateAddressCopy_float_ADDRESS_scrub_copy1', 'validateAddressCopy_float_ADDRESS_scrub_copy2',
             'validateAddressCopy_float_ADDRESS_untouched_copy1', 'validateAddressCopy_float_ADDRESS_untouched_copy2',
             'validateAddressCopy_32bit_ADDRESS',
             'validateAddressCopy_32bit_ADDRESS_scrub_copy1', 'validateAddressCopy_32bit_ADDRESS_scrub_copy2',
             'validateAddressCopy_32bit_ADDRESS_untouched_copy1', 'validateAddressCopy_32bit_ADDRESS_untouched_copy2']
    print("inputs/function: %d" % N)
    for n in names:
        print("  %-42s %s (%d)" % (n, "OK" if not f.get(n) else "FAIL", f.get(n, 0)))
    sys.exit(1 if any(f.get(n) for n in names) else 0)


if __name__ == '__main__':
    main()
