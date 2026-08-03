#!/usr/bin/env python3
"""
Verify reset_handler @0x4E0 against the ACTUAL ROM bytes, run in the SH-2E
emulator.  The real resetWatchdog @0x572 body runs (writes 0xEC10/0xEC12);
the hw-init leaves 0x170/0x41C/0x3D4, the 0x08F6 leaf, and checkWatchdog
@0x5B0 are replaced with trace stubs; the boot stub @0x40 captures r4 (rv).

Flow (from ROM disasm, ground truth):

  0x4E0 add #-8,r15 ; [SP+4]=cold_start(r4); [SP]=reason(r5)
  0x4E6 bsr 0x572   real resetWatchdog: [0xEC12]=0x5A1F, [0xEC10]=0xA53C
  0x4E8 mov #1,r14  (recovered flag, default 1)
  0x4EA/0x4F0/0x4F6 jsr 0x170, 0x41C, 0x3D4  (trace 0,1,2)
  0x4FC-0x500  cold_start != 0 -> warm path (0x556)
  cold path:
    0x502-0x50A  [0xFFFFDFFC] == 0x5AA5A55A -> recovered
    0x50C        bsr 0x5B0 (trace 4); if wdt != 0 -> recovered else clean (rv=0x06C8)
  recovery (recovered):
    0x520-0x530  v7ffc=[0x7FFFC], deref=[[0x7FFFC]]
                 if v7ffc==0xFFFFFFFF or deref==0xFFFFFFFF -> retry (0x532)
                 else 0x546: rv = [0x1000] unless ==0xFFFFFFFF then [0x7FFF8]
    0x532        retry: bsr 0x5B0 (trace 4); wdt==0 -> rv=0x06C8
                 else [0x1000]==0xFFFFFFFF -> loop (avoid in tests); else rv=[0x1000]
  warm path 0x556: [0xFFFFDFA8]=reason ; jsr 0x08F6 (trace 3) ; rv=0x06C8
  finish 0x562: [0xFFFFDFFC]=0x5AA5A55A ; jsr @0x40 (boot stub:
                 [BOOT_CELL]=r4=rv, r0=rv, jmp SENT)

Model inputs: cold_start, reason, magic([0xFFFFDFFC]), wdt(WDT_CELL),
v7ffc=[0x7FFFC], v7fff8=[0x7FFF8], v1000=[0x1000], dv=[DV_ADDR].
deref = 32-bit value at address v7ffc (emulator ram-first, then ROM).

Run from repo root:  python3 c/tests/test_reset_handler_4E0.py [N]
"""
import os, sys, random, struct

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x000004E0

MAGIC = 0x5AA5A55A
MAGIC_LOC = 0xFFFFDFFC      # magic store cell (written on every finish)
REASON_STORE = 0xFFFFDFA8   # warm path: reason byte written here
LEN_ADDR = 0xFFFFD130       # trace length (byte)
TRACE_ADDR = 0xFFFFD140     # trace bytes
WDT_CELL = 0xFFFFD120       # checkWatchdog stub return (0 -> wdt==0)
BOOT_CELL = 0xFFFFD150      # boot stub captures r4 (rv) here
DV_ADDR = 0xFFFFD0F0        # [[0x7FFFC]] when v7ffc == DV_ADDR
SENT = 0xEEEE0000
DEFAULT_RV = 0x06C8
WDT0 = 0xFFFFEC10         # real resetWatchdog writes (word)
WDT1 = 0xFFFFEC12         # real resetWatchdog writes (word)


def make_slot(k, addr):
    """34-byte trace-append stub: [LEN]=k at TRACE_ADDR+len, RTS."""
    b = bytearray(34)
    b[0] = 0xE4; b[1] = k & 0xFF
    pool = (addr + 22 + 3) & ~3
    b2 = (addr + 6) & ~3
    b4 = (addr + 8) & ~3
    b[2] = 0xD0; b[3] = (pool - b2) // 4
    b[4] = 0xD3; b[5] = (pool + 4 - b4) // 4
    b[6] = 0x62; b[7] = 0x00
    b[8] = 0x32; b[9] = 0x3C
    b[10] = 0x22; b[11] = 0x40
    b[12] = 0x62; b[13] = 0x00
    b[14] = 0x72; b[15] = 0x01
    b[16] = 0x20; b[17] = 0x20
    b[18] = 0x00; b[19] = 0x0B
    b[20] = 0x00; b[21] = 0x09
    lo = pool - addr
    b[lo:lo + 4] = struct.pack('>I', LEN_ADDR)
    b[lo + 4:lo + 8] = struct.pack('>I', TRACE_ADDR)
    return bytes(b)


def make_wdt(addr):
    """46-byte stub for checkWatchdog @0x5B0: trace slot 4, r0=WDT_CELL, RTS."""
    b = bytearray(46)
    b[0] = 0xE4; b[1] = 4
    pool = (addr + 26 + 3) & ~3
    b2 = (addr + 2 + 4) & ~3
    b4 = (addr + 4 + 4) & ~3
    b18 = (addr + 18 + 4) & ~3
    b[2] = 0xD0; b[3] = (pool - b2) // 4
    b[4] = 0xD3; b[5] = (pool + 4 - b4) // 4
    b[6] = 0x62; b[7] = 0x00
    b[8] = 0x32; b[9] = 0x3C
    b[10] = 0x22; b[11] = 0x40
    b[12] = 0x62; b[13] = 0x00
    b[14] = 0x72; b[15] = 0x01
    b[16] = 0x20; b[17] = 0x20
    b[18] = 0xD1; b[19] = (pool + 8 - b18) // 4
    b[20] = 0x60; b[21] = 0x10
    b[22] = 0x00; b[23] = 0x0B
    b[24] = 0x00; b[25] = 0x09
    lo = pool - addr
    b[lo:lo + 4] = struct.pack('>I', LEN_ADDR)
    b[lo + 4:lo + 8] = struct.pack('>I', TRACE_ADDR)
    b[lo + 8:lo + 12] = struct.pack('>I', WDT_CELL)
    return bytes(b)


def make_boot(addr):
    """30-byte boot stub @0x40: [BOOT_CELL]=r4; r0=r4; jmp SENT."""
    b = bytearray(30)
    pool = (addr + 20 + 3) & ~3
    base1 = (addr + 2 + 2) & ~3
    b[0] = 0xD3; b[1] = (pool - base1) // 4
    b[2] = 0x23; b[3] = 0x42
    b[4] = 0x60; b[5] = 0x43
    base2 = (addr + 6 + 2) & ~3
    b[6] = 0xD1; b[7] = (pool + 4 - base2) // 4
    b[8] = 0x41; b[9] = 0x2B
    b[10] = 0x00; b[11] = 0x09
    lo = pool - addr
    b[lo:lo + 4] = struct.pack('>I', BOOT_CELL)
    b[lo + 4:lo + 8] = struct.pack('>I', SENT)
    return bytes(b)


def build_stubs():
    ram = {}
    # 0x572 (resetWatchdog) is deliberately NOT stubbed: its real body
    # (0x572..0x585) ends before the handler pool at 0x586.  A stub there
    # would clobber the pool words the handler loads (0x170, 0x41C, ...).
    for k, a in enumerate((0x170, 0x41C, 0x3D4, 0x08F6)):
        st = make_slot(k, a)
        for i, byte in enumerate(st):
            ram[a + i] = byte
    st = make_wdt(0x5B0)
    for i, byte in enumerate(st):
        ram[0x5B0 + i] = byte
    st = make_boot(0x40)
    for i, byte in enumerate(st):
        ram[0x40 + i] = byte
    return ram


STUBS = build_stubs()


def seed32(ram, addr, v):
    v &= 0xFFFFFFFF
    for i in range(4):
        ram[addr + i] = (v >> (8 * (3 - i))) & 0xFF


def rd32(ram, addr):
    return ((ram.get(addr, 0) << 24) | (ram.get(addr + 1, 0) << 16)
            | (ram.get(addr + 2, 0) << 8) | ram.get(addr + 3, 0))


def emu_rd32(rom, ram, addr):
    """32-bit read matching the emulator's ram-first, then ROM, else 0."""
    v = 0
    for i in range(4):
        a = (addr + i) & 0xFFFFFFFF
        b = ram.get(a)
        if b is None:
            b = rom[a] if a < len(rom) else 0
        v = (v << 8) | (b & 0xFF)
    return v


def model(cold, reason, magic, wdt, v7ffc, v7fff8, v1000, deref):
    """Return (trace, rv, reason_stored, magic_after).  deref = [[0x7FFFC]]."""
    trace = [0, 1, 2]                    # hw1, hw2, hw3
    if cold != 0:
        # warm: [0xFFFFDFA8]=reason, jsr 0x08F6, rv = default
        trace.append(3)
        return trace, DEFAULT_RV, reason & 0xFF, MAGIC
    recovered = (magic == MAGIC)
    if magic != MAGIC:
        trace.append(4)                  # checkWatchdog at 0x50C
        if wdt != 0:
            recovered = True
    if not recovered:
        return trace, DEFAULT_RV, None, MAGIC
    # recovery
    if v7ffc == 0xFFFFFFFF or deref == 0xFFFFFFFF:
        trace.append(4)                  # checkWatchdog retry at 0x532
        if wdt == 0:
            rv = DEFAULT_RV              # bt 0x560
        else:
            if v1000 == 0xFFFFFFFF:
                rv = 'LOOP'              # infinite retry - callers must skip
            else:
                rv = v1000
    else:
        if v1000 == 0xFFFFFFFF:
            rv = v7fff8
        else:
            rv = v1000
    return trace, rv, None, MAGIC


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    def run_one(cold, reason, magic, wdt, v7ffc, v7fff8, v1000, dv):
        ram = dict(STUBS)
        ram[WDT_CELL] = wdt & 0xFF
        seed32(ram, MAGIC_LOC, magic)
        seed32(ram, 0x7FFFC, v7ffc)
        seed32(ram, 0x7FFF8, v7fff8)
        seed32(ram, 0x1000, v1000)
        if dv is not None:
            seed32(ram, DV_ADDR, dv)
        deref = emu_rd32(rom, ram, v7ffc)
        ram[REASON_STORE] = 0xAA
        ret = cpu.call(ENTRY, r4=cold, r5=reason, ram=ram)
        r = cpu.ram
        trace = []
        for i in range(r.get(LEN_ADDR, 0) & 0xFF):
            trace.append(r.get(TRACE_ADDR + i, 0))
        rv = rd32(r, BOOT_CELL)
        reason_stored = r.get(REASON_STORE, 0)
        magic_after = rd32(r, MAGIC_LOC)
        wdt0 = (r.get(WDT0, 0) << 8) | r.get(WDT0 + 1, 0)   # word @0xEC10
        wdt1 = (r.get(WDT1, 0) << 8) | r.get(WDT1 + 1, 0)   # word @0xEC12
        return (trace, rv, reason_stored, magic_after, ret, wdt0, wdt1, deref)

    def check(cold, reason, magic, wdt, v7ffc, v7fff8, v1000, dv):
        # deref for the LOOP decision must be computed identically to run_one.
        pr = dict(STUBS)
        pr[WDT_CELL] = wdt & 0xFF
        seed32(pr, MAGIC_LOC, magic)
        seed32(pr, 0x7FFFC, v7ffc)
        seed32(pr, 0x7FFF8, v7fff8)
        seed32(pr, 0x1000, v1000)
        if dv is not None:
            seed32(pr, DV_ADDR, dv)
        deref = emu_rd32(rom, pr, v7ffc)
        m = model(cold, reason, magic, wdt, v7ffc, v7fff8, v1000, deref)
        if m[1] == 'LOOP':
            return True
        g = run_one(cold, reason, magic, wdt, v7ffc, v7fff8, v1000, dv)
        gtrace, grv, greason, gmagic, _ret, gw0, gw1, gderef = g
        mtrace, mrv, mreason, mmagic = m
        if (gtrace != mtrace or grv != mrv or gmagic != mmagic
                or gderef != deref
                or ((mreason is None) != (cold == 0))
                or (mreason is not None and mreason != greason)
                or gw0 != 0xA53C or gw1 != 0x5A1F):
            print("FAIL: cold=%d reason=%02X magic=%08X wdt=%d "
                  "v7ffc=%08X v7fff8=%08X v1000=%08X dv=%08X"
                  % (cold, reason, magic, wdt, v7ffc, v7fff8, v1000, dv))
            print("  emu trace=%s rv=%06X reason=%02X magic=%08X "
                  "ret=%08X wdt=%08X/%08X deref=%08X"
                  % (gtrace, grv, greason, gmagic, _ret, gw0, gw1, gderef))
            print("  mod trace=%s rv=%s reason=%s magic=%08X"
                  % (mtrace, '--' if mrv == 'LOOP' else '%06X' % mrv,
                     '--' if mreason is None else '%02X' % mreason, mmagic))
            return False
        return True

    # Targeted: branch matrix.
    cases = []
    for cold in (0, 1):
        for reason in (0x00, 0x01, 0x55, 0xAA, 0xFF):
            for magic in (MAGIC, 0, 0x12345678):
                for wdt in (0, 1):
                    for v7ffc in (0xFFFFFFFF, DV_ADDR):
                        for dv in (0xFFFFFFFF, 0x12B4):
                            for v1000 in (0xFFFFFFFF, 0x12B4):
                                for v7fff8 in (0xD49C, 0xFFFFFFFF):
                                    cases.append((cold, reason, magic, wdt,
                                                  v7ffc, v7fff8, v1000, dv))
    for c in cases:
        if not check(*c):
            sys.exit(1)

    # Random.
    rng = random.Random(0x4E0)
    vals = [0xFFFFFFFF, 0x00000000, 0x000000FF, 0x00000100, 0x06C8, 0x12B4,
            DV_ADDR, 0x7FFFC, 0x1000, 0x7FFF8, 0x0000A53C, 0x5A1F, 0x00000040,
            0x31415FFF, 0x000004E0, 0x55555555]
    for _ in range(N):
        cold = rng.choice([0, 0, 0, 1])
        reason = rng.randint(0, 255)
        magic = rng.choice([MAGIC, 0, 0x12345678, rng.randint(0, 0xFFFFFFFF)])
        wdt = rng.randint(0, 1)
        v7ffc = rng.choice(vals)
        v7fff8 = rng.choice(vals)
        v1000 = rng.choice(vals)
        dv = rng.choice(vals)
        if not check(cold, reason, magic, wdt, v7ffc, v7fff8, v1000, dv):
            sys.exit(1)

    print("OK  reset_handler @0x%04X  (targeted %d + %d random)"
          % (ENTRY, len(cases), N))
    sys.exit(0)


if __name__ == '__main__':
    main()
