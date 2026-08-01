#!/usr/bin/env python3
"""
Verify 0x189EE (rotor_sync_position_detector) against the ACTUAL ROM bytes, run
in the SH-2E emulator (tools/sh2emu.py).

Two-stage state machine on RAM8[0xFFFFA98B]:

  Stage A (mode == 0 only): compare old position RAM8[A8F1] vs new position
  RAM8[A974]:  A8F1 > A974 -> A98B = 0;  A8F1 < A974 -> A98B = 1;
               A8F1 == A974 -> A98B = 2, r13 = 1.

  Stage B (state blocks, on current A98B; odd = (A97C & 1) from entry):
    state 0: A8F1 >= A974:  A8F1==A974 && !odd -> A98B=2, r13=1
             A8F1 <  A974:  !odd -> A98B=3
    state 1: A8F1 > A974:   !odd || A974==0 -> A98B=3
             A8F1 == A974:  !odd || A974==0: A974>=5 -> A98B=4
                                             else    -> A98B=2, r13=1
    state 2: A8F1 > A974 -> A98B=0;  A8F1 < A974 -> A98B=1
    state 3: A8F1 > A974 -> A98B=0;  A8F1 < A974 -> A98B=1;
             equal -> A98B=2, r13=1
    state 4: !odd: (A8F1+0xFE)>=A974 -> A98B=3;  A8F1<5 -> A98B=2, r13=1

  Stage C (tail, on final A98B; wave = 0x18552):
    state 0: wave(2), A97B = 0x10
    state 1: A974 >= 5 -> wave(3), A97B = 0x10
             else      -> wave(1), A97B = 8 (odd) else 0x30
    state 2: r13==1 && A974==0 -> A97D = A97C, A97B = 4  (no wave)
             else              -> wave(4), A97B = 4
    state 3: A97B = 0x30
    state 4: A974 >= 5 -> wave(3), A97B = 0x10
             else      -> wave(1), A97B = 8 (odd) else 0x30

Run: python3 c/tests/test_rotor_sync_position_detector.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'c', 'tests'))

from sh2emu import SH2
from test_omp_stepper_waveform_driver import model as wave_model

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')

A8F1 = 0xFFFFA8F1
A974 = 0xFFFFA974
A97C = 0xFFFFA97C
A97D = 0xFFFFA97D
A98B = 0xFFFFA98B
A97B = 0xFFFFA97B
A97F = 0xFFFFA97F
A98A = 0xFFFFA98A
A98D = 0xFFFFA98D
A969 = 0xFFFFA969
A96A = 0xFFFFA96A
F746 = 0xFFFFF746


def model(mode, ram):
    m = dict(ram)

    def B(a): return m.get(a, 0) & 0xFF
    def W(a, v): m[a & 0xFFFFFFFF] = v & 0xFF
    def W16(a, v): W(a, (v >> 8) & 0xFF); W(a + 1, v & 0xFF)

    def do_wave(wmode):
        step, a97d = B(A97C), B(A97D)
        a974 = B(A974); a98a = B(A98A); a969 = B(A969); a96a = B(A96A)
        port = (B(F746) << 8) | B(F746 + 1)
        nstep, na97d, wf_ok, wf, na98a, nport = wave_model(
            wmode, step, a97d, a974, a98a, a969, a96a, port)
        W(A97C, nstep); W(A97D, na97d); W(A98A, na98a); W(A98D, wmode)
        W16(F746, nport)
        if wf_ok:
            W(A97F, wf)

    mode &= 0xFF
    a8f1 = B(A8F1)
    a974 = B(A974)
    odd = B(A97C) & 1           # r12 / r8: 1 if A97C odd at entry
    r13 = 0
    state = B(A98B)

    # stage A (mode == 0)
    if mode == 0:
        if a8f1 > a974:
            state = 0
        elif a8f1 == a974:
            state = 2
            r13 = 1
        else:
            state = 1
        W(A98B, state)

    # stage B (state blocks)
    if state == 0:
        if a8f1 >= a974:
            if a8f1 == a974 and odd == 0:
                W(A98B, 2)
                r13 = 1
        else:
            if odd == 0:
                W(A98B, 3)
    elif state == 1:
        if a8f1 > a974:
            if odd == 0 or a974 == 0:
                W(A98B, 3)
        elif a8f1 == a974:
            if odd == 0 or a974 == 0:
                if a974 >= 5:
                    W(A98B, 4)
                else:
                    W(A98B, 2)
                    r13 = 1
    elif state == 2:
        if a8f1 > a974:
            W(A98B, 0)
        elif a8f1 < a974:
            W(A98B, 1)
    elif state == 3:
        if a8f1 > a974:
            W(A98B, 0)
        elif a8f1 < a974:
            W(A98B, 1)
        else:
            W(A98B, 2)
            r13 = 1
    elif state == 4:
        if odd == 0:
            if (a8f1 - 2) >= a974:      # add #0xFE sign-extends: A8F1 - 2
                W(A98B, 3)
            if a8f1 < 5:
                W(A98B, 2)
                r13 = 1

    # stage C (tail, on final state)
    state = B(A98B)
    a974 = B(A974)
    if state == 0:
        do_wave(2)
        W(A97B, 0x10)
    elif state == 1:
        if a974 >= 5:
            do_wave(3)
            W(A97B, 0x10)
        else:
            do_wave(1)
            W(A97B, 8 if odd else 0x30)
    elif state == 2:
        if r13 == 1 and a974 == 0:
            W(A97D, B(A97C))
        else:
            do_wave(4)
        W(A97B, 4)
    elif state == 3:
        W(A97B, 0x30)
    elif state == 4:
        if a974 >= 5:
            do_wave(3)
            W(A97B, 0x10)
        else:
            do_wave(1)
            W(A97B, 8 if odd else 0x30)
    return m


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 60000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    fails = 0
    random.seed(0x189EE)

    for _ in range(N):
        mode = random.choice([0, 0, 1, 1, 2, 3, 4, 5, 0xFF])
        ram = {
            A8F1: random.randint(0, 255),
            A974: random.randint(0, 255),
            A97C: random.randint(0, 8),
            A97D: random.randint(0, 8),
            A98B: random.choice([0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 6]),
            A97B: random.randint(0, 255),
            A97F: 0x5A, A98A: random.randint(0, 255),
            A969: random.randint(0, 1), A96A: random.randint(0, 1),
            A98D: 0x11,
        }
        port = random.randint(0, 0xFFFF)
        ram[F746] = (port >> 8) & 0xFF
        ram[F746 + 1] = port & 0xFF

        want = model(mode, ram)
        cpu.call(0x189EE, r4=mode, ram=ram, sr=0xF0)

        addrs = [A98B, A97B, A97C, A97D, A97F, A98A, A98D, F746, F746 + 1]
        for a in addrs:
            got = cpu.ram.get(a, 0)
            exp = want.get(a, 0)
            if got != exp:
                print("MISMATCH @0x%X mode=%d state_in=%d" % (a, mode, ram[A98B]))
                print("  addr 0x%X: got=0x%02X want=0x%02X" % (a, got, exp))
                print("  inputs: A8F1=%d A974=%d A97C=%d A97D=%d A97B=%d port=0x%04X"
                      % (ram[A8F1], ram[A974], ram[A97C], ram[A97D], ram[A97B], port))
                print("  full ram got :", {hex(k): v for k, v in sorted(cpu.ram.items()) if k in addrs})
                print("  full ram want:", {hex(k): v for k, v in sorted(want.items()) if isinstance(k, int) and k in addrs})
                fails += 1
                break
        else:
            continue
        break

    if fails:
        print("\n%d FAILURE(S)" % fails)
        sys.exit(1)
    print("OK  0x189EE rotor_sync_position_detector  (%d random inputs)" % N)
    print("\nAll rotor_sync_position_detector tests passed.")
    sys.exit(0)


if __name__ == '__main__':
    main()
