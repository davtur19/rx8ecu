#!/usr/bin/env python3
"""
sweep.py — version x flags sweep for the match-and-compile experiment.

Compiles each c_src/*.c with the (real) sh-elf-gcc under test, extracts the
.text bytes, and compares the instruction sequence against the exact ROM bytes
(rom_hex/*.txt), offset-relative.

Usage:
  python3 sweep.py --gcc /path/to/sh-elf-gcc [--tag mytag] [--rom roms/stock/60E1D400.bin]
                   [--funcs add16bitSaturate,addSaturate8Bit,addS32Saturate,seed_mixer]

Outputs a per-(func,flagset) verdict line and prints a table at the end.
All file writes go to /tmp (sweep_<tag>/) — the repo match dir stays read-only.
"""
import argparse, os, struct, subprocess, sys, glob

HERE = os.path.dirname(os.path.abspath(__file__))
MATCH = os.path.normpath(os.path.join(HERE, ".."))
SRC   = os.path.join(MATCH, "c_src")
ROMH  = os.path.join(MATCH, "rom_hex")
TOOLS = [os.path.join(MATCH, "..", "..", "..", "..", "tools", "toolchain", "usr", "bin"),
         os.path.join(MATCH, "..", "..", "..", "..", "tools", "toolchain.bak", "usr", "bin")]

def find_tool(prog):
    for base in TOOLS:
        p = os.path.join(base, prog)
        if os.path.exists(p):
            return p
    return prog  # fall back to PATH

OBJCOPY = find_tool("sh-elf-objcopy")
OBJDUMP = find_tool("sh-elf-objdump")

# name -> (rom_offset, window_len_bytes) matching the rom_hex/*.txt files
CASES = {
    "add16bitSaturate": (0x2460, 24),
    "addSaturate8Bit":  (0x2478, 24),
    "addS32Saturate":   (0x2304, 24),
    "seed_mixer":       (0x366B8, 164),
}

FLAGSETS = [
    ("O0",      ["-O0"]),
    ("O0_nfp",  ["-O0", "-fomit-frame-pointer"]),
    ("O1",      ["-O1"]),
    ("O1_nfp",  ["-O1", "-fomit-frame-pointer"]),
    ("O2",      ["-O2"]),
    ("O2_nfp",  ["-O2", "-fomit-frame-pointer"]),
    ("Os",      ["-Os"]),
    ("O2_nodel",["-O2", "-fno-delayed-branch"]),
    ("O1_nodel",["-O1", "-fno-delayed-branch"]),
]

def parse_hex(path):
    lines = open(path).read().splitlines()
    for l in lines:
        l = l.strip()
        if l and not l.startswith("#") and len(l) >= 8:
            return bytes.fromhex(l)
    return None

def ins_list(data, base=0):
    """Decode bytes into a list of (offset, opcode, mnemonic, operands)."""
    out = []
    try:
        sys.path.insert(0, os.path.join(MATCH, "..", "..", "..", "..", "tools"))
        from disasm_sh2e import disasm_one
    except Exception:
        disasm_one = None
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

def compile_one(gcc, cfile, outo, flags, extra_isa):
    cmd = [gcc, "-c", cfile, "-o", outo] + flags
    if extra_isa:
        cmd = [gcc, "-c", cfile, "-o", outo, extra_isa] + flags
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0, r.stderr[-400:] if r.returncode else ""

def text_bytes(outo):
    subprocess.run([OBJCOPY, "-O", "binary", "--only-section=.text", outo, outo + ".bin"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return open(outo + ".bin", "rb").read()

def match_insn(got, exp):
    """Compare instruction sequences (offset-relative). Returns (n_matched_insn, n_tot_insn, first_diff)."""
    gi = [x for x in ins_list(got)]
    ei = [x for x in ins_list(exp)]
    n = min(len(gi), len(ei))
    same = 0
    first = None
    for i in range(n):
        if gi[i][1] == ei[i][1]:
            same += 1
        elif first is None:
            first = i
    return same, n, first, gi, ei

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gcc", required=True, help="path to sh-elf-gcc under test")
    ap.add_argument("--tag", default="x", help="sweep tag for /tmp output dir")
    ap.add_argument("--rom", default=os.path.join(MATCH, "..", "..", "..", "..", "roms", "stock", "60E1D400.bin"))
    ap.add_argument("--funcs", default="add16bitSaturate,addSaturate8Bit,addS32Saturate,seed_mixer")
    ap.add_argument("--isa", default="-m2e", help="subtarget flag (e.g. -m2e, -m4-nofpu, -m4)")
    ap.add_argument("--flags", default=None, help="override flagset list (comma list of 'name=flags' separated by |)")
    args = ap.parse_args()

    rom = open(args.rom, "rb").read()
    work = f"/tmp/sweep_{args.tag}"
    os.makedirs(work, exist_ok=True)
    print(f"# sweep tag={args.tag}  gcc={args.gcc}")
    ver = subprocess.run([args.gcc, "-dumpversion"], capture_output=True, text=True).stdout.strip()
    print(f"# gcc version: {ver}")
    print(f"# isa flag: {args.isa}")
    print()

    results = []
    for fname in args.funcs.split(","):
        cfile = os.path.join(SRC, fname + ".c")
        if not os.path.exists(cfile):
            print(f"!! missing C source {cfile}")
            continue
        roff, wlen = CASES[fname]
        exp = rom[roff:roff + wlen]
        print(f"== {fname}  ROM@0x{roff:05X} window={wlen}B")
        for fset_name, flags in FLAGSETS:
            outo = os.path.join(work, f"{fname}.{fset_name}.o")
            ok, err = compile_one(args.gcc, cfile, outo, flags, args.isa)
            if not ok:
                print(f"   [{fset_name:9s}] COMPILE-FAIL {err[:120].replace(chr(10),' ')}")
                results.append((fname, fset_name, "COMPILE-FAIL", 0, 0, None))
                continue
            got = text_bytes(outo)
            n = min(len(got), len(exp))
            nbyte = sum(1 for i in range(n) if got[i] == exp[i])
            same_i, tot_i, first_i, gi, ei = match_insn(got, exp)
            pct = 100.0 * nbyte / len(exp)
            verdict = "MATCH" if (nbyte == len(exp) and len(got) == len(exp)) else "diff"
            print(f"   [{fset_name:9s}] bytes {nbyte}/{len(exp)} ({pct:5.1f}%)  insn {same_i}/{tot_i}  -> {verdict}")
            results.append((fname, fset_name, verdict, nbyte, len(exp), same_i))
        print()

    print("\n# SUMMARY TABLE  (func x flagset -> matched bytes / window)")
    hdr = "func".ljust(20) + "".join(f"{f:>12}" for f, _ in FLAGSETS)
    print(hdr)
    for fname in args.funcs.split(","):
        row = fname.ljust(20)
        for fs, _ in FLAGSETS:
            r = next((x for x in results if x[0] == fname and x[1] == fs), None)
            if r is None:
                row += f"{'-':>12}"
            elif r[2] == "COMPILE-FAIL":
                row += f"{'CF':>12}"
            elif r[2] == "MATCH":
                row += f"{'MATCH!':>12}"
            else:
                row += f"{r[3]}/{r[4]}:{100*r[3]/r[4]:4.1f}%".rjust(12)
        print(row)

if __name__ == "__main__":
    main()
