#!/usr/bin/env python3
"""
compile_all_gcc346.py — compile sweep of EVERY reconstructed sample C against the
era-ROM toolchain (sh-elf gcc 3.4.6).

Purpose
-------
Bound the *theoretical* validation coverage: how many of the abstract-C samples
in reconstructed/samples/src/ can even be compiled by the era-ROM compiler
(which is the hard prerequisite for any behavioural verification on the
emulator, cf. verify_gcc346.py).  For the ones that fail we record the FIRST
diagnostic line and classify it:

  (a) header mancante            — `#include <x.h>` not resolvable on the
                                   -nostdinc -I stub path (system-ish header
                                   absent from /tmp/verify_gcc346/inc)
  (b) sintassi / estensione      — gcc 3.4.6 rejects the construct (syntax
                                   error, unsupported extension, undeclared
                                   type/token, invalid suffix, ...)
  (c) include relativo mancante  — `#include "x.h"` whose file does not exist
                                   in the file's own dir / src / include
  (d) altro                      — anything else (toolchain, asm, ...)

The sweep is READ-ONLY w.r.t. the repo: every artifact goes to /tmp.  It
(re)creates the minimal stub headers under /tmp/verify_gcc346/inc (stdint.h,
math.h, stddef.h, string.h, limits.h, stdbool.h) so it is idempotent even if
verify_gcc346.py later overwrites stdint.h/math.h with its embedded minimal
versions.  The C files themselves are NEVER modified.

Usage
-----
  python3 compile_all_gcc346.py               # full sweep (all src/*.c)
  python3 compile_all_gcc346.py --sample 60   # stratified sample of 60 files
  python3 compile_all_gcc346.py --limit 20    # first 20 files (smoke test)
  python3 compile_all_gcc346.py --out /tmp/compile_all_report.md

If the full sweep exceeds the 10-minute timebox the script automatically falls
back to a deterministic stratified sample of 60 files and documents the fact
in the report.
"""
import os
import re
import sys
import time
import argparse
import subprocess
import datetime

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
TESTS = os.path.dirname(os.path.abspath(__file__))      # reconstructed/samples/tests
SAMPLES = os.path.dirname(TESTS)                          # reconstructed/samples
ROOT = os.path.dirname(os.path.dirname(SAMPLES))          # rx8ecu repo root
SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')
STUB_INC = '/tmp/verify_gcc346/inc'

XGCC = '/home/davide/gcc346-build/gcc/xgcc'
XGCC_B = '/home/davide/gcc346-build/gcc/'
OUT_OBJ = '/tmp/compile_all_gcc346.o'

TIMEOUT_SEC = 600            # 10-minute timebox for the full sweep
DEFAULT_SAMPLE = 60          # stratified sample size on timeout / --sample

# ---------------------------------------------------------------------------
# Stub headers (minimal target headers for the --without-headers gcc 3.4.6).
# Written once per run under STUB_INC; a superset of what verify_gcc346.py
# embeds, extended with the headers the wider sample corpus needs.
# ---------------------------------------------------------------------------
STUB_HEADERS = {
    'stdint.h': (
        '#ifndef _STDINT_H\n#define _STDINT_H\n'
        'typedef signed char int8_t; typedef unsigned char uint8_t;\n'
        'typedef signed short int16_t; typedef unsigned short uint16_t;\n'
        'typedef signed int int32_t; typedef unsigned int uint32_t;\n'
        'typedef signed long long int64_t; typedef unsigned long long uint64_t;\n'
        'typedef unsigned long uintptr_t; typedef long intptr_t;\n'
        '#ifndef __SIZE_T_DEFINED\n#define __SIZE_T_DEFINED\n'
        'typedef unsigned int size_t;\n#endif\n'
        '#ifndef NULL\n#define NULL ((void *)0)\n#endif\n'
        '#define INT8_MIN (-128)\n#define INT16_MIN (-32767-1)\n'
        '#define INT32_MIN (-2147483647-1)\n#define INT64_MIN (-9223372036854775807LL-1)\n'
        '#define INT8_MAX 127\n#define INT16_MAX 32767\n#define INT32_MAX 2147483647\n'
        '#define INT64_MAX 9223372036854775807LL\n'
        '#define UINT8_MAX 255\n#define UINT16_MAX 65535\n'
        '#define UINT32_MAX 4294967295U\n#define UINT64_MAX 18446744073709551615ULL\n'
        '#endif\n'
    ),
    'math.h': (
        '#ifndef _MATH_H\n#define _MATH_H\n'
        'float fabsf(float x);\n'
        'double fabs(double x);\n'
        'double round(double x);\n'
        'double floor(double x);\n'
        'double sqrt(double x);\n'
        'double exp(double x);\n'
        '#define isfinite(x) __builtin_isfinite(x)\n'
        '#endif\n'
    ),
    'stddef.h': (
        '#ifndef _STDDEF_H\n#define _STDDEF_H\n'
        '#ifndef __SIZE_T_DEFINED\n#define __SIZE_T_DEFINED\n'
        'typedef unsigned int size_t;\n#endif\n'
        '#ifndef __PTRDIFF_T_DEFINED\n#define __PTRDIFF_T_DEFINED\n'
        'typedef int ptrdiff_t;\n#endif\n'
        '#ifndef __WCHAR_T_DEFINED\n#define __WCHAR_T_DEFINED\n'
        'typedef unsigned int wchar_t;\n#endif\n'
        '#ifndef NULL\n#define NULL ((void *)0)\n#endif\n'
        '#endif\n'
    ),
    'string.h': (
        '#ifndef _STRING_H\n#define _STRING_H\n'
        '#include <stddef.h>\n'
        'void *memcpy(void *dst, const void *src, size_t n);\n'
        'void *memset(void *s, int c, size_t n);\n'
        'int memcmp(const void *a, const void *b, size_t n);\n'
        'size_t strlen(const char *s);\n'
        'char *strcpy(char *dst, const char *src);\n'
        'int strcmp(const char *a, const char *b);\n'
        '#endif\n'
    ),
    'limits.h': (
        '#ifndef _LIMITS_H\n#define _LIMITS_H\n'
        '#define CHAR_BIT 8\n'
        '#define SCHAR_MIN (-128)\n#define SCHAR_MAX 127\n#define UCHAR_MAX 255\n'
        '#define SHRT_MIN (-32767-1)\n#define SHRT_MAX 32767\n#define USHRT_MAX 65535\n'
        '#define INT_MIN (-2147483647-1)\n#define INT_MAX 2147483647\n'
        '#define UINT_MAX 4294967295U\n'
        '#define LONG_MIN (-2147483647L-1)\n#define LONG_MAX 2147483647L\n'
        '#define ULONG_MAX 4294967295UL\n'
        '#define LLONG_MIN (-9223372036854775807LL-1)\n'
        '#define LLONG_MAX 9223372036854775807LL\n'
        '#define ULLONG_MAX 18446744073709551615ULL\n'
        '#endif\n'
    ),
    'stdbool.h': (
        '#ifndef _STDBOOL_H\n#define _STDBOOL_H\n'
        '#define bool _Bool\n#define true 1\n#define false 0\n'
        '#define __bool_true_false_are_defined 1\n'
        '#endif\n'
    ),
}


def ensure_stubs():
    """(Re)create the minimal target stub headers under /tmp/verify_gcc346/inc."""
    os.makedirs(STUB_INC, exist_ok=True)
    for name, content in STUB_HEADERS.items():
        path = os.path.join(STUB_INC, name)
        with open(path, 'w') as f:
            f.write(content)
    # sanity: the standard types the corpus relies on must be there
    stdint = open(os.path.join(STUB_INC, 'stdint.h')).read()
    for need in ('int32_t', 'uint16_t', 'uintptr_t', 'size_t', 'INT32_MIN'):
        assert need in stdint, 'stub stdint.h missing %r' % need


# ---------------------------------------------------------------------------
# Compile + first-error extraction
# ---------------------------------------------------------------------------
def build_cmd(src_path):
    return [
        XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
        '-nostdinc', '-I', STUB_INC, '-I', INC_DIR,
        '-c', src_path, '-o', OUT_OBJ,
    ]


def first_error_line(stderr_text):
    """Return the FIRST diagnostic line containing 'error:' (warnings skipped)."""
    for ln in stderr_text.splitlines():
        if 'error:' in ln:
            return ln.strip()
    return None


_RE_LINE = re.compile(r'^([^:]+):(\d+)(?::(\d+))?:\s*(.*)$')
_RE_MISSING_H = re.compile(r'([\w./\\-]+\.h): No such file or directory')

# tokens that indicate a syntax / extension / language issue (category b)
_RE_SYNTAX_HINTS = re.compile(
    r'syntax error|parse error|stray |invalid suffix|undeclared|'
    r'expected |invalid operands|incompatible types|unknown type name|'
    r'called object|too few arguments|too many arguments|'
    r'conflicting types|storage class|static assertion|'
    r'not.*an.*lvalue|has no member|flexible array|empty struct|'
    r'dereferencing pointer to incomplete|void value not ignored|'
    r'ISO C forbids|no known conversion|missing terminating|'
    r'control reaches end|initializer element|array type has incomplete|'
    r'used outside C99 mode|C99 mode|mixed declaration'
)


def source_line_for(path, lineno):
    """Return the source line at `lineno` (best effort, for report context)."""
    try:
        with open(path, 'r', errors='replace') as f:
            lines = f.readlines()
        if 1 <= lineno <= len(lines):
            return lines[lineno - 1].rstrip('\n').strip()
    except OSError:
        pass
    return None


def classify_error(first_err, src_path):
    """Classify the first error line.

    Returns (category, detail):
      category in {'a_header', 'b_syntax', 'c_rel_include', 'd_other'}
    """
    m_h = _RE_MISSING_H.search(first_err)
    if m_h:
        header = m_h.group(1)
        quoted = include_is_quoted(src_path, header)
        if quoted:
            return 'c_rel_include', header
        return 'a_header', header
    if _RE_SYNTAX_HINTS.search(first_err):
        return 'b_syntax', first_err
    return 'd_other', first_err


_INCLUDE_RE = re.compile(r'^\s*#\s*include\s+([<"])([^>"]+)[>"]', re.M)
_LOCAL_INC_RE = re.compile(r'^\s*#\s*include\s+"([^"]+)"', re.M)


def include_is_quoted(src_file, header, visited=None):
    """True if `header` is reached via a quoted (not angle) include somewhere
    in the local include chain of `src_file`.  Used to split "header mancante"
    (a) from "include relativo mancante" (c)."""
    if visited is None:
        visited = set()
    src_file = os.path.abspath(src_file)
    if src_file in visited:
        return None
    visited.add(src_file)
    try:
        text = open(src_file, 'r', errors='replace').read()
    except OSError:
        return None
    for m in _INCLUDE_RE.finditer(text):
        if m.group(2) == header:
            return m.group(1) == '"'
    # follow local includes to find where the header is referenced
    for m in _LOCAL_INC_RE.finditer(text):
        cand = None
        for base in (os.path.dirname(src_file), SRC_DIR, INC_DIR):
            p = os.path.join(base, m.group(1))
            if os.path.exists(p):
                cand = p
                break
        if cand:
            r = include_is_quoted(cand, header, visited)
            if r is not None:
                return r
    return None


# ---------------------------------------------------------------------------
# Pure-math plausibility heuristic (theoretical max for emulator validation)
# ---------------------------------------------------------------------------
_ALREADY_VALIDATED = set()  # src names behaviourally validated by verify_gcc346.py


def load_already_validated():
    """Regex-extract the 'src' names from verify_gcc346.py's FUNCS table
    without importing/executing the harness module."""
    path = os.path.join(TESTS, 'verify_gcc346.py')
    try:
        text = open(path, 'r', errors='replace').read()
    except OSError:
        return
    for m in re.finditer(r"['\"]src['\"]\s*:\s*['\"](rx8_[^'\"]+\.c)['\"]", text):
        _ALREADY_VALIDATED.add(m.group(1))


def pure_math_plausible(src_path):
    """Heuristic: a sample is a plausible pure-math (emulator-comparable) leaf
    if it compiles AND does not poke documented hardware addresses / MMIO.
    Uses only obvious static markers; it is an *estimate* for coverage."""
    try:
        text = open(src_path, 'r', errors='replace').read()
    except OSError:
        return False
    if 'rx8_hw.h' in text:
        return False
    if re.search(r'0xFFFF[0-9A-Fa-f]', text):
        return False
    if re.search(r'\bvolatile\b', text):
        return False
    # must define at least one function body (non-static symbol)
    if not re.search(r'\b(?:float|double|u?int(?:8|16|32|64)_t|void|char|short|int|long|unsigned)\b[^;]*\([^;]*\)\s*\{', text):
        return False
    return True


# ---------------------------------------------------------------------------
# Sweep driver
# ---------------------------------------------------------------------------
def stratified_sample(files, n):
    """Deterministic even-spacing sample of `n` files from sorted `files`."""
    files = sorted(files)
    if len(files) <= n:
        return files
    idx = [int(round(i * (len(files) - 1) / (n - 1))) for i in range(n)]
    seen, out = set(), []
    for i in idx:
        if files[i] not in seen:
            seen.add(files[i])
            out.append(files[i])
    return out


def run_sweep(files):
    results = []
    for i, path in enumerate(files, 1):
        proc = subprocess.run(build_cmd(path), capture_output=True, text=True)
        stderr = proc.stderr or ''
        first_err = first_error_line(stderr)
        if proc.returncode == 0:
            results.append({'file': path, 'ok': True, 'error': None,
                            'cat': None, 'line': None})
        else:
            cat, detail = classify_error(first_err, path)
            lineno = None
            m = _RE_LINE.match(first_err or '')
            if m:
                try:
                    lineno = int(m.group(2))
                except ValueError:
                    lineno = None
            results.append({'file': path, 'ok': False, 'error': first_err,
                            'cat': cat, 'line': lineno,
                            'src_line': source_line_for(path, lineno)})
        sys.stdout.write('\r  [%3d/%d] %-55s %s'
                         % (i, len(files), os.path.basename(path),
                            'OK ' if proc.returncode == 0 else 'FAIL'))
        sys.stdout.flush()
    sys.stdout.write('\n')
    return results


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def write_report(out_path, files, results, sample_mode, elapsed, timeboxed):
    ok = [r for r in results if r['ok']]
    fail = [r for r in results if not r['ok']]
    by_cat = {}
    for r in fail:
        by_cat.setdefault(r['cat'], []).append(r)

    compilable = {os.path.basename(r['file']) for r in ok}
    pure_math = [r for r in ok if pure_math_plausible(r['file'])]
    pure_math_names = {os.path.basename(r['file']) for r in pure_math}
    already = {n for n in _ALREADY_VALIDATED if n in compilable}
    pure_union = pure_math_names | already

    cat_names = {
        'a_header': 'a) header mancante',
        'b_syntax': 'b) sintassi / estensione non supportata da gcc 3.4.6',
        'c_rel_include': 'c) include relativo mancante',
        'd_other': 'd) altro',
    }

    def example_block(rs, n=3):
        lines = []
        for r in rs[:n]:
            lines.append('  - `%s`' % os.path.basename(r['file']))
            if r['cat'] in ('a_header', 'c_rel_include'):
                lines.append('    header: `%s`' % r['error'].split(':', 1)[-1].strip()
                             if False else '    header: `%s`' % (r['error'] or ''))
            lines.append('    first error: `%s`' % (r['error'] or ''))
            if r['src_line']:
                lines.append('    source @%s: `%s`' % (r['line'], r['src_line']))
        return '\n'.join(lines)

    L = []
    L.append('# Compile sweep report — reconstructed samples vs era-ROM toolchain')
    L.append('')
    L.append('- Generated: %s' % datetime.datetime.now().isoformat(timespec='seconds'))
    L.append('- Toolchain: `%s` (sh-elf gcc 3.4.6, `--without-headers` build)' % XGCC)
    L.append('- Command: `%s -B %s -m2e -O1 -fomit-frame-pointer -nostdinc -I %s -I %s -c <file> -o %s`'
             % (XGCC, XGCC_B, STUB_INC, INC_DIR, OUT_OBJ))
    L.append('- Stub headers: `%s` {stdint.h, math.h, stddef.h, string.h, limits.h, stdbool.h}'
             % STUB_INC)
    L.append('- Source set: `%s/*.c`' % SRC_DIR)
    L.append('- Sample mode: %s' % ('yes — deterministic stratified sample of %d files'
                                     % len(files) if sample_mode else 'no — full sweep'))
    if timeboxed:
        L.append('- **NOTE: full sweep exceeded the 10-min timebox; results are for a '
                 'deterministic stratified sample of %d files.**' % len(files))
    L.append('- Elapsed: %.1f s' % elapsed)
    L.append('')
    L.append('## Summary')
    L.append('')
    L.append('| metric | value |')
    L.append('|---|---|')
    L.append('| total files swept | %d |' % len(files))
    L.append('| compile OK | %d (%.1f%%) |' % (len(ok), 100.0 * len(ok) / len(files)))
    L.append('| compile FAIL | %d (%.1f%%) |' % (len(fail), 100.0 * len(fail) / len(files)))
    for cat in ('a_header', 'b_syntax', 'c_rel_include', 'd_other'):
        L.append('| %s | %d |' % (cat_names[cat], len(by_cat.get(cat, []))))
    L.append('')
    L.append('## Error categories (with examples)')
    L.append('')
    for cat in ('a_header', 'b_syntax', 'c_rel_include', 'd_other'):
        rs = by_cat.get(cat, [])
        L.append('### %s — %d file(s)' % (cat_names[cat], len(rs)))
        L.append('')
        if rs:
            L.append(example_block(rs))
        else:
            L.append('_none_')
        L.append('')
    L.append('## Pure-math validation coverage (theoretical max)')
    L.append('')
    L.append('Heuristic: a compiling sample is a *plausible* pure-math/emulator-'
             'comparable leaf when it does not include `rx8_hw.h`, does not reference '
             '`0xFFFF...` MMIO addresses and does not use `volatile`; already-'
             'behaviourally-validated FUNCS sources from verify_gcc346.py count too.')
    L.append('')
    L.append('| metric | value |')
    L.append('|---|---|')
    L.append('| compile OK | %d |' % len(ok))
    L.append('| plausible pure-math (heuristic) | %d (%.1f%% of OK, %.1f%% of swept)' % (
        len(pure_math_names | already), 100.0 * len(pure_union) / max(len(ok), 1),
        100.0 * len(pure_union) / len(files)))
    L.append('| already behaviourally validated (verify_gcc346.py FUNCS) | %d |'
             % len(already))
    L.append('')
    L.append('Plausible pure-math files:')
    L.append('')
    for n in sorted(pure_union):
        tag = ' [validated]' if n in already else ''
        L.append('- `%s`%s' % (n, tag))
    L.append('')
    L.append('## Failing files (full list)')
    L.append('')
    for r in fail:
        L.append('- `%s` — %s' % (os.path.basename(r['file']), r['cat']))
        L.append('  - `%s`' % (r['error'] or ''))
    L.append('')
    L.append('## Compiling files (full list)')
    L.append('')
    for r in ok:
        L.append('- `%s`' % os.path.basename(r['file']))
    L.append('')

    with open(out_path, 'w') as f:
        f.write('\n'.join(L))
    return len(ok), len(fail), by_cat, pure_union, already


def main():
    ap = argparse.ArgumentParser(description='gcc 3.4.6 compile sweep of the samples')
    ap.add_argument('--out', default='/tmp/compile_all_report.md')
    ap.add_argument('--sample', type=int, default=0,
                    help='deterministic stratified sample size (0 = all files)')
    ap.add_argument('--limit', type=int, default=0,
                    help='compile only the first N files (smoke test)')
    args = ap.parse_args()

    ensure_stubs()
    load_already_validated()

    files = sorted(p for p in glob_join(SRC_DIR, '*.c') if os.path.isfile(p))
    if not files:
        print('ERROR: no *.c files under %s' % SRC_DIR)
        return 2

    sample_mode = False
    timeboxed = False
    if args.limit and args.limit < len(files):
        files = files[:args.limit]
    elif args.sample and args.sample < len(files):
        files = stratified_sample(files, args.sample)
        sample_mode = True

    print('Compile sweep: %d files with %s (gcc 3.4.6, sh-elf)'
          % (len(files), XGCC))
    print('  stubs: %s' % STUB_INC)
    t0 = time.time()
    results = run_sweep(files)
    elapsed = time.time() - t0

    # timebox fallback: if a full sweep is requested but runs past 10 min,
    # re-run on a stratified sample and document it.
    if not sample_mode and not args.limit and elapsed > TIMEOUT_SEC:
        print('  full sweep exceeded %ds timebox -> falling back to a '
              'stratified sample of %d' % (TIMEOUT_SEC, DEFAULT_SAMPLE))
        files2 = stratified_sample(files, DEFAULT_SAMPLE)
        sample_mode, timeboxed = True, True
        results = run_sweep(files2)
        elapsed = time.time() - t0

    ok_n, fail_n, by_cat, pure_union, already = write_report(
        args.out, files, results, sample_mode, elapsed, timeboxed)

    print()
    print('Report written to %s' % args.out)
    print('total=%d  OK=%d  FAIL=%d' % (len(files), ok_n, fail_n))
    for cat in ('a_header', 'b_syntax', 'c_rel_include', 'd_other'):
        print('  %-9s %3d' % (cat, len(by_cat.get(cat, []))))
    print('plausible pure-math (estimate): %d  (already validated: %d)'
          % (len(pure_union), len({n for n in pure_union if n in already})))
    return 0


def glob_join(d, pat):
    import glob
    return glob.glob(os.path.join(d, pat))


if __name__ == '__main__':
    sys.exit(main())
