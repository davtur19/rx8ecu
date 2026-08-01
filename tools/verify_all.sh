#!/usr/bin/env bash
# verify_all.sh — rebuild EVERY stock ROM and prove each is byte-exact.
#
# For each of the 9 public stock ROMs in ../roms/stock/ this runs the same
# asm-first rebuild as `make ROM=<rom> verify` — capstone disassembly + sh-elf
# binutils, code window 0x800..0x60000, everything else raw .word data (the
# defaults of rom_rebuild.py) — then compares the rebuilt bytes to the source ROM.
#
# NOTE: the dataset originally had 10 stock ROMs; the 10th ([REDACTED], the
# owner's personal live-ECU dump) is kept PRIVATE and is not shipped, so this
# verifier covers the 9 public images (the private image was verified
# byte-exact before exclusion — see VERIFICATION.md).
#
# Self-contained: resolves the sh-elf toolchain itself (./tools/toolchain/usr/bin,
# then the legacy ./toolchain/root/usr/bin, then whatever is on PATH) so it
# works from a fresh clone with NO ~/.bashrc exports. Requires:
#   - python3 + capstone  (pip install capstone --break-system-packages)
#   - sh-elf binutils     (./tools/get_toolchain.sh)
#   - GNU coreutils       (sha256sum, wc, sort)
#
# Usage:   ./tools/verify_all.sh     (from repo root)
#          make verify-all           (equivalent)
#
# Exit status: 0 = every ROM rebuilt byte-exact; 1 = any mismatch/failure;
#              2 = environment error (missing toolchain, wrong ROM count, ...).
set -euo pipefail

cd "$(dirname "$0")/.."              # always run from the repo root
ROMS_DIR="${ROMS_DIR:-roms/stock}"
BUILD="build"

die() { echo "ERROR: $*" >&2; exit 2; }

command -v python3 >/dev/null 2>&1 || die "python3 not found on PATH"
python3 -c 'import capstone' 2>/dev/null \
    || die "capstone missing: run  python3 -m pip install capstone --break-system-packages"

# Resolve the sh-elf toolchain: local install first (canonical, then legacy
# layout from older get_toolchain.sh versions), else rely on PATH.
if [ -x ./tools/toolchain/usr/bin/sh-elf-as ]; then
    export PATH="$PWD/tools/toolchain/usr/bin:$PATH"
elif [ -x ./tools/toolchain/root/usr/bin/sh-elf-as ]; then
    export PATH="$PWD/tools/toolchain/root/usr/bin:$PATH"
fi
command -v sh-elf-as >/dev/null 2>&1 || die "sh-elf-as not found — run ./tools/get_toolchain.sh first"

shopt -s nullglob
mapfile -t ROMS < <(printf '%s\n' "$ROMS_DIR"/*.bin | sort)
if [ "${#ROMS[@]}" -ne 9 ]; then
    die "expected 9 public stock ROMs in $ROMS_DIR, found ${#ROMS[@]}"
fi

mkdir -p "$BUILD"

echo "Rebuilding and byte-exact-verifying ${#ROMS[@]} stock ROMs (code window 0x800..0x60000)..."
printf '%-30s %-28s %7s %6s  %s\n' "ROM" "sha256 match" "cov%" "raw" "STATUS"
printf '%s\n' "-----------------------------------------------------------------------"

fail=0
for rom in "${ROMS[@]}"; do
    id=$(basename "$rom")
    size=$(wc -c < "$rom")
    if [ "$size" -ne 524288 ]; then
        printf '%-30s %-28s %7s %6s  %s\n' "$id" "-" "-" "-" "BAD SIZE ($size B)"
        fail=$((fail+1))
        continue
    fi
    src_sha=$(sha256sum "$rom" | awk '{print $1}')
    if out=$(python3 tools/rom_rebuild.py --rom "$rom" --asm "$BUILD/$id.s" --out "$BUILD/$id.bin" 2>&1); then
        rc=0
    else
        rc=$?
    fi
    if [ "$rc" -ne 0 ]; then
        printf '%-30s %-28s %7s %6s  %s\n' "$id" "${src_sha:0:24}" "-" "-" "REBUILD FAILED"
        printf '  %s\n' "$(printf '%s\n' "$out" | tail -2 | tr '\n' ' ')"
        fail=$((fail+1))
        continue
    fi
    got_sha=$(sha256sum "$BUILD/$id.bin" | awk '{print $1}')
    cov=$(printf '%s\n' "$out" | grep -oE '\([0-9]+\.[0-9]+%\)' | head -1 | tr -d '()%')
    raw=$(printf '%s\n' "$out" | grep -oE 'raw fallbacks: [0-9]+' | grep -oE '[0-9]+' | head -1)
    if [ "$got_sha" = "$src_sha" ]; then
        printf '%-30s %-28s %7s %6s  %s\n' "$id" "${src_sha:0:24}" "${cov:-?}" "${raw:-?}" "BYTE-EXACT"
    else
        printf '%-30s %-28s %7s %6s  %s\n' "$id" "${src_sha:0:12}!=${got_sha:0:12}" "${cov:-?}" "${raw:-?}" "MISMATCH"
        fail=$((fail+1))
    fi
done
printf '%s\n' "-----------------------------------------------------------------------"
if [ "$fail" -eq 0 ]; then
    echo "OK: all ${#ROMS[@]} stock ROMs rebuilt byte-exact (code window 0x800..0x60000)."
    exit 0
fi
echo "FAILED: $fail/${#ROMS[@]} ROMs did not rebuild byte-exact." >&2
exit 1
