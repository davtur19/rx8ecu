# Stato tabelle ROM — RX-8

Riepilogo dei conteggi delle tabelle definite in
`symbols/romraider_rx8_tables.csv` per ciascun ROM code, con range di indirizzi.

## Conteggi per ROM

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

Totale righe: 37121.

## Note

### 5 ROM non in nostro possesso

I seguenti ROM code compaiono nelle definizioni tabelle ma **non** sono presenti come
binario in `roms/stock/`:

- **60E1D300**
- **60E0E600**
- **60E1A500**
- **60E1A300**
- **G-ROM_FLEX**

Le altre ROM, di cui disponiamo del binario, sono: `60E0E500`, `60E0E700`, `60E0FB00`,
`60E0FC00`, `60E15120`, `60E1B900`, `60E1C500`, `60E1D400` (più `60E32000`, presente come
file ma senza tabelle registrate nel csv).

## Sorgente dei dati

Le definizioni provengono dalle release di **RomRaider / GROM** (`romraider_rx8_tables.csv`).
Gli indirizzi sono espressi nel campo `addr` come offset `bare-hex`; il campo `rom_code`
identifica la ROM destino. Il campo `xmlid` dei def XML e referenziabile a partire
dall'immagine binaria all'offset `0x2000` per l'identificazione del firmware.