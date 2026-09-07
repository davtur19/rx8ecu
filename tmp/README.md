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
