#!/usr/bin/env python3
"""
tools/tests/test_lift_fdiv_ieee.py — M1 regression: the v3 FPU mirror must
not crash on a zero divisor, and the v8 oracle-side ZeroDivisionError
wrapper must be gone (the emulator returns IEEE +-inf/NaN and never raises).

  - v3 _code_literal rewrites the fdiv mirror fragment to the template's
    fdiv() helper (ported from v8's _fdiv_ieee), for both plain and
    delay-slot records.
  - the rewritten fragment exec's to +inf (1.0/0.0) and NaN (0.0/0.0),
    bit-agreeing with the sh2emu oracle.
  - v8 _v8_code_literal keeps its (correct) rewrite — locked here.
  - the dead v8 `class _SH2` wrapper is removed from the generator source
    and the emitted template instantiates plain SH2.

Run from repo root: python3 tools/tests/test_lift_fdiv_ieee.py
Exit status is non-zero if any check fails.  All vectors are fixed.
"""
import math
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, f2bits
import c_lift_ops as ops
import gen_c_lift_v3 as v3
import gen_c_lift_v8 as v8mod

FAILS = []
CHECKS = [0]


def check(cond, msg):
    CHECKS[0] += 1
    if not cond:
        FAILS.append(msg)
        print("FAIL: " + msg)
    else:
        print("ok: " + msg)


def fdiv(a, b):
    # Same 3-line helper the v3/v8 test templates carry.
    return a / b if b else (math.inf if a > 0 else (-math.inf if a < 0
                                                   else math.nan))


def _emu_fdiv(a, b):
    cpu = SH2(b'\x00' * 0x100)
    cpu.ram = {}
    cpu.r = [0] * 16
    cpu.fr = [0.0] * 16
    cpu.fr[0], cpu.fr[1] = a, b
    cpu.pr = cpu.SENT
    cpu.macl = cpu.mach = cpu.gbr = 0
    cpu.T = 0
    cpu._Q = cpu._M = 0
    cpu.sr = 0xF0
    cpu._sync_TQM_from_sr()
    cpu._exec(0xF013, 0)          # fdiv fr1,fr0
    return cpu.fr[0]


def test_v3_rewrite():
    rec = {'pc': 0, 'op': 0xF013, 'kind': 'fpu',
           'py': ['fr[0] = ts(fr[0] / fr[1])'],
           'target': None, 'slot': None}
    out = v3._code_literal([rec])
    check('ts(fdiv(fr[0], fr[1]))' in out,
          "m1: v3 _code_literal rewrites the fdiv mirror to fdiv()")
    # delay-slot fdiv gets the same rewrite
    slot = {'pc': 2, 'op': 0xF013, 'kind': 'fpu',
            'py': ['fr[0] = ts(fr[0] / fr[1])'],
            'target': None, 'slot': None}
    brec = {'pc': 0, 'op': 0x000B, 'kind': 'branch',
            'target': None, 'slot': slot}
    out = v3._code_literal([brec])
    check('ts(fdiv(fr[0], fr[1]))' in out,
          "m1: v3 _code_literal rewrites a delay-slot fdiv too")


def test_mirror_ieee_values():
    for a, b, want in ((1.0, 0.0, 'inf'), (-1.0, 0.0, '-inf'),
                       (0.0, 0.0, 'nan'), (1.5, 0.5, 'finite')):
        ns = {'fr': [0.0] * 16, 'ts': ops.ts, 'fdiv': fdiv}
        ns['fr'][0], ns['fr'][1] = a, b
        try:
            exec('fr[0] = ts(fdiv(fr[0], fr[1]))', ns)
        except ZeroDivisionError:
            check(False, "m1: mirror fdiv(%r, %r) must not raise" % (a, b))
            continue
        got = ns['fr'][0]
        emu = _emu_fdiv(a, b)
        if want == 'inf':
            check(got == math.inf and emu == math.inf,
                  "m1: 1.0/0.0 -> +inf on both sides")
        elif want == '-inf':
            check(got == -math.inf and emu == -math.inf,
                  "m1: -1.0/0.0 -> -inf on both sides")
        elif want == 'nan':
            check(got != got and emu != emu,
                  "m1: 0.0/0.0 -> NaN on both sides")
        else:
            check(f2bits(got) == f2bits(emu) == f2bits(3.0),
                  "m1: 1.5/0.5 -> 3.0 bit-exact on both sides")


def test_v8_rewrite_locked():
    rec = {'pc': 0, 'op': 0xF013, 'kind': 'fpu',
           'py': ['fr[0] = ts(fr[0] / fr[1])'],
           'target': None, 'slot': None}
    out = v8mod._v8_code_literal([rec], {}, [])
    check('ts(fdiv(fr[0], fr[1]))' in out,
          "m1: v8 _v8_code_literal keeps the IEEE rewrite")


def test_wrapper_gone():
    src = open(os.path.join(ROOT, 'tools', 'gen_c_lift_v8.py')).read()
    check('class _SH2' not in src,
          "m1: dead v8 _SH2 ZeroDivisionError wrapper removed")
    check('cpu = SH2(ROM_BYTES)' in src,
          "m1: emitted template instantiates the plain SH2 oracle")
    src3 = open(os.path.join(ROOT, 'tools', 'gen_c_lift_v3.py')).read()
    check('def fdiv(a, b):' in src3,
          "m1: v3 FPU template carries the fdiv() helper")


def main():
    test_v3_rewrite()
    test_mirror_ieee_values()
    test_v8_rewrite_locked()
    test_wrapper_gone()
    print('-' * 70)
    print('fdiv-ieee: %d checks, %d failures' % (CHECKS[0], len(FAILS)))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
