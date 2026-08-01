#!/usr/bin/env python3
"""
organize_src.py — emit an *organized, annotated* reassemblable source for the ROM.

Same byte-exact whole-ROM reassembly as rom_rebuild.py, but the flat `.s` is turned
into navigable source: each function gets a header comment + a named label (from
symbols/), and calibration-table addresses get a comment (from symbols/cal_tables.csv).
The bytes are unchanged, so `cmp` against the ROM still matches.

Decoding mirrors rom_rebuild.py: capstone (SH-2, big-endian) first; every word capstone
fails to decode is handed to tools/disasm_sh2e.py (disasm_one), so the SH-2E families
capstone misses (FPU, fpul/fpscr, 0x82xx/0x86xx mov.l disp, SSR/SPC, ...) are emitted
as real mnemonics instead of `.word`. The self-correction loop forces any word that
GNU-as rejects or that re-encodes to different bytes back to raw `.word`, so the
result is byte-exact by construction.

Optional `--regions CSV` (analysis/data_regions_60E1D400.csv, D400 only): appends one
lightweight `! [class] 0xADDR..0xADDR (N words)` comment per `.word` run start.

Name provenance / confidence is carried in the header tag, e.g. `[ida-ai]` — these
names are AI-derived (IDA) and to be treated as PROVISIONAL until cross-checked
against the hand-annotated Ghidra work. Anything flagged `rotary_check` referenced a
piston-engine concept and must be re-examined (this is a rotary — no cams/poppet valves).

Run from the repo root. Usage:
  python tools/organize_src.py --rom roms/stock/60E1D400.bin \
      --symbols symbols/symbols_60E1D400_merged.csv --cal symbols/cal_tables.csv --out src/60E1D400_annotated.s
  python tools/organize_src.py --rom roms/stock/60E1D400.bin \
      --symbols symbols/symbols_60E1D400_merged.csv --cal symbols/cal_tables.csv \
      --regions analysis/data_regions_60E1D400.csv --out src/60E1D400_annotated.s
"""
import argparse, csv, os, re, subprocess, sys, types
try:
    import capstone as C
except ImportError:
    sys.exit("need capstone: pip install capstone --break-system-packages")

import disasm_sh2e as SH2E

PCREL = {'mov.l', 'mov.w', 'mova'}
BR = {'bra', 'bsr', 'bt', 'bf', 'bt/s', 'bf/s'}


def _tgt(op):
    m = re.search(r'0x([0-9a-fA-F]+)', op)
    return int(m.group(1), 16) if m else None


def _sh2e_fallback(w, a):
    """Decode one word with disasm_sh2e (capstone returned None for it).
    Returns a capstone-shaped instruction (mnemonic/op_str) or None."""
    mne, ops, _ = SH2E.disasm_one(w, a)
    if mne in ('unknown', 'fpu_unknown'):
        return None
    return types.SimpleNamespace(mnemonic=mne, op_str=ops)


def _san(n, used, addr):
    s = re.sub(r'[^A-Za-z0-9_]', '_', n)
    if not s or s[0].isdigit():
        s = '_' + s
    if s in used:
        s = '%s_%06x' % (s, addr)
    used.add(s)
    return s


def load_symbols(path):
    funcs = {}
    with open(path, newline='') as f:
        used = set()
        for r in csv.DictReader(f):
            a = int(r['addr'], 16)
            funcs[a] = {
                'name': _san(r['name'], used, a),
                'raw': r['name'],
                'end': int(r['end'], 16),
                'src': r.get('source', ''),
                'flag': r.get('flag', ''),
            }
    return funcs


def load_cal(path):
    cal = {}
    if not path or not os.path.exists(path):
        return cal
    with open(path, newline='') as f:
        for r in csv.DictReader(f):
            try:
                cal.setdefault(int(r['address'], 16), (r['name'], r.get('src', '')))
            except ValueError:
                pass
    return cal


def load_regions(path):
    """CSV rows (addr_start,addr_end,word_count,class,notes); decimal byte offsets."""
    reg = {}
    if not path or not os.path.exists(path):
        return reg
    with open(path, newline='') as f:
        for r in csv.DictReader(f):
            try:
                a = int(r['addr_start'])
                reg[a] = (r['class'], int(r['addr_end']), int(r['word_count']))
            except (ValueError, KeyError):
                pass
    return reg


def build(rom, symbols, cal, regions, out, code_lo, code_hi, win_lo, win_hi, max_iter=16):
    d = open(rom, 'rb').read(); N = len(d)
    md = C.Cs(C.CS_ARCH_SH, C.CS_MODE_SH2 | C.CS_MODE_BIG_ENDIAN)
    dis = {}
    for a in range(code_lo, code_hi, 2):
        w = int.from_bytes(d[a:a + 2], 'big')
        i = (list(md.disasm(d[a:a + 2], a)) or [None])[0]
        if i is None:
            i = _sh2e_fallback(w, a)          # capstone miss -> disasm_sh2e
        dis[a] = i
    labels = set()
    for a, i in dis.items():
        if i and (i.mnemonic in BR or i.mnemonic in PCREL):
            t = _tgt(i.op_str)
            if t is not None and 0 <= t < N:
                labels.add(t)
    force = set()

    def emit():
        out_lines = ['\t.text']; meta = [None]
        a = 0
        while a < N:
            if a in symbols:
                s = symbols[a]
                tag = s['src'] + (' ' + s['flag'] if s['flag'] else '')
                out_lines.append('')
                out_lines.append('! --- %s  0x%X-0x%X  [%s] ---' % (s['raw'], a, s['end'], tag))
                out_lines.append('%s:' % s['name']); meta += [None, None, None]
            if a in cal:
                out_lines.append('! cal[%s]: %s  @0x%X' % (cal[a][1], cal[a][0], a)); meta.append(None)
            if a in labels:
                out_lines.append('L_%06x:' % a); meta.append(None)
            i = dis.get(a) if code_lo <= a < code_hi else None
            is_word = True
            if i is not None and a not in force:
                op = i.op_str
                if i.mnemonic in PCREL or i.mnemonic in BR:
                    t = _tgt(op)
                    if t is not None and 0 <= t < N:
                        op = re.sub(r'0x[0-9a-fA-F]+', 'L_%06x' % t, op, count=1)
                        is_word = False
                    elif t is not None:                 # unresolved target -> raw
                        is_word = True
                    else:
                        is_word = False
                else:
                    is_word = False
            if is_word:
                if a in regions:
                    r = regions[a]
                    out_lines.append('! [%s] 0x%X..0x%X (%d words)' % (r[0], a, r[1], r[2]))
                    meta.append(None)
                out_lines.append('\t.word 0x%04x' % int.from_bytes(d[a:a + 2], 'big')); meta.append(a)
            else:
                out_lines.append(('\t%s %s' % (i.mnemonic, op)).rstrip()); meta.append(a)
            a += 2
        return '\n'.join(out_lines) + '\n', meta

    for _ in range(max_iter):
        s, meta = emit(); open(out, 'w').write(s)
        r = subprocess.run(['sh-elf-as', '-big', out, '-o', out + '.o'], capture_output=True, text=True)
        if r.returncode:
            errs = {meta[int(m.group(1)) - 1] for m in re.finditer(r':(\d+): Error', r.stderr)
                    if 0 <= int(m.group(1)) - 1 < len(meta) and meta[int(m.group(1)) - 1] is not None}
            if not errs:
                sys.exit('as failed (unmapped):\n' + r.stderr[:800])
            force |= errs; continue
        subprocess.run(['sh-elf-ld', '-Ttext=0x0', '-e', '0x0', '-o', out + '.elf', out + '.o'], check=True)
        subprocess.run(['sh-elf-objcopy', '-O', 'binary', '-j', '.text', out + '.elf', out + '.bin'], check=True)
        got = open(out + '.bin', 'rb').read()
        if got == d:
            nfn = sum(1 for a in symbols if a < N and a % 2 == 0)   # emitted `! ---` headers
            wlo, whi = max(code_lo, win_lo), min(code_hi, win_hi)
            nword = max(0, (whi - wlo) // 2)
            lifted = sum(1 for a in range(wlo, whi, 2)
                         if dis[a] is not None and a not in force)
            return True, nfn, len(cal), len(force), lifted, nword
        newf = {(k & ~1) for k in range(min(len(got), N)) if got[k] != d[k] and code_lo <= (k & ~1) < code_hi}
        if not (newf - force):
            sys.exit('stall: diffs outside code region')
        force |= newf
    sys.exit('did not converge')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', default='roms/stock/60E1D400.bin')
    ap.add_argument('--symbols', default='symbols/symbols_60E1D400_merged.csv')
    ap.add_argument('--cal', default='symbols/cal_tables.csv')
    ap.add_argument('--regions', default='analysis/data_regions_60E1D400.csv', help='data-regions CSV (D400 only); one [class] comment per .word run start')
    ap.add_argument('--out', default='src/rom.s')
    ap.add_argument('--code-lo', type=lambda x: int(x, 0), default=0x40)
    ap.add_argument('--code-hi', type=lambda x: int(x, 0), default=0x6CE00)
    ap.add_argument('--win-lo', type=lambda x: int(x, 0), default=0x800, help='coverage window start (inclusive)')
    ap.add_argument('--win-hi', type=lambda x: int(x, 0), default=0x60000, help='coverage window end (exclusive)')
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    funcs = load_symbols(a.symbols); cal = load_cal(a.cal); regions = load_regions(a.regions)
    ok, nfn, ncal, raw, lifted, nword = build(a.rom, funcs, cal, regions, a.out,
                                              a.code_lo, a.code_hi, a.win_lo, a.win_hi)
    if ok:
        print('BYTE-EXACT annotated source: %s' % a.out)
        print('functions labeled: %d | cal tables commented: %d | raw fallbacks: %d' % (nfn, ncal, raw))
        print('coverage window 0x%x..0x%x: lifted to instructions %d/%d words (%.1f%%)'
              % (a.win_lo, a.win_hi, lifted, nword, 100.0 * lifted / nword))


if __name__ == '__main__':
    main()
