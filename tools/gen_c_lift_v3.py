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
slot T-sampling) against the sh2emu oracle over 2000 random inputs; the tests
are run at generation time and summarized in a report.

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
# ---------------------------------------------------------------------------
def select_v3(cats, max_n, seed, rom, catalog, outdir, root=ROOT):
    """Returns (selected, counters) — see gen_c_lift.select_mem; extra counter
    'skipped_no_branch' for functions that pass the mem scan but have no
    admitted internal branch."""
    counters = {'selected': 0, 'rejected': Counter(),
                'motivo_dettaglio': Counter(),
                'skipped_no_span': 0, 'skipped_size': 0, 'skipped_dedup': 0,
                'skipped_no_branch': 0, 'by_category': {}}
    branch_stats = {'branch_tot': 0,
                    'branch_ammessi': Counter(),
                    'branch_rigettati': Counter()}
    pool = []
    for c in cats:
        cat = c['category']
        catstat = counters['by_category'].setdefault(cat, {'selected': 0, 'rejected': 0})
        end = catalog.get(c['addr'])
        if end is None:
            counters['skipped_no_span'] += 1
            continue
        size = end - c['addr']
        if not (gcl.MEM_MIN <= size <= gcl.MEM_MAX):
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
        entry, reason = gcl._scan_mem_function(rom, c, end, branch_stats)
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
                counters['rejected'][reason] += 1
            catstat['rejected'] += 1
            continue
        if not entry['branches']:                   # v3 = branch lifts only
            counters['skipped_no_branch'] += 1
            catstat['rejected'] += 1
            continue
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
    st = {'written': set(), 'lits': {}, 'tmp': [0],
          'gbr_known': False, 'gbr_value': None,
          'stack_ok': True, 'frame_live': False, 'frame_off': None,
          'sp_off': 0x400}
    info = {'stack_offs': set(), 'ram_addrs': set(),
            'has_stack': False, 'has_literal': False}
    labels = set()
    records = []
    skip = set()

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
        """Emit one non-branch instruction record (mutates the tracking state).
        Mirrors _walk_mem_span's per-instruction logic; returns None when the
        instruction is not emittable (caller drops the function)."""
        d = ops.translate(op, pc, rom)
        if d is not None:
            ctext = '\n'.join(d.get('c') or [])
            writes = gcl._stmt_writes(ctext)
            if op == 0x6E3F:                       # mov r15,r14 -> frame pointer
                if st['stack_ok'] and 'r14' not in st['written']:
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
            c, py = gcl._mem_record(pc, op, m, bkind, abs_addr, temp)
            gcl._apply_mem_writes(m, st['written'], st['lits'])
            return {'pc': pc, 'op': op, 'kind': 'mem', 'c': c, 'py': py,
                    'target': None, 'slot': None, 'mnem': m['ann']}
        g = gcl._decode_gbr(op)
        if g is not None:
            size, gdir, disp = g
            if not st['gbr_known'] or st['gbr_value'] is None or 'r0' not in st['lits']:
                return None
            abs_addr = (st['gbr_value'] + st['lits']['r0'] + disp) & gcl.MASK
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
            return {'pc': pc, 'op': op, 'kind': 'stack', 'c': c, 'py': py,
                    'target': None, 'slot': None, 'mnem': gcl._stack_mnem(sh)}
        return None

    pc = addr
    while pc + 1 < bound:
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
            if kind != 'rts':
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
            line = BRANCH_C[kind] if kind == 'rts' else BRANCH_C[kind] % target
            mnem = BRANCH_MNEM[kind] if kind == 'rts' else BRANCH_MNEM[kind] % target
            records.append({'pc': pc, 'op': op, 'kind': 'branch',
                            'c': [line], 'mnem': mnem,
                            'target': target, 'slot': slot})
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
    r8..r14 as one-per-line uint32_t; r4..r7 are the params -> note only; r15 is
    the stack pointer -> implicit).  T is declared ONLY when the body mentions
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
    return lines


def emit_v3(addr, name, size, rom, out_c):
    """Lift one accepted v3 function: write c/<name>_<addr>.c, compile-gate it
    with `cc -O2 -c`, and delete the file if the gate fails."""
    fn = gcl.sanitize(name)
    walked = walk_v3(rom, addr, addr + size)
    if walked is None:
        print('WARNING: lift 0x%X %-40s re-walk diverged from selection; dropped'
              % (addr, fn))
        return False
    records, info, labels = walked
    stmts = render_body(records, labels)
    body = build_locals(stmts, info)
    body.extend('    ' + s for s in stmts)
    body.append('    return r0; /* fallthrough */')
    cbody = '\n'.join(body)

    banner = ('/* ROM: %s | Address: 0x%X | Size: %d bytes | STATUS: DRAFT\n'
              ' * Auto-generated by tools/gen_c_lift_v3.py — not human-verified.\n'
              ' * v3: branches + delay slots. */') % (gcl.ROM_LABEL, addr, size)
    c_text = (banner + '\n'
              '#include <stdint.h>\n'
              'uint32_t %s_%x(uint32_t r4, uint32_t r5, uint32_t r6, uint32_t r7)\n'
              '{\n%s\n}\n') % (fn, addr, cbody)
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
                'frame': 'reg', 'ldc': 'reg'}
_BRANCH_COND = {'bt': 'T', 'bts': 'T', 'bf': 'notT', 'bfs': 'notT', 'bra': 'always'}


def _code_literal(records):
    """Render the interpreter's CODE = {addr: inst} dict as Python source."""
    lines = []
    for rec in records:
        pc = rec['pc']
        if rec['kind'] == 'branch':
            bi = ops.branch_info(rec['op'])
            bkind = bi['kind']
            slot = rec.get('slot')
            slot_py = '\n'.join(slot['py']) if slot and slot.get('py') else None
            if bkind == 'rts':
                lines.append('    %#x: {"kind": "ret", "py": None, '
                             '"slot_py": %r, "target": None, "cond": None},'
                             % (pc, slot_py))
            else:
                lines.append('    %#x: {"kind": "branch", "py": None, '
                             '"slot_py": %r, "target": %#x, "cond": %r},'
                             % (pc, slot_py, rec['target'], _BRANCH_COND[bkind]))
        else:
            py = '\n'.join(rec.get('py') or []) or None
            lines.append('    %#x: {"kind": %r, "py": %r, "slot_py": None, '
                         '"target": None, "cond": None},'
                         % (pc, _MIRROR_KIND[rec['kind']], py))
    return 'CODE = {\n%s}\n' % '\n'.join(lines)


def emit_v3_test(addr, name, size, rom, records, info, seed, out_t):
    """Write c/tests/test_<name>_<addr>.py for one compile-gated v3 lift."""
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
        'N = 2000\n'
        'MAXSTEPS = 100000\n'
        'STACK_BASE = 0xFFFFD000\n'
        'STACK_TOP = STACK_BASE + 0x400\n'
        'STACK_OFFS = (%s)\n'
        'RAM_MIN = %s\n'
        'RAM_MAX = %s\n\n'
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
        '    """pc-interpreter over CODE; returns ("RET", regs, writes, ram, pr) or\n'
        '    ("SKIP"/"ERR", detail).  Every instruction is the mapper py fragment\n'
        '    exec\'d in a shared ns (registers/T/ram/writes follow sh2emu)."""\n'
        '    global _WRITES\n'
        '    _WRITES[:] = []\n'
        '    r = [0] * 16\n'
        '    r[4], r[5], r[6], r[7] = r4 & 0xFFFFFFFF, r5 & 0xFFFFFFFF, r6 & 0xFFFFFFFF, r7 & 0xFFFFFFFF\n'
        '    r[15] = STACK_TOP & 0xFFFFFFFF\n'
        '    ns = {"r": r, "T": 0, "Q": 0, "M": 0, "mach": 0, "macl": 0, "pr": 0xEEEE0000,\n'
        '          "s8": s8, "s16": s16, "s32": s32, "ram": ram, "sp": r[15],\n'
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
        '        elif kind == "ret":\n'
        '            slot_py = inst["slot_py"]\n'
        '            if slot_py:\n'
        '                exec(slot_py, ns)\n'
        '            r[15] = ns["sp"] & 0xFFFFFFFF\n'
        '            return ("RET", [x & 0xFFFFFFFF for x in r], _WRITES, ram, ns["pr"] & 0xFFFFFFFF)\n'
        '        else:\n'
        '            py = inst["py"]\n'
        '            if py:\n'
        '                exec(py, ns)\n'
        '            pc = pc + 2\n\n'
        'def run(cpu, ram, a, b, c_, d):\n'
        '    end = ENTRY + len(RAW)\n'
        '    ram = dict(ram)\n'
        '    ram[end] = 0x00; ram[end + 1] = 0x0B; ram[end + 2] = 0x00; ram[end + 3] = 0x09\n'
        '    cpu.call(ENTRY, r4=a, r5=b, r6=c_, r7=d, ram=ram, regs={15: STACK_TOP},\n'
        '             max_steps=MAXSTEPS)\n'
        '    out = dict(cpu.ram)\n'
        '    for i in range(4):\n'
        '        out.pop(end + i, None)\n'
        '    return cpu.r[0] & 0xFFFFFFFF, [x & 0xFFFFFFFF for x in cpu.r], out, cpu.pr & 0xFFFFFFFF\n\n'
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
        '        m = spec_mirror(a, b, c_, d, dict(ram))\n'
        '        if m[0] != "RET":\n'
        '            skipped += 1\n'
        '            continue\n'
        '        try:\n'
        '            g = run(cpu, ram, a, b, c_, d)\n'
        '        except (StepLimitExceeded, NotImplementedError, RuntimeError):\n'
        '            skipped += 1\n'
        '            continue\n'
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
    ) % (fn, addr, size, 2000, fn, addr, addr, flat, seed, stack_offs,
         'None' if ram_min is None else '0x%X' % ram_min,
         'None' if ram_max is None else '0x%X' % ram_max,
         _code_literal(records))

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


def print_dryrun(pool, counters, args):
    """--dryrun report: pool + rejection reasons + branch breakdown."""
    rej = counters['rejected']
    print('=== v3 selection (--dryrun): no files written ===')
    print('pool_v3=%d' % counters['selected'])
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


def main():
    ap = argparse.ArgumentParser(
        description='Generate v3 C lifts (branches + delay slots) for SH-2 functions')
    ap.add_argument('--category', default=None,
                    help='filter by FUNCTION_CATEGORIES category')
    ap.add_argument('--n', type=int, default=1,
                    help='number of functions to lift')
    ap.add_argument('--seed', type=int, default=0,
                    help='RNG seed (deterministic selection)')
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
    catalog = gcl.load_catalog_end(os.path.join(ROOT, 'symbols', 'CATALOG_MASTER.csv'))
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

    outdir = args.outdir if os.path.isabs(args.outdir) else os.path.join(ROOT, args.outdir)
    selected, counters = select_v3(cands, args.n, args.seed, rom, catalog,
                                   outdir=outdir)
    if args.dryrun:
        print_dryrun(selected, counters, args)
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
        if not emit_v3(e['addr'], e['name'], e['size'], rom, out_c):
            dropped += 1
            report.append((lf, 'dropped_compile'))
            continue
        emitted += 1
        print('lifted 0x%X %-40s size=%3d -> %s'
              % (e['addr'], e['name'], e['size'], out_c))
        out_t = os.path.join(ROOT, 'c', 'tests', 'test_%s_%x.py' % (base, e['addr']))
        walked = walk_v3(rom, e['addr'], e['addr'] + e['size'])
        if walked is None:                       # cannot happen after emit_v3
            report.append((lf, 'test_skipped'))
            continue
        records, info, labels = walked
        if emit_v3_test(e['addr'], e['name'], e['size'], rom, records, info,
                        args.seed, out_t):
            res = run_test(out_t)
            report.append((lf, res))
            print('test 0x%X %-40s -> %s %s' % (e['addr'], e['name'], res, out_t))
        else:
            report.append((lf, 'test_write_failed'))
    print('emitted=%d dropped_compile=%d' % (emitted, dropped))
    if report:
        g = sum(1 for _, r in report if r == 'PASS')
        f = sum(1 for _, r in report if r == 'FAIL')
        print('test report: generated=%d pass=%d fail=%d' % (len(report), g, f))
        for name, res in report:
            print('  %-10s %s' % (res, name))


if __name__ == '__main__':
    main()
