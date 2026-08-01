#!/usr/bin/env python3
"""
sweep_puremath_gcc346.py — sweep the extended pure-math candidate set against
GCC 3.4.6 (era ROM).  Same compile/assemble/compare pipeline as sweep_gcc346.py.

Each candidate has an exact ROM window (body bytes only; literal pools that are
not physically adjacent are excluded from the window and listed for info).

Usage: python3 scripts/sweep_puremath_gcc346.py [--out /tmp/sweep_puremath/report.txt]
"""
import argparse, os, re, struct, subprocess, sys, shutil

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

# name -> (rom_off, body_len, pool_info)
# pool_info: "" if none, "pool@0xXXXX:NN" for info (non-contiguous)
CASES = [
    ("complement_shift_u16_2430",            0x2430, 16, ""),
    ("encode_2420",                          0x2420, 16, ""),
    ("atu_get_rx_byte_count_1FA2",           0x1FA2, 20, "pool@0x1FB8:2"),
    ("getHCANRegisterAddress_D198",          0xD198, 20, "pool@0xD1BA:2"),
    ("can_get_mailbox_offset_high_D164",     0xD164, 22, "pool@0xD186:2"),
    ("pulse_window_compute_FCD2",            0xFCD2, 20, "pool@0xFD54:4"),
    ("calc_manifold_pressure_error_diff_10A88", 0x10A88, 22, "pool@0x10C2C:4+0x10C30:4"),
    ("obd_service_handler_67154",            0x67154, 18, ""),
    ("charging_status_59C24",                0x59C24, 18, ""),
    ("shift_right_8_r0_467A",                0x467A, 18, ""),
    ("alignment_boundary_validator_D90C",    0xD90C, 38, ""),
]

OPTS   = ["-O0", "-O1", "-O2", "-Os"]
EXTRAS = [
    ("default",   []),
    ("nodel",     ["-fno-delayed-branch"]),
    ("omitfp",    ["-fomit-frame-pointer"]),
    ("no-omitfp", ["-fno-omit-frame-pointer"]),
]

def rom_bytes(off, n):
    rom = open(ROMF, "rb").read()
    return rom[off:off+n]

def ins_list(data, base=0):
    out = []
    for i in range(0, len(data) - 1, 2):
        op = struct.unpack(">H", data[i:i+2])[0]
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
    ap.add_argument("--out", default="/tmp/sweep_puremath/report.txt")
    ap.add_argument("--funcs", default=",".join(c[0] for c in CASES))
    args = ap.parse_args()

    workdir = "/tmp/sweep_puremath"
    os.makedirs(workdir, exist_ok=True)

    ver = subprocess.run([XGCC, "-B", XB, "-dumpversion"], capture_output=True, text=True).stdout.strip()
    lines = []
    lines.append(f"# sweep_puremath_gcc346  gcc={XGCC}  version={ver}")
    lines.append(f"# window = body bytes only (pools non-contiguous listed for info)\n")

    best = {}
    funcs = args.funcs.split(",")
    for fname in funcs:
        c = next(x for x in CASES if x[0] == fname)
        off, blen, poolinfo = c[1], c[2], c[3]
        exp = rom_bytes(off, blen)
        lines.append(f"== {fname}  ROM@0x{off:05X} window={blen}B  {poolinfo}")
        for opt in OPTS:
            for ename, extra in EXTRAS:
                suffix = f"m2e.{opt}.{ename}"
                ok, err, got = compile_and_get_text(fname, "-m2e", [opt], extra, workdir, suffix)
                if not ok:
                    lines.append(f"   [{suffix:24s}] COMPILE-FAIL {err[:80].replace(chr(10),' ')}")
                    continue
                res = compare(got, exp)
                tag = "MATCH" if (res["nbyte"] == res["nwin"] and res["same_b"] == res["nwin"]) else "diff"
                if res["pct"] > best.get(fname, (0,))[0]:
                    best[fname] = (res["pct"], suffix, res, tag)
                firsts = f"first@+0x{res['first']:02X}" if res["first"] is not None else "first=-"
                lines.append(f"   [{suffix:24s}] bytes {res['same_b']:3d}/{res['nwin']:3d} "
                             f"({res['pct']:5.1f}%) insn {res['same_i']:3d}/{res['nins']:3d} "
                             f"{firsts}  {tag}")
        lines.append("")

    lines.append("# === BEST PER FUNCTION (m2e) ===")
    for fname, (pct, suffix, res, tag) in best.items():
        firsts = f"first@+0x{res['first']:02X}" if res["first"] is not None else "first=-"
        lines.append(f"{fname}: best {pct:.1f}%  [{suffix}]  bytes {res['same_b']}/{res['nwin']} "
                     f"insn {res['same_i']}/{res['nins']} {firsts}  {tag}")

    report = "\n".join(lines)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(report + "\n")
    print(report)

if __name__ == "__main__":
    main()
