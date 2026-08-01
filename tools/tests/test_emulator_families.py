#!/usr/bin/env python3
"""
tools/tests/test_emulator_families.py — regression tests for the SH-2E EMULATOR
(tools/sh2emu.py): every opcode family that used to raise NotImplementedError
(the 9 decode-gap families plus the control-register/selector forms they pull
in), EXECUTED rather than disassembled.

All opcodes below were round-tripped through GNU-as 2.46 (sh-elf-as -big, from
tools/get_toolchain.sh); the canonical encodings also appear in
tools/tests/test_decode_families.py.  The div1 model is additionally validated
end-to-end by running the ROM's signed-division routine @0x3FE8 in the BASE
emulator (no subclass) against golden vectors, including the INT32_MIN/MAX
edge cases and the div-by-zero diag-code write.

Run from repo root:
    python3 tools/tests/test_emulator_families.py [N]     # N = random div cases (default 2000)
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, MASK

ROM_CANDIDATES = [
    os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin'),
    os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin'),
]
ROM = next((p for p in ROM_CANDIDATES if os.path.exists(p)), None)
DIV_ENTRY = 0x003FE8          # div32_signed(divisor r0, dividend r1) -> r0

FAILS = []
CHECKS = [0]


def check(cond, msg):
    CHECKS[0] += 1
    if not cond:
        FAILS.append(msg)
        print("FAIL: " + msg)


def sub(seq, regs=None, ram=None, sr=0x000000F0):
    """Run the 16-bit word sequence in a fresh base SH2 from pc=0 until rts
    returns to SENT (or pc hits SENT).  Returns the cpu for state inspection."""
    buf = bytearray()
    for w in seq + [0x0009, 0x0009]:   # pad: the delay slot after a trailing rts
        buf += bytes(((w >> 8) & 0xFF, w & 0xFF))
    cpu = SH2(bytes(buf))
    cpu.ram = dict(ram or {})
    cpu.r = [0] * 16
    for k, v in (regs or {}).items():
        cpu.r[k] = v & MASK
    cpu.r[15] = 0xFFFFDF00
    cpu.fr = [0.0] * 16
    cpu.pr = cpu.SENT
    cpu.T = 0
    cpu.macl = 0; cpu.mach = 0; cpu.gbr = 0; cpu.sr = sr & MASK
    cpu.vbr = 0; cpu.ssr = 0; cpu.spc = 0
    cpu.fpul = 0; cpu.fpscr = 0
    cpu._Q = (cpu.sr >> 3) & 1; cpu._M = (cpu.sr >> 2) & 1
    cpu.pc = 0
    steps = 0
    while True:
        if cpu.pc == cpu.SENT:
            return cpu
        steps += 1
        if steps > 500000:
            raise RuntimeError("runaway at 0x%X" % cpu.pc)
        op = cpu.rd(cpu.pc, 2)
        br = cpu._delayed(op)
        if br is None:
            cpu._exec(op, cpu.pc)
            cpu.pc = (cpu.pc + 2) & MASK
        else:
            target, take = br
            cpu._exec(cpu.rd(cpu.pc + 2, 2), cpu.pc + 2)
            cpu.pc = target if take else (cpu.pc + 4) & MASK


def r0(cpu):
    return cpu.r[0]


def l32(ram, a):
    return (ram.get(a, 0) << 24) | (ram.get(a + 1, 0) << 16) | \
           (ram.get(a + 2, 0) << 8) | ram.get(a + 3, 0)


# ---------------------------------------------------------------------------
# 1. GBR-relative MOV — direction AND displacement (the old 0xF0FF/disp==0 bug)
# ---------------------------------------------------------------------------
def test_gbr_mov():
    # stores: mov.b R0,@(0x5,GBR); mov.w R0,@(0xA,GBR); mov.l R0,@(0xC,GBR)
    cpu = sub([0x411E,              # ldc r1,GBR
               0xE07F,              # mov #0x7F,r0
               0xC005,              # mov.b r0,@(0x5,gbr)
               0x000B], regs={1: 0x1000})
    check(cpu.ram.get(0x1005) == 0x7F, "GBR mov.b store wrote wrong byte")

    cpu = sub([0x411E,
               0x9001,              # mov.w @(1,pc),r0 -> 0xFFFF8020 (pc=2: 2+4+2=8)
               0xC105,              # mov.w r0,@(0xA,gbr)
               0x000B, 0x8020], regs={1: 0x1000})
    check(cpu.ram.get(0x100A) == 0x80 and cpu.ram.get(0x100B) == 0x20,
          "GBR mov.w store wrote wrong bytes")

    cpu = sub([0x411E,
               0xD001,              # mov.l @(1,pc),r0 -> 0x12345678 (pc=2: (6&~3)+4=8)
               0xC203,              # mov.l r0,@(0xC,gbr)
               0x000B, 0x1234, 0x5678], regs={1: 0x1000})
    check(l32(cpu.ram, 0x100C) == 0x12345678, "GBR mov.l store wrote wrong dword")

    # loads: sign-extended byte, sign-extended word, plain long
    cpu = sub([0x411E, 0xC403, 0x000B], regs={1: 0x1000}, ram={0x1003: 0xFF})
    check(r0(cpu) == 0xFFFFFFFF, "GBR mov.b load not sign-extended")
    cpu = sub([0x411E, 0xC501, 0x000B], regs={1: 0x1000}, ram={0x1002: 0x00, 0x1003: 0xFF})
    check(r0(cpu) == 0x000000FF, "GBR mov.w load not sign-extended")
    cpu = sub([0x411E, 0xC601, 0x000B], regs={1: 0x1000},
              ram={0x1004: 0x12, 0x1005: 0x34, 0x1006: 0x56, 0x1007: 0x78})
    check(r0(cpu) == 0x12345678, "GBR mov.l load wrong value")


# ---------------------------------------------------------------------------
# 2. mov.l R0,@(disp,Rm) / mov.l @(disp,Rm),R0  (0x82xx / 0x86xx)
# ---------------------------------------------------------------------------
def test_movl_disp_r0():
    cpu = sub([0x828C, 0x000B], regs={8: 0x2000, 0: 0x11223344})
    check(l32(cpu.ram, 0x2030) == 0x11223344, "mov.l r0,@(0x30,r8) wrong")
    cpu = sub([0x8614, 0x000B], regs={1: 0x3000},
              ram={0x3010: 0xDE, 0x3011: 0xAD, 0x3012: 0xBE, 0x3013: 0xEF})
    check(r0(cpu) == 0xDEADBEEF, "mov.l @(0x10,r1),r0 wrong")


# ---------------------------------------------------------------------------
# 3. div0s / div0u / div1 — raw flag behaviour
# ---------------------------------------------------------------------------
def test_div_flags():
    # div0s r3,r4 (0x2nm7): Q=MSB(Rn=r4), M=MSB(Rm=r3), T=Q^M
    cpu = sub([0x2437, 0x0329, 0x000B], regs={3: 0x80000000, 4: 0x00000001})  # div0s; movt r3
    check(cpu._Q == 0 and cpu._M == 1 and cpu.T == 1 and cpu.r[3] == 1,
          "div0s flags wrong (Q=%d M=%d T=%d)" % (cpu._Q, cpu._M, cpu.T))

    # one div1 step (0x3nm4) in the Q==M (subtract) case, divisor in Rm:
    #   div0s r3,r4 (Q=1,M=1,T=0); div1 r3,r4:
    #   r4 = (0x80000000<<1)|0 = 0; subtract Rm: 0 - 0x80000000 = 0x80000000;
    #   t1 = (0xFFFFFFFF+0)&1 ^ MSB(r4)_old(1) = 0 -> T=1, Q = M^0 = 1
    cpu = sub([0x2437, 0x3434, 0x000B], regs={3: 0x80000000, 4: 0x80000000})
    check(cpu.r[4] == 0x80000000 and cpu._Q == 1 and cpu._M == 1 and cpu.T == 1,
          "div1 Q==M step wrong (r4=0x%08X Q=%d M=%d T=%d)"
          % (cpu.r[4], cpu._Q, cpu._M, cpu.T))

    # div0u clears M,Q,T
    cpu = sub([0x0019, 0x0329, 0x000B], regs={0: 0x80000000})  # div0u; movt r3
    check(cpu._Q == 0 and cpu._M == 0 and cpu.T == 0 and cpu.r[3] == 0,
          "div0u did not clear M/Q/T")

    # movt: T -> r3  (movt rN = 0x0n29)
    cpu = sub([0x0018, 0x0329, 0x000B])   # sett; movt r3
    check(cpu.r[3] == 1, "movt with T=1 wrong")
    cpu = sub([0x0008, 0x0329, 0x000B])   # clrt; movt r3
    check(cpu.r[3] == 0, "movt with T=0 wrong")


def ref_quot(divisor, dividend):
    """C99-style truncating signed division (the ROM loop's semantics)."""
    d = divisor - (1 << 32) if divisor & 0x80000000 else divisor
    v = dividend - (1 << 32) if dividend & 0x80000000 else dividend
    if d == 0:
        return 0
    q = abs(v) // abs(d)
    if (v < 0) != (d < 0):
        q = -q
    return q & 0xFFFFFFFF


def test_div32_rom(N):
    """Run the ACTUAL ROM routine @0x3FE8 in the BASE emulator."""
    if ROM is None:
        print("  SKIP ROM div32: ROM not found")
        return
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    def call_div(divisor, dividend):
        return sub_wrap(cpu, divisor, dividend)

    edges = [
        (1, 0), (1, 1), (2, 5), (5, 17), (7, 100),
        (7, 0xFFFFFF9C),                # -100 / 7 = -14
        (0xFFFFFFFF, 0xFFFFFFFF),       # -1 / -1 = 1
        (0xFFFFFFFF, 0x00000001),       # -1 / 1 = -1
        (0x00000001, 0xFFFFFFFF),       # 1 / -1 = -1
        (0xFFFFFFFF, 0x80000000),       # INT32_MIN / -1 -> wraps to INT32_MIN
        (0x80000000, 0x40000000),       # 2^30 / -2^31 = 0
        (0x7FFFFFFF, 0x7FFFFFFF),       # 1
        (0x80000000, 0x80000000),       # 1
        (0x80000000, 1),                # 1 / -2^31 = 0
        (0x7FFFFFFF, 0x80000000),       # INT32_MIN / INT32_MAX = -1
    ]
    for divisor, dividend in edges:
        got = call_div(divisor, dividend)
        exp = ref_quot(divisor, dividend)
        check(got == exp, "ROM div32 edge %d/%d -> 0x%08X expected 0x%08X"
              % (divisor - (1 << 32) if divisor & 0x80000000 else divisor,
                 dividend - (1 << 32) if dividend & 0x80000000 else dividend,
                 got, exp))

    # div-by-zero: returns 0 and writes diag code 0x44E to 0xFFFF7304
    got = call_div(0, 100)
    check(got == 0, "ROM div32 div-by-zero returned 0x%08X" % got)
    check(l32(cpu.ram, 0xFFFF7304) == 0x44E,
          "ROM div32 div-by-zero diag code wrong: 0x%08X" % l32(cpu.ram, 0xFFFF7304))

    rnd = random.Random(0x5EED)
    bad = 0
    for _ in range(N):
        divisor = rnd.randint(0, 0xFFFFFFFF)
        dividend = rnd.randint(0, 0xFFFFFFFF)
        if divisor == 0:
            continue
        got = call_div(divisor, dividend)
        exp = ref_quot(divisor, dividend)
        if got != exp:
            bad += 1
            if bad <= 3:
                print("  ROM div32 random mismatch: %d/%d -> 0x%08X exp 0x%08X"
                      % (signed(divisor), signed(dividend), got, exp))
    check(bad == 0, "ROM div32 random: %d mismatches out of %d" % (bad, N))


def signed(x):
    return x - (1 << 32) if x & 0x80000000 else x


def sub_wrap(cpu, divisor, dividend):
    """Re-arm cpu and call DIV_ENTRY with r0=divisor, r1=dividend."""
    cpu.ram = {}
    cpu.r = [0] * 16
    cpu.r[0] = divisor & MASK
    cpu.r[1] = dividend & MASK
    cpu.r[15] = 0xFFFFDF00
    cpu.fr = [0.0] * 16
    cpu.pr = cpu.SENT; cpu.T = 0
    cpu.macl = 0; cpu.mach = 0; cpu.gbr = 0; cpu.sr = 0x000000F0
    cpu.vbr = 0; cpu.ssr = 0; cpu.spc = 0
    cpu.fpul = 0; cpu.fpscr = 0
    cpu._Q = 0; cpu._M = 0
    cpu.pc = DIV_ENTRY
    steps = 0
    while True:
        if cpu.pc == cpu.SENT:
            return cpu.r[0] & MASK
        steps += 1
        if steps > 500000:
            raise RuntimeError("runaway at 0x%X" % cpu.pc)
        op = cpu.rd(cpu.pc, 2)
        br = cpu._delayed(op)
        if br is None:
            cpu._exec(op, cpu.pc)
            cpu.pc = (cpu.pc + 2) & MASK
        else:
            target, take = br
            cpu._exec(cpu.rd(cpu.pc + 2, 2), cpu.pc + 2)
            cpu.pc = target if take else (cpu.pc + 4) & MASK


# ---------------------------------------------------------------------------
# 4. cmp/str
# ---------------------------------------------------------------------------
def test_cmp_str():
    for regs, exp in [
        ({2: 0x11223344, 3: 0x11223344}, 1),   # all 4 bytes equal
        ({2: 0x11223344, 3: 0xAABBCCDD}, 0),   # no byte equal
        ({2: 0x11223344, 3: 0x11000000}, 1),   # top byte equal
        ({2: 0x11223344, 3: 0x00000044}, 1),   # low byte equal
    ]:
        cpu = sub([0x223C, 0x000B], regs=regs)   # cmp/str r3,r2
        check(cpu.T == exp, "cmp/str r3,r2 regs=%r -> T=%d expected %d"
              % (regs, cpu.T, exp))


# ---------------------------------------------------------------------------
# 5. mac.l / mac.w (accumulation, post-increment, S-bit saturation)
# ---------------------------------------------------------------------------
def test_mac():
    # mac.l @r1+,@r4+ twice: 2*3 + 5*7 = 41
    cpu = sub([0x014F, 0x014F, 0x001A, 0x000B],
              regs={1: 0x1000, 4: 0x2000},
              ram={0x1000: 0x00, 0x1001: 0x00, 0x1002: 0x00, 0x1003: 0x02,
                   0x1004: 0x00, 0x1005: 0x00, 0x1006: 0x00, 0x1007: 0x05,
                   0x2000: 0x00, 0x2001: 0x00, 0x2002: 0x00, 0x2003: 0x03,
                   0x2004: 0x00, 0x2005: 0x00, 0x2006: 0x00, 0x2007: 0x07})
    check(r0(cpu) == 41, "mac.l accumulate wrong: %d" % r0(cpu))
    check(cpu.r[1] == 0x1008 and cpu.r[4] == 0x2008,
          "mac.l post-increment wrong: r1=0x%X r4=0x%X" % (cpu.r[1], cpu.r[4]))
    check(cpu.mach == 0, "mac.l mach should be 0")

    # mac.w @r4+,@r0+ x4 with 0x7FFF*0x7FFF products:
    #   no S: wraps in 32 bits -> 4 * 0x3FFF0001 = 0xFFFC0004
    #   S set: saturates at 0x7FFFFFFF
    ram = {}
    for a in (0x1000, 0x1002, 0x1004, 0x1006, 0x2000, 0x2002, 0x2004, 0x2006):
        ram[a] = 0x7F
        ram[a + 1] = 0xFF
    seq = [0x404F, 0x404F, 0x404F, 0x404F, 0x001A, 0x000B]
    cpu = sub(seq, regs={0: 0x1000, 4: 0x2000}, ram=ram)
    check(r0(cpu) == 0xFFFC0004, "mac.w wrap wrong: 0x%08X" % r0(cpu))
    cpu = sub(seq, regs={0: 0x1000, 4: 0x2000}, ram=ram, sr=0x000000F2)
    check(r0(cpu) == 0x7FFFFFFF, "mac.w S-saturation wrong: 0x%08X" % r0(cpu))


# ---------------------------------------------------------------------------
# 6. control registers: vbr / ssr / spc  (register + memory forms)
# ---------------------------------------------------------------------------
def test_ctrl_regs():
    for ldc, stcl, ldcl, stc in [        # (ldc Rn,X, stc.l X,@-Rn, ldc.l @Rn+,X, stc X,Rn)
        (0x412E, 0x4523, 0x4527, 0x0022),  # vbr
        (0x413E, 0x4533, 0x4537, 0x0032),  # ssr
        (0x414E, 0x4543, 0x4547, 0x0042),  # spc
    ]:
        cpu = sub([ldc, 0xE510, stcl, ldcl, stc, 0x000B], regs={1: 0x11223344})
        check(r0(cpu) == 0x11223344,
              "ctrl reg 0x%04X roundtrip wrong: 0x%08X" % (ldc, r0(cpu)))


# ---------------------------------------------------------------------------
# 7. fpul / fpscr memory forms (0x4n52/56/62/66 — fixed)
# ---------------------------------------------------------------------------
def test_fpul_fpscr_mem():
    cpu = sub([0x416A, 0xE530, 0x4562, 0x4566, 0x006A, 0x000B], regs={1: 0x11223344})
    check(r0(cpu) == 0x11223344, "sts.l/lds.l fpscr roundtrip wrong: 0x%08X" % r0(cpu))
    cpu = sub([0x415A, 0xE530, 0x4552, 0x4556, 0x005A, 0x000B], regs={1: 0x11223344})
    check(r0(cpu) == 0x11223344, "sts.l/lds.l fpul roundtrip wrong: 0x%08X" % r0(cpu))


# ---------------------------------------------------------------------------
# 8. negc / xtrct / addc / subc / addv / subv
# ---------------------------------------------------------------------------
def test_arith():
    cpu = sub([0x640A, 0x000B], regs={0: 0})
    check(cpu.r[4] == 0 and cpu.T == 0, "negc 0 -> wrong")
    cpu = sub([0x0018, 0x640A, 0x000B], regs={0: 0})
    check(cpu.r[4] == 0xFFFFFFFF and cpu.T == 1, "negc 0 (T=1) -> wrong")
    cpu = sub([0x640A, 0x000B], regs={0: 0x80000000})
    check(cpu.r[4] == 0x80000000 and cpu.T == 1, "negc 0x80000000 -> wrong")

    cpu = sub([0x240D, 0x000B], regs={0: 0x12345678, 4: 0xAABBCCDD})
    check(cpu.r[4] == 0xCCDD1234, "xtrct wrong: 0x%08X" % cpu.r[4])

    cpu = sub([0x340E, 0x000B], regs={0: 1, 4: 0xFFFFFFFF})
    check(cpu.r[4] == 0 and cpu.T == 1, "addc carry wrong")
    cpu = sub([0x0018, 0x340E, 0x000B], regs={0: 1, 4: 0xFFFFFFFE})
    check(cpu.r[4] == 0 and cpu.T == 1, "addc with T=1 wrong")

    cpu = sub([0x340A, 0x000B], regs={0: 1, 4: 0})
    check(cpu.r[4] == 0xFFFFFFFF and cpu.T == 1, "subc borrow wrong")

    cpu = sub([0x340F, 0x000B], regs={0: 1, 4: 0x7FFFFFFF})
    check(cpu.r[4] == 0x80000000 and cpu.T == 1, "addv overflow not flagged")
    cpu = sub([0x340F, 0x000B], regs={0: 1, 4: 0x40000000})
    check(cpu.r[4] == 0x40000001 and cpu.T == 0, "addv false overflow")
    cpu = sub([0x340B, 0x000B], regs={0: 1, 4: 0x80000000})
    check(cpu.r[4] == 0x7FFFFFFF and cpu.T == 1, "subv overflow not flagged")
    cpu = sub([0x340B, 0x000B], regs={0: 1, 4: 0})
    check(cpu.r[4] == 0xFFFFFFFF and cpu.T == 0, "subv false overflow")


# ---------------------------------------------------------------------------
# 9. muls.w / mulu.w / mul.l
# ---------------------------------------------------------------------------
def test_mul():
    cpu = sub([0x240F, 0x001A, 0x000B], regs={0: 2, 4: 0xFFFF8001})  # -32767*2
    check(r0(cpu) == 0xFFFF0002, "muls.w wrong: 0x%08X" % r0(cpu))
    cpu = sub([0x240E, 0x001A, 0x000B], regs={0: 2, 4: 0xFFFF8001})  # 0x8001*2
    check(r0(cpu) == 0x00010002, "mulu.w wrong: 0x%08X" % r0(cpu))
    cpu = sub([0x0407, 0x001A, 0x000B], regs={0: 0x00001234, 4: 0x00012345})
    check(r0(cpu) == 0x14B60404 and cpu.mach == 0,
          "mul.l wrong: macl=0x%08X mach=0x%08X" % (r0(cpu), cpu.mach))


# ---------------------------------------------------------------------------
# 10. sleep / tas.b
# ---------------------------------------------------------------------------
def test_sleep_tas():
    cpu = sub([0x001B, 0x000B])
    check(r0(cpu) == 0, "sleep should be a no-op")
    cpu = sub([0x441B, 0x000B], regs={4: 0x1000}, ram={0x1000: 0x00})
    check(cpu.T == 1 and cpu.ram.get(0x1000) == 0x80, "tas.b zero case wrong")
    cpu = sub([0x441B, 0x000B], regs={4: 0x1000}, ram={0x1000: 0x40})
    check(cpu.T == 0 and cpu.ram.get(0x1000) == 0xC0, "tas.b nonzero case wrong")


# ---------------------------------------------------------------------------
# 11. and/or/xor #imm,R0
# ---------------------------------------------------------------------------
def test_imm_logic():
    cpu = sub([0xC95F, 0x000B], regs={0: 0xFF})   # and #0x5F,r0
    check(r0(cpu) == 0x5F, "and #0x5F,r0 wrong: 0x%08X" % r0(cpu))
    cpu = sub([0xCA5F, 0x000B], regs={0: 0xFF})   # xor #0x5F,r0
    check(r0(cpu) == 0xA0, "xor #0x5F,r0 wrong: 0x%08X" % r0(cpu))
    cpu = sub([0xCB5F, 0x000B], regs={0: 0x0A})   # or #0x5F,r0
    check(r0(cpu) == 0x5F, "or #0x5F,r0 wrong: 0x%08X" % r0(cpu))


# ---------------------------------------------------------------------------
# 12. bsrf / braf (delayed, PC = PC+4+Rn; bsrf also sets PR)
# ---------------------------------------------------------------------------
def test_braf_bsrf():
    # bsrf r2 with r2=2: target = 0+4+2 = 6 (mov at word 3); delay slot fixes PR to SENT.
    # mov #0xAA,r0 sign-extends to 0xFFFFFFAA.
    cpu = sub([0x0203, 0x412A, 0x0009, 0xE0AA, 0x000B], regs={2: 2, 1: 0xEEEE0000})
    check(r0(cpu) == 0xFFFFFFAA, "bsrf target wrong: r0=0x%08X" % r0(cpu))
    # braf r2 with r2=2: target = 0+4+2 = 6   (braf Rn = 0x0n23)
    cpu = sub([0x0223, 0x0009, 0x0009, 0xE0BB, 0x000B], regs={2: 2})
    check(r0(cpu) == 0xFFFFFFBB, "braf target wrong: r0=0x%08X" % r0(cpu))


# ---------------------------------------------------------------------------
# 11b. indexed mov.b @(R0,Rm),Rn sign-extends (0x0nmC)
# ---------------------------------------------------------------------------
def test_indexed_movb_signext():
    # mov.b @(r0,r4),r4 = 0x044C ; byte 0x80 at r0+r4 -> r4 must sign-extend
    cpu = sub([0x044C, 0x000B], regs={0: 0x1000, 4: 4}, ram={0x1004: 0x80})
    check(cpu.r[4] == 0xFFFFFF80, "mov.b @(R0,Rm),Rn sign-ext wrong: 0x%08X" % cpu.r[4])
    # positive byte stays positive
    cpu = sub([0x044C, 0x000B], regs={0: 0x1000, 4: 4}, ram={0x1004: 0x7F})
    check(cpu.r[4] == 0x7F, "mov.b @(R0,Rm),Rn pos wrong: 0x%08X" % cpu.r[4])


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    print("sh2emu decode-family regression tests")
    test_gbr_mov()
    test_movl_disp_r0()
    test_div_flags()
    test_div32_rom(N)
    test_cmp_str()
    test_mac()
    test_ctrl_regs()
    test_fpul_fpscr_mem()
    test_arith()
    test_mul()
    test_sleep_tas()
    test_imm_logic()
    test_indexed_movb_signext()
    test_braf_bsrf()
    print("%d checks, %d failures" % (CHECKS[0], len(FAILS)))
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main()
