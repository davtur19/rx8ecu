# RX-8 PCM Cross-ROM Diff Analysis

9 stock ROMs, 512 KB (0x80000) each, Renesas SH-2E / SH7055, big-endian. Baseline: **60E1D400** (SW-N3J1EM000, the documented RE baseline).

## Method

- **Raw byte diff** at identical file offsets (36 pairs).
- **Block-content similarity**: 16-byte windows of A (stride 16) searched in the set of *all* 16-byte windows of B (stride 1). Tolerant to code/table relocation; the metric used to group variants.
- Differing bytes merged into ranges (identical runs of <=8 bytes spliced), classified against baseline-anchored address bands:
  - `header` 0x00000-0x01FFF (vectors/boot, below Denso checksum lo=0x2000)
  - `code` 0x02000-0x6C26F (checksummed code, OBD handlers to ~0x6BFE0)
  - `padding` 0x6C270-0x6CDFF (baseline 0xFF filler gap)
  - `cal_data` 0x6CE00-0x7DAFF (calibration tables region)
  - `tail` 0x7DAFF-0x7FFFF (checksum descriptor @0x7FB80 + trailing)
- Known-table hits use `symbols/cal_tables.csv` (1210 addrs, 60E1D400 layout). Valid only for J-line builds; other families relocate the table block.
- All 9 ROMs share an identical 0x0-0x40 vector table (reset vector 0x8B8); divergence accumulates through the body.

## 1. Similarity matrices

### 1a. Raw byte diff, % differing at identical offsets

| | 60E0E500 | 60E0E700_N3YLEE | 60E0FB00 | 60E0FC00 | 60E15120_N3J1E | 60E1B900 | 60E1C500_N3J6EB | 60E1D400 | 60E32000_N3M5E |
|---|---|---|---|---|---|---|---|---|---|
| 60E0E500 | -- | 76.847 | 81.269 | 81.269 | 83.771 | 88.906 | 77.563 | 91.482 | 92.634 |
| 60E0E700_N3YLEE | 76.847 | -- | 81.476 | 81.477 | 83.699 | 88.904 | 86.740 | 91.340 | 92.627 |
| 60E0FB00 | 81.269 | 81.476 | -- | 0.008 | 83.972 | 76.433 | 89.246 | 91.426 | 92.750 |
| 60E0FC00 | 81.269 | 81.477 | 0.008 | -- | 83.972 | 76.428 | 89.246 | 91.426 | 92.750 |
| 60E15120_N3J1E | 83.771 | 83.699 | 83.972 | 83.972 | -- | 91.642 | 91.568 | 91.447 | 92.240 |
| 60E1B900 | 88.906 | 88.904 | 76.433 | 76.428 | 91.642 | -- | 81.215 | 83.392 | 89.057 |
| 60E1C500_N3J6EB | 77.563 | 86.740 | 89.246 | 89.246 | 91.568 | 81.215 | -- | 80.927 | 88.991 |
| 60E1D400 | 91.482 | 91.340 | 91.426 | 91.426 | 91.447 | 83.392 | 80.927 | -- | 88.730 |
| 60E32000_N3M5E | 92.634 | 92.627 | 92.750 | 92.750 | 92.240 | 89.057 | 88.991 | 88.730 | -- |

High values appear everywhere, except 60E0FB00 vs 60E0FC00 at 0.008%. Every build relocates code and table blocks. The raw same-offset comparison is mostly a layout-divergence measure.

### 1b. Content similarity (shift-tolerant 16B blocks), whole ROM / code region / cal region

| pair | whole | code | cal |
|---|---|---|---|
| 60E0FB00 vs 60E0FC00 | 99.95% | 100.00% | 99.76% |
| 60E0FC00 vs 60E1B900 | 91.15% | 89.79% | 99.88% |
| 60E0FB00 vs 60E1B900 | 91.13% | 89.79% | 99.72% |
| 60E0E500 vs 60E1C500_N3J6EB | 89.77% | 89.62% | 91.18% |
| 60E1C500_N3J6EB vs 60E1D400 | 80.27% | 76.85% | 87.75% |
| 60E0E500 vs 60E0E700_N3YLEE | 77.68% | 77.51% | 71.02% |
| 60E0E500 vs 60E1D400 | 76.79% | 74.63% | 79.15% |
| 60E0E700_N3YLEE vs 60E1C500_N3J6EB | 74.91% | 75.15% | 68.95% |
| 60E0E500 vs 60E15120_N3J1E | 73.69% | 70.99% | 73.35% |
| 60E0E700_N3YLEE vs 60E1D400 | 73.55% | 73.74% | 60.84% |
| 60E15120_N3J1E vs 60E1D400 | 73.34% | 70.18% | 91.10% |
| 60E15120_N3J1E vs 60E1C500_N3J6EB | 71.48% | 68.89% | 85.33% |
| 60E1B900 vs 60E1C500_N3J6EB | 71.10% | 67.46% | 81.22% |
| 60E0E700_N3YLEE vs 60E15120_N3J1E | 71.05% | 70.49% | 57.14% |
| 60E1B900 vs 60E1D400 | 70.43% | 66.75% | 76.96% |
| 60E0E500 vs 60E0FC00 | 69.85% | 66.49% | 79.73% |
| 60E0E500 vs 60E0FB00 | 69.84% | 66.49% | 79.67% |
| 60E0FC00 vs 60E1C500_N3J6EB | 69.13% | 65.65% | 81.20% |
| 60E0FB00 vs 60E1C500_N3J6EB | 69.13% | 65.65% | 81.15% |
| 60E0FC00 vs 60E1D400 | 68.49% | 64.97% | 76.94% |
| 60E0FB00 vs 60E1D400 | 68.49% | 64.97% | 76.89% |
| 60E0E500 vs 60E1B900 | 67.90% | 64.77% | 79.71% |
| 60E0E700_N3YLEE vs 60E0FC00 | 66.84% | 65.93% | 61.23% |
| 60E0E700_N3YLEE vs 60E0FB00 | 66.84% | 65.93% | 61.18% |
| 60E0FB00 vs 60E15120_N3J1E | 65.84% | 61.83% | 71.06% |
| 60E0FC00 vs 60E15120_N3J1E | 65.84% | 61.83% | 71.06% |
| 60E0E700_N3YLEE vs 60E1B900 | 64.91% | 64.23% | 61.21% |
| 60E15120_N3J1E vs 60E1B900 | 61.36% | 58.98% | 74.84% |
| 60E1B900 vs 60E32000_N3M5E | 60.01% | 56.53% | 60.45% |
| 60E0FC00 vs 60E32000_N3M5E | 58.38% | 55.12% | 60.45% |
| 60E0FB00 vs 60E32000_N3M5E | 58.37% | 55.12% | 60.41% |
| 60E1C500_N3J6EB vs 60E32000_N3M5E | 55.25% | 52.59% | 53.22% |
| 60E1D400 vs 60E32000_N3M5E | 54.77% | 52.91% | 58.56% |
| 60E0E500 vs 60E32000_N3M5E | 53.51% | 51.01% | 53.37% |
| 60E0E700_N3YLEE vs 60E32000_N3M5E | 51.61% | 50.64% | 41.95% |
| 60E15120_N3J1E vs 60E32000_N3M5E | 49.54% | 48.28% | 54.21% |

## 2. Per-ROM layout (0xFF-gap structure)

| ROM | code_end | first gap | cal_lo | cal span |
|---|---|---|---|---|
| 60E0E500 | 0x6AAB4 | 0x6AAB4-0x6C600 | 0x6C600 | 70911 |
| 60E0E700_N3YLEE | 0x6AD34 | 0x6AD34-0x6C600 | 0x6C600 | 70911 |
| 60E0FB00 | 0x69F44 | 0x69F44-0x6D300 | 0x6D300 | 67583 |
| 60E0FC00 | 0x69F44 | 0x69F44-0x6D300 | 0x6D300 | 67583 |
| 60E15120_N3J1E | 0x6BC7C | 0x6BC7C-0x6C000 | 0x6C000 | 72447 |
| 60E1B900 | 0x6A1DC | 0x6A1DC-0x6D300 | 0x6D300 | 67583 |
| 60E1C500_N3J6EB | 0x6AD84 | 0x6AD84-0x6C600 | 0x6C600 | 70911 |
| 60E1D400 | 0x6C270 | 0x6C270-0x6CE00 | 0x6CE00 | 68863 |
| 60E32000_N3M5E | 0x7144C | 0x7144C-0x71500 | 0x71500 | 50687 |

## 3. Clustering / variant families

Content distance (1 - similarity):
- **<= 10%:** single members: 60E0E500 · 60E0E700_N3YLEE · {60E0FB00+60E0FC00+60E1B900} · 60E15120_N3J1E · 60E1C500_N3J6EB · 60E1D400 · 60E32000_N3M5E
- **<= 20%:** {60E0E500+60E1C500_N3J6EB+60E1D400} · 60E0E700_N3YLEE · {60E0FB00+60E0FC00+60E1B900} · 60E15120_N3J1E · 60E32000_N3M5E
- **<= 35%:** all except 60E32000_N3M5E

Full merge tree in `clusters.txt`.

## 4. Diff ranges vs baseline (classified)

Cumulative over the 8 baseline comparisons; **raw diff at identical offsets** (so `code` volume is mostly relocation smear, see other_ff_fraction).

| region | runs | diff bytes | known cal tables hit |
|---|---|---|---|
| code | 1269 | 3304274 | 310 |
| cal_data | 101 | 548589 | 9329 |
| tail | 89 | 46943 | 5 |
| header | 17 | 20242 | 0 |
| padding | 3 | 291 | 0 |

`other_ff_fraction` in diff_ranges.csv flags runs where the other ROM is 0xFF where baseline has content (relocated/layout-shift regions).

### Boot region (0x40-0x1FFF) is shared across families

Header-region byte diffs vs baseline: 60E1C500 = 0, 60E1B900 = 3, 60E32000 = 3, but 60E0E500 = 3888, 60E0E700 = 3887, 60E0FB00/60E0FC00 = 3887, 60E15120 = 3887. The boot/vector-handler block below the checksum start is byte-identical among {60E1D400, 60E1C500, 60E1B900, 60E32000} and differs as one block in the other five.

## 5. Calibration-table differences

9644 rows / 1209 distinct known-table addresses (60E1D400 map) differ vs baseline. Full u16 values + signed deltas in `cal_table_diffs_baseline.csv`. Per pair:

| pair | total addrs | value diffs | equal | FF artifact | max|delta| |
|---|---|---|---|---|---|---|
| 60E1D400__vs__60E0E500 | 1208 | 1160 | 25 | 23 | 64255 |
| 60E1D400__vs__60E0E700_N3YLEE | 1206 | 1181 | 11 | 14 | 65532 |
| 60E1D400__vs__60E0FB00 | 1204 | 1158 | 14 | 32 | 65534 |
| 60E1D400__vs__60E0FC00 | 1204 | 1158 | 14 | 32 | 65534 |
| 60E1D400__vs__60E15120_N3J1E | 1202 | 1186 | 16 | 0 | 64240 |
| 60E1D400__vs__60E1B900 | 1204 | 1158 | 14 | 32 | 65534 |
| 60E1D400__vs__60E1C500_N3J6EB | 1208 | 1159 | 26 | 23 | 64255 |
| 60E1D400__vs__60E32000_N3M5E | 1208 | 1175 | 19 | 14 | 64255 |

Nearly every known table address differs vs baseline — the calibration set itself is retuned between builds (rev-limit, sensor scaling, 2D/3D maps). FF artifacts = addresses 0xFF in the other ROM (relocated table block, mostly Z-line). NOTE: cal_tables.csv addresses are u16-aligned entries of f32 tables; a u16 read from an f32 word shows half the value, so deltas are indicative, not the full numeric difference.

## 6. Conclusions

- **60E0FB00 vs 60E0FC00 are near-duplicate images** (raw 0.008% = 43 bytes; content 99.95%, code 100.00%, cal 99.76%). The 43 bytes split as: cal-ID char (0x2005 `B`→`C`), two ASCII string bytes (0x6D316, 0x6D34B, 0x6D35D), a 2-byte boot field (0xFFC), a ~24-byte data block at 0x728D5 (ramp/serial-like values, not a plain string), a ~10-byte calibration-constant block at 0x77B47-0x77CC7 (for example 0x00000007 vs 0x01250125; 0x07 vs 0x62 triples), and checksum fields (0x7FB01-0x7FB04, descriptor diff @0x7FB88, tail CRC @0x7FFF4).
- **No other pair is a near-duplicate.** The 8 remaining builds are distinct firmwares sharing 50-92% of their 16-byte content.
- **5 variant families (content-distance based):**
  1. **Z-line US 6-port MT** = 60E0FB00 + 60E0FC00 + 60E1B900 (pairwise content >=91%; calibration blocks ~99.7% identical).
  2. **J-line** = 60E1D400 + 60E0E500 + 60E1C500 (pairwise content 77-90%; E500-C500 89.8% is the closest non-Z pair).
  3. **60E0E700 (N3YLEE)** — JDM-flavoured N3YL build; closer to J-line than Z-line but distinct (72-78% from J-line members).
  4. **60E15120 (internal SW-N3ZHEB000, tag _N3J1E)** — hybrid: cal content 91.1% vs baseline (near-J-line calibration) but code closer to Z-line (61-70%).
  5. **60E32000 (N3M5E)** — structural outlier (later/different market build): no large 0xFF gap, code dense to ~0x7144C, cal block ~0x715C0 (5-50KB later than everyone else); lowest content similarity overall (50-60%).
- **Where the bytes differ (vs baseline):** raw diff dominated by the `code` band, but most of that is relocation (other_ff_fraction near 1.0), not logic edits. The *true* tuning differences live in the `cal_data` band (0x6CE00-0x7DAFF): per-address table values differ nearly everywhere, and the table block is relocated per family (cal_lo 0x6C000-0x6D300, N3M5E ~0x715C0).
- **Calibration vs code:** code-region content similarity (49-100%) is usually higher than cal-region similarity (42-100%) for a given pair — code reading the tables is more conserved than the tables themselves.

## 7. Open questions

- Do the Z-line ROMs share a common relocated table layout (cal_lo ~0x6D300) or is relocation non-uniform? Needs a fresh mapscan per ROM.
- 60E15120 is tagged `_N3J1E` but carries Z-line software (SW-N3ZHEB000); its hybrid position (J-line calibration, Z-line code) should be confirmed against a per-ROM mapscan.
- What are the 0x728D5 and 0x77B47-0x77CC7 blocks that differ between FB00/FC00? (serial/anti-tamper vs real calibration constants).
- Baseline-anchored classification labels relocated code as `code`; a function-level (cross-reference / decompiler) diff would separate real logic edits from pure relocation.
