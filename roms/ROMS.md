# RX-8 PCM ROM catalog

Reference for every ROM image shipped in this repo: which calibration ID is
which build, its Denso software module, security key, and checksum status. All
identifiers below are **extracted directly from the binaries** (offsets given
under "How IDs are derived"); market/spec attributions are marked where they
still need confirmation.

All images are 512 KB (0x80000), Renesas/Hitachi **SH-2 big-endian**, Denso PCM,
RX-8 Series 1 family. Every stock image has a **valid Denso additive checksum**
(target `0x5AA5A55A`, descriptor @`0x7FB80`).

Provenance: the community stock ROMs come from
[equinox311/Mazda_RX8_PCM_ReverseEngineering](https://github.com/equinox311/Mazda_RX8_PCM_ReverseEngineering)
(`Stock_ROMs/`). The six images originally in this repo were verified
**byte-for-byte identical** to that source; three more (`60E15120`, `60E1C500`,
`60E32000`) were added from it to widen the dataset.

> **What is (and is not) shipped.** This repo ships **9 public stock ROMs**
> (the table below). The 10th dataset image — **`[REDACTED]`** (`[REDACTED]`,
> the project owner's personal live-ECU dump, `SW-[REDACTED]`) — is **kept
> private** and not shipped, as are all **modified/tuned images** ([REDACTED]
> launch-control & [REDACTED], [REDACTED]-patched) and any IDA `.i64`/Ghidra `.gar`
> project files. Every image listed here is stock factory firmware already in
> public circulation; the private images were verified byte-exact before
> exclusion (see [VERIFICATION.md](../VERIFICATION.md)).

## Stock ROMs (9 shipped)

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

Full sha256 for every shipped image (and the private `[REDACTED]`): see
[VERIFICATION.md](../VERIFICATION.md).

Observations:

- **All stock keys are `MazdA`** (the factory SecurityAccess constant); only the
  key *offset* moves between builds (0x5D90C → 0x65134), tracking code-layout size.
- Denso SW-module prefixes cluster into families: `N3J1`/`N3J6` (the "J" line,
  incl. the documented baseline), `N3YL`/`N3YM`, `N3Z2`/`N3ZD`/`N3ZH` (the "Z"
  line), and the outlier `N3M5`. `N3` is the RENESIS 13B engine-code prefix in
  Mazda's `N3xx-18-881` PCM part numbers.
- Market / spec per cal ID, **confirmed** from equinox92's guide: `60E0FC00` =
  US 6-Port MT (equinox's RE target); `60E0FB00` = US 6-Port MT; `60E1B900` =
  US 6-Port MT; `**removed-private**` = N3J1EL 6-Port MT; `60E1D400` = N3J1EM 6-Port MT;
  `60E1A300` = 2005 JDM 4-Port MT; `60E1A500` = JDM 4/6-Port. The private
  `[REDACTED]` = 2004 **EU 6-Port MT** (the owner's car). All 04-09 (03-08 global)
  S1 RX-8. `N3` prefix = RENESIS 13B. Editor/logger defs:
  [equinox311/RX8Defs](https://github.com/equinox311/RX8Defs).
- **CPU = Renesas HD64F7055(S)** (SH7055, SH-2 core + single-precision FPU =
  SH-2E). Flash recovery via BOOT mode on header CN400 — see
  `docs/notes/FULL_ANALYSIS.md` / `docs/notes/BOOT_RECOVERY.md`.

## Kept private (not shipped)

| File | Base cal ID | SW module | Sec key | Size | Notes |
|------|-------------|-----------|---------|------|-------|
| `[REDACTED]` | [REDACTED] | [REDACTED] | MazdA | 512 KB | **Owner's personal live-ECU dump**; byte-exact verified pre-exclusion (see VERIFICATION.md) |
| `[REDACTED]` | 60E1D400 | [REDACTED] | [REDACTED] | 512 KB | [REDACTED] tune of 60E1D400; launch-control cave @`0x6C7FE`, checksum bypassed (see `docs/notes/FULL_ANALYSIS.md`) |
| `[REDACTED]` | 60E1D400 | [REDACTED] | [REDACTED] | 512 KB | [REDACTED] + finalized LC patch |
| `[REDACTED]` | 60E1D400 | – | – | **525312 B** | [REDACTED]-saved: **prefixed with a 1024-byte (0x400) header** — the raw 512 KB image starts at file offset `0x400`, so cal ID/strings are shifted. Not a flat dump. |

IDA project files (`*.i64`) and Ghidra archives (`*.gar`) are also excluded
from the public repo (redundant with the RE deliverables here, and they carry
project-local state).

## Naming note: filename suffix vs internal module

Some community filenames carry a `_N3xxxx` suffix (e.g. `60E1C500_N3J6EB`,
`60E32000_N3M5E`). This tag is generally the **Denso/Mazda part number of the
physical PCM** the dump was pulled from, which usually — but **not always** —
matches the internal `SW-*.HEX` calibration flashed on it:

- Consistent: `60E0E700_N3YLEE` → internal `SW-N3YLEE000.HEX`; `60E1C500_N3J6EB`
  → task `N3J6EBMW`; `60E32000_N3M5E` → `SW-N3M5EK000.HEX`.
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
| Security key (5 bytes) | search for `MazdA` / `vendor-family secret` / `[REDACTED]`; offset varies per build (LFSR params follow the key) |
| Denso checksum | descriptor @`0x7FB80` = `[lo:4][hi:4][diff:4]`; Σ BE32 over `[lo,hi]` + `diff` must equal `0x5AA5A55A`. Verify with `python3 tools/denso_ck.py <rom>` |
| Reset vector | PC = BE32 @ `0x0` (all = `0x000008B8`), SP = BE32 @ `0x4` (`0xFFFFDFA0`) |

## Reproduce this catalog

```bash
# checksum of any image
python3 tools/denso_ck.py roms/stock/<id>.bin
# byte-exact rebuild of any image (asm-first oracle)
make ROM=roms/stock/<id>.bin verify
```
