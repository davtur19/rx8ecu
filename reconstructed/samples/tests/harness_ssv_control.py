#!/usr/bin/env python3
"""
harness_ssv_control.py — equivalence of rx8_ssv_control @0x225C8.

Reconstructed source: samples/src/rx8_ssv_control.c
Verified lift   : c/ssvControl.c (same address; verified by
                  c/tests/test_ssv_control.py over 12000 finite random temps).

The function is a void task with NO ABI return value: its whole effect is on
RAM (the SSV command byte @0xFFFFB324, the transition counter @0xFFFFB322,
the SM result byte @0xFFFFB320, status-word bit 0x80 @0xFFFFF754, the mode
store @0xFFFFB325, plus the state-machine side-effects @0xFFFFD355/@0xFFFFD387
and the output byte behind the stored pointer), so the equivalence check
compares RAM side-effects, not a return value:

  - emulator side: seed the input bytes in the sparse ram overlay (f32 temp
    @0xFFFFAA10, mode @0xFFFFAAE0, previous mode @0xFFFFB325, command
    pre-state @0xFFFFB324, counter @0xFFFFB322, status @0xFFFFBF39, the SM
    descriptor mask @0x6021C / output ptr @0x60220, the SM cells
    @0xFFFFD350/D352/D354/D355/D3A8/D387 and the output byte @0xFFFFD400,
    status word @0xFFFFF754), call the ROM entry @0x225C8 (which internally
    jsr's the REAL ROM bytes of sm_08 @0x5D3E8, setRegister_REG_BIT_VAL
    @0x4BBC, setSR_PARAM @0x2054 and loadStatusRegister_ADDR @0x2064), read
    the eight cells back;
  - host side: the dedicated oracle mmap()s the pages backing the cells AND
    the two ROM calibration pages (0x72F70..0x72F74, 0x226D4) straight from
    the ROM file, seeds the same bytes, runs the reconstructed C and prints
    the same eight cells.

EDGE vectors cover: the hysteresis boundaries (0, denormals, 197.0/200.0
+/- 1 ulp, +inf/-inf, NaN, -0.0), the counter reload/countdown/zero paths,
the enable gating with the status byte and the (mode, counter, command)
combinations, every branch of the alternating-sensor FSM (state 0/1/2/5/7,
magic 0xE926 vs mismatch, masked vs clear, count 7 vs not, all output-cell
values) and distinguishable stale pre-states for every written cell; N random
pre-states follow (fixed seed = the ROM address).

Usage:  python3 harness_ssv_control.py [N]  (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x225C8
N_DEFAULT = 20000
SEED = 0x225C8
BUILD_DIR = '/tmp/rx8-recon-ssv_control'
PTR_CELL = 0xFFFFD400          # scratch cell the SM output pointer targets

# ---- cell addresses (see rx8_ssv_control.c) ----
AA10 = 0xFFFFAA10              # f32 temperature
AAE0 = 0xFFFFAAE0              # u8 mode
B324 = 0xFFFFB324              # u8 SSV command
B322 = 0xFFFFB322              # u16 transition counter
B320 = 0xFFFFB320              # u8 SM result
B325 = 0xFFFFB325              # u8 previous mode
BF39 = 0xFFFFBF39              # u8 status byte
F754 = 0xFFFFF754              # u16 status word (bit 0x80)
SM_MASK = 0x6021C              # u8 sensor mask (base+8)
SM_PTR = 0x60220               # u32 stored output pointer (base+0xC)
D355 = 0xFFFFD355              # u8 SM state byte
D350 = 0xFFFFD350              # u16 SM magic word
D352 = 0xFFFFD352              # u16 SM source word
D354 = 0xFFFFD354              # u8 SM count byte
D3A8 = 0xFFFFD3A8              # u8 SM input byte
D387 = 0xFFFFD387              # u8 SM latch byte

# ---- ROM calibration cells ----
ROM_CAL_FLAG = 0x72F70         # u8  (= 0)
ROM_RELOAD = 0x72F72           # u16 (= 188)
ROM_T_ON = 0x72F74             # f32 (= 200.0)
ROM_T_HY = 0x226D4             # f32 (= -3.0)

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_ssv_control.c'),
           os.path.join(SAMPLES, 'src', 'rx8_ssv_control.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def seed(init, addr, n, val):
    """Byte-exact big-endian store of a width-`n` value in the ram overlay."""
    for i in range(n):
        init[addr + i] = (val >> (8 * (n - 1 - i))) & 0xFF


def run_emu(cpu, vec):
    """Seed every input cell, run the ROM bytes @0x225C8 (callees included)
    and return the 8-tuple of post-state cells with side effects visible."""
    t, mode, prevm, cmd0, cnt0, status, mask, st, magic, src, csm, inp, \
        latch, cell, f754 = vec
    init = {}
    seed(init, AA10, 4, t & 0xFFFFFFFF)          # raw float bits of the temp
    init[AAE0] = mode & 0xFF
    init[B325] = prevm & 0xFF
    init[B324] = cmd0 & 0xFF
    seed(init, B322, 2, cnt0 & 0xFFFF)
    init[BF39] = status & 0xFF
    seed(init, F754, 2, f754 & 0xFFFF)
    init[SM_MASK] = mask & 0xFF
    seed(init, SM_PTR, 4, PTR_CELL)
    init[D355] = st & 0xFF
    seed(init, D350, 2, magic & 0xFFFF)
    seed(init, D352, 2, src & 0xFFFF)
    init[D354] = csm & 0xFF
    init[D3A8] = inp & 0xFF
    init[D387] = latch & 0xFF
    init[PTR_CELL] = cell & 0xFF
    cpu.call(ADDR, ram=init)
    return (cpu.rd(B324, 1), cpu.rd(B322, 2), cpu.rd(B320, 1),
            cpu.rd(F754, 2), cpu.rd(B325, 1), cpu.rd(D355, 1),
            cpu.rd(D387, 1), cpu.rd(PTR_CELL, 1))


def gen_edges():
    """Edge pre-states (t, mode, prevm, cmd0, cnt0, status, mask, st, magic,
    src, csm, inp, latch, cell, f754) targeting every branch."""
    v = []
    # (a) temperature hysteresis: boundaries, 0, denormals, NaN, +/-inf.
    temps = (0x00000000, 0x00000001, 0x007FFFFF, 0x00800000, 0x3F800000,
             0x4344FFFF, 0x43450000, 0x43450001,          # 197.0 -/+ 1ulp
             0x4347FFFF, 0x43480000, 0x43480001,          # 200.0 -/+ 1ulp
             0x42C80000, 0x43160000, 0x437A0000,          # 100/150/250
             0x7F800000, 0xFF800000,                      # +inf / -inf
             0x7FC00000, 0x7FA00000, 0xFFFFFFFF,          # NaN payloads
             0x80000000, 0xC3480000,                      # -0.0 / -200.0
             0x4E6E6B28, 0xCE6E6B28)                      # +1e9 / -1e9
    for t in temps:
        # enable = 1 path (mode 0, prevm 1, cmd 0) and enable = 0 path
        # (mode 1, prevm 0, cmd 1), with the SM latch around its ==1 test.
        for latch in (0x00, 0x01, 0xFF):
            v.append((t, 0, 1, 0, 5, 0, 0xFF, 0, 0xE926, 0xABCD, 7, 0xFF,
                      latch, 0x00, 0x0000))
            v.append((t, 1, 0, 1, 0, 0, 0xFF, 0, 0xE926, 0xABCD, 7, 0xFF,
                      latch, 0x00, 0x0080))
    # (b) counter: reload (mode 0, prevm 1) vs countdown (mode != 0 or prevm
    # != 1) vs zero (no write) across boundary counter values.
    for cnt0 in (0x0000, 0x0001, 0x0002, 0x00BC, 0x00BD, 0x7FFF, 0x8000, 0xFFFF):
        v.append((0x43480000, 0, 1, 0, cnt0, 0, 0xFF, 0, 0xE926, 0xABCD, 7,
                  0xFF, 0x00, 0x00, 0x0000))
        v.append((0x43480000, 1, 1, 0, cnt0, 0, 0xFF, 0, 0xE926, 0xABCD, 7,
                  0xFF, 0x00, 0x00, 0x0000))
        v.append((0x43480000, 0, 0, 0, cnt0, 0, 0xFF, 0, 0xE926, 0xABCD, 7,
                  0xFF, 0x00, 0x00, 0x0000))
    # (c) enable gating: the status byte around its ==1 test.
    for status in (0x00, 0x01, 0xFF):
        v.append((0x43160000, 1, 1, 1, 5, status, 0xFF, 0, 0xE926, 0xABCD, 7,
                  0xFF, 0x00, 0x00, 0x0000))
    # (d) enable gating: the (mode, counter > 0, command == 0) conjunction.
    for mode in (0, 1):
        for cnt0 in (0x0000, 0x0001):
            for cmd0 in (0x00, 0x01):
                v.append((0x43160000, mode, 1, cmd0, cnt0, 0, 0xFF, 0, 0xE926,
                          0xABCD, 7, 0xFF, 0x00, 0x00, 0x0000))
    # (e) alternating-sensor FSM branches.  st=0 -> first block runs:
    # magic 0xE926 + masked!=0 + cnt==7 -> cell=7, latch=src>>8, st=1;
    # masked!=0 cnt!=7 -> cell=cnt, st=1; masked==0 -> cell=0, st=2;
    # magic mismatch -> st=0 (cell=0 only when masked==0).  st!=0 skips the
    # first block.  The second block then keys the return on the output cell:
    # 0 -> latch=(cmd==1), return cmd; 5/7 -> return (latch==1); else cmd.
    sm_edges = (
        (0x00, 0xE926, 0xFF, 0x07, 0xFF, 0xABCD),   # masked!=0 cnt==7
        (0x00, 0xE926, 0xFF, 0x07, 0xFF, 0x1234),   # src high byte -> latch
        (0x00, 0xE926, 0xFF, 0x06, 0xFF, 0xABCD),   # cnt != 7
        (0x00, 0xE926, 0x00, 0x00, 0xFF, 0xABCD),   # mask 0 -> masked==0
        (0x00, 0xE926, 0x0F, 0x07, 0x40, 0xABCD),   # inp&mask == 0
        (0x00, 0xE926, 0x0F, 0x07, 0x4F, 0xABCD),   # inp&mask == 0x0F
        (0x00, 0x0000, 0xFF, 0x07, 0xFF, 0xABCD),   # magic mismatch masked!=0
        (0x00, 0x0000, 0xFF, 0x07, 0x00, 0xABCD),   # magic mismatch masked==0
        (0x00, 0xFFFF, 0x80, 0x05, 0x80, 0xABCD),   # cnt = 5 (out=5 latch src)
        (0x01, 0xE926, 0xFF, 0x07, 0xFF, 0xABCD),   # st=1 -> skip first block
        (0x02, 0xE926, 0xFF, 0x07, 0xFF, 0xABCD),
        (0x05, 0xE926, 0xFF, 0x07, 0xFF, 0xABCD),
        (0x07, 0xE926, 0xFF, 0x07, 0xFF, 0xABCD),
        (0xFF, 0xE926, 0xFF, 0x07, 0xFF, 0xABCD),
    )
    for (st, magic, mask, csm, inp, src) in sm_edges:
        for cell in (0x00, 0x01, 0x05, 0x07, 0x08, 0x55, 0xFF):
            for latch in (0x00, 0x01, 0xFF):
                v.append((0x43480000, 1, 1, 1, 0, 0, mask, st, magic, src,
                          csm, inp, latch, cell, 0x0000))
    # (f) status-word pre-states around bit 0x80.
    for f754 in (0x0000, 0x0080, 0xFF7F, 0x8000, 0xFFFF):
        v.append((0x43480000, 0, 0, 0, 0, 1, 0xFF, 0, 0xE926, 0xABCD, 7, 0xFF,
                  0x00, 0x00, f754))
    return v


def gen_random(rng, k):
    """k random pre-states over the full byte/word range of every input, with
    the SM magic / state / count and the temp biased toward the hot paths."""
    v = []
    for _ in range(k):
        if rng.random() < 0.5:
            t = struct.unpack('>I', struct.pack('>f', rng.uniform(150, 250)))[0]
        else:
            t = rng.getrandbits(32)                  # raw float bits incl NaN
        magic = rng.choice((0xE926, 0xE926, rng.getrandbits(16)))
        st = rng.choice((0, 0, 0, 1, 2, 5, 7, rng.getrandbits(8)))
        csm = rng.choice((7, rng.getrandbits(8)))
        latch = rng.choice((0, 1, rng.getrandbits(8)))
        v.append((t,
                  rng.choice((0, 0, 1, 2, 0xFF)),
                  rng.choice((0, 1, 2, 0xFF)),
                  rng.choice((0, 1, 0x55, 0xFF)),
                  rng.getrandbits(16),
                  rng.choice((0, 1, 0xFF)),
                  rng.getrandbits(8),                # sensor mask
                  st,
                  magic,
                  rng.getrandbits(16),               # source word
                  csm,
                  rng.getrandbits(8),                # sensor input
                  latch,
                  rng.choice((0, 1, 5, 7, 0x55, 0xFF)),  # output cell
                  rng.getrandbits(16)))              # status word
    return v


def check_cal(cpu):
    """The stock-Rom calibration constants are fixed; refuse to run if they
    ever change so the ROM-page mapping stays meaningful."""
    if (cpu.rom[ROM_CAL_FLAG] != 0
            or struct.unpack_from('>H', cpu.rom, ROM_RELOAD)[0] != 188
            or struct.unpack_from('>f', cpu.rom, ROM_T_ON)[0] != 200.0
            or struct.unpack_from('>f', cpu.rom, ROM_T_HY)[0] != -3.0):
        raise RuntimeError('unexpected SSV calibration bytes @0x%X/0x%X/0x%X/0x%X'
                           % (ROM_CAL_FLAG, ROM_RELOAD, ROM_T_ON, ROM_T_HY))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)
    check_cal(cpu)
    # The oracle maps the ROM pages straight from the file — point it there.
    os.environ['RX8_ROM_PATH'] = ROM_PATH

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM side-effects; the 0x5D3E8 /
    # 0x4BBC / 0x2054 / 0x2064 callees run as real ROM bytes).
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host-C on the same pre-states (cal constants from the mapped ROM).
    lines = ['ssv %08X %02X %02X %02X %04X %02X %02X %02X %04X %04X %02X '
             '%02X %02X %02X %04X' % v for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the post-state tuples byte-for-byte.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d t=0x%08X mode=%02X prevm=%02X cmd0=%02X cnt0=%04X '
                'status=%02X mask=%02X st=%02X magic=%04X src=%04X csm=%02X '
                'inp=%02X latch=%02X cell=%02X f754=%04X '
                'ROM=(%02X,%04X,%02X,%04X,%02X,%02X,%02X,%02X) '
                'C=(%02X,%04X,%02X,%04X,%02X,%02X,%02X,%02X)'
                % (i, v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8],
                   v[9], v[10], v[11], v[12], v[13], v[14],
                   e[0], e[1], e[2], e[3], e[4], e[5], e[6], e[7],
                   h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7]))
            if len(mismatches) >= 5:
                break

    report('ssv_control', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
