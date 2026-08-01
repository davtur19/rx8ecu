#!/usr/bin/env python3
"""
opcode_audit.py — static audit of lifted C functions against tools/sh2emu.py.

Ground-truth partial risk: an untested code path that uses an opcode the emulator
does NOT implement stays invisible to the test suite (NotImplementedError is only
raised if that path is actually executed). This tool scans every ROM range that a
lifted function in c/*.c claims to cover, decodes every 16-bit word, and checks
each distinct opcode against the set the emulator can actually execute.

How the "implemented" set is derived (authoritative, not regex):
  the SH2 class in tools/sh2emu.py dispatches in _delayed() (branches) and
  _exec() (everything else). For every 16-bit opcode we instantiate the real
  class, reset register state, and call _delayed/_exec: any opcode that returns
  (or executes) without raising NotImplementedError is "implemented". This is
  exact — it probes the same code the tests run, including the intentionally
  unimplemented `trapa`.

Code vs data discrimination:
  src/60E1D400_annotated.s is a byte-exact re-assembly of the whole ROM
  (rom_rebuild.py): lines "\t.word 0xXXXX" are data, lines "\t<mnemonic> ..."
  are real instructions. Walking the file from address 0 maps every 2-byte slot
  to code|data, so a "non-implemented opcode" found in a code slot is a REAL gap,
  while one found only in data slots is noise (literal pools/tables are
  over-decoded by any linear disassembler).

Usage:
  python tools/opcode_audit.py                                  # auto: c/*.c functions
  python tools/opcode_audit.py --funcs 0x1825E,0x18CC0          # explicit list
  python tools/opcode_audit.py --bin roms/stock/60E1D400.bin --verbose

Output: per-function table (range, distinct opcodes, non-implemented in code,
non-implemented in data only) plus a final list of high-severity gaps with
address + instruction.
"""
import argparse
import importlib.util
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C_DIR = os.path.join(REPO, 'c')

RE_HEADER_ADDR = re.compile(r'Address:\s*0x([0-9A-Fa-f]{4,6})')
RE_HEADER_SIZE = re.compile(r'Size:\s*(\d+)\s*bytes')
RE_FILENAME_ADDR = re.compile(r'(?:0x)?([0-9A-Fa-f]{5})\.c$')
RE_ASM_HEADER = re.compile(r'^! --- (\S+)\s+0x([0-9a-fA-F]+)-(0x[0-9a-fA-F]+)')
RE_ASM_LABEL = re.compile(r'^L_[0-9a-f]{6}:$')
RE_ASM_FUNC_LABEL = re.compile(r'^\w+:$')
RE_ASM_WORD = re.compile(r'^\t\.word\s+0x[0-9a-fA-F]+\s*$')


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def extract_mnemonics_regex(emu_path):
    """Task-requested regex pass over sh2emu.py comments (informational only;
    the probe in EmulatorImplSet is the ground truth used for classification)."""
    names = set()
    pat = re.compile(r'#\s*([a-z][a-z0-9/\.]*|mov\.\w+|fmov\.\w+|ld[sc]\.\w+|st[sc]\.\w+)')
    for ln in open(emu_path):
        m = pat.search(ln)
        if m:
            t = m.group(1)
            if re.match(r'^[a-z][a-z0-9]*$', t) or re.match(r'^[a-z]+[\./][a-z0-9]+$', t):
                names.add(t)
    return names


class EmulatorImplSet:
    """Implemented-opcode set probed directly against tools/sh2emu.py dispatch."""

    def __init__(self, emu_path, rom_len):
        self.emu_path = emu_path
        self.mod = load_module(emu_path, 'sh2emu_probe')
        self.cpu = self.mod.SH2(b'\x00' * min(rom_len, 0x10000))
        self.cache = {}
        self.reason = {}

    def _reset(self):
        c = self.cpu
        c.ram = {}
        c.r = [0] * 16
        c.fr = [0.0] * 16
        c.pr = c.T = c.macl = c.mach = c.gbr = c.vbr = c.ssr = c.spc = 0
        c.sr = 0
        c.fpul = c.fpscr = 0
        c._Q = c._M = 0
        c.pc = 0

    def implemented(self, op):
        if op in self.cache:
            return self.cache[op]
        # delayed-branch dispatch
        self._reset()
        try:
            if self.cpu._delayed(op) is not None:
                self.cache[op] = True
                return True
        except Exception as e:
            self.cache[op] = False
            self.reason[op] = 'delayed raise %s' % type(e).__name__
            return False
        # main dispatch
        self._reset()
        try:
            self.cpu._exec(op, 0)
            self.cache[op] = True
            return True
        except NotImplementedError:
            self.cache[op] = False
            self.reason[op] = 'NotImplementedError'
            return False
        except Exception as e:
            self.cache[op] = False
            self.reason[op] = 'raise %s' % type(e).__name__
            return False

    def all_impl(self):
        """Probe every possible 16-bit opcode once (for summary stats)."""
        for op in range(0x10000):
            self.implemented(op)
        return sum(1 for v in self.cache.values() if v)


def build_asm_map(asm_path):
    """Walk annotated.s → {addr: 'code'|'data'} and {func_addr: (name,end)}."""
    kind = {}
    funcs = {}
    addr = 0
    other = 0
    for raw in open(asm_path):
        s = raw.rstrip('\n')
        m = RE_ASM_HEADER.match(s)
        if m:
            funcs[int(m.group(2), 16)] = (m.group(1), int(m.group(3), 16))
            continue
        if s == '\t.text' or not s.strip():
            continue
        if RE_ASM_LABEL.match(s) or RE_ASM_FUNC_LABEL.match(s):
            continue  # zero-size labels
        if RE_ASM_WORD.match(s):
            kind[addr] = 'data'
            addr += 2
            continue
        if s.startswith('\t'):
            kind[addr] = 'code'
            addr += 2
            continue
        other += 1  # unexpected line — ignore
    return kind, funcs, addr


def load_symbols(syms_path):
    """symbols_*.csv → {addr: (end, name)}."""
    m = {}
    if not syms_path or not os.path.exists(syms_path):
        return m
    import csv
    for r in csv.DictReader(open(syms_path)):
        try:
            a = int(r['addr'], 16)
            m[a] = (int(r['end'], 16), r['name'])
        except (KeyError, ValueError):
            pass
    return m


def derive_functions(c_dir):
    """From c/*.c headers (Address: + Size:) with filename fallback."""
    funcs = []
    for f in sorted(os.listdir(c_dir)):
        if not f.endswith('.c'):
            continue
        path = os.path.join(c_dir, f)
        head = open(path, 'rb').read(1200).decode('utf-8', 'replace')
        m = RE_HEADER_ADDR.search(head)
        addr = None
        if not m:
            fm = RE_FILENAME_ADDR.search(f)
            if fm:
                addr = int(fm.group(1), 16)
            else:
                continue
        else:
            addr = int(m.group(1), 16)
        ms = RE_HEADER_SIZE.search(head)
        size = int(ms.group(1)) if ms else None
        funcs.append((f[:-2], addr, size))
    return funcs


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--bin', default=os.path.join(REPO, 'roms/stock/60E1D400.bin'))
    ap.add_argument('--emu', default=os.path.join(REPO, 'tools/sh2emu.py'))
    ap.add_argument('--asm', default=os.path.join(REPO, 'src/60E1D400_annotated.s'))
    ap.add_argument('--syms', default=os.path.join(REPO, 'symbols/symbols_60E1D400_merged.csv'))
    ap.add_argument('--funcs', default=None,
                    help='comma list of function start addrs, e.g. 0x1825E,0x18CC0 (overrides auto-derive)')
    ap.add_argument('--c-dir', default=C_DIR)
    ap.add_argument('--verbose', action='store_true')
    a = ap.parse_args()

    for p in (a.bin, a.emu, a.asm):
        if not os.path.exists(p):
            sys.exit('missing file: %s' % p)

    rom = open(a.bin, 'rb').read()
    kind, asm_funcs, final_addr = build_asm_map(a.asm)
    syms = load_symbols(a.syms)
    if final_addr != len(rom):
        print('WARN: annotated.s walk ended at 0x%X but ROM is 0x%X bytes' % (final_addr, len(rom)))

    # ---- implemented set (probe the real emulator dispatch) ----
    emu = EmulatorImplSet(a.emu, len(rom))
    n_impl = emu.all_impl()
    print('emulator: %s  implemented opcodes: %d/65536  (%.1f%%)' %
          (a.emu, n_impl, 100.0 * n_impl / 65536))
    regex_names = extract_mnemonics_regex(a.emu)
    if a.verbose:
        print('mnemonics seen in sh2emu.py comments (regex, informational): %d' % len(regex_names))

    # ---- decoder: repo's own SH-2E disassembler (same decode families as emulator) ----
    dec = load_module(os.path.join(REPO, 'tools/disasm_sh2e.py'), 'disasm_sh2e')

    # ---- function list ----
    if a.funcs:
        funcs = []
        for tok in a.funcs.split(','):
            tok = tok.strip()
            if not tok:
                continue
            addr = int(tok, 16)
            end = syms.get(addr, (None, None))[0]
            if end is None:
                end = asm_funcs.get(addr, (None, None))[1]
            if end is None:  # next symbol after addr
                nxt = sorted(x for x in syms if x > addr)
                end = syms[nxt[0]][0] if nxt else addr + 0x100
            funcs.append(('ARG_%05X' % addr, addr, end - addr))
    else:
        funcs = derive_functions(a.c_dir)
        print('functions derived from %s: %d' % (a.c_dir, len(funcs)))

    # ---- audit each function ----
    print('%-42s %-14s %6s %6s %6s %5s | %6s %6s | %s' % (
        'function', 'range', 'words', 'code', 'data', 'distinct', 'NI-code', 'NI-data', ''))

    all_real = []   # (func, addr, opcode, mnemonic)
    bad_syms = []
    for name, addr, size in funcs:
        if addr >= len(rom):
            print('SKIP %-40s 0x%05X out of ROM' % (name, addr))
            continue
        # End of range: prefer symbol-table range (ground-truth function extent),
        # then header Size, then next symbol, else a default window.
        sym_end = syms.get(addr, (None, None))[0]
        asm_end = asm_funcs.get(addr, (None, None))[1]
        if sym_end is not None:
            end = min(sym_end, len(rom))
        elif asm_end is not None:
            end = min(asm_end, len(rom))
        elif size is not None:
            end = min(addr + size, len(rom))
        else:
            nxt = sorted(x for x in syms if x > addr)
            end = min(syms[nxt[0]][0], len(rom)) if nxt else min(addr + 0x100, len(rom))
        if a.verbose and addr in syms and size is not None and sym_end != addr + size:
            print('note: %s header size 0x%X..0x%X vs symbol 0x%X..0x%X' %
                  (name, addr, addr + size, addr, sym_end))
        n_words = n_code = n_data = 0
        distinct = set()
        ni_code = []
        ni_data = []
        for o in range(addr, end, 2):
            opcode = int.from_bytes(rom[o:o + 2], 'big')
            k = kind.get(o, 'data')
            mne, ops, _ = dec.disasm_one(opcode, o)
            distinct.add(mne)
            if k == 'code':
                n_code += 1
            else:
                n_data += 1
            if not emu.implemented(opcode):
                if k == 'code':
                    ni_code.append((o, opcode, mne, ops))
                else:
                    ni_data.append((o, opcode, mne, ops))
            n_words += 1
        n_ni_c, n_ni_d = len(ni_code), len(ni_data)
        if n_ni_c and n_words:
            all_real.append((name, addr, end, ni_code))
        print('%-42s 0x%05X-%05X %6d %6d %6d %5d | %6d %6d%s' % (
            name[:42], addr, end - 1, n_words, n_code, n_data, len(distinct),
            n_ni_c, n_ni_d, '' if n_words == 0 else ''))
        if a.verbose:
            for o, opc, mne, ops in ni_code:
                print('    REAL-GAP 0x%05X: %04X  %-10s %s' % (o, opc, mne, ops))
            for o, opc, mne, ops in ni_data:
                print('    data      0x%05X: %04X  %-10s %s' % (o, opc, mne, ops))

    # ---- final report ----
    print()
    print('=' * 78)
    print('HIGH SEVERITY: non-implemented opcodes in PURE CODE regions')
    print('=' * 78)
    if not all_real:
        print('  none — every opcode executed by these functions is emulated.')
    for name, addr, end, nis in all_real:
        for o, opc, mne, ops in nis:
            print('  0x%05X  %04X  %-10s %s   (in %s @ 0x%05X..0x%05X)' %
                  (o, opc, mne, ops, name, addr, end - 1))
    print()
    print('NOTE: opcodes in data-only slots are literal pools/tables over-decoded by the')
    print('linear disassembler and are NOT gaps. Recheck any HIGH entry in a real .s code')
    print('slot; a matching opcode in sh2emu.py means a stale annotation, not a gap.')


if __name__ == '__main__':
    main()
