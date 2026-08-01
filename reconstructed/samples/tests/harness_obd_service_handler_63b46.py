#!/usr/bin/env python3
"""
harness_obd_service_handler_63b46.py — equivalence of
rx8_obd_service_handler_63b46 @0x63B46.

Reconstructed source: samples/src/rx8_obd_service_handler_63b46.c
Verified lift   : c/obd_service_handler_63B46.c  (OBD debounce-state writer
                  leaf, r4 = new sample value).

The ROM function is entered through the normal ABI path (argument in r4,
result returned in r0), so cpu.call(ADDR, r4=..., ram=...) drives it exactly.
But its observable behaviour is a RAM side effect: it addresses the DTC
context-table row selected by the "current DTC index" word @0xFFFF8928
(base 0xFFFF87D8, 16-byte stride) and folds r4 into the row's bytes at
+0x0D and +0x0E:

    idx = word@0xFFFF8928 & 0xFFFF
    p   = 0xFFFF87D8 + idx*16
    p[0x0E] = (s8(p[0x0E]) + s8(p[0x0D]) - r4) & 0xFF
    p[0x0D] = r4 & 0xFF
    r0 = r4

Equivalence is therefore judged on the return value AND the two side-effected
bytes: the emulator seeds/reads them in its big-endian sparse RAM overlay,
the host oracle mmap()s the 0xFFFF8000 page and seeds/reads the same numeric
values (same setup as host_oracle.c and the 632D6/63312 sibling harnesses).

The row index is restricted to the realistic table rows 0..0x14 (21 rows,
0xFFFF87D8..0xFFFF8928, per the lift) so the host row pointer stays inside
the mapped page; the >0x14 32-bit pointer-wrap semantics are pinned
emulator-only at the end (idx 0x7FFF/0x8000/0xFFFF, same precedent as
harness_idx_table.py).

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (r4 at 0/1/0x7F/0x80/0xFE/0xFF boundaries and sign flips
     around the 32-bit range, every sign-flip byte pre-state, idx 0/1/0x14)
     + N random (r4, idx, b0d, b0e) vectors,
  3. run the ROM bytes @0x63B46 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the return value + side-effected RAM bytes — 0 mismatches.

Usage:  python3 harness_obd_service_handler_63b46.py [N]  (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x63B46
N_DEFAULT = 20000

CTX_BASE = 0xFFFF87D8          # DTC context table base
CTX_STRIDE = 16
CUR_INDEX = 0xFFFF8928         # word: current DTC index being serviced
MAX_ROW = 0x14                 # realistic table rows 0..0x14 (21 * 16 bytes)

# This harness' own build dir (kept separate from the shared host_oracle build).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-obd_service_handler_63b46'

# Edge vectors.  r4 spans the 32-bit boundary values (0, 1, sign-flip points
# around 0x80/0xFF low bytes, plus full-word sign flips 0x7FFFFFFF/0x80000000
# and 0xFFFFFFFE/0xFFFFFFFF), b0d/b0e span the sign-extension-relevant byte
# edges (mov.b reads are SIGN-EXTENDED, so 0x80..0xFF contribute negatively),
# and idx spans the first/last realistic rows plus row 1.
R4_EDGE = [0x00000000, 0x00000001, 0x0000007F, 0x00000080, 0x000000FE,
           0x000000FF, 0x00000100, 0x00007FFF, 0x00008000, 0x7FFFFFFF,
           0x80000000, 0xFFFFFFFE, 0xFFFFFFFF]
BYTE_EDGE = [0x00, 0x01, 0x7F, 0x80, 0xFE, 0xFF]
IDX_EDGE = [0, 1, MAX_ROW]

EDGE = [(r4, idx, d, e)
        for r4 in R4_EDGE for idx in IDX_EDGE
        for d in BYTE_EDGE for e in BYTE_EDGE]


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_obd_service_handler_63b46.c
    + the reconstructed source)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests',
                        'oracle_obd_service_handler_63b46.c'),
           os.path.join(SAMPLES, 'src', 'rx8_obd_service_handler_63b46.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def s8(x):
    x &= 0xFF
    return x - 256 if x & 0x80 else x


def row_ram(r4, idx, b0d, b0e):
    """Sparse-RAM overlay seeding the row-selection word and the two row
    bytes exactly where the ROM reads them (big-endian word at CUR_INDEX).
    The row pointer is masked to 32 bits like the SH-2E's add r2,r5, so
    high idx values wrap to the same keys the emulator touches."""
    p = (CTX_BASE + (idx & 0xFFFF) * CTX_STRIDE) & 0xFFFFFFFF
    return {CUR_INDEX: (idx >> 8) & 0xFF, CUR_INDEX + 1: idx & 0xFF,
            p + 0x0D: b0d & 0xFF, p + 0x0E: b0e & 0xFF}


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x63B46)

    vectors = list(EDGE) + [(rng.getrandbits(32),
                             rng.randint(0, MAX_ROW),
                             rng.randint(0, 0xFF),
                             rng.randint(0, 0xFF)) for _ in range(n)]

    # (a) ROM behaviour via the emulator: seed the three RAM cells, call the
    # entry with r4, read back the return value + the two written bytes
    # (big-endian sparse RAM overlay == ROM byte layout).
    emu = []
    for r4, idx, b0d, b0e in vectors:
        ram = row_ram(r4, idx, b0d, b0e)
        p = (CTX_BASE + (idx & 0xFFFF) * CTX_STRIDE) & 0xFFFFFFFF
        ret = cpu.call(ADDR, r4=r4, ram=ram)
        emu.append('%08X %02X %02X'
                   % (ret, cpu.ram.get(p + 0x0D, 0) & 0xFF,
                      cpu.ram.get(p + 0x0E, 0) & 0xFF))

    # (b) host C on the same vectors (same numeric values, printed as
    # return + row bytes in ROM order).
    lines = ['obd %08X %02X %02X %02X' % (r4 & 0xFFFFFFFF, idx & 0xFFFF,
                                          b0d & 0xFF, b0e & 0xFF)
             for r4, idx, b0d, b0e in vectors]
    host = run_oracle(oracle, lines)

    # (c) compare the return value + side-effected RAM byte-for-byte.
    mismatches = []
    for i, ((r4, idx, b0d, b0e), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d r4=%08X idx=%02X (b0d,b0e)=(%02X,%02X) ROM=[%s] C=[%s]'
                % (i, r4, idx, b0d, b0e, e, h))
            if len(mismatches) >= 5:
                break

    report('obd_service_handler_63b46', ADDR, n, mismatches, edges=len(EDGE))

    # (d) emulator-only wrap pins: rows 0x7FFF/0x8000/0xFFFF wrap the row
    # pointer through 32-bit arithmetic below the host mmap floor; the
    # &0xFFFF masking + 16-byte stride semantics still hold (same precedent
    # as harness_idx_table.py).  Reference = the lift's own model.
    for idx in (0x7FFF, 0x8000, 0xFFFF):
        p = (CTX_BASE + (idx & 0xFFFF) * CTX_STRIDE) & 0xFFFFFFFF
        r4, b0d, b0e = 0x80000000, 0xFF, 0x80
        ret = cpu.call(ADDR, r4=r4, ram=row_ram(r4, idx, b0d, b0e))
        ne = (s8(b0e) + s8(b0d) - r4) & 0xFF
        got = (ret, cpu.ram.get(p + 0x0D, 0) & 0xFF,
               cpu.ram.get(p + 0x0E, 0) & 0xFF)
        if got != (r4, r4 & 0xFF, ne):
            print('FAIL obd_service_handler_63b46 wrap idx=%X addr=%08X '
                  'got=%s expected=(%08X,%02X,%02X)'
                  % (idx, p, got, r4, r4 & 0xFF, ne))
            sys.exit(1)
    print('    wrap pins idx=0x7FFF/0x8000/0xFFFF OK (emulator-only)')


if __name__ == '__main__':
    main()
