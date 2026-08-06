#!/usr/bin/env python3
"""
c_lift_ops.py — SH-2 (big-endian) opcode -> C / Python mapping for pure-integer
lift generation (tools/gen_c_lift.py).

Every opcode's semantics here mirrors tools/sh2emu.py EXACTLY — that emulator is
the verification oracle, so a lift generated from these tables is guaranteed to
agree with it (modulo translator bugs, which the differential tests catch).

Each translate() returns a dict:

    { 'c':    [C statements, rendered into the lift body],
      'py':   [Python statements, rendered into the test's ref() model],
      'uses': set of variable names (r0..r15, T, mach, macl, Q, M, pr),
      'kind': 'st' | 'branch' | 'ret',
      'cond_c':  C condition string for branch kind,
      'cond_py': Python condition string for branch kind,
      'target':  resolved branch target address (branch kind),
      'delayed': True if the branch executes its delay slot first,
      'ann':     disassembly annotation string (for comments) }

Registers r4..r7 are the function arguments (set once at entry); r0..r3 and
r8..r15 are locals (initialized 0).  r0 holds the return value.  All arithmetic
is 32-bit unsigned (uint32_t / & 0xFFFFFFFF) as in the emulator.

Memory ops (b/w/l) are NOT handled by translate() — it still returns None for
them, exactly as before — but by the v2 entry point decode_mem():

    decode_mem(opcode_hi_word, opcode_lo_word_or_None, ctx)

    ctx (optional dict):
        ctx['resolve'](reg) -> ('RAM', abs_addr) | ('ROM', abs_addr) | None
                               (resolves the runtime value of base register `reg`,
                                e.g. a literal-pool address tracked by the caller)
        ctx['temp']()       -> unique temp variable name ('t1', 't2', ...)
    Returns None when `opcode_hi_word` is not a b/w/l memory op, or when its
    base register is neither a function param (r4..r7) nor resolvable — the v2
    generator then rejects the function.  Otherwise returns a dict:
        {'kind': 'mem', 'size': 1|2|4, 'dir': 'load'|'store',
         'base': 'param'|'literal', 'c': [C statements], ...}
    For base='literal' the fragment embeds the resolved absolute address with a
    `/* RAM 0x... */` / `/* ROM */` note (classify_addr); for base='param' the
    address is written as `(rN + disp)` so the C uses the runtime r4..r7 value.
    Covered SH-2 directions (b/w/l): loads  @(disp,Rn)->Rd (Rd==R0 only),
    @Rn->Rd, @Rn+->Rd, @(R0,Rn)->Rd; stores Rs->@(disp,Rn) (Rs==R0 only),
    Rs->@Rn, Rs->@-Rn, Rs->@(R0,Rn).  v6 adds the 4-bit-displacement mov.l
    forms the SH-2 emulator runs but the mapper used to leave 'unmapped':
    loads 0x5nmd mov.l @(disp,Rm),Rn and stores 0x1nmd mov.l Rn,@(disp,Rm)
    with disp = nib*4 (0,4,..,60) — same param/literal base rule, size 4,
    no sign-extend, no auto.  The SH-2 ISA has NO @-Rn load and NO @Rn+
    store, so those two directions are inherently undecodable (None).

v3 (additive, same module): the T-flag templates and the branch/return decode
API, ready for the generator's branch emission (translate() above is untouched
for branch/ret opcodes and gen_c_lift.py still rejects them):
    branch_info(opcode_hi) -> {'kind': 'bt'|'bf'|'bts'|'bfs'|'bra'|'rts'|'rte'|None,
                               'delayed': bool, 'target_disp': int|None}
    BRANCH_C_TEMPLATE / BRANCH_PY_TEMPLATE — goto/return C templates and their
    pc-updating mirror equivalents.
    Target formulas: bt/bf/bt.s/bf.s target = P+4 + s8(low byte)*2; bra target =
    P+4 + s12*2; rts target = PR (mirror `pc = pr`); rte has NO template (the
    generator must reject it).  The C never reads T for branches — the generator
    emits `if (T) goto L_...;` / `if (!T) goto L_...;` and places the delay slot
    BEFORE the branch when delayed; the mirror uses T as its internal flag.

v6 (additive, this module): GBR byte bit-ops — decode_gbr_bit() decodes the
0xCC-CF forms sh2emu runs but _decode_gbr (0xC0-C6) and decode_mem leave
'unmapped': tst.b/and.b/xor.b/or.b #imm,@(r0,GBR) — address = GBR + R0 (both
must resolve to constants, passed as ctx['gbr']), size 1, tst.b sets T only,
the others read-modify-write the byte.  translate() additionally gains the
real lds Rn,mach/macl/pr (0x4n0A/0x4n1A/0x4n2A, previously dead-code 'unmapped')
and xtrct (0x2nmD).  The v6 "NOT implemented" note below is now partially
superseded: translate() additionally maps ldc Rn,VBR (0x4n2E) as a pure op, and
decode_mem() maps the sts.l/lds.l mach/macl/pr stack/memory forms
(0x4n02/06/12/16/22/26, param/literal bases only) plus mac.l @Rm+,@Rn+ (0x0nmF,
when BOTH base registers resolve); the mac.w form, the stc.l/ldc.l VBR/SSR/SPC
and stc GBR memory forms, and tas.b @Rn remain 'unmapped'.
"""
import struct

MASK = 0xFFFFFFFF
REG = "r0 r1 r2 r3 r4 r5 r6 r7 r8 r9 r10 r11 r12 r13 r14 r15".split()


def s8(x):  x &= 0xFF;  return x - 0x100 if x & 0x80 else x
def s16(x): x &= 0xFFFF; return x - 0x10000 if x & 0x8000 else x
def s32(x): x &= MASK;  return x - 0x100000000 if x & 0x80000000 else x


def c_imm(v, bits=32):
    """C literal for an unsigned 32-bit constant."""
    v &= MASK
    if v <= 0xFF:
        return "0x%02Xu" % v
    return "0x%08Xu" % v


def py_imm(v, bits=32):
    return "0x%08X" % (v & MASK)


# ---------------------------------------------------------------------------
# operand-level helpers
# ---------------------------------------------------------------------------
def rn(op): return (op >> 8) & 0xF
def rm(op): return (op >> 4) & 0xF
def lo(op): return op & 0xFF


def lit16(rom, pc, disp):
    """mov.w @(disp,PC): sign-extended 16-bit value."""
    addr = (pc + 4 + disp * 2) & MASK
    return s16(struct.unpack('>H', rom[addr:addr + 2])[0]) & MASK


def lit32(rom, pc, disp):
    """mov.l @(disp,PC): 32-bit value at ((pc+4)&~3)+disp*4."""
    addr = ((pc + 4) & ~3) + disp * 4
    return struct.unpack('>I', rom[addr:addr + 4])[0] & MASK


def mova_target(pc, disp):
    return (((pc + 4) & ~3) + disp * 4) & MASK


def bra_target(pc, d12):
    d12 &= 0xFFF
    if d12 & 0x800: d12 -= 0x1000
    return (pc + 4 + d12 * 2) & MASK


def cond_target(pc, d8):
    return (pc + 4 + s8(d8) * 2) & MASK


# ---------------------------------------------------------------------------
# statement builders — each returns (c_stmt, py_stmt) text
# ---------------------------------------------------------------------------
def _st(reg_c, reg_py, c, py):
    return ({'c': [c], 'py': [py], 'uses': set(reg_c) | set(reg_py)})


def _mk(c, py, uses):
    return {'c': [c], 'py': [py], 'uses': set(uses)}


def translate(op, pc, rom, ann=''):
    """Return the semantic dict for opcode `op` at address `pc`, or None if the
    opcode is not in the pure-integer mapping (memory ops, FPU, calls...)."""
    n = rn(op); m = rm(op); n0 = op >> 12; nib = op & 0xF; l = lo(op)
    R = REG
    cu = 'r'  # C register prefix (r0..)
    # helper to build statement pairs for a plain register op
    def pair(cfmt, pyfmt, args):
        # args: list of ('r', idx) or ('const', value) or ('T',) etc.
        d = {}
        return None

    # ---- mov / extu / exts / not / neg / swap ----
    if n0 == 0x6:
        if nib == 0x3:
            return _mk('r%d = r%d;' % (n, m), 'r[%d] = r[%d]' % (n, m), ['r%d' % n, 'r%d' % m])
        if nib == 0xC:
            return _mk('r%d = r%d & 0xFFu;' % (n, m), 'r[%d] = r[%d] & 0xFF' % (n, m), ['r%d' % n, 'r%d' % m])
        if nib == 0xD:
            return _mk('r%d = r%d & 0xFFFFu;' % (n, m), 'r[%d] = r[%d] & 0xFFFF' % (n, m), ['r%d' % n, 'r%d' % m])
        if nib == 0xE:
            return _mk('r%d = (uint32_t)(int32_t)(int8_t)(r%d & 0xFFu);' % (n, m),
                       'r[%d] = s8(r[%d] & 0xFF)' % (n, m), ['r%d' % n, 'r%d' % m])
        if nib == 0xF:
            return _mk('r%d = (uint32_t)(int32_t)(int16_t)(r%d & 0xFFFFu);' % (n, m),
                       'r[%d] = s16(r[%d] & 0xFFFF)' % (n, m), ['r%d' % n, 'r%d' % m])
        if nib == 0x7:
            return _mk('r%d = ~r%d;' % (n, m), 'r[%d] = (~r[%d]) & 0xFFFFFFFF' % (n, m), ['r%d' % n, 'r%d' % m])
        if nib == 0xB:
            return _mk('r%d = 0u - r%d;' % (n, m), 'r[%d] = (-r[%d]) & 0xFFFFFFFF' % (n, m), ['r%d' % n, 'r%d' % m])
        if nib == 0x8:
            return _mk('r%d = ((r%d << 8) & 0xFF00FF00u) | ((r%d >> 8) & 0x00FF00FFu);' % (n, m, m),
                       'r[%d] = (((r[%d] << 8) & 0xFF00FF00) | ((r[%d] >> 8) & 0x00FF00FF)) & 0xFFFFFFFF' % (n, m, m),
                       ['r%d' % n, 'r%d' % m])
        if nib == 0x9:
            return _mk('r%d = (r%d << 16) | (r%d >> 16);' % (n, m, m),
                       'r[%d] = ((r[%d] << 16) | (r[%d] >> 16)) & 0xFFFFFFFF' % (n, m, m), ['r%d' % n, 'r%d' % m])
        if nib == 0xA:   # negc Rm,Rn  (mirror sh2emu: T = borrow, rn = 0-rm-T;
            # T reads r[m] AFTER the write, so n==m sees the negated value)
            return _mk('{ uint32_t _m0 = r%d; r%d = (uint32_t)(0u - _m0 - T); T = ((r%d + T) & 0xFFFFFFFFu) ? 1u : 0u; }' % (m, n, m),
                       's = -r[%d] - T\n            r[%d] = s & 0xFFFFFFFF\n            T = 1 if (r[%d] + T) & 0xFFFFFFFF else 0' % (m, n, m),
                       ['T', 'r%d' % n, 'r%d' % m])

    # ---- arithmetic / compare (n0==3) ----
    if n0 == 0x3:
        if nib == 0xC:
            return _mk('r%d = r%d + r%d;' % (n, n, m), 'r[%d] = (r[%d] + r[%d]) & 0xFFFFFFFF' % (n, n, m), ['r%d' % n, 'r%d' % m])
        if nib == 0x8:
            return _mk('r%d = r%d - r%d;' % (n, n, m), 'r[%d] = (r[%d] - r[%d]) & 0xFFFFFFFF' % (n, n, m), ['r%d' % n, 'r%d' % m])
        if nib == 0x0:
            return _mk('T = (r%d == r%d) ? 1u : 0u;' % (n, m), 'T = 1 if r[%d] == r[%d] else 0' % (n, m), ['T', 'r%d' % n, 'r%d' % m])
        if nib == 0x2:
            return _mk('T = (r%d >= r%d) ? 1u : 0u;' % (n, m),
                       'T = 1 if (r[%d] & 0xFFFFFFFF) >= (r[%d] & 0xFFFFFFFF) else 0' % (n, m), ['T', 'r%d' % n, 'r%d' % m])
        if nib == 0x3:
            return _mk('T = ((int32_t)r%d >= (int32_t)r%d) ? 1u : 0u;' % (n, m),
                       'T = 1 if s32(r[%d]) >= s32(r[%d]) else 0' % (n, m), ['T', 'r%d' % n, 'r%d' % m])
        if nib == 0x6:
            return _mk('T = (r%d > r%d) ? 1u : 0u;' % (n, m),
                       'T = 1 if (r[%d] & 0xFFFFFFFF) > (r[%d] & 0xFFFFFFFF) else 0' % (n, m), ['T', 'r%d' % n, 'r%d' % m])
        if nib == 0x7:
            return _mk('T = ((int32_t)r%d > (int32_t)r%d) ? 1u : 0u;' % (n, m),
                       'T = 1 if s32(r[%d]) > s32(r[%d]) else 0' % (n, m), ['T', 'r%d' % n, 'r%d' % m])
        if nib == 0xE:   # addc
            return _mk('{ uint64_t _s = (uint64_t)r%d + r%d + T; T = (uint32_t)(_s >> 32); r%d = (uint32_t)_s; }' % (n, m, n),
                       's = r[%d] + r[%d] + T\n            r[%d] = s & 0xFFFFFFFF\n            T = (s >> 32) & 1' % (n, m, n),
                       ['T', 'r%d' % n, 'r%d' % m])
        if nib == 0xA:   # subc
            return _mk('{ int64_t _s = (int64_t)r%d - r%d - T; T = (_s < 0) ? 1u : 0u; r%d = (uint32_t)_s; }' % (n, m, n),
                       's = r[%d] - r[%d] - T\n            r[%d] = s & 0xFFFFFFFF\n            T = 1 if s < 0 else 0' % (n, m, n),
                       ['T', 'r%d' % n, 'r%d' % m])
        if nib == 0xB:   # subv (saturating? no: T=overflow, r=wrapped)
            return _mk('{ int64_t _s = (int64_t)(int32_t)r%d - (int64_t)(int32_t)r%d; r%d = (uint32_t)_s; T = (_s > 0x7FFFFFFFLL || _s < -0x80000000LL) ? 1u : 0u; }' % (n, m, n),
                       's = s32(r[%d]) - s32(r[%d])\n            r[%d] = s & 0xFFFFFFFF\n            T = 1 if s > 0x7FFFFFFF or s < -0x80000000 else 0' % (n, m, n),
                       ['T', 'r%d' % n, 'r%d' % m])
        if nib == 0xF:   # addv
            return _mk('{ int64_t _s = (int64_t)(int32_t)r%d + (int64_t)(int32_t)r%d; r%d = (uint32_t)_s; T = (_s > 0x7FFFFFFFLL || _s < -0x80000000LL) ? 1u : 0u; }' % (n, m, n),
                       's = s32(r[%d]) + s32(r[%d])\n            r[%d] = s & 0xFFFFFFFF\n            T = 1 if s > 0x7FFFFFFF or s < -0x80000000 else 0' % (n, m, n),
                       ['T', 'r%d' % n, 'r%d' % m])
        if nib == 0x4:   # div1 Rm,Rn  (mirror sh2emu._exec)
            return _mk(
                '{ uint32_t _t0 = (r%d >> 31) & 1u;'
                ' r%d = (r%d << 1) | (T & 1u);'
                ' uint32_t _t1 = (Q ^ M) & 1u;'
                ' _t1 = (_t1 - 1u) & 0xFFFFFFFFu;'
                ' uint32_t _t2 = (0u - r%d) & 0xFFFFFFFFu;'
                ' if (_t1 == 0u) _t2 = r%d;'
                ' uint64_t _lo = (uint64_t)r%d + _t2;'
                ' r%d = (uint32_t)_lo;'
                ' uint32_t _carry = (uint32_t)(_lo >> 32) & 1u;'
                ' _t1 = (_t1 + _carry) & 1u; _t1 ^= _t0;'
                ' T = (_t1 ^ 1u) & 1u; Q = (M ^ _t1) & 1u; }' % (n, n, n, m, m, n, n),
                't0 = (r[%d] >> 31) & 1\n'
                '            r[%d] = ((r[%d] << 1) | (T & 1)) & 0xFFFFFFFF\n'
                '            t1 = (Q ^ M) & 1\n'
                '            t1 = (t1 - 1) & 0xFFFFFFFF\n'
                '            t2 = (-r[%d]) & 0xFFFFFFFF\n'
                '            if t1 == 0: t2 = r[%d]\n'
                '            lo = r[%d] + t2\n'
                '            r[%d] = lo & 0xFFFFFFFF\n'
                '            carry = (lo >> 32) & 1\n'
                '            t1 = (t1 + carry) & 1\n'
                '            t1 ^= t0\n'
                '            T = (t1 ^ 1) & 1\n'
                '            Q = (M ^ t1) & 1' % (n, n, n, m, m, n, n),
                ['T', 'Q', 'M', 'r%d' % n, 'r%d' % m])
        if nib == 0xD:   # dmuls.l
            return _mk('{ int64_t _p = (int64_t)(int32_t)r%d * (int64_t)(int32_t)r%d; mach = (uint32_t)(_p >> 32); macl = (uint32_t)_p; }' % (m, n),
                       'p = s32(r[%d]) * s32(r[%d])\n            mach = (p >> 32) & 0xFFFFFFFF\n            macl = p & 0xFFFFFFFF' % (m, n),
                       ['mach', 'macl', 'r%d' % m, 'r%d' % n])
        if nib == 0x5:   # dmulu.l
            return _mk('{ uint64_t _p = (uint64_t)r%d * r%d; mach = (uint32_t)(_p >> 32); macl = (uint32_t)_p; }' % (m, n),
                       'p = r[%d] * r[%d]\n            mach = (p >> 32) & 0xFFFFFFFF\n            macl = p & 0xFFFFFFFF' % (m, n),
                       ['mach', 'macl', 'r%d' % m, 'r%d' % n])

    # ---- tst / and / xor / or / cmp/str / div0s / mulu.w / muls.w (n0==2) ----
    if n0 == 0x2:
        if nib == 0x8:
            return _mk('T = ((r%d & r%d) == 0u) ? 1u : 0u;' % (n, m), 'T = 1 if (r[%d] & r[%d]) == 0 else 0' % (n, m), ['T', 'r%d' % n, 'r%d' % m])
        if nib == 0x9:
            return _mk('r%d &= r%d;' % (n, m), 'r[%d] = (r[%d] & r[%d]) & 0xFFFFFFFF' % (n, n, m), ['r%d' % n, 'r%d' % m])
        if nib == 0xA:
            return _mk('r%d ^= r%d;' % (n, m), 'r[%d] = (r[%d] ^ r[%d]) & 0xFFFFFFFF' % (n, n, m), ['r%d' % n, 'r%d' % m])
        if nib == 0xB:
            return _mk('r%d |= r%d;' % (n, m), 'r[%d] = (r[%d] | r[%d]) & 0xFFFFFFFF' % (n, n, m), ['r%d' % n, 'r%d' % m])
        if nib == 0xC:   # cmp/str
            return _mk('{ uint32_t _x = r%d ^ r%d; uint32_t _y = (_x - 0x01010101u) & ~_x; T = (_y & 0x80808080u) ? 1u : 0u; }' % (m, n),
                       'x = r[%d] ^ r[%d]\n            y = ((x - 0x01010101) & (~x) & 0xFFFFFFFF)\n            T = 1 if (y & 0x80808080) else 0' % (m, n),
                       ['T', 'r%d' % m, 'r%d' % n])
        if nib == 0x7:   # div0s Rm,Rn
            return _mk('Q = (r%d >> 31) & 1u; M = (r%d >> 31) & 1u; T = Q ^ M;' % (n, m),
                       'Q = (r[%d] >> 31) & 1\n            M = (r[%d] >> 31) & 1\n            T = Q ^ M' % (n, m),
                       ['Q', 'M', 'T', 'r%d' % n, 'r%d' % m])
        if nib == 0xD:   # xtrct Rm,Rn  (mirror sh2emu: (Rm<<16)|(Rn>>16))
            return _mk('r%d = ((r%d << 16) | (r%d >> 16));' % (n, m, n),
                       'r[%d] = ((r[%d] << 16) | (r[%d] >> 16)) & 0xFFFFFFFF' % (n, m, n),
                       ['r%d' % n, 'r%d' % m])
        if nib == 0xF:   # muls.w
            return _mk('macl = (uint32_t)((int32_t)(int16_t)(r%d & 0xFFFFu) * (int32_t)(int16_t)(r%d & 0xFFFFu));' % (m, n),
                       'macl = (s16(r[%d]) * s16(r[%d])) & 0xFFFFFFFF' % (m, n),
                       ['macl', 'r%d' % m, 'r%d' % n])
        if nib == 0xE:   # mulu.w
            return _mk('macl = ((r%d & 0xFFFFu) * (r%d & 0xFFFFu));' % (m, n),
                       'macl = ((r[%d] & 0xFFFF) * (r[%d] & 0xFFFF)) & 0xFFFFFFFF' % (m, n),
                       ['macl', 'r%d' % m, 'r%d' % n])

    # ---- add #imm / mov #imm (n0 7 / E) ----
    if n0 == 0x7:
        return _mk('r%d = r%d + (uint32_t)(int32_t)(int8_t)0x%02X;' % (n, n, l),
                   'r[%d] = (r[%d] + s8(0x%02X)) & 0xFFFFFFFF' % (n, n, l), ['r%d' % n])
    if n0 == 0xE:
        return _mk('r%d = (uint32_t)(int32_t)(int8_t)0x%02X;' % (n, l),
                   'r[%d] = s8(0x%02X)' % (n, l), ['r%d' % n])

    # ---- literal pool loads ----
    if n0 == 0xD:
        v = lit32(rom, pc, l)
        return _mk('r%d = %s;' % (n, c_imm(v)), 'r[%d] = %s' % (n, py_imm(v)), ['r%d' % n])
    if n0 == 0x9:
        v = lit16(rom, pc, l)
        return _mk('r%d = (uint32_t)(int32_t)(int16_t)%s;' % (n, c_imm(v & 0xFFFF, 16)),
                   'r[%d] = %s' % (n, py_imm(v)), ['r%d' % n])
    if op & 0xFF00 == 0xC700:   # mova
        v = mova_target(pc, l)
        return _mk('r0 = %s;' % c_imm(v), 'r[0] = %s' % py_imm(v), ['r0'])

    # ---- immediate logical ops on r0 ----
    if op & 0xFF00 == 0xC800:
        return _mk('T = ((r0 & 0x%02Xu) == 0u) ? 1u : 0u;' % l, 'T = 1 if (r[0] & 0x%02X) == 0 else 0' % l, ['T', 'r0'])
    if op & 0xFF00 == 0xC900:
        return _mk('r0 &= 0x%02Xu;' % l, 'r[0] = (r[0] & 0x%02X) & 0xFFFFFFFF' % l, ['r0'])
    if op & 0xFF00 == 0xCA00:
        return _mk('r0 ^= 0x%02Xu;' % l, 'r[0] = (r[0] ^ 0x%02X) & 0xFFFFFFFF' % l, ['r0'])
    if op & 0xFF00 == 0xCB00:
        return _mk('r0 |= 0x%02Xu;' % l, 'r[0] = (r[0] | 0x%02X) & 0xFFFFFFFF' % l, ['r0'])
    if op & 0xFF00 == 0x8800:   # cmp/eq #imm,R0 (signed imm)
        return _mk('T = ((int32_t)r0 == (int32_t)(int8_t)0x%02X) ? 1u : 0u;' % l,
                   'T = 1 if s32(r[0]) == s8(0x%02X) else 0' % l, ['T', 'r0'])

    # ---- shifts / rotates / T-flag tests (n0==4, small set) ----
    f = op & 0xF0FF
    if n0 == 0x4:
        if f == 0x4000: return _mk('T = (r%d >> 31) & 1u; r%d = (r%d << 1);' % (n, n, n),
                                   'T = (r[%d] >> 31) & 1\n            r[%d] = (r[%d] << 1) & 0xFFFFFFFF' % (n, n, n),
                                   ['T', 'r%d' % n])
        if f == 0x4001: return _mk('T = r%d & 1u; r%d = (r%d >> 1);' % (n, n, n),
                                   'T = r[%d] & 1\n            r[%d] = (r[%d] >> 1) & 0xFFFFFFFF' % (n, n, n),
                                   ['T', 'r%d' % n])
        if f == 0x4008: return _mk('r%d = (r%d << 2);' % (n, n), 'r[%d] = (r[%d] << 2) & 0xFFFFFFFF' % (n, n), ['r%d' % n])
        if f == 0x4009: return _mk('r%d = (r%d >> 2);' % (n, n), 'r[%d] = (r[%d] >> 2) & 0xFFFFFFFF' % (n, n), ['r%d' % n])
        if f == 0x4018: return _mk('r%d = (r%d << 8);' % (n, n), 'r[%d] = (r[%d] << 8) & 0xFFFFFFFF' % (n, n), ['r%d' % n])
        if f == 0x4019: return _mk('r%d = (r%d >> 8);' % (n, n), 'r[%d] = (r[%d] >> 8) & 0xFFFFFFFF' % (n, n), ['r%d' % n])
        if f == 0x4028: return _mk('r%d = (r%d << 16);' % (n, n), 'r[%d] = (r[%d] << 16) & 0xFFFFFFFF' % (n, n), ['r%d' % n])
        if f == 0x4029: return _mk('r%d = (r%d >> 16);' % (n, n), 'r[%d] = (r[%d] >> 16) & 0xFFFFFFFF' % (n, n), ['r%d' % n])
        if f == 0x4021: return _mk('T = r%d & 1u; r%d = (r%d >> 1) | (r%d & 0x80000000u);' % (n, n, n, n),
                                   'T = r[%d] & 1\n            r[%d] = ((r[%d] >> 1) | (r[%d] & 0x80000000)) & 0xFFFFFFFF' % (n, n, n, n),
                                   ['T', 'r%d' % n])
        if f == 0x4020: return _mk('T = (r%d >> 31) & 1u; r%d = (r%d << 1);' % (n, n, n),
                                   'T = (r[%d] >> 31) & 1\n            r[%d] = (r[%d] << 1) & 0xFFFFFFFF' % (n, n, n),
                                   ['T', 'r%d' % n])
        if f == 0x4004: return _mk('T = (r%d >> 31) & 1u; r%d = (r%d << 1) | (r%d >> 31);' % (n, n, n, n),
                                   'T = (r[%d] >> 31) & 1\n            r[%d] = ((r[%d] << 1) | (r[%d] >> 31)) & 0xFFFFFFFF' % (n, n, n, n),
                                   ['T', 'r%d' % n])
        if f == 0x4005: return _mk('T = r%d & 1u; r%d = (r%d >> 1) | ((r%d & 1u) << 31);' % (n, n, n, n),
                                   'T = r[%d] & 1\n            r[%d] = ((r[%d] >> 1) | ((r[%d] & 1) << 31)) & 0xFFFFFFFF' % (n, n, n, n),
                                   ['T', 'r%d' % n])
        if f == 0x4024: return _mk('{ uint32_t _t = (r%d >> 31) & 1u; r%d = (r%d << 1) | T; T = _t; }' % (n, n, n),
                                   't = (r[%d] >> 31) & 1\n            r[%d] = ((r[%d] << 1) | T) & 0xFFFFFFFF\n            T = t' % (n, n, n),
                                   ['T', 'r%d' % n])
        if f == 0x4025: return _mk('{ uint32_t _t = r%d & 1u; r%d = (r%d >> 1) | (T << 31); T = _t; }' % (n, n, n),
                                   't = r[%d] & 1\n            r[%d] = ((r[%d] >> 1) | (T << 31)) & 0xFFFFFFFF\n            T = t' % (n, n, n),
                                   ['T', 'r%d' % n])
        if f == 0x4011: return _mk('T = ((int32_t)r%d >= 0) ? 1u : 0u;' % n, 'T = 1 if s32(r[%d]) >= 0 else 0' % n, ['T', 'r%d' % n])
        if f == 0x4015: return _mk('T = ((int32_t)r%d > 0) ? 1u : 0u;' % n, 'T = 1 if s32(r[%d]) > 0 else 0' % n, ['T', 'r%d' % n])
        if f == 0x4010: return _mk('r%d = r%d - 1u; T = (r%d == 0u) ? 1u : 0u;' % (n, n, n),
                                   'r[%d] = (r[%d] - 1) & 0xFFFFFFFF\n            T = 1 if r[%d] == 0 else 0' % (n, n, n),
                                   ['T', 'r%d' % n])
        # lds Rn,mach/macl/pr = 0x4n0A/0x4n1A/0x4n2A (mirror sh2emu n0==0x4).
        # The pre-v6 entries here checked f == 0x000A/0x001A/0x002A — dead code
        # inside the n0==0x4 block (f is always 0x40xx there), so the real lds
        # forms fell through to None as 'unmapped'; the n0==0x0 sts block below
        # owns the 0x000A/0x001A/0x002A encodings.  All three are pure register
        # writes, 1:1 with the oracle.
        if f == 0x400A: return _mk('mach = r%d;' % n, 'mach = r[%d] & 0xFFFFFFFF' % n, ['mach', 'r%d' % n])
        if f == 0x401A: return _mk('macl = r%d;' % n, 'macl = r[%d] & 0xFFFFFFFF' % n, ['macl', 'r%d' % n])
        if f == 0x402A: return _mk('pr = r%d;' % n, 'pr = r[%d] & 0xFFFFFFFF' % n, ['pr', 'r%d' % n])
        # memory / stack / sr ops under n0==4 are NOT pure -> None (caller filters)

    # ---- misc system ops ----
    if op == 0x0009: return _mk('', '', [])                       # nop
    if op == 0x0019: return _mk('Q = 0u; M = 0u; T = 0u;', 'Q = 0; M = 0; T = 0', ['Q', 'M', 'T'])  # div0u
    if op == 0x0008: return _mk('T = 0u;', 'T = 0', ['T'])       # clrt
    if op == 0x0018: return _mk('T = 1u;', 'T = 1', ['T'])       # sett
    if op == 0x0028: return _mk('mach = 0u; macl = 0u;', 'mach = 0; macl = 0', ['mach', 'macl'])  # clrmac
    if op & 0xF0FF == 0x0029: return _mk('r%d = T;' % n, 'r[%d] = T;' % n, ['r%d' % n, 'T'])      # movt
    if op == 0x001B: return _mk('', '', [])                       # sleep -> no-op (as sh2emu)

    # ---- mul.l / sts macl / mach (n0==0) ----
    if n0 == 0x0:
        if nib == 0x7:   # mul.l Rm,Rn -> macl = low32(signed product)
            return _mk('macl = (uint32_t)((int32_t)r%d * (int32_t)r%d);' % (n, m),
                       'macl = (s32(r[%d]) * s32(r[%d])) & 0xFFFFFFFF' % (n, m), ['macl', 'r%d' % n, 'r%d' % m])
        if op & 0xF0FF == 0x000A: return _mk('r%d = mach;' % n, 'r[%d] = mach' % n, ['r%d' % n, 'mach'])
        if op & 0xF0FF == 0x001A: return _mk('r%d = macl;' % n, 'r[%d] = macl' % n, ['r%d' % n, 'macl'])
        if op & 0xF0FF == 0x002A: return _mk('r%d = pr;' % n, 'r[%d] = pr' % n, ['r%d' % n, 'pr'])

    # ---- SR system-register ops (additive, real): sh2emu executes these
    # (stc SR,Rn 0x0n02 / ldc Rn,SR 0x4n0E — see sh2emu._exec).  `sr` is an
    # independent uint32 state, init 0x000000F0 (sh2emu call() default), and is
    # NOT synced with T: ldc sets sr verbatim, stc reads it verbatim, exactly
    # like the oracle.  The generator declares sr (uint32_t, default 0x000000F0)
    # only when the body references it, and the test mirror seeds sr likewise.
    if op & 0xF0FF == 0x0002 and (op >> 12) == 0:      # stc SR,Rn
        return _mk('r%d = sr;' % n, 'r[%d] = sr' % n, ['r%d' % n, 'sr'])
    if op & 0xF0FF == 0x400E:                          # ldc Rn,SR
        return _mk('sr = r%d;' % n, 'sr = r[%d]' % n, ['r%d' % n, 'sr'])
    if op & 0xF0FF == 0x402E:                          # ldc Rn,VBR (mirror sh2emu 0x4n2E)
        # `vbr` is modeled like `sr`: an independent uint32 state (sh2emu seeds
        # it 0 at call()).  NOTE: gen_c_lift_v3.build_locals currently declares
        # no `vbr` C local (only T/Q/M/macl/mach/sr/pr/fr*/fpul/fpscr), so a
        # lift containing this op would need a generator update to compile —
        # out of scope here; the decode itself is 1:1 with the oracle.
        return _mk('vbr = r%d;' % n, 'vbr = r[%d] & 0xFFFFFFFF' % n, ['vbr', 'r%d' % n])

    # ---- branches / return (control flow) ----
    if op == 0x000B:   # rts (delayed)
        return {'c': [], 'py': [], 'uses': set(), 'kind': 'ret', 'delayed': True,
                'target': None, 'cond_c': None, 'cond_py': None, 'ann': ann}
    if op & 0xFF00 == 0x8B00:   # bf (not delayed)
        return {'c': [], 'py': [], 'uses': {'T'}, 'kind': 'branch', 'delayed': False,
                'target': cond_target(pc, l), 'cond_c': 'T == 0u', 'cond_py': 'T == 0', 'ann': ann}
    if op & 0xFF00 == 0x8900:   # bt (not delayed)
        return {'c': [], 'py': [], 'uses': {'T'}, 'kind': 'branch', 'delayed': False,
                'target': cond_target(pc, l), 'cond_c': 'T != 0u', 'cond_py': 'T != 0', 'ann': ann}
    if op & 0xFF00 == 0x8D00:   # bt/s (delayed)
        return {'c': [], 'py': [], 'uses': {'T'}, 'kind': 'branch', 'delayed': True,
                'target': cond_target(pc, l), 'cond_c': 'T != 0u', 'cond_py': 'T != 0', 'ann': ann}
    if op & 0xFF00 == 0x8F00:   # bf/s (delayed)
        return {'c': [], 'py': [], 'uses': {'T'}, 'kind': 'branch', 'delayed': True,
                'target': cond_target(pc, l), 'cond_c': 'T == 0u', 'cond_py': 'T == 0', 'ann': ann}
    if n0 == 0xA:   # bra (delayed, unconditional)
        return {'c': [], 'py': [], 'uses': set(), 'kind': 'branch', 'delayed': True,
                'target': bra_target(pc, op & 0xFFF), 'cond_c': '1u', 'cond_py': '1', 'ann': ann}
    # bsrf Rn / braf Rn (delayed, DYNAMIC target = P+4+Rn — never statically
    # known; only bsrf also writes PR = P+4).  The selector's _v3_branch_rule
    # needs an in-span target to admit a branch, so these carry a DUMMY target
    # == pc (the instruction itself is always inside the scanned span); the
    # generator never uses it (walk_v3 emits them as terminal `return r0;` and
    # the test mirror as a dynamic pc jump).  Matching sh2emu's _delayed().
    if op & 0xF0FF == 0x0003 and (op >> 12) == 0:      # bsrf Rn
        return {'c': [], 'py': [], 'uses': {'r%d' % n}, 'kind': 'branch', 'delayed': True,
                'target': pc, 'cond_c': None, 'cond_py': None, 'ann': ann}
    if op & 0xF0FF == 0x0023 and (op >> 12) == 0:      # braf Rn
        return {'c': [], 'py': [], 'uses': {'r%d' % n}, 'kind': 'branch', 'delayed': True,
                'target': pc, 'cond_c': None, 'cond_py': None, 'ann': ann}

    return None  # unsupported / impure opcode


# ---------------------------------------------------------------------------
# v2 generator: memory ops (b/w/l) — RAM/ROM accesses whose base register is a
# function param (r4..r7) or resolves to a fixed address (literal pool).  The
# existing translate() is untouched and still returns None for these opcodes;
# decode_mem() is purely additive.  Encodings mirror tools/sh2emu.py:
#   loads 0x6nxx (nib 0/1/2 = @Rn, nib 4/5/6 = @Rn+), R0-only disp 0x84/85/86,
#          indexed 0x0nmC/D/E (@(R0,Rm))
#   stores 0x2nxx (nib 0/1/2 = @Rn, nib 4/5/6 = @-Rn), R0-only disp 0x80/81/82,
#          indexed 0x0nm4/5/6 (@(R0,Rn))
# ---------------------------------------------------------------------------
import itertools as _itertools

_SIZE_NIB = {0: 1, 1: 2, 2: 4, 4: 1, 5: 2, 6: 4, 0xC: 1, 0xD: 2, 0xE: 4}
# (lo|hi) nibble -> access size: 0x2/0x6 family low nibbles 0/1/2 (plain) and
# 4/5/6 (@-/@+), R0-only 0x8nxx upper nibbles, indexed low nibbles 4/5/6 and
# 0xC/D/E (@(R0,Rm) loads)
_SIZE_CH = {1: 'b', 2: 'w', 4: 'l'}
_CTYPE = {1: 'uint8_t', 2: 'uint16_t', 4: 'uint32_t'}
# sign-extension casts for b/w GBR/mem loads (C) and s8/s16 helpers (mirror)
_SEXT_C = {1: '(uint32_t)(int32_t)(int8_t)', 2: '(uint32_t)(int32_t)(int16_t)'}
_SEXT_PY = {1: 's8', 2: 's16'}
_tmp = _itertools.count(1)


def _default_temp():
    return 't%d' % next(_tmp)


def sign_extend16(v):
    """16-bit value -> 32-bit two's-complement (unsigned form): 0xD3F0 -> 0xFFFFD3F0."""
    v &= 0xFFFF
    return (v - 0x10000 if v & 0x8000 else v) & MASK


def classify_addr(v):
    """'RAM' (0xFFFF0000..0xFFFFFFFF) | 'ROM' (0x00000000..0x000FFFFF) | 'OTHER'."""
    v &= MASK
    if 0xFFFF0000 <= v <= 0xFFFFFFFF:
        return 'RAM'
    if 0x00000000 <= v <= 0x000FFFFF:
        return 'ROM'
    return 'OTHER'


def _c_addr(v):
    return '0x%08X' % (v & MASK)


def _ram_note(abs_addr):
    """Trailing C comment for a literal-base access: RAM addr vs ROM."""
    if classify_addr(abs_addr) == 'RAM':
        return ' /* RAM %s */' % _c_addr(abs_addr)
    return ' /* ROM */'


def _resolve_base(ctx, reg):
    """('param', None) for r4..r7; ('literal', addr) via ctx['resolve']; else None."""
    if 4 <= reg <= 7:
        return ('param', None)
    res = (ctx or {}).get('resolve')
    if res is None:
        return None
    hit = res(reg)
    if not hit or hit[0] not in ('RAM', 'ROM'):
        return None
    addr = hit[1]
    if isinstance(addr, str):
        addr = int(addr, 0)
    return ('literal', addr & MASK)


def _eff_addr(base_kind, base_c, off, idx, abs_addr):
    """C expression for the effective address.

    base_kind 'literal': baked absolute constant (abs_addr + off); 'param':
    runtime register expression `(rN + off)` (disp included, off may be 0).
    idx (e.g. 'r0') adds a runtime index for the @(R0,Rn) forms.
    """
    if base_kind == 'literal':
        a = (abs_addr + off) & MASK
        expr = _c_addr(a)
        if idx is not None:
            expr = '(%s + %s)' % (expr, idx)
        return expr, a
    if idx is not None:
        return '(%s + %s)' % (base_c, idx), None
    if off < 0:
        return '(%s - %d)' % (base_c, -off), None
    return '(%s + %d)' % (base_c, off), None


def lit_load_value(rom, abs_addr, size, sext=True, ram_known=None):
    """Value a load of `size` bytes from the literal absolute address `abs_addr`
    reads, IF statically knowable — else None (the caller keeps the register
    UNKNOWN, i.e. leaves base_unresolved).

    ROM  (< 1MB, inside the ROM file): the bytes are deterministic, so the
         loaded value is known and sign-extended per `sext` (mov.b/mov.w).
    RAM: only when EVERY byte is present in `ram_known` ({addr: byte} written by
         earlier KNOWN stores on the same execution path); a missing byte means
         the slot was never written with a known value -> None.  The caller is
         responsible for only allowing RAM folds when the path is linear (no
         branch/call between the known store and this load).

    Matches sh2emu._rb and the generated test mirror's _rd (RAM overlay first,
    then ROM bytes), so a folded value equals what both engines read.
    """
    a = abs_addr & MASK
    if classify_addr(a) == 'ROM':
        if a + size > len(rom):
            return None
        v = int.from_bytes(rom[a:a + size], 'big')
    elif classify_addr(a) == 'RAM' and ram_known:
        bs = [ram_known.get((a + i) & MASK) for i in range(size)]
        if any(b is None for b in bs):
            return None
        v = int.from_bytes(bytes(bs), 'big')
    else:
        return None
    if sext:
        if size == 1 and v & 0x80:
            v -= 0x100
        elif size == 2 and v & 0x8000:
            v -= 0x10000
    return v & MASK


def lit_store_bytes(ram_known, abs_addr, size, value):
    """Record a KNOWN store of `value` (size bytes) at literal absolute address
    `abs_addr` in ram_known; pass value=None to invalidate the slot (an unknown
    write makes any later load from it non-foldable).  No-op for non-RAM
    addresses (ROM stores never fold RAM reads)."""
    a = abs_addr & MASK
    if classify_addr(a) != 'RAM':
        return
    for i in range(size):
        if value is None:
            ram_known.pop((a + i) & MASK, None)
        else:
            ram_known[(a + i) & MASK] = (value >> (8 * (size - 1 - i))) & 0xFF


def decode_mem(opcode_hi_word, opcode_lo_word_or_None=None, ctx=None):
    """Decode a SH-2 b/w/l memory op into a C fragment (v2 generator).

    See the module docstring for the full contract.  Returns None when the
    opcode is not a covered memory op or its base register is neither a param
    (r4..r7) nor resolvable via ctx['resolve'] — the generator then rejects the
    function.  The returned dict always carries at least:
        {'kind': 'mem', 'size': 1|2|4, 'dir': 'load'|'store',
         'base': 'param'|'literal', 'c': [C statements], ...}
    plus extra keys the generator may use: 'temp' (load temp name), 'dest' /
    'src' (register index), 'base_reg', 'disp' (scaled byte offset), 'idx',
    'auto' ('post'|'pre'|None), 'sext' (True for mov.b/mov.w loads, which the
    emulator sign-extends), 'ann' (disassembly-style annotation), 'uses'.
    `opcode_lo_word_or_None` is reserved for the generator's uniform two-word
    decode interface; every SH-2 memory op here is single-word (displacements
    live in the hi word), so it is accepted and ignored.
    """
    ctx = ctx or {}
    temp = ctx.get('temp') or _default_temp
    op = opcode_hi_word & 0xFFFF
    n = (op >> 8) & 0xF
    m = (op >> 4) & 0xF
    n0 = op >> 12
    nib = op & 0xF

    def mem(kind, size, base_reg, src, dest, disp_off, idx, auto, ann):
        rb = _resolve_base(ctx, base_reg)
        if rb is None:
            return None
        base_kind, abs_addr = rb
        eff, eff_abs = _eff_addr(base_kind, 'r%d' % base_reg, disp_off, idx, abs_addr)
        if kind == 'load':
            t = temp()
            c = ['uint32_t %s = *(volatile %s*)%s;' % (t, _CTYPE[size], eff)]
            if eff_abs is not None:
                c[0] += _ram_note(eff_abs)
            if auto == 'post':
                c.append('r%d = r%d + %d;' % (base_reg, base_reg, size))
            return {'kind': 'mem', 'size': size, 'dir': 'load', 'base': base_kind,
                    'c': c, 'temp': t, 'dest': dest, 'base_reg': base_reg,
                    'disp': disp_off, 'idx': idx, 'auto': auto,
                    'sext': size < 4, 'ann': ann,
                    'uses': {t} | {'r%d' % base_reg} | ({'r0'} if idx else set())}
        c = ['*(volatile %s*)%s = r%d;' % (_CTYPE[size], eff, src)]
        if eff_abs is not None:
            c[0] += _ram_note(eff_abs)
        if auto == 'pre':
            c.append('r%d = r%d - %d;' % (base_reg, base_reg, size))
        return {'kind': 'mem', 'size': size, 'dir': 'store', 'base': base_kind,
                'c': c, 'src': src, 'base_reg': base_reg,
                'disp': disp_off, 'idx': idx, 'auto': auto,
                'sext': False, 'ann': ann,
                'uses': {'r%d' % src, 'r%d' % base_reg} | ({'r0'} if idx else set())}

    # ---- loads @Rn / @Rn+ -> Rd  (0x6n00/10/20, 0x6n40/50/60) ----
    if n0 == 0x6 and nib in (0, 1, 2, 4, 5, 6):
        size = _SIZE_NIB[nib]
        auto = 'post' if nib >= 4 else None
        ann = 'mov.%s @r%d%s,r%d' % (_SIZE_CH[size], m, '+' if auto else '', n)
        return mem('load', size, m, None, n, 0, None, auto, ann)

    # ---- stores Rs -> @Rn / @-Rn  (0x2n00/10/20, 0x2n40/50/60) ----
    if n0 == 0x2 and nib in (0, 1, 2, 4, 5, 6):
        size = _SIZE_NIB[nib]
        # @-Rn: sh2emu captures the value first, then r[n]-=size and writes to
        # the decremented address -> bake -size into the address expression and
        # append the register update AFTER the store (src==base stays correct).
        auto = 'pre' if nib >= 4 else None
        disp_off = -size if auto == 'pre' else 0
        ann = 'mov.%s r%d,@%sr%d' % (_SIZE_CH[size], m, '-' if auto else '', n)
        return mem('store', size, n, m, None, disp_off, None, auto, ann)

    # ---- 4-bit-displacement mov.l forms (additive v6): 0x5nmd loads and
    # 0x1nmd stores with disp = nib*4 (0,4,..,60), exactly sh2emu n0==0x5
    # (`r[n] = rd(r[m] + nib*4, 4)`) and n0==0x1 (`wr(r[n] + nib*4, 4, r[m])`).
    # These were previously 'unmapped' (only _mem_shape knew their shape for
    # the r15/r14 stack path).  Size is always 4, no sign-extend, no auto;
    # base resolution is the standard param/literal rule. ----
    if n0 == 0x5:
        ann = 'mov.l @(0x%X,r%d),r%d' % (nib * 4, m, n)
        return mem('load', 4, m, None, n, nib * 4, None, None, ann)
    if n0 == 0x1:
        ann = 'mov.l r%d,@(0x%X,r%d)' % (m, nib * 4, n)
        return mem('store', 4, n, m, None, nib * 4, None, None, ann)

    # ---- R0-only 4-bit displacement forms  (stores 0x80/81/82, loads 0x84/85/86) ----
    f = op & 0xFF00
    if f in (0x8000, 0x8100, 0x8200, 0x8400, 0x8500, 0x8600):
        size = _SIZE_NIB[(op >> 8) & 0xF]
        disp_off = (op & 0xF) * size
        if f in (0x8000, 0x8100, 0x8200):
            ann = 'mov.%s r0,@(0x%X,r%d)' % (_SIZE_CH[size], disp_off, m)
            return mem('store', size, m, 0, None, disp_off, None, None, ann)
        ann = 'mov.%s @(0x%X,r%d),r0' % (_SIZE_CH[size], disp_off, m)
        return mem('load', size, m, None, 0, disp_off, None, None, ann)

    # ---- indexed @(R0,Rn): stores 0x0nm4/5/6, loads 0x0nmC/D/E ----
    if op & 0xF00F in (0x0004, 0x0005, 0x0006):
        size = _SIZE_NIB[nib]
        ann = 'mov.%s r%d,@(r0,r%d)' % (_SIZE_CH[size], m, n)
        return mem('store', size, n, m, None, 0, 'r0', None, ann)
    if op & 0xF00F in (0x000C, 0x000D, 0x000E):
        size = _SIZE_NIB[nib]
        ann = 'mov.%s @(r0,r%d),r%d' % (_SIZE_CH[size], m, n)
        return mem('load', size, m, None, n, 0, 'r0', None, ann)

    # ---- SR system-register memory forms (additive, real): stc.l SR,@-Rn
    # (0x4n03) / ldc.l @Rn+,SR (0x4n07) — sh2emu._exec 0x4n03/0x4n07.  Base
    # resolution is exactly the param/literal rule of the other mem forms (a
    # r15/r14 stack base falls through _resolve_base -> None and is rejected,
    # as documented).  The value transferred is the `sr` state, not an rN, so
    # src/dest stay None and 'sr_src'/'sr_dest' flag the op for the generator —
    # _scan_mem_function only consumes size/dir/base_reg/auto (selection), and
    # gen_c_lift_v3.walk_v3 renders the record itself (c_lift_ops.decode_mem
    # dicts are never re-rendered by _mem_record for these).
    if op & 0xF0FF == 0x4003:    # stc.l SR,@-Rn: rn -= 4; wr(rn, 4, sr)
        rb = _resolve_base(ctx, n)
        if rb is None:
            return None
        base_kind, abs_addr = rb
        eff, eff_abs = _eff_addr(base_kind, 'r%d' % n, -4, None, abs_addr)
        c = ['*(volatile uint32_t*)%s = sr;' % eff]
        if eff_abs is not None:
            c[0] += _ram_note(eff_abs)
        c.append('r%d = r%d - 4;' % (n, n))
        return {'kind': 'mem', 'size': 4, 'dir': 'store', 'base': base_kind,
                'c': c, 'src': None, 'base_reg': n, 'disp': -4, 'idx': None,
                'auto': 'pre', 'sext': False, 'ann': 'stc.l SR,@-r%d' % n,
                'uses': {'sr', 'r%d' % n}, 'sr_src': True}
    if op & 0xF0FF == 0x4007:    # ldc.l @Rn+,SR: sr = rd(rn, 4); rn += 4
        rb = _resolve_base(ctx, n)
        if rb is None:
            return None
        base_kind, abs_addr = rb
        eff, eff_abs = _eff_addr(base_kind, 'r%d' % n, 0, None, abs_addr)
        t = temp()
        c = ['uint32_t %s = *(volatile uint32_t*)%s;' % (t, eff)]
        if eff_abs is not None:
            c[0] += _ram_note(eff_abs)
        c.append('sr = %s;' % t)
        c.append('r%d = r%d + 4;' % (n, n))
        return {'kind': 'mem', 'size': 4, 'dir': 'load', 'base': base_kind,
                'c': c, 'temp': t, 'dest': None, 'base_reg': n, 'disp': 0,
                'idx': None, 'auto': 'post', 'sext': False,
                'ann': 'ldc.l @r%d+,SR' % n, 'uses': {'sr', 'r%d' % n, t},
                'sr_dest': True}

    # ---- sts.l / lds.l mach/macl/pr stack/memory forms (additive, real):
    # mirror sh2emu._exec n0==0x4 `op & 0xF0FF` lines 450-455.  The transferred
    # value is a multiply system register (mach/macl/pr), NOT an rN, so src/dest
    # stay None and 'sys_src'/'sys_dest' + 'sys_reg' flag the transfer for the
    # generator — the exact same contract as the SR forms (0x4n03/0x4n07 above).
    # Base resolution is the standard param/literal rule; a r15/r14 stack base
    # falls through _resolve_base -> None and is rejected, exactly as documented
    # for the SR forms (the SH-2 prologue/epilogue sts.l/lds.l pr use r15).
    # NOTE: gen_c_lift_v3.walk_v3 special-cases ONLY 0x4003/0x4007 (SR); these
    # six encodings need a matching walker block to render end-to-end (out of
    # scope here).  The decode dicts are nevertheless 1:1 with the oracle and
    # carry self-contained 'py' mirror fragments for the differential test.
    if op & 0xF0FF in (0x4002, 0x4012, 0x4022):    # sts.l mach/macl/pr,@-Rn
        reg = {0x4002: 'mach', 0x4012: 'macl', 0x4022: 'pr'}[op & 0xF0FF]
        rb = _resolve_base(ctx, n)
        if rb is None:
            return None
        base_kind, abs_addr = rb
        eff, eff_abs = _eff_addr(base_kind, 'r%d' % n, -4, None, abs_addr)
        c = ['*(volatile uint32_t*)%s = %s;' % (eff, reg)]
        if eff_abs is not None:
            c[0] += _ram_note(eff_abs)
        c.append('r%d = r%d - 4;' % (n, n))
        py = ['_wrw(ram, (r[%d] - 4) & 0xFFFFFFFF, 4, %s)' % (n, reg),
              'r[%d] = (r[%d] - 4) & 0xFFFFFFFF' % (n, n)]
        return {'kind': 'mem', 'size': 4, 'dir': 'store', 'base': base_kind,
                'c': c, 'src': None, 'base_reg': n, 'disp': -4, 'idx': None,
                'auto': 'pre', 'sext': False, 'ann': 'sts.l %s,@-r%d' % (reg, n),
                'uses': {reg, 'r%d' % n}, 'sys_src': True, 'sys_reg': reg, 'py': py}
    if op & 0xF0FF in (0x4006, 0x4016, 0x4026):    # lds.l @Rn+,mach/macl/pr
        reg = {0x4006: 'mach', 0x4016: 'macl', 0x4026: 'pr'}[op & 0xF0FF]
        rb = _resolve_base(ctx, n)
        if rb is None:
            return None
        base_kind, abs_addr = rb
        eff, eff_abs = _eff_addr(base_kind, 'r%d' % n, 0, None, abs_addr)
        t = temp()
        c = ['uint32_t %s = *(volatile uint32_t*)%s;' % (t, eff)]
        if eff_abs is not None:
            c[0] += _ram_note(eff_abs)
        c.append('%s = %s;' % (reg, t))
        c.append('r%d = r%d + 4;' % (n, n))
        py = ['%s = _rdw(ram, r[%d], 4)' % (reg, n),
              'r[%d] = (r[%d] + 4) & 0xFFFFFFFF' % (n, n)]
        return {'kind': 'mem', 'size': 4, 'dir': 'load', 'base': base_kind,
                'c': c, 'temp': t, 'dest': None, 'base_reg': n, 'disp': 0,
                'idx': None, 'auto': 'post', 'sext': False,
                'ann': 'lds.l @r%d+,%s' % (n, reg),
                'uses': {reg, 'r%d' % n, t}, 'sys_dest': True, 'sys_reg': reg,
                'py': py}

    # ---- mac.l @Rm+,@Rn+ (0x0nmF) — additive.  sh2emu._exec n0==0x0 nib==0xF
    # reads TWO 32-bit words (signed) at r[m]/r[n], post-increments BOTH, then
    # accumulates 64-bit: MAC = ((mach<<32)|macl) sign-adjusted + a*b, saturated
    # to 64-bit when SR bit 1 (S) is set.  Two independent base registers make
    # this unlike every single-base mem form: the decode returns None unless
    # BOTH r[m] and r[n] resolve (param r4..r7 / known literal) — exactly the
    # _resolve_base rule applied twice.  With dynamic bases (the common rN data
    # pointer case) it returns None, so the v3 generator keeps rejecting the
    # function as before (no behavior change).  The dict is self-contained
    # (kind 'mac') with C + 'py' mirror fragments 1:1 to the oracle; the
    # generator has no emission path for it yet (out of scope here).
    if n0 == 0x0 and nib == 0xF:            # mac.l @Rm+,@Rn+ (0x0nmF)
        rb_m = _resolve_base(ctx, m)
        rb_n = _resolve_base(ctx, n)
        if rb_m is None or rb_n is None:
            return None
        bm_kind, am_addr = rb_m
        bn_kind, an_addr = rb_n
        eff_m, em_abs = _eff_addr(bm_kind, 'r%d' % m, 0, None, am_addr)
        eff_n, en_abs = _eff_addr(bn_kind, 'r%d' % n, 0, None, an_addr)
        c = ['int32_t _ma = (int32_t)*(volatile uint32_t*)%s;' % eff_m,
             'int32_t _mb = (int32_t)*(volatile uint32_t*)%s;' % eff_n]
        if em_abs is not None:
            c[0] += _ram_note(em_abs)
        if en_abs is not None:
            c[1] += _ram_note(en_abs)
        c += ['r%d = r%d + 4;' % (m, m), 'r%d = r%d + 4;' % (n, n),
              '{ int64_t _p = (int64_t)_ma * _mb;'
              ' int64_t _mac = (int64_t)(((uint64_t)(uint32_t)mach << 32) | (uint32_t)macl);'
              ' int64_t _res = _mac + _p;'
              ' if ((sr >> 1) & 1u) {'
              '   if (_res > 0x7FFFFFFFFFFFFFFFLL) _res = 0x7FFFFFFFFFFFFFFFLL;'
              '   else if (_res < (-0x8000000000000000LL)) _res = -0x8000000000000000LL; }'
              ' mach = (uint32_t)(_res >> 32); macl = (uint32_t)_res; }']
        py = ['_ma = s32(_rdw(ram, r[%d], 4))' % m,
              '_mb = s32(_rdw(ram, r[%d], 4))' % n,
              'r[%d] = (r[%d] + 4) & 0xFFFFFFFF' % (m, m),
              'r[%d] = (r[%d] + 4) & 0xFFFFFFFF' % (n, n),
              '_mac = ((mach << 32) | macl) & 0xFFFFFFFFFFFFFFFF',
              'if _mac >= 0x8000000000000000: _mac -= 0x10000000000000000',
              '_res = _mac + _ma * _mb',
              'if (sr >> 1) & 1:',
              '    if _res > 0x7FFFFFFFFFFFFFFF: _res = 0x7FFFFFFFFFFFFFFF',
              '    elif _res < -0x8000000000000000: _res = -0x8000000000000000',
              'mach = (_res >> 32) & 0xFFFFFFFF',
              'macl = _res & 0xFFFFFFFF']
        return {'kind': 'mac', 'dir': 'load', 'size': 4,
                'base_reg': n, 'auto': 'post', 'sext': False,
                'base': bn_kind, 'base2_reg': m, 'base2': bm_kind,
                'ann': 'mac.l @r%d+,@r%d+' % (m, n),
                'c': c, 'py': py, 'uses': {'mach', 'macl', 'sr',
                                           'r%d' % m, 'r%d' % n}}

    return None  # not a covered memory op


# ---------------------------------------------------------------------------
# v6 (additive): GBR byte bit-ops — decode_gbr_bit().  These are the 0xCC-CF
# forms sh2emu executes but gen_c_lift._decode_gbr (0xC0-C6 only) and
# decode_mem leave 'unmapped':  the address is GBR + R0 (indexed, not a
# displacement), and the op reads/writes ONE byte with an 8-bit immediate:
#   0xCC00 tst.b #imm,@(r0,GBR):  T = (rd(gbr+r0,1) & imm) == 0
#   0xCD00 and.b #imm,@(r0,GBR):  wr(gbr+r0,1, rd(gbr+r0,1) & imm)
#   0xCE00 xor.b #imm,@(r0,GBR):  wr(gbr+r0,1, rd(gbr+r0,1) ^ imm)
#   0xCF00 or.b  #imm,@(r0,GBR):  wr(gbr+r0,1, rd(gbr+r0,1) | imm)
# (semantics verbatim from sh2emu._exec n0==0xC).  The caller (gen_c_lift scan
# / walk_v3) resolves GBR and R0 to a constant absolute address — both must be
# known literals at scan time — and passes it via ctx['gbr'] = int; the C/py
# fragments bake that address (RAM note like the other literal-base ops), which
# is 1:1 with sh2emu when the literals are genuinely constant (same contract as
# the 0xC0-C6 GBR mov forms).  tst.b sets T only; and/xor/or read-modify-write
# the byte and touch no integer register.  Returns None for any non-0xCC-CF
# opcode; returns {'kind':'gbr_bit','unresolved':True,...} when ctx['gbr'] is
# missing/None (encoding recognized, base not yet resolved — the caller
# rejects).  The mirror fragments need `_rdw`/`_wrw`/`ram` (+ T for tst.b) in
# the exec ns, exactly like decode_mem's py cousins.
# ---------------------------------------------------------------------------
_GBR_BIT_FAMILY = {0xCC00: ('tst', 'load', 'tst.b #0x%02X,@(r0,gbr)'),
                   0xCD00: ('and', 'rmw', 'and.b #0x%02X,@(r0,gbr)'),
                   0xCE00: ('xor', 'rmw', 'xor.b #0x%02X,@(r0,gbr)'),
                   0xCF00: ('or',  'rmw', 'or.b  #0x%02X,@(r0,gbr)')}


def gbr_mov_runtime(size, gdir, disp, temp):
    """C + py for a 0xC0-C6 GBR-relative b/w/l op with GBR as a RUNTIME base
    (caller-supplied register, not a baked literal): EA = gbr + r0 + disp.
    `disp` is the already-scaled displacement (as gen_c_lift._decode_gbr
    returns it).  The C uses the `gbr` parameter and `r0`; the mirror uses
    ns['gbr'] and r[0].  Semantics match sh2emu exactly:
      mov.b/w/l r0,@(disp,gbr) -> wr(gbr + r0 + disp, size, r0)
      mov.b/w/l @(disp,gbr),r0 -> r0 = sext/rd(gbr + r0 + disp, size)"""
    d = '0x%X' % disp
    if gdir == 'load':
        t = temp()
        if size < 4:
            c = ['uint32_t %s = %s*(volatile %s*)(gbr + r0 + %s);' % (t, _SEXT_C[size], _CTYPE[size], d),
                 'r0 = %s;' % t]
            py = ['r[0] = %s(_rdw(ram, (gbr + r[0] + %s), %d))' % (_SEXT_PY[size], d, size)]
        else:
            c = ['uint32_t %s = *(volatile %s*)(gbr + r0 + %s);' % (t, _CTYPE[size], d),
                 'r0 = %s;' % t]
            py = ['r[0] = _rdw(ram, (gbr + r[0] + %s), %d)' % (d, size)]
    else:
        c = ['*(volatile %s*)(gbr + r0 + %s) = r0;' % (_CTYPE[size], d)]
        py = ['_wrw(ram, (gbr + r[0] + %s), %d, r[0])' % (d, size)]
    return c, py


def decode_gbr_bit(op, pc, rom, ctx=None):
    """Decode a 0xCC-CF GBR byte bit-op -> semantic dict (additive v6 API).

    `ctx['gbr']` is the resolved constant absolute address (GBR literal + R0
    literal) baked into the C/py fragments; with `ctx['gbr_runtime']` truthy the
    address is emitted as the runtime expression (gbr + r0) / (gbr + r[0])
    (mirror ns carries `gbr`); without either the dict is returned with
    'unresolved': True (encoding recognized, base unresolved).  The dict:
        {'kind': 'gbr_bit', 'family': 'tst'|'and'|'xor'|'or',
         'dir': 'load'|'rmw', 'size': 1, 'imm': int,
         'c': [C statements], 'py': [mirror statements], 'uses': set,
         'ann': mnemonic}
    """
    fam = _GBR_BIT_FAMILY.get(op & 0xFF00)
    if fam is None:
        return None
    family, gdir, mnem = fam
    lo = op & 0xFF
    ann = mnem % lo
    ctx = ctx or {}
    gbr = ctx.get('gbr')
    if gbr is None and not ctx.get('gbr_runtime'):
        return {'kind': 'gbr_bit', 'family': family, 'dir': gdir, 'size': 1,
                'imm': lo, 'unresolved': True, 'c': [], 'py': [],
                'uses': set(), 'ann': ann}
    if ctx.get('gbr_runtime'):
        # runtime GBR: EA = gbr + r0 (both live registers).  sh2emu semantics:
        #   tst.b #imm,@(r0,gbr): T = (rd(gbr + r0, 1) & imm) == 0
        #   and/xor/or.b #imm,@(r0,gbr): RMW on rd/wr(gbr + r0, 1)
        addr_c = '(gbr + r0)'
        addr_py = '(gbr + r[0])'
        note = ''
    else:
        gbr &= MASK
        note = (' /* RAM 0x%08X */' % gbr if classify_addr(gbr) == 'RAM'
                else ' /* ROM */')
        addr_c = '0x%08X' % gbr
        addr_py = '0x%08X' % gbr
    if family == 'tst':
        c = ['T = ((*(volatile uint8_t*)%s & 0x%02Xu) == 0u) ? 1u : 0u;%s'
             % (addr_c, lo, note)]
        py = ['T = 1 if (_rdw(ram, %s, 1) & 0x%02X) == 0 else 0' % (addr_py, lo)]
        uses = {'T'}
    else:
        c = ['*(volatile uint8_t*)%s %s= 0x%02Xu;%s'
             % (addr_c, {'and': '&', 'xor': '^', 'or': '|'}[family], lo, note)]
        py = ['_wrw(ram, %s, 1, _rdw(ram, %s, 1) %s 0x%02X)'
              % (addr_py, addr_py, {'and': '&', 'xor': '^', 'or': '|'}[family], lo)]
        uses = set()
    return {'kind': 'gbr_bit', 'family': family, 'dir': gdir, 'size': 1,
            'imm': lo, 'c': c, 'py': py, 'uses': uses, 'ann': ann}


# ---------------------------------------------------------------------------
# v3: branch/return decode API — branch_info() + C/mirror templates for the
# generator's branch emission (bt/bf/bt.s/bf.s/bra/rts).  Purely additive:
# translate() above is untouched for these opcodes and gen_c_lift.py still
# rejects every branch ('branch' / 'branch_v3'), so v1/v2 consumers see no
# change.  The mirror uses T as its internal branch flag, exactly as
# translate()'s cond_py does; the C uses T only inside the generator-emitted
# `if (T) goto L_...;` / `if (!T) goto L_...;` (delay slot first when delayed).
# ---------------------------------------------------------------------------

# C templates, rendered with the resolved target address (the generator fills
# `%x` with the target: bt/bf/bt.s/bf.s target = P+4 + s8(low byte)*2, bra
# target = P+4 + s12*2).  bt.s/bf.s reuse bt/bf — branch_info()['delayed']
# tells the generator to emit the delay slot BEFORE the branch.  'rte' has NO
# template: the generator rejects it.
BRANCH_C_TEMPLATE = {
    'bt':  'if (T) goto L_%x;',
    'bts': 'if (T) goto L_%x;',
    'bf':  'if (!T) goto L_%x;',
    'bfs': 'if (!T) goto L_%x;',
    'bra': 'goto L_%x;',
    'rts': 'return r0; /* delay slot handled by generator */',
}

# Mirror equivalents for the test's ref() model: a branch is a pc update using
# T as the internal flag; rts returns through PR (`pc = pr`).
BRANCH_PY_TEMPLATE = {
    'bt':  'pc = %#x if T else pc',
    'bts': 'pc = %#x if T else pc',
    'bf':  'pc = %#x if not T else pc',
    'bfs': 'pc = %#x if not T else pc',
    'bra': 'pc = %#x',
    'rts': 'pc = pr',
}


def branch_info(opcode_hi):
    """Decode a SH-2 branch/return opcode (v3 API).

    `opcode_hi` is the 16-bit opcode word.  Returns
        {'kind': 'bt'|'bf'|'bts'|'bfs'|'bra'|'rts'|'rte'|None,
         'delayed': bool,
         'target_disp': int|None}
    or None when `opcode_hi` is not a branch/return opcode.  target_disp is the
    raw displacement, sign-extended to 32 bits; the caller resolves the target
    as (P + 4 + target_disp * 2) for bt/bf/bt.s/bf.s/bra (P = opcode address).
    rts/rte have no displacement: target_disp is None — rts target is PR (the
    mirror is `pc = pr`), rte target is SPC/SSR and has NO template (the
    generator rejects it).  delayed is True for bt.s/bf.s/bra/rts/rte (the
    delay slot executes first), False for bt/bf.
    """
    op = opcode_hi & 0xFFFF
    d8 = s8(op & 0xFF)
    if op == 0x000B:                                    # rts (delayed, PR)
        return {'kind': 'rts', 'delayed': True, 'target_disp': None}
    if op == 0x002B:                                    # rte (delayed, SPC/SSR)
        return {'kind': 'rte', 'delayed': True, 'target_disp': None}
    if op & 0xFF00 == 0x8900:                           # bt
        return {'kind': 'bt', 'delayed': False, 'target_disp': d8}
    if op & 0xFF00 == 0x8B00:                           # bf
        return {'kind': 'bf', 'delayed': False, 'target_disp': d8}
    if op & 0xFF00 == 0x8D00:                           # bt/s
        return {'kind': 'bts', 'delayed': True, 'target_disp': d8}
    if op & 0xFF00 == 0x8F00:                           # bf/s
        return {'kind': 'bfs', 'delayed': True, 'target_disp': d8}
    if op & 0xF000 == 0xA000:                           # bra (12-bit disp)
        d12 = op & 0xFFF
        if d12 & 0x800:
            d12 -= 0x1000
        return {'kind': 'bra', 'delayed': True, 'target_disp': d12}
    if op & 0xF0FF == 0x0003 and (op >> 12) == 0:       # bsrf Rn (delayed, dynamic)
        return {'kind': 'bsrf', 'delayed': True, 'target_disp': None,
                'reg': (op >> 8) & 0xF}
    if op & 0xF0FF == 0x0023 and (op >> 12) == 0:       # braf Rn (delayed, dynamic)
        return {'kind': 'braf', 'delayed': True, 'target_disp': None,
                'reg': (op >> 8) & 0xF}
    return None


# ---------------------------------------------------------------------------
# v4 (additive): SH-2E FPU decode — decode_fpu().  translate() is untouched and
# still returns None for every FPU opcode, so v1/v2/v3 consumers see no change;
# gen_c_lift_v3.py's dryrun-only pool_fpu counter is the first consumer.
#
# Every opcode's semantics mirrors tools/sh2emu.py's 0xF___ block EXACTLY:
#   fadd/fsub/fmul/fdiv FRm,FRn        F0n0..F0n3  frn = ts(frn op frm)
#   fcmp/eq / fcmp/gt Fm,Fn            F0n4/F0n5   T = (frn==frm) / (frn>frm)
#   fmov.s @(R0,Rm),FRn                F0n6        frn = rdf(r0+rm)   (mem)
#   fmov.s FRm,@(R0,Rn)                F0n7        wrf(r0+rn, frm)    (mem)
#   fmov.s @Rm,FRn                     F0n8        (mem)
#   fmov.s @Rm+,FRn                    F0n9        (mem, rm += 4)
#   fmov.s FRm,@Rn                     F0nA        (mem)
#   fmov.s FRm,@-Rn                    F0nB        (mem, rn -= 4)
#   fmov FRm,FRn                       F0nC        frn = frm
#   fsts FPUL,FRn / flds FRn,FPUL      F0nD0/F0nD1 bit pattern <-> fpul
#   float FPUL,FRn / ftrc FRn,FPUL     F0nD2/F0nD3 int32 <-> trunc
#   fneg FRn / fabs FRn                F0nD4/F0nD5
#   fsqrt FRn                          F0nD6
#   fldi0 FRn / fldi1 FRn              F0nD8/F0nD9  0.0 / 1.0
#   fsca FPUL,FR(2k)/FR(2k+1)          FFnD        fr2k=sin(f),fr2k+1=cos(f)
#                                               f = s32(fpul)*2pi/65536 (full
#                                               32-bit signed fraction,
#                                               0x10000 == 2pi; double->float32)
#   fmac FR0,FRm,FRn                   F0nE        frn = ts(fr0*frm+frn)
#   sts fpul/fpscr,Rn / lds Rn,fpul/fpscr            0x005A/0x006A/0x405A/0x406A
#   sts.l fpul/fpscr,@-Rn / lds.l @Rn+,fpul/fpscr    0x4052/0x4062/0x4056/0x4066
# Reserved encodings sh2emu raises NotImplementedError for (0xFnnF, the
# F0nD7/F0nDA-F sub-slots) decode to None — they count as fpu/altre rejects.
#
# Register model: FR0..FR15 are uint32_t frN C locals holding the IEEE-754
# single-precision BIT PATTERN; the Python mirror holds FRs as float32 values
# (sh2emu semantics).  The mirror fragments are float32-exact via struct and
# need `ts`, `bits2f`, `f2bits` in the exec ns (c_lift_ops exports them; a
# future FPU emission adds them to the `from c_lift_ops import ...` line) plus
# the existing `_rdw`/`_wrw`/`ram` for the fmov.s memory forms.
#
# Known limits (documented, not modeled):
#   - FPSCR flags (V/ZD/IM/...) and the RM rounding-mode bits are NOT modeled
#     (sh2emu doesn't either): every op is round-to-nearest-even single.
#   - NaN payloads/signaling behavior are best-effort (Python float vs the
#     hardware FPU differ); fcmp/eq and fcmp/gt use plain == / > as sh2emu.
#   - Denormals are kept (ts() does not flush; hardware may).
#   - ftrc NaN -> 0x80000000 and the +/-overflow saturation match sh2emu.
#   - fmov.s memory forms read/write 4 big-endian bytes == the frN bit pattern.
#   - C arithmetic uses an anonymous union with `float` ops; fmac promotes its
#     operands to double so the result rounds exactly once (SH-2E/s hm2emu
#     single-rounding semantics: frn = ts(fr0*frm+frn)).  The Python mirror
#     computes in double then rounds via ts(), matching sh2emu bit-for-bit
#     (the mirror is the differential oracle; the C is a human-verifiable
#     draft).  fsqrt C needs <math.h> (future emission adds it next to
#     <stdint.h>).
# ---------------------------------------------------------------------------

def ts(x):
    """Round a Python float to IEEE-754 single precision (identical to sh2emu)."""
    try:
        return struct.unpack('>f', struct.pack('>f', x))[0]
    except OverflowError:
        return float('inf') if x > 0 else float('-inf')


def f2bits(v):
    """float32 value -> 32-bit IEEE-754 bit pattern (big-endian), as sh2emu."""
    return struct.unpack('>I', struct.pack('>f', ts(v)))[0]


def bits2f(b):
    """32-bit IEEE-754 bit pattern -> float32 value, as sh2emu."""
    return struct.unpack('>f', struct.pack('>I', b & MASK))[0]


def is_fpu_op(op):
    """SH-2E FPU block (0xF___) or the FPUL/FPSCR system transfers."""
    return (op & 0xF000 == 0xF000 or
            op & 0xF0FF in (0x005A, 0x006A, 0x405A, 0x406A,
                            0x4052, 0x4056, 0x4062, 0x4066))


def decode_fpu(op, pc, rom, ctx=None):
    """Decode a SH-2E FPU opcode -> semantic dict (additive v4 API).

    Returns None when `op` is not an FPU opcode, or is an FPU encoding sh2emu
    does NOT execute (reserved sub-slots — the caller rejects fpu/altre).
    Pure register/FPUL ops return {'kind': 'fpu', 'c': [...], 'py': [...],
    'uses': set, 'ann': ...}; the fmov.s / sts.l / lds.l memory forms return
    {'kind': 'fpu_mem', ...} mirroring decode_mem's contract ('dir', 'size',
    'base': 'param'|'literal'|'unresolved', 'base_reg', 'idx', 'auto',
    'dest'/'src' as FR index or 'fpul'/'fpscr', plus 'c'/'py'/'uses'/'ann').
    Memory-form base resolution uses ctx['resolve'] exactly like decode_mem;
    an unresolvable base yields {'kind': 'fpu_mem', 'unresolved': True, ...}
    so the caller can reject base_unresolved (not fpu/altre).
    """
    op &= 0xFFFF
    n = (op >> 8) & 0xF
    m = (op >> 4) & 0xF
    n0 = op >> 12
    nib = op & 0xF

    def pure(c, py, uses, mnem):
        return {'kind': 'fpu', 'c': [c], 'py': [py],
                'uses': set(uses), 'ann': mnem}

    if n0 == 0xF:
        # fsca FPUL,FR(2k)/FR(2k+1) = 0xFFnD (SH-2E FPU; encoding
        # 1111 0nnn 1111 1101, k = bits 11-9, DRn = FR2k/FR2k+1).  FPUL is the
        # FULL 32-bit signed angle fraction (0x10000 == 360 deg == 2*pi rad);
        # FR(2k) = sin, FR(2k+1) = cos, abs err < 2^-21.  Matched BEFORE the
        # nib==0xD sub-dispatch (which treats 0xFFnD as reserved).  C emits
        # sinf/cosf (double angle rounded to float32 by the call); mirror +
        # sh2emu run the identical double formula rounded once by ts(), so the
        # differential pair is bit-exact by construction.  Requires `math`
        # (mirror test ns) and <math.h> (lift, added by gen_c_lift when
        # _records_have_fpu) — both already wired for the FPU path.
        if (op & 0xF1FF) == 0xF0FD:
            k = (op >> 9) & 0x7
            f2k, f2k1 = 'fr%d' % (2 * k), 'fr%d' % (2 * k + 1)
            return pure('{ union { uint32_t u; float f; } _a, _b;'
                        ' _a.f = sinf((float)((double)(int32_t)fpul'
                        ' * (2.0 * 3.14159265358979323846 / 65536.0)));'
                        ' _b.f = cosf((float)((double)(int32_t)fpul'
                        ' * (2.0 * 3.14159265358979323846 / 65536.0)));'
                        ' %s = _a.u; %s = _b.u; }' % (f2k, f2k1),
                        'fr[%d] = ts(math.sin(s32(fpul) * (2.0 * math.pi / 65536.0)));'
                        ' fr[%d] = ts(math.cos(s32(fpul) * (2.0 * math.pi / 65536.0)))'
                        % (2 * k, 2 * k + 1),
                        [f2k, f2k1, 'fpul'], 'fsca fpul,%s/%s' % (f2k, f2k1))
        frn, frm = 'fr%d' % n, 'fr%d' % m
        # ---- binary arithmetic (round-to-nearest single) ----
        if nib == 0x0:
            return pure('{ union { uint32_t u; float f; } _a, _b, _r;'
                        ' _a.u = %s; _b.u = %s; _r.f = _a.f + _b.f; %s = _r.u; }'
                        % (frn, frm, frn),
                        'fr[%d] = ts(fr[%d] + fr[%d])' % (n, n, m),
                        ['fr%d' % n, 'fr%d' % m], 'fadd %s,%s' % (frm, frn))
        if nib == 0x1:
            return pure('{ union { uint32_t u; float f; } _a, _b, _r;'
                        ' _a.u = %s; _b.u = %s; _r.f = _a.f - _b.f; %s = _r.u; }'
                        % (frn, frm, frn),
                        'fr[%d] = ts(fr[%d] - fr[%d])' % (n, n, m),
                        ['fr%d' % n, 'fr%d' % m], 'fsub %s,%s' % (frm, frn))
        if nib == 0x2:
            return pure('{ union { uint32_t u; float f; } _a, _b, _r;'
                        ' _a.u = %s; _b.u = %s; _r.f = _a.f * _b.f; %s = _r.u; }'
                        % (frn, frm, frn),
                        'fr[%d] = ts(fr[%d] * fr[%d])' % (n, n, m),
                        ['fr%d' % n, 'fr%d' % m], 'fmul %s,%s' % (frm, frn))
        if nib == 0x3:
            return pure('{ union { uint32_t u; float f; } _a, _b, _r;'
                        ' _a.u = %s; _b.u = %s; _r.f = _a.f / _b.f; %s = _r.u; }'
                        % (frn, frm, frn),
                        'fr[%d] = ts(fr[%d] / fr[%d])' % (n, n, m),
                        ['fr%d' % n, 'fr%d' % m], 'fdiv %s,%s' % (frm, frn))
        # ---- compare (T-flag only, as sh2emu) ----
        if nib == 0x4:
            return pure('{ union { uint32_t u; float f; } _a, _b;'
                        ' _a.u = %s; _b.u = %s;'
                        ' T = (_a.f == _b.f) ? 1u : 0u; }' % (frn, frm),
                        'T = 1 if fr[%d] == fr[%d] else 0' % (n, m),
                        ['T', 'fr%d' % n, 'fr%d' % m], 'fcmp/eq %s,%s' % (frm, frn))
        if nib == 0x5:
            return pure('{ union { uint32_t u; float f; } _a, _b;'
                        ' _a.u = %s; _b.u = %s;'
                        ' T = (_a.f > _b.f) ? 1u : 0u; }' % (frn, frm),
                        'T = 1 if fr[%d] > fr[%d] else 0' % (n, m),
                        ['T', 'fr%d' % n, 'fr%d' % m], 'fcmp/gt %s,%s' % (frm, frn))
        # ---- fmov.s memory forms ----
        if nib == 0x6:
            return _fpu_mem(op, 'load', m, 'r0', None, n, None, 0,
                            'fmov.s @(r0,r%d),%s' % (m, frn), ctx)
        if nib == 0x7:
            return _fpu_mem(op, 'store', n, 'r0', None, None, m, 0,
                            'fmov.s %s,@(r0,r%d)' % (frm, n), ctx)
        if nib == 0x8:
            return _fpu_mem(op, 'load', m, None, None, n, None, 0,
                            'fmov.s @r%d,%s' % (m, frn), ctx)
        if nib == 0x9:
            return _fpu_mem(op, 'load', m, None, 'post', n, None, 0,
                            'fmov.s @r%d+,%s' % (m, frn), ctx)
        if nib == 0xA:
            return _fpu_mem(op, 'store', n, None, None, None, m, 0,
                            'fmov.s %s,@r%d' % (frm, n), ctx)
        if nib == 0xB:
            return _fpu_mem(op, 'store', n, None, 'pre', None, m, -4,
                            'fmov.s %s,@-r%d' % (frm, n), ctx)
        # ---- register transfers ----
        if nib == 0xC:
            return pure('%s = %s;' % (frn, frm),
                        'fr[%d] = fr[%d]' % (n, m),
                        ['fr%d' % n, 'fr%d' % m], 'fmov %s,%s' % (frm, frn))
        if nib == 0xE:
            return pure('{ union { uint32_t u; float f; } _a, _b, _c, _r;'
                        ' _a.u = fr0; _b.u = %s; _c.u = %s;'
                        ' _r.f = (float)((double)_a.f * (double)_b.f + (double)_c.f);'
                        ' %s = _r.u; }'
                        % (frm, frn, frn),
                        'fr[%d] = ts(fr[0] * fr[%d] + fr[%d])' % (n, m, n),
                        ['fr0', 'fr%d' % m, 'fr%d' % n],
                        'fmac fr0,%s,%s' % (frm, frn))
        # ---- F0nD sub-encodings (m = sub-opcode) ----
        if nib == 0xD:
            if m == 0x0:    # fsts FPUL,FRn
                return pure('%s = fpul;' % frn, 'fr[%d] = bits2f(fpul)' % n,
                            ['fr%d' % n, 'fpul'], 'fsts fpul,%s' % frn)
            if m == 0x1:    # flds FRn,FPUL
                return pure('fpul = %s;' % frn, 'fpul = f2bits(fr[%d])' % n,
                            ['fr%d' % n, 'fpul'], 'flds %s,fpul' % frn)
            if m == 0x2:    # float FPUL,FRn (int32 -> float32)
                return pure('{ union { uint32_t u; float f; } _r;'
                            ' _r.f = (float)(int32_t)fpul; %s = _r.u; }' % frn,
                            'fr[%d] = ts(float(s32(fpul)))' % n,
                            ['fr%d' % n, 'fpul'], 'float fpul,%s' % frn)
            if m == 0x3:    # ftrc FRn,FPUL (trunc, NaN->0x80000000, saturate)
                return pure('{ union { uint32_t u; float f; } _a; _a.u = %s;'
                            ' if (_a.f != _a.f) fpul = 0x80000000u;'
                            ' else if (_a.f >= 2147483648.0f) fpul = 0x7FFFFFFFu;'
                            ' else if (_a.f < -2147483648.0f) fpul = 0x80000000u;'
                            ' else fpul = (uint32_t)(int32_t)_a.f; }' % frn,
                            'fpul = (0x80000000 if fr[%d] != fr[%d]'
                            ' else (0x7FFFFFFF if fr[%d] >= 2147483648.0'
                            ' else (0x80000000 if fr[%d] < -2147483648.0'
                            ' else int(fr[%d])))) & 0xFFFFFFFF' % (n, n, n, n, n),
                            ['fr%d' % n, 'fpul'], 'ftrc %s,fpul' % frn)
            if m == 0x4:    # fneg (bit sign flip == float negation)
                return pure('%s = %s ^ 0x80000000u;' % (frn, frn),
                            'fr[%d] = -fr[%d]' % (n, n),
                            ['fr%d' % n], 'fneg %s' % frn)
            if m == 0x5:    # fabs (clear sign bit == float abs)
                return pure('%s = %s & 0x7FFFFFFFu;' % (frn, frn),
                            'fr[%d] = abs(fr[%d])' % (n, n),
                            ['fr%d' % n], 'fabs %s' % frn)
            if m == 0x6:    # fsqrt (needs <math.h> in the lift)
                return pure('{ union { uint32_t u; float f; } _a, _r;'
                            ' _a.u = %s; _r.f = sqrtf(_a.f); %s = _r.u; }'
                            % (frn, frn),
                            'fr[%d] = ts(fr[%d] ** 0.5)' % (n, n),
                            ['fr%d' % n], 'fsqrt %s' % frn)
            if m == 0x8:    # fldi0
                return pure('%s = 0u;' % frn, 'fr[%d] = 0.0' % n,
                            ['fr%d' % n], 'fldi0 %s' % frn)
            if m == 0x9:    # fldi1
                return pure('%s = 0x3F800000u;' % frn, 'fr[%d] = 1.0' % n,
                            ['fr%d' % n], 'fldi1 %s' % frn)
        return None         # reserved sub-encoding: sh2emu raises (fpu/altre)
    # ---- FPUL / FPSCR system transfers (integer-value ops) ----
    f = op & 0xF0FF
    if f == 0x005A:
        return pure('r%d = fpul;' % n, 'r[%d] = fpul' % n,
                    ['r%d' % n, 'fpul'], 'sts fpul,r%d' % n)
    if f == 0x006A:
        return pure('r%d = fpscr;' % n, 'r[%d] = fpscr' % n,
                    ['r%d' % n, 'fpscr'], 'sts fpscr,r%d' % n)
    if f == 0x405A:
        return pure('fpul = r%d;' % n, 'fpul = r[%d]' % n,
                    ['r%d' % n, 'fpul'], 'lds r%d,fpul' % n)
    if f == 0x406A:
        return pure('fpscr = r%d;' % n, 'fpscr = r[%d]' % n,
                    ['r%d' % n, 'fpscr'], 'lds r%d,fpscr' % n)
    if f in (0x4052, 0x4062):                       # sts.l fpul/fpscr,@-Rn
        reg = 'fpul' if f == 0x4052 else 'fpscr'
        return _fpu_mem(op, 'store', n, None, 'pre', None, reg, -4,
                        'sts.l %s,@-r%d' % (reg, n), ctx)
    if f in (0x4056, 0x4066):                       # lds.l @Rn+,fpul/fpscr
        reg = 'fpul' if f == 0x4056 else 'fpscr'
        return _fpu_mem(op, 'load', n, None, 'post', reg, None, 0,
                        'lds.l @r%d+,%s' % (n, reg), ctx)
    return None


def _fpu_mem(op, dir_, base_reg, idx, auto, dest, src, off, mnem, ctx):
    """Build the fpu_mem dict for one fmov.s / sts.l / lds.l memory form.

    dest/src is an FR index (int) for fmov.s, or 'fpul'/'fpscr' for the system
    transfers.  Base resolution and the C address expression reuse the v2
    decode_mem helpers (_resolve_base / _eff_addr) so the base rules are
    identical (param r4..r7 / literal via ctx['resolve']; caller checks the
    'r0' index and the param-not-written condition)."""
    rb = _resolve_base(ctx, base_reg)
    if rb is None:
        return {'kind': 'fpu_mem', 'unresolved': True, 'dir': dir_,
                'base_reg': base_reg, 'idx': idx, 'auto': auto,
                'dest': dest, 'src': src, 'ann': mnem, 'c': [], 'py': [],
                'uses': set()}
    base_kind, abs_addr = rb
    eff, eff_abs = _eff_addr(base_kind, 'r%d' % base_reg, off, idx, abs_addr)
    if idx is not None:
        pyaddr = 'r[0] + r[%d]' % base_reg
    elif base_kind == 'literal':
        pyaddr = '0x%08X' % ((abs_addr + off) & MASK)
    else:
        pyaddr = 'r[%d]' % base_reg
    if dir_ == 'load':
        c = ['fr%d = *(volatile uint32_t*)%s;' % (dest, eff)] \
            if isinstance(dest, int) else \
            ['%s = *(volatile uint32_t*)%s;' % (dest, eff)]
        if eff_abs is not None:
            c[0] += _ram_note(eff_abs)
        if auto == 'post':
            c.append('r%d = r%d + 4;' % (base_reg, base_reg))
        if isinstance(dest, int):
            py = ['fr[%d] = bits2f(_rdw(ram, %s, 4))' % (dest, pyaddr)]
        else:
            py = ['%s = _rdw(ram, %s, 4)' % (dest, pyaddr)]
        if auto == 'post':
            py.append('r[%d] = (r[%d] + 4) & 0xFFFFFFFF' % (base_reg, base_reg))
    else:                                            # store
        if isinstance(src, int):
            c = ['*(volatile uint32_t*)%s = fr%d;' % (eff, src)]
        else:
            c = ['*(volatile uint32_t*)%s = %s;' % (eff, src)]
        if eff_abs is not None:
            c[0] += _ram_note(eff_abs)
        if auto == 'pre':                            # @-Rn: decrement then store
            c.append('r%d = r%d - 4;' % (base_reg, base_reg))
            py = ['r[%d] = (r[%d] - 4) & 0xFFFFFFFF' % (base_reg, base_reg)]
            # sh2emu decrements r[n] FIRST and stores at the NEW address, so
            # the mirror write must target the post-decrement register.
            pyaddr = 'r[%d]' % base_reg
        else:
            py = []
        if isinstance(src, int):
            py.append('_wrw(ram, %s, 4, f2bits(fr[%d]))' % (pyaddr, src))
        else:
            py.append('_wrw(ram, %s, 4, %s)' % (pyaddr, src))
    uses = {'r%d' % base_reg}
    if idx is not None:
        uses.add('r0')
    if isinstance(dest, int):
        uses.add('fr%d' % dest)
    else:
        uses.add(dest)
    if isinstance(src, int):
        uses.add('fr%d' % src)
    else:
        uses.add(src)
    return {'kind': 'fpu_mem', 'dir': dir_, 'size': 4, 'base': base_kind,
            'base_reg': base_reg, 'idx': idx, 'auto': auto,
            'dest': dest if dir_ == 'load' else None,
            'src': src if dir_ == 'store' else None,
            'c': c, 'py': py, 'uses': uses, 'ann': mnem}
