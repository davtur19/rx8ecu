# GitHub Actions CI — rx8ecu

This directory contains the CI definition for the rx8ecu repo (Mazda RX-8 ECU
firmware reverse-engineering project). Everything here is self-contained:
**no repo-root files are required** (no `requirements.txt` is shipped at the
repo root — CI keeps its own pin in `.github/requirements.txt`).

## What CI runs

| Job | Steps | Local equivalent |
|-----|-------|------------------|
| `verify` | `make verify-all` — byte-exact rebuild of **all 9 public stock ROMs** (sha256 match); `make c-test` — host-compiled behavior-equivalence suites (26/26); `make c-emu` — C lifts vs emulated ROM (5×100k random) | same three make targets |
| `tests` | ONE step: `python3 tools/run_tests_parallel.py -j 2` — the project's parallel runner (same code as `make test-fast`). Auto-discovers every `c/tests/test_*.py` and `tools/tests/test_*.py` suite (decode families incl. the GNU-as bulk round-trip, emulator families, all per-function suites), so new test files are picked up without editing CI | `make test-fast` |

Both jobs run in **parallel**, each **fails the workflow** on any failing step
(that's the point: verification must be green on every push/PR).

### Triggers

- `push` to `main` / `master`
- `pull_request` targeting `main` / `master`

Runs for the same branch are **cancelled in favour of the newest** push
(`concurrency.cancel-in-progress`).

## Caching

- **pip**: `actions/setup-python` with `cache: pip`, keyed on
  `.github/requirements.txt` (caches the capstone wheel download).
- **sh-elf toolchain**: `actions/cache` over `tools/toolchain/`, keyed on
  `tools/get_toolchain.sh` content hash + runner OS. On a cache miss the
  documented install runs (see below); on a hit the install step is skipped.

## Toolchain install in CI

The toolchain (`sh-elf-as`, `sh-elf-ld`, `sh-elf-objcopy` for target sh-elf) is
git-ignored (`tools/toolchain/`), so a fresh checkout has none. CI reproduces
the **project's own documented, rootless method**:

```bash
sudo apt-get update        # ensure apt lists are present on the runner
./tools/get_toolchain.sh   # apt-get download binutils-sh-elf + dpkg-deb -x -> tools/toolchain/usr/bin
```

This works because the runners are Ubuntu. On a cache miss this takes a few
seconds; the installed tree is then cached for subsequent runs. The Makefile
and `verify_all.sh` resolve `tools/toolchain/usr/bin` themselves; only
`test_decode_families.py` needs the directory on `PATH` (done explicitly in the
`tests` job).

**Version caveat (follow-up):** the local/dev verification was measured with
**sh-elf binutils 2.46**. `get_toolchain.sh` installs whatever `binutils-sh-elf`
the runner's Ubuntu apt provides, which may be older (e.g. 2.42 on 24.04) — the
project guarantees byte-exactness against *any* sh-elf binutils because
`rom_rebuild.py` self-corrects re-encoding differences back to raw `.word`, but
if you want to pin CI to exactly 2.46, either pin the runner image to one whose
apt ships 2.46 or build binutils 2.46 from source in a custom step. Coverage
percentages can drift slightly with the `as` version; `BYTE-EXACT` should not.

## Environment reproduced from the local dev box

| Component | Local (verified 2026-08-01) | CI |
|-----------|------------------------------|----|
| Python | 3.14.6 | 3.14 (setup-python) |
| capstone | 5.0.9 | `capstone==5.0.9` (`.github/requirements.txt`) |
| sh-elf binutils | 2.46 | apt `binutils-sh-elf` (may differ, see above) |
| C compiler | cc (gcc/clang) | preinstalled gcc on the runner |

Note: `VERIFICATION.md` quotes capstone **5.0.7** (the version the original
measurement used); the local install has since been updated to 5.0.9, so CI
pins 5.0.9. If you ever need the exact documented-measurement environment,
pin `.github/requirements.txt` to `capstone==5.0.7` instead.

## Running the same checks locally (ci-local)

From the repo root, on any Linux/macOS box:

```bash
# 1. Python deps (the ONLY pip dependency of the project)
python3 -m pip install --break-system-packages capstone==5.0.9

# 2. sh-elf binutils toolchain (one-time, idempotent, no root; needs internet)
./tools/get_toolchain.sh

# 3. Verification battery
make verify-all      # byte-exact rebuild, 9/9 ROMs, sha256 compared
make c-test          # host-compiled C behavior-equivalence suites
make c-emu           # C lifts vs emulated ROM (5x100k random)

# 4. Python regression suites
export PATH="$PWD/tools/toolchain/usr/bin:$PATH"   # needed by test_decode_families.py
python3 tools/tests/test_decode_families.py        # disassembler, incl. GNU-as round-trip
python3 tools/tests/test_emulator_families.py      # emulator families

# 5. Per-function Python suites — use the parallel runner (auto-discovers all
#    c/tests/test_*.py + tools/tests/test_*.py suites; -j to tune workers):
python3 tools/run_tests_parallel.py -j 2
```

> **Why `-j 2` in CI?** `run_tests_parallel.py` defaults to `cpu_count-1`
> workers, which is **1 (= serial)** on the 2-vCPU free-tier runner; passing
> `-j 2` uses both vCPUs and roughly halves the ~3 min serial runtime of the
> per-function suites. The parallel runner replaces the old serial `for` loop
> and the two standalone family suites as the single canonical way to run the
> Python battery (locally `make test-fast` is the same code without `-j`).

On Debian/Ubuntu the toolchain can alternatively be installed system-wide with
`sudo apt-get install binutils-sh-elf` (the Makefile picks it up from PATH if
no local install exists).
