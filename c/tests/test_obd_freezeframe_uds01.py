#!/usr/bin/env python3
"""
Verify two OBD service handlers against the ACTUAL ROM bytes, run in the
SH-2E emulator (tools/sh2emu.py):

  0x467D0  FreezeFrameHandler   (side-effect leaf, no args)
  0x66258  UDSMode01Handler     (r4 = byte count, r5 = request ptr)

FULL differential over a small RAM seed per call: the pure-Python model below
re-implements exactly which RAM cells each handler reads/writes, and we compare
the emulator's whole post-call ram dump (minus the stack region) to the model.

===================================================================
FreezeFrameHandler @0x467D0
===================================================================
Reachable control flow (the emission-DTC gate inside 0x6743C(0x69) always
returns 1 for this ROM configuration, so the early path is always taken):

  0x46858  word@0xFFFFCC44 = 0                                  (2 bytes)
  0x4685A  r = read_8bit_cal(0xFFFF875C, default 0)
             read_8bit_cal (0x3ED3C) returns byte@0xFFFF875C when it forms a
             valid complement pair with byte@0xFFFF875D
             (byte@875C == ~byte@875D), else returns r5 (=0) and sets a
             "recompute" flag byte@0xFFFFC6AC = 1 (via 0x3F050).
   if r == 1                    -> tail 0x60774(0x69, 1)
   elif byte@0xFFFFCC40 == 1    -> tail 0x60774(0x69, 2)
   else: no request queued.

The tail 0x60774(r4, r5) is a "write-if-changed" store to the DTC-status
area. Exact rule (verified against the ROM bytes, tail body @0x6085C,
leaf @0x60996, D4F3 store @0x60A76):

   0x609AA  r3 = byte@0xFFFFD467                  (previous value)
   0x609AE  cmp/eq r3, r5                          (T = prev D467 == r5)
   0x609B0  bt/s  0x60A78  -> if prev D467 == r5, jump over BOTH stores
   0x609B4  byte@0xFFFFD467 = r5                  (unconditional otherwise)
   0x60A72  r3 = word@0x7DAEA + 2*r4 (DTC table)  (DTC 0x69 -> 0x005F)
   0x60A76  byte@0xFFFFD494 + r3 = r4'            (-> 0xFFFFD4F3)

So: D467 is ALWAYS r5, and D4F3 = r5 ONLY when the previous D467 differed
from r5; when prev D467 == r5 the D4F3 store is skipped entirely and D4F3
is left untouched. (The r4' value is r5 for r5 in {1,2,4}; other r5 values
collapse to 0 at 0x609E8 and skip the store at 0x60A6C, so r5==0/3 never
write D4F3.) Verified: r5=2 with old D467==2 leaves D4F3 untouched;
old D467!=2 writes D4F3=2. The only D4F3 write site reachable from
0x467D0..0x6077x is 0x60A76.

Cells touched: 0xFFFFCC44/0xFFFFCC45 (=0), 0xFFFFC6AC (invalid pair only),
0xFFFFD467, 0xFFFFD4F3 (tail-call only).

===================================================================
UDSMode01Handler @0x66258
===================================================================
With the CAN RX/TX channel gated off (RAM8@0xFFFFDE2F == 0, the default in
this test), the whole send/queue machinery is inert except:

  - valid count (1..6):
      word@0xFFFFD852 = 1 + 5*count     (written @0x66294, then +5 per PID)
      the loop reads the "received PID" byte from the (empty) RX buffer, i.e.
      byte@stack = 0 -> PID 0 -> 0x670B4(1,0)=0 -> 0x67154(0)=0 -> 0x66372(0)
      increments word@0xFFFFD852 by +5 each iteration.
  - invalid count (0, or >= 7): word@0xFFFFD852 untouched (NRC path).
      r13 = 1 (count==0 or count>6) -> NRC sender 0x67166, channel still off.

Both paths eventually submit one request through 0x69792 -> 0x9668 -> the
OS-task dispatch (0x5F34), which increments byte@0xFFFFA18D once (capped at
0xFF by the task frame).

  Model:
    byte@0xFFFFA18D = min(byte@0xFFFFA18D + 1, 0xFF)          (always)
    if 1 <= count <= 6: word@0xFFFFD852 = (1 + 5*count) & 0xFFFF
    else:              word@0xFFFFD852 unchanged

Run from repo root:  python3 c/tests/test_obd_freezeframe_uds01.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')

FF_ENTRY = 0x00467D0
UDS_ENTRY = 0x0066258

# Stack region (grows down from 0xFFFFDF00); excluded from comparisons. The
# UDS NRC path lays its task/queue frames down to 0xFFFFDE34.
STACK_LO = 0xFFFFDE00
STACK_HI = 0xFFFFDF40

P875C = 0xFFFF875C   # complement-pair cell 0
P875D = 0xFFFF875D   # complement-pair cell 1
CC40  = 0xFFFFCC40   # freeze-frame request pending flag
C6AC  = 0xFFFFC6AC   # "recompute" flag set by invalid pair
CC44  = 0xFFFFCC44   # freeze-frame status word (low byte)
CC45  = 0xFFFFCC45
D467  = 0xFFFFD467   # DTC-status area written by the queue tail
D4F3  = 0xFFFFD4F3
D8    = 0xFFFFD852   # word@0xFFFFD852 (big-endian), the pair counter
A1    = 0xFFFFA18D   # task event byte, incremented once per call


def model_ff(b875c, b875d, bcc40, bc6ac, bd467, bd4f3):
    """Expected final RAM (the cells ever read/written) for FreezeFrameHandler."""
    out = {P875C: b875c & 0xFF, P875D: b875d & 0xFF, CC40: bcc40 & 0xFF,
           C6AC: bc6ac & 0xFF, D467: bd467 & 0xFF, D4F3: bd4f3 & 0xFF}
    out[CC44] = 0                     # word@0xFFFFCC44 = 0 (bytes CC44, CC45)
    out[CC45] = 0
    if (b875c & 0xFF) == ((~b875d) & 0xFF):   # byte@875C == ~byte@875D
        r = b875c & 0xFF                        # returns byte@875C, no C6AC write
    else:                                       # invalid pair -> 0x3F050
        out[C6AC] = 1
        r = 0
    if r == 1:
        out[D467] = 1
        if (bd467 & 0xFF) != 1:      # tail @0x609B0: D4F3 store skipped when prev D467 == r5
            out[D4F3] = 1
    elif (bcc40 & 0xFF) == 1:
        out[D467] = 2
        if (bd467 & 0xFF) != 2:      # tail @0x609B0: D4F3 store skipped when prev D467 == r5
            out[D4F3] = 2
    return out


def run_ff(cpu, b875c, b875d, bcc40, bc6ac, bd467, bd4f3):
    """Run FreezeFrameHandler; return the emulator's non-stack RAM dump."""
    r = {P875C: b875c & 0xFF, P875D: b875d & 0xFF, CC40: bcc40 & 0xFF,
         C6AC: bc6ac & 0xFF, D467: bd467 & 0xFF, D4F3: bd4f3 & 0xFF}
    cpu.call(FF_ENTRY, ram=r)
    return {a: v for a, v in cpu.ram.items()
            if not (STACK_LO <= a < STACK_HI)}


def model_uds(count, a18d_hi, d8_seed_hi, d8_seed_lo):
    """Expected final RAM for UDSMode01Handler (channel gated off)."""
    out = {A1: min((a18d_hi & 0xFF) + 1, 0xFF)}
    if 1 <= count <= 6:
        w = (1 + 5 * count) & 0xFFFF
        out[D8] = (w >> 8) & 0xFF
        out[D8 + 1] = w & 0xFF
    else:
        out[D8] = d8_seed_hi & 0xFF
        out[D8 + 1] = d8_seed_lo & 0xFF
    return out


def run_uds(cpu, count, a18d, d852):
    """Run UDSMode01Handler; return the emulator's non-stack RAM dump."""
    ram = {A1: a18d & 0xFF, D8: (d852 >> 8) & 0xFF, D8 + 1: d852 & 0xFF}
    cpu.call(UDS_ENTRY, r4=count, r5=0x40, ram=ram)
    return {a: v for a, v in cpu.ram.items()
            if not (STACK_LO <= a < STACK_HI)}


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    random.seed(0x141A01)
    cpu = SH2(open(ROM, 'rb').read())
    fails = {'0x467D0': 0, '0x66258': 0}

    def check(got, exp, tag):
        if got != exp:
            print("FAIL %s\n  got  %s\n  want %s" % (tag, got, exp))
            return 1
        return 0

    # ---- targeted FreezeFrame edges (branch + overwrite coverage) ----
    for (c, d, cc, c6, d467, d4f3) in [
        (0x00, 0x00, 0x00, 0x00, 0x00, 0x00),   # invalid pair -> C6AC=1, r=0, no tail
        (0x01, 0xFE, 0x00, 0x00, 0xAA, 0x55),   # valid r=1 -> tail(0x69,1) overwrite
        (0x00, 0xFF, 0x00, 0x00, 0x00, 0x00),   # valid r=0, CC40=0 -> none
        (0x00, 0xFF, 0x01, 0x00, 0x00, 0x00),   # valid r=0, CC40=1 -> tail(0x69,2)
        (0x02, 0xFD, 0x01, 0x00, 0x00, 0x00),   # valid r=2, CC40=1 -> tail(0x69,2)
        (0xFF, 0x00, 0x00, 0x00, 0x00, 0x00),   # valid r=0xFF !=1, CC40=0 -> none
        (0xFF, 0x00, 0x01, 0x00, 0x00, 0x00),   # valid r=0xFF, CC40=1 -> tail(0x69,2)
        (0x7F, 0x80, 0x01, 0xFF, 0x3F, 0x40),   # valid r=0x7F, CC40=1 -> tail(0x69,2)
        (0x5A, 0xA5, 0x00, 0x00, 0x11, 0x22),   # valid r=0x5A, CC40=0 -> none
    ]:
        got = run_ff(cpu, c, d, cc, c6, d467, d4f3)
        fails['0x467D0'] += check(got, model_ff(c, d, cc, c6, d467, d4f3),
                                  "ff(target:%02X/%02X/%02X)" % (c, d, cc))

    # ---- random FreezeFrame (both branches + tail coverage) ----
    for _ in range(N):
        c = random.randint(0, 255)
        if random.random() < 0.5:           # half valid complement pairs
            d = (0xFF - c) & 0xFF
        else:
            d = random.randint(0, 255)
        cc = random.choice([0, 0, 1])
        c6 = random.randint(0, 255)
        d467 = random.randint(0, 255)
        d4f3 = random.randint(0, 255)
        got = run_ff(cpu, c, d, cc, c6, d467, d4f3)
        fails['0x467D0'] += check(got, model_ff(c, d, cc, c6, d467, d4f3),
                                  "ff(%02X/%02X/%02X)" % (c, d, cc))

    # ---- targeted UDS edges (count boundaries + A18D cap + D852 overwrite) ----
    for count in (0, 1, 2, 6, 7, 8):
        for a18d in (0x00, 0x7F, 0x80, 0xFE, 0xFF):
            for d852 in (0x0000, 0xFFFF, 0x1234):
                got = run_uds(cpu, count, a18d, d852)
                fails['0x66258'] += check(got, model_uds(count, a18d, d852 >> 8, d852 & 0xFF),
                                          "uds(c=%d a=%02X w=%04X)" % (count, a18d, d852))

    # ---- random UDS ----
    for _ in range(N):
        count = random.choice([0, 1, 1, 1, 2, 3, 4, 5, 6, 7, 0x3FF])
        a18d = random.randint(0, 255)
        d852 = random.randint(0, 65535)
        got = run_uds(cpu, count, a18d, d852)
        fails['0x66258'] += check(got, model_uds(count, a18d, d852 >> 8, d852 & 0xFF),
                                  "uds(c=%d)" % count)

    for n in ('0x467D0 FreezeFrameHandler', '0x66258 UDSMode01Handler'):
        e = n.split()[0]
        print('  %-32s %s (%d)' % (n, "OK" if not fails[e] else "FAIL", fails[e]))
    sys.exit(1 if fails['0x467D0'] or fails['0x66258'] else 0)


if __name__ == '__main__':
    main()