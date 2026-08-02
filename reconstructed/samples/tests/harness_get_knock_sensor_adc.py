#!/usr/bin/env python3
"""
harness_get_knock_sensor_adc.py — equivalence of rx8_get_knock_sensor_adc @0xC3CE.

Reconstructed source: samples/src/rx8_get_knock_sensor_adc.c
Lifts (truth candidates, all overridden by the ROM — see the source header):
  c/getKnockSensorADC.c      @0xC3CE — filter/ADC-read function of the OLDER
                             60E0FC00.bin image; WRONG for 60E1D400.bin.
  c/knock_sensor_adc_read.c  @0xC3CE — duplicate lift, same wrong filter
                             behaviour (its RAM map is largely right).
  c/knockRelatedInit.c       @0xC3C8 — the SAME body (knockRelatedInit
                             pushes r13/r12/r11 and falls through into
                             0xC3CE; the body is shared), but with lift
                             errors (RAM ADC/RPM reads that never happen,
                             0xFFFFA37A instead of 0xFFFFA37E, single-rotor
                             loop).  The ROM bytes win on every discrepancy.

The function is a fixed RAM side effect: NO arguments, NO return value, NO
sub-calls — it publishes two 16-bit ADC-output copies (0xFFFFA37E = 0x005E,
0xFFFFA37C = 0x00C1 from the ROM cal block), six calibration floats/words
(3.6875 / 0.0 / 10.0 / 64.0 / 10.0 / 64.0), arms the max byte (0xFF),
clears the counter and both fault bytes, and fills the two per-rotor
threshold / filter-state / sensor-ID cells.  Equivalence therefore compares
the RAM bytes after the call, not a return value (Track-A RAM pattern, cf.
harness_knock_function_init.py):

  - emulator side: seed the 19 written cells + 13 store-boundary sentinels
    in the sparse `ram` overlay, call the ROM entry @0xC3CE (self-contained;
    calibration reads come from the real ROM bytes), read the cells back;
  - host side: the oracle mmap()s the backing page (MAP_FIXED, same trick
    as host_oracle.c) plus the ROM calibration page @0x7A000 seeded from
    $RX8_ROM_PATH, seeds the same pre-states, runs the reconstructed C,
    reads the cells back.

The 16-bit words and 32-bit floats are compared as NUMERIC values (big-endian
assembly on both sides) so the little-endian host and the big-endian SH-2E
agree bit-for-bit; the six byte cells and the 13 sentinels are compared
byte-for-byte.  The sentinels must survive untouched — they pin the store
count and the write boundaries (e.g. a `mov.b` mistake for a 4-byte float
would leave its upper three bytes at pre-state).

The critical properties this harness pins:
  - the calibration table addresses/values are the real 60E1D400.bin ones
    (0x7A178=0x005E, 0x7A17A=0x00C1, 0x7A1A4=3.6875, 0x7A1D0=64.0,
    sensor IDs 0x7A164..0x7A165 = {0x01,0x01}) — validated before the run;
  - the filter/ADC-read lifts are FALSE for this ROM: the body at 0xC3CE
    reads NO RAM input and calls NO function, so any oracle variant that
    reads 0xFFFF9F0E / 0xFFFF9F80 or calls firstOrderFilter fails every
    vector;
  - the per-rotor B-pair is NOT zeroed: 0xFFFFA350/0xFFFFA354 = 10.0 and
    0xFFFFA368/0xFFFFA36C = 64.0.

Usage:  python3 harness_get_knock_sensor_adc.py [N]  (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0xC3CE          # 60E1D400.bin (see header: the body is shared with
                       # knockRelatedInit @0xC3C8, which pushes 3 extra
                       # registers and falls through into this entry)
N_DEFAULT = 20000
SEED = 0x60E1D400
BUILD_DIR = '/tmp/rx8-recon-get_knock_sensor_adc'

# ---- RAM cells written by the function (see rx8_get_knock_sensor_adc.c) ----
FLT_ADDRS = (0xFFFFA328, 0xFFFFA32C, 0xFFFFA334, 0xFFFFA338, 0xFFFFA348,
             0xFFFFA350, 0xFFFFA354, 0xFFFFA360, 0xFFFFA364, 0xFFFFA368,
             0xFFFFA36C)                            # 11 x f32
WRD_ADDRS = (0xFFFFA37C, 0xFFFFA37E)                # 2 x u16
BYT_ADDRS = (0xFFFFA324, 0xFFFFA384, 0xFFFFA385, 0xFFFFA386,
             0xFFFFA389, 0xFFFFA38A)                # 6 x u8
SENT_ADDRS = (0xFFFFA323, 0xFFFFA327, 0xFFFFA330, 0xFFFFA33C, 0xFFFFA34C,
              0xFFFFA358, 0xFFFFA370, 0xFFFFA37B, 0xFFFFA380, 0xFFFFA383,
              0xFFFFA387, 0xFFFFA388, 0xFFFFA38B)   # 13 sentinel bytes

# Vector byte order: the 11 floats (4 B each), the 2 words (2 B each), the
# 6 bytes, then the 13 sentinels — 67 bytes in total.
VEC_ADDRS = []
for a in FLT_ADDRS:
    VEC_ADDRS += [a + i for i in range(4)]
for a in WRD_ADDRS:
    VEC_ADDRS += [a + i for i in range(2)]
VEC_ADDRS += list(BYT_ADDRS)
VEC_ADDRS += list(SENT_ADDRS)
assert len(VEC_ADDRS) == 67

# Expected post-state of the 19 written cells (from the ROM; sentinels are
# variable and only pinned per-vector).
EXPECT = {
    0xFFFFA328: struct.unpack('>I', struct.pack('>f', 3.6875))[0],
    0xFFFFA32C: 0x00000000,
    0xFFFFA334: 0x00000000,
    0xFFFFA338: 0x00000000,
    0xFFFFA348: 0x00000000,
    0xFFFFA350: 0x41200000,   # 10.0
    0xFFFFA354: 0x41200000,
    0xFFFFA360: 0x41200000,
    0xFFFFA364: 0x42800000,   # 64.0
    0xFFFFA368: 0x42800000,
    0xFFFFA36C: 0x42800000,
    0xFFFFA37C: 0x00C1,
    0xFFFFA37E: 0x005E,
    0xFFFFA324: 0x00,
    0xFFFFA384: 0xFF,
    0xFFFFA385: 0x00,
    0xFFFFA386: 0x00,
    0xFFFFA389: 0x01,
    0xFFFFA38A: 0x01,
}

# ---- ROM calibration block (validated against the ROM before the run) ----
ROM_SENSOR_IDS = 0x7A164      # u8[2] = {0x01, 0x01}
ROM_ADC_WORD_A = 0x7A178      # u16 = 0x005E
ROM_ADC_WORD_B = 0x7A17A      # u16 = 0x00C1
ROM_REF_FLOAT = 0x7A1A4       # f32 = 3.6875
ROM_FILT_PARAM = 0x7A1D0      # f32 = 64.0
ROM_GAIN_LITERAL = 0xC4B0     # f32 = 10.0 (function literal pool)
ROM_MAX_LITERAL = 0xC494      # u16 = 0x00FF (function literal pool)


def check_cal(cpu):
    """The stock-ROM calibration is fixed; refuse to run if it changes so the
    ROM-page mapping and the hardcoded expectations stay meaningful."""
    if (cpu.rom[ROM_SENSOR_IDS:ROM_SENSOR_IDS + 2] != bytes([0x01, 0x01])
            or struct.unpack_from('>H', cpu.rom, ROM_ADC_WORD_A)[0] != 0x005E
            or struct.unpack_from('>H', cpu.rom, ROM_ADC_WORD_B)[0] != 0x00C1
            or struct.unpack_from('>f', cpu.rom, ROM_REF_FLOAT)[0] != 3.6875
            or struct.unpack_from('>f', cpu.rom, ROM_FILT_PARAM)[0] != 64.0
            or struct.unpack_from('>f', cpu.rom, ROM_GAIN_LITERAL)[0] != 10.0
            or struct.unpack_from('>H', cpu.rom, ROM_MAX_LITERAL)[0] != 0x00FF):
        raise RuntimeError('unexpected knock calibration bytes in the ROM')


def build_oracle():
    """Compile the reconstructed source + its own oracle into /tmp.

    (Recipe: this harness compiles its OWN oracle — only the file under test,
    not common.build_oracle's shared SRC_FILES bundle.)"""
    samples = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(samples, 'src'),
           '-I', os.path.join(samples, 'include'),
           os.path.join(samples, 'tests', 'oracle_get_knock_sensor_adc.c'),
           os.path.join(samples, 'src', 'rx8_get_knock_sensor_adc.c'),
           '-lm', '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def rd_post(cpu):
    """Assemble the 32-field post-state tuple (numeric big-endian values)."""
    out = []
    for a in FLT_ADDRS:
        out.append(struct.unpack(
            '>I', bytes(cpu.ram.get(a + i, 0) for i in range(4)))[0])
    for a in WRD_ADDRS:
        out.append((cpu.ram.get(a, 0) << 8) | cpu.ram.get(a + 1, 0))
    for a in BYT_ADDRS:
        out.append(cpu.ram.get(a, 0))
    for a in SENT_ADDRS:
        out.append(cpu.ram.get(a, 0))
    return tuple(out)


def gen_edges():
    """Distinctive pre-state patterns over the 67 vector bytes."""
    return [
        (0x00,) * 67,                                        # all zero
        (0xFF,) * 67,                                        # all ones
        tuple((0x55, 0xAA)[i % 2] for i in range(67)),       # alternating
        tuple((0xAA, 0x55)[i % 2] for i in range(67)),       # reversed
        tuple(0x80 if i % 4 == 0 else 0x00 for i in range(67)),   # sign bits
        tuple(0xFF if i % 4 == 3 else 0x00 for i in range(67)),   # lo-byte FF
        tuple((i * 37 + 11) % 256 for i in range(67)),       # ramp
    ]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)
    check_cal(cpu)
    # The oracle maps the ROM calibration page straight from the file.
    os.environ['RX8_ROM_PATH'] = ROM_PATH

    edges = gen_edges()
    vectors = list(edges) + [tuple(rng.randint(0, 255) for _ in range(67))
                             for _ in range(n)]

    # (a) ROM behaviour via the emulator: seed the pre-states + sentinels,
    #     call the actual ROM bytes @0xC3CE, read the cells back.
    emu = []
    for v in vectors:
        cpu.call(ADDR, ram=dict(zip(VEC_ADDRS, v)))
        emu.append(rd_post(cpu))

    # (b) host-C on the same vectors (oracle mmap-seeds and reads back).
    lines = ['knk ' + ' '.join('%02X' % b for b in v) for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the 32-field post-state tuples.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append('vec#%d ROM=%s C=%s pre=%s'
                              % (i, ' '.join('%X' % x for x in e),
                                 ' '.join('%X' % x for x in h),
                                 ' '.join('%02X' % b for b in v)))
            if len(mismatches) >= 5:
                break

    report('get_knock_sensor_adc', ADDR, n, mismatches, edges=len(edges))


if __name__ == '__main__':
    main()
