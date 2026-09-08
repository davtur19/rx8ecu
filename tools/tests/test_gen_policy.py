#!/usr/bin/env python3
"""
tools/tests/test_gen_policy.py — policy regression for the lift pipeline:

  M3: --stub-on-fail must not pollute c/lib/ (stubs go to a scratch dir);
      c/lib/ must contain no empty STATUS: STUB files.
  M5: the v3 CODE emitter closes the block with a standalone `}` (the
      `},}` inline close — source of the runner-dedup special case — is gone
      for future regens).
  M4: opcode_audit's "implemented" docstring matches the code (ANY exception
      in the probe counts as not-implemented, not just NotImplementedError).
  L1: disasm_sh2e prints usage + exit 2 on a bad address (no raw ValueError).
  L2: gen_c_lift_v3 / gen_c_lift_v8 refuse a missing --rom with a clean
      Error + nonzero exit (no traceback).

Run from repo root: python3 tools/tests/test_gen_policy.py
Exit status is non-zero if any check fails.  All vectors are fixed.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

FAILS = []
CHECKS = [0]


def check(cond, msg):
    CHECKS[0] += 1
    if not cond:
        FAILS.append(msg)
        print("FAIL: " + msg)
    else:
        print("ok: " + msg)


def test_no_stubs_in_lib():
    bad = []
    lib = os.path.join(ROOT, 'c', 'lib')
    for f in sorted(os.listdir(lib)):
        if not f.endswith('.c'):
            continue
        with open(os.path.join(lib, f), 'rb') as fh:
            head = fh.read(800).decode('utf-8', 'replace')
        if 'STATUS: STUB' in head:
            bad.append(f)
    check(bad == [], "m3: c/lib/ holds no STATUS: STUB files (got %r)" % bad)


def test_stub_goes_to_scratch():
    import gen_c_lift_v8 as V
    lib = os.path.join(ROOT, 'c', 'lib')
    before = set(os.listdir(lib))
    path = V._write_stub_lib(0x9ABCDEF, 'policy-test reason',
                             rom_label='POLICYTEST')
    try:
        check(os.path.abspath(path) != os.path.join(lib, 'f_9ABCDEF.c')
              and lib not in os.path.abspath(path),
              "m3: _write_stub_lib lands outside c/lib/ (got %s)" % path)
        check(os.path.exists(path),
              "m3: scratch stub file exists")
        check(set(os.listdir(lib)) == before,
              "m3: c/lib/ untouched by stub emission")
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_code_close_standalone():
    import gen_c_lift_v3 as v3
    rec = {'pc': 0x100, 'op': 0xE004, 'kind': 'st',
           'py': ['r[4] = 4'], 'target': None, 'slot': None}
    out = v3._code_literal([rec])
    lines = [l for l in out.split('\n') if l.strip()]
    check(lines[-1] == '}',
          "m5: v3 CODE block ends with a standalone `}` (got %r)"
          % lines[-1])
    check('},}' not in out.replace(' ', ''),
          "m5: no inline `},}` close in v3 CODE emission")


def test_opcode_audit_docstring():
    import opcode_audit as OA
    doc = (OA.__doc__ or '')
    check('without raising NotImplementedError' not in doc,
          "m4: docstring no longer claims NotImplementedError-only")
    probes = [l for l in doc.split('\n') if 'mplemented' in l]
    check(any('any exception' in l for l in probes),
          "m4: docstring documents any-exception semantics")


def _run(args):
    p = subprocess.run([sys.executable] + args, cwd=ROOT,
                       capture_output=True, text=True, timeout=120)
    return p.returncode, (p.stdout or '') + (p.stderr or '')


def test_disasm_bad_addr():
    rc, out = _run([os.path.join('tools', 'disasm_sh2e.py'), '0xZZZ'])
    check(rc == 2 and 'Traceback' not in out and 'Usage' in out,
          "l1: disasm 0xZZZ -> usage + exit 2 (got rc=%d %r)"
          % (rc, out.strip().splitlines()[-1:] if out.strip() else []))


def test_missing_rom_guards():
    for tool, extra in (('tools/gen_c_lift_v3.py', ['--dryrun']),
                        ('tools/gen_c_lift_v8.py', ['--dryrun'])):
        rc, out = _run([tool, '--rom', '/nonexistent_dir/nope.bin'] + extra)
        check(rc != 0 and 'Traceback' not in out
              and ('Error' in out or 'error' in out or 'ERROR' in out),
              "l2: %s missing ROM -> clean Error, nonzero exit "
              "(got rc=%d %r)" % (tool, rc,
                                  out.strip().splitlines()[-1:]
                                  if out.strip() else []))


def main():
    test_no_stubs_in_lib()
    test_stub_goes_to_scratch()
    test_code_close_standalone()
    test_opcode_audit_docstring()
    test_disasm_bad_addr()
    test_missing_rom_guards()
    print('-' * 70)
    print('gen-policy: %d checks, %d failures' % (CHECKS[0], len(FAILS)))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
