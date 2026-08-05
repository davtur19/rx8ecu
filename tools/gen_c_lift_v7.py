#!/usr/bin/env python3
"""gen_c_lift_v7.py — SH-2 call-composition (v7) for gen_c_lift_v3.

Two halves:

1) pool_v5 selection (--pool): the faithful "admit calls" re-scan (verbatim
   _scan_mem_function with the call branch recording instead of rejecting).
   A candidate is pool_v5 iff the whole sanitized span passes every other
   criterion and it holds >=1 jsr/bsr whose targets resolve to already-lifted
   addresses (or that can be re-emitted as c/lib/f_<hex>.c callees).
   --pool prints the real numbers (v4-cat and v3-est universes).

2) ST-based callee library emission (--callee 0xADDR): re-emit an already-lifted
   LEAF function as c/lib/f_<hex>.c with the shared-state ABI
       void f_<hex>(ST *s)
   reading args from s->r[4..5], writing results to s->r[0]/s->T/s->ram.
   ST is a POD struct (r[16], T, Q, M, macl, mach, sr, pr, gbr, fpul, fpscr,
   fr[16] bit patterns, ram pointer + bank base).  Compile-gated with
   `cc -O2 -c`; the file is deleted if the gate fails.  Never touches the
   existing c/*.c lifts.

Design notes (v7):
  - call semantic: s->pr = <retaddr>; <delay slot>; f_<callee>(s);  (pr always)
  - tail jmp: f_<callee>(s); return;
  - callee clobbering r8..r14 without saving -> composition mismatch -> the
    caller is dropped (detected, not silently wrong).
  - recursion/cycles -> skipped (depth guard 8).

Usage:
    python3 tools/gen_c_lift_v7.py --pool
    python3 tools/gen_c_lift_v7.py --callee 0x3EE58 [--outdir c/lib]
"""
import argparse
import glob
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import c_lift_ops as ops
import gen_c_lift as gcl
import gen_c_lift_v3 as v3
_MIRROR_KIND = v3._MIRROR_KIND

DEFAULT_ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
MASK = 0xFFFFFFFF

# ---------------------------------------------------------------------------
# ST (shared state) struct — the v7 ABI.  All composed functions take one ST*
# and exchange arguments/results/state through it, exactly mirroring the SH-2
# register file + pr + T + FPU state + RAM overlay that sh2emu's call() sets up.
# ---------------------------------------------------------------------------
ST_STRUCT = (
    'typedef struct {\n'
    '    uint32_t r[16];\n'
    '    uint32_t pr, T, Q, M, macl, mach, sr, gbr, fpul, fpscr;\n'
    '    uint32_t fr[16];   /* FPU bit patterns (IEEE-754) */\n'
    '    uint32_t ram_base; /* bank base (0 for 60E1D400-style flat test) */\n'
    '} ST;\n'
)

# Token rewrite table: existing per-function lift fragments use rN/T/macl/... as
# locals; the ST body rewrites them to s->r[N]/s->T/...  The rewriter is applied
# to the record C fragments (per-record, so temps/local_%x stay per-function).
_RE_R = re.compile(r'\br(?:[0-9]|1[0-5])\b')
_RE_SYS = re.compile(r'\b(pr|T|Q|M|macl|mach|sr|gbr|fpul|fpscr)\b')
_FR = re.compile(r'\bfr(?:[0-9]|1[0-5])\b')


def to_st_c(c_text):
    """Rewrite a per-function C fragment to the shared-state form.  Memory ops
    are absolute-address volatile stores (unchanged — RAM in the diff test is a
    flat overlay).  Temps (tN) and local_%x stack slots remain per-function
    locals (a leaf callee owns its frame)."""
    out = _RE_R.sub(lambda m: 's->r[%s]' % m.group(0)[1:], c_text)
    out = _RE_SYS.sub(lambda m: 's->%s' % m.group(0), out)
    # v7 ABI: functions are void and return through s->r[0] — map return stmts
    out = re.sub(r'return\s+s->r\[0\]\s*;', 'return;', out)
    return out


def _render_st(records, labels, fn, addr, size, banner_extra=''):
    """Render the ST body of an already-walked v3 span.  `fn` is the C
    function name.  Returns the full C source string (no header)."""
    body = []
    body.append('void %s(ST *s)' % fn)
    body.append('{')
    # locals: only temps + stack slots (registers/system live in s)
    body_text = '\n'.join(''.join(r.get('c') or []) for r in records)
    for rec in records:
        slot = rec.get('slot')
        if slot is not None:
            body_text += '\n' + '\n'.join(slot.get('c') or [])
    # per-function stack slots (local_%x) and fp locals: keep the same shape
    stmts = []
    for rec in records:
        pc = rec['pc']
        if pc in labels:
            stmts.append('L_%X: ;' % pc)
        stmts.append('/* 0x%06X: %s */' % (pc, rec['mnem']))
        slot = rec.get('slot')
        if slot is not None:
            if slot['pc'] in labels:
                stmts.append('L_%X: ;' % slot['pc'])
            stmts.append('/* 0x%06X: %s */' % (slot['pc'], slot['mnem']))
            stmts.extend(to_st_c(s) for s in slot.get('c') or [])
        if rec.get('kind') == 'call':
            stmts.extend(rec.get('c') or [])     # already ST-form
        else:
            stmts.extend(to_st_c(s) for s in rec.get('c') or [])
    offs = set()
    for m_ in re.finditer(r'local_([0-9a-f]+)\b', '\n'.join(stmts)):
        offs.add(int(m_.group(1), 16))
    for o in sorted(offs):
        body.append('    uint32_t local_%x = 0;' % o)
    frs = set()
    for m_ in _FR.finditer('\n'.join(stmts)):
        frs.add(m_.group(0))
    for f in sorted(frs):
        body.append('    uint32_t %s = 0;' % f)
    for s in stmts:
        body.append('    ' + s)
    body.append('    return; /* fallthrough */')
    body.append('}')
    return '\n'.join(body)


def emit_callee(addr, size, rom, out_c, rom_label=None, force_name=None):
    """Re-emit a (call-free) span as c/lib/f_<hex>.c (ST ABI).
    Compile-gates with cc -O2 -c; deletes on failure."""
    fn = force_name or ('f_%X' % addr)
    walked = v3.walk_v3(rom, addr, addr + size)
    if walked is None:
        return False, 'walk_diverged'
    records, info, labels = walked
    has_fpu = v3._records_have_fpu(records)
    body = _render_st(records, labels, fn, addr, size)
    banner = ('/* ROM: %s | Address: 0x%X | Size: %d bytes | STATUS: DRAFT\n'
              ' * Auto-generated by tools/gen_c_lift_v7.py — ST (shared state) ABI,\n'
              ' * leaf callee library (c/lib/f_<hex>.c). Never replaces c/*.c. */\n'
              ) % (rom_label or gcl.ROM_LABEL, addr, size)
    c_text = (banner + '#include <stdint.h>\n' + ST_STRUCT + '\n' + body + '\n')
    with open(out_c, 'w') as f:
        f.write(c_text)
    tmp_obj = os.path.join(tempfile.gettempdir(),
                           'gen_c_lift_v7_%d.o' % os.getpid())
    gate = subprocess.run(['cc', '-O2', '-c', out_c, '-o', tmp_obj],
                          capture_output=True, text=True)
    if os.path.exists(tmp_obj):
        os.remove(tmp_obj)
    if gate.returncode != 0:
        os.remove(out_c)
        return False, gate.stderr[:300]
    return True, None


# ---------------------------------------------------------------------------
# pool_v5 selection — the faithful admit-calls re-scan.
# ---------------------------------------------------------------------------

def emit_compose(addr, rom, outdir, cat, end_bounds, rom_label=None,
                 use_est=False, force=False):
    """Emit caller_<hex>.c (ST ABI) that jsr/bsr/jmp-calls its callees via the
    shared state struct.  Returns (out_path, reason, ok).  Emits even when the
    callee chain is unclean — unlinked/DRAFT callers reference f_<hex> that the
    lib must define (emit_callee per callee)."""
    fn = 'caller_%X' % addr
    end = cat.get(addr)
    if end is None and use_est:
        end = v3._next_addr(addr, end_bounds)
    if end is None:
        return None, 'no-span', False
    c = {'addr': addr, 'name': 'fwd'}
    entry, reason = scan_admit_calls(rom, c, end)
    if entry is None:
        return None, reason, False
    entry['name'] = fn
    records, labels, err = _call_records(entry, rom, end, cat, end_bounds,
                                         use_est=use_est)
    if records is None:
        return None, err, False
    body = _render_st(records, labels, fn, addr, end - addr)
    fwd = '\n'.join('void f_%X(ST *s);' % r['target']
                    for r in records if r.get('kind') == 'call'
                    and r.get('target') is not None)
    body = (fwd + '\n' if fwd else '') + body
    banner = ('/* ROM: %s | Address: 0x%X | Size: %d bytes | STATUS: DRAFT\n'
              ' * Auto-generated by tools/gen_c_lift_v7.py — ST caller.\n'
              ' * jsr/bsr -> s->pr=<ret>; <delay slot>; f_<callee>(s);\n'
              ' * jmp -> f_<callee>(s); return;  (tail). Never replaces c/*.c. */\n'
              ) % (rom_label or gcl.ROM_LABEL, addr, end - addr)
    c_text = banner + '#include <stdint.h>\n' + ST_STRUCT + '\n' + body + '\n'
    os.makedirs(outdir, exist_ok=True)
    out_c = os.path.join(outdir, '%s.c' % fn)
    with open(out_c, 'w') as f:
        f.write(c_text)
    tmp_obj = os.path.join(tempfile.gettempdir(),
                           'gen_c_lift_v7_%d.o' % os.getpid())
    gate = subprocess.run(['cc', '-O2', '-c', out_c, '-o', tmp_obj],
                          capture_output=True, text=True)
    if os.path.exists(tmp_obj):
        os.remove(tmp_obj)
    if gate.returncode != 0:
        os.remove(out_c)
        return out_c, gate.stderr[:200], False
    return out_c, None, True


_BRANCH_COND = {'bt': 'T', 'bts': 'T', 'bf': 'notT', 'bfs': 'notT'}


def collect_compose(addr, rom, cat, end_bounds, use_est=False, depth=0,
                    seen=None):
    """Flatten a caller + all reachable callee records into one span-agnostic
    edit-list, merging each callee's walk_v3 records at their real pcs and the
    caller's call records.  Returns (records, info) or (None, reason)."""
    if depth > 8:
        return None, ('depth>8', addr)
    if seen is None:
        seen = set()
    if addr in seen:
        return [], {'stack_offs': set(), 'ram_addrs': set()}
    seen = seen | {addr}
    end = cat.get(addr)
    if end is None and use_est and end_bounds is not None:
        end = v3._next_addr(addr, end_bounds)
    if end is None:
        return None, ('no-span', addr)
    entry, reason = scan_admit_calls(rom, {'addr': addr, 'name': 'x'}, end)
    if entry is None:
        return None, (addr, reason)
    records, labels, err = _call_records(entry, rom, end, cat, end_bounds,
                                         use_est=use_est)
    if records is None:
        return None, (addr, err)
    rec = list(records)
    info = {'stack_offs': set(), 'ram_addrs': set()}
    call_tgts = [r['target'] for r in records
                 if r.get('kind') == 'call' and r.get('target') is not None]
    for tgt in sorted(set(call_tgts)):
        sub, einfo = collect_compose(tgt, rom, cat, end_bounds,
                                     use_est=use_est, depth=depth + 1,
                                     seen=seen)
        if sub is None:
            return None, (addr, ('callee-chain', tgt, einfo))
        rec.extend(sub)
        info['stack_offs'] |= einfo['stack_offs']
        info['ram_addrs'] |= einfo['ram_addrs']
    return rec, info


def _s12(x):
    return ((x - 0x1000) if (x & 0x800) else x)


def compose_code_literal(records):
    """CODE dict for a composition: caller's call records (kind 'call') plus
    every callee's walk_v3 records at their real pcs.  Nested rts pops pr."""
    lines = []
    for rec in records:
        pc = rec['pc']
        if rec.get('kind') == 'call':
            slot = rec.get('slot')
            slot_py = '\n'.join(slot['py']) if slot and slot.get('py') else None
            lines.append('    %#x: {"kind": "call", "py": None,'
                         ' "slot_py": %r, "target": %#x, "ret_pc": %#x,'
                         ' "set_pr": %r, "cond": None},'
                         % (pc, slot_py, rec['target'], rec['ret_pc'],
                            rec['set_pr']))
            continue
        bi = ops.branch_info(rec.get('op')) if rec.get('op') is not None else None
        if rec['kind'] == 'branch' and bi is not None:
            bkind = bi['kind']
            slot = rec.get('slot')
            slot_py = '\n'.join(slot['py']) if slot and slot.get('py') else None
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
        py = '\n'.join(rec.get('py') or []) or None
        lines.append('    %#x: {"kind": %r, "py": %r, "slot_py": None, '
                     '"target": None, "cond": None},'
                     % (pc, _MIRROR_KIND.get(rec['kind'], 'st'), py))
    return 'CODE = {\n%s}\n' % '\n'.join(lines)


def emit_compose_test(addr, rom, cat, end_bounds, out_t, seed=42, N=2000,
                      rom_label='60E1D400', use_est=False):
    """Write a differential test for a call-composition: the Python pc-mirror
    runs the flattened caller+callee CODE with nested-return semantics ('call'
    jmps to the callee; 'rts' pops pc=pr) against the sh2emu oracle running the
    real ROM bytes from the caller entry.  Cases leaving the model -> skip."""
    records, info = collect_compose(addr, rom, cat, end_bounds, use_est=use_est)
    if records is None:
        return False, info
    entry, reason = scan_admit_calls(rom, {'addr': addr, 'name': 'x'},
                                     cat.get(addr))
    n_sites = len(entry['call_sites']) if entry is not None else 0
    if n_sites > 1:
        # multi-dispatch callers have conditional branches reaching a second
        # jmp past the first — needs full CFG modeling, out of scope for the
        # linear tail-dispatch composition.
        return False, ('multi-dispatch: %d call sites (full CFG needed)' % n_sites)
    offs_list = sorted(info['stack_offs'])
    stack_offs = ', '.join('0x%X' % o for o in offs_list)
    if len(offs_list) == 1:
        stack_offs += ','
    ram_addrs = [v for v in info['ram_addrs'] if ops.classify_addr(v) == 'RAM']
    ram_min = min(ram_addrs) if ram_addrs else None
    ram_max = max(ram_addrs) if ram_addrs else None
    entry = addr
    fn = 'caller_%X' % addr
    test = (
        '#!/usr/bin/env python3\n'
        '"""Differential test for call-composition %s (entry 0x%X) — v7 ST caller'
        ' + callee lib, flattened CODE with nested returns.\n'
        'Auto-generated by tools/gen_c_lift_v7.py — not human-verified.\n'
        'Compares a Python pc-interpreter spec_mirror (running the caller and'
        ' every inlined callee; rts pops pc=pr, call jmps to callee) against the'
        ' sh2emu oracle over %d random inputs.  Cases leaving the modeled span /'
        ' exceeding max_steps are skipped.\n'
        'Run: python3 %s\n'
        '"""\n'
        'import os, random, sys\n\n'
        'ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n'
        'sys.path.insert(0, os.path.join(ROOT, "tools"))\n'
        'from sh2emu import SH2, StepLimitExceeded\n'
        'from c_lift_ops import s8, s16, s32\n\n'
        'ROM = os.path.join(ROOT, "roms", "stock", "60E1D400.bin")\n'
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
        'PRET = 0xEEEE0000\n\n'
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
        '    ns = {"r": r, "T": 0, "Q": 0, "M": 0, "mach": 0, "macl": 0, "pr": PRET,\n'
        '          "sr": 0x000000F0, "s8": s8, "s16": s16, "s32": s32, "ram": ram,\n'
        '          "sp": r[15], "_rdw": _rdw, "_wrw": _wrw, "STACK_BASE": STACK_BASE}\n'
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
        '        if kind == "call":\n'
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
        '    if skipped > 200:\n'
        '        print("FAIL %%d/%%d (skipped=%%d)" %% (ok, N, skipped))\n'
        '        sys.exit(1)\n'
        '    print("PASS %%d/%%d (skipped=%%d)" %% (ok, N, skipped))\n\n'
        'if __name__ == "__main__":\n'
        '    main()\n'
    ) % (fn, addr, N, out_t, entry, seed, N, stack_offs,
         'None' if ram_min is None else '0x%X' % ram_min,
         'None' if ram_max is None else '0x%X' % ram_max,
         compose_code_literal(records))
    with open(out_t, 'w') as f:
        f.write(test)
    return True, None


def resolve_call_target(entry, pc, kind, arg):
    """Static target of one call site from scan_admit_calls, or None.
    bsr: pc+4+disp*2; jmp/jsr: rN fetched from the lits snapshot at pc."""
    if kind == 'bsr':
        return (pc + 4 + _s12(arg) * 2) & gcl.MASK
    lits = entry.get('lits_at', {}).get(pc) or {}
    v = lits.get('r%d' % arg)
    if v is None:
        return None
    return v & gcl.MASK


def chain_validate(addr, rom, cat, end_bounds, use_est=False, depth=0, seen=None):
    """Recursively validate that caller `addr` and every resolvable callee in
    its call tree is clean (full-span scan_admit_calls passes), so a
    deterministic ST composition can be emitted and diff-verified.  Returns
    (ok, reason-or-None).  depth guard 8, cycle guard via `seen`."""
    if seen is None:
        seen = set()
    if depth > 8:
        return False, 'depth>8'
    if addr in seen:
        return True, None                       # cycle: already proven clean
    seen = seen | {addr}
    end = cat.get(addr)
    if end is None and use_est:
        end = v3._next_addr(addr, end_bounds)
    if end is None:
        return False, ('no-span', addr)
    c = {'addr': addr, 'name': 'x'}
    entry, reason = scan_admit_calls(rom, c, end)
    if entry is None:
        return False, (addr, reason)
    for (pc, kind, arg) in entry['call_sites']:
        tgt = resolve_call_target(entry, pc, kind, arg)
        if tgt is None:
            return False, (addr, ('unresolved', pc, kind))
        if cat.get(tgt) is None and not use_est and \
                v3._next_addr(tgt, end_bounds) is None:
            return False, (addr, ('no-span', tgt))
        if cat.get(tgt) is None and not use_est:
            t_end = tgt                     # in-span sibling (no own catalog row)
            sub_ok = True
        else:
            t_end = cat.get(tgt)
        ok, sub = chain_validate(tgt, rom, cat, end_bounds,
                                 use_est=use_est, depth=depth + 1, seen=seen)
        if not ok:
            return False, (addr, ('callee-chain', tgt, sub))
    return True, None


def _call_records(entry, rom, end, cat, end_bounds, use_est=False):
    """Render the caller's records for the whole span with calls kept in place.
    Uses walk_v3 per call-free segment and splices call records with their
    delay slot (P+2) as a `slot` like a delayed branch.  Returns (records,
    labels, info) or (None, None, reason)."""
    addr = entry['addr']
    call_pcs = sorted(set(pc for pc, _, _ in entry['call_sites']))
    records = []
    labels = set()
    info = {'stack_offs': set(), 'ram_addrs': set()}
    seg_start = addr
    seg_map = {}
    for (pc, kind, val) in entry['call_sites']:
        seg_map[pc] = (resolve_call_target(entry, pc, kind, val),
                       kind, (pc + 4) & gcl.MASK)
    for pc in call_pcs + [end]:
        if pc > seg_start:
            w = v3.walk_v3(rom, seg_start, pc)
            if w is None:
                return None, None, ('walk/free-seg', seg_start, pc)
            r, inf, lab = w
            records.extend(r)
            labels |= lab
            info['stack_offs'] |= inf['stack_offs']
            info['ram_addrs'] |= inf['ram_addrs']
        if pc >= end:
            break
        tgt, kind, ret = seg_map[pc]
        mnem = {'jsr': 'jsr @0x%X' % (tgt or 0), 'bsr': 'bsr 0x%X' % (tgt or 0),
                'jmp': 'jmp @0x%X' % (tgt or 0)}.get(kind, kind)
        # jmp @Rm is a DELAYED branch on SH-2 (SH-1/SH-2 Programming Manual
        # Table 4.2 lists JMP among the delayed-branch instructions): the P+2
        # slot executes BEFORE the branch, so a tail jmp's slot (typically the
        # last-arg setup, e.g. `mov #imm,r5`) runs and is visible to the
        # callee.  Emit it into the call record so the C caller and the test
        # mirror both execute it (the earlier "no delay slot" model only
        # matched the buggy emulator and silently dropped the slot).
        slot_c = []
        slot_rec = None
        if pc + 2 < end:
            sop = (rom[pc + 2] << 8) | rom[pc + 3]
            d = ops.translate(sop, pc + 2, rom)
            if d is not None:
                slot_c = list(d.get('c') or [])
                slot_rec = {'pc': pc + 2, 'kind': 'st', 'op': None,
                            'c': slot_c, 'py': list(d.get('py') or []),
                            'mnem': d.get('ann') or ('op 0x%04X' % sop),
                            'target': None, 'slot': None}
        if tgt is None:
            c = ['/* %s @0x%X: target not literal-resolvable */' % (kind, pc),
                 'return s->r[0]; /* UNLINKED (DRAFT) */']
        elif kind in ('jsr', 'bsr'):
            # real HW: PR := P+4, THEN delay slot runs, THEN branch to callee.
            c = ['s->pr = 0x%08X;' % ret] + slot_c + ['f_%X(s);' % tgt]
        else:                                # jmp: tail call — slot first, then callee; never returns
            c = ['f_%X(s);' % tgt, 'return;']
        records.append({'pc': pc, 'kind': 'call', 'mnem': mnem,
                        'slot': slot_rec if kind == 'jmp' else None,
                        'target': tgt, 'c': c,
                        'ret_pc': ret, 'set_pr': kind in ('jsr', 'bsr'),
                        'py': [], 'op': None})
        seg_start = pc + 2
        if kind == 'jmp':                    # tail dispatch: composition ends here
            break
    return records, labels, None


def scan_admit_calls(rom, c, end):
    """Verbatim _scan_mem_function with the call branch patched to RECORD and
    continue.  Returns (entry, call_sites) where entry is the standard entry or
    None (then the second element is the rejection reason); call_sites =
    [(pc, 'bsr', disp) | (pc, 'jsr', reg) | (pc, 'jmp', reg)]."""
    addr = c['addr']
    bound = min(end, len(rom))
    written = set()
    lits = {}
    tmp = [0]
    gbr_known = False
    gbr_value = None
    stack_ok = True
    frame_live = False
    call_sites = []
    lits_at = {}

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
    bases = {}
    ops_list = []
    lit_vals = []
    brs = []
    pc = addr
    while pc + 1 < bound:
        op = (rom[pc] << 8) | rom[pc + 1]
        d = ops.translate(op, pc, rom)
        if d is not None:
            if d.get('kind') in ('branch', 'ret'):
                target = d.get('target')
                admit, det = gcl._v3_branch_rule(rom, op, target, pc, addr, end)
                if admit:
                    brs.append((det, pc, target))
                    pc += 2
                    continue
                return None, ('branch_v3', det)
            writes = gcl._stmt_writes('\n'.join(d.get('c') or []))
            if op == 0x6E3F:
                if stack_ok and 'r14' not in written:
                    frame_live = True
            else:
                if 'r15' in writes:
                    stack_ok = False
                if 'r14' in writes:
                    frame_live = False
            if not gcl._apply_stmt(rom, pc, op, d, written, lits):
                return None, 'unmapped'
            pc += 2
            continue
        if op & 0xF0FF == 0x401E:
            gbr_known = True
            gbr_value = lits.get('r%d' % ((op >> 8) & 0xF))
            pc += 2
            continue
        if gcl.is_call_op(op):
            lits_at[pc] = dict(lits)
            if op & 0xF000 == 0xB000:
                call_sites.append((pc, 'bsr', op & 0xFFF))
            else:
                kind = 'jsr' if op & 0xF0FF == 0x400B else 'jmp'
                call_sites.append((pc, kind, (op >> 8) & 0xF))
            pc += 2
            continue
        if op == 0x002B:
            return None, 'rte'
        if gcl.is_branch_op(op):
            return None, 'branch'
        m = ops.decode_mem(op, None, ctx)
        if m is not None:
            base_reg = m['base_reg']
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
            gcl._apply_mem_writes(m, written, lits)
            pc += 2
            continue
        g = gcl._decode_gbr(op)
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
            gcl._apply_mem_writes(gm, written, lits)
            pc += 2
            continue
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
        if gcl.is_mem_opcode(op):
            return None, ('base_unresolved', 'altro')
        if gcl.is_fpu_op(op):
            return None, 'fpu/altre'
        return None, 'unmapped'

    if not ops_list and not call_sites:
        return None, 'no_mem_op'
    return ({'name': c['name'], 'addr': addr, 'size': end - addr,
             'bases': bases, 'ops': ops_list, 'literal_values': lit_vals,
             'branches': brs, 'call_sites': call_sites,
             'lits_at': lits_at}, None)


def s12(x):
    x &= 0xFFF
    return x - 0x1000 if x & 0x800 else x


def run_pool(rom_path=DEFAULT_ROM, outdir='c'):
    rom = open(rom_path, 'rb').read()
    rom_label = os.path.splitext(os.path.basename(rom_path))[0]
    outdir = outdir if os.path.isabs(outdir) else os.path.join(ROOT, outdir)
    cat_path = os.path.join(ROOT, 'symbols', 'CATALOG_MASTER.csv')
    catalog_bank, no_spans, bounds = v3.load_catalog_nospans(cat_path)
    catalog = catalog_bank.get(rom_label, {})
    end_bounds = bounds.get(rom_label)
    categories = gcl.load_categories(
        os.path.join(ROOT, 'symbols', 'FUNCTION_CATEGORIES.csv'))
    cands = v3._merge_nospan_cands(categories, no_spans, bounds, rom_label)

    lifted = set()
    for p in glob.glob(os.path.join(outdir, '*.c')):
        m = re.search(r'_([0-9a-fA-F]+)\.c$', p)
        if m:
            lifted.add(int(m.group(1), 16))
    for p in glob.glob(os.path.join(ROOT, 'c', 'lib', 'f_*.c')):
        m = re.search(r'_([0-9a-fA-F]+)\.c$', os.path.basename(p))
        if m:
            lifted.add(int(m.group(1), 16))

    print('already-lifted addresses: %d' % len(lifted))
    for flow, use_est in (('v4-cat', False), ('v3-est', True)):
        comp = []
        call_rej = 0
        for c in cands:
            addr = c['addr']
            end = catalog.get(addr)
            if end is None and use_est:
                end = v3._next_addr(addr, end_bounds)
            if end is None:
                continue
            _a, end_s, _r = v3.sanitize_span(addr, end, rom)
            if not (gcl.MEM_MIN <= end_s - addr <= gcl.MEM_MAX + 16):
                continue
            base = gcl.sanitize(c['name'])
            if os.path.exists(os.path.join(outdir, '%s_%x.c' % (base, addr))):
                continue
            entry, reason = gcl._scan_mem_function(rom, c, end_s, None)
            if entry is not None or reason != 'call':
                continue
            call_rej += 1
            e2, r2 = scan_admit_calls(rom, c, end_s)
            if e2 is None:
                continue
            sites = e2['call_sites']
            if not any(k in ('jsr', 'bsr') for _, k, _ in sites):
                continue
            comp.append((addr, c['name'], sites))
        print('[%s] call-rejected=%d  composable(has jsr/bsr)=%d'
              % (flow, call_rej, len(comp)))
        chain_ok = 0
        for addr, name, sites in sorted(comp):
            desc = ', '.join('%s@%X' % (k, pc) for pc, k, _ in sites)
            print('    0x%06X %-34s %s' % (addr, name, desc))
            ok, reason = chain_validate(addr, rom, catalog, end_bounds,
                                        use_est=use_est)
            if ok:
                chain_ok += 1
                print('         -> pool_v5 candidate (full chain clean)')
            else:
                print('         -> chain blocked: %s' % (reason,))
        print('     pool_v5 (full-chain clean) = %d' % chain_ok)
    return 0


def main():
    ap = argparse.ArgumentParser(
        description='v7 SH-2 call-composition: pool_v5 selection + ST callee lib')
    ap.add_argument('--pool', action='store_true',
                    help='print the real pool_v5 numbers (v4-cat / v3-est)')
    ap.add_argument('--callee', default=None,
                    help='re-emit this address as c/lib/f_<hex>.c (ST ABI)')
    ap.add_argument('--compose', default=None,
                    help='emit caller_<hex>.c for this address (ST ABI, jsr/bsr/jmp)')
    ap.add_argument('--compose-test', default=None,
                    help='emit a differential sh2emu test for this composition')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--cases', type=int, default=2000)
    ap.add_argument('--use-est', action='store_true',
                    help='use v3-est (next-addr) ends for no-span functions')
    ap.add_argument('--size', type=lambda s: int(s, 0), default=None,
                    help='callee span size in bytes (default: catalog end-addr)')
    ap.add_argument('--rom', default=DEFAULT_ROM)
    ap.add_argument('--outdir', default=os.path.join(ROOT, 'c', 'lib'),
                    help='directory for callee files (default c/lib)')
    args = ap.parse_args()

    if args.pool:
        return run_pool(args.rom, outdir=os.path.join(ROOT, 'c'))
    if args.callee:
        addr = int(args.callee, 16)
        rom = open(args.rom, 'rb').read()
        size = args.size
        if size is None:
            rom_label = os.path.splitext(os.path.basename(args.rom))[0]
            catalog_bank, _, _ = v3.load_catalog_nospans(
                os.path.join(ROOT, 'symbols', 'CATALOG_MASTER.csv'))
            end = catalog_bank.get(rom_label, {}).get(addr)
            if end is None:
                print('error: no catalog end for 0x%X; pass --size' % addr)
                return 2
            _a, end_s, _r = v3.sanitize_span(addr, end, rom)
            size = end_s - addr
        outdir = args.outdir if os.path.isabs(args.outdir) else \
            os.path.join(ROOT, args.outdir)
        os.makedirs(outdir, exist_ok=True)
        out_c = os.path.join(outdir, 'f_%X.c' % addr)
        ok, err = emit_callee(addr, size, rom, out_c,
                              rom_label=os.path.splitext(
                                  os.path.basename(args.rom))[0])
        if ok:
            print('emitted %s (size=%d)' % (out_c, size))
            return 0
        print('FAILED: %s' % err)
        return 1
    if args.compose:
        addr = int(args.compose, 16)
        rom = open(args.rom, 'rb').read()
        rom_label = os.path.splitext(os.path.basename(args.rom))[0]
        catalog_bank, _, bounds = v3.load_catalog_nospans(
            os.path.join(ROOT, 'symbols', 'CATALOG_MASTER.csv'))
        cat = catalog_bank.get(rom_label, {})
        end_bounds = bounds.get(rom_label)
        outdir = args.outdir if os.path.isabs(args.outdir) else \
            os.path.join(ROOT, args.outdir)
        out_c, reason, ok = emit_compose(addr, rom, outdir, cat, end_bounds,
                                         rom_label=rom_label,
                                         use_est=args.use_est)
        if ok:
            print('emitted %s' % out_c)
            return 0
        print('FAILED: %s' % reason)
        return 1
    if args.compose_test:
        addr = int(args.compose_test, 16)
        rom = open(args.rom, 'rb').read()
        rom_label = os.path.splitext(os.path.basename(args.rom))[0]
        catalog_bank, _, bounds = v3.load_catalog_nospans(
            os.path.join(ROOT, 'symbols', 'CATALOG_MASTER.csv'))
        cat = catalog_bank.get(rom_label, {})
        end_bounds = bounds.get(rom_label)
        outdir = args.outdir if os.path.isabs(args.outdir) else \
            os.path.join(ROOT, args.outdir)
        os.makedirs(outdir, exist_ok=True)
        out_t = os.path.join(outdir, 'test_caller_%X.py' % addr)
        ok, reason = emit_compose_test(addr, rom, cat, end_bounds, out_t,
                                       seed=args.seed, N=args.cases,
                                       rom_label=rom_label,
                                       use_est=args.use_est)
        if ok:
            print('emitted %s' % out_t)
            return 0
        print('FAILED: %s' % reason)
        return 1
    ap.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
