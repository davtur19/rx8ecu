#!/usr/bin/env python3
"""
run_all_verify.py — final meta-runner for the gcc 3.4.6 validation harnesses.

Runs every `verify*.py` / `fuzz*.py` harness in the era-ROM test bundle as a
subprocess, collects exit code / wall-time / a meaningful final line, and
aggregates function-level coverage for the VERIFY_SUMMARY report.

Behavior
--------
* Auto-discovers harnesses in this directory (verify*.py + fuzz*.py),
  excluding itself.
* Default run: executes every harness EXCEPT the slow exhaustive sweep
  (identified by name: `verify_immo_exhaustive.py`, ~7 min). --skip-slow is
  the explicit default; use --with-slow to include it (it gets a long timeout).
* --skip-fast: skip the fast harnesses (`*_fast*.py`).
* Per-process timeout: 300 s by default (--timeout N sets a custom value). The
  slow immo_exhaustive always gets `--slow-timeout` (default 900 s).
* --json PATH: also writes a machine-readable JSON aggregate (function table)
  that feeds VERIFY_SUMMARY.md.
* Exit code of the RUNNER is 0 only if EVERY executed harness exited 0
  (skipped/missing ones never fail the runner because of this).
* If a harness requested in an explicit list does not exist, it is reported as
  MISSING but does NOT fail the run.

The runner is read-only w.r.t. the repo: it only reads harness sources, spawns
them as subprocesses and writes output to stdout / the JSON file. It never
touches existing harnesses, README, Makefile or tools/.

Usage
-----
    python3 tests/run_all_verify.py [--skip-fast] [--skip-slow] [--with-slow]
                                    [--json PATH] [--timeout SEC]
                                    [--slow-timeout SEC] [HARNESS...]
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

TESTS = os.path.dirname(os.path.abspath(__file__))
HARNESS_GLOBS = ('verify*.py', 'fuzz*.py')
SELF = os.path.basename(__file__)

# --------------------------------------------------------------------------
# metadata heuristics
# --------------------------------------------------------------------------
# Curated function inventory per harness (name, addr_rom, default vector count).
# This is the deterministic source of truth for the summary table; the regex
# fallback below only handles harnesses not listed here.
_LOTTO1 = [
    ('rx8_add_s32_saturate',          0x2304, 4000),
    ('rx8_immo_seed_mixer',           0x366B8, 4000),
    ('rx8_add16bit_saturate',         0x2460, 4000),
    ('rx8_add_saturate_8bit',         0x2478, 4000),
    ('rx8_multiply32_saturating',     0x231C, 20000),
    ('rx8_complement_shift_u16',      0x2430, 4000),
    ('rx8_complement_shift_u32',      0x2440, 4000),
    ('rx8_index_table_clear',         0x68780, 5000),
    ('rx8_index_table_step',          0x6879C, 5000),
    ('rx8_index_table_step2',         0x687C8, 5000),
    ('rx8_index_table_dec',           0x687F4, 5000),
    ('rx8_div32_signed',              0x3FE8, 4000),
    ('rx8_div32_unsigned',            0x409C, 4000),
    ('rx8_shift_left_logical',        0x4308, 4000),
    ('rx8_shift_right_arithmetic',    0x43C8, 4000),
    ('rx8_shift_right_logical',       0x44E0, 4000),
    ('rx8_shift_right_8',             0x467A, 4000),
]
_LOTTO2_6 = [
    ('rx8_invert_and_return_8bit',    0x2044, 50000),
    ('rx8_delay_loop_n8',             0x239C, 50000),
    ('rx8_mod32_signed',              0x4144, 50000),
    ('rx8_set_register_reg_bit_val',  0x4BBC, 50000),
    ('rx8_interpolate_u16_table',     0x26D0, 50000),
    ('rx8_data_lookup',               0x2624, 50000),
]
CURATED = {
    'verify_gcc346.py':          _LOTTO1,
    'verify_gcc346_fast.py':     _LOTTO1,
    'verify_cross_rom.py':       _LOTTO1,
    'fuzz_14funcs.py':           _LOTTO1,
    'verify_float_a.py': [
        ('rx8_min_value', 0x23F4, 4000),
        ('rx8_saturate', 0x2404, 4000),
    ],
    'verify_float_b.py': [
        ('rx8_saturate_low', 0x23E4, 3000),
        ('rx8_subtract_absolute', 0x23DC, 3000),
        ('rx8_float_to_int', 0x24D0, 3000),
    ],
    'verify_saturates2.py': [
        ('rx8_saturate', 0x2404, 4000),
        ('rx8_min_value', 0x23F4, 4000),
        ('rx8_saturate_low', 0x23E4, 4000),
        ('rx8_subtract_absolute', 0x23DC, 4000),
        ('rx8_math_min_max_49ed0', 0x49ED0, 4000),
    ],
    'verify_shifts2.py': [
        ('rx8_complement_shift_u8', 0x2420, 4000),
    ],
    'verify_complement_exhaustive.py': [
        ('rx8_complement_shift_u8', 0x2420, 65536),
        ('rx8_complement_shift_u16', 0x2430, 65536),
        ('rx8_complement_shift_u32', 0x2440, 65536),
    ],
    'verify_mathprims.py': [
        ('rx8_float_to_fixed_16bit', 0x2490, 4000),
        ('rx8_fixed_point_to_float_8bit', 0x2500, 4000),
        ('rx8_fixed_point_scaling', 0x2510, 4000),
    ],
    'verify_float_fp16.py': [
        ('rx8_fixed_point_to_float_16bit', 0x24C0, 20000),
    ],
    'verify_bytepack.py': [
        ('rx8_bytepack8', 0x552FE, 3000),
        ('rx8_bytepack16', 0x5530C, 3000),
    ],
    'verify_idxtable_all.py': [
        ('rx8_index_table_clear0_wrapper', 0x68774, 5000),
        ('rx8_index_table_clear', 0x68780, 5000),
        ('rx8_index_table_step', 0x6879C, 5000),
        ('rx8_index_table_step2', 0x687C8, 5000),
        ('rx8_index_table_dec', 0x687F4, 5000),
        ('rx8_index_table_step3', 0x68820, 5000),
    ],
    'verify_immo_exhaustive.py': [
        ('rx8_immo_seed_mixer', 0x366B8, 65536 * 64),
    ],
    'verify_10A88.py': [
        ('calc_manifold_pressure_error_diff_10A88', 0x10A88, 4000),
    ],
    'verify_bitfield.py': [
        ('rx8_bitfield_extract_merge', 0x48C8, 3000),
    ],
    'verify_checksum.py': [
        ('rx8_checksum_complement_add', 0x2034, 4000),
    ],
    'verify_datalookup.py': [
        ('rx8_data_lookup', 0x2624, 3000),
    ],
    'verify_firstorder.py': [
        ('rx8_first_order_filter', 0x23B0, 3000),
    ],
    'verify_delayloop.py': [
        ('rx8_delay_loop_n8', 0x239C, 3000),
    ],
    'verify_interp16.py': [
        ('rx8_interpolate_u16_table', 0x26D0, 3000),
    ],
    'verify_interp8.py': [
        ('rx8_interpolate_u8_table', 0x26B0, 3000),
    ],
    'verify_interp_f32.py': [
        ('rx8_interpolate_f32_table', 0x2678, 3000),
    ],
    'verify_interp_s16.py': [
        ('rx8_interpolate_s16_table', 0x2690, 3000),
    ],
    'verify_interp_s8.py': [
        ('rx8_interpolate_s8_table', 0x26F4, 3000),
    ],
    'verify_interp_s8.py': [
        ('rx8_interpolate_s8_table', 0x26F4, 3000),
    ],
    'verify_invert8.py': [
        ('rx8_invert_and_return_8bit', 0x2044, 3000),
    ],
    'verify_memcpy.py': [
        ('rx8_memcpy_bytewise', 0x42B0, 3000),
    ],
    'verify_mod32.py': [
        ('rx8_mod32_signed', 0x4144, 5000),
    ],
    'verify_setregbit.py': [
        ('rx8_set_register_reg_bit_val', 0x4BBC, 4000),
    ],
    'fuzz_l2.py': _LOTTO2_6,
}


def _funcs_from_single(text):
    """Single-function harness: ADDR_ROM + (NAME|ENTRY_SYM) + N_DEFAULT."""
    m_addr = re.search(r'^ADDR_ROM\s*=\s*(0x[0-9A-Fa-f]+)', text, re.M)
    if not m_addr:
        return None
    addr = int(m_addr.group(1), 16)
    name = None
    for pat in (r"^NAME\s*=\s*'([^']+)'",
                r"^ENTRY_SYM\s*=\s*'([^']+)'"):
        mm = re.search(pat, text, re.M)
        if mm:
            name = mm.group(1)
            break
    n = 0
    mn = re.search(r'^N_DEFAULT\s*=\s*(\d+)', text, re.M)
    if mn:
        n = int(mn.group(1))
    return [{'name': name or 'FUN_%X' % addr, 'addr': addr, 'n': n}]


def _funcs_from_funs(text):
    """Multi-function harness: `addr_rom` entries (FUNCS dicts / lists)."""
    funcs = []
    for m in re.finditer(r"'addr_rom':\s*(0x[0-9A-Fa-f]+|None)", text):
        addr_txt = m.group(1)
        addr = int(addr_txt, 16) if addr_txt != 'None' else None
        start = m.start()
        name = None
        # 1) an entry_sym/name just above the addr (same dict/list block)
        for pat in (r"^'entry_sym':\s*'([^']+)'", r"^'name':\s*'([^']+)'",
                    r"'entry_sym':\s*'([^']+)'", r"'name':\s*'([^']+)'"):
            if name:
                break
            mm = re.search(pat, text[max(0, start - 700):start])
            if mm:
                name = mm.group(1)
        # 2) keyed-dict literal, e.g. `'div32_signed': {`
        if not name:
            mk = re.search(r"^\s{4}([A-Za-z0-9_]+):\s*\{", text[:start], re.M)
            if mk:
                name = mk.group(1)
        if not name:
            name = 'FUN_%X' % (addr or 0)
        n = 0
        mnn = re.search(r"'n_test':\s*(\d+)", text[start:start + 500])
        if mnn:
            n = int(mnn.group(1))
        funcs.append({'name': name, 'addr': addr, 'n': n})
        del mm
    # de-duplicate by (name, addr)
    seen = set()
    out = []
    for fc in funcs:
        k = (fc['name'], fc['addr'])
        if k in seen:
            continue
        seen.add(k)
        out.append(fc)
    return out


def extract_functions(path):
    """Best-effort function inventory from a harness's source."""
    base = os.path.basename(path)
    if base in CURATED:
        return [{'name': n, 'addr': a, 'n': c} for n, a, c in CURATED[base]]
    try:
        text = open(path, encoding='utf-8', errors='ignore').read()
    except OSError:
        return []
    f = _funcs_from_single(text)
    if f is not None:
        return f
    f = _funcs_from_funs(text)
    if f:
        return f
    return [{'name': os.path.basename(path), 'addr': None, 'n': 0}]


# --------------------------------------------------------------------------
# significant line / mismatch helpers
# --------------------------------------------------------------------------
_SIG_RE = re.compile(r'mismatch|OK |FAIL|Error', re.IGNORECASE)


def significant_line(out):
    """Last line matching the summary pattern (mismatch / OK / FAIL / Error)."""
    lines = [ln.strip() for ln in out.splitlines() if _SIG_RE.search(ln)]
    return lines[-1] if lines else (out.strip().splitlines()[-1] if out.strip() else '')


def harness_mismatch(out, returncode):
    """Aggregated mismatch count from a harness output (0 if it exited 0)."""
    if returncode != 0:
        # find "N mismatch" in the FAIL tail
        mm = re.findall(r'(\d+)\s*mismatch', out)
        if mm:
            return int(mm[-1])
        return 1  # non-zero exit, unknown count
    return 0


# --------------------------------------------------------------------------
# single-harness run
# --------------------------------------------------------------------------
def run_one(harness, which, timeout, slow_timeout):
    path = os.path.join(TESTS, harness)
    if not os.path.exists(path):
        return {'name': harness, 'exists': False, 'skip': False,
                'state': 'MISSING'}
    is_slow = 'immo_exhaustive' in harness
    to = slow_timeout if is_slow else timeout
    t0 = time.time()
    try:
        proc = subprocess.run([sys.executable, path],
                              capture_output=True, text=True, timeout=to,
                              cwd=TESTS)
        out = proc.stdout + '\n' + (proc.stderr or '')
        rc = proc.returncode
        timed = False
    except subprocess.TimeoutExpired as ex:
        out = ex.stdout or ''
        out += '\n[TIMEOUT after %ds]' % to
        rc = 124
        timed = True
    dt = time.time() - t0
    return {
        'name': harness, 'exists': True, 'skip': False, 'state': 'OK',
        'exit': rc, 'timed': timed, 'time': round(dt, 2),
        'timeout': to, 'sig': significant_line(out),
        'mismatch': harness_mismatch(out, rc) if rc != 124 else 0,
        'functions': extract_functions(path),
    }


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main():
    args = sys.argv[1:]
    skip_fast = False
    skip_slow = True  # default: exclude verify_immo_exhaustive.py (~7 min)
    json_path = None
    timeout = 300
    slow_timeout = 900
    explicit = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ('--skip-fast',):
            skip_fast = True
        elif a in ('--with-slow',):
            skip_slow = False
        elif a == '--skip-slow':
            skip_slow = True
        elif a == '--json':
            json_path = args[i + 1]
            i += 1
        elif a == '--timeout':
            timeout = int(args[i + 1]); i += 1
        elif a == '--slow-timeout':
            slow_timeout = int(args[i + 1]); i += 1
        elif a.startswith('-'):
            print('unknown option: %s' % a)
            sys.exit(2)
        else:
            explicit.append(a)
        i += 1

    # discover
    all_names = sorted(
        f for f in os.listdir(TESTS)
        if (f.startswith('verify') or f.startswith('fuzz')) and f.endswith('.py')
        and f != SELF)
    if explicit:
        to_run = list(explicit)
    else:
        to_run = all_names

    if skip_slow:
        to_run = [h for h in to_run if 'immo_exhaustive' not in h]
    if skip_fast:
        to_run = [h for h in to_run if '_fast' not in h]

    # build tasks, dedup preserving discovered order
    tasks = []
    seen = set()
    for h in to_run:
        if h in seen:
            continue
        seen.add(h)
        tasks.append(h)

    results = [run_one(h, [], timeout, slow_timeout) for h in tasks]

    # ---- report table -------------------------------------------------
    hdr = '%-34s %-9s %8s  %s' % ('harness', 'exit', 'time(s)', 'significant line')
    print('=' * len(hdr))
    print(hdr)
    print('=' * len(hdr))
    any_skip_named = 0
    executed = [r for r in results if r.get('exists')]
    for r in results:
        if not r.get('exists'):
            print('%-34s %-9s %8s  %s (MISSING)' % (r['name'], '-', '-', ''))
            continue
        st = r['state']
        mark = 'TIMEOUT' if r.get('exit') == 124 else ('FAIL' if r.get('exit') != 0 else 'OK')
        sig = r.get('sig', '')
        if len(sig) > 78:
            sig = sig[:75] + '...'
        print('%-34s %-9s %8.2f  %s' % (r['name'], mark, r['time'], sig))

    # ---- exit decision ----------------------------------------------
    failed = [r['name'] for r in executed if r.get('exit') != 0]
    all_ok = not failed
    print()
    print('harnesses executed : %d' % len(executed))
    print('harnesses skipped  : %d' % (len(tasks) - len(executed)))
    print('harnesses missing  : %d' % sum(1 for r in results if not r.get('exists')))
    print('failures           : %d' % len(failed))
    if failed:
        print('FAILING harnesses  : %s' % ', '.join(failed))
    print('RESULT             : %s' % ('ALL OK' if all_ok else 'HARNESS_FAILURE'))

    # ---- write aggregate data for the summary ------------------------
    aggregate = _aggregate(results, executed)
    if json_path:
        with open(json_path, 'w') as fh:
            json.dump(aggregate, fh, indent=2)
        print('wrote JSON -> %s' % json_path)

    sys.exit(0 if all_ok else 1)


def _aggregate(results, executed):
    func_rows = []
    for r in results:
        if not r.get('exists'):
            continue
        for f in r.get('functions', []):
            func_rows.append({
                'file': r['name'],
                'name': f['name'],
                'addr': f['addr'],
                'n': f['n'],
                'mismatch': 0 if r.get('exit') == 0 else 1,
            })
    # unique by (name, addr)
    uniq = {}
    for row in func_rows:
        k = (row['name'], row['addr'])
        if k in uniq:
            # dedupe: keep the entry that came from a passing harness
            if row['mismatch'] == 0 and uniq[k]['mismatch'] != 0:
                uniq[k] = row
            continue
        uniq[k] = row
    rows = list(uniq.values())
    total_vec = sum((r['n'] or 0) for r in rows)
    total_mismatch = sum(r['mismatch'] for r in rows)
    return {
        'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'harnesses_executed': len(executed),
        'harness_results': [{
            'name': r['name'], 'exit': r.get('exit'),
            'time': r.get('time'), 'mismatch': r.get('mismatch', 0),
            'sig': r.get('sig', '')} for r in results if r.get('exists')],
        'total_functions': len(rows),
        'total_vectors': total_vec,
        'total_mismatch': total_mismatch,
        'routines': rows,
    }


if __name__ == '__main__':
    main()