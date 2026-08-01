#!/usr/bin/env python3
"""
callgraph.py <rom> --syms symbols/symbols_60E0FC00.csv [--out-csv symbols/callgraph.csv] [--out-md docs/subsystems/OVERVIEW.md]

Whole-ROM static call graph for the RX-8 PCM (SH-2E). For every function boundary in
the symbol table it extracts caller->callee edges by two mechanisms:

  * bsr  (0xB___)               PC-relative direct call; target = pc+4+disp*2
  * mov.l @(disp,pc),Rn (0xD__) literal-pool load whose 32-bit value is a function
                                start — the address SHC pools for a subsequent `jsr @Rn`.

An edge is recorded only when the resolved target is itself a known function start, so
data/pointer noise is filtered. Output:
  - CSV of edges (caller,callee,kind)
  - OVERVIEW.md: coverage stats, the most-called functions (hubs = core primitives),
    subsystem grouping over equinox's hand names, and a doc-coverage line.

Also prints a priority worklist: equinox-named, undocumented functions, most-called first.
"""
import argparse, csv, os, re, struct
from collections import defaultdict


def load_syms(p):
    funcs = {}   # addr -> (end, name, source)
    for r in csv.DictReader(open(p)):
        try:
            a = int(r['addr'], 16)
        except Exception:
            continue
        e = None
        try:
            e = int(r['end'], 16)
        except Exception:
            pass
        funcs[a] = (e, r.get('name', ''), r.get('source', ''))
    return funcs


def func_end(funcs, a, starts):
    e = funcs[a][0]
    if e and e > a:
        return e
    i = starts.index(a)
    return starts[i + 1] if i + 1 < len(starts) else a + 0x100


def build(rom, funcs):
    starts = sorted(funcs)
    fset = set(starts)
    edges = set()          # (caller, callee, kind)
    for a in starts:
        e = func_end(funcs, a, starts)
        b = a
        while b + 1 < e and b + 1 < len(rom):
            w = (rom[b] << 8) | rom[b + 1]
            top = w >> 12
            if top == 0xB:                                   # bsr disp12
                d = w & 0xFFF
                if d & 0x800:
                    d -= 0x1000
                tgt = (b + 4 + d * 2) & 0xFFFFFFFF
                if tgt in fset and tgt != a:
                    edges.add((a, tgt, 'bsr'))
            elif top == 0xD:                                 # mov.l @(disp,pc),Rn
                lit = ((b + 4) & ~3) + (w & 0xFF) * 4
                if lit + 4 <= len(rom):
                    val = int.from_bytes(rom[lit:lit + 4], 'big')
                    if val in fset and val != a:
                        edges.add((a, val, 'ref'))
            b += 2
    return starts, edges


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--syms', required=True)
    ap.add_argument('--out-csv', default='symbols/callgraph.csv')
    ap.add_argument('--out-md', default='docs/subsystems/OVERVIEW.md')
    ap.add_argument('--docs', default='docs/functions')
    ap.add_argument('--worklist', type=int, default=0, help='print N top undocumented equinox funcs')
    a = ap.parse_args()

    rom = open(a.rom, 'rb').read()
    funcs = load_syms(a.syms)
    starts, edges = build(rom, funcs)

    callees = defaultdict(set)   # callee -> callers
    callers = defaultdict(set)   # caller -> callees
    for c, t, k in edges:
        callees[t].add(c)
        callers[c].add(t)

    # write edge CSV
    with open(a.out_csv, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['caller_addr', 'caller_name', 'callee_addr', 'callee_name', 'kind'])
        for c, t, k in sorted(edges):
            w.writerow(['0x%X' % c, funcs[c][1], '0x%X' % t, funcs[t][1], k])

    # doc coverage
    docn = set()
    if os.path.isdir(a.docs):
        for fn in os.listdir(a.docs):
            if fn.endswith('.md') and fn != 'README.md':
                docn.add(re.sub(r'[^a-z0-9]', '', os.path.splitext(fn)[0].lower()))
    def norm(n): return re.sub(r'[^a-z0-9]', '', n.lower())
    hand = [x for x in starts if funcs[x][2] == 'ghidra-hand']
    documented = [x for x in hand if norm(funcs[x][1]) in docn]

    # hubs = most-called
    hubs = sorted(starts, key=lambda x: len(callees[x]), reverse=True)

    # subsystem grouping over equinox names
    SUB = {
        'fuel/injection': ['fuel', 'inject', 'injector', 'pulse', 'latency'],
        'ignition/spark': ['ignit', 'spark', 'coil', 'dwell', 'timing'],
        'air/throttle':   ['throttle', 'tps', 'pedal', 'maf', 'airflow', 'iat', 'baro', 'map', 'vis', 'tumble'],
        'sensors/adc':    ['sensor', 'adc', 'o2', 'lambda', 'coolant', 'temp', 'knock', 'crank', 'cam', 'rpm', 'volt'],
        'idle/oil/emiss': ['idle', 'oil', 'omp', 'meter', 'purge', 'egr', 'evap', 'cat', 'pump', 'vac'],
        'CAN/comm/UDS':   ['can', 'uds', 'iso', 'kwp', 'diag', 'dtc', 'msg', 'tx', 'rx', 'serial'],
        'math/lookup':    ['lookup', 'interp', 'filter', 'saturate', 'clamp', 'fixedpoint', 'scale', 'calc', 'table'],
        'sched/init/sys': ['init', 'sched', 'task', 'timer', 'watchdog', 'reset', 'main', 'loop', 'isr', 'interrupt'],
    }
    def classify(nm):
        l = nm.lower()
        for k, kws in SUB.items():
            if any(w in l for w in kws):
                return k
        return 'other/unclassified'
    groups = defaultdict(list)
    for x in hand:
        groups[classify(funcs[x][1])].append(x)

    lines = []
    P = lines.append
    P("# RX-8 PCM firmware — assembly overview (60E0FC00)\n")
    P("Whole-ROM structural map generated by `tools/callgraph.py`. This is the backbone for a")
    P("complete view of the assembly: every function, who calls it, and its subsystem.\n")
    P("## Coverage\n")
    P("- **%d functions** total in the symbol table (code region fully segmented)." % len(starts))
    hd = len(hand); au = len(starts) - hd
    P("- **%d hand-named by equinox** (reliable) + %d Ghidra-auto (`FUN_*`, generic)." % (hd, au))
    P("- **%d call edges** resolved (%d bsr-direct, %d pooled `jsr` targets)."
      % (len(edges), sum(k == 'bsr' for _, _, k in edges), sum(k == 'ref' for _, _, k in edges)))
    P("- **%d/%d equinox functions documented** in `docs/functions/` (%.0f%%)."
      % (len(documented), hd, 100.0 * len(documented) / max(hd, 1)))
    P("- Edge list: `symbols/callgraph.csv`.\n")

    P("## Core primitives — most-called functions (hubs)\n")
    P("These are called from the most places, so naming/verifying them explains the most code.\n")
    P("| callers | addr | name | source |")
    P("|--:|---|---|---|")
    shown = 0
    for x in hubs:
        if len(callees[x]) < 3:
            break
        P("| %d | 0x%X | %s | %s |" % (len(callees[x]), x, funcs[x][1] or '(auto)', funcs[x][2]))
        shown += 1
        if shown >= 30:
            break
    P("")

    P("## Subsystems (over equinox's hand names)\n")
    for k in list(SUB) + ['other/unclassified']:
        g = groups.get(k, [])
        if not g:
            continue
        P("- **%s** — %d functions" % (k, len(g)))
    P("")
    P("_Grouping is keyword-based on equinox's labels; a starting index, not ground truth._\n")

    open(a.out_md, 'w').write("\n".join(lines) + "\n")

    print("functions=%d  hand=%d  auto=%d  edges=%d  documented(hand)=%d"
          % (len(starts), hd, au, len(edges), len(documented)))
    print("wrote", a.out_csv, "and", a.out_md)

    if a.worklist:
        print("\n# Priority worklist — equinox-named, undocumented, most-called first:")
        pri = [x for x in hubs if funcs[x][2] == 'ghidra-hand' and norm(funcs[x][1]) not in docn]
        for x in pri[:a.worklist]:
            e = func_end(funcs, x, starts)
            print("0x%X\t%d\t%d\t%s" % (x, len(callees[x]), e - x, funcs[x][1]))


if __name__ == '__main__':
    main()
