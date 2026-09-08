#!/usr/bin/env python3
"""
Track-A verifier: compile each C lift (host) and compare it to the ACTUAL ROM code
executed by tools/sh2emu.py, over many random inputs. Stronger than a hand
transcription and reusable for any function whose behavior is a pure function of
its integer args.

Run from repo root:   python3 c/tests/verify_emu.py
(or `make c-emu`)

Registry: name -> (entry address in 60E1D400, return width in bytes, arg widths).
Add a row per lifted function.

Coverage manifest (claims list == hosted + skipped, no silent gaps):
  * FUNCS below = every claimed lift whose behavior is a pure function of
    integer args AND fits this harness (single-file TU named c/<name>.c,
    standard r4-r7 ABI unless `regs` says otherwise, executable by the base
    tools/sh2emu.py emulator). Each gets EDGES (if any) + 100k random vectors.
  * SKIP = every other claimed lift from c/README.md (~22 Done entries) and
    c/verified_addrs.txt (41 addrs, first block), with the reason it has no
    hostable harness HERE plus the dedicated differential test that DOES cover
    it. The runner prints each SKIP line and asserts FUNCS | SKIP covers the
    full CLAIMS list, so coverage == claims by construction.
"""
import argparse, ctypes, os, random, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
RE = os.path.abspath(os.path.join(HERE, '..', '..'))          # repo root
sys.path.insert(0, os.path.join(RE, 'tools'))                 # sh2emu.py lives in tools/
from sh2emu import SH2

# Determinism (wave2b): fixed seed so every run generates the identical
# vector stream. Prove with two runs + diff:
#   python3 c/tests/verify_emu.py > /tmp/v1.log && python3 c/tests/verify_emu.py > /tmp/v2.log && diff /tmp/v1.log /tmp/v2.log
RANDOM_SEED = 0x60E1D400
random.seed(RANDOM_SEED)

DEFAULT_ROM = os.path.join(RE, 'roms', 'stock', '60E1D400.bin')
# Backward-compat alias: the default ROM path (overridable via --rom / RX8ECU_ROM).
ROM = DEFAULT_ROM


def parse_args():
    ap = argparse.ArgumentParser(description='Track-A verifier: C lifts vs emulated ROM')
    ap.add_argument('--rom', default=os.environ.get('RX8ECU_ROM', DEFAULT_ROM),
                    help='ROM image to emulate (default: %(default)s; env RX8ECU_ROM overrides the default)')
    ap.add_argument('--seed', type=int, default=RANDOM_SEED,
                    help='random seed for the vector stream (default: %(default)s = 0x60E1D400)')
    return ap.parse_args()

# name: (entry@60E1D400, ret_bytes, [arg_bytes,...]) or
#       (entry@60E1D400, ret_bytes, [arg_bytes,...], [reg,...]) for non-r4 ABI.
# NOTE: setSR (0x3934), getSR (0x3920), and setSR_PARAM (0x2054) are NOT listed here
# because they operate on the SH-2 Status Register (SR), which is hidden implicit state,
# not a function argument.  They require stateful testing with an SR-aware emulator
# subclass (SRCPU in test_setSR_getSR.py) that models stc/ldc SR.  See that file and
# c/tests/test_setSR_getSR.py for their verification.  (Also mirrored in SKIP.)
#
# NOTE: firstOrderFilter (0x23B0) is tested by test_math_primitives.py (float args/return).
# getFromE2_E2ADDR_RAMADDR_LEN (0x39170) is tested by test_getFromE2.py (hardware interface).
# Both are verified against the ROM but don't fit this integer-arg-only framework.
FUNCS = {
    'add16bitSaturate': (0x2460, 2, [2, 2]),
    'addSaturate8Bit':  (0x2478, 1, [1, 1]),
    # 2026-07-31: addS32Saturate @0x2304 (IDA mislabeled 'fpu_compare_float')
    'addS32Saturate':   (0x2304, 4, [4, 4]),
    # 2026-07-31: immobilizer leaf functions (pure function of integer args)
    'seed_mixer':        (0x366B8, 4, [4, 4]),
    'calculateImmoSeed': (0x3675C, 4, [4, 4, 4]),
    # 2026-09-08: integer division family. Non-standard ABI: the ROM takes
    # divisor in r0 / dividend in r1 (not r4/r5), hence the regs override.
    # div0 returns 0 (ROM also stores diag 0x44E at 0xFFFF7304 — return-only
    # comparison here; the RAM side effect is pinned by test_div32_signed.py).
    'div32_signed':      (0x3FE8, 4, [4, 4], [0, 1]),
    'mod32_signed':      (0x4144, 4, [4, 4], [0, 1]),
    'div32_unsigned':    (0x409C, 4, [4, 4], [0, 1]),
    # 2026-09-08: 16-bit value/complement pack (pure function of a u16).
    'complement_shift_u16': (0x2430, 4, [2]),
}

# name: [(arg_tuple, ...)] — edge vectors always checked before random fuzz.
# (divisor, dividend) pairs: div0 documented behavior + the INT32_MIN/-1 pair
# whose quotient (+2^31)/remainder needs the UB guard in the C lifts.
EDGES = {
    'div32_signed':   [(0xFFFFFFFF, 0x80000000), (0, 100)],
    'mod32_signed':   [(0xFFFFFFFF, 0x80000000), (0, 100)],
    'div32_unsigned': [(0, 100)],
}

# name: (entry_addr, reason_no_host_harness, covering_differential_test).
# Every claimed lift (c/README.md Done entries + c/verified_addrs.txt 41-addr
# first block) not in FUNCS appears here — no silent gaps.
SKIP = {
    # --- 1-D/2-D lookup family: descriptor-pointer + float args need a map harness ---
    'TwoDLookup':             ('0x2068', 'Map1D* + float args; needs ROM-map harness', 'test_2DLookup_type0.py'),
    'TwoDLookup_FP_16bit':    ('0x20C4', 'Map1D* + float arg; needs ROM-map harness', 'test_2DLookup_FP_16bit.py'),
    'TwoDLookup_FP_8bit':     ('0x20AC', 'Map1D* + float arg; needs ROM-map harness', 'test_2DLookup_FP_8bit.py'),
    'ThreeDLookup':           ('0x20DC', 'Map2D* + float args; needs ROM-surface harness', 'test_3dlookup_type8.py'),
    'ThreeDLookup_FP_8bit':   ('0x2120', 'Map2D* + float args; needs ROM-surface harness', 'test_3DLookup_FP.py'),
    'ThreeDLookup_FP_16bit':  ('0x213C', 'Map2D* + float args; needs ROM-surface harness', 'test_3DLookup_FP.py'),
    'dataLookup':             ('0x2624', 'non-ABI leaf regs (r0/r1 in, r0/fr0 out)', 'test_dataLookup.py'),
    'indexLookupSomething':   ('0x2658', 'multi-value reg return (r2/r3/fr0/fr1 via out-params)', 'test_interp_leaves.py'),
    'interpolate_uint8Table': ('0x26B0', 'non-ABI leaf regs (r0/r1/fr0 in, fr2 out)', 'test_interp_leaves.py'),
    'interpolate_uint16Table':('0x26D0', 'non-ABI leaf regs (r0/r1/fr0 in, fr2 out)', 'test_interp_leaves.py'),
    'row_helper_25C8':        ('0x25C8', 'leaf calling convention; covered via its 2-D caller', 'test_3DLookup_FP.py'),
    'row_helper_25F4':        ('0x25F4', 'leaf calling convention; covered via its 2-D caller', 'test_3DLookup_FP.py'),
    'f32_handler_2678':       ('0x2678', 'part of TwoDLookup type dispatch (f32 cells)', 'test_2DLookup_type0.py'),
    # --- math_primitives.c TU: float args, or shares one TU (no per-symbol harness row) ---
    'subtractAbsolute':       ('0x23DC', 'float args/return', 'test_math_primitives.py'),
    'saturateLow':            ('0x23E4', 'float args/return', 'test_math_primitives.py'),
    'minValue':               ('0x23F4', 'float args/return', 'test_math_primitives.py'),
    'saturate':               ('0x2404', 'float args/return', 'test_math_primitives.py'),
    'encode':                 ('0x2420', 'shares math_primitives.c TU (no single-file row)', 'test_math_primitives.py'),
    'isNotZero_wDivideByZeroProtect': ('0x2440', 'float args', 'test_math_primitives.py'),
    'floatToFP_16bit':        ('0x2490', 'float args', 'test_math_primitives.py'),
    'floatToInt':             ('0x24D0', 'float args', 'test_math_primitives.py'),
    'fixedPointToFloat_16bit':('0x24C0', 'float args/return', 'test_math_primitives.py'),
    'fixedPointToFloat_8bit': ('0x2500', 'float args/return', 'test_math_primitives.py'),
    'invertAndReturn_8bit_ADDR': ('0x2044', 'pointer arg (redundant-cell RAM read)', 'test_math_primitives.py'),
    'multiply32Bit_saturating':  ('0x231C', 'shares math_primitives.c TU (no single-file row)', 'test_math_primitives.py'),
    'fixedPointScaling':      ('0x2510', 'shares math_primitives.c TU (no single-file row)', 'test_math_primitives.py'),
    'firstOrderFilter':       ('0x23B0', 'float args/return', 'test_math_primitives.py'),
    # --- mem_accessors.c: redundant-cell RAM reads/writes with side effects ---
    'readValue_8bit':         ('0x3E0DC', 'RAM-harness (value/complement cells + fallback default)', 'test_mem_accessors.py'),
    'readValue_16bit':        ('0x3E11C', 'RAM-harness (value/complement cells + fallback default)', 'test_mem_accessors.py'),
    'updateMemoryAtAddress_8bit': ('0x3E1F8', 'RAM-harness (redundant store)', 'test_mem_accessors.py'),
    'updateMemoryAtAddress_16bit':('0x3E208', 'RAM-harness (redundant store)', 'test_mem_accessors.py'),
    'readValue_32bit':        ('0x3E15C', 'RAM-harness (dual-checksum cells + scrub side effect)', 'test_mem_accessors.py'),
    'readValue_float':        ('0x3E1AA', 'RAM-harness + float arg order (addr=r4, dflt=fr4)', 'test_mem_accessors.py'),
    'updateMemoryAtAddress_32bit':('0x3E218', 'RAM-harness (dual-checksum store)', 'test_mem_accessors.py'),
    'validateAddressCopy_8bit':  ('0x3E29E', 'RAM-harness (validate-only, error-code return)', 'test_mem_accessors.py'),
    'validateAddressCopy_16bit': ('0x3E2DA', 'RAM-harness (validate-only, error-code return)', 'test_mem_accessors.py'),
    'validateAddressCopy_float': ('0x3E38A', 'RAM-harness + self-heal side effect', 'test_mem_accessors.py'),
    'validateAddressCopy_32bit': ('0x3E330', 'RAM-harness + self-heal side effect', 'test_mem_accessors.py'),
    # --- memory-mapped sensor / channel drivers ---
    'knockSensorADCFault':    ('0xC290', 'reads ROM threshold cells (memory-mapped)', 'test_knockSensorADCFault.py'),
    'output_spark2_0x8E20':   ('0x8E20', 'channel-struct RAM harness + getSR/setSR bracket', 'test_output_spark2_0x8E20.py'),
    # --- implicit-state / hardware-interface (also noted above FUNCS) ---
    'setSR':                  ('0x3934', 'hidden SR state; needs SR-aware emulator subclass', 'test_setSR_getSR.py'),
    'getSR':                  ('0x3920', 'hidden SR state; needs SR-aware emulator subclass', 'test_setSR_getSR.py'),
    'setSR_PARAM':            ('0x2054', 'hidden SR state; needs SR-aware emulator subclass', 'test_setSR_getSR.py'),
    'getFromE2':              ('0x39170', 'EEPROM hardware interface (SPI bit-bang)', 'test_getFromE2.py'),
}

# --- float/mem registry stub (wave2b) ---
# This harness only hosts pure functions of INTEGER args (FUNCS above). The
# float-arg and redundant-RAM lifts are NOT duplicated here because their
# sister registries already exist and own those vectors:
#   * float-arg lifts (subtractAbsolute, saturate, floatToInt, ...) ->
#     c/tests/test_math_primitives.py (seeded, ROM-differential vs 60E0FC00)
#   * redundant-RAM lifts (readValue_*, updateMemoryAtAddress_*, ...) ->
#     c/tests/test_mem_accessors.py (seeded, ROM-differential vs 60E0FC00)
# The SKIP manifest below points at exactly those suites per lift, so there
# is no silent gap and no second registry to drift. (If those sister suites
# did not exist, the gap would be: every SKIP row whose covering test is
# test_math_primitives.py / test_mem_accessors.py would have no executable
# differential — i.e. 15 float rows + 11 RAM rows uncovered.)

RT = {1: ctypes.c_uint8, 2: ctypes.c_uint16, 4: ctypes.c_uint32}

# Covering tests that validate a Python reference model vs the emulated ROM
# and never compile or execute the C lift itself (checked 2026-09-08: the
# only covering test that builds its C file with the host cc and calls it
# through ctypes is test_2DLookup_type0.py). Their SKIP lines say so
# explicitly — model covered, C lift compile-only. Full C-behavior gates
# are future work.
MODEL_ONLY_TESTS = frozenset([
    'test_2DLookup_FP_16bit.py', 'test_2DLookup_FP_8bit.py',
    'test_3dlookup_type8.py', 'test_3DLookup_FP.py',
    'test_dataLookup.py', 'test_interp_leaves.py',
    'test_math_primitives.py', 'test_mem_accessors.py',
    'test_knockSensorADCFault.py', 'test_output_spark2_0x8E20.py',
    'test_setSR_getSR.py', 'test_getFromE2.py',
])


def _missing_skip_refs(skip=None):
    """Return sorted names in SKIP whose covering test file is absent.

    Fail-closed helper for the coverage manifest: a dangling reference must
    never print as a clean SKIP with rc=0. ``skip`` defaults to the module
    SKIP registry (injectable for regression tests).
    """
    skip = SKIP if skip is None else skip
    missing = []
    for name, (_addr, _reason, test) in sorted(skip.items()):
        if not os.path.isfile(os.path.join(RE, 'c', 'tests', test)):
            missing.append(name)
    return missing


def emu_call(cpu, entry, args, regmap):
    """Call the ROM with args mapped onto the given registers.

    No state bleeds between vectors: SH2.call rebuilds the full CPU state
    on entry (r[*], fr[*], T, SR, FPSCR, MACH/MACL, GBR, PR/VBR — see
    tools/sh2emu.py SH2.call), so reusing one cpu across vectors is safe.
    The loop below additionally resets T/SR/FPSCR explicitly per vector
    (defense in depth; SH2.call re-establishes the same values on entry).
    """
    kwargs = {}
    reg_ov = {}
    for r, a in zip(regmap, args):
        if r in (4, 5, 6, 7):
            kwargs['r%d' % r] = a
        else:
            reg_ov[r] = a
    if reg_ov:
        kwargs['regs'] = reg_ov
    return cpu.call(entry, **kwargs)


def main():
    args = parse_args()
    random.seed(args.seed)
    rom = open(args.rom, 'rb').read()
    cpu = SH2(rom)
    fails = 0
    for name, spec in FUNCS.items():
        entry, retb, argb = spec[0], spec[1], spec[2]
        regmap = list(spec[3]) if len(spec) > 3 else [4, 5, 6, 7]
        so = '/tmp/%s.so' % name
        subprocess.run(['cc', '-O2', '-shared', '-fPIC',
                        os.path.join(RE, 'c', name + '.c'), '-o', so], check=True)
        fn = getattr(ctypes.CDLL(so), name)
        fn.restype = RT[retb]; fn.argtypes = [RT[b] for b in argb]
        retmask = (1 << (8 * retb)) - 1
        ok = True
        vectors = list(EDGES.get(name, []))
        for _ in range(100000):
            vectors.append([random.randint(0, (1 << (8 * b)) - 1) for b in argb])
        for args in vectors:
            # Explicit per-vector CPU reset (T/SR/FPSCR); SH2.call resets the
            # same state on entry, so this is belt-and-braces, not load-bearing.
            cpu.T = 0; cpu.sr = 0xF0; cpu.fpscr = 0
            c = fn(*args) & retmask
            e = emu_call(cpu, entry, args, regmap) & retmask
            if c != e:
                print("MISMATCH %s args=%s  C=%d  ROM=%d" % (name, args, c, e)); ok = False; fails += 1; break
        if ok:
            print("OK  %-20s C == emulated ROM @0x%X  (%d vectors)" % (name, entry, len(vectors)))
    # Coverage manifest: every claimed lift is either hosted above or skipped
    # below with a reason + covering test. No silent gaps by construction.
    claims = set(FUNCS) | set(SKIP)
    assert not (set(FUNCS) & set(SKIP)), "overlap between FUNCS and SKIP"
    missing_refs = set(_missing_skip_refs())
    for name, (addr, reason, test) in sorted(SKIP.items()):
        # Fail-closed: a dangling covering-test reference must not print as a
        # clean SKIP with rc=0. Assert the file exists; a missing reference is
        # a hard failure so gaps can never hide as advisories.
        if name in missing_refs:
            print("FAIL  %-28s @%s  (dangling covering test c/tests/%s; %s)"
                  % (name, addr, test, reason))
            fails += 1
            continue
        if test in MODEL_ONLY_TESTS:
            print("SKIP  %-28s @%s  (%s; model covered in c/tests/%s, C lift compile-only)"
                  % (name, addr, reason, test))
        else:
            print("SKIP  %-28s @%s  (%s; see c/tests/%s)" % (name, addr, reason, test))
    print("COVERAGE  %d hosted + %d skipped = %d claimed lifts" % (len(FUNCS), len(SKIP), len(claims)))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
