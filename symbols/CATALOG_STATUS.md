# CATALOG_STATUS -- stato catalogo master (post lift-merge, DEDUP)

All `symbols_*.csv` files (variants included) are merged with the lift names (`c/*.c`, `c/tests/test_*.py`) into `CATALOG_MASTER.csv`. The catalog is DEDUP per `(bank, addr)`. Each key keeps ONE row (the most authoritative source). The other lost sources are listed in `also_sources`. `lift_name` carries the authoritative name if available, otherwise it matches `src_name`. The `category` column is at the end. Join it with `FUNCTION_CATEGORIES.csv` on `(bank normalizzato, int(addr,16))` — it matched ~6.082 rows, with an empty cell for the unclassified rows.

| bank | file | rows (incl. variants) | total (unique) | nominate | anonime | lift-named | di cui VERIFIED | note |
|-----:|------|----------------------:|---------------:|---------:|--------:|-----------:|----------------:|------|
| 60E0E500 | symbols_60E0E500.csv<br/>symbols_60E0E500_connor.csv | 7312 | 7305 | 416 | 6889 | 189 | 56 | derivata over-segmentata |
| 60E0E700 | symbols_60E0E700.csv<br/>symbols_60E0E700_connor.csv | 7313 | 7306 | 435 | 6871 | 200 | 58 | derivata over-segmentata |
| 60E0FB00 | symbols_60E0FB00.csv<br/>symbols_60E0FB00_connor.csv | 7203 | 7197 | 832 | 6365 | 805 | 64 | derivata over-segmentata |
| 60E0FC00 | equinox311_60E0FC00_named.csv<br/>symbols_60E0FC00.csv<br/>symbols_60E0FC00_connor.csv<br/>symbols_60E0FC00_ghidra.csv<br/>symbols_60E0FC00_merged2.csv | 9014 | 3491 | 1758 | 1733 | 845 | 61 | canonico affidabile (equiname) |
| 60E15120 | symbols_60E15120.csv<br/>symbols_60E15120_connor.csv | 7480 | 7473 | 388 | 7085 | 179 | 54 | derivata over-segmentata |
| 60E1B900 | symbols_60E1B900.csv<br/>symbols_60E1B900_connor.csv | 7185 | 7173 | 457 | 6716 | 215 | 68 | derivata over-segmentata |
| 60E1C500 | symbols_60E1C500.csv<br/>symbols_60E1C500_connor.csv | 7327 | 7315 | 459 | 6856 | 234 | 78 | derivata over-segmentata |
| 60E1D400 | symbols_60E1D400_connor.csv<br/>symbols_60E1D400_ida.csv<br/>symbols_60E1D400_merged.csv | 5609 | 2795 | 2794 | 1 | 936 | 189 | canonico affidabile (IDA-ai) |
| 60E32000 | symbols_60E32000.csv<br/>symbols_60E32000_connor.csv | 6911 | 6899 | 382 | 6517 | 176 | 54 | derivata over-segmentata |

* `rows (incl. variants)` = cumulative rows from ALL CSVs of the bank (redundant variants included); `total (unique)` = unique rows per (bank, addr) after the dedup — this is the real figure per bank.

**LIFT_ONLY addrs (boundary not in IDA): 5** — lift addrs without a row START in any CSV, adopted as catalog entries (`source=lift`, `flag=LIFT_ONLY`; 4 of them VERIFIED). Bank attribution through the CSV range, fallback 60E1D400.

## NOISE (span<=4, derived only)

Rows `source=derived` (over-segmented derived banks), not LIFT_ONLY, not named, with span `(end - addr) <= 4` bytes — almost certainly segmentation noise (pooled pointers / false boundaries). The row is NOT deleted: `flag` receives `NOISE` (added with `|` if already present).

| bank | unique | noise | real-estimate (unique - noise) |
|-----:|-------:|------:|-------------------------------:|
| 60E0E500 | 7305 | 886 | 6419 |
| 60E0E700 | 7306 | 917 | 6389 |
| 60E0FB00 | 7197 | 819 | 6378 |
| 60E15120 | 7473 | 943 | 6530 |
| 60E1B900 | 7173 | 838 | 6335 |
| 60E1C500 | 7315 | 905 | 6410 |
| 60E32000 | 6899 | 864 | 6035 |
| **TOT** | **56954** | **6172** | **50782** |


