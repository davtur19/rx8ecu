#!/usr/bin/env python3
"""
harness_math_min_max_49ed0.py — equivalence of rx8_math_min_max_49ed0 @0x49ED0.

Reconstructed source: samples/src/rx8_math_min_max_49ed0.c
Verified lift   : c/math_min_max_49ED0.c

CALLING CONVENTION: the ROM routine is a NON-ABI "flag-setter" leaf.  It takes
NO register arguments — the input address is a literal (mov.w @(disp,PC), which
SIGN-EXTENDS, so 0xCD49/0xCD48/0xF76C become 0xFFFFCD49/0xFFFFCD48/0xFFFFF76C)
and the function reads a fixed 16-bit RAM word at 0xFFFFF76C, tests bit 0x100
and writes a 0/1 flag byte to BOTH 0xFFFFCD48 and 0xFFFFCD49, returning the
flag in r0.  The standard SH2.call(r4=, r5=) entry point is therefore
meaningless; a call_leaf() driver (line-for-line copy of SH2.call()'s body, as
in harness_div32_signed.py / harness_interpolate_u8_table.py) runs the ROM
bytes so the harness can seed the RAM overlay — including SENTINEL bytes at
the two output addresses, which proves the byte writes actually happen.

RAM SIDE EFFECTS: the function's footprint spans two pages (0xFFFFC000 holds
the output bytes, 0xFFFFF000 the input word).  The host oracle mmap()s both
with MAP_FIXED (same trick as tests/host_oracle.c) and mirrors the sentinel
writes, so the C side performs the same reads/writes as the emulated ROM and
the harness compares the return value AND both flag bytes byte-exactly.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (boundaries of bit 0x100: 0x0000, 0x00FF, 0x0100, 0x0101,
     0x01FF, 0x02FF; sign bit flips 0x8000/0x80FF; all-ones 0xFFFF; high-byte
     masks) + N random 16-bit words (default N = 20000),
  3. run the ROM bytes @0x49ED0 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare return + RAM bytes — 0 mismatches required.

Usage:  python3 harness_math_min_max_49ed0.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report, run_oracle  # noqa: E402
# common.py already put <repo>/tools on sys.path (its sh2emu import); fetch the
# leaf-driving pieces of the emulator API from the same module.
from sh2emu import SH2, MASK  # noqa: E402

ADDR = 0x49ED0
N_DEFAULT = 20000

IN_WORD = 0xFFFFF76C   # input  word (RAM, seeded big-endian)
OUT_A   = 0xFFFFCD48   # output flag byte A (RAM)
OUT_B   = 0xFFFFCD49   # output flag byte B (RAM)

# Sentinel bytes pre-filled at the two output addresses; never 0 or 1 so a
# missed (or wrong) write is always caught.
SENTINELS = (0xA5, 0x5A, 0x7F, 0xFE, 0x80, 0x3C)

# Edge words: bit-0x100 off/on boundaries, zero, max, sign flips, all-ones.
EDGE = [0x0000, 0x0001, 0x00FF, 0x0100, 0x0101, 0x01FF, 0x02FF,
        0x8000, 0x80FF, 0xFFFF, 0x7F00, 0xFEFF, 0xFF00, 0xFF01]

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-math_min_max_49ed0'


class SH2E(SH2):
    """SH2 + call_leaf(): inject arbitrary initial registers (r0-r15) and a RAM
    overlay, then run the ROM bytes to their rts (pr seeded with SENT).  Needed
    because math_min_max_49ED0 is entered with no register arguments at all —
    it reads its input straight from a fixed RAM address.  Line-for-line copy
    of SH2.call()'s body, as in c/tests/test_math_min_max_49ED0.py."""

    def call_leaf(self, entry, regs=None, ram=None):
        self.ram = dict(ram or {})
        self.r = [0] * 16
        for k, v in (regs or {}).items():
            self.r[k] = v & MASK
        self.r[15] = 0xFFFFDF00
        self.fr = [0.0] * 16
        self.pr = self.SENT; self.T = 0; self.macl = 0; self.mach = 0; self.gbr = 0
        self.fpul = 0; self.fpscr = 0
        self.pc = entry & MASK
        steps = 0
        while True:
            if self.pc == self.SENT:
                return self.r[0] & MASK
            steps += 1
            if steps > 500000:
                raise RuntimeError("runaway at 0x%X" % self.pc)
            op = self.rd(self.pc, 2)
            br = self._delayed(op)
            if br is None:
                self._exec(op, self.pc); self.pc = (self.pc + 2) & MASK
            else:
                target, take = br
                self._exec(self.rd(self.pc + 2, 2), self.pc + 2)
                self.pc = target if take else (self.pc + 4) & MASK


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a host binary.
    (common.build_oracle is not reusable: it hardcodes the sample .c list.)"""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_math_min_max_49ed0.c'),
           os.path.join(SAMPLES, 'src', 'rx8_math_min_max_49ed0.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def call_fn(cpu, word, out_a, out_b):
    """Run the ROM bytes with word@0xFFFFF76C (big-endian 16-bit) and sentinel
    bytes at the two output addresses; return (r0, byte@CD48, byte@CD49)."""
    ram = {
        IN_WORD:     (word >> 8) & 0xFF,   # hi byte (mov.w is big-endian)
        IN_WORD + 1: word & 0xFF,          # lo byte
        OUT_A:       out_a & 0xFF,
        OUT_B:       out_b & 0xFF,
    }
    r = cpu.call_leaf(ADDR, regs={}, ram=ram)
    return r, cpu.ram.get(OUT_A), cpu.ram.get(OUT_B)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2E(f.read())
    oracle = build_oracle()
    rng = make_rng(0x49ED0)

    vectors = [(w, 0xAA, 0x55) for w in EDGE]
    vectors += [(rng.getrandbits(16), rng.choice(SENTINELS), rng.choice(SENTINELS))
                for _ in range(n)]

    # (a) ROM behaviour via the emulator (RAM seeded: input word + sentinels),
    # (b) host C on the same inputs (sentinel bytes mirrored via the oracle).
    emu = [call_fn(cpu, w, a, b) for w, a, b in vectors]
    lines = ['flg %04X %02X %02X' % (w, a, b) for w, a, b in vectors]
    host = []
    for ln in run_oracle(oracle, lines):
        r, a, b = ln.split()
        host.append((int(r, 16), int(a, 16), int(b, 16)))

    # (c) compare return value + both RAM side-effect bytes.
    mismatches = []
    for k, ((w, a, b), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d word=0x%04X sent=(0x%02X,0x%02X) ROM=(0x%X,0x%02X,0x%02X) '
                'C=(0x%X,0x%02X,0x%02X)'
                % (k, w, a, b, e[0], e[1], e[2], h[0], h[1], h[2]))
            if len(mismatches) >= 5:
                break

    report('math_min_max_49ED0', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
