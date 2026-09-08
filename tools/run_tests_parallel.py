#!/usr/bin/env python3
"""
run_tests_parallel.py — run all Python regression suites in parallel.

Discovers every c/tests/test_*.py and tools/tests/test_*.py at runtime (so new
test files created by other agents are picked up automatically), plus any extra
test paths given on the command line (e.g. c/tests/verify_emu.py), and runs
them concurrently with a multiprocessing process pool.  Each suite runs in its
own subprocess so stdout/stderr stay un-garbled; output of failed suites is
replayed after the summary.

Usage:
  python3 tools/run_tests_parallel.py [options] [extra_test.py ...]

Options:
  -j N, --jobs N   number of parallel workers (default: max(1, cpu_count-1))
  -q, --quiet      don't print per-suite PASS lines (still prints failures)
  -v, --verbose    print each suite's full captured output
  --serial         run one suite at a time (no pool); equivalent to the old
                   `for t in ...; do python3 "$t"; done` loop

Exit status is non-zero if any suite fails.
"""

import argparse
import atexit
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Per-suite wall-clock budget (seconds): a hung suite FAILs instead of
# wedging the whole run forever.
_TIMEOUT_S = 600

# Temp-file registry for the dedup copies: run_one() already unlinks its
# temp in a finally, but a kill/exception between mkstemp and unlink would
# leak a `.dedup_*.py` next to the suite.  Registered paths are removed at
# interpreter exit (and unregistered on the normal path).
_TEMP_FILES = set()


def _register_temp(path):
    _TEMP_FILES.add(path)


def _unregister_temp(path):
    _TEMP_FILES.discard(path)


def _cleanup_temps():
    for path in sorted(_TEMP_FILES):
        try:
            os.unlink(path)
        except OSError:
            pass
    _TEMP_FILES.clear()


atexit.register(_cleanup_temps)

# Generated v8 lift tests inline the whole callee span once per call site, so a
# single test file can hold hundreds of thousands of lines while the final
# CODE dict has only a few thousand UNIQUE keys (Python's dict-literal overwrite
# keeps the last occurrence).  Parsing the duplicates transiently needs
# multi-GiB of RAM (measured: 4.8 GB peak on c/tests/test_caller_648E.py, which
# has 432k lines but only 14274 unique entries), which OOM-kills the suite on
# memory-constrained machines.  Deduping the CODE block before the interpreter
# parses it keeps the exact same dict (last occurrence wins, matching Python)
# at ~30x less memory.
_CODE_ENTRY = re.compile(r'^\s*(0x[0-9a-fA-F]+):')


def _find_code_end(lines, start):
    """Return the line index closing the CODE dict opened at lines[start].

    String/comment-aware brace matching from the opening ``{``: tracks
    single/double/triple-quoted strings (with backslash escapes) and ``#``
    comments so braces inside literals never affect the depth.  Returns None
    when the block never closes cleanly (fail-closed signal: the caller must
    return the source unchanged, never truncate).
    """
    text = '\n'.join(lines)
    # Offset of the opening brace on the start line.
    brace_col = lines[start].find('{')
    if brace_col < 0:
        return None
    off = sum(len(l) + 1 for l in lines[:start]) + brace_col
    depth = 0
    i = off
    n = len(text)
    # Lexer state: None | "'" | '"' | "'''" | '"""' | '#'
    state = None
    while i < n:
        if state == '#':
            if text[i] == '\n':
                state = None
            i += 1
            continue
        if state in ("'", '"'):
            if text[i] == '\\':
                i += 2
                continue
            if text[i] == state:
                state = None
            i += 1
            continue
        if state in ("'''", '"""'):
            if text.startswith(state, i):
                state = None
                i += 3
                continue
            if text[i] == '\\':
                i += 2
                continue
            i += 1
            continue
        # Code state.
        if text[i] == '#':
            state = '#'
            i += 1
            continue
        if text.startswith("'''", i):
            state = "'''"
            i += 3
            continue
        if text.startswith('"""', i):
            state = '"""'
            i += 3
            continue
        if text[i] in ("'", '"'):
            state = text[i]
            i += 1
            continue
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text.count('\n', 0, i)
        i += 1
    return None


def _dedup_code_block(source):
    """Collapse repeated single-line CODE-dict entries (last occurrence wins).

    Returns the original source unchanged when there is no CODE block, the
    duplication is not worth the rewrite, the block end is not found cleanly
    (fail-closed: never truncate), or any in-block line is not a plain
    single-line ``_CODE_ENTRY`` (comments, multi-line values, nested dicts —
    dedup would change semantics or break syntax, so leave it alone).
    """
    lines = source.split('\n')
    try:
        start = next(i for i, l in enumerate(lines) if l.startswith('CODE = {'))
    except StopIteration:
        return source
    end = _find_code_end(lines, start)
    if end is None or end >= len(lines):
        return source                    # fail-closed: never truncate
    if end - start < 4:
        return source
    # Fail-closed for non-uniform blocks (MEDIUM-5): every in-block line must
    # be blank/whitespace-only or a single-line _CODE_ENTRY; otherwise the
    # block may hold comments, multi-line values, or nested dicts that the
    # kept-lines reconstruction would delete or corrupt.
    for i in range(start + 1, end):
        if not lines[i].strip():
            continue
        if not _CODE_ENTRY.match(lines[i]):
            return source
    # The closing line itself must be either a standalone '}' or a final
    # CODE entry carrying the inline close (e.g. '...},}'); anything else
    # means an unexpected shape — leave it alone.
    end_stripped = lines[end].strip()
    end_is_entry = bool(_CODE_ENTRY.match(lines[end]))
    if not end_is_entry and end_stripped != '}':
        return source
    last = {}
    stop = end if not end_is_entry else end + 1
    for i in range(start + 1, stop):
        m = _CODE_ENTRY.match(lines[i])
        if m:
            last[m.group(1).lower()] = i
    if len(last) * 2 >= (stop - start):
        return source                      # few duplicates: nothing to gain
    kept = sorted(last.values())
    if end_is_entry:
        # Inline close ('},}'): the closing brace lives on the last entry
        # line, which is always kept (last line == last occurrence of its
        # key, sorted last), so the suffix starts AFTER it to avoid doubling.
        return '\n'.join(lines[:start + 1] + [lines[i] for i in kept] + lines[end + 1:])
    return '\n'.join(lines[:start + 1] + [lines[i] for i in kept] + lines[end:])


def discover_tests():
    """Dynamically collect all test_*.py under c/tests/ and tools/tests/."""
    paths = []
    for sub in ('c', 'tools'):
        d = os.path.join(ROOT, sub, 'tests')
        if not os.path.isdir(d):
            continue
        names = sorted(n for n in os.listdir(d)
                       if n.startswith('test_') and n.endswith('.py'))
        for n in names:
            paths.append(os.path.join(d, n))
    return paths


def run_one(test_path, verbose=False):
    """Run a single test file in a subprocess; return (orig_path, rc, wall, out).

    Huge generated tests are deduped (see _dedup_code_block) into a temporary
    .py next to the original — the test derives ROOT from __file__, so the copy
    must stay in the same directory — and the temp file is removed afterwards.
    The returned path is always the ORIGINAL suite path (not the temp exec
    path) so the caller can match results back to discovery order; losing that
    mapping silently drops deduped suites from the summary (always-PASS bug).
    """
    t0 = time.time()
    orig_path = test_path
    tmp_path = None
    exec_path = test_path
    src = None
    try:
        with open(test_path, 'r', encoding='utf-8', errors='replace') as fh:
            src = fh.read()
    except OSError:
        src = None
    if src is not None:
        dedup = _dedup_code_block(src)
        if dedup != src:
            fd, tmp_path = tempfile.mkstemp(
                dir=os.path.dirname(test_path), prefix='.dedup_', suffix='.py')
            with os.fdopen(fd, 'w', encoding='utf-8') as fh:
                fh.write(dedup)
            _register_temp(tmp_path)
            exec_path = tmp_path
    try:
        p = subprocess.run(
            [sys.executable, exec_path],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=_TIMEOUT_S,
        )
        rc = p.returncode
        out = p.stdout or ''
    except subprocess.TimeoutExpired:
        rc = 1
        out = ('TIMEOUT after %ds: %s\n'
               % (_TIMEOUT_S, os.path.relpath(orig_path, ROOT)))
    except Exception as e:  # subprocess-level failure (should not happen)
        rc = 2
        out = '%s\n' % e
    finally:
        if tmp_path is not None:
            _unregister_temp(tmp_path)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    wall = time.time() - t0
    return (orig_path, rc, wall, out)


def main():
    ap = argparse.ArgumentParser(description='Parallel test runner for rx8ecu')
    ap.add_argument('-j', '--jobs', type=int, default=None,
                    help='parallel workers (default: cpu_count-1)')
    ap.add_argument('-q', '--quiet', action='store_true')
    ap.add_argument('-v', '--verbose', action='store_true')
    ap.add_argument('--serial', action='store_true')
    ap.add_argument('extras', nargs='*', help='extra test files (e.g. c/tests/verify_emu.py)')
    args = ap.parse_args()

    tests = discover_tests()
    # de-duplicate while preserving order.  Extras are resolved against ROOT
    # (not the cwd) so `cd /tmp; run_tests_parallel.py c/tests/x.py` names
    # the same absolute path discovery produced instead of a cwd-dependent
    # phantom that either double-runs or spuriously fails.
    resolved_extras = []
    for e in args.extras:
        if os.path.isabs(e):
            resolved_extras.append(os.path.normpath(e))
        else:
            resolved_extras.append(os.path.normpath(os.path.join(ROOT, e)))
    seen, ordered = set(), []
    for t in tests + resolved_extras:
        if t not in seen:
            seen.add(t)
            ordered.append(t)
    tests = ordered

    if not tests:
        print('run_tests_parallel: no tests found under c/tests or tools/tests', file=sys.stderr)
        return 2

    jobs = 1 if args.serial else (args.jobs or max(1, (os.cpu_count() or 1) - 1))
    if not args.serial and args.jobs is not None and args.jobs < 1:
        ap.error('--jobs must be >= 1 (got %d)' % args.jobs)

    print('run_tests_parallel: %d suites, %d workers' % (len(tests), jobs))
    print('-' * 78)
    t_start = time.time()

    results = []
    if args.serial:
        for t in tests:
            try:
                res = run_one(t, args.verbose)
            except Exception as e:  # run_one must not abort the whole run
                res = (t, 1, 0.0, 'RUNNER-ERROR %s: %s\n'
                       % (os.path.relpath(t, ROOT), e))
            results.append(res)
            path, rc, wall, out = results[-1]
            status = 'PASS' if rc == 0 else 'FAIL'
            print('%-14s %-58s %6.1fs' % (status, os.path.relpath(path, ROOT), wall),
                  flush=True)
            if rc != 0 and not args.quiet:
                print(out, end='')
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            futs = {pool.submit(run_one, t, args.verbose): t for t in tests}
            # Preserve discovery order in the summary; results come back as done.
            done = {}
            for fut in as_completed(futs):
                try:
                    path, rc, wall, out = fut.result()
                except Exception as e:  # one raising suite -> FAIL row, not abort
                    t = futs[fut]
                    path, rc, wall, out = (
                        t, 1, 0.0, 'RUNNER-ERROR %s: %s: %s\n'
                        % (os.path.relpath(t, ROOT), type(e).__name__, e))
                done[path] = (rc, wall, out)
                if not args.quiet:
                    status = 'PASS' if rc == 0 else 'FAIL'
                    print('%-14s %-58s %6.1fs' % (status, os.path.relpath(path, ROOT), wall),
                          flush=True)
            results = [(t, *done[t]) for t in tests if t in done]

    wall_total = time.time() - t_start
    failed = [(t, rc, wall, out) for (t, rc, wall, out) in results if rc != 0]
    print('-' * 78)

    if failed:
        print('FAILURES:')
        for t, rc, wall, out in failed:
            print('  %s (exit %d, %.1fs)' % (os.path.relpath(t, ROOT), rc, wall))
            print('  ' + out.replace('\n', '\n  ').rstrip())
        print()
        print('SUMMARY: %d/%d suites passed, %d FAILED  (%.1fs wall, %d workers)'
              % (len(results) - len(failed), len(results), len(failed),
                 wall_total, jobs))
        return 1

    print('SUMMARY: %d/%d suites passed  (%.1fs wall, %d workers)'
          % (len(results), len(results), wall_total, jobs))
    return 0


if __name__ == '__main__':
    sys.exit(main())
