#!/usr/bin/env python3
"""
harness_mem_accessors.py — equivalence of the redundant-RAM accessor family
(reconstructed source samples/src/rx8_mem_accessors.c, 11 functions).

Reconstructed source: samples/src/rx8_mem_accessors.c
Verified lift   : c/mem_accessors.c with the ground-truth addresses of
                  c/verified_addrs.txt (line 3).

ROM: roms/stock/60E0FC00.bin — see the sample header "ROM IDENTIFICATION".
The addresses 0x3E0DC..0x3E38A hold the accessor bodies ONLY in 60E0FC00.bin
(the ROM c/mem_accessors.c and c/tests/test_mem_accessors.py were verified
against); in 60E1D400.bin the same family moved to 0x3ED3C+ / 0x3EE58 /
0x3EE68.  This harness therefore loads 60E0FC00.bin directly (common.load_cpu
hard-codes 60E1D400.bin) and executes the REAL ROM bytes of each accessor.

CALLING CONVENTIONS — all eleven are standard SH-2E ABI leaves, entered via
r4/r5 (and fr4 for the single float arg of readValue_float) and returning in
r0 / fr0, so plain cpu.call() is used for every address — no call_leaf driver
is needed (none of these is a non-ABI leaf).  The ROM returns the 8-bit and
16-bit reads SIGN-EXTENDED in r0; the lift returns uint8_t/uint16_t, so the
harness compares r0&0xFF / r0&0xFFFF against the lifted width (r32/fr0 are
compared in full).

The read/validate functions call getSR(0x3920)/setSR(0x3934) around
setMemInsideFUNCto1(0x3E3F0) / SetMemoryNotValid2(0x3E5A8); those four are
stubbed to `rts; nop` in the emulator RAM overlay exactly as in
c/tests/test_mem_accessors.py (they are orthogonal to the datum and are
omitted from the lift).  The cell image (8 bytes) is seeded at 0xFFFF9000;
the returned r0/fr0 AND the full resulting cell (including the checksum
"scrub" side-effect of validateAddressCopy_32bit/float) are compared
bit-exactly.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors + N random (seeded) vectors per accessor,
  3. run the ROM bytes in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare bit-exactly — 0 mismatches required.

Usage:  python3 harness_mem_accessors.py [N]   (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import make_rng, report, run_oracle  # noqa: E402
# common.py already put <repo>/tools on sys.path (its sh2emu import).
from sh2emu import SH2, MASK, bits2f, f2bits  # noqa: E402

# --- addresses of the family (60E0FC00.bin) --------------------------------
ADDR_R8 = 0x3E0DC   # readValue_8bit_ADDRESS_VAL
ADDR_R16 = 0x3E11C  # readValue_16bit_ADDRESS_VAL
ADDR_R32 = 0x3E15C  # readValue_32bit_ADDRESS_VAL
ADDR_RF = 0x3E1AA   # readValue_float_DEFAULTVAL_ADDRESS
ADDR_U8 = 0x3E1F8   # updateMemoryAtAddress_8bit_ADDR_VAL
ADDR_U16 = 0x3E208  # updateMemoryAtAddress_16bit_ADDR_VAL
ADDR_U32 = 0x3E218  # updateMemoryAtAddress_32bit_ADDR_VAL
ADDR_V8 = 0x3E29E   # validateAddressCopy_8bit_ADDRESS
ADDR_V16 = 0x3E2DA  # validateAddressCopy_16bit_ADDRESS
ADDR_V32 = 0x3E330  # validateAddressCopy_32bit_ADDRESS
ADDR_VF = 0x3E38A   # validateAddressCopy_float_ADDRESS

N_DEFAULT = 20000

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(SAMPLES))
ROM_FC = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-mem_accessors')
ORACLE = os.path.join(BUILD_DIR, 'oracle')

A = 0xFFFF9000           # cell base (sparse-RAM overlay, like c/tests)
# getSR / setSR / setMemInsideFUNCto1 / SetMemoryNotValid2 -> rts;nop
STUB_ADDRS = (0x3920, 0x3934, 0x3E3F0, 0x3E5A8)


def stub():
    s = {}
    for a in STUB_ADDRS:
        s[a] = 0x00
        s[a + 1] = 0x0B
        s[a + 2] = 0x00
        s[a + 3] = 0x09
    return s


def build_oracle():
    """Compile THIS sample + its own oracle (do NOT touch common.build_oracle)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_mem_accessors.c'),
           os.path.join(SAMPLES, 'src', 'rx8_mem_accessors.c'),
           '-lm', '-o', ORACLE]
    subprocess.run(cmd, check=True)
    return ORACLE


# ---- helpers ----------------------------------------------------------------
def cs32(val):
    """16-bit checksum ~(hi16(val) + lo16(val))."""
    return (~(((val >> 16) + (val & 0xFFFF)) & 0xFFFF)) & 0xFFFF


def cs_from_bytes(b):
    hi = (b[0] << 8) | b[1]
    lo = (b[2] << 8) | b[3]
    return (~((hi + lo) & 0xFFFF)) & 0xFFFF


def cell_bytes(b):
    return b + [0] * (8 - len(b))


def put_cell(ram, b):
    for i, v in enumerate(b[:8]):
        ram[(A + i) & MASK] = v & 0xFF


def get_cell(cpu):
    return [cpu.ram.get((A + i) & MASK, 0) for i in range(8)]


def checksum_pair(cs, rng):
    """(copy1, copy2): one of {valid1, valid2, invalid}."""
    mode = rng.choice(['valid1', 'valid2', 'invalid'])
    if mode == 'valid1':
        c1, c2 = cs, rng.getrandbits(16)
        if c2 == cs:
            c2 = (c2 + 1) & 0xFFFF
    elif mode == 'valid2':
        c1, c2 = rng.getrandbits(16), cs
        if c1 == cs:
            c1 = (c1 + 1) & 0xFFFF
    else:
        c1 = rng.getrandbits(16)
        if c1 == cs:
            c1 = (c1 + 1) & 0xFFFF
        c2 = rng.getrandbits(16)
        if c2 == cs:
            c2 = (c2 + 1) & 0xFFFF
    return c1, c2


# ---- edge vectors -----------------------------------------------------------
_BYTES = [0x00, 0x01, 0x02, 0x7F, 0x80, 0xFE, 0xFF]
_U16S = [0x0000, 0x0001, 0x7FFF, 0x8000, 0xFFFF, 0x1234, 0xABCD]
_U32S = [0x00000000, 0x00000001, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF,
         0x11223344, 0xDEADBEEF, 0xFFFF8000, 0x0000FFFF]
_FBITS = [0x00000000, 0x80000000, 0x3F800000, 0xBF800000, 0x40000000,
          0x7F800000, 0xFF800000, 0x7FC00000, 0x461C4000, 0x3DCCCCCD]
_DF8 = [0x00, 0x01, 0x7F, 0x80, 0xFF]
_DF16 = [0x0000, 0x0001, 0x8000, 0xFFFF, 0x5A5A]
_DF32 = [0x00000000, 0xFFFFFFFF, 0x5A5A5A5A, 0x80000000]
_DFF = [0x00000000, 0x3F800000, 0xBF800000, 0x7FC00000]

EDGE_U8 = [(v,) for v in _BYTES]
EDGE_U16 = [(v,) for v in _U16S]
EDGE_U32 = [(v,) for v in _U32S]

EDGE_R8 = [(v, comp, d) for v in _BYTES
           for comp in [~v & 0xFF, 0x00, 0xFF, (~v + 1) & 0xFF, (~v - 1) & 0xFF]
           for d in _DF8]
EDGE_R16 = [(v, comp, d) for v in _U16S
            for comp in [~v & 0xFFFF, 0x0000, 0xFFFF,
                         (~v + 1) & 0xFFFF, (~v - 1) & 0xFFFF]
            for d in _DF16]
EDGE_V8 = [(v, comp) for v in _BYTES
           for comp in [~v & 0xFF, 0x00, 0xFF, (~v + 1) & 0xFF, (~v - 1) & 0xFF]]
EDGE_V16 = [(v, comp) for v in _U16S
            for comp in [~v & 0xFFFF, 0x0000, 0xFFFF,
                         (~v + 1) & 0xFFFF, (~v - 1) & 0xFFFF]]


def _cell32(val, c1, c2):
    hi = (val >> 16) & 0xFFFF
    lo = val & 0xFFFF
    return [(hi >> 8) & 0xFF, hi & 0xFF, (lo >> 8) & 0xFF, lo & 0xFF,
            (c1 >> 8) & 0xFF, c1 & 0xFF, (c2 >> 8) & 0xFF, c2 & 0xFF]


# full cross-product for 32-bit/float edges: value x pair-mode x default
EDGE_R32 = [(val, cs32(val), c1, c2, d)
            for val in _U32S for (c1, c2) in [
                (cs32(val), 0x0000), (0x0000, cs32(val)),
                ((cs32(val) + 1) & 0xFFFF, (cs32(val) + 2) & 0xFFFF)]
            for d in _DF32]
EDGE_V32 = [(val, cs32(val), c1, c2)
            for val in _U32S for (c1, c2) in [
                (cs32(val), 0x0000), (0x0000, cs32(val)),
                ((cs32(val) + 1) & 0xFFFF, (cs32(val) + 2) & 0xFFFF)]]
EDGE_RF = [(bits, cs32(bits), c1, c2, d)
           for bits in _FBITS for (c1, c2) in [
               (cs32(bits), 0x0000), (0x0000, cs32(bits)),
               ((cs32(bits) + 1) & 0xFFFF, (cs32(bits) + 2) & 0xFFFF)]
           for d in _DFF]
EDGE_VF = [(bits, cs32(bits), c1, c2)
           for bits in _FBITS for (c1, c2) in [
               (cs32(bits), 0x0000), (0x0000, cs32(bits)),
               ((cs32(bits) + 1) & 0xFFFF, (cs32(bits) + 2) & 0xFFFF)]]


# ---- emulator driver --------------------------------------------------------
def run_emu(cpu, addr, cell, r5=None, fr4=None):
    """Execute ROM @addr with the 8-byte cell at 0xFFFF9000 and optional
    r5 (integer dflt) / fr4 (float dflt); return (ret, cell_after)."""
    ram = stub()
    put_cell(ram, cell)
    kwargs = {'r4': A, 'ram': ram}
    if r5 is not None:
        kwargs['r5'] = r5
    if fr4 is not None:
        kwargs['fr'] = {4: bits2f(fr4)}
    cpu.call(addr, **kwargs)
    if addr == ADDR_RF:
        ret = f2bits(cpu.fr[0])
    else:
        ret = cpu.r[0] & MASK
    return ret, get_cell(cpu)


# ---- oracle vector text -----------------------------------------------------
def to_lines(op, vectors):
    """Build stdin lines for the oracle: '<op> <16hex cell> <arg>'."""
    lines = []
    for vec in vectors:
        cell = vec[0]
        arg = vec[1]
        lines.append('%s %s %08X' % (op, bytes(cell[:8]).hex(), arg))
    return lines


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    with open(ROM_FC, 'rb') as f:
        cpu = SH2(f.read())
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    # (1) generate vectors:  (cell[8], arg) per accessor
    vecs = {}
    vecs['u8'] = [(cell_bytes([]), v) for (v,) in EDGE_U8] + \
                 [(cell_bytes([]), rng.getrandbits(8)) for _ in range(n)]
    vecs['u16'] = [(cell_bytes([]), v) for (v,) in EDGE_U16] + \
                  [(cell_bytes([]), rng.getrandbits(16)) for _ in range(n)]
    vecs['u32'] = [(cell_bytes([]), v) for (v,) in EDGE_U32] + \
                  [(cell_bytes([]), rng.getrandbits(32)) for _ in range(n)]

    # r8: cell = [value, comp, 0..]; arg = dflt
    vecs['r8'] = [(cell_bytes([v, c]), d) for (v, c, d) in EDGE_R8] + \
                 [(cell_bytes([v, c]), d) for _ in range(n)
                  for (v, c, d) in
                  [(rng.getrandbits(8),
                    rng.choice([(~rng.getrandbits(8)) & 0xFF,
                                rng.getrandbits(8)]),
                    rng.getrandbits(8))]]
    vecs['r16'] = [(cell_bytes([(v >> 8) & 0xFF, v & 0xFF,
                                (c >> 8) & 0xFF, c & 0xFF]), d)
                   for (v, c, d) in EDGE_R16] + \
                  [(cell_bytes([(v >> 8) & 0xFF, v & 0xFF,
                                (c >> 8) & 0xFF, c & 0xFF]), d)
                   for _ in range(n)
                   for (v, c, d) in
                   [(rng.getrandbits(16),
                     rng.choice([(~rng.getrandbits(16)) & 0xFFFF,
                                 rng.getrandbits(16)]),
                     rng.getrandbits(16))]]

    # r32 / rf: cell = value + pair; arg = dflt
    vecs['r32'] = [(_cell32(v, c1, c2), d) for (v, cs, c1, c2, d) in EDGE_R32] + \
                  [(cell := _cell32(rng.getrandbits(32), *checksum_pair(
                      cs32(rng.getrandbits(32)), rng)),
                    rng.getrandbits(32)) for _ in range(n)]
    vecs['rf'] = [(_cell32(b, c1, c2), d) for (b, cs, c1, c2, d) in EDGE_RF] + \
                 [(cell := _cell32(b, *checksum_pair(cs32(b), rng)), d)
                  for _ in range(n)
                  for (b, d) in [(f2bits(rng.uniform(-1e4, 1e4)),
                                  f2bits(rng.uniform(-1e4, 1e4)))]]

    # validate-only variants: cell = value+comp / value+pair; no arg
    vecs['v8'] = [(cell_bytes([v, c]), 0) for (v, c) in EDGE_V8] + \
                 [(cell_bytes([v, c]), 0) for _ in range(n)
                  for (v, c) in [(rng.getrandbits(8),
                                  rng.choice([(~rng.getrandbits(8)) & 0xFF,
                                              rng.getrandbits(8)]))]]
    vecs['v16'] = [(cell_bytes([(v >> 8) & 0xFF, v & 0xFF,
                                (c >> 8) & 0xFF, c & 0xFF]), 0)
                   for (v, c) in EDGE_V16] + \
                  [(cell_bytes([(v >> 8) & 0xFF, v & 0xFF,
                                (c >> 8) & 0xFF, c & 0xFF]), 0)
                   for _ in range(n)
                   for (v, c) in [(rng.getrandbits(16),
                                   rng.choice([(~rng.getrandbits(16)) & 0xFFFF,
                                               rng.getrandbits(16)]))]]
    vecs['v32'] = [(_cell32(v, c1, c2), 0) for (v, cs, c1, c2) in EDGE_V32] + \
                  [(cell := _cell32(rng.getrandbits(32), *checksum_pair(
                      cs32(rng.getrandbits(32)), rng)), 0) for _ in range(n)]
    vecs['vf'] = [(_cell32(b, c1, c2), 0) for (b, cs, c1, c2) in EDGE_VF] + \
                 [(cell := _cell32(f2bits(rng.uniform(-1e4, 1e4)),
                                   *checksum_pair(cs32(f2bits(
                                       rng.uniform(-1e4, 1e4))), rng)), 0)
                  for _ in range(n)]

    # (2) run the ROM bytes in the emulator, per accessor
    emu = {}
    emu['u8'] = [run_emu(cpu, ADDR_U8, cell, r5=arg) for cell, arg in vecs['u8']]
    emu['u16'] = [run_emu(cpu, ADDR_U16, cell, r5=arg) for cell, arg in vecs['u16']]
    emu['u32'] = [run_emu(cpu, ADDR_U32, cell, r5=arg) for cell, arg in vecs['u32']]
    emu['r8'] = [run_emu(cpu, ADDR_R8, cell, r5=arg) for cell, arg in vecs['r8']]
    emu['r16'] = [run_emu(cpu, ADDR_R16, cell, r5=arg) for cell, arg in vecs['r16']]
    emu['r32'] = [run_emu(cpu, ADDR_R32, cell, r5=arg) for cell, arg in vecs['r32']]
    emu['rf'] = [run_emu(cpu, ADDR_RF, cell, fr4=arg) for cell, arg in vecs['rf']]
    emu['v8'] = [run_emu(cpu, ADDR_V8, cell) for cell, arg in vecs['v8']]
    emu['v16'] = [run_emu(cpu, ADDR_V16, cell) for cell, arg in vecs['v16']]
    emu['v32'] = [run_emu(cpu, ADDR_V32, cell) for cell, arg in vecs['v32']]
    emu['vf'] = [run_emu(cpu, ADDR_VF, cell) for cell, arg in vecs['vf']]

    # (3) run the host C oracle on the same vectors
    host = {}
    for op in ('u8', 'u16', 'u32', 'r8', 'r16', 'r32', 'rf', 'v8', 'v16',
               'v32', 'vf'):
        host[op] = run_oracle(oracle, to_lines(op, vecs[op]))

    # (4) compare bit-exactly: ret (masked to the lifted width) + cell bytes
    masks = {'u8': 0xFFFFFFFF, 'u16': 0xFFFFFFFF, 'u32': 0xFFFFFFFF,
             'r8': 0xFF, 'r16': 0xFFFF, 'r32': 0xFFFFFFFF, 'rf': 0xFFFFFFFF,
             'v8': 0xFF, 'v16': 0xFF, 'v32': 0xFF, 'vf': 0xFF}
    names = {
        'u8': ('updateMemoryAtAddress_8bit', ADDR_U8, len(EDGE_U8)),
        'u16': ('updateMemoryAtAddress_16bit', ADDR_U16, len(EDGE_U16)),
        'u32': ('updateMemoryAtAddress_32bit_ADDR_VAL', ADDR_U32, len(EDGE_U32)),
        'r8': ('readValue_8bit_ADDRESS_VAL', ADDR_R8, len(EDGE_R8)),
        'r16': ('readValue_16bit_ADDRESS_VAL', ADDR_R16, len(EDGE_R16)),
        'r32': ('readValue_32bit_ADDRESS_VAL', ADDR_R32, len(EDGE_R32)),
        'rf': ('readValue_float_DEFAULTVAL_ADDRESS', ADDR_RF, len(EDGE_RF)),
        'v8': ('validateAddressCopy_8bit_ADDRESS', ADDR_V8, len(EDGE_V8)),
        'v16': ('validateAddressCopy_16bit_ADDRESS', ADDR_V16, len(EDGE_V16)),
        'v32': ('validateAddressCopy_32bit_ADDRESS', ADDR_V32, len(EDGE_V32)),
        'vf': ('validateAddressCopy_float_ADDRESS', ADDR_VF, len(EDGE_VF)),
    }

    for op, (name, addr, nedge) in names.items():
        mask = masks[op]
        mismatches = []
        for i, ((cell, arg), (eret, ecell), hline) in enumerate(
                zip(vecs[op], emu[op], host[op])):
            toks = hline.split()
            hret = int(toks[0], 16)
            hcell = [int(toks[1][2 * j:2 * j + 2], 16) for j in range(8)]
            if (eret & mask) != hret or ecell != hcell:
                mismatches.append(
                    'vec#%d cell=%s arg=%08X ROM=ret%08X/cell%s C=ret%08X/cell%s'
                    % (i, bytes(cell[:8]).hex(), arg, eret,
                       bytes(ecell).hex(), hret, bytes(hcell).hex()))
                if len(mismatches) >= 5:
                    break
        report(name, addr, n, mismatches, edges=nedge)
        if mismatches:
            return


if __name__ == '__main__':
    main()
