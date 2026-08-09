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