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