#!/usr/bin/env python3
"""
Differential tests for the CAN TX pack / getAndPack leaves lifted in
c/can_uds_subsystem.c, verified against the ACTUAL ROM bytes run in the
SH-2E emulator (tools/sh2emu.py).  The emulator executes the real ROM,
including the CAN-send tail (0x9AE4) and all ROM callees natively; the
Python models below are independent reimplementations derived from the
disassembly.

Covered here (entry used in the emulator + the table label):

  0x4C888  can240TX_pack           (table 04C888)  straight 8-byte copy
  0x4C984  can250TX_pack           (table 04C984)  straight 8-byte copy
  0x39348  can41TXPack             (table 039348)  gate @0xFFFFC241==1 -> copy
  0x2C806  can650TX_getAndPack     (table 02C806)  div-12 counter + 4-bit pack
  0x29B4C  can201TX_getAndPack     (table 029B52 — the table address is the
            first instruction after the prologue; the real entry is 0x29B4C:
            0x29A44 does `bsr 0x29B4C`.  Calling 0x29B52 skips the prologue
            and the epilogue pops garbage, so we call 0x29B4C.)
0x299DA  CANRX216TimeoutCount    (table 0299DA)  div-25 counter + pack-chain
             (can201 leaf + status-bit flags) + 7-byte TX copy
   0x33A36  can620TX_getAndPack     (table 033A36)  div-25 counter + 2 priority
             bitfield decoders: byte@CD4E -> byte@C05C (<<4), byte@CD4C ->
             byte@C05B, then 0x33A68 send (C05C/C05B into the mailbox frame)

Not yet modelled (complex multi-callee chains, TODO skeletons):
   0x29D24  can203TX_getAndPack     (table 029DC2 — real entry 0x29D24)
   0x2AAB6  can251TX_getAndPack
   0x11540  someMainFunction        (dispatcher, NOT a leaf)

Run from repo root:  python3 c/tests/test_can_packers.py [N]
"""
import os, sys, random, struct

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')


def rd16(ram, a):
    return ((ram.get(a, 0) << 8) | ram.get(a + 1, 0)) & 0xFFFF


def wr16(ram, a, v):
    v &= 0xFFFF
    ram[a] = (v >> 8) & 0xFF
    ram[a + 1] = v & 0xFF


def f32(x):
    return struct.unpack('>f', struct.pack('>f', x))[0]


# ---------------------------------------------------------------------------
# 0x4C888 can240TX_pack — TX buffer 0xFFFFCEA4 <- bytes 0xFFFFCEAC..0xFFFFCEB3
# ---------------------------------------------------------------------------
A240_SRC = 0xFFFFCEAC
A240_DST = 0xFFFFCEA4


def model_can240(ram):
    """8 source bytes at CEAC..CEB3 copied verbatim to CEA4..CEAB. r0=0 (CAN send)."""
    out = {}
    for i in range(8):
        out[A240_DST + i] = ram.get(A240_SRC + i, 0)
    return out, 0


# ---------------------------------------------------------------------------
# 0x4C984 can250TX_pack — TX buffer 0xFFFFCEB8 <- bytes 0xFFFFCEC0..0xFFFFCEC7
# ---------------------------------------------------------------------------
A250_SRC = 0xFFFFCEC0
A250_DST = 0xFFFFCEB8


def model_can250(ram):
    """8 source bytes at CEC0..CEC7 copied verbatim to CEB8..CEBF. r0=0."""
    out = {}
    for i in range(8):
        out[A250_DST + i] = ram.get(A250_SRC + i, 0)
    return out, 0


# ---------------------------------------------------------------------------
# 0x39348 can41TXPack — gate @0xFFFFC241 == 1 -> copy 0xFFFFC238..23F -> 0xFFFFC518
# ---------------------------------------------------------------------------
A41_GATE = 0xFFFFC241
A41_SRC = 0xFFFFC238
A41_DST = 0xFFFFC518


def model_can41(ram):
    """If gate@C241 == 1: copy 8 bytes C238..C23F -> C518..C51F, r0=0.
    Else: no TX writes, r0 = gate value (extu.b of the gate byte)."""
    g = ram.get(A41_GATE, 0)
    if g != 1:
        return {}, g
    out = {}
    for i in range(8):
        out[A41_DST + i] = ram.get(A41_SRC + i, 0)
    return out, 0


# ---------------------------------------------------------------------------
# 0x2C806 can650TX_getAndPack
#   counter word@0xFFFFBC6A += 1
#   if counter >= 0x0C (12): pack 4 flag bits -> byte@0xFFFFBC69,
#                            copy byte@BC69 -> byte@BC68, reset counter
# ---------------------------------------------------------------------------
A65_CNT = 0xFFFFBC6A
A65_B68 = 0xFFFFBC68
A65_B69 = 0xFFFFBC69
A65_FLAGS = (0xFFFFBDB8, 0xFFFFBDB9, 0xFFFFBDCD, 0xFFFFBDCC)
A65_BITS = (0x80, 0x40, 0x20, 0x10)


def model_can650(ram):
    cnt = (rd16(ram, A65_CNT) + 1) & 0xFFFF
    out = {}
    if cnt >= 12:                               # cmp/ge #0x0C on extu.w (unsigned)
        b = 0
        for (f, bit) in zip(A65_FLAGS, A65_BITS):
            if ram.get(f, 0) == 1:
                b |= bit
        out[A65_B69] = b
        out[A65_B68] = b
        cnt = 0
    wr16(out, A65_CNT, cnt)
    return out, 0


# ---------------------------------------------------------------------------
# 0x29B4C can201TX_getAndPack
#   flag byte@0xFFFFC656: != 0 -> byte@0xFFFFBB13 = 0xFF
#   == 0 -> fr0 = clamp(float@0xFFFFAA18, -40.0, 214.0) via ROM 0x2404
#           r0  = floatToInt(fr0, 1.0, -40.0) via ROM 0x24D0  (round .5, clamp
#           0..255) -> byte@0xFFFFBB13
# ---------------------------------------------------------------------------
A201_FLAG = 0xFFFFC656
A201_VAL = 0xFFFFAA18
A201_OUT = 0xFFFFBB13


def can201_value(flag, v):
    if flag != 0:
        return 0xFF
    if v != v:                                  # NaN -> 0
        return 0
    c = v
    if c < -40.0:
        c = -40.0
    if c > 214.0:
        c = 214.0
    # ROM 0x24D0: trunc((c - (-40.0)) / 1.0 + 0.5), single-precision steps
    x = f32(f32(f32(c) - f32(-40.0)) / f32(1.0))
    x = f32(x + f32(0.5))
    r = int(x)                                  # ftrc (truncate toward zero)
    if r > 255:
        r = 255
    if r < 0:
        r = 0
    return r


def model_can201(ram):
    flag = ram.get(A201_FLAG, 0)
    v = struct.unpack('>f', bytes(ram.get(A201_VAL + i, 0) for i in range(4)))[0]
    return {A201_OUT: can201_value(flag, v)}, None      # r0 not compared


# ---------------------------------------------------------------------------
# 0x299DA CANRX216TimeoutCount
#   counter word@0xFFFFBB1C += 1
#   if counter >= 25: pack chain (can201 leaf + flag bits), 7-byte TX copy
#   BB0C..BB12, reset counter
#   pack chain (0x29A44 -> 0x29AA0..0x29B4A):
#     byte@BB13 = can201_value(byte@C656, float@AA18)
#     byte@BB14 = byte@BB13
#     byte@BB15 = byte@BC65
#     word@BB16 = 0
#     byte@BB18 = 1 if (byte@BC7C == 0 or byte@B738 == 1) else 0
#     word@BB1A = (D1DD?0x8000 : D1DE?0x4000 : 0) | 0400|0100|0080|0040|0002
#   send (0x29A0C): BB0C..BB12 = {BB14, BB15, w16>>8, w16&FF, BB18, w1A>>8, w1A&FF}
# ---------------------------------------------------------------------------
A216_CNT = 0xFFFFBB1C
A216_FLAG = A201_FLAG
A216_VAL = A201_VAL
A216_BC65 = 0xFFFFBC65
A216_BC7C = 0xFFFFBC7C
A216_B738 = 0xFFFFB738
A216_D1DD = 0xFFFFD1DD
A216_D1DE = 0xFFFFD1DE
A216_BBCC = 0xFFFFBBCC
A216_BBCD = 0xFFFFBBCD
A216_BBCE = 0xFFFFBBCE
A216_B624 = 0xFFFFB624
A216_BBCF = 0xFFFFBBCF
A216_TX = 0xFFFFBB0C


def model_canrx216(ram):
    cnt = (rd16(ram, A216_CNT) + 1) & 0xFFFF
    out = {}
    if cnt >= 25:                               # cmp/ge #0x19 on extu.w (unsigned)
        b13 = can201_value(ram.get(A216_FLAG, 0),
                           struct.unpack('>f', bytes(ram.get(A216_VAL + i, 0)
                                                     for i in range(4)))[0])
        b14 = b13
        b15 = ram.get(A216_BC65, 0)
        w16 = 0
        b18 = 1 if (ram.get(A216_BC7C, 0) == 0 or ram.get(A216_B738, 0) == 1) else 0
        w1a = 0x8000 if ram.get(A216_D1DD, 0) == 1 else \
              (0x4000 if ram.get(A216_D1DE, 0) == 1 else 0)
        if ram.get(A216_BBCC, 0) == 1:
            w1a |= 0x0400
        if ram.get(A216_BBCD, 0) == 1:
            w1a |= 0x0100
        if ram.get(A216_BBCE, 0) == 1:
            w1a |= 0x0080
        if ram.get(A216_B624, 0) == 1:
            w1a |= 0x0040
        if ram.get(A216_BBCF, 0) == 1:
            w1a |= 0x0002
        out[A201_OUT] = b13
        out[0xFFFFBB14] = b14
        out[0xFFFFBB15] = b15
        wr16(out, 0xFFFFBB16, w16)
        out[0xFFFFBB18] = b18
        wr16(out, 0xFFFFBB1A, w1a)
        tx = [b14, b15, (w16 >> 8) & 0xFF, w16 & 0xFF, b18,
              (w1a >> 8) & 0xFF, w1a & 0xFF]
        for i, b in enumerate(tx):
            out[A216_TX + i] = b
        cnt = 0
    wr16(out, A216_CNT, cnt)
    return out, 0


# ---------------------------------------------------------------------------
# 0x33A36 can620TX_getAndPack
#   counter word@0xFFFFC05E += 1
#   if counter >= 25 (0x19):
#     pack chain (0x33A8E -> 0x33A98 + 0x33AEA):
#       priority-decode byte@0xFFFFCD4E (0x40->0, 0x20->1, 0x80->2, else 3)
#           -> byte@0xFFFFC05C = value << 4
#       priority-decode byte@0xFFFFCD4C (0x80->1,0x10->2,0x20->3,0x08->4,
#           0x02->5,0x04->6, else 7) -> byte@0xFFFFC05B
#     send (0x33A68): zero C054..C057/C059, C058=C05C, C05A=C05B, reset counter
# ---------------------------------------------------------------------------
A620_CNT = 0xFFFFC05E
A620_CD4E = 0xFFFFCD4E
A620_CD4C = 0xFFFFCD4C
A620_C05B = 0xFFFFC05B
A620_C05C = 0xFFFFC05C
A620_C054 = 0xFFFFC054
A620_C055 = 0xFFFFC055
A620_C056 = 0xFFFFC056
A620_C057 = 0xFFFFC057
A620_C058 = 0xFFFFC058
A620_C059 = 0xFFFFC059
A620_C05A = 0xFFFFC05A


def _dec_CD4E(d):
    if d & 0x40:
        return 0
    if d & 0x20:
        return 1
    if d & 0x80:
        return 2
    return 3


def _dec_CD4C(d):
    if d & 0x80:
        return 1
    if d & 0x10:
        return 2
    if d & 0x20:
        return 3
    if d & 0x08:
        return 4
    if d & 0x02:
        return 5
    if d & 0x04:
        return 6
    return 7


def model_can620(ram):
    cnt = (rd16(ram, A620_CNT) + 1) & 0xFFFF
    out = {}
    if cnt >= 25:                              # cmp/ge #0x19 on extu.w
        v1 = _dec_CD4E(ram.get(A620_CD4E, 0))
        v2 = _dec_CD4C(ram.get(A620_CD4C, 0))
        c05c = v1 << 4
        out[A620_C05C] = c05c
        out[A620_C05B] = v2
        # send frame C054..C05A + C05C/C05B copy
        out[A620_C054] = 0
        out[A620_C055] = 0
        out[A620_C056] = 0
        out[A620_C057] = 0
        out[A620_C058] = c05c
        out[A620_C059] = 0
        out[A620_C05A] = v2
        cnt = 0
    wr16(out, A620_CNT, cnt)
    return out, 0


# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------
def seed_word(ram, a, v):
    ram[a] = (v >> 8) & 0xFF
    ram[a + 1] = v & 0xFF
    return ram


def seed_float(ram, a, v):
    for i, b in enumerate(struct.pack('>f', v)):
        ram[a + i] = b


def check(name, actual_ram, actual_r0, model_ram, expect_r0):
    for a, v in model_ram.items():
        got = actual_ram.get(a, 0)
        if got != v:
            return "MISMATCH %s @%05X got=%02X exp=%02X" % (name, a, got, v)
    if expect_r0 is not None and actual_r0 != expect_r0:
        return "MISMATCH %s r0=%08X exp=%08X" % (name, actual_r0, expect_r0)
    return None


def gen_ram_240(rng):
    return {A240_SRC + i: rng.randint(0, 255) for i in range(8)}


def gen_ram_250(rng):
    return {A250_SRC + i: rng.randint(0, 255) for i in range(8)}


def gen_ram_41(rng):
    r = {A41_GATE: rng.choice([0, 1, 1, 1, 2, 0xFF])}
    for i in range(8):
        r[A41_SRC + i] = rng.randint(0, 255)
    return r


def gen_ram_65(rng):
    r = {}
    seed_word(r, A65_CNT, rng.choice([rng.randint(0, 40),
                                      rng.randint(0, 0xFFFF)]))
    for f in A65_FLAGS:
        r[f] = rng.choice([0, 1])
    return r


def gen_ram_201(rng):
    r = {A201_FLAG: rng.choice([0, 1])}
    seed_float(r, A201_VAL, rng.uniform(-100.0, 300.0))
    return r


def gen_ram_216(rng):
    r = {}
    seed_word(r, A216_CNT, rng.choice([rng.randint(0, 40),
                                       rng.randint(0, 0xFFFF)]))
    r[A216_FLAG] = rng.choice([0, 1])
    seed_float(r, A216_VAL, rng.uniform(-100.0, 300.0))
    r[A216_BC65] = rng.randint(0, 255)
    r[A216_BC7C] = rng.choice([0, 1])
    r[A216_B738] = rng.choice([0, 1])
    for a in (A216_D1DD, A216_D1DE, A216_BBCC, A216_BBCD, A216_BBCE, A216_B624, A216_BBCF):
        r[a] = rng.choice([0, 1])
    return r


def gen_ram_620(rng):
    r = {}
    seed_word(r, A620_CNT, rng.choice([rng.randint(0, 40),
                                       rng.randint(0, 0xFFFF)]))
    r[A620_CD4E] = rng.randint(0, 255)
    r[A620_CD4C] = rng.randint(0, 255)
    return r


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    def run(entry, ram):
        cpu.call(entry, ram=ram)
        return dict(cpu.ram), cpu.r[0]

    funcs = [
        ("can240TX_pack", 0x4C888, gen_ram_240, model_can240),
        ("can250TX_pack", 0x4C984, gen_ram_250, model_can250),
        ("can41TXPack", 0x39348, gen_ram_41, model_can41),
        ("can650TX_getAndPack", 0x2C806, gen_ram_65, model_can650),
        ("can201TX_getAndPack", 0x29B4C, gen_ram_201, model_can201),
        ("CANRX216TimeoutCount", 0x299DA, gen_ram_216, model_canrx216),
        ("can620TX_getAndPack", 0x33A36, gen_ram_620, model_can620),
    ]

    directed = {
        "can240TX_pack": [
            {A240_SRC + i: 0x00 for i in range(8)},
            {A240_SRC + i: 0xFF for i in range(8)},
            {A240_SRC + i: (0xAA if i % 2 == 0 else 0x55) for i in range(8)},
        ],
        "can250TX_pack": [
            {A250_SRC + i: 0x00 for i in range(8)},
            {A250_SRC + i: 0xFF for i in range(8)},
            {A250_SRC + i: (0xAA if i % 2 == 0 else 0x55) for i in range(8)},
        ],
        "can41TXPack": [
            {A41_GATE: 0, A41_SRC: 0x11},
            {A41_GATE: 2, A41_SRC: 0x22},
            {**{A41_GATE: 1}, **{A41_SRC + i: 0x00 for i in range(8)}},
            {**{A41_GATE: 1}, **{A41_SRC + i: 0xFF for i in range(8)}},
        ],
        "can650TX_getAndPack": [
            {**seed_word({}, A65_CNT, 0x0B), **{f: 1 for f in A65_FLAGS}},
            {**seed_word({}, A65_CNT, 0x0C), **{f: 0 for f in A65_FLAGS}},
            {**seed_word({}, A65_CNT, 0x0D), **{f: 1 for f in A65_FLAGS}},
            {**seed_word({}, A65_CNT, 0xFFFF), **{f: 1 for f in A65_FLAGS}},
            {**seed_word({}, A65_CNT, 0x7FFF), **{f: 1 for f in A65_FLAGS}},
        ],
        "can201TX_getAndPack": [
            {**{A201_FLAG: 0}, **{A201_VAL + i: b for i, b in
                 enumerate(struct.pack('>f', -100.0))}},
            {**{A201_FLAG: 0}, **{A201_VAL + i: b for i, b in
                 enumerate(struct.pack('>f', 300.0))}},
            {**{A201_FLAG: 0}, **{A201_VAL + i: b for i, b in
                 enumerate(struct.pack('>f', 0.0))}},
            {**{A201_FLAG: 1}, **{A201_VAL + i: b for i, b in
                 enumerate(struct.pack('>f', 0.0))}},
        ],
        "CANRX216TimeoutCount": [
            {**seed_word({}, A216_CNT, 0x18)},
            {**seed_word({}, A216_CNT, 0x19),
                 **{A216_FLAG: 0, A216_BC65: 0x5A, A216_BC7C: 1, A216_B738: 0}},
            {**seed_word({}, A216_CNT, 0xFFFF)},
            {**seed_word({}, A216_CNT, 0x7FFF)},
        ],
        "can620TX_getAndPack": [
            {**seed_word({}, A620_CNT, 0x18), A620_CD4E: 0x40, A620_CD4C: 0x80},
            {**seed_word({}, A620_CNT, 0x19), A620_CD4E: 0x20, A620_CD4C: 0x10},
            {**seed_word({}, A620_CNT, 0x24), A620_CD4E: 0x80, A620_CD4C: 0x20},
            {**seed_word({}, A620_CNT, 0x25), A620_CD4E: 0x00, A620_CD4C: 0x08},
            {**seed_word({}, A620_CNT, 0xFFFF), A620_CD4E: 0x02, A620_CD4C: 0x02},
            {**seed_word({}, A620_CNT, 0x7FFF), A620_CD4E: 0xFF, A620_CD4C: 0xFF},
        ],
    }

    for name, entry, gen, model in funcs:
        for ram in directed[name]:
            act_ram, act_r0 = run(entry, dict(ram))
            exp, er0 = model(dict(ram))
            err = check(name + " (directed)", act_ram, act_r0, exp, er0)
            if err:
                print("FAIL:", err, "seed=", {hex(k): v for k, v in ram.items()})
                sys.exit(1)
        rng = random.Random(entry)
        for _ in range(N):
            ram = gen(rng)
            act_ram, act_r0 = run(entry, dict(ram))
            exp, er0 = model(dict(ram))
            err = check(name + " (rand)", act_ram, act_r0, exp, er0)
            if err:
                print("FAIL:", err, "seed=", {hex(k): v for k, v in ram.items()})
                sys.exit(1)
        print("OK  %-24s @0x%05X  (directed + %d random)" % (name, entry, N))

    print("ALL GREEN  test_can_packers (7 functions, %d random each)" % N)
    sys.exit(0)


if __name__ == '__main__':
    main()
