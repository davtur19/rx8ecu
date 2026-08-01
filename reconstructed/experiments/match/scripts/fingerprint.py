#!/usr/bin/env python3
"""
fingerprint.py — Compiler fingerprinting on the RX-8 ROM annotated asm.

Reads ../../../../../src/60E1D400_annotated.s (read-only) and computes:
  * prologue style statistics (first 1-2 instructions of each function)
  * epilogue style statistics (delay slot after `rts`)
  * frequency of distinctive instructions: addv/subv, div0s/div1 (div library),
    mac.l/mulu.w/muls.w, FPU ops, stc/ldc SR (privileged), mov.l @(r15)...
Used by reconstructed/experiments/match/REPORT.md to fingerprint the compiler
that produced the ROM.

Usage: python3 fingerprint.py [path-to-annotated.s]
"""
import re
import sys
import os
import collections

_HERE = os.path.dirname(os.path.abspath(__file__))
S = os.path.join(_HERE, "..", "..", "..", "..", "src", "60E1D400_annotated.s")
if len(sys.argv) > 1:
    S = sys.argv[1]

FUNC_RE = re.compile(r"^! --- (\S+)\s+0x([0-9a-fA-F]+)-0x([0-9a-fA-F]+)")
INS_RE = re.compile(r"^\s+(\S+)\s*(.*)$")

def norm(instr):
    """Return a canonical signature of an instruction line."""
    m = INS_RE.match(instr)
    if not m:
        return None
    mnem = m.group(1)
    ops = m.group(2).strip()
    # strip label / comment markers and addresses for comparisons
    ops = re.sub(r"0x[0-9a-fA-F]+", "X", ops)
    return mnem, ops

stats = collections.Counter()
epi_delay = collections.Counter()
pro_probe = collections.Counter()
distinct = collections.Counter()
n_funcs = 0
cur = None

with open(S) as f:
    for line in f:
        fm = FUNC_RE.match(line)
        if fm:
            cur = fm.group(1)
            n_funcs += 1
            stats["total_functions"] += 1
            continue
        if cur is None or not line.strip():
            continue
        ins = norm(line)
        if ins is None:
            continue
        mnem = ins[0]

        # ---- distinctive instructions ----
        if mnem in ("addv", "subv"):
            distinct[f"addv/subv({mnem})"] += 1
        elif mnem in ("div0s", "div1"):
            distinct["div0s/div1"] += 1
        elif mnem in ("mulu.w", "muls.w", "mul.l"):
            distinct[mnem] += 1
        elif mnem in ("mac.l", "mac.w"):
            distinct[mnem] += 1
        elif mnem.startswith("f"):
            distinct["FPU(" + mnem + ")"] += 1
        elif mnem in ("stc", "ldc"):
            distinct[f"{mnem} {ins[1][:8]}"] += 1
        elif mnem in ("stc.l", "ldc.l"):
            distinct[f"{mnem} {ins[1][:8]}"] += 1
        elif mnem in ("rts",):
            epi_delay["rts_total"] += 1
            continue  # handled below with next line
        elif mnem in ("sleep", "trapa", "tas.b", "ldtlb"):
            distinct[f"system({mnem})"] += 1

        # ---- epilogue: capture instruction right after rts ----
        if epi_delay["rts_total"] > epi_delay.get("rts_seen", 0):
            epi_delay["rts_seen"] += 1
            if mnem == "nop":
                epi_delay["rts;nop"] += 1
            elif mnem in ("mov", "mov.l", "mov.w", "mov.b"):
                epi_delay["rts;mov*"] += 1
            else:
                epi_delay[f"rts;{mnem}"] += 1

        # ---- prologue probes (only for the first real instruction seen) ----
        if not pro_probe.get(cur):
            pro_probe[cur] = mnem
            if mnem == "mov.l":
                ops = ins[1]
                if ops.startswith("r14,@-r15"):
                    stats["prologue: mov.l r14,@-r15"] += 1
                elif ops.startswith("r8,@-r15"):
                    stats["prologue: mov.l r8,@-r15"] += 1
                elif "@-r15" in ops:
                    stats["prologue: mov.l other,@-r15"] += 1
                elif ops.startswith("@(X,") or ops.startswith("@"):
                    stats["prologue: mov.l (load)"] += 1
                else:
                    stats["prologue: mov.l other"] += 1
            elif mnem == "add":
                ops = ins[1]
                if "#" in ops and "r15" in ops:
                    stats["prologue: add #imm,r15"] += 1
                else:
                    stats["prologue: add other"] += 1
            elif mnem == "mov":
                ops = ins[1]
                if "#" in ops:
                    stats["prologue: mov #imm,rN"] += 1
                elif "r15" in ops:
                    stats["prologue: mov rN,r15"] += 1
                else:
                    stats["prologue: mov reg,reg"] += 1
            elif mnem == "stc":
                stats["prologue: stc SR"] += 1
            elif mnem in ("extu.b", "extu.w", "exts.b", "exts.w"):
                stats[f"prologue: {mnem}"] += 1
            elif mnem == "mov.l":
                stats["prologue: mov.l @(...)"] += 1
            else:
                stats[f"prologue: {mnem}"] += 1

print(f"Functions parsed: {n_funcs}\n")
print("=== PROLOGUE (first instruction of function) ===")
for k in sorted(stats):
    if k.startswith("prologue") or k.startswith("total"):
        print(f"  {k:40s} {stats[k]:5d}  {100*stats[k]/n_funcs:5.1f}%")
print("\n=== EPILOGUE (delay-slot instruction after rts) ===")
for k in sorted(epi_delay):
    if k != "rts_total":
        print(f"  {k:24s} {epi_delay[k]:5d}")
print(f"  (total rts: {epi_delay['rts_total']})")
print("\n=== DISTINCTIVE INSTRUCTIONS ===")
for k in sorted(distinct):
    print(f"  {k:32s} {distinct[k]:5d}")
