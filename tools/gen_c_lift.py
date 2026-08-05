#!/usr/bin/env python3
"""
gen_c_lift.py — deterministic CLI that lifts PURE straight-line SH-2 functions
from the RX-8 ECU ROM into C (c/<name>_<addr>.c) plus a differential spec_mirror
test (c/tests/test_<name>_<addr>.py) that checks the Python mirror against the
sh2emu oracle over 2000 random inputs.

Semantics for every instruction come from tools/c_lift_ops.py (big-endian
SH-2) — that table mirrors tools/sh2emu.py exactly, so a lift generated here is
guaranteed to agree with the emulator.  Only opcodes the mapper accepts (its
pure straight-line set: register/literal/PC-pool/T-flag ops; statement dicts
carry no 'kind' key) are lifted; any unsupported/branch/return/memory opcode
terminates the pure span, so the lifted body is genuinely "no calls, no memory
side effects".

Usage:
    python3 tools/gen_c_lift.py [--category CAN Bus] [--n 10] [--seed 0] [--addr 0x1234]
    python3 tools/gen_c_lift.py --mode pure --dryrun --category "Math / FPU" --n 1
    python3 tools/gen_c_lift.py --mode mem --dryrun --category "CAN Bus" --n 20
    python3 tools/gen_c_lift.py --stats
"""
import argparse
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
sys.path.insert(0, os.path.join(ROOT, 'c', 'tests'))

import c_lift_ops as ops

MASK = 0xFFFFFFFF
ROM_LABEL = '60E1D400'
MAX_INSTR = 48          # size cap: <= 96 bytes / 2
MIN_LEN, MAX_LEN = 8, 96
N_CASES = 2000


def load_catalog_end(path):
    """CATALOG_MASTER.csv -> {addr: end}, dropping NOISE rows."""
    m = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            if (row.get('flag') or '').strip() == 'NOISE':
                continue
            try:
                addr = int(row['addr'].strip(), 16)
            except (ValueError, TypeError):
                continue
            try:
                m[addr] = int(row['end'].strip(), 16)
            except (ValueError, TypeError):
                m[addr] = None
    return m


def load_categories(path):
    """FUNCTION_CATEGORIES.csv -> list of {addr, name, category}."""
    rows = []
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                addr = int(row['addr'].strip(), 16)
            except (ValueError, TypeError):
                continue
            rows.append({
                'addr': addr,
                'name': (row.get('name') or '').strip(),
                'category': (row.get('category') or '').strip(),
            })
    return rows


def decode_pure_span(rom, addr, end):
    """Decode the maximal pure straight-line span starting at addr.

    Big-endian SH-2 decode using c_lift_ops.translate.  Stops at the first
    instruction that is unsupported (translate->None) or not a straight-line
    statement (kind != 'st': branch/ret, or any memory/side-effect op).  Returns
    list of (pc, op, translate_dict) tuples, or None if nothing pure.
    """
    bound = end if end is not None else addr + 0x1000
    bound = min(bound, len(rom))
    instrs = []
    pc = addr
    while pc + 1 < bound and len(instrs) < MAX_INSTR:
        op = (rom[pc] << 8) | rom[pc + 1]
        d = ops.translate(op, pc, rom)
        # unsupported / branch / return / memory access / side-effect -> end span
        # (statement ops carry no 'kind' key; only branch/ret dicts do)
        if d is None or d.get('kind') in ('branch', 'ret'):
            break
        instrs.append((pc, op, d))
        pc += 2
    return instrs if instrs else None


# ---------------------------------------------------------------------------
# v2: --mode mem selection.  Additive: the pure flow above is untouched.
# A function is accepted when every instruction in its catalog span [addr,end)
# decodes as a pure statement (translate) or as a memory op (decode_mem) whose
# base register is statically resolvable: PARAM (r4..r7 never written before),
# LITERAL (register loaded from mov.w/l @(disp,PC) before use), GBR (gbr_value
# tracked from `ldc Rn,GBR` = 0x4n1E with rN a known literal, and r0 literal ->
# base ('LITERAL', gbr_value + r0_val + disp) with gbr=True), or STACK (base
# r15 kept stack-clean — only @-r15/@r15+ auto modifications — or base r14
# established as frame pointer by `mov r15,r14`; disp/auto preserved, absolute
# resolution deferred to emission).  Everything else rejects the whole function
# with a reason counter; residual base_unresolved rejections are split out in
# counters['motivo_dettaglio'] (r15-non-tracked / r14-non-frame /
# GBR-non-risolto / r0-non-literal / altro).
# ---------------------------------------------------------------------------
MEM_MIN, MEM_MAX = 8, 160


def is_call_op(op):
    """jmp @Rn / jsr @Rn / bsr (translate() returns None for these)."""
    return (op & 0xF0FF == 0x402B or op & 0xF0FF == 0x400B or op & 0xF000 == 0xB000)


def is_branch_op(op):
    """bt/bf/bt.s/bf.s/bra/rts/rte — translate() already maps most of these."""
    return (op & 0xFF00 in (0x8900, 0x8B00, 0x8D00, 0x8F00) or
            op & 0xF000 == 0xA000 or op in (0x000B, 0x002B))


# ---------------------------------------------------------------------------
# v3 (complete): internal-branch admission (selection only + counters, emission
# untouched).  A translatable branch/return is ADMITTED iff its target lies
# inside the function span [addr,end) — rts (kind 'ret', target PR) is admitted
# in ANY position (early return OK) — and, for the delayed variants
# (bt.s/bf.s/bra/rts), the delay slot at P+2 is not itself a
# branch/call/rte/jmp/bsr/jsr.  Admitted: bt/bf (non delayed, both directions),
# bt.s/bf.s (delayed), bra (delayed, both directions incl. loop-back), rts
# (delayed, any position).  Rejected with a per-motivo reason: delay_slot_ctrl
# (P+2 of a delayed branch is itself a ctrl instruction — checked via
# ops.branch_info + the call predicates), target_fuori (target not in
# [addr,end)), rte (privileged, translate() -> None, never admitted).
# ---------------------------------------------------------------------------
def _v3_branch_rule(rom, op, target, pc, addr, end):
    """Classify one branch/return instruction.  Returns (admit, det) with det
    one of the admitted keys 'bt/bf' | 'bts/bfs' | 'bra' | 'rts' or the
    rejected keys 'delay_slot_ctrl' | 'target_fuori' | 'rte' — det doubles as
    the branch_stats key."""
    bi = ops.branch_info(op)
    if bi is None:                       # not a branch/return — caller bug
        return False, 'rte'
    kind = bi['kind']
    if kind == 'rte':                    # privileged: no template, never admitted
        return False, 'rte'
    if kind != 'rts' and not (addr <= target < end):
        return False, 'target_fuori'     # rts targets PR — no span check
    if bi['delayed']:                    # bts/bfs/bra/rts: P+2 must be in-span
        # and must not itself be a branch/call/rte/jmp/bsr/jsr (delay slot ctrl)
        if pc + 2 >= end or pc + 4 > len(rom):
            return False, 'delay_slot_ctrl'
        nxt = (rom[pc + 2] << 8) | rom[pc + 3]
        if ops.branch_info(nxt) is not None or is_call_op(nxt):
            return False, 'delay_slot_ctrl'
    if kind == 'rts':
        return True, 'rts'
    if kind in ('bt', 'bf'):
        return True, 'bt/bf'
    if kind in ('bts', 'bfs'):
        return True, 'bts/bfs'
    return True, 'bra'                   # bra: both directions (loop-back OK)


def _count_branch(branch_stats, det):
    """Instruction-level branch counter (no double counting: one increment per
    branch actually scanned; det is the motivo)."""
    if branch_stats is None:
        return
    branch_stats['branch_tot'] += 1
    if det in ('bt/bf', 'bts/bfs', 'bra', 'rts'):
        branch_stats['branch_ammessi'][det] += 1
    else:
        branch_stats['branch_rigettati'][det] += 1


def is_fpu_op(op):
    """SH-2E FPU block (0xFxxx) + LDS/STS FPU regs (0x4Fxx)."""
    return op & 0xF000 == 0xF000 or op & 0xFF00 == 0x4F00


def is_mem_opcode(op):
    """True iff the encoding has a b/w/l memory-op shape (mirrors decode_mem's
    pattern checks, plus the GBR forms 0xC0-C6, which _scan_mem_function now
    resolves itself via _decode_gbr; an op reaching is_mem_opcode with a GBR /
    r15 / r14 base is therefore always an unresolvable residual -> altro)."""
    n0 = op >> 12
    nib = op & 0xF
    if n0 == 0x6 and nib in (0, 1, 2, 4, 5, 6):       # loads @Rn / @Rn+
        return True
    if n0 == 0x2 and nib in (0, 1, 2, 4, 5, 6):       # stores @Rn / @-Rn
        return True
    if op & 0xFF00 in (0x8000, 0x8100, 0x8200, 0x8400, 0x8500, 0x8600):
        return True                                   # R0-only disp forms
    if op & 0xF00F in (0x0004, 0x0005, 0x0006, 0x000C, 0x000D, 0x000E):
        return True                                   # indexed @(R0,Rn)
    if op & 0xFF00 in (0xC000, 0xC100, 0xC200, 0xC400, 0xC500, 0xC600):
        return True                                   # GBR disp forms
    return False


_WRITE_RE = re.compile(r'\b(r(?:[0-9]|1[0-5])|macl|mach|pr|T|Q|M)\b\s*=(?!=)')


def _stmt_writes(c_text):
    """Registers a pure statement assigns (parsed from the mapper's C text;
    `=` not followed by `=` so `rN == ...` is not a write)."""
    return set(_WRITE_RE.findall(c_text))


def _apply_stmt(rom, pc, op, d, written, lits):
    """Track register writes + literal-pool loads (mov.w/l @(disp,PC)) for a
    pure statement.  Returns False when a literal pool read falls outside the
    ROM (function must be rejected)."""
    ctext = '\n'.join(d.get('c') or [])
    for reg in _stmt_writes(ctext):
        written.add(reg)
        lits.pop(reg, None)          # a write kills any previously loaded literal
    n = (op >> 8) & 0xF
    if op & 0xF000 == 0x9000:                        # mov.w @(disp,PC),Rn
        a = (pc + 4 + (op & 0xFF) * 2)
        if a + 2 > len(rom):
            return False
        lits['r%d' % n] = ops.lit16(rom, pc, op & 0xFF)   # sign_extend16
    elif op & 0xF000 == 0xD000:                      # mov.l @(disp,PC),Rn
        a = ((pc + 4) & ~3) + (op & 0xFF) * 4
        if a + 4 > len(rom):
            return False
        lits['r%d' % n] = ops.lit32(rom, pc, op & 0xFF)
    return True


def _apply_mem_writes(m, written, lits):
    """Track register side effects of an accepted mem op (dest of a load; base
    reg of @Rn+ / @-Rn auto-forms)."""
    if m['dir'] == 'load' and m.get('dest') is not None:
        reg = 'r%d' % m['dest']
        written.add(reg)
        lits.pop(reg, None)
    if m.get('auto') in ('post', 'pre'):
        reg = 'r%d' % m['base_reg']
        written.add(reg)
        lits.pop(reg, None)


_GBR_FORMS = {0xC000: (1, 'store'), 0xC100: (2, 'store'), 0xC200: (4, 'store'),
              0xC400: (1, 'load'), 0xC500: (2, 'load'), 0xC600: (4, 'load')}


def _decode_gbr(op):
    """0xC0-C6 GBR-relative b/w/l movs -> (size, 'load'|'store', disp_scaled)
    or None.  Address = GBR + disp (mov.b disp=lo, mov.w disp=lo*2, mov.l
    disp=lo*4, as sh2emu).  The 0xCC-CF GBR bit-ops stay unmapped."""
    hit = _GBR_FORMS.get(op & 0xFF00)
    if hit is None:
        return None
    size, gdir = hit
    return size, gdir, (op & 0xFF) * size


_SIZE_NIB = {0: 1, 1: 2, 2: 4, 4: 1, 5: 2, 6: 4, 0xC: 1, 0xD: 2, 0xE: 4}


def _mem_shape(op):
    """Decode a b/w/l memory op's shape for ANY base register, mirroring
    decode_mem and adding the 0x5nxx/0x1nxx 4-bit-disp mov.l forms (which the
    mapper keeps unmapped but are needed for @(disp,r15)/@(disp,r14) stack
    access).  Returns {size, dir, base, disp, auto, idx, dest, src} or None.
    Used only for base r15 (stack) / r14 (frame) acceptance."""
    n = (op >> 8) & 0xF
    m = (op >> 4) & 0xF
    n0 = op >> 12
    nib = op & 0xF
    if n0 == 0x6 and nib in (0, 1, 2, 4, 5, 6):        # loads @Rm / @Rm+
        return {'size': _SIZE_NIB[nib], 'dir': 'load', 'base': m, 'disp': 0,
                'auto': 'post' if nib >= 4 else None, 'idx': None,
                'dest': n, 'src': None}
    if n0 == 0x2 and nib in (0, 1, 2, 4, 5, 6):        # stores @Rn / @-Rn
        size = _SIZE_NIB[nib]
        auto = 'pre' if nib >= 4 else None
        return {'size': size, 'dir': 'store', 'base': n,
                'disp': -size if auto == 'pre' else 0, 'auto': auto,
                'idx': None, 'dest': None, 'src': m}
    f = op & 0xFF00
    if f in (0x8000, 0x8100, 0x8200, 0x8400, 0x8500, 0x8600):   # R0-only disp
        size = _SIZE_NIB[(op >> 8) & 0xF]
        disp = (op & 0xF) * size
        if f in (0x8000, 0x8100, 0x8200):
            return {'size': size, 'dir': 'store', 'base': m, 'disp': disp,
                    'auto': None, 'idx': None, 'dest': None, 'src': 0}
        return {'size': size, 'dir': 'load', 'base': m, 'disp': disp,
                'auto': None, 'idx': None, 'dest': 0, 'src': None}
    if op & 0xF00F in (0x0004, 0x0005, 0x0006):        # stores @(R0,Rn)
        return {'size': _SIZE_NIB[nib], 'dir': 'store', 'base': n, 'disp': 0,
                'auto': None, 'idx': 'r0', 'dest': None, 'src': m}
    if op & 0xF00F in (0x000C, 0x000D, 0x000E):        # loads @(R0,Rm)
        return {'size': _SIZE_NIB[nib], 'dir': 'load', 'base': m, 'disp': 0,
                'auto': None, 'idx': 'r0', 'dest': n, 'src': None}
    if n0 == 0x5:                                       # mov.l @(disp,Rm),Rn
        return {'size': 4, 'dir': 'load', 'base': m, 'disp': nib * 4,
                'auto': None, 'idx': None, 'dest': n, 'src': None}
    if n0 == 0x1:                                       # mov.l Rm,@(disp,Rn)
        return {'size': 4, 'dir': 'store', 'base': n, 'disp': nib * 4,
                'auto': None, 'idx': None, 'dest': None, 'src': m}
    return None


def _pcrel_pool_words(rom, addr, end):
    """Word (2-byte) addresses inside [addr, min(end,len(rom))) that are
    LITERAL-POOL DATA — referenced by mov.l/mov.w @(disp,PC) or mova
    @(disp,PC) — and so must be SKIPPED by the instruction walkers (never
    decoded as instructions, never 'unmapped').  Uses the exact sh2emu EA
    formulas: mov.l -> (pc+4)&~3 + disp*4 (4 bytes), mov.w -> pc+4 + disp*2
    (2 bytes), mova -> (pc+4)&~3 + disp*4 (4 bytes).  Only words that fall
    inside the span are marked (words after `end` are never walked).  A word
    that is BOTH pool data and executed (rare) keeps the walker skipping it —
    the differential tests surface those.
    """
    bound = min(end, len(rom))
    words = set()
    pc = addr
    while pc + 1 < bound:
        op = (rom[pc] << 8) | rom[pc + 1]
        lo = op & 0xFF
        if op >> 12 == 0xD:                      # mov.l @(disp,PC),Rn  (4 bytes)
            ea = ((pc + 4) & ~3) + lo * 4
            for a in (ea, ea + 2):
                if a < bound:
                    words.add(a)
        elif op >> 12 == 0x9:                    # mov.w @(disp,PC),Rn  (2 bytes)
            ea = pc + 4 + lo * 2
            if ea < bound:
                words.add(ea)
        elif op & 0xFF00 == 0xC700:              # mova @(disp,PC),R0  (4 bytes)
            ea = ((pc + 4) & ~3) + lo * 4
            for a in (ea, ea + 2):
                if a < bound:
                    words.add(a)
        pc += 2
    return words


def _scan_mem_function(rom, c, end, branch_stats=None):
    """Decode one classified function's span [addr,end) for mem mode.

    Returns (entry, None) on success, or (None, reason) at the first rejecting
    instruction.  reason is a plain string ('branch', 'call', ...) or the tuple
    ('base_unresolved', detail) so select_mem can split the residual into
    counters['motivo_dettaglio'].  entry = {name, addr, size, bases, ops,
    literal_values}; each ops entry is a dict
        {'pc', 'size', 'dir', 'kind': param|literal|stack|gbr,
         'base_reg', 'disp', 'auto', 'idx', 'gbr'}

    v3 (branch_stats): internal branches/returns (bt/bf/bt.s/bf.s/bra with
    in-span target, rts in any position; delay slots not ctrl — see
    _v3_branch_rule) are ADMITTED — the scan skips them and continues —
    instead of rejecting the function; rejected branch/return opcodes carry a
    per-motivo reason ('delay_slot_ctrl' / 'target_fuori' / 'rte').
    branch_stats, when given, accumulates instruction-level branch counters
    (branch_tot + ammessi/rigettati by motivo); a branch counted here is never
    counted elsewhere.  The entry carries 'branches': list of (kind, pc,
    target|None) for the ADMITTED branches (for the dryrun example report).
    """
    addr = c['addr']
    bound = min(end, len(rom))
    written = set()
    lits = {}
    tmp = [0]
    gbr_known = False        # saw `ldc Rn,GBR` (0x4n1E) before any GBR use
    gbr_value = None         # its literal value, if rN was a known literal
    stack_ok = True          # r15 written only by @-r15/@r15+ auto forms
    frame_live = False       # r14 established as frame ptr (mov r15,r14) & alive

    def temp():
        tmp[0] += 1
        return 't%d' % tmp[0]

    def resolve(reg):
        # reg arrives as an int register index (0..15) from decode_mem's
        # _resolve_base, but lits is keyed by 'r%d' strings -> normalize here.
        v = lits.get('r%d' % reg)
        if v is None:
            return None
        cls = ops.classify_addr(v)
        if cls in ('RAM', 'ROM'):
            return (cls, v)
        return None

    ctx = {'temp': temp, 'resolve': resolve}
    bases = {}
    ops_list = []
    lit_vals = []
    brs = []                              # admitted branches: (kind, pc, target)
    pool_words = _pcrel_pool_words(rom, addr, end)
    pc = addr
    while pc + 1 < bound:
        if pc in pool_words:              # literal-pool data — not an instruction
            pc += 2
            continue
        op = (rom[pc] << 8) | rom[pc + 1]
        d = ops.translate(op, pc, rom)
        if d is not None:
            if d.get('kind') in ('branch', 'ret'):
                # v3 (complete): translatable branch (bt/bf/bt.s/bf.s/bra —
                # kind 'branch') or early return (rts — kind 'ret') is admitted
                # iff its target lies in [addr,end) (rts: any position) and, for
                # delayed variants, its P+2 delay slot is not a ctrl instruction.
                # rte (kind none — translate() -> None) is handled below.
                target = d.get('target')
                admit, det = _v3_branch_rule(rom, op, target, pc, addr, end)
                _count_branch(branch_stats, det)
                if admit:
                    brs.append((det, pc, target))
                    pc += 2
                    continue
                return None, ('branch_v3', det)
            writes = _stmt_writes('\n'.join(d.get('c') or []))
            if op == 0x6EF3:                 # mov r15,r14 -> frame pointer
                if 'r14' not in written:
                    frame_live = True
            else:
                if 'r15' in writes:          # r15 rewritten non-stack -> taint
                    stack_ok = False
                if 'r14' in writes:          # r14 clobbered -> frame dead
                    frame_live = False
            if not _apply_stmt(rom, pc, op, d, written, lits):
                return None, 'unmapped'
            pc += 2
            continue
        # ---- not a pure statement ----
        if op & 0xF0FF == 0x401E:            # ldc Rn,GBR (rN may be a literal)
            gbr_known = True
            gbr_value = lits.get('r%d' % ((op >> 8) & 0xF))
            pc += 2
            continue
        if is_call_op(op):
            return None, 'call'
        if op == 0x002B:                      # rte (privileged) — dedicated reason
            return None, 'rte'
        if is_branch_op(op):
            return None, 'branch'             # unreachable: rte is the only branch
                                              # translate() doesn't map
        m = ops.decode_mem(op, None, ctx)
        if m is not None:
            base_reg = m['base_reg']
            # @(R0,Rn) indexed forms: the r0 index must itself be a known
            # literal — r0 loaded from memory (or unknown) is unresolvable.
            if m.get('idx') == 'r0' and 'r0' not in lits:
                return None, ('base_unresolved', 'altro')
            if base_reg in (4, 5, 6, 7) and 'r%d' % base_reg not in written:
                kind = ('PARAM', None)
                bkind = 'param'
            elif 'r%d' % base_reg in lits:
                kind = ('LITERAL', lits['r%d' % base_reg])
                bkind = 'literal'
            else:
                return None, ('base_unresolved', 'altro')
            bases.setdefault('r%d' % base_reg, kind)
            if kind[0] == 'LITERAL' and kind[1] not in lit_vals:
                lit_vals.append(kind[1])
            ops_list.append({'pc': pc, 'size': m['size'], 'dir': m['dir'],
                             'kind': bkind, 'base_reg': base_reg,
                             'disp': m.get('disp', 0), 'auto': m.get('auto'),
                             'idx': m.get('idx'), 'gbr': False})
            _apply_mem_writes(m, written, lits)
            pc += 2
            continue
        # ---- v2 extensions: GBR and stack/frame bases ----
        g = _decode_gbr(op)
        if g is not None:
            size, gdir, disp = g
            if not gbr_known or gbr_value is None:
                return None, ('base_unresolved', 'GBR-non-risolto')
            if 'r0' not in lits:
                return None, ('base_unresolved', 'r0-non-literal')
            abs_addr = (gbr_value + lits['r0'] + disp) & MASK
            bases.setdefault('gbr', ('LITERAL', abs_addr))
            if abs_addr not in lit_vals:
                lit_vals.append(abs_addr)
            gm = {'dir': gdir, 'dest': 0 if gdir == 'load' else None,
                  'src': 0 if gdir == 'store' else None}
            ops_list.append({'pc': pc, 'size': size, 'dir': gdir, 'kind': 'gbr',
                             'base_reg': None, 'disp': disp, 'auto': None,
                             'idx': None, 'gbr': True})
            _apply_mem_writes(gm, written, lits)   # GBR load writes r0
            pc += 2
            continue
        # ---- v6: GBR byte bit-ops (0xCC-CF) — decode_gbr_bit recognizes the
        # encoding; acceptance needs the same gbr_known/r0-literal contract as
        # the 0xC0-C6 movs (address = GBR + R0, both constants).  tst.b sets T
        # only, and/xor/or RMW the byte — no rN side effects, so no
        # _apply_mem_writes. ----
        gb = ops.decode_gbr_bit(op, pc, rom, None)
        if gb is not None:
            if not gbr_known or gbr_value is None:
                return None, ('base_unresolved', 'GBR-non-risolto')
            if 'r0' not in lits:
                return None, ('base_unresolved', 'r0-non-literal')
            abs_addr = (gbr_value + lits['r0']) & MASK
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
        sh = _mem_shape(op)
        if sh is not None and sh['base'] in (14, 15):
            breg = sh['base']
            if sh['idx'] is not None:            # @(R0,r15/r14): not mappable
                return None, ('base_unresolved', 'altro')
            if breg == 15:
                if not stack_ok or sh['dest'] == 15:
                    # r15 rewritten (or loaded into) non-stack-wise: untracked
                    return None, ('base_unresolved', 'r15-non-tracked')
            else:                                   # base r14 -> needs frame
                if not frame_live or sh['dest'] == 14:
                    return None, ('base_unresolved', 'r14-non-frame')
            bases.setdefault('r%d' % breg, ('STACK', None))
            sm = {'dir': sh['dir'], 'size': sh['size'], 'base_reg': breg,
                  'auto': sh['auto'], 'dest': sh.get('dest'), 'src': sh.get('src')}
            ops_list.append({'pc': pc, 'size': sh['size'], 'dir': sh['dir'],
                             'kind': 'stack', 'base_reg': breg, 'disp': sh['disp'],
                             'auto': sh['auto'], 'idx': sh.get('idx'), 'gbr': False})
            _apply_mem_writes(sm, written, lits)   # @-r15/@r15+ side effects
            pc += 2
            continue
        if is_mem_opcode(op):
            return None, ('base_unresolved', 'altro')
        if is_fpu_op(op):
            return None, 'fpu/altre'
        return None, 'unmapped'

    if not ops_list:
        return None, 'no_mem_op'
    return ({'name': c['name'], 'addr': addr, 'size': end - addr,
             'bases': bases, 'ops': ops_list, 'literal_values': lit_vals,
             'branches': brs}, None)


def select_mem(cats, max_n, seed, rom, catalog, root=ROOT):
    """Select classified functions (span known, size 8..160) for --mode mem.

    Returns (selected, counters):
      selected:  list of {name, addr, size, bases, ops, literal_values},
                 size-sorted then capped at max_n by a deterministic sample.
      counters:  {'selected', 'rejected': {reason: n},
                  'motivo_dettaglio': {base_unresolved detail: n},
                  'base_param'/'base_literal'/'base_stack'/'base_gbr' (selected
                  mem ops by base kind), 'skipped_no_span', 'skipped_size',
                  'skipped_dedup', 'by_category': {cat: {'selected','rejected'}}}
    """
    counters = {'selected': 0, 'rejected': Counter(),
                'motivo_dettaglio': Counter(),
                'base_param': 0, 'base_literal': 0, 'base_stack': 0, 'base_gbr': 0,
                'skipped_no_span': 0, 'skipped_size': 0, 'skipped_dedup': 0,
                'by_category': {}}
    branch_stats = {'branch_tot': 0,
                    'branch_ammessi': Counter(),      # bt/bf, bts/bfs, bra, rts
                    'branch_rigettati': Counter()}    # delay_slot_ctrl, target_fuori, rte
    pool = []
    for c in cats:
        cat = c['category']
        catstat = counters['by_category'].setdefault(cat, {'selected': 0, 'rejected': 0})
        end = catalog.get(c['addr'])
        if end is None:
            counters['skipped_no_span'] += 1
            continue
        size = end - c['addr']
        if not (MEM_MIN <= size <= MEM_MAX):
            counters['skipped_size'] += 1
            continue
        # dedup: skip if c/<name>_<addr>.c already exists (or addr already lifted)
        base = sanitize(c['name'])
        out_c = os.path.join(root, 'c', '%s_%x.c' % (base, c['addr']))
        out_t = os.path.join(root, 'c', 'tests', 'test_%s_%x.py' % (base, c['addr']))
        if os.path.exists(out_c) or os.path.exists(out_t) or \
                glob.glob(os.path.join(root, 'c', '*_%x.c' % c['addr'])):
            counters['skipped_dedup'] += 1
            continue
        entry, reason = _scan_mem_function(rom, c, end, branch_stats)
        if entry is None:
            if isinstance(reason, tuple):
                r, det = reason
                if r == 'branch_v3':                # v3 per-motivo branch reject
                    r = _BRANCH_V3_REASON.get(det, 'branch')
                    counters['rejected'][r] += 1
                else:
                    counters['rejected'][r] += 1
                    counters['motivo_dettaglio'][det] += 1
            else:
                counters['rejected'][reason] += 1
            catstat['rejected'] += 1
            continue
        pool.append(entry)
        counters['selected'] += 1
        for o in entry['ops']:
            k = o['kind']
            if k == 'param':
                counters['base_param'] += 1
            elif k == 'literal':
                counters['base_literal'] += 1
            elif k == 'stack':
                counters['base_stack'] += 1
            elif k == 'gbr':
                counters['base_gbr'] += 1
        catstat['selected'] += 1

    pool.sort(key=lambda x: x['size'])                 # stable
    counters['branch_tot'] = branch_stats['branch_tot']
    counters['branch_ammessi'] = branch_stats['branch_ammessi']
    counters['branch_rigettati'] = branch_stats['branch_rigettati']
    if max_n is not None and max_n < len(pool):
        pool = random.Random(seed).sample(pool, max_n)
    return pool, counters


_BRANCH_V3_REASON = {'delay_slot_ctrl': 'delay_slot_ctrl',
                     'target_fuori': 'target_fuori',
                     'rte': 'rte'}

_REASONS = ('unmapped', 'branch', 'delay_slot_ctrl', 'target_fuori', 'rte',
            'call', 'base_unresolved', 'fpu/altre', 'no_mem_op')


def print_mem_report(selected, counters, args):
    """--dryrun report: totals by reason, per-category top-8, base breakdown
    of the selected pool, residual base_unresolved detail, first 15 picks."""
    rej = counters['rejected']
    print('=== mem selection (--mode mem --dryrun): no files written ===')
    print('pool_v3=%d' % counters['selected'])
    print('rejected_total=%d' % sum(rej.values()))
    for r in _REASONS:
        print('  rejected_%-15s %d' % (r, rej.get(r, 0)))
    print('skipped_no_span=%d skipped_size=%d skipped_dedup=%d'
          % (counters['skipped_no_span'], counters['skipped_size'], counters['skipped_dedup']))
    print('--- branch breakdown (v3 internal-branch admission) ---')
    ba, br = counters.get('branch_ammessi', {}), counters.get('branch_rigettati', {})
    print('  branch_tot=%d (ammessi %d: bt/bf=%d bts/bfs=%d bra=%d rts=%d;'
          ' rigettati %d:'
          % (counters.get('branch_tot', 0), sum(ba.values()),
             ba.get('bt/bf', 0), ba.get('bts/bfs', 0), ba.get('bra', 0),
             ba.get('rts', 0), sum(br.values())))
    print('             delay_slot_ctrl=%d target_fuori=%d rte=%d)'
          % (br.get('delay_slot_ctrl', 0), br.get('target_fuori', 0),
             br.get('rte', 0)))
    print('--- selected mem ops by base ---')
    print('  base_param=%d base_literal=%d base_stack=%d base_gbr=%d'
          % (counters['base_param'], counters['base_literal'],
             counters['base_stack'], counters['base_gbr']))
    print('--- base_unresolved residual (motivo_dettaglio) ---')
    det = counters['motivo_dettaglio']
    for d in ('r15-non-tracked', 'r14-non-frame', 'GBR-non-risolto',
              'r0-non-literal', 'altro'):
        print('  base_unresolved_%-16s %d' % (d, det.get(d, 0)))
    print('  base_unresolved_total     %d (== rejected_base_unresolved %d)'
          % (sum(det.values()), rej.get('base_unresolved', 0)))
    print('--- per-category (top-8 by selected) ---')
    top = sorted(counters['by_category'].items(),
                 key=lambda kv: (kv[1]['selected'], kv[1]['rejected']), reverse=True)[:8]
    for cat, st in top:
        print('  %-24s selected=%4d rejected=%4d' % (cat, st['selected'], st['rejected']))
    print('--- branch functions in sampled pool ---')
    dl = sum(1 for e in selected if any(
        k in ('bts', 'bfs', 'bra', 'rts') for k, _, _ in e.get('branches', [])))
    ndl = sum(1 for e in selected if e.get('branches') and not any(
        k in ('bts', 'bfs', 'bra', 'rts') for k, _, _ in e.get('branches', [])))
    print('  fns_with_delay_slot_branch=%d fns_btbf_only=%d fns_without_branch=%d'
          % (dl, ndl, len(selected) - dl - ndl))
    print('--- first 15 selected (addr, branch types present, size) ---')
    for e in selected[:15]:
        brs = ', '.join(k for k, pc_, t_ in e.get('branches', [])) or 'none'
        print('  0x%06X %-32s size=%3d branches={%s} ops=%d'
              % (e['addr'], e['name'], e['size'], brs, len(e['ops'])))
    print('options: --mode mem --dryrun --n %d --seed %d' % (args.n, args.seed))


def sanitize(name):
    return re.sub(r'\W', '_', name or 'fun') or 'fun'


def gen_c_body(instrs, rom):
    """Return (c_text, used_set) — full lift body incl. locals + return r0.

    Only the registers the emitted C actually references are declared (one per
    line, no dead declarations).  r4..r7 are the C function parameters, so when
    any of them is used we add the `/* params (possibly) */` note instead of a
    local re-declaration (which would shadow the parameter and fail to compile).
    """
    stmts = []
    used = set()
    for pc, op, d in instrs:
        ann = d.get('ann') or ('op 0x%04X' % op)
        stmts.append('/* 0x%06X: %s */' % (pc, ann))
        stmts.extend(d['c'])
        used |= d.get('uses', set())

    # Scan the emitted C fragments (mapper text) for the register tokens the
    # function actually touches: r0..r15 plus the control/mult/accumulator regs.
    body_text = '\n'.join(stmts)
    refs = set()
    for m in re.finditer(r'\br(?:[0-9]|1[0-5])\b', body_text):
        refs.add(m.group(0))
    for tok in ('T', 'Q', 'M', 'macl', 'mach', 'sr', 'pr'):
        if re.search(r'\b%s\b' % tok, body_text):
            refs.add(tok)

    # r0 is the function's return register (`return r0;` is always emitted),
    # so it is always a live local regardless of the mapper's 'uses' set.
    refs.add('r0')

    lines = []
    # r4..r7 are possible function arguments (set at entry) — note only.
    if any('r%d' % n in refs for n in range(4, 8)):
        lines.append('    /* params (possibly) */')
    # locals: only the registers actually referenced (r0..r3, r8..r15), one per line.
    for n in list(range(0, 4)) + list(range(8, 16)):
        if 'r%d' % n in refs:
            lines.append('    uint32_t r%d = 0;' % n)
    for t in ('T', 'Q', 'M', 'macl', 'mach', 'sr', 'pr'):
        if t in refs:
            if t == 'pr':
                lines.append('    uint32_t pr = 0xEEEE0000u;')
            else:
                lines.append('    uint32_t %s = 0;' % t)
    lines.extend('    ' + s for s in stmts)
    lines.append('    return r0;')
    return '\n'.join(lines), used


def emit(addr, name, size, instrs, rom, seed, out_c, out_t):
    fn = sanitize(name)
    cbody, used = gen_c_body(instrs, rom)

    # collect raw bytes (for the emulator copy in the test)
    raw = rom[addr:addr + size]
    flat = ' '.join('%02X' % b for b in raw)

    banner = '/* ROM: %s | Address: 0x%X | Size: %d bytes | STATUS: DRAFT\n' \
             ' * Auto-generated by tools/gen_c_lift.py - not human-verified.\n' \
             ' * Pure straight-line function: no calls, no memory side effects. */' % (
                 ROM_LABEL, addr, size)

    c_text = (
        banner + '\n'
        '#include <stdint.h>\n'
        'uint32_t %s_%x(uint32_t r4, uint32_t r5, uint32_t r6, uint32_t r7)\n'
        '{\n%s\n}\n') % (fn, addr, cbody)

    with open(out_c, 'w') as f:
        f.write(c_text)

    # ---- compile gate: must pass the repo's real C gate (PASSO 1: cc -O2) ----
    # If the lift doesn't compile, drop it: remove the .c, write no test, warn.
    tmp_obj = os.path.join(tempfile.gettempdir(),
                           'gen_c_lift_%d.o' % os.getpid())
    gate = subprocess.run(['cc', '-O2', '-c', out_c, '-o', tmp_obj],
                          capture_output=True, text=True)
    if os.path.exists(tmp_obj):
        os.remove(tmp_obj)
    if gate.returncode != 0:
        os.remove(out_c)
        print('WARNING: lift 0x%X %-40s failed `cc -O2 -c`; .c dropped, no test written'
              % (addr, fn))
        return False

    # ---- spec_mirror: replicate the same semantics in Python ----
    py_stmts = []
    for pc, op, d in instrs:
        py_stmts.append('    # 0x%06X: op 0x%04X' % (pc, op))
        for s in d['py']:
            joined = '\n    '.join(ln.strip() for ln in s.split('\n') if ln.strip())
            py_stmts.append('    ' + joined)

    test = (
        '#!/usr/bin/env python3\n'
        '"""Differential test for %s (0x%X) — pure straight-line lift, %d bytes.\n'
        'Auto-generated by tools/gen_c_lift.py — not human-verified.\n'
        'Compares a Python spec_mirror against the sh2emu oracle (which runs the\n'
        'actual ROM bytes) over %d random inputs.\n'
        'Run from repo root: python3 c/tests/test_%s_%x.py\n'
        '"""\n'
        'import os, random, sys\n\n'
        'ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n'
        'sys.path.insert(0, os.path.join(ROOT, "tools"))\n'
        'from sh2emu import SH2\n'
        'from c_lift_ops import s8, s16, s32\n\n'
        'ROM = os.path.join(ROOT, "roms", "stock", "60E1D400.bin")\n'
        'ENTRY = 0x%X\n'
        'RAW = bytes.fromhex("%s")\n'
        'SEED = %d\n'
        'N = 2000\n\n'
        'def spec_mirror(r4, r5, r6, r7):\n'
        '    r = [0] * 16\n'
        '    r[4], r[5], r[6], r[7] = r4 & 0xFFFFFFFF, r5 & 0xFFFFFFFF, r6 & 0xFFFFFFFF, r7 & 0xFFFFFFFF\n'
        '    T = 0; Q = 0; M = 0; mach = 0; macl = 0; pr = 0xEEEE0000\n'
        '    ns = {"r": r, "T": T, "Q": Q, "M": M, "mach": mach, "macl": macl, "pr": pr,\n'
        '          "s8": s8, "s16": s16, "s32": s32}\n'
        '%s\n'
        '    return ns["r"][0] & 0xFFFFFFFF\n\n'
        'def run(cpu, a, b, c_, d):\n'
        '    # run at the original ROM entry; overlay a synthetic rts(0x000B)+nop\n'
        '    # right after the pure span so PC-relative literal pools stay intact.\n'
        '    # pr defaults to SENT -> emulator returns r0.\n'
        '    end = ENTRY + len(RAW)\n'
        '    ram = {end: 0x00, end + 1: 0x0B, end + 2: 0x00, end + 3: 0x09}\n'
        '    return cpu.call(ENTRY, r4=a, r5=b, r6=c_, r7=d, ram=ram)\n\n'
        'def main():\n'
        '    rnd = random.Random(SEED)\n'
        '    cpu = SH2(open(ROM, "rb").read())\n'
        '    for _ in range(N):\n'
        '        a = rnd.randint(0, 0xFFFFFFFF)\n'
        '        b = rnd.randint(0, 0xFFFFFFFF)\n'
        '        c_ = rnd.randint(0, 0xFFFFFFFF)\n'
        '        d = rnd.randint(0, 0xFFFFFFFF)\n'
        '        exp = spec_mirror(a, b, c_, d)\n'
        '        got = run(cpu, a, b, c_, d)\n'
        '        if got != exp:\n'
        '            print("MISMATCH args=(%%08X %%08X %%08X %%08X) mirror=%%08X emu=%%08X" %% (a,b,c_,d,exp,got))\n'
        '            sys.exit(1)\n'
        '    print("PASS 2000/2000")\n\n'
        'if __name__ == "__main__":\n'
        '    main()\n'
    ) % (fn, addr, size, N_CASES, fn, addr, addr, flat, seed, '\n'.join(py_stmts).rstrip())

    with open(out_t, 'w') as f:
        f.write(test)
    return True


# ---------------------------------------------------------------------------
# v2 --mode mem emission.  Additive: the pure flow above is untouched.
# For an accepted mem entry we RE-WALK the span with the same acceptance
# tracking (written/lits/gbr/stack/frame) as _scan_mem_function so the emitted
# instruction stream resolves bases identically, and emit:
#   - a C lift: register locals (r15 is the stack pointer -> implicit) plus one
#     uint32_t local_<off> per used stack offset; stack accesses become local
#     reads/writes (r15 inc/dec is implicit in the offsets), param/literal
#     accesses use decode_mem fragments (with sign-extension for b/w loads);
#   - a differential test: spec_mirror vs the sh2emu oracle over 2000 random
#     inputs with deterministic RAM prefill + a synthetic stack.
# ---------------------------------------------------------------------------
_SIZE_CH = {1: 'b', 2: 'w', 4: 'l'}
_CTYPE = {1: 'uint8_t', 2: 'uint16_t', 4: 'uint32_t'}
_SEXT_C = {1: '(uint32_t)(int32_t)(int8_t)', 2: '(uint32_t)(int32_t)(int16_t)'}
_SEXT_PY = {1: 's8', 2: 's16'}
STACK_BASE = 0xFFFFD000
STACK_TOP = STACK_BASE + 0x400


def _stack_mnem(sh):
    """Disassembly-style annotation for a stack/frame mem op."""
    d = _SIZE_CH[sh['size']]
    base = 'r15' if sh['base'] == 15 else 'r14'
    if sh['dir'] == 'load':
        if sh['auto'] == 'post':
            return 'mov.%s @%s+,r%d' % (d, base, sh['dest'])
        if sh['disp']:
            return 'mov.%s @(0x%X,%s),r%d' % (d, sh['disp'], base, sh['dest'])
        return 'mov.%s @%s,r%d' % (d, base, sh['dest'])
    if sh['auto'] == 'pre':
        return 'mov.%s r%d,@-%s' % (d, sh['src'], base)
    if sh['disp']:
        return 'mov.%s r%d,@(0x%X,%s)' % (d, sh['src'], sh['disp'], base)
    return 'mov.%s r%d,@%s' % (d, sh['src'], base)


def _mem_record(pc, op, m, bkind, abs_addr, temp, dynbase=False):
    """C + py emission for one param/literal mem op (decode_mem output m).

    bkind 'param' -> effective address (rN + disp) (runtime); 'literal' ->
    baked absolute address.  b/w loads sign-extend (emulator does s8/s16).

    dynbase=True: base register was folded to a literal but the mem op sits at a
    re-entered (= branch-target) PC, so the base can hold a different runtime
    value on re-entry (loop counter / duplicate entry).  Address must then be
    emitted register-relative (rN + disp) exactly like 'param' — the literal is
    still reported (note/RAM tag) but never baked into c/py.
    """
    size, gdir = m['size'], m['dir']
    breg = m['base_reg']
    disp = m.get('disp') or 0
    idx = m.get('idx')
    auto = m.get('auto')
    if bkind == 'literal':
        a = (abs_addr + disp) & MASK
        note = ' /* RAM 0x%08X */' % a if ops.classify_addr(a) == 'RAM' else ' /* ROM */'
        if dynbase:
            base_c, base_py = 'r%d' % breg, 'r[%d]' % breg
            if idx is not None:
                eff_c, eff_py = '(%s + %s)' % (base_c, idx), '(%s + r[%s])' % (base_py, idx.lstrip('r'))
            elif disp < 0:
                eff_c, eff_py = '(%s - %d)' % (base_c, -disp), '(%s - %d)' % (base_py, -disp)
            elif disp > 0:
                eff_c, eff_py = '(%s + %d)' % (base_c, disp), '(%s + %d)' % (base_py, disp)
            else:
                eff_c, eff_py = base_c, base_py
        else:
            eff_c = '0x%08X' % a
            eff_py = '0x%08X' % a
            if idx is not None:
                eff_c = '(%s + %s)' % (eff_c, idx)
                eff_py = '(%s + r[0])' % eff_py
    else:
        base_c, base_py = 'r%d' % breg, 'r[%d]' % breg
        if idx is not None:
            eff_c = '(%s + %s)' % (base_c, idx)
            eff_py = '(%s + r[%s])' % (base_py, idx.lstrip('r'))
        elif disp < 0:
            eff_c, eff_py = '(%s - %d)' % (base_c, -disp), '(%s - %d)' % (base_py, -disp)
        elif disp > 0:
            eff_c, eff_py = '(%s + %d)' % (base_c, disp), '(%s + %d)' % (base_py, disp)
        else:
            eff_c, eff_py = base_c, base_py
        note = ''
    if gdir == 'load':
        t = temp()
        if m.get('sext'):
            c = ['uint32_t %s = %s*(volatile %s*)%s;%s' % (t, _SEXT_C[size], _CTYPE[size], eff_c, note),
                 'r%d = %s;' % (m['dest'], t)]
            py = ['r[%d] = %s(_rdw(ram, %s, %d))' % (m['dest'], _SEXT_PY[size], eff_py, size)]
        else:
            c = ['uint32_t %s = *(volatile %s*)%s;%s' % (t, _CTYPE[size], eff_c, note),
                 'r%d = %s;' % (m['dest'], t)]
            py = ['r[%d] = _rdw(ram, %s, %d)' % (m['dest'], eff_py, size)]
        if auto == 'post':
            c.append('r%d = r%d + %d;' % (breg, breg, size))
            py.append('r[%d] = (r[%d] + %d) & 0xFFFFFFFF' % (breg, breg, size))
    else:
        c = ['*(volatile %s*)%s = r%d;%s' % (_CTYPE[size], eff_c, m['src'], note)]
        py = ['_wrw(ram, %s, %d, r[%d])' % (eff_py, size, m['src'])]
        if auto == 'pre':
            c.append('r%d = r%d - %d;' % (breg, breg, size))
            py.append('r[%d] = (r[%d] - %d) & 0xFFFFFFFF' % (breg, breg, size))
    return c, py


def _gbr_record(pc, op, size, gdir, abs_addr, temp):
    """C + py for a 0xC0-C6 GBR-relative b/w/l op (baked abs address)."""
    note = ' /* RAM 0x%08X */' % abs_addr if ops.classify_addr(abs_addr) == 'RAM' else ' /* ROM */'
    if gdir == 'load':
        t = temp()
        if size < 4:
            c = ['uint32_t %s = %s*(volatile %s*)0x%08X;%s' % (t, _SEXT_C[size], _CTYPE[size], abs_addr, note),
                 'r0 = %s;' % t]
            py = ['r[0] = %s(_rdw(ram, 0x%08X, %d))' % (_SEXT_PY[size], abs_addr, size)]
        else:
            c = ['uint32_t %s = *(volatile %s*)0x%08X;%s' % (t, _CTYPE[size], abs_addr, note),
                 'r0 = %s;' % t]
            py = ['r[0] = _rdw(ram, 0x%08X, %d)' % (abs_addr, size)]
    else:
        c = ['*(volatile %s*)0x%08X = r0;%s' % (_CTYPE[size], abs_addr, note)]
        py = ['_wrw(ram, 0x%08X, %d, r[0])' % (abs_addr, size)]
    return c, py


def _stack_record(pc, op, sh, off):
    """C + py for one stack/frame mem op.  off is the absolute offset from
    STACK_BASE (after decrement for @-r15 stores, before increment for @r15+
    loads); r15/r14 movement is implicit in the local_<off> model."""
    size, gdir = sh['size'], sh['dir']
    if gdir == 'load':
        if size < 4:
            c = ['r%d = %s(local_%x & 0x%Xu);' % (sh['dest'], _SEXT_C[size], off, (1 << (8 * size)) - 1)]
            py = ['r[%d] = %s(_rdw(ram, STACK_BASE + 0x%X, %d))' % (sh['dest'], _SEXT_PY[size], off, size)]
        else:
            c = ['r%d = local_%x;' % (sh['dest'], off)]
            py = ['r[%d] = _rdw(ram, STACK_BASE + 0x%X, %d)' % (sh['dest'], off, size)]
        if sh['auto'] == 'post':
            py.append('sp = (sp + %d) & 0xFFFFFFFF' % size)
    else:
        c = ['local_%x = r%d;' % (off, sh['src'])]
        py = ['local[0x%X] = r[%d]' % (off, sh['src']),
              '_wrw(ram, STACK_BASE + 0x%X, %d, r[%d])' % (off, size, sh['src'])]
        if sh['auto'] == 'pre':
            py.append('sp = (sp - %d) & 0xFFFFFFFF' % size)
    return c, py


def _walk_mem_span(rom, addr, end):
    """Re-decode an accepted mem span for emission.  Mirrors _scan_mem_function's
    acceptance tracking (written/lits/gbr/stack_ok/frame_live) exactly, so the
    resolved bases agree with selection.  Returns (records, info) or None on any
    divergence (caller drops the function):
      records: [{'pc', 'op', 'kind', 'c': [C lines], 'py': [py lines], 'mnem'}]
      info:    {'stack_offs': set, 'ram_addrs': set, 'has_stack', 'has_literal'}
    """
    bound = min(end, len(rom))
    written = set()
    lits = {}
    tmp = [0]
    gbr_known = False
    gbr_value = None
    stack_ok = True
    frame_live = False
    frame_off = None
    sp_off = STACK_TOP - STACK_BASE      # init r15 offset (== 0x400)
    records = []
    info = {'stack_offs': set(), 'ram_addrs': set(),
            'has_stack': False, 'has_literal': False}

    def temp():
        tmp[0] += 1
        return 't%d' % tmp[0]

    def resolve(reg):
        v = lits.get('r%d' % reg)
        if v is None:
            return None
        cls = ops.classify_addr(v)
        if cls in ('RAM', 'ROM'):
            return (cls, v)
        return None

    ctx = {'temp': temp, 'resolve': resolve}
    pool_words = _pcrel_pool_words(rom, addr, end)
    pc = addr
    while pc + 1 < bound:
        if pc in pool_words:              # literal-pool data — not an instruction
            pc += 2
            continue
        op = (rom[pc] << 8) | rom[pc + 1]
        d = ops.translate(op, pc, rom)
        if d is not None:
            if d.get('kind') in ('branch', 'ret'):
                return None
            ctext = '\n'.join(d.get('c') or [])
            if op == 0x6EF3:                       # mov r15,r14 -> frame pointer
                if 'r14' not in written:
                    frame_live = True
                    frame_off = sp_off
                records.append({'pc': pc, 'op': op, 'kind': 'frame',
                                'c': ['/* 0x%06X: mov r15,r14 (frame pointer — implicit) */' % pc],
                                'py': ['r[14] = sp'], 'mnem': 'mov r15,r14'})
            else:
                writes = _stmt_writes(ctext)
                if 'r15' in writes:
                    stack_ok = False
                if 'r14' in writes:
                    frame_live = False
                if not _apply_stmt(rom, pc, op, d, written, lits):
                    return None
                records.append({'pc': pc, 'op': op, 'kind': 'st',
                                'c': list(d.get('c') or []),
                                'py': list(d.get('py') or []),
                                'mnem': d.get('ann') or ('op 0x%04X' % op)})
            pc += 2
            continue
        if op & 0xF0FF == 0x401E:                  # ldc Rn,GBR
            gbr_known = True
            gbr_value = lits.get('r%d' % ((op >> 8) & 0xF))
            records.append({'pc': pc, 'op': op, 'kind': 'ldc',
                            'c': ['/* 0x%06X: ldc r%d,GBR (GBR = 0x%08X) */'
                                  % (pc, (op >> 8) & 0xF, gbr_value or 0)],
                            'py': [], 'mnem': 'ldc r%d,GBR' % ((op >> 8) & 0xF)})
            pc += 2
            continue
        if is_call_op(op) or is_branch_op(op):
            return None
        m = ops.decode_mem(op, None, ctx)
        if m is not None:
            base_reg = m['base_reg']
            if m.get('idx') == 'r0' and 'r0' not in lits:
                return None
            if base_reg in (4, 5, 6, 7) and 'r%d' % base_reg not in written:
                bkind, abs_addr = 'param', None
            elif 'r%d' % base_reg in lits:
                bkind, abs_addr = 'literal', lits['r%d' % base_reg]
            else:
                return None
            if bkind == 'literal':
                info['has_literal'] = True
                info['ram_addrs'].add(abs_addr)
            c, py = _mem_record(pc, op, m, bkind, abs_addr, temp)
            records.append({'pc': pc, 'op': op, 'kind': 'mem',
                            'c': c, 'py': py, 'mnem': m['ann']})
            _apply_mem_writes(m, written, lits)
            pc += 2
            continue
        g = _decode_gbr(op)
        if g is not None:
            size, gdir, disp = g
            if not gbr_known or gbr_value is None or 'r0' not in lits:
                return None
            abs_addr = (gbr_value + lits['r0'] + disp) & MASK
            info['has_literal'] = True
            info['ram_addrs'].add(abs_addr)
            gm = {'dir': gdir, 'dest': 0 if gdir == 'load' else None,
                  'src': 0 if gdir == 'store' else None}
            c, py = _gbr_record(pc, op, size, gdir, abs_addr, temp)
            if gdir == 'store':
                mnem = 'mov.%s r0,@(0x%X,gbr)' % (_SIZE_CH[size], disp)
            else:
                mnem = 'mov.%s @(0x%X,gbr),r0' % (_SIZE_CH[size], disp)
            records.append({'pc': pc, 'op': op, 'kind': 'gbr',
                            'c': c, 'py': py, 'mnem': mnem})
            _apply_mem_writes(gm, written, lits)
            pc += 2
            continue
        sh = _mem_shape(op)
        if sh is not None and sh['base'] in (14, 15):
            breg = sh['base']
            if breg == 15:
                if not stack_ok or sh['dest'] == 15:
                    return None
            else:
                if not frame_live or sh['dest'] == 14:
                    return None
            if sh['idx'] is not None:              # dynamic r0 index: not mappable
                return None
            if breg == 15:
                if sh['auto'] == 'pre':
                    sp_off -= sh['size']
                    off = sp_off
                elif sh['auto'] == 'post':
                    off = sp_off
                    sp_off += sh['size']
                else:
                    off = sp_off + sh['disp']
            else:
                off = (frame_off if frame_off is not None else sp_off) + sh['disp']
            info['has_stack'] = True
            info['stack_offs'].add(off)
            sm = {'dir': sh['dir'], 'size': sh['size'], 'base_reg': breg,
                  'auto': sh['auto'], 'dest': sh.get('dest'), 'src': sh.get('src')}
            c, py = _stack_record(pc, op, sh, off)
            records.append({'pc': pc, 'op': op, 'kind': 'stack',
                            'c': c, 'py': py, 'mnem': _stack_mnem(sh)})
            _apply_mem_writes(sm, written, lits)
            pc += 2
            continue
        if is_mem_opcode(op) or is_fpu_op(op):
            return None
        return None
    return records, info


def emit_mem(addr, name, size, entry, rom, seed, out_c, out_t):
    """--mode mem emission: lift one accepted mem function.

    Writes c/<name>_<addr>.c (compile-gated: dropped if `cc -O2 -c` fails, no
    test written) and c/tests/test_<name>_<addr>.py.  The test differentials a
    Python spec_mirror against the sh2emu oracle over 2000 random inputs with
    deterministic RAM prefill around the literal addresses and a synthetic
    0x400-byte stack at STACK_BASE (r15 init = STACK_TOP, passed via regs=).
    """
    fn = sanitize(name)
    span = _walk_mem_span(rom, addr, addr + size)
    if span is None:
        print('WARNING: lift 0x%X %-40s re-walk diverged from selection; dropped'
              % (addr, fn))
        return False
    records, info = span

    # ---- C body: locals (registers + stack slots) + statements ----
    stmts = []
    for rec in records:
        stmts.append('/* 0x%06X: %s */' % (rec['pc'], rec['mnem']))
        stmts.extend(rec['c'])
    body_text = '\n'.join(stmts)
    refs = set()
    for m_ in re.finditer(r'\br(?:[0-9]|1[0-5])\b', body_text):
        refs.add(m_.group(0))
    for tok in ('T', 'Q', 'M', 'macl', 'mach', 'sr', 'pr'):
        if re.search(r'\b%s\b' % tok, body_text):
            refs.add(tok)
    refs.add('r0')

    lines = []
    if any('r%d' % n in refs for n in range(4, 8)):
        lines.append('    /* params (possibly) */')
    # r15 is the stack pointer (implicit in local_<off>) and is never declared.
    for n in list(range(0, 4)) + list(range(8, 15)):
        if 'r%d' % n in refs:
            lines.append('    uint32_t r%d = 0;' % n)
    for t in ('T', 'Q', 'M', 'macl', 'mach', 'sr', 'pr'):
        if t in refs:
            if t == 'pr':
                lines.append('    uint32_t pr = 0xEEEE0000u;')
            else:
                lines.append('    uint32_t %s = 0;' % t)
    for off in sorted(info['stack_offs']):
        lines.append('    uint32_t local_%x = 0;' % off)
    lines.extend('    ' + s for s in stmts)
    lines.append('    return r0;')
    cbody = '\n'.join(lines)

    raw = rom[addr:addr + size]
    flat = ' '.join('%02X' % b for b in raw)

    banner = ('/* ROM: %s | Address: 0x%X | Size: %d bytes | STATUS: DRAFT\n'
              ' * Auto-generated by tools/gen_c_lift.py - not human-verified.\n'
              ' * Mode: mem (RAM-only, straight-line) */') % (ROM_LABEL, addr, size)
    c_text = (banner + '\n'
              '#include <stdint.h>\n'
              'uint32_t %s_%x(uint32_t r4, uint32_t r5, uint32_t r6, uint32_t r7)\n'
              '{\n%s\n}\n') % (fn, addr, cbody)
    with open(out_c, 'w') as f:
        f.write(c_text)

    # ---- compile gate (same gate as the pure path) ----
    tmp_obj = os.path.join(tempfile.gettempdir(),
                           'gen_c_lift_%d.o' % os.getpid())
    gate = subprocess.run(['cc', '-O2', '-c', out_c, '-o', tmp_obj],
                          capture_output=True, text=True)
    if os.path.exists(tmp_obj):
        os.remove(tmp_obj)
    if gate.returncode != 0:
        os.remove(out_c)
        print('WARNING: lift 0x%X %-40s failed `cc -O2 -c`; .c dropped, no test written'
              % (addr, fn))
        return False

    # ---- test harness: spec_mirror vs sh2emu, 2000 random cases ----
    py_stmts = []
    for rec in records:
        py_stmts.append('    # 0x%06X: %s' % (rec['pc'], rec['mnem']))
        for s in rec['py']:
            joined = '\n    '.join(ln.strip() for ln in s.split('\n') if ln.strip())
            py_stmts.append('    ' + joined)

    offs_list = sorted(info['stack_offs'])
    stack_offs = ', '.join('0x%X' % o for o in offs_list)
    if len(offs_list) == 1:
        stack_offs += ','                 # (0x414,) must stay a tuple, not an int
    ram_addrs = [v for v in info['ram_addrs'] if ops.classify_addr(v) == 'RAM']
    ram_min = min(ram_addrs) if ram_addrs else None
    ram_max = max(ram_addrs) if ram_addrs else None

    test = (
        '#!/usr/bin/env python3\n'
        '"""Differential test for %s (0x%X) — mem lift (RAM-only, straight-line), %d bytes.\n'
        'Auto-generated by tools/gen_c_lift.py — not human-verified.\n'
        'Compares a Python spec_mirror against the sh2emu oracle (which runs the\n'
        'actual ROM bytes) over %d random inputs: deterministic RAM prefill around\n'
        'the literal addresses plus a synthetic 0x400-byte stack at STACK_BASE.\n'
        'Run from repo root: python3 c/tests/test_%s_%x.py\n'
        '"""\n'
        'import os, random, sys\n\n'
        'ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n'
        'sys.path.insert(0, os.path.join(ROOT, "tools"))\n'
        'from sh2emu import SH2\n'
        'from c_lift_ops import s8, s16, s32\n\n'
        'ROM = os.path.join(ROOT, "roms", "stock", "60E1D400.bin")\n'
        'ROM_BYTES = open(ROM, "rb").read()\n'
        'ENTRY = 0x%X\n'
        'RAW = bytes.fromhex("%s")\n'
        'SEED = %d\n'
        'N = 2000\n'
        'STACK_BASE = 0xFFFFD000\n'
        'STACK_TOP = STACK_BASE + 0x400\n'
        'STACK_OFFS = (%s)\n'
        'RAM_MIN = %s\n'
        'RAM_MAX = %s\n\n'
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
        '        ram[(a + i) & 0xFFFFFFFF] = (v >> (8 * (n - 1 - i))) & 0xFF\n\n'
        'def spec_mirror(r4, r5, r6, r7, ram, stack_top):\n'
        '    r = [0] * 16\n'
        '    r[4], r[5], r[6], r[7] = r4 & 0xFFFFFFFF, r5 & 0xFFFFFFFF, r6 & 0xFFFFFFFF, r7 & 0xFFFFFFFF\n'
        '    T = 0; Q = 0; M = 0; mach = 0; macl = 0; pr = 0xEEEE0000\n'
        '    sp = stack_top & 0xFFFFFFFF\n'
        '    local = {off: int.from_bytes(bytes(_rd(ram, STACK_BASE + off + i) for i in range(4)), "big") for off in STACK_OFFS}\n'
        '    ns = {"r": r, "T": T, "Q": Q, "M": M, "mach": mach, "macl": macl, "pr": pr,\n'
        '          "s8": s8, "s16": s16, "s32": s32}\n'
        '%s\n'
        '    r[15] = sp\n'
        '    return r[0] & 0xFFFFFFFF, [x & 0xFFFFFFFF for x in r], ram, local\n\n'
        'def run(cpu, ram, a, b, c_, d):\n'
        '    end = ENTRY + len(RAW)\n'
        '    ram = dict(ram)\n'
        '    ram[end] = 0x00; ram[end + 1] = 0x0B; ram[end + 2] = 0x00; ram[end + 3] = 0x09\n'
        '    cpu.call(ENTRY, r4=a, r5=b, r6=c_, r7=d, ram=ram, regs={15: STACK_TOP})\n'
        '    out = dict(cpu.ram)\n'
        '    for i in range(4):\n'
        '        out.pop(end + i, None)\n'
        '    return cpu.r[0] & 0xFFFFFFFF, [x & 0xFFFFFFFF for x in cpu.r], out\n\n'
        'def main():\n'
        '    rnd = random.Random(SEED)\n'
        '    cpu = SH2(ROM_BYTES)\n'
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
        '        exp_r0, exp_regs, exp_ram, exp_local = spec_mirror(a, b, c_, d, dict(ram), STACK_TOP)\n'
        '        got_r0, got_regs, got_ram = run(cpu, ram, a, b, c_, d)\n'
        '        if exp_regs != got_regs:\n'
        '            for i in range(16):\n'
        '                if exp_regs[i] != got_regs[i]:\n'
        '                    print("MISMATCH case=%%d reg=r%%d mirror=%%08X emu=%%08X" %% (caso, i, exp_regs[i], got_regs[i]))\n'
        '                    sys.exit(1)\n'
        '        for ad in sorted(set(exp_ram) | set(got_ram)):\n'
        '            if exp_ram.get(ad, 0) != got_ram.get(ad, 0):\n'
        '                print("MISMATCH case=%%d addr=0x%%08X mirror=%%02X emu=%%02X" %% (caso, ad, exp_ram.get(ad, 0), got_ram.get(ad, 0)))\n'
        '                sys.exit(1)\n'
        '    print("PASS 2000/2000")\n\n'
        'if __name__ == "__main__":\n'
        '    main()\n'
    ) % (fn, addr, size, N_CASES, fn, addr, addr, flat, seed, stack_offs,
         'None' if ram_min is None else '0x%X' % ram_min,
         'None' if ram_max is None else '0x%X' % ram_max,
         '\n'.join(py_stmts).rstrip())

    with open(out_t, 'w') as f:
        f.write(test)
    return True


def compute_stats():
    """unique lift addrs from existing c/*.c banners + catalog totals."""
    unique = set()
    for p in glob.glob(os.path.join(ROOT, 'c', '*.c')):
        try:
            with open(p) as f:
                head = f.read(4000)
        except OSError:
            continue
        for m in re.finditer(r'Address:\s*0x([0-9A-Fa-f]+)', head):
            unique.add(int(m.group(1), 16))
            break  # one banner per file
    total = sum(
        1 for row in csv.DictReader(open(os.path.join(ROOT, 'symbols', 'CATALOG_MASTER.csv')))
        if (row.get('flag') or '').strip() != 'NOISE'
    )
    of_classified = sum(1 for _ in csv.DictReader(
        open(os.path.join(ROOT, 'symbols', 'FUNCTION_CATEGORIES.csv'))))
    pct = 100.0 * len(unique) / total if total else 0.0
    pct_of_classified = (100.0 * len(unique) / of_classified
                         if of_classified else 0.0)
    return len(unique), total, of_classified, pct, pct_of_classified


def main():
    ap = argparse.ArgumentParser(description='Generate C lifts for pure SH-2 functions')
    ap.add_argument('--category', default=None, help='filter by FUNCTION_CATEGORIES category')
    ap.add_argument('--n', type=int, default=1, help='number of functions to lift')
    ap.add_argument('--seed', type=int, default=0, help='RNG seed (deterministic)')
    ap.add_argument('--mode', choices=('pure', 'mem'), default='mem',
                    help='pure = v1 straight-line lift; mem = memory-op selection (additive)')
    ap.add_argument('--dryrun', action='store_true',
                    help='select/count only, write no files (mem mode default report)')
    ap.add_argument('--addr', default=None, help='lift only this addr (hex, e.g. 0x1234)')
    ap.add_argument('--stats', action='store_true', help='print lift stats and exit')
    ap.add_argument('--rom', default=os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin'))
    args = ap.parse_args()

    if args.stats:
        n, total, ofc, pct, pct_of_classified = compute_stats()
        print('unique_lift_addrs=%d total=%d pct=%.2f' % (n, total, pct))
        print('of_classified=%d' % ofc)
        print('pct_of_classified=%.2f  (coverage vs classified functions)'
              % pct_of_classified)
        return

    rom = open(args.rom, 'rb').read()
    catalog = load_catalog_end(os.path.join(ROOT, 'symbols', 'CATALOG_MASTER.csv'))
    categories = load_categories(os.path.join(ROOT, 'symbols', 'FUNCTION_CATEGORIES.csv'))

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

    # ---- --mode mem: selection + emission ----
    if args.mode == 'mem':
        selected, counters = select_mem(cands, args.n, args.seed, rom, catalog)
        if args.dryrun:
            print_mem_report(selected, counters, args)
            return
        emitted = 0
        dropped = 0
        for e in selected:
            base = sanitize(e['name'])
            lf = '%s_%x' % (base, e['addr'])
            out_c = os.path.join(ROOT, 'c', lf + '.c')
            out_t = os.path.join(ROOT, 'c', 'tests', 'test_' + lf + '.py')
            if emit_mem(e['addr'], e['name'], e['size'], e, rom, args.seed,
                        out_c, out_t):
                emitted += 1
                print('lifted 0x%X %-40s size=%3d -> %s'
                      % (e['addr'], e['name'], e['size'], out_c))
            else:
                dropped += 1
        print('emitted=%d dropped_compile=%d' % (emitted, dropped))
        return

    # decode + purity + length filter, keep stable (size) order for selection
    pool = []
    for c in cands:
        span = decode_pure_span(rom, c['addr'], catalog.get(c['addr']))
        if not span:
            continue
        size = span[-1][0] + 2 - c['addr']
        if not (MIN_LEN <= size <= MAX_LEN):
            continue
        pool.append({'g': c, 'size': size, 'span': span})

    pool.sort(key=lambda x: x['size'])            # stable
    rnd = random.Random(args.seed)

    emitted = 0
    skipped = 0
    dropped = 0
    for hit in rnd.sample(pool, min(args.n, len(pool))):
        c = hit['g']
        size = hit['size']
        span = hit['span']
        base = sanitize(c['name'])
        lf = '%s_%x' % (base, c['addr'])
        out_c = os.path.join(ROOT, 'c', lf + '.c')
        out_t = os.path.join(ROOT, 'c', 'tests', 'test_' + lf + '.py')

        # dedup: skip if c/<name>_<addr>.c already exists or addr already lifted
        if os.path.exists(out_c) or os.path.exists(out_t):
            skipped += 1
            continue
        if glob.glob(os.path.join(ROOT, 'c', '*_%x.c' % c['addr'])):
            skipped += 1
            continue

        if args.dryrun:
            emitted += 1
            print('would_lift 0x%X %-40s size=%3d -> %s (dry-run, no file written)'
                  % (c['addr'], c['name'], size, out_c))
            continue
        if not emit(c['addr'], c['name'], size, span, rom, args.seed, out_c, out_t):
            dropped += 1
            continue
        emitted += 1
        print('lifted 0x%X %-40s size=%3d -> %s' % (c['addr'], c['name'], size, out_c))

    print('emitted=%d skipped_dedup=%d dropped_compile=%d pool=%d'
          % (emitted, skipped, dropped, len(pool)))


if __name__ == '__main__':
    main()