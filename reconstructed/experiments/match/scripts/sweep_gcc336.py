#!/usr/bin/env python3
"""
sweep_gcc336.py — full matrix sweep for the match-and-compile experiment using
GCC 3.3.6 sh-elf (xgcc from /home/davide/gcc336-build), the era of the RX-8 ROM.

Key difference vs the 3.4.6 harnesses: **GCC 3.3.6 has NO -m2e** (cc1 rejects
"2e"); the SH-2 core without the single FPU is selected with plain **-m2**
(same core: SH-2 big-endian, no FPU).  Also 3.3.6 does not accept
-mrenesas/-mhitachi/-mrelax/-mspace/-misize/-mnomacsave (dropped as
unrecognized), so the flag matrix below uses only the -f* knobs that exist in
3.3.6 plus the -m1/-m3/-m4-nofpu CPU switches.

Pipeline: gcc 3.3.6 -S -> /usr/bin/sh-elf-as (-isa=sh2e; superset, accepts all
SH-2 integer insns) -> sh-elf-objcopy --only-section=.text -> byte compare
against the exact ROM window (offset-relative), same as sweep_gcc346.py.

Usage: python3 scripts/sweep_gcc336.py [--out /tmp/sweep_gcc336/report.txt]
              [--funcs a,b,c] [--flagset O1.omitfp]
"""
import argparse, os, re, struct, subprocess, sys, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
MATCH = os.path.normpath(os.path.join(HERE, ".."))
SRC   = os.path.join(MATCH, "c_src")
EXP   = os.path.join(MATCH, "expected_gcc_sh2e")
ROOT  = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
ROMF  = os.path.join(ROOT, "roms", "stock", "60E1D400.bin")
STUB  = "/tmp/stubinc"
XGCC  = "/home/davide/gcc336-build/gcc/xgcc"
XB    = "/home/davide/gcc336-build/gcc/"
AS    = "/usr/bin/sh-elf-as"
OBJC  = "/usr/bin/sh-elf-objcopy"

# name -> (rom_off, window_len)
# windows match sweep_puremath_gcc346.py (body only; pools non-contiguous
# excluded) and sweep_gcc346.py for the saturating-add family (body+pool).
CASES = [
    ("add16bitSaturate",                     0x2460, 24),
    ("add16bitSaturate_reg",                 0x2460, 24),
    ("addSaturate8Bit",                      0x2478, 24),
    ("addSaturate8Bit_reg",                  0x2478, 24),
    ("addS32Saturate",                       0x2304, 24),
    ("addS32Saturate_addv",                  0x2304, 24),
    ("seed_mixer",                           0x366B8, 164),
    ("complement_shift_u16_2430",            0x2430, 16),
    ("complement_shift_u16_2430_match",      0x2430, 16),
    ("encode_2420",                          0x2420, 16),
    ("encode_2420_match",                    0x2420, 16),
    ("atu_get_rx_byte_count_1FA2",           0x1FA2, 20),
    ("atu_get_rx_byte_count_1FA2_spec",      0x1FA2, 20),
    ("can_get_mailbox_offset_high_D164",     0xD164, 22),
    ("can_get_mailbox_offset_high_D164_spec",0xD164, 22),
    ("getHCANRegisterAddress_D198",          0xD198, 20),
    ("getHCANRegisterAddress_D198_spec",     0xD198, 20),
    ("pulse_window_compute_FCD2",            0xFCD2, 20),
    ("pulse_window_compute_FCD2_r4",         0xFCD2, 20),
    ("calc_manifold_pressure_error_diff_10A88", 0x10A88, 22),
    ("obd_service_handler_67154",            0x67154, 18),
    ("obd_service_handler_67154_branch",     0x67154, 18),
    ("obd_service_handler_67154_m1",         0x67154, 18),
    ("charging_status_59C24",                0x59C24, 18),
    ("charging_status_59C24_branch",         0x59C24, 18),
    ("shift_right_8_r0_467A",                0x467A, 18),
    ("shift_right_8_r0_467A_loop",           0x467A, 18),
    ("alignment_boundary_validator_D90C",    0xD90C, 38),
    ("alignment_boundary_validator_D90C_r6", 0xD90C, 38),
]

# (name, flags) — -m2 (base SH-2 core) is prepended by the harness; -m1/-m3/-m4 override.
FLAGSETS = [
    ("O0.omitfp",              ["-O0", "-fomit-frame-pointer"]),
    ("O1.default",             ["-O1"]),
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
]

def rom_bytes(off, n):
    return open(ROMF, "rb").read()[off:off+n]

def ins_list(data, base=0):
    out = []
    for i in range(0, len(data) - 1, 2):
        op = struct.unpack(">H", data[i:i+2])[0]
        out.append((i, op, f"{op:04X}", ""))
    return out

def compile_and_get_text(fname, flags, workdir):
    cfile = os.path.join(SRC, fname + ".c")
    if not os.path.exists(cfile):
        return False, "no source", None
    suffix = fname + "." + ".".join(f.replace("-", "").replace("/", "_") for f in flags)
    sfile = os.path.join(workdir, suffix + ".s")
    ofile = sfile + ".o"
    bfile = sfile + ".bin"
    cmds = [XGCC, "-B", XB, "-nostdinc", "-I", STUB, "-S", cfile, "-o", sfile, "-m2"] + flags
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
    gi = ins_list(got[:n - (n % 2)])
    ei = ins_list(exp[:n - (n % 2)])
    mi = min(len(gi), len(ei))
    same_i = sum(1 for i in range(mi) if gi[i][1] == ei[i][1])
    first = next((i for i in range(n) if got[i] != exp[i]), None)
    return dict(nbyte=len(got), nwin=len(exp), ncmp=n, same_b=same_b,
                same_i=same_i, nins=mi, first=first,
                pct=(100.0 * same_b / len(exp)) if exp else 0.0)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/sweep_gcc336/report.txt")
    ap.add_argument("--funcs", default=None)
    ap.add_argument("--flagsets", default=None, help="comma list of flagset names")
    args = ap.parse_args()

    workdir = "/tmp/sweep_gcc336"
    os.makedirs(workdir, exist_ok=True)
    os.makedirs(EXP, exist_ok=True)

    ver = subprocess.run([XGCC, "-B", XB, "-dumpversion"], capture_output=True, text=True).stdout.strip()
    target = subprocess.run([XGCC, "-B", XB, "-dumpmachine"], capture_output=True, text=True).stdout.strip()

    lines = []
    lines.append(f"# sweep_gcc336  gcc={XGCC}  version={ver}  target={target}")
    lines.append(f"# base ISA = -m2 (GCC 3.3.6 has NO -m2e; SH-2 core, no single FPU)")
    lines.append(f"# as={AS} -isa=sh2e  objcopy={OBJC}  stdint stub={STUB}")
    lines.append(f"# window = body bytes from ROM (offset-relative)\n")

    best = {}
    funcs = args.funcs.split(",") if args.funcs else [c[0] for c in CASES]
    for fname in funcs:
        c = next((x for x in CASES if x[0] == fname), None)
        if not c:
            lines.append(f"!! no case for {fname}")
            continue
        off, blen = c[1], c[2]
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
            if res["pct"] > best.get(fname, (0,))[0]:
                best[fname] = (res["pct"], fset, flags, res, tag)
            lines.append(f"   [{fset:18s}] bytes {res['same_b']:3d}/{res['nwin']:3d} "
                         f"({res['pct']:5.1f}%) insn {res['same_i']:3d}/{res['nins']:3d} "
                         f"{fstr}  {tag}")
        lines.append("")

    lines.append("# === BEST PER SOURCE (GCC 3.3.6, base -m2) ===")
    for fname, (pct, fset, flags, res, tag) in sorted(best.items()):
        fstr = f"first@+0x{res['first']:02X}" if res["first"] is not None else "first=-"
        lines.append(f"{fname:42s} [{fset:18s}] {pct:5.1f}%  {res['same_b']}/{res['nwin']} "
                     f"{fstr}  {tag}")
        if tag == "MATCH":
            cmd = f"{XGCC} -B {XB} -nostdinc -I {STUB} -c {fname}.c -m2 {' '.join(flags)}"
            lines.append(f"  >>> BYTE-PERFECT MATCH cmd: {cmd}")
            src = os.path.join(workdir, f"{fname}." + ".".join(
                f.replace("-", "").replace("/", "_") for f in flags) + ".s")
            if os.path.exists(src):
                dst = os.path.join(EXP, f"{fname}.m2.{fset}.s")
                shutil.copy(src, dst)
                lines.append(f"  >>> .s saved to expected_gcc_sh2e/{fname}.m2.{fset}.s")

    report = "\n".join(lines)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(report + "\n")
    print(report)

if __name__ == "__main__":
    main()
