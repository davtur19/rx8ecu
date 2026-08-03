#!/usr/bin/env python3
"""
test_security_statecheck.py — Verify the state_check1/state_check2 semantics of
the SecurityAccess handler @0x584A0 (ROM 60E1D400) that the C lift in
c/security_access.c encodes.

Resolves the (former) DRAFT at c/security_access.c:163: the old guess
"if state_check1() != 0 -> return NRC_GR (0x11)" is WRONG.  Confirmed against
the ROM:

  * state_check1 @0x56866 returns byte @0xFFFFD20B (SECURITY_STATE_1) — no
    comparison, no flag.  state_check2 @0x568E6 returns byte @0xFFFFD20C
    (SECURITY_STATE_2).
  * The handler calls both unconditionally at entry (0x584CC / 0x584D2); the
    state_check1 result is saved to [r15+8] by the delay-slot at 0x584D6 and
    becomes the FIRST argument (b0) of the key_validate() call at 0x58538;
    the state_check2 result is kept in r10 and becomes b1.
  * The handler NEVER emits NRC 0x11: the only NRC literals in
    0x584A0-0x58640 are {0x31, 0x12, 0x35, 0x22}.

This test runs the ACTUAL ROM bytes in tools/sh2emu.py (same pattern as
test_seed_gen_5699A.py).  Heavy sub-functions are stubbed; state_check1 and
state_check2 run for real.  It checks, over N randomized inputs plus directed
cases (state1 == 0 vs != 0, both RequestSeed and SendKey paths):

  1. state_check1/state_check2 return exactly byte @0xFFFFD20B / @0xFFFFD20C.
  2. the key_validate call receives b0 = state1, b1 = state2 (the C wiring).
  3. uds_error_response is never called with NRC 0x11 (NRC_GR).

Run from repo root:  python3 c/tests/test_security_statecheck.py [N]
"""
import os
import sys
import random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
HANDLER = 0x0584A0
STATE1_ADDR = 0xFFFFD20B   # SECURITY_STATE_1 — read by state_check1 @0x56866
STATE2_ADDR = 0xFFFFD20C   # SECURITY_STATE_2 — read by state_check2 @0x568E6

# NRCs that may legitimately be emitted by the handler (disasm 0x584A0-0x58640).
ALLOWED_NRC = {0x31, 0x12, 0x35, 0x22}


def build_rom():
    """Stock ROM with only the heavy sub-functions stubbed to `mov #0,r0; rts; nop`.
    state_check1 (0x56866) and state_check2 (0x568E6) are left REAL."""
    rom = bytearray(open(ROM, 'rb').read())
    zero = bytes([0xE0, 0x00, 0x00, 0x0B, 0x00, 0x09])   # mov #0,r0 ; rts ; nop
    for a in (0x688B4, 0x5864A, 0x42B0, 0x3920, 0x3934,
              0x5699A, 0x56928, 0x56AC0, 0x56ADA, 0x56720, 0x5698A,
              0x56892,                 # position_check -> 0 (keeps flow in RequestSeed)
              0x55362, 0x55386, 0x553AA):
        rom[a:a + 6] = zero
    # SID payload reader 0x68BC0: mov.b r1,@r5 ; mov #0,r0 ; rts ; nop
    rom[0x68BC0:0x68BC0 + 8] = bytes([0x25, 0x01, 0xE0, 0x00, 0x00, 0x0B, 0x00, 0x09])
    return bytes(rom)


_ROM = build_rom()  # patched stock ROM (built once at import)


class TraceSH2(SH2):
    """SH2 that records every call to uds_error_response (NRC) and to
    key_validate (b0,b1,b2) as (nrc,) / (b0,b1,b2) tuples."""
    def __init__(self, rom):
        super().__init__(rom)
        self.nrcs = []
        self.kv_calls = []
    def _delayed(self, op):
        if (op & 0xF0FF) == 0x400B:                      # jsr @Rn
            m = (op >> 8) & 0xF
            tgt = self.r[m] & 0xFFFFFFFF
            if tgt == 0x553AA:                           # uds_error_response(0x27, nrc)
                self.nrcs.append(self.r[5] & 0xFF)
            elif tgt == 0x56928:                         # key_validate(b0,b1,b2)
                self.kv_calls.append((self.r[4] & 0xFF, self.r[5] & 0xFF,
                                      self.r[6] & 0xFF))
        return super()._delayed(op)


def run(subfunc, state1, state2, payload):
    cpu = TraceSH2(_ROM)
    cpu.call(HANDLER, r4=0x2200, r5=subfunc, regs={1: payload},
             ram={STATE1_ADDR: state1, STATE2_ADDR: state2, 0xFFFFD3F0: 0x61})
    return cpu


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    random.seed(0x584A0)
    mismatches = 0

    # ---- directed cases: state1 == 0 vs != 0, both payload branches ----
    directed = [
        (0x01, 0x00, 0x00, 0x01, "state1=0,  RequestSeed"),      # old guard OFF
        (0x01, 0x01, 0x00, 0x01, "state1=1,  RequestSeed"),      # old guard ON
        (0x01, 0x04, 0x04, 0x01, "state1=4,  RequestSeed"),
        (0x01, 0xFF, 0xFF, 0x01, "state1=FF, RequestSeed"),
        (0x01, 0x00, 0x00, 0x02, "state1=0,  SendKey"),
        (0x01, 0x04, 0x00, 0x02, "state1=4,  SendKey"),
    ]
    for subfunc, st1, st2, payload, label in directed:
        # --- direct state_check1/state_check2 semantics (ROM 0x56866/0x568E6) ---
        c1 = SH2(_ROM).call(0x56866, ram={STATE1_ADDR: st1}) & 0xFF
        c2 = SH2(_ROM).call(0x568E6, ram={STATE2_ADDR: st2}) & 0xFF
        if c1 != st1:
            mismatches += 1
            print("FAIL state_check1", label, "want", st1, "got", c1)
        if c2 != st2:
            mismatches += 1
            print("FAIL state_check2", label, "want", st2, "got", c2)
        # --- handler: never NRC 0x11; key_validate b0/b1 == state1/state2 ---
        cpu = run(subfunc, st1, st2, payload)
        for nrc in cpu.nrcs:
            if nrc == 0x11:
                mismatches += 1
                print("FAIL NRC_GR emitted", label, "nrc=0x11")
            if nrc not in ALLOWED_NRC:
                mismatches += 1
                print("FAIL unexpected NRC", label, hex(nrc))
        for b0, b1, _b2 in cpu.kv_calls:
            if b0 != st1:
                mismatches += 1
                print("FAIL key_validate b0", label, "want st1", st1, "got", b0)
            if b1 != st2:
                mismatches += 1
                print("FAIL key_validate b1", label, "want st2", st2, "got", b1)

    # ---- randomized cases ----
    for i in range(n):
        subfunc = random.choice((0x01, 0x01, 0x02, 0x00))
        st1 = random.randint(0, 0xFF)
        st2 = random.randint(0, 0xFF)
        payload = random.choice((0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0xFF))
        cpu = run(subfunc, st1, st2, payload)
        for nrc in cpu.nrcs:
            if nrc == 0x11:
                mismatches += 1
                print("FAIL NRC_GR emitted", hex(subfunc), hex(st1), hex(st2),
                      hex(payload), "nrc=0x11")
                break
            if nrc not in ALLOWED_NRC:
                mismatches += 1
                print("FAIL unexpected NRC", hex(nrc), hex(subfunc), hex(st1))
                break
        for b0, b1, _b2 in cpu.kv_calls:
            if b0 != st1 or b1 != st2:
                mismatches += 1
                print("FAIL key_validate args", hex(subfunc), "want", hex(st1),
                      hex(st2), "got", hex(b0), hex(b1))
                break

    total = n + len(directed)
    print("OK  security_statecheck @0x%06X  cases=%d mismatches=%d"
          % (HANDLER, total, mismatches))
    sys.exit(1 if mismatches else 0)


if __name__ == '__main__':
    main()
