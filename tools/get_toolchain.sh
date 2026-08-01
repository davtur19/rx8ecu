#!/usr/bin/env bash
# Fetch GNU binutils for the sh-elf target into ./toolchain WITHOUT root.
# Provides sh-elf-as / sh-elf-ld / sh-elf-objcopy for the asm-first round-trip.
#
# Deterministic, idempotent install path:  <repo>/tools/toolchain/usr/bin
# (canonical; earlier versions of this script extracted to toolchain/root/usr/bin —
#  a legacy install is detected and migrated so nothing is re-downloaded).
#
# The Makefile and verify_all.sh resolve this path themselves, so after running
# this script you normally do NOT need to touch PATH. If you want it for ad-hoc
# use (e.g. rom2asm.py):
#   export PATH="$PWD/toolchain/usr/bin:$PATH"
#
# On a normal box you can instead: sudo apt-get install binutils-sh-elf
# On Windows: use any sh-elf binutils (e.g. the Renesas GNU SH build, or
# devkitPro's) — only as/ld/objcopy for target sh-elf, big-endian, are needed.
set -euo pipefail
cd "$(dirname "$0")"

TC_BIN="toolchain/usr/bin"          # canonical location of the sh-elf tools
LEGACY_BIN="toolchain/root/usr/bin" # layout used by older versions of this script

say_done() {
    echo "Done. sh-elf binutils installed at: $PWD/$TC_BIN"
    echo "  (make / make verify-all resolve this automatically; a manual export would be:)"
    echo "  export PATH=\"$PWD/$TC_BIN:\$PATH\""
}

# 1) Canonical install already present -> idempotent fast path, no download.
if [ -x "$TC_BIN/sh-elf-as" ] && "$TC_BIN/sh-elf-as" --version >/dev/null 2>&1; then
    echo "sh-elf binutils already installed at $PWD/$TC_BIN"
    "$TC_BIN/sh-elf-as" --version | head -1
    say_done
    exit 0
fi

# 2) Legacy install from an older script version (toolchain/root/usr/bin) ->
#    migrate to the canonical path instead of re-downloading.
if [ -x "$LEGACY_BIN/sh-elf-as" ] && "$LEGACY_BIN/sh-elf-as" --version >/dev/null 2>&1; then
    echo "Legacy install found at $PWD/$LEGACY_BIN — moving to $PWD/$TC_BIN"
    mkdir -p "$(dirname "$TC_BIN")"
    rm -rf "$TC_BIN"               # canonical dir is missing/broken (step 1 failed)
    mv "$LEGACY_BIN" "$TC_BIN"
    rm -rf toolchain/root          # drop the now-empty legacy container
    "$TC_BIN/sh-elf-as" --version | head -1
    say_done
    exit 0
fi

# 3) Fresh install: unpack the distro .deb locally (no root needed).
if ! command -v apt-get >/dev/null 2>&1; then
    # Last resort: rely on a system-installed sh-elf-as if one already exists.
    if command -v sh-elf-as >/dev/null 2>&1; then
        echo "No apt-get available; using system sh-elf-as already on PATH: $(command -v sh-elf-as)"
        exit 0
    fi
    echo "ERROR: no apt-get and no system sh-elf-as. Install binutils-sh-elf" >&2
    echo "       (or run this script on Debian/Ubuntu)." >&2
    exit 1
fi
mkdir -p "$(dirname "$TC_BIN")"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
( cd "$tmp" && apt-get download binutils-sh-elf )
# The .deb root contains usr/bin/sh-elf-*; extract it into tools/toolchain/ so
# the tools land at $TC_BIN (= toolchain/usr/bin) instead of one dir too deep.
dpkg-deb -x "$tmp"/binutils-sh-elf_*.deb "$(dirname "$(dirname "$TC_BIN")")"
"$TC_BIN/sh-elf-as" --version | head -1
say_done
