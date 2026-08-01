#!/usr/bin/env python3
"""Smoke-test the SH-2E emulator against the 6 key DTC functions in 60E1D400.bin.

Unlike the old no-crash check, every entry is now run against a Python model of
its documented behaviour (the same models used by the dedicated per-function
tests in this directory) over a small number of randomized states.  Any
mismatch or emulator exception is a FAIL and the script exits 1.

Entries covered:
  dtcRelated                 0x062002  (model from test_dtcRelated)
  dtc_handler_610FA          0x0610FA  (dispatch semantics from test_dtc_handler_610FA)
  dtc_handler_61550          0x061550  (tail stores + 62ABC effect)
  dtc_code_set / dtc_code_clear 0x046780 / 0x0467AA  (model from test_dtc_code_set_clear)
  dtc_debounce_monitor_43760 0x043760  (model from test_dtc_debounce_monitor_43760)

Run from repo root:  python3 c/tests/smoke_dtc_functions.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
# the sibling per-function tests live in this same directory; we reuse their
# models/helpers so the smoke test can never drift from the dedicated tests.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sh2emu import SH2

import test_dtcRelated
import test_dtc_handler_610FA
import test_dtc_handler_61550
import test_dtc_code_set_clear
import test_dtc_debounce_monitor_43760

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')

FAIL = 0
CHECKS = [0]


def check(cond, msg):
    global FAIL
    CHECKS[0] += 1
    if not cond:
        FAIL += 1
        print("FAIL: " + msg)


def smoke_dtcRelated(cpu, rng, N):
    rom = cpu.rom
    types = [0x00, 0x60, 0x80, 0xC0, 0xC1, 0x50, 0xF0, 0x70, 0x01, 0xFF]
    enables = [0, 1, 2, 3]
    for it in range(N):
        ram, cur = test_dtcRelated.random_state(rng)
        dtype = rng.choice(types)
        enable = rng.choice(enables)
        try:
            got_cnt, got_out = test_dtcRelated.run(cpu, dict(ram), dtype, enable)
        except Exception as e:
            check(False, "dtcRelated iter %d type=0x%02X enable=%d: emulator raised %s: %s"
                  % (it, dtype, enable, type(e).__name__, e))
            continue
        exp_cnt, exp_out = test_dtcRelated.model(rom, ram, dtype, enable)
        check(got_cnt == exp_cnt and got_out == exp_out,
              "dtcRelated iter %d type=0x%02X enable=%d cur=%d: count/out mismatch (%d vs %d)"
              % (it, dtype, enable, cur, got_cnt, exp_cnt))


def smoke_dtc_handler_610FA(cpu, rng, N):
    E = test_dtc_handler_610FA
    for it in range(N):
        idx = rng.randrange(0, 21)
        opcode = rng.choice([0x00, 0x50, 0x01, 0x02, 0x03, 0xFF])
        ram = {E.DISP_FLAG: 0, E.SEL_WORD: 0, E.SEL_WORD + 1: 0}
        ram[E.CUR_IDX] = (idx >> 8) & 0xFF
        ram[E.CUR_IDX + 1] = idx & 0xFF
        for e in range(21):
            ram[E.OPCODES + e * 16] = rng.randrange(0x100)
        ram[E.OPCODES + idx * 16] = opcode
        marker = E.SVC_BASE + 0x34 * 0
        watch = [marker + 7, marker + 8, marker + 0x32]
        before = {a: ram.get(a, -1) for a in watch}
        try:
            cpu.call(E.ENTRY, ram=dict(ram))
        except Exception as e:
            check(False, "dtc_handler_610FA iter %d opcode=0x%02X idx=%d: emulator raised %s: %s"
                  % (it, opcode, idx, type(e).__name__, e))
            continue
        after = {a: cpu.ram.get(a, -1) for a in watch}
        if opcode in (0x00, 0x50):
            check(after[marker + 7] == 1 and after[marker + 8] == 7,
                  "dtc_handler_610FA iter %d opcode=0x%02X idx=%d: expected pending marker "
                  "(+7=1,+8=7) got (+7=0x%02X,+8=0x%02X)"
                  % (it, opcode, idx, after[marker + 7], after[marker + 8]))
            check(after[marker + 0x32] != before[marker + 0x32],
                  "dtc_handler_610FA iter %d opcode=0x%02X idx=%d: pending counter +0x32 unchanged"
                  % (it, opcode, idx))
        else:
            check(after == before,
                  "dtc_handler_610FA iter %d opcode=0x%02X idx=%d: no writes expected but bytes changed"
                  % (it, opcode, idx))


def smoke_dtc_handler_61550(cpu, rng, N):
    """Tail stores + 62ABC observable effect.

    Deterministic entry-0 fill (unlike the dedicated test, which re-randomizes
    entry 0 between the two runs) so a difference between the D700==dtc and
    D700!=dtc runs can only come from 62ABC's running-sum update.
    """
    E = test_dtc_handler_61550
    for it in range(N):
        dtc = rng.randrange(0x100, 0x2000)
        mode = rng.choice([1, 2, 3])

        def run_case(cur_dtc):
            ram = {}
            ram[0xFFFF87CE] = 0
            ram[0xFFFF8928] = 0; ram[0xFFFF8928 + 1] = 0
            ram[0xFFFF892C] = 0; ram[0xFFFF892C + 1] = 0
            ram[0xFFFF87D0] = 0
            ram[0xFFFF87C4] = 0; ram[0xFFFF87C4 + 1] = 0
            e0 = 0xFFFF87D8
            for o in range(16):
                ram[e0 + o] = 0xAA          # deterministic entry-0 fill
            ram[E.RESULT_FC] = 0xEE; ram[E.RESULT_FC + 1] = 0xEE
            ram[E.RESULT_ST] = 0xEE; ram[E.RESULT_ST + 1] = 0xEE
            ram[E.DTC_CUR] = (cur_dtc >> 8) & 0xFF
            ram[E.DTC_CUR + 1] = cur_dtc & 0xFF
            addr = E.PER_DTC_MODE + dtc * 2
            ram[addr] = 0
            ram[E.RUN_SUM_0] = 0x11; ram[E.RUN_SUM_0 + 1] = 0x11
            ram[E.RUN_SUM_1] = 0x22; ram[E.RUN_SUM_1 + 1] = 0x22
            cpu.call(E.ENTRY, r4=dtc, r5=mode, ram=ram)
            return dict(cpu.ram)

        try:
            ramA = run_case(cur_dtc=dtc)
            ramB = run_case(cur_dtc=(dtc + 1) & 0xFFFF)
        except Exception as ex:
            check(False, "dtc_handler_61550 iter %d dtc=0x%04X mode=%d: emulator raised %s: %s"
                  % (it, dtc, mode, type(ex).__name__, ex))
            continue
        fc = ramA.get(E.RESULT_FC, 0xEE)
        st = ramA.get(E.RESULT_ST, 0xEE)
        check(fc != 0xEE and st != 0xEE,
              "dtc_handler_61550 iter %d dtc=0x%04X mode=%d: tail stores missing (D6FC=0x%02X D6FF=0x%02X)"
              % (it, dtc, mode, fc, st))
        check(ramA != ramB,
              "dtc_handler_61550 iter %d dtc=0x%04X mode=%d: D700==dtc run identical to "
              "D700!=dtc run (62ABC had no observable effect)" % (it, dtc, mode))


def smoke_dtc_code_set_clear(cpu, rng, N):
    E = test_dtc_code_set_clear
    for it in range(N):
        ram = E.random_state(rng)
        for entry, do_gate, label in ((0x046780, True, 'dtc_code_set'),
                                      (0x0467AA, False, 'dtc_code_clear')):
            try:
                cpu.call(entry, ram=dict(ram))
            except Exception as e:
                check(False, "%s iter %d: emulator raised %s: %s"
                      % (label, it, type(e).__name__, e))
                continue
            exp = E.model(ram, do_gate)
            for a in E.WRITES:
                got = cpu.ram.get(a, -1)
                check(got == exp[a], "%s iter %d @0x%04X: got 0x%02X expected 0x%02X"
                      % (label, it, a, got, exp[a]))


def smoke_dtc_debounce_monitor_43760(cpu, rng, N):
    E = test_dtc_debounce_monitor_43760
    for it in range(N):
        ram = E.random_state(rng)
        try:
            cpu.call(E.ENTRY, ram=dict(ram))
        except Exception as e:
            check(False, "dtc_debounce_monitor_43760 iter %d: emulator raised %s: %s"
                  % (it, type(e).__name__, e))
            continue
        exp = E.model(cpu.rom, ram)
        for a in E.WATCH:
            got = cpu.ram.get(a, -1)
            check(got == exp[a], "dtc_debounce_monitor_43760 iter %d @0x%04X: got 0x%02X expected 0x%02X"
                  % (it, a, got, exp[a]))


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    if not os.path.exists(ROM):
        print("FAIL: ROM not found: %s" % ROM)
        sys.exit(1)
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    rng = random.Random(0xD7C5)
    print("smoke_dtc_functions: 6 DTC entries x %d random states" % N)
    smoke_dtcRelated(cpu, rng, N)
    smoke_dtc_handler_610FA(cpu, rng, N)
    smoke_dtc_handler_61550(cpu, rng, N)
    smoke_dtc_code_set_clear(cpu, rng, N)
    smoke_dtc_debounce_monitor_43760(cpu, rng, N)
    print("%d checks, %d failures" % (CHECKS[0], FAIL))
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == '__main__':
    main()
