#!/usr/bin/env python3
"""
tools/tests/test_review_wave1.py — deterministic repro/verification suite for
the critical-review wave-1 fixes (runner result-loss, ADC bytes, RAM
persistence, denso_ck safety, fsqrt NaN, negc n==m alias, crank N=20).

Run from repo root:
    python3 tools/tests/test_review_wave1.py

Exit status is non-zero if any check fails.  Each test_* function covers one
review finding; all vectors are fixed (no randomness).
"""
import math
import os
import struct
import subprocess
import sys
import tempfile
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import denso_ck
from sh2emu import SH2, MASK
import c_lift_ops
import ecu_pin_emu
from ecu_pin_emu import (
    ECUPinEmu, CrankPulseGen, CRANK_TOTAL_TEETH, CRANK_GAP_INDICES,
)

FAILS = []
CHECKS = [0]


def check(cond, msg):
    CHECKS[0] += 1
    if not cond:
        FAILS.append(msg)
        print("FAIL: " + msg)
    else:
        print("ok: " + msg)


def _run_seq(seq, regs=None, fr=None):
    """Run 16-bit words from pc=0 until rts->SENT; return cpu."""
    buf = bytearray()
    for w in seq + [0x0009, 0x0009]:
        buf += bytes(((w >> 8) & 0xFF, w & 0xFF))
    cpu = SH2(bytes(buf))
    cpu.call(0, regs=regs, fr=fr)
    return cpu


def _nop_rom_512k(bad_at_8b8=False):
    """512 KiB ROM filled with SH-2 nop (0x0009), optionally poisoning 0x8B8."""
    rom = bytearray(b'\x00\x09' * (512 * 1024 // 2))
    assert len(rom) == 512 * 1024
    if bad_at_8b8:
        rom[0x8B8] = 0xFF
        rom[0x8B8 + 1] = 0xFF
    return rom


# ---------------------------------------------------------------------------
# 1. run_tests_parallel: deduped FAIL suite must be reported (no silent PASS)
# ---------------------------------------------------------------------------
def test_runner_dedup_failure_reported():
    import run_tests_parallel as rtp

    with tempfile.TemporaryDirectory() as td:
        # Dedup-eligible body: a CODE block with heavy duplication
        # (1 unique key over 12 lines -> 1*2 < 12 triggers the rewrite).
        lines = ['CODE = {']
        for i in range(12):
            lines.append('0x1000: %d,' % i)
        lines.append('}')
        lines.append('import sys')
        lines.append('print("DEDUP-FAIL-MARKER-xyz")')
        lines.append('sys.exit(1)')
        victim = os.path.join(td, 'test_dedup_fail_xyz.py')
        with open(victim, 'w') as fh:
            fh.write('\n'.join(lines) + '\n')

        src = open(victim).read()
        check(rtp._dedup_code_block(src) != src,
              "runner/1: crafted suite is dedup-eligible")
        orig, rc, wall, out = rtp.run_one(victim)
        check(orig == victim,
              "runner/1: run_one returns the ORIGINAL path (not tmp exec path)")
        check(rc != 0, "runner/1: failing dedup suite returns rc != 0")
        check('DEDUP-FAIL-MARKER-xyz' in out,
              "runner/1: failing dedup suite output is captured")

        # End-to-end through main(): exit != 0 and the suite is named.
        # (isolated via monkeypatched discovery so we run just the victim,
        # not the whole tree; exercises both serial and parallel mapping).
        import io
        import contextlib
        for mode in (['--serial'], []):
            old_argv, old_disc = sys.argv, rtp.discover_tests
            sys.argv = ['run_tests_parallel.py'] + mode + [victim]
            rtp.discover_tests = lambda: []
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    rc_main = rtp.main()
            finally:
                sys.argv = old_argv
                rtp.discover_tests = old_disc
            out_main = buf.getvalue()
            check(rc_main != 0,
                  "runner/1: main(%s) exit != 0 with failing dedup suite"
                  % (mode or ['parallel']))
            check('test_dedup_fail_xyz.py' in out_main,
                  "runner/1: main(%s) names the failing dedup suite"
                  % (mode or ['parallel']))


# ---------------------------------------------------------------------------
# 2. ecu_pin_emu.run_until honors the target (PC==target breakpoint)
# ---------------------------------------------------------------------------
def test_run_until_hits_target():
    with tempfile.TemporaryDirectory() as td:
        rp = os.path.join(td, 'nop.bin')
        open(rp, 'wb').write(bytes(_nop_rom_512k()))
        emu = ECUPinEmu(rom_path=rp)
        target = 0x8B8 + 100
        pc, steps = emu.run_until(target, max_steps=100000)
        check(pc == target,
              "run_until/2: stops at target 0x%X (got 0x%X)" % (target, pc))
        check(steps == 50,
              "run_until/2: 100-byte nop slide takes 50 steps (got %d)" % steps)
        # Unreachable target + tight budget -> limit path, pc != target.
        pc2, steps2 = emu.run_until(0xFFFF0000, max_steps=10)
        check(pc2 != 0xFFFF0000 and steps2 > 0,
              "run_until/2: miss reports limit pc/steps (pc=0x%X steps=%d)"
              % (pc2, steps2))


# ---------------------------------------------------------------------------
# 3. ADC MMIO bytes: even -> (val>>2)&0xFF, odd -> (val<<6)&0xC0
# ---------------------------------------------------------------------------
def test_adc_bytes():
    with tempfile.TemporaryDirectory() as td:
        rp = os.path.join(td, 'nop.bin')
        open(rp, 'wb').write(bytes(_nop_rom_512k()))
        emu = ECUPinEmu(rom_path=rp)
        base = 0xFFFFE500
        for val, hi, lo in ((1, 0x00, 0x40),
                            (512, 0x80, 0x00),
                            (1023, 0xFF, 0xC0)):
            emu.adc[0] = val
            got_hi = emu._mmio_read(base)
            got_lo = emu._mmio_read(base + 1)
            check(got_hi == hi and got_lo == lo,
                  "adc/3: val=%d -> hi=0x%02X lo=0x%02X (got 0x%02X/0x%02X)"
                  % (val, hi, lo, got_hi, got_lo))
        # step()/_build_full_mmio() population must agree with _mmio_read.
        emu.adc[3] = 1023
        mm = emu._build_full_mmio()
        check(mm[base + 6] == emu._mmio_read(base + 6)
              and mm[base + 7] == emu._mmio_read(base + 7),
              "adc/3: mmio dict agrees with _mmio_read")


# ---------------------------------------------------------------------------
# 4. step(): crank/RAM persists, PC resumes (not reset), errors surface
# ---------------------------------------------------------------------------
def test_step_ram_persists_and_pc_advances():
    import io
    import contextlib
    with tempfile.TemporaryDirectory() as td:
        rp = os.path.join(td, 'nop.bin')
        open(rp, 'wb').write(bytes(_nop_rom_512k()))
        emu = ECUPinEmu(rom_path=rp)
        emu.set_crank(800)
        emu.step(10)
        ram1 = emu.get_ram(0xFFFFF434)
        pc1 = emu._next_pc
        check(ram1 != 0,
              "step/4: crank pulse timestamp persists after step 1 (0x%08X)"
              % ram1)
        check(pc1 != 0x8B8,
              "step/4: PC advances past entry after step 1 (0x%08X)" % pc1)
        emu.step(10)
        ram2 = emu.get_ram(0xFFFFF434)
        pc2 = emu._next_pc
        check(ram2 != 0,
              "step/4: crank pulse data still present after step 2 (0x%08X)"
              % ram2)
        check(pc2 != pc1 and pc2 != 0x8B8,
              "step/4: PC resumes (0x%08X -> 0x%08X), not reset to 0x8B8"
              % (pc1, pc2))

        # Unexpected CPU errors must reach stderr (not bare except:pass).
        rp2 = os.path.join(td, 'bad.bin')
        open(rp2, 'wb').write(bytes(_nop_rom_512k(bad_at_8b8=True)))
        emu2 = ECUPinEmu(rom_path=rp2)
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            emu2.step(1)
        check(buf.getvalue().strip() != "",
              "step/4: unknown-opcode error surfaces on stderr")


# ---------------------------------------------------------------------------
# 5. denso_ck -f safety
# ---------------------------------------------------------------------------
def _mk_valid_rom(bad_store=None, lo=0x1000, hi=0x2000):
    rom = bytearray(512 * 1024)
    for i in range(0, len(rom), 4):
        rom[i:i + 4] = struct.pack('>I', (i * 0x01010101) & 0xFFFFFFFF)
    struct.pack_into('>I', rom, denso_ck.DESC_OFF, lo)
    struct.pack_into('>I', rom, denso_ck.DESC_OFF + 4, hi)
    _lo, _hi, _s, correct = denso_ck.compute(rom)
    struct.pack_into('>I', rom, denso_ck.DIFF_OFF,
                     correct if bad_store is None else bad_store)
    return rom, correct


def test_denso_ck_safety():
    import io
    import contextlib
    with tempfile.TemporaryDirectory() as td:
        # Short ROM -> clean error, no traceback.
        shortp = os.path.join(td, 'short.bin')
        open(shortp, 'wb').write(b'\x00' * 100)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = denso_ck.main([shortp])
        check(rc != 0 and '524288' in err.getvalue()
              and 'Traceback' not in err.getvalue(),
              "denso_ck/5: short ROM rejected cleanly")

        # Missing file -> clean error.
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = denso_ck.main([os.path.join(td, 'nope.bin')])
        check(rc != 0 and 'not found' in err.getvalue().lower(),
              "denso_ck/5: missing ROM reports FileNotFound cleanly")

        # Corrupt descriptor (lo > hi) -> refused.
        badp = os.path.join(td, 'baddesc.bin')
        rom, _c = _mk_valid_rom()
        struct.pack_into('>I', rom, denso_ck.DESC_OFF, 0x80000)
        struct.pack_into('>I', rom, denso_ck.DESC_OFF + 4, 0x1000)
        open(badp, 'wb').write(bytes(rom))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = denso_ck.main([badp])
        check(rc != 0 and 'descriptor' in err.getvalue().lower(),
              "denso_ck/5: corrupt descriptor (lo>hi) refused")

        # Misaligned lo -> refused.
        badp2 = os.path.join(td, 'badalign.bin')
        rom2, _c2 = _mk_valid_rom()
        struct.pack_into('>I', rom2, denso_ck.DESC_OFF, 0x1001)
        open(badp2, 'wb').write(bytes(rom2))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = denso_ck.main([badp2])
        check(rc != 0 and 'align' in err.getvalue().lower(),
              "denso_ck/5: misaligned lo refused")

        # -f + -o together -> forbidden.
        okp = os.path.join(td, 'ok.bin')
        rom3, correct3 = _mk_valid_rom(bad_store=0)
        open(okp, 'wb').write(bytes(rom3))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = denso_ck.main([okp, '-f', '-o', os.path.join(td, 'o.bin')])
        check(rc != 0 and 'mutually exclusive' in err.getvalue(),
              "denso_ck/5: -f + -o combo rejected")

        # Positive -o path: fixed copy verifies.
        outp = os.path.join(td, 'fixed.bin')
        rc = denso_ck.main([okp, '-o', outp])
        check(rc == 0 and os.path.isfile(outp),
              "denso_ck/5: -o fix writes output")
        check(denso_ck.main([outp]) == 0,
              "denso_ck/5: -o output re-verifies OK")

        # Positive -f path: .bak kept, image verifies.
        fixp = os.path.join(td, 'fixme.bin')
        before, _c4 = _mk_valid_rom(bad_store=0x12345678)
        open(fixp, 'wb').write(bytes(before))
        rc = denso_ck.main([fixp, '-f'])
        bakp = fixp + '.bak'
        check(rc == 0 and os.path.isfile(bakp)
              and open(bakp, 'rb').read() == bytes(before),
              "denso_ck/5: -f keeps exact .bak")
        check(denso_ck.main([fixp]) == 0,
              "denso_ck/5: -f image re-verifies OK")


# ---------------------------------------------------------------------------
# 6. sh2emu fsqrt(-1.0) -> NaN, no exception
# ---------------------------------------------------------------------------
def test_fsqrt_negative_nan():
    cpu = _run_seq([0xF16D, 0x000B], fr={1: -1.0})   # fsqrt fr1
    check(isinstance(cpu.fr[1], float) and math.isnan(cpu.fr[1]),
          "fsqrt/6: fsqrt(-1.0) -> NaN without exception")
    cpu = _run_seq([0xF16D, 0x000B], fr={1: 4.0})
    check(cpu.fr[1] == 2.0, "fsqrt/6: fsqrt(4.0) -> 2.0 (got %r)" % cpu.fr[1])
    cpu = _run_seq([0xF06D, 0x000B], fr={0: -0.0})   # fsqrt fr0, -0.0 edge
    check(cpu.fr[0] == 0.0 and not math.isnan(cpu.fr[0]),
          "fsqrt/6: fsqrt(-0.0) -> +0.0 (got %r)" % cpu.fr[0])


# ---------------------------------------------------------------------------
# 7. negc n==m alias: T from ORIGINAL Rm (sh2emu + c_lift_ops agree)
# ---------------------------------------------------------------------------
def test_negc_alias():
    # Rm=0,T=1 -> r=0xFFFFFFFF, borrow T=1 (buggy impl gave T=0).
    cpu = _run_seq([0x0018, 0x655A, 0x000B], regs={5: 0})  # sett; negc r5,r5
    check(cpu.r[5] == 0xFFFFFFFF and cpu.T == 1,
          "negc/7: negc r5,r5 Rm=0 T=1 -> r=0x%08X T=%d"
          % (cpu.r[5], cpu.T))
    # Rm=0xFFFFFFFF,T=1 -> r=0, borrow T=0 (buggy impl gave T=1).
    cpu = _run_seq([0x0018, 0x655A, 0x000B], regs={5: 0xFFFFFFFF})
    check(cpu.r[5] == 0 and cpu.T == 0,
          "negc/7: negc r5,r5 Rm=0xFFFFFFFF T=1 -> r=0x%08X T=%d"
          % (cpu.r[5], cpu.T))

    # c_lift_ops mirror must snapshot Rm: T expr uses _m0/_t0.
    d = c_lift_ops.translate(0x655A, 0, b'')
    check(d is not None, "negc/7: c_lift_ops decodes negc")
    c_text = ' '.join(d['c'])
    check('_m0' in c_text and '(_m0 + _t0)' in c_text,
          "negc/7: C lift tests original Rm (_m0): %s" % c_text)
    ns = {'r': [0] * 16, 'T': 1}
    ns['r'][5] = 0
    code = '\n'.join(ln.strip() for ln in '\n'.join(d['py']).splitlines()
                     if ln.strip())
    exec(compile(code, '<negc-mirror>', 'exec'),
         dict(ns, s32=c_lift_ops.s32), ns)
    check(ns['r'][5] == 0xFFFFFFFF and ns['T'] == 1,
          "negc/7: py mirror alias case r=0x%08X T=%d" % (ns['r'][5], ns['T']))


# ---------------------------------------------------------------------------
# MAJOR. crank N=20 + gap indices + period at 800/3000/9000 rpm
# ---------------------------------------------------------------------------
def test_crank_n20_periods():
    check(CRANK_TOTAL_TEETH == 20, "crank/M: N == 20")
    check(tuple(CRANK_GAP_INDICES) == (5, 15), "crank/M: gap indices (5, 15)")
    for rpm, tooth, gap in ((800, 3750.0, 5625.0),
                            (3000, 1000.0, 1500.0),
                            (9000, 333.3333333333333, 500.0)):
        g = CrankPulseGen()
        g.set_rpm(rpm)
        check(abs(g.us_per_tooth - tooth) < 1e-6
              and abs(g.us_per_gap - 1.5 * g.us_per_tooth) < 1e-9,
              "crank/M: %drpm tooth=%.3fus gap=1.5x" % (rpm, g.us_per_tooth))
        g.tooth_idx = 5
        check(abs(g.get_current_period_us() - gap) < 1e-6,
              "crank/M: %drpm gap period %.3fus" % (rpm, gap))
        g.tooth_idx = 0
        check(abs(g.get_current_period_us() - tooth) < 1e-6,
              "crank/M: %drpm tooth period %.3fus" % (rpm, tooth))
    # Full 20-cycle wraps and visits both gaps.
    g = CrankPulseGen()
    g.set_rpm(1000)
    seen = set()
    idx = g.tooth_idx
    for _ in range(20):
        seen.add(g.tooth_idx)
        g.next_tooth()
    check(len(seen) == 20 and g.tooth_idx == idx,
          "crank/M: 20-cycle visits all positions and wraps")


def main():
    test_runner_dedup_failure_reported()
    test_run_until_hits_target()
    test_adc_bytes()
    test_step_ram_persists_and_pc_advances()
    test_denso_ck_safety()
    test_fsqrt_negative_nan()
    test_negc_alias()
    test_crank_n20_periods()
    print('-' * 70)
    print('wave1: %d checks, %d failures' % (CHECKS[0], len(FAILS)))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
