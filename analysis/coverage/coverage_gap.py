#!/usr/bin/env python3
"""
coverage_gap.py — reproduce the "instruction-lift coverage" measurement of the
RX-8 ECU annotated assembly (src/<ROM>_annotated.s) and classify the
~6.4% of in-window words that are NOT lifted to instructions (the ".word gap").

Coverage definition (see src/ANNOTATED_SOURCES.md, tools/organize_src.py,
tools/rom_rebuild.py):
  * window = [0x800, 0x60000), 195,584 words (every even offset decoded
    independently; SH-2 instructions are all 2 bytes, so the sweep never drifts).
  * a word is "covered" iff the shipped annotated .s emits it as a real
    instruction line (after the capstone + disasm_sh2e decode and the
    GNU-as self-correction force loop).  Everything else in the window is
    emitted as `.word 0x....` and counts as uncovered.
  * declared coverage ~93.5-93.8% => uncovered ~6.2-6.5% (~12.4k words).

The shipped .s is the ground truth of the shipped coverage (it is the output
of the exact force loop), so this script parses the .s directly instead of
re-running sh-elf-as.

Classification of each uncovered (`.word`) in-window word:
  A) instr_forced   : the word DOES decode as a valid SH-2E instruction via
                      capstone or tools/disasm_sh2e.py, but was forced back to
                      `.word` because GNU-as cannot express it (mostly the
                      SH-2E 0x82nn/0x86nn mov.l @(disp,Rm) encodings).  Real
                      code, recoverable at zero cost.
  B) data (run)     : part of a >=2-word contiguous `.word` run classified by
                      analysis/data_regions_60E1D400.csv
                      (literal_pool / padding / jump_table / string /
                       unknown_data) when available.
  C) data (single)  : isolated `.word` among instructions -> pcrel-referenced
                      (pool_single), padding value (padding_single), or
                      unclassified (data_single_unref).
  D) suspicious     : vector-table entry (ROM 0x000..0x400) points into the
                      window but at an uncovered word (vector_handler_undecoded)
                      or a branch label sits on a data word (label_on_data).

Read-only: never modifies src/, tools/, roms/.  Writes only in this directory
(analysis/coverage/).  Does not touch tools/sh2emu.py or any existing file.

Usage:
  python3 coverage_gap.py                     # baseline 60E1D400 + summary for all 9 ROMs
  python3 coverage_gap.py 60E32000_N3M5E      # detailed classification for one ROM
  python3 coverage_gap.py --all-9             # detailed classification for all 9 (slow-ish)
"""
import argparse, csv, os, re, sys, types
from collections import Counter, defaultdict

try:
    import capstone as C
except ImportError:
    sys.exit("need capstone: pip install capstone --break-system-packages")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import disasm_sh2e as SH2E   # read-only import

WIN_LO, WIN_HI = 0x800, 0x60000
VEC_LO, VEC_HI = 0x000, 0x400

# ---------------------------------------------------------------------------
# 1. Parse the annotated .s back to per-address content
# ---------------------------------------------------------------------------

RE_FUNC_HEAD = re.compile(r'^! --- .*?  0x([0-9A-Fa-f]+)-0x[0-9A-Fa-f]+  \[.*?\] ---$')
RE_REGION = re.compile(r'^! \[([a-z_]+)\] 0x([0-9A-Fa-f]+)\.\.0x[0-9A-Fa-f]+ \(\d+ words\)$')
RE_CAL = re.compile(r'^! cal\[')
RE_LABEL = re.compile(r'^L_([0-9a-fA-F]{6}):$')
RE_FUNLABEL = re.compile(r'^[A-Za-z_.$][A-Za-z0-9_.$]*:$')
RE_WORD = re.compile(r'^\t\.word\s+0x([0-9a-fA-F]{1,4})\s*$')
RE_INSTR = re.compile(r'^\t([a-z][a-z0-9/.]*)\s*(.*)$')


def parse_src(path):
    """Return (instr, words, region, labels) dicts keyed by byte address.
    instr[a] = (mnemonic, op_str)   words[a] = word value
    region[a] = data_regions class (for the first word of a classified run)
    labels[a] = True if an L_xxxxxx / function label sits at a.
    """
    instr, words, region, labels = {}, {}, {}, {}
    addr = None
    pending = None
    with open(path) as f:
        for line in f:
            line = line.rstrip('\n')
            if line == '\t.text':
                addr = 0
                continue
            if not line:
                continue
            m = RE_FUNC_HEAD.match(line)
            if m:
                addr = int(m.group(1), 16)
                continue
            m = RE_REGION.match(line)
            if m:
                pending = m.group(1)
                continue
            if RE_CAL.match(line):
                continue
            if line.startswith('!'):
                continue
            m = RE_LABEL.match(line)
            if m:
                a = int(m.group(1), 16)
                addr = a
                labels[a] = True
                continue
            if RE_FUNLABEL.match(line):
                continue            # function label at the header addr already set
            m = RE_WORD.match(line)
            if m:
                v = int(m.group(1), 16)
                words[addr] = v
                if pending is not None:
                    region[addr] = pending
                    pending = None
                addr += 2
                continue
            m = RE_INSTR.match(line)
            if m:
                instr[addr] = (m.group(1), m.group(2).strip())
                addr += 2
                continue
            # ignore anything else (should not happen in this .s format)
    return instr, words, region, labels


# ---------------------------------------------------------------------------
# 2. Decoders
# ---------------------------------------------------------------------------

def make_decoders():
    md = C.Cs(C.CS_ARCH_SH, C.CS_MODE_SH2 | C.CS_MODE_BIG_ENDIAN)
    md.detail = False

    def cap(w, a):
        i = list(md.disasm(w.to_bytes(2, 'big'), a))
        return (i[0].mnemonic, i[0].op_str) if i else None

    def sh2e(w, a):
        mne, ops, _ = SH2E.disasm_one(w, a)
        if mne in ('unknown', 'fpu_unknown'):
            return None
        return (mne, ops)

    return cap, sh2e


# ---------------------------------------------------------------------------
# 3. Reference sets (branch + pcrel targets) from the .s
# ---------------------------------------------------------------------------

RE_LREF = re.compile(r'L_([0-9a-fA-F]{6})')


def refs_from_src(instr):
    branch_tgt, pcrel_tgt = set(), set()
    PCREL = {'mov.w', 'mov.l', 'mova'}
    for a, (mne, ops) in instr.items():
        for t in RE_LREF.findall(ops):
            tgt = int(t, 16)
            if mne in PCREL:
                pcrel_tgt.add(tgt)
            else:
                branch_tgt.add(tgt)
    return branch_tgt, pcrel_tgt


def vector_targets(rom):
    return [int.from_bytes(rom[i:i + 4], 'big') for i in range(VEC_LO, VEC_HI, 4)]


# ---------------------------------------------------------------------------
# 4. Classification of the uncovered set
# ---------------------------------------------------------------------------

def classify(rom_name, src_path, rom_path, detailed=True):
    d = open(rom_path, 'rb').read()
    instr, words, region, labels = parse_src(src_path)
    cap, sh2e = make_decoders()

    # named-function ranges (symbols) — read-only, best-effort
    funcs = []
    sym_path = os.path.join(ROOT, 'symbols', 'symbols_%s_merged.csv' % rom_name)
    if not os.path.exists(sym_path):
        sym_path = os.path.join(ROOT, 'symbols', 'symbols_%s.csv' % rom_name)
    if os.path.exists(sym_path):
        with open(sym_path, newline='') as f:
            for r in csv.DictReader(f):
                try:
                    funcs.append((int(r['addr'], 16), int(r['end'], 16), r['name']))
                except (ValueError, KeyError):
                    pass

    def infunc(a):
        for s, e, n in funcs:
            if s <= a < e:
                return n
        return None

    # per-window classification
    covered = []
    for a in range(WIN_LO, WIN_HI, 2):
        if a in instr:
            covered.append(a)
    uncovered = [a for a in range(WIN_LO, WIN_HI, 2) if a not in instr]
    nword = (WIN_HI - WIN_LO) // 2
    cov_pct = 100.0 * len(covered) / nword

    # decodable-but-forced?
    forced = []
    for a in uncovered:
        w = int.from_bytes(d[a:a + 2], 'big')
        dec = cap(w, a) or sh2e(w, a)
        if dec is not None:
            forced.append((a, w, dec[0], dec[1]))

    # data-region CSV (D400 only; optional for others)
    region_class = {}
    csv_path = os.path.join(ROOT, 'analysis', 'data_regions_60E1D400.csv')
    if os.path.exists(csv_path):
        with open(csv_path, newline='') as f:
            for r in csv.DictReader(f):
                s, e = int(r['addr_start']), int(r['addr_end'])
                cls = r['class']
                for a in range(s, e, 2):
                    region_class[a] = cls

    # clusters of contiguous uncovered words (labels do not split a cluster)
    clusters = []
    cur = []
    for a in uncovered:
        if cur and a != cur[-1] + 2:
            clusters.append(cur)
            cur = []
        cur.append(a)
    if cur:
        clusters.append(cur)

    # Data-like marker values that the linear sweep decodes as "instructions"
    # but that are in practice table members (0x0007 mul.l r0,r0 marker, 0x0002/
    # 0x0004/0x0005/0x0006 mov r0,@(r0,r0), 0xFFFF, 0x00xx...). Used to tell
    # "real stranded instruction" from "16-bit table half".
    MARK = set(range(0x20)) | {0xFFFF, 0xFFFE, 0xFFFD}

    def marker_neighbor(a):
        """True if either immediate neighbour of `a` is a data-marker value."""
        for off in (-2, +2):
            if 0 <= a + off < len(d) - 1:
                if int.from_bytes(d[a + off:a + off + 2], 'big') in MARK:
                    return True
        return False

    branch_tgt, pcrel_tgt = refs_from_src(instr)
    vec = vector_targets(d)
    vec_in_win = [v for v in vec if WIN_LO <= v < WIN_HI]
    vec_uncovered = [v for v in vec_in_win if v in set(uncovered)]

    # cluster-level classification
    cl_rows = []
    cat_counter = Counter()
    word_cat = {}
    for cl in clusters:
        a0, a1 = cl[0], cl[-1]
        vals = [int.from_bytes(d[a:a + 2], 'big') for a in cl]
        n = len(cl)
        ref_pcrel = [a for a in cl if a in pcrel_tgt]
        ref_branch = [a for a in cl if a in branch_tgt]
        lab = [a for a in cl if a in labels]
        csvcls = None
        if a0 in region_class:
            csvcls = region_class[a0]
        elif a0 in region:
            csvcls = region[a0]
        # cluster category
        if csvcls:
            cat = 'data:' + csvcls
        elif n == 1:
            a = cl[0]
            if a in pcrel_tgt:
                cat = 'data:pool_single'
            elif vals[0] in (0xFFFF, 0x0000):
                cat = 'data:padding_single'
            elif a in {x[0] for x in forced}:
                # decodes as a valid instruction -> either a real instruction
                # GNU-as can't express, or a 16-bit data-table half. A marker
                # or 0x82xx/0x86xx table pattern next to it => table member.
                v = vals[0]
                table_like = marker_neighbor(a) or (0x8200 <= v <= 0x86FF)
                cat = 'instr_forced' if not table_like else 'data:table_member'
            elif a in branch_tgt:
                cat = 'label_on_data'
            elif a in labels:
                cat = 'data:labelled_unref'
            else:
                cat = 'data:single_unref'
        else:
            # multi-word run without CSV class (only possible on non-D400 ROMs)
            if all(v in (0xFFFF, 0x0000) for v in vals):
                cat = 'data:padding_pattern'
            elif any(a in pcrel_tgt for a in cl):
                cat = 'data:pool_unclassified'
            else:
                cat = 'data:run_unclassified'
        for a in cl:
            word_cat[a] = cat
        cat_counter[cat] += n
        cl_rows.append({
            'start': a0, 'end': a1, 'words': n,
            'class': csvcls or (cat.split(':', 1)[1] if ':' in cat else cat),
            'category': cat,
            'pcrel_refs': len(ref_pcrel), 'branch_refs': len(ref_branch),
            'labels': len(lab),
            'fn': infunc(a0),
            'values': vals[:8],
        })

    # opcode histogram of the forced instructions
    forced_hist = Counter(x[2] for x in forced)
    forced_addr = {x[0] for x in forced}

    # vector-covered check
    vec_covered = [v for v in vec_in_win if v not in forced_addr and v in set(uncovered) or v in instr]

    summary = {
        'rom': rom_name,
        'covered_words': len(covered),
        'uncovered_words': len(uncovered),
        'nword': nword,
        'coverage_pct': round(cov_pct, 3),
        'forced_words': len(forced),
        'forced_hist': dict(forced_hist),
        'clusters': len(clusters),
        'category_words': dict(cat_counter),
        'category_clusters': dict(Counter(r['category'] for r in cl_rows)),
        'vec_in_window': len(vec_in_win),
        'vec_uncovered': [hex(v) for v in vec_uncovered],
        'vec_uncovered_count': len(vec_uncovered),
        'fn_words': sum(1 for a in uncovered if infunc(a) is not None),
        'fn_pct': round(100.0 * sum(1 for a in uncovered if infunc(a) is not None) / max(1, len(uncovered)), 2),
    }

    out = {
        'summary': summary,
        'clusters': sorted(cl_rows, key=lambda r: r['start']),
        'forced': [(hex(a), hex(w), m, o) for a, w, m, o in forced],
    }
    if detailed:
        out['word_cat'] = {hex(a): c for a, c in word_cat.items()}
    return out


# ---------------------------------------------------------------------------
# 5. Output helpers
# ---------------------------------------------------------------------------

def write_ranges_csv(path, res):
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['start', 'end', 'words', 'category', 'pcrel_refs', 'branch_refs',
                    'labels', 'function', 'sample_values'])
        for r in res['clusters']:
            w.writerow(['0x%X' % r['start'], '0x%X' % r['end'], r['words'],
                        r['category'], r['pcrel_refs'], r['branch_refs'],
                        r['labels'], r['fn'] or '',
                        ' '.join('%04X' % v for v in r['values'])])


def write_txt(path, res):
    s = res['summary']
    lines = []
    lines.append('# Uncovered words (".word" gap) in code window 0x800..0x60000 — %s' % s['rom'])
    lines.append('# covered=%d words  uncovered=%d words  coverage=%.3f%%' %
                 (s['covered_words'], s['uncovered_words'], s['coverage_pct']))
    lines.append('# forced-to-.word real instructions: %d' % s['forced_words'])
    lines.append('')
    lines.append('category,words,clusters')
    cats = sorted(s['category_words'])
    for c in cats:
        lines.append('%s,%d,%d' % (c, s['category_words'][c], s['category_clusters'].get(c, 0)))
    lines.append('')
    lines.append('FORCED INSTRUCTION MNEMONICS (real code, zero-cost recoverable):')
    for m, n in sorted(s['forced_hist'].items(), key=lambda x: -x[1]):
        lines.append('  %-12s %d' % (m, n))
    lines.append('')
    if s['vec_uncovered_count']:
        lines.append('SUSPICIOUS vector entries pointing at uncovered words: %s' %
                     ','.join(s['vec_uncovered']))
    lines.append('')
    lines.append('CLUSTERS (start,end,words,category,pcrel_refs,branch_refs,labels,function):')
    for r in res['clusters']:
        lines.append('0x%X,0x%X,%d,%s,%d,%d,%d,%s' % (r['start'], r['end'], r['words'],
                     r['category'], r['pcrel_refs'], r['branch_refs'], r['labels'],
                     r['fn'] or ''))
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')


def pretty(res):
    s = res['summary']
    print('== %s ==' % s['rom'])
    print('  coverage %.3f%% (%d/%d words covered; %d uncovered words = %.2f%%)'
          % (s['coverage_pct'], s['covered_words'], s['nword'], s['uncovered_words'],
             100.0 * s['uncovered_words'] / s['nword']))
    print('  forced real instructions (recoverable): %d' % s['forced_words'])
    for m, n in sorted(s['forced_hist'].items(), key=lambda x: -x[1])[:12]:
        print('      %-14s %d' % (m, n))
    print('  clusters: %d' % s['clusters'])
    tot = sum(s['category_words'].values()) or 1
    for c, n in sorted(s['category_words'].items(), key=lambda x: -x[1]):
        print('    %-28s %6d words (%5.2f%%)' % (c, n, 100.0 * n / tot))
    if s['vec_uncovered_count']:
        print('  !! %d vector entries point at uncovered words: %s' %
              (s['vec_uncovered_count'], ','.join(s['vec_uncovered'])))
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('roms', nargs='*', help='ROM stems to detail (default: 60E1D400)')
    ap.add_argument('--all-9', action='store_true', help='detail all 9 shipped ROMs')
    ap.add_argument('--outdir', default=os.path.dirname(os.path.abspath(__file__)))
    args = ap.parse_args()

    stock = os.path.join(ROOT, 'roms', 'stock')
    src = os.path.join(ROOT, 'src')
    all_roms = sorted(f[:-len('_annotated.s')] for f in os.listdir(src)
                      if f.endswith('_annotated.s'))

    detail = set(args.roms) or {'60E1D400'}
    if args.all_9:
        detail = set(all_roms)

    all_summaries = []
    for rom in all_roms:
        rom_path = os.path.join(stock, rom + '.bin')
        if not os.path.exists(rom_path):
            continue
        src_path = os.path.join(src, rom + '_annotated.s')
        res = classify(rom, src_path, rom_path, detailed=(rom in detail))
        all_summaries.append(res)
        if rom in detail:
            outbase = os.path.join(args.outdir, 'uncovered_%s' % rom)
            write_ranges_csv(outbase + '.csv', res)
            write_txt(outbase + '.txt', res)
        pretty(res)

    # summary table
    print('SUMMARY (all ROMs):')
    print('%-18s %8s %9s %8s %7s %7s' % ('rom', 'coverage%', 'uncovered', 'forced', 'clusters', 'vec?un'))
    for res in all_summaries:
        s = res['summary']
        print('%-18s %8.3f %9d %8d %7d %7d' % (s['rom'], s['coverage_pct'],
              s['uncovered_words'], s['forced_words'], s['clusters'],
              s['vec_uncovered_count']))


if __name__ == '__main__':
    main()
