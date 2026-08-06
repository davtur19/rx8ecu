#!/usr/bin/env python3
"""
Minimal SH-2E disassembler built on the same opcode decode logic as sh2emu.py.
Useful for extracting human-readable asm for functions in the RX-8 ECU ROMs.
"""

import struct, sys

MASK = 0xFFFFFFFF
REG = "r0 r1 r2 r3 r4 r5 r6 r7 r8 r9 r10 r11 r12 r13 r14 r15".split()
FREG = "fr0 fr1 fr2 fr3 fr4 fr5 fr6 fr7 fr8 fr9 fr10 fr11 fr12 fr13 fr14 fr15".split()


def s32(x):
    x &= MASK
    return x - (1 << 32) if x & 0x80000000 else x


def s16(x):
    x &= 0xFFFF
    return x - (1 << 16) if x & 0x8000 else x


def s8(x):
    x &= 0xFF
    return x - (1 << 8) if x & 0x80 else x


def disasm_one(op, pc, rd16=None, rd32=None):
    """
    Return (mnemonic, operands_string, annotation) for one SH-2E opcode.
    rd16(addr) and rd32(addr) are callbacks for reading PC-relative data.
    """
    r = REG
    fr = FREG
    n = (op >> 8) & 0xF
    m = (op >> 4) & 0xF
    n0 = op >> 12
    lo = op & 0xFF
    nib = op & 0xF

    ann = ""

    # ---- FPU (0xF___) ----
    if n0 == 0xF:
        # fsca FPUL,DRn = 0xFFnD (encoding 1111 0nnn 1111 1101, DR = FR2k/FR2k+1
        # pair, k = bits 11-9).  DRn = sin, DR[n+1] = cos; abs err < 2^-21.
        # Emitted as GNU-as "fsca fpul,drN" (drN = DR2k) so the bulk
        # assemble/re-assemble round-trip keeps the exact word.
        if (op & 0xF1FF) == 0xF0FD:
            k = (op >> 9) & 0x7
            return ("fsca", "fpul,dr%d" % (2 * k), ann)
        if nib == 0x0:
            return ("fadd", f"{fr[m]},{fr[n]}", ann)
        if nib == 0x1:
            return ("fsub", f"{fr[m]},{fr[n]}", ann)
        if nib == 0x2:
            return ("fmul", f"{fr[m]},{fr[n]}", ann)
        if nib == 0x3:
            return ("fdiv", f"{fr[m]},{fr[n]}", ann)
        if nib == 0x4:
            return ("fcmp/eq", f"{fr[m]},{fr[n]}", ann)
        if nib == 0x5:
            return ("fcmp/gt", f"{fr[m]},{fr[n]}", ann)
        if nib == 0x6:
            return ("fmov.s", f"@(r0,{r[m]}),{fr[n]}", ann)
        if nib == 0x7:
            return ("fmov.s", f"{fr[m]},@(r0,{r[n]})", ann)
        if nib == 0x8:
            return ("fmov.s", f"@{r[m]},{fr[n]}", ann)
        if nib == 0x9:
            return ("fmov.s", f"@{r[m]}+,{fr[n]}", ann)
        if nib == 0xA:
            return ("fmov.s", f"{fr[m]},@{r[n]}", ann)
        if nib == 0xB:
            return ("fmov.s", f"{fr[m]},@-{r[n]}", ann)
        if nib == 0xC:
            return ("fmov", f"{fr[m]},{fr[n]}", ann)
        if nib == 0xE:
            return ("fmac", f"fr0,{fr[m]},{fr[n]}", ann)
        if nib == 0xD:
            if m == 0x0:
                return ("fsts", f"fpul,{fr[n]}", ann)
            if m == 0x1:
                return ("flds", f"{fr[n]},fpul", ann)
            if m == 0x2:
                return ("float", f"fpul,{fr[n]}", ann)
            if m == 0x3:
                return ("ftrc", f"{fr[n]},fpul", ann)
            if m == 0x4:
                return ("fneg", f"{fr[n]}", ann)
            if m == 0x5:
                return ("fabs", f"{fr[n]}", ann)
            if m == 0x6:
                return ("fsqrt", f"{fr[n]}", ann)
            if m == 0x8:
                return ("fldi0", f"{fr[n]}", ann)
            if m == 0x9:
                return ("fldi1", f"{fr[n]}", ann)
        return (f"fpu_unknown", f"0x{op:04X}", ann)

    # ---- Specials ----
    if op == 0x0009:
        return ("nop", "", ann)
    if op == 0x0008:
        return ("clrt", "", ann)
    if op == 0x0018:
        return ("sett", "", ann)
    if op == 0x0028:
        return ("clrmac", "", ann)
    if op == 0x000B:
        return ("rts", "", ann)
    if op == 0x002B:
        return ("rte", "", ann)
    if op == 0x001B:
        return ("sleep", "", ann)
    if op == 0x0019:
        # GNU-as 2.46 accepts div0u ONLY with no operands (emits 0x0019)
        return ("div0u", "", ann)
    if op & 0xF0FF == 0x0029:
        return ("movt", r[n], ann)

    # ---- Branches ----
    # NOTE: SH-2 encodes the source register in bits 11-8 for jsr/jmp
    # (0x4n0B jsr@Rn / 0x4n2B jmp@Rn), so the register is r[n], not r[m].
    if op & 0xF0FF == 0x400B:  # jsr @Rn
        return ("jsr", f"@{r[n]}", ann)
    if op & 0xF0FF == 0x402B:  # jmp @Rn
        return ("jmp", f"@{r[n]}", ann)
    if op & 0xF0FF == 0x0003:  # bsrf Rn: PC <- PC+4+Rn (register-relative, no disp)
        return ("bsrf", r[n], ann)
    if op & 0xF0FF == 0x0023:  # braf Rn: PC <- PC+4+Rn
        return ("braf", r[n], ann)
    if n0 == 0xA:  # bra disp (12-bit signed)
        d = op & 0xFFF
        d -= 0x1000 if d & 0x800 else 0
        target = pc + 4 + d * 2
        return ("bra", f"0x{target:05X}", ann)
    if n0 == 0xB:  # bsr disp
        d = op & 0xFFF
        d -= 0x1000 if d & 0x800 else 0
        target = pc + 4 + d * 2
        return ("bsr", f"0x{target:05X}", ann)

    # ---- Immediate loads ----
    if n0 == 0xE:
        return ("mov", f"#0x{s8(lo)&0xFF:02X},{r[n]}", ann)
    if n0 == 0x9:
        # mov.w @(disp,PC) — emit absolute target so GNU-as / rom_rebuild
        # label substitution round-trips (disp = target-(pc+4), field = disp/2)
        tgt = pc + 4 + lo * 2
        if rd16:
            val = rd16(tgt)
            ann = f" ; 0x{val:04X}"
        return ("mov.w", f"0x{tgt:05X},{r[n]}", ann)
    if n0 == 0xD:
        # mov.l @(disp,PC)
        addr = ((pc + 4) & ~3) + lo * 4
        if rd32:
            val = rd32(addr)
            if val & 0x80000000:
                try:
                    fval = struct.unpack('>f', struct.pack('>I', val & MASK))[0]
                    ann = f" ; 0x{val:08X} = {fval}"
                except:
                    ann = f" ; 0x{val:08X}"
            else:
                ann = f" ; 0x{val:08X}"
        return ("mov.l", f"0x{addr:05X},{r[n]}", ann)
    if op & 0xFF00 == 0xC700:
        # mova @(disp,PC),R0
        addr = ((pc + 4) & ~3) + lo * 4
        return ("mova", f"0x{addr:05X},{r[0]}", ann)

    # ---- n0 == 0x8: conditionals & short load/store ----
    if n0 == 0x8:
        if op & 0xFF00 == 0x8800:
            return ("cmp/eq", f"#0x{s8(lo)&0xFF:02X},{r[0]}", ann)
        if op & 0xFF00 == 0x8D00:
            d = s8(lo) * 2
            return ("bt/s", f"0x{pc+4+d:05X}", ann)
        if op & 0xFF00 == 0x8F00:
            d = s8(lo) * 2
            return ("bf/s", f"0x{pc+4+d:05X}", ann)
        if op & 0xFF00 == 0x8B00:
            d = s8(lo) * 2
            return ("bf", f"0x{pc+4+d:05X}", ann)
        if op & 0xFF00 == 0x8900:
            d = s8(lo) * 2
            return ("bt", f"0x{pc+4+d:05X}", ann)
        if op & 0xFF00 == 0x8000:
            return ("mov.b", f"r0,@(0x{op&0xF:02X},{r[m]})", ann)
        if op & 0xFF00 == 0x8100:
            return ("mov.w", f"r0,@(0x{(op&0xF)*2:02X},{r[m]})", ann)
        if op & 0xFF00 == 0x8200:
            return ("mov.l", f"r0,@(0x{(op&0xF)*4:02X},{r[m]})", ann)
        if op & 0xFF00 == 0x8400:
            return ("mov.b", f"@(0x{op&0xF:02X},{r[m]}),r0", ann)
        if op & 0xFF00 == 0x8500:
            return ("mov.w", f"@(0x{(op&0xF)*2:02X},{r[m]}),r0", ann)
        if op & 0xFF00 == 0x8600:
            return ("mov.l", f"@(0x{(op&0xF)*4:02X},{r[m]}),r0", ann)
    # ---- n0 == 0xC: GBR-relative, TST/AND/XOR/OR #imm,R0, bit ops ----
    if n0 == 0xC:
        # Correct SH-2E semantics (GNU-as verified):
        #   0xC0/0xC1/0xC2 = MOV.B/W/L R0,@(disp,GBR)   (STORE)
        #   0xC4/0xC5/0xC6 = MOV.B/W/L @(disp,GBR),R0   (LOAD)
        # disp field is BYTES for .b, bytes/2 for .w, bytes/4 for .l
        t = (op >> 8) & 0xF
        imm = op & 0xFF
        if t == 0x0:
            return ("mov.b", f"r0,@(0x{imm:02X},gbr)", ann)
        if t == 0x1:
            return ("mov.w", f"r0,@(0x{imm*2:02X},gbr)", ann)
        if t == 0x2:
            return ("mov.l", f"r0,@(0x{imm*4:02X},gbr)", ann)
        if t == 0x3:
            return ("trapa", f"#0x{imm:02X}", ann)
        if t == 0x4:
            return ("mov.b", f"@(0x{imm:02X},gbr),r0", ann)
        if t == 0x5:
            return ("mov.w", f"@(0x{imm*2:02X},gbr),r0", ann)
        if t == 0x6:
            return ("mov.l", f"@(0x{imm*4:02X},gbr),r0", ann)
        # t == 0x7 (mova @(disp,PC),R0) handled above
        if t == 0x8:
            return ("tst", f"#0x{imm:02X},{r[0]}", ann)
        if t == 0x9:
            return ("and", f"#0x{imm:02X},{r[0]}", ann)
        if t == 0xA:
            return ("xor", f"#0x{imm:02X},{r[0]}", ann)
        if t == 0xB:
            return ("or", f"#0x{imm:02X},{r[0]}", ann)
        if t == 0xC:
            return ("tst.b", f"#0x{imm:02X},@(r0,gbr)", ann)
        if t == 0xD:
            return ("and.b", f"#0x{imm:02X},@(r0,gbr)", ann)
        if t == 0xE:
            return ("xor.b", f"#0x{imm:02X},@(r0,gbr)", ann)
        if t == 0xF:
            return ("or.b", f"#0x{imm:02X},@(r0,gbr)", ann)

    # ---- n0 == 0x6: reg-reg movs, extensions, loads ----
    if n0 == 0x6:
        if nib == 0x3:
            return ("mov", f"{r[m]},{r[n]}", ann)
        if nib == 0xC:
            return ("extu.b", f"{r[m]},{r[n]}", ann)
        if nib == 0xD:
            return ("extu.w", f"{r[m]},{r[n]}", ann)
        if nib == 0xE:
            return ("exts.b", f"{r[m]},{r[n]}", ann)
        if nib == 0xF:
            return ("exts.w", f"{r[m]},{r[n]}", ann)
        if nib == 0x0:
            return ("mov.b", f"@{r[m]},{r[n]}", ann)
        if nib == 0x1:
            return ("mov.w", f"@{r[m]},{r[n]}", ann)
        if nib == 0x2:
            return ("mov.l", f"@{r[m]},{r[n]}", ann)
        if nib == 0x4:
            return ("mov.b", f"@{r[m]}+,{r[n]}", ann)
        if nib == 0x5:
            return ("mov.w", f"@{r[m]}+,{r[n]}", ann)
        if nib == 0x6:
            return ("mov.l", f"@{r[m]}+,{r[n]}", ann)
        if nib == 0x7:
            return ("not", f"{r[m]},{r[n]}", ann)
        if nib == 0xB:
            return ("neg", f"{r[m]},{r[n]}", ann)
        if nib == 0x8:
            return ("swap.b", f"{r[m]},{r[n]}", ann)
        if nib == 0x9:
            return ("swap.w", f"{r[m]},{r[n]}", ann)
        if nib == 0xA:
            return ("negc", f"{r[m]},{r[n]}", ann)

    # ---- n0 == 0x2: stores and ALU ----
    if n0 == 0x2:
        if nib == 0x0:
            return ("mov.b", f"{r[m]},@{r[n]}", ann)
        if nib == 0x1:
            return ("mov.w", f"{r[m]},@{r[n]}", ann)
        if nib == 0x2:
            return ("mov.l", f"{r[m]},@{r[n]}", ann)
        if nib == 0x4:
            return ("mov.b", f"{r[m]},@-{r[n]}", ann)
        if nib == 0x5:
            return ("mov.w", f"{r[m]},@-{r[n]}", ann)
        if nib == 0x6:
            return ("mov.l", f"{r[m]},@-{r[n]}", ann)
        if nib == 0x7:
            return ("div0s", f"{r[m]},{r[n]}", ann)
        if nib == 0x8:
            return ("tst", f"{r[m]},{r[n]}", ann)
        if nib == 0x9:
            return ("and", f"{r[m]},{r[n]}", ann)
        if nib == 0xA:
            return ("xor", f"{r[m]},{r[n]}", ann)
        if nib == 0xB:
            return ("or", f"{r[m]},{r[n]}", ann)
        if nib == 0xC:
            return ("cmp/str", f"{r[m]},{r[n]}", ann)
        if nib == 0xD:
            return ("xtrct", f"{r[m]},{r[n]}", ann)
        if nib == 0xF:
            return ("muls.w", f"{r[m]},{r[n]}", ann)
        if nib == 0xE:
            return ("mulu.w", f"{r[m]},{r[n]}", ann)

    # ---- n0 == 0x3: add/sub/cmp ----
    if n0 == 0x3:
        if nib == 0x4:
            return ("div1", f"{r[m]},{r[n]}", ann)
        if nib == 0xC:
            return ("add", f"{r[m]},{r[n]}", ann)
        if nib == 0x8:
            return ("sub", f"{r[m]},{r[n]}", ann)
        if nib == 0x0:
            return ("cmp/eq", f"{r[m]},{r[n]}", ann)
        if nib == 0x2:
            return ("cmp/hs", f"{r[m]},{r[n]}", ann)
        if nib == 0x3:
            return ("cmp/ge", f"{r[m]},{r[n]}", ann)
        if nib == 0x6:
            return ("cmp/hi", f"{r[m]},{r[n]}", ann)
        if nib == 0x7:
            return ("cmp/gt", f"{r[m]},{r[n]}", ann)
        if nib == 0xE:
            return ("addc", f"{r[m]},{r[n]}", ann)
        if nib == 0xA:
            return ("subc", f"{r[m]},{r[n]}", ann)
        if nib == 0xF:
            return ("addv", f"{r[m]},{r[n]}", ann)
        if nib == 0xB:
            return ("subv", f"{r[m]},{r[n]}", ann)
        if nib == 0xD:
            return ("dmuls.l", f"{r[m]},{r[n]}", ann)
        if nib == 0x5:
            return ("dmulu.l", f"{r[m]},{r[n]}", ann)

    # ---- n0 == 0x7: add #imm,Rn ----
    if n0 == 0x7:
        return ("add", f"#0x{s8(lo)&0xFF:02X},{r[n]}", ann)

    # ---- n0 == 0x5: mov.l @(disp,Rm),Rn ----
    if n0 == 0x5:
        return ("mov.l", f"@(0x{nib*4:X},{r[m]}),{r[n]}", ann)

    # ---- n0 == 0x1: mov.l Rm,@(disp,Rn) ----
    if n0 == 0x1:
        return ("mov.l", f"{r[m]},@(0x{nib*4:X},{r[n]})", ann)

    # ---- n0 == 0x0: sts, lds, @(R0,Rm) loads ----
    if n0 == 0x0:
        if nib == 0x7:
            return ("mul.l", f"{r[m]},{r[n]}", ann)
        if op & 0xF00F == 0x000F:
            return ("mac.l", f"@{r[m]}+,@{r[n]}+", ann)
        if op & 0xF0FF == 0x000A:
            return ("sts", f"mach,{r[n]}", ann)
        if op & 0xF0FF == 0x001A:
            return ("sts", f"macl,{r[n]}", ann)
        if op & 0xF0FF == 0x002A:
            return ("sts", f"pr,{r[n]}", ann)
        if op & 0xF0FF == 0x005A:
            return ("sts", f"fpul,{r[n]}", ann)
        if op & 0xF0FF == 0x006A:
            return ("sts", f"fpscr,{r[n]}", ann)
        if op & 0xF0FF == 0x0002:
            return ("stc", f"SR,{r[n]}", ann)
        if op & 0xF0FF == 0x0012:
            return ("stc", f"GBR,{r[n]}", ann)
        if op & 0xF0FF == 0x0022:
            return ("stc", f"VBR,{r[n]}", ann)
        if op & 0xF0FF == 0x0032:
            return ("stc", f"SSR,{r[n]}", ann)
        if op & 0xF0FF == 0x0042:
            return ("stc", f"SPC,{r[n]}", ann)
        if op & 0xF00F == 0x0004:
            return ("mov.b", f"{r[m]},@(r0,{r[n]})", ann)
        if op & 0xF00F == 0x0005:
            return ("mov.w", f"{r[m]},@(r0,{r[n]})", ann)
        if op & 0xF00F == 0x0006:
            return ("mov.l", f"{r[m]},@(r0,{r[n]})", ann)
        if op & 0xF00F == 0x000C:
            return ("mov.b", f"@(r0,{r[m]}),{r[n]}", ann)
        if op & 0xF00F == 0x000D:
            return ("mov.w", f"@(r0,{r[m]}),{r[n]}", ann)
        if op & 0xF00F == 0x000E:
            return ("mov.l", f"@(r0,{r[m]}),{r[n]}", ann)

    # ---- n0 == 0x4: shifts, rotates, lds/sts specials ----
    if n0 == 0x4:
        if op & 0xF0FF == 0x4000:
            return ("shll", r[n], ann)
        if op & 0xF0FF == 0x4001:
            return ("shlr", r[n], ann)
        if op & 0xF0FF == 0x4008:
            return ("shll2", r[n], ann)
        if op & 0xF0FF == 0x4009:
            return ("shlr2", r[n], ann)
        if op & 0xF0FF == 0x4018:
            return ("shll8", r[n], ann)
        if op & 0xF0FF == 0x4019:
            return ("shlr8", r[n], ann)
        if op & 0xF0FF == 0x4028:
            return ("shll16", r[n], ann)
        if op & 0xF0FF == 0x4029:
            return ("shlr16", r[n], ann)
        if op & 0xF0FF == 0x4021:
            return ("shar", r[n], ann)
        if op & 0xF0FF == 0x4020:
            return ("shal", r[n], ann)
        if op & 0xF0FF == 0x4010:
            return ("dt", r[n], ann)
        if op & 0xF0FF == 0x4025:
            return ("rotcr", r[n], ann)
        if op & 0xF0FF == 0x4024:
            return ("rotcl", r[n], ann)
        if op & 0xF0FF == 0x4004:
            return ("rotl", r[n], ann)
        if op & 0xF0FF == 0x4005:
            return ("rotr", r[n], ann)
        if op & 0xF0FF == 0x4011:
            return ("cmp/pz", r[n], ann)
        if op & 0xF0FF == 0x4015:
            return ("cmp/pl", r[n], ann)
        if op & 0xF0FF == 0x400A:
            return ("lds", f"{r[n]},mach", ann)
        if op & 0xF0FF == 0x401A:
            return ("lds", f"{r[n]},macl", ann)
        if op & 0xF0FF == 0x402A:
            return ("lds", f"{r[n]},pr", ann)
        if op & 0xF0FF == 0x4022:
            return ("sts.l", f"pr,@-{r[n]}", ann)
        if op & 0xF0FF == 0x4026:
            return ("lds.l", f"@{r[n]}+,pr", ann)
        if op & 0xF0FF == 0x4012:
            return ("sts.l", f"macl,@-{r[n]}", ann)
        if op & 0xF0FF == 0x4002:
            return ("sts.l", f"mach,@-{r[n]}", ann)
        if op & 0xF0FF == 0x4016:
            return ("lds.l", f"@{r[n]}+,macl", ann)
        if op & 0xF0FF == 0x4006:
            return ("lds.l", f"@{r[n]}+,mach", ann)
        if op & 0xF00F == 0x400F:
            return ("mac.w", f"@{r[m]}+,@{r[n]}+", ann)
        if op & 0xF0FF == 0x401B:
            return ("tas.b", f"@{r[n]}", ann)
        if op & 0xF0FF == 0x405A:
            return ("lds", f"{r[n]},fpul", ann)
        if op & 0xF0FF == 0x406A:
            return ("lds", f"{r[n]},fpscr", ann)
        if op & 0xF0FF == 0x4056:
            return ("lds.l", f"@{r[n]}+,fpul", ann)
        if op & 0xF0FF == 0x4066:
            return ("lds.l", f"@{r[n]}+,fpscr", ann)
        if op & 0xF0FF == 0x4052:
            return ("sts.l", f"fpul,@-{r[n]}", ann)
        if op & 0xF0FF == 0x4062:
            return ("sts.l", f"fpscr,@-{r[n]}", ann)
        if op & 0xF0FF == 0x4003:
            return ("stc.l", f"SR,@-{r[n]}", ann)
        if op & 0xF0FF == 0x4013:
            return ("stc.l", f"GBR,@-{r[n]}", ann)
        if op & 0xF0FF == 0x4023:
            return ("stc.l", f"VBR,@-{r[n]}", ann)
        if op & 0xF0FF == 0x4033:
            return ("stc.l", f"SSR,@-{r[n]}", ann)
        if op & 0xF0FF == 0x4043:
            return ("stc.l", f"SPC,@-{r[n]}", ann)
        if op & 0xF0FF == 0x400E:
            return ("ldc", f"{r[n]},SR", ann)
        if op & 0xF0FF == 0x401E:
            return ("ldc", f"{r[n]},GBR", ann)
        if op & 0xF0FF == 0x402E:
            return ("ldc", f"{r[n]},VBR", ann)
        if op & 0xF0FF == 0x403E:
            return ("ldc", f"{r[n]},SSR", ann)
        if op & 0xF0FF == 0x404E:
            return ("ldc", f"{r[n]},SPC", ann)
        if op & 0xF0FF == 0x4007:
            return ("ldc.l", f"@{r[n]}+,SR", ann)
        if op & 0xF0FF == 0x4017:
            return ("ldc.l", f"@{r[n]}+,GBR", ann)
        if op & 0xF0FF == 0x4027:
            return ("ldc.l", f"@{r[n]}+,VBR", ann)
        if op & 0xF0FF == 0x4037:
            return ("ldc.l", f"@{r[n]}+,SSR", ann)
        if op & 0xF0FF == 0x4047:
            return ("ldc.l", f"@{r[n]}+,SPC", ann)

    return (f"unknown", f"0x{op:04X}", ann)


def disasm_range(rom, start, length, base=0):
    """Disassemble a range of ROM bytes starting at `start` offset (relative to base addr)."""
    lines = []
    i = 0
    while i < length:
        addr = start + i
        op = struct.unpack('>H', rom[addr:addr + 2])[0]

        def rd16(a):
            if a >= base and a - base < len(rom):
                return struct.unpack('>H', rom[a - base:a - base + 2])[0]
            return 0

        def rd32(a):
            if a >= base and a - base + 4 <= len(rom):
                return struct.unpack('>I', rom[a - base:a - base + 4])[0]
            return 0

        mne, ops, ann = disasm_one(op, addr, rd16=rd16, rd32=rd32)
        a = ann and f"  {ann}" or ""
        lines.append(f"  0x{addr:04X}:  {op:04X}    {mne:12s} {ops}{a}")
        i += 2
    return lines


if __name__ == '__main__':
    import os

    if len(sys.argv) > 1:
        addr = int(sys.argv[1], 0)
        length = int(sys.argv[2], 0) if len(sys.argv) > 2 else 64
        rom_name = sys.argv[3] if len(sys.argv) > 3 else '60E0FC00.bin'
    else:
        print("Usage: disasm_sh2e.py <hex_addr> [length=64] [rom_name=60E0FC00.bin]")
        print("Example: disasm_sh2e.py 0x23B0 44 60E0FC00.bin")
        sys.exit(1)

    # Search for ROM in stock dirs, build dirs
    for d in ['../roms/stock', 'build', '.']:
        p = os.path.join(os.path.dirname(__file__), d, rom_name)
        if os.path.exists(p):
            rom_path = p
            break
    else:
        print(f"ROM not found: {rom_name}")
        sys.exit(1)

    rom = open(rom_path, 'rb').read()
    lines = disasm_range(rom, addr, length, base=0)
    for l in lines:
        print(l)
