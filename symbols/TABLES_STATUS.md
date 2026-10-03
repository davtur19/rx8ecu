# ROM table status — RX-8

This file summarizes the counts of the tables defined in
`symbols/romraider_rx8_tables.csv` for each ROM code, with address ranges.

## Counts per ROM

| ROM | Tables | Addr range |
|-----|--------|------------|
| 60E0E500 | 6828 | 0x035868 .. 0x07e324 |
| 60E0E600 | 2662 | 0x000000 .. 0x07c7db |
| 60E0E700 | 2662 | 0x000000 .. 0x07c7db |
| 60E0FB00 | 2572 | 0x035230 .. 0x07cb00 |
| 60E0FC00 | 2684 | 0x02584c .. 0x07cb8f |
| 60E15120 | 2500 | 0x034da8 .. 0x07e6f0 |
| 60E1A300 | 2406 | 0x034a24 .. 0x07e8fc |
| 60E1A500 | 2660 | 0x000000 .. 0x07bdc0 |
| 60E1B900 | 2476 | 0x0354c8 .. 0x07ca74 |
| 60E1C500 | 1331 | 0x000000 .. 0x07c7db |
| 60E1D300 | 2742 | 0x000000 .. 0x07dd60 |
| 60E1D400 | 2926 | 0x000000 .. 0x07d92c |
| G-ROM_FLEX | 2672 | 0x035230 .. 0x07cb8f |

Total rows: 37121.

## Notes

### Counts include exact duplicates

The per-ROM `Tables` counts and `Total rows` count **every data row, including
exact duplicates** — they are raw definition counts, not counts of distinct
tables. Measured 2026-10-04 with a streaming `LC_ALL=C sort | uniq` pass
(`ulimit -v`, sort spills to disk): the 37,121 data rows contain only
**19,870 distinct** lines, so **17,251 rows (46.5%) are exact duplicates** of
another row (17,163 distinct duplicated definitions, covering 34,414 rows).
All 13 per-ROM counts and address ranges above were re-verified against the
CSV (13/13 exact, total 37121 exact). The CSV is intentionally **not
deduplicated**: dedup is out of scope (upstream RomRaider/GROM source churn
risk), so consumers must dedup themselves if they need distinct tables.

### 5 ROMs we do not possess

These ROM codes appear in the table definitions but are **not** present as a binary in `roms/stock/`:

- **60E1D300**
- **60E0E600**
- **60E1A500**
- **60E1A300**
- **G-ROM_FLEX**

The other ROMs, whose binary we have, are: `60E0E500`, `60E0E700`, `60E0FB00`,
`60E0FC00`, `60E15120`, `60E1B900`, `60E1C500`, `60E1D400`. `60E32000` is present
as a file but has no tables registered in the csv.

## Data source

The definitions come from the **RomRaider / GROM** releases (`romraider_rx8_tables.csv`).
The `addr` field expresses the addresses as `bare-hex` offsets; the field `rom_code`
identifies the destination ROM. The field `xmlid` of the XML defs is referencable
from the binary image at the offset `0x2000` to identify the firmware.