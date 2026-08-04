# CATALOG_STATUS -- stato catalogo master (post lift-merge, DEDUP)

Merge di TUTTI i `symbols_*.csv` (varianti incluse) con i nomi lift (`c/*.c`, `c/tests/test_*.py`). `CATALOG_MASTER.csv` e' DEDUP per `(bank, addr)`: per chiave si tiene UNA sola riga (source piu' autorevole); le altre sorgenti perse sono elencate in `also_sources`. `lift_name` porta il nome autorevole se disponibile, altrimenti coincide con `src_name`. Colonna `category` in coda: join con `FUNCTION_CATEGORIES.csv` su `(bank normalizzato, int(addr,16))` — ~6.082 righe matchate, cella vuota per le non classificate.

| bank | file | rows (incl. variants) | total (unique) | nominate | anonime | lift-named | di cui VERIFIED | note |
|-----:|------|----------------------:|---------------:|---------:|--------:|-----------:|----------------:|------|
| 60E0E500 | symbols_60E0E500.csv<br/>symbols_60E0E500_connor.csv | 7312 | 7305 | 310 | 6995 | 50 | 49 | derivata over-segmentata |
| 60E0E700 | symbols_60E0E700.csv<br/>symbols_60E0E700_connor.csv | 7313 | 7306 | 313 | 6993 | 53 | 52 | derivata over-segmentata |
| 60E0FB00 | symbols_60E0FB00.csv<br/>symbols_60E0FB00_connor.csv | 7203 | 7197 | 339 | 6858 | 56 | 55 | derivata over-segmentata |
| 60E0FC00 | equinox311_60E0FC00_named.csv<br/>symbols_60E0FC00.csv<br/>symbols_60E0FC00_connor.csv<br/>symbols_60E0FC00_ghidra.csv<br/>symbols_60E0FC00_merged2.csv | 9018 | 3490 | 1518 | 1972 | 53 | 52 | canonico affidabile (equiname) |
| 60E15120 | symbols_60E15120.csv<br/>symbols_60E15120_connor.csv | 7480 | 7473 | 288 | 7185 | 49 | 48 | derivata over-segmentata |
| 60E1B900 | symbols_60E1B900.csv<br/>symbols_60E1B900_connor.csv | 7185 | 7173 | 330 | 6843 | 63 | 61 | derivata over-segmentata |
| 60E1C500 | symbols_60E1C500.csv<br/>symbols_60E1C500_connor.csv | 7327 | 7315 | 316 | 6999 | 73 | 71 | derivata over-segmentata |
| 60E1D400 | symbols_60E1D400_connor.csv<br/>symbols_60E1D400_ida.csv<br/>symbols_60E1D400_merged.csv | 5607 | 2794 | 2753 | 41 | 175 | 171 | canonico affidabile (IDA-ai) |
| 60E32000 | symbols_60E32000.csv<br/>symbols_60E32000_connor.csv | 6911 | 6899 | 272 | 6627 | 49 | 48 | derivata over-segmentata |

* `rows (incl. variants)` = righe CUMULATIVE da TUTTI i CSV della bank (varianti ridondanti incluse); `total (unique)` = righe uniche per (bank, addr) dopo il dedup — questa e' la cifra reale per bank.

**LIFT_ONLY addrs (boundary non in IDA): 5** — lift addrs senza START di riga in alcun CSV, adottati come entry del catalogo (`source=lift`, `flag=LIFT_ONLY`; di cui 4 VERIFIED). Attribuzione bank via range CSV, fallback 60E1D400.

## NOISE (span<=4, derived only)

Righe `source=derived` (banche derivate over-segmentate), non LIFT_ONLY, non nominate, con span `(end - addr) <= 4` byte — quasi certamente rumore di segmentazione (puntatori pooled / boundary falsi). La riga NON e' cancellata: `flag` riceve `NOISE` (aggiunto con `|` se gia' presente).

| bank | unique | noise | real-estimate (unique - noise) |
|-----:|-------:|------:|-------------------------------:|
| 60E0E500 | 7305 | 899 | 6406 |
| 60E0E700 | 7306 | 926 | 6380 |
| 60E0FB00 | 7197 | 852 | 6345 |
| 60E15120 | 7473 | 954 | 6519 |
| 60E1B900 | 7173 | 854 | 6319 |
| 60E1C500 | 7315 | 915 | 6400 |
| 60E32000 | 6899 | 876 | 6023 |
| **TOT** | **56952** | **6276** | **50676** |


