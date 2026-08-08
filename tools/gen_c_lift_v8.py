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
import csv
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

# Per-function MAXSTEPS override for the emitted test template (default
# 100000).  0x45E94's callee 0xD2F6 runs a 409,230-step deterministic loop
# per case: at 100k the mirror+sh2emu both hit the limit and the case is a
# silent SKIP, so that function needs 1M steps to get real PASS semantics
# (verified: both complete at 1M and agree).
MAXSTEPS_OVERRIDE = {0x45E94: 1000000}

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


def _find_nullsub(rom, start=0x200):
    """A clean callable nullsub for the call_runtime seed override.  sh2emu
    executes a call target from ITS bytes only; an address whose first word is
    `rts` (0x000B) + `nop` (0x0009) returns to pr immediately with no side
    effects, so ANY such pair is a functional no-op.  Returns the first one at
    an even offset >= start (skips the low vector area)."""
    for a in range(start, len(rom) - 4, 2):
        if rom[a] == 0x00 and rom[a + 1] == 0x0B \
                and rom[a + 2] == 0x00 and rom[a + 3] == 0x09:
            return a
    return None


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


def _rt_mem_mnem(op, sh):
    """A compact disassembly-style mnemonic for a rt-base (register-relative)
    mem op decoded via gcl._mem_shape.  c_lift_ops.decode_mem is bypassed for
    these (base unresolvable), so build a descriptive label."""
    sz = {1: 'b', 2: 'w', 4: 'l'}[sh['size']]
    b, i = sh['base'], sh['idx']
    btxt = ('@(r0,r%d)' % b) if i else ('@r%d' % b)
    if i:
        btxt = '@(r%d+r0)' % b
    if sh['auto'] == 'post':
        btxt = '@r%d+' % b
    elif sh['auto'] == 'pre':
        btxt = '@-r%d' % b
    if sh['dir'] == 'load':
        return 'mov.%s %s,r%d' % (sz, btxt, sh['dest'])
    return 'mov.%s r%d,%s' % (sz, sh['src'], btxt)


def _fpu_mem_rt(pc, op, f, temp):
    """Emit an fpu_mem record for a base register that decode_fpu left
    unresolved (runtime register, not r4..r7 param / not a foldable literal).
    Mirror _fpu_mem's param-base c/py exactly so the differential test stays
    bit-consistent with sh2emu (rdf @rN / wrf).  Returns a record dict."""
    breg = f['base_reg']
    idx = f.get('idx')
    auto = f.get('auto')
    dest = f.get('dest')
    src = f.get('src')
    if idx:
        caddr, pyaddr = '(r0 + r%d)' % breg, 'r[0] + r[%d]' % breg
    else:
        caddr, pyaddr = 'r%d' % breg, 'r[%d]' % breg
    if f['dir'] == 'load':
        if isinstance(dest, int):
            tgt = 'fr%d' % dest
            pyv = 'fr[%d] = bits2f(_rdw(ram, %s, 4))' % (dest, pyaddr)
        else:
            tgt = dest
            pyv = '%s = _rdw(ram, %s, 4)' % (dest, pyaddr)
        stmts = ['%s = *(volatile uint32_t*)%s;' % (tgt, caddr)]
        if auto == 'post':
            stmts.append('r%d = r%d + 4;' % (breg, breg))
            py = [pyv, 'r[%d] = (r[%d] + 4) & 0xFFFFFFFF' % (breg, breg)]
        else:
            py = [pyv]
    else:
        if isinstance(src, int):
            val_c = 'fr%d' % src
            val_py = 'f2bits(fr[%d])' % src
        else:
            val_c = src
            val_py = src
        stmts = []
        if auto == 'pre':
            # sh2emu decrements r[n] FIRST then stores at the new address.
            stmts.append('r%d -= 4;' % breg)
            stmts.append('*(volatile uint32_t*)r%d = %s;' % (breg, val_c))
            py = ['r[%d] = (r[%d] - 4) & 0xFFFFFFFF' % (breg, breg),
                  '_wrw(ram, r[%d], 4, %s)' % (breg, val_py)]
        else:
            stmts.append('*(volatile uint32_t*)%s = %s;' % (caddr, val_c))
            py = ['_wrw(ram, %s, 4, %s)' % (pyaddr, val_py)]
    return {'pc': pc, 'op': op, 'kind': 'fpu_mem', 'dir': f['dir'], 'size': 4,
            'base_reg': breg, 'idx': idx, 'auto': auto,
            'dest': dest, 'src': src, 'c': stmts, 'py': py,
            'uses': set(f.get('uses') or {}), 'mnem': '%s (rt-base)' % f.get('ann', 'op')}


def _v6_reclaim(rom, pc, data, addr, ops, gcl):
    prev = pc - 2
    if prev < addr:
        return False
    # prev is the DELAY SLOT of a walked call (pc-4 is a call op): the slot
    # executed as part of the call, so the candidate at pc is the call's
    # ret_pc fallthrough (e.g. 0x1CB26 after jsr at 0x1CB22 in 0x1AA1E).
    # Skip the prev-op checks entirely: neither the `prev in data` rejection
    # nor the translate/_mem_shape checks apply (the slot is part of the call
    # record, not a live back-edge into the lifted region).
    slot_of_call = (pc - 4 >= addr and
                    gcl.is_call_op((rom[pc - 4] << 8) | rom[pc - 3]))
    if prev in data and not slot_of_call:
        return False
    if not slot_of_call:
        _op = (rom[prev] << 8) | rom[prev + 1]
        _dd = ops.translate(_op, prev, rom)
        if _dd is None:
            # prev is a mem op (translate covers pure-int only): accept a
            # register-based load/store prev (e.g. reclaimed 0xB1C0 mov.w r14,@r1)
            _pms = gcl._mem_shape(_op)
            if _pms is None or _pms.get('dir') not in ('load', 'store'):
                return False
        elif _dd.get('kind') in ('branch', 'ret') or gcl.is_call_op(_op):
            return False
    opc = (rom[pc] << 8) | rom[pc + 1]
    if ops.translate(opc, pc, rom) is not None:
        return True
    if gcl.is_call_op(opc):                    # jsr/bsr/jmp (e.g. 0xB1A8 jsr @r13)
        return True
    ms = gcl._mem_shape(opc)
    if ms is not None and ms.get('dir') in ('load', 'store'):
        return True
    if opc >> 12 == 0xD or opc >> 12 == 0x9 or (opc & 0xFF00) == 0xC700:
        return True                            # PC-rel literal load (0xB1C2 mov.l @(disp,PC))
    # sts.l/stc.l/lds.l/ldc.l control-register memory forms (c_lift_ops.decode_mem
    # family: op & 0xF0FF in 0x4002/0x4012/0x4022 sts.l, 0x4006/0x4016/0x4026
    # lds.l, 0x4003/0x4013 stc.l SR/GBR, 0x4007/0x4017 ldc.l, any base-reg nibble).
    # A pool word that is one of these is CODE, not data — e.g. 0x4F26
    # `lds.l @r15+,pr` at 0x7A76: without reclaim the walker skips it (hole at the
    # branch target/ret_pc), the mirror RETs early and sp/r0 diverge.
    if (opc & 0xF0FF) in (0x4002, 0x4012, 0x4022, 0x4006, 0x4016, 0x4026,
                          0x4003, 0x4013, 0x4007, 0x4017):
        return True
    return False


def build_cfg(rom, addr, end, lifted=None, catalog=None, data_extra=None,
              allow_runtime_base=False, tail_bra_as_call=False):
    """Decode [addr, end) as basic blocks + edges; resolve all indirects.
    allow_runtime_base=True: a LOAD/STORE whose base register cannot be folded
    to a literal (or param-of-r4..r7) is emitted register-relative
    (rt-base: `r[R] = _rdw(ram, s->r[N], size)` / `_wrw`, mirror==sh2emu) instead
    of being rejected 'unmapped'.  Used ONLY by the caller/callee EMISSION path
    (emit_caller / _emit_callee_cfg); the selection scanners keep the default
    False so pool metrics / dryruns are unchanged.

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
          'litdefs': {},
          # ENH1: stack-slot literal tracking.  'stacks' maps slot_offset (r15
          # sp_off + disp at store time) -> literal value written by a
          # `mov.l Rn,@(disp,r15)` / `mov.l Rn,@-r15` whose Rn holds a literal.
          # A later `mov.l @(disp,r15),Rn` / `mov.l @r15+,Rn` of a tracked slot
          # restores that literal into Rn so the runtime stack reload feeds
          # subsequent resolve() (e.g. jsr/jmp @Rn dispatch tables).
          'stacks': {},
          # RAM/ROM-pointer indirect call slots.  'slotdefs' maps 'rN' -> the
          # ROM slot ADDRESS when rN's defining instruction was a plain
          # `mov.l @Rm,Rn` (size-4, no idx/disp) whose base Rm holds a ROM
          # literal (e.g. 0x4B10).  A later `jsr @rN` with NO literal target
          # then emits a 'call_runtime' record (the callback value is runtime-
          # selected; the mirror models it as a no-op — matches sh2emu with the
          # slot seeded to a nullsub) instead of rejecting 'jsr_unresolved'.
          # Cleared whenever rN is redefined by any other write.
          'slotdefs': {}}
    info = res.info
    labels = res.labels
    data = set(gcl._pcrel_pool_words(rom, addr, end))
    if data_extra:
        data |= set(data_extra)
    mova_lits = {}
    tbl_base = {}       # reg index -> table base literal (set by indexed load)
    rt_tbl = {}         # reg index -> (table base literal, index reg) for
                        # runtime-dispatch target INCLUSION (see below)
    # runtime-dispatch table bases (target INCLUSION): reg index -> (base
    # literal, index reg).  Set by an indexed `mov.l @(r0,rB),rN` whose r0
    # holds the ROM table literal (mova / mov.l @(disp,PC)) while rB is the
    # runtime index (e.g. 0x20EC mov.l @(r0,r6),r5 / jsr @r5 with mova
    # 0x210C,r0) — the orientation OPPOSITE of tbl_base (which needs the
    # base literal + runtime r0).  Cleared on any redefinition of rN (via
    # _clr_slot / _record_slot_deref) so a stale table is never used.

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

    # bug c: a literal base whose register is REDEFINED by a non-literal
    # instruction (add #imm,Rn / mov Rm,Rn / ...) inside a loop that
    # re-executes the mem op is not path-constant: after the first iteration
    # the base holds a different runtime value, so the folded constant is
    # stale (memset-style `mov.b Rn,@r5 / add #1,r5` loops bake the start
    # address and re-write the same slot forever).  Pre-scan the span once for
    # (a) loop bodies (backward static-branch intervals) and (b) non-literal
    # register writes, so a literal-base mem inside such a loop can be emitted
    # register-relative (dynbase) like a re-entry pc.
    loop_bodies = []        # (loop_head, loop_end) backward-branch intervals
    nonlit_writes = {}      # reg ('r5') -> set of pcs of non-literal writes
    for _lp in range(addr, bound, 2):
        if _lp in data:
            continue
        _lo = (rom[_lp] << 8) | rom[_lp + 1]
        _lb = ops.branch_info(_lo)
        if _lb is not None and _lb.get('target_disp') is not None \
                and _lb['kind'] not in ('rte', 'rts', 'bsrf', 'braf'):
            _lt = (_lp + 4 + _lb['target_disp'] * 2) & MASK
            if addr <= _lt < _lp:               # backward edge -> loop body
                loop_bodies.append((_lt, _lp + (4 if _lb['delayed'] else 2)))
        _ld = ops.translate(_lo, _lp, rom)
        if _ld is None or _ld.get('kind') in ('branch', 'ret'):
            continue
        # skip literal-pinning statements (mov #imm / mov.w/l @(disp,PC) /
        # mova): they fold a constant into the reg and are NOT the runtime
        # redefinition we track.
        if (_lo & 0xF000) in (0xE000, 0x9000, 0xD000) or (_lo & 0xFF00) == 0xC700:
            continue
        for _w in gcl._stmt_writes('\n'.join(_ld.get('c') or [])):
            nonlit_writes.setdefault(_w, set()).add(_lp)

    def _pin_lit(reg, val, pc):
        """Record a literal definition of `reg` at `pc` (path-sensitivity)."""
        st['lits']['r%d' % reg] = val
        st['litdefs'].setdefault('r%d' % reg, set()).add(pc)
        st['slotdefs'].pop('r%d' % reg, None)   # a literal def overrides a slot deref
        tbl_base.pop(reg, None)     # a literal def overrides a jump-table base
        rt_tbl.pop(reg, None)       # (belt-and-braces for direct pins)
        return val

    def _rom_deref_value(mr):
        """ENH2: for a `mov.l @Rm,Rn` deref (either `mov.l @Rn,Rn` same-reg or
        `mov.l @Rm,Rn` cross-reg) whose base Rm holds a ROM literal (address
        < 0x10000), return the big-endian 4-byte word at ROM[base] so the
        caller can pin dest = that table entry.  Returns None otherwise.
        Reads ONLY the pre-write literal (dest==base would otherwise be gone
        after _apply_mem_writes pops it).  Scoped to plain @Rn derefs used for
        indirect dispatch: no index, no disp, load, size 4.  The base register
        keeps its literal address (NOT the deref) when dest != base."""
        _base = st['lits'].get('r%d' % mr['base_reg'])
        if not (mr['dir'] == 'load' and mr.get('dest') is not None
                and mr.get('idx') is None and not mr.get('disp')
                and mr.get('size') == 4
                and _base is not None and _base < 0x10000
                and _base + 4 <= len(rom)):
            return None
        _out = int.from_bytes(rom[_base:_base + 4], 'big') & MASK
        if _out == 0 or ops.classify_addr(_out) != 'ROM':
            return None
        return _out

    def _record_slot_deref(mr):
        """For a plain `mov.l @Rm,Rn` (size-4 load, no idx/disp) whose base Rm
        holds a ROM address literal, record slotdefs[dest] = that slot address.
        Called after _apply_mem_writes so the dest write has already popped
        lits/written.  The callback VALUE is runtime-selected (ROM slot often
        0 / a RAM ptr), so the register gets no literal here — only the slot
        address is tracked for the 'call_runtime' jsr path.  For any OTHER
        load into a register the dest's slotdef is cleared (stale-mark guard).
        Note: mirror==sh2emu on the deref itself (both read the real slot word),
        so only the later `jsr @rN` semantics differ (mirror no-op vs nullsub)."""
        if mr['dir'] == 'load' and mr.get('dest') is not None:
            _dname = 'r%d' % mr['dest']
            if (mr.get('idx') is None and not mr.get('disp') and mr.get('size') == 4
                    and 'r%d' % mr['base_reg'] in st['lits']):
                _base = st['lits']['r%d' % mr['base_reg']]
                if _base is not None and _base < 0x10000 and _base + 4 <= len(rom) \
                        and ops.classify_addr(_base) == 'ROM':
                    st['slotdefs'][_dname] = _base
                    rt_tbl.pop(mr['dest'], None)
                    return
            st['slotdefs'].pop(_dname, None)
            rt_tbl.pop(mr['dest'], None)

    def _clr_slot(reg):
        """Clear the slot-deref marker when `reg` is redefined (non-slot write).
        Accepts an int register number or an 'rN' name."""
        if isinstance(reg, int):
            st['slotdefs'].pop('r%d' % reg, None)
            rt_tbl.pop(reg, None)
            tbl_base.pop(reg, None)
        elif isinstance(reg, str) and reg[0] == 'r' and reg[1:].isdigit():
            st['slotdefs'].pop(reg, None)
            rt_tbl.pop(int(reg[1:]), None)
            tbl_base.pop(int(reg[1:]), None)

    def _record_tbl_base(mr):
        """Dispatch-table base bookkeeping for an indexed load `mov.l @(r0,Rm),Rn`.
        Two orientations:
          - Rm holds the table literal, r0 is the runtime index (existing
            jump-table path, tbl_base);
          - r0 holds the ROM table literal (mova / mov.l @(disp,PC)) and Rm is
            the runtime index (e.g. 0x20EC mov.l @(r0,r6),r5 / jsr @r5 with
            mova 0x210C,r0; 0x207A mov.l @(r0,r3),r2 / jsr @r2) — recorded in
            rt_tbl so the runtime_dispatch target INCLUSION can enumerate the
            table and put the TARGETS' code in the caller's mirror CODE dict.
        Called from BOTH mem emission paths (decode_mem and the rt-base
        fallback, which decode_mem cannot resolve for non-param bases)."""
        if mr.get('idx') == 'r0' and mr['dir'] == 'load' and mr.get('dest') is not None:
            _r0l = st['lits'].get('r0')
            _bl = st['lits'].get('r%d' % mr['base_reg'])
            # NOTE: if BOTH the index register r0 and the base register Rm
            # hold literals, @(r0,Rm) is a fully-static indexed deref ->
            # single target ROM[bl + r0l], NOT a jump table; record no table
            # bookkeeping so the jsr falls through to the runtime-dispatch
            # path instead of jump_table_unresolved (fa7b748).
            if _r0l is not None and _bl is not None:
                return
            if _bl is not None:
                # Rm holds the table literal, r0 is the runtime index
                # (existing jump-table path).
                tbl_base[mr['dest']] = _bl
            elif _r0l is not None and _r0l + 4 <= len(rom) \
                    and ops.classify_addr(_r0l) == 'ROM':
                # r0 holds the ROM table literal, Rm is the runtime index ->
                # runtime_dispatch table (target INCLUSION).
                rt_tbl[mr['dest']] = (_r0l, mr['base_reg'])

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
                # r14 may be READ as a value, not just used as a frame *base* (e.g.
                # `mov r14,rN` copies the frame ptr into another reg).  Eliding the
                # assignment would leave r14 unset in the mirror (MISMATCH reg=rN
                # mirror=00000000).  Always emit r14 = r15 (=SP), which is correct
                # whenever 0x6EF3 executes.  Keeps frame_live/frame_off intact.
                return {'pc': pc, 'op': op, 'kind': 'frame',
                        'c': ['r14 = r15;'],
                        'py': ['r[14] = r[15]'],
                        'target': None, 'slot': None,
                        'mnem': 'mov r15,r14 (frame pointer)'}
            if 'r15' in writes:
                if op & 0xF000 == 0x7000 and ((op >> 8) & 0xF) == 15:
                    # `add #imm,r15` is a stack allocation, NOT a loss of the
                    # r15 stack model: keep stack_ok, shift sp_off by the
                    # signed immediate (every subsequent @r15/@(disp,r15) offset
                    # must move with the runtime pointer) and make the mirror's
                    # `sp` alias follow or the final r15 compare diverges from
                    # sh2emu (unbalanced prologue) — mirrors walk_v3.
                    _imm = op & 0xFF
                    if _imm & 0x80:
                        _imm -= 0x100
                    st['sp_off'] += _imm
                    d = dict(d)
                    d['py'] = list(d.get('py') or [])
                    d['py'].append('sp = (sp + s8(0x%02X)) & 0xFFFFFFFF'
                                   % (op & 0xFF))
                else:
                    st['stack_ok'] = False
            if 'r14' in writes:
                st['frame_live'] = False
            if not gcl._apply_stmt(rom, pc, op, d, st['written'], st['lits']):
                return None
            for _w in writes:
                _clr_slot(_w)
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
        if op & 0xF0FF in (0x4003, 0x4007, 0x4013, 0x4017):
            # stc.l SR (0x4003) / ldc.l SR (0x4007) / stc.l GBR (0x4013) /
            # ldc.l GBR (0x4017) via @-Rn / @Rn+.  Mirror sh2emu._exec
            # (0x4003/0x4007/0x4013/0x4017): SR and GBR are independent state
            # seeded in the mirror ('gbr' is seeded 0, like sr 0xF0), so a
            # running lift stays == sh2emu (which also seeds gbr=0) even though
            # nothing else in the body writes GBR.
            srn = (op >> 8) & 0xF
            _sr_store = (op & 0xF) == 0x3   # low nibble 3 = stc.l (@-), 7 = ldc.l (@+)
            _sr_reg = 'sr' if (op & 0xF0FF) in (0x4003, 0x4007) else 'gbr'
            if srn in (4, 5, 6, 7) and 'r%d' % srn not in st['written']:
                bkind, abs_addr = 'param', None
            elif 'r%d' % srn in st['lits']:
                bkind, abs_addr = 'literal', st['lits']['r%d' % srn]
            else:
                if not allow_runtime_base:
                    return None
                # rt-base: stack/indirect state transfer through an
                # unresolvable runtime register -> emit r-register-relative.
                bkind, abs_addr = 'param', None
            if bkind == 'literal':
                info['has_literal'] = True
                info['ram_addrs'].add(abs_addr)
            if _sr_store:
                if bkind == 'literal':
                    a = (abs_addr - 4) & MASK
                    eff = '0x%08X' % a
                    note = (' /* RAM 0x%08X */' % a
                            if ops.classify_addr(a) == 'RAM' else ' /* ROM */')
                else:
                    eff, note = '(r%d - 4)' % srn, ''
                c = ['*(volatile uint32_t*)%s = %s;%s' % (eff, _sr_reg, note),
                     'r%d = r%d - 4;' % (srn, srn)]
                if srn == 15 and bkind != 'literal':
                    # r15 push via stc.l: update the runtime `sp` alias too.
                    # The mirror re-syncs r[15] = sp at the top of every step,
                    # so an r[15]-only py would silently drop the push from
                    # stack accounting (MISMATCH on the next sp-relative op).
                    py = ['_wrw(ram, (sp - 4) & 0xFFFFFFFF, 4, %s)' % _sr_reg,
                          'sp = (sp - 4) & 0xFFFFFFFF']
                else:
                    py = ['_wrw(ram, (r[%d] - 4) & 0xFFFFFFFF, 4, %s)' % (srn, _sr_reg),
                          'r[%d] = (r[%d] - 4) & 0xFFFFFFFF' % (srn, srn)]
                mnem = 'stc.l %s,@-r%d' % (_sr_reg.upper(), srn)
            else:
                if bkind == 'literal':
                    eff = '0x%08X' % (abs_addr & MASK)
                    note = (' /* RAM 0x%08X */' % (abs_addr & MASK)
                            if ops.classify_addr(abs_addr) == 'RAM' else ' /* ROM */')
                else:
                    eff, note = 'r%d' % srn, ''
                t = temp()
                c = ['uint32_t %s = *(volatile uint32_t*)%s;%s' % (t, eff, note),
                     '%s = %s;' % (_sr_reg, t),
                     'r%d = r%d + 4;' % (srn, srn)]
                if srn == 15 and bkind != 'literal':
                    # r15 pop via ldc.l: mirror against the runtime `sp` alias
                    # (see the stc.l push above — r[15] only would drop the
                    # pop from stack accounting).
                    py = ['%s = _rdw(ram, sp, 4)' % _sr_reg,
                          'sp = (sp + 4) & 0xFFFFFFFF']
                else:
                    py = ['%s = _rdw(ram, r[%d], 4)' % (_sr_reg, srn),
                          'r[%d] = (r[%d] + 4) & 0xFFFFFFFF' % (srn, srn)]
                mnem = 'ldc.l @r%d+,%s' % (srn, _sr_reg.upper())
            st['written'].add('r%d' % srn)
            st['lits'].pop('r%d' % srn, None)
            _clr_slot(srn)
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
            _dyn = False    # runtime-r15 pop (no static stack-offset model)
            if srn == 15:
                if not st['stack_ok']:
                    if sys_store:
                        return None   # dynamic r15 PUSH: untrackable -> reject
                    # dynamic r15 POP: r15 holds a runtime address.  Mirror the
                    # pop against r[15] directly (== sh2emu's lds.l @r15+,X),
                    # with no sp_off accounting.  Used by dispatcher epilogues
                    # that restore r15 from a register then pop.
                    _dyn = True
            elif srn == 14:
                if not st['frame_live']:
                    return None
            else:
                return None
            st['written'].add('r%d' % srn)
            st['lits'].pop('r%d' % srn, None)
            _clr_slot(srn)
            if _dyn:
                c = ['%s = *(volatile uint32_t*)r15;' % sys_reg,
                     'r15 = r15 + 4;']
                py = ['%s = _rdw(ram, r[15], 4)' % sys_reg,
                      'r[15] = (r[15] + 4) & 0xFFFFFFFF']
                mnem = 'lds.l @r15+,%s' % sys_reg.upper()
                return {'pc': pc, 'op': op, 'kind': 'sys_stack', 'c': c,
                        'py': py, 'target': None, 'slot': None, 'mnem': mnem}
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
                if not allow_runtime_base:
                    return None
                # rt-base: @(r0,Rn) with an unknown (runtime) r0 index — emit
                # the (base + r0) register-relative; mirror==sh2emu on r0.
            if base_reg in (4, 5, 6, 7) and 'r%d' % base_reg not in st['written']:
                bkind, abs_addr = 'param', None
            elif 'r%d' % base_reg in st['lits']:
                bkind, abs_addr = 'literal', st['lits']['r%d' % base_reg]
            else:
                if not allow_runtime_base:
                    return None
                # rt-base: base register holds a runtime (unfolded/pool- or
                # param-derived) pointer — emit register-relative.
                bkind, abs_addr = 'param', None
            if bkind == 'literal':
                info['has_literal'] = True
                info['ram_addrs'].add(abs_addr)
            # bug b: don't bake a literal base that is not path-constant.
            # (1) mem at a branch-target pc (re-entry) can be reached with the
            # base register already modified on another path; (2) a base with
            # >=2 distinct literal def-sites (e.g. a jsr delay-slot write on a
            # sibling path) leaks the wrong constant here.  (3, bug c) a base
            # whose literal def-site is followed by a NON-literal write inside
            # a loop body that re-executes this mem (memset-style counter) —
            # the folded constant is stale after the first iteration.  Emit
            # the runtime register (dynbase) in all three cases.
            _dyn = ((pc in reentry)
                    or len(st['litdefs'].get('r%d' % base_reg, ())) > 1)
            if not _dyn:
                _bname = 'r%d' % base_reg
                _pins = st['litdefs'].get(_bname, ())
                if len(_pins) == 1 and _bname in nonlit_writes:
                    _bp = min(_pins)
                    for _lhs, _lend in loop_bodies:
                        if _lhs <= pc <= _lend and \
                                any(_bp < _pw <= _lend
                                    for _pw in nonlit_writes[_bname]):
                            _dyn = True
                            break
            c, py = gcl._mem_record(pc, op, m, bkind, abs_addr, temp,
                                    dynbase=_dyn)
            _rompin = _rom_deref_value(m)
            gcl._apply_mem_writes(m, st['written'], st['lits'])
            _record_slot_deref(m)
            if _rompin is not None:
                _pin_lit(m['dest'], _rompin, pc)
            # dispatch-table base bookkeeping (see _record_tbl_base)
            _record_tbl_base(m)
            return {'pc': pc, 'op': op, 'kind': 'mem', 'c': c, 'py': py,
                    'target': None, 'slot': None, 'mnem': m['ann']}
        # ---- rt-base fallback: mem op whose base register decode_mem could not
        # resolve (not r4..r7 param, no foldable literal).  When the emission
        # path allows it, emit register-relative instead of rejecting: the
        # mirror reads/writes whatever runtime RAM register `rN` points at and
        # sh2emu does the same from the seed — differential-consistent.  Same
        # limits as walk_v3's relax_chain (simple single-op forms only): the
        # live r15/r14 stack-slot forms keep their dedicated path below, and
        # @-Rn/@Rn+ auto-forms keep their register updates via _mem_record.
        if m is None and allow_runtime_base:
            sh = gcl._mem_shape(op)
            if sh is not None:
                _breg = sh['base']
                if sh.get('idx') is None and (
                        (_breg == 15 and st['stack_ok']) or
                        (_breg == 14 and st['frame_live'])):
                    pass          # live stack/frame slot — handled below
                else:
                    m2 = {'dir': sh['dir'], 'size': sh['size'],
                          'base_reg': _breg, 'dest': sh.get('dest'),
                          'src': sh.get('src'), 'disp': sh.get('disp') or 0,
                          'idx': sh.get('idx'), 'auto': sh.get('auto'),
                          'sext': sh['dir'] == 'load' and sh['size'] < 4}
                    c, py = gcl._mem_record(pc, op, m2, 'param', None, temp)
                    _rompin = _rom_deref_value(m2)
                    gcl._apply_mem_writes(m2, st['written'], st['lits'])
                    _record_slot_deref(m2)
                    if _rompin is not None:
                        _pin_lit(m2['dest'], _rompin, pc)
                    # dispatch-table base bookkeeping (see _record_tbl_base)
                    _record_tbl_base(m2)
                    return {'pc': pc, 'op': op, 'kind': 'mem', 'c': c, 'py': py,
                            'target': None, 'slot': None,
                            'mnem': '%s (rt-base)' % _rt_mem_mnem(op, sh)}
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
            if gdir == 'load':
                _clr_slot(0)
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
        if (op & 0xF0FF) == 0x60F6:                # 0x6nF6 == mov.l @r15+,Rn
            # Epilogue stack pop into ANY dest register n (0..14), e.g.
            # 0x64F6 (mov.l @r15+,r4) and 0x6EF6 (mov.l @r15+,r14).  The
            # generic r15/r14 mem-shape block below already covers these
            # encodings via _mem_shape (base 15, nib 6); this explicit branch
            # documents the family and guarantees the pop decodes for every n
            # without depending on the generic base-resolution rules.  Same
            # stack-slot model as _mem_shape / _stack_record: auto='post', so
            # off = sp_off BEFORE the pop.
            _dn = (op >> 8) & 0xF
            if not st['stack_ok'] or _dn == 15:
                return None
            off = st['sp_off']
            st['sp_off'] += 4
            info['has_stack'] = True
            info['stack_offs'].add(off)
            c = ['r%d = local_%x;' % (_dn, off)]
            py = ['r[%d] = _rdw(ram, STACK_BASE + 0x%X, 4)' % (_dn, off),
                  'sp = (sp + 4) & 0xFFFFFFFF']
            st['written'].add('r%d' % _dn)
            st['lits'].pop('r%d' % _dn, None)
            _clr_slot(_dn)
            st['written'].add('r15')
            st['lits'].pop('r15', None)
            _clr_slot(15)
            return {'pc': pc, 'op': op, 'kind': 'stack', 'c': c, 'py': py,
                    'target': None, 'slot': None,
                    'mnem': 'mov.l @r15+,r%d' % _dn}
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
            # ENH1: track/restore stack-slot literals for r15 slots (sp_off +
            # disp addressing).  A store of a literal-holding Rn into an r15
            # slot records stacks[slot]=value; a subsequent load of a tracked
            # slot restores Rn's literal (AFTER _apply_mem_writes pops the
            # ordinary dest-write).  Untracked slots behave as before.
            if breg == 15 and sh['dir'] == 'store' and sh['size'] == 4:
                _src = sh.get('src')
                if _src is not None and 'r%d' % _src in st['lits']:
                    st['stacks'][off] = st['lits']['r%d' % _src]
                else:
                    st['stacks'].pop(off, None)
            gcl._apply_mem_writes(sm, st['written'], st['lits'])
            if breg == 15 and sh['dir'] == 'load' and sh.get('dest') is not None:
                _clr_slot(sh['dest'])
                if off in st['stacks']:
                    _pin_lit(sh['dest'], st['stacks'][off], pc)
            return {'pc': pc, 'op': op, 'kind': 'stack', 'c': c, 'py': py,
                    'target': None, 'slot': None, 'mnem': gcl._stack_mnem(sh)}
        f = ops.decode_fpu(op, pc, rom, ctx)
        if f is not None:
            if f.get('kind') == 'fpu_mem':
                if f.get('unresolved'):
                    if not allow_runtime_base:
                        return None
                    return _fpu_mem_rt(pc, op, f, temp)
                base_reg = f['base_reg']
                if f.get('idx') == 'r0' and 'r0' not in st['lits']:
                    if not allow_runtime_base:
                        return None
                    # rt-base: @(R0,Rn) fmov.s with an unknown runtime r0 index.
                    return _fpu_mem_rt(pc, op, f, temp)
                if f['base'] == 'literal':
                    info['has_literal'] = True
                    v = st['lits'].get('r%d' % base_reg)
                    if v is not None and ops.classify_addr(v) == 'RAM':
                        info['ram_addrs'].add(v)
                if f.get('auto') in ('post', 'pre'):
                    reg = 'r%d' % base_reg
                    st['written'].add(reg)
                    st['lits'].pop(reg, None)
                    _clr_slot(base_reg)
                return {'pc': pc, 'op': op, 'kind': 'fpu_mem',
                        'c': list(f.get('c') or []),
                        'py': list(f.get('py') or []),
                        'target': None, 'slot': None,
                        'mnem': f.get('ann') or ('op 0x%04X' % op)}
            for reg in gcl._stmt_writes('\n'.join(f.get('c') or [])):
                st['written'].add(reg)
                st['lits'].pop(reg, None)
                _clr_slot(int(reg[1:]) if reg[0] == 'r' else reg)
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

    def enum_rt_entries(base):
        """Enumerate a runtime-dispatch table at `base` (4-byte big-endian
        words) while each word is a plausible ROM code address (classify_addr
        'ROM', < 0x100000, even).  Looser than enum_table: the targets need NOT
        be in-span/lifted/catalog — they are walked as callees (target
        INCLUSION) so the mirror can execute them after the runtime dispatch.
        Returns the entry list (may be empty = not a dispatch table)."""
        entries = []
        a = base
        while a + 4 <= len(rom) and len(entries) < 1024:
            v = int.from_bytes(rom[a:a + 4], 'big')
            if v == 0 or v == 0xFFFFFFFF or v % 2 != 0 \
                    or ops.classify_addr(v) != 'ROM' or v >= 0x100000:
                break
            entries.append(v)
            a += 4
        return entries

    pending = [addr]
    visited = set()
    seen_pc = set()        # every pc already consumed (record emitted / slot /
                           # data) — dedups blocks reached by fall-through AND
                           # by a branch target, and skips consumed delay slots.
    # Path-sensitive literal/state isolation (walker-artifact fix).  pending is a
    # LIFO walk: the SAME st['lits'] / st['written'] get mutated by every block,
    # so an epilogue block popped first can `mov.l @r15+,Rn` (0x6Fn6) and pop a
    # literal def out of a register before the block that LATER does `jsr @Rn`
    # (e.g. callee 0x361AC: r14=0x385C4 set at 0x361B4, single def, never
    # overwritten on the real path, yet the jsr at 0x36354 saw r14 gone when the
    # epilogue was walked first).  Snapshot lits/written at each pending-push
    # and restore on pop so each block walks from the state at its branch point.
    pending_state = {}     # block pc -> (lits-dict, written-set) snapshot
    def _snapshot_st():
        return (dict(st['lits']), set(st['written']), dict(st['slotdefs']))
    def _push_with_state(target):
        pending.append(target)
        pending_state[target] = _snapshot_st()
    while pending:
        bs = pending.pop()
        if bs in pending_state:
            st['lits'], st['written'], st['slotdefs'] = pending_state[bs]
        if bs in visited or bs in seen_pc:
            continue
        visited.add(bs)
        pc = bs
        # Per-column flag: this LINEAR walk passed the function's first rts.
        # After a return the fall-through continuation runs into the literal
        # pool / unreferenced data words that the pcrel-pool set does not mark
        # (e.g. FUN_00036b84: rts@0x36BE8 + slot 0x36BEA, then data word
        # 0x36BEC) — emit_one returns None for them and a hard reject would
        # kill a valid function.  Per-column (reset per block), NOT per-call:
        # a branch target that lands on a data word later gets the same
        # unmapped logic with seen_rts False (its own column) -> real
        # corruption still rejects.
        seen_rts = False
        while pc + 1 < bound:
            if pc in seen_pc:            # already walked via another path
                break
            if pc in data:
                if _v6_reclaim(rom, pc, data, addr, ops, gcl):
                    data.discard(pc)
                else:
                    pc += 2
                    continue
            op = (rom[pc] << 8) | rom[pc + 1]
            d = ops.translate(op, pc, rom)
            if (d is not None and d.get('kind') in ('branch', 'ret')) or op == 0x002B:
                bi = ops.branch_info(op)
                kind = bi['kind'] if bi is not None else None
                if kind is None:
                    res.reject = ('rte', pc)
                    return res
                if kind == 'rte':
                    # rte (return-from-exception): pops PC/SR from the stack and
                    # jumps to an arbitrary runtime address, so sh2emu escapes the
                    # tested span (runaway -> StepLimitExceeded -> case skipped).
                    # Model it as a terminal return in the mirror (falls out to
                    # RET), which matches upgraded-to-rts for a clean span end.
                    kind = 'rts'
                target = None
                if kind == 'rts':
                    seen_rts = True
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
                        _push_with_state(target)
                    elif tail_bra_as_call and (kind == 'bra' or kind in ('bt', 'bts', 'bf', 'bfs')):
                        # out-of-span static branch => tail call to a sibling.
                        # bra (unconditional) exits; bt/bf/bt.s/bf.s are CONDITIONAL
                        # tail calls: `if (T/!T) { f_%X(s); return; }` with fallthrough
                        # continuing when the branch is not taken.
                        cond = v3.BRANCH_C[kind].split(' goto ')[0]   # 'if (T)' / 'if (!T)'
                        rec = {'pc': pc, 'op': op, 'kind': 'call',
                               'mnem': '%s (tail)' % (v3.BRANCH_MNEM[kind] % target),
                               'c': ([v7.to_st_c(s) for s in slot['c']] if slot else [])
                                    + ['%s { f_%X(s); return; }' % (cond, target)],
                               'slot': slot, 'target': target,
                               'ret_pc': (pc + 4) & MASK, 'set_pr': False,
                               'cond': _BRANCH_COND.get(kind)}
                        res.records.append(rec)
                        seen_pc.add(pc)
                        if slot is not None:
                            seen_pc.add(pc + 2)
                        if kind == 'bra':
                            break
                        pc += 4 if slot is not None else 2
                        continue
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
                if kind == 'bra':
                    # unconditional branch: no fallthrough edge — stop walking
                    # this linear column (the target is reached via pending).
                    break
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
                        _push_with_state(tgt)
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
                            _push_with_state(e)
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
                    # RAM-pointer indirect call: rN was deref'd from a ROM slot
                    # address literal (`mov.l @Rm,Rn`, e.g. rN = [0x4B10]).  The
                    # callback VALUE is runtime-selected and unknown statically;
                    # model it as a call_runtime no-op (mirror == sh2emu when the
                    # test seeds the slot with a nullsub address).  Only this
                    # ROM-slot jsr family is admitted — other truly-runtime
                    # jsr (indexed-table dispatch) stays 'jsr_unresolved'.
                    if kind == 'jsr' and ('r%d' % rn) in st['slotdefs']:
                        _slot_addr = st['slotdefs']['r%d' % rn]
                        slot = slot_record(pc + 2) if pc + 2 < end else None
                        # same pr_loop guard as the literal jsr below (0x4F26 slot
                        # after the jsr clobbers pr -> diverges).
                        if slot is not None and pc + 3 < bound and \
                                (rom[pc + 2] << 8) | rom[pc + 3] == 0x4F26:
                            res.reject = ('pr_loop', pc)
                            return res
                        res.edges.append((pc, 'jsr@romslot', None))
                        rec = {'pc': pc, 'op': op, 'kind': 'call_runtime',
                               'mnem': 'jsr @r%d (ROM slot 0x%X)' % (rn, _slot_addr),
                               'c': (['s->pr = 0x%08X;' % ((pc + 4) & MASK)]
                                     + ([v7.to_st_c(s) for s in slot['c']] if slot else [])
                                     + ['((void(*)(ST*))s->r[%d])(s);' % rn]),
                               'slot': slot, 'target': None,
                               'ret_pc': (pc + 4) & MASK, 'set_pr': True,
                               'slot_addr': _slot_addr, 'reg': rn}
                        res.records.append(rec)
                        seen_pc.add(pc)
                        if slot is not None:
                            seen_pc.add(pc + 2)
                        pc += 4 if slot is not None else 2
                        continue
                    # General runtime dispatch: jmp/jsr @rN with no static
                    # literal (and not a ROM-slot call_runtime).  rN holds a
                    # runtime-computed target (e.g. an indexed dispatch table).
                    # The mirror dispatches to the target if it was lifted into
                    # CODE (in-span), else jsr->nullsub-return (ret_pc) / jmp->RET.
                    # Previously this rejected jsr_unresolved/indirect_unresolved;
                    # now it yields a runtime_dispatch record.
                    slot = slot_record(pc + 2) if pc + 2 < end else None
                    _is_jsr = (kind == 'jsr')
                    if _is_jsr and slot is not None and pc + 3 < bound and \
                            (rom[pc + 2] << 8) | rom[pc + 3] == 0x4F26:
                        res.reject = ('pr_loop', pc)
                        return res
                    res.edges.append((pc, 'rt-dispatch', None))
                    # target INCLUSION: rN was loaded from a ROM dispatch table
                    # (rt_tbl bookkeeping on `mov.l @(r0,rB),rN` with r0 = table
                    # literal) — enumerate the table targets so the caller's
                    # mirror CODE can carry their code (walked as callees).
                    # Without this the mirror nullsub-falls-through while sh2emu
                    # executes the real target (MISMATCH); with it the mirror
                    # dispatches to the target address like sh2emu.
                    _rt = rt_tbl.get(rn)
                    _rt_entries = enum_rt_entries(_rt[0]) if _rt is not None else []
                    rec = {'pc': pc, 'op': op, 'kind': 'runtime_dispatch',
                           'mnem': '%s @r%d (runtime)' % ('jsr' if _is_jsr else 'jmp', rn),
                           'reg': rn, 'is_call': _is_jsr,
                           'ret_pc': (pc + 4) & MASK,
                           'c': ([v7.to_st_c(s) for s in slot['c']] if slot else [])
                                + (['s->pr = 0x%08X;' % ((pc + 4) & MASK)] if _is_jsr else [])
                                + ['((void(*)(ST*))s->r[%d])(s);' % rn]
                                + (['return;'] if not _is_jsr else []),
                           'slot': slot, 'target': None,
                           'rt_entries': _rt_entries or None}
                    res.records.append(rec)
                    seen_pc.add(pc)
                    if slot is not None:
                        seen_pc.add(pc + 2)
                    pc += 4 if slot is not None else 2
                    continue
                tgt = v & MASK
                res.edges.append((pc, kind, tgt))
                if addr <= tgt < end:
                    labels.add(tgt)
                    _push_with_state(tgt)
                slot = slot_record(pc + 2) if pc + 2 < end else None
                # PR LOOP GUARD: a `lds.l @r15+,pr` delay slot (0x4F26) after a
                # `jsr` leaves pr = stack-popped value, which the inlined callee's
                # `rts` then consumes while sh2emu's real call/return runs the
                # callee's own frame — the two pr values diverge (known case:
                # 0x298F4).  The guard deliberately does NOT apply to the tail
                # `jmp` (set_pr=False) epilogue: there the 0x4F26 slot is this
                # function's own prologue-pop (`sts.l pr,@-r15` balance) and the
                # mirror and sh2emu pop the SAME RAM slot, so the callee's rts
                # resolves identically on both sides (0x25C40 / 0x292BA).
                if kind == 'jsr' and slot is not None and pc + 3 < bound and \
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
                if kind == 'jsr':
                    pc += 4 if slot is not None else 2
                    continue
                # tail jmp @Rn: no fallthrough -- stop the linear walk so it
                # does not over-run into the literal pool (0x3D58 case).
                break
            rec = emit_one(pc, op)
            if rec is None:
                if seen_rts:
                    # Post-return linear continuation ran into a non-decodable
                    # word (unreferenced literal-pool / data word the pcrel set
                    # misses, e.g. 0x36BEC).  Treat it as data: skip and keep
                    # walking — the function already returned.
                    pc += 2
                    continue
                res.reject = ('unmapped', pc)
                return res
            if op & 0xFF00 == 0xC700:                  # mova
                mova_lits['r0'] = ops.mova_target(pc, op & 0xFF)
            res.records.append(rec)
            seen_pc.add(pc)
            pc += 2
    # ---- span/fallthrough guard (bug d) -----------------------------------
    # A catalog span cut mid-epilogue leaves `lds.l @r15+,pr` (0x4F26) as its
    # final in-span instruction with no `rts` following: sh2emu (no span bound)
    # falls through into the next function and clobbers r0 while the mirror
    # stops at the span end (MISMATCH, e.g. 0x02C2A8).  Reject when the last
    # in-span word is 0x4F26 and the word right after the span is NOT an `rts`
    # (an immediately-following rts is a clean epilogue cut, so those are kept
    # and the mirror/emu agree on the return path).
    for _r_ in res.records:
        if _r_.get('pc') is not None and _r_.get('op') == 0x4F26 \
                and _r_['pc'] + 2 == bound:
            _nxt = (rom[bound] << 8) | rom[bound + 1] \
                if bound + 1 < len(rom) else None
            if _nxt != 0x000B:
                res.reject = ('span_no_return', _r_['pc'])
            return res
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


def _load_categories_bank(csv_path, bank):
    """FUNCTION_CATEGORIES.csv rows for ONE bank only.

    gcl.load_categories returns every bank's rows (bank column dropped), so
    scanning e.g. 60E0FC00 used to evaluate the 2789 60E1D400 rows against the
    FC00 catalog + FC00 next-addr bounds (cross-bank contamination: 6082
    candidates scanned, D400 rows like 0x02C2A8 getting FC00 estimated ends).
    The scan/CLI must only see the selected bank's candidates."""
    rows = []
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            # the CSV's first header carries a UTF-8 BOM (\ufeffbank)
            if '\ufeffbank' in row and 'bank' not in row:
                row['bank'] = row.pop('\ufeffbank')
            if (row.get('bank') or '').strip() != bank:
                continue
            try:
                addr = int(row['addr'].strip(), 16)
            except (ValueError, TypeError):
                continue
            rows.append({'addr': addr,
                         'name': (row.get('name') or '').strip(),
                         'category': (row.get('category') or '').strip()})
    return rows


def run_metrics(rom_path=DEFAULT_ROM, bank='60E1D400', verbose=True):
    rom = open(rom_path, 'rb').read()
    cat_path = os.path.join(ROOT, 'symbols', 'CATALOG_MASTER.csv')
    catalog, no_spans, bounds = _load_catalog(cat_path, bank)
    categories = _load_categories_bank(
        os.path.join(ROOT, 'symbols', 'FUNCTION_CATEGORIES.csv'), bank)
    cands = v3._merge_nospan_cands(categories, no_spans, bounds, bank)
    lifted = _load_lifted()
    names = _bank_names(bank)
    drop_set = _fragment_drop_addrs(rom, catalog, bounds, names)

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
        if addr in drop_set:
            continue
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


def run_dryrun(rom_path, bank, seed=42):
    """--dryrun: bank-clean v8 scan, no files written.

    Fixes (B): the candidate universe is the SELECTED bank only (the global
    FUNCTION_CATEGORIES.csv would evaluate e.g. the 2789 60E1D400 rows against
    the 60E0FC00 catalog + FC00 next-addr bounds), and an end=0xFFFFFFFF
    sentinel row is treated as no-end (consistent with load_catalog_nospans and
    the catalog loader: 60E0FC00 has 129 no-end rows, 1 of which is the
    0xFFFFFFFF sentinel)."""
    rom = open(rom_path, 'rb').read()
    cat_path = os.path.join(ROOT, 'symbols', 'CATALOG_MASTER.csv')
    catalog, no_spans, bounds = _load_catalog(cat_path, bank)
    categories = _load_categories_bank(
        os.path.join(ROOT, 'symbols', 'FUNCTION_CATEGORIES.csv'), bank)
    cands = v3._merge_nospan_cands(categories, no_spans, bounds, bank)
    sent = 0
    with open(cat_path) as f:
        for row in csv.DictReader(f):
            if (row.get('bank') or '').strip() != bank:
                continue
            if (row.get('addr') or '').strip().upper() == '0XFFFFFFFF':
                continue
            if (row.get('end') or '').strip().upper() == '0XFFFFFFFF':
                sent += 1
    lifted = _load_lifted()
    names = _bank_names(bank)
    drop_set = _fragment_drop_addrs(rom, catalog, bounds, names)
    pool, no_span_est = 0, 0
    reasons = Counter()
    for c in cands:
        addr = c['addr']
        if addr in drop_set:
            continue
        if glob.glob(os.path.join(ROOT, 'c', '*_%x.c' % addr)):
            continue
        if addr in lifted:
            continue
        end = catalog.get(addr)
        if end is None:
            end = v3._next_addr(addr, bounds)
            no_span_est += 1
        if end is None:
            continue
        _a, end_s, _r = v3.sanitize_span(addr, end, rom)
        if not (SIZE_MIN <= end_s - addr <= SIZE_MAX):
            continue
        ok, reason, res = scan_v8(rom, c, end_s, lifted, catalog)
        if not ok:
            if isinstance(reason, tuple):
                reasons[reason[0]] += 1
            else:
                reasons[reason] += 1
            continue
        pool += 1
    print('== v8 dryrun (bank %s, seed %d) ==' % (bank, seed))
    no_span_bank = [n for n in no_spans if n['bank'] == bank]
    print('candidates scanned            : %d' % len(cands))
    print('  no-span rows (end=None)     : %d' % len(no_span_bank))
    print('    of which end=0xFFFFFFFF sentinel (treated as no-end): %d' % sent)
    print('  no-span -> estimated end     : %d' % no_span_est)
    print('pool_v8 admitted              : %d' % pool)
    print('rejections (top):')
    for k, v in reasons.most_common(12):
        print('    %-28s %d' % (k, v))
    return pool, len(no_spans)


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
    # caller-span fix (truncated-span MISMATCH class, e.g. 0x54B04): the
    # catalog end (here an estimate) + sanitize_span can cut the caller
    # mid-epilogue — last record `lds.l @r15+,pr` with the real rts (and its
    # delay slot) just outside the span -> r15 off-by-4 in the mirror.  Pull
    # the rts (and delay slot) into the span when none is in-span: first the
    # rts sitting exactly at end_s, then the bounded rts-scan fallback.
    if _callee_first_rts(rom, addr, end_s) is None:
        if end_s + 1 < len(rom) and \
                (rom[end_s] << 8) | rom[end_s + 1] == 0x000B:
            end_s = min(end_s + 4, len(rom))
        else:
            _ext = _callee_extend_to_rts(rom, addr, end_s, bounds)
            if _ext is not None:
                end_s = _ext
    lifted = _load_lifted()
    res = build_cfg(rom, addr, end_s, lifted, catalog, allow_runtime_base=True, tail_bra_as_call=True)
    if res.reject is not None:
        return None, None, False, res.reject
    if not res.records:
        return None, None, False, 'no_records'
    fn = 'caller_%X' % addr
    # callees referenced by call records (bsr/jsr/jmp-tail) must exist in lib:
    # generate any missing DRAFT f_<hex>.c instead of hard-failing — same
    # ensure step run_batch performs before calling emit_caller.
    callees = sorted({r['target'] for r in res.records if r['kind'] == 'call'
                      and r.get('target') is not None})
    for t in callees:
        lib_p, err = _ensure_callee_lib(t, rom, catalog, bounds,
                                        rom_label=rom_label)
        if err is not None:
            return None, None, False, ('callee-lib', t, err)

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
    # runtime-dispatch table targets (target INCLUSION): every entry enumerated
    # from a ROM dispatch table must have its code in the caller's mirror CODE
    # dict, so collect them from the runtime_dispatch records (callees are
    # walked by _emit_v8_test; rt entries are walked with per-entry tolerance).
    rt_entries = sorted({e for r in res.records for e in (r.get('rt_entries') or [])})
    ok, reason = _emit_v8_test(addr, rom, end_s, res, callees, out_t,
                               seed=seed, cases=cases, rom_label=rom_label,
                               catalog=catalog, bounds=bounds,
                               rt_entries=rt_entries)
    return out_c, out_t, ok, reason


def _callee_span_end(t, catalog, bounds):
    """Walk bound for a callee: its catalog end, else the next-catalog-address
    estimate (same rule as v3 selection).  Replaces the fixed t+32 window."""
    end_c = catalog.get(t)
    if end_c is None and bounds is not None:
        end_c = v3._next_addr(t, bounds)
    return end_c


_GHIDRA_SPANS = None


def _load_ghidra_spans():
    """Lazily load symbols/symbols_60E0FC00.csv (addr -> end) once.  The
    ghidra spans are the reference disassembly's function bounds: a callee's
    CATALOG_MASTER end is frequently truncated mid-body while the ghidra span
    covers the full function (e.g. 0x5F1C: catalog end 0x5F36 vs ghidra
    0x6010, real rts@0x5FF2)."""
    global _GHIDRA_SPANS
    _GHIDRA_SPANS = {}
    p = os.path.join(ROOT, 'symbols', 'symbols_60E0FC00.csv')
    if not os.path.exists(p):
        return
    with open(p) as f:
        for row in csv.DictReader(f):
            try:
                a = int(row['addr'].strip(), 16)
                e = int((row['end'] or '').strip(), 16)
            except (ValueError, TypeError):
                continue
            _GHIDRA_SPANS[a] = e


def _ghidra_span_end(t):
    """Ghidra span end for address `t` (symbols_60E0FC00.csv) or None."""
    if _GHIDRA_SPANS is None:
        _load_ghidra_spans()
    return _GHIDRA_SPANS.get(t)


def _fragment_spans(rom, catalog, bounds):
    """Effective span end per catalog row:
      1. end = catalog end; else ghidra span end (symbols_60E0FC00.csv);
         else next-addr estimate (v3 rule).
      2. sanitize_span(a, end, rom) and use end_s VERBATIM — NO rts+2
         pull-in, NO forward rts-scan.  Those rts-extensions walked a
         mislabeled DATA table (e.g. parent 0x26F4 interpolate_charTable) as
         code and stretched spans past real functions.  Fragments are now
         identified by the curated NAME (rule 2), so spans stay honest.
    Returns {addr: end} for rows with end > start."""
    spans = {}
    for a in catalog:
        end = catalog.get(a)
        if end is None:
            end = _ghidra_span_end(a)
        if end is None:
            end = v3._next_addr(a, bounds)
        if end is None:
            continue
        _a, end, _r = v3.sanitize_span(a, end, rom)
        if end > a:
            spans[a] = end
    return spans


_FRAG_NAMES = None


def _load_fragment_names():
    """CATALOG_MASTER.csv -> {bank: {addr: {'end': end_or_None,
    'src': src_name, 'lift': lift_name}}}, cached module-level.  Mirrors
    v3.load_catalog_nospans filtering (NOISE rows and the 0xFFFFFFFF addr
    sentinel excluded; end 0xFFFFFFFF treated as None) so the bank can be
    resolved exactly from a bare catalog dict via (addr, end) pair match."""
    global _FRAG_NAMES
    if _FRAG_NAMES is not None:
        return _FRAG_NAMES
    _FRAG_NAMES = {}
    p = os.path.join(ROOT, 'symbols', 'CATALOG_MASTER.csv')
    with open(p) as f:
        for row in csv.DictReader(f):
            if (row.get('flag') or '').strip() == 'NOISE':
                continue
            try:
                addr = int(row['addr'].strip(), 16)
            except (ValueError, TypeError):
                continue
            if addr == 0xFFFFFFFF:
                continue
            bank = (row.get('bank') or '').strip()
            try:
                end = int((row.get('end') or '').strip(), 16)
            except (ValueError, TypeError):
                end = None
            if end == 0xFFFFFFFF:
                end = None
            _FRAG_NAMES.setdefault(bank, {})[addr] = {
                'end': end,
                'src': (row.get('src_name') or '').strip(),
                'lift': (row.get('lift_name') or '').strip(),
            }
    return _FRAG_NAMES


def _bank_names(bank):
    """{addr: (src_name, lift_name)} for the CATALOG_MASTER rows of `bank`
    ('frag' is matched case-insensitively against both names)."""
    return {a: (d['src'], d['lift'])
            for a, d in _load_fragment_names().get(bank, {}).items()}


def _fragment_names_for_catalog(catalog):
    """Bank {addr: (src_name, lift_name)} resolved from a bare catalog dict
    (no bank label available): exact (addr, end) pair match against the loaded
    banks, then a key-subset fallback."""
    loaded = _load_fragment_names()
    pairs = set(catalog.items())
    for rows in loaded.values():
        if pairs == set((a, d['end']) for a, d in rows.items()):
            return {a: (d['src'], d['lift']) for a, d in rows.items()}
    ks = set(catalog)
    for rows in loaded.values():
        if ks and ks <= set(rows):
            return {a: (d['src'], d['lift']) for a, d in rows.items()}
    return {}


def _fragment_drop_addrs(rom, catalog, bounds, names=None):
    """Catalog rows that are TRUE fragments, judged by NAME only: X is dropped
    iff (a) X's name (src_name or lift_name, case-insensitive) contains 'frag'
    — the curated name is authoritative evidence — AND (b) X.start is strictly
    inside ANOTHER row's effective span (o < X.start < oe).

    The earlier walker-based rule was wrong: it built the parent's CFG and
    dropped whatever the walker covered, but parent 0x26F4 (interpolate_
    charTable) is a mislabeled DATA table the walker walks as CODE, so real
    functions (e.g. 0x2710 ISR_100) sitting inside its span were dropped too.
    'frag' in the curated catalog name never misfires.

    `names` is the bank's {addr: (src_name, lift_name)} map, loaded once at the
    call sites; when it can't be passed (bare 3-arg call) the CSV is loaded
    itself (module-level cache).  Returns a set of dropped addresses."""
    if names is None:
        names = _fragment_names_for_catalog(catalog)
    spans = _fragment_spans(rom, catalog, bounds)
    drops = set()
    for a in catalog:
        nm = names.get(a)
        if not nm:
            continue
        if 'frag' not in ((nm[0] + ' ' + nm[1]).lower()):
            continue
        for o, oe in spans.items():
            if o != a and o < a < oe:
                drops.add(a)
                break
    return drops


def _fragment_parent(rom, catalog, bounds, addr):
    """Address of the catalog row whose effective span strictly contains
    `addr` (for the 'skipped: fragment of 0xXXXX' message), else None."""
    for o, oe in _fragment_spans(rom, catalog, bounds).items():
        if o < addr < oe:
            return o
    return None


def _callee_extend_to_rts(rom, t, end_c, bounds):
    """Extend a truncated span [t, end_c) that contains NO rts: scan forward
    from `end_c` for the next real `rts` (opcode 0x000B at an even offset,
    skipping literal-pool words) and return rts+4 (the rts plus its delay
    slot) as the new end.  Bounded by the next catalog row start — never
    extends past a catalogued function — or a +0x400 cap; only the FIRST rts
    found is used.  Returns None when there is no room to extend or no rts."""
    cap = min(end_c + 0x400, len(rom))
    nxt = v3._next_addr(t, bounds) if bounds else None
    if nxt is None:
        ub = cap
    elif end_c < nxt < cap:
        ub = nxt
    else:
        # next catalog row starts at/before end_c: no extension window
        return None
    pool = gcl._pcrel_pool_words(rom, t, cap)
    pc = end_c
    while pc + 1 < ub:
        if pc not in pool and (rom[pc] << 8) | rom[pc + 1] == 0x000B:
            return pc + 4
        pc += 2
    return None


def _callee_eff_end(rom, t, catalog, bounds):
    """Effective walk end for callee `t`, fixing truncated spans:
      1. ghidra-span preference: the symbols_60E0FC00.csv end when it is
         LONGER than the catalog end (catalog ends are often cut mid-body);
      2. rts-scan fallback: when the resulting span still has no in-span rts,
         extend past the catalog end to the next real rts (rts+4), bounded by
         the next catalog row start / +0x400 cap.
    Returns the effective end, or None when no span exists."""
    end_c = _callee_span_end(t, catalog, bounds)
    if end_c is None:
        return None
    g_end = _ghidra_span_end(t)
    if g_end is not None and g_end > end_c:
        end_c = g_end
    if _callee_first_rts(rom, t, end_c) is None:
        ext = _callee_extend_to_rts(rom, t, end_c, bounds)
        if ext is not None:
            end_c = ext
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


def _callee_walk_end(rom, t, end_c):
    """Walk bound for a callee's inline mirror.

    Base = first `rts` (or catalog end).  A callee with a conditional branch
    (bt/bf/bt.s/bf.s) whose target lies PAST that first rts has a SECOND return
    path — the first rts belongs to the other path only.  The linear v3.walk_v3
    would stop short, so the mirror hits `<no code>` at the branch target and
    returns early while sh2emu keeps running (MISMATCH, e.g. callee 0x4BBC of
    0x7094: bf@0x4BC2 -> 0x4BCC past rts@0x4BC8).  Extend the walk end, by
    fixpoint, to the furthest in-span (<= catalog end) branch target so BOTH
    return paths have records.  Bounded by `end_c` so it never crosses into the
    next function."""
    bound = min(end_c, len(rom))
    pool = gcl._pcrel_pool_words(rom, t, end_c)
    rts = _callee_first_rts(rom, t, end_c)
    walk_end = rts + 2 if rts is not None else end_c
    changed = True
    while changed:
        changed = False
        _p = t
        while _p + 1 < min(walk_end, bound):
            if _p in pool:
                _p += 2
                continue
            _bi = ops.branch_info((rom[_p] << 8) | rom[_p + 1])
            if _bi is not None and _bi.get('target_disp') is not None \
                    and _bi['kind'] not in ('rts', 'rte', 'bsrf', 'braf'):
                _tgt = (_p + 4 + _bi['target_disp'] * 2) & MASK
                if _tgt + 2 > walk_end:
                    # extend past the target AND its linear continuation up to
                    # the next rts (or the span bound), so the second return
                    # path's records exist in the walk.
                    _rx = _callee_first_rts(rom, _tgt, end_c)
                    _new = (_rx + 2 if _rx is not None else end_c)
                    if walk_end < _new <= bound:
                        walk_end = _new
                        changed = True
            _p += 2
    return walk_end


def _emit_one(pc, op, rom):
    """Emit a single non-branch instruction record (synthesized delay slot for a
    trampoline bra).  Mirrors build_cfg's local emit_one but records a generic
    'st' without stack-state tracking — the trampoline's delay slot is normally
    a nop / plain stmt.  Returns the record, or an opaque stub if unmapped."""
    d = ops.translate(op, pc, rom)
    if d is None:
        return {'pc': pc, 'kind': 'st', 'op': None,
                'c': ['/* delay slot 0x%04X — opaque */' % op],
                'py': [], 'target': None, 'slot': None,
                'mnem': 'op 0x%04X' % op}
    return {'pc': pc, 'op': op, 'kind': 'st',
            'c': list(d.get('c') or []),
            'py': list(d.get('py') or []),
            'target': None, 'slot': None,
            'mnem': d.get('ann') or ('op 0x%04X' % op)}


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
    if depth > 32:
        return None, 'depth>32'
    if seen is None:
        seen = set()
    if t in seen:
        return None, 'cycle'
    seen = seen | {t}
    end_c = _callee_eff_end(rom, t, catalog, bounds)
    if end_c is None:
        return None, ('no-span', t)
    rts = _callee_first_rts(rom, t, end_c)
    walk_end = _callee_walk_end(rom, t, end_c)
    # literal-pool words inside the walk span: a nested-call edge that lands on
    # a pool/data word (not code) must not be walked as a function — recursing
    # hard-fails with ('unmapped', tgt).  Same pool source the *_first_rts /
    # *_walk_end helpers already use.
    pool = gcl._pcrel_pool_words(rom, t, walk_end)
    cfg_end = min(walk_end + 2, end_c)
    res = build_cfg(rom, t, cfg_end, allow_runtime_base=True, tail_bra_as_call=True)
    if res.reject is not None:
        reason, pc = res.reject
        if reason == 'target_fuori':
            # trampoline: callee immediately bra's to an out-of-span target.
            # Re-decode the bra at pc to get the target, then recurse.
            op = (rom[pc] << 8) | rom[pc + 1]
            bi = ops.branch_info(op)
            if bi is None or bi.get('kind') != 'bra':
                return None, ('trampoline', t, pc, reason)
            tgt = (pc + 4 + bi['target_disp'] * 2) & MASK
            sub, reason2 = _walk_callee(rom, tgt, catalog, bounds,
                                        depth=depth + 1, seen=seen)
            if sub is None:
                return None, ('trampoline', t, tgt, reason2)
            # synthesize the bra record (delay slot at pc+2)
            slot = None
            spc = pc + 2
            if spc + 1 < walk_end:
                sop = (rom[spc] << 8) | rom[spc + 1]
                slot = _emit_one(spc, sop, rom)
                if slot is None:
                    return None, ('trampoline-slot', t, pc)
            br_rec = {'pc': pc, 'op': op, 'kind': 'branch',
                      'mnem': 'bra %#x' % tgt, 'target': tgt, 'slot': slot}
            return [br_rec] + sub, None
        if reason == 'midfunc_nop':
            # NOP-sled padding target (e.g. 0x4C14): synthesize a no-op body
            # (NOPs until the first rts) instead of failing the whole emit.
            e2 = pc
            body = []
            while e2 + 1 < end_c:
                w = (rom[e2] << 8) | rom[e2 + 1]
                if w == 0x000B:
                    body.append({'pc': e2, 'op': w, 'kind': 'ret',
                                 'mnem': 'rts', 'c': ['return r0;']})
                    return body, None
                if w != 0x0009:
                    break
                body.append({'pc': e2, 'op': w, 'kind': 'nop',
                             'mnem': 'nop', 'c': []})
                e2 += 2
        return None, (reason, pc)
    records = res.records
    # bug d (walk): a callee whose catalog span is cut mid-epilogue ends its
    # walk on `lds.l @r15+,pr` (0x4F26) with no rts in-span — the inlined
    # mirror stops there while sh2emu falls into the next function.  Reject
    # the walk (same conservative rule as build_cfg) unless an rts follows.
    if records and rts is None:
        _lr = records[-1]
        if _lr.get('op') == 0x4F26 and _lr.get('pc', 0) + 2 >= walk_end:
            _nxt = (rom[walk_end] << 8) | rom[walk_end + 1] \
                if walk_end + 1 < len(rom) else None
            if _nxt != 0x000B:
                return None, ('span-no-return', t)
    # inline nested call targets so the mirror can execute them (a callee that
    # jsr/jmp's another function needs that function's records in the mirror,
    # or the mirror returns early at the call and diverges from sh2emu).
    out = []
    for rec in records:
        out.append(rec)
        if rec['kind'] == 'call' and rec.get('target') is not None:
            tgt = rec['target']
            if not (t <= tgt < walk_end):
                if tgt in pool:
                    # bug f: nested-call edge lands on a literal-pool / data
                    # word (e.g. 0x00648E's chain ends at 0x36BEC, a pool word
                    # inside FUN_00036b84's span).  Recursing hard-fails with
                    # ('unmapped', tgt).  Mirror the runtime_dispatch record
                    # instead: jsr -> pr=ret_pc, dispatch on s->r[0] (the
                    # literal target register); the pool word is never in CODE,
                    # so jsr falls through to ret_pc and a tail jmp returns —
                    # the nullsub-fallback behaviour.  Mutate the record in
                    # place (the edge stays in the walk).
                    _sp = rec.get('set_pr', False)
                    _rp = rec.get('ret_pc')
                    rec.update({
                        'kind': 'runtime_dispatch',
                        'mnem': '%s @r0 (pool target 0x%X)' % ('jsr' if _sp else 'jmp', tgt),
                        'reg': 0,
                        'is_call': _sp,
                        'ret_pc': _rp,
                        'target': None,
                        'c': ([v7.to_st_c(s) for s in rec['slot']['c']]
                              if rec.get('slot') is not None else [])
                             + (['s->pr = 0x%08X;' % _rp] if _sp else [])
                             + ['((void(*)(ST*))s->r[0])(s);']
                             + (['return;'] if not _sp else []),
                    })
                    continue
                sub, reason = _walk_callee(rom, tgt, catalog, bounds,
                                           depth=depth + 1, seen=seen)
                if sub is None:
                    return None, ('nested-call', t, tgt, reason)
                out.extend(sub)
    return out, None


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
        elif rec['kind'] == 'call_runtime':
            stmts.extend(rec['c'])           # already ST-form
        elif rec['kind'] == 'runtime_dispatch':
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
    end_c = _callee_eff_end(rom, t, catalog, bounds)
    if end_c is None:
        return None, ('callee-no-span', t)
    # The callee leaf is bounded by its first `rts` (plus any conditional-branch
    # target past it), NOT the full catalog span — same rule as _walk_callee.
    # Using end_c here walked the CFG into the post-rts literal/data words
    # (e.g. 0x5E2CE: rts@0x5E2DE, pool 0x00C0..@0x5E2E2) and rejected
    # 'unmapped' on a data word, even though the walk of the same span succeeds.
    cfg_end = min(_callee_walk_end(rom, t, end_c) + 2, end_c)
    lifted = _load_lifted()
    res = build_cfg(rom, t, cfg_end, lifted, catalog, allow_runtime_base=True, tail_bra_as_call=True)
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
    end_c = _callee_eff_end(rom, t, catalog, bounds)
    if end_c is None:
        return None, ('callee-no-span', t)
    rts = _callee_first_rts(rom, t, end_c)
    size = (rts + 2 if rts is not None else end_c) - t
    if size <= 0 or size > 704:
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
    categories = _load_categories_bank(
        os.path.join(ROOT, 'symbols', 'FUNCTION_CATEGORIES.csv'), rom_label)
    _, no_spans, _b = _load_catalog(
        os.path.join(ROOT, 'symbols', 'CATALOG_MASTER.csv'), rom_label)
    cands = v3._merge_nospan_cands(categories, no_spans, bounds, rom_label)
    names = _bank_names(rom_label)
    drop_set = _fragment_drop_addrs(rom, catalog, bounds, names)
    for c in cands:
        addr = c['addr']
        if addr in drop_set:
            continue
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
                  rom_label='60E1D400', catalog=None, bounds=None,
                  rt_entries=None):
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
    # target INCLUSION: runtime_dispatch table entries are additional inlined
    # callees (their own nested bsr/jsr targets are walked recursively by
    # _walk_callee).  Entries surface from ANY record — the caller's own
    # dispatches AND the inlined callees' dispatches (e.g. a callee that does
    # mova <table>,r0 / mov.l @(r0,rB),rN / jsr @rN) — so collect from
    # all_records with a fixpoint: an included target's own nested dispatches
    # add further entries.  Per-entry tolerance: an entry that fails to walk
    # (e.g. its own span contains an unresolvable dispatch) is dropped — the
    # mirror keeps the nullsub fallback for its cases and they may diverge;
    # the remaining entries still get their code included.  Failures are
    # reported on stdout.
    all_records = list(res.records) + callee_records
    _seen = set(callees)
    queue = []
    for r in all_records:
        for e in (r.get('rt_entries') or []):
            if e not in _seen:
                queue.append(e)
    while queue:
        t = queue.pop()
        if t in _seen:
            continue
        _seen.add(t)
        w, reason = _walk_callee(rom, t, catalog, bounds)
        if w is None:
            print('WARN rt-dispatch target 0x%X not included: %r '
                  '(its cases keep the nullsub fallback -> may diverge)'
                  % (t, reason))
            continue
        all_records.extend(w)
        for r in w:
            for e in (r.get('rt_entries') or []):
                if e not in _seen:
                    queue.append(e)
    # (bug c) PR-LEAK fix: the composite mirror addresses the stack with the
    # RUNTIME sp (r15), not per-function fixed STACK_BASE+off slots.  Each
    # function's records were emitted with its own sp_off starting at 0x400, so
    # the inlined callee's first @-r15 push collided with the caller's pr save
    # slot (both at 0x3FC) and the caller epilogue `lds.l @r15+,pr` restored a
    # clobbered pr.  Real r15 at callee entry is below the caller's frame, so
    # sp-relative addressing keeps the caller's pr slot untouched.
    for _rec in all_records:
        _rec['py'] = _sprel_py(_rec)
        _slot = _rec.get('slot')
        if _slot is not None:
            _slot['py'] = _sprel_py(_slot)

    # call_runtime seed override: every ROM callback slot referenced by a
    # call_runtime record (caller OR inlined callee) gets its 4 bytes pinned to
    # a clean nullsub address (big-endian) so sh2emu's `jsr @rN` runs the
    # nullsub (clean return) exactly like the mirror's no-op call_runtime.
    _nullsub = _find_nullsub(rom)
    if _nullsub is None:
        return False, ('no-nullsub', addr)
    _seen_slots = set()
    slot_seeds = []
    for _rec in all_records:
        if _rec.get('kind') == 'call_runtime':
            _sl = _rec.get('slot_addr')
            if _sl is not None and _sl not in _seen_slots:
                _seen_slots.add(_sl)
                slot_seeds.append((_sl, _nullsub))
    slot_seeds = tuple(slot_seeds)

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
        'MAXSTEPS = %d\n'
        'STACK_BASE = 0xFFFFD000\n'
        'STACK_TOP = STACK_BASE + 0x400\n'
        'STACK_OFFS = (%s)\n'
        'RAM_MIN = %s\n'
        'RAM_MAX = %s\n'
        'PRET = 0xEEEE0000\n'
        'JTABLES = %r\n'
        'SLOT_SEEDS = %r\n\n'
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
        '          "sr": 0x000000F0, "gbr": 0, "s8": s8, "s16": s16, "s32": s32, "ts": ts,\n'
        '          "bits2f": bits2f, "f2bits": f2bits, "ram": ram,\n'
        '          "sp": r[15], "_rdw": _rdw, "_wrw": _wrw, "STACK_BASE": STACK_BASE,\n'
        '          "local": {off: _rdw(ram, STACK_BASE + off, 4) for off in STACK_OFFS}}\n'
        '    pc = ENTRY\n'
        '    steps = 0\n'
        '    while True:\n'
        '        # (v8.8) keep r[15] in lockstep with the runtime `sp` alias.  The\n'
        '        # stack opcodes (sts.l pr,@-r15 / add #imm,r15 / mov.l @r15+,Rn)\n'
        '        # are emitted sp-relative (sp updates only); any instruction that\n'
        '        # COPIES r15 into another register (frame ptr / wrapper arg, e.g.\n'
        '        # mov r15,r4) would otherwise read a stale r[15] one push ahead of\n'
        '        # sp, making the callee store/load the WRONG stack slot (MISMATCH\n'
        '        # case=0 reg=r0/r2/r3/r4 on caller wrappers).\n'
        '        r[15] = ns["sp"] & 0xFFFFFFFF\n'
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
        '            # out-of-span conditional tail calls (bt/s, bf/s) carry the\n'
        '            # branch condition on the record; the mirror must only jump\n'
        '            # when T matches, else fall through past the branch (the\n'
        '            # delay slot, if any, still executes on SH/H8).\n'
        '            _cond = inst["cond"]\n'
        '            if _cond == "T":\n'
        '                _taken = (ns["T"] == 1)\n'
        '            elif _cond == "notT":\n'
        '                _taken = (ns["T"] == 0)\n'
        '            else:\n'
        '                _taken = True\n'
        '            slot_py = inst["slot_py"]\n'
        '            if _taken:\n'
        '                if inst["set_pr"]:\n'
        '                    ns["pr"] = inst["ret_pc"]\n'
        '                if slot_py:\n'
        '                    exec(slot_py, ns)\n'
        '                pc = inst["target"]\n'
        '            else:\n'
        '                if slot_py:\n'
        '                    exec(slot_py, ns)\n'
        '                pc = pc + (4 if slot_py is not None else 2)\n'
        '        elif kind == "call_runtime":\n'
        '            # RAM/ROM-slot indirect call: the runtime target value is\n'
        '            # ignored; sh2emu executes the seeded nullsub (clean return)\n'
        '            # so both sides continue together at ret_pc with pr=pc+4.\n'
        '            if inst["set_pr"]:\n'
        '                ns["pr"] = inst["ret_pc"]\n'
        '            slot_py = inst["slot_py"]\n'
'            if slot_py:\n'
         '                exec(slot_py, ns)\n'
         '            pc = inst["ret_pc"]\n'
         '        elif kind == "runtime_dispatch":\n'
         '            # runtime-indexed jmp/jsr: dispatches to r[reg] if that\n'
         '            # target was lifted into CODE (in-span); else jsr falls\n'
         '            # through to ret_pc and jmp returns (RET).  Mirrors\n'
         '            # sh2emu, which runs the real target on the shared seeded\n'
         '            # RAM (in-span targets match; out-of-span targets drift,\n'
         '            # but sh2emu escaping is caught by StepLimitExceeded->skip).\n'
         '            slot_py = inst["slot_py"]\n'
         '            if slot_py:\n'
         '                exec(slot_py, ns)\n'
         '            reg = inst["reg"]\n'
         '            _tg = r[reg] & 0xFFFFFFFF\n'
         '            _tgt = CODE.get(_tg)\n'
         '            if inst["is_call"]:\n'
         '                ns["pr"] = inst["ret_pc"]\n'
         '                pc = inst["ret_pc"] if _tgt is None else _tg\n'
         '            else:\n'
         '                if _tgt is None:\n'
         '                    return ("RET", [x & 0xFFFFFFFF for x in r],\n'
         '                            list(_WRITES), dict(ram), ns["pr"] & 0xFFFFFFFF)\n'
         '                pc = _tg\n'
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
        '            if inst.get("rte"):\n'
        '                # rte pops PC+SR (8 bytes) off the stack before the\n'
        '                # delay slot / jump; the mirror returns via pr like rts.\n'
        '                ns["sp"] = (ns["sp"] + 8) & 0xFFFFFFFF\n'
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
        '        for _sl, _tv in SLOT_SEEDS:\n'
        '            _tb = _tv.to_bytes(4, "big")\n'
        '            for _i in range(4):\n'
        '                ram[_sl + _i] = _tb[_i]\n'
        '        a = rnd.randint(0, 0xFFFFFFFF); b = rnd.randint(0, 0xFFFFFFFF)\n'
        '        c_ = rnd.randint(0, 0xFFFFFFFF); d = rnd.randint(0, 0xFFFFFFFF)\n'
        '        m = spec_mirror(a, b, c_, d, dict(ram))\n'
        '        if m[0] != "RET":\n'
        '            if m[0] == "SKIP":\n'
        '                try:\n'
        '                    run(cpu, ram, a, b, c_, d)\n'
        '                except StepLimitExceeded:\n'
        '                    continue\n'
        '                except (NotImplementedError, RuntimeError):\n'
        '                    skipped += 1; continue\n'
        '                print("MISMATCH case=%%d mirror=SKIP emu=RET" %% (caso,))\n'
        '                sys.exit(1)\n'
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
        '    has_ret = False\n'
        '    seen = set(); stack = [ENTRY]\n'
        '    while stack:\n'
        '        pc = stack.pop()\n'
        '        if pc in seen:\n'
        '            continue\n'
        '        seen.add(pc)\n'
        '        inst = CODE.get(pc)\n'
        '        if inst is None:\n'
        '            continue\n'
        '        k = inst["kind"]\n'
        '        if k == "ret":\n'
        '            has_ret = True; break\n'
        '        if k == "branch":\n'
        '            if inst["target"] is not None:\n'
        '                stack.append(inst["target"])\n'
        '            stack.append(pc + (4 if inst["slot_py"] is not None else 2))\n'
        '        elif k == "call":\n'
        '            if inst["cond"] in ("T", "notT"):\n'
        '                stack.append(inst["target"])\n'
        '                stack.append(pc + (4 if inst["slot_py"] is not None else 2))\n'
        '            else:\n'
        '                stack.append(inst["ret_pc"])\n'
'        elif k == "call_runtime":\n'
         '            stack.append(inst["ret_pc"])\n'
         '        elif k == "runtime_dispatch":\n'
         '            if inst["is_call"]:\n'
         '                stack.append(inst["ret_pc"])\n'
         '            stack.append(pc + (4 if inst["slot_py"] is not None else 2))\n'
        '        elif k == "jt":\n'
        '            stack.extend(c for c in inst["cases"] if c is not None)\n'
        '            stack.append(pc + (4 if inst["slot_py"] is not None else 2))\n'
        '        elif k == "dynbranch":\n'
        '            stack.append(pc + (4 if inst["slot_py"] is not None else 2))\n'
        '        else:\n'
        '            stack.append(pc + 2)\n'
        '    if ok == 0 and not has_ret:\n'
        '        print("HALT (correct) %%d/%%d (skipped=%%d)" %% (ok, N, skipped))\n'
        '        sys.exit(0)\n'
        '    if skipped > 200 or ok == 0:\n'
        '        print("FAIL %%d/%%d (skipped=%%d)" %% (ok, N, skipped))\n'
        '        sys.exit(1)\n'
        '    print("PASS %%d/%%d (skipped=%%d)" %% (ok, N, skipped))\n\n'
        'if __name__ == "__main__":\n'
        '    main()\n'
    ) % (fn, addr, end - addr, cases, os.path.basename(out_t), rom_label,
         addr, seed, cases, MAXSTEPS_OVERRIDE.get(addr, 100000), stack_offs,
         'None' if ram_min is None else '0x%X' % ram_min,
         'None' if ram_max is None else '0x%X' % ram_max,
         jt_lits, slot_seeds,
         _v8_code_literal(all_records, res.labels, res.jump_tables))
    with open(out_t, 'w') as f:
        f.write(test)
    return True, None


def _sprel_py(rec):
    """Rewrite an r15/r14 based stack/frame record's py to runtime-relative
    addressing.  Returns the new py list (local[] writes are dropped: they are
    write-only mirror state that would re-bake the fixed-offset model).  Only
    r15-based and r14-frame ops are rewritten; literal-RAM ops keep their
    addressing.

    r14-frame records (@(disp,r14) / @r14) are baked to absolute STACK_BASE+off
    where off uses the record's own sp_off seed (STACK_TOP for an inlined
    callee), NOT the caller's real sp at the call site.  Since the frame-pointer
    fix guarantees r14==r15 (runtime sp) in the mirror, emit them as runtime
    r[14]+disp instead like the r15 ops."""
    op = rec.get('op', 0)
    kind = rec.get('kind')
    if kind == 'fpu_mem':
        # fmov.s frN,@-r15 (pre) / fmov.s @r15+,frN (post): runtime r15 stack
        # push/pop.  The py was emitted r[15]-relative by _fpu_mem/_fpu_mem_rt;
        # the mirror re-syncs r[15] = sp at the top of every step, so the
        # r[15] update alone would silently drop the push/pop from stack
        # accounting.  Rewrite to the sp alias: write/read at `sp`, then
        # advance sp.  Only the @-r15 (pre) / @r15+ (post) forms; the plain
        # @r15 / @(disp,r15) / @(r0,r15) forms keep r[15] addressing.
        if rec.get('base_reg') == 15 and rec.get('auto') in ('pre', 'post'):
            out = []
            for ln in (rec.get('py') or []):
                ln = re.sub(r'^r\[15\] = \(r\[15\] - 4\) & 0xFFFFFFFF$',
                            'sp = (sp - 4) & 0xFFFFFFFF', ln)
                ln = re.sub(r'^r\[15\] = \(r\[15\] \+ 4\) & 0xFFFFFFFF$',
                            'sp = (sp + 4) & 0xFFFFFFFF', ln)
                ln = re.sub(r'^_wrw\(ram, r\[15\], 4,',
                            '_wrw(ram, sp, 4,', ln)
                ln = re.sub(r'_rdw\(ram, r\[15\], 4\)',
                            '_rdw(ram, sp, 4)', ln)
                out.append(ln)
            return out
        return list(rec.get('py') or [])
    if kind == 'sys_stack':
        if (op >> 8) & 0xF != 15:
            return list(rec.get('py') or [])
        sys_store = (op & 0xF) == 0x2
        addr = '(sp - 4) & 0xFFFFFFFF' if sys_store else 'sp'
    elif kind == 'stack':
        sh = gcl._mem_shape(op)
        if sh is None or sh.get('idx') is not None:
            return list(rec.get('py') or [])
        if sh['base'] == 15:
            if sh['auto'] == 'pre':
                addr = '(sp - %d) & 0xFFFFFFFF' % sh['size']
            elif sh['auto'] == 'post':
                addr = 'sp'
            else:
                addr = 'sp + %d' % sh['disp'] if sh['disp'] else 'sp'
        elif sh['base'] == 14:
            if sh['auto'] in ('pre', 'post'):
                return list(rec.get('py') or [])
            addr = 'r[14] + %d' % sh['disp'] if sh['disp'] else 'r[14]'
        else:
            return list(rec.get('py') or [])
    else:
        # Generic r15 stack model: the mirror re-syncs r[15] = sp at the top
        # of every step, so a py that addresses memory via r[15] or updates
        # r[15] (push/pop/restore like mov rN,r15, mov.l rN,@-r15, lds.l
        # @r15+,...) would silently drop the write from stack accounting —
        # r[15] gets clobbered back to sp at the next step.  Since r[15] is
        # synced to sp, substituting the sp alias is value-preserving for any
        # record that does not already carry sp (those already-relative
        # records stay untouched).  Mirrors the fpu_mem / sys_stack rewrite
        # above for the remaining kinds ('mem'/'st'/'reg'/'ldc').
        py = list(rec.get('py') or [])
        if not py or any('sp' in ln for ln in py):
            return py
        # standalone r[15] only — never mangle fr[15] (fpu) into fsp
        return [re.sub(r'(?<!f)r\[15\]', 'sp', ln) for ln in py]
    out = []
    for ln in (rec.get('py') or []):
        if re.match(r'^local\[0x[0-9A-Fa-f]+\]\s*=', ln):
            continue
        if '_rdw(ram, STACK_BASE + 0x' in ln:
            ln = re.sub(r'_rdw\(ram, STACK_BASE \+ 0x[0-9A-Fa-f]+, (\d+)\)',
                        '_rdw(ram, %s, \\1)' % addr, ln)
        elif '_wrw(ram, STACK_BASE + 0x' in ln:
            ln = re.sub(r'_wrw\(ram, STACK_BASE \+ 0x[0-9A-Fa-f]+, (\d+),',
                        '_wrw(ram, %s, \\1,' % addr, ln)
        # rt-base/dyn py (kind 'sys_stack'/'stack') is emitted r[15]-relative
        # (pr = _rdw(ram, r[15], 4) / r[15] = (r[15] - 4) & 0xFFFFFFFF); the
        # mirror re-syncs r[15] = sp at the top of every step so r[15]-only
        # pops/pushes would silently drop the stack accounting.  r[15] is
        # synced to sp, so substituting the sp alias is value-preserving.
        if 'r[15]' in ln and 'sp' not in ln:
            ln = re.sub(r'(?<!f)r\[15\]', 'sp', ln)
        out.append(ln)
    return out


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
            if bkind in ('rts', 'rte'):
                rte_flag = '"rte": True, ' if bkind == 'rte' else ''
                lines.append('    %#x: {"kind": "ret", "py": None, '
                             '"slot_py": %r, "target": None, "cond": None, %s},'
                             % (pc, slot_py, rte_flag))
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
        if kind == 'ret':
            # inlined-callee return: emitted directly as 'ret' (e.g. the
            # midfunc_nop rts synthesis in _walk_callee for a nop-delay-loop
            # callee like f_4C14).  Without this branch the fallback below
            # maps it to 'st' and the mirror walks past the inlined block
            # (falls off the end -> returns pre-call state, MISMATCH).
            lines.append('    %#x: {"kind": "ret", "py": None, '
                         '"slot_py": %r, "target": None, "cond": None},'
                         % (pc, slot_py))
            continue
        if kind == 'call':
            lines.append('    %#x: {"kind": "call", "py": None, '
                         '"slot_py": %r, "target": %#x, "ret_pc": %#x,'
                         ' "set_pr": %r, "cond": %r},'
                         % (pc, slot_py, rec['target'], rec['ret_pc'],
                            rec['set_pr'], rec.get('cond')))
            continue
        if kind == 'call_runtime':
            lines.append('    %#x: {"kind": "call_runtime", "py": None, '
                         '"slot_py": %r, "target": None, "ret_pc": %#x,'
                         ' "set_pr": %r, "cond": None, "slot_addr": %#x},'
                         % (pc, slot_py, rec['ret_pc'], rec['set_pr'],
                            rec['slot_addr']))
            continue
        if kind == 'runtime_dispatch':
            lines.append('    %#x: {"kind": "runtime_dispatch", "py": None, '
                         '"slot_py": %r, "target": None, "ret_pc": %#x,'
                         ' "reg": %d, "is_call": %r, "cond": None},'
                         % (pc, slot_py, rec['ret_pc'], rec.get('reg'),
                            rec.get('is_call')))
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
    ap.add_argument('--dryrun', action='store_true',
                    help='bank-clean scan: count the pool only, write no files')
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
    if args.dryrun:
        run_dryrun(args.rom, rom_label, seed=args.seed)
        return 0
    if args.emit:
        addr = int(args.emit, 16)
        cat_path = os.path.join(ROOT, 'symbols', 'CATALOG_MASTER.csv')
        catalog, _, bounds = _load_catalog(cat_path, rom_label)
        names = _bank_names(rom_label)
        drop_set = _fragment_drop_addrs(rom, catalog, bounds, names)
        if addr in drop_set:
            parent = _fragment_parent(rom, catalog, bounds, addr)
            print('skipped: 0x%X is a fragment of 0x%X' % (addr, parent))
            return 0
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
