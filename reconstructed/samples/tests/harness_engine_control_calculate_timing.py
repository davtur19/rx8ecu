#!/usr/bin/env python3
"""
harness_engine_control_calculate_timing.py — equivalence of
rx8_engine_control_calculate_timing @0x14584.

Reconstructed source: samples/src/rx8_engine_control_calculate_timing.c
Verified lift   : c/engineControlCalculateTiming.c (same address 0x14584,
                  414 bytes — the ROM bytes of the dispatcher AND of all 66
                  callees are executed for real here via tools/sh2emu.py).

The function is a zero-branch DISPATCHER: it has no RAM inputs, no branches
and no calibration pages of its own; its whole observable behaviour is the
interrupt-mask save/restore pair (getSR/setSR), the two stack cells it
manages and the exact 66-entry call sequence.  The equivalence check compares
exactly those, bit-for-bit:

  - emulator side: seed the initial SR, drive the ROM entry @0x14584 (every
    subsystem callee runs its REAL ROM bytes, incl. getSR @0x3920 / setSR
    @0x3934 / stack-save @0x14B04), then read back: final SR, r4 (the final
    setSR argument), r15, the saved-SR stack cell @0xFFFFDEF8, the saved-PR
    cell @0xFFFFDEFC, and the 68-entry dispatch call sequence (recorded by a
    Tracer subclass of SH2 that logs every jsr/jmp whose call site lies inside
    0x14584..0x14722);
  - host side: the oracle seeds its model SR, runs the reconstructed C (whose
    getSR/setSR model implements the ROM's mask semantics; the 63 subsystem
    callees are recording stubs) and prints the same five observables plus the
    identical 68-entry call sequence.

Vectors are initial SR values with (SR & 0xF0) >= 0x10 (the interrupt-mask
field non-zero): this is the regime where setSR takes the ROM's simple
`ldc r4,SR` path.  The r4 == 0 path would detour through the kernel routine
@0x3DB0 and overwrite the saved-PR stack cell, which the host model does not
reproduce (documented in the source header).  EDGE vectors sweep every IMASK
value 0x10..0xF0 against the other SR bits (T/S/MQ/flags, high words, sign);
N random full-32-bit SR values (fixed seed 0x60E1D400) follow.

Usage:  python3 harness_engine_control_calculate_timing.py [N]  (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2, MASK  # noqa: E402

ADDR = 0x14584
DISP_LO = 0x14584             # dispatcher code range (call-site filter)
DISP_HI = 0x14722
N_DEFAULT = 20000
SEED = 0x60E1D400
BUILD_DIR = '/tmp/rx8-recon-engine_control_calculate_timing'

# Dispatcher-owned stack cells (the only RAM the function itself touches).
SLOT_SR = 0xFFFFDEF8          # u32 saved-SR slot
SLOT_PR = 0xFFFFDEFC          # u32 saved return address (= 0xEEEE0000 SENT)
R15_END = 0xFFFFDF00
SENT = 0xEEEE0000

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Tracer(SH2):
    """SH2 + dispatch tracer: record every jsr/jmp target whose call site lies
    inside the dispatcher's own code range, so the emulator-side call sequence
    is exactly the 68 top-level dispatch calls (the subsystem callees live
    outside the range and their internal calls stay unrecorded)."""

    def __init__(self, rom):
        super().__init__(rom)
        self.trace = []

    def _delayed(self, op):
        n0 = op >> 12
        if n0 == 4:
            f = op & 0xF0FF
            if f == 0x400B or f == 0x402B:            # jsr @Rn / jmp @Rn
                m = (op >> 8) & 0xF
                target = self.r[m] & MASK
                if DISP_LO <= self.pc <= DISP_HI:
                    self.trace.append(target)
                if f == 0x400B:
                    self.pr = (self.pc + 4) & MASK
                return (target, True)
        return super()._delayed(op)


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into /tmp."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests',
                        'oracle_engine_control_calculate_timing.c'),
           os.path.join(SAMPLES, 'src',
                        'rx8_engine_control_calculate_timing.c'),
           '-lm',
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def run_emu(cpu, sr0):
    """Drive the ROM bytes @0x14584 with the given initial SR and return
    (final_sr, r4, slot_sr, slot_pr, r15, call_sequence)."""
    cpu.trace = []
    cpu.call(ADDR, ram={}, sr=sr0)
    return (cpu.sr & MASK,
            cpu.r[4] & MASK,
            cpu.rd(SLOT_SR, 4),
            cpu.rd(SLOT_PR, 4),
            cpu.r[15] & MASK,
            list(cpu.trace))


def gen_edges():
    """EDGE vectors: initial SR values.  Every (SR & 0xF0) value 0x10..0xF0
    crossed with the other SR bits (T/S/MQ/flags, high words, sign bit), plus
    boundary/low-nibble specials — all with the mask field >= 0x10."""
    v = []
    masks = (0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80,
             0x90, 0xA0, 0xB0, 0xC0, 0xD0, 0xE0, 0xF0)
    others = (0x00000000, 0x00000001, 0x00000002, 0x00000004,
              0x00000008, 0x0000000F, 0x00000100, 0x00001000,
              0x0000FFFF, 0x7FFF0000, 0x80000000, 0xFFFF0000,
              0x7FFFFFFF)
    for m in masks:
        for o in others:
            v.append(m | o)
    v += [0x00000010, 0x000000F0, 0x0000001F, 0x000000FF, 0x000000F1,
          0x000001F0, 0x00000FF0, 0x0000F0F0, 0x0F000010, 0xFFFFFFFF,
          0x80000010, 0x7FFFFFF0, 0xFFFF0010, 0x000010F0, 0x0000F010]
    return v


def gen_random(rng, n):
    """n random full-32-bit SR values with bit 4 forced, so the interrupt-mask
    field is never zero (keeps setSR on the simple `ldc r4,SR` path)."""
    return [rng.getrandbits(32) | 0x10 for _ in range(n)]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = Tracer(load_cpu().rom)
    oracle = build_oracle()
    rng = make_rng(SEED)

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator: real ROM bytes for the dispatcher
    #     and every callee; observables + traced call sequence.
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host-C on the same pre-states (model SR + recording stubs).
    lines = ['ect %08X' % v for v in vectors]
    host = []
    for out in run_oracle(oracle, lines):
        parts = out.split()
        host.append((tuple(int(x, 16) for x in parts[:5]),
                     [int(x, 16) for x in parts[5:]]))

    # (c) compare the five observables and the full 68-entry call sequence.
    #     Oracle field order: (sr_final, set_arg, slot_sr, slot_pr, r15).
    #     Emulator field order: (sr_final, r4, slot_sr, slot_pr, r15).
    mismatches = []
    for i, (sr0, e, (h5, hseq)) in enumerate(zip(vectors, emu, host)):
        (e_sr, e_r4, e_sr_slot, e_pr_slot, e_r15, eseq) = e
        (h_sr, h_arg, h_sr_slot, h_pr_slot, h_r15) = h5
        if (e_sr, e_r4, e_sr_slot, e_pr_slot, e_r15) != h5 or eseq != hseq:
            mismatches.append(
                'vec#%d sr0=%08X ROM=(sr=%08X r4=%08X slot8=%08X '
                'slotC=%08X r15=%08X seq=%d) C=(sr=%08X set=%08X '
                'slot8=%08X slotC=%08X r15=%08X seq=%d)'
                % (i, sr0, e_sr, e_r4, e_sr_slot, e_pr_slot, e_r15,
                   len(eseq), h_sr, h_arg, h_sr_slot, h_pr_slot, h_r15,
                   len(hseq)))
            if len(mismatches) >= 5:
                break

    report('engineControlCalculateTiming', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
