#!/usr/bin/env python3
"""
sh2emu.py — tiny SH-2E (big-endian) interpreter for Track-A verification.

Executes the ACTUAL ROM bytes of a function so a C lift can be checked against real
machine behavior over many inputs. This CPU is a Renesas SH7055 (HD64F7055S): SH-2
integer core **plus a single-precision hardware FPU** — so the FPU is emulated too
(FR0-15, FPUL, fadd/fsub/fmul/fdiv/fmac/fmov(.s)/fcmp/float/ftrc/fsts/flds/fneg/fabs/
fsqrt/fldi0/1). Unknown opcodes raise NotImplementedError so gaps are explicit.

API:
  cpu = SH2(rom_bytes)
  r0  = cpu.call(entry, r4=..., r5=..., ram={addr:byte}, fr={4:1.5,5:2.0})
  # FP result is in cpu.fr[0]
"""
import struct

MASK = 0xFFFFFFFF


def s32(x): x &= MASK; return x - (1 << 32) if x & 0x80000000 else x
def s16(x): x &= 0xFFFF; return x - (1 << 16) if x & 0x8000 else x
def s8(x):  x &= 0xFF;   return x - (1 << 8) if x & 0x80 else x
def ts(x):  # round a Python float to IEEE-754 single precision
    return struct.unpack('>f', struct.pack('>f', x))[0]
def f2bits(v): return struct.unpack('>I', struct.pack('>f', ts(v)))[0]
def bits2f(b): return struct.unpack('>f', struct.pack('>I', b & MASK))[0]


class SH2:
    def __init__(self, rom):
        self.rom = rom
        self._romlen = len(rom)
        self.SENT = 0xEEEE0000

    # ---- memory (ROM base + sparse RAM overlay) ----
    def _rb(self, a):
        a &= MASK
        v = self.ram.get(a)          # single dict probe (values are always ints)
        if v is not None: return v
        return self.rom[a] if a < self._romlen else 0
    def _wb(self, a, v): self.ram[a & MASK] = v & 0xFF
    def rd(self, a, n):
        v = 0
        for i in range(n): v = (v << 8) | self._rb(a + i)
        return v
    def wr(self, a, n, v):
        for i in range(n): self._wb(a + i, (v >> (8 * (n - 1 - i))) & 0xFF)
    def rdf(self, a): return struct.unpack('>f', bytes(self._rb(a + i) for i in range(4)))[0]
    def wrf(self, a, v):
        b = struct.pack('>f', ts(v))
        for i in range(4): self._wb(a + i, b[i])

    def call(self, entry, r4=0, r5=0, r6=0, r7=0, ram=None, fr=None, sr=0x000000F0):
        self.ram = dict(ram or {})
        self.r = [0] * 16
        self.r[4], self.r[5], self.r[6], self.r[7] = r4 & MASK, r5 & MASK, r6 & MASK, r7 & MASK
        self.r[15] = 0xFFFFDF00
        self.fr = [0.0] * 16
        for k, v in (fr or {}).items(): self.fr[k] = ts(v)
        self.pr = self.SENT; self.T = 0; self.macl = 0; self.mach = 0; self.gbr = 0; self.sr = sr & MASK
        self.vbr = 0; self.ssr = 0; self.spc = 0
        self.fpul = 0; self.fpscr = 0
        # division flags (SR bits 3/2); T bit mirrored in self.T
        self._Q = (self.sr >> 3) & 1
        self._M = (self.sr >> 2) & 1
        # Hot loop: hoist attribute lookups into locals and inline the 2-byte
        # opcode fetch (avoids rd/_rb/len call overhead per instruction).
        # Two variants: with a RAM overlay every fetch must probe the ram dict;
        # without one (common for pure busy-wait verification) the fetch is a
        # single C-level int.from_bytes slice.
        r = self.r
        ram = self.ram
        rom = self.rom
        romlen = self._romlen
        SENT = self.SENT
        M = MASK
        delayed = self._delayed
        exec_op = self._exec
        pc = entry & M
        steps = 0
        if not ram:
            while True:
                if ram:
                    break           # a memory write happened: fall back to the
                                    # ram-aware fetch below (self-modifying case)
                if pc == SENT:
                    self.pc = pc
                    return r[0] & M
                steps += 1
                if steps > 500000:
                    self.pc = pc
                    raise RuntimeError("runaway at 0x%X" % pc)
                a = pc
                if a + 1 < romlen:
                    op = (rom[a] << 8) | rom[a + 1]
                else:                                   # near/over end of ROM
                    b = rom[a] if a < romlen else 0
                    b1 = rom[a + 1] if a + 1 < romlen else 0
                    op = (b << 8) | b1
                self.pc = pc
                br = delayed(op)
                if br is None:
                    exec_op(op, pc)
                    pc = (self.pc + 2) & M
                else:
                    target, take = br
                    a = (pc + 2) & M
                    if a + 1 < romlen:
                        op2 = (rom[a] << 8) | rom[a + 1]
                    else:
                        b = rom[a] if a < romlen else 0
                        b1 = rom[a + 1] if a + 1 < romlen else 0
                        op2 = (b << 8) | b1
                    exec_op(op2, a)
                    pc = target if take else (self.pc + 4) & M
        # Mixed ram/rom fetch.  Reached when ram was non-empty up front, or when
        # the empty-ram loop above bailed out after the first memory write.
        while True:
            if pc == SENT:
                self.pc = pc
                return r[0] & M
            steps += 1
            if steps > 500000:
                self.pc = pc
                raise RuntimeError("runaway at 0x%X" % pc)
            a = pc
            b = ram.get(a)
            if b is None:
                b = rom[a] if a < romlen else 0
            a1 = (a + 1) & M
            b1 = ram.get(a1)
            if b1 is None:
                b1 = rom[a1] if a1 < romlen else 0
            op = (b << 8) | b1
            self.pc = pc
            br = delayed(op)
            if br is None:
                exec_op(op, pc)
                pc = (self.pc + 2) & M
            else:
                target, take = br
                a = (pc + 2) & M
                b = ram.get(a)
                if b is None:
                    b = rom[a] if a < romlen else 0
                a1 = (a + 1) & M
                b1 = ram.get(a1)
                if b1 is None:
                    b1 = rom[a1] if a1 < romlen else 0
                exec_op((b << 8) | b1, a)
                pc = target if take else (self.pc + 4) & M

    def _delayed(self, op):
        # Dispatch on the top nibble first so the common (non-delayed) case
        # exits after at most a couple of comparisons instead of ~10.
        n0 = op >> 12
        if n0 == 0:
            if op == 0x000B: return (self.pr, True)                     # rts
            if op == 0x002B:                                            # rte (delayed): pop PC,SR
                self.sr = self.rd(self.r[15] + 4, 4)
                target = self.rd(self.r[15], 4) & MASK
                self.r[15] = (self.r[15] + 8) & MASK
                return (target, True)
            f = op & 0xF0FF
            if f == 0x0003:                                             # bsrf Rn (delayed)
                m = (op >> 8) & 0xF; self.pr = (self.pc + 4) & MASK
                return (((self.pc + 4 + self.r[m]) & MASK), True)
            if f == 0x0023:                                             # braf Rn (delayed)
                m = (op >> 8) & 0xF; return (((self.pc + 4 + self.r[m]) & MASK), True)
            return None
        if n0 == 4:
            f = op & 0xF0FF
            if f == 0x400B:                                             # jsr @Rn
                m = (op >> 8) & 0xF; self.pr = (self.pc + 4) & MASK; return (self.r[m] & MASK, True)
            if f == 0x402B:                                             # jmp @Rn
                m = (op >> 8) & 0xF; return (self.r[m] & MASK, True)
            return None
        if n0 == 0xA:                                                   # bra
            d = op & 0xFFF; d -= 0x1000 if d & 0x800 else 0; return ((self.pc + 4 + d * 2) & MASK, True)
        if n0 == 0xB:                                                   # bsr
            d = op & 0xFFF; d -= 0x1000 if d & 0x800 else 0; self.pr = (self.pc + 4) & MASK
            return ((self.pc + 4 + d * 2) & MASK, True)
        if n0 == 8:
            f = op & 0xFF00
            if f == 0x8D00:                                             # bt/s
                d = s8(op & 0xFF); return ((self.pc + 4 + d * 2) & MASK, self.T == 1)
            if f == 0x8F00:                                             # bf/s
                d = s8(op & 0xFF); return ((self.pc + 4 + d * 2) & MASK, self.T == 0)
            return None
        return None

    def _exec(self, op, pc):
        r = self.r; n = (op >> 8) & 0xF; m = (op >> 4) & 0xF; n0 = op >> 12
        lo = op & 0xFF; nib = op & 0xF
        if n0 == 0x6:
            if nib == 0x3: r[n] = r[m]; return
            if nib == 0xC: r[n] = r[m] & 0xFF; return              # extu.b
            if nib == 0xD: r[n] = r[m] & 0xFFFF; return            # extu.w
            if nib == 0xE: r[n] = s8(r[m]) & MASK; return          # exts.b
            if nib == 0xF: r[n] = s16(r[m]) & MASK; return         # exts.w
            if nib == 0x0: r[n] = s8(self.rd(r[m], 1)) & MASK; return   # mov.b @Rm,Rn (sign-ext)
            if nib == 0x1: r[n] = s16(self.rd(r[m], 2)) & MASK; return  # mov.w @Rm,Rn
            if nib == 0x2: r[n] = self.rd(r[m], 4); return             # mov.l @Rm,Rn
            if nib == 0x4: r[n] = s8(self.rd(r[m], 1)) & MASK; r[m] = (r[m] + 1) & MASK; return
            if nib == 0x5: r[n] = s16(self.rd(r[m], 2)) & MASK; r[m] = (r[m] + 2) & MASK; return
            if nib == 0x6: r[n] = self.rd(r[m], 4); r[m] = (r[m] + 4) & MASK; return
            if nib == 0x7: r[n] = (~r[m]) & MASK; return           # not
            if nib == 0xB: r[n] = (-s32(r[m])) & MASK; return      # neg
            if nib == 0x8: r[n] = (((r[m] << 8) & 0xFF00FF00) | ((r[m] >> 8) & 0x00FF00FF)) & MASK; return  # swap.b
            if nib == 0x9: r[n] = ((r[m] << 16) | (r[m] >> 16)) & MASK; return  # swap.w
            if nib == 0xA: s = -r[m] - self.T; r[n] = s & MASK; self.T = 1 if ((r[m] + self.T) & MASK) else 0; return  # negc
        if n0 == 0x8:
            if op & 0xFF00 == 0x8800: self.T = 1 if s32(r[0]) == s8(lo) else 0; return  # cmp/eq #imm,R0
            if op & 0xFF00 == 0x8B00:                              # bf
                if self.T == 0: self.pc = ((pc + 4 + s8(lo) * 2) & MASK) - 2
                return
            if op & 0xFF00 == 0x8900:                              # bt
                if self.T == 1: self.pc = ((pc + 4 + s8(lo) * 2) & MASK) - 2
                return
            if op & 0xFF00 == 0x8000: self.wr(r[m] + (op & 0xF), 1, r[0]); return  # mov.b R0,@(disp,Rm)
            if op & 0xFF00 == 0x8100: self.wr(r[m] + ((op & 0xF) * 2), 2, r[0]); return  # mov.w R0,@(disp,Rm)
            if op & 0xFF00 == 0x8200: self.wr(r[m] + ((op & 0xF) * 4), 4, r[0]); return  # mov.l R0,@(disp,Rm)
            if op & 0xFF00 == 0x8400: r[0] = s8(self.rd(r[m] + (op & 0xF), 1)) & MASK; return  # mov.b @(disp,Rm),R0
            if op & 0xFF00 == 0x8500: r[0] = s16(self.rd(r[m] + ((op & 0xF) * 2), 2)) & MASK; return  # mov.w @(disp,Rm),R0
            if op & 0xFF00 == 0x8600: r[0] = self.rd(r[m] + ((op & 0xF) * 4), 4); return  # mov.l @(disp,Rm),R0
        if n0 == 0x3:
            if nib == 0xC: r[n] = (r[n] + r[m]) & MASK; return     # add
            if nib == 0x8: r[n] = (r[n] - r[m]) & MASK; return     # sub
            if nib == 0x0: self.T = 1 if s32(r[n]) == s32(r[m]) else 0; return  # cmp/eq
            if nib == 0x2: self.T = 1 if (r[n] & MASK) >= (r[m] & MASK) else 0; return  # cmp/hs
            if nib == 0x3: self.T = 1 if s32(r[n]) >= s32(r[m]) else 0; return  # cmp/ge
            if nib == 0x6: self.T = 1 if (r[n] & MASK) > (r[m] & MASK) else 0; return  # cmp/hi
            if nib == 0x7: self.T = 1 if s32(r[n]) > s32(r[m]) else 0; return   # cmp/gt
            if nib == 0xE: s = r[n] + r[m] + self.T; self.T = 1 if s > MASK else 0; r[n] = s & MASK; return  # addc
            if nib == 0xA: s = r[n] - r[m] - self.T; self.T = 1 if s < 0 else 0; r[n] = s & MASK; return  # subc
            if nib == 0xB: s = s32(r[n]) - s32(r[m]); r[n] = s & MASK; self.T = 1 if s > 0x7FFFFFFF or s < -0x80000000 else 0; return  # subv
            if nib == 0xF: s = s32(r[n]) + s32(r[m]); r[n] = s & MASK; self.T = 1 if s > 0x7FFFFFFF or s < -0x80000000 else 0; return  # addv
            if nib == 0x4:                                          # div1 Rm,Rn
                t0 = (r[n] >> 31) & 1                               # MSB of Rn, pushed out
                r[n] = ((r[n] << 1) | (self.T & 1)) & MASK          # rotate left, insert old T
                t1 = (self._Q ^ self._M) & 1
                t1 = (t1 - 1) & MASK                                # 0xFFFFFFFF if Q==M else 0
                t2 = (-r[m]) & MASK
                if t1 == 0: t2 = r[m]                               # Q==M: subtract Rm, else add Rm
                lo = r[n] + t2
                r[n] = lo & MASK
                carry = (lo >> 32) & 1                              # carry AND borrow
                t1 = (t1 + carry) & 1
                t1 ^= t0
                self.T = (t1 ^ 1) & 1
                self._Q = (self._M ^ t1) & 1
                return
            if nib == 0xD: p = s32(r[m]) * s32(r[n]); self.mach = (p >> 32) & MASK; self.macl = p & MASK; return  # dmuls.l
            if nib == 0x5: p = (r[m] & MASK) * (r[n] & MASK); self.mach = (p >> 32) & MASK; self.macl = p & MASK; return  # dmulu.l
        if n0 == 0x2:
            if nib == 0x0: self.wr(r[n], 1, r[m]); return          # mov.b Rm,@Rn
            if nib == 0x1: self.wr(r[n], 2, r[m]); return
            if nib == 0x2: self.wr(r[n], 4, r[m]); return
            if nib == 0x4: r[n] = (r[n] - 1) & MASK; self.wr(r[n], 1, r[m]); return  # @-Rn
            if nib == 0x5: r[n] = (r[n] - 2) & MASK; self.wr(r[n], 2, r[m]); return
            if nib == 0x6: r[n] = (r[n] - 4) & MASK; self.wr(r[n], 4, r[m]); return
            if nib == 0x8: self.T = 1 if (r[n] & r[m]) == 0 else 0; return  # tst
            if nib == 0x9: r[n] &= r[m]; return                    # and
            if nib == 0xA: r[n] ^= r[m]; return                    # xor
            if nib == 0xB: r[n] |= r[m]; return                    # or
            if nib == 0xC:                                          # cmp/str Rm,Rn
                x = r[m] ^ r[n]; y = (x - 0x01010101) & MASK; y &= (~x) & MASK
                self.T = 1 if (y & 0x80808080) else 0; return
            if nib == 0xD: r[n] = ((r[n] << 16) | (r[m] >> 16)) & MASK; return  # xtrct
            if nib == 0x7:                                          # div0s Rm,Rn
                self._Q = (r[n] >> 31) & 1; self._M = (r[m] >> 31) & 1
                self.T = self._Q ^ self._M; return
            if nib == 0xF: self.macl = (s16(r[m]) * s16(r[n])) & MASK; return  # muls.w
            if nib == 0xE: self.macl = ((r[m] & 0xFFFF) * (r[n] & 0xFFFF)) & MASK; return  # mulu.w
        if n0 == 0x7: r[n] = (r[n] + s8(lo)) & MASK; return        # add #imm,Rn
        if n0 == 0xE: r[n] = s8(lo) & MASK; return                 # mov #imm,Rn
        if n0 == 0xD: r[n] = self.rd(((pc + 4) & ~3) + lo * 4, 4) & MASK; return  # mov.l @(disp,PC)
        if n0 == 0x9: r[n] = s16(self.rd((pc + 4 + lo * 2), 2)) & MASK; return  # mov.w @(disp,PC)
        if op & 0xFF00 == 0xC700: r[0] = (((pc + 4) & ~3) + lo * 4) & MASK; return  # mova @(disp,PC),R0
        if n0 == 0xC:
            if op & 0xFF00 == 0xC800: self.T = 1 if (r[0] & lo) == 0 else 0; return  # tst #imm,R0
            if op & 0xFF00 == 0xC900: r[0] &= lo; return                          # and #imm,R0
            if op & 0xFF00 == 0xCA00: r[0] ^= lo; return                          # xor #imm,R0
            if op & 0xFF00 == 0xCB00: r[0] |= lo; return                          # or #imm,R0
            if op & 0xFF00 == 0xC300: raise NotImplementedError("trapa @0x%X" % pc)  # trapa #imm
            if op & 0xFF00 == 0xC000: self.wr(self.gbr + lo, 1, r[0]); return     # mov.b R0,@(disp,GBR)
            if op & 0xFF00 == 0xC100: self.wr(self.gbr + lo * 2, 2, r[0]); return  # mov.w R0,@(disp,GBR)
            if op & 0xFF00 == 0xC200: self.wr(self.gbr + lo * 4, 4, r[0]); return  # mov.l R0,@(disp,GBR)
            if op & 0xFF00 == 0xC400: r[0] = s8(self.rd(self.gbr + lo, 1)) & MASK; return   # mov.b @(disp,GBR),R0
            if op & 0xFF00 == 0xC500: r[0] = s16(self.rd(self.gbr + lo * 2, 2)) & MASK; return  # mov.w @(disp,GBR),R0
            if op & 0xFF00 == 0xC600: r[0] = self.rd(self.gbr + lo * 4, 4); return  # mov.l @(disp,GBR),R0
        if op == 0x0009: return
        if op == 0x001B: return                                    # sleep (halt; treated as no-op)
        if op == 0x0019: self._Q = 0; self._M = 0; self.T = 0; return  # div0u
        if op == 0x0008: self.T = 0; return                    # clrt
        if op == 0x0018: self.T = 1; return                    # sett
        if op == 0x0028: self.mach = 0; self.macl = 0; return  # clrmac
        if op & 0xF0FF == 0x0029: r[(op >> 8) & 0xF] = self.T; return  # movt Rn
        if n0 == 0x0:
            if nib == 0x7: self.macl = (s32(r[n]) * s32(r[m])) & MASK; return  # mul.l
            if op & 0xF0FF == 0x000A: r[n] = self.mach; return     # sts mach,Rn
            if op & 0xF0FF == 0x001A: r[n] = self.macl; return     # sts macl,Rn
            if op & 0xF0FF == 0x002A: r[n] = self.pr; return       # sts pr,Rn
            if op & 0xF0FF == 0x005A: r[n] = self.fpul; return     # sts fpul,Rn
            if op & 0xF0FF == 0x006A: r[n] = self.fpscr; return    # sts fpscr,Rn
            if op & 0xF00F == 0x0004: self.wr(r[0] + r[n], 1, r[m]); return  # mov.b Rm,@(R0,Rn)
            if op & 0xF00F == 0x0005: self.wr(r[0] + r[n], 2, r[m]); return  # mov.w Rm,@(R0,Rn)
            if op & 0xF00F == 0x0006: self.wr(r[0] + r[n], 4, r[m]); return  # mov.l Rm,@(R0,Rn)
            if op & 0xF00F == 0x000C: r[n] = s8(self.rd(r[0] + r[m], 1)) & MASK; return  # mov.b @(R0,Rm),Rn (sign-ext)
            if op & 0xF00F == 0x000D: r[n] = s16(self.rd(r[0] + r[m], 2)) & MASK; return  # mov.w @(R0,Rm),Rn
            if op & 0xF00F == 0x000E: r[n] = self.rd(r[0] + r[m], 4); return  # mov.l @(R0,Rm),Rn
            if op & 0xF0FF == 0x0002 and (op >> 12) == 0: r[n] = self.sr; return  # stc SR,Rn
            if op & 0xF0FF == 0x0012 and (op >> 12) == 0: r[n] = self.gbr; return  # stc GBR,Rn
            if op & 0xF0FF == 0x0022 and (op >> 12) == 0: r[n] = self.vbr; return  # stc VBR,Rn
            if op & 0xF0FF == 0x0032 and (op >> 12) == 0: r[n] = self.ssr; return  # stc SSR,Rn
            if op & 0xF0FF == 0x0042 and (op >> 12) == 0: r[n] = self.spc; return  # stc SPC,Rn
            if nib == 0xF:                                    # mac.l @Rm+,@Rn+
                a = s32(self.rd(r[m], 4)); b = s32(self.rd(r[n], 4))
                r[m] = (r[m] + 4) & MASK; r[n] = (r[n] + 4) & MASK
                p = a * b
                mac = ((self.mach << 32) | self.macl)
                if mac >= 0x8000000000000000: mac -= 0x10000000000000000  # to signed
                res = mac + p
                if (self.sr >> 1) & 1:                      # S bit: saturate 64-bit
                    if res > 0x7FFFFFFFFFFFFFFF: res = 0x7FFFFFFFFFFFFFFF
                    elif res < -0x8000000000000000: res = -0x8000000000000000
                self.mach = (res >> 32) & MASK; self.macl = res & MASK; return
        # ---- FPU (0xF___) ----
        if n0 == 0xF:
            f = self.fr
            if nib == 0x0: f[n] = ts(f[n] + f[m]); return           # fadd FRm,FRn
            if nib == 0x1: f[n] = ts(f[n] - f[m]); return           # fsub
            if nib == 0x2: f[n] = ts(f[n] * f[m]); return           # fmul
            if nib == 0x3: f[n] = ts(f[n] / f[m]); return           # fdiv
            if nib == 0x4: self.T = 1 if f[n] == f[m] else 0; return   # fcmp/eq Fm,Fn  (FRn == FRm)
            if nib == 0x5: self.T = 1 if f[n] > f[m] else 0; return    # fcmp/gt Fm,Fn  (FRn > FRm)
            if nib == 0x6: f[n] = self.rdf(r[0] + r[m]); return      # fmov.s @(R0,Rm),FRn
            if nib == 0x7: self.wrf(r[0] + r[n], f[m]); return       # fmov.s FRm,@(R0,Rn)
            if nib == 0x8: f[n] = self.rdf(r[m]); return            # fmov.s @Rm,FRn
            if nib == 0x9: f[n] = self.rdf(r[m]); r[m] = (r[m] + 4) & MASK; return  # @Rm+
            if nib == 0xA: self.wrf(r[n], f[m]); return             # fmov.s FRm,@Rn
            if nib == 0xB: r[n] = (r[n] - 4) & MASK; self.wrf(r[n], f[m]); return   # FRm,@-Rn
            if nib == 0xC: f[n] = f[m]; return                      # fmov FRm,FRn
            if nib == 0xE: f[n] = ts(f[0] * f[m] + f[n]); return    # fmac FR0,FRm,FRn
            if nib == 0xD:
                if m == 0x0: f[n] = bits2f(self.fpul); return       # fsts FPUL,FRn
                if m == 0x1: self.fpul = f2bits(f[n]); return       # flds FRn,FPUL
                if m == 0x2: f[n] = ts(float(s32(self.fpul))); return  # float FPUL,FRn
                if m == 0x3: self.fpul = int(f[n]) & MASK; return   # ftrc FRn,FPUL (trunc)
                if m == 0x4: f[n] = -f[n]; return                   # fneg
                if m == 0x5: f[n] = abs(f[n]); return               # fabs
                if m == 0x6: f[n] = ts(f[n] ** 0.5); return         # fsqrt
                if m == 0x8: f[n] = 0.0; return                     # fldi0
                if m == 0x9: f[n] = 1.0; return                     # fldi1
            raise NotImplementedError("FPU 0x%04X @0x%X" % (op, pc))
        if n0 == 0x5: r[n] = self.rd(r[m] + (nib * 4), 4); return  # mov.l @(disp,Rm),Rn
        if n0 == 0x1: self.wr(r[n] + (nib * 4), 4, r[m]); return   # mov.l Rm,@(disp,Rn)
        if n0 == 0x4:
            if op & 0xF0FF == 0x4000: self.T = (r[n] >> 31) & 1; r[n] = (r[n] << 1) & MASK; return  # shll
            if op & 0xF0FF == 0x4001: self.T = r[n] & 1; r[n] = (r[n] >> 1) & MASK; return          # shlr
            if op & 0xF0FF == 0x4008: r[n] = (r[n] << 2) & MASK; return   # shll2
            if op & 0xF0FF == 0x4009: r[n] = (r[n] >> 2) & MASK; return   # shlr2
            if op & 0xF0FF == 0x4018: r[n] = (r[n] << 8) & MASK; return   # shll8
            if op & 0xF0FF == 0x4019: r[n] = (r[n] >> 8) & MASK; return   # shlr8
            if op & 0xF0FF == 0x4028: r[n] = (r[n] << 16) & MASK; return  # shll16
            if op & 0xF0FF == 0x4029: r[n] = (r[n] >> 16) & MASK; return  # shlr16
            if op & 0xF0FF == 0x4021: self.T = r[n] & 1; r[n] = ((r[n] >> 1) | (s32(r[n]) & 0x80000000)) & MASK; return  # shar
            if op & 0xF0FF == 0x4020: self.T = (r[n] >> 31) & 1; r[n] = (r[n] << 1) & MASK; return  # shal
            if op & 0xF0FF == 0x4010: r[n] = (r[n] - 1) & MASK; self.T = 1 if r[n] == 0 else 0; return  # dt
            if op & 0xF0FF == 0x4025: t = r[n] & 1; r[n] = ((r[n] >> 1) | (self.T << 31)) & MASK; self.T = t; return  # rotcr
            if op & 0xF0FF == 0x4024: t = (r[n] >> 31) & 1; r[n] = ((r[n] << 1) | self.T) & MASK; self.T = t; return  # rotcl
            if op & 0xF0FF == 0x4004: t = (r[n] >> 31) & 1; r[n] = ((r[n] << 1) | (r[n] >> 31)) & MASK; self.T = t; return  # rotl
            if op & 0xF0FF == 0x4005: t = r[n] & 1; r[n] = ((r[n] >> 1) | ((r[n] & 1) << 31)) & MASK; self.T = t; return  # rotr
            if op & 0xF0FF == 0x4011: self.T = 1 if s32(r[n]) >= 0 else 0; return  # cmp/pz
            if op & 0xF0FF == 0x4015: self.T = 1 if s32(r[n]) > 0 else 0; return   # cmp/pl
            if op & 0xF0FF == 0x400A: self.mach = r[n]; return     # lds Rn,mach
            if op & 0xF0FF == 0x401A: self.macl = r[n]; return     # lds Rn,macl
            if op & 0xF0FF == 0x402A: self.pr = r[n]; return       # lds Rn,pr
            if op & 0xF0FF == 0x4022: r[n] = (r[n] - 4) & MASK; self.wr(r[n], 4, self.pr); return  # sts.l pr,@-Rn
            if op & 0xF0FF == 0x4026: self.pr = self.rd(r[n], 4); r[n] = (r[n] + 4) & MASK; return  # lds.l @Rn+,pr
            if op & 0xF0FF == 0x4012: r[n] = (r[n] - 4) & MASK; self.wr(r[n], 4, self.macl); return  # sts.l macl,@-Rn
            if op & 0xF0FF == 0x4002: r[n] = (r[n] - 4) & MASK; self.wr(r[n], 4, self.mach); return  # sts.l mach,@-Rn
            if op & 0xF0FF == 0x4016: self.macl = self.rd(r[n], 4); r[n] = (r[n] + 4) & MASK; return  # lds.l @Rn+,macl
            if op & 0xF0FF == 0x4006: self.mach = self.rd(r[n], 4); r[n] = (r[n] + 4) & MASK; return  # lds.l @Rn+,mach
            if op & 0xF0FF == 0x405A: self.fpul = r[n]; return     # lds Rn,fpul
            if op & 0xF0FF == 0x406A: self.fpscr = r[n]; return    # lds Rn,fpscr
            if op & 0xF0FF == 0x4056: self.fpul = self.rd(r[n], 4); r[n] = (r[n] + 4) & MASK; return  # lds.l @Rn+,fpul
            if op & 0xF0FF == 0x4052: r[n] = (r[n] - 4) & MASK; self.wr(r[n], 4, self.fpul); return   # sts.l fpul,@-Rn
            if op & 0xF0FF == 0x4066: self.fpscr = self.rd(r[n], 4); r[n] = (r[n] + 4) & MASK; return  # lds.l @Rn+,fpscr
            if op & 0xF0FF == 0x4062: r[n] = (r[n] - 4) & MASK; self.wr(r[n], 4, self.fpscr); return   # sts.l fpscr,@-Rn
            # stc.l SR,@-Rn = 0x4n03
            if op & 0xF0FF == 0x4003: r[n] = (r[n] - 4) & MASK; self.wr(r[n], 4, self.sr); return
            # stc.l GBR,@-Rn = 0x4n13
            if op & 0xF0FF == 0x4013: r[n] = (r[n] - 4) & MASK; self.wr(r[n], 4, self.gbr); return
            # ldc Rn,SR = 0x4n0E (register to SR)
            if op & 0xF0FF == 0x400E: self.sr = r[n]; return
            # ldc Rn,GBR = 0x4n1E
            if op & 0xF0FF == 0x401E: self.gbr = r[n]; return
            # ldc.l @Rn+,SR = 0x4n07
            if op & 0xF0FF == 0x4007: self.sr = self.rd(r[n], 4); r[n] = (r[n] + 4) & MASK; return
            # ldc.l @Rn+,GBR = 0x4n17
            if op & 0xF0FF == 0x4017: self.gbr = self.rd(r[n], 4); r[n] = (r[n] + 4) & MASK; return
            # stc.l VBR,@-Rn = 0x4n23
            if op & 0xF0FF == 0x4023: r[n] = (r[n] - 4) & MASK; self.wr(r[n], 4, self.vbr); return
            # stc.l SSR,@-Rn = 0x4n33
            if op & 0xF0FF == 0x4033: r[n] = (r[n] - 4) & MASK; self.wr(r[n], 4, self.ssr); return
            # stc.l SPC,@-Rn = 0x4n43
            if op & 0xF0FF == 0x4043: r[n] = (r[n] - 4) & MASK; self.wr(r[n], 4, self.spc); return
            # ldc.l @Rn+,VBR = 0x4n27
            if op & 0xF0FF == 0x4027: self.vbr = self.rd(r[n], 4); r[n] = (r[n] + 4) & MASK; return
            # ldc.l @Rn+,SSR = 0x4n37
            if op & 0xF0FF == 0x4037: self.ssr = self.rd(r[n], 4); r[n] = (r[n] + 4) & MASK; return
            # ldc.l @Rn+,SPC = 0x4n47
            if op & 0xF0FF == 0x4047: self.spc = self.rd(r[n], 4); r[n] = (r[n] + 4) & MASK; return
            # ldc Rn,VBR = 0x4n2E
            if op & 0xF0FF == 0x402E: self.vbr = r[n]; return
            # ldc Rn,SSR = 0x4n3E
            if op & 0xF0FF == 0x403E: self.ssr = r[n]; return
            # ldc Rn,SPC = 0x4n4E
            if op & 0xF0FF == 0x404E: self.spc = r[n]; return
            # tas.b @Rn = 0x4n1B
            if op & 0xF0FF == 0x401B: self.T = 1 if self.rd(r[n], 1) == 0 else 0; self.wr(r[n], 1, self.rd(r[n], 1) | 0x80); return
            if nib == 0xF:                                    # mac.w @Rm+,@Rn+
                a = s16(self.rd(r[m], 2)); b = s16(self.rd(r[n], 2))
                r[m] = (r[m] + 2) & MASK; r[n] = (r[n] + 2) & MASK
                s = self.macl + a * b
                if (self.sr >> 1) & 1:                        # S bit: saturate 32-bit
                    if s > 0x7FFFFFFF: self.macl = 0x7FFFFFFF
                    elif s < -0x80000000: self.macl = 0x80000000
                    else: self.macl = s & MASK
                else:
                    self.macl = s & MASK
                return
        raise NotImplementedError("opcode 0x%04X @0x%X" % (op, pc))
