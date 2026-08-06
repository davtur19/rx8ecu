#!/usr/bin/env python3
"""
gen_c_lift_v3.py — deterministic CLI that lifts SH-2 functions WITH internal
branches + delay slots from the RX-8 ECU ROM into C (c/<name>_<addr>.c).

v3 (this tool) reuses gen_c_lift.py's v3 SELECTION — `_scan_mem_function` already
admits bt/bf/bt.s/bf.s/bra/rts (target inside the catalog span [addr,end), rts
anywhere; delayed variants only when the P+2 delay slot is not itself a branch/
call/rte) and rejects call/unmapped/fpu/rte/delay_slot_ctrl/target_fuori — and
adds the missing half: EMISSION of branches and delay slots.  Only functions
that have at least one admitted branch are lifted (v3 = branch/delay-slot
lifts).  Output is a single C file per function plus a differential test
(c/tests/test_<name>_<addr>.py) that runs a Python pc-interpreter spec_mirror
(exec'ing the mapper py fragments over a CODE dict, with sh2emu's branch/delay-
slot T-sampling) against the sh2emu oracle over N random inputs (--cases,
default 2000); the tests are run at generation time and summarized in a report.

Emission rules (v3):
  - instructions in linear order; every branch-target address gets a
    `L_<addr_hex>: ;` label line right before its instruction;
  - a delayed branch/return emits its delay slot BEFORE the branch, exactly
    once (the slot address is skipped in the linear stream);
  - bt/bf read T: `if (T) goto L_...;` / `if (!T) goto L_...;`; bra is
    unconditional; rts emits `return r0;` (slot first); end of span falls
    through to `return r0; /* fallthrough */`;
  - locals: only registers actually referenced, `uint32_t T = 0;` only when T
    appears in the body, temps t1.. inline for mem loads (same helpers as
    gen_c_lift._walk_mem_span).

Every lift is compile-gated with `cc -O2 -c`; a failing lift is deleted.

Usage:
    python3 tools/gen_c_lift_v3.py --n 2 --seed 42
    python3 tools/gen_c_lift_v3.py --dryrun --n 10 --seed 0 --category "CAN Bus"
    python3 tools/gen_c_lift_v3.py --addr 0x1234
"""
import argparse
import bisect
import csv
import glob
import os
import random
import re
import subprocess
import sys
import tempfile
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import c_lift_ops as ops
import gen_c_lift as gcl          # reuse v3 selection + mem-emission helpers
import sh2emu                     # emu:(yes/no) check for unmapped opcodes (additive C)

DEFAULT_ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')

# Branch emission templates (keyed by branch_info()['kind']).  The delay slot
# (if any) is emitted before the template by the walker/renderer.
BRANCH_C = {
    'bt':  'if (T) goto L_%X;',
    'bts': 'if (T) goto L_%X;',
    'bf':  'if (!T) goto L_%X;',
    'bfs': 'if (!T) goto L_%X;',
    'bra': 'goto L_%X;',
    'rts': 'return r0;',
}
BRANCH_MNEM = {
    'bt':  'bt 0x%06X',
    'bts': 'bt.s 0x%06X',
    'bf':  'bf 0x%06X',
    'bfs': 'bf.s 0x%06X',
    'bra': 'bra 0x%06X',
    'rts': 'rts',
}


# ---------------------------------------------------------------------------
# Selection: same span/base rules as gen_c_lift.select_mem (reuses
# _scan_mem_function verbatim, including the v3 branch admission + per-motivo
# branch counters), but the pool only keeps functions with >= 1 admitted
# branch — v3 lifts are branch/delay-slot lifts by construction.
#
# v4: selection AND emission run on the SANITIZED span (addr_s, end_s) — the
# catalog end is trimmed of trailing 0x0000/0xFFFF padding and extended into
# near branch targets (sanitize_span).  The size gate is adapted to the
# sanitized span (8 <= end_s-addr <= 160+16); each accepted entry carries the
# sanitized end (entry['size'] = end_s - addr, entry['end_s'] = end_s) so the
# emission path (emit_v3 / emit_v3_test / walk_v3 / banner / sentinel) decodes
# exactly the sanitized span.
# ---------------------------------------------------------------------------
# v5 (additive, no-span end estimation): a function with NO known catalog end
# (no_span) gets an estimated end = the next known catalog address strictly
# greater than its addr, from the SAME bank (NOISE rows and the 0xFFFFFFFF
# sentinel are excluded).  The estimate only feeds the existing selection gate
# (sanitize_span + size 8..176 + _scan_mem_function/_scan_fpu_function +
# >=1 branch + dedup) — it never loosens any criterion.  Selected entries carry
# `estimated_end` (the next-addr used) so the .c banner can flag them.
# ---------------------------------------------------------------------------
def _next_addr(addr, addrs):
    """Smallest element of sorted `addrs` strictly greater than `addr`, or None."""
    i = bisect.bisect_right(addrs, addr)
    return addrs[i] if i < len(addrs) else None


def load_catalog_nospans(path):
    """Parse CATALOG_MASTER.csv once -> (catalog_bank, no_spans, bounds).

      catalog_bank : {bank: {addr: end_or_None}}  (NOISE excluded; addr
                     0xFFFFFFFF excluded; end 0xFFFFFFFF treated as no-end).
                     KEY: the catalog stores each function once PER BANK and
                     some banks legitimately lack the end (e.g. 60E0FC00 rows
                     with flag GHIDRA-EQX and an empty end) — lookups must use
                     the FUNCTION'S OWN BANK, not a global addr->end dict.
      no_spans     : [{addr,bank,name}]  rows (bank-specific) with no real end
      bounds       : {bank: sorted addrs of that bank}  (estimation boundaries)
    """
    catalog_bank, no_spans = {}, []
    with open(path) as f:
        for row in csv.DictReader(f):
            if (row.get('flag') or '').strip() == 'NOISE':
                continue
            try:
                addr = int(row['addr'].strip(), 16)
            except (ValueError, TypeError):
                continue
            if addr == 0xFFFFFFFF:                  # HUDI sentinel: not a boundary
                continue
            bank = (row.get('bank') or '').strip()
            try:
                end = int((row.get('end') or '').strip(), 16)
            except (ValueError, TypeError):
                end = None
            if end == 0xFFFFFFFF:                      # "unknown end" sentinel
                end = None
            cat = catalog_bank.setdefault(bank, {})
            cat[addr] = end
            if end is None:
                no_spans.append({'addr': addr, 'bank': bank,
                                 'name': (row.get('src_name')
                                          or row.get('name') or '').strip()})
    bounds = {b: sorted(c) for b, c in catalog_bank.items()}
    return catalog_bank, no_spans, bounds


def _merge_nospan_cands(cands, no_spans, bounds, bank):
    """Append the catalog no-span functions of `bank` (module-side estimation) to
    the candidate list.  Only addresses NOT already present are added (the FC
    rows keep their nicer name; catalog-only no_span rows get src_name/start).
    Order is deterministic: existing cats first, then sorted by addr.
    Returns a NEW list (input not mutated)."""
    existing = {c['addr'] for c in cands}
    out = list(cands)
    if bounds is None or bank not in bounds:
        return out
    for e in sorted(no_spans, key=lambda x: x['addr']):
        if e['bank'] == bank and e['addr'] not in existing:
            out.append({'addr': e['addr'], 'name': e['name'],
                        'category': 'Other / Unclassified'})
            existing.add(e['addr'])
    return out


# ---------------------------------------------------------------------------
# copy+arith register tracker (a "what the base register equals at the mem
# access" model) for the v3/v4 SELECTION scanner `_scan_mem_v3`.  Tracks each of
# r0..r14 as one of:
#   None                       -> UNKNOWN (any non-foldable write)
#   ('lit', val)              -> known constant value
#   ('expr', base_reg, off)   -> r<base_reg> + off
# Rules (write to rN):
#   mov rM->rN         copy   trk[rN] = trk[rM]
#   mov #imm,rN        -> ('lit', imm)
#   mov.w/l @(d,PC)    -> ('lit', literal)          (mov.b @(d,PC) does not exist)
#   mova @(d,PC)       -> trk[r0] = ('lit', address)
#   add #imm,rN        -> fold literal / bump expr off
#   shll/shll2/shlr(& 8/16)   evaluate on a literal, else UNKNOWN
#   any other write (RAM load, two-register arith, auto post/pre, ...) -> UNKNOWN
# `fold` (rN): chase ['expr'] through copy/add edges back to a literal root
# ('lit', val) or an unwritten param root ('param', off); None if unreolvable.
# ---------------------------------------------------------------------------
def _trk_fold(trk, written, reg, depth=0):
    if depth > 10:
        return None
    st = trk.get('r%d' % reg)
    if st is None:
        return None
    if st[0] == 'lit':
        return ('lit', st[1])
    base, off = st[1], st[2]
    if 4 <= base <= 7 and 'r%d' % base not in written:
        return ('param', off)
    r = _trk_fold(trk, written, base, depth + 1)
    if r is None:
        return None
    if r[0] == 'lit':
        return ('lit', (r[1] + off) & 0xFFFFFFFF)
    if r[0] == 'param':
        return ('param', r[1] + off)
    return None


def _lit_of(reg, lits, trk, written):
    """Resolve a register to a literal constant: the trusted `lits` dict first,
    then the tracker's literal fold (mova/add/#imm/lit-pool chains — cases the
    old GBR code only consulted `lits` for, so `ldc r0,GBR` fed by a mova
    stayed unresolved).  Returns the int or None."""
    v = lits.get('r%d' % reg)
    if v is not None:
        return v
    r = _trk_fold(trk, written, reg)
    if r and r[0] == 'lit':
        return r[1]
    return None


# opcodes whose fold must EVALUATE a literal (shll/shll2/shlr, shll8/16, shlr8/16)
_TRK_SHIFTS = {0x4000: 1, 0x4008: 2, 0x4018: 8, 0x4028: 16,
               0x4009: 1, 0x4019: 8, 0x4029: 16}
_TRK_SHIFT_LEFT = frozenset((0x4000, 0x4008, 0x4018, 0x4028))


def _trk_apply_stmt(trk, op, rom, pc):
    """Apply the tracker write-rules for a translated pure statement op.
    Returns True if `op` is an r15 stack allocation we should KEEP stack_ok.
    Mirrors a MOV/ADD/IMM/lit/shift subset; everything else -> UNKNOWN."""
    n = (op >> 8) & 0xF
    m = (op >> 4) & 0xF
    regN = 'r%d' % n
    if op & 0xF000 == 0x6000 and (op & 0xF) == 0x3:       # mov rM,rN
        src = trk.get('r%d' % m)
        trk[regN] = list(src) if src else None
    elif op & 0xF000 == 0x7000:                            # add #imm,rN
        imm = ops.s8(op & 0xFF)
        st = trk.get(regN)
        if st and st[0] == 'lit':
            trk[regN] = ('lit', (st[1] + imm) & 0xFFFFFFFF)
        elif st and st[0] == 'expr':
            trk[regN] = ('expr', st[1], st[2] + imm)
    elif op & 0xF000 == 0xE000:                          # mov #imm,rN
        trk[regN] = ('lit', ops.s8(op & 0xFF) & 0xFFFFFFFF)
    elif op & 0xF000 == 0xD000:                          # mov.l @(d,PC),rN
        trk[regN] = ('lit', ops.lit32(rom, pc, op & 0xFF))
    elif op & 0xF000 == 0x9000:                          # mov.w @(d,PC),rN
        trk[regN] = ('lit', ops.lit16(rom, pc, op & 0xFF))
    elif op & 0xFF00 == 0xC700:                          # mova @(d,PC),r0
        trk['r0'] = ('lit', ops.mova_target(pc, op & 0xFF))
    elif op & 0xF0FF in _TRK_SHIFTS:                     # shifts
        st = trk.get(regN)
        if st and st[0] == 'lit':
            v = st[1]; f = op & 0xF0FF; sh = _TRK_SHIFTS[f]
            if f in _TRK_SHIFT_LEFT:
                trk[regN] = ('lit', (v << sh) & 0xFFFFFFFF)
            else:
                trk[regN] = ('lit', v >> sh)
        else:
            trk[regN] = None
    else:
        trk[regN] = None
    return (op & 0xF000 == 0x7000 and n == 15)           # add #imm,r15


def _scan_mem_v3(rom, c, end, branch_stats=None):
    """v3 selection scan mirroring gcl._scan_mem_function VERBATIM (same
    decision order, param/literal/GBR/stack/frame rules, branch admission,
    'no_mem_op' gate) but with the copy+arith register tracker wired into the
    base-resolution path.  `_trk_apply` fold gives a base register a LITERAL
    (or param-rooted expr) value through mov/add/#imm/lit-pool loads — cases the
    old scan rejected as ('base_unresolved', 'altro'); 'r15' stack/allocation
    model and the 'r14' frame rule stay otherwise untouched.  Returns
    (entry, None) | (None, reason) with the identical contract as
    gcl._scan_mem_function."""
    addr = c['addr']
    bound = min(end, len(rom))
    written = set()
    lits = {}
    trk = {}
    tmp = [0]
    gbr_known = False
    gbr_value = None
    stack_ok = True
    frame_live = False
    # v7: known-store RAM model + path gate for literal-base LOAD propagation.
    # `ram_known` = {byte_addr: byte} written by KNOWN stores to literal RAM
    # addresses; `branches_seen` guards RAM folds — once a branch is admitted the
    # linear walk can no longer prove a store precedes a later load on every
    # path, so RAM loads stay unresolved (ROM loads always fold: deterministic).
    ram_known = {}
    branches_seen = False

    def temp():
        tmp[0] += 1
        return 't%d' % tmp[0]

    def resolve(reg):
        # literal base via lits (trusted) OR the tracker's literal fold.
        v = lits.get('r%d' % reg)
        if v is None:
            r = _trk_fold(trk, written, reg)
            if r and r[0] == 'lit':
                v = r[1]
            else:
                return None
        cls = ops.classify_addr(v)
        if cls in ('RAM', 'ROM'):
            return (cls, v)
        return None

    ctx = {'temp': temp, 'resolve': resolve}
    bases = {}
    ops_list = []
    lit_vals = []
    brs = []
    pool_words = gcl._pcrel_pool_words(rom, addr, end)
    pc = addr
    while pc + 1 < bound:
        if pc in pool_words:              # literal-pool data — not an instruction
            pc += 2
            continue
        op = (rom[pc] << 8) | rom[pc + 1]
        d = ops.translate(op, pc, rom)
        if d is not None:
            if d.get('kind') in ('branch', 'ret'):
                target = d.get('target')
                admit, det = gcl._v3_branch_rule(rom, op, target, pc, addr, end)
                gcl._count_branch(branch_stats, det)
                if admit:
                    brs.append((det, pc, target))
                    branches_seen = True
                    pc += 2
                    continue
                return None, ('branch_v3', det)
            writes = gcl._stmt_writes('\n'.join(d.get('c') or []))
            is_stack_alloc = False
            if op == 0x6EF3:
                if 'r14' not in written:
                    frame_live = True
            else:
                if 'r15' in writes:
                    # r15 stack model: `add #imm,r15` is an allocation that keeps
                    # stack_ok; anything else writing r15 leaves it untracked.
                    is_stack_alloc = (op & 0xF000 == 0x7000
                                      and ((op >> 8) & 0xF) == 15)
                    if not is_stack_alloc:
                        stack_ok = False
                if 'r14' in writes:
                    frame_live = False
                # tracker folds every pure-statement write (exactly once)
                _trk_apply_stmt(trk, op, rom, pc)
            if not gcl._apply_stmt(rom, pc, op, d, written, lits):
                return None, 'unmapped'
            pc += 2
            continue
        if op & 0xF0FF == 0x401E:            # ldc Rn,GBR
            gbr_known = True
            _lit = _lit_of((op >> 8) & 0xF, lits, trk, written)
            gbr_value = _lit if _lit is not None else 'input'
            pc += 2
            continue
        if op & 0xF0FF == 0x4017:            # lds.l @Rm+,GBR (GBR = RAM[Rm])
            gbr_known = True
            _lit = _lit_of((op >> 8) & 0xF, lits, trk, written)
            if _lit is not None and _lit < len(rom) and ops.classify_addr(_lit) == 'ROM':
                gbr_value = (rom[_lit] << 24 | rom[_lit + 1] << 16
                             | rom[_lit + 2] << 8 | rom[_lit + 3])
            else:
                gbr_value = 'input'
            pc += 2
            continue
        if gcl.is_call_op(op):
            return None, 'call'
        if op == 0x002B:
            return None, 'rte'
        if gcl.is_branch_op(op):
            return None, 'branch'
        m = ops.decode_mem(op, None, ctx)
        if m is not None:
            base_reg = m['base_reg']
            if m.get('idx') == 'r0' and 'r0' not in lits:
                if not _trk_fold(trk, written, 0):
                    return None, ('base_unresolved', 'altro')
            if base_reg in (4, 5, 6, 7) and 'r%d' % base_reg not in written:
                kind = ('PARAM', None)
                bkind = 'param'
            elif 'r%d' % base_reg in lits:
                kind = ('LITERAL', lits['r%d' % base_reg])
                bkind = 'literal'
            else:
                r = _trk_fold(trk, written, base_reg)
                if not r:
                    return None, ('base_unresolved', 'altro')
                if r[0] == 'lit':
                    kind = ('LITERAL', r[1]); bkind = 'literal'
                else:
                    kind = ('PARAM', None); bkind = 'param'
            bases.setdefault('r%d' % base_reg, kind)
            if kind[0] == 'LITERAL' and kind[1] not in lit_vals:
                lit_vals.append(kind[1])
            ops_list.append({'pc': pc, 'size': m['size'], 'dir': m['dir'],
                             'kind': bkind, 'base_reg': base_reg,
                             'disp': m.get('disp', 0), 'auto': m.get('auto'),
                             'idx': m.get('idx'), 'gbr': False})
            gcl._apply_mem_writes(m, written, lits)
            # v7: propagate LOADs from literal bases (base is a known pool
            # literal / copy+arith): a ROM effective address is deterministic
            # (read from the .bin); a RAM effective address folds only when a
            # KNOWN store wrote the slot earlier on the linear path (no branch
            # admitted yet).  Otherwise the dest stays UNKNOWN (base_unresolved
            # survives for any later use) — conservative.
            if kind[0] == 'LITERAL' and m.get('idx') is None:
                eff = (kind[1] + m.get('disp', 0)) & gcl.MASK
                if m['dir'] == 'load' and m.get('dest') is not None:
                    v = ops.lit_load_value(rom, eff, m['size'], m.get('sext', False),
                                           ram_known if not branches_seen else None)
                    trk['r%d' % m['dest']] = ('lit', v) if v is not None else None
                elif m['dir'] == 'store' and m.get('src') is not None:
                    sv = _trk_fold(trk, written, m['src'])
                    ops.lit_store_bytes(ram_known, eff, m['size'],
                                        sv[1] if sv and sv[0] == 'lit' else None)
            if m['dir'] == 'load' and m.get('dest') is not None:
                trk.setdefault('r%d' % m['dest'], None)
            if m.get('auto') in ('post', 'pre'):
                trk['r%d' % m['base_reg']] = None
            pc += 2
            continue
        g = gcl._decode_gbr(op)
        if g is not None:
            size, gdir, disp = g
            if gbr_value is None:
                # GBR never set in-span (caller sets it): runtime input base.
                # The address is `gbr + r0 + disp` with BOTH live at runtime, so
                # neither GBR nor r0 needs to be a literal — the only requirement
                # is that the mirror and the emulator track r0 identically, which
                # the mapper fragments do.
                gbr_value = 'input'
            if gbr_value == 'input':
                bases.setdefault('gbr', ('PARAM', None))
                ops_list.append({'pc': pc, 'size': size, 'dir': gdir,
                                 'kind': 'gbr', 'base_reg': None, 'disp': disp,
                                 'auto': None, 'idx': None, 'gbr': True,
                                 'gbr_input': True})
                gcl._apply_mem_writes({'dir': gdir,
                                       'dest': 0 if gdir == 'load' else None,
                                       'src': 0 if gdir == 'store' else None},
                                      written, lits)
                if gdir == 'load':
                    trk['r0'] = None
                pc += 2
                continue
            if 'r0' not in lits:
                r0 = _trk_fold(trk, written, 0)
                if not r0 or r0[0] != 'lit':
                    return None, ('base_unresolved', 'r0-non-literal')
                lits['r0'] = r0[1]
            abs_addr = (gbr_value + lits['r0'] + disp) & gcl.MASK
            bases.setdefault('gbr', ('LITERAL', abs_addr))
            if abs_addr not in lit_vals:
                lit_vals.append(abs_addr)
            gm = {'dir': gdir, 'dest': 0 if gdir == 'load' else None,
                  'src': 0 if gdir == 'store' else None}
            ops_list.append({'pc': pc, 'size': size, 'dir': gdir, 'kind': 'gbr',
                             'base_reg': None, 'disp': disp, 'auto': None,
                             'idx': None, 'gbr': True})
            gcl._apply_mem_writes(gm, written, lits)
            if gdir == 'load':
                trk['r0'] = None
            pc += 2
            continue
        gb = ops.decode_gbr_bit(op, pc, rom, None)
        if gb is not None:
            if gbr_value is None:
                gbr_value = 'input'
            if gbr_value == 'input':
                bases.setdefault('gbr', ('PARAM', None))
                ops_list.append({'pc': pc, 'size': 1,
                                 'dir': 'load' if gb['dir'] == 'load' else 'store',
                                 'kind': 'gbr_bit', 'base_reg': None, 'disp': 0,
                                 'auto': None, 'idx': None, 'gbr': True,
                                 'gbr_input': True,
                                 'family': gb['family'], 'imm': gb['imm']})
                pc += 2
                continue
            if 'r0' not in lits:
                return None, ('base_unresolved', 'r0-non-literal')
            abs_addr = (gbr_value + lits['r0']) & gcl.MASK
            bases.setdefault('gbr', ('LITERAL', abs_addr))
            if abs_addr not in lit_vals:
                lit_vals.append(abs_addr)
            ops_list.append({'pc': pc, 'size': 1,
                             'dir': 'load' if gb['dir'] == 'load' else 'store',
                             'kind': 'gbr_bit', 'base_reg': None, 'disp': 0,
                             'auto': None, 'idx': None, 'gbr': True,
                             'family': gb['family'], 'imm': gb['imm']})
            pc += 2
            continue
        sh = gcl._mem_shape(op)
        if sh is not None and sh['base'] in (14, 15):
            breg = sh['base']
            if sh['idx'] is not None:
                return None, ('base_unresolved', 'altro')
            if breg == 15:
                if not stack_ok or sh['dest'] == 15:
                    return None, ('base_unresolved', 'r15-non-tracked')
            else:
                if not frame_live or sh['dest'] == 14:
                    return None, ('base_unresolved', 'r14-non-frame')
            bases.setdefault('r%d' % breg, ('STACK', None))
            sm = {'dir': sh['dir'], 'size': sh['size'], 'base_reg': breg,
                  'auto': sh.get('auto'), 'dest': sh.get('dest'), 'src': sh.get('src')}
            ops_list.append({'pc': pc, 'size': sh['size'], 'dir': sh['dir'],
                             'kind': 'stack', 'base_reg': breg, 'disp': sh.get('disp', 0),
                             'auto': sh.get('auto'), 'idx': sh.get('idx'), 'gbr': False})
            gcl._apply_mem_writes(sm, written, lits)
            if sh['dir'] == 'load' and sh.get('dest') is not None:
                trk['r%d' % sh['dest']] = None
            if sh.get('auto') in ('post', 'pre'):
                trk['r%d' % breg] = None
            pc += 2
            continue
        if op & 0xF0FF in (0x4002, 0x4012, 0x4022, 0x4006, 0x4016, 0x4026):
            # ---- sts.l/lds.l mach/macl/pr @-Rn/@Rn+ (sys_src/sys_dest) ----
            # decode_mem maps the param/literal-base forms above (mem path); the
            # r15/r14 stack-base forms fall through _resolve_base -> None, so
            # they previously died at the is_fpu_op fallback as 'fpu/altre'.
            # Admit them here with the SAME r15/r14 stack-slot rule as the
            # generic r15/r14 mem ops (stack_ok / frame_live gates identical).
            sys_store = (op & 0xF) == 0x2    # low nibble: 2 = sts.l, 6 = lds.l
            srn = (op >> 8) & 0xF
            if srn == 15:
                if not stack_ok:
                    return None, ('base_unresolved', 'r15-non-tracked')
                bases.setdefault('r15', ('STACK', None))
            elif srn == 14:
                if not frame_live:
                    return None, ('base_unresolved', 'r14-non-frame')
                bases.setdefault('r14', ('STACK', None))
            else:
                # param/literal/tracked base — decode_mem already returned None
                # (should not reach here; decode_mem covers these), so reject
                # rather than silently accept an unrendered form.
                return None, ('base_unresolved', 'altro')
            ops_list.append({'pc': pc, 'size': 4,
                             'dir': 'store' if sys_store else 'load',
                             'kind': 'sys_stack', 'base_reg': srn,
                             'disp': -4 if sys_store else 0,
                             'auto': 'pre' if sys_store else 'post',
                             'idx': None, 'gbr': False,
                             'sys_reg': 'pr' if (op & 0xF0FF) == 0x4022 else
                                        ('macl' if (op & 0xF0FF) == 0x4012 else
                                         ('mach' if (op & 0xF0FF) == 0x4002 else
                                          ('pr' if (op & 0xF0FF) == 0x4026 else
                                           ('macl' if (op & 0xF0FF) == 0x4016 else 'mach'))))})
            trk['r%d' % srn] = None
            pc += 2
            continue
        if gcl.is_mem_opcode(op):
            return None, ('base_unresolved', 'altro')
        if gcl.is_fpu_op(op):
            return None, 'fpu/altre'
        return None, 'unmapped'

    if not ops_list:
        return None, 'no_mem_op'
    return ({'name': c['name'], 'addr': addr, 'size': end - addr,
             'bases': bases, 'ops': ops_list, 'literal_values': lit_vals,
             'branches': brs}, None)


# ---------------------------------------------------------------------------
def select_v3(cats, max_n, seed, rom, catalog, outdir, root=ROOT, end_bounds=None):
    """Returns (selected, counters) — see gen_c_lift.select_mem; extra counter
    'skipped_no_branch' for functions that pass the mem scan but have no
    admitted internal branch.  v4: spans are sanitized (sanitize_span) and the
    sanitized end is returned on each entry; sanitize breakdown counters
    (n_trimmed/n_extended/n_entrambi) track the pool composition."""
    counters = {'selected': 0, 'rejected': Counter(),
                'motivo_dettaglio': Counter(),
                'skipped_no_span': 0, 'skipped_size': 0, 'skipped_dedup': 0,
                'skipped_no_branch': 0, 'by_category': {},
                'n_trimmed': 0, 'n_extended': 0, 'n_entrambi': 0,
                # v5: no-span end-estimation pool members (additive)
                'pool_no_span': 0,
                # ---- additive dryrun counters (never affect selection) ----
                'fuori_vicini_8': 0, 'fuori_vicini_16': 0,   # A: span-end
                'chain_resolvable': 0,                       # B: copy-chain
                'unmapped_opcodes': Counter(),               # C: unmapped list
                '_fuori8_addrs': set()}   # addrs of the A<=8 candidates (v4 hook)
    branch_stats = {'branch_tot': 0,
                    'branch_ammessi': Counter(),
                    'branch_rigettati': Counter()}
    pool = []
    for c in cats:
        cat = c['category']
        catstat = counters['by_category'].setdefault(cat, {'selected': 0, 'rejected': 0})
        end = catalog.get(c['addr'])
        estimated_end = None
        if end is None:
            # v5: no known end -> estimate next known catalog addr > addr.
            if end_bounds is not None:
                end = _next_addr(c['addr'], end_bounds)
                estimated_end = end
            if end is None:
                counters['skipped_no_span'] += 1
                continue
        # v4: sanitized span — addr_s == addr; size/scan/emission use end_s.
        _addr_s, end_s, reasons = sanitize_span(c['addr'], end, rom)
        size = end_s - c['addr']
        if not (gcl.MEM_MIN <= size <= gcl.MEM_MAX + 16):
            counters['skipped_size'] += 1
            continue
        # dedup: skip if c/<name>_<addr>.c exists, a v1/v2 test exists, or any
        # c/*_<addr>.c already lifted the address.
        base = gcl.sanitize(c['name'])
        out_c = os.path.join(outdir, '%s_%x.c' % (base, c['addr']))
        out_t = os.path.join(root, 'c', 'tests', 'test_%s_%x.py' % (base, c['addr']))
        if os.path.exists(out_c) or os.path.exists(out_t) or \
                glob.glob(os.path.join(outdir, '*_%x.c' % c['addr'])):
            counters['skipped_dedup'] += 1
            continue
        entry, reason = _scan_mem_v3(rom, c, end_s, branch_stats)
        if entry is None:
            if isinstance(reason, tuple):
                r, det = reason
                if r == 'branch_v3':                # v3 per-motivo branch reject
                    r = gcl._BRANCH_V3_REASON.get(det, 'branch')
                    counters['rejected'][r] += 1
                else:
                    counters['rejected'][r] += 1
                    counters['motivo_dettaglio'][det] += 1
            else:
                r = reason
                counters['rejected'][reason] += 1
            catstat['rejected'] += 1
            # ---- additive dryrun-only counters (do NOT change selection) ----
            # analyze the SAME span the scan rejected on (end_s == sanitized).
            _accum_additive(counters, rom, c, end_s, r)
            continue
        if not entry['branches']:                   # v3 = branch lifts only
            counters['skipped_no_branch'] += 1
            catstat['rejected'] += 1
            continue
        entry['end_s'] = end_s                      # sanitized end for emission
        if estimated_end is not None:               # v5: no-span (next_addr)
            entry['estimated_end'] = estimated_end
            counters['pool_no_span'] += 1
        trimmed = 'trimmed_padding' in reasons
        extended = 'extended_end' in reasons
        if trimmed and extended:
            counters['n_entrambi'] += 1
        elif trimmed:
            counters['n_trimmed'] += 1
        elif extended:
            counters['n_extended'] += 1
        pool.append(entry)
        counters['selected'] += 1
        catstat['selected'] += 1

    pool.sort(key=lambda x: x['size'])              # stable, deterministic
    counters['branch_tot'] = branch_stats['branch_tot']
    counters['branch_ammessi'] = branch_stats['branch_ammessi']
    counters['branch_rigettati'] = branch_stats['branch_rigettati']
    if max_n is not None and max_n < len(pool):
        pool = random.Random(seed).sample(pool, max_n)
    return pool, counters


# ---------------------------------------------------------------------------
# v4 additive: SANITIZED-SPAN selection (dryrun measurement only; never touches
# the v3 pool/counters and never emission).  sanitize_span trims trailing
# 0x0000/0xFFFF padding from the catalog end and extends the end into near
# branch targets; select_v4_sanitized re-runs the v3 criteria on the sanitized
# span (only the size gate is adapted: 8 <= end_s-addr <= 160+16).
# ---------------------------------------------------------------------------
_PAD_WORDS = (0x0000, 0xFFFF)


def sanitize_span(addr, end, rom_bytes):
    """Return (addr_s, end_s, reasons) for the sanitized span of [addr, end).

    reasons is a list of 'trimmed_padding' | 'extended_end' markers (additive).
    a) TRIM: trailing 16-bit big-endian words of value 0x0000/0xFFFF are
       dropped from the END (end_s stops at the first non-padding word, or at
       addr+4 — the span never shrinks below 4 bytes).
    b) EXTEND: branch targets (P+4+disp*2 for bt/bf/bt.s/bf.s/bra) of
       instructions INSIDE the scan that fall in [end_s, end_s+16] and whose
       target word is not 0x0000/0xFFFF pull the end out to max(target)+4;
       iterated to fixed point (max 2 rounds).
    c) GUARD: if the resulting end_s - addr is < 4 or > 200, the ORIGINAL
       (addr, end) is returned untouched with no reasons (no sanitization).
    addr_s == addr always (only the end is sanitized).
    """
    n = len(rom_bytes)
    addr_s = addr
    end_s = end
    # (a) trim trailing padding words (big-endian)
    while end_s - 2 >= addr + 4 and end_s <= n:
        w = (rom_bytes[end_s - 2] << 8) | rom_bytes[end_s - 1]
        if w not in _PAD_WORDS:
            break
        end_s -= 2
    reasons = []
    if end_s < end:
        reasons.append('trimmed_padding')
    # (b) extend into near branch targets (fixed point, max 2 rounds)
    for _ in range(2):
        best = end_s
        bound = min(end_s, n)
        pc = addr
        while pc + 1 < bound:
            op = (rom_bytes[pc] << 8) | rom_bytes[pc + 1]
            bi = ops.branch_info(op)
            if bi is not None and bi.get('target_disp') is not None:
                t = (pc + 4 + bi['target_disp'] * 2) & gcl.MASK
                if end_s <= t <= end_s + 16 and t + 2 <= n:
                    tw = (rom_bytes[t] << 8) | rom_bytes[t + 1]
                    if tw not in _PAD_WORDS:     # never extend into padding
                        best = max(best, t + 4)
            pc += 2
        if best == end_s:
            break
        end_s = best
    if end_s > end:
        reasons.append('extended_end')
    # (c) bounds guard: out-of-range spans are left unsanitized
    if end_s - addr < 4 or end_s - addr > 200:
        return addr, end, []
    return addr_s, end_s, reasons


def _span_out_targets(rom, addr, end):
    """All (pc, target) of bt/bf/bt.s/bf.s/bra in [addr, min(end,len(rom)))
    whose target lies OUTSIDE [addr, end).  Mirrors _analyze_rejected's
    counter-A collection (ops.branch_info, target = P+4+disp*2)."""
    outs = []
    bound = min(end, len(rom))
    pc = addr
    while pc + 1 < bound:
        op = (rom[pc] << 8) | rom[pc + 1]
        bi = ops.branch_info(op)
        if bi is not None and bi.get('target_disp') is not None:
            t = (pc + 4 + bi['target_disp'] * 2) & gcl.MASK
            if not (addr <= t < end):
                outs.append((pc, t))
        pc += 2
    return outs


def select_v4_sanitized(cats, rom, catalog, outdir, root=ROOT, v3_pool=None):
    """Additive dryrun-only sanitized-span selection -> (pool_v4, v4_counters).

    Re-runs the v3 criteria on the sanitized span (addr_s, end_s):
      - size gate 8 <= end_s-addr <= 160+16 (the sanitized span MAY exceed the
        old 160 cap; the count of pool members that do is reported);
      - _scan_mem_function on [addr, end_s) -> branch targets must still lie in
        [addr_s, end_s);
      - same dedup as v3.
    The v3 pool / counters / emission are untouched.
    """
    v3_addrs = {e['addr'] for e in (v3_pool or [])}
    counters = {
        'pool_v4': 0,
        'rejected': Counter(),
        'skipped_size': 0, 'skipped_dedup': 0, 'skipped_no_branch': 0,
        'n_trimmed': 0, 'n_extended': 0, 'n_entrambi': 0,
        'n_over_160': 0,
        'fuori8_now': 0, 'fuori8_total': 0,
        'examples': [],     # (addr, name, end_orig, end_san, reasons, in_v3)
    }
    pool = []
    for c in cats:
        addr = c['addr']
        end = catalog.get(c['addr'])
        if end is None:
            continue
        # classify the ORIGINAL span as a v3-A fuori_vicini_8 candidate
        outs = _span_out_targets(rom, addr, end)
        is_fuori8 = bool(outs) and all(end <= t <= end + 8 for _, t in outs)
        if is_fuori8:
            counters['fuori8_total'] += 1
        addr_s, end_s, reasons = sanitize_span(addr, end, rom)
        if not (gcl.MEM_MIN <= end_s - addr <= gcl.MEM_MAX + 16):
            counters['skipped_size'] += 1
            continue
        # dedup mirrors v3
        base = gcl.sanitize(c['name'])
        out_c = os.path.join(outdir, '%s_%x.c' % (base, addr))
        out_t = os.path.join(root, 'c', 'tests', 'test_%s_%x.py' % (base, addr))
        if os.path.exists(out_c) or os.path.exists(out_t) or \
                glob.glob(os.path.join(outdir, '*_%x.c' % addr)):
            counters['skipped_dedup'] += 1
            continue
        entry, reason = _scan_mem_v3(rom, c, end_s, None)
        if entry is None:
            if isinstance(reason, tuple):
                r, det = reason
                if r == 'branch_v3':       # v3 per-motivo branch reject
                    r = gcl._BRANCH_V3_REASON.get(det, 'branch')
                # else: r stays 'base_unresolved' (mirror select_v3)
            else:
                r = reason
            counters['rejected'][r] += 1
            continue
        if not entry['branches']:
            counters['skipped_no_branch'] += 1
            continue
        trimmed = 'trimmed_padding' in reasons
        extended = 'extended_end' in reasons
        if trimmed and extended:
            counters['n_entrambi'] += 1
        elif trimmed:
            counters['n_trimmed'] += 1
        elif extended:
            counters['n_extended'] += 1
        if end_s - addr > gcl.MEM_MAX:
            counters['n_over_160'] += 1
        if is_fuori8:
            counters['fuori8_now'] += 1
        if (trimmed or extended) and len(counters['examples']) < 5:
            counters['examples'].append(
                (addr, c['name'], end, end_s, list(reasons), addr in v3_addrs))
        pool.append(entry)
        counters['pool_v4'] += 1
    pool.sort(key=lambda x: x['size'])
    return pool, counters


# ---------------------------------------------------------------------------
# FPU-aware selection (dryrun-only feasibility measurement).  pool_fpu counts
# the functions that would pass ALL the existing v3/v4 selection criteria
# (sanitized span, size gate, dedup, call/branch/base/stack rules, unmapped =
# reject) IF the FPU opcodes that c_lift_ops.decode_fpu now maps were allowed.
# It NEVER changes the real selection: _scan_mem_function / the v3/v4 pools and
# counters are untouched — a function with any FPU op is still rejected by the
# real pipeline (fpu/altre) until FPU emission lands.  The FPU-using functions
# are further broken down by whether they ALSO trip up on a call, an unresolved
# base, or nothing else (fpu_only).
# ---------------------------------------------------------------------------
def _scan_fpu_function(rom, c, end, branch_stats=None):
    """Mirror of gcl._scan_mem_function whose only difference is that an FPU
    opcode decode_fpu() maps is treated as an admitted statement (instead of
    rejecting the function with 'fpu/altre').  Everything else — decision
    order, call/branch/GBR/stack/base rules, and the final 'no_mem_op' gate —
    is identical, so the counter is a faithful "what if FPU were allowed"."
    """
    addr = c['addr']
    bound = min(end, len(rom))
    written = set()
    lits = {}
    trk = {}
    tmp = [0]
    gbr_known = False
    gbr_value = None
    stack_ok = True
    frame_live = False
    # v7: known-store RAM model + path gate for literal-base LOAD propagation
    # (identical to _scan_mem_v3).
    ram_known = {}
    branches_seen = False

    def temp():
        tmp[0] += 1
        return 't%d' % tmp[0]

    def resolve(reg):
        v = lits.get('r%d' % reg)
        if v is None:
            r = _trk_fold(trk, written, reg)
            if r and r[0] == 'lit':
                v = r[1]
            else:
                return None
        cls = ops.classify_addr(v)
        if cls in ('RAM', 'ROM'):
            return (cls, v)
        return None

    ctx = {'temp': temp, 'resolve': resolve}
    bases = {}
    ops_list = []
    lit_vals = []
    brs = []
    pool_words = gcl._pcrel_pool_words(rom, addr, end)
    pc = addr
    while pc + 1 < bound:
        if pc in pool_words:              # literal-pool data — not an instruction
            pc += 2
            continue
        op = (rom[pc] << 8) | rom[pc + 1]
        d = ops.translate(op, pc, rom)
        if d is not None:
            if d.get('kind') in ('branch', 'ret'):
                target = d.get('target')
                admit, det = gcl._v3_branch_rule(rom, op, target, pc, addr, end)
                gcl._count_branch(branch_stats, det)
                if admit:
                    brs.append((det, pc, target))
                    branches_seen = True
                    pc += 2
                    continue
                return None, ('branch_v3', det)
            writes = gcl._stmt_writes('\n'.join(d.get('c') or []))
            if op == 0x6EF3:
                if 'r14' not in written:
                    frame_live = True
            else:
                if 'r15' in writes:
                    if not (op & 0xF000 == 0x7000 and ((op >> 8) & 0xF) == 15):
                        stack_ok = False
                if 'r14' in writes:
                    frame_live = False
                _trk_apply_stmt(trk, op, rom, pc)
            if not gcl._apply_stmt(rom, pc, op, d, written, lits):
                return None, 'unmapped'
            pc += 2
            continue
        if op & 0xF0FF == 0x401E:
            gbr_known = True
            _lit = _lit_of((op >> 8) & 0xF, lits, trk, written)
            gbr_value = _lit if _lit is not None else 'input'
            pc += 2
            continue
        if op & 0xF0FF == 0x4017:            # lds.l @Rm+,GBR (GBR = RAM[Rm])
            gbr_known = True
            _lit = _lit_of((op >> 8) & 0xF, lits, trk, written)
            if _lit is not None and _lit < len(rom) and ops.classify_addr(_lit) == 'ROM':
                gbr_value = (rom[_lit] << 24 | rom[_lit + 1] << 16
                             | rom[_lit + 2] << 8 | rom[_lit + 3])
            else:
                gbr_value = 'input'
            pc += 2
            continue
        if gcl.is_call_op(op):
            return None, 'call'
        if op == 0x002B:
            return None, 'rte'
        if gcl.is_branch_op(op):
            return None, 'branch'
        m = ops.decode_mem(op, None, ctx)
        if m is not None:
            base_reg = m['base_reg']
            if m.get('idx') == 'r0' and 'r0' not in lits:
                if not _trk_fold(trk, written, 0):
                    return None, ('base_unresolved', 'altro')
            if base_reg in (4, 5, 6, 7) and 'r%d' % base_reg not in written:
                kind = ('PARAM', None)
                bkind = 'param'
            elif 'r%d' % base_reg in lits:
                kind = ('LITERAL', lits['r%d' % base_reg])
                bkind = 'literal'
            else:
                r = _trk_fold(trk, written, base_reg)
                if not r:
                    return None, ('base_unresolved', 'altro')
                if r[0] == 'lit':
                    kind = ('LITERAL', r[1]); bkind = 'literal'
                else:
                    kind = ('PARAM', None); bkind = 'param'
            bases.setdefault('r%d' % base_reg, kind)
            if kind[0] == 'LITERAL' and kind[1] not in lit_vals:
                lit_vals.append(kind[1])
            ops_list.append({'pc': pc, 'size': m['size'], 'dir': m['dir'],
                             'kind': bkind, 'base_reg': base_reg,
                             'disp': m.get('disp', 0), 'auto': m.get('auto'),
                             'idx': m.get('idx'), 'gbr': False})
            gcl._apply_mem_writes(m, written, lits)
            # v7: literal-base LOAD propagation (identical to _scan_mem_v3).
            if kind[0] == 'LITERAL' and m.get('idx') is None:
                eff = (kind[1] + m.get('disp', 0)) & gcl.MASK
                if m['dir'] == 'load' and m.get('dest') is not None:
                    v = ops.lit_load_value(rom, eff, m['size'], m.get('sext', False),
                                           ram_known if not branches_seen else None)
                    trk['r%d' % m['dest']] = ('lit', v) if v is not None else None
                elif m['dir'] == 'store' and m.get('src') is not None:
                    sv = _trk_fold(trk, written, m['src'])
                    ops.lit_store_bytes(ram_known, eff, m['size'],
                                        sv[1] if sv and sv[0] == 'lit' else None)
            if m['dir'] == 'load' and m.get('dest') is not None:
                trk.setdefault('r%d' % m['dest'], None)
            if m.get('auto') in ('post', 'pre'):
                trk['r%d' % m['base_reg']] = None
            pc += 2
            continue
        g = gcl._decode_gbr(op)
        if g is not None:
            size, gdir, disp = g
            if gbr_value is None:
                # GBR never set in-span (caller sets it): runtime input base.
                gbr_value = 'input'
            if gbr_value == 'input':
                bases.setdefault('gbr', ('PARAM', None))
                ops_list.append({'pc': pc, 'size': size, 'dir': gdir,
                                 'kind': 'gbr', 'base_reg': None, 'disp': disp,
                                 'auto': None, 'idx': None, 'gbr': True,
                                 'gbr_input': True})
                gcl._apply_mem_writes({'dir': gdir,
                                       'dest': 0 if gdir == 'load' else None,
                                       'src': 0 if gdir == 'store' else None},
                                      written, lits)
                if gdir == 'load':
                    trk['r0'] = None
                pc += 2
                continue
            if 'r0' not in lits:
                r0 = _trk_fold(trk, written, 0)
                if not r0 or r0[0] != 'lit':
                    return None, ('base_unresolved', 'r0-non-literal')
                lits['r0'] = r0[1]
            abs_addr = (gbr_value + lits['r0'] + disp) & gcl.MASK
            bases.setdefault('gbr', ('LITERAL', abs_addr))
            if abs_addr not in lit_vals:
                lit_vals.append(abs_addr)
            gm = {'dir': gdir, 'dest': 0 if gdir == 'load' else None,
                  'src': 0 if gdir == 'store' else None}
            ops_list.append({'pc': pc, 'size': size, 'dir': gdir, 'kind': 'gbr',
                             'base_reg': None, 'disp': disp, 'auto': None,
                             'idx': None, 'gbr': True})
            gcl._apply_mem_writes(gm, written, lits)
            if gdir == 'load':
                trk['r0'] = None
            pc += 2
            continue
        # ---- v6: GBR byte bit-ops (0xCC-CF) — same contract as the 0xC0-C6
        # movs (GBR + R0 both constants); tst.b sets T only, and/xor/or RMW
        # the byte (no rN side effects). ----
        gb = ops.decode_gbr_bit(op, pc, rom, None)
        if gb is not None:
            if gbr_value is None:
                gbr_value = 'input'
            if gbr_value == 'input':
                bases.setdefault('gbr', ('PARAM', None))
                ops_list.append({'pc': pc, 'size': 1,
                                 'dir': 'load' if gb['dir'] == 'load' else 'store',
                                 'kind': 'gbr_bit', 'base_reg': None, 'disp': 0,
                                 'auto': None, 'idx': None, 'gbr': True,
                                 'gbr_input': True,
                                 'family': gb['family'], 'imm': gb['imm']})
                pc += 2
                continue
            if 'r0' not in lits:
                return None, ('base_unresolved', 'r0-non-literal')
            abs_addr = (gbr_value + lits['r0']) & gcl.MASK
            bases.setdefault('gbr', ('LITERAL', abs_addr))
            if abs_addr not in lit_vals:
                lit_vals.append(abs_addr)
            ops_list.append({'pc': pc, 'size': 1,
                             'dir': 'load' if gb['dir'] == 'load' else 'store',
                             'kind': 'gbr_bit', 'base_reg': None, 'disp': 0,
                             'auto': None, 'idx': None, 'gbr': True,
                             'family': gb['family'], 'imm': gb['imm']})
            pc += 2
            continue
        sh = gcl._mem_shape(op)
        if sh is not None and sh['base'] in (14, 15):
            breg = sh['base']
            if sh['idx'] is not None:
                return None, ('base_unresolved', 'altro')
            if breg == 15:
                if not stack_ok or sh['dest'] == 15:
                    return None, ('base_unresolved', 'r15-non-tracked')
            else:
                if not frame_live or sh['dest'] == 14:
                    return None, ('base_unresolved', 'r14-non-frame')
            bases.setdefault('r%d' % breg, ('STACK', None))
            sm = {'dir': sh['dir'], 'size': sh['size'], 'base_reg': breg,
                  'auto': sh['auto'], 'dest': sh.get('dest'), 'src': sh.get('src')}
            ops_list.append({'pc': pc, 'size': sh['size'], 'dir': sh['dir'],
                             'kind': 'stack', 'base_reg': breg, 'disp': sh['disp'],
                             'auto': sh['auto'], 'idx': sh.get('idx'), 'gbr': False})
            gcl._apply_mem_writes(sm, written, lits)
            pc += 2
            continue
        if op & 0xF0FF in (0x4002, 0x4012, 0x4022, 0x4006, 0x4016, 0x4026):
            # ---- sts.l/lds.l mach/macl/pr @-Rn/@Rn+ (sys_src/sys_dest) ----
            # identical to _scan_mem_v3: admit the r15/r14 stack-base forms with
            # the same stack_ok / frame_live gates (param/literal bases are
            # already admitted by decode_mem in the mem path above).
            sys_store = (op & 0xF) == 0x2    # low nibble: 2 = sts.l, 6 = lds.l
            srn = (op >> 8) & 0xF
            if srn == 15:
                if not stack_ok:
                    return None, ('base_unresolved', 'r15-non-tracked')
                bases.setdefault('r15', ('STACK', None))
            elif srn == 14:
                if not frame_live:
                    return None, ('base_unresolved', 'r14-non-frame')
                bases.setdefault('r14', ('STACK', None))
            else:
                return None, ('base_unresolved', 'altro')
            ops_list.append({'pc': pc, 'size': 4,
                             'dir': 'store' if sys_store else 'load',
                             'kind': 'sys_stack', 'base_reg': srn,
                             'disp': -4 if sys_store else 0,
                             'auto': 'pre' if sys_store else 'post',
                             'idx': None, 'gbr': False,
                             'sys_reg': 'pr' if (op & 0xF0FF) in (0x4022, 0x4026)
                             else ('macl' if (op & 0xF0FF) in (0x4012, 0x4016)
                                   else 'mach')})
            trk['r%d' % srn] = None
            pc += 2
            continue
        if gcl.is_mem_opcode(op):
            return None, ('base_unresolved', 'altro')
        # ---- FPU (additive): decode_fpu maps it -> admitted; else fpu/altre ----
        f = ops.decode_fpu(op, pc, rom, ctx)
        if f is not None:
            if f.get('kind') == 'fpu_mem':
                if f.get('unresolved'):
                    return None, ('base_unresolved', 'altro')
                base_reg = f['base_reg']
                if f.get('idx') == 'r0' and 'r0' not in lits:
                    if not _trk_fold(trk, written, 0):
                        return None, ('base_unresolved', 'altro')
                if base_reg in (4, 5, 6, 7) and 'r%d' % base_reg not in written:
                    bkind = 'param'
                elif 'r%d' % base_reg in lits:
                    bkind = 'literal'
                else:
                    r = _trk_fold(trk, written, base_reg)
                    if not r:
                        return None, ('base_unresolved', 'altro')
                    if r[0] == 'lit':
                        bkind = 'literal'
                        lits.setdefault('r%d' % base_reg, r[1])
                    else:
                        bkind = 'param'
                bases.setdefault('r%d' % base_reg, ('LITERAL', lits['r%d' % base_reg])
                                 if bkind == 'literal' else ('PARAM', None))
                ops_list.append({'pc': pc, 'size': 4, 'dir': f['dir'],
                                 'kind': 'fpu_mem', 'base_reg': base_reg,
                                 'disp': 0, 'auto': f.get('auto'),
                                 'idx': f.get('idx'), 'gbr': False})
                if f.get('auto') in ('post', 'pre'):
                    reg = 'r%d' % base_reg
                    written.add(reg)
                    lits.pop(reg, None)
                    trk[reg] = None
                elif f.get('dir') == 'load' and f.get('dest') is not None:
                    trk['r%d' % f['dest']] = None
            else:                       # pure fpu op: track any integer-RN write
                # (fmul/fadd/etc write frN only; sts fpul,Rn / fcmp set rN / T)
                for reg in gcl._stmt_writes('\n'.join(f.get('c') or [])):
                    written.add(reg)
                    lits.pop(reg, None)
                    trk[reg] = None
            pc += 2
            continue
        if ops.is_fpu_op(op):
            return None, 'fpu/altre'
        return None, 'unmapped'

    if not ops_list:
        return None, 'no_mem_op'
    return ({'name': c['name'], 'addr': addr, 'size': end - addr,
             'bases': bases, 'ops': ops_list, 'literal_values': lit_vals,
             'branches': brs}, None)


def select_fpu(cats, rom, catalog, outdir, root=ROOT, max_n=None, seed=0,
               rescue_trailing_rts=True, end_bounds=None):
    """pool_fpu selection (v4: now the REAL selector when emission lands — FPU
    opcodes decode_fpu() maps are admitted; every other criterion is identical
    to select_v3/select_v4_sanitized: sanitized span, size gate, dedup,
    call/branch/GBR/stack/base rules, unmapped = reject).  Returns
    (pool_fpu, counters).  counters carries the fpu breakdown:
      pool_fpu      : functions passing every existing v4 criterion WITH the
                      mapped FPU ops admitted (superset of the v4 pool).
      fpu_used      : span/size/dedup-passing candidates whose span holds any
                      FPU op (decode_fpu-able or recognizably FPU).
      fpu_only      : the fpu_used subset that passes cleanly (in pool_fpu).
      fpu_calls     : fpu_used subsets tripping over a call (reject reason).
      fpu_bases     : ... over an unresolved base (base_unresolved reason).
      fpu_other     : ... over another reject (rte, unmapped FPU, no_mem_op,
                      delay_slot_ctrl, target_fuori, branch).
      fpu_no_branch : admitted span but zero internal branches (skipped).
      rescued_trailing_rts: candidates REJECTED on the sanitized span that were
                      recovered by (A) TRAILING-RTS: an rts (0x000B) at an even
                      offset in [end, end+16] marks the true function end, and
                      the FULL gate sequence passes on the span extended through
                      that rts and its delay slot.  Rescue-only + fallback: the
                      extension is attempted only after a sanitized-span reject
                      and a failed extended attempt keeps the original
                      rejection — the existing pool never regresses.  Rescued
                      entries carry entry['rescued_trailing_rts'] = True.
    Every accepted entry carries the sanitized end (entry['end_s'] = end_s) so
    the emission path decodes exactly the sanitized span.  max_n/seed sampling
    matches select_v3 (sorted by size, then random.Random(seed).sample)."""
    counters = {'pool_fpu': 0,
                'fpu_used': 0, 'fpu_only': 0, 'fpu_calls': 0,
                'fpu_bases': 0, 'fpu_other': 0, 'fpu_no_branch': 0,
                'rescued_trailing_rts': 0,
                'rejected': Counter(),
                'skipped_size': 0, 'skipped_dedup': 0, 'skipped_no_branch': 0,
                'n_over_160': 0, 'n_trimmed': 0, 'n_extended': 0,
                'n_entrambi': 0, 'examples': [],
                # v5: no-span end-estimation pool members (additive)
                'pool_no_span': 0}
    pool = []
    for c in cats:
        addr = c['addr']
        end = catalog.get(c['addr'])
        estimated_end = None
        if end is None:
            # v5: no known end -> estimate next known catalog addr > addr.
            if end_bounds is not None:
                end = _next_addr(c['addr'], end_bounds)
                estimated_end = end
            if end is None:
                continue

        def _gate(end_cand):
            """Full pool_fpu gate sequence on [addr, sanitize(end_cand)):
            sanitize + size + dedup + _scan_fpu_function + >=1-branch.
            Returns (entry, reason, end_s, reasons); entry None on reject and
            `reason` is the exact rejection key the counters use
            ('skipped_size' / 'skipped_dedup' / 'skipped_no_branch' / the scan
            reason string-or-tuple)."""
            _a, _e, _r = sanitize_span(addr, end_cand, rom)
            if not (gcl.MEM_MIN <= _e - addr <= gcl.MEM_MAX + 16):
                return None, 'skipped_size', _e, _r
            _base = gcl.sanitize(c['name'])
            if os.path.exists(os.path.join(outdir, '%s_%x.c' % (_base, addr))) \
                    or os.path.exists(os.path.join(root, 'c', 'tests',
                                                   'test_%s_%x.py' % (_base, addr))) \
                    or glob.glob(os.path.join(outdir, '*_%x.c' % addr)):
                return None, 'skipped_dedup', _e, _r
            _entry, _reason = _scan_fpu_function(rom, c, _e, None)
            if _entry is None:
                return None, _reason, _e, _r
            if not _entry['branches']:
                return None, 'skipped_no_branch', _e, _r
            _entry['end_s'] = _e
            if estimated_end is not None:      # v5: no-span (next_addr)
                _entry['estimated_end'] = estimated_end
            return _entry, None, _e, _r

        # ---- sanitized-span selection ----
        entry, reason, end_s, reasons = _gate(end)
        if entry is None and rescue_trailing_rts:
            # (A) TRAILING-RTS rescue: an rts (0x000B) at an even offset in
            # [end, end+16] marks the true function end (the catalog end sits
            # in padding/alignment after it).  Retry the FULL gate sequence on
            # the span extended through that rts AND its delay slot (rts is a
            # delayed return, so P+2 stays in-span).  Rescue-only + fallback:
            # only sanitized-span rejects are extended, and a failed extended
            # attempt keeps the original rejection — the pool never regresses.
            rts_addr = _find_trailing_rts(rom, end)
            if rts_addr is not None:
                entry2, _r2, end_s2, reasons2 = _gate(rts_addr + 4)
                if entry2 is not None:
                    entry, reason, end_s, reasons = entry2, None, end_s2, reasons2
                    entry['rescued_trailing_rts'] = True
                    counters['rescued_trailing_rts'] += 1
        # does the (final) span hold any FPU op?
        has_fpu = False
        pc = addr
        b = min(end_s, len(rom))
        pw = gcl._pcrel_pool_words(rom, addr, end_s)
        while pc + 1 < b:
            if pc in pw:                       # literal-pool data — not an opcode
                pc += 2
                continue
            op = (rom[pc] << 8) | rom[pc + 1]
            if ops.is_fpu_op(op) or ops.decode_fpu(op, pc, rom, None) is not None:
                has_fpu = True
                break
            pc += 2
        if has_fpu:
            counters['fpu_used'] += 1
        if entry is None:
            if reason == 'skipped_size':
                counters['skipped_size'] += 1
                continue
            if reason == 'skipped_dedup':
                counters['skipped_dedup'] += 1
                continue
            if reason == 'skipped_no_branch':
                counters['skipped_no_branch'] += 1
                if has_fpu:
                    counters['fpu_no_branch'] += 1
                continue
            if isinstance(reason, tuple):
                r, det = reason
                if r == 'branch_v3':
                    r = gcl._BRANCH_V3_REASON.get(det, 'branch')
            else:
                r = reason
            counters['rejected'][r] += 1
            if has_fpu:
                if r == 'call':
                    counters['fpu_calls'] += 1
                elif r == 'base_unresolved':
                    counters['fpu_bases'] += 1
                else:
                    counters['fpu_other'] += 1
            continue
        cnt = len(entry['branches'])
        if not cnt:
            counters['skipped_no_branch'] += 1
            if has_fpu:
                counters['fpu_no_branch'] += 1
            continue
        if end_s - addr > gcl.MEM_MAX:
            counters['n_over_160'] += 1
        trimmed = 'trimmed_padding' in reasons
        extended = 'extended_end' in reasons
        if trimmed and extended:
            counters['n_entrambi'] += 1
        elif trimmed:
            counters['n_trimmed'] += 1
        elif extended:
            counters['n_extended'] += 1
        entry['end_s'] = end_s            # sanitized end for emission
        if estimated_end is not None:     # v5: no-span (next_addr)
            counters['pool_no_span'] += 1
        pool.append(entry)
        counters['pool_fpu'] += 1
        if has_fpu:
            counters['fpu_only'] += 1
            if len(counters['examples']) < 5:
                counters['examples'].append((addr, c['name']))
    pool.sort(key=lambda x: x['size'])
    if max_n is not None and max_n < len(pool):
        pool = random.Random(seed).sample(pool, max_n)
    return pool, counters


# ---------------------------------------------------------------------------
# Additive dryrun-only feasibility counters (A/B/C).  They NEVER change the
# selection: they post-mortem spans that _scan_mem_function already rejected.
# The baseline pool / rejection numbers / branch breakdown are untouched.
# ---------------------------------------------------------------------------
def _analyze_rejected(rom, addr, end):
    """Re-walk a REJECTED span [addr,end) to feed the additive counters.

    Mirrors _scan_mem_function's instruction walk and decision order (same
    written/lits/gbr/stack/frame tracking) so the FIRST rejecting instruction
    matches the real scan — but continues to the end of the span (the real scan
    stops at the first reject) to collect:
      out_targets : [(pc,target)] for EVERY branch (bt/bf/bt.s/bf.s/bra) whose
                    target lies OUTSIDE [addr,end)            -> counter A
      unmapped    : Counter of every opcode ops.translate() leaves unmapped
                    across the whole span                     -> counter C
      reject      : (pc, reason, base_reg) at the first rejecting instruction.
                    base_reg is the integer register index a copy-chain fix
                    (counter B) would need to resolve to a literal, else None.
    It never mutates shared branch_stats and never touches selection.
    """
    bound = min(end, len(rom))
    written = set()
    lits = {}
    tmp = [0]
    gbr_known = False;  gbr_value = None
    stack_ok = True;  frame_live = False

    def temp():
        tmp[0] += 1
        return 't%d' % tmp[0]

    def resolve(reg):
        # identical to _scan_mem_function's: decode_mem's _resolve_base uses
        # this to accept literal-based (non-param) bases — stubbing it would
        # change decode_mem's output and shift the reject point.
        v = lits.get('r%d' % reg)
        if v is None:
            return None
        cls = ops.classify_addr(v)
        if cls in ('RAM', 'ROM'):
            return (cls, v)
        return None

    ctx = {'temp': temp, 'resolve': resolve}
    out_targets = []
    unmapped = Counter()
    reject = None
    pool_words = gcl._pcrel_pool_words(rom, addr, end)
    pc = addr
    while pc + 1 < bound:
        if pc in pool_words:              # literal-pool data — not an instruction
            pc += 2
            continue
        op = (rom[pc] << 8) | rom[pc + 1]
        d = ops.translate(op, pc, rom)
        if d is None:
            unmapped[op] += 1            # C: opcodes the mapper doesn't know
        if d is not None:
            if d.get('kind') in ('branch', 'ret'):
                if d.get('kind') == 'branch':
                    t = d.get('target')
                    if t is not None and not (addr <= t < end):
                        out_targets.append((pc, t))
                pc += 2
                continue
            writes = gcl._stmt_writes('\n'.join(d.get('c') or []))
            if op == 0x6EF3:             # mov r15,r14 -> frame pointer
                if 'r14' not in written:
                    frame_live = True
            else:
                if 'r15' in writes:
                    stack_ok = False
                if 'r14' in writes:
                    frame_live = False
            if not gcl._apply_stmt(rom, pc, op, d, written, lits):
                if reject is None:
                    reject = (pc, 'unmapped', None)
            pc += 2
            continue
        if op & 0xF0FF == 0x401E:        # ldc Rn,GBR
            gbr_known = True
            gbr_value = lits.get('r%d' % ((op >> 8) & 0xF))
            pc += 2
            continue
        if gcl.is_call_op(op):
            if reject is None:
                reject = (pc, 'call', None)
            pc += 2
            continue
        if op == 0x002B:                 # rte
            if reject is None:
                reject = (pc, 'rte', None)
            pc += 2
            continue
        if gcl.is_branch_op(op):
            if reject is None:
                reject = (pc, 'branch', None)
            pc += 2
            continue
        m = ops.decode_mem(op, None, ctx)
        if m is not None:
            base_reg = m['base_reg']
            if m.get('idx') == 'r0' and 'r0' not in lits:
                if reject is None:
                    reject = (pc, 'base_unresolved', 0)
            elif base_reg in (4, 5, 6, 7) and 'r%d' % base_reg not in written:
                pass                    # param base: accepted
            elif 'r%d' % base_reg in lits:
                pass                    # literal base: accepted
            else:
                if reject is None:
                    reject = (pc, 'base_unresolved', base_reg)
            gcl._apply_mem_writes(m, written, lits)
            pc += 2
            continue
        g = gcl._decode_gbr(op)
        if g is not None:
            if not gbr_known or gbr_value is None:
                if reject is None:
                    reject = (pc, 'base_unresolved', None)
            elif 'r0' not in lits:
                if reject is None:
                    reject = (pc, 'base_unresolved', 0)
            pc += 2
            continue
        sh = gcl._mem_shape(op)
        if sh is not None and sh['base'] in (14, 15):
            breg = sh['base']
            if sh['idx'] is not None:    # @(R0,r15/r14): unresolved index r0
                if reject is None:
                    reject = (pc, 'base_unresolved', 0)
            elif breg == 15:
                if not stack_ok or sh['dest'] == 15:
                    if reject is None:
                        reject = (pc, 'base_unresolved', 15)
            else:
                if not frame_live or sh['dest'] == 14:
                    if reject is None:
                        reject = (pc, 'base_unresolved', 14)
            sm = {'dir': sh['dir'], 'size': sh['size'], 'base_reg': breg,
                  'auto': sh['auto'], 'dest': sh.get('dest'), 'src': sh.get('src')}
            gcl._apply_mem_writes(sm, written, lits)
            pc += 2
            continue
        if gcl.is_mem_opcode(op):
            sh2 = gcl._mem_shape(op)
            base_reg = sh2['base'] if sh2 is not None else None
            if reject is None:
                reject = (pc, 'base_unresolved', base_reg)
            pc += 2
            continue
        if gcl.is_fpu_op(op):
            if reject is None:
                reject = (pc, 'fpu/altre', None)
            pc += 2
            continue
        if reject is None:               # fallthrough: truly unmapped
            reject = (pc, 'unmapped', None)
        pc += 2
    return out_targets, unmapped, reject


def _chain_resolvable(rom, addr, reject_pc, base_reg):
    """Counter B: is base_reg at reject_pc derivable, walking BACKWARD through
    the preceding span instructions, from a LITERAL origin using ONLY:
      - mov rA,rB          (0x6n3m: a direct copy)
      - mov #imm,Rn        (0xEnnn)
      - mov.w @(disp,PC),Rn(0x9nnn) / mov.l @(disp,PC),Rn (0xDnnn)
    There must be NO branch/call/return in the walk, and no instruction that
    REWRITES a chased register (arithmetic/memory/other) — the value has to
    propagate purely through copies.  translate() leaves some system/shift ops
    unmapped; for those we heuristically infer rN writes.  Anything fully
    unknown breaks the chain (cannot prove purity)."""
    if base_reg is None:
        return False
    live = [base_reg]
    p = reject_pc - 2
    while p + 2 > addr:
        op = (rom[p] << 8) | rom[p + 1]
        n = (op >> 8) & 0xF
        # a branch/call/return anywhere in the walk => linear order untrusted
        if ops.branch_info(op) is not None or gcl.is_call_op(op) \
                or gcl.is_branch_op(op):
            return False
        # literal loads: the chain origin
        if op & 0xF000 in (0xE000, 0x9000, 0xD000):
            if n in live:
                live.remove(n)
                if not live:
                    return True
            p -= 2
            continue
        # mov rA,rB copy: Rn <- Rm
        if op & 0xF000 == 0x6000 and (op & 0xF) == 0x3:
            if n in live:
                live.remove(n)
                live.append((op >> 4) & 0xF)
            p -= 2
            continue
        d = ops.translate(op, p, rom)
        if d is not None:                # pure statement: which R does it write?
            writes = gcl._stmt_writes('\n'.join(d.get('c') or []))
            if any(i in live for i in range(16) if 'r%d' % i in writes):
                return False             # arithmetic/etc. rewrote a chased reg
            p -= 2
            continue
        sh = gcl._mem_shape(op)
        if sh is not None:
            w = []
            if sh['dir'] == 'load':
                if sh.get('dest') is not None:
                    w.append(sh['dest'])
                if sh.get('auto') == 'post':
                    w.append(sh['base'])
            elif sh.get('auto') == 'pre':
                w.append(sh['base'])
            if any(i in live for i in w):
                return False
            p -= 2
            continue
        g = gcl._decode_gbr(op)
        if g is not None:
            if g[1] == 'load' and 0 in live:
                return False             # GBR load writes r0
            p -= 2
            continue
        if gcl.is_fpu_op(op):
            p -= 2
            continue                     # writes FR/FPUL only, never Rn
        if op & 0xF000 == 0x4:           # 0x4nxx system-control / shift family
            ctrlload = op & 0xF0FF in (0x400A, 0x401A, 0x402A, 0x405A, 0x406A,
                                       0x400E, 0x401E, 0x402E, 0x403E, 0x404E)
            tonly = op in (0x4011, 0x4015, 0x401B)
            if ctrlload or tonly:
                p -= 2
                continue
            if n in live:
                return False
            p -= 2
            continue
        if op & 0xF000 == 0x0:           # 0x0nxx sts/stc/movt write Rn
            if op & 0xF0FF in (0x000A, 0x001A, 0x002A, 0x005A, 0x006A,
                               0x0002, 0x0012, 0x0022, 0x0032, 0x0042, 0x0029):
                if n in live:
                    return False
            p -= 2
            continue
        return False                     # unknown opcode: cannot verify purity
    return False


def _accum_additive(counters, rom, c, end, reason):
    """Additive dryrun-only counter updates for one rejected candidate.  Called
    only for reasons target_fuori / base_unresolved / unmapped.  Does NOT alter
    the selection pool or the existing rejected/skipped counters."""
    addr = c['addr']
    out_targets, unmapped, reject = _analyze_rejected(rom, addr, end)
    if reason == 'target_fuori':
        if out_targets:
            if all(end <= t <= end + 8 for _, t in out_targets):
                counters['fuori_vicini_8'] += 1
                counters.setdefault('_fuori8_addrs', set()).add(addr)
            if all(end <= t <= end + 16 for _, t in out_targets):
                counters['fuori_vicini_16'] += 1
    elif reason == 'base_unresolved':
        rpc, rreason, base_reg = reject
        if _chain_resolvable(rom, addr, rpc, base_reg):
            counters['chain_resolvable'] += 1
    elif reason == 'unmapped':
        counters['unmapped_opcodes'].update(unmapped)


_EMU_CACHE = {}


def _emu_executes(rom, op):
    """emu:(yes/no) for counter C: does sh2emu actually implement this exact
    opcode?  Branches are dispatched by _delayed() (bsrf/braf/jsr/jmp/bsr/bra/
    bt.s/bf.s/rts/rte) — a non-None _delayed result means sh2emu executes it.
    Non-branches go through _exec(), which raises NotImplementedError at every
    unhandled path (unknown-opcode fallthrough, unhandled FPU sub-encoding,
    trapa).  The opcode runs on a freshly-initialized CPU with a zeroed integer
    state; a completed handler (or any incidental non-NotImplemented exception
    from the zeroed state) means a handler exists -> emu:yes, else emu:no."""
    key = (id(rom), op)
    if key in _EMU_CACHE:
        return _EMU_CACHE[key]
    try:
        c = sh2emu.SH2(rom)
        c.ram = {}
        c.r = [0] * 16
        c.fr = [0.0] * 16
        c.pr = 0; c.T = 0; c.macl = 0; c.mach = 0; c.gbr = 0
        c.sr = 0x000000F0
        c._Q = (c.sr >> 3) & 1; c._M = (c.sr >> 2) & 1
        c.vbr = 0; c.ssr = 0; c.spc = 0; c.fpul = 0; c.fpscr = 0
        c.pc = 0
        if c._delayed(op) is not None:
            _EMU_CACHE[key] = True   # sh2emu dispatches it as a branch/return
        else:
            c._exec(op, 0)
            _EMU_CACHE[key] = True
    except NotImplementedError:
        _EMU_CACHE[key] = False
    except Exception:
        _EMU_CACHE[key] = True
    return _EMU_CACHE[key]


# ---------------------------------------------------------------------------
# Additive dryrun-only extension measurements (a) TRAILING-RTS and (b)
# UNMAPPED-REALI.  Both NEVER change the selection: they post-mortem spans the
# v3 selector (select_v3) already rejected and count how many would be
# rescued by a concrete, bounded criterion.  No files are written.
# ---------------------------------------------------------------------------
def _is_dedup(c, outdir, root=ROOT):
    """Mirror of select_v3's dedup check (same names, same globs)."""
    base = gcl.sanitize(c['name'])
    out_c = os.path.join(outdir, '%s_%x.c' % (base, c['addr']))
    out_t = os.path.join(root, 'c', 'tests', 'test_%s_%x.py' % (base, c['addr']))
    return (os.path.exists(out_c) or os.path.exists(out_t) or
            glob.glob(os.path.join(outdir, '*_%x.c' % c['addr'])))


def _find_trailing_rts(rom, end, limit=16):
    """First rts (opcode 0x000B) 16-bit word at an even offset in
    [end, end+limit] -> its address, or None.  SH-2 is 2-byte aligned, so an
    odd `end` is aligned up to the first even address before scanning."""
    start = end if end % 2 == 0 else end + 1
    for p in range(start, end + limit + 1, 2):
        if p + 2 > len(rom):
            break
        if (rom[p] << 8) | rom[p + 1] == 0x000B:
            return p
    return None


def scan_with_end_ext(cats, rom, catalog, outdir, root=ROOT):
    """Additive dryrun-only (a): TRAILING-RTS feasibility.

    Scope = candidates the v3 selector (select_v3) rejects on END-related
    motifs — the "size / no_span / target_fuori / skipped" reasons found in the
    selector: skipped_size, skipped_dedup, skipped_no_branch and the rejected
    'target_fuori' (both direct and branch_v3).  skipped_no_span candidates
    have NO catalog end, so there is no end..end+16 window to inspect — they
    cannot participate (documented exclusion).

    For each in-scope candidate we look for an rts (0x000B) in
    rom[end:end+16]; trailing_rts_n counts those.  Then scan_with_end_ext
    re-runs the FULL v3 criteria on the span extended past that rts AND its
    delay slot (new_end = rts_addr + 4; rts is a delayed return, so its P+2
    slot must stay in-span per _v3_branch_rule) — sanitize_span, the size
    gate, the dedup rule, _scan_mem_function and the >= 1 admitted-branch
    gate — and counts how many would be selected: pool_rts =
    pool_attuale + rescued.  Pure measurement; selection/emission untouched.
    Returns (trailing_rts_n, rescued, examples).
    """
    trailing_rts_n = 0
    rescued = 0
    examples = []
    for c in cats:
        end = catalog.get(c['addr'])
        if end is None:
            continue                        # no_span: no end to extend from
        _a, end_s, _r = sanitize_span(c['addr'], end, rom)
        size = end_s - c['addr']
        # -- classify the v3 reject/skip motif, exactly select_v3's order --
        if not (gcl.MEM_MIN <= size <= gcl.MEM_MAX + 16):
            motif = 'skipped_size'
        elif _is_dedup(c, outdir, root):
            motif = 'skipped_dedup'
        else:
            entry, reason = gcl._scan_mem_function(rom, c, end_s, None)
            if entry is None:
                if isinstance(reason, tuple):
                    r, det = reason
                    motif = (gcl._BRANCH_V3_REASON.get(det, 'branch')
                             if r == 'branch_v3' else r)
                else:
                    motif = reason
            elif not entry['branches']:
                motif = 'skipped_no_branch'
            else:
                continue                    # selected: not in scope
        if motif not in ('skipped_size', 'skipped_dedup', 'skipped_no_branch',
                         'target_fuori'):
            continue                        # not an end-related motif
        rts_addr = _find_trailing_rts(rom, end)
        if rts_addr is None:
            continue
        trailing_rts_n += 1
        # re-run the FULL v3 criteria on the extended span (rts + its slot)
        _a2, end_s2, _r2 = sanitize_span(c['addr'], rts_addr + 4, rom)
        if not (gcl.MEM_MIN <= end_s2 - c['addr'] <= gcl.MEM_MAX + 16):
            continue
        if _is_dedup(c, outdir, root):
            continue
        entry, reason = gcl._scan_mem_function(rom, c, end_s2, None)
        if entry is None or not entry['branches']:
            continue
        rescued += 1
        if len(examples) < 5:
            examples.append((c['addr'], c['name'], end, rts_addr, motif))
    return trailing_rts_n, rescued, examples


def _v3_unmapped_op(rom, op, pc):
    """True when NO v3 mapper stage handles `op`: translate(), the ldc-Rn-GBR
    pattern (0x4n1E), decode_mem, _decode_gbr, the r14/r15 mem shapes,
    is_mem_opcode and is_fpu_op — i.e. the op would hit _scan_mem_function's
    `return None, 'unmapped'` fallthrough.  (decode_mem runs with a stub
    resolve ctx: base RESOLUTION doesn't change whether the encoding decodes.)"""
    if ops.translate(op, pc, rom) is not None:
        return False
    if op & 0xF0FF == 0x401E:
        return False
    if gcl.is_call_op(op) or op == 0x002B or gcl.is_branch_op(op):
        return False
    ctx = {'temp': (lambda: 't1'), 'resolve': (lambda reg: None)}
    if ops.decode_mem(op, None, ctx) is not None:
        return False
    if gcl._decode_gbr(op) is not None:
        return False
    if ops.decode_gbr_bit(op, pc, rom, {'gbr': 0}) is not None:
        return False
    sh = gcl._mem_shape(op)
    if sh is not None and sh['base'] in (14, 15):
        return False
    if gcl.is_mem_opcode(op) or gcl.is_fpu_op(op):
        return False
    return True


def scan_unmapped_reali(cats, rom, catalog, outdir, root=ROOT):
    """Additive dryrun-only (b): UNMAPPED-REALI feasibility.

    Scope = candidates the v3 selector rejects 'unmapped' (on the sanitized
    span).  Count those whose EVERY 16-bit word in [addr, end_s) is an opcode
    sh2emu actually executes (_emu_executes: _exec/_delayed do NOT raise
    NotImplementedError — e.g. bsrf 0x0003, stc SR 0x0002, 0x2FE6, 0x4F22)
    with NO call, NO rte and NO FPU op anywhere ("solo opcode che sh2emu
    esegue, niente call/altro"): the only thing standing between the function
    and the pool is the mapper not knowing an opcode the emulator runs.
    Returns (count, top_opcodes Counter of the mapper-unmapped opcodes,
    examples); pool_unmap = pool_attuale + count.  Pure measurement;
    selection/emission untouched.
    """
    count = 0
    top = Counter()
    examples = []
    for c in cats:
        end = catalog.get(c['addr'])
        if end is None:
            continue
        _a, end_s, _r = sanitize_span(c['addr'], end, rom)
        if not (gcl.MEM_MIN <= end_s - c['addr'] <= gcl.MEM_MAX + 16):
            continue
        if _is_dedup(c, outdir, root):
            continue
        entry, reason = gcl._scan_mem_function(rom, c, end_s, None)
        if entry is not None:
            continue
        r = reason[0] if isinstance(reason, tuple) else reason
        if r != 'unmapped':
            continue
        ok = True
        these = Counter()
        pw = gcl._pcrel_pool_words(rom, c['addr'], end_s)
        pc = c['addr']
        bound = min(end_s, len(rom))
        while pc + 1 < bound:
            if pc in pw:                        # literal-pool data — not an opcode
                pc += 2
                continue
            op = (rom[pc] << 8) | rom[pc + 1]
            if gcl.is_call_op(op) or op == 0x002B or gcl.is_fpu_op(op) \
                    or not _emu_executes(rom, op):
                ok = False
                break
            if _v3_unmapped_op(rom, op, pc):
                these[op] += 1
            pc += 2
        if ok:
            count += 1
            top.update(these)
            if len(examples) < 5:
                examples.append((c['addr'], c['name'], end_s,
                                 sorted(these)))
    return count, top, examples


# ---------------------------------------------------------------------------
# Emission walker: re-decode an accepted span with the SAME acceptance tracking
# as gen_c_lift._walk_mem_span (written/lits/gbr/stack_ok/frame_live/frame_off/
# sp_off), but treat admitted branches as first-class records with their delay
# slot folded in.  Returns (records, info, labels) or None on divergence (the
# caller drops the function).  records are dicts:
#   {'pc', 'op', 'kind': st|mem|gbr|stack|frame|ldc|branch,
#    'c': [C lines], 'mnem', 'target': int|None, 'slot': record|None}
# labels = set of branch-target pcs (each gets `L_<pc>: ;`).
# ---------------------------------------------------------------------------
def walk_v3(rom, addr, end):
    bound = min(end, len(rom))
    st = {'written': set(), 'lits': {}, 'tmp': [0], 'trk': {},
          'gbr_known': False, 'gbr_value': None,
          'stack_ok': True, 'frame_live': False, 'frame_off': None,
          'sp_off': 0x400,
          # v7: literal-base LOAD propagation (must mirror _scan_mem_v3 so the
          # walker accepts exactly the spans the selector admitted).
          'ram_known': {}, 'branches_seen': False}
    info = {'stack_offs': set(), 'ram_addrs': set(),
            'has_stack': False, 'has_literal': False, 'gbr_input': False}
    labels = set()
    records = []
    skip = set()

    def temp():
        st['tmp'][0] += 1
        return 't%d' % st['tmp'][0]

    def resolve(reg):
        v = st['lits'].get('r%d' % reg)
        if v is None:
            r = _trk_fold(st['trk'], st['written'], reg)
            if r and r[0] == 'lit':
                v = r[1]
            else:
                return None
        cls = ops.classify_addr(v)
        if cls in ('RAM', 'ROM'):
            return (cls, v)
        return None

    ctx = {'temp': temp, 'resolve': resolve}

    def emit_one(pc, op):
        """Emit one non-branch instruction record (mutates the tracking state).
        Mirrors _walk_mem_span's per-instruction logic; returns None when the
        instruction is not emittable (caller drops the function)."""
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
                if op & 0xF000 == 0x7000 and ((op >> 8) & 0xF) == 15:
                    # `add #imm,r15` keeps stack_ok (stack allocation).  The
                    # runtime stack pointer moves by the signed immediate, so
                    # (a) every subsequent @r15/@(disp,r15) offset must shift by
                    # it (sp_off tracks r15-relative-to-STACK_BASE) and (b) the
                    # mirror's `sp` alias must follow, or the final r15
                    # comparison diverges from sh2emu (unbalanced prologues).
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
            _trk_apply_stmt(st['trk'], op, rom, pc)
            if not gcl._apply_stmt(rom, pc, op, d, st['written'], st['lits']):
                return None
            return {'pc': pc, 'op': op, 'kind': 'st',
                    'c': list(d.get('c') or []),
                    'py': list(d.get('py') or []),
                    'target': None, 'slot': None,
                    'mnem': d.get('ann') or ('op 0x%04X' % op)}
        if op & 0xF0FF == 0x401E:                  # ldc Rn,GBR
            st['gbr_known'] = True
            _lit = _lit_of((op >> 8) & 0xF, st['lits'], st['trk'], st['written'])
            st['gbr_value'] = _lit if _lit is not None else 'input'
            return {'pc': pc, 'op': op, 'kind': 'ldc',
                    'c': ['/* ldc r%d,GBR (GBR = %s) */'
                          % ((op >> 8) & 0xF,
                             ('0x%08X' % st['gbr_value']) if _lit is not None
                             else 'runtime input')],
                    'py': [], 'target': None, 'slot': None,
                    'mnem': 'ldc r%d,GBR' % ((op >> 8) & 0xF)}
        if op & 0xF0FF == 0x4017:                  # lds.l @Rm+,GBR (GBR = RAM[Rm])
            st['gbr_known'] = True
            _lit = _lit_of((op >> 8) & 0xF, st['lits'], st['trk'], st['written'])
            if _lit is not None and _lit < len(rom) and ops.classify_addr(_lit) == 'ROM':
                st['gbr_value'] = (rom[_lit] << 24 | rom[_lit + 1] << 16
                                   | rom[_lit + 2] << 8 | rom[_lit + 3])
            else:
                st['gbr_value'] = 'input'
            return {'pc': pc, 'op': op, 'kind': 'ldc',
                    'c': ['/* lds.l @r%d+,GBR (GBR = %s) */'
                          % ((op >> 8) & 0xF,
                             ('0x%08X' % st['gbr_value'])
                             if st['gbr_value'] != 'input' else 'runtime input')],
                    'py': [], 'target': None, 'slot': None,
                    'mnem': 'lds.l @r%d+,GBR' % ((op >> 8) & 0xF)}
        if op & 0xF0FF in (0x4003, 0x4007):        # stc.l SR,@-Rn / ldc.l @Rn+,SR
            # Same base resolution as decode_mem (param r4..r7 | known literal);
            # the value transferred is `sr` (not an rN), so _mem_record cannot
            # render these — build the record here.  Auto side-effects and the
            # sr state are modeled exactly as sh2emu (0x4n03: rn -= 4 then
            # wr(rn,sr); 0x4n07: sr = rd(rn) then rn += 4).
            srn = (op >> 8) & 0xF
            if srn in (4, 5, 6, 7) and 'r%d' % srn not in st['written']:
                bkind, abs_addr = 'param', None
            elif 'r%d' % srn in st['lits']:
                bkind, abs_addr = 'literal', st['lits']['r%d' % srn]
            else:
                r = _trk_fold(st['trk'], st['written'], srn)
                if not r:
                    return None
                if r[0] == 'lit':
                    bkind, abs_addr = 'literal', r[1]
                else:
                    bkind, abs_addr = 'param', None
            if bkind == 'literal':
                info['has_literal'] = True
                info['ram_addrs'].add(abs_addr)
            if op & 0xF0FF == 0x4003:              # stc.l SR,@-Rn (pre-decrement)
                if bkind == 'literal':
                    a = (abs_addr - 4) & gcl.MASK
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
            else:                                  # ldc.l @Rn+,SR (post-increment)
                if bkind == 'literal':
                    eff = '0x%08X' % (abs_addr & gcl.MASK)
                    note = (' /* RAM 0x%08X */' % (abs_addr & gcl.MASK)
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
            st['written'].add('r%d' % srn)         # auto side-effect kills literal
            st['lits'].pop('r%d' % srn, None)
            st['trk']['r%d' % srn] = None
            return {'pc': pc, 'op': op, 'kind': 'mem', 'c': c, 'py': py,
                    'target': None, 'slot': None, 'mnem': mnem}
        if op & 0xF0FF in (0x4002, 0x4012, 0x4022, 0x4006, 0x4016, 0x4026):
            # ---- sts.l/lds.l mach/macl/pr @-Rn/@Rn+ (sys_src/sys_dest) ----
            # c_lift_ops.decode_mem flags these with sys_src/sys_dest + sys_reg
            # and carries 1:1 'py' mirror fragments, but _mem_record cannot
            # render them (src/dest are None — the value transferred is the
            # system register, not an rN).  Render here, mirroring the SR block
            # above AND the r15/r14 stack-slot model of the sh block below:
            #   sts.l pr,@-r15   0x4F22: off = sp-4; local_off = pr; sp -= 4
            #   lds.l @r15+,pr   0x4F26: pr = local_off; sp += 4
            # For a stack base the local_<off> slot is shared with every other
            # r15/r14 mem op (sh2emu writes/reads the same RAM), so pr/macl/mach
            # round-trips through the function prologue/epilogue for free.
            SYS_REG = {0x4002: 'mach', 0x4012: 'macl', 0x4022: 'pr',
                       0x4006: 'mach', 0x4016: 'macl', 0x4026: 'pr'}
            reg = SYS_REG[op & 0xF0FF]
            sys_store = (op & 0xF) == 0x2    # low nibble: 2 = sts.l (0x02/0x12/0x22), 6 = lds.l (0x06/0x16/0x26)
            srn = (op >> 8) & 0xF
            st['written'].add('r%d' % srn)         # auto side-effect kills literal
            st['lits'].pop('r%d' % srn, None)
            st['trk']['r%d' % srn] = None
            if srn == 15 and st['stack_ok']:
                if sys_store:
                    st['sp_off'] -= 4
                    off = st['sp_off']
                else:
                    off = st['sp_off']
                    st['sp_off'] += 4
                info['has_stack'] = True
                info['stack_offs'].add(off)
                if sys_store:
                    c = ['local_%x = %s;' % (off, reg)]
                    py = ['local[0x%X] = %s' % (off, reg),
                          '_wrw(ram, STACK_BASE + 0x%X, 4, %s)' % (off, reg),
                          'sp = (sp - 4) & 0xFFFFFFFF']
                else:
                    c = ['%s = local_%x;' % (reg, off)]
                    py = ['%s = _rdw(ram, STACK_BASE + 0x%X, 4)' % (reg, off),
                          'sp = (sp + 4) & 0xFFFFFFFF']
                mnem = ('sts.l %s,@-r15' % reg if sys_store
                        else 'lds.l @r15+,%s' % reg)
            elif srn == 14 and st['frame_live']:
                base_off = (st['frame_off'] if st['frame_off'] is not None
                            else st['sp_off'])
                off = base_off - 4 if sys_store else base_off
                info['has_stack'] = True
                info['stack_offs'].add(off)
                if sys_store:
                    c = ['local_%x = %s;' % (off, reg)]
                    py = ['local[0x%X] = %s' % (off, reg),
                          '_wrw(ram, STACK_BASE + 0x%X, 4, %s)' % (off, reg),
                          'sp = (sp - 4) & 0xFFFFFFFF']
                else:
                    c = ['%s = local_%x;' % (reg, off)]
                    py = ['%s = _rdw(ram, STACK_BASE + 0x%X, 4)' % (reg, off),
                          'sp = (sp + 4) & 0xFFFFFFFF']
                mnem = ('sts.l %s,@-r14' % reg if sys_store
                        else 'lds.l @r14+,%s' % reg)
            else:
                if srn in (4, 5, 6, 7) and 'r%d' % srn not in st['written']:
                    bkind, abs_addr = 'param', None
                elif 'r%d' % srn in st['lits']:
                    bkind, abs_addr = 'literal', st['lits']['r%d' % srn]
                else:
                    r = _trk_fold(st['trk'], st['written'], srn)
                    if not r:
                        return None
                    if r[0] == 'lit':
                        bkind, abs_addr = 'literal', r[1]
                    else:
                        bkind, abs_addr = 'param', None
                if bkind == 'literal':
                    info['has_literal'] = True
                    info['ram_addrs'].add(abs_addr)
                if sys_store:
                    if bkind == 'literal':
                        a = (abs_addr - 4) & gcl.MASK
                        eff = '0x%08X' % a
                        note = (' /* RAM 0x%08X */' % a
                                if ops.classify_addr(a) == 'RAM' else ' /* ROM */')
                    else:
                        eff, note = '(r%d - 4)' % srn, ''
                    c = ['*(volatile uint32_t*)%s = %s;%s' % (eff, reg, note),
                         'r%d = r%d - 4;' % (srn, srn)]
                    py = ['_wrw(ram, (r[%d] - 4) & 0xFFFFFFFF, 4, %s)' % (srn, reg),
                          'r[%d] = (r[%d] - 4) & 0xFFFFFFFF' % (srn, srn)]
                    mnem = 'sts.l %s,@-r%d' % (reg, srn)
                else:
                    if bkind == 'literal':
                        eff = '0x%08X' % (abs_addr & gcl.MASK)
                        note = (' /* RAM 0x%08X */' % (abs_addr & gcl.MASK)
                                if ops.classify_addr(abs_addr) == 'RAM' else ' /* ROM */')
                    else:
                        eff, note = 'r%d' % srn, ''
                    t = temp()
                    c = ['uint32_t %s = *(volatile uint32_t*)%s;%s' % (t, eff, note),
                         '%s = %s;' % (reg, t),
                         'r%d = r%d + 4;' % (srn, srn)]
                    py = ['%s = _rdw(ram, r[%d], 4)' % (reg, srn),
                          'r[%d] = (r[%d] + 4) & 0xFFFFFFFF' % (srn, srn)]
                    mnem = 'lds.l @r%d+,%s' % (srn, reg)
            return {'pc': pc, 'op': op, 'kind': 'mem', 'c': c, 'py': py,
                    'target': None, 'slot': None, 'mnem': mnem}
        m = ops.decode_mem(op, None, ctx)
        if m is not None:
            base_reg = m['base_reg']
            if m.get('idx') == 'r0' and 'r0' not in st['lits']:
                if not _trk_fold(st['trk'], st['written'], 0):
                    return None
            if base_reg in (4, 5, 6, 7) and 'r%d' % base_reg not in st['written']:
                bkind, abs_addr = 'param', None
            elif 'r%d' % base_reg in st['lits']:
                bkind, abs_addr = 'literal', st['lits']['r%d' % base_reg]
            else:
                r = _trk_fold(st['trk'], st['written'], base_reg)
                if not r:
                    return None
                if r[0] == 'lit':
                    bkind, abs_addr = 'literal', r[1]
                else:
                    bkind, abs_addr = 'param', None
            if bkind == 'literal':
                info['has_literal'] = True
                info['ram_addrs'].add(abs_addr)
            _dyn = ((pc in reentry)
                    or ('r%d' % base_reg) in carried.get(pc, ())
                    # v7.1: path-sensitivity guard — a literal base folded from
                    # the copy+arith tracker (i.e. NOT a fresh pool load still
                    # in st['lits']) can be stale once any branch was admitted:
                    # a forward conditional branch may SKIP a write in the
                    # chain, so the runtime register differs from the baked
                    # linear value (seen at 0x5B194 diagMeteringPumpPosition
                    # Control: bf@0x5B176 taken skips `r6+=0x14`@0x5B17A, so
                    # the runtime effective address was 0xFFFFD15D vs the
                    # linear-baked 0xFFFFD171 -> generated test case 52 FAIL).
                    # Emit register-relative (dynbase) for those; the fold then
                    # stays off (dest UNKNOWN), so a dependent mem drops the
                    # function — conservative and always runtime-correct.
                    or (st['branches_seen']
                        and 'r%d' % base_reg not in st['lits']))
            c, py = gcl._mem_record(pc, op, m, bkind, abs_addr, temp,
                                    dynbase=_dyn)
            gcl._apply_mem_writes(m, st['written'], st['lits'])
            # v7: literal-base LOAD propagation (mirrors _scan_mem_v3).  A ROM
            # effective address folds to the .bin bytes; a RAM slot folds only
            # when a KNOWN store wrote it earlier on the linear path (no branch
            # admitted yet).  dynbase (re-entry pc / loop-carried base) never
            # folds — the runtime address can differ on a later visit, so the
            # dest stays UNKNOWN and any dependent mem just drops the function.
            if bkind == 'literal' and m.get('idx') is None:
                eff = (abs_addr + m.get('disp', 0)) & gcl.MASK
                if m['dir'] == 'load' and m.get('dest') is not None:
                    if not _dyn:
                        v = ops.lit_load_value(
                            rom, eff, m['size'], m.get('sext', False),
                            st['ram_known'] if not st['branches_seen'] else None)
                        st['trk']['r%d' % m['dest']] = ('lit', v) if v is not None else None
                elif m['dir'] == 'store' and m.get('src') is not None and not _dyn:
                    sv = _trk_fold(st['trk'], st['written'], m['src'])
                    ops.lit_store_bytes(st['ram_known'], eff, m['size'],
                                        sv[1] if sv and sv[0] == 'lit' else None)
            if m['dir'] == 'load' and m.get('dest') is not None:
                st['trk'].setdefault('r%d' % m['dest'], None)
            if m.get('auto') in ('post', 'pre'):
                st['trk']['r%d' % m['base_reg']] = None
            return {'pc': pc, 'op': op, 'kind': 'mem', 'c': c, 'py': py,
                    'target': None, 'slot': None, 'mnem': m['ann']}
        g = gcl._decode_gbr(op)
        if g is not None:
            size, gdir, disp = g
            if st['gbr_value'] is None:
                # GBR never set in-span (caller sets it): runtime input base.
                st['gbr_value'] = 'input'
            gm = {'dir': gdir, 'dest': 0 if gdir == 'load' else None,
                  'src': 0 if gdir == 'store' else None}
            if st['gbr_value'] == 'input':
                # EA = gbr + r0 + disp at runtime (mirror tracks r0); the gbr
                # param is added to the C signature and seeded in the harness.
                info['gbr_input'] = True
                c, py = ops.gbr_mov_runtime(size, gdir, disp, temp)
                mnem = ('mov.%s r0,@(0x%X,gbr) [gbr=runtime]' % (gcl._SIZE_CH[size], disp)
                        if gdir == 'store' else
                        'mov.%s @(0x%X,gbr),r0 [gbr=runtime]' % (gcl._SIZE_CH[size], disp))
                gcl._apply_mem_writes(gm, st['written'], st['lits'])
                if gdir == 'load':
                    st['trk']['r0'] = None
                return {'pc': pc, 'op': op, 'kind': 'gbr', 'c': c, 'py': py,
                        'target': None, 'slot': None, 'mnem': mnem}
            if 'r0' not in st['lits']:
                r0 = _trk_fold(st['trk'], st['written'], 0)
                if not r0 or r0[0] != 'lit':
                    return None
                st['lits']['r0'] = r0[1]
            abs_addr = (st['gbr_value'] + st['lits']['r0'] + disp) & gcl.MASK
            info['has_literal'] = True
            info['ram_addrs'].add(abs_addr)
            c, py = gcl._gbr_record(pc, op, size, gdir, abs_addr, temp)
            if gdir == 'store':
                mnem = 'mov.%s r0,@(0x%X,gbr)' % (gcl._SIZE_CH[size], disp)
            else:
                mnem = 'mov.%s @(0x%X,gbr),r0' % (gcl._SIZE_CH[size], disp)
            gcl._apply_mem_writes(gm, st['written'], st['lits'])
            if gdir == 'load':
                st['trk']['r0'] = None
            return {'pc': pc, 'op': op, 'kind': 'gbr', 'c': c, 'py': py,
                    'target': None, 'slot': None, 'mnem': mnem}
        gb = ops.decode_gbr_bit(op, pc, rom, None)
        if gb is not None:
            if st['gbr_value'] is None:
                st['gbr_value'] = 'input'
            if st['gbr_value'] == 'input':
                info['gbr_input'] = True
                gbd = ops.decode_gbr_bit(op, pc, rom, {'gbr_runtime': True})
                return {'pc': pc, 'op': op, 'kind': 'gbr', 'c': list(gbd['c']),
                        'py': list(gbd['py']), 'target': None, 'slot': None,
                        'mnem': gbd['ann'] + ' [gbr=runtime]'}
            if 'r0' not in st['lits']:
                r0 = _trk_fold(st['trk'], st['written'], 0)
                if not r0 or r0[0] != 'lit':
                    return None
                else:
                    st['lits']['r0'] = r0[1]
            abs_addr = (st['gbr_value'] + st['lits']['r0']) & gcl.MASK
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
            if sh['idx'] is not None:              # dynamic r0 index: not mappable
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
            if sh['dir'] == 'load' and sh.get('dest') is not None:
                st['trk']['r%d' % sh['dest']] = None
            if sh.get('auto') in ('post', 'pre'):
                st['trk']['r%d' % breg] = None
            return {'pc': pc, 'op': op, 'kind': 'stack', 'c': c, 'py': py,
                    'target': None, 'slot': None, 'mnem': gcl._stack_mnem(sh)}
        # ---- v4 FPU (additive): decode_fpu-able ops are emitted verbatim ----
        f = ops.decode_fpu(op, pc, rom, ctx)
        if f is not None:
            if f.get('kind') == 'fpu_mem':
                if f.get('unresolved'):          # base not param/literal
                    return None
                base_reg = f['base_reg']
                if f.get('idx') == 'r0' and 'r0' not in st['lits']:
                    if not _trk_fold(st['trk'], st['written'], 0):
                        return None
                if f['base'] == 'literal':
                    info['has_literal'] = True
                    v = st['lits'].get('r%d' % base_reg)
                    if v is None:
                        r = _trk_fold(st['trk'], st['written'], base_reg)
                        v = r[1] if r and r[0] == 'lit' else None
                        if v is not None:
                            st['lits']['r%d' % base_reg] = v
                    if v is not None and ops.classify_addr(v) == 'RAM':
                        info['ram_addrs'].add(v)
                if f.get('auto') in ('post', 'pre'):
                    reg = 'r%d' % base_reg
                    st['written'].add(reg)       # auto-update kills any literal
                    st['lits'].pop(reg, None)
                    st['trk'][reg] = None
                elif f.get('dir') == 'load' and f.get('dest') is not None:
                    st['trk']['r%d' % f['dest']] = None
                return {'pc': pc, 'op': op, 'kind': 'fpu_mem',
                        'c': list(f.get('c') or []),
                        'py': list(f.get('py') or []),
                        'target': None, 'slot': None,
                        'mnem': f.get('ann') or ('op 0x%04X' % op)}
            for reg in gcl._stmt_writes('\n'.join(f.get('c') or [])):
                st['written'].add(reg)           # sts/lds write rN (frN too)
                st['lits'].pop(reg, None)
                st['trk'][reg] = None
            return {'pc': pc, 'op': op, 'kind': 'fpu',
                    'c': list(f.get('c') or []),
                    'py': list(f.get('py') or []),
                    'target': None, 'slot': None,
                    'mnem': f.get('ann') or ('op 0x%04X' % op)}
        return None

    pc = addr
    pool_words = gcl._pcrel_pool_words(rom, addr, end)
    # Pre-pass: every static branch target in the span.  A literal-base mem whose
    # PC is a re-entry point may be reached again with the base register already
    # modified (loop counter / duplicate entry) — such mems must emit the runtime
    # register (dynbase) instead of baking the first-pass literal address.
    reentry = set()
    _p = addr
    while _p + 1 < bound:
        if _p in pool_words or _p in skip:
            _p += 2
            continue
        _op = (rom[_p] << 8) | rom[_p + 1]
        _d = ops.translate(_op, _p, rom)
        if _d is not None and _d.get('kind') in ('branch', 'ret'):
            _bi = ops.branch_info(_op)
            if _bi and _bi['kind'] not in ('rte', 'rts', 'bsrf', 'braf'):
                _t = (_p + 4 + _bi['target_disp'] * 2) & gcl.MASK
                if addr <= _t < end:
                    reentry.add(_t)
        _p += 2
    # ---- Bug 2: loop-carried (register) base · dynbase extension -------------
    # A literal-folded mem base (bkind='literal') is only valid when the base
    # register stays constant between re-entries.  If the register is WRITTEN
    # again inside a backward-branch loop body that re-enters the mem, the
    # runtime address changes across iterations, so the mem must be emitted
    # register-relative (`rN(+disp)`) instead of baking the folded literal.
    # gen_c_lift._mem_record already does this for mem directly at a re-entry
    # PC (dynbase=); here we broaden it to REGISTER bases modified anywhere in
    # the enclosing loop body (initial entry run included) — the same principle
    # extended from literal-base to register-base loop-carried mems.
    carried = {}                       # pc -> set of registers written in its loop
    _p2 = addr
    while _p2 + 1 < bound:
        if _p2 in pool_words:
            _p2 += 2
            continue
        _op2 = (rom[_p2] << 8) | rom[_p2 + 1]
        _d2 = ops.translate(_op2, _p2, rom)
        if _d2 is not None and _d2.get('kind') in ('branch',):
            _bi2 = ops.branch_info(_op2)
            if _bi2 and _bi2['kind'] not in ('rte', 'rts', 'bsrf', 'braf'):
                _lo = (_p2 + 4 + _bi2['target_disp'] * 2) & gcl.MASK
                if addr <= _lo < _p2:            # backward branch -> loop body
                    _wr = set()
                    _q = _lo
                    _qend = _p2 + 2              # include the delay slot
                    while _q < bound and _q <= _qend:
                        if _q not in pool_words:
                            _oq = (rom[_q] << 8) | rom[_q + 1]
                            _dqr = ops.translate(_oq, _q, rom)
                            if _dqr is not None:
                                _wr |= gcl._stmt_writes(
                                    '\n'.join(_dqr.get('c') or []))
                            _m = ops.decode_mem(_oq, None, ctx)
                            if _m is not None:
                                gcl._apply_mem_writes(_m, _wr, {})
                            _sh = gcl._mem_shape(_oq)
                            if _sh is not None and _sh['base'] in (14, 15):
                                gcl._apply_mem_writes(
                                    {'dir': _sh['dir'], 'size': _sh['size'],
                                     'base_reg': _sh['base'], 'auto': _sh['auto'],
                                     'dest': _sh.get('dest'),
                                     'src': _sh.get('src')}, _wr, {})
                        _q += 2
                    for _q in range(_lo, _qend + 1, 2):
                        if _q in pool_words:
                            continue
                        carried.setdefault(_q, set()).update(_wr)
        _p2 += 2
    while pc + 1 < bound:
        if pc in pool_words:                     # literal-pool data word
            pc += 2
            continue
        if pc in skip:                             # consumed delay slot
            pc += 2
            continue
        op = (rom[pc] << 8) | rom[pc + 1]
        d = ops.translate(op, pc, rom)
        if d is not None and d.get('kind') in ('branch', 'ret'):
            bi = ops.branch_info(op)
            kind = bi['kind'] if bi is not None else None
            if kind is None or kind == 'rte':      # not a v3-admitted branch
                return None
            target = None
            if kind == 'rts':
                pass                               # target is PR — no static addr
            elif kind in ('bsrf', 'braf'):
                pass                               # dynamic target P+4+Rn
            else:
                target = (pc + 4 + bi['target_disp'] * 2) & gcl.MASK
                labels.add(target)
            slot = None
            if bi['delayed']:                      # slot at P+2: emit once here
                spc = pc + 2
                sop = (rom[spc] << 8) | rom[spc + 1]
                slot = emit_one(spc, sop)
                if slot is None:
                    return None
                skip.add(spc)
            if kind in ('bsrf', 'braf'):
                # dynamic jump: not statically liftable as a goto.  The C ends
                # the lift here (DRAFT — matches the model's fallthrough return);
                # the test mirror jumps pc = P+4+Rn dynamically (CODE dict entry
                # kind 'dynbranch'), so cases that leave the modeled span are
                # skipped and cases landing back inside it still diff exactly.
                reg = bi['reg']
                line = ('return r0; /* %s r%d — dynamic target P+4+r%d, leaves '
                        'the modeled span (DRAFT) */' % (kind, reg, reg))
                mnem = '%s r%d' % (kind, reg)
            else:
                line = BRANCH_C[kind] if kind == 'rts' else BRANCH_C[kind] % target
                mnem = BRANCH_MNEM[kind] if kind == 'rts' else BRANCH_MNEM[kind] % target
            records.append({'pc': pc, 'op': op, 'kind': 'branch',
                            'c': [line], 'mnem': mnem,
                            'target': target, 'slot': slot})
            st['branches_seen'] = True
            pc += 2
            continue
        rec = emit_one(pc, op)
        if rec is None:
            return None
        records.append(rec)
        pc += 2
    return records, info, labels


def render_body(records, labels):
    """Linear emission: label line before every branch-target instruction;
    each record gets `/* 0xADDR: mnemonic */` then its C fragment(s); a delayed
    branch's slot is rendered inside the branch record (before the goto)."""
    stmts = []
    for rec in records:
        if rec['pc'] in labels:
            stmts.append('L_%X: ;' % rec['pc'])
        stmts.append('/* 0x%06X: %s */' % (rec['pc'], rec['mnem']))
        slot = rec.get('slot')
        if slot is not None:
            if slot['pc'] in labels:
                stmts.append('L_%X: ;' % slot['pc'])
            stmts.append('/* 0x%06X: %s */' % (slot['pc'], slot['mnem']))
            stmts.extend(slot['c'])
        stmts.extend(rec['c'])
    return stmts


def build_locals(stmts, info):
    """Locals: only the registers the emitted C actually references (r0..r3 and
    r8..r15 as one-per-line uint32_t; r4..r7 are the params -> note only; r15 is
    declared when the body writes it as a bare register e.g. `add #imm,r15`,
    mirroring gen_c_lift.py's pure path which declares `uint32_t r15 = 0`).
    T is declared ONLY when the body mentions
    it (a v3 body mentions T iff some bt/bf reads it or a compare writes it).
    Temps t1.. for mem loads are declared inline by the mem fragments."""
    body_text = '\n'.join(stmts)
    refs = set()
    for m_ in re.finditer(r'\br(?:[0-9]|1[0-5])\b', body_text):
        refs.add(m_.group(0))
    for tok in ('T', 'Q', 'M', 'macl', 'mach', 'sr', 'pr'):
        if re.search(r'\b%s\b' % tok, body_text):
            refs.add(tok)
    refs.add('r0')                     # always read by `return r0;`
    lines = []
    if any('r%d' % n in refs for n in range(4, 8)):
        lines.append('    /* params (possibly) */')
    for n in list(range(0, 4)) + list(range(8, 16)):
        if 'r%d' % n in refs:
            lines.append('    uint32_t r%d = 0;' % n)
    for t in ('T', 'Q', 'M', 'macl', 'mach', 'sr', 'pr'):
        if t in refs:
            if t == 'pr':
                lines.append('    uint32_t pr = 0xEEEE0000u;')
            elif t == 'sr':
                # sh2emu call() default: sr = 0x000000F0 (independent of T —
                # ldc/stc SR ops only, never auto-synced with T)
                lines.append('    uint32_t sr = 0x000000F0u;')
            else:
                lines.append('    uint32_t %s = 0;' % t)
    # v4 FPU locals: frN bit-pattern registers for the FRs the body touches,
    # plus fpul/fpscr if the FPUL/FPSCR system transfers appear.  Arithmetic/
    # compare unions are declared inline inside the decode_fpu fragments, so no
    # top-level union is needed here.
    frrefs = set()
    for m_ in re.finditer(r'\bfr(?:[0-9]|1[0-5])\b', body_text):
        frrefs.add(m_.group(0))
    for tok in ('fpul', 'fpscr'):
        if re.search(r'\b%s\b' % tok, body_text):
            frrefs.add(tok)
    for n in range(16):
        if 'fr%d' % n in frrefs:
            lines.append('    uint32_t fr%d = 0;' % n)
    if 'fpul' in frrefs:
        lines.append('    uint32_t fpul = 0;')
    if 'fpscr' in frrefs:
        lines.append('    uint32_t fpscr = 0;')
    for off in sorted(info['stack_offs']):
        lines.append('    uint32_t local_%x = 0;' % off)
    return lines


def _records_have_fpu(records):
    """True when any top-level record — OR the delay slot nested inside a branch
    record — is an FPU record (kind 'fpu'/'fpu_mem').

    walk_v3 stores a delayed branch's delay slot INSIDE the branch record
    (rec['slot']), so a top-level-only scan misses FPU ops that live in a delay
    slot.  That matters for emission: the FPU test template's mirror ns carries
    ts/bits2f/f2bits (decode_fpu's py fragments call ts()/f2bits()), while the
    v3 non-FPU template's ns does not — routing an FPU-slot function to the
    non-FPU template makes its mirror NameError on `ts`.  Checking the slots
    guarantees the FPU template is selected whenever any FPU op is emitted.
    """
    for r in records:
        if r['kind'] in ('fpu', 'fpu_mem'):
            return True
        s = r.get('slot')
        if s is not None and s['kind'] in ('fpu', 'fpu_mem'):
            return True
    return False


def emit_v3(addr, name, size, rom, out_c, rom_label=None, estimated_end=None):
    """Lift one accepted v3 function: write c/<name>_<addr>.c, compile-gate it
    with `cc -O2 -c`, and delete the file if the gate fails.  `rom_label` (e.g.
    '60E0FC00') overrides the hardcoded default for the banner ROM field;
    `estimated_end` (next-addr) marks a no-span lift whose end was estimated."""
    fn = gcl.sanitize(name)
    walked = walk_v3(rom, addr, addr + size)
    if walked is None:
        print('WARNING: lift 0x%X %-40s re-walk diverged from selection; dropped'
              % (addr, fn))
        return False
    records, info, labels = walked
    has_fpu = _records_have_fpu(records)
    gbr_input = info.get('gbr_input', False)
    stmts = render_body(records, labels)
    body = build_locals(stmts, info)
    body.extend('    ' + s for s in stmts)
    body.append('    return r0; /* fallthrough */')
    cbody = '\n'.join(body)

    banner = ('/* ROM: %s | Address: 0x%X | Size: %d bytes | STATUS: DRAFT\n'
              ' * Auto-generated by tools/gen_c_lift_v3.py — not human-verified.\n'
              ' * v3: branches + delay slots%s%s. */') % (
        rom_label or gcl.ROM_LABEL, addr, size,
        ' + v4 FPU (frN bit-pattern locals; fpul/fpscr)' if has_fpu else '',
        ' + gbr runtime input' if gbr_input else '')
    if estimated_end is not None:
        banner = banner.replace(
            ' * v3: branches + delay slots', ' * End: estimated (next_addr 0x%06X)\n * v3: branches + delay slots' % estimated_end)
    c_text = (banner + '\n'
              '#include <stdint.h>\n'
              + ('#include <math.h>\n' if has_fpu else '')
              + 'uint32_t %s_%x(uint32_t r4, uint32_t r5, uint32_t r6, uint32_t r7%s)\n'
                '{\n%s\n}\n') % (fn, addr,
                                 ', uint32_t gbr' if gbr_input else '', cbody)
    with open(out_c, 'w') as f:
        f.write(c_text)

    # ---- compile gate: same real C gate as gen_c_lift (cc -O2 -c) ----
    tmp_obj = os.path.join(tempfile.gettempdir(),
                           'gen_c_lift_v3_%d.o' % os.getpid())
    gate = subprocess.run(['cc', '-O2', '-c', out_c, '-o', tmp_obj],
                          capture_output=True, text=True)
    if os.path.exists(tmp_obj):
        os.remove(tmp_obj)
    if gate.returncode != 0:
        os.remove(out_c)
        print('WARNING: lift 0x%X %-40s failed `cc -O2 -c`; .c dropped'
              % (addr, fn))
        return False
    return True


# ---------------------------------------------------------------------------
# v3 test emission: c/tests/test_<name>_<addr>.py — a pc-interpreter
# spec_mirror differentialed against the sh2emu oracle over 2000 random inputs.
# The mirror runs the SAME mapper py fragments as the C lift, but driven by a
# CODE dict {addr: inst} with the branch/delay-slot semantics of sh2emu:
#   - delayed branch: cond sampled on T BEFORE the slot executes (sh2emu
#     samples T in _delayed at decode time, slot runs after); taken -> target,
#     not taken -> P+4 (slot address skipped);
#   - non-delayed bt/bf: not taken -> P+2;
#   - rts: slot first, then return (mirror RET; the emulator returns through
#     pr == SENT, StepLimitExceeded cases are skipped).
# RAM prefill + stack + sh2emu call config copied verbatim from the v2 tests.
# ---------------------------------------------------------------------------
_MIRROR_KIND = {'st': 'reg', 'mem': 'mem', 'gbr': 'mem', 'stack': 'mem',
                'frame': 'reg', 'ldc': 'reg',
                'fpu': 'fpu', 'fpu_mem': 'fpu'}   # v4 FPU records (py-only)
_BRANCH_COND = {'bt': 'T', 'bts': 'T', 'bf': 'notT', 'bfs': 'notT', 'bra': 'always'}


def _pool_end(records, fallback):
    """Byte-exclusive end of the PC-relative literal pool region that is
    SHADOWED by the stop-sentinel, or `fallback` (normally `end`) when nothing
    is shadowed.  Uses the exact sh2emu EA formulas: mov.l @(disp,PC) ->
    ((pc+4)&~3)+disp*4 (4 bytes); mov.w @(disp,PC) -> pc+4+disp*2 (2 bytes).

    The harness writes the 4-byte stop-sentinel (00 0B 00 09 = rts+nop) at
    `end`; a Denso literal pool sits immediately after the span, so [end, end+4)
    can shadow real ROM literals the function reads via @(disp,PC) — the
    emulator then reads 00 0B/00 09 where the mirror reads the true literal
    (spurious FFFFxxxx vs 00000009/0B mismatches).  We only relocate the
    sentinel when the first pool byte actually falls in the shadow window, and
    place it past the last shadowed byte."""
    pool_start = None
    pool_end = fallback
    def consider(pc, op):
        nonlocal pool_start, pool_end
        if op >> 12 == 0xD:                       # mov.l @(disp,PC),Rn
            ea = ((pc + 4) & ~3) + (op & 0xFF) * 4
            pool_start = ea if pool_start is None else min(pool_start, ea)
            pool_end = max(pool_end, ea + 4)
        elif op >> 12 == 0x9:                     # mov.w @(disp,PC),Rn
            ea = (pc + 4) + (op & 0xFF) * 2
            pool_start = ea if pool_start is None else min(pool_start, ea)
            pool_end = max(pool_end, ea + 2)
    for rec in records:
        consider(rec['pc'], rec['op'])
        slot = rec.get('slot')
        if slot is not None:
            consider(slot['pc'], slot['op'])
    if pool_start is not None and pool_start < fallback + 4:
        return pool_end                       # sentinel would shadow a pool byte
    return fallback


def _norm_py(parts):
    """Normalize mapper py fragments for the mirror CODE dict.

    Some c_lift_ops templates embed newline + indentation inside ONE py
    fragment (div1/addc/subc/negc/cmp-str/div0s/shll/rotcl/... — every
    multi-line 'T'-expression template).  exec()ing such a fragment at module
    indentation level raises ``IndentationError: unexpected indent`` on the
    indented continuation line.  Every line is a complete simple statement (or
    a one-line compound such as ``if t1 == 0: t2 = r[0]``), so stripping the
    leading whitespace of each line is semantics-preserving (T stays the
    integer 0/1 the mapper produces)."""
    out = []
    for frag in parts:
        for ln in frag.split('\n'):
            s = ln.strip()
            if s:
                out.append(s)
    return '\n'.join(out)


def _code_literal(records):
    """Render the interpreter's CODE = {addr: inst} dict as Python source."""
    lines = []
    for rec in records:
        pc = rec['pc']
        if rec['kind'] == 'branch':
            bi = ops.branch_info(rec['op'])
            bkind = bi['kind']
            slot = rec.get('slot')
            slot_py = _norm_py(slot['py']) if slot and slot.get('py') else None
            if bkind == 'rts':
                lines.append('    %#x: {"kind": "ret", "py": None, '
                             '"slot_py": %r, "target": None, "cond": None},'
                             % (pc, slot_py))
            elif bkind in ('bsrf', 'braf'):
                # dynamic branch: the mirror executes the delay slot, then (for
                # bsrf) sets pr = P+4, then pc = P+4 + r[reg] — sh2emu's
                # _delayed().  The interpreter's 'dynbranch' case performs the
                # pc update itself (pc is an interpreter local, not in ns).
                lines.append('    %#x: {"kind": "dynbranch", "py": None, '
                             '"slot_py": %r, "target": None, "cond": None, '
                             '"reg": %d, "set_pr": %r},'
                             % (pc, slot_py, bi['reg'], bkind == 'bsrf'))
            else:
                lines.append('    %#x: {"kind": "branch", "py": None, '
                             '"slot_py": %r, "target": %#x, "cond": %r},'
                             % (pc, slot_py, rec['target'], _BRANCH_COND[bkind]))
        else:
            py = _norm_py(rec.get('py') or []) or None
            lines.append('    %#x: {"kind": %r, "py": %r, "slot_py": None, '
                         '"target": None, "cond": None},'
                         % (pc, _MIRROR_KIND[rec['kind']], py))
    return 'CODE = {\n%s}\n' % '\n'.join(lines)


def emit_v3_test(addr, name, size, rom, records, info, seed, out_t,
                 cases=2000, rom_path=None):
    """Write c/tests/test_<name>_<addr>.py for one compile-gated v3 lift.
    `rom_path` lets the generated harness read the correct ROM bank (the
    standalone harness needs the real bytes; default 60E1D400)."""
    fn = gcl.sanitize(name)
    raw = rom[addr:addr + size]
    flat = ' '.join('%02X' % b for b in raw)

    offs_list = sorted(info['stack_offs'])
    stack_offs = ', '.join('0x%X' % o for o in offs_list)
    if len(offs_list) == 1:
        stack_offs += ','                     # (0x414,) must stay a tuple
    # sys-form stack LOAD slots (lds.l @r15+/@r14+, pr/macl/mach).  These pop a
    # slot the function never wrote (no sts.l epilogue in these catalog-boundary
    # fragments), so without seeding pr lands on prefill garbage and the emulator's
    # rts jumps to a random pc -> every case is skipped.  Seed the slot with the
    # sh2emu return sentinel 0xEEEE0000 (exactly what call() initialises pr to) so
    # the load round-trips into the rts and the test actually compares the lds.l
    # emission against sh2emu.  Both sides read the same ram; the sentinel bytes
    # are masked out of the RAM comparison (harness input, not function output).
    seed_offs = []
    for rec in records:
        if rec.get('kind') != 'mem':
            continue
        if (rec.get('op', 0) & 0xF0FF) not in (0x4006, 0x4016, 0x4026):
            continue
        for py in rec.get('py') or ():
            if '_rdw(ram, STACK_BASE + 0x' in py:
                off = int(py.split('STACK_BASE + 0x')[1].split(',')[0], 16)
                if off not in seed_offs:
                    seed_offs.append(off)
                break
    seed_offs.sort()
    seed_offs_s = ', '.join('0x%X' % o for o in seed_offs)
    if len(seed_offs) == 1:
        seed_offs_s += ','                     # (0x400,) must stay a tuple
    if not seed_offs:
        seed_offs_s = '()'
    ram_addrs = [v for v in info['ram_addrs'] if ops.classify_addr(v) == 'RAM']
    ram_min = min(ram_addrs) if ram_addrs else None
    ram_max = max(ram_addrs) if ram_addrs else None

    end_addr = addr + size
    # Stop-sentinel address: past the last instruction (end) AND past any real
    # PC-relative literal-pool byte the function reads.  Writing it at `end`
    # shadows literals that live right after the span (mov.w/mov.l @(dis,PC)),
    # so the emulator would read 00 0B/00 09 sentinel bytes where the mirror
    # reads the true ROM literal -> spurious FFFFxxxx vs 00000009/0B mismatches.
    sent_addr = _pool_end(records, end_addr)

    test = (
        '#!/usr/bin/env python3\n'
        '"""Differential test for %s (0x%X) — v3 lift (branches + delay slots), %d bytes.\n'
        'Auto-generated by tools/gen_c_lift_v3.py — not human-verified.\n'
        'Compares a Python pc-interpreter spec_mirror against the sh2emu oracle\n'
        '(which runs the actual ROM bytes) over %d random inputs: deterministic RAM\n'
        'prefill around the literal addresses plus a synthetic 0x400-byte stack at\n'
        'STACK_BASE.  Branch cond is sampled on T BEFORE the delay slot (as sh2emu);\n'
        'cases where either side leaves the modeled span / exceeds max_steps are\n'
        'skipped (StepLimitExceeded -> skip).\n'
        'Run from repo root: python3 c/tests/test_%s_%x.py\n'
        '"""\n'
        'import os, random, sys\n\n'
        'ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n'
        'sys.path.insert(0, os.path.join(ROOT, "tools"))\n'
        'from sh2emu import SH2, StepLimitExceeded\n'
        'from c_lift_ops import s8, s16, s32\n\n'
        'ROM = os.path.join(ROOT, "roms", "stock", "60E1D400.bin")\n'
        'ROM_BYTES = open(ROM, "rb").read()\n'
        'ENTRY = 0x%X\n'
        'RAW = bytes.fromhex("%s")\n'
        'SEED = %d\n'
        'N = %d\n'
        'MAXSTEPS = 100000\n'
        'STACK_BASE = 0xFFFFD000\n'
        'STACK_TOP = STACK_BASE + 0x400\n'
        'STACK_OFFS = (%s)\n'
        'SEED_OFFS = (%s)   # lds.l pr/macl/mach slots seeded with the return sentinel\n'
        'RAM_MIN = %s\n'
        'RAM_MAX = %s\n'
        'SPAN_END = 0x%X\n'
        'SENT = 0x%X     # stop-sentinel, placed past the literal pool\n\n'
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
        'def spec_mirror(r4, r5, r6, r7, ram, gbr=0):\n'
        '    """pc-interpreter over CODE; returns ("RET", regs, writes, ram, pr) or\n'
        '    ("SKIP"/"ERR", detail).  Every instruction is the mapper py fragment\n'
        '    exec\'d in a shared ns (registers/T/ram/writes follow sh2emu)."""\n'
        '    global _WRITES\n'
        '    _WRITES[:] = []\n'
        '    r = [0] * 16\n'
        '    r[4], r[5], r[6], r[7] = r4 & 0xFFFFFFFF, r5 & 0xFFFFFFFF, r6 & 0xFFFFFFFF, r7 & 0xFFFFFFFF\n'
        '    r[15] = STACK_TOP & 0xFFFFFFFF\n'
        '    ns = {"r": r, "T": 0, "Q": 0, "M": 0, "mach": 0, "macl": 0, "pr": 0xEEEE0000,\n'
        '          "sr": 0x000000F0,  # sh2emu call() default (independent of T)\n'
        '          "s8": s8, "s16": s16, "s32": s32, "ram": ram, "sp": r[15],\n'
        '          "gbr": gbr & 0xFFFFFFFF,\n'
        '          "local": {off: _rdw(ram, STACK_BASE + off, 4) for off in STACK_OFFS},\n'
        '          "_rdw": _rdw, "_wrw": _wrw, "STACK_BASE": STACK_BASE}\n'
        '    pc = ENTRY\n'
        '    steps = 0\n'
        '    while True:\n'
        '        steps += 1\n'
        '        if steps > MAXSTEPS:\n'
        '            return ("SKIP", None)\n'
        '        inst = CODE.get(pc)\n'
        '        if inst is None:\n'
        '            return ("ERR", pc)\n'
        '        kind = inst["kind"]\n'
        '        if kind == "branch":\n'
        '            t = ns["T"]\n'
        '            cond = inst["cond"]\n'
        '            taken = True\n'
        '            if cond == "T":\n'
        '                taken = (t == 1)\n'
        '            elif cond == "notT":\n'
        '                taken = (t == 0)\n'
        '            slot_py = inst["slot_py"]\n'
        '            if slot_py:\n'
        '                exec(slot_py, ns)\n'
        '            if taken:\n'
        '                pc = inst["target"]\n'
        '            elif slot_py is not None:\n'
        '                pc = pc + 4            # delayed: slot at P+2 already ran\n'
        '            else:\n'
        '                pc = pc + 2            # non-delayed bt/bf\n'
        '        elif kind == "dynbranch":\n'
        '            slot_py = inst["slot_py"]\n'
        '            if slot_py:\n'
        '                exec(slot_py, ns)\n'
        '            if inst["set_pr"]:\n'
        '                ns["pr"] = (pc + 4) & 0xFFFFFFFF\n'
        '            pc = (pc + 4 + ns["r"][inst["reg"]]) & 0xFFFFFFFF\n'
        '        elif kind == "ret":\n'
        '            slot_py = inst["slot_py"]\n'
        '            if slot_py:\n'
        '                exec(slot_py, ns)\n'
        '            r[15] = ns["sp"] & 0xFFFFFFFF\n'
        '            return ("RET", [x & 0xFFFFFFFF for x in r], _WRITES, ram, ns["pr"] & 0xFFFFFFFF,\n'
        '                    ns["macl"] & 0xFFFFFFFF, ns["mach"] & 0xFFFFFFFF)\n'
        '        else:\n'
        '            py = inst["py"]\n'
        '            if py:\n'
        '                exec(py, ns)\n'
        '            pc = pc + 2\n\n'
        'def run(cpu, ram, a, b, c_, d, gbr=0):\n'
        '    ram = dict(ram)\n'
        '    ram[SENT] = 0x00; ram[SENT + 1] = 0x0B; ram[SENT + 2] = 0x00; ram[SENT + 3] = 0x09\n'
        '    cpu.call(ENTRY, r4=a, r5=b, r6=c_, r7=d, ram=ram, regs={15: STACK_TOP, "gbr": gbr},\n'
        '             max_steps=MAXSTEPS)\n'
        '    out = dict(cpu.ram)\n'
        '    for i in range(4):\n'
        '        out.pop(SENT + i, None)\n'
        '    return (cpu.r[0] & 0xFFFFFFFF, [x & 0xFFFFFFFF for x in cpu.r], out,\n'
        '            cpu.pr & 0xFFFFFFFF, cpu.macl & 0xFFFFFFFF,\n'
        '            cpu.mach & 0xFFFFFFFF)\n\n'
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
        '        for off in SEED_OFFS:\n'
        '            for i in range(4):\n'
        '                ram[STACK_BASE + off + i] = (0xEEEE0000 >> (8 * (3 - i))) & 0xFF\n'
                '        a = rnd.randint(0, 0xFFFFFFFF)\n'
        '        b = rnd.randint(0, 0xFFFFFFFF)\n'
        '        c_ = rnd.randint(0, 0xFFFFFFFF)\n'
        '        d = rnd.randint(0, 0xFFFFFFFF)\n'
        '        gbr = rnd.randint(0, 0xFFFFFFFF)\n'
        '        m = spec_mirror(a, b, c_, d, dict(ram), gbr)\n'
        '        if m[0] != "RET":\n'
        '            skipped += 1\n'
        '            continue\n'
        '        try:\n'
        '            g = run(cpu, ram, a, b, c_, d, gbr)\n'
        '        except (StepLimitExceeded, NotImplementedError, RuntimeError):\n'
        '            skipped += 1\n'
        '            continue\n'
        '        _, exp_regs, _, exp_ram, exp_pr, exp_macl, exp_mach = m\n'
        '        _, got_regs, got_ram, got_pr, got_macl, got_mach = g\n'
        '        for i in range(16):\n'
        '            if exp_regs[i] != got_regs[i]:\n'
        '                print("MISMATCH case=%%d reg=r%%d mirror=%%08X emu=%%08X" %% (caso, i, exp_regs[i], got_regs[i]))\n'
        '                sys.exit(1)\n'
        '        if exp_pr != got_pr:\n'
        '            print("MISMATCH case=%%d reg=pr mirror=%%08X emu=%%08X" %% (caso, exp_pr, got_pr))\n'
        '            sys.exit(1)\n'
        '        if exp_macl != got_macl:\n'
        '            print("MISMATCH case=%%d reg=macl mirror=%%08X emu=%%08X" %% (caso, exp_macl, got_macl))\n'
        '            sys.exit(1)\n'
        '        if exp_mach != got_mach:\n'
        '            print("MISMATCH case=%%d reg=mach mirror=%%08X emu=%%08X" %% (caso, exp_mach, got_mach))\n'
        '            sys.exit(1)\n'
        '        for ad in sorted(set(exp_ram) | set(got_ram)):\n'
        '            if any(STACK_BASE + off <= ad < STACK_BASE + off + 4 for off in SEED_OFFS):\n'
        '                continue\n'
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
    ) % (fn, addr, size, cases, fn, addr, addr, flat, seed, cases, stack_offs,
          seed_offs_s,
'None' if ram_min is None else '0x%X' % ram_min,
          'None' if ram_max is None else '0x%X' % ram_max,
          end_addr, sent_addr,
          _code_literal(records))

    rom_label = os.path.splitext(os.path.basename(rom_path))[0] if rom_path \
        else '60E1D400'
    test = test.replace('"60E1D400.bin"', '"%s.bin"' % rom_label)
    with open(out_t, 'w') as f:
        f.write(test)
    return True


# ---------------------------------------------------------------------------
# v4 FPU test emission: c/tests/test_<name>_<addr>.py — the v3 pc-interpreter
# spec_mirror extended with the FR state.  spec_mirror(r4,r5,r6,r7,ram,fr_in)
# takes fr_in = 16 uint32 IEEE-754 bit patterns (the C lift holds FRs as
# bit-pattern uint32 locals); the mirror converts them to float32 values with
# bits2f (sh2emu semantics — decode_fpu's py fragments operate on float32 like
# the emulator), runs the mapper py fragments (ts/f2bits/bits2f/s32 + _rdw/
# _wrw for the fmov.s memory forms), and returns ("RET", regs, writes, ram, pr,
# fr_bits, fpul) where fr_bits = [f2bits(f) for f in fr] (exact bit patterns).
# main() seeds FR input deterministically per case:
#   fr_in[i] = (case*0x9E3779B1 + i*0x1000003) & 0xFFFFFFFF
#   then NaN/Inf-free filtered: (x & 0x7F7FFFFF) | 0x3F800000
#   — clears the sign bit and forces exponent < 0xFF so no -0.0 edge/NaN/Inf
#   (every bit pattern is a finite, positive float32; the OR keeps the value
#   >= 1.0 magnitude so denormal corner cases never enter the comparison).
# The sh2emu oracle is fed the SAME bit patterns as float32 values:
#   cpu.call(..., fr={i: bits2f(fr_in[i]) for i in range(16)}, ...).
# Comparison: r0..r15, the 16 FR bit patterns, fpul, pr and every written RAM
# address (T is not part of the state call() exposes — not compared).
# fsqrt on a negative input makes both sides raise ValueError (Python complex
# branch of **0.5 / the C sqrtf domain) -> those cases are counted as skips.
# ---------------------------------------------------------------------------
def emit_fpu_test(addr, name, size, rom, records, info, seed, out_t,
                  cases=2000, rom_path=None):
    """Write c/tests/test_<name>_<addr>.py for a v3 lift whose span holds FPU
    ops (mirror + oracle both track FR)."""
    fn = gcl.sanitize(name)
    raw = rom[addr:addr + size]
    flat = ' '.join('%02X' % b for b in raw)

    offs_list = sorted(info['stack_offs'])
    stack_offs = ', '.join('0x%X' % o for o in offs_list)
    if len(offs_list) == 1:
        stack_offs += ','                     # (0x414,) must stay a tuple
    ram_addrs = [v for v in info['ram_addrs'] if ops.classify_addr(v) == 'RAM']
    ram_min = min(ram_addrs) if ram_addrs else None
    ram_max = max(ram_addrs) if ram_addrs else None

    end_addr = addr + size
    sent_addr = _pool_end(records, end_addr)

    test = (
        '#!/usr/bin/env python3\n'
        '"""Differential test for %s (0x%X) — v3 lift + v4 FPU, %d bytes.\n'
        'Auto-generated by tools/gen_c_lift_v3.py — not human-verified.\n'
        'Compares a Python pc-interpreter spec_mirror against the sh2emu oracle\n'
        '(which runs the actual ROM bytes) over %d random inputs: deterministic RAM\n'
        'prefill around the literal addresses plus a synthetic 0x400-byte stack at\n'
        'STACK_BASE.  FR inputs are seeded per case as 16 uint32 bit patterns\n'
        'fr_in[i] = (case*0x9E3779B1 + i*0x1000003) & 0xFFFFFFFF, filtered with\n'
        '(x & 0x7F7FFFFF) | 0x3F800000 to keep every value a finite positive\n'
        'float32 (sign cleared, exponent < 0xFF — no NaN/Inf/-0.0 in the diff).\n'
        'The mirror converts bit patterns to float32 via bits2f (sh2emu\n'
        'semantics); the oracle is fed the same patterns as float values via\n'
        'cpu.call(..., fr={i: bits2f(fr_in[i]) ...}).  Compared: r0..r15, the 16\n'
        'FR bit patterns (f2bits), fpul, pr and every written RAM address (T is\n'
        'not part of the state call() exposes).  fsqrt of a negative input raises\n'
        'ValueError on both sides -> counted as skip.  Branch cond is sampled on T\n'
        'BEFORE the delay slot (as sh2emu); cases where either side leaves the\n'
        'modeled span / exceeds max_steps are skipped.\n'
        'Run from repo root: python3 c/tests/test_%s_%x.py\n'
        '"""\n'
        'import os, random, sys\n\n'
        'ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n'
        'sys.path.insert(0, os.path.join(ROOT, "tools"))\n'
        'from sh2emu import SH2, StepLimitExceeded\n'
        'from c_lift_ops import s8, s16, s32, ts, bits2f, f2bits\n\n'
        'ROM = os.path.join(ROOT, "roms", "stock", "60E1D400.bin")\n'
        'ROM_BYTES = open(ROM, "rb").read()\n'
        'ENTRY = 0x%X\n'
        'RAW = bytes.fromhex("%s")\n'
        'SEED = %d\n'
        'N = %d\n'
        'MAXSTEPS = 100000\n'
        'STACK_BASE = 0xFFFFD000\n'
        'STACK_TOP = STACK_BASE + 0x400\n'
        'STACK_OFFS = (%s)\n'
        'RAM_MIN = %s\n'
        'RAM_MAX = %s\n'
        'SPAN_END = 0x%X\n'
        'SENT = 0x%X     # stop-sentinel, placed past the literal pool\n\n'
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
        'def spec_mirror(r4, r5, r6, r7, ram, fr_in, gbr=0):\n'
        '    """pc-interpreter over CODE; returns ("RET", regs, writes, ram, pr,\n'
        '    fr_bits, fpul) or ("SKIP"/"ERR", detail).  fr_in is 16 uint32 bit\n'
        '    patterns; fr is the float32 mirror (bits2f) the FPU fragments run\n'
        '    on — sh2emu semantics, exact same list the emulator builds from\n'
        '    ts(v) in call()."""\n'
        '    global _WRITES\n'
        '    _WRITES[:] = []\n'
        '    r = [0] * 16\n'
        '    r[4], r[5], r[6], r[7] = r4 & 0xFFFFFFFF, r5 & 0xFFFFFFFF, r6 & 0xFFFFFFFF, r7 & 0xFFFFFFFF\n'
        '    r[15] = STACK_TOP & 0xFFFFFFFF\n'
        '    fr = [bits2f(x) for x in fr_in]\n'
        '    ns = {"r": r, "T": 0, "Q": 0, "M": 0, "mach": 0, "macl": 0, "pr": 0xEEEE0000,\n'
        '          "sr": 0x000000F0,  # sh2emu call() default (independent of T)\n'
        '          "fr": fr, "fpul": 0, "fpscr": 0,\n'
        '          "s8": s8, "s16": s16, "s32": s32, "ts": ts, "bits2f": bits2f,\n'
        '          "f2bits": f2bits, "ram": ram, "sp": r[15],\n'
        '          "gbr": gbr & 0xFFFFFFFF,\n'
        '          "local": {off: _rdw(ram, STACK_BASE + off, 4) for off in STACK_OFFS},\n'
        '          "_rdw": _rdw, "_wrw": _wrw, "STACK_BASE": STACK_BASE}\n'
        '    pc = ENTRY\n'
        '    steps = 0\n'
        '    while True:\n'
        '        steps += 1\n'
        '        if steps > MAXSTEPS:\n'
        '            return ("SKIP", None)\n'
        '        inst = CODE.get(pc)\n'
        '        if inst is None:\n'
        '            return ("ERR", pc)\n'
        '        kind = inst["kind"]\n'
        '        if kind == "branch":\n'
        '            t = ns["T"]\n'
        '            cond = inst["cond"]\n'
        '            taken = True\n'
        '            if cond == "T":\n'
        '                taken = (t == 1)\n'
        '            elif cond == "notT":\n'
        '                taken = (t == 0)\n'
        '            slot_py = inst["slot_py"]\n'
        '            if slot_py:\n'
        '                exec(slot_py, ns)\n'
        '            if taken:\n'
        '                pc = inst["target"]\n'
        '            elif slot_py is not None:\n'
        '                pc = pc + 4            # delayed: slot at P+2 already ran\n'
        '            else:\n'
        '                pc = pc + 2            # non-delayed bt/bf\n'
        '        elif kind == "dynbranch":\n'
        '            slot_py = inst["slot_py"]\n'
        '            if slot_py:\n'
        '                exec(slot_py, ns)\n'
        '            if inst["set_pr"]:\n'
        '                ns["pr"] = (pc + 4) & 0xFFFFFFFF\n'
        '            pc = (pc + 4 + ns["r"][inst["reg"]]) & 0xFFFFFFFF\n'
        '        elif kind == "ret":\n'
        '            slot_py = inst["slot_py"]\n'
        '            if slot_py:\n'
        '                exec(slot_py, ns)\n'
        '            r[15] = ns["sp"] & 0xFFFFFFFF\n'
        '            return ("RET", [x & 0xFFFFFFFF for x in r], _WRITES, ram,\n'
        '                    ns["pr"] & 0xFFFFFFFF,\n'
        '                    [f2bits(f) for f in fr], ns["fpul"] & 0xFFFFFFFF,\n'
        '                    ns["macl"] & 0xFFFFFFFF, ns["mach"] & 0xFFFFFFFF)\n'
        '        else:\n'
        '            py = inst["py"]\n'
        '            if py:\n'
        '                exec(py, ns)\n'
        '            pc = pc + 2\n\n'
        'def run(cpu, ram, a, b, c_, d, fr_in, gbr=0):\n'
        '    ram = dict(ram)\n'
        '    ram[SENT] = 0x00; ram[SENT + 1] = 0x0B; ram[SENT + 2] = 0x00; ram[SENT + 3] = 0x09\n'
        '    cpu.call(ENTRY, r4=a, r5=b, r6=c_, r7=d, ram=ram,\n'
        '             fr={i: bits2f(fr_in[i]) for i in range(16)},\n'
        '             regs={15: STACK_TOP, "gbr": gbr}, max_steps=MAXSTEPS)\n'
        '    out = dict(cpu.ram)\n'
        '    for i in range(4):\n'
        '        out.pop(SENT + i, None)\n'
        '    return (cpu.r[0] & 0xFFFFFFFF, [x & 0xFFFFFFFF for x in cpu.r], out,\n'
        '            cpu.pr & 0xFFFFFFFF,\n'
        '            [f2bits(cpu.fr[i]) for i in range(16)], cpu.fpul & 0xFFFFFFFF,\n'
        '            cpu.macl & 0xFFFFFFFF, cpu.mach & 0xFFFFFFFF)\n\n'
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
        '        a = rnd.randint(0, 0xFFFFFFFF)\n'
        '        b = rnd.randint(0, 0xFFFFFFFF)\n'
        '        c_ = rnd.randint(0, 0xFFFFFFFF)\n'
        '        d = rnd.randint(0, 0xFFFFFFFF)\n'
        '        gbr = rnd.randint(0, 0xFFFFFFFF)\n'
        '        fr_in = [((caso * 0x9E3779B1 + i * 0x1000003) & 0xFFFFFFFF) for i in range(16)]\n'
        '        fr_in = [((x & 0x7F7FFFFF) | 0x3F800000) for x in fr_in]  # finite, positive, no NaN/Inf\n'
        '        try:\n'
        '            m = spec_mirror(a, b, c_, d, dict(ram), fr_in, gbr)\n'
        '        except ValueError:\n'
        '            skipped += 1          # fsqrt of a negative input (both sides)\n'
        '            continue\n'
        '        if m[0] != "RET":\n'
        '            skipped += 1\n'
        '            continue\n'
        '        try:\n'
        '            g = run(cpu, ram, a, b, c_, d, fr_in, gbr)\n'
        '        except (StepLimitExceeded, NotImplementedError, RuntimeError, ValueError):\n'
        '            skipped += 1\n'
        '            continue\n'
        '        _, exp_regs, _, exp_ram, exp_pr, exp_fr, exp_fpul, exp_macl, exp_mach = m\n'
        '        _, got_regs, got_ram, got_pr, got_fr, got_fpul, got_macl, got_mach = g\n'
        '        for i in range(16):\n'
        '            if exp_regs[i] != got_regs[i]:\n'
        '                print("MISMATCH case=%%d reg=r%%d mirror=%%08X emu=%%08X" %% (caso, i, exp_regs[i], got_regs[i]))\n'
        '                sys.exit(1)\n'
        '        for i in range(16):\n'
        '            if exp_fr[i] != got_fr[i]:\n'
        '                print("MISMATCH case=%%d fr%%d mirror=%%08X emu=%%08X" %% (caso, i, exp_fr[i], got_fr[i]))\n'
        '                sys.exit(1)\n'
        '        if exp_fpul != got_fpul:\n'
        '            print("MISMATCH case=%%d fpul mirror=%%08X emu=%%08X" %% (caso, exp_fpul, got_fpul))\n'
        '            sys.exit(1)\n'
        '        if exp_pr != got_pr:\n'
        '            print("MISMATCH case=%%d reg=pr mirror=%%08X emu=%%08X" %% (caso, exp_pr, got_pr))\n'
        '            sys.exit(1)\n'
        '        if exp_macl != got_macl:\n'
        '            print("MISMATCH case=%%d reg=macl mirror=%%08X emu=%%08X" %% (caso, exp_macl, got_macl))\n'
        '            sys.exit(1)\n'
        '        if exp_mach != got_mach:\n'
        '            print("MISMATCH case=%%d reg=mach mirror=%%08X emu=%%08X" %% (caso, exp_mach, got_mach))\n'
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
    ) % (fn, addr, size, cases, fn, addr, addr, flat, seed, cases, stack_offs,
         'None' if ram_min is None else '0x%X' % ram_min,
         'None' if ram_max is None else '0x%X' % ram_max,
         end_addr, sent_addr,
          _code_literal(records))

    rom_label = os.path.splitext(os.path.basename(rom_path))[0] if rom_path \
        else '60E1D400'
    test = test.replace('"60E1D400.bin"', '"%s.bin"' % rom_label)
    with open(out_t, 'w') as f:
        f.write(test)
    return True


def run_test(out_t):
    """Run one generated test from the repo root; returns 'PASS' or 'FAIL'."""
    try:
        r = subprocess.run([sys.executable, out_t], cwd=ROOT,
                           capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return 'FAIL'
    out = (r.stdout or '').strip().splitlines()
    return 'PASS' if r.returncode == 0 and out and out[-1].startswith('PASS') else 'FAIL'


def print_dryrun(pool, counters, args, rom):
    """--dryrun report: pool + rejection reasons + branch breakdown + the
    additive feasibility counters (A/B/C).  Existing numbers are unchanged from
    the baseline; the additive sections only ADD counts."""
    rej = counters['rejected']
    print('=== v3 selection (--dryrun): no files written ===')
    print('pool_v3=%d' % counters['selected'])
    print('  pool_no_span=%d (end estimated as next known catalog addr)'
          % counters.get('pool_no_span', 0))
    print('rejected_total=%d' % sum(rej.values()))
    for r in ('unmapped', 'branch', 'delay_slot_ctrl', 'target_fuori', 'rte',
              'call', 'base_unresolved', 'fpu/altre', 'no_mem_op'):
        print('  rejected_%-15s %d' % (r, rej.get(r, 0)))
    print('skipped_no_span=%d skipped_size=%d skipped_dedup=%d skipped_no_branch=%d'
          % (counters['skipped_no_span'], counters['skipped_size'],
             counters['skipped_dedup'], counters['skipped_no_branch']))
    print('--- branch breakdown (v3 internal-branch admission) ---')
    ba, br = counters.get('branch_ammessi', {}), counters.get('branch_rigettati', {})
    print('  branch_tot=%d (ammessi %d: bt/bf=%d bts/bfs=%d bra=%d rts=%d;'
          ' rigettati %d: delay_slot_ctrl=%d target_fuori=%d rte=%d)'
          % (counters.get('branch_tot', 0), sum(ba.values()),
             ba.get('bt/bf', 0), ba.get('bts/bfs', 0), ba.get('bra', 0),
             ba.get('rts', 0), sum(br.values()),
             br.get('delay_slot_ctrl', 0), br.get('target_fuori', 0),
             br.get('rte', 0)))
    det = counters['motivo_dettaglio']
    if det:
        print('--- base_unresolved residual (motivo_dettaglio) ---')
        for d in ('r15-non-tracked', 'r14-non-frame', 'GBR-non-risolto',
                  'r0-non-literal', 'altro'):
            print('  base_unresolved_%-16s %d' % (d, det.get(d, 0)))
    print('--- first 15 selected (addr, branch types present, size) ---')
    for e in pool[:15]:
        brs = ', '.join(k for k, pc_, t_ in e.get('branches', [])) or 'none'
        print('  0x%06X %-32s size=%3d branches={%s} ops=%d'
              % (e['addr'], e['name'], e['size'], brs, len(e['ops'])))
    print('options: --n %d --seed %d' % (args.n, args.seed))

    # ---- additive feasibility counters (never change selection) ----
    pool_n = counters['selected']
    print('=== additive counters (feasibility only; selection unchanged) ===')
    # A) SPAN-END: among target_fuori-rejected functions, out-of-span targets
    #    all within [end, end+8] / [end, end+16] (catalog `end` under-guesses
    #    the real function end).
    f8 = counters.get('fuori_vicini_8', 0)
    f16 = counters.get('fuori_vicini_16', 0)
    print('A) fuori_vicini(<=8)=%d  fuori_vicini(<=16)=%d' % (f8, f16))
    print('   pool_endfix (pool_v3 + <=8) = %d' % (pool_n + f8))
    # B) COPIA-CATENA: among base_unresolved-rejected functions whose base
    #    register is derivable via pure mov-copy / literal chain.
    ch = counters.get('chain_resolvable', 0)
    print('B) chain_resolvable=%d  pool_chain (pool_v3 + chain_resolvable) = %d'
          % (ch, pool_n + ch))
    # C) UNMAPPED LIST: all mapper-unrecognized opcodes in unmapped-rejected
    #    functions, top 20 by count, tagged with whether sh2emu executes them.
    um = counters.get('unmapped_opcodes')
    if um:
        print('C) unmapped opcodes in unmapped-rejected fns (top 20, cur=%d distinct)'
              % len(um))
        for op, cnt in um.most_common(20):
            print('   0x%04X  %6d  emu:%s'
                  % (op, cnt, 'yes' if _emu_executes(rom, op) else 'no'))

    # ---- v4 additive: sanitized-span pool (dryrun only; v3 untouched) ----
    v4p = counters.get('v4_pool')
    v4c = counters.get('v4')
    if v4p is not None and v4c is not None:
        print('=== v4 sanitized-span selection (additive; v3 counters above'
              ' untouched) ===')
        print('pool_v4=%d   (pool_v3=%d + sanitized-span rescues)'
              % (len(v4p), pool_n))
        v4rej = v4c['rejected']
        print('  v4 rejected_total=%d' % sum(v4rej.values()))
        for r in ('unmapped', 'branch', 'delay_slot_ctrl', 'target_fuori',
                  'rte', 'call', 'base_unresolved', 'fpu/altre', 'no_mem_op'):
            print('  v4 rejected_%-15s %d' % (r, v4rej.get(r, 0)))
        print('  v4 skipped_size=%d skipped_dedup=%d skipped_no_branch=%d'
              % (v4c['skipped_size'], v4c['skipped_dedup'],
                 v4c['skipped_no_branch']))
        tr_ = v4c['n_trimmed'] + v4c['n_extended'] + v4c['n_entrambi']
        print('  sanitize breakdown (of pool_v4): trimmed=%d extended=%d'
              ' both=%d untouched=%d'
              % (v4c['n_trimmed'], v4c['n_extended'], v4c['n_entrambi'],
                 len(v4p) - tr_))
        print('  n_over_160 (end_s-addr in (160,176]) = %d' % v4c['n_over_160'])
        fuori8_set = counters.get('_fuori8_addrs') or set()
        v4_addrs = {e['addr'] for e in v4p}
        print('  fuori_vicini_8 now selectable: %d/%d'
              ' (v3 additive counter A: %d)'
              % (sum(1 for a in fuori8_set if a in v4_addrs),
                 len(fuori8_set), counters.get('fuori_vicini_8', 0)))
        ex = v4c['examples']
        if ex:
            print('  examples (first %d sanitized selectable):' % len(ex))
            for addr, name, end_o, end_s, reasons, in_v3 in ex:
                print('    0x%06X %-32s %-18s end 0x%X -> 0x%X%s'
                      % (addr, name, '+'.join(reasons), end_o, end_s,
                         '' if in_v3 else '  [new, not in v3 pool]'))

    # ---- FPU additive: pool_fpu if mapped FPU ops were allowed (dryrun only) ----
    fp = counters.get('fpu_pool')
    fc = counters.get('fpu')
    if fp is not None and fc is not None:
        print('=== FPU pool measurement (additive; selection unchanged: FPU'
              ' functions still rejected until emission) ===')
        print('pool_fpu=%d   (pool_v4=%d + fpu_gained=%d)'
              % (len(fp), len(v4p) if v4p is not None else -1,
                 len(fp) - len(v4p) if v4p is not None else -1))
        print('  fpu_used=%d (span+size+dedup candidates holding any FPU op):'
              ' fpu_only=%d fpu_calls=%d fpu_bases=%d fpu_other=%d'
              ' fpu_no_branch=%d'
              % (fc.get('fpu_used', 0), fc.get('fpu_only', 0),
                 fc.get('fpu_calls', 0), fc.get('fpu_bases', 0),
                 fc.get('fpu_other', 0), fc.get('fpu_no_branch', 0)))
        fpu_rej = fc['rejected']
        print('  fpu rejected_total=%d' % sum(fpu_rej.values()))
        for r in ('call', 'base_unresolved', 'fpu/altre', 'unmapped', 'rte',
                  'delay_slot_ctrl', 'target_fuori', 'no_mem_op', 'branch'):
            if fpu_rej.get(r):
                print('    rejected_%-15s %d' % (r, fpu_rej.get(r)))
        ex = fc['examples']
        if ex:
            print('  examples (first %d FPU-using, in pool_fpu):' % len(ex))
            for addr, name in ex:
                print('    0x%06X %-32s' % (addr, name))

    # ---- additive (a): TRAILING-RTS (dryrun only; selection unchanged) ----
    tr = counters.get('trailing_rts')
    if tr is not None:
        print('=== trailing-rts measurement (additive; selection unchanged) ===')
        print('  trailing_rts_n=%d   (rts 0x000B in end..end+16 of v3 rejects'
              ' size/no_span/target_fuori/skipped; no_span has no end -> n/a)'
              % tr['n'])
        print('  rescued=%d   pool_rts (pool_v3 + rescued) = %d'
              % (tr['rescued'], pool_n + tr['rescued']))
        if tr['examples']:
            print('  examples (first %d trailing-rts rescued):' % len(tr['examples']))
            for addr, name, end_o, rts_addr, motif in tr['examples']:
                print('    0x%06X %-32s end 0x%X -> rts 0x%X (%s)'
                      % (addr, name, end_o, rts_addr, motif))

    # ---- additive (b): UNMAPPED-REALI (dryrun only; selection unchanged) ----
    um = counters.get('unmapped_reali')
    if um is not None:
        print('=== unmapped-reali measurement (additive; selection unchanged) ===')
        print('  unmapped_reali=%d   (v3 unmapped rejects whose span has ONLY'
              ' sh2emu-executable opcodes, no call/rte/fpu)'
              % um['n'])
        print('  pool_unmap (pool_v3 + unmapped_reali) = %d' % (pool_n + um['n']))
        top = um['top']
        if top:
            print('  top-10 opcodes involved:')
            for op, cnt in top.most_common(10):
                print('    0x%04X  %6d  emu:yes' % (op, cnt))
        if um['examples']:
            print('  examples (first %d):' % len(um['examples']))
            for addr, name, end_s, ops_l in um['examples']:
                print('    0x%06X %-32s end_s 0x%X unmapped %s'
                      % (addr, name, end_s,
                         ' '.join('0x%04X' % o for o in ops_l[:8])))


def main():
    ap = argparse.ArgumentParser(
        description='Generate v3 C lifts (branches + delay slots) for SH-2 functions')
    ap.add_argument('--category', default=None,
                    help='filter by FUNCTION_CATEGORIES category')
    ap.add_argument('--n', type=int, default=1,
                    help='number of functions to lift')
    ap.add_argument('--seed', type=int, default=0,
                    help='RNG seed (deterministic selection)')
    ap.add_argument('--cases', type=int, default=2000,
                    help='number of random test cases N in each generated test '
                         '(default 2000)')
    ap.add_argument('--addr', default=None,
                    help='lift only this addr (hex, e.g. 0x1234)')
    ap.add_argument('--rom', default=DEFAULT_ROM,
                    help='ROM file (default roms/stock/60E1D400.bin)')
    ap.add_argument('--dryrun', action='store_true',
                    help='select/count only, write no files')
    ap.add_argument('--outdir', default='c',
                    help='output directory for the .c files (default c/)')
    args = ap.parse_args()

    rom = open(args.rom, 'rb').read()
    rom_label = os.path.splitext(os.path.basename(args.rom))[0]
    cat_path = os.path.join(ROOT, 'symbols', 'CATALOG_MASTER.csv')
    catalog_bank, no_spans, bounds = load_catalog_nospans(cat_path)
    # v5: the catalog stores each function PER BANK; a 60E0FC00 row may lack the
    # end its 60E1D400 twin has.  Lookups use THIS bank's table + boundaries.
    catalog = catalog_bank.get(rom_label, {})
    end_bounds = bounds.get(rom_label)
    categories = gcl.load_categories(os.path.join(ROOT, 'symbols', 'FUNCTION_CATEGORIES.csv'))

    if args.addr is not None:
        addr = int(args.addr, 16)
        cands = [c for c in categories if c['addr'] == addr]
        if not cands:
            print('error: addr 0x%X not in FUNCTION_CATEGORIES.csv' % addr)
            sys.exit(2)
    else:
        cands = categories
        if args.category:
            cands = [c for c in cands if c['category'] == args.category]
        else:
            # v5 (additive): catalog no-span functions of the ROM's bank are
            # candidates too (they have no catalog end; end gets estimated).
            cands = _merge_nospan_cands(cands, no_spans, bounds, rom_label)

    outdir = args.outdir if os.path.isabs(args.outdir) else os.path.join(ROOT, args.outdir)
    # v4: the FPU-aware scan is now the REAL selector — functions whose span
    # holds decode_fpu-mappable FPU ops are admitted (call/unmapped/base rules
    # unchanged); non-FPU functions take the identical v3 path.
    selected, counters = select_fpu(cands, rom, catalog, outdir=outdir,
                                    max_n=args.n, seed=args.seed,
                                    end_bounds=end_bounds)
    if args.dryrun:
        # "pool attuale" baseline = the classic v3 selection (counters carry
        # the rejected/skipped/branch breakdown print_dryrun reports); the
        # sanitized-span, FPU, trailing-rts and unmapped-reali pools are
        # ADDITIVE dryrun-only measurements that never affect selection.
        v3_pool, v3_counters = select_v3(cands, args.n, args.seed, rom, catalog,
                                         outdir=outdir, root=ROOT,
                                         end_bounds=end_bounds)
        # v4 additive measurement: sanitized-span pool (never affects emission)
        v4_pool, v4_counters = select_v4_sanitized(
            cands, rom, catalog, outdir=outdir, root=ROOT, v3_pool=v3_pool)
        v3_counters['v4_pool'] = v4_pool
        v3_counters['v4'] = v4_counters
        # FPU additive measurement: pool_fpu if mapped FPU ops were allowed
        # (rescue disabled so the additive pool reflects the baseline criteria)
        fpu_pool, fpu_counters = select_fpu(cands, rom, catalog, outdir=outdir,
                                            root=ROOT, rescue_trailing_rts=False,
                                            end_bounds=end_bounds)
        v3_counters['fpu_pool'] = fpu_pool
        v3_counters['fpu'] = fpu_counters
        # additive (a): TRAILING-RTS — trailing rts rescue with end extended
        rts_n, rts_rescued, rts_ex = scan_with_end_ext(
            cands, rom, catalog, outdir=outdir, root=ROOT)
        v3_counters['trailing_rts'] = {'n': rts_n, 'rescued': rts_rescued,
                                       'examples': rts_ex}
        # additive (b): UNMAPPED-REALI — mapper-unmapped but emu-executable
        unmap_n, unmap_top, unmap_ex = scan_unmapped_reali(
            cands, rom, catalog, outdir=outdir, root=ROOT)
        v3_counters['unmapped_reali'] = {'n': unmap_n, 'top': unmap_top,
                                         'examples': unmap_ex}
        print_dryrun(v3_pool, v3_counters, args, rom)
        return

    if args.addr is not None and not selected:
        print('error: addr 0x%X is not v3-liftable (run --dryrun for the reason)'
              % addr)
        sys.exit(2)

    emitted = dropped = 0
    report = []
    for e in selected:
        base = gcl.sanitize(e['name'])
        lf = '%s_%x' % (base, e['addr'])
        out_c = os.path.join(outdir, lf + '.c')
        if not emit_v3(e['addr'], e['name'], e['size'], rom, out_c,
                       rom_label=rom_label, estimated_end=e.get('estimated_end')):
            dropped += 1
            report.append((lf, 'dropped_compile'))
            continue
        emitted += 1
        print('lifted 0x%X %-40s size=%3d end_s=0x%X -> %s'
              % (e['addr'], e['name'], e['size'], e['end_s'], out_c))
        out_t = os.path.join(ROOT, 'c', 'tests', 'test_%s_%x.py' % (base, e['addr']))
        walked = walk_v3(rom, e['addr'], e['addr'] + e['size'])
        if walked is None:                       # cannot happen after emit_v3
            report.append((lf, 'test_skipped'))
            continue
        records, info, labels = walked
        has_fpu = _records_have_fpu(records)     # includes delay-slot FPU ops
        if has_fpu:
            if emit_fpu_test(e['addr'], e['name'], e['size'], rom, records, info,
                             args.seed, out_t, cases=args.cases, rom_path=args.rom):
                res = run_test(out_t)
                report.append((lf, res))
                print('test 0x%X %-40s -> %s %s' % (e['addr'], e['name'], res, out_t))
            else:
                report.append((lf, 'test_write_failed'))
        else:
            if emit_v3_test(e['addr'], e['name'], e['size'], rom, records, info,
                            args.seed, out_t, cases=args.cases, rom_path=args.rom):
                res = run_test(out_t)
                report.append((lf, res))
                print('test 0x%X %-40s -> %s %s' % (e['addr'], e['name'], res, out_t))
            else:
                report.append((lf, 'test_write_failed'))
    print('emitted=%d dropped_compile=%d' % (emitted, dropped))
    n_nospan = sum(1 for e in selected if e.get('estimated_end'))
    if n_nospan:
        print('no-span lifts in batch=%d (end estimated as next known catalog addr)'
              % n_nospan)
    tr_ = (counters.get('n_trimmed', 0) + counters.get('n_extended', 0)
           + counters.get('n_entrambi', 0))
    print('sanitized-span (of selected): trimmed=%d extended=%d both=%d untouched=%d'
          % (counters.get('n_trimmed', 0), counters.get('n_extended', 0),
             counters.get('n_entrambi', 0), emitted - tr_))
    if counters.get('rescued_trailing_rts'):
        print('(A) trailing-rts rescued=%d (span extended through a trailing rts'
              ' in [catalog_end, +16))' % counters['rescued_trailing_rts'])
    if report:
        g = sum(1 for _, r in report if r == 'PASS')
        f = sum(1 for _, r in report if r == 'FAIL')
        print('test report: generated=%d pass=%d fail=%d' % (len(report), g, f))
        for name, res in report:
            print('  %-10s %s' % (res, name))


if __name__ == '__main__':
    main()
