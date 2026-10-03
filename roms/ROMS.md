# RX-8 PCM ROM catalog

This file is the reference for every ROM image shipped in this repo. It states
the calibration ID and the build for each image. It states the Denso software
module, the security key, and the checksum status. All identifiers below are
**extracted directly from the binaries** (offsets given under "How IDs are
derived"); market/spec attributions are marked where they still need confirmation.

All images are 512 KB (0x80000), Renesas/Hitachi **SH-2 big-endian**, Denso PCM,
RX-8 Series 1 family. Every stock image has a **valid Denso additive checksum**
(target `0x5AA5A55A`, descriptor @`0x7FB80`).

Provenance: the community stock ROMs come from
[equinox311/Mazda_RX8_PCM_ReverseEngineering](https://github.com/equinox311/Mazda_RX8_PCM_ReverseEngineering)
(`Stock_ROMs/`). The six images originally in this repo were verified
**byte-for-byte identical** to that source; three more (`60E15120`, `60E1C500`,
`60E32000`) were added from it to widen the dataset. The newest,
`60E32000_N3N5EB`, was **added upstream by content commit**
[`47be913`](https://github.com/equinox311/Mazda_RX8_PCM_ReverseEngineering/commit/47be913a80feed6cbd16e996860aa3a9b43faf49)
("Added 60E32000_N3N5EB.bin", 2026-09-19), which **reached upstream `master`
via the merge**
[`fe4fa71`](https://github.com/equinox311/Mazda_RX8_PCM_ReverseEngineering/commit/fe4fa71725a99422d80279cb1fa30aca6b53aa00)
(2026-09-25; `47be913` is its second parent, the first parent `46e9b4d`
predates the file) — our copy comes from the `fe4fa71` tree. Upstream states
**no license** for the repository (all rights reserved — see
[CREDITS.md](../CREDITS.md)).

> **What is (and is not) shipped.** This repo ships **10 public stock ROMs**
> (the table below). No tuned-ROM rows are added here, and any IDA `.i64`/Ghidra
> `.gar` project files are excluded. Every image listed here is stock factory
> firmware already in public circulation and verified byte-exact
> (see [VERIFICATION.md](../VERIFICATION.md)).

## Stock ROMs (10 shipped)

| Cal ID (@0x2000) | Denso SW module | Task module | Sec key | Key offset | Checksum | sha256[:10] | Role / notes |
|------------------|-----------------|-------------|---------|-----------|----------|-------------|--------------|
| **60E1D400** | SW-N3J1EM000.HEX | N3J1E_3W.T50 | MazdA | 0x5FAC0 | OK | `344cb8b960` | **RE baseline** — fully documented in `docs/`; primary Track-A/B target |
| 60E0E500 | SW-N3YMEC000.HEX | – | MazdA | 0x5E460 | OK | `c05dfd0422` | community ref |
| 60E0E700 | SW-N3YLEE000.HEX | – | MazdA | 0x5E6B8 | OK | `bba52346a0` | community ref (file tagged `_N3YLEE`) |
| 60E0FB00 | SW-N3Z2ET000.HEX | – | MazdA | 0x5D90C | OK | `3d32e2591a` | community ref |
| 60E0FC00 | SW-N3Z2EU000.HEX | – | MazdA | 0x5D90C | OK | `476ddcbed4` | community ref (Data_binaries dup = same blob); equinox hand-annotation reference |
| 60E15120 | SW-N3ZHEB000.HEX | – | MazdA | 0x5F084 | OK | `a7cd953c2a` | community ref; **file tagged `_N3J1E` but internal SW is N3ZHEB000** (see naming note) |
| 60E1B900 | SW-N3ZDEH000.HEX | N3ZDEBWW.T50 | MazdA | 0x5DBA4 | OK | `b0dc94f96e` | community ref |
| 60E1C500 | SW-N3J6EN000.HEX | N3J6EBMW.T50 | MazdA | 0x5E730 | OK | `b3b6e1e416` | community ref (file tagged `_N3J6EB`) |
| 60E32000 | SW-N3M5EK000.HEX | N3M5E_SW.T01 | MazdA | 0x65134 | OK | `d5406459cc` | community ref (file tagged `_N3M5E`); **structurally distinct** — key ~0x65000 vs ~0x5Exxx elsewhere, task suffix `.T01` not `.T50` (likely a later/different-market build) |
| 60E32000 | SW-N3N5EB000.HEX | N3N5E_2W.T01 | MazdA | 0x64C84 | OK | `6c043bd4c9` | community ref (file tagged `_N3N5EB`); **sibling of `60E32000_N3M5E`** — same cal ID but a genuinely distinct SW build (N3N5EB vs N3M5EK: 415,621/524,288 bytes differ, ~79%); same `.T01` task-suffix style as its sibling. **Attribution**: upstream `equinox311/RX8Defs` attributes N3N5EB → **JDM, 2006, 6-Port, AT** (`rx8_defs.xml` second romid; the fields were filled in 2026-09-29 by single-author commit `ff5ab4f` — upstream-stated, single-source, **not independently confirmed**). Local markers: `PF_J60E_06MY_55` @`0x710C0` (present only in the two `60E32000` images) and header date bytes `06 07 07` @`0x2020` (possible BCD 2006-07-07 — **hypothesis**, not confirmed) |

Full sha256 for every shipped image: see
[VERIFICATION.md](../VERIFICATION.md).

**Defs coverage gaps** (sources: `symbols/cal_tables.csv` +
`equinox311/RX8Defs`):
`60E0E500` still lacks **public address-level defs** (RomRaider/EcuFlash table
maps); it is likely address-compatible with its sibling `60E0E600` (same
family — verify with a diff), and `equinox311/RX8Defs` contains no entry for it
at all. For `60E32000` the picture changed on **2026-09-29**: upstream
[equinox311/RX8Defs](https://github.com/equinox311/RX8Defs) (HEAD `e1fe0a5`)
publishes a RomRaider entry (`RomRaider/rx8_defs.xml` block ~lines 28034–28348,
`<xmlid>60E32000</xmlid>` + second romid `<xmlid>N3N5EB</xmlid>`) with **266
addressed tables = 264 DTC enable/disable + 2 Immobilizer switches**
(`0x371D8` / `0x37624`), **byte-verified against our `60E32000_N3N5EB` image**
(its immo off-state @`0x371D8` = `B5 6E 00 09 60 D0 60 0C 88 00 8D 11 00 09
88 01` matches the def; the `N3M5E` image does **not** match). That entry is
DTC+immo only — **still no tuning-map defs and no ECUFlash def** for this cal
ID; the fork source `Rx8Man/RX8Defs` has neither cal (stale since 2023-12) and
open unmerged PR `Rx8Man/RX8Defs#1` (2026-09-20) claims 676 tables. Two shipped
images share this cal ID (`60E32000_N3M5E` and `60E32000_N3N5EB`); upstream
covers only `N3N5EB`. `60E32000` additionally has community Ghidra labels
(cjv0513) — code labels, not calibration table defs. Note
`symbols/cal_tables.csv` holds **only `60E1D400` rows**, so it cannot evidence
defs for any other cal ID.
All other shipped ROMs have published defs.

Observations:

- **All stock keys are `MazdA`** (the factory SecurityAccess constant); only the
  key *offset* moves between builds (0x5D90C → 0x65134). It follows the
  code-layout size. The LFSR init table (`C5 41 A9`) is unchanged across builds.
- Denso SW-module prefixes cluster into families: `N3J1`/`N3J6` (the "J" line),
  `N3YL`/`N3YM`, `N3Z2`/`N3ZD`/`N3ZH` (the "Z" line), and the outliers
  `N3M5`/`N3N5` (both seen only on cal ID `60E32000` in this set — two distinct
  SW builds of the same cal ID).
  The "J" line includes the documented baseline. `N3` is the RENESIS 13B
  engine-code prefix in Mazda's `N3xx-18-881` PCM part numbers.
- Market / spec per cal ID, **confirmed** from equinox92's guide: `60E0FC00` =
  US 6-Port MT (equinox's RE target); `60E0FB00` = US 6-Port MT; `60E1B900` =
  US 6-Port MT; `60E1D400` = N3J1EM 6-Port MT;
  `60E1A300` = 2005 JDM 4-Port MT; `60E1A500` = JDM 4/6-Port.
  All 04-09 (03-08 global)
  S1 RX-8. `N3` prefix = RENESIS 13B. Editor/logger defs:
  [equinox311/RX8Defs](https://github.com/equinox311/RX8Defs).
- **CPU = Renesas HD64F7055(S)** (SH7055, SH-2 core + single-precision FPU =
   SH-2E). Flash recovery through BOOT mode on header CN400 — see
   `docs/notes/BOOT_RECOVERY.md`.

No tuned- or modified-ROM images are tracked in this repo. IDA project files
(`*.i64`) and Ghidra archives (`*.gar`) are also excluded from the public repo
(redundant with the RE deliverables here, and they carry project-local state).

## Naming note: filename suffix vs internal module

Some community filenames carry a `_N3xxxx` suffix (for example `60E1C500_N3J6EB`,
`60E32000_N3M5E`). This tag is generally the **Denso/Mazda part number of the
physical PCM** the dump was pulled from. It usually — but **not always** —
matches the internal `SW-*.HEX` calibration flashed on it:

- Consistent: `60E0E700_N3YLEE` → internal `SW-N3YLEE000.HEX`; `60E1C500_N3J6EB`
  → task `N3J6EBMW`; `60E32000_N3M5E` → `SW-N3M5EK000.HEX`;
  `60E32000_N3N5EB` → `SW-N3N5EB000.HEX`.
- **Mismatch**: `60E15120_N3J1E` carries internal `SW-N3ZHEB000.HEX` (a "Z"-line
  cal), not an `N3J1` cal. Treat the internal `SW-*.HEX` as authoritative for the
  software; the suffix identifies the donor hardware.

## How the IDs are derived (from each binary)

| Field | Offset / method |
|-------|-----------------|
| Cal ID (e.g. `60E1D400`) | 8 ASCII bytes @ `0x2000` |
| Denso copyright | `Copr.DENSO2000S…` @ `0x2022` and `~0x6CE33` |
| SW module `SW-*.HEX` | ASCII near `~0x6CE40` (search `SW-[0-9A-Z]+\.HEX`) |
| Task module `N3*.T50` | ASCII near `~0x6CE00` (search `N3[0-9A-Z_]+\.T[0-9][0-9]`) |
| Security key (5 bytes) | search for `MazdA` (the factory SecurityAccess constant); offset varies per build (LFSR params follow the key) |
| Denso checksum | descriptor @`0x7FB80` = `[lo:4][hi:4][diff:4]`; Σ BE32 over `[lo,hi]` + `diff` must equal `0x5AA5A55A`. Verify with `python3 tools/denso_ck.py <rom>` |
| Reset vector | PC = BE32 @ `0x0` (all = `0x000008B8`), SP = BE32 @ `0x4` (`0xFFFFDFA0`) |

## Reproduce this catalog

```bash
# checksum of any image
python3 tools/denso_ck.py roms/stock/<id>.bin
# byte-exact rebuild of any image (asm-first oracle)
make ROM=roms/stock/<id>.bin verify
```
