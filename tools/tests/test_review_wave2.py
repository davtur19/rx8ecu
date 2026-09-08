#!/usr/bin/env python3
"""
tools/tests/test_review_wave2.py — deterministic repro/verification suite for
the tools-review wave-2 fixes (memo keys, atomic compile gate, strict jump
tables, disasm bounds, runner timeout/jobs, sh2emu MMIO fetch, mazda
validation, denso ASCII tokens).

Run from repo root:
    python3 tools/tests/test_review_wave2.py

Exit status is non-zero if any check fails.  All vectors are fixed (no
randomness); no ROM files or toolchains needed.
"""
import io
import os
import struct
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import disasm_sh2e
from sh2emu import SH2
import mazda_security
import denso_ck
import run_tests_parallel as rtp

FAILS = []
CHECKS = [0]


def check(cond, msg):
    CHECKS[0] += 1
    if not cond:
        FAILS.append(msg)
        print("FAIL: " + msg)
    else:
        print("ok: " + msg)


# ---------------------------------------------------------------------------
# 1. memoize: sound ROM keys (no id(rom)) + different ROMs never alias
# ---------------------------------------------------------------------------
def test_memo_rom_keys():
    import gen_c_lift_v8 as G

    # Same length, different bytes -> different keys.
    ra = b'\xD0\x00' + b'\x00\x09' * 31          # mov.l @(0,PC),r0 at 0
    rb = b'\x00\x09' * 32                        # pure nops
    assert len(ra) == len(rb)
    for mod, name in ((G, 'v8'),):
        check(mod._rom_key(ra) != mod._rom_key(rb),
              "memo/1: %s keys differ for different ROMs (same length)" % name)
        check(mod._rom_key(ra) == mod._rom_key(bytearray(ra)),
              "memo/1: %s key is content-based (bytes == bytearray)" % name)

    # Functional: whole-ROM pool cache distinguishes the two images in
    # either query order (a stale id()-alias would return rb's set for ra).
    for first, second in ((rb, ra), (ra, rb)):
        G._POOL_ALL_CACHE.clear()
        p_first = set(G._pcrel_pool_all(first))
        p_second = set(G._pcrel_pool_all(second))
        p_ra = p_first if first is ra else p_second
        p_rb = p_second if first is ra else p_first
        check(4 in p_ra and len(p_rb) == 0,
              "memo/1: pool sets are per-content (order %s first)"
              % ('rb' if first is rb else 'ra'))
    G._POOL_ALL_CACHE.clear()


# ---------------------------------------------------------------------------
# 2. atomic compile gate: publish-on-PASS, keep pre-existing on FAIL
# ---------------------------------------------------------------------------
def test_gate_atomic():
    import gen_c_lift as gcl

    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, 'lift.c')
        with open(out, 'w') as fh:
            fh.write('/* sentinel good lift */\nvoid keep(void){}\n')
        # FAIL gate: bogus C must NOT truncate/delete the pre-existing file.
        ok, err = gcl._gate_and_publish('this is not C @@@\n', out)
        check(not ok and isinstance(err, str) and len(err) > 0,
              "gate/2: bogus C fails the gate with an error tail")
        check(open(out).read().startswith('/* sentinel good lift */'),
              "gate/2: pre-existing lift survives a FAIL untouched")
        # PASS gate: valid C is published via replace.
        ok, err = gcl._gate_and_publish('void fresh(void){}\n', out)
        check(ok and err is None,
              "gate/2: valid C passes the gate")
        check(open(out).read() == 'void fresh(void){}\n',
              "gate/2: PASS publishes the new source")
        # No temp litter left behind in the target dir.
        leftovers = [n for n in os.listdir(td) if n.startswith('.gate_')]
        check(leftovers == [],
              "gate/2: no .gate_ temp files remain (got %r)" % leftovers)


# ---------------------------------------------------------------------------
# 3. strict jump tables: a hole rejects, a clean table resolves
# ---------------------------------------------------------------------------
def _jt_rom(hole):
    """Tiny synthetic ROM: mov.l pool->r5; mov r4,r0; mov.l @(r0,r5),r6;
    jmp @r6; table at 0x40 = [0x10, hole|0x10, 0x10, 0]; code at 0x10."""
    rom = bytearray(0x50)
    struct.pack_into('>H', rom, 0x00, 0xD507)    # mov.l @(7,PC),r5 -> pool 0x20
    struct.pack_into('>H', rom, 0x02, 0x6043)    # mov r4,r0 (runtime index)
    struct.pack_into('>H', rom, 0x04, 0x065E)    # mov.l @(r0,r5),r6
    struct.pack_into('>H', rom, 0x06, 0x462B)    # jmp @r6
    struct.pack_into('>H', rom, 0x08, 0x0009)    # delay slot: nop
    struct.pack_into('>H', rom, 0x10, 0x000B)    # target: rts
    struct.pack_into('>H', rom, 0x12, 0x0009)    # nop
    struct.pack_into('>I', rom, 0x20, 0x40)      # pool: table base
    struct.pack_into('>I', rom, 0x40, 0x10)
    struct.pack_into('>I', rom, 0x44, hole)
    struct.pack_into('>I', rom, 0x48, 0x10)
    struct.pack_into('>I', rom, 0x4C, 0x0)
    return bytes(rom)


def test_enum_table_strict():
    import gen_c_lift_v8 as G

    for mod, name in ((G, 'v8'),):
        res = mod.build_cfg(_jt_rom(0x10), 0, 0x30, set(), {},
                            allow_runtime_base=True)
        check(res.reject is None,
              "jtable/3: %s clean table resolves (reject=%r)" % (name, res.reject))
        res = mod.build_cfg(_jt_rom(0x123456), 0, 0x30, set(), {},
                            allow_runtime_base=True)
        check(res.reject is not None and res.reject[0] == 'jump_table_unresolved',
              "jtable/3: %s hole rejects jump_table_unresolved (got %r)"
              % (name, res.reject))


# ---------------------------------------------------------------------------
# 4. disasm_range bounds: truncate, odd tail, no struct.error
# ---------------------------------------------------------------------------
def test_disasm_range_bounds():
    rom = b'\x00\x09\x00'                        # nop + stray byte
    lines = disasm_sh2e.disasm_range(rom, 0, 3)
    check(len(lines) == 2 and 'unknown' in lines[1],
          "disasm/4: truncated tail emits (unknown,...) (got %r)" % (lines,))
    lines = disasm_sh2e.disasm_range(b'\x00\x09', 0, 100)
    check(len(lines) == 1 and 'nop' in lines[0],
          "disasm/4: overlong length truncates to ROM end")
    check(disasm_sh2e.disasm_range(rom, 10, 4) == [],
          "disasm/4: start past end gives []")
    for bad in (('neg-start', lambda: disasm_sh2e.disasm_range(rom, -2, 4)),
                ('neg-len', lambda: disasm_sh2e.disasm_range(rom, 0, -1))):
        try:
            bad[1]()
            check(False, "disasm/4: %s raises ValueError" % bad[0])
        except ValueError:
            check(True, "disasm/4: %s raises ValueError" % bad[0])
        except Exception as e:  # noqa: BLE001 — must NOT be struct.error
            check(False, "disasm/4: %s raised %r (want ValueError)"
                  % (bad[0], e))


# ---------------------------------------------------------------------------
# 5. runner: jobs<1 rejected, suite timeout FAILs, temps cleaned
# ---------------------------------------------------------------------------
def test_runner_jobs_rejected():
    import contextlib
    for argv in (['run_tests_parallel.py', '--jobs', '0'],
                 ['run_tests_parallel.py', '-j', '-5']):
        old = sys.argv
        sys.argv = argv
        try:
            buf = io.StringIO()
            try:
                with contextlib.redirect_stderr(buf):
                    rtp.main()
                check(False, "runner/5: %s exits (no return)" % ' '.join(argv[1:]))
            except SystemExit as e:
                check(e.code == 2,
                      "runner/5: %s -> argparse error (exit 2, got %r)"
                      % (' '.join(argv[1:]), e.code))
        finally:
            sys.argv = old


def test_runner_timeout_and_cleanup():
    from unittest import mock
    with tempfile.TemporaryDirectory() as td:
        victim = os.path.join(td, 'test_wave2_dummy_xyz.py')
        with open(victim, 'w') as fh:
            fh.write('print("hi")\n')
        with mock.patch('subprocess.run',
                        side_effect=subprocess.TimeoutExpired('cmd', 600)):
            orig, rc, wall, out = rtp.run_one(victim)
        check(rc != 0 and 'TIMEOUT' in out,
              "runner/5: TimeoutExpired -> FAIL with TIMEOUT marker")
        check(not [n for n in os.listdir(td) if n.startswith('.dedup_')],
              "runner/5: no .dedup_ litter after timeout path")
    # atexit registry removes leftovers even off the normal path.
    with tempfile.TemporaryDirectory() as td:
        stray = os.path.join(td, 'stray.py')
        with open(stray, 'w') as fh:
            fh.write('x\n')
        rtp._register_temp(stray)
        rtp._cleanup_temps()
        check(not os.path.exists(stray) and stray not in rtp._TEMP_FILES,
              "runner/5: atexit registry cleans registered temps")
    check(getattr(rtp, '_TIMEOUT_S', None) == 600,
          "runner/5: per-suite timeout is 600s")


# ---------------------------------------------------------------------------
# 6. sh2emu: MMIO-mapped code bytes are fetched (no fast-path blind spot)
# ---------------------------------------------------------------------------
def test_sh2emu_mmio_fetch():
    rom = bytes([0xE0, 0x01,   # mov #1,r0
                 0x00, 0x0B,   # rts
                 0x00, 0x09])  # delay slot: nop
    cpu = SH2(rom)
    check(cpu.call(0) == 1, "mmio/6: baseline without MMIO gives r0=1")
    cpu = SH2(rom)
    got = cpu.call(0, mmio={0: 0xE0, 1: 0x02})   # overlay: mov #2,r0
    check(got == 2, "mmio/6: MMIO-overlaid opcode executes (r0=%d, want 2)" % got)


# ---------------------------------------------------------------------------
# 7. mazda_security: length validation with messages
# ---------------------------------------------------------------------------
def test_mazda_validation():
    for seed, secret, tag in ((b'\x01\x02', b'MazdA', 'short seed'),
                              (b'\x01\x02\x03\x04', b'MazdA', 'long seed'),
                              (b'\x45\x82\x0A', b'ab', 'short secret'),
                              (b'\x45\x82\x0A', b'toolongsecret', 'long secret')):
        try:
            mazda_security.compute_key(seed, secret)
            check(False, "mazda/7: %s raises ValueError" % tag)
        except ValueError as e:
            check(str(e) != "",
                  "mazda/7: %s raises ValueError with message (%s)" % (tag, e))
    check(mazda_security.compute_key(bytes([0x45, 0x82, 0x0A]), b'MazdA')
          == bytes([0xA0, 0x72, 0x58]),
          "mazda/7: ROM-verified vector still computes")


# ---------------------------------------------------------------------------
# 8. denso_ck: ASCII-only output with stable OK/FAIL tokens
# ---------------------------------------------------------------------------
def _mk_rom(bad_store=None, lo=0x1000, hi=0x2000):
    rom = bytearray(512 * 1024)
    for i in range(0, len(rom), 4):
        rom[i:i + 4] = struct.pack('>I', (i * 0x01010101) & 0xFFFFFFFF)
    struct.pack_into('>I', rom, denso_ck.DESC_OFF, lo)
    struct.pack_into('>I', rom, denso_ck.DESC_OFF + 4, hi)
    _lo, _hi, _s, correct = denso_ck.compute(rom)
    struct.pack_into('>I', rom, denso_ck.DIFF_OFF,
                     correct if bad_store is None else bad_store)
    return rom


def test_denso_tokens():
    import contextlib
    with tempfile.TemporaryDirectory() as td:
        okp = os.path.join(td, 'ok.bin')
        open(okp, 'wb').write(bytes(_mk_rom()))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = denso_ck.main([okp])
        out = buf.getvalue()
        check(rc == 0 and out.splitlines()[-1].startswith('OK'),
              "denso/8: valid ROM ends with a stable OK token")
        badp = os.path.join(td, 'bad.bin')
        open(badp, 'wb').write(bytes(_mk_rom(bad_store=0)))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = denso_ck.main([badp])
        out = buf.getvalue()
        check(rc != 0 and 'FAIL' in out,
              "denso/8: bad ROM reports a stable FAIL token")
        try:
            (out).encode('ascii')
            check(True, "denso/8: verify output is pure ASCII")
        except UnicodeEncodeError:
            check(False, "denso/8: verify output is pure ASCII")


def main():
    test_memo_rom_keys()
    test_gate_atomic()
    test_enum_table_strict()
    test_disasm_range_bounds()
    test_runner_jobs_rejected()
    test_runner_timeout_and_cleanup()
    test_sh2emu_mmio_fetch()
    test_mazda_validation()
    test_denso_tokens()
    print('-' * 70)
    print('wave2: %d checks, %d failures' % (CHECKS[0], len(FAILS)))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
