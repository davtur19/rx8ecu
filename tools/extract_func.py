#!/usr/bin/env python3
"""
extract_func.py <rom> <addr> [--syms symbols/symbols_60E0FC00.csv] — dump one function's FPU-decoded
SH-2E assembly with literal-pool loads resolved to their values and jsr/bsr call
targets named. Produces an analysis-ready block (for a human or a sub-agent).

Example:
  python tools/extract_func.py roms/stock/60E0FC00.bin 0x7298 --syms symbols/symbols_60E0FC00.csv
"""
import argparse, csv, struct, sys
try:
    import capstone as C
except ImportError:
    sys.exit("need capstone: pip install capstone --break-system-packages")

KNOWN = {0x2068: 'TwoDLookup(desc r4, x fr4)->fr0', 0x20DC: 'ThreeDLookup(desc r4, x fr4, y fr5)->fr0',
         0x2624: 'axis_search', 0x2658: 'axis_search_2d', 0x2460: 'add16bitSaturate', 0x2478: 'addSaturate8Bit'}


def fpu(w):
    if (w >> 12) != 0xF: return None
    n = (w >> 8) & 0xF; m = (w >> 4) & 0xF; lo = w & 0xF
    t = {0: 'fadd', 1: 'fsub', 2: 'fmul', 3: 'fdiv', 4: 'fcmp/eq', 5: 'fcmp/gt'}
    if lo in t: return '%s fr%d,fr%d' % (t[lo], m, n)
    fm = {6: 'fmov.s @(r0,r%d),fr%d' % (m, n), 7: 'fmov.s fr%d,@(r0,r%d)' % (m, n),
          8: 'fmov.s @r%d,fr%d' % (m, n), 9: 'fmov.s @r%d+,fr%d' % (m, n),
          0xA: 'fmov.s fr%d,@r%d' % (m, n), 0xB: 'fmov.s fr%d,@-r%d' % (m, n),
          0xC: 'fmov fr%d,fr%d' % (m, n), 0xE: 'fmac fr0,fr%d,fr%d' % (m, n)}
    if lo in fm: return fm[lo]
    if lo == 0xD:
        o = {0: 'fsts fpul,fr%d' % n, 1: 'flds fr%d,fpul' % n, 2: 'float fpul,fr%d' % n,
             3: 'ftrc fr%d,fpul' % n, 4: 'fneg fr%d' % n, 5: 'fabs fr%d' % n,
             6: 'fsqrt fr%d' % n, 8: 'fldi0 fr%d' % n, 9: 'fldi1 fr%d' % n}
        return o.get(m)
    return None


def intx(w, n):
    return {0x005A: 'sts fpul,r%d' % n, 0x405A: 'lds r%d,fpul' % n, 0x006A: 'sts fpscr,r%d' % n,
            0x406A: 'lds r%d,fpscr' % n, 0x4022: 'sts.l pr,@-r15', 0x4026: 'lds.l @r15+,pr',
            0x4012: 'sts.l macl,@-r15', 0x4002: 'sts.l mach,@-r15'}.get(w & 0xF0FF)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom'); ap.add_argument('addr', type=lambda x: int(x, 0))
    ap.add_argument('--syms'); ap.add_argument('--end', type=lambda x: int(x, 0))
    a = ap.parse_args()
    d = open(a.rom, 'rb').read()
    md = C.Cs(C.CS_ARCH_SH, C.CS_MODE_SH2 | C.CS_MODE_BIG_ENDIAN)
    names = {}
    if a.syms:
        for r in csv.DictReader(open(a.syms)):
            names[int(r['addr'], 16)] = r['name']
    end = a.end
    if end is None:                       # next symbol after addr, else +0x100
        nxt = sorted(x for x in names if x > a.addr)
        end = nxt[0] if nxt else a.addr + 0x100
    nm = names.get(a.addr, 'FUN_%06x' % a.addr)
    print("### %s @ 0x%X  (%d bytes)" % (nm, a.addr, end - a.addr))
    b = a.addr
    while b < end:
        w = int.from_bytes(d[b:b + 2], 'big'); n = (w >> 8) & 0xF
        txt = fpu(w) or intx(w, n)
        note = ''
        if not txt:
            g = list(md.disasm(d[b:b + 2], b))
            txt = ('%s %s' % (g[0].mnemonic, g[0].op_str)).strip() if g else '.word 0x%04x' % w
            # resolve pc-relative literal loads
            if (w >> 12) == 0xD:                       # mov.l @(disp,pc),Rn
                lit = ((b + 4) & ~3) + (w & 0xFF) * 4; val = int.from_bytes(d[lit:lit + 4], 'big')
                note = '= 0x%08X' % val + (('  ; ' + names[val]) if val in names else ('  ; call->' + KNOWN[val] if val in KNOWN else ''))
            elif (w >> 12) == 0x9:                     # mov.w @(disp,pc),Rn
                lit = b + 4 + (w & 0xFF) * 2; note = '= 0x%04X' % int.from_bytes(d[lit:lit + 2], 'big')
            elif (w & 0xFF00) == 0xC700:               # mova @(disp,pc),r0
                lit = ((b + 4) & ~3) + (w & 0xFF) * 4
                try: note = '= &0x%05X (f32 %.6g)' % (lit, struct.unpack('>f', d[lit:lit + 4])[0])
                except Exception: note = '= &0x%05X' % lit
        print("0x%06X %-26s %s" % (b, txt, note))
        b += 2


if __name__ == '__main__':
    main()
