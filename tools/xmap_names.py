#!/usr/bin/env python3
"""
xmap_names.py — transfer function names ACROSS ROMs by content signature.

The community's reliable hand analysis (equinox) is on 60E0FC00, but the other ROMs
(baseline 60E1D400, ...) have different code layouts, so names
cannot be moved by address. This matches functions by a layout-invariant signature —
the instruction mnemonics + operands, with absolute pool/branch addresses masked
(they differ across builds) — and transfers a name only on a UNIQUE 1:1 signature match.

Output: a merged symbols CSV for the destination ROM (addr,end,name,source,flag):
- uniquely matched  -> equinox name, source `ghidra-hand-xmap` (high confidence)
- otherwise         -> destination's own name/source kept (e.g. `ida-ai`, provisional)

Destination functions come from --dst-syms (a symbols CSV) or, with --derive, are
discovered from the ROM (bsr targets + pooled code pointers).

Usage:
  # baseline (has IDA symbols):
  python tools/xmap_names.py --src-rom roms/stock/60E0FC00.bin --src-syms symbols/symbols_60E0FC00.csv \
      --dst-rom roms/stock/60E1D400.bin --dst-syms symbols/symbols_60E1D400_ida.csv --out symbols/symbols_60E1D400_merged.csv
  # private (user's ECU, derive entries — not in the public repo; use repo-relative
  # or local paths for the private dump, which is intentionally not shipped):
  python tools/xmap_names.py --src-rom roms/stock/60E0FC00.bin --src-syms symbols/symbols_60E0FC00.csv \
      --dst-rom <dst.bin> --derive --out <symbols.csv>
"""
import argparse, csv, re, sys
try:
    import capstone as C
except ImportError:
    sys.exit("need capstone: pip install capstone --break-system-packages")

_md = C.Cs(C.CS_ARCH_SH, C.CS_MODE_SH2 | C.CS_MODE_BIG_ENDIAN)
_HEXAT = re.compile(r'0x[0-9a-fA-F]+')


def sig(d, entry, limit, cap=64):
    out = []; a = entry; seen = False; extra = 0
    while a < limit and len(out) < cap:
        g = list(_md.disasm(d[a:a + 2], a))
        if not g:
            break
        i = g[0]; mn = i.mnemonic
        out.append((mn, _HEXAT.sub('@', i.op_str)))
        if seen:
            extra += 1
        if extra >= 1:
            break
        if mn in ('rts', 'rte'):
            seen = True
        a += 2
    return tuple(out)


def load_syms(p):
    rows = []
    with open(p) as f:
        for r in csv.DictReader(f):
            rows.append((int(r['addr'], 16), int(r['end'], 16), r['name'],
                         r.get('source', ''), r.get('flag', '')))
    return rows


def derive_entries(d, lo, hi):
    ent = set()
    for off in range(lo, hi, 2):
        w = int.from_bytes(d[off:off + 2], 'big')
        if (w & 0xF000) == 0xB000:                       # bsr disp12
            disp = w & 0xFFF
            if disp & 0x800:
                disp -= 0x1000
            t = off + 4 + disp * 2
            if lo <= t < hi:
                ent.add(t)
        elif (w & 0xF000) == 0xD000:                     # mov.l @(disp,pc),Rn
            lit = ((off + 4) & ~3) + (w & 0xFF) * 4
            if lit + 4 <= len(d):
                val = int.from_bytes(d[lit:lit + 4], 'big')
                if lo <= val < hi and val % 2 == 0:
                    ent.add(val)
    ent = sorted(ent)
    return [(ent[i], ent[i + 1] if i + 1 < len(ent) else ent[i] + 128, 'FUN_%06x' % ent[i], 'derived', '')
            for i in range(len(ent))]


def build_index(d, rows, min_sig, limit=140):
    from collections import defaultdict
    idx = defaultdict(list)
    for a, e, n, *_ in rows:
        s = sig(d, a, min(e, a + limit))
        if len(s) >= min_sig:
            idx[s].append((a, n))
    return idx


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--src-rom', required=True)
    ap.add_argument('--src-syms', required=True, help='CSV with a source column; only ghidra-hand rows used')
    ap.add_argument('--dst-rom', required=True)
    ap.add_argument('--dst-syms', help='CSV of destination functions (addr,end,name,source,flag)')
    ap.add_argument('--derive', action='store_true', help='discover dst functions from the ROM')
    ap.add_argument('--code-lo', type=lambda x: int(x, 0), default=0x40)
    ap.add_argument('--code-hi', type=lambda x: int(x, 0), default=0x6CE00)
    ap.add_argument('--min-sig', type=int, default=4)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    src_d = open(a.src_rom, 'rb').read()
    dst_d = open(a.dst_rom, 'rb').read()
    src = [r for r in load_syms(a.src_syms) if r[3] == 'ghidra-hand']
    if a.dst_syms:
        dst = load_syms(a.dst_syms)
    elif a.derive:
        dst = derive_entries(dst_d, a.code_lo, a.code_hi)
    else:
        sys.exit('need --dst-syms or --derive')

    src_idx = build_index(src_d, src, a.min_sig)
    dst_idx = build_index(dst_d, dst, a.min_sig)
    # unique 1:1 signature matches
    xmap = {}                                            # dst_addr -> equinox name
    for s, sl in src_idx.items():
        dl = dst_idx.get(s)
        if dl and len(sl) == 1 and len(dl) == 1:
            xmap[dl[0][0]] = sl[0][1]

    w = csv.writer(open(a.out, 'w', newline='')); w.writerow(['addr', 'end', 'name', 'source', 'flag'])
    n_hi = 0
    for a_, e_, n_, src_, fl_ in sorted(dst, key=lambda r: r[0]):
        if a_ in xmap:
            w.writerow(['0x%06X' % a_, '0x%06X' % e_, xmap[a_], 'ghidra-hand-xmap', ''])
            n_hi += 1
        else:
            w.writerow(['0x%06X' % a_, '0x%06X' % e_, n_, src_, fl_])
    print('dst funcs: %d | equinox hand names available: %d | HIGH-confidence transfers: %d -> %s'
          % (len(dst), len(src), n_hi, a.out))


if __name__ == '__main__':
    main()
