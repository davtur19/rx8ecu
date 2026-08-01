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
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
    """Run a single test file in a subprocess; return (test_path, rc, wall, out)."""
    t0 = time.time()
    try:
        p = subprocess.run(
            [sys.executable, test_path],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        rc = p.returncode
        out = p.stdout or ''
    except Exception as e:  # subprocess-level failure (should not happen)
        rc = 2
        out = '%s\n' % e
    wall = time.time() - t0
    return (test_path, rc, wall, out)


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
    # de-duplicate while preserving order
    seen, ordered = set(), []
    for t in tests + [os.path.abspath(e) for e in args.extras]:
        if t not in seen:
            seen.add(t)
            ordered.append(t)
    tests = ordered

    if not tests:
        print('run_tests_parallel: no tests found under c/tests or tools/tests', file=sys.stderr)
        return 2

    jobs = 1 if args.serial else (args.jobs or max(1, (os.cpu_count() or 1) - 1))
    jobs = max(1, jobs)

    print('run_tests_parallel: %d suites, %d workers' % (len(tests), jobs))
    print('-' * 78)
    t_start = time.time()

    results = []
    if args.serial:
        for t in tests:
            results.append(run_one(t, args.verbose))
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
                path, rc, wall, out = fut.result()
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
