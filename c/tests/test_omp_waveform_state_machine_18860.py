#!/usr/bin/env python3
"""
Verify 0x18860 (omp_waveform_state_machine_18860) against the ACTUAL ROM bytes,
run in the SH-2E emulator (tools/sh2emu.py).

4-state machine on RAM8[0xFFFFA981] driving the OMP stepper:
  - mode == 0      -> A981 = 0, A982 = 0
  - A981 == 1      -> if A968 == 1: gate on ADDRESS_VAL port bytes 8078/807C,
                      compare f32 AA10 against ROM 0x78E68 (-40.0);
                      A97E = cal byte, A977/A978 latch the branch, A981 -> 2
  - A981 == 0      -> step drive: A97C==5 -> A97B=0x80,A981=1;
                      A97C==4 -> A97B=0x30, wave(0), A974<60 -> A97F=A974+1;
                      else    -> A97B=0x10, wave(2)
  - A981 == 2      -> if A977==1 or A978==1:
                      even step -> A97B=0x30, wave(1); if A97C==5 (after wave)
                                   and A97E<=1: A982=1,A97F=0,A97E=0,
                                   A97B=sat8(A97B,0x30)
                      odd step  -> A97B=8, wave(1); A97E>0 -> A97E-=1

wave() = 0x18552 (verified separately); its effects (A97C/A97D/A97F/A98A/A98D/
F746) are folded in via test_omp_stepper_waveform_driver.model.

Run: python3 c/tests/test_omp_waveform_state_machine_18860.py [N]
"""
import os, sys, random, struct

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'c', 'tests'))

from sh2emu import SH2
from test_omp_stepper_waveform_driver import model as wave_model

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')

A981 = 0xFFFFA981
A982 = 0xFFFFA982
A97E = 0xFFFFA97E
A97B = 0xFFFFA97B
A97F = 0xFFFFA97F
A977 = 0xFFFFA977
A978 = 0xFFFFA978
A968 = 0xFFFFA968
A97C = 0xFFFFA97C
A97D = 0xFFFFA97D
A974 = 0xFFFFA974
A98A = 0xFFFFA98A
A98D = 0xFFFFA98D
A969 = 0xFFFFA969
A96A = 0xFFFFA96A
AA10 = 0xFFFFAA10
P8078 = 0xFFFF8078
P807C = 0xFFFF807C
F746 = 0xFFFFF746


def read_val8(ram, addr, default):
    """readValue_8bit_ADDRESS_VAL model (default 0 -> only val matters)."""
    b0 = ram.get(addr, 0)
    b1 = ram.get(addr + 1, 0)
    return b0 if b0 == ((~b1) & 0xFF) else default


def model(mode, st):
    """st: dict of RAM state (same keys as the emulator ram overlay, plus
    'temp' as a Python float).  Returns the full effect dict."""
    m = dict(st)
    mode &= 0xFF

    def B(a): return m.get(a, 0)
    def W(a, v): m[a & 0xFFFFFFFF] = v & 0xFF
    def W16(a, v):
        W(a, (v >> 8) & 0xFF); W(a + 1, v & 0xFF)

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

    if mode == 0:
        W(A981, 0); W(A982, 0)

    if B(A981) == 1:
        r9 = 0; r14 = 0
        if B(A968) == 1:
            if read_val8(m, P8078, 0) != 0:
                if read_val8(m, P807C, 0) == 1:
                    if m['temp'] < -40.0:
                        r14 = 1
                    else:
                        r9 = 1
                else:
                    r14 = 1
            else:
                r14 = 1
            W(A97E, 0x3C if r9 == 1 else 0x3C)   # cal B / cal A (both 0x3C)
        W(A977, r9)
        W(A978, r14)
        W(A981, 2)

    if B(A981) == 0:
        c = B(A97C)
        if c == 5:
            W(A97B, 0x80); W(A981, 1)
        elif c == 4:
            W(A97B, 0x30)
            do_wave(0)
            if B(A974) < 60:
                W(A97F, (B(A974) + 1) & 0xFF)
        else:
            W(A97B, 0x10)
            do_wave(2)

    if B(A981) == 2:
        if B(A977) == 1 or B(A978) == 1:
            if (B(A97C) & 1) == 0:
                W(A97B, 0x30)
                do_wave(1)
                if B(A97C) == 5 and B(A97E) <= 1:
                    W(A982, 1); W(A97F, 0); W(A97E, 0)
                    W(A97B, min((B(A97B) + 0x30) & 0xFF, 0xFF))
            else:
                W(A97B, 8)
                do_wave(1)
                if B(A97E) > 0:
                    W(A97E, (B(A97E) + 0xFF) & 0xFF)
    return m


def rand_temp():
    r = random.random()
    if r < 0.2:
        return random.choice([-40.0, -39.999, -50.0, 30.0, 0.0])
    return random.uniform(-100.0, 150.0)


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 60000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    fails = 0
    random.seed(0xC6AC)

    for _ in range(N):
        mode = random.randint(0, 255)
        # prefer interesting A981 states (0/1/2 persist across calls)
        a981 = random.choice([0, 0, 1, 1, 2, 2, 3])
        ram = {
            A981: a981, A982: random.randint(0, 1),
            A97E: random.randint(0, 255), A97B: random.randint(0, 255),
            A977: random.randint(0, 1), A978: random.randint(0, 1),
            A968: random.randint(0, 1),
            A97C: random.randint(0, 8), A97D: random.randint(0, 8),
            A974: random.randint(0, 255), A98A: random.randint(0, 255),
            A969: random.randint(0, 1), A96A: random.randint(0, 1),
            A97F: 0x5A, A98D: 0x11,
        }
        port = random.randint(0, 0xFFFF)
        ram[F746] = (port >> 8) & 0xFF
        ram[F746 + 1] = port & 0xFF
        # ADDRESS_VAL pairs: 50% complement-valid
        for base in (P8078, P807C):
            if random.random() < 0.5:
                v = random.randint(0, 255)
                ram[base] = v
                ram[base + 1] = (~v) & 0xFF
            else:
                ram[base] = random.randint(0, 255)
                ram[base + 1] = random.randint(0, 255)
        temp = rand_temp()
        ram[AA10] = struct.unpack('>I', struct.pack('>f', temp))[0] >> 24
        ram[AA10 + 1] = (struct.unpack('>I', struct.pack('>f', temp))[0] >> 16) & 0xFF
        ram[AA10 + 2] = (struct.unpack('>I', struct.pack('>f', temp))[0] >> 8) & 0xFF
        ram[AA10 + 3] = struct.unpack('>I', struct.pack('>f', temp))[0] & 0xFF

        st = dict(ram)
        st['temp'] = temp
        want = model(mode, st)

        cpu.call(0x18860, r4=mode, ram=ram, sr=0xF0)

        addrs = [A981, A982, A97E, A97B, A97F, A977, A978, A97C, A97D,
                 A974, A98A, A98D, F746, F746 + 1]
        for a in addrs:
            got = cpu.ram.get(a, 0)
            exp = want.get(a, 0)
            if got != exp:
                print("MISMATCH @0x%X mode=%d a981=%d temp=%g" % (a, mode, a981, temp))
                print("  addr 0x%X: got=0x%02X want=0x%02X" % (a, got, exp))
                print("  full ram got:", {hex(k): v for k, v in sorted(cpu.ram.items()) if k in addrs})
                print("  full ram want:", {hex(k): v for k, v in sorted(want.items()) if isinstance(k, int) and k in addrs})
                fails += 1
                break
        else:
            continue
        break

    if fails:
        print("\n%d FAILURE(S)" % fails)
        sys.exit(1)
    print("OK  0x18860 omp_waveform_state_machine_18860  (%d random inputs)" % N)
    print("\nAll omp_waveform_state_machine_18860 tests passed.")
    sys.exit(0)


if __name__ == '__main__':
    main()
