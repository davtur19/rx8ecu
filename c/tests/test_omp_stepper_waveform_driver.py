#!/usr/bin/env python3
"""
Verify 0x18552 (omp_stepper_waveform_driver) against the ACTUAL ROM bytes, run
in the SH-2E emulator (tools/sh2emu.py).

The function advances the OMP stepper step register RAM8[0xFFFFA97C] per its
mode (r4), optionally writes the waveform byte RAM8[0xFFFFA97F], latches the
mode into RAM8[0xFFFFA98A]/[0xFFFFA98D], and drives the 4-phase pattern for the
new step onto RAM16[0xFFFFF746] (bits 0..3) using the 9-entry table copied from
ROM 0x4ED5C.  The port RMW runs through 0x4BBC and the SR-bracketing calls
(0x2054/0x2064) — all executed natively by the emulator; SR must be unchanged.

Inputs  (RAM): A97C step, A97D rotor-sync source, A974 rotor pos, A98A latched
               mode, A969/A96A gate flags, F746 drive port.
Outputs (RAM): A97C/A97D/A97F/A98A/A98D, F746.

Run: python3 c/tests/test_omp_stepper_waveform_driver.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')

A97C = 0xFFFFA97C
A97D = 0xFFFFA97D
A974 = 0xFFFFA974
A97F = 0xFFFFA97F
A98A = 0xFFFFA98A
A98D = 0xFFFFA98D
A969 = 0xFFFFA969
A96A = 0xFFFFA96A
F746 = 0xFFFFF746

# ROM 0x4ED5C, copied to the function's stack frame at entry
PATTERN = (
    (1, 0, 0, 1), (1, 0, 0, 0), (1, 1, 0, 0), (0, 1, 0, 0), (0, 1, 1, 0),
    (0, 0, 1, 0), (0, 0, 1, 1), (0, 0, 0, 1), (0, 0, 0, 0),
)
MASKS = (1, 2, 4, 8)


def model(mode, step, a97d, a974, a98a, a969, a96a, port):
    """Python model of 0x18552.  Returns (step, a97d, wf_ok, wf, a98a, port)."""
    wf_ok, wf = False, 0
    if mode == 0:
        step = (step + 1) & 7
        if (step & 1) == 0 and a974 < 60:
            wf_ok, wf = True, (a974 + 1) & 0xFF
    elif mode == 1:
        if step == 8:
            step = (a97d + 0xFF) & 7
        else:
            step = (step + 0xFF) & 7
            if a974 == 1 and a98a != 4 and (a969 == 1 or a96a == 1):
                wf_ok, wf = True, 0
        if (step & 1) == 0 and a98a != 4 and a974 > 0:
            wf_ok, wf = True, (0xFF + a974) & 0xFF
    elif mode == 2:
        if a98a == 4 or (step & 1) == 1:
            step = (a97d + 1) & 7 if step == 8 else (step + 1) & 7
        else:
            step = (step + 2) & 7
        if a974 < 60:
            wf_ok, wf = True, (a974 + 1) & 0xFF
    elif mode == 3:
        if a98a == 4 or (step & 1) == 1:
            if step == 8:
                step = (a97d + 0xFF) & 7
            else:
                step = (step + 0xFF) & 7
                if a974 == 1 and a98a != 4:
                    wf_ok, wf = True, 0
        else:
            step = (step + 0xFE) & 7
            if a974 > 0:
                wf_ok, wf = True, (0xFF + a974) & 0xFF
    elif mode == 4:
        if step == 8:
            step = a97d
        elif (step & 1) == 0:
            step = (step + 1) & 7
            a97d = step
        else:
            step = 8
    elif mode == 6:
        step = 8
    # tail: A98A = mode; A98D = mode (written at entry); A97F iff wf_ok;
    #       4-phase port drive from PATTERN[step]
    a98a_out = mode
    pat = PATTERN[step]
    for i in range(4):
        port = (port | MASKS[i]) if pat[i] == 1 else (port & ~MASKS[i])
    port &= 0xFFFF
    return step, a97d, wf_ok, wf, a98a_out, port


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 60000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    fails = 0
    modes = [0, 1, 2, 3, 4, 6, 5, 7, 8, 9, 0xFF]  # 6 real + default path

    for _ in range(N):
        mode = random.choice(modes)
        step = random.randint(0, 8)
        a97d = random.randint(0, 8)
        a974 = random.randint(0, 255)
        a98a = random.randint(0, 255)
        a969 = random.randint(0, 255)
        a96a = random.randint(0, 255)
        port = random.randint(0, 0xFFFF)
        ram = {
            A97C: step, A97D: a97d, A974: a974, A98A: a98a,
            A969: a969, A96A: a96a, A97F: 0x5A, A98D: 0x11,
            F746: (port >> 8) & 0xFF, F746 + 1: port & 0xFF,
        }
        cpu.call(0x18552, r4=mode, ram=ram, sr=0xF0)
        want = model(mode, step, a97d, a974, a98a, a969, a96a, port)

        got = (cpu.ram.get(A97C), cpu.ram.get(A97D), cpu.ram.get(A97F),
               cpu.ram.get(A98A), cpu.ram.get(A98D),
               (cpu.ram.get(F746, 0) << 8) | cpu.ram.get(F746 + 1, 0))
        want_t = (want[0], want[1], want[3] if want[2] else 0x5A, want[4],
                  mode, want[5])
        if got != want_t:
            print("MISMATCH mode=%d step=%d a97d=%d a974=%d a98a=%d a969=%d "
                  "a96a=%d port=0x%04X" % (mode, step, a97d, a974, a98a,
                                           a969, a96a, port))
            print("  got : A97C=%d A97D=%d A97F=%d A98A=%d A98D=%d port=0x%04X"
                  % got)
            print("  want: A97C=%d A97D=%d A97F=%d A98A=%d A98D=%d port=0x%04X"
                  % want_t)
            fails += 1
            break
    else:
        print("OK  0x18552 omp_stepper_waveform_driver  (%d random inputs, "
              "modes 0-6 + defaults)" % N)

    # ---- SR preservation (tail runs setSR_PARAM/0x2064 pairs) ----
    for sr in (0xF0, 0xE0, 0x80, 0x00):
        cpu.call(0x18552, r4=2, ram={A97C: 3, A97D: 0, A974: 0, A98A: 0,
                                     A97F: 0, A98D: 0, F746: 0, F746 + 1: 0},
                 sr=sr)
        if cpu.sr != sr:
            print("MISMATCH SR preservation sr-in=0x%X sr-out=0x%X" % (sr, cpu.sr))
            fails += 1
    print("OK  SR preserved across the port-drive SR bracket (0x2054/0x2064)")

    if fails:
        print("\n%d FAILURE(S)" % fails)
        sys.exit(1)
    print("\nAll omp_stepper_waveform_driver tests passed.")
    sys.exit(0)


if __name__ == '__main__':
    main()
