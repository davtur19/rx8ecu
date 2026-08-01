#!/usr/bin/env python3
"""
idamap.py — transfer the IDA (AI) function names from the 60E1D400 IDB onto the working
ROM 60E0FC00, by layout-invariant instruction signature (same idea as xmap_names.py but
the OTHER direction and a lower-confidence source).

Why: equinox hand-named 931 of 60E0FC00's 3459 functions; the rest are FUN_*. The 60E1D400
IDB (reversed in IDA with AI help) has ~2789 names. They are less reliable and may be a bit
wrong, but a plausible candidate name beats FUN_*. This fills only the *unnamed* slots and
never overrides an equinox name.

Rules:
- source names come from --src-syms (all rows); GENERIC/auto names (addr-suffixed,
  sub_/nullsub_/loc_/FUN_) are skipped — they add nothing over FUN_*.
- match only on a UNIQUE 1:1 signature (same function shape in both ROMs).
- output (--out) = dst symbols where: equinox `ghidra-hand` kept as-is; else a unique
  descriptive IDA match becomes source `ida-ai-xmap` (DUBIOUS); else FUN_*/ghidra-auto kept.
- --report writes a side-by-side equinox-vs-IDA comparison for functions both name.

Usage:
  python tools/idamap.py --src-rom roms/stock/60E1D400.bin --src-syms symbols/symbols_60E1D400_ida.csv \
      --dst-rom roms/stock/60E0FC00.bin --dst-syms symbols/symbols_60E0FC00.csv \
      --out <private-storage>/symbols_60E0FC00_idamap.csv --report <private-storage>/compare_equinox_vs_ida.csv
  (the `_idamap.csv` output and comparison report are kept in private storage, not shipped)
"""
import argparse, csv, re, sys
try:
    import capstone as C
except ImportError:
    sys.exit("need capstone: pip install capstone --break-system-packages")

_md = C.Cs(C.CS_ARCH_SH, C.CS_MODE_SH2 | C.CS_MODE_BIG_ENDIAN)
_GENERIC = re.compile(r'(_[0-9A-Fa-f]{4,6}$)|^(sub_|nullsub_|loc_|FUN_|unknown_|off_|byte_|word_|dword_)')


def is_generic(n):
    return bool(_GENERIC.search(n))


def sig(d, entry, limit, cap=64):
    out = []; a = entry; seen = False; extra = 0
    while a < limit and len(out) < cap:
        g = list(_md.disasm(d[a:a + 2], a))
        if not g:
            break
        i = g[0]; mn = i.mnemonic
        out.append((mn, re.sub(r'0x[0-9a-fA-F]+', '@', i.op_str)))
        if seen:
            extra += 1
        if extra >= 1:
            break
        if mn in ('rts', 'rte'):
            seen = True
        a += 2
    return tuple(out)


def load_syms(p):
    return [(int(r['addr'], 16), int(r['end'], 16), r['name'], r.get('source', ''), r.get('flag', ''))
            for r in csv.DictReader(open(p))]


def build_index(d, rows, min_sig, limit=140):
    from collections import defaultdict
    idx = defaultdict(list)
    for a, e, n, *_ in rows:
        s = sig(d, a, min(e, a + limit))
        if len(s) >= min_sig:
            idx[s].append((a, n))
    return idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src-rom', required=True)
    ap.add_argument('--src-syms', required=True)
    ap.add_argument('--dst-rom', required=True)
    ap.add_argument('--dst-syms', required=True)
    ap.add_argument('--min-sig', type=int, default=5)
    ap.add_argument('--out', required=True)
    ap.add_argument('--report')
    a = ap.parse_args()

    src_d = open(a.src_rom, 'rb').read()
    dst_d = open(a.dst_rom, 'rb').read()
    src = load_syms(a.src_syms)
    dst = load_syms(a.dst_syms)

    src_idx = build_index(src_d, src, a.min_sig)
    dst_idx = build_index(dst_d, dst, a.min_sig)
    xmap = {}
    for s, sl in src_idx.items():
        dl = dst_idx.get(s)
        if dl and len(sl) == 1 and len(dl) == 1:
            xmap[dl[0][0]] = sl[0][1]          # dst_addr -> ida name (any, incl generic)

    filled = 0
    both = []      # (addr, equinox_name, ida_name)
    w = csv.writer(open(a.out, 'w', newline='')); w.writerow(['addr', 'end', 'name', 'source', 'flag'])
    for a_, e_, n_, src_, fl_ in sorted(dst, key=lambda r: r[0]):
        ida = xmap.get(a_)
        if src_ == 'ghidra-hand':
            w.writerow(['0x%06X' % a_, '0x%06X' % e_, n_, src_, fl_])
            if ida and not is_generic(ida):
                both.append((a_, n_, ida))
        elif ida and not is_generic(ida):
            w.writerow(['0x%06X' % a_, '0x%06X' % e_, ida, 'ida-ai-xmap', 'DUBIOUS'])
            filled += 1
        else:
            w.writerow(['0x%06X' % a_, '0x%06X' % e_, n_, src_, fl_])

    hand = sum(1 for r in dst if r[3] == 'ghidra-hand')
    print('dst funcs: %d | equinox hand: %d | signature xmatches: %d | FUN_* filled w/ descriptive IDA: %d'
          % (len(dst), hand, len(xmap), filled))
    print('functions named by BOTH equinox and IDA: %d' % len(both))
    if a.report:
        rw = csv.writer(open(a.report, 'w', newline='')); rw.writerow(['addr', 'equinox_name', 'ida_ai_name'])
        for a_, en, ida in both:
            rw.writerow(['0x%06X' % a_, en, ida])
        print('wrote comparison ->', a.report)
    print('wrote ->', a.out)


if __name__ == '__main__':
    main()
