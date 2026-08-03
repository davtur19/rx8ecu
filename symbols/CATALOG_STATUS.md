# CATALOG_STATUS -- stato catalogo master (post lift-merge)

Merge di tutti i `symbols_*.csv` con i nomi lift (`c/*.c`, `c/tests/test_*.py`). `CATALOG_MASTER.csv` preserva ogni riga originale; `lift_name` porta il nome autorevole se disponibile, altrimenti coincide con `src_name`.

| bank | file | total | nominate | anonime | lift-named | di cui VERIFIED | note |
|-----:|------|------:|---------:|--------:|-----------:|----------------:|------|
| 60E0E500 | symbols_60E0E500.csv | 7305 | 310 | 6995 | 50 | 49 | derivata over-segmentata |
| 60E0E700 | symbols_60E0E700.csv | 7306 | 313 | 6993 | 53 | 52 | derivata over-segmentata |
| 60E0FB00 | symbols_60E0FB00.csv | 7197 | 339 | 6858 | 56 | 55 | derivata over-segmentata |
| 60E0FC00 | symbols_60E0FC00.csv<br/>symbols_60E0FC00_ghidra.csv<br/>symbols_60E0FC00_merged2.csv | 7849 | 3304 | 4545 | 137 | 134 | canonico affidabile (equiname) |
| 60E15120 | symbols_60E15120.csv | 7473 | 288 | 7185 | 49 | 48 | derivata over-segmentata |
| 60E1B900 | symbols_60E1B900.csv | 7173 | 330 | 6843 | 63 | 61 | derivata over-segmentata |
| 60E1C500 | symbols_60E1C500.csv | 7315 | 316 | 6999 | 73 | 71 | derivata over-segmentata |
| 60E1D400 | symbols_60E1D400_ida.csv<br/>symbols_60E1D400_merged.csv | 5578 | 5496 | 82 | 340 | 334 | canonico affidabile (IDA-ai) |
| 60E32000 | symbols_60E32000.csv | 6899 | 272 | 6627 | 49 | 48 | derivata over-segmentata |

