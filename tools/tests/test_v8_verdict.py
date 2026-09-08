#!/usr/bin/env python3
"""
tools/tests/test_v8_verdict.py — H2 regression: the v8 test-template verdict
must not PASS on zero agreeing cases, and must REPORT an honest skip budget.

The verdict tail shipped inside every v8-generated test is hoisted as
gen_c_lift_v8._V8_VERDICT_TAIL (pre-%-format source, `%%`-escaped).  These
checks exec the ACTUAL shipped logic in stubbed namespaces:

  - all-skipped LOOP_AGREE (busy-wait agreement) -> FAIL (rc=1), LOOP label kept
  - HALT (0 agreeing, no ret reachable)           -> FAIL (rc=1), HALT label kept
  - SELF_LOOP with 0 agreeing                     -> FAIL (rc=1)
  - clean run (ok>0, skips<=50)                   -> PASS (rc=0), no WARN
  - high-skip run (skips>50, ok>0)                -> PASS (rc=0) + WARN line
  - skipped>200                                   -> FAIL (rc=1)

Keeping the LOOP/HALT labels (with a FAIL verdict line) preserves the
gen_lib_test sweep parsing: FAIL + SKIPREASONS still re-grade to
UNVERIFIED-HWPOLL for genuine agreement, while a direct run no longer
reports a non-returning function as passing.

Run from repo root: python3 tools/tests/test_v8_verdict.py
Exit status is non-zero if any check fails.  All vectors are fixed.
"""
import io
import os
import sys
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import gen_c_lift_v8 as V

FAILS = []
CHECKS = [0]


def check(cond, msg):
    CHECKS[0] += 1
    if not cond:
        FAILS.append(msg)
        print("FAIL: " + msg)
    else:
        print("ok: " + msg)


def _tail_src():
    return V._V8_VERDICT_TAIL.replace('%%', '%')


def _run(ok, skipped, reasons, code, self_loop=False):
    src = _tail_src()
    ns = {'ok': ok, 'skipped': skipped, 'N': 500,
          'SKIPREASONS': dict(reasons),
          'SELF_LOOP': [self_loop], 'OOB_TGTS': [],
          'CODE': dict(code), 'ENTRY': 0x1000, 'sys': sys}
    buf = io.StringIO()
    rc = 0
    with redirect_stdout(buf):
        try:
            exec(src, ns)
        except SystemExit as e:
            rc = e.code
    return rc, buf.getvalue()


_RET_CODE = {0x1000: {'kind': 'ret', 'py': None, 'slot_py': None,
                      'target': None, 'cond': None}}
_LOOP_CODE = {0x1000: {'kind': 'branch', 'py': None, 'slot_py': None,
                       'target': 0x1000, 'cond': None}}


def test_loop_agree_fails():
    rc, out = _run(0, 500, {'step-limit-both': 500}, _RET_CODE)
    check(rc == 1 and 'LOOP' in out and 'FAIL' in out,
          "h2: all-skipped LOOP_AGREE -> FAIL rc=1 (got rc=%d %r)"
          % (rc, out.strip().splitlines()[-2:]))


def test_halt_fails():
    rc, out = _run(0, 500, {'emu-step-limit': 500}, _LOOP_CODE)
    check(rc == 1 and 'HALT' in out and 'FAIL' in out,
          "h2: HALT with 0 agreeing -> FAIL rc=1 (got rc=%d %r)"
          % (rc, out.strip().splitlines()[-2:]))


def test_self_loop_fails():
    # SELF_LOOP arm needs has_ret True (else the earlier HALT arm fires):
    # a self-loop branch plus a reachable ret elsewhere in CODE.
    code = {0x1000: {'kind': 'branch', 'py': None, 'slot_py': None,
                     'target': 0x1000, 'cond': None},
            0x1002: {'kind': 'ret', 'py': None, 'slot_py': None,
                     'target': None, 'cond': None}}
    rc, out = _run(0, 500, {'emu-exc': 500}, code, self_loop=True)
    check(rc == 1 and 'LOOP' in out and 'FAIL' in out,
          "h2: SELF_LOOP with 0 agreeing -> FAIL rc=1 (got rc=%d %r)"
          % (rc, out.strip().splitlines()[-2:]))


def test_clean_pass():
    rc, out = _run(490, 10, {'table-miss': 10}, _RET_CODE)
    check(rc == 0 and 'PASS' in out and 'WARN' not in out,
          "h2: clean run -> PASS rc=0, no WARN (got rc=%d %r)"
          % (rc, out.strip().splitlines()[-2:]))


def test_high_skip_warns():
    rc, out = _run(400, 100, {'table-miss': 100}, _RET_CODE)
    check(rc == 0 and 'PASS' in out and 'WARN' in out,
          "h2: 100-skip run -> PASS rc=0 with WARN (got rc=%d %r)"
          % (rc, out.strip().splitlines()[-3:]))


def test_skip_budget_fails():
    rc, out = _run(250, 250, {'table-miss': 250}, _RET_CODE)
    check(rc == 1 and 'FAIL' in out,
          "h2: 250-skip run -> FAIL rc=1 (got rc=%d %r)"
          % (rc, out.strip().splitlines()[-2:]))


def main():
    try:
        _tail_src()
    except AttributeError:
        check(False, "h2: gen_c_lift_v8._V8_VERDICT_TAIL missing")
        print('-' * 70)
        print('v8-verdict: %d checks, %d failures' % (CHECKS[0], len(FAILS)))
        return 1
    test_loop_agree_fails()
    test_halt_fails()
    test_self_loop_fails()
    test_clean_pass()
    test_high_skip_warns()
    test_skip_budget_fails()
    print('-' * 70)
    print('v8-verdict: %d checks, %d failures' % (CHECKS[0], len(FAILS)))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
