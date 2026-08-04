#!/usr/bin/env python3
"""Regenerate MANIFEST.md — full inventory of every git-tracked file.

Hashes/sizes are computed from the COMMITTED blob content (HEAD), so the
inventory never depends on uncommitted working-tree edits.  Purpose texts for
previously-listed files are preserved from the current MANIFEST.md; new files
(notably reconstructed/) get rule-based purposes.  Stdlib only.

Usage (from the repo root):  python3 tools/gen_manifest.py
Writes MANIFEST.md in place; deterministic (no timestamps, no absolute paths).
"""
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def git(args):
    out = subprocess.run(
        ["git", "-C", str(ROOT)] + args,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return out


def human_size(num):
    if num < 1024:
        return f"{num}B"
    if num < 1024 * 1024:
        return f"{num / 1024:.1f}K"
    return f"{num / (1024 * 1024):.1f}M"


def section_of(path):
    if "/" not in path:
        return "(root)"
    if path.startswith("c/tests/"):
        return "c/tests"
    if path.startswith("c/"):
        return "c"
    if path.startswith("tools/tests/"):
        return "tools/tests"
    if path.startswith("tools/"):
        return "tools"
    if path.startswith("reconstructed/experiments/match/"):
        return "reconstructed/experiments/match"
    if path.startswith("reconstructed/samples/"):
        return "reconstructed/samples"
    return path.split("/", 1)[0]


def purpose_for(path, old):
    if path in old:
        return old[path]
    # Rule-based purposes for newly-inventoried files.
    if path == "tools/gen_manifest.py":
        return "Regenerates MANIFEST.md (repo inventory; python3 tools/gen_manifest.py)"
    if path == "reconstructed/samples/README.md":
        return "Reconstructed-source sample catalog (abstract idiomatic C, verified lifts)"
    if path == "reconstructed/samples/Makefile":
        return "Build: compile reconstructed samples + host oracle (host gcc)"
    if path == "reconstructed/samples/.gitignore":
        return "Git ignore rules (sample build artifacts)"
    if path.startswith("reconstructed/samples/include/"):
        return "Sample shared header (SH7055 hardware access)"
    if path.startswith("reconstructed/samples/src/"):
        return "Reconstructed C source sample (readable, verified lift)"
    if path == "reconstructed/samples/tests/common.py":
        return "Shared harness helpers (emulator vs C equivalence)"
    if path.startswith("reconstructed/samples/tests/harness_"):
        return "Sample Python harness (emulator vs C equivalence)"
    if path == "reconstructed/samples/tests/host_oracle.c":
        return "Host oracle driver for sample harnesses"
    if path.startswith("reconstructed/samples/tests/oracle_"):
        return "Host oracle for sample harness"
    if path == "reconstructed/experiments/match/REPORT.md":
        return "Compiler-match experiment report (GCC sh-elf sweeps)"
    if path == "reconstructed/experiments/match/match_recipe.txt":
        return "Compiler-match sweep recipe (GCC sh-elf)"
    if path.startswith("reconstructed/experiments/match/c_src/"):
        return "Compiler-match experiment C source"
    if path.startswith("reconstructed/experiments/match/expected_gcc_sh2e/"):
        return "Expected GCC sh-elf assembly (match reference)"
    if path.startswith("reconstructed/experiments/match/rom_hex/"):
        return "ROM hex bytes of matched function"
    if path.startswith("reconstructed/experiments/match/scripts/"):
        return "Compiler-match sweep/analysis script"
    if path.startswith("docs/notes/"):
        return "Project knowledge / session notes"
    return "Tracked file"


def main():
    # Existing purposes from current MANIFEST.md.
    old = {}
    for line in (ROOT / "MANIFEST.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\| `([^`]+)` \| `([0-9a-f]{64}|--)` \| [^|]+ \| (.*) \|$", line)
        if m:
            old[m.group(1)] = m.group(3)

    # Tracked files (index == HEAD; nothing staged) + blob hashes.
    entries = {}  # path -> (blob_hash, size, sha256)
    out = git(["ls-files", "-s"])
    blob_hash = {}  # path -> blob
    for line in out.splitlines():
        # format: <mode> <blob> <stage>\t<path>
        meta, _, path = line.partition("\t")
        mode, blob, stage = meta.split()
        if mode == "160000":  # submodule
            raise SystemExit(f"submodule unsupported: {path}")
        blob_hash[path] = blob
        entries[path] = None

    # Bulk content fetch via git cat-file --batch.
    lines = "".join(f"{h}\n" for h in blob_hash.values()).encode()
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "--batch"],
        input=lines,
        capture_output=True,
        text=False,
    )
    if proc.returncode != 0:
        raise SystemExit("git cat-file --batch failed")
    data = proc.stdout
    pos = 0
    info = {}
    while pos < len(data):
        nl = data.index(b"\n", pos)
        header = data[pos:nl].decode()
        if header.startswith("missing"):
            raise SystemExit(f"missing blob: {header}")
        _, typ, sizestr = header.split()
        size = int(sizestr)
        content = data[nl + 1 : nl + 1 + size]
        # advance past content + trailing newline
        pos = nl + 1 + size + 1
        if typ != "blob":
            continue
        info[header.split()[0]] = (size, hashlib.sha256(content).hexdigest())

    # Build buckets preserving byte-sorted order (git ls-files is sorted).
    sections = [
        "(root)", "roms", "src", "symbols", "c", "c/tests", "tools",
        "tools/tests", "docs", "hardware", "web", "analysis", ".github",
        "reconstructed/experiments/match", "reconstructed/samples",
    ]
    buckets = {s: [] for s in sections}
    for path in sorted(entries):
        buckets[section_of(path)].append(path)

    summary = []
    out_lines = []
    for sec in sections:
        files = buckets[sec]
        if not files:
            continue
        total_bytes = 0
        rows = []
        for path in files:
            blob = blob_hash[path]
            size, sha = info[blob]
            total_bytes += size
            purpose = purpose_for(path, old)
            if path == "MANIFEST.md":
                row = f"| `MANIFEST.md` | `--` | -- | This inventory (self-referential; verify with `sha256sum MANIFEST.md`) |"
            else:
                row = f"| `{path}` | `{sha}` | {human_size(size)} | {purpose} |"
            rows.append(row)
        summary.append((sec, len(files), total_bytes))
        out_lines.append(f"## {sec}\n")
        out_lines.append("| Relative path | sha256 | Size | Purpose |")
        out_lines.append("|---|--:|---:|---|")
        out_lines.extend(rows)
        out_lines.append("")

    total_files = sum(n for _, n, _ in summary)
    total_bytes = sum(b for _, _, b in summary)

    # ---- Header ----
    header = f"""# MANIFEST — RX-8 ECU reverse-engineering public release

Every file shipped in this repository, with sha256, size, purpose, and its source path
in the working repository. **{total_files} entries, {human_size(total_bytes)}.** Regenerated 2026-08-02 for the
9-ROM public tree; see roms/ROMS.md).

## Summary

| Area | Files | Bytes |
|------|------:|------:|
"""
    for sec, n, b in summary:
        label = sec if sec == "(root)" else sec + "/"
        header += f"| {label} | {n} | {human_size(b)} |\n"
    header += f"| **Total** | **{total_files}** | {human_size(total_bytes)} |\n"

    # ---- External dependencies (verbatim) ----
    dep = """## External dependencies

The repo is self-contained except for:

| Dependency | Version | Notes |
|------------|---------|-------|
| Python 3 | >= 3.8 (tested 3.14) | `python3` on PATH |
| capstone | >= 5.0 | `python3 -m pip install capstone --break-system-packages` (SH-2 disassembly) |
| sh-elf binutils | 2.46 | SHIPPED at `tools/toolchain/usr/bin`; re-install via `./tools/get_toolchain.sh` |
| cc (host C compiler) | any | only for `make c-test` (host-side tests) |

No other runtime dependencies. The repo does NOT ship tuned/private ROM images,
Ghidra/IDA project files (`.gar`, `.i64`), other binaries, the toolchain source,
or the toolchain install (git-ignored; re-create with
`./tools/get_toolchain.sh`).

## Notes on adapted files

- Path resolution in `c/tests/*.py`, `tools/tests/*.py` and the tools was rewritten to
  the public layout (`tools/` for `sh2emu.py`/`disasm_sh2e.py`, `roms/stock/` for ROMs,
  `symbols/` for symbol tables, `analysis/` for data regions). All suites re-verified
  green in this tree (see VERIFICATION.md).
- The 9 annotated `.s` files regenerate byte-identical with `make src` (verified).
- `tools/toolchain/` (sh-elf binutils 2.46) is git-ignored but ships in the working tree
  at `tools/toolchain/usr/bin`; `./tools/get_toolchain.sh` re-creates it idempotently.
- `src/*.bin`, `*.elf`, `*.o` build intermediates (e.g. from `make src`) are git-ignored;
  `make clean` removes them. Only the 9 `src/*_annotated.s` sources ship.
- `reconstructed/` is fully inventoried (no longer excluded): compiler-match experiments
  (C sources, expected GCC sh-elf output, ROM hex, sweep scripts) under
  `reconstructed/experiments/match`, and readable reconstructed-source C samples with
  Python harnesses + host oracles under `reconstructed/samples`.
"""

    manifest = header + "\n" + dep + "\n" + "\n".join(out_lines) + "\n"
    (ROOT / "MANIFEST.md").write_text(manifest, encoding="utf-8")
    print(f"wrote {total_files} entries, {human_size(total_bytes)}")


if __name__ == "__main__":
    main()
