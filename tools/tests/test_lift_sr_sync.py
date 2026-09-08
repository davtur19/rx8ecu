#!/usr/bin/env python3
"""
tools/tests/test_lift_sr_sync.py — C1 regression: the lift SR/T/Q/M model
must match the sh2emu oracle (T=bit0, Q=bit8, M=bit9, synced on every write).

Background: sh2emu keeps T/Q/M as properties that push into SR bits 0/8/9 on
every write, and every SR write (ldc Rn,SR / ldc.l @Rn+,SR) re-syncs T/Q/M
from SR.  The lift (c_lift_ops.translate + v3/v8 stc.l/ldc.l handlers +
generated mirrors) must carry the same sync statements.

Three layers:
  1. unit: every T/Q/M/SR-writing pure op — emulator single-step (_exec) vs
     the translate() py fragment exec'd in a mirror ns, over a T/Q/M x SR
     state grid.  Must agree on (r, T, Q, M, sr) exactly.
  2. micro-ROMs: end-to-end lift-vs-oracle agreement on the exact divergence
     patterns (sett/clrt->ldc->movt, sett->stc, div0s->stc image 0x2F1,
     cmp/hi + delay-slot ldc a.k.a. getSR, stc.l/ldc.l round-trip).  The
     mirror side runs the REAL v3 walk_v3 / v8 build_cfg records through a
     tiny pc-interpreter; the oracle side runs cpu.call() on the ROM bytes.
  3. generator sync presence: the v3/v8 stc.l/ldc.l SR records carry the
     resync statements in both C and py.

Run from repo root: python3 tools/tests/test_lift_sr_sync.py
Exit status is non-zero if any check fails.  All vectors are fixed.
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, MASK
import c_lift_ops as ops
import gen_c_lift_v3 as v3
import gen_c_lift_v8 as v8mod

FAILS = []
CHECKS = [0]


def check(cond, msg):
    CHECKS[0] += 1
    if not cond:
        FAILS.append(msg)
        print("FAIL: " + msg)
    else:
        print("ok: " + msg)


def _base_regs():
    return [((0x11111111 * (i + 1) + 0x12345678) & MASK) for i in range(16)]


def _emu_step(op, regs, T, Q, M, sr_other, fr=None):
    """Single oracle step: consistent (T,Q,M,sr) init, _exec(op, 0)."""
    cpu = SH2(b'\x00' * 0x100)
    cpu.ram = {}
    cpu.r = list(regs)
    cpu.fr = list(fr) if fr is not None else [0.0] * 16
    cpu.pr = cpu.SENT
    cpu.macl = 0xAAAAAAAA
    cpu.mach = 0x55555555
    cpu.gbr = 0
    cpu.T = T
    cpu._Q = Q
    cpu._M = M
    cpu.sr = (sr_other & ~0x301) | (T & 1) | ((Q & 1) << 8) | ((M & 1) << 9)
    cpu.sr &= MASK
    cpu._sync_TQM_from_sr()
    cpu._exec(op, 0)
    return cpu


def _mirror_step(d, regs, T, Q, M, sr_other, fr=None):
    """Exec the translate() py fragment in a template-like ns."""
    ns = {'r': list(regs), 'T': T, 'Q': Q, 'M': M,
          'sr': ((sr_other & ~0x301) | (T & 1) | ((Q & 1) << 8)
                 | ((M & 1) << 9)) & MASK,
          'mach': 0x55555555, 'macl': 0xAAAAAAAA, 'pr': 0xEEEE0000,
          'gbr': 0, 'vbr': 0, 'fpul': 0, 'fpscr': 0,
          'fr': list(fr) if fr is not None else [0.0] * 16,
          's8': ops.s8, 's16': ops.s16, 's32': ops.s32, 'ts': ops.ts,
          'ram': {}, 'sp': 0xFFFFD400, 'STACK_BASE': 0xFFFFD000,
          'local': {}}
    py = v3._norm_py(d.get('py') or [])
    if py:
        exec(py, ns)
    return ns


def _same_state(cpu, ns, tag):
    ok = True
    for i in range(16):
        if (ns['r'][i] & MASK) != (cpu.r[i] & MASK):
            ok = False
    if (ns['T'] & 1) != (cpu.T & 1):
        ok = False
    if (ns['Q'] & 1) != (cpu._Q & 1):
        ok = False
    if (ns['M'] & 1) != (cpu._M & 1):
        ok = False
    if (ns['sr'] & MASK) != (cpu.sr & MASK):
        ok = False
    if (ns['mach'] & MASK) != (cpu.mach & MASK):
        ok = False
    if (ns['macl'] & MASK) != (cpu.macl & MASK):
        ok = False
    check(ok, tag + " (T=%d Q=%d M=%d sr=%08X | emu T=%d Q=%d M=%d sr=%08X)"
          % (ns['T'] & 1, ns['Q'] & 1, ns['M'] & 1, ns['sr'] & MASK,
             cpu.T & 1, cpu._Q & 1, cpu._M & 1, cpu.sr & MASK))
    return ok


# ---------------------------------------------------------------------------
# 1. unit battery: every T/Q/M/SR writer
# ---------------------------------------------------------------------------
def test_unit_ops():
    rom = b'\x00' * 64
    # (op, {reg: value} overrides, fr pair or None)
    cases = [
        (0x0018, {}, None), (0x0008, {}, None), (0x0019, {}, None),
        (0x2457, {4: 0x80000000, 5: 0x00000001}, None),   # div0s -> Q=1 M=0 T=1
        (0x2457, {4: 0x00000000, 5: 0x80000000}, None),   # div0s -> Q=0 M=1 T=1
        (0x3450, {4: 7, 5: 7}, None), (0x3450, {4: 7, 5: 8}, None),
        (0x3452, {4: 7, 5: 7}, None), (0x3452, {4: 6, 5: 7}, None),
        (0x3453, {4: 0xFFFFFFFF, 5: 1}, None),
        (0x3456, {4: 8, 5: 7}, None), (0x3456, {4: 7, 5: 7}, None),
        (0x3457, {4: 0x80000000, 5: 1}, None),
        (0x345E, {}, None), (0x345A, {}, None),
        (0x345B, {4: 0x7FFFFFFF, 5: 0xFFFFFFFF}, None),
        (0x345F, {4: 0x7FFFFFFF, 5: 1}, None),
        (0x3454, {4: 0x12345678, 5: 0x9ABCDEF0}, None),   # div1
        (0x645A, {}, None),                               # negc r4,r5
        (0x2458, {4: 0, 5: 0}, None), (0x2458, {4: 3, 5: 5}, None),
        (0x245C, {4: 0x01020304, 5: 0x01020304}, None),
        (0xC804, {0: 0x04}, None), (0xC804, {0: 0x00}, None),
        (0x88FE, {0: 0xFFFFFFFE}, None), (0x88FE, {0: 0}, None),
        (0x4400, {4: 0x80000001}, None), (0x4401, {4: 0x00000001}, None),
        (0x4421, {4: 0x00000001}, None), (0x4420, {4: 0x80000001}, None),
        (0x4404, {4: 0x80000001}, None), (0x4405, {4: 0x00000001}, None),
        (0x4424, {4: 0x80000001}, None), (0x4425, {4: 0x00000001}, None),
        (0x4410, {4: 1}, None), (0x4410, {4: 2}, None),
        (0x4411, {4: 0}, None), (0x4411, {4: 0xFFFFFFFF}, None),
        (0x4415, {4: 1}, None), (0x4415, {4: 0x80000000}, None),
        (0x0402, {}, None),                               # stc SR,r4
        (0x440E, {4: 0x000002F1}, None),                  # ldc r4,SR
        (0x440E, {4: 0x000000F0}, None),
        (0x0429, {}, None),                               # movt r4 (read-only)
        (0xF014, {}, (1.5, 1.5)), (0xF014, {}, (2.0, 1.5)),
        (0xF015, {}, (2.0, 1.5)), (0xF015, {}, (1.5, 1.5)),
    ]
    states = [(0, 0, 0, 0xF0), (1, 0, 0, 0xF0), (0, 1, 1, 0xF0),
              (1, 1, 1, 0x00), (0, 1, 0, 0xA500)]
    n = 0
    for op, over, frpair in cases:
        if (op & 0xF000) == 0xF000:
            d = ops.decode_fpu(op, 0, rom)
        else:
            d = ops.translate(op, 0, rom)
        if d is None:
            check(False, "unit/1: op 0x%04X unmapped (test bug)" % op)
            continue
        for T, Q, M, other in states:
            regs = _base_regs()
            for k, val in over.items():
                regs[k] = val & MASK
            fr = [0.0] * 16
            if frpair is not None:
                fr[0], fr[1] = frpair
            cpu = _emu_step(op, regs, T, Q, M, other, fr)
            ns = _mirror_step(d, regs, T, Q, M, other, fr)
            n += 1
            _same_state(cpu, ns, "unit/1: op 0x%04X regs=%s TQM=%d%d%d"
                        % (op, {k: '0x%X' % v for k, v in over.items()},
                           T, Q, M))
    print("unit/1: %d op x state vectors checked" % n)


# ---------------------------------------------------------------------------
# 2. micro-ROM end-to-end patterns (real walk records vs cpu.call)
# ---------------------------------------------------------------------------
def _u16(words):
    rom = bytearray()
    for w in words:
        rom += struct.pack('>H', w & 0xFFFF)
    return bytes(rom)


def _run_records(records, rom, r4=0, r5=0, r6=0, r7=0, ram=None):
    """Tiny pc-interpreter over v3/v8 walk records (st/mem/branch/ret)."""
    ram = dict(ram or {})

    def _rd(a):
        a &= MASK
        v = ram.get(a)
        if v is not None:
            return v
        return rom[a] if a < len(rom) else 0

    def _rdw(a, n):
        a &= MASK
        return int.from_bytes(bytes(_rd((a + i) & MASK) for i in range(n)), 'big')

    def _wrw(a, n, v):
        a &= MASK
        for i in range(n):
            ram[(a + i) & MASK] = (v >> (8 * (n - 1 - i))) & 0xFF

    r = [0] * 16
    r[4], r[5], r[6], r[7] = r4 & MASK, r5 & MASK, r6 & MASK, r7 & MASK
    r[15] = 0xFFFFD400
    ns = {'r': r, 'T': 0, 'Q': 0, 'M': 0, 'mach': 0, 'macl': 0,
          'pr': 0xEEEE0000, 'sr': 0xF0, 'gbr': 0, 'vbr': 0,
          'fpul': 0, 'fpscr': 0, 'fr': [0.0] * 16,
          's8': ops.s8, 's16': ops.s16, 's32': ops.s32, 'ts': ops.ts,
          'ram': ram, 'sp': r[15], 'STACK_BASE': 0xFFFFD000, 'local': {},
          '_rdw': lambda _ram, a, n: _rdw(a, n),
          '_wrw': lambda _ram, a, n, v: _wrw(a, n, v)}
    by_pc = {rec['pc']: rec for rec in records}
    code = sorted(by_pc)

    def _norm(py):
        out = []
        for frag in (py or []):
            for ln in frag.split('\n'):
                s = ln.strip()
                if s:
                    out.append(s)
        return '\n'.join(out)

    def _exec_py(py):
        s = _norm(py)
        if s:
            exec(s, ns)

    pc = code[0]
    for _ in range(10000):
        rec = by_pc.get(pc)
        if rec is None:
            return ('ERR', pc, ns, ram)
        kind = rec.get('kind')
        if kind == 'branch':
            if rec.get('target') is None and rec.get('cond') is None:
                # rts at walk/CFG level (render maps it to 'ret'): the delay
                # slot runs, then the function returns.
                slot = rec.get('slot')
                if slot is not None:
                    _exec_py(slot.get('py'))
                return ('RET', None, ns, ram)
            cond = rec.get('cond')
            if cond is None:
                # walk records leave cond unset; the render maps the branch
                # kind via _BRANCH_COND — replicate that here.
                bk = (ops.branch_info(rec.get('op', 0)) or {}).get('kind')
                cond = v3._BRANCH_COND.get(bk)
            t = ns['T']
            # NOTE: no re-read of rec['cond'] here — the block above already
            # mapped an unset cond via _BRANCH_COND; re-reading would clobber
            # it back to None and force taken=True (micro/2e: a not-taken bf
            # would wrongly jump to its target, skipping the fallthrough).
            taken = True
            if cond == 'T':
                taken = (t == 1)
            elif cond == 'notT':
                taken = (t == 0)
            slot = rec.get('slot')
            if slot is not None:
                _exec_py(slot.get('py'))
                pc = rec['target'] if taken else pc + 4
            else:
                pc = rec['target'] if taken else pc + 2
        elif kind == 'ret':
            slot = rec.get('slot')
            if slot is not None:
                _exec_py(slot.get('py'))
            return ('RET', None, ns, ram)
        elif kind in ('st', 'mem', 'reg', 'frame', 'ldc', 'sys_stack',
                      'stack', 'gbr'):
            _exec_py(rec.get('py'))
            pc += 2
        else:
            return ('ERR', 'kind %r' % kind, ns, ram)
    return ('ERR', 'steps', ns, ram)


def _check_pattern(tag, words, expect, r4=0, r5=0, r6=0, r7=0, ram=None):
    rom = _u16(words)
    end = len(rom)
    ram = dict(ram or {})
    # oracle
    cpu = SH2(rom)
    cpu.call(0, r4=r4, r5=r5, r6=r6, r7=r7, ram=dict(ram))
    # v3 lift mirror (real walk records)
    recs3, _info3, _labels3 = v3.walk_v3(rom, 0, end)
    st3, _, ns3, ram3 = _run_records(recs3, rom, r4, r5, r6, r7, ram)
    # v8 lift mirror (real CFG records)
    res8 = v8mod.build_cfg(rom, 0, end, set(), {}, allow_runtime_base=True)
    if res8.reject is not None:
        check(False, "%s: v8 build_cfg rejects synthetic ROM %r" % (tag, res8.reject))
        return
    st8, _, ns8, ram8 = _run_records(res8.records, rom, r4, r5, r6, r7, ram)
    got = {'r0': (cpu.r[0] & MASK, ns3['r'][0] & MASK, ns8['r'][0] & MASK),
           'r1': (cpu.r[1] & MASK, ns3['r'][1] & MASK, ns8['r'][1] & MASK),
           'T': (cpu.T & 1, ns3['T'] & 1, ns8['T'] & 1),
           'Q': (cpu._Q & 1, ns3['Q'] & 1, ns8['Q'] & 1),
           'M': (cpu._M & 1, ns3['M'] & 1, ns8['M'] & 1),
           'sr': (cpu.sr & MASK, ns3['sr'] & MASK, ns8['sr'] & MASK)}
    ok = (st3 == 'RET' and st8 == 'RET')
    for k, (o, m3, m8) in got.items():
        if k in expect and not (o == expect[k] and m3 == expect[k]
                                and m8 == expect[k]):
            ok = False
    check(ok, "%s: oracle==v3==v8==0x%X on %s (got %s)" % (
        tag, expect.get('r0', expect.get('sr', 0)),
        {k: '0x%X/0x%X/0x%X' % v for k, v in got.items()
         if k in expect}, {k: '0x%X' % v for k, v in expect.items()}))


def test_micro_roms():
    RTS = 0x000B
    NOP = 0x0009
    # P1: sett -> ldc r4,sr -> movt r0 -> stc sr,r1 ; r4=0xFFFFFF00 => r0=0
    _check_pattern("micro/2a sett-ldc-movt",
                   [0x0018, 0x440E, 0x0029, 0x0102, RTS, NOP],
                   {'r0': 0x0, 'r1': 0xFFFFFF00, 'T': 0, 'Q': 1, 'M': 1,
                    'sr': 0xFFFFFF00},
                   r4=0xFFFFFF00)
    # P2: clrt -> ldc r4,sr -> movt r0 ; r4 bit0=1 => r0=1
    _check_pattern("micro/2b clrt-ldc-movt",
                   [0x0008, 0x440E, 0x0029, RTS, NOP],
                   {'r0': 0x1, 'T': 1, 'sr': 0xF1},
                   r4=0xF1)
    # P3: sett -> stc sr,r0 => r0=0xF1
    _check_pattern("micro/2c sett-stc",
                   [0x0018, 0x0002, RTS, NOP],
                   {'r0': 0xF1, 'sr': 0xF1})
    # P4: div0s r5,r4 (Q=0 M=1 T=1) -> stc => r0=0x2F1
    _check_pattern("micro/2d div0s-stc",
                   [0x2457, 0x0002, RTS, NOP],
                   {'r0': 0x2F1, 'T': 1, 'Q': 0, 'M': 1, 'sr': 0x2F1},
                   r4=0x00000000, r5=0x80000000)
    # P5: getSR pattern — cmp/hi sets T, ldc in bf delay slot, then movt.
    # r4=5 > r5=3 => T=1, bf not taken; ldc r6 (bit0=0) => T=0; r0=0.
    _check_pattern("micro/2e getSR cmp/hi+ldc",
                   [0x3456, 0x8B03, 0x460E, 0x0029, RTS, NOP,
                    0x0129, RTS, NOP],
                   {'r0': 0x0, 'T': 0, 'sr': 0x12345600},
                   r4=5, r5=3, r6=0x12345600)
    # P6: ldc.l @r4+,SR from a literal RAM pool word, then movt/stc.
    # The v3/v8 walkers only admit ldc.l with a provable (literal/param)
    # base, so the pool word pins r4.  RAM holds 0x12345671 (bit0=1).
    _check_pattern("micro/2f ldc.l-movt",
                   [0xD402, 0x4407, 0x0029, 0x0102, RTS, NOP,
                    0xFFFF, 0xD100],
                   {'r0': 0x1, 'r1': 0x12345671, 'T': 1,
                    'sr': 0x12345671},
                   ram={0xFFFFD100: 0x12, 0xFFFFD101: 0x34,
                        0xFFFFD102: 0x56, 0xFFFFD103: 0x71})


# ---------------------------------------------------------------------------
# 3. generator-level sync presence (C and py, v3 + v8 stc.l/ldc.l SR)
# ---------------------------------------------------------------------------
def _has_sync(frags):
    t = '\n'.join(frags)
    return ('sr & ~1u' in t or 'sr & ~1)' in t or 'sr & ~0x301' in t)


def test_gen_sync_presence():
    rom = _u16([0xD402, 0x4407, 0x0029, 0x0102, 0x000B, 0x0009,
                0xFFFF, 0xD100])
    walked = v3.walk_v3(rom, 0, len(rom))
    check(walked is not None, "gen/3: v3 walk admits the ldc.l SR ROM")
    recs3 = walked[0] if walked is not None else []
    ldc3 = [r for r in recs3
            if 'ldc.l' in (r.get('mnem') or '') and 'SR' in (r.get('mnem') or '')]
    check(len(ldc3) == 1, "gen/3: v3 walk finds the ldc.l SR record")
    if ldc3:
        c = '\n'.join(ldc3[0].get('c') or [])
        py = '\n'.join(ldc3[0].get('py') or [])
        check('T = sr & 1u' in c and '(sr >> 8)' in c,
              "gen/3: v3 ldc.l C resyncs T/Q/M from sr")
        check('T = sr & 1' in py and '(sr >> 8)' in py,
              "gen/3: v3 ldc.l py resyncs T/Q/M from sr")
    res8 = v8mod.build_cfg(rom, 0, len(rom), set(), {},
                           allow_runtime_base=True)
    check(res8.reject is None, "gen/3: v8 build_cfg accepts the stc.l/ldc.l ROM")
    ldc8 = [r for r in res8.records
            if 'ldc.l' in (r.get('mnem') or '') and 'SR' in (r.get('mnem') or '')]
    check(len(ldc8) == 1, "gen/3: v8 CFG finds the ldc.l SR record")
    if ldc8:
        c = '\n'.join(ldc8[0].get('c') or [])
        py = '\n'.join(ldc8[0].get('py') or [])
        check('T = sr & 1u' in c and '(sr >> 8)' in c,
              "gen/3: v8 ldc.l C resyncs T/Q/M from sr")
        check('T = sr & 1' in py and '(sr >> 8)' in py,
              "gen/3: v8 ldc.l py resyncs T/Q/M from sr")
    # pure-op sync: a T-writer and ldc via translate carry sr sync
    rom0 = b'\x00' * 64
    d = ops.translate(0x3456, 0, rom0)      # cmp/hi
    check(_has_sync(d['c']) and _has_sync(d['py']),
          "gen/3: cmp/hi fragments update the sr image")
    d = ops.translate(0x440E, 0, rom0)      # ldc r4,SR
    check('T = sr & 1' in '\n'.join(d['py']),
          "gen/3: ldc Rn,SR mirror resyncs T/Q/M from sr")


def main():
    test_unit_ops()
    test_micro_roms()
    test_gen_sync_presence()
    print('-' * 70)
    print('sr-sync: %d checks, %d failures' % (CHECKS[0], len(FAILS)))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
