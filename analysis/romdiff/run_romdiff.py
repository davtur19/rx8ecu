#!/usr/bin/env python3
"""
run_romdiff.py -- cross-ROM byte-level diff analysis for the RX-8 PCM firmware.

Reads the 9 stock 512KB SH-2E ROMs in roms/stock/ and produces, under
analysis/romdiff/:

  diff_matrix.csv                     all-pairs raw byte similarity (36 pairs)
  diff_matrix_blocks.csv              all-pairs shift-tolerant 16B-block content similarity
  diff_ranges.csv                     merged differing byte ranges per pair, classified
  cal_table_diffs_baseline.csv        per-known-table value deltas (baseline vs each ROM)
  clusters.txt                        clustering on raw and on block-content similarity
  REPORT.md                           human-readable report
  README.md                           how to regenerate

Two complementary similarity metrics
-----------------------------------
1. RAW byte diff at identical offsets (diff_matrix.csv).  High (~75-93%) for
   every non-identical pair because different builds relocate code/table
   blocks (variable shifts), so same-offset comparison mostly measures
   layout divergence, not content divergence.
2. BLOCK-content similarity (diff_matrix_blocks.csv): every 16-byte window of
   ROM A (stride 16) is looked up in the set of all 16-byte windows of ROM B
   (stride 1, i.e. shift-tolerant).  Measures how much actual content is
   shared regardless of relocation.  This is the metric used for variant
   clustering.

Classification bands are anchored on the RE baseline 60E1D400:
  header     0x00000-0x01FFF  (vectors/boot, below Denso checksum lo=0x2000)
  code       0x02000-0x6C26F  (checksummed code, incl. OBD handlers ~0x6BFE0)
  padding    0x6C270-0x6CEDF  (baseline 0xFF filler gap, code/table boundary)
  cal_data   0x6CEE0-0x7DAFF  (checksummed calibration tables region)
  tail       0x7DAFF-0x7FFFF  (checksum descriptor @0x7FB80 + trailing words)

Exact known-table classification uses symbols/cal_tables.csv (1210 addrs,
extracted from the 60E1D400 ROM).  Those addresses are only valid for
ROMs sharing the 60E1D400 table layout; other families relocate the
table block (cal_start measured per ROM: J-line 0x6CEE0, Z-line 0x6D300,
N3M5E ~0x715C0).
"""

import os
import sys
import csv
import itertools

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
ROM_DIR = os.path.join(ROOT, 'roms', 'stock')
SYM_DIR = os.path.join(ROOT, 'symbols')
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

BASELINE = '60E1D400.bin'
MIN_GAP = 8          # splice differing bytes separated by <= 8 identical bytes
GAP_LEN = 256        # min 0xFF run treated as a structural gap
CAL_HI = 0x7DAFF     # Denso checksum high bound
ROM_SIZE = 0x80000


def load_rom(name):
    with open(os.path.join(ROM_DIR, name), 'rb') as f:
        return f.read()


def load_cal_tables():
    addrs = set()
    names = {}
    with open(os.path.join(SYM_DIR, 'cal_tables.csv')) as f:
        for row in csv.DictReader(f):
            try:
                a = int(row['address'], 16)
            except (KeyError, ValueError):
                continue
            addrs.add(a)
            names.setdefault(a, row['name'])
    return addrs, names


def structural_gaps(rom, lo=0x2000, hi=0x7DB00, min_len=GAP_LEN):
    gaps = []
    i = lo
    while i < hi:
        if rom[i] == 0xFF:
            j = i
            while j < hi and rom[j] == 0xFF:
                j += 1
            if j - i >= min_len:
                gaps.append((i, j))
            i = j
        else:
            i += 1
    return gaps


def rom_layout(rom):
    """Per-ROM structural bands: (code_end, padding gaps, cal_lo).

    code_end = start of the first structural 0xFF gap after 0x2000 (the
    code->tables separator).  cal_lo = end of that same gap (start of the
    table block).  NOTE: for 60E32000 (N3M5E) no gap >= GAP_LEN exists; the
    fallback uses its largest >=64B gap (0x7144C, approximate).
    """
    gaps = structural_gaps(rom)
    if not gaps:
        gaps = structural_gaps(rom, min_len=64)
    if not gaps:
        return 0x60000, [], 0x60000
    code_end = gaps[0][0]
    cal_lo = gaps[0][1]
    return code_end, gaps, cal_lo


def diff_runs(a, b, min_gap=MIN_GAP):
    diffs = [i for i in range(min(len(a), len(b))) if a[i] != b[i]]
    if not diffs:
        return []
    runs = []
    s = p = diffs[0]
    for i in diffs[1:]:
        if i - p <= min_gap:
            p = i
        else:
            runs.append((s, p + 1))
            s = p = i
    runs.append((s, p + 1))
    return runs


def block_sim(a, b, step=16, a_stride=16):
    """% of A's (stride-a_stride) step-byte windows present anywhere in B."""
    bs = set(b[i:i + step] for i in range(0, len(b) - step + 1))
    hit = 0
    tot = 0
    for i in range(0, len(a) - step + 1, a_stride):
        tot += 1
        if a[i:i + step] in bs:
            hit += 1
    return 100.0 * hit / tot if tot else 0.0


class Classifier:
    """Anchors on baseline 60E1D400 bands; classifies diff addresses."""

    def __init__(self, baseline_rom, cal_addrs, cal_names):
        self.base = baseline_rom
        self.cal_addrs = cal_addrs
        self.cal_names = cal_names
        code_end, gaps, cal_lo = rom_layout(baseline_rom)
        self.code_end = code_end
        self.cal_lo = max(cal_lo, code_end)
        self.cal_hi = CAL_HI
        self.pad_ranges = gaps  # baseline 0xFF gaps => layout-shift padding

    def classify(self, addr):
        if addr < 0x2000:
            return 'header'
        if addr >= self.cal_hi:
            return 'tail'
        if addr in self.cal_addrs:
            return 'cal_table'
        if self.code_end <= addr < self.cal_lo:
            return 'padding'
        if self.cal_lo <= addr < self.cal_hi:
            return 'cal_data'
        return 'code'

    def class_breakdown(self, run):
        from collections import Counter
        s, e = run
        return Counter(self.classify(a) for a in range(s, e))

    def other_ff_frac(self, run, other):
        """Fraction of run bytes where baseline!=0xFF but other==0xFF (relocation)."""
        s, e = run
        total = e - s
        if total == 0:
            return 0.0
        return sum(1 for a in range(s, e)
                   if other[a] == 0xFF and self.base[a] != 0xFF) / total


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    rom_files = sorted(n for n in os.listdir(ROM_DIR) if n.endswith('.bin'))
    roms = {n: load_rom(n) for n in rom_files}
    if BASELINE not in roms:
        print(f'ERROR: baseline {BASELINE} missing', file=sys.stderr)
        sys.exit(1)

    cal_addrs, cal_names = load_cal_tables()
    clf = Classifier(roms[BASELINE], cal_addrs, cal_names)
    short = {n: n.replace('.bin', '') for n in rom_files}
    base_s = short[BASELINE]

    pairs = list(itertools.combinations(rom_files, 2))

    # ---------------- 1. raw byte diff matrix
    raw_rows = []
    for a, b in pairs:
        ba, bb = roms[a], roms[b]
        diff = sum(1 for x, y in zip(ba, bb) if x != y)
        raw_rows.append((a, b, ROM_SIZE, diff, round(100.0 * diff / ROM_SIZE, 4)))
    with open(os.path.join(OUT_DIR, 'diff_matrix.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['file1', 'file2', 'byte_totali', 'byte_diversi', 'percentuale'])
        w.writerows(raw_rows)

    # ---------------- 2. block-content similarity matrix (+ per-region)
    layout = {n: rom_layout(roms[n]) for n in rom_files}
    blk_rows = []
    code_sim = {}
    cal_sim = {}
    for a, b in pairs:
        ba, bb = roms[a], roms[b]
        whole = round(block_sim(ba, bb), 4)
        # region-restricted block sim (code & cal windows)
        a_ce, a_gaps, a_cl = layout[a]
        b_ce, b_gaps, b_cl = layout[b]
        a_code_hi = min(a_ce, 0x60000) if a_ce <= 0x60000 else a_ce
        # code region block similarity (over code windows of both)
        a_cs = block_sim(ba[0x2000:a_ce], bb[0x2000:b_ce])
        # cal region block similarity
        a_cal = block_sim(ba[a_cl:CAL_HI], bb[b_cl:CAL_HI])
        code_sim[(a, b)] = code_sim[(b, a)] = round(a_cs, 4)
        cal_sim[(a, b)] = cal_sim[(b, a)] = round(a_cal, 4)
        blk_rows.append((a, b, round(whole, 4), round(a_cs, 4), round(a_cal, 4)))
    with open(os.path.join(OUT_DIR, 'diff_matrix_blocks.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['file1', 'file2', 'content_similarity_pct',
                    'code_region_sim_pct', 'cal_region_sim_pct'])
        w.writerows(blk_rows)

    # ---------------- 3. diff ranges (classified)
    range_rows = []
    for a, b in pairs:
        for (s, e) in diff_runs(roms[a], roms[b]):
            brk = clf.class_breakdown((s, e))
            dom = brk.most_common(1)[0][0]
            hits = sorted(cal_names.get(a2, f'0x{a2:x}')
                          for a2 in range(s, e) if a2 in cal_addrs)
            ff = clf.other_ff_frac((s, e), roms[b]) if a == BASELINE else \
                 clf.other_ff_frac((s, e), roms[a]) if b == BASELINE else None
            range_rows.append({
                'pair': f'{short[a]}__vs__{short[b]}',
                'file1': short[a], 'file2': short[b],
                'start': f'0x{s:x}', 'end': f'0x{e:x}', 'length': e - s,
                'region': dom,
                'breakdown': ' '.join(f'{k}:{v}' for k, v in brk.most_common()),
                'other_ff_fraction': '' if ff is None else round(ff, 3),
                'n_cal_tables': len(hits),
                'cal_tables': '; '.join(hits[:8]) + ('; ...' if len(hits) > 8 else ''),
            })
    with open(os.path.join(OUT_DIR, 'diff_ranges.csv'), 'w', newline='') as f:
        cols = ['pair', 'file1', 'file2', 'start', 'end', 'length', 'region',
                'breakdown', 'other_ff_fraction', 'n_cal_tables', 'cal_tables']
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(range_rows)

    # ---------------- 4. known-table value deltas vs baseline
    cal_rows = []
    for other in rom_files:
        if other == BASELINE:
            continue
        for (s, e) in diff_runs(roms[BASELINE], roms[other]):
            for a in range(s, e):
                if a in cal_addrs:
                    vb = int.from_bytes(roms[BASELINE][a:a + 2], 'big')
                    vo = int.from_bytes(roms[other][a:a + 2], 'big')
                    cal_rows.append({
                        'pair': f'{base_s}__vs__{short[other]}',
                        'addr': f'0x{a:x}',
                        'table': cal_names.get(a, '?'),
                        'baseline_u16': f'0x{vb:04X}',
                        'other_u16': f'0x{vo:04X}',
                        'delta_signed': vb - vo,
                    })
    with open(os.path.join(OUT_DIR, 'cal_table_diffs_baseline.csv'), 'w', newline='') as f:
        cols = ['pair', 'addr', 'table', 'baseline_u16', 'other_u16', 'delta_signed']
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(cal_rows)

    # ---------------- 5. clustering
    write_clusters(raw_rows, blk_rows, rom_files)

    # ---------------- 6. report
    write_report(raw_rows, blk_rows, range_rows, cal_rows, layout, rom_files, short)

    # ---------------- 7. readme
    write_readme()
    # stdout summary
    print('RAW %diff matrix:')
    for a, b, t, d, p in raw_rows:
        print(f'  {short[a]:<20} vs {short[b]:<20} {p:7.3f}%')
    print('\nCONTENT similarity (block, shift-tolerant):')
    for a, b, w, cs, cal in blk_rows:
        print(f'  {short[a]:<20} vs {short[b]:<20} {w:6.2f}%  code {cs:6.2f}%  cal {cal:6.2f}%')
    print(f'\nDistinct known cal addresses differing vs baseline: {len(set(r["addr"] for r in cal_rows))}')
    print('Wrote:', ', '.join(sorted(os.listdir(OUT_DIR))))


def _group_at(names, sim_dict, threshold):
    edges = [(a, b) for a, b in itertools.combinations(names, 2)
             if sim_dict.get((a, b), 100.0) <= threshold]
    adj = {n: set() for n in names}
    for a, b in edges:
        adj[a].add(b); adj[b].add(a)
    seen = set(); out = []
    for n in names:
        if n in seen:
            continue
        comp = []; stack = [n]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x); comp.append(x)
            stack.extend(adj[x] - seen)
        out.append(sorted(comp))
    return out


def write_clusters(raw_rows, blk_rows, rom_files):
    names = rom_files
    raw_sim = {}
    for a, b, t, d, p in raw_rows:
        raw_sim[(a, b)] = raw_sim[(b, a)] = p
    blk_sim = {}
    for a, b, w, cs, cal in blk_rows:
        blk_sim[(a, b)] = blk_sim[(b, a)] = 100.0 - w  # distance
    with open(os.path.join(OUT_DIR, 'clusters.txt'), 'w') as f:
        f.write('RX-8 PCM stock-ROM clustering\n')
        f.write('(A) RAW byte distance (%diff at identical offsets) — dominated by layout relocation.\n')
        f.write('(B) CONTENT distance (100 - 16B-block content similarity) — relocation-tolerant.\n\n')
        f.write('(A) single-linkage merges on raw distance:\n')
        cl = [{n} for n in names]
        while len(cl) > 1:
            best = min((min(raw_sim[(x, y)] for x in ca for y in cb), i, j)
                       for i, ca in enumerate(cl) for j, cb in enumerate(cl) if i < j)
            d, i, j = best
            f.write(f'  merge @ {d:.3f}% : {"+".join(sorted(cl[i]))} <-> {"+".join(sorted(cl[j]))}\n')
            new = cl[i] | cl[j]
            cl = [c for k, c in enumerate(cl) if k != i and k != j] + [new]
        f.write('\n(B) single-linkage merges on content distance:\n')
        cl = [{n} for n in names]
        while len(cl) > 1:
            best = min((min(blk_sim[(x, y)] for x in ca for y in cb), i, j)
                       for i, ca in enumerate(cl) for j, cb in enumerate(cl) if i < j)
            d, i, j = best
            f.write(f'  merge @ {d:.3f}% : {"+".join(sorted(cl[i]))} <-> {"+".join(sorted(cl[j]))}\n')
            new = cl[i] | cl[j]
            cl = [c for k, c in enumerate(cl) if k != i and k != j] + [new]
        for th in (1.0, 5.0, 10.0, 20.0):
            f.write(f'\n(B) groups at content distance <= {th:.0f}%:\n')
            for g in _group_at(names, blk_sim, th):
                f.write('  ' + ', '.join(short_name(n) for n in g) + '\n')
        f.write('\nNote: content distance = 100 - block_content_similarity\n')


def short_name(n):
    return n.replace('.bin', '')


def write_report(raw_rows, blk_rows, range_rows, cal_rows, layout, rom_files, short):
    base_s = short[BASELINE]
    code_end, gaps, cal_lo = layout[BASELINE]

    # per-pair known-table stats (vs baseline)
    from collections import defaultdict
    cal_pair = defaultdict(lambda: {'total': 0, 'value': 0, 'equal': 0, 'ff': 0, 'maxd': 0})
    for r in cal_rows:
        d = cal_pair[r['pair']]
        d['total'] += 1
        if r['other_u16'] == '0xFFFF':
            d['ff'] += 1
        elif r['baseline_u16'] != r['other_u16']:
            d['value'] += 1
            d['maxd'] = max(d['maxd'], abs(int(r['delta_signed'])))
        else:
            d['equal'] += 1

    lines = []
    A = lines.append
    A('# RX-8 PCM Cross-ROM Diff Analysis')
    A('')
    A('9 stock ROMs, 512 KB (0x80000) each, Renesas SH-2E / SH7055, big-endian. '
      'Baseline: **60E1D400** (SW-N3J1EM000, the documented RE baseline).')
    A('')
    A('## Method')
    A('')
    A('- **Raw byte diff** at identical file offsets (36 pairs).')
    A('- **Block-content similarity**: 16-byte windows of A (stride 16) searched in '
      'the set of *all* 16-byte windows of B (stride 1). Tolerant to code/table '
      'relocation; this is the metric used to group variants.')
    A('- Differing bytes merged into ranges (identical runs of <=8 bytes spliced) '
      'and classified against baseline-anchored address bands:')
    A(f'  - `header`  0x00000-0x01FFF  vectors/boot (below Denso checksum lo=0x2000)')
    A(f'  - `code`    0x02000-0x{code_end-1:05X}  checksummed code (OBD handlers to ~0x6BFE0)')
    A(f'  - `padding` 0x{code_end:05X}-0x{cal_lo-1:05X}  baseline 0xFF filler gap(s)')
    A(f'  - `cal_data` 0x{cal_lo:05X}-0x{CAL_HI:05X}  calibration tables region')
    A(f'  - `tail`    0x{CAL_HI:05X}-0x7FFFF  checksum descriptor @0x7FB80 + trailing')
    A('- Known-table hits use `symbols/cal_tables.csv` (1210 addrs, 60E1D400 '
      'layout). Valid only for J-line builds; other families relocate the table block.')
    A('- All 9 ROMs share an identical 0x0-0x40 vector table (reset vector 0x8B8), '
      'so headers are aligned; divergence accumulates through the body.')
    A('')
    A('## 1. Similarity matrices')
    A('')
    A('### 1a. Raw byte diff, % differing at identical offsets')
    A('')
    A('| | ' + ' | '.join(short[f] for f in rom_files) + ' |')
    A('|---|' + '---|' * len(rom_files))
    rowmap = {}
    for a, b, t, d, p in raw_rows:
        rowmap.setdefault(a, {})[b] = p
        rowmap.setdefault(b, {})[a] = p
    for f in rom_files:
        A('| ' + short[f] + ' | ' + ' | '.join(
            '--' if g == f else f'{rowmap[f][g]:.3f}' for g in rom_files) + ' |')
    A('')
    A('High values everywhere (except 60E0FB00 vs 60E0FC00, 0.008%) because every '
      'build relocates code and table blocks; raw same-offset comparison is mostly '
      'a layout-divergence measure.')
    A('')
    A('### 1b. Content similarity (shift-tolerant 16B blocks), whole ROM / code region / cal region')
    A('')
    A('| pair | whole | code | cal |')
    A('|---|---|---|---|')
    for a, b, w, cs, cal in sorted(blk_rows, key=lambda r: -r[2]):
        A(f'| {short[a]} vs {short[b]} | {w:.2f}% | {cs:.2f}% | {cal:.2f}% |')
    A('')
    A('## 2. Per-ROM layout (0xFF-gap structure)')
    A('')
    A('| ROM | code_end | first gap | cal_lo | cal span |')
    A('|---|---|---|---|---|')
    for n in sorted(rom_files):
        ce, gaps, cl = layout[n]
        g = gaps[0] if gaps else None
        gs = f'0x{g[0]:05X}-0x{g[1]:05X}' if g else 'none'
        A(f'| {short[n]} | 0x{ce:05X} | {gs} | 0x{cl:05X} | {max(0, CAL_HI - cl)} |')
    A('')
    A('## 3. Clustering / variant families')
    A('')
    # content groups at <=10% and <=20%
    blk_sim = {}
    for a, b, w, cs, cal in blk_rows:
        blk_sim[(a, b)] = blk_sim[(b, a)] = 100.0 - w
    for th, lab in ((10.0, 'content distance <= 10%'), (20.0, 'content distance <= 20%'),
                    (35.0, 'content distance <= 35%')):
        groups = _group_at(rom_files, blk_sim, th)
        A(f'- **{lab}:**')
        for g in groups:
            A(f'  - ' + ' + '.join(short[n] for n in g))
    A('')
    A('Full merge tree in `clusters.txt`.')
    A('')
    A('## 4. Diff ranges vs baseline (classified)')
    A('')
    A('Cumulative over the 8 baseline comparisons; **raw diff at identical offsets** '
      '(so the `code` volume is mostly relocation smear, see other_ff_fraction).')
    A('')
    reg_stats = {}
    for r in range_rows:
        if r['file1'] != base_s and r['file2'] != base_s:
            continue
        d = reg_stats.setdefault(r['region'], {'bytes': 0, 'runs': 0, 'tables': 0})
        d['bytes'] += r['length']
        d['runs'] += 1
        d['tables'] += r['n_cal_tables']
    A('| region | runs | diff bytes | known cal tables hit |')
    A('|---|---|---|---|')
    for reg in sorted(reg_stats, key=lambda k: -reg_stats[k]['bytes']):
        d = reg_stats[reg]
        A(f'| {reg} | {d["runs"]} | {d["bytes"]} | {d["tables"]} |')
    A('')
    A('`other_ff_fraction` in diff_ranges.csv flags runs where the other ROM is 0xFF '
      'where baseline has content (relocated/layout-shift regions).')
    A('')
    A('### Boot region (0x40-0x1FFF) is shared across families')
    A('')
    A('Header-region byte diffs vs baseline: 60E1C500 = 0, 60E1B900 = 3, '
      '60E32000 = 3, but 60E0E500 = 3888, 60E0E700 = 3887, 60E0FB00/60E0FC00 = 3887, '
      '60E15120 = 3887. I.e. the boot/vector-handler block below the checksum start '
      'is byte-identical among {60E1D400, 60E1C500, 60E1B900, 60E32000} and differs '
      'as one block in the other five.')
    A('')
    A('## 5. Calibration-table differences')
    A('')
    A(f'{len(cal_rows)} rows / {len(set(r["addr"] for r in cal_rows))} distinct known-table '
      'addresses (60E1D400 map) differ vs baseline. Full u16 values + signed deltas in '
      '`cal_table_diffs_baseline.csv`. Per pair:')
    A('')
    A('| pair | total addrs | value diffs | equal | FF artifact | max|delta| |')
    A('|---|---|---|---|---|---|')
    for p in sorted(cal_pair):
        d = cal_pair[p]
        A(f'| {p} | {d["total"]} | {d["value"]} | {d["equal"]} | {d["ff"]} | {d["maxd"]} |')
    A('')
    A('Nearly every known table address differs in value vs the baseline — the '
      'calibration set itself is retuned between builds (rev-limit, sensor scaling, '
      '2D/3D maps). FF artifacts = addresses that are 0xFF in the other ROM '
      '(relocated table block, mostly Z-line). NOTE: cal_tables.csv addresses are '
      'u16-aligned entries of f32 tables; a u16 read from an f32 word shows half the '
      'value, so deltas are indicative, not the full numeric difference.')
    A('')
    A('## 6. Conclusions')
    A('')
    A('- **60E0FB00 vs 60E0FC00 are near-duplicate images** (raw 0.008% = 43 bytes; '
      'content 99.95%, code 100.00%, cal 99.76%). The 43 bytes split as: cal-ID '
      'char (0x2005 `B`→`C`), two ASCII string bytes (0x6D316, 0x6D34B, 0x6D35D), a '
      '2-byte boot field (0xFFC), a ~24-byte data block at 0x728D5 (ramp/serial-like '
      'values, not a plain string), a ~10-byte calibration-constant block at '
      '0x77B47-0x77CC7 (e.g. 0x00000007 vs 0x01250125; 0x07 vs 0x62 triples), and '
      'checksum fields (0x7FB01-0x7FB04, descriptor diff @0x7FB88, tail CRC '
      '@0x7FFF4).')
    A('- **No other pair is a near-duplicate.** The 8 remaining builds are distinct '
      'firmwares sharing 50-92% of their 16-byte content.')
    A('- **5 variant families (content-distance based):**')
    A('  1. **Z-line US 6-port MT** = 60E0FB00 + 60E0FC00 + 60E1B900 '
      '(pairwise content >=91%; calibration blocks ~99.7% identical).')
    A('  2. **J-line** = 60E1D400 + 60E0E500 + 60E1C500 (pairwise content 77-90%; '
      'E500-C500 89.8% is the closest non-Z pair).')
    A('  3. **60E0E700 (N3YLEE)** — JDM-flavoured N3YL build; closer to the J-line '
      'than to the Z-line but distinct (72-78% from J-line members).')
    A('  4. **60E15120 (internal SW-N3ZHEB000, tag _N3J1E)** — hybrid: cal content '
      '91.1% vs baseline (near-J-line calibration) but code closer to Z-line '
      '(61-70%).')
    A('  5. **60E32000 (N3M5E)** — structural outlier (later/different market build): '
      'no large 0xFF gap, code dense to ~0x7144C, cal block ~0x715C0 (5-50KB later '
      'than everyone else); lowest content similarity overall (50-60%).')
    A('- **Where the bytes differ (vs baseline):** dominated by the `code` band in '
      'raw terms, but most of that is relocation (other_ff_fraction near 1.0), not '
      'logic edits. The *true* tuning differences live in the `cal_data` band '
      '(0x6CE00-0x7DAFF): per-address table values differ nearly everywhere, and the '
      'table block itself is relocated per family (cal_lo 0x6C000-0x6D300, N3M5E '
      '~0x715C0).')
    A('- **Calibration vs code:** code-region content similarity (49-100%) is '
      'usually higher than cal-region similarity (42-100%) for a given pair — i.e. '
      'the code reading the tables is more conserved than the tables themselves.')
    A('')
    A('## 7. Open questions')
    A('')
    A('- Do the Z-line ROMs share a common relocated table layout (cal_lo ~0x6D300) '
      'or is relocation non-uniform? Needs a fresh mapscan per ROM.')
    A('- 60E15120 is tagged `_N3J1E` but carries Z-line software (SW-N3ZHEB000); '
      'its hybrid position (J-line calibration, Z-line code) should be confirmed '
      'against a per-ROM mapscan.')
    A('- What are the 0x728D5 and 0x77B47-0x77CC7 blocks that differ between '
      'FB00/FC00? (serial/anti-tamper vs real calibration constants).')
    A('- Baseline-anchored classification labels relocated code as `code`; a '
      'function-level (cross-reference / decompiler) diff would separate real logic '
      'edits from pure relocation.')
    A('')

    with open(os.path.join(OUT_DIR, 'REPORT.md'), 'w') as f:
        f.write('\n'.join(lines) + '\n')


def write_readme():
    with open(os.path.join(OUT_DIR, 'README.md'), 'w') as f:
        f.write('''# romdiff — cross-ROM diff analysis

Generated by `run_romdiff.py` (no repo files modified; read-only inputs).

## Regenerate

```bash
cd rx8ecu
python3 analysis/romdiff/run_romdiff.py
```

Python 3.8+, no third-party packages.

## Inputs (read-only)

- `roms/stock/*.bin` — 9 stock 512 KB SH-2E ROMs
- `symbols/cal_tables.csv` — 1210 calibration-table addresses (60E1D400 layout)

## Outputs

| file | contents |
|---|---|
| `REPORT.md` | methodology, matrices, clusters, region analysis, insights |
| `diff_matrix.csv` | all-pairs raw byte diff (file1, file2, byte_totali, byte_diversi, percentuale) |
| `diff_matrix_blocks.csv` | all-pairs shift-tolerant 16B-block content similarity (whole / code / cal) |
| `diff_ranges.csv` | per-pair merged differing ranges, classified header/code/padding/cal_data/cal_table/tail |
| `cal_table_diffs_baseline.csv` | per-known-table u16 deltas vs baseline 60E1D400 |
| `clusters.txt` | clustering on raw distance and on content distance |

## Two metrics

- **Raw %diff**: bytes differing at identical offsets. High for every distinct
  build because code/table blocks are relocated (layout divergence).
- **Content similarity**: % of A's 16B windows found anywhere in B
  (relocation-tolerant). Use this for variant grouping.

## Classification bands (anchored to baseline 60E1D400)

See REPORT.md. Exact known-table matching uses the 60E1D400 address map from
`cal_tables.csv`; Z-line (cal_lo 0x6D300) and N3M5E (~0x715C0) builds relocate
their table block, so `cal_table` hits are exact only for J-line-layout ROMs.

## Notes

- Denso checksum covers [0x2000, 0x7DAFF]; descriptor @0x7FB80.
- Only `analysis/romdiff/` is written; everything else is read-only input.
''')
    with open(os.path.join(OUT_DIR, 'README.md'), 'r'):
        pass


if __name__ == '__main__':
    main()
