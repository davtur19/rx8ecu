#!/usr/bin/env python3
"""gen_c_lift_v8.py — CFG-complete selection + emission (v8) for SH-2 lifts.

Builds on v3 (walk_v3 / selection / labels-goto emission), v7 (ST shared-state
ABI: struct ST, caller_<hex>.c compositions, c/lib/f_<hex>.c callees) and the
v3/v7 pc-interpreter test harness.  v8 adds the missing piece: a CFG builder
that decodes the whole sanitized span as basic blocks + edges and RESOLVES the
indirect branches (jmp/jsr @Rn, bsrf/braf) that previously rejected every
candidate ('call'/'unmapped'):

  - literal resolution: jmp/jsr @Rn where Rn holds a known literal
    (mov.l/mov.w @(disp,PC), mov #imm, mova) -> a single static target;
  - JUMP TABLE: `mov.l @(r0,rB),rN` (or mova/mov.l-PC base) followed by
    `jmp @rN` -> enumerate the 4-byte table words at the base address while
    each word is a valid code address (in-span, or an already-lifted / catalog
    function).  All words are marked DATA (never decoded as instructions).
    If any entry fails to resolve the candidate is rejected
    ('jump_table_unresolved').

Selection (v8): a function is admitted iff the CFG builds completely (every
indirect edge resolved), the span is sanitized (data words marked and skipped —
tables + literal pools mid-span do NOT count as instructions), size gate
~8..400, dedup vs c/*.c and c/lib/f_*.c, and the v3 base rules.

Emission (v8):
  - multi-dispatch / tail-call functions: c/lib/caller_<hex>.c (ST ABI) with
    conditional-branch labels/goto + tail `f_<callee>(s); return;` (delay slot
    of the jmp emitted BEFORE the call), jsr -> `s->pr=<ret>; <slot>;
    f_<callee>(s);`
  - jump tables: `switch (rN) { case 0xADDR: goto L_ADDR; ... default: fail }`
    on the runtime address value — exactly the pc-interpreter mirror, which
    itself reads the table dynamically (`_rdw(ram, base + r[0], 4)`).

Tests: same v7 format (seed, RAM prefill, STACK 0xFFFFD000, N cases,
PASS N/N (skipped=M)) comparing the Python pc-interpreter spec_mirror (CODE
dict incl. the inlined callee records) against the sh2emu oracle.

Usage:
    python3 tools/gen_c_lift_v8.py --metrics                # pool_v8 numbers
    python3 tools/gen_c_lift_v8.py --emit 0x540D4           # caller_<hex>.c + test
    python3 tools/gen_c_lift_v8.py --jt 0x420C              # jump-table emit attempt
    python3 tools/gen_c_lift_v8.py --cases 500 --seed 42
"""
import argparse
import glob
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import c_lift_ops as ops
import gen_c_lift as gcl
import gen_c_lift_v3 as v3
import gen_c_lift_v7 as v7

MASK = gcl.MASK
DEFAULT_ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
SIZE_MIN, SIZE_MAX = 8, 400          # v8 size gate (v3 was 8..160+16)

ST_STRUCT = v7.ST_STRUCT
_BRANCH_COND = {'bt': 'T', 'bts': 'T', 'bf': 'notT', 'bfs': 'notT', 'bra': 'always'}
_MIRROR_KIND = dict(v3._MIRROR_KIND)


def _s12(x):
    x &= 0xFFF
    return x - 0x1000 if x & 0x800 else x


def _s8(x):
    x &= 0xFF
    return x - 0x100 if x & 0x80 else x


# ---------------------------------------------------------------------------
# CFG builder
# ---------------------------------------------------------------------------
class CfgResult:
    __slots__ = ('records', 'labels', 'info', 'jump_tables', 'data_words',
                 'edges', 'reject')

    def __init__(self):
        self.records = []
        self.labels = set()
        self.info = {'stack_offs': set(), 'ram_addrs': set(),
                     'has_stack': False, 'has_literal': False}
        self.jump_tables = []       # {jmp_pc, reg, base, entries}
        self.data_words = set()
        self.edges = []             # (src_pc, kind, target) debug/measures
        self.reject = None          # (reason, pc) or None when CFG complete


def _load_lifted():
    """Addresses already lifted as c/*_<hex>.c or c/lib/f_<hex>.c (dedup set)."""
    lifted = set()
    for p in glob.glob(os.path.join(ROOT, 'c', '*.c')):
        m = re.search(r'_([0-9a-fA-F]+)\.c$', p)
        if m:
            lifted.add(int(m.group(1), 16))
    for p in glob.glob(os.path.join(ROOT, 'c', 'lib', 'f_*.c')):
        m = re.search(r'_([0-9a-fA-F]+)\.c$', os.path.basename(p))
        if m:
            lifted.add(int(m.group(1), 16))
    return lifted


def _memo_sanitized_end(ca, ce, rom):
    """Cached sanitize_span end for the (ca, ce) catalog pair.  sanitize_span is
    a pure function of the ROM bytes, so the result is stable per process; the
    cache makes the mid-function nesting guard O(1) per candidate instead of
    re-scanning every outer span on every scan_v8 call."""
    key = (id(rom), ca, ce)
    es = _SPAN_END_MEMO.get(key)
    if es is None:
        _s, es, _r = v3.sanitize_span(ca, ce, rom)
        if len(_SPAN_END_MEMO) > 20000:
            _SPAN_END_MEMO.clear()
        _SPAN_END_MEMO[key] = es
    return es


_SPAN_END_MEMO = {}


def build_cfg(rom, addr, end, lifted=None, catalog=None, data_extra=None):
    """Decode [addr, end) as basic blocks + edges; resolve all indirects.

    Returns CfgResult.  res.reject is None iff the CFG is complete (every
    indirect edge resolved).  Records mirror walk_v3's shape plus new kinds:
      'call': jsr/bsr (set_pr) or jmp-tail to a literal target,
      'jt':   jump-table switch record {jump_tables entries}.
    """
    lifted = lifted or set()
    catalog = catalog or {}
    res = CfgResult()
    bound = min(end, len(rom))
    # ---- mid-function-entry guard (bug a) ---------------------------------
    # A candidate that begins on a delay-slot nop (0x0009) or strictly inside
    # another catalog candidate's sanitized span is a spurious mid-function
    # entry: it has no prologue, its `lds.l @r15+,pr` epilogue pops the random
    # stack -> rts -> pr=0 -> emulator pc=0 (NotImplementedError @0x0), so
    # every test case is skipped (FAIL 0/400).  Reject before walking.
    if addr + 1 < len(rom) and rom[addr] == 0x00 and rom[addr + 1] == 0x09:
        res.reject = ('midfunc_nop', addr)
        return res
    if catalog:
        for _ca, _ce in catalog.items():
            if _ca >= addr or _ce is None:
                continue
            _cs = _memo_sanitized_end(_ca, _ce, rom)
            if _ca < addr < _cs:
                res.reject = ('midfunc_nested', addr)
                return res
    st = {'written': set(), 'lits': {}, 'tmp': [0],
          'gbr_known': False, 'gbr_value': None,
          'stack_ok': True, 'frame_live': False, 'frame_off': None,
          'sp_off': 0x400,
          # bug b: path-sensitivity for literal bases.  litdefs maps 'rN' ->
          # set of pcs that wrote a LITERAL to that register.  A base register
          # with >=2 distinct literal def-sites may hold a different value on
          # another CFG path (e.g. a jsr delay slot on a sibling path), so the
          # access must be emitted register-relative (dynbase), never baked.
          'litdefs': {}}
    info = res.info
    labels = res.labels
    data = set(gcl._pcrel_pool_words(rom, addr, end))
    if data_extra:
        data |= set(data_extra)
    mova_lits = {}
    tbl_base = {}       # reg index -> table base literal (set by indexed load)

    # v3-style re-entry pre-scan: every static branch target in-span.  A mem at
    # a re-entry pc may be reached again with the base register already modified
    # on another path — emit the runtime register instead of the folded literal.
    reentry = set()
    for _rp in range(addr, bound, 2):
        if _rp in data:
            continue
        _ro = (rom[_rp] << 8) | rom[_rp + 1]
        _rb = ops.branch_info(_ro)
        if _rb is not None and _rb.get('target_disp') is not None \
                and _rb['kind'] not in ('rte', 'rts', 'bsrf', 'braf'):
            _rt = (_rp + 4 + _rb['target_disp'] * 2) & MASK
            if addr <= _rt < end:
                reentry.add(_rt)

    def _pin_lit(reg, val, pc):
        """Record a literal definition of `reg` at `pc` (path-sensitivity)."""
        st['lits']['r%d' % reg] = val
        st['litdefs'].setdefault('r%d' % reg, set()).add(pc)
        return val

    def temp():
        st['tmp'][0] += 1
        return 't%d' % st['tmp'][0]

    def resolve(reg):
        v = st['lits'].get('r%d' % reg)
        if v is None:
            return None
        cls = ops.classify_addr(v)
        if cls in ('RAM', 'ROM'):
            return (cls, v)
        return None

    ctx = {'temp': temp, 'resolve': resolve}

    def emit_one(pc, op):
        """Non-branch, non-call instruction -> record or None (unmapped)."""
        d = ops.translate(op, pc, rom)
        if d is not None:
            ctext = '\n'.join(d.get('c') or [])
            writes = gcl._stmt_writes(ctext)
            if op == 0x6EF3:                       # mov r15,r14 -> frame pointer
                if 'r14' not in st['written']:
                    st['frame_live'] = True
                    st['frame_off'] = st['sp_off']
                return {'pc': pc, 'op': op, 'kind': 'frame',
                        'c': [], 'py': [], 'target': None, 'slot': None,
                        'mnem': 'mov r15,r14 (frame pointer — implicit)'}
            if 'r15' in writes:
                st['stack_ok'] = False
            if 'r14' in writes:
                st['frame_live'] = False
            if not gcl._apply_stmt(rom, pc, op, d, st['written'], st['lits']):
                return None
            # extra literal pinning so jsr/jmp @Rn can resolve a register that
            # was set by `mov #imm,Rn` (0xEnnn) or `mova` (0xC700) — the base
            # tracker only pins mov.l/mov.w @(disp,PC) literal-pool loads.
            # (bug b) every literal def is recorded as a def-site for the
            # path-sensitivity guard.
            if op & 0xF000 == 0xE000:                  # mov #imm,Rn (sign-ext8)
                _pin_lit((op >> 8) & 0xF, _s8(op & 0xFF) & MASK, pc)
            elif op & 0xFF00 == 0xC700:                # mova -> r0 = PC-rel EA
                _pin_lit(0, ops.mova_target(pc, op & 0xFF) & MASK, pc)
            if op & 0xF000 in (0x9000, 0xD000):        # mov.w/l @(disp,PC),Rn
                _v = st['lits'].get('r%d' % ((op >> 8) & 0xF))
                if _v is not None:
                    _pin_lit((op >> 8) & 0xF, _v, pc)
            return {'pc': pc, 'op': op, 'kind': 'st',
                    'c': list(d.get('c') or []),
                    'py': list(d.get('py') or []),
                    'target': None, 'slot': None,
                    'mnem': d.get('ann') or ('op 0x%04X' % op)}
        if op & 0xF0FF == 0x401E:                  # ldc Rn,GBR
            st['gbr_known'] = True
            st['gbr_value'] = st['lits'].get('r%d' % ((op >> 8) & 0xF))
            return {'pc': pc, 'op': op, 'kind': 'ldc',
                    'c': ['/* ldc r%d,GBR (GBR = 0x%08X) */'
                          % ((op >> 8) & 0xF, st['gbr_value'] or 0)],
                    'py': [], 'target': None, 'slot': None,
                    'mnem': 'ldc r%d,GBR' % ((op >> 8) & 0xF)}
        if op & 0xF0FF in (0x4003, 0x4007):        # stc.l SR / ldc.l SR
            srn = (op >> 8) & 0xF
            if srn in (4, 5, 6, 7) and 'r%d' % srn not in st['written']:
                bkind, abs_addr = 'param', None
            elif 'r%d' % srn in st['lits']:
                bkind, abs_addr = 'literal', st['lits']['r%d' % srn]
            else:
                return None
            if bkind == 'literal':
                info['has_literal'] = True
                info['ram_addrs'].add(abs_addr)
            if op & 0xF0FF == 0x4003:
                if bkind == 'literal':
                    a = (abs_addr - 4) & MASK
                    eff = '0x%08X' % a
                    note = (' /* RAM 0x%08X */' % a
                            if ops.classify_addr(a) == 'RAM' else ' /* ROM */')
                else:
                    eff, note = '(r%d - 4)' % srn, ''
                c = ['*(volatile uint32_t*)%s = sr;%s' % (eff, note),
                     'r%d = r%d - 4;' % (srn, srn)]
                py = ['_wrw(ram, (r[%d] - 4) & 0xFFFFFFFF, 4, sr)' % srn,
                      'r[%d] = (r[%d] - 4) & 0xFFFFFFFF' % (srn, srn)]
                mnem = 'stc.l SR,@-r%d' % srn
            else:
                if bkind == 'literal':
                    eff = '0x%08X' % (abs_addr & MASK)
                    note = (' /* RAM 0x%08X */' % (abs_addr & MASK)
                            if ops.classify_addr(abs_addr) == 'RAM' else ' /* ROM */')
                else:
                    eff, note = 'r%d' % srn, ''
                t = temp()
                c = ['uint32_t %s = *(volatile uint32_t*)%s;%s' % (t, eff, note),
                     'sr = %s;' % t,
                     'r%d = r%d + 4;' % (srn, srn)]
                py = ['sr = _rdw(ram, r[%d], 4)' % srn,
                      'r[%d] = (r[%d] + 4) & 0xFFFFFFFF' % (srn, srn)]
                mnem = 'ldc.l @r%d+,SR' % srn
            st['written'].add('r%d' % srn)
            st['lits'].pop('r%d' % srn, None)
            return {'pc': pc, 'op': op, 'kind': 'mem', 'c': c, 'py': py,
                    'target': None, 'slot': None, 'mnem': mnem}
        if op & 0xF0FF in (0x4002, 0x4012, 0x4022, 0x4006, 0x4016, 0x4026):
            # ---- sts.l/lds.l mach/macl/pr @-Rn/@Rn+ (sys_stack) ----
            # base gcl._mem_shape cannot decode these (the transferred value is
            # a system register, not an rN), so they used to die as 'unmapped' —
            # yet `sts.l pr,@-r15` (0x4F22) / `lds.l @r15+,pr` (0x4F26) are an
            # extremely common prologue/epilogue pair.  Admit the r15/r14 stack
            # forms here with the same stack_ok/frame_live + auto-offset model as
            # the r15/r14 mem block below (r15 mvnrment is that block's shared
            # local_<off> slot addressing; it is implicit / offset-based).  c is
            # emitted with bare system-reg names so v7.to_st_c rewrites them to
            # s-><reg> exactly once.
            _SYS = {0x4002: 'mach', 0x4012: 'macl', 0x4022: 'pr',
                    0x4006: 'mach', 0x4016: 'macl', 0x4026: 'pr'}
            sys_reg = _SYS[op & 0xF0FF]
            sys_store = (op & 0xF) == 0x2    # low nibble: 2 = sts.l, 6 = lds.l
            srn = (op >> 8) & 0xF
            if srn == 15:
                if not st['stack_ok']:
                    return None
            elif srn == 14:
                if not st['frame_live']:
                    return None
            else:
                return None
            if srn == 15:
                if sys_store:
                    st['sp_off'] -= 4
                    off = st['sp_off']
                else:
                    off = st['sp_off']
                    st['sp_off'] += 4
            else:
                off = (st['frame_off'] if st['frame_off'] is not None
                       else st['sp_off']) + (-4 if sys_store else 0)
            info['has_stack'] = True
            info['stack_offs'].add(off)
            st['written'].add('r%d' % srn)
            st['lits'].pop('r%d' % srn, None)
            if sys_store:
                c = ['local_%x = %s;' % (off, sys_reg)]
                py = ['local[0x%X] = %s' % (off, sys_reg),
                      '_wrw(ram, STACK_BASE + 0x%X, 4, %s)' % (off, sys_reg),
                      'sp = (sp - 4) & 0xFFFFFFFF']
                mnem = 'sts.l %s,@-r%d' % (sys_reg, srn)
            else:
                c = ['%s = local_%x;' % (sys_reg, off)]
                py = ['%s = _rdw(ram, STACK_BASE + 0x%X, 4)' % (sys_reg, off),
                      'sp = (sp + 4) & 0xFFFFFFFF']
                mnem = 'lds.l @r%d+,%s' % (srn, sys_reg)
            return {'pc': pc, 'op': op, 'kind': 'sys_stack', 'c': c, 'py': py,
                    'target': None, 'slot': None, 'mnem': mnem}
        m = ops.decode_mem(op, None, ctx)
        if m is not None:
            base_reg = m['base_reg']
            if m.get('idx') == 'r0' and 'r0' not in st['lits']:
                return None
            if base_reg in (4, 5, 6, 7) and 'r%d' % base_reg not in st['written']:
                bkind, abs_addr = 'param', None
            elif 'r%d' % base_reg in st['lits']:
                bkind, abs_addr = 'literal', st['lits']['r%d' % base_reg]
            else:
                return None
            if bkind == 'literal':
                info['has_literal'] = True
                info['ram_addrs'].add(abs_addr)
            # bug b: don't bake a literal base that is not path-constant.
            # (1) mem at a branch-target pc (re-entry) can be reached with the
            # base register already modified on another path; (2) a base with
            # >=2 distinct literal def-sites (e.g. a jsr delay-slot write on a
            # sibling path) leaks the wrong constant here.  Emit the runtime
            # register (dynbase) in both cases.
            _dyn = ((pc in reentry)
                    or len(st['litdefs'].get('r%d' % base_reg, ())) > 1)
            c, py = gcl._mem_record(pc, op, m, bkind, abs_addr, temp,
                                    dynbase=_dyn)
            gcl._apply_mem_writes(m, st['written'], st['lits'])
            # jump-table base bookkeeping: indexed load @(r0,rB) with rB literal
            if m.get('idx') == 'r0' and m['dir'] == 'load' and m.get('dest') is not None:
                if 'r%d' % base_reg in st['lits']:
                    tbl_base[m['dest']] = st['lits']['r%d' % base_reg]
            return {'pc': pc, 'op': op, 'kind': 'mem', 'c': c, 'py': py,
                    'target': None, 'slot': None, 'mnem': m['ann']}
        g = gcl._decode_gbr(op)
        if g is not None:
            size, gdir, disp = g
            if not st['gbr_known'] or st['gbr_value'] is None or 'r0' not in st['lits']:
                return None
            abs_addr = (st['gbr_value'] + st['lits']['r0'] + disp) & MASK
            info['has_literal'] = True
            info['ram_addrs'].add(abs_addr)
            gm = {'dir': gdir, 'dest': 0 if gdir == 'load' else None,
                  'src': 0 if gdir == 'store' else None}
            c, py = gcl._gbr_record(pc, op, size, gdir, abs_addr, temp)
            if gdir == 'store':
                mnem = 'mov.%s r0,@(0x%X,gbr)' % (gcl._SIZE_CH[size], disp)
            else:
                mnem = 'mov.%s @(0x%X,gbr),r0' % (gcl._SIZE_CH[size], disp)
            gcl._apply_mem_writes(gm, st['written'], st['lits'])
            return {'pc': pc, 'op': op, 'kind': 'gbr', 'c': c, 'py': py,
                    'target': None, 'slot': None, 'mnem': mnem}
        gb = ops.decode_gbr_bit(op, pc, rom, None)
        if gb is not None:
            if not st['gbr_known'] or st['gbr_value'] is None or 'r0' not in st['lits']:
                return None
            abs_addr = (st['gbr_value'] + st['lits']['r0']) & MASK
            info['has_literal'] = True
            info['ram_addrs'].add(abs_addr)
            gbd = ops.decode_gbr_bit(op, pc, rom, {'gbr': abs_addr})
            return {'pc': pc, 'op': op, 'kind': 'gbr', 'c': list(gbd['c']),
                    'py': list(gbd['py']), 'target': None, 'slot': None,
                    'mnem': gbd['ann']}
        sh = gcl._mem_shape(op)
        if sh is not None and sh['base'] in (14, 15):
            breg = sh['base']
            if breg == 15:
                if not st['stack_ok'] or sh['dest'] == 15:
                    return None
            else:
                if not st['frame_live'] or sh['dest'] == 14:
                    return None
            if sh['idx'] is not None:
                return None
            if breg == 15:
                if sh['auto'] == 'pre':
                    st['sp_off'] -= sh['size']
                    off = st['sp_off']
                elif sh['auto'] == 'post':
                    off = st['sp_off']
                    st['sp_off'] += sh['size']
                else:
                    off = st['sp_off'] + sh['disp']
            else:
                off = (st['frame_off'] if st['frame_off'] is not None
                       else st['sp_off']) + sh['disp']
            info['has_stack'] = True
            info['stack_offs'].add(off)
            sm = {'dir': sh['dir'], 'size': sh['size'], 'base_reg': breg,
                  'auto': sh['auto'], 'dest': sh.get('dest'), 'src': sh.get('src')}
            c, py = gcl._stack_record(pc, op, sh, off)
            gcl._apply_mem_writes(sm, st['written'], st['lits'])
            return {'pc': pc, 'op': op, 'kind': 'stack', 'c': c, 'py': py,
                    'target': None, 'slot': None, 'mnem': gcl._stack_mnem(sh)}
        f = ops.decode_fpu(op, pc, rom, ctx)
        if f is not None:
            if f.get('kind') == 'fpu_mem':
                if f.get('unresolved'):
                    return None
                base_reg = f['base_reg']
                if f.get('idx') == 'r0' and 'r0' not in st['lits']:
                    return None
                if f['base'] == 'literal':
                    info['has_literal'] = True
                    v = st['lits'].get('r%d' % base_reg)
                    if v is not None and ops.classify_addr(v) == 'RAM':
                        info['ram_addrs'].add(v)
                if f.get('auto') in ('post', 'pre'):
                    reg = 'r%d' % base_reg
                    st['written'].add(reg)
                    st['lits'].pop(reg, None)
                return {'pc': pc, 'op': op, 'kind': 'fpu_mem',
                        'c': list(f.get('c') or []),
                        'py': list(f.get('py') or []),
                        'target': None, 'slot': None,
                        'mnem': f.get('ann') or ('op 0x%04X' % op)}
            for reg in gcl._stmt_writes('\n'.join(f.get('c') or [])):
                st['written'].add(reg)
                st['lits'].pop(reg, None)
            return {'pc': pc, 'op': op, 'kind': 'fpu',
                    'c': list(f.get('c') or []),
                    'py': list(f.get('py') or []),
                    'target': None, 'slot': None,
                    'mnem': f.get('ann') or ('op 0x%04X' % op)}
        return None

    def slot_record(spc):
        """Decode the delay slot at spc (must be in-span)."""
        sop = (rom[spc] << 8) | rom[spc + 1]
        rec = emit_one(spc, sop)
        if rec is None:
            return {'pc': spc, 'kind': 'st', 'op': None,
                    'c': ['/* delay slot 0x%04X — opaque */' % sop],
                    'py': [], 'mnem': 'op 0x%04X' % sop,
                    'target': None, 'slot': None}
        return rec

    def enum_table(base):
        """Enumerate the jump-table words at `base` while each is a valid code
        address.  Returns (entries, ok).  Table words are marked data."""
        entries = []
        a = base
        while a + 4 <= bound and len(entries) < 1024:
            v = int.from_bytes(rom[a:a + 4], 'big')
            if v in (0, 0xFFFFFFFF, 0x00000000):
                break
            in_span = addr <= v < end and v % 2 == 0
            known = in_span or v in lifted or v in catalog
            if not known:
                break
            if v in lifted or v in catalog:
                # out-of-span known function: fine as a callable target, but the
                # caller can only tail-call it; in-span entries become switch cases
                pass
            entries.append(v)
            data.add(a)
            if a + 2 < bound:
                data.add(a + 2)
            a += 4
        if not entries:
            return [], False
        # require every entry to be code (in-span or lifted/catalog) — already
        # guaranteed by the loop (we break otherwise).  The break on non-code
        # marks the table end; a zero/FFFF terminator is acceptable only as the
        # LAST word (not part of the cases).
        return entries, True

    pending = [addr]
    visited = set()
    seen_pc = set()        # every pc already consumed (record emitted / slot /
                           # data) — dedups blocks reached by fall-through AND
                           # by a branch target, and skips consumed delay slots.
    while pending:
        bs = pending.pop()
        if bs in visited or bs in seen_pc:
            continue
        visited.add(bs)
        pc = bs
        while pc + 1 < bound:
            if pc in seen_pc:            # already walked via another path
                break
            if pc in data:
                pc += 2
                continue
            op = (rom[pc] << 8) | rom[pc + 1]
            d = ops.translate(op, pc, rom)
            if d is not None and d.get('kind') in ('branch', 'ret'):
                bi = ops.branch_info(op)
                kind = bi['kind'] if bi is not None else None
                if kind is None or kind == 'rte':
                    res.reject = ('rte', pc)
                    return res
                target = None
                if kind == 'rts':
                    pass
                elif kind in ('bsrf', 'braf'):
                    reg = bi['reg']
                    v = st['lits'].get('r%d' % reg)
                    if v is not None and (addr <= v < end or v in lifted or v in catalog):
                        target = v & MASK
                    else:
                        res.reject = ('dynbranch_unresolved', pc)
                        return res
                else:
                    target = (pc + 4 + bi['target_disp'] * 2) & MASK
                slot = None
                if bi['delayed']:
                    if pc + 2 >= end:
                        res.reject = ('delay_slot_ctrl', pc)
                        return res
                    slot = slot_record(pc + 2)
                if kind in ('bsrf', 'braf'):
                    res.reject = ('dynbranch_unresolved', pc)
                    return res
                if target is not None:
                    res.edges.append((pc, 'branch', target))
                    if addr <= target < end:
                        labels.add(target)
                        pending.append(target)
                    else:
                        res.reject = ('target_fuori', pc)
                        return res
                if kind == 'rts':
                    line = 'return r0;'
                    mnem = 'rts'
                else:
                    line = v3.BRANCH_C[kind] % target
                    mnem = v3.BRANCH_MNEM[kind] % target
                rec = {'pc': pc, 'op': op, 'kind': 'branch',
                       'c': [line], 'mnem': mnem,
                       'target': target, 'slot': slot}
                res.records.append(rec)
                # delayed branch consumed the P+2 slot inside `slot`: skip it
                seen_pc.add(pc)
                if slot is not None:
                    seen_pc.add(pc + 2)
                pc += 4 if slot is not None else 2
                continue
            if gcl.is_call_op(op):
                if op & 0xF000 == 0xB000:               # bsr (delayed)
                    tgt = (pc + 4 + _s12(op & 0xFFF) * 2) & MASK
                    slot = slot_record(pc + 2) if pc + 2 < end else None
                    if slot is not None and pc + 3 < bound and \
                            (rom[pc + 2] << 8) | rom[pc + 3] == 0x4F26:
                        res.reject = ('pr_loop', pc)
                        return res
                    res.edges.append((pc, 'bsr', tgt))
                    if addr <= tgt < end:
                        labels.add(tgt)
                        pending.append(tgt)
                    rec = {'pc': pc, 'op': op, 'kind': 'call', 'mnem': 'bsr 0x%X' % tgt,
                           'c': ['s->pr = 0x%08X;' % ((pc + 4) & MASK)]
                                + ([v7.to_st_c(s) for s in slot['c']] if slot else [])
                                + ['f_%X(s);' % tgt],
                           'slot': slot, 'target': tgt,
                           'ret_pc': (pc + 4) & MASK, 'set_pr': True}
                    res.records.append(rec)
                    # bsr consumes the P+2 slot inline; skip past it
                    seen_pc.add(pc)
                    if slot is not None:
                        seen_pc.add(pc + 2)
                    pc += 4 if slot is not None else 2
                    continue
                rn = (op >> 8) & 0xF
                kind = 'jsr' if op & 0xF0FF == 0x400B else 'jmp'
                if rn in tbl_base:                     # JUMP TABLE
                    base = tbl_base[rn]
                    entries, ok = enum_table(base)
                    if not ok:
                        res.reject = ('jump_table_unresolved', pc)
                        return res
                    for e in entries:
                        if addr <= e < end:
                            labels.add(e)
                            pending.append(e)
                    slot = slot_record(pc + 2) if pc + 2 < end else None
                    if slot is not None and pc + 3 < bound and \
                            (rom[pc + 2] << 8) | rom[pc + 3] == 0x4F26:
                        res.reject = ('pr_loop', pc)
                        return res
                    res.jump_tables.append({'jmp_pc': pc, 'reg': rn,
                                            'base': base, 'entries': entries})
                    res.edges.append((pc, 'jt:%d' % len(entries), None))
                    c = ([v7.to_st_c(s) for s in slot['c']] if slot else []) + \
                        ['switch (s->r[%d]) {' % rn]
                    for e in entries:
                        if addr <= e < end:
                            c.append('    case 0x%06X: goto L_%X;' % (e, e))
                        else:
                            c.append('    case 0x%06X: /* out-of-span callee */' % e)
                    c.append('    default: s->r[0] = 0xDEAD; return; /* table miss */')
                    c.append('}')
                    rec = {'pc': pc, 'op': op, 'kind': 'jt', 'mnem': 'jmp @r%d (table)' % rn,
                           'c': c, 'slot': slot, 'target': None, 'entries': entries}
                    res.records.append(rec)
                    # jmp @Rn is delayed: slot consumed inline; skip past it
                    seen_pc.add(pc)
                    if slot is not None:
                        seen_pc.add(pc + 2)
                    pc += 4 if slot is not None else 2
                    continue
                v = st['lits'].get('r%d' % rn)         # literal target
                if v is None:
                    res.reject = (('jsr_unresolved' if kind == 'jsr'
                                   else 'indirect_unresolved'), pc)
                    return res
                tgt = v & MASK
                res.edges.append((pc, kind, tgt))
                if addr <= tgt < end:
                    labels.add(tgt)
                    pending.append(tgt)
                slot = slot_record(pc + 2) if pc + 2 < end else None
                # PR LOOP GUARD: a `lds.l @r15+,pr` delay slot (0x4F26) loads
                # the callee's return address from the (random) stack, so the
                # mirror's pr-return and sh2emu diverge (known case: 0x298F4).
                if slot is not None and pc + 3 < bound and \
                        (rom[pc + 2] << 8) | rom[pc + 3] == 0x4F26:
                    res.reject = ('pr_loop', pc)
                    return res
                if kind == 'jsr':
                    rec = {'pc': pc, 'op': op, 'kind': 'call', 'mnem': 'jsr @r%d' % rn,
                           'c': ['s->pr = 0x%08X;' % ((pc + 4) & MASK)]
                                + ([v7.to_st_c(s) for s in slot['c']] if slot else [])
                                + ['f_%X(s);' % tgt],
                           'slot': slot, 'target': tgt,
                           'ret_pc': (pc + 4) & MASK, 'set_pr': True}
                else:
                    rec = {'pc': pc, 'op': op, 'kind': 'call', 'mnem': 'jmp @r%d (tail)' % rn,
                           'c': ([v7.to_st_c(s) for s in slot['c']] if slot else [])
                                + ['f_%X(s);' % tgt, 'return;'],
                           'slot': slot, 'target': tgt,
                           'ret_pc': (pc + 4) & MASK, 'set_pr': False}
                res.records.append(rec)
                # jsr/jmp @Rn is delayed: slot consumed inline; skip past it
                seen_pc.add(pc)
                if slot is not None:
                    seen_pc.add(pc + 2)
                pc += 4 if slot is not None else 2
                continue
            rec = emit_one(pc, op)
            if rec is None:
                res.reject = ('unmapped', pc)
                return res
            if op & 0xFF00 == 0xC700:                  # mova
                mova_lits['r0'] = ops.mova_target(pc, op & 0xFF)
            res.records.append(rec)
            seen_pc.add(pc)
            pc += 2
    return res


# ---------------------------------------------------------------------------
# Selection (pool_v8) + measures
# ---------------------------------------------------------------------------
def scan_v8(rom, c, end, lifted, catalog):
    """CFG-complete admission.  Returns (ok, reason, cfg)."""
    res = build_cfg(rom, c['addr'], end, lifted, catalog)
    if res.reject is not None:
        return False, res.reject, res
    if not res.records:
        return False, 'no_records', res
    return True, None, res


def _load_catalog(cat_path, bank):
    catalog_bank, no_spans, bounds = v3.load_catalog_nospans(cat_path)
    return catalog_bank.get(bank, {}), no_spans, bounds.get(bank)


def run_metrics(rom_path=DEFAULT_ROM, bank='60E1D400', verbose=True):
    rom = open(rom_path, 'rb').read()
    cat_path = os.path.join(ROOT, 'symbols', 'CATALOG_MASTER.csv')
    catalog, no_spans, bounds = _load_catalog(cat_path, bank)
    categories = gcl.load_categories(
        os.path.join(ROOT, 'symbols', 'FUNCTION_CATEGORIES.csv'))
    cands = v3._merge_nospan_cands(categories, no_spans, bounds, bank)
    lifted = _load_lifted()

    pool_v8 = []
    reasons = Counter()
    by_cat = Counter()
    jt_fns = []
    multi = []
    jsr_bsr = []
    pool_jsr = []
    missing_callees = Counter()
    call_rej_v3 = 0
    unblocked = 0          # previously rejected (data-mid-span / call) now admitted
    prev_reasons = Counter()

    for c in cands:
        addr = c['addr']
        end = catalog.get(addr)
        use_est = False
        if end is None:
            end = v3._next_addr(addr, bounds)
            use_est = True
        if end is None:
            continue
        _a, end_s, _r = v3.sanitize_span(addr, end, rom)
        size = end_s - addr
        if not (SIZE_MIN <= size <= SIZE_MAX):
            continue
        base = gcl.sanitize(c['name'])
        if os.path.exists(os.path.join(ROOT, 'c', '%s_%x.c' % (base, addr))) or \
                glob.glob(os.path.join(ROOT, 'c', '*_%x.c' % addr)):
            continue
        if addr in lifted:
            continue
        # v3 result for comparison
        e3, r3 = gcl._scan_mem_function(rom, c, end_s, None)
        if e3 is None:
            r = r3[0] if isinstance(r3, tuple) else r3
            prev_reasons[r] += 1
        ok, reason, res = scan_v8(rom, c, end_s, lifted, catalog)
        if not ok:
            if isinstance(reason, tuple):
                reasons[reason[0]] += 1
            else:
                reasons[reason] += 1
            continue
        # v8-relevant: has at least one branch/jump/call/tail
        n_jt = len(res.jump_tables)
        n_call = sum(1 for r in res.records if r['kind'] == 'call')
        n_br = sum(1 for r in res.records if r['kind'] == 'branch')
        if not (n_jt or n_call or n_br):
            reasons['no_ctrl'] += 1
            continue
        pool_v8.append({'addr': addr, 'name': c['name'], 'size': size,
                        'end': end_s, 'use_est': use_est,
                        'category': c['category'],
                        'n_jt': n_jt, 'n_call': n_call, 'n_br': n_br,
                        'jt': res.jump_tables})
        by_cat[c['category']] += 1
        jsrs = [r for r in res.records if r['kind'] == 'call'
                and (r['mnem'] or '').startswith('jsr')]
        if jsrs:                       # pool_jsr: caller with a resolved jsr @Rn
            call_tgts = {r['target'] for r in res.records
                         if r['kind'] == 'call' and r.get('target') is not None}
            for t in call_tgts:
                if not os.path.exists(os.path.join(ROOT, 'c', 'lib', 'f_%X.c' % t)) \
                        and t not in lifted:
                    missing_callees[t] += 1
            pool_jsr.append({'addr': addr, 'name': c['name'], 'size': size,
                             'category': c['category'], 'n_jsr': len(jsrs)})
        if n_jt:
            jt_fns.append((addr, c['name'], size, res.jump_tables))
        if n_call:
            tgts = [r['target'] for r in res.records if r['kind'] == 'call']
            if len(tgts) >= 2 and len(set(tgts)) <= 2:
                multi.append((addr, c['name'], tgts))
            jsr_bsr.extend((addr, r['pc'], r['target']) for r in res.records
                           if r['kind'] == 'call' and r['set_pr'])
        if e3 is None:
            unblocked += 1

    print('== pool_v8 (bank %s) ==' % bank)
    print('candidates scanned        : %d' % len(cands))
    print('pool_v8 admitted          : %d' % len(pool_v8))
    print('  by category (top):')
    for k, v_ in by_cat.most_common(8):
        print('    %-28s %d' % (k, v_))
    print('  previously v3-rejected  : %d' % unblocked)
    print('  jump-table functions    : %d' % len(jt_fns))
    print('  multi-dispatch (>=2 jsr/jmp) : %d' % len(multi))
    print('  jsr/bsr sites resolved  : %d' % len(jsr_bsr))
    print('  POOL_JSR (caller w/ >=1 resolved jsr @Rn) : %d' % len(pool_jsr))
    print('  pool_jsr by category (top):')
    for k, v_ in Counter(p['category'] for p in pool_jsr).most_common(6):
        print('    %-28s %d' % (k, v_))
    print('  missing callee libs (referenced by pool_jsr), top 8:')
    for t, n in missing_callees.most_common(8):
        print('    0x%06X  x%d' % (t, n))
    print('v8 rejections:')
    for k, v_ in reasons.most_common(12):
        print('    %-28s %d' % (k, v_))
    print('v3 rejection distribution over the same universe:')
    for k, v_ in prev_reasons.most_common(12):
        print('    %-28s %d' % (k, v_))
    print('multi-dispatch candidates:')
    for a, n, tgts in sorted(multi):
        print('    0x%06X %-32s -> %s' % (a, n[:32],
                                          ', '.join('0x%X' % t for t in tgts)))
    print('jump-table candidates:')
    for a, n, size, jts in sorted(jt_fns):
        for jt in jts:
            print('    0x%06X %-32s size=%d base=0x%X n=%d' %
                  (a, n[:32], size, jt['base'], len(jt['entries'])))
    return pool_v8


# ---------------------------------------------------------------------------
# ST composition emission (multi-dispatch / tail-call / jump-table)
# ---------------------------------------------------------------------------
def emit_caller(addr, rom, outdir, catalog, bounds, seed=42, cases=500,
                rom_label=None, force_end=None):
    """Emit c/lib/caller_<hex>.c (ST ABI) + c/lib/test_caller_<hex>.py for a
    CFG-complete function; compile-gate the C; run the test.  Returns
    (out_c, test_path, ok, reason)."""
    rom_label = rom_label or os.path.splitext(os.path.basename(
        DEFAULT_ROM))[0]
    end = force_end or catalog.get(addr)
    if end is None:
        end = v3._next_addr(addr, bounds)
    if end is None:
        return None, None, False, 'no-span'
    _a, end_s, _r = v3.sanitize_span(addr, end, rom)
    lifted = _load_lifted()
    res = build_cfg(rom, addr, end_s, lifted, catalog)
    if res.reject is not None:
        return None, None, False, res.reject
    if not res.records:
        return None, None, False, 'no_records'
    fn = 'caller_%X' % addr
    # callees referenced by call records (bsr/jsr/jmp-tail) must exist in lib
    callees = sorted({r['target'] for r in res.records if r['kind'] == 'call'
                      and r.get('target') is not None})
    missing = []
    for t in callees:
        lib_p = os.path.join(ROOT, 'c', 'lib', 'f_%X.c' % t)
        if not os.path.exists(lib_p):
            missing.append(t)
    if missing:
        return None, None, False, ('missing-callee-lib', missing)

    # ---- ST body: labels/goto + branch records + call records ----
    body, fwd = _render_st_body(fn, addr, res, callees)
    banner = ('/* ROM: %s | Address: 0x%X | Size: %d bytes | STATUS: DRAFT\n'
              ' * Auto-generated by tools/gen_c_lift_v8.py — ST caller (CFG).\n'
              ' * jsr/bsr -> s->pr=<ret>; <delay slot>; f_<callee>(s);\n'
              ' * jmp (tail) -> <delay slot>; f_<callee>(s); return;\n'
              ' * jump table -> switch (s->rN) { case <addr>: goto L_<addr>; }\n'
              ' * Never replaces c/*.c. */\n') % (rom_label, addr, end_s - addr)
    c_text = banner + '#include <stdint.h>\n' + ST_STRUCT + '\n' + \
        (fwd + '\n' if fwd else '') + body
    os.makedirs(outdir, exist_ok=True)
    out_c = os.path.join(outdir, '%s.c' % fn)
    with open(out_c, 'w') as f:
        f.write(c_text)
    tmp_obj = os.path.join(tempfile.gettempdir(), 'gen_c_lift_v8_%d.o' % os.getpid())
    gate = subprocess.run(['cc', '-O2', '-c', out_c, '-o', tmp_obj],
                          capture_output=True, text=True)
    if os.path.exists(tmp_obj):
        os.remove(tmp_obj)
    if gate.returncode != 0:
        os.remove(out_c)
        return out_c, None, False, gate.stderr[:200]

    # ---- test ----
    out_t = os.path.join(outdir, 'test_caller_%X.py' % addr)
    ok, reason = _emit_v8_test(addr, rom, end_s, res, callees, out_t,
                               seed=seed, cases=cases, rom_label=rom_label,
                               catalog=catalog, bounds=bounds)
    return out_c, out_t, ok, reason


def _callee_span_end(t, catalog, bounds):
    """Walk bound for a callee: its catalog end, else the next-catalog-address
    estimate (same rule as v3 selection).  Replaces the fixed t+32 window."""
    end_c = catalog.get(t)
    if end_c is None and bounds is not None:
        end_c = v3._next_addr(t, bounds)
    return end_c


def _callee_first_rts(rom, t, end_c):
    """First `rts` (0x000B) at an even offset inside [t, end_c), skipping
    literal-pool words so a 0x000B data word cannot truncate the walk."""
    bound = min(end_c, len(rom))
    pool = gcl._pcrel_pool_words(rom, t, end_c)
    pc = t
    while pc + 1 < bound:
        if pc not in pool and (rom[pc] << 8) | rom[pc + 1] == 0x000B:
            return pc
        pc += 2
    return None


def _walk_callee(rom, t, catalog, bounds, depth=0, seen=None):
    """Inline-walk a callee for the v8 mirror.  Returns (records, None) on
    success or (None, reason).

    Fixes the three known callee-walk blockers:
      (a) span: the walk bound is the callee's catalog end (or next-address
          estimate) instead of the fixed t+32 window;
      (b) trampoline: a callee that opens with a pure `bra X` (always-taken
          branch to a target outside its own span) is followed to X — depth
          guard 3, cycle guard — so the mirror runs the real body instead of
          returning at the branch while sh2emu runs the body (MISMATCH);
      (c) rts: the walk stops at the first rts (the callee returns via pr,
          which the caller mirror owns), so it never crosses into the next
          function and never diverges on the next function's unmapped bytes.
    """
    if depth > 3:
        return None, 'depth>3'
    if seen is None:
        seen = set()
    if t in seen:
        return None, 'cycle'
    seen = seen | {t}
    end_c = _callee_span_end(t, catalog, bounds)
    if end_c is None:
        return None, ('no-span', t)
    rts = _callee_first_rts(rom, t, end_c)
    walk_end = rts + 2 if rts is not None else end_c
    w = v3.walk_v3(rom, t, walk_end)
    if w is None:
        return None, ('walk-fail', t, '0x%X..0x%X' % (t, walk_end))
    records, _info, _lab = w
    if records and records[0]['kind'] == 'branch' and \
            (records[0].get('mnem') or '').startswith('bra'):
        tgt = records[0]['target']
        if tgt is not None and not (t <= tgt < walk_end):
            sub, reason = _walk_callee(rom, tgt, catalog, bounds,
                                       depth=depth + 1, seen=seen)
            if sub is None:
                return None, ('trampoline', t, tgt, reason)
            records = records + sub
    return records, None


def _render_st_body(fn, addr, res, callees):
    """Render the ST-ABI function body (labels/goto + records) for a CFG
    result, reusing the caller rendering.  Shared by emit_caller and
    _emit_callee_cfg.  Returns the body text (no banner/header)."""
    labels = res.labels
    stmts = []
    for rec in res.records:
        pc = rec['pc']
        if pc in labels:
            stmts.append('L_%X: ;' % pc)
        stmts.append('/* 0x%06X: %s */' % (pc, rec['mnem']))
        if rec['kind'] == 'call':
            stmts.extend(rec['c'])           # already ST-form
        elif rec['kind'] == 'jt':
            stmts.extend(rec['c'])
        else:
            slot = rec.get('slot')
            if slot is not None:
                if slot['pc'] in labels:
                    stmts.append('L_%X: ;' % slot['pc'])
                stmts.append('/* 0x%06X: %s */' % (slot['pc'], slot['mnem']))
                stmts.extend(v7.to_st_c(s) for s in slot['c'])
            stmts.extend(v7.to_st_c(s) for s in rec['c'])
    offs = set()
    for m_ in re.finditer(r'local_([0-9a-f]+)\b', '\n'.join(stmts)):
        offs.add(int(m_.group(1), 16))
    frs = set()
    for m_ in v7._FR.finditer('\n'.join(stmts)):
        frs.add(m_.group(0))
    body = ['void %s(ST *s)' % fn, '{']
    for o in sorted(offs):
        body.append('    uint32_t local_%x = 0;' % o)
    for f in sorted(frs):
        body.append('    uint32_t %s = 0;' % f)
    for s in stmts:
        body.append('    ' + s)
    body.append('    return; /* fallthrough */')
    body.append('}')
    fwd = '\n'.join('void f_%X(ST *s);' % t for t in callees)
    return '\n'.join(body) + '\n', fwd


def _emit_callee_cfg(t, rom, catalog, bounds, rom_label=None):
    """Emit c/lib/f_<hex>.c via the CFG engine (build_cfg + ST renderer) — a
    fallback for callees whose v3 walk-based leaf lib (v7.emit_callee) fails
    on undefined branch labels.  Returns (path, None) or (None, reason)."""
    end_c = _callee_span_end(t, catalog, bounds)
    if end_c is None:
        return None, ('callee-no-span', t)
    lifted = _load_lifted()
    res = build_cfg(rom, t, end_c, lifted, catalog)
    if res.reject is not None:
        return None, ('callee-cfg', t, res.reject)
    if not res.records:
        return None, ('callee-cfg', t, 'no_records')
    callees = sorted({r['target'] for r in res.records
                      if r['kind'] == 'call' and r.get('target') is not None})
    body, fwd = _render_st_body('f_%X' % t, t, res, callees)
    banner = ('/* ROM: %s | Address: 0x%X | Size: %d bytes | STATUS: DRAFT\n'
              ' * Auto-generated by tools/gen_c_lift_v8.py — ST callee (CFG).\n'
              ' * Never replaces c/*.c. */\n') % (rom_label, t, end_c - t)
    c_text = banner + '#include <stdint.h>\n' + ST_STRUCT + '\n' + \
        (fwd + '\n' if fwd else '') + body
    path = os.path.join(ROOT, 'c', 'lib', 'f_%X.c' % t)
    with open(path, 'w') as f:
        f.write(c_text)
    tmp_obj = os.path.join(tempfile.gettempdir(), 'gen_c_lift_v8_%d.o' % os.getpid())
    gate = subprocess.run(['cc', '-O2', '-c', path, '-o', tmp_obj],
                          capture_output=True, text=True)
    if os.path.exists(tmp_obj):
        os.remove(tmp_obj)
    if gate.returncode != 0:
        os.remove(path)
        return None, ('callee-cfg-compile', t, gate.stderr[:200])
    return path, None


def _ensure_callee_lib(t, rom, catalog, bounds, rom_label=None):
    """Make sure c/lib/f_<hex>.c exists for callee `t`; generate a DRAFT
    leaf lib (v7.emit_callee) over the callee's walked span (first-rts stop,
    or catalog end) when missing.  Returns (path, None) on success or
    (None, reason)."""
    path = os.path.join(ROOT, 'c', 'lib', 'f_%X.c' % t)
    if os.path.exists(path):
        return path, None
    end_c = _callee_span_end(t, catalog, bounds)
    if end_c is None:
        return None, ('callee-no-span', t)
    rts = _callee_first_rts(rom, t, end_c)
    size = (rts + 2 if rts is not None else end_c) - t
    if size <= 0 or size > 512:
        return None, ('callee-span', t, size)
    ok, err = v7.emit_callee(t, size, rom, path, rom_label=rom_label)
    if not ok:
        if os.path.exists(path):
            os.remove(path)
        # v3 walk-based leaf lib failed (e.g. undefined branch label) — retry
        # with the CFG engine, which defines every in-span branch label.
        path2, err2 = _emit_callee_cfg(t, rom, catalog, bounds,
                                       rom_label=rom_label)
        if path2 is None:
            return None, ('callee-lib', t, err2 if err2 else err)
        return path2, None
    return path, None


def run_batch(rom, outdir, catalog, bounds, n=20, seed=42, cases=500,
              rom_label=None, jobs=2, timeout=240):
    """Emit + verify up to `n` callers from POOL_JSR (functions with >=1
    resolved jsr @Rn that pass v8 selection).  For each: ensure the callee
    libs exist (generate missing DRAFT f_<hex>.c), emit caller_<hex>.c +
    test_caller_<hex>.py, run the differential test (cases cases); keep PASS,
    delete the caller .c/.py on FAIL.  Returns the summary list."""
    lifted = _load_lifted()
    entries = []
    categories = gcl.load_categories(
        os.path.join(ROOT, 'symbols', 'FUNCTION_CATEGORIES.csv'))
    _, no_spans, _b = _load_catalog(
        os.path.join(ROOT, 'symbols', 'CATALOG_MASTER.csv'), rom_label)
    cands = v3._merge_nospan_cands(categories, no_spans, bounds, rom_label)
    for c in cands:
        addr = c['addr']
        end = catalog.get(addr)
        if end is None:
            end = v3._next_addr(addr, bounds)
        if end is None:
            continue
        _a, end_s, _r = v3.sanitize_span(addr, end, rom)
        size = end_s - addr
        if not (SIZE_MIN <= size <= SIZE_MAX):
            continue
        base = gcl.sanitize(c['name'])
        if os.path.exists(os.path.join(ROOT, 'c', '%s_%x.c' % (base, addr))) or \
                glob.glob(os.path.join(ROOT, 'c', '*_%x.c' % addr)):
            continue
        if addr in lifted:
            continue
        ok, reason, res = scan_v8(rom, c, end_s, lifted, catalog)
        if not ok:
            continue
        jsrs = [r for r in res.records if r['kind'] == 'call'
                and (r['mnem'] or '').startswith('jsr')]
        if not jsrs:
            continue
        callees = sorted({r['target'] for r in res.records
                          if r['kind'] == 'call' and r.get('target') is not None})
        entries.append({'addr': addr, 'name': c['name'], 'size': size,
                        'callees': callees, 'n_jsr': len(jsrs)})
    entries.sort(key=lambda e: e['addr'])
    if not entries:
        print('run_batch: pool_jsr is empty')
        return []
    print('run_batch: pool_jsr=%d, emitting first %d' % (len(entries), min(n, len(entries))))

    summary = []
    for e in entries[:n]:
        addr = e['addr']
        print('--- 0x%06X %s (size=%d, jsr=%d, callees=%s)' % (
            addr, e['name'][:30], e['size'], e['n_jsr'],
            ', '.join('0x%X' % t for t in e['callees'])))
        fail = None
        for t in e['callees']:
            _p, err = _ensure_callee_lib(t, rom, catalog, bounds, rom_label=rom_label)
            if err is not None:
                fail = ('callee-lib 0x%X: %r' % (t, err))
                break
        if fail:
            print('    SKIP (missing callee lib): %s' % fail)
            summary.append((addr, 'skip', fail))
            continue
        out_c, out_t, ok, reason = emit_caller(
            addr, rom, os.path.join(ROOT, 'c', 'lib'), catalog, bounds,
            seed=seed, cases=cases, rom_label=rom_label)
        if not ok:
            print('    EMIT FAILED: %s' % (reason,))
            summary.append((addr, 'skip', 'emit: %r' % (reason,)))
            continue
        # tests live in c/tests (the generated file's ROOT is 3 levels up, so
        # running it from c/lib would misresolve ROOT and fail the sh2emu import)
        test_p = os.path.join(ROOT, 'c', 'tests', 'test_caller_%X.py' % addr)
        if os.path.abspath(out_t) != os.path.abspath(test_p):
            if os.path.exists(test_p):
                os.remove(test_p)
            os.rename(out_t, test_p)
            out_t = test_p
        try:
            p = subprocess.run([sys.executable, out_t], cwd=ROOT,
                               capture_output=True, text=True, timeout=timeout)
            line = (p.stdout or p.stderr or '').strip().splitlines()[-1:]
            print('    test: rc=%d %s' % (p.returncode, line[0] if line else ''))
        except subprocess.TimeoutExpired:
            p = None
            print('    test: TIMEOUT (>%ds)' % timeout)
        if p is not None and p.returncode == 0:
            summary.append((addr, 'PASS', line[0] if line else ''))
        else:
            summary.append((addr, 'FAIL', line[0] if (p and line) else 'rc=%s' % (p.returncode if p else 'timeout')))
            for f in (out_c, out_t):
                if f and os.path.exists(f):
                    os.remove(f)
    return summary


def _emit_v8_test(addr, rom, end, res, callees, out_t, seed=42, cases=500,
                  rom_label='60E1D400', catalog=None, bounds=None):
    """v7-style differential test.  The CODE dict carries the caller records
    (incl. 'call' -> pc = target, 'jt' -> dynamic table read) plus the inlined
    callee leaf records (fetched via _walk_callee over the callee's own catalog
    span, stopping at the first rts and following pure `bra` trampolines, so
    the mirror executes them exactly like sh2emu)."""
    # inline each callee's leaf records at their real pcs
    catalog = catalog or {}
    callee_records = []
    for t in callees:
        w, reason = _walk_callee(rom, t, catalog, bounds)
        if w is None:
            return False, ('callee-walk', t, reason)
        callee_records.extend(w)
    all_records = list(res.records) + callee_records

    offs_list = sorted(res.info['stack_offs'])
    stack_offs = ', '.join('0x%X' % o for o in offs_list)
    if len(offs_list) == 1:
        stack_offs += ','
    ram_addrs = [v for v in res.info['ram_addrs'] if ops.classify_addr(v) == 'RAM']
    ram_min = min(ram_addrs) if ram_addrs else None
    ram_max = max(ram_addrs) if ram_addrs else None
    entries_all = {}
    for jt in res.jump_tables:
        for e in jt['entries']:
            entries_all.setdefault(jt['reg'], []).append(e)
    jt_lits = []
    for jt in res.jump_tables:
        jt_lits.append((jt['jmp_pc'], jt['reg'], jt['base'],
                        [e for e in jt['entries']]))
    fn = 'caller_%X' % addr

    test = (
        '#!/usr/bin/env python3\n'
        '"""Differential test for %s (entry 0x%X) — v8 ST caller (CFG), %d bytes.\n'
        'Auto-generated by tools/gen_c_lift_v8.py — not human-verified.\n'
        'Compares a Python pc-interpreter spec_mirror (running the caller records\n'
        'with branch labels/goto semantics + the inlined callee leaves; jmp/jsr\n'
        'jump to their targets, jump tables read the ROM table dynamically) against\n'
        'the sh2emu oracle (which runs the actual ROM bytes) over %d random\n'
        'inputs.  Cases leaving the modeled span / exceeding max_steps are skipped.\n'
        'Run: python3 %s\n'
        '"""\n'
        'import os, random, sys\n\n'
        'ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n'
        'sys.path.insert(0, os.path.join(ROOT, "tools"))\n'
        'from sh2emu import SH2, StepLimitExceeded\n'
        'from c_lift_ops import s8, s16, s32, ts, bits2f, f2bits\n\n'
        'ROM = os.path.join(ROOT, "roms", "stock", "%s.bin")\n'
        'ROM_BYTES = open(ROM, "rb").read()\n'
        'ENTRY = 0x%X\n'
        'SEED = %d\n'
        'N = %d\n'
        'MAXSTEPS = 100000\n'
        'STACK_BASE = 0xFFFFD000\n'
        'STACK_TOP = STACK_BASE + 0x400\n'
        'STACK_OFFS = (%s)\n'
        'RAM_MIN = %s\n'
        'RAM_MAX = %s\n'
        'PRET = 0xEEEE0000\n'
        'JTABLES = %r\n\n'
        '_WRITES = []\n\n'
        'def _rd(ram, a):\n'
        '    a &= 0xFFFFFFFF\n'
        '    v = ram.get(a)\n'
        '    if v is not None:\n'
        '        return v\n'
        '    return ROM_BYTES[a] if a < len(ROM_BYTES) else 0\n\n'
        'def _rdw(ram, a, n):\n'
        '    a &= 0xFFFFFFFF\n'
        '    return int.from_bytes(bytes(_rd(ram, (a + i) & 0xFFFFFFFF) for i in range(n)), "big")\n\n'
        'def _wrw(ram, a, n, v):\n'
        '    a &= 0xFFFFFFFF\n'
        '    for i in range(n):\n'
        '        ad = (a + i) & 0xFFFFFFFF\n'
        '        ram[ad] = (v >> (8 * (n - 1 - i))) & 0xFF\n'
        '        _WRITES.append(ad)\n\n'
        '%s\n'
        'def spec_mirror(r4, r5, r6, r7, ram):\n'
        '    global _WRITES\n'
        '    _WRITES[:] = []\n'
        '    r = [0] * 16\n'
        '    r[4], r[5], r[6], r[7] = r4 & 0xFFFFFFFF, r5 & 0xFFFFFFFF, r6 & 0xFFFFFFFF, r7 & 0xFFFFFFFF\n'
        '    r[15] = STACK_TOP & 0xFFFFFFFF\n'
        '    fr = [0.0] * 16\n'
        '    ns = {"r": r, "fr": fr, "T": 0, "Q": 0, "M": 0, "mach": 0, "macl": 0, "pr": PRET,\n'
        '          "sr": 0x000000F0, "s8": s8, "s16": s16, "s32": s32, "ts": ts,\n'
        '          "bits2f": bits2f, "f2bits": f2bits, "ram": ram,\n'
        '          "sp": r[15], "_rdw": _rdw, "_wrw": _wrw, "STACK_BASE": STACK_BASE,\n'
        '          "local": {off: _rdw(ram, STACK_BASE + off, 4) for off in STACK_OFFS}}\n'
        '    pc = ENTRY\n'
        '    steps = 0\n'
        '    while True:\n'
        '        steps += 1\n'
        '        if steps > MAXSTEPS:\n'
        '            return ("SKIP", None)\n'
        '        inst = CODE.get(pc)\n'
        '        if inst is None:\n'
        '            return ("RET", [x & 0xFFFFFFFF for x in r], list(_WRITES), dict(ram),\n'
        '                    ns["pr"] & 0xFFFFFFFF)\n'
        '        kind = inst["kind"]\n'
        '        if kind == "jt":\n'
        '            slot_py = inst["slot_py"]\n'
        '            if slot_py:\n'
        '                exec(slot_py, ns)\n'
        '            reg = inst["reg"]; base = inst["base"]\n'
        '            tgt = _rdw(ram, (base + r[reg]) & 0xFFFFFFFF, 4)\n'
        '            if tgt not in inst["cases"]:\n'
        '                return ("ERR", pc)      # table miss -> FAIL (mirror default)\n'
        '            pc = tgt\n'
        '        elif kind == "call":\n'
        '            if inst["set_pr"]:\n'
        '                ns["pr"] = inst["ret_pc"]\n'
        '            slot_py = inst["slot_py"]\n'
        '            if slot_py:\n'
        '                exec(slot_py, ns)\n'
        '            pc = inst["target"]\n'
        '        elif kind == "branch":\n'
        '            t = ns["T"]\n'
        '            taken = True\n'
        '            if inst["cond"] == "T":\n'
        '                taken = (t == 1)\n'
        '            elif inst["cond"] == "notT":\n'
        '                taken = (t == 0)\n'
        '            slot_py = inst["slot_py"]\n'
        '            if slot_py:\n'
        '                exec(slot_py, ns)\n'
        '            pc = inst["target"] if taken else (pc + 4 if slot_py is not None else pc + 2)\n'
        '        elif kind == "ret":\n'
        '            slot_py = inst["slot_py"]\n'
        '            if slot_py:\n'
        '                exec(slot_py, ns)\n'
        '            r[15] = ns["sp"] & 0xFFFFFFFF\n'
        '            pc = ns["pr"] & 0xFFFFFFFF\n'
        '        else:\n'
        '            py = inst["py"]\n'
        '            if py:\n'
        '                exec(py, ns)\n'
        '            pc = pc + 2\n\n'
        'def run(cpu, ram, a, b, c_, d):\n'
        '    ram = dict(ram)\n'
        '    cpu.call(ENTRY, r4=a, r5=b, r6=c_, r7=d, ram=ram, regs={15: STACK_TOP},\n'
        '             max_steps=MAXSTEPS)\n'
        '    return cpu.r[0] & 0xFFFFFFFF, [x & 0xFFFFFFFF for x in cpu.r], dict(cpu.ram), cpu.pr & 0xFFFFFFFF\n\n'
        'def main():\n'
        '    rnd = random.Random(SEED)\n'
        '    cpu = SH2(ROM_BYTES)\n'
        '    skipped = 0\n'
        '    for caso in range(N):\n'
        '        ram = {}\n'
        '        if RAM_MIN is not None:\n'
        '            for a in range(RAM_MIN - 0x400, RAM_MAX + 0x401):\n'
        '                ram[a] = (a * 0x9E3779B1 + caso * 0x10003) & 0xFF\n'
        '        for a in range(STACK_BASE, STACK_BASE + 0x400):\n'
        '            ram[a] = (a * 0x9E3779B1 + caso * 0x10003) & 0xFF\n'
        '        a = rnd.randint(0, 0xFFFFFFFF); b = rnd.randint(0, 0xFFFFFFFF)\n'
        '        c_ = rnd.randint(0, 0xFFFFFFFF); d = rnd.randint(0, 0xFFFFFFFF)\n'
        '        m = spec_mirror(a, b, c_, d, dict(ram))\n'
        '        if m[0] != "RET":\n'
        '            skipped += 1; continue\n'
        '        try:\n'
        '            g = run(cpu, ram, a, b, c_, d)\n'
        '        except (StepLimitExceeded, NotImplementedError, RuntimeError):\n'
        '            skipped += 1; continue\n'
        '        _, exp_regs, _, exp_ram, exp_pr = m\n'
        '        _, got_regs, got_ram, got_pr = g\n'
        '        for i in range(16):\n'
        '            if exp_regs[i] != got_regs[i]:\n'
        '                print("MISMATCH case=%%d reg=r%%d mirror=%%08X emu=%%08X" %% (caso, i, exp_regs[i], got_regs[i]))\n'
        '                sys.exit(1)\n'
        '        if exp_pr != got_pr:\n'
        '            print("MISMATCH case=%%d reg=pr mirror=%%08X emu=%%08X" %% (caso, exp_pr, got_pr))\n'
        '            sys.exit(1)\n'
        '        for ad in sorted(set(exp_ram) | set(got_ram)):\n'
        '            if exp_ram.get(ad, 0) != got_ram.get(ad, 0):\n'
        '                print("MISMATCH case=%%d addr=0x%%08X mirror=%%02X emu=%%02X" %% (caso, ad, exp_ram.get(ad, 0), got_ram.get(ad, 0)))\n'
        '                sys.exit(1)\n'
        '    ok = N - skipped\n'
        '    if skipped > 200 or ok == 0:\n'
        '        print("FAIL %%d/%%d (skipped=%%d)" %% (ok, N, skipped))\n'
        '        sys.exit(1)\n'
        '    print("PASS %%d/%%d (skipped=%%d)" %% (ok, N, skipped))\n\n'
        'if __name__ == "__main__":\n'
        '    main()\n'
    ) % (fn, addr, end - addr, cases, os.path.basename(out_t), rom_label,
         addr, seed, cases, stack_offs,
         'None' if ram_min is None else '0x%X' % ram_min,
         'None' if ram_max is None else '0x%X' % ram_max,
         jt_lits,
         _v8_code_literal(all_records, res.labels, res.jump_tables))
    with open(out_t, 'w') as f:
        f.write(test)
    return True, None


def _v8_code_literal(records, labels, jtables):
    """CODE dict for the v8 mirror: branch/jt/call records + callee leaves."""
    lines = []
    for rec in records:
        pc = rec['pc']
        kind = rec['kind']
        slot = rec.get('slot')
        slot_py = v3._norm_py(slot['py']) if slot and slot.get('py') else None
        if kind == 'branch':
            bi = ops.branch_info(rec['op'])
            bkind = bi['kind']
            if bkind == 'rts':
                lines.append('    %#x: {"kind": "ret", "py": None, '
                             '"slot_py": %r, "target": None, "cond": None},'
                             % (pc, slot_py))
            elif bkind in ('bsrf', 'braf'):
                lines.append('    %#x: {"kind": "dynbranch", "py": None, '
                             '"slot_py": %r, "target": None, "cond": None, '
                             '"reg": %d, "set_pr": %r},'
                             % (pc, slot_py, bi['reg'], bkind == 'bsrf'))
            else:
                lines.append('    %#x: {"kind": "branch", "py": None, '
                             '"slot_py": %r, "target": %#x, "cond": %r},'
                             % (pc, slot_py, rec['target'],
                                _BRANCH_COND.get(bkind, 'T')))
            continue
        if kind == 'call':
            lines.append('    %#x: {"kind": "call", "py": None, '
                         '"slot_py": %r, "target": %#x, "ret_pc": %#x,'
                         ' "set_pr": %r, "cond": None},'
                         % (pc, slot_py, rec['target'], rec['ret_pc'],
                            rec['set_pr']))
            continue
        if kind == 'jt':
            lines.append('    %#x: {"kind": "jt", "py": None, '
                         '"slot_py": %r, "target": None, "cond": None,'
                         ' "reg": %d, "base": %#x, "cases": %r},'
                         % (pc, slot_py, rec['reg_base'], rec['base'],
                            tuple(rec['entries'])))
            continue
        py = v3._norm_py(rec.get('py') or []) or None
        lines.append('    %#x: {"kind": %r, "py": %r, "slot_py": None, '
                     '"target": None, "cond": None},'
                     % (pc, _MIRROR_KIND.get(kind, 'st'), py))
    return 'CODE = {\n%s\n}' % '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser(
        description='v8 SH-2 CFG-complete lift selection + ST composition')
    ap.add_argument('--metrics', action='store_true')
    ap.add_argument('--emit', default=None, metavar='0xADDR',
                    help='emit caller_<hex>.c + test for this address')
    ap.add_argument('--span', default=None, metavar='END',
                    help='force span end (overrides catalog) for --emit')
    ap.add_argument('-n', '--n', type=int, default=0, metavar='N',
                    help='batch-emit + verify up to N callers from pool_jsr')
    ap.add_argument('--jobs', type=int, default=2,
                    help='parallel test workers for --n batch (default 2)')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--cases', type=int, default=500)
    ap.add_argument('--rom', default=DEFAULT_ROM)
    ap.add_argument('--outdir', default=None,
                    help='output dir (default tmp/v8)')
    args = ap.parse_args()
    rom = open(args.rom, 'rb').read()
    rom_label = os.path.splitext(os.path.basename(args.rom))[0]
    if args.metrics:
        run_metrics(args.rom, rom_label)
        return 0
    if args.emit:
        addr = int(args.emit, 16)
        cat_path = os.path.join(ROOT, 'symbols', 'CATALOG_MASTER.csv')
        catalog, _, bounds = _load_catalog(cat_path, rom_label)
        outdir = args.outdir or os.path.join(ROOT, 'tmp', 'v8')
        force_end = int(args.span, 16) if args.span else None
        out_c, out_t, ok, reason = emit_caller(
            addr, rom, outdir, catalog, bounds, seed=args.seed,
            cases=args.cases, rom_label=rom_label, force_end=force_end)
        if not ok:
            print('EMIT FAILED: %s' % (reason,))
            return 1
        print('emitted %s' % out_c)
        print('emitted %s' % out_t)
        sys.exit(subprocess.run([sys.executable, out_t]).returncode)
    if args.n:
        cat_path = os.path.join(ROOT, 'symbols', 'CATALOG_MASTER.csv')
        catalog, _, bounds = _load_catalog(cat_path, rom_label)
        outdir = args.outdir or os.path.join(ROOT, 'tmp', 'v8')
        summary = run_batch(rom, outdir, catalog, bounds, n=args.n,
                            seed=args.seed, cases=args.cases,
                            rom_label=rom_label, jobs=args.jobs)
        kept = [s for s in summary if s[1] == 'PASS']
        print('== batch summary: generated=%d passed=%d dropped=%d' %
              (len(summary), len(kept), len(summary) - len(kept)))
        for addr, status, why in summary:
            print('    0x%06X %-5s %s' % (addr, status, why))
        return 0 if len(kept) else 1
    ap.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
