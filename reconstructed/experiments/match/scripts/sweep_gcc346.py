#!/usr/bin/env python3
"""
sweep_gcc346.py — full matrix sweep for the match-and-compile experiment using
the era-correct freshly-built GCC 3.4.6 sh-elf (xgcc from /home/davide/gcc346-build).

Same methodology as scripts/sweep_gcc14.py (which swept GCC 14.2.0): for each
target function compile c_src/<func>.c with
    opt    x { -O0, -O1, -O2, -Os }
    isa    x { -m2e, -m3, -m4-nofpu }
    extra  x { (none), -fno-delayed-branch, -fomit-frame-pointer, -fno-omit-frame-pointer }
assemble the emitted .s with /usr/bin/sh-elf-as -isa=sh2e, extract .text with
/usr/bin/sh-elf-objcopy, and compare the byte sequence against the exact ROM
bytes from rom_hex/*.txt — offset-relative, as scripts/compare.py does.

Differences vs sweep_gcc14.py:
  * toolchain -> /home/davide/gcc346-build/gcc/xgcc (GCC 3.4.6, era ROM);
  * rom_hex parser only keeps pure-hex lines (the current *.txt files contain
    a "replacement ; regex ..." annotation line that would break fromhex);
  * on a BYTE-PERFECT match the generated .s is copied to
    expected_gcc_sh2e/<func>.<suffix>.s for the recipe record.

All intermediate files go to /tmp; nothing outside match/ is touched.

Usage: python3 scripts/sweep_gcc346.py [--out /tmp/sweep_gcc346/report.txt]
              [--funcs add16bitSaturate,add16bitSaturate_reg,...]
              [--isa -m2e]
"""
import argparse, os, re, struct, subprocess, sys, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
MATCH = os.path.normpath(os.path.join(HERE, ".."))
SRC   = os.path.join(MATCH, "c_src")
ROMH  = os.path.join(MATCH, "rom_hex")
EXP   = os.path.join(MATCH, "expected_gcc_sh2e")
STUB  = "/tmp/stubinc"
XGCC  = "/home/davide/gcc346-build/gcc/xgcc"
XB    = "/home/davide/gcc346-build/gcc/"
AS    = "/usr/bin/sh-elf-as"
OBJC  = "/usr/bin/sh-elf-objcopy"

try:
    sys.path.insert(0, os.path.normpath(os.path.join(MATCH, "..", "..", "..", "..", "tools")))
    from disasm_sh2e import disasm_one
except Exception:
    disasm_one = None

# func -> (rom_offset, window_len_bytes) — window = body + literal pool.
# window_len is informational; the authoritative window comes from rom_hex/*.txt.
CASES = {
    "add16bitSaturate": (0x2460, 24),
    "addSaturate8Bit":  (0x2478, 24),
    "addS32Saturate":   (0x2304, 24),
    "seed_mixer":       (0x366B8, 164),
}

OPTS   = ["-O0", "-O1", "-O2", "-Os"]
ISAS   = ["-m2e", "-m3", "-m4-nofpu"]
EXTRAS = [
    ("default",   []),
    ("nodel",     ["-fno-delayed-branch"]),
    ("omitfp",    ["-fomit-frame-pointer"]),
    ("no-omitfp", ["-fno-omit-frame-pointer"]),
]

HEX_RE = re.compile(r"^[0-9a-fA-F]+$")

def parse_rom_hex(fname):
    """Return (offset, window_len, bytes) from rom_hex/<fname>.
    Only pure-hex lines are kept (skips # comments and the 'replacement' line)."""
    hx = []
    for l in open(os.path.join(ROMH, fname)).read().splitlines():
        l = l.strip()
        if l and not l.startswith("#") and HEX_RE.match(l) and len(l) % 2 == 0:
            hx.append(l)
    body = hx[0]
    lit = hx[1] if len(hx) > 1 else ""
    off = 0x2460 if "2460" in fname else \
          0x2478 if "2478" in fname else \
          0x2304 if "2304" in fname else \
          0x366B8 if "366B8" in fname else \
          0x3675C if "3675C" in fname else 0
    total = (len(body) + len(lit)) // 2
    return off, total, bytes.fromhex(body + lit)

ROM_CACHE = {}
def rom_bytes(fname):
    if fname not in ROM_CACHE:
        ROM_CACHE[fname] = parse_rom_hex(fname)
    return ROM_CACHE[fname]

def ins_list(data, base=0):
    out = []
    for i in range(0, len(data) - 1, 2):
        op = struct.unpack(">H", data[i:i+2])[0]
        if disasm_one:
            try:
                mne, ops, _ = disasm_one(op, base + i)
                out.append((i, op, mne, ops))
                continue
            except Exception:
                pass
        out.append((i, op, f"{op:04X}", ""))
    return out

def compile_and_get_text(fname, isa, opts, extra, workdir, suffix):
    cfile = os.path.join(SRC, fname + ".c")
    if not os.path.exists(cfile):
        return False, "no source", None
    sfile = os.path.join(workdir, f"{fname}.{suffix}.s")
    ofile = sfile + ".o"
    bfile = sfile + ".bin"
    cmds = [XGCC, "-B", XB, "-nostdinc", "-I", STUB, "-S", cfile, "-o", sfile,
            isa] + opts + extra
    r = subprocess.run(cmds, capture_output=True, text=True)
    if r.returncode != 0:
        return False, r.stderr[-300:], None
    asm_isa = {"-m2e": "sh2e", "-m3": "sh3", "-m4-nofpu": "sh4a-nofpu"}.get(isa, "sh2e")
    r2 = subprocess.run([AS, f"-isa={asm_isa}", "-o", ofile, sfile],
                        capture_output=True, text=True)
    if r2.returncode != 0:
        return False, r2.stderr[-300:], None
    r3 = subprocess.run([OBJC, "-O", "binary", "--only-section=.text", ofile, bfile],
                        capture_output=True, text=True)
    if r3.returncode != 0:
        return False, r3.stderr[-300:], None
    return True, "", open(bfile, "rb").read()

def compare(got, exp):
    """Byte and instruction comparison, offset-relative. Returns dict."""
    n = min(len(got), len(exp))
    same_b = sum(1 for i in range(n) if got[i] == exp[i])
    gi = ins_list(got[:n - (n % 2)])
    ei = ins_list(exp[:n - (n % 2)])
    mi = min(len(gi), len(ei))
    same_i = sum(1 for i in range(mi) if gi[i][1] == ei[i][1])
    first_diff = next((i for i in range(n) if got[i] != exp[i]), None)
    return dict(
        nbyte=len(got), nwin=len(exp), ncmp=n, same_b=same_b,
        same_i=same_i, nins=mi, first=first_diff,
        pct=(100.0 * same_b / len(exp)) if len(exp) else 0.0,
    )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/sweep_gcc346/report.txt")
    ap.add_argument("--funcs", default=(
        "add16bitSaturate,addSaturate8Bit,addS32Saturate,seed_mixer,"
        "add16bitSaturate_reg,addSaturate8Bit_reg,addS32Saturate_addv"))
    ap.add_argument("--isa", default=None, help="restrict isa (e.g. -m2e)")
    args = ap.parse_args()

    workdir = "/tmp/sweep_gcc346"
    os.makedirs(workdir, exist_ok=True)
    os.makedirs(EXP, exist_ok=True)

    ver = subprocess.run([XGCC, "-B", XB, "-dumpversion"], capture_output=True, text=True).stdout.strip()
    target = subprocess.run([XGCC, "-B", XB, "-dumpmachine"], capture_output=True, text=True).stdout.strip()

    lines = []
    lines.append(f"# sweep_gcc346  gcc={XGCC}  version={ver}  target={target}")
    lines.append(f"# as={AS}  objcopy={OBJC}  stdint stub={STUB}")
    lines.append(f"# window = body + literal pool from rom_hex/*.txt (offset-relative)\n")

    best = {}
    table = {}

    funcs = args.funcs.split(",")
    for fname in funcs:
        romf = next((f for f in os.listdir(ROMH) if f.startswith(fname.split("_")[0] + "_") or f.startswith(fname.split("_")[0])), None)
        if not romf:
            # fallback: match base name prefix
            base = fname.split("_")[0]
            romf = next((f for f in os.listdir(ROMH) if f.startswith(base)), None)
        if not romf:
            lines.append(f"!! no rom_hex for {fname}")
            continue
        roff, wlen, exp = rom_bytes(romf)
        lines.append(f"== {fname}  (rom_hex={romf})  ROM@0x{roff:05X} window={wlen}B")
        table[fname] = {}
        for isa in ([args.isa] if args.isa else ISAS):
            for opt in OPTS:
                for ename, extra in EXTRAS:
                    suffix = f"{isa[1:]}.{opt}.{ename}"
                    ok, err, got = compile_and_get_text(fname, isa, [opt], extra, workdir, suffix)
                    if not ok:
                        lines.append(f"   [{suffix:24s}] COMPILE-FAIL {err[:100].replace(chr(10),' ')}")
                        table[fname][(isa, opt, ename)] = ("CF", 0, 0, 0.0)
                        continue
                    res = compare(got, exp)
                    tag = "MATCH" if (res["nbyte"] == res["nwin"] and res["same_b"] == res["nwin"]) else "diff"
                    if res["pct"] > best.get(fname, (0,))[0]:
                        best[fname] = (res["pct"], suffix, isa, opt, ename, res, tag)
                    lines.append(
                        f"   [{suffix:24s}] bytes {res['same_b']:3d}/{res['nwin']:3d} "
                        f"({res['pct']:5.1f}%) insn {res['same_i']:3d}/{res['nins']:3d} "
                        f"first@+0x{res['first']:02X}" if res["first"] is not None
                        else f"   [{suffix:24s}] bytes {res['same_b']:3d}/{res['nwin']:3d} "
                             f"({res['pct']:5.1f}%) insn {res['same_i']:3d}/{res['nins']:3d} first=-  {tag}")
                    table[fname][(isa, opt, ename)] = (tag, res["same_b"], res["nwin"], res["pct"])
        lines.append("")

    lines.append("\n# === BEST MATCH PER FUNCTION ===")
    for fname, (pct, suffix, isa, opt, ename, res, tag) in best.items():
        firsts = f"first@+0x{res['first']:02X}" if res["first"] is not None else "first=-"
        lines.append(f"{fname}: best {pct:.1f}%  [{suffix}]  bytes {res['same_b']}/{res['nwin']} "
                     f"insn {res['same_i']}/{res['nins']} {firsts}  {tag}")
        if tag == "MATCH":
            lines.append(f"  >>> BYTE-PERFECT MATCH: {XGCC} -B {XB} -nostdinc -I {STUB} "
                         f"{isa} {opt} {ename}")
            src = os.path.join(workdir, f"{fname}.{suffix}.s")
            if os.path.exists(src):
                dst = os.path.join(EXP, f"{fname}.{suffix}.s")
                shutil.copy(src, dst)
                lines.append(f"  >>> .s saved to expected_gcc_sh2e/{fname}.{suffix}.s")

    lines.append("\n# === SUMMARY TABLE (bytes matched / window) ===")
    cols = [f"{isa[1:]}|{o}|{e}" for isa in ISAS for o in OPTS for e, _ in EXTRAS]
    hdr = "func".ljust(22) + "".join(c.ljust(14) for c in cols)
    lines.append(hdr)
    for fname in funcs:
        if fname not in table: continue
        row = fname.ljust(22)
        for key in [(isa, o, e) for isa in ISAS for o in OPTS for e, _ in EXTRAS]:
            r = table[fname].get(key, None)
            if r is None:
                cell = "-"
            else:
                tag, sb, nw, pct = r
                if tag == "MATCH": cell = "MATCH!"
                elif tag == "diff": cell = f"{sb}/{nw}:{pct:4.1f}%"
                elif tag == "CF": cell = "CF"
                else: cell = "-"
            row += cell.ljust(14)
        lines.append(row)

    report = "\n".join(lines)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(report + "\n")
    print(report)

if __name__ == "__main__":
    main()
