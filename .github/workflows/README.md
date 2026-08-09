# GitHub Actions CI — rx8ecu

CI definition for the rx8ecu repo. It is self-contained: CI requires **no repo-root files**; it keeps its own pin in `.github/requirements.txt`.

## What CI runs

| Job | Steps | Local equivalent |
|-----|-------|------------------|
| `verify` | `make verify-all` — byte-exact rebuild of **all 9 public stock ROMs** (`sha256` match); `make c-test` (26/26); `make c-emu` (5×100k random) | same three make targets |
| `tests` | `python3 tools/run_tests_parallel.py -j 4` — auto-discovers every `c/tests/test_*.py` and `tools/tests/test_*.py` suite; new files picked up automatically | `make test-fast` |
| `catalog` | `python3 tools/classify_functions.py` + `python3 tools/gen_catalog.py` on clean checkout, then `git diff --exit-code` on four catalog artifacts — **fails on drift** (skipped unless catalog paths changed, via `dorny/paths-filter`) | `make classify catalog` |
| `formal-cert` | `make cert` — formal certification (`tools/verify_formal.py`) of **all 9 stock ROMs**; **fails unless CERTIFIED** (skipped unless `src/**`, verifier, or configs changed) | `make cert` |

All four jobs run in **parallel** (subject to path triggers). Each job **fails the workflow** on any failed step.

### Triggers

- `push` to `main` / `master`; `pull_request` that targets those branches
- Same-branch runs **cancelled in favour of the newest** (`concurrency.cancel-in-progress`)

## Caching

- **pip**: `actions/setup-python` with `cache: pip`, keyed on `.github/requirements.txt`
- **sh-elf toolchain**: `actions/cache` over `tools/toolchain/`, keyed on `tools/get_toolchain.sh` hash + runner OS; on hit, install skipped

## Toolchain install in CI

The toolchain (`sh-elf-as`, `sh-elf-ld`, `sh-elf-objcopy`) is git-ignored; CI reproduces the rootless project method:

```bash
sudo apt-get update        # ensure apt lists are present
./tools/get_toolchain.sh   # apt-get download binutils-sh-elf + dpkg-deb -x -> tools/toolchain/usr/bin
```

Works because runners are Ubuntu. Makefile/`verify_all.sh` resolve `tools/toolchain/usr/bin` themselves; only `test_decode_families.py` needs it on `PATH` (set in the `tests` job).

**Version caveat:** local measurement used **sh-elf binutils 2.46**; `get_toolchain.sh` installs whatever apt provides (can be older, for example 2.42 on 24.04). Byte-exactness holds against any version (`rom_rebuild.py` self-corrects back to raw `.word`). Coverage % can drift slightly with the `as` version; `BYTE-EXACT` does not.

## Environment (local vs CI)

| Component | Local (verified 2026-08-01) | CI |
|-----------|------------------------------|----|
| Python | 3.14.6 | 3.14 (setup-python) |
| capstone | 5.0.7 | `capstone==5.0.9` (`.github/requirements.txt`) |
| sh-elf binutils | 2.46 | apt `binutils-sh-elf` (may differ, see above) |
| C compiler | cc (gcc/clang) | preinstalled gcc |

Note: `VERIFICATION.md` quotes capstone **5.0.7** (original measurement); CI pins 5.0.9. To reproduce the documented-measurement env, pin `.github/requirements.txt` to `capstone==5.0.7`.

## Running the same checks locally (ci-local)

```bash
python3 -m pip install --break-system-packages capstone==5.0.9
./tools/get_toolchain.sh
make verify-all
make c-test
make c-emu
export PATH="$PWD/tools/toolchain/usr/bin:$PATH"   # needed by test_decode_families.py
python3 tools/tests/test_decode_families.py      # disassembler, incl. GNU-as round-trip
python3 tools/tests/test_emulator_families.py    # emulator families
python3 tools/run_tests_parallel.py -j 2     # auto-discovers all c/tests + tools/tests suites
```

> **`-j 4` in CI?** `run_tests_parallel.py` defaults to `cpu_count-1` = 3 on the 4-vCPU `ubuntu-latest` runner; `-j 4` uses all four vCPUs. The parallel runner is the single canonical way to run the Python battery (locally `make test-fast`).

On Debian/Ubuntu you can also install the toolchain system-wide with `sudo apt-get install binutils-sh-elf` (Makefile picks it up from PATH).