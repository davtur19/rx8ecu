#!/usr/bin/env python3
"""
sweep_flagmatrix_gcc346.py — targeted flag-matrix sweep for the pure-math
candidates (GCC 3.4.6).  Complements sweep_puremath_gcc346.py by adding the
flag families that actually change the four documented divergences:

  1. branch polarity / delay-slot scheduling: -fno-if-conversion{,2}
     (kills movt/negc boolean idioms), -fno-delayed-branch,
  2. loop unrolling: -funroll-loops / -funroll-all-loops,
  3. plus the new hand-tuned c_src/*_match / *_branch sources.

Usage: python3 scripts/sweep_flagmatrix_gcc346.py [--out /tmp/flagmatrix/report.txt]
"""
import argparse, os, struct, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
MATCH = os.path.normpath(os.path.join(HERE, ".."))
SRC   = os.path.join(MATCH, "c_src")
ROOT  = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
ROMF  = os.path.join(ROOT, "roms", "stock", "60E1D400.bin")
STUB  = "/tmp/stubinc"
XGCC  = "/home/davide/gcc346-build/gcc/xgcc"
XB    = "/home/davide/gcc346-build/gcc/"
AS    = "/usr/bin/sh-elf-as"
OBJC  = "/usr/bin/sh-elf-objcopy"

# (src_base_name, rom_off, body_len)  — src name may differ from func name
CASES = [
    ("complement_shift_u16_2430",            0x2430, 16),
    ("complement_shift_u16_2430_match",      0x2430, 16),
    ("encode_2420",                          0x2420, 16),
    ("encode_2420_match",                    0x2420, 16),
    ("atu_get_rx_byte_count_1FA2",           0x1FA2, 20),
    ("can_get_mailbox_offset_high_D164",     0xD164, 22),
    ("getHCANRegisterAddress_D198",          0xD198, 20),
    ("charging_status_59C24",                0x59C24, 18),
    ("charging_status_59C24_branch",         0x59C24, 18),
    ("obd_service_handler_67154",            0x67154, 18),
    ("obd_service_handler_67154_branch",     0x67154, 18),
    ("calc_manifold_pressure_error_diff_10A88", 0x10A88, 22),
    ("pulse_window_compute_FCD2",            0xFCD2, 20),
    ("shift_right_8_r0_467A",                0x467A, 18),
    ("alignment_boundary_validator_D90C",    0xD90C, 38),
]

FLAGSETS = [
    ("baseline-O1.omitfp",       ["-O1", "-fomit-frame-pointer"]),
    ("baseline-O2.omitfp",       ["-O2", "-fomit-frame-pointer"]),
    ("noifconv-O1",              ["-O1", "-fomit-frame-pointer", "-fno-if-conversion", "-fno-if-conversion2"]),
    ("noifconv-O1.nodel",        ["-O1", "-fomit-frame-pointer", "-fno-if-conversion", "-fno-if-conversion2", "-fno-delayed-branch"]),
    ("noifconv-O2",              ["-O2", "-fomit-frame-pointer", "-fno-if-conversion", "-fno-if-conversion2"]),
    ("unroll-all-O2",            ["-O2", "-fomit-frame-pointer", "-funroll-all-loops"]),
    ("unroll-loops-O1",          ["-O1", "-fomit-frame-pointer", "-funroll-loops"]),
    ("renesas-O1",               ["-O1", "-fomit-frame-pointer", "-mrenesas"]),
    ("m3-O1.omitfp",             ["-m3", "-O1", "-fomit-frame-pointer"]),
    ("m4nofpu-O2.omitfp",        ["-m4-nofpu", "-O2", "-fomit-frame-pointer"]),
    ("m1-O1.omitfp",             ["-m1", "-O1", "-fomit-frame-pointer"]),
    ("m1-noifconv-O1",           ["-m1", "-O1", "-fomit-frame-pointer", "-fno-if-conversion", "-fno-if-conversion2"]),
]

def rom_bytes(off, n):
    return open(ROMF, "rb").read()[off:off+n]

def compile_and_get_text(fname, flags, workdir):
    cfile = os.path.join(SRC, fname + ".c")
    if not os.path.exists(cfile):
        return False, "no source", None
    suffix = fname + "." + ".".join(f.replace("-", "").replace("/", "_") for f in flags)
    sfile = os.path.join(workdir, suffix + ".s")
    ofile = sfile + ".o"
    bfile = sfile + ".bin"
    cmds = [XGCC, "-B", XB, "-nostdinc", "-I", STUB, "-S", cfile, "-o", sfile, "-m2e"] + flags
    r = subprocess.run(cmds, capture_output=True, text=True)
    if r.returncode != 0:
        return False, r.stderr[-200:], None
    r2 = subprocess.run([AS, "-isa=sh2e", "-o", ofile, sfile], capture_output=True, text=True)
    if r2.returncode != 0:
        return False, r2.stderr[-200:], None
    r3 = subprocess.run([OBJC, "-O", "binary", "--only-section=.text", ofile, bfile],
                        capture_output=True, text=True)
    if r3.returncode != 0:
        return False, r3.stderr[-200:], None
    return True, "", open(bfile, "rb").read()

def compare(got, exp):
    n = min(len(got), len(exp))
    same_b = sum(1 for i in range(n) if got[i] == exp[i])
    mi = min(len(got), len(exp)) // 2
    same_i = sum(1 for i in range(0, n - 1, 2) if got[i:i+2] == exp[i:i+2])
    first = next((i for i in range(n) if got[i] != exp[i]), None)
    return dict(nwin=len(exp), same_b=same_b, same_i=same_i, nins=mi,
                first=first, pct=(100.0*same_b/len(exp)) if exp else 0.0)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/flagmatrix/report.txt")
    ap.add_argument("--funcs", default=None, help="comma list to filter")
    args = ap.parse_args()
    workdir = "/tmp/flagmatrix"
    os.makedirs(workdir, exist_ok=True)
    lines = []
    lines.append("# sweep_flagmatrix_gcc346  (GCC 3.4.6 xgcc, -m2e base; -m1 sets override)")
    lines.append("# flags matrix = targeted at the 4 documented divergences\n")
    best = {}
    for fname, off, blen in CASES:
        if args.funcs and fname not in args.funcs.split(","):
            continue
        lines.append(f"== {fname}  ROM@0x{off:05X} window={blen}B")
        for fset, flags in FLAGSETS:
            ok, err, got = compile_and_get_text(fname, flags, workdir)
            if not ok:
                lines.append(f"   [{fset:18s}] FAIL {err[:60]}")
                continue
            res = compare(got, exp)
            tag = "MATCH" if (res["same_b"] == res["nwin"] and len(got) == len(exp)) else "diff"
            fstr = f"first@+0x{res['first']:02X}" if res["first"] is not None else "first=-"
            key = (fname, fset)
            if res["pct"] > best.get(key, (0,))[0]:
                best[key] = (res["pct"], fstr, tag, res)
            lines.append(f"   [{fset:18s}] bytes {res['same_b']:3d}/{res['nwin']:3d} "
                         f"({res['pct']:5.1f}%) insn {res['same_i']:3d}/{res['nins']:3d} "
                         f"{fstr}  {tag}")
        lines.append("")
    lines.append("# === BEST PER SOURCE x FLAGSET ===")
    for (fname, fset), (pct, fstr, tag, res) in sorted(best.items()):
        lines.append(f"{fname:42s} [{fset:18s}] {pct:5.1f}%  {res['same_b']}/{res['nwin']} {fstr} {tag}")
    report = "\n".join(lines)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(report + "\n")
    print(report)

if __name__ == "__main__":
    main()
