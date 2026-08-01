#!/usr/bin/env python3
"""
harness_crank_sensor_init.py — equivalence of rx8_crank_sensor_init @0x7C30.

Reconstructed source: samples/src/rx8_crank_sensor_init.c
Verified lift   : c/crankSensorInit.c (crankSensorInit @ 0x007C30, 36 bytes)

The function is a conditional RAM side effect: it forces two sensor control
registers (0xFFFF9FC9 = 0x00, 0xFFFF9FCA = 0xFF), and if the engine-running
flag byte at 0xFFFF9F96 == 1 it clears the flag and TAIL-CALLS the crank-mode
state machine at 0x0768C (`bra`, NOT `jsr`, with r4 = 0 in the delay slot);
otherwise it returns.  Equivalence therefore compares the RAM bytes after the
call plus the tail-call boundary (Track-A RAM pattern, cf.
harness_rev_limit_fuel_cut_init.py):

  - emulator side: seed the flag + both control registers + sentinel bytes in
    the sparse `ram` overlay, drive the ROM entry @0x7C30 with call_crank()
    (a copy of SH2.call()'s body that stops when the tail-call branch lands on
    0x0768C, so crank_mode_switch's own body never runs), then read the seven
    bytes back, the r4 argument at the boundary, and the branch marker;
  - host side: the oracle mmap()s the backing page (MAP_FIXED, same trick as
    host_oracle.c), seeds the same bytes, runs the reconstructed C (whose
    rx8_crank_mode_switch stub only records the call), reads the bytes + tail
    marker back.

The sentinels pin the store count and width: 0xFFFF9F95 / 0xFFFF9F97 /
0xFFFF9FC8 / 0xFFFF9FCB are never written, and only the flag byte itself is
cleared (not its neighbours) — the flag clear is `mov.b` (byte).

The tail-call argument is pinned in-harness: every flag==1 vector must hit the
0x0768C boundary with r4 == 0 (the ROM's delay-slot `mov r2,r4` reloads the
just-written zero).  The oracle mirrors that boundary as its tail marker.

Usage:  python3 harness_crank_sensor_init.py [N]  (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2, MASK  # noqa: E402

ADDR = 0x7C30
TAIL = 0x0768C                 # crank_mode_switch entry (tail-call target)
N_DEFAULT = 20000

# Flag byte plus the two control registers and the sentinels around them.
A_LO  = 0xFFFF9F95   # sentinel: left of the flag byte
A_FLAG = 0xFFFF9F96  # engine-running flag (u8)
A_HI  = 0xFFFF9F97   # sentinel: right of the flag byte
C_LO  = 0xFFFF9FC8   # sentinel: left of control reg A
A_CTRLA = 0xFFFF9FC9 # sensor control register A (u8)
A_CTRLB = 0xFFFF9FCA # sensor control register B (u8)
C_HI  = 0xFFFF9FCB   # sentinel: right of control reg B
ADDRS = (A_LO, A_FLAG, A_HI, C_LO, A_CTRLA, A_CTRLB, C_HI)

EDGE = [
    # (f95, f96, f97, c8, c9, ca, cb)  --  f96 = flag pre-state
    (0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00),  # flag off, all zero
    (0xFF, 0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF),  # flag off, all ones
    (0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00),  # flag on, all zero
    (0xFF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF),  # flag on, all ones
    (0x00, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00),  # flag == 2 -> no flag clear
    (0x00, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00),  # flag == 0xFF -> no-op path
    (0x55, 0x01, 0xAA, 0x55, 0xAA, 0x55, 0xAA),  # flag on, bit patterns
    (0xDE, 0x01, 0xAD, 0xBE, 0xEF, 0x00, 0xFF),  # flag on, sentinels non-zero
    (0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF),  # flag off, ctrl B stays 0xFF
    (0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01),  # flag on, all 0x01
    (0xA5, 0x01, 0x5A, 0xC3, 0x3C, 0x0F, 0xF0),  # flag on, arbitrary
    (0x7F, 0x00, 0x80, 0x01, 0xFE, 0x80, 0x7F),  # flag off, sign bits set
]


class SH2C(SH2):
    """SH2 + call_crank(): drive the ROM bytes @0x7C30 and stop at the
    tail-call boundary 0x0768C (the `bra` that hands control to
    crank_mode_switch).  Line-for-line copy of SH2.call()'s mixed
    ram/rom-fetch body (same trick as call_leaf in
    harness_interpolate_u8_table.py) with the extra boundary check; the
    function always touches the ram overlay, so the mixed loop is the one that
    matters.  Returns ('TAIL', r4) when the tail-call fires, ('RET', r0)
    when the rts path returns."""

    def call_crank(self, entry, ram=None):
        self.ram = dict(ram or {})
        self.r = [0] * 16
        self.r[15] = 0xFFFFDF00
        self.fr = [0.0] * 16
        self.pr = self.SENT
        self.T = 0
        self.macl = 0
        self.mach = 0
        self.gbr = 0
        self.sr = 0x000000F0
        self.vbr = 0
        self.ssr = 0
        self.spc = 0
        self.fpul = 0
        self.fpscr = 0
        self._Q = (self.sr >> 3) & 1
        self._M = (self.sr >> 2) & 1
        r = self.r
        ram = self.ram
        rom = self.rom
        romlen = self._romlen
        M = MASK
        delayed = self._delayed
        exec_op = self._exec
        pc = entry & M
        steps = 0
        while True:
            if pc == TAIL:
                self.pc = pc
                return ('TAIL', r[4] & M)
            if pc == self.SENT:
                self.pc = pc
                return ('RET', r[0] & M)
            steps += 1
            if steps > 500000:
                self.pc = pc
                raise RuntimeError('runaway at 0x%X' % pc)
            a = pc
            b = ram.get(a)
            if b is None:
                b = rom[a] if a < romlen else 0
            a1 = (a + 1) & M
            b1 = ram.get(a1)
            if b1 is None:
                b1 = rom[a1] if a1 < romlen else 0
            op = (b << 8) | b1
            self.pc = pc
            br = delayed(op)
            if br is None:
                exec_op(op, pc)
                pc = (self.pc + 2) & M
            else:
                target, take = br
                a = (pc + 2) & M
                b = ram.get(a)
                if b is None:
                    b = rom[a] if a < romlen else 0
                a1 = (a + 1) & M
                b1 = ram.get(a1)
                if b1 is None:
                    b1 = rom[a1] if a1 < romlen else 0
                exec_op((b << 8) | b1, a)
                pc = target if take else (self.pc + 4) & M


def build_oracle():
    """Compile the reconstructed source + its own oracle into /tmp
    (this harness compiles its OWN oracle, not common.build_oracle's shared
    bundle)."""
    samples = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = '/tmp/rx8-recon-crank_sensor_init'
    os.makedirs(out, exist_ok=True)
    oracle = os.path.join(out, 'oracle')
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(samples, 'include'),
           '-I', os.path.join(samples, 'src'),
           os.path.join(samples, 'tests', 'oracle_crank_sensor_init.c'),
           os.path.join(samples, 'src', 'rx8_crank_sensor_init.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = SH2C(load_cpu().rom)
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + [tuple(rng.randint(0, 255) for _ in range(7))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator: seed the flag + regs + sentinels,
    #     drive the actual ROM bytes @0x7C30, stop at the tail-call boundary,
    #     read the seven bytes back plus the boundary marker and r4.
    emu = []
    for v in vectors:
        ram = dict(zip(ADDRS, v))
        kind, extra = cpu.call_crank(ADDR, ram=ram)
        tail = 1 if kind == 'TAIL' else 0
        bytes_out = tuple(cpu.ram.get(a, 0) for a in ADDRS)
        emu.append((bytes_out, tail, extra))

    # (b) host-C on the same vectors (oracle mmap-seeds, calls the
    #     reconstructed C, prints the bytes + tail marker).
    lines = ['crank %02X %02X %02X %02X %02X %02X %02X' % v
             for v in vectors]
    host = []
    for out in run_oracle(oracle, lines):
        parts = out.split()
        host.append((tuple(int(x, 16) for x in parts[:7]), int(parts[7])))

    # (c) compare: seven RAM bytes bit-exactly AND the tail-call marker.
    #     Every TAIL vector must also carry r4 == 0 (the ROM's delay-slot
    #     `mov r2,r4`), pinned in-harness.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        (e_bytes, e_tail, e_r4) = e
        (h_bytes, h_tail) = h
        r4_ok = (e_r4 == 0) if e_tail else True
        if e_bytes != h_bytes or e_tail != h_tail or not r4_ok:
            mismatches.append(
                'vec#%d pre=(%02X,%02X,%02X,%02X,%02X,%02X,%02X) '
                'ROM=(%02X,%02X,%02X,%02X,%02X,%02X,%02X,tail=%d,r4=%d) '
                'C=(%02X,%02X,%02X,%02X,%02X,%02X,%02X,tail=%d)'
                % (i, v[0], v[1], v[2], v[3], v[4], v[5], v[6],
                   e_bytes[0], e_bytes[1], e_bytes[2], e_bytes[3],
                   e_bytes[4], e_bytes[5], e_bytes[6], e_tail, e_r4,
                   h_bytes[0], h_bytes[1], h_bytes[2], h_bytes[3],
                   h_bytes[4], h_bytes[5], h_bytes[6], h_tail))
            if len(mismatches) >= 5:
                break

    report('crankSensorInit', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
