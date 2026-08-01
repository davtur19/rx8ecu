#!/usr/bin/env python3
"""
Verify setSR (0x3934), getSR (0x3920), setSR_PARAM (0x2054) against the ACTUAL ROM
bytes, run in the SH-2E emulator (tools/sh2emu.py).  These three functions are SH-2 status
register (SR) accessors — they use `stc sr,Rn` and `ldc Rn,SR` which the base emulator
does not implement.  A subclass below adds a plain `self.sr` register (no interrupt
modelling, just read/write state).

Why this matters: setSR is called from 166 sites, getSR from 165, setSR_PARAM from 68 —
together they form the interrupt-masking critical-section layer that protects every
redundant-memory access in the ECU.  Verifying their lift pins down the SR read/write
behaviour so the calling code can be trusted.

Limitations:
  - Real SH-2 hardware prevents lowering the IPL (interrupt priority level, bits 7–4 of
    SR) via `ldc Rn,SR` when running in user mode — this emulation does not enforce that
    constraint because the firmware runs privileged.  The extra software guard in
    setSR_PARAM is tested explicitly.
  - setSR (0x3934) has a special case when r4 == 0: it reads a flag byte through a
    pointer chain anchored at 0xFFFF72B0 (a kernel structure).  If the flag != 1, it
    calls an OS task-switch at 0x3DB0 before the `ldc`.  Our test sets the flag to 1
    so the fast path is taken — the OS callback is orthogonal to the SR-setting
    behaviour.
  - No interrupt model: SR is a plain uint32.  The `stc`/`ldc` opcodes simply
    read/write `self.sr`.

Run from repo root:  python3 c/tests/test_setSR_getSR.py [N]
"""
import os, sys, random, struct

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, MASK

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')


class SRCPU(SH2):
    """SH-2E + stc sr,Rn / ldc Rn,SR + cmp/pz/cmp/pl (needed by setSR's extra path)
    + a plain self.sr register."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        # Power-on reset default for SH-2: IPL = 15 (0xF0), MD=1, BL=1, RB=1
        self.sr = 0x000000F0

    def _exec(self, op, pc):
        r = self.r
        # ---- stc SR,Rn  (opcode 0x0n02 — mask 0xF0FF == 0x0002) ----
        if op & 0xF0FF == 0x0002:
            r[(op >> 8) & 0xF] = self.sr & MASK
            return

        # ---- ldc Rn,SR  (opcode 0x4n0E — mask 0xF0FF == 0x400E) ----
        if op & 0xF0FF == 0x400E:
            self.sr = r[(op >> 8) & 0xF] & MASK
            return

        # ---- and #imm,R0  (0xC9ii) — used by setSR_PARAM @0x2056 ----
        if op & 0xFF00 == 0xC900:
            r[0] = r[0] & (op & 0xFF)
            return

        # ---- or #imm,R0   (0xCBii) ----
        if op & 0xFF00 == 0xCB00:
            r[0] = r[0] | (op & 0xFF)
            return

        # ---- xor #imm,R0  (0xCAii) ----
        if op & 0xFF00 == 0xCA00:
            r[0] = r[0] ^ (op & 0xFF)
            return

        # ---- tst #imm,R0  (0xC8ii) ----
        if op & 0xFF00 == 0xC800:
            self.T = 1 if (r[0] & (op & 0xFF)) == 0 else 0
            return

        # ---- cmp/pz (needed by setSR's OS-handler code at 0x3DB0 if we trace into it) ----
        if op & 0xF0FF == 0x4011:
            self.T = 1 if (r[(op >> 8) & 0xF] & 0x80000000) == 0 else 0
            return

        # ---- cmp/pl ----
        if op & 0xF0FF == 0x4015:
            n = (op >> 8) & 0xF
            self.T = 1 if 0 < (r[n] & MASK) < 0x80000000 else 0
            return

        return super()._exec(op, pc)


def build_ram_setSR_flag1():
    """
    Build a RAM overlay that makes setSR(0) take the fast path (flag == 1).
    The ROM code does:
        r5 = *(0x394C)          → 0xFFFF72B0
        r6 = *(r5 + 24)         → second pointer
        r0 = *(r6 + 1)          → flag byte
    We need *(0xFFFF72B0) = ptr1, *(ptr1 + 24) = ptr2, *(ptr2 + 1) = 1.
    Pick convenient addresses (safe scratch area).
    """
    PTR1 = 0xFFFFA000          # fake "kernel struct" address
    PTR2 = 0xFFFFA100          # fake "state block" address
    ram = {}
    # Write PTR1 as a 32-bit big-endian value at address 0xFFFF72B0
    for i in range(4):
        ram[0xFFFF72B0 + i] = (PTR1 >> (24 - 8 * i)) & 0xFF
    # Write PTR2 at PTR1 + 24 (= 0xFFFFA018)
    for i in range(4):
        ram[PTR1 + 24 + i] = (PTR2 >> (24 - 8 * i)) & 0xFF
    # Write flag = 1 at PTR2 + 1
    ram[PTR2 + 1] = 1
    return ram


# Pre-built RAM for setSR fast path
SETSR_RAM = build_ram_setSR_flag1()


def test_getSR(cpu, N):
    """Verify getSR @0x3920 against pure-Python reference."""
    for _ in range(N):
        # Pick a random current SR value (but keep IPL in valid 0x00-0xF0 range)
        cur_ipl = random.choice([0x00, 0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70,
                                  0x80, 0x90, 0xA0, 0xB0, 0xC0, 0xD0, 0xE0, 0xF0])
        cpu.sr = cur_ipl | 0x00000003           # set T=1, S=1 to verify mask works
        requested = random.randint(0, 0xFF)

        r0 = cpu.call(0x3920, r4=requested, sr=cur_ipl | 0x00000003)

        expected_ret = cur_ipl & 0xF0
        got = r0 & 0xFF
        if got != expected_ret:
            return "getSR ret", (cur_ipl, requested, got, expected_ret)

        # ROM: 0x3926 cmp/hi r0,r4 ; 0x3928 bf -> plain rts+nop (SR unchanged);
        #       else rts with delay ldc r4,SR (SR = requested)
        if requested > cur_ipl:
            if cpu.sr != requested:
                return "getSR sr_raised", (cur_ipl, requested, cpu.sr)
        else:
            if cpu.sr != (cur_ipl | 0x00000003):
                return "getSR sr_unchanged", (cur_ipl, requested, cpu.sr)

    return None


def test_setSR(cpu, N):
    """Verify setSR @0x3934 — always writes r4 to SR (fast path when r4==0)."""
    for _ in range(N):
        cpu.sr = random.randint(0, 0xFFFFFFFF)
        new_val = random.randint(0, 0xFFFFFFFF)

        cpu.call(0x3934, r4=new_val, ram=SETSR_RAM)

        if cpu.sr != new_val:
            return "setSR", (cpu.sr, new_val)

    return None


def test_setSR_zero(cpu):
    """Verify setSR @0x3934 with r4=0 (triggers the pointer-chain flag check)."""
    # Case 1: flag=1 → fast path, SR should become 0
    cpu.sr = 0x000000F0
    cpu.call(0x3934, r4=0, ram=SETSR_RAM)
    if cpu.sr != 0:
        return "setSR_zero_fast", (cpu.sr, 0)

    # Case 2: flag ≠ 1 → tail-call to 0x3DB0 (see test_setSR_tailcall below).
    return None


def test_setSR_tailcall(cpu):
    """r4 == 0 with scheduler flag != 1 → the ROM tail-calls the OS
    task-switch handler 0x3DB0 (delay slot ldc r4,SR fires first, so SR = 0
    at handler entry).  Seed the kernel struct so 0x3DB0 takes its
    early-exit path (word@0x04 == word@0x06 → bt to 0x3DF0): final SR must
    be restored to 0 and r0 must be 0."""
    ram = dict(SETSR_RAM)
    PTR2 = 0xFFFFA100
    ram[PTR2 + 1] = 2                    # flag != 1 -> tail-call 0x3DB0
    ram[0xFFFF72B4] = 0; ram[0xFFFF72B5] = 0   # word@0x04 of the struct
    ram[0xFFFF72B6] = 0; ram[0xFFFF72B7] = 0   # word@0x06 (equal -> early exit)
    cpu.sr = 0x000000F0
    r0 = cpu.call(0x3934, r4=0, ram=ram)
    if cpu.sr != 0 or r0 != 0:
        return "setSR_tailcall", (cpu.sr, r0)
    return None


def test_setSR_PARAM(cpu, N):
    """Verify setSR_PARAM @0x2054 against pure-Python reference."""
    STORE_ADDR = 0xFFFF9000   # scratch write area
    for _ in range(N):
        cur_ipl = random.choice([0x00, 0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70,
                                  0x80, 0x90, 0xA0, 0xB0, 0xC0, 0xD0, 0xE0, 0xF0])
        cpu.sr = cur_ipl | 0x00000002           # S bit set
        new_sr = random.randint(0, 0xFF)

        ram = {STORE_ADDR: 0xAA, STORE_ADDR + 1: 0xBB,
               STORE_ADDR + 2: 0xCC, STORE_ADDR + 3: 0xDD}  # poison
        r0 = cpu.call(0x2054, r4=STORE_ADDR, r5=new_sr,
                      sr=cur_ipl | 0x00000002, ram=ram)

        # Read back stored value
        stored = ((cpu.ram.get(STORE_ADDR, 0) << 24) |
                  (cpu.ram.get(STORE_ADDR + 1, 0) << 16) |
                  (cpu.ram.get(STORE_ADDR + 2, 0) << 8) |
                  cpu.ram.get(STORE_ADDR + 3, 0))

        old_masked = cur_ipl & 0xF0
        # ROM: 0x205A bt/s 0x2060 — delay slot 0x205C mov.l r0,@r4 ALWAYS executes,
        # so [r4] = SR&0xF0 in both cases.  Only the SR clamp is conditional:
        #   taken  (new_sr >= old_masked): SR = new_sr
        #   not taken (new_sr < old_masked): 0x205E mov r0,r5 -> SR = old_masked
        expected_stored = old_masked
        expected_sr = new_sr if new_sr >= old_masked else old_masked
        if stored != expected_stored:
            return "setSR_PARAM store", (cur_ipl, new_sr, stored, expected_stored)

        if cpu.sr != expected_sr:
            return "setSR_PARAM sr", (cur_ipl, new_sr, cpu.sr, expected_sr)

        if r0 != old_masked:
            return "setSR_PARAM ret", (cur_ipl, new_sr, r0, old_masked)

    return None


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 50000
    rom = open(ROM, 'rb').read()
    fails = []

    # ---- getSR ----
    cpu = SRCPU(rom)
    err = test_getSR(cpu, N)
    if err:
        fails.append(err)
    else:
        print("OK  getSR       @0x3920  (%d random inputs)" % N)

    # ---- setSR ----
    cpu = SRCPU(rom)
    err = test_setSR(cpu, N)
    if err:
        fails.append(err)
    else:
        print("OK  setSR       @0x3934  (%d random inputs)" % N)

    # ---- setSR zero special case ----
    cpu = SRCPU(rom)
    err = test_setSR_zero(cpu)
    if err:
        fails.append(err)
    else:
        print("OK  setSR zero  @0x3934  (flag=1 fast path)")

    # ---- setSR r4==0, flag!=1 -> 0x3DB0 tail-call ----
    cpu = SRCPU(rom)
    err = test_setSR_tailcall(cpu)
    if err:
        fails.append(err)
    else:
        print("OK  setSR tail  @0x3934  (flag!=1 -> 0x3DB0 early-exit path)")

    # ---- setSR_PARAM ----
    cpu = SRCPU(rom)
    err = test_setSR_PARAM(cpu, N)
    if err:
        fails.append(err)
    else:
        print("OK  setSR_PARAM @0x2054  (%d random inputs)" % N)

    if fails:
        print("\n%d FAILURE(S):" % len(fails))
        for f in fails:
            print("  %s: %s" % (f[0], f[1]))
        sys.exit(1)
    else:
        print("\nAll tests passed.")
        sys.exit(0)


if __name__ == '__main__':
    main()
