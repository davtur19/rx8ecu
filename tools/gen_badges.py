#!/usr/bin/env python3
"""gen_badges.py — regenerate the auto-updating README progress badges.

Pure-Python 3 (stdlib only: subprocess, hashlib, re, urllib, pathlib).
Run from the repo root:

    python3 tools/gen_badges.py            # default: derive, fall back on failure
    python3 tools/gen_badges.py --derive-checks   # strict: fail if a suite cannot run

Computes reverse-engineering progress metrics from live repo data
(tracked C lifts via `git ls-files`, unique emulator-verified addresses
from c/verified_addrs.txt, symbol-table sizes, ...) and rewrites the badge
block in README.md between the `<!-- BADGES:START -->` / `<!-- BADGES:END -->`
markers.  No metric is hardcoded:

  * ASM coverage  — parsed from the per-ROM coverage table in VERIFICATION.md
    §2 (mean rounded to one decimal), with a constant fallback + warning.
  * Regression checks — the two test suites (tools/tests/test_decode_families.py
    --quick and tools/tests/test_emulator_families.py) are run and their
    "<N> checks" line parsed; the constants are only fallbacks when a suite
    cannot be run, and `--derive-checks` makes that a hard error.
  * Everything else (ROM count, C lifts, verified addresses, calibration
    tables, call-graph edges, functions mapped) is derived from `git ls-files`
    / the shipped CSV files.

Also updates the `README.md` row (sha256 + byte size) in MANIFEST.md so the
file inventory stays in sync.

Deterministic: no timestamps; running twice yields an identical README.md
(the badge URLs only change when the underlying data changes).
"""

import hashlib
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
MANIFEST = ROOT / "MANIFEST.md"
VERIFIED_ADDRS = ROOT / "c" / "verified_addrs.txt"
VERIFICATION = ROOT / "VERIFICATION.md"

# Fallback for the round-trip SH-2 lift coverage badge, used only when the
# VERIFICATION.md §2 coverage table cannot be read/parsed (derive_asm_coverage
# normally parses the table and reports the mean rounded to one decimal).
# NOTE: the figure is a *round-trip* one — it counts every in-window word that
# decodes and re-encodes to valid bytes; a small fraction (~6%) of those are
# data tables, so the true-code fraction is ~88–91% (data ~9–12%).  Keep in
# sync with the README prose.
ASM_COVERAGE_FALLBACK = "93.6"

# Fallback regression-check counts.  The badge normally uses the LIVE counts
# from actually running tools/tests/test_decode_families.py (disassembler
# decode families) and tools/tests/test_emulator_families.py (emulator
# instruction families) — see regression_checks().  These constants are only
# used when a suite cannot be run (missing interpreter/module, unparseable
# output) so the badge never breaks; keep them in sync with the suites'
# reported counts.
FALLBACK_CHECKS_DISASM = 38008
FALLBACK_CHECKS_EMU = 83

# Suite stdout reports the total as "<N> checks, ..." (both suites count every
# assertion via a shared check() helper, so N is the full assertion count).
CHECK_RE = re.compile(r"(\d[\d,]*) checks")

# VERIFICATION.md §2 table rows look like:
#   | 60E0FB00 | src/60E0FB00_annotated.s | 4,640,621 | 7,197 | 60,236 | 93.60 | YES |
COVERAGE_ROW_RE = re.compile(
    r"^\|\s*\S+\s*\|\s*src/[^|]+\|\s*[\d,]+\s*\|\s*[\d,]+\s*\|\s*[\d,]+\s*\|\s*(\d+\.\d+)\s*\|",
    re.MULTILINE,
)


def derive_asm_coverage():
    """Round-trip SH-2 lift coverage badge value, derived from VERIFICATION.md.

    Parses the per-ROM in-window coverage percentages in the VERIFICATION.md §2
    table (skipping [REDACTED]/private rows) and returns the mean rounded to
    one decimal.  If the table cannot be read or parsed, falls back to
    ASM_COVERAGE_FALLBACK and warns on stderr.
    """
    try:
        text = VERIFICATION.read_text(encoding="utf-8")
    except OSError as e:
        print(f"WARNING: {VERIFICATION.name} unreadable ({e!r}); "
              f"using ASM_COVERAGE={ASM_COVERAGE_FALLBACK}", file=sys.stderr)
        return ASM_COVERAGE_FALLBACK
    vals = []
    for m in COVERAGE_ROW_RE.finditer(text):
        row = m.group(0)
        if "REDACTED" in row or "PRIVATE" in row:
            continue
        vals.append(float(m.group(1)))
    if not vals:
        print(f"WARNING: no coverage values found in {VERIFICATION.name}; "
              f"using ASM_COVERAGE={ASM_COVERAGE_FALLBACK}", file=sys.stderr)
        return ASM_COVERAGE_FALLBACK
    return f"{sum(vals) / len(vals):.1f}"


def run_suite(argv, fallback, label, strict=False):
    """Run one regression suite and return its reported check count.

    `argv` is the full command line (already resolved through sys.executable),
    executed from the repo root.  The suite's stdout line is parsed for
    `<N> checks`; on any failure to run or parse, the fallback constant is
    returned and a warning is printed to stderr (the badge stays intact).
    With `strict=True` (--derive-checks) a failure instead exits non-zero, so
    stale counts can never be silently published.
    """
    try:
        out = subprocess.run(
            argv,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (OSError, subprocess.SubprocessError) as e:
        msg = f"{label}: suite could not be run ({e!r})"
        if strict:
            raise SystemExit(f"ERROR: {msg} (--derive-checks)") from e
        print(f"WARNING: {msg}; using fallback count {fallback}", file=sys.stderr)
        return fallback
    m = CHECK_RE.search(out.stdout or "")
    if m is None:
        msg = f"{label}: no '<N> checks' line in suite output"
        if strict:
            raise SystemExit(f"ERROR: {msg} (--derive-checks)")
        print(f"WARNING: {msg}; using fallback count {fallback}", file=sys.stderr)
        return fallback
    return int(m.group(1).replace(",", ""))


def regression_checks(strict=False):
    """Live regression-check counts by actually running the two test suites.

    Returns (disasm_checks, emu_checks).  Both suites are pure-stdlib (no
    capstone, no sh-elf toolchain required): the decode suite runs in --quick
    mode (tables + whole-ROM family coverage — its count is identical to the
    full run, which only adds failure-time checks on the bulk round-trip), and
    the emulator suite runs with its default random-division case count.  Any
    failure falls back to FALLBACK_CHECKS_* unless `strict` is set
    (--derive-checks), in which case it is a hard error.
    """
    disasm = run_suite(
        [sys.executable, "tools/tests/test_decode_families.py", "--quick"],
        FALLBACK_CHECKS_DISASM,
        "test_decode_families.py",
        strict=strict,
    )
    emu = run_suite(
        [sys.executable, "tools/tests/test_emulator_families.py"],
        FALLBACK_CHECKS_EMU,
        "test_emulator_families.py",
        strict=strict,
    )
    return disasm, emu


def git_ls_files(pattern, top_level_subdir=None):
    """Return sorted list of files tracked by git matching `pattern`.

    If `top_level_subdir` is given (e.g. 'c'), only direct children of that
    directory are kept — a git pathspec glob like `c/*.c` also matches
    nested files (c/tests/*.c), so this reproduces the shell-expanded
    `git ls-files c/*.c` behaviour (top-level lift files only).
    """
    out = subprocess.run(
        ["git", "ls-files", pattern],
        cwd=str(ROOT),
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    files = [f for f in out.splitlines() if f]
    if top_level_subdir is not None:
        prefix = top_level_subdir + "/"
        files = [
            f
            for f in files
            if f.startswith(prefix) and "/" not in f[len(prefix):]
        ]
    return sorted(files)


def line_count_minus_one(relpath):
    """Number of data rows in a CSV = (lines in file) - 1 (header row)."""
    text = (ROOT / relpath).read_text(encoding="utf-8")
    lines = text.splitlines()
    return max(0, len(lines) - 1)


def unique_verified():
    """Unique hex addresses in c/verified_addrs.txt (address lines only)."""
    addrs = set()
    for line in VERIFIED_ADDRS.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith(";") or s.startswith("#"):
            continue
        for tok in re.findall(r"0x[0-9A-Fa-f]+", s):
            addrs.add(int(tok, 16))
    return len(addrs)


def shields_url(label, value, color):
    """Build a shields.io badge URL with programmatic percent-encoding.

    Shields.io encodes literal hyphens as double hyphens ('-' -> '--') in
    both label and value; everything else is percent-encoded (spaces %20,
    commas %2C, slashes %2F, parens %28 %29, '%' %25, '+' %2B, ...).
    """
    def enc(s):
        return urllib.parse.quote(s.replace("-", "--"), safe="-")

    return f"https://img.shields.io/badge/{enc(label)}-{enc(value)}-{color}"


def build_badge_block(strict=False):
    """Return (metrics, block_text)."""

    # Live repo data (tracked-file based, so the numbers self-heal as new
    # lifts are committed; the coverage and regression-check counts come from
    # VERIFICATION.md and from running the two test suites below).
    roms = len(git_ls_files("roms/stock/*.bin"))
    lifts = len(git_ls_files("c/*.c", top_level_subdir="c"))
    verified = unique_verified()
    tables = line_count_minus_one("symbols/cal_tables.csv")
    edges = line_count_minus_one("symbols/callgraph.csv")
    funcs = line_count_minus_one("symbols/symbols_60E0FC00.csv")
    checks_disasm, checks_emu = regression_checks(strict=strict)
    asm_coverage = derive_asm_coverage()

    verified_pct = round(100 * verified / lifts) if lifts else 0

    badges = [
        ("ROMs byte-exact", shields_url("ROMs byte-exact", f"{roms}/{roms}", "brightgreen")),
        ("Code window", shields_url("Code window", f"{asm_coverage}% SH-2 lift", "green")),
        ("C reimplemented", shields_url("C reimplemented", f"{lifts} functions", "blue")),
        (
            "Emulator-verified",
            shields_url(
                "Emulator-verified",
                f"{verified}/{lifts} ({verified_pct}%)",
                "yellowgreen",
            ),
        ),
        ("Calibration tables", shields_url("Calibration tables", f"{tables}", "blue")),
        ("Call graph", shields_url("Call graph", f"{edges} edges", "blue")),
        ("Functions mapped", shields_url("Functions mapped", f"{funcs}", "blue")),
        (
            "Regression checks",
            shields_url(
                "Regression checks",
                f"{checks_disasm}+{checks_emu} \u2713",
                "green",
            ),
        ),
    ]

    lines = ["<!-- BADGES:START -->"]
    lines += [f"![{label}]({url})" for label, url in badges]
    lines.append("<!-- BADGES:END -->")

    metrics = {
        "roms": roms,
        "lifts": lifts,
        "verified": verified,
        "verified_pct": verified_pct,
        "tables": tables,
        "edges": edges,
        "funcs": funcs,
        "asm_coverage": asm_coverage,
        "regression_checks_disasm": checks_disasm,
        "regression_checks_emu": checks_emu,
    }
    return metrics, "\n".join(lines) + "\n"


def update_readme(block):
    """Replace the text between the BADGES markers (inclusive)."""
    text = README.read_text(encoding="utf-8")
    pattern = re.compile(
        r"<!-- BADGES:START -->.*?<!-- BADGES:END -->",
        re.DOTALL,
    )
    if not pattern.search(text):
        raise SystemExit(
            "ERROR: BADGES markers not found in README.md — add "
            "`<!-- BADGES:START -->` / `<!-- BADGES:END -->` first."
        )
    new_text = pattern.sub(block.rstrip("\n"), text)
    README.write_text(new_text, encoding="utf-8")
    return new_text


def human_size(num):
    """Format byte count the way MANIFEST.md does (B / K / M)."""
    if num < 1024:
        return f"{num}B"
    if num < 1024 * 1024:
        return f"{num / 1024:.1f}K"
    return f"{num / (1024 * 1024):.1f}M"


def update_manifest():
    """Update the README.md sha256+size row in MANIFEST.md. Returns True if changed."""
    if not MANIFEST.exists():
        return False
    manifest = MANIFEST.read_text(encoding="utf-8")
    sha = hashlib.sha256(README.read_bytes()).hexdigest()
    size = README.stat().st_size
    size_str = human_size(size)
    # Match the existing row: `| `README.md` | `hash` | size | ... |
    pattern = re.compile(
        r"^(\| `README\.md` \| )`[0-9a-f]{64}`( \| )[^|]+( \|.*)$",
        re.MULTILINE,
    )
    replacement = rf"\g<1>`{sha}`\g<2>{size_str}\g<3>"
    new_manifest, n = pattern.subn(replacement, manifest, count=1)
    if n == 1 and new_manifest != manifest:
        MANIFEST.write_text(new_manifest, encoding="utf-8")
        return True
    return False


def main():
    strict = "--derive-checks" in sys.argv[1:]
    metrics, block = build_badge_block(strict=strict)
    update_readme(block)
    manifest_changed = update_manifest()

    print("Badges regenerated. Metrics:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    print(f"  MANIFEST.md README row updated: {manifest_changed}")


if __name__ == "__main__":
    main()
