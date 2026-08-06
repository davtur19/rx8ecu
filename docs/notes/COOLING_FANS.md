# Cooling Fans — verified calibration tables

Verified cooling-fan control tables in ROM **60E1D400** (`roms/stock/60E1D400.bin`),
f32 big-endian, confirmed by reading the binary. Same block in stock and fanmod-tuned variants.

## Fan temperature thresholds (60E1D400)

| Address | f32 value | Meaning |
|----------|-----------|---------|
| `0x07793C` | 97.0 °C | Fan 1 enable coolant temperature threshold |
| `0x077940` | 3.0  °C | Fan 1 disable hysteresis |
| `0x077944` | 97.0 °C | Fan 2 enable coolant temperature threshold |
| `0x077948` | 3.0  °C | Fan 2 disable hysteresis |
| `0x07794C` | 101.0 °C | Fan high-speed enable coolant temperature threshold |
| `0x077950` | 3.0  °C | Fan high-speed disable hysteresis |

Range: `0x07793C`–`0x077950` (3-byte groups per RomRaider table layout).

## Vehicle-speed cuts

| Address | f32 value | Meaning |
|----------|-----------|---------|
| `0x077988` | 10.0 (km/h) | Fan 2 disable vehicle-speed threshold (aero assist) |
| `0x07798C` | 2.0  (km/h) | Fan 2 disable vehicle-speed hysteresis |

## Tuned-ROM evidence (fanmod V1/V2) — confirms the table function

The fanmod tuned ROMs lower these thresholds **at the same addresses** (per `V1/V2 modifications.txt`):

- Variant A: 97→90 °C (Fan 1 + Fan 2), 101→95 °C (high speed)
- Variant B: 97→88 °C (Fan 1 + Fan 2), 101→93 °C (high speed)

Byte-level spot check of the tuned bins confirms the f32 at `0x07793C`/`0x077944` drops to 90.0 (V1) / 88.0 (V2), layout otherwise unchanged — direct evidence these are the coolant-temp fan-enable thresholds.

## Mapping

- Cooling subsystem reference: `12_vehicle_subsystems/05_cooling.md` (ROM fan tables, `0xFFFFA73C` coolant temp RAM input, `0xFFFFA95C` fan control output, DTCs P0480/P0481, CAN status frames 0x620/0x630).
- Fan behavior: No. 1 on with ECT above ~96–97 °C and/or A/C request; No. 2 + high-speed staged above that; high-speed cut at high vehicle speed.
- OBD control PIDs (secured session): `0x17C3` Fan Enable 1, `0x17C4` Fan Enable 2.
