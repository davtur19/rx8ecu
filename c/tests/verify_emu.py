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
"""
import ctypes, os, random, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
RE = os.path.abspath(os.path.join(HERE, '..', '..'))          # repo root
sys.path.insert(0, os.path.join(RE, 'tools'))                 # sh2emu.py lives in tools/
from sh2emu import SH2

ROM = os.path.join(RE, 'roms', 'stock', '60E1D400.bin')

# name: (entry@60E1D400, ret_bytes, [arg_bytes,...])
# NOTE: setSR (0x3934), getSR (0x3920), and setSR_PARAM (0x2054) are NOT listed here
# because they operate on the SH-2 Status Register (SR), which is hidden implicit state,
# not a function argument.  They require stateful testing with an SR-aware emulator
# subclass (SRCPU in test_setSR_getSR.py) that models stc/ldc SR.  See that file and
# c/tests/test_setSR_getSR.py for their verification.
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
}

RT = {1: ctypes.c_uint8, 2: ctypes.c_uint16, 4: ctypes.c_uint32}


def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    fails = 0
    for name, (entry, retb, argb) in FUNCS.items():
        so = '/tmp/%s.so' % name
        subprocess.run(['cc', '-O2', '-shared', '-fPIC',
                        os.path.join(RE, 'c', name + '.c'), '-o', so], check=True)
        fn = getattr(ctypes.CDLL(so), name)
        fn.restype = RT[retb]; fn.argtypes = [RT[b] for b in argb]
        retmask = (1 << (8 * retb)) - 1
        ok = True
        for _ in range(100000):
            args = [random.randint(0, (1 << (8 * b)) - 1) for b in argb]
            c = fn(*args) & retmask
            regs = (args + [0, 0, 0, 0])[:4]
            e = cpu.call(entry, r4=regs[0], r5=regs[1], r6=regs[2], r7=regs[3]) & retmask
            if c != e:
                print("MISMATCH %s args=%s  C=%d  ROM=%d" % (name, args, c, e)); ok = False; fails += 1; break
        if ok:
            print("OK  %-20s C == emulated ROM @0x%X  (100k random)" % (name, entry))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
