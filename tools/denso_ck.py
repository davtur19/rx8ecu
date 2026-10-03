#!/usr/bin/env python3
"""
denso_ck.py - DENSO SH7055 checksum tool

Verify or fix the checksum of a Mazda RX-8 ROM (60Exxxxx).

  Algorithm: sum_dwords(ROM, lo, hi, step=4) + diff = 0x5AA5A55A
  Descriptor at 0x7FB80: [lo:4][hi:4][diff:4]

Coverage (read this before trusting "OK"): the algorithm sums only the
dwords in [lo, hi) from the descriptor (e.g. 0x2000-0x7DAFF on stock
ROMs). Bytes outside that range (vector table, calibration band tail,
etc.) are NOT covered, so corruption there is undetectable by this
algorithm. Every run prints the verified range plus a WARNING naming the
uncovered segments. For a whole-file gate (e.g. on imports) pass
--expect-sha256 <hex>: the full-file sha256 must match or the tool fails.

Usage:
  python denso_ck.py <rom.bin>              # verify only
  python denso_ck.py <rom.bin> -f           # fix in place
  python denso_ck.py <rom.bin> -o out.bin   # fix a copy
  python denso_ck.py <rom.bin> --expect-sha256 <hex>  # gate full-file sha256
"""

import sys
import os
import shutil
import struct
import argparse
import hashlib
import re
import tempfile
from pathlib import Path

TARGET   = 0x5AA5A55A
DESC_OFF = 0x7FB80
DIFF_OFF = 0x7FB88
ROM_LEN  = 512 * 1024  # 524288


def compute(rom):
    lo  = struct.unpack_from(">I", rom, DESC_OFF)[0]
    hi  = struct.unpack_from(">I", rom, DESC_OFF + 4)[0]
    s   = sum(struct.unpack_from(">I", rom, j)[0] for j in range(lo, hi, 4)) & 0xFFFFFFFF
    return lo, hi, s, (TARGET - s) & 0xFFFFFFFF


def check_bounds(lo, hi, length):
    """Return an error string when the descriptor is invalid, else None.

    The checksum loop is sum(struct.unpack_from(">I", rom, j) for j in
    range(lo, hi, 4)): only lo must be 4-byte aligned.  hi may be
    unaligned (stock ROMs use e.g. hi=0x7DAFF); range() simply stops at
    the last full dword, so no hi-alignment requirement is enforced.
    """
    if not (0 <= lo < hi <= length):
        return (f"Invalid descriptor range: lo=0x{lo:X} hi=0x{hi:X} "
                f"(need 0 <= lo < hi <= 0x{length:X})")
    if lo % 4 != 0:
        return f"Invalid descriptor: lo=0x{lo:X} is not 4-byte aligned"
    return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("-f", "--fix",    action="store_true", help="fix in place")
    ap.add_argument("-o", "--output", metavar="FILE",      help="fix a copy")
    ap.add_argument("--expect-sha256", metavar="HEX",
                    help="full-file sha256 of the INPUT file: FAIL (exit 1) "
                         "when it does not match; whole-file integrity gate "
                         "for imports")
    args = ap.parse_args(argv)

    if args.fix and args.output:
        print("Error: -f/--fix and -o/--output are mutually exclusive "
              "(in-place fix vs copy); use one or the other.",
              file=sys.stderr)
        return 2

    try:
        raw = Path(args.rom).read_bytes()
    except FileNotFoundError:
        print(f"Error: ROM not found: {args.rom}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Error: cannot read ROM {args.rom}: {e}", file=sys.stderr)
        return 1

    if len(raw) != ROM_LEN:
        print(f"Error: expected {ROM_LEN}-byte (512 KiB) ROM, "
              f"got {len(raw)} bytes: {args.rom}", file=sys.stderr)
        return 1

    # Optional whole-file integrity gate: the checksum algorithm below covers
    # only [lo, hi); --expect-sha256 pins the ENTIRE file (imports).
    if args.expect_sha256 is not None:
        want = args.expect_sha256.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", want):
            print("Error: --expect-sha256 must be a 64-character hex sha256.",
                  file=sys.stderr)
            return 2
        got_sha = hashlib.sha256(raw).hexdigest()
        if got_sha != want:
            print(f"FAIL: sha256 mismatch (expected {want}, got {got_sha})")
            return 1
        print(f"sha256 : {want} matches --expect-sha256")

    rom = bytearray(raw)
    try:
        lo, hi, s, correct = compute(rom)
        stored = struct.unpack_from(">I", rom, DIFF_OFF)[0]
    except struct.error as e:
        print(f"Error: cannot parse checksum descriptor at 0x{DESC_OFF:X}: {e}",
              file=sys.stderr)
        return 1

    print(f"Range  : 0x{lo:05X} - 0x{hi:05X}")
    print(f"Sum    : 0x{s:08X}")
    print(f"Stored : 0x{stored:08X}")
    print(f"Correct: 0x{correct:08X}")

    bad = check_bounds(lo, hi, len(rom))
    if bad is not None:
        print(f"Error: {bad}; refusing to fix.", file=sys.stderr)
        return 1

    # Honest coverage disclosure: this algorithm verifies ONLY [lo, hi).
    # Name the segments it cannot see, so a green result is never mistaken
    # for whole-file integrity (use --expect-sha256 for that).
    uncovered = []
    if lo > 0:
        uncovered.append(f"[0x00000-0x{lo:05X})")
    if hi < len(rom):
        uncovered.append(f"[0x{hi:05X}-0x{len(rom):05X})")
    if uncovered:
        print(f"WARNING: checksum covers only 0x{lo:05X}-0x{hi:05X}; "
              f"bytes {', '.join(uncovered)} are NOT covered - corruption "
              "there is undetectable by this algorithm")

    if stored == correct:
        print(f"OK: checksum valid (verified range 0x{lo:05X}-0x{hi:05X})")
        return 0

    print("FAIL: checksum mismatch")

    if not args.fix and not args.output:
        print("Use -f to fix in place or -o <file> for a copy.")
        return 1

    # Patch a COPY first, then re-compute and compare before touching disk.
    fixed = bytearray(rom)
    struct.pack_into(">I", fixed, DIFF_OFF, correct)
    try:
        _lo2, _hi2, s2, correct2 = compute(fixed)
        stored2 = struct.unpack_from(">I", fixed, DIFF_OFF)[0]
    except struct.error as e:
        print(f"Error: re-computation failed after patch: {e}", file=sys.stderr)
        return 1
    if stored2 != correct2 or (s2 + stored2) & 0xFFFFFFFF != TARGET:
        print("Error: patched image does not verify; refusing to write.",
              file=sys.stderr)
        return 1

    if args.output:
        try:
            Path(args.output).write_bytes(bytes(fixed))
        except OSError as e:
            print(f"Error: cannot write {args.output}: {e}", file=sys.stderr)
            return 1
        print(f"Fixed -> {args.output}  (0x{stored:08X} -> 0x{correct:08X})")
        return 0

    # In-place fix: keep a .bak of the original, stage via a temp file,
    # re-read and re-verify, then atomically replace.
    src = Path(args.rom)
    bak = Path(str(src) + ".bak")
    try:
        shutil.copyfile(src, bak)
    except OSError as e:
        print(f"Error: cannot write backup {bak}: {e}", file=sys.stderr)
        return 1
    try:
        fd, tmp = tempfile.mkstemp(dir=str(src.parent), prefix=".denso_ck_",
                                   suffix=".bin")
        with os.fdopen(fd, "wb") as fh:
            fh.write(bytes(fixed))
        back = bytearray(Path(tmp).read_bytes())
        _lo3, _hi3, s3, correct3 = compute(back)
        stored3 = struct.unpack_from(">I", back, DIFF_OFF)[0]
        if stored3 != correct3 or (s3 + stored3) & 0xFFFFFFFF != TARGET:
            os.unlink(tmp)
            print("Error: staged image does not verify; "
                  "original kept, backup at %s." % bak, file=sys.stderr)
            return 1
        os.replace(tmp, src)
    except OSError as e:
        print(f"Error: in-place fix failed: {e} (backup at {bak})",
              file=sys.stderr)
        return 1
    print(f"Fixed -> {src}  (0x{stored:08X} -> 0x{correct:08X}) [backup: {bak}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
