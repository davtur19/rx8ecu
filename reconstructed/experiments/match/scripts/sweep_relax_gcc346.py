#!/usr/bin/env python3
"""
sweep_relax_gcc346.py — targeted -mrelax / -mhitachi / -mspace test (2026-08-02).

Question: does GCC 3.4.6 -mrelax (plus -mhitachi/-mspace) close the residual
gaps on the 3 last candidates (atu_spec 95%, pulse_r4 90%, shift_loop 66.7%)?
Those gaps are ONLY about the literal-pool layout / PC-relative displacement
of `mov.w @(pc),rN` (gcc pool@0x1FB6 vs ROM@0x1FB8 for atu).

Pipeline: xgcc 3.4.6 -S [-mrelax/-mhitachi/-mspace] -> sh-elf-as [-relax]
-> objcopy --only-section=.text -> byte-compare vs ROM body window.

Each run is also executed BOTH with and without `-relax` on the assembler
(asm-relax shortens long jumps; worth checking against the ROM branch forms).

Usage: python3 scripts/sweep_relax_gcc346.py [--out /tmp/sweep_relax/report.txt]
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

# name -> (rom_off, body_len, [ (flagset_label, flags), ... ])
# -m2e is prepended by the harness; later -m1/-m2 override it.
CASES = [
    ("atu_get_rx_byte_count_1FA2_spec", 0x1FA2, 20, [
        ("m1.O1.omitfp.noifconv",      ["-m1", "-O1", "-fomit-frame-pointer",
                                        "-fno-if-conversion", "-fno-if-conversion2"]),
        ("m1.O1.omitfp.noifconv.relax",["-m1", "-O1", "-fomit-frame-pointer",
                                        "-fno-if-conversion", "-fno-if-conversion2",
                                        "-mrelax"]),
        ("m2e.O1.omitfp.noifconv.relax",["-O1", "-fomit-frame-pointer",
                                        "-fno-if-conversion", "-fno-if-conversion2",
                                        "-mrelax"]),
        ("m1.O2.omitfp.noifconv.relax",["-m1", "-O2", "-fomit-frame-pointer",
                                        "-fno-if-conversion", "-fno-if-conversion2",
                                        "-mrelax"]),
        ("m1.O1.omitfp.noifconv.hitachi",["-m1", "-O1", "-fomit-frame-pointer",
                                        "-fno-if-conversion", "-fno-if-conversion2",
                                        "-mhitachi"]),
        ("m1.O1.omitfp.noifconv.space",["-m1", "-O1", "-fomit-frame-pointer",
                                        "-fno-if-conversion", "-fno-if-conversion2",
                                        "-mspace"]),
    ]),
    ("pulse_window_compute_FCD2_r4", 0xFCD2, 20, [
        ("m2e.O1.omitfp",             ["-O1", "-fomit-frame-pointer"]),
        ("m2e.O1.omitfp.relax",       ["-O1", "-fomit-frame-pointer", "-mrelax"]),
        ("m2.O1.omitfp.relax",        ["-m2", "-O1", "-fomit-frame-pointer", "-mrelax"]),
        ("m1.O1.omitfp.relax",        ["-m1", "-O1", "-fomit-frame-pointer", "-mrelax"]),
        ("m2e.O2.omitfp.relax",       ["-O2", "-fomit-frame-pointer", "-mrelax"]),
        ("m2e.O1.omitfp.hitachi",     ["-O1", "-fomit-frame-pointer", "-mhitachi"]),
        ("m2e.O1.omitfp.space",       ["-O1", "-fomit-frame-pointer", "-mspace"]),
    ]),
    ("shift_right_8_r0_467A_loop", 0x467A, 18, [
        ("m2e.O2.omitfp.unrollall",          ["-O2", "-fomit-frame-pointer",
                                              "-funroll-all-loops"]),
        ("m2e.O2.omitfp.unrollall.relax",    ["-O2", "-fomit-frame-pointer",
                                              "-funroll-all-loops", "-mrelax"]),
        ("m2e.O1.omitfp.nodel.unroll.relax", ["-O1", "-fomit-frame-pointer",
                                              "-fno-delayed-branch", "-funroll-loops",
                                              "-mrelax"]),
        ("m2.O1.omitfp.nodel.unroll.relax",  ["-m2", "-O1", "-fomit-frame-pointer",
                                              "-fno-delayed-branch",
                                              "-funroll-loops", "-mrelax"]),
        ("m1.O1.omitfp.nodel.unroll.relax",  ["-m1", "-O1", "-fomit-frame-pointer",
                                              "-fno-delayed-branch",
                                              "-funroll-loops", "-mrelax"]),
        ("m2e.O2.omitfp.unrollall.hitachi",  ["-O2", "-fomit-frame-pointer",
                                              "-funroll-all-loops", "-mhitachi"]),
        ("m2e.O2.omitfp.unrollall.space",    ["-O2", "-fomit-frame-pointer",
                                              "-funroll-all-loops", "-mspace"]),
    ]),
]

def rom_bytes(off, n):
    return open(ROMF, "rb").read()[off:off+n]

def compile_and_get_text(fname, flags, as_relax, workdir):
    cfile = os.path.join(SRC, fname + ".c")
    if not os.path.exists(cfile):
        return False, "no source", None
    sfx = fname + "." + ".".join(f.replace("-", "").replace("/", "_") for f in flags)
    sfile = os.path.join(workdir, sfx + ".s")
    ofile = sfile + ".o"
    bfile = sfile + ".bin"
    cmds = [XGCC, "-B", XB, "-nostdinc", "-I", STUB, "-S", cfile, "-o", sfile,
            "-m2e"] + flags
    r = subprocess.run(cmds, capture_output=True, text=True)
    if r.returncode != 0:
        return False, r.stderr[-200:], None
    asargs = [AS, "-isa=sh2e"]
    if as_relax:
        asargs.append("-relax")
    r2 = subprocess.run(asargs + ["-o", ofile, sfile], capture_output=True, text=True)
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
    return dict(nwin=len(exp), nbyte=len(got), same_b=same_b, same_i=same_i,
                nins=n // 2, first=first,
                pct=(100.0 * same_b / len(exp)) if exp else 0.0)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/sweep_relax/report.txt")
    ap.add_argument("--funcs", default=None)
    args = ap.parse_args()
    workdir = "/tmp/sweep_relax"
    os.makedirs(workdir, exist_ok=True)
    lines = []
    lines.append("# sweep_relax_gcc346  (GCC 3.4.6 xgcc, base -m2e; m1/m2 override)")
    lines.append("# targeted -mrelax / -mhitachi / -mspace test; as assembled with AND")
    lines.append("# without -relax to separate compiler effect from assembler effect\n")
    for fname, off, blen, flagset in CASES:
        if args.funcs and fname not in args.funcs.split(","):
            continue
        exp = rom_bytes(off, blen)
        lines.append(f"== {fname}  ROM@0x{off:05X} window={blen}B  ROM={exp.hex()}")
        for label, flags in flagset:
            for arel in (False, True):
                ok, err, got = compile_and_get_text(fname, flags, arel, workdir)
                if not ok:
                    lines.append(f"   [{label:32s} as-relax={int(arel)}] FAIL "
                                 f"{err[:60].replace(chr(10),' ')}")
                    continue
                res = compare(got, exp)
                tag = "MATCH" if (res["same_b"] == res["nwin"] and len(got) == len(exp)) else "diff"
                fstr = f"first@+0x{res['first']:02X}" if res["first"] is not None else "first=-"
                lines.append(f"   [{label:32s} as-relax={int(arel)}] bytes "
                             f"{res['same_b']:3d}/{res['nwin']:3d} ({res['pct']:5.1f}%) "
                             f"insn {res['same_i']:3d}/{res['nins']:3d} {fstr}  {tag}")
        lines.append("")
    report = "\n".join(lines)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(report + "\n")
    print(report)

if __name__ == "__main__":
    main()
