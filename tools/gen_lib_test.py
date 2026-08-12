#!/usr/bin/env python3
"""gen_lib_test.py — differential run-test harness for c/lib/f_*.c bodies.

For a lib address, builds the v8 CFG lift over the same span rules the lib
regen used (_emit_callee_cfg: ghidra-span / rts-scan effective end, walk-end
fixpoint, delay_slot_ctrl +2/+4 extensions), compile-gates the COMMITTED
c/lib/f_<hex>.c with the same flags caller tests use (cc -O2 -c), then emits
test_lib_<hex>.py: the same Python pc-interpreter spec-mirror vs sh2emu-oracle
differential as test_caller_*.py, but with ENTRY=lib addr and N random r4..r7
inputs (default seed=42, cases=10).  Per-case PASS/FAIL + reason come from the
test's stdout (MISMATCH case=.. reg=.. / addr=0x.. / SKIP reasons).

Usage:
  python3 tools/gen_lib_test.py --emit 0x1B3EA [--cases 10] [--seed 42]
  python3 tools/gen_lib_test.py --addrs 0x1B3EA,0x686A0 --csv
  python3 tools/gen_lib_test.py --list-20
  python3 tools/gen_lib_test.py --sweep-all       # all 1059 already-lib addrs
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import gen_c_lift_v8 as G

BANK = '60E0FC00'
ROM_PATH = os.path.join(ROOT, 'roms', 'stock', '%s.bin' % BANK)
LIB_DIR = os.path.join(ROOT, 'c', 'lib')

# The 20-lib validation set (task spec): 5 OTHER-BUG + 10 CFG + 5 v7leaf.
OTHER_BUG = [0x29DEA, 0x686A0, 0x54BE, 0x5DDC, 0x387A2]
CFG_SET = [0x3E38A, 0x1B3EA, 0xE278]
V7_SET = [0x30570, 0x5D9B8]


def _banner_kind(addr):
    """'cfg' / 'v7' / 'stub' / 'missing' for the committed c/lib/f_<hex>.c."""
    p = os.path.join(LIB_DIR, 'f_%X.c' % addr)
    if not os.path.exists(p):
        return 'missing'
    with open(p, 'r', errors='replace') as f:
        head = f.read(600)
    if 'STUB' in head:
        return 'stub'
    if 'gen_c_lift_v8.py' in head:
        return 'cfg'
    return 'v7'


def _build_lib_cfg(addr, rom, catalog, bounds):
    """CFG lift of the lib span with _emit_callee_cfg's exact span/reject
    rules.  Returns (res, cfg_end, None) or (None, None, reason)."""
    end_c = G._callee_eff_end(rom, addr, catalog, bounds)
    if end_c is None:
        return None, None, ('callee-no-span', addr)
    cfg_end = min(G._callee_walk_end(rom, addr, end_c) + 2, end_c)
    lifted = G._load_lifted()
    res = G.build_cfg(rom, addr, cfg_end, lifted, catalog,
                      allow_runtime_base=True, tail_bra_as_call=True,
                      data_tail_ok=True)
    if res.reject is not None:
        _rej = res.reject
        if isinstance(_rej, tuple) and _rej[0] == 'midfunc_nested':
            res = G.build_cfg(rom, addr, cfg_end, lifted, catalog,
                              allow_runtime_base=True, tail_bra_as_call=True,
                              allow_boundary_entry=True, data_tail_ok=True)
        elif isinstance(_rej, tuple) and _rej[0] == 'delay_slot_ctrl':
            cfg_end = min(G._callee_walk_end(rom, addr, end_c) + 4, end_c + 2)
            res = G.build_cfg(rom, addr, cfg_end, lifted, catalog,
                              allow_runtime_base=True, tail_bra_as_call=True,
                              allow_boundary_entry=True, data_tail_ok=True)
    if res.reject is not None:
        return None, None, ('callee-cfg', addr, res.reject)
    if not res.records:
        return None, None, ('callee-cfg', addr, 'no_records')
    return res, cfg_end, None


def _compile_gate(addr):
    """Compile the committed C body with the caller-test flags (cc -O2 -c)."""
    c_path = os.path.join(LIB_DIR, 'f_%X.c' % addr)
    if not os.path.exists(c_path):
        return False, 'missing-c'
    tmp_obj = os.path.join(tempfile.gettempdir(),
                           'gen_lib_test_%d.o' % os.getpid())
    gate = subprocess.run(['cc', '-O2', '-c', c_path, '-o', tmp_obj],
                          capture_output=True, text=True)
    if os.path.exists(tmp_obj):
        os.remove(tmp_obj)
    if gate.returncode != 0:
        return False, (gate.stderr or '').strip().split('\n')[-1][:160]
    return True, None


def gen_lib_test(addr, rom, catalog, bounds, outdir, seed=42, cases=10):
    """Emit + return (test_path, ok, reason).  Test is NOT run here."""
    res, cfg_end, err = _build_lib_cfg(addr, rom, catalog, bounds)
    if err is not None:
        return None, False, err
    ok_g, g_err = _compile_gate(addr)
    if not ok_g:
        return None, False, ('lib-compile', addr, g_err)
    callees = sorted({r['target'] for r in res.records
                      if r['kind'] == 'call' and r.get('target') is not None})
    # target INCLUSION like emit_caller: rt-dispatch entries are extra leaves.
    rt_entries = sorted({e for r in res.records for e in (r.get('rt_entries') or [])})
    os.makedirs(outdir, exist_ok=True)
    out_t = os.path.join(outdir, 'test_lib_%X.py' % addr)
    try:
        ok, reason = G._emit_v8_test(addr, rom, cfg_end, res, callees, out_t,
                                     seed=seed, cases=cases, rom_label=BANK,
                                     catalog=catalog, bounds=bounds,
                                     rt_entries=rt_entries)
    except Exception as e:  # walker rough edges (e.g. dynbase 'dest' KeyError)
        return None, False, ('test-exc', addr, type(e).__name__, str(e)[:120])
    if not ok:
        return None, False, reason
    return out_t, True, None


def _run_test(addr, test_path, timeout=120):
    p = subprocess.run([sys.executable, test_path], capture_output=True,
                       text=True, timeout=timeout)
    out = (p.stdout or '') + (p.stderr or '')
    lines = [l for l in out.splitlines() if l.strip()]
    verdict_line = ''
    for l in reversed(lines):
        if l.startswith(('PASS ', 'FAIL ', 'LOOP ', 'HALT ', 'MISMATCH')):
            verdict_line = l
            break
    if p.returncode == 0 and verdict_line.startswith(('PASS', 'LOOP', 'HALT')):
        if verdict_line.startswith(('LOOP', 'HALT')):
            return 'UNVERIFIED', verdict_line, out
        return 'PASS', verdict_line, out
    if p.returncode == 0:
        return 'WEAK-PASS', verdict_line or 'rc=0 no-verdict', out
    # rc != 0: pick the first MISMATCH / error line as the failure reason
    why = ''
    for l in lines:
        if l.startswith('MISMATCH') or l.startswith('Traceback') or \
           l.startswith('ERROR'):
            why = l
            break
    return 'FAIL', (verdict_line or why or 'rc=%s' % p.returncode), out


def _load_rom_catalog():
    rom = open(ROM_PATH, 'rb').read()
    cat_path = os.path.join(ROOT, 'symbols', 'CATALOG_MASTER.csv')
    catalog, _, bounds = G._load_catalog(cat_path, BANK)
    return rom, catalog, bounds


def pick_20():
    """The 20-lib set: 5 OTHER-BUG + 10 CFG + 5 v7leaf (all in the 1059)."""
    addrs = [int(x) for x in open('/tmp/opencode/lib_addrs.txt')]
    cfg_pool = [a for a in addrs if _banner_kind(a) == 'cfg']
    v7_pool = [a for a in addrs if _banner_kind(a) == 'v7']
    cfg20 = []
    for a in CFG_SET:
        if a in cfg_pool and a not in cfg20:
            cfg20.append(a)
    for a in cfg_pool:
        if len(cfg20) >= 10:
            break
        if a in OTHER_BUG:
            continue
        if a not in cfg20:
            cfg20.append(a)
    v720 = []
    for a in V7_SET:
        if a in v7_pool and a not in v720:
            v720.append(a)
    for a in v7_pool:
        if len(v720) >= 5:
            break
        if a in OTHER_BUG:
            continue
        if a not in v720:
            v720.append(a)
    return OTHER_BUG + cfg20[:10] + v720[:5]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--emit', default=None, metavar='0xADDR')
    ap.add_argument('--addrs', default=None,
                    help='comma list of addrs (hex 0x.. or f_XXXXXX names)')
    ap.add_argument('--list-20', action='store_true')
    ap.add_argument('--sweep-all', action='store_true')
    ap.add_argument('--cases', type=int, default=10)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--outdir', default=os.path.join(ROOT, 'tmp', 'v8'))
    ap.add_argument('--timeout', type=int, default=120)
    ap.add_argument('--csv', default='/tmp/opencode/libtest_results.csv')
    ap.add_argument('--run', action='store_true',
                    help='also run the generated tests')
    args = ap.parse_args()

    rom, catalog, bounds = _load_rom_catalog()

    if args.list_20:
        for a in pick_20():
            print('0x%X %s %s' % (a, _banner_kind(a),
                                  'BUG' if a in OTHER_BUG else ''))
        return 0

    if args.emit:
        addr = int(args.emit, 16)
        t0 = time.time()
        test_path, ok, reason = gen_lib_test(
            addr, rom, catalog, bounds, args.outdir,
            seed=args.seed, cases=args.cases)
        if not ok:
            print('EMIT FAILED 0x%X: %s' % (addr, G._fmt_reason(reason)))
            return 1
        print('emitted %s (%.1fs)' % (test_path, time.time() - t0))
        if args.run:
            sys.exit(subprocess.run([sys.executable, test_path]).returncode)
        return 0

    if args.sweep_all or args.addrs or args.csv:
        if args.sweep_all:
            addrs = [int(x) for x in open('/tmp/opencode/lib_addrs.txt')]
        elif args.addrs:
            addrs = []
            for tok in args.addrs.split(','):
                tok = tok.strip()
                if tok.lower().startswith('0x'):
                    addrs.append(int(tok, 16))
                elif tok.lower().startswith('f_'):
                    addrs.append(int(tok[2:], 16))
                else:
                    addrs.append(int(tok, 16))
        else:
            addrs = pick_20()
        rows = []
        for addr in addrs:
            kind = _banner_kind(addr)
            test_path, ok, reason = gen_lib_test(
                addr, rom, catalog, bounds, args.outdir,
                seed=args.seed, cases=args.cases)
            if not ok:
                rows.append((addr, 'EMIT-FAIL', kind,
                             G._fmt_reason(reason)))
                print('0x%X %-10s %s' % (addr, 'EMIT-FAIL', reason))
                continue
            status, verdict, out = _run_test(addr, test_path, args.timeout)
            notes = verdict.replace('\n', ' ')
            rows.append((addr, status, kind, notes))
            print('0x%X %-10s %-5s %s' % (addr, status, kind, notes))
        if args.csv:
            with open(args.csv, 'w') as f:
                f.write('addr,result,kind,notes\n')
                for addr, status, kind, notes in rows:
                    f.write('0x%X,%s,%s,%s\n' % (addr, status, kind,
                                                 notes.replace(',', ';')))
            print('wrote %s (%d rows)' % (args.csv, len(rows)))
        return 0

    ap.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
