#!/usr/bin/env python3
"""
common.py — shared machinery for the restored-source equivalence harnesses.

Every harness in this directory follows the same Track-A pattern as
c/tests/verify_emu.py:

  1. build the restored sources + tests/host_oracle.c into one host binary
     (system gcc; NO cross toolchain needed — equivalence is behavioural);
  2. generate N random (seeded) input vectors;
  3. execute the ACTUAL ROM bytes of the function under test with
     tools/sh2emu.py on the very same vectors;
  4. feed the same vectors to the host oracle and compare the results.

All harnesses are read-only w.r.t. the rest of the repo: they only read the
ROM and the tools; the compiled oracle goes to /tmp.
"""
import os
import random
import subprocess
import sys

# restored/samples
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# rx8ecu (repo root)
ROOT = os.path.dirname(os.path.dirname(SAMPLES))
# tools/ must be importable for sh2emu
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2  # noqa: E402

ROM_PATH = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
BUILD_DIR = os.path.join('/tmp', 'opencode', 'rx8-restored-build')

SRC_FILES = ['rx8_s32_saturate.c', 'rx8_immo_seed_mixer.c', 'rx8_index_table.c']
ORACLE_SRC = os.path.join(SAMPLES, 'tests', 'host_oracle.c')


def build_oracle(cc='cc'):
    """Compile the restored sources + host_oracle.c into a host binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'host_oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           ORACLE_SRC] + [os.path.join(SAMPLES, 'src', f) for f in SRC_FILES]
    cmd += ['-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def run_oracle(oracle, vectors):
    """Feed vectors (list of string lines) to the oracle, return output lines."""
    proc = subprocess.run([oracle], input='\n'.join(vectors) + '\n',
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError('host oracle failed:\n' + proc.stderr)
    lines = proc.stdout.splitlines()
    if len(lines) != len(vectors):
        raise RuntimeError(
            'oracle produced %d outputs for %d vectors' % (len(lines), len(vectors)))
    return lines


def load_cpu():
    """Fresh SH-2E emulator over the stock ROM (read-only)."""
    with open(ROM_PATH, 'rb') as f:
        return SH2(f.read())


def make_rng(seed):
    return random.Random(seed)


def report(name, addr, n, mismatches, edges=None):
    if mismatches:
        print('FAIL %-22s @0x%X  %d mismatch(es)' % (name, addr, len(mismatches)))
        for m in mismatches[:5]:
            print('    ' + str(m))
        sys.exit(1)
    extra = '  (+%d edge vectors)' % edges if edges else ''
    print('OK  %-22s host-C == emulated ROM @0x%X  (%d random%s)'
          % (name, addr, n, extra))
