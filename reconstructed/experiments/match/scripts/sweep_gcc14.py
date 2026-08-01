#!/usr/bin/env python3
"""
sweep_gcc14.py — full matrix sweep for the match-and-compile experiment using the
real freshly-built gcc (GCC 14.2.0 sh-elf, xgcc from /home/davide/gcc-sh2e-build).

For each target function the toolchain compiles c_src/<func>.c with
  opt    x { -O0, -O1, -O2, -Os }
  isa    x { -m2e, -m3, -m4-nofpu }
  extra  x { (none), -fno-delayed-branch, -fomit-frame-pointer, -fno-omit-frame-pointer }
assemble the emitted .s with /usr/bin/sh-elf-as -isa=sh2e, extract .text with
/usr/bin/sh-elf-objcopy, and compare the byte sequence (and decoded instruction
sequence) against the exact ROM bytes from rom_hex/*.txt — offset-relative, as
the existing scripts/compare.py oracle does.

All intermediate files go to /tmp; nothing outside match/ is touched.

Usage: python3 scripts/sweep_gcc14.py [--out /tmp/sweep_gcc14/report.txt]
"""
import argparse, os, struct, subprocess, sys, itertools

HERE = os.path.dirname(os.path.abspath(__file__))
MATCH = os.path.normpath(os.path.join(HERE, ".."))
SRC   = os.path.join(MATCH, "c_src")
ROMH  = os.path.join(MATCH, "rom_hex")
STUB  = "/tmp/stubinc"
XGCC  = "/home/davide/gcc-sh2e-build/gcc/xgcc"
XB    = "/home/davide/gcc-sh2e-build/gcc/"
AS    = "/usr/bin/sh-elf-as"
OBJC  = "/usr/bin/sh-elf-objcopy"

try:
    sys.path.insert(0, os.path.join(MATCH, "..", "..", "..", "..", "tools"))
    from disasm_sh2e import disasm_one
except Exception:
    disasm_one = None

# func -> (rom_offset, window_len_bytes)  — window = body + literal pool,
# matching rom_hex/*.txt "total span".
CASES = {
    "add16bitSaturate": (0x2460, 24),
    "addSaturate8Bit":  (0x2478, 24),
    "addS32Saturate":   (0x2304, 24),
    "seed_mixer":       (0x366B8, 164),
}

OPTS   = ["-O0", "-O1", "-O2", "-Os"]
ISAS   = ["-m2e", "-m3", "-m4-nofpu"]
EXTRAS = [
    ("default",        []),
    ("nodel",          ["-fno-delayed-branch"]),
    ("omitfp",         ["-fomit-frame-pointer"]),
    ("no-omitfp",      ["-fno-omit-frame-pointer"]),
]

def parse_rom_hex(fname):
    """Return (offset, window_len, body_hex, lit_hex) from rom_hex/<fname>."""
    off = None
    body, lit = "", ""
    lines = open(os.path.join(ROMH, fname)).read().splitlines()
    for l in lines:
        l = l.strip()
        if l.startswith("#"):
            if "ROM offset 0x" in l:
                off = int(l.split("0x")[1][:5], 16)
            continue
        if l and len(l) >= 8:
            if lit:
                body += l
            elif l.startswith("0000") or len(l) > 40:  # body line is the long hex
                body += l
        # literal handled below via separate pass
    # simpler: re-read keeping order of non-comment hex lines
    hx = [l.strip() for l in open(os.path.join(ROMH, fname)).read().splitlines()
          if l.strip() and not l.strip().startswith("#")]
    body = hx[0]
    lit = hx[1] if len(hx) > 1 else ""
    if "2460" in fname: off = 0x2460
    elif "2478" in fname: off = 0x2478
    elif "2304" in fname: off = 0x2304
    elif "366B8" in fname: off = 0x366B8
    elif "3675C" in fname: off = 0x3675C
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
    sfile = os.path.join(workdir, f"{fname}.{suffix}.s")
    ofile = sfile + ".o"
    bfile = sfile + ".bin"
    cmd = [XGCC, "-B", XB, "-nostdinc", "-I", STUB, "-c", cfile, "-o", ofile, isa]
    # get .s first so we can record it on a match
    cmds = [XGCC, "-B", XB, "-nostdinc", "-I", STUB, "-S", cfile, "-o", sfile, isa] + opts + extra
    r = subprocess.run(cmds, capture_output=True, text=True)
    if r.returncode != 0:
        return False, r.stderr[-300:], None
    asm_isa = {"-m1": "sh", "-m2": "sh2", "-m2e": "sh2e", "-m3": "sh3",
               "-m3e": "sh3e", "-m4-nofpu": "sh4a-nofpu", "-m4": "sh4a"}.get(isa, "sh2e")
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
    ap.add_argument("--out", default="/tmp/sweep_gcc14/report.txt")
    ap.add_argument("--funcs", default="add16bitSaturate,addSaturate8Bit,addS32Saturate,seed_mixer")
    ap.add_argument("--isa", default=None, help="restrict isa (e.g. -m2e)")
    args = ap.parse_args()

    workdir = "/tmp/sweep_gcc14"
    os.makedirs(workdir, exist_ok=True)

    ver = subprocess.run([XGCC, "-B", XB, "-dumpversion"], capture_output=True, text=True).stdout.strip()
    target = subprocess.run([XGCC, "-B", XB, "-dumpmachine"], capture_output=True, text=True).stdout.strip()

    lines = []
    lines.append(f"# sweep_gcc14  gcc={XGCC}  version={ver}  target={target}")
    lines.append(f"# as={AS}  objcopy={OBJC}  stdint stub={STUB}")
    lines.append(f"# window = body + literal pool from rom_hex/*.txt (offset-relative)\n")

    # best-match bookkeeping
    best = {}   # fname -> (pct, suffix, isa, opts, extra, res)
    table = {}  # fname -> dict of (isa,opt,extra) -> res

    funcs = args.funcs.split(",")
    for fname in funcs:
        romf = next((f for f in os.listdir(ROMH) if f.startswith(fname)), None)
        if not romf:
            lines.append(f"!! no rom_hex for {fname}")
            continue
        roff, wlen, exp = rom_bytes(romf)
        lines.append(f"== {fname}  ROM@0x{roff:05X} window={wlen}B")
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
        lines.append(f"{fname}: best {pct:.1f}%  [{suffix}]  bytes {res['same_b']}/{res['nwin']} "
                     f"insn {res['same_i']}/{res['nins']} first@+0x{res['first']:02X}  {tag}")
        if tag == "MATCH":
            lines.append(f"  >>> BYTE-PERFECT MATCH: {XGCC} -B {XB} -nostdinc -I {STUB} "
                         f"{isa} {opt} {ename}")

    lines.append("\n# === SUMMARY TABLE (bytes matched / window) ===")
    cols = [f"{isa[1:]}|{o}|{e}" for isa in ISAS for o in OPTS for e, _ in EXTRAS]
    hdr = "func".ljust(20) + "".join(c.ljust(14) for c in cols)
    lines.append(hdr)
    for fname in funcs:
        if fname not in table: continue
        row = fname.ljust(20)
        for key in [(isa, o, e) for isa in ISAS for o in OPTS for e, _ in EXTRAS]:
            r = table[fname].get(key, ("-", 0, 0, 0.0))
            tag, sb, nw, pct = r
            row += ("MATCH!" if tag == "MATCH" else (f"{sb}/{nw}:{pct:4.1f}%" if tag == "diff" else "CF")).ljust(14)
        lines.append(row)

    report = "\n".join(lines)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(report + "\n")
    print(report)

if __name__ == "__main__":
    main()
