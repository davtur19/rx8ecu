# CATALOG_STATUS -- stato catalogo master (post lift-merge, DEDUP)

Merge di TUTTI i `symbols_*.csv` (varianti incluse) con i nomi lift (`c/*.c`, `c/tests/test_*.py`). `CATALOG_MASTER.csv` e' DEDUP per `(bank, addr)`: per chiave si tiene UNA sola riga (source piu' autorevole); le altre sorgenti perse sono elencate in `also_sources`. `lift_name` porta il nome autorevole se disponibile, altrimenti coincide con `src_name`.

| bank | file | rows (incl. variants) | total (unique) | nominate | anonime | lift-named | di cui VERIFIED | note |
|-----:|------|----------------------:|---------------:|---------:|--------:|-----------:|----------------:|------|
| 60E0E500 | symbols_60E0E500.csv | 7305 | 7305 | 310 | 6995 | 50 | 49 | derivata over-segmentata |
| 60E0E700 | symbols_60E0E700.csv | 7306 | 7306 | 313 | 6993 | 53 | 52 | derivata over-segmentata |
| 60E0FB00 | symbols_60E0FB00.csv | 7197 | 7197 | 339 | 6858 | 56 | 55 | derivata over-segmentata |
| 60E0FC00 | symbols_60E0FC00.csv<br/>symbols_60E0FC00_ghidra.csv<br/>symbols_60E0FC00_merged2.csv | 7849 | 3459 | 1367 | 2092 | 53 | 52 | canonico affidabile (equiname) |
| 60E15120 | symbols_60E15120.csv | 7473 | 7473 | 288 | 7185 | 49 | 48 | derivata over-segmentata |
| 60E1B900 | symbols_60E1B900.csv | 7173 | 7173 | 330 | 6843 | 63 | 61 | derivata over-segmentata |
| 60E1C500 | symbols_60E1C500.csv | 7315 | 7315 | 316 | 6999 | 73 | 71 | derivata over-segmentata |
| 60E1D400 | symbols_60E1D400_ida.csv<br/>symbols_60E1D400_merged.csv | 5583 | 2794 | 2753 | 41 | 175 | 171 | canonico affidabile (IDA-ai) |
| 60E32000 | symbols_60E32000.csv | 6899 | 6899 | 272 | 6627 | 49 | 48 | derivata over-segmentata |

* `rows (incl. variants)` = righe CUMULATIVE da TUTTI i CSV della bank (varianti ridondanti incluse); `total (unique)` = righe uniche per (bank, addr) dopo il dedup — questa e' la cifra reale per bank.

**LIFT_ONLY addrs (boundary non in IDA): 5** — lift addrs senza START di riga in alcun CSV, adottati come entry del catalogo (`source=lift`, `flag=LIFT_ONLY`; di cui 4 VERIFIED). Attribuzione bank via range CSV, fallback 60E1D400.

