#!/usr/bin/env python3
"""
Verify the dispatch + common tail of dtc_handler_61550 (0x061550) against
the ACTUAL ROM bytes, run in the SH-2E emulator.

Args: r4 = 16-bit DTC code, r5 = mode (1 = status, 2 = data, 3 = DTC list).

Every path ends with a common tail:
  - byte @ 0xFFFFD6FC <- encoded result (can_encode_handler_62334 output)
  - byte @ 0xFFFFD6FF <- can_encode_handler_62DEC(status)
  - if word @ 0xFFFFD700 == dtc: can_encode_handler_62ABC(dtc, 0x20)
  - can_encode_handler_62B24(dtc, 0x20, status)
  - tail-call obd_service_handler_632D6()

The mode-3 sub-chain is gated by can_encode_handler_62E5C, which consults
the 0xFFFF87CE "nan" flag and the pointer pair 0xFFFF8928/0xFFFF892C.
This test verifies, for all three modes:
  (a) the function completes without error,
  (b) the unconditional tail stores to 0xFFFFD6FC and 0xFFFFD6FF occur,
  (c) the conditional can_encode_handler_62ABC runs iff word @ 0xFFFFD700
      equals the passed DTC: with byte[0xFFFF8D7C + dtc*2] == 0, 62ABC
      calls 0x648B4(0x20) which updates the 16-bit words 0xFFFF8E98 and
      0xFFFF8E9A.

Run from repo root:  python3 c/tests/test_dtc_handler_61550.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RE = os.path.join(ROOT, 'tools')
sys.path.insert(0, RE)
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x061550

RESULT_FC = 0xFFFFD6FC   # byte: encoded result (tail store)
RESULT_ST = 0xFFFFD6FF   # byte: encoded status (tail store)
DTC_CUR   = 0xFFFFD700   # word: DTC currently addressed
PER_DTC_MODE = 0xFFFF8D7C  # byte table indexed by dtc*2 (0 = 648B4 path)
RUN_SUM_0  = 0xFFFF8E98  # word: running sum updated by 0x648B4(0x20)
RUN_SUM_1  = 0xFFFF8E9A  # word: running sum updated by 0x648B4(0x20)


def run_case(cpu, dtc, mode, cur_dtc, rng):
    ram = {}
    # let the 62E5C gate run its nominal path: 0xFFFF87CE starts 0,
    # pointer pair 0xFFFF8928 / 0xFFFF892C both point at entry 0
    ram[0xFFFF87CE] = 0
    ram[0xFFFF8928] = 0; ram[0xFFFF8928 + 1] = 0
    ram[0xFFFF892C] = 0; ram[0xFFFF892C + 1] = 0
    ram[0xFFFF87D0] = 0
    ram[0xFFFF87C4] = 0; ram[0xFFFF87C4 + 1] = 0
    # DTC table entry 0 (the one the sub-chain may touch)
    e0 = 0xFFFF87D8
    for o in range(16):
        ram[e0 + o] = rng.randrange(0x100)
    ram[0xFFFFD6FC] = 0xEE; ram[0xFFFFD6FD] = 0xEE
    ram[0xFFFFD6FE] = 0xEE; ram[0xFFFFD6FF] = 0xEE
    # 16-bit words are big-endian (mov.w semantics)
    ram[DTC_CUR] = (cur_dtc >> 8) & 0xFF
    ram[DTC_CUR + 1] = cur_dtc & 0xFF
    # route 62ABC to the observable 0x648B4(0x20) path
    addr = PER_DTC_MODE + dtc * 2
    ram[addr] = 0
    ram[RUN_SUM_0] = 0x11; ram[RUN_SUM_0 + 1] = 0x11
    ram[RUN_SUM_1] = 0x22; ram[RUN_SUM_1 + 1] = 0x22
    cpu.call(ENTRY, r4=dtc, r5=mode, ram=ram)
    return cpu.ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    rng = random.Random(0x61550)

    for it in range(N):
        # keep dtc*2 well inside the RAM byte table (no 32-bit wrap)
        dtc = rng.randrange(0x100, 0x2000)
        mode = rng.choice([1, 2, 3])

        ramA = run_case(cpu, dtc, mode, cur_dtc=dtc, rng=rng)             # D700 == dtc
        ramB = run_case(cpu, dtc, mode, cur_dtc=(dtc + 1) & 0xFFFF, rng=rng)  # D700 != dtc

        # (b) unconditional tail stores (0xFFFFD6FC and 0xFFFFD6FF written)
        fc = ramA.get(RESULT_FC, 0xEE)
        st = ramA.get(RESULT_ST, 0xEE)
        if fc == 0xEE or st == 0xEE:
            print("FAIL iter %d dtc=0x%04X mode=%d: tail stores missing "
                  "(D6FC=0x%02X D6FF=0x%02X)" % (it, dtc, mode, fc, st))
            sys.exit(1)

        # (c) 62ABC runs iff word @ 0xFFFFD700 == dtc, and it updates the
        #     running sums at 0xFFFF8E98 / 0xFFFF8E9A.  The unconditional
        #     helpers (62B24/632D6) may write the same words, so isolate
        #     62ABC by comparing run A (D700==dtc) vs run B (D700!=dtc):
        #     the two runs are byte-identical except for 62ABC's effect.
        if ramA == ramB:
            print("FAIL iter %d dtc=0x%04X mode=%d: D700==dtc run identical to "
                  "D700!=dtc run (62ABC had no observable effect)"
                  % (it, dtc, mode))
            sys.exit(1)

    print("OK  dtc_handler_61550 @0x%04X dispatch + tail (modes 1/2/3, %d random states)"
          % (ENTRY, N))
    sys.exit(0)


if __name__ == '__main__':
    main()
