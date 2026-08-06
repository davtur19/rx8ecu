# CATALOG_STATUS -- stato catalogo master (post lift-merge, DEDUP)

Merge di TUTTI i `symbols_*.csv` (varianti incluse) con i nomi lift (`c/*.c`, `c/tests/test_*.py`). `CATALOG_MASTER.csv` e' DEDUP per `(bank, addr)`: per chiave si tiene UNA sola riga (source piu' autorevole); le altre sorgenti perse sono elencate in `also_sources`. `lift_name` porta il nome autorevole se disponibile, altrimenti coincide con `src_name`. Colonna `category` in coda: join con `FUNCTION_CATEGORIES.csv` su `(bank normalizzato, int(addr,16))` — ~6.082 righe matchate, cella vuota per le non classificate.

| bank | file | rows (incl. variants) | total (unique) | nominate | anonime | lift-named | di cui VERIFIED | note |
|-----:|------|----------------------:|---------------:|---------:|--------:|-----------:|----------------:|------|
| 60E0E500 | symbols_60E0E500.csv<br/>symbols_60E0E500_connor.csv | 7312 | 7305 | 431 | 6874 | 203 | 61 | derivata over-segmentata |
| 60E0E700 | symbols_60E0E700.csv<br/>symbols_60E0E700_connor.csv | 7313 | 7306 | 438 | 6868 | 203 | 63 | derivata over-segmentata |
| 60E0FB00 | symbols_60E0FB00.csv<br/>symbols_60E0FB00_connor.csv | 7203 | 7197 | 844 | 6353 | 814 | 69 | derivata over-segmentata |
| 60E0FC00 | equinox311_60E0FC00_named.csv<br/>symbols_60E0FC00.csv<br/>symbols_60E0FC00_connor.csv<br/>symbols_60E0FC00_ghidra.csv<br/>symbols_60E0FC00_merged2.csv | 9018 | 3490 | 1767 | 1723 | 845 | 66 | canonico affidabile (equiname) |
| 60E15120 | symbols_60E15120.csv<br/>symbols_60E15120_connor.csv | 7480 | 7473 | 398 | 7075 | 188 | 60 | derivata over-segmentata |
| 60E1B900 | symbols_60E1B900.csv<br/>symbols_60E1B900_connor.csv | 7185 | 7173 | 466 | 6707 | 225 | 73 | derivata over-segmentata |
| 60E1C500 | symbols_60E1C500.csv<br/>symbols_60E1C500_connor.csv | 7327 | 7315 | 477 | 6838 | 253 | 83 | derivata over-segmentata |
| 60E1D400 | symbols_60E1D400_connor.csv<br/>symbols_60E1D400_ida.csv<br/>symbols_60E1D400_merged.csv | 5609 | 2795 | 2795 | 0 | 1081 | 197 | canonico affidabile (IDA-ai) |
| 60E32000 | symbols_60E32000.csv<br/>symbols_60E32000_connor.csv | 6911 | 6899 | 390 | 6509 | 184 | 59 | derivata over-segmentata |

* `rows (incl. variants)` = righe CUMULATIVE da TUTTI i CSV della bank (varianti ridondanti incluse); `total (unique)` = righe uniche per (bank, addr) dopo il dedup — questa e' la cifra reale per bank.

**LIFT_ONLY addrs (boundary non in IDA): 5** — lift addrs senza START di riga in alcun CSV, adottati come entry del catalogo (`source=lift`, `flag=LIFT_ONLY`; di cui 4 VERIFIED). Attribuzione bank via range CSV, fallback 60E1D400.

## NOISE (span<=4, derived only)

Righe `source=derived` (banche derivate over-segmentate), non LIFT_ONLY, non nominate, con span `(end - addr) <= 4` byte — quasi certamente rumore di segmentazione (puntatori pooled / boundary falsi). La riga NON e' cancellata: `flag` riceve `NOISE` (aggiunto con `|` se gia' presente).

| bank | unique | noise | real-estimate (unique - noise) |
|-----:|-------:|------:|-------------------------------:|
| 60E0E500 | 7305 | 885 | 6420 |
| 60E0E700 | 7306 | 915 | 6391 |
| 60E0FB00 | 7197 | 817 | 6380 |
| 60E15120 | 7473 | 942 | 6531 |
| 60E1B900 | 7173 | 838 | 6335 |
| 60E1C500 | 7315 | 903 | 6412 |
| 60E32000 | 6899 | 864 | 6035 |
| **TOT** | **56953** | **6164** | **50789** |


