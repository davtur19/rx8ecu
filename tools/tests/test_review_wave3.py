#!/usr/bin/env python3
"""
tools/tests/test_review_wave3.py — deterministic repro/verification suite for
the tools-review wave-3 fixes (sh2emu SR/T/Q/M mirror desync, ecu_pin_emu
port writes, fdiv-by-zero, _emu_executes crash counting, SH2.call input
validation).

Run from repo root:
    python3 tools/tests/test_review_wave3.py

Exit status is non-zero if any check fails.  All vectors are fixed (no
randomness); no ROM files or toolchains needed (the pin-emu test builds its
own 512 KiB mini-ROM in a temp dir).
"""
import math
import os
import struct
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2
from ecu_pin_emu import ECUPinEmu, PORT_BASE

FAILS = []
CHECKS = [0]


def check(cond, msg):
    CHECKS[0] += 1
    if not cond:
        FAILS.append(msg)
        print("FAIL: " + msg)
    else:
        print("ok: " + msg)


def _prog(words):
    """Small ROM image (4 KiB) holding the 16-bit words at address 0."""
    buf = bytearray(0x1000)
    for i, w in enumerate(words):
        struct.pack_into('>H', buf, i * 2, w)
    return bytes(buf)


# ---------------------------------------------------------------------------
# CRITICAL-1. sh2emu SR <-> T/Q/M mirror (single source of truth)
# ---------------------------------------------------------------------------
def test_sr_tqm_mirror():
    # sett; mov #0,R0; ldc R0,SR; movt R1 -> SR=0 so T=0, R1=0
    # (0xE000 = mov #0,R0; 0x400E = ldc R0,SR; 0x0129 = movt R1)
    cpu = SH2(_prog([0x0018, 0xE000, 0x400E, 0x0129, 0x0009]))
    cpu.call(0, break_addrs={0x8})
    check(cpu.T == 0 and cpu.r[1] == 0 and cpu.sr == 0x0,
          "sr/1: sett;ldc SR=0 -> T=%d R1=%d sr=0x%X (want 0/0/0x0)"
          % (cpu.T, cpu.r[1], cpu.sr))

    # clrt; mov #1,R0; ldc R0,SR; movt R1 -> SR=1 so T=1, R1=1
    cpu = SH2(_prog([0x0008, 0xE001, 0x400E, 0x0129, 0x0009]))
    cpu.call(0, break_addrs={0x8})
    check(cpu.T == 1 and cpu.r[1] == 1 and cpu.sr == 0x1,
          "sr/1: clrt;ldc SR=1 -> T=%d R1=%d sr=0x%X (want 1/1/0x1)"
          % (cpu.T, cpu.r[1], cpu.sr))

    # sett; stc SR,R1 (0x0102) -> live T bit visible (0xF0|1 = 0xF1)
    cpu = SH2(_prog([0x0018, 0x0102, 0x0009]))
    cpu.call(0, break_addrs={0x4})
    check(cpu.r[1] == 0xF1,
          "sr/1: sett;stc SR,R1 -> R1=0x%X (want 0xF1)" % cpu.r[1])
    cpu = SH2(_prog([0x0008, 0x0102, 0x0009]))
    cpu.call(0, break_addrs={0x4})
    check(cpu.r[1] == 0xF0,
          "sr/1: clrt;stc SR,R1 -> R1=0x%X (want 0xF0)" % cpu.r[1])

    # sett; stc.l SR,@-R15 (0x4F03) -> stacked word carries T
    cpu = SH2(_prog([0x0018, 0x4F03, 0x0009]))
    cpu.call(0, regs={15: 0x1000}, break_addrs={0x4})
    stacked = (cpu.ram.get(0xFFC, 0) << 24) | (cpu.ram.get(0xFFD, 0) << 16) | \
              (cpu.ram.get(0xFFE, 0) << 8) | cpu.ram.get(0xFFF, 0)
    check(stacked == 0xF1,
          "sr/1: sett;stc.l SR,@-R15 -> [R15]=0x%X (want 0xF1)" % stacked)

    # ldc.l @R1+,SR resyncs too (SR=0x301 -> T=1,Q=1,M=1; movt R2 = 1)
    ram = {0x1000: 0x00, 0x1001: 0x00, 0x1002: 0x03, 0x1003: 0x01}
    cpu = SH2(_prog([0x4107, 0x0229, 0x0009]))   # ldc.l @r1+,SR; movt r2
    cpu.call(0, regs={1: 0x1000}, ram=ram, break_addrs={0x4})
    check(cpu.sr == 0x301 and cpu.T == 1 and cpu._Q == 1 and cpu._M == 1
          and cpu.r[2] == 1,
          "sr/1: ldc.l SR=0x301 -> T=%d Q=%d M=%d R2=%d (want 1/1/1/1)"
          % (cpu.T, cpu._Q, cpu._M, cpu.r[2]))

    # rte pops SR and resyncs T (stacked PC=0x10, SR=0x1; target: movt R1)
    img = bytearray(0x1000)
    for a, w in {0x0: 0x002B, 0x2: 0x0009, 0x10: 0x0129, 0x12: 0x0009}.items():
        struct.pack_into('>H', img, a, w)
    ram = {0xFFFFDF00: 0x00, 0xFFFFDF01: 0x00, 0xFFFFDF02: 0x00,
           0xFFFFDF03: 0x10, 0xFFFFDF04: 0x00, 0xFFFFDF05: 0x00,
           0xFFFFDF06: 0x00, 0xFFFFDF07: 0x01}
    cpu = SH2(bytes(img))
    cpu.call(0, ram=ram, break_addrs={0x14})
    check(cpu.T == 1 and cpu.r[1] == 1 and cpu.sr == 0x1,
          "sr/1: rte SR=0x1 -> T=%d R1=%d sr=0x%X (want 1/1/0x1)"
          % (cpu.T, cpu.r[1], cpu.sr))

    # Q/M live in the manual-correct SR bits 8/9 (not the old 3/2):
    # div0s R3,R4 (0x2437) with Rn=1 (Q=0), Rm=0x80000000 (M=1), T=1.
    cpu = SH2(_prog([0x2437, 0x0009]))
    cpu.call(0, regs={3: 0x80000000, 4: 0x1}, break_addrs={0x2})
    check(cpu.T == 1 and cpu._Q == 0 and cpu._M == 1 and cpu.sr == 0x2F1,
          "sr/1: div0s -> T=%d Q=%d M=%d sr=0x%X (want 1/0/1/0x2F1)"
          % (cpu.T, cpu._Q, cpu._M, cpu.sr))

    # DIV still works after the Q/M bit move (one div1 step, Q==M case).
    cpu = SH2(_prog([0x2437, 0x3434, 0x0009]))
    cpu.call(0, regs={3: 0x80000000, 4: 0x80000000}, break_addrs={0x4})
    check(cpu.r[4] == 0x80000000 and cpu._Q == 1 and cpu._M == 1
          and cpu.T == 1,
          "sr/1: div1 step -> r4=0x%08X Q=%d M=%d T=%d (want ...000/1/1/1)"
          % (cpu.r[4], cpu._Q, cpu._M, cpu.T))

    # div0u clears M/Q/T and the SR image.
    cpu = SH2(_prog([0x0019, 0x0009]))
    cpu.call(0, break_addrs={0x2})
    check(cpu.T == 0 and cpu._Q == 0 and cpu._M == 0 and cpu.sr == 0xF0,
          "sr/1: div0u -> T=%d Q=%d M=%d sr=0x%X (want 0/0/0/0xF0)"
          % (cpu.T, cpu._Q, cpu._M, cpu.sr))


# ---------------------------------------------------------------------------
# CRITICAL-2. ecu_pin_emu firmware port writes reach the pins
# ---------------------------------------------------------------------------
def _mini_port_rom():
    """512 KiB ROM: mov #0x0F,R0; mov.l @(PC),R1(=0xFFFFF720);
    mov.b R0,@R1; nop; bra $ (slice ends via max_steps)."""
    rom = bytearray(0x80000)
    for a, w in ((0x8B8, 0xE00F), (0x8BA, 0xD103), (0x8BC, 0x2100),
                 (0x8BE, 0x0009), (0x8C0, 0xAFFE), (0x8C2, 0x0009)):
        struct.pack_into('>H', rom, a, w)
    struct.pack_into('>I', rom, 0x8C8, 0xFFFFF720)
    return bytes(rom)


def test_port_writes_reach_pins():
    with tempfile.TemporaryDirectory() as td:
        rp = os.path.join(td, 'miniport.bin')
        with open(rp, 'wb') as fh:
            fh.write(_mini_port_rom())
        emu = ECUPinEmu(rom_path=rp)
        emu.step(10)
        check(emu.port_output[0] == 0xF,
              "port/2: port0 latch=0x%X (want 0xF)" % emu.port_output[0])
        check(emu.pins["COIL1"] == 1 and emu.pins["COIL2"] == 1
              and emu.pins["COIL3"] == 1 and emu.pins["COIL4"] == 1,
              "port/2: COIL1-4=%d%d%d%d (want 1111)"
              % (emu.pins["COIL1"], emu.pins["COIL2"],
                 emu.pins["COIL3"], emu.pins["COIL4"]))
        # Write-through: the firmware byte is visible in _ram and seeds the
        # next slice's MMIO (no stale-latch fallback).
        check(emu._ram.get(0xFFFFF720) == 0xF,
              "port/2: _ram[PORT0]=0x%X (want 0xF)"
              % (emu._ram.get(0xFFFFF720, -1)))
        mm = emu._build_full_mmio()
        check(mm[PORT_BASE] == 0xF,
              "port/2: full-mmio PORT0=0x%X (want 0xF from _ram)"
              % mm[PORT_BASE])


# ---------------------------------------------------------------------------
# MEDIUM-3. fdiv by zero -> +-Inf / NaN, no ZeroDivisionError
# ---------------------------------------------------------------------------
def test_fdiv_by_zero():
    vectors = [
        (1.0, 0.0, 'inf'),
        (-1.0, 0.0, '-inf'),
        (0.0, 0.0, 'nan'),
        (float('nan'), 0.0, 'nan'),
        (1.0, -0.0, '-inf'),
        (1.0, 2.0, '0.5'),       # normal path unchanged
    ]
    for a, b, exp in vectors:
        try:
            cpu = SH2(_prog([0xF433, 0x0009]))   # fdiv FR3,FR4
            cpu.call(0, fr={4: a, 3: b}, break_addrs={0x2})
            got = cpu.fr[4]
        except ZeroDivisionError:
            check(False, "fdiv/3: %r/%r raised ZeroDivisionError" % (a, b))
            continue
        if exp == 'nan':
            ok = isinstance(got, float) and math.isnan(got)
        else:
            ok = repr(got) == exp
        check(ok, "fdiv/3: %r/%r -> %r (want %s)" % (a, b, got, exp))


# ---------------------------------------------------------------------------
# MEDIUM-4. _emu_executes is honest about crashing opcodes
# ---------------------------------------------------------------------------
def test_emu_executes_honest():
    import gen_c_lift_v3 as v3
    import sh2emu

    v3._EMU_CACHE.clear()
    # Coupling note: 0xF003 is fdiv FR0,FR0 on a zeroed fr (0.0/0.0). While
    # the MEDIUM-3 bug lived this probe raised ZeroDivisionError and the old
    # `except Exception -> True` mislabeled it implemented; with the fdiv
    # fix it executes cleanly -> True.
    check(v3._emu_executes(bytes(0x100), 0xF003) is True,
          "emu/4: fdiv zeroed-state executes -> True (post-M3 coupling)")
    check(v3._emu_executes(bytes(0x100), 0x0009) is True,
          "emu/4: nop executes -> True")
    check(v3._emu_executes(bytes(0x101), 0x0000) is False,
          "emu/4: unknown opcode -> False")
    check(v3._emu_executes(bytes(0x102), 0xC300) is False,
          "emu/4: trapa (NotImplementedError) -> False")

    # Any non-NotImplemented crash on valid input -> False (never True).
    orig = sh2emu.SH2._exec

    def _boom(self, op, pc):
        raise RuntimeError("probe crash")

    sh2emu.SH2._exec = _boom
    try:
        v3._EMU_CACHE.clear()
        check(v3._emu_executes(bytes(0x103), 0x0009) is False,
              "emu/4: crashing handler -> False")
    finally:
        sh2emu.SH2._exec = orig
        v3._EMU_CACHE.clear()


# ---------------------------------------------------------------------------
# MEDIUM-9. SH2.call fr/regs input validation
# ---------------------------------------------------------------------------
def test_call_validation():
    rom = _prog([0x0009, 0x0009])

    def fresh(**kw):
        cpu = SH2(rom)
        cpu.call(0, break_addrs={0x2}, **kw)
        return cpu

    # fr: out-of-range int keys raise (no IndexError / silent aliasing).
    for key in (16, -1):
        try:
            fresh(fr={key: 1.0})
            check(False, "call/9: fr={%r} silently accepted" % (key,))
        except ValueError:
            check(True, "call/9: fr={%r} -> ValueError" % (key,))
        except Exception as e:
            check(False, "call/9: fr={%r} -> %s (want ValueError)"
                  % (key, type(e).__name__))

    # regs int indices: 16 / -1 raise (no IndexError / r[15] wrap).
    for key in (16, -1):
        try:
            fresh(regs={key: 1})
            check(False, "call/9: regs={%r} silently accepted" % (key,))
        except ValueError:
            check(True, "call/9: regs={%r} -> ValueError" % (key,))
        except Exception as e:
            check(False, "call/9: regs={%r} -> %s (want ValueError)"
                  % (key, type(e).__name__))

    # Case-insensitive rN + sp alias are applied (never silently ignored).
    check(fresh(regs={"R4": 123}).r[4] == 123,
          "call/9: regs R4 applied to r4")
    check(fresh(regs={"r4": 123}).r[4] == 123,
          "call/9: regs r4 still works")
    check(fresh(regs={"sp": 0x1000}).r[15] == 0x1000,
          "call/9: regs sp alias applied to r15")

    # Unknown string keys raise (never silently ignored).
    for key in ("t", "xyz", ""):
        try:
            fresh(regs={key: 1})
            check(False, "call/9: regs={%r} silently ignored" % (key,))
        except ValueError:
            check(True, "call/9: regs={%r} -> ValueError" % (key,))
        except Exception as e:
            check(False, "call/9: regs={%r} -> %s (want ValueError)"
                  % (key, type(e).__name__))


def main():
    test_sr_tqm_mirror()
    test_port_writes_reach_pins()
    test_fdiv_by_zero()
    test_emu_executes_honest()
    test_call_validation()
    print('-' * 70)
    print('wave3: %d checks, %d failures' % (CHECKS[0], len(FAILS)))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
