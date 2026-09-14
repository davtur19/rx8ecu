# tmp/ — promotion table

New artifacts go to `tmp/<topic>/` first. This table defines what to keep,
what to promote, and what to discard. General rule (AGENTS.md): new
artifacts → `tmp/<topic>/`; promote only when the artifact is mature and
reusable outside the current workflow.

## Promotion table

| Artifact | Status | Decision |
|---|---|---|
| `tmp/ida/make_elf.py` | **keep in tmp** | Build script for the canonical ELF big-endian configuration (`60E1D400_be.elf`), referenced by `docs/notes/IDA_ANALYSIS.md`. Promotion to `tools/` is optional: it is deterministic, has `assert` on sizes, and is reusable to rebuild the file if needed. |
| `tmp/ida/60E1D400_be.elf` | **keep in tmp** | Canonical IDA configuration (ELF BE with ROM + RAM + peripherals). It is a working artifact, not a tool: stays in tmp. |
| `tmp/ida/60E1D400_bswap.bin` + `tmp/ida/swap16.py` | **keep in tmp** | Superseded configuration (word-swap workaround). Keep for history/comparison, do NOT promote. |
| `tmp/ida/test_sh4.bin` (+ `.i64`) | **discard** | Test file for SH loader probing. No lasting value. |
| `tmp/ida/uds_obd_analysis.md` | **keep in tmp** | UDS/OBD analysis complementary to `docs/notes/IDA_ANALYSIS.md` and `docs/notes/CAN_PROTOCOL.md`. |
| `tmp/ida/chunks/` | **keep in tmp** | Symbol import chunks (codearr_*/def_*/ren_*). Needed to reproduce or extend the import. |
| `tmp/ida/reimport_report.txt` + `name_verify_report.txt` + `manual_names.txt` | **keep in tmp** | Verified reports for symbol import and manual name verification; referenced in `docs/notes/IDA_ANALYSIS.md`. |

## Force-tracked snapshots (`git ls-files tmp/` → 36 files)

`tmp/` is ignored (`.gitignore:16`), but 36 files are force-tracked (`git add -f`)
as review snapshots, not transient work:

| Group | Files | Why tracked |
|---|---|---|
| `tmp/README.md` | this file | Promotion policy for `tmp/`. |
| `tmp/ida/deep_review_*_1.3.txt` (3) | `deep_review_code_1.3.txt`, `deep_review_docs_1.3.txt`, `deep_review_hygiene_1.3.txt` | Versioned deep-review snapshots. |
| `tmp/ida/firmware_*_report.txt` + `tmp/ida/emu_*_report.txt` (9) | `firmware_can/dtc/engine/engine_completion/impl/rtos/uds`, `emu_can_uds`, `emu_engine_dtc_rtos` | Firmware/EMU subsystem analysis snapshots. |
| `tmp/ida/review_*_report.txt` + `fix_todos_report.txt` + `verify_uncertain_report.txt` (5) | `review_build/docs/firmware`, `fix_todos`, `verify_uncertain` | Review/hygiene verification snapshots. |
| `tmp/ida/ecu_*_report.txt` + `tmp/ida/site_*_report.txt` (5) | `ecu_boot_debug/pin_emu/webui`, `site_menu/visual` | ECU emulator, web UI, and site review snapshots. |
| `tmp/ida/screenshots/*.png` (13) | `emu*.png` (7), `explorer*.png` (5), `landing*.png` (2) | UI screenshots backing the web UI / site reports. |

> **Warning: do NOT `git rm` these files in a "cleanup".** They are
> intentionally force-tracked despite the `tmp/` ignore rule. Removing them
> deletes published review evidence with no regenerable source.
