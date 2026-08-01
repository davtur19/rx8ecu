#!/usr/bin/env python3
"""
harness_mod32_signed.py — equivalence of rx8_mod32_signed @0x4144.

Reconstructed source: samples/src/rx8_mod32_signed.c
Verified lift   : c/mod32_signed.c (the merged-symbol name for the range,
                  `engineSomethingConditonCheckAndSet?`, is a placeholder;
                  the code is the div0s/div1 signed-remainder counterpart of
                  div32_signed @0x3FE8).

Register convention — the ROM uses the SAME "broken" r0/r1 argument pair as
div32_signed (NOT the r4/r5 ABI the base SH2.call() seeds):
    r0 = divisor, r1 = dividend, result in r0.
The harness therefore runs the ROM through a tiny SH2 subclass that re-does
the call prologue with r0/r1 injected.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc) from tests/oracle_mod32_signed.c +
     samples/src/rx8_mod32_signed.c (this harness compiles ONLY those two),
  2. generate N random (seeded) input pairs + edge cases,
  3. run the ACTUAL ROM bytes @0x4144 in tools/sh2emu.py,
  4. run the host C on the same inputs,
  5. compare — 0 mismatches required.

The divide-by-zero path writes diag code 0x44E to 0xFFFF7304 on the
emulator; that side effect is pinned separately (the host oracle cannot
dereference the fixed address).

Usage:  python3 harness_mod32_signed.py [N]     (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2, MASK  # noqa: E402

ADDR = 0x4144
N_DEFAULT = 20000

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(SAMPLES))
ROM_PATH = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-mod32_signed')

# Edge cases mirroring c/tests/test_mod32_signed.c, plus the div-by-zero
# vector and the INT32_MIN extremes.  (divisor, dividend)
EDGE = [
    (0x00000001, 0x00000000),   # 0 % 1
    (0x00000001, 0x00000001),   # 1 % 1
    (0x00000002, 0x00000005),   # 5 % 2 = 1
    (0x00000005, 0x00000011),   # 17 % 5 = 2
    (0xFFFFFFFF, 0xFFFFFFFF),   # -1 % -1 = 0
    (0x00000001, 0xFFFFFFFF),   # -1 % 1 = 0
    (0xFFFFFFFF, 0x00000001),   # 1 % -1 = 0
    (0x00000003, 0x00000007),   # 7 % 3 = 1
    (0xFFFFFFFD, 0x00000007),   # 7 % -3 = 1  (trunc toward zero)
    (0x00000003, 0xFFFFFFF9),   # -7 % 3 = -1
    (0xFFFFFFFD, 0xFFFFFFF9),   # -7 % -3 = -1
    (0x7FFFFFFF, 0x00000064),   # 100 % INT32_MAX = 100
    (0x80000000, 0x00000064),   # 100 % INT32_MIN = 100
    (0x00000064, 0x00000000),   # 0 % 100
    (0xFFFFFF9C, 0x00000000),   # 0 % -100
    (0x00010000, 0x0001E240),   # 123456 % 65536 = 123456 % 65536
    (0x00000002, 0x80000000),   # INT32_MIN % 2 = 0
    (0xFFFFFFFE, 0x80000000),   # INT32_MIN % -2 = 0
    (0xFFFFFFFF, 0x80000000),   # INT32_MIN % -1 = 0 (ROM & gcc agree)
    (0x80000000, 0x80000000),   # INT32_MIN % INT32_MIN = 0
    (0x00000000, 0x00000064),   # div-by-zero -> 0
    (0x80000000, 0x7FFFFFFF),   # INT32_MAX % INT32_MIN = INT32_MAX
    (0x7FFFFFFF, 0x80000000),   # INT32_MIN % INT32_MAX = -1
    (0xABCDEF01, 0x12345678),
    (0xDEADBEEF, 0xCAFEBABE),
]


class SH2Mod(SH2):
    """SH-2E + the ROM's "broken" r0/r1 calling convention.

    div32_signed @0x3FE8 and mod32_signed @0x4144 read their arguments from
    r0 (divisor) and r1 (dividend) instead of the r4/r5 ABI that the base
    SH2.call() seeds, so the call prologue is re-done with r0/r1 injected.
    The hot loop is the same one used by c/tests/test_div32_signed.py.
    """

    def call(self, entry, r0=0, r1=0, ram=None, fr=None, sr=0x000000F0):
        self.ram = dict(ram or {})
        self.r = [0] * 16
        self.r[0] = r0 & MASK
        self.r[1] = r1 & MASK
        self.r[15] = 0xFFFFDF00
        self.fr = [0.0] * 16
        for k, v in (fr or {}).items():
            self.fr[k] = v
        self.pr = self.SENT
        self.T = 0
        self.macl = 0
        self.mach = 0
        self.gbr = 0
        self.sr = sr & MASK
        self.vbr = 0
        self.ssr = 0
        self.spc = 0
        self.fpul = 0
        self.fpscr = 0
        self._Q = 0
        self._M = 0
        self.pc = entry & MASK
        steps = 0
        while True:
            if self.pc == self.SENT:
                return self.r[0] & MASK
            steps += 1
            if steps > 500000:
                raise RuntimeError('runaway at 0x%X' % self.pc)
            op = self.rd(self.pc, 2)
            br = self._delayed(op)
            if br is None:
                self._exec(op, self.pc)
                self.pc = (self.pc + 2) & MASK
            else:
                target, take = br
                self._exec(self.rd(self.pc + 2, 2), self.pc + 2)
                self.pc = target if take else (self.pc + 4) & MASK


def build_oracle(cc='cc'):
    """Compile ONLY this sample's C against its own oracle into /tmp."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_mod32_signed.c'),
           os.path.join(SAMPLES, 'src', 'rx8_mod32_signed.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = SH2Mod(open(ROM_PATH, 'rb').read())
    oracle = build_oracle()
    rng = make_rng(0x4144)

    vectors = list(EDGE) + [(rng.getrandbits(32), rng.getrandbits(32))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator, (b) host-C on the same inputs.
    emu = [cpu.call(ADDR, r0=d, r1=v) for d, v in vectors]
    lines = ['mod %08X %08X' % (d, v) for d, v in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, ((d, v), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d r0=0x%08X r1=0x%08X ROM=0x%08X C=0x%08X'
                % (i, d, v, e, h))
            if len(mismatches) >= 5:
                break

    # Emulator-only pin: div-by-zero stores diag code 0x44E at 0xFFFF7304
    # (host oracle cannot dereference that fixed address).
    cpu.call(ADDR, r0=0, r1=0x64)
    diag = int.from_bytes(
        bytes(cpu.ram.get(0xFFFF7304 + i, 0) for i in range(4)), 'big')
    if diag != 0x44E:
        print('FAIL div-by-zero diag write @0xFFFF7304: 0x%04X (expected 0x44E)'
              % diag)
        sys.exit(1)

    report('mod32_signed', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
