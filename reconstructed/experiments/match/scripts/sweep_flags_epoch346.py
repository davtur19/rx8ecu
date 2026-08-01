#!/usr/bin/env python3
"""
sweep_flags_epoch346.py — NEW sweep (this session): GCC 3.4.6 flag matrix aimed
at the 4 structural divergences (branch polarity, return-register,
boolean/movt, loop-unroll) for the pure-math candidates.

GCC 3.4.6 SH has NO -mbranch-cost / -mnomovt / -madjust-unroll /
-maccumulate-outgoing-args / -mpretend-cmove (those are GCC 4.x).  The only
controls are the -m* target switches (m1/m2/m2e/m3/m4-*, mrenesas, mrelax,
misize, mspace, ...) plus the generic -f* knobs (-fno-if-conversion{,2} kill
movt/negc boolean idioms; -fno-delayed-branch kills delay-slot filling;
-funroll-all-loops / -fno-unroll-loops steer loop unrolling).

Usage: python3 scripts/sweep_flags_epoch346.py [--out /tmp/flagepoch/report.txt] [--funcs a,b,c]
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
    ("pulse_window_compute_FCD2_r4",         0xFCD2, 20),
    ("shift_right_8_r0_467A",                0x467A, 18),
    ("shift_right_8_r0_467A_loop",           0x467A, 18),
    ("obd_service_handler_67154_m1",         0x67154, 18),
    ("alignment_boundary_validator_D90C",    0xD90C, 38),
    ("alignment_boundary_validator_D90C_r6", 0xD90C, 38),
]

# (name, flags) — -m2e already prepended by the harness; -m1/-m3/-m4 override
FLAGSETS = [
    ("O1.omitfp",              ["-O1", "-fomit-frame-pointer"]),
    ("O2.omitfp",              ["-O2", "-fomit-frame-pointer"]),
    ("Os.omitfp",              ["-Os", "-fomit-frame-pointer"]),
    ("O1.noifconv",            ["-O1", "-fomit-frame-pointer", "-fno-if-conversion", "-fno-if-conversion2"]),
    ("O2.noifconv",            ["-O2", "-fomit-frame-pointer", "-fno-if-conversion", "-fno-if-conversion2"]),
    ("O1.noifconv.nodel",      ["-O1", "-fomit-frame-pointer", "-fno-if-conversion", "-fno-if-conversion2", "-fno-delayed-branch"]),
    ("O1.nodel",               ["-O1", "-fomit-frame-pointer", "-fno-delayed-branch"]),
    ("O2.unrollall",           ["-O2", "-fomit-frame-pointer", "-funroll-all-loops"]),
    ("O2.unroll",              ["-O2", "-fomit-frame-pointer", "-funroll-loops"]),
    ("O1.nounroll",            ["-O1", "-fomit-frame-pointer", "-fno-unroll-loops"]),
    ("m1.O1.omitfp",           ["-m1", "-O1", "-fomit-frame-pointer"]),
    ("m1.O1.noifconv",         ["-m1", "-O1", "-fomit-frame-pointer", "-fno-if-conversion", "-fno-if-conversion2"]),
    ("m3.O1.omitfp",           ["-m3", "-O1", "-fomit-frame-pointer"]),
    ("m3.O2.omitfp",           ["-m3", "-O2", "-fomit-frame-pointer"]),
    ("m4nofpu.O2.omitfp",      ["-m4-nofpu", "-O2", "-fomit-frame-pointer"]),
    ("renesas.O1",             ["-O1", "-fomit-frame-pointer", "-mrenesas"]),
    ("renesas.O2",             ["-O2", "-fomit-frame-pointer", "-mrenesas"]),
    ("relax.O1",               ["-O1", "-fomit-frame-pointer", "-mrelax"]),
    ("space.O1",               ["-O1", "-fomit-frame-pointer", "-mspace"]),
    ("isize.O1",               ["-O1", "-fomit-frame-pointer", "-misize"]),
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
    same_i = sum(1 for i in range(0, n - 1, 2) if got[i:i+2] == exp[i:i+2])
    first = next((i for i in range(n) if got[i] != exp[i]), None)
    return dict(nwin=len(exp), same_b=same_b, same_i=same_i, nins=n // 2,
                first=first, pct=(100.0 * same_b / len(exp)) if exp else 0.0)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/flagepoch/report.txt")
    ap.add_argument("--funcs", default=None)
    ap.add_argument("--flagsets", default=None, help="comma list of flagset names")
    args = ap.parse_args()
    workdir = "/tmp/flagepoch"
    os.makedirs(workdir, exist_ok=True)
    lines = []
    lines.append("# sweep_flags_epoch346  (GCC 3.4.6 xgcc, base -m2e; -m1/-m3/-m4 override)")
    lines.append("# flag matrix targeted at the 4 documented divergences\n")
    best = {}
    for fname, off, blen in CASES:
        if args.funcs and fname not in args.funcs.split(","):
            continue
        exp = rom_bytes(off, blen)
        lines.append(f"== {fname}  ROM@0x{off:05X} window={blen}B")
        for fset, flags in FLAGSETS:
            if args.flagsets and fset not in args.flagsets.split(","):
                continue
            ok, err, got = compile_and_get_text(fname, flags, workdir)
            if not ok:
                lines.append(f"   [{fset:18s}] FAIL {err[:60].replace(chr(10),' ')}")
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
