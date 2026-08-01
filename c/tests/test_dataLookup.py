#!/usr/bin/env python3
"""
Verify c/2DLookup.c's dataLookup() against the ACTUAL ROM bytes of the axis-search leaf
@0x2624, run in the SH-2E emulator (tools/sh2emu.py). dataLookup is the 1-D axis-search helper
every 2DLookup.c / 3dLookup.c lookup calls via `bsr` — this test exercises it standalone
rather than only indirectly through its callers.

Non-ABI leaf convention (confirmed from asm, see 2DLookup.c's dataLookup header):
  in:  r0 = count, r1 = axis pointer, fr0 = x
  out: r0 = index i, fr0 = t
To feed that from Python we reuse `call_leaf`, a line-for-line copy of SH2.call()'s body
that accepts arbitrary initial registers (same technique as
c/tests/test_interp_leaves.py) — no edit to sh2emu.py needed (mount serves truncated
copies of just-edited files; see CRITICAL GOTCHA #1 in the task brief).

Real axis array: 60E0FC00.bin @0x67870 (the 16-point u16 table also used by
test_2DLookup_FP_16bit.py; breakpoints -40..110 step 10) — the axis pointer is fed straight
from real ROM (r1 points directly at ROM, no RAM staging needed: dataLookup only reads,
never writes, and issues no bsr/jsr of its own).

Run from repo root:  python3 c/tests/test_dataLookup.py [N]
"""
import os, sys, random, struct, math
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, MASK, ts, s32


class SH2E(SH2):
    """+ cmp/pz, cmp/pl, and call_leaf() — a copy of SH2.call()'s body that accepts
    arbitrary initial registers (r0-r15), needed for dataLookup's r0/r1/fr0 leaf-level
    calling convention (it is not entered via r4-r7)."""
    def _exec(self, op, pc):
        if op & 0xF0FF == 0x4011:  # cmp/pz
            self.T = 1 if s32(self.r[(op >> 8) & 0xF]) >= 0 else 0; return
        if op & 0xF0FF == 0x4015:  # cmp/pl
            self.T = 1 if s32(self.r[(op >> 8) & 0xF]) > 0 else 0; return
        return super()._exec(op, pc)

    def call_leaf(self, entry, regs=None, fr=None, ram=None):
        self.ram = dict(ram or {})
        self.r = [0] * 16
        for k, v in (regs or {}).items():
            self.r[k] = v & MASK
        self.r[15] = 0xFFFFDF00
        self.fr = [0.0] * 16
        for k, v in (fr or {}).items():
            self.fr[k] = ts(v)
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


ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
rom = open(ROM, 'rb').read()
cpu = SH2E(rom)


def u16(p): return int.from_bytes(rom[p:p + 2], 'big')
def u32(p): return int.from_bytes(rom[p:p + 4], 'big')
def f32(p): return struct.unpack('>f', rom[p:p + 4])[0]


DESC = 0x67870   # real Map1D descriptor (same one test_2DLookup_FP_16bit.py uses)
COUNT = u16(DESC)
AXP = u32(DESC + 4)
AXIS = [f32(AXP + i * 4) for i in range(COUNT)]


def ref(x):
    n = COUNT
    x = ts(x)
    if not (x < AXIS[n - 1]):
        return n - 1, ts(0.0)
    if x < AXIS[0]:
        return 0, ts(0.0)
    i = 0
    while i + 1 < n and not (AXIS[i] <= x < AXIS[i + 1]):
        i += 1
    t = ts(ts(x - AXIS[i]) / ts(AXIS[i + 1] - AXIS[i]))
    return i, t


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    fails = 0
    tested = 0
    xs = list(AXIS) + [a - 0.001 for a in AXIS] + [a + 0.001 for a in AXIS]
    xs += [-1000.0, 1000.0, AXIS[0], AXIS[-1], float('nan')]
    xs += [random.uniform(-60, 130) for _ in range(N)]
    for x in xs:
        cpu.call_leaf(0x2624, regs={0: COUNT, 1: AXP}, fr={0: x})
        got_i, got_t = cpu.r[0], cpu.fr[0]
        want_i, want_t = ref(x)
        tested += 1
        ok = (got_i == want_i and struct.pack('>f', got_t) == struct.pack('>f', want_t))
        if not ok:
            fails += 1
            if fails <= 8:
                print("MISMATCH x=%r got=(%d,%r) want=(%d,%r)" % (x, got_i, got_t, want_i, want_t))
    print("dataLookup  tested=%d fails=%d  %s" % (tested, fails, "OK" if not fails else "FAIL"))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
