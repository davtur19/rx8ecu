#!/usr/bin/env python3
"""
rom_rebuild.py — whole-ROM asm-first rebuild.

Emit ONE reassemblable GNU-as source file for the entire ROM (code region as
symbolic SH-2 instructions, everything else as `.word` data), assemble + link at
the real VMA, and produce a byte-exact copy of the ROM. This is the concrete
"`make` reproduces the stock ROM byte-for-byte" milestone of PLANS.md — achieved
WITHOUT the original Renesas/Hitachi SHC compiler, because re-assembling the
existing instructions reproduces the bytes by construction.

Why this is byte-exact and robust
---------------------------------
* SH-2 instructions are all exactly 2 bytes, so decode/emit never drifts: every
  even offset is independently either an instruction or a `.word`.
* All data (literal pools, tables, calibration, strings, vectors) is emitted as
  `.word`, so it round-trips verbatim.
* Branch / PC-relative operands are rewritten to `L_xxxxxx` labels; the whole ROM
  is one unit linked at VMA 0, so displacements/ranges are the originals.
* Self-correcting: any word GNU-as rejects (e.g. data that capstone over-decodes
  as an SH-2A/SH-4 op like `ldc.l @rn+,tbr` or `synco`) or that re-encodes to
  different bytes is forced back to raw `.word`. The loop converges to cmp == 0.

* capstone fallback: words capstone does not decode are handed to
  tools/disasm_sh2e.py (disasm_one), so the SH-2E families GNU-as/capstone miss
  (GBR MOV, 0x82xx/0x86xx mov.l, div0s/div1, cmp/str, mac, negc, addc/subc,
  addv/subv, control registers, bsrf/braf, ...) are lifted too. The one
  documented exception: 0x82xx/0x86xx `mov.l r0,@(disp,Rm)` have no GNU-as
  syntax, so the self-correction loop forces those to `.word` (byte-exact by
  construction). Verified by tools/tests/test_decode_families.py.

Coverage is reported (how much of the code region is lifted to real instructions);
the remainder is byte-exact data. Semantic code/data refinement (jump tables,
naming) is layered on top later from the Ghidra/IDA map.

Requires capstone>=5.0 and sh-elf binutils on PATH (tools/get_toolchain.sh).

Usage:
  python rom_rebuild.py --rom roms/stock/60E1D400.bin --asm build/rom.s --out build/out.bin
"""
import argparse, re, subprocess, sys, types

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


def rebuild(rom, asm_out, bin_out, code_lo, code_hi, max_iter=16):
    d = open(rom, 'rb').read()
    N = len(d)
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
        out = ['\t.text']
        meta = [None]                       # meta[k] = addr of source line k (1-based -> index)
        a = 0
        while a < N:
            if a in labels:
                out.append('L_%06x:' % a); meta.append(None)
            i = dis.get(a) if code_lo <= a < code_hi else None
            if i is not None and a not in force:
                op = i.op_str
                if i.mnemonic in PCREL or i.mnemonic in BR:
                    t = _tgt(op)
                    if t is not None and 0 <= t < N:
                        op = re.sub(r'0x[0-9a-fA-F]+', 'L_%06x' % t, op, count=1)
                    elif t is not None:                 # unresolved target -> raw
                        out.append('\t.word 0x%04x' % int.from_bytes(d[a:a + 2], 'big'))
                        meta.append(a); a += 2; continue
                out.append(('\t%s %s' % (i.mnemonic, op)).rstrip()); meta.append(a)
            else:
                out.append('\t.word 0x%04x' % int.from_bytes(d[a:a + 2], 'big'))
                meta.append(a)
            a += 2
        return '\n'.join(out) + '\n', meta

    for _ in range(max_iter):
        s, meta = emit()
        open(asm_out, 'w').write(s)
        r = subprocess.run(['sh-elf-as', '-big', asm_out, '-o', asm_out + '.o'],
                           capture_output=True, text=True)
        if r.returncode:
            errs = set()
            for m in re.finditer(r':(\d+): Error', r.stderr):
                k = int(m.group(1)) - 1
                if 0 <= k < len(meta) and meta[k] is not None:
                    errs.add(meta[k])
            if not errs:
                sys.exit("as failed (unmapped):\n" + r.stderr[:600])
            force |= errs
            continue
        subprocess.run(['sh-elf-ld', '-Ttext=0x0', '-e', '0x0',
                        '-o', asm_out + '.elf', asm_out + '.o'], check=True)
        subprocess.run(['sh-elf-objcopy', '-O', 'binary', '-j', '.text',
                        asm_out + '.elf', bin_out], check=True)
        got = open(bin_out, 'rb').read()
        if got == d:
            n = sum(1 for a in range(code_lo, code_hi, 2)
                    if dis[a] is not None and a not in force)
            return True, n, (code_hi - code_lo) // 2, len(force)
        newf = {(k & ~1) for k in range(min(len(got), N))
                if got[k] != d[k] and code_lo <= (k & ~1) < code_hi}
        if not (newf - force):
            bad = [hex(k) for k in range(min(len(got), N)) if got[k] != d[k]][:8]
            sys.exit("stall: diffs outside code region: " + ', '.join(bad))
        force |= newf
    sys.exit("did not converge")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', default='roms/stock/60E1D400.bin')
    ap.add_argument('--asm', default='build/rom.s')
    ap.add_argument('--out', default='build/out.bin')
    ap.add_argument('--code-lo', type=lambda x: int(x, 0), default=0x800)
    ap.add_argument('--code-hi', type=lambda x: int(x, 0), default=0x60000)
    a = ap.parse_args()
    import os
    for p in (a.asm, a.out):
        os.makedirs(os.path.dirname(p) or '.', exist_ok=True)
    ok, n, tot, raw = rebuild(a.rom, a.asm, a.out, a.code_lo, a.code_hi)
    if ok:
        print("BYTE-EXACT: %s == %s" % (a.out, a.rom))
        print("code region 0x%x..0x%x lifted to instructions: %d/%d words (%.1f%%), raw fallbacks: %d"
              % (a.code_lo, a.code_hi, n, tot, 100.0 * n / tot, raw))


if __name__ == '__main__':
    main()
