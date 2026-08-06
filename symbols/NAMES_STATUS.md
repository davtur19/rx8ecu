# NAMES_STATUS — catalogo simboli per ROM

Stato della catalogazione dei nomi funzione per le 9 ROM stock pubbliche, dopo la
campagna "CATALOGAZIONE" (fusione IDA-ai nel canonico + cross-ROM via firma di contenuto).

Colonne: **totali** (funzioni nel catalogo), **descrittivi** (nome non-FUN_/sub_/loc_/nullsub_),
**anonimi** (nome generico), **fonte** (source column del CSV), **delta anon vs recce**.

> Nota di affidabilità: i cataloghi `60E0FC00*` sono generati da analisi Ghidra/equinox
> (confini funzione affidabili). I cataloghi delle altre ROM derivano con
> `tools/xmap_names.py --derive` (scoperta entry da `bsr`+pooled pointer, range
> `0x40..0x6CE00`) e quindi risultano **over-segmentati** (~2× il canonico); i nomi
> trasferiti `ghidra-hand-xmap` sono però match 1:1 ad alta confidenza — il *count di
> descrittivi* è affidabile, il *total* è provvisorio finché non si fa un'analisi
> funzione con Ghidra.

## Tabella per ROM

| ROM | CSV | total | descrittivi | anonimi | fonte | note |
|-----|-----|-------|------------|---------|-------|------|
| 60E0FC00 | symbols_60E0FC00.csv | 3459 | 985 | 2474 | ghidra-hand 931 + ghidra-auto | **canonico** (equiname reference) |
| 60E0FC00 | symbols_60E0FC00_merged2.csv | 3459 | **1357** | **2102** | +ida-ai-xmap 374 | canonico + fusione IDA-ai (NUOVO) |
| 60E1D400 | symbols_60E1D400_ida.csv | 2789 | 2747 | 42 | ida-ai 2788 + c-lift 1 | baseline, fonte IDA-ai |
| 60E1D400 | symbols_60E1D400_merged.csv | 2789 | 2747 | 42 | ida-ai + ghidra-hand-xmap 313 | baseline fusa |
| 60E0E500 | symbols_60E0E500.csv | 7305 | 277 | 7028 | ghidra-hand-xmap 277 (derive) | NUOVO, derivato (*) |
| 60E0E700 | symbols_60E0E700.csv | 7306 | 277 | 7029 | ghidra-hand-xmap 277 (derive) | NUOVO, derivato (*) |
| 60E0FB00 | symbols_60E0FB00.csv | 7197 | 300 | 6897 | ghidra-hand-xmap 300 (derive) | NUOVO, derivato (*) |
| 60E15120 | symbols_60E15120.csv | 7473 | 255 | 7218 | ghidra-hand-xmap 255 (derive) | NUOVO, derivato (*) |
| 60E1B900 | symbols_60E1B900.csv | 7173 | 295 | 6878 | ghidra-hand-xmap 295 (derive) | NUOVO, derivato (*) |
| 60E1C500 | symbols_60E1C500.csv | 7315 | 275 | 7040 | ghidra-hand-xmap 275 (derive) | NUOVO, derivato (*) |
| 60E32000 | symbols_60E32000.csv | 6899 | 239 | 6660 | ghidra-hand-xmap 239 (derive) | NUOVO, derivato (*) |

(*) Over-segmentazione: ~6.9–7.5k funzioni vs 3459 del canonico — boundaries funzione
non affidabili; solo i nomi `ghidra-hand-xmap` sono attendibili. I conteggi desc>i qui
sono **solo i nomi trasferiti 1:1**, non una copertura completa.

## Delta canonico vs recce precedente

Recce precedente (canonico `symbols_60E0FC00.csv`): **985 descrittivi / 2474 anonimi**.

Dopo fusione IDA (`symbols_60E0FC00_merged2.csv`):

- **descrittivi: 985 → 1357** (Δ **+372**)
- **anonimi: 2474 → 2102** (Δ **−372**)
- 1212 firme xmatch; 374 slot `FUN_*`/anonimi riempiti con nome descrittivo IDA-ai
  (`source=ida-ai-xmap`, flag `DUBIOUS`); 133 funzioni nominate sia da equiname che IDA.

Il canonico originale non è stato sovrascritto (backup: `/tmp/symbols_60E0FC00.csv.bak`);
l'arricchimento vive nel nuovo `symbols_60E0FC00_merged2.csv`.

## File toccati in questa campagna

- `symbols/symbols_60E0FC00_merged2.csv` — NUOVO: canonico + nomi IDA-ai (fusione).
- `symbols/symbols_60E0E500.csv`, `..._60E0E700.csv`, `..._60E0FB00.csv`,
  `..._60E15120.csv`, `..._60E1B900.csv`, `..._60E1C500.csv`, `..._60E32000.csv`
  — NUOVI: cataloghi cross-ROM derivati poi mani equinox (derivate).
- `symbols/NAMES_STATUS.md` — questo file.
- `reconstructed/samples/README.md` — §7 pt.1 aggiornato a “APPLICATO (commit 099bf8b)” (stale fix).

## v2 — catalogo master (post-lift-merge, DEDUP)

Collega i nomi lift autorevoli (`c/*.c`, `c/tests/test_*.py`) ai CSV: ogni riga di `symbols/CATALOG_MASTER.csv` porta `src_name` (originale) e `lift_name` (autorevole se disponibile). Il catalogo e' DEDUP per `(bank, addr)` — `total (unique)` e' il numero reale di funzioni per bank, `rows (incl. variants)` e' il conteggio cumulativo dei CSV varianti (ridondanti). `verified=YES` per addr in `c/verified_addrs.txt`.

| bank | file | rows (incl. variants) | total (unique) | nominate | anonime | lift-named | di cui VERIFIED | note | Δ nominate |
|-----:|------|----------------------:|---------------:|---------:|--------:|-----------:|----------------:|------|----------:|
| 60E0E500 | symbols_60E0E500.csv<br/>symbols_60E0E500_connor.csv | 7312 | 7305 | 391 | 6914 | 159 | 59 | derivata over-segmentata | +114 |
| 60E0E700 | symbols_60E0E700.csv<br/>symbols_60E0E700_connor.csv | 7313 | 7306 | 397 | 6909 | 157 | 62 | derivata over-segmentata | +120 |
| 60E0FB00 | symbols_60E0FB00.csv<br/>symbols_60E0FB00_connor.csv | 7203 | 7197 | 567 | 6630 | 497 | 67 | derivata over-segmentata | +267 |
| 60E0FC00 | equinox311_60E0FC00_named.csv<br/>symbols_60E0FC00.csv<br/>symbols_60E0FC00_connor.csv<br/>symbols_60E0FC00_ghidra.csv<br/>symbols_60E0FC00_merged2.csv | 9018 | 3490 | 1601 | 1889 | 524 | 64 | canonico affidabile (equiname) | +91 |
| 60E15120 | symbols_60E15120.csv<br/>symbols_60E15120_connor.csv | 7480 | 7473 | 359 | 7114 | 147 | 59 | derivata over-segmentata | +104 |
| 60E1B900 | symbols_60E1B900.csv<br/>symbols_60E1B900_connor.csv | 7185 | 7173 | 444 | 6729 | 202 | 72 | derivata over-segmentata | +149 |
| 60E1C500 | symbols_60E1C500.csv<br/>symbols_60E1C500_connor.csv | 7327 | 7315 | 457 | 6858 | 231 | 82 | derivata over-segmentata | +182 |
| 60E1D400 | symbols_60E1D400_connor.csv<br/>symbols_60E1D400_ida.csv<br/>symbols_60E1D400_merged.csv | 5607 | 2794 | 2794 | 0 | 1019 | 193 | canonico affidabile (IDA-ai) | +0 |
| 60E32000 | symbols_60E32000.csv<br/>symbols_60E32000_connor.csv | 6911 | 6899 | 372 | 6527 | 165 | 58 | derivata over-segmentata | +133 |

Dedup: `rows (incl. variants)` (cumulativo varianti) vs `total (unique)` (post-dedup) — la differenza e' il numero di righe ridondanti eliminate. `also_sources` nel CSV elenca i source persi.

Lift addrs senza corrispondenza in alcun CSV (`lift_orphans`): 5 — es.: 0x094C8 (get_ignition_dwell_time), 0x0D49C (main_entry).

## v2b — LIFT_ONLY orphans adopted

Gli `orphan` (lift addrs senza START di riga in alcun CSV) sono ora ENTRY del catalogo master con `flag=LIFT_ONLY` (boundary non in IDA). Attribuzione bank via range CSV (fallback 60E1D400 se fuori range); `verified=YES` per addr in `c/verified_addrs.txt`.

| bank | addr | lift_name | source | flag | verified |
|-----:|-----:|-----------|--------|------|----------|
| 60E1D400 | 0x094C8 | get_ignition_dwell_time | lift | LIFT_ONLY | YES |
| 60E1D400 | 0x0D49C | main_entry | lift | LIFT_ONLY | YES |
| 60E1D400 | 0x360E8 | ImmoStateMachine | lift | LIFT_ONLY | YES |
| 60E1D400 | 0x584A0 | security_access | lift | LIFT_ONLY |  |
| 60E1D400 | 0x6443E | obd_dtc_find | lift | LIFT_ONLY | YES |
