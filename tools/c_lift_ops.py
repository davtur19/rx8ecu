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
    Rs->@Rn, Rs->@-Rn, Rs->@(R0,Rn).  The SH-2 ISA has NO @-Rn load and NO
    @Rn+ store, so those two directions are inherently undecodable (None).
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

    # ---- arithmetic / compare (n0==3) ----
    if n0 == 0x3:
        if nib == 0xC:
            return _mk('r%d = r%d + r%d;' % (n, n, m), 'r[%d] = (r[%d] + r[%d]) & 0xFFFFFFFF' % (n, n, m), ['r%d' % n, 'r%d' % m])
        if nib == 0x8:
            return _mk('r%d = r%d - r%d;' % (n, n, m), 'r[%d] = (r[%d] - r[%d]) & 0xFFFFFFFF' % (n, n, m), ['r%d' % n, 'r%d' % m])
        if nib == 0x0:
            return _mk('T = (r%d == r%d) ? 1u : 0u;' % (n, m), 'T = 1 if r[%d] == r[%d] else 0' % (n, m), ['T', 'r%d' % n, 'r%d' % m])
        if nib == 0x2:
            return _mk('T = (r%d >= r%d) ? 1u : 0u;' % (n, m), 'T = 1 if r[%d] >= r[%d] else 0' % (n, m), ['T', 'r%d' % n, 'r%d' % m])
        if nib == 0x3:
            return _mk('T = ((int32_t)r%d >= (int32_t)r%d) ? 1u : 0u;' % (n, m),
                       'T = 1 if s32(r[%d]) >= s32(r[%d]) else 0' % (n, m), ['T', 'r%d' % n, 'r%d' % m])
        if nib == 0x6:
            return _mk('T = (r%d > r%d) ? 1u : 0u;' % (n, m), 'T = 1 if r[%d] > r[%d] else 0' % (n, m), ['T', 'r%d' % n, 'r%d' % m])
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
        if f == 0x4000: return _mk('r%d = (r%d << 1);' % (n, n), 'r[%d] = (r[%d] << 1) & 0xFFFFFFFF' % (n, n), ['r%d' % n])
        if f == 0x4001: return _mk('r%d = (r%d >> 1);' % (n, n), 'r[%d] = (r[%d] >> 1) & 0xFFFFFFFF' % (n, n), ['r%d' % n])
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
        if f == 0x000A: return _mk('mach = r%d;' % n, 'mach = r[%d] & 0xFFFFFFFF' % n, ['mach', 'r%d' % n])
        if f == 0x001A: return _mk('macl = r%d;' % n, 'macl = r[%d] & 0xFFFFFFFF' % n, ['macl', 'r%d' % n])
        if f == 0x002A: return _mk('pr = r%d;' % n, 'pr = r[%d] & 0xFFFFFFFF' % n, ['pr', 'r%d' % n])
        # memory / stack / sr ops under n0==4 are NOT pure -> None (caller filters)

    # ---- misc system ops ----
    if op == 0x0009: return _mk('', '', [])                       # nop
    if op == 0x0019: return _mk('Q = 0u; M = 0u; T = 0u;', 'Q = 0; M = 0; T = 0', ['Q', 'M', 'T'])  # div0u
    if op == 0x0008: return _mk('T = 0u;', 'T = 0', ['T'])       # clrt
    if op == 0x0018: return _mk('T = 1u;', 'T = 1', ['T'])       # sett
    if op == 0x0028: return _mk('mach = 0u; macl = 0u;', 'mach = 0; macl = 0', ['mach', 'macl'])  # clrmac
    if op & 0xF0FF == 0x0029: return _mk('r%d = T;' % n, 'r[%d] = T' % n, ['r%d' % n, 'T'])      # movt
    if op == 0x001B: return _mk('', '', [])                       # sleep -> no-op (as sh2emu)

    # ---- mul.l / sts macl / mach (n0==0) ----
    if n0 == 0x0:
        if nib == 0x7:   # mul.l Rm,Rn -> macl = low32(signed product)
            return _mk('macl = (uint32_t)((int32_t)r%d * (int32_t)r%d);' % (n, m),
                       'macl = (s32(r[%d]) * s32(r[%d])) & 0xFFFFFFFF' % (n, m), ['macl', 'r%d' % n, 'r%d' % m])
        if op & 0xF0FF == 0x000A: return _mk('r%d = mach;' % n, 'r[%d] = mach' % n, ['r%d' % n, 'mach'])
        if op & 0xF0FF == 0x001A: return _mk('r%d = macl;' % n, 'r[%d] = macl' % n, ['r%d' % n, 'macl'])
        if op & 0xF0FF == 0x002A: return _mk('r%d = pr;' % n, 'r[%d] = pr' % n, ['r%d' % n, 'pr'])

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

    return None  # not a covered memory op
