#!/usr/bin/env python3
"""iter_match.py — quick single-source byte-compare vs ROM window (m2e -O1 -fomit-frame-pointer).
Usage: python3 iter_match.py <c_src_name> <rom_off> <len>
Prints generated .text bytes + disasm vs ROM window bytes + disasm."""
import os, struct, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
MATCH = os.path.normpath(os.path.join(HERE, ".."))
SRC = os.path.join(MATCH, "c_src")
ROMF = os.path.normpath(os.path.join(HERE, "..", "..", "..", "..", "roms", "stock", "60E1D400.bin"))
STUB = "/tmp/stubinc"
XGCC = "/home/davide/gcc346-build/gcc/xgcc"
XB = "/home/davide/gcc346-build/gcc/"
AS = "/usr/bin/sh-elf-as"
OBJC = "/usr/bin/sh-elf-objcopy"

def main():
    name, off, n = sys.argv[1], int(sys.argv[2], 0), int(sys.argv[3], 0)
    opts = sys.argv[4] if len(sys.argv) > 4 else "-O1"
    wd = "/tmp/sweep_puremath"
    os.makedirs(wd, exist_ok=True)
    sfile = os.path.join(wd, f"{name}.iter.s")
    r = subprocess.run([XGCC, "-B", XB, "-nostdinc", "-I", STUB, "-S",
                        os.path.join(SRC, name + ".c"), "-o", sfile,
                        "-m2e"] + opts.split() + ["-fomit-frame-pointer"],
                       capture_output=True, text=True)
    if r.returncode:
        print("COMPILE FAIL:", r.stderr[-400:]); return
    subprocess.run([AS, "-isa=sh2e", "-o", sfile + ".o", sfile], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([OBJC, "-O", "binary", "--only-section=.text", sfile + ".o", sfile + ".bin"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    got = open(sfile + ".bin", "rb").read()
    exp = open(ROMF, "rb").read()[off:off + n]
    print(f"GOT {len(got)}B  ROM window {n}B")
    print("GOT :", got.hex())
    print("ROM :", exp.hex())
    ncmp = min(len(got), len(exp))
    same = sum(1 for i in range(ncmp) if got[i] == exp[i])
    print(f"same {same}/{len(exp)} ({100.0*same/len(exp):.1f}%)")
    d = open(sfile + ".bin", "rb")
    dd = subprocess.run(["/usr/bin/sh-elf-objdump", "-D", "-b", "binary", "-m", "sh2e", "-EB", sfile + ".bin"],
                        capture_output=True, text=True).stdout
    print(dd)

if __name__ == "__main__":
    main()
