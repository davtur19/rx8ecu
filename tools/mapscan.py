#!/usr/bin/env python3
"""
mapscan.py <rom> [--defs symbols/cal_tables.csv] [--dump 0xADDR]

Find the calibration-map descriptors consumed by TwoDLookup (0x2068) / ThreeDLookup
(0x20DC), decode their axes + int->physical scaling, and cross-reference RX8Defs names.
The descriptor formats were reverse-engineered and emulator-verified (see c/2DLookup.c,
c/3dLookup.c). --dump 0xADDR prints one map's full grid in physical units.

Descriptor layouts (big-endian):
  Map1D (20B): u16 count; u8 type; f32* axis@4; void* values@8; f32 scale@12; f32 offset@16
  Map2D (28B): u16 count_x; u16 count_y; f32* axis_x@4; f32* axis_y@8; void* values@12;
               u8 type@16; f32 scale@20; f32 offset@24
  type: 0=f32 cells (no scale/offset) | 4=u8 | 8=u16 | 12=s8 | 16=s16
"""
import argparse, csv, math, struct, sys

CELL = {0: ('f', 4), 4: ('B', 1), 8: ('H', 2), 12: ('b', 1), 16: ('h', 2)}


def scan(d, lo=0x1000, hi=0x7E000):
    N = len(d)
    def u16(o): return int.from_bytes(d[o:o + 2], 'big')
    def u32(o): return int.from_bytes(d[o:o + 4], 'big')
    def f32(o):
        try: return struct.unpack('>f', d[o:o + 4])[0]
        except Exception: return None
    def vptr(p): return lo <= p < hi and p % 2 == 0
    def axis(p, n):
        if not (lo <= p < hi and p % 4 == 0): return None
        out, prev = [], None
        for i in range(n):
            v = f32(p + i * 4)
            if v is None or not math.isfinite(v) or abs(v) > 1e7: return None
            if prev is not None and not v > prev: return None
            out.append(v); prev = v
        return out
    def okf(x): return x is not None and math.isfinite(x) and abs(x) < 1e6

    maps = []
    for o in range(lo, hi, 2):
        t = d[o + 16] if o + 16 < N else 255           # Map2D type slot
        if 2 <= u16(o) <= 64 and 2 <= u16(o + 2) <= 64 and t in CELL:
            cx, cy = u16(o), u16(o + 2); axp, ayp, vp = u32(o + 4), u32(o + 8), u32(o + 12)
            if vptr(axp) and vptr(ayp) and vptr(vp) and len({axp, ayp, vp}) == 3:
                ax, ay = axis(axp, cx), axis(ayp, cy)
                sc, of = f32(o + 20), f32(o + 24)
                if ax and ay and okf(sc) and okf(of) and sc != 0:
                    maps.append(dict(kind='2D', o=o, cx=cx, cy=cy, type=t, vp=vp, axp=axp, ayp=ayp,
                                     sc=sc, of=of, ax=ax, ay=ay)); continue
        t = d[o + 2] if o + 2 < N else 255             # Map1D type slot
        if 2 <= u16(o) <= 64 and t in CELL:
            c = u16(o); axp, vp = u32(o + 4), u32(o + 8)
            if vptr(axp) and vptr(vp) and axp != vp:
                ax = axis(axp, c); sc, of = f32(o + 12), f32(o + 16)
                if ax and okf(sc) and okf(of) and sc != 0:
                    maps.append(dict(kind='1D', o=o, cx=c, type=t, vp=vp, axp=axp, sc=sc, of=of, ax=ax))
    return maps


def load_defs(p):
    m = {}
    try:
        for r in csv.DictReader(open(p)):
            try: m[int(r['address'], 16)] = r['name']
            except Exception: pass
    except FileNotFoundError:
        pass
    return m


def cell_val(d, vp, type, idx):
    fmt, sz = CELL[type]
    return struct.unpack('>' + fmt, d[vp + idx * sz: vp + idx * sz + sz])[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom'); ap.add_argument('--defs', default='symbols/cal_tables.csv')
    ap.add_argument('--dump', type=lambda x: int(x, 0))
    a = ap.parse_args()
    d = open(a.rom, 'rb').read()
    defs = load_defs(a.defs)
    maps = scan(d)
    named = sum(1 for m in maps if m['vp'] in defs or m['axp'] in defs)
    print("%s: %d map descriptors (%d 2D, %d 1D); %d match RX8Defs by pointer"
          % (a.rom, len(maps), sum(m['kind'] == '2D' for m in maps),
             sum(m['kind'] == '1D' for m in maps), named))
    if a.dump is not None:
        m = next((x for x in maps if x['o'] == a.dump or x['vp'] == a.dump), None)
        if not m: sys.exit("no descriptor at 0x%X" % a.dump)
        nm = defs.get(m['vp'], defs.get(m['axp'], '(unnamed)'))
        ty = {0: 'f32', 4: 'u8', 8: 'u16', 12: 's8', 16: 's16'}[m['type']]
        print("\n%s  desc@0x%05X  values@0x%05X  %s  scale=%g offset=%g"
              % (nm, m['o'], m['vp'], ty, m['sc'], m['of']))
        def phys(raw): return raw if m['type'] == 0 else raw * m['sc'] + m['of']
        if m['kind'] == '1D':
            print("axis:", ['%.4g' % v for v in m['ax']])
            print("vals:", ['%.4g' % phys(cell_val(d, m['vp'], m['type'], i)) for i in range(m['cx'])])
        else:
            print("axisX:", ['%.4g' % v for v in m['ax']])
            print("axisY:", ['%.4g' % v for v in m['ay']])
            for j in range(m['cy']):
                row = [phys(cell_val(d, m['vp'], m['type'], j * m['cx'] + i)) for i in range(m['cx'])]
                print("  Y=%-7.4g " % m['ay'][j], ['%.4g' % v for v in row])
        return
    # catalog
    print("\naddr     kind  dims    type  scale     offset    values    name(RX8Defs)")
    for m in sorted(maps, key=lambda x: x['o']):
        ty = {0: 'f32', 4: 'u8', 8: 'u16', 12: 's8', 16: 's16'}[m['type']]
        dims = '%dx%d' % (m['cx'], m['cy']) if m['kind'] == '2D' else '%d' % m['cx']
        nm = defs.get(m['vp'], defs.get(m['axp'], ''))
        print("0x%05X %-4s %-7s %-4s %-9.4g %-9.4g 0x%05X  %s"
              % (m['o'], m['kind'], dims, ty, m['sc'], m['of'], m['vp'], nm))


if __name__ == '__main__':
    main()
