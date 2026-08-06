# RX-8 ECU Calibration Table Cross-Reference

> **WARNING:** the descriptor addresses below reference a **private ROM variant** (J-line shift +0x298); on the shipped `60E1D400.bin` apply a **+0x298** shift (verified: Ignition Leading Base @0x69AF8, MAF @0x6A0E4, deadtime @0x6B264). Always verify with `tools/mapscan.py`.

> **ROM:** N3J1EL (60E1D400) · **ECU:** Mazda RX-8 S1 (2004–2008), Renesis 1.3L · **CPU:** Renesas SH7055 (SH-2E) · **ROM:** 512 KB (0x00000–0x7FFFF) · **Generated:** July 2026
> **Sources:** `cal_tables.csv`, `mapscan.py`, verified C in `c/`, IDA reports (private storage), RomRaider `rx8_defs.xml` (not redistributed; naming follows its conventions)

Maps every identified calibration table to the functions that consume it (`c/`), the map descriptor (`mapscan.py`), and the RomRaider definition name.

Two lookup functions:

| Function | ROM Address | Purpose | C Source |
|----------|-------------|---------|----------|
| `TwoDLookup` | 0x2068 | 1D table lookup (axis + value array) | `c/2DLookup.c` |
| `ThreeDLookup` | 0x20DC | 2D/3D lookup (X + Y axis + grid) | `c/3dLookup.c` |

Descriptor format read by both:
```
Map1D (20B): u16 count; u8 type; f32* axis@4; void* values@8; f32 scale@12; f32 offset@16
Map2D (28B): u16 count_x; u16 count_y; f32* axis_x@4; f32* axis_y@8; void* values@12; u8 type@16; f32 scale@20; f32 offset@24
```
Type codes: 0=f32 (no scale/offset) · 4=u8 · 8=u16 · 12=s8 · 16=s16. Physical = `raw * scale + offset` (integer types); f32 stored as-is.

Data flow: code → loads descriptor addr into R4 → calls `TwoDLookup`/`ThreeDLookup` → descriptor struct (ROM 0x6969C–0x6BFC0, **499 descriptors**: 119×2D, 380×1D) → value/axis arrays (0x6CFA4–0x7D92C, ~1,209 named entries).

## Descriptor Catalog (mapscan.py -> values)

### Ignition System Descriptors (0x697BC–0x69C98)

| Desc Addr | Kind | Dims | Type | Scale | Offset | Values | Name |
|-----------|------|------|------|-------|--------|--------|------|
| 0x697BC | 1D | 6 | u8 | 0.5 | -50 | 0x6D59C | Ignition Maybe Idle Base |
| 0x697D0 | 1D | 9 | u8 | 0.01 | 0 | 0x6D5C8 | Ignition Temp Correction? |
| 0x697E4 | 1D | 6 | u8 | 0.5 | -50 | 0x6D5EC | Ignition 2 |
| 0x697F8 | 1D | 9 | u8 | 0.01 | 0 | 0x6D618 | Ignition Leading 0 |
| 0x6980C | 2D | 10×7 | u8 | 0.5 | -50 | 0x6D668 | Ignition Timing Lead |
| 0x69828 | 2D | 20×18 | u8 | 0.5 | -50 | 0x6D748 | Ignition Leading 1 |
| 0x69844 | 2D | 20×18 | u8 | 0.5 | -50 | 0x6D948 | Ignition Leading Base - Safe Mode |
| 0x69860 | 2D | 20×18 | u8 | 0.5 | -50 | 0x6DB48 | Ignition Leading Base |
| 0x6987C | 2D | 10×7 | u8 | 0.5 | -50 | 0x6DCF4 | Ignition Leading 4 |
| 0x69898 | 2D | 20×18 | u8 | 0.5 | -50 | 0x6DDD4 | Ignition |
| 0x698B4 | 2D | 20×18 | u8 | 0.5 | -50 | 0x6DFD4 | Ignition 0 - Safe Mode |
| 0x698D0 | 2D | 20×18 | u8 | 0.5 | -50 | 0x6E1D4 | Ignition 1 |
| 0x698EC | 2D | 4×3 | f32 | — | — | 0x6E358 | Ignition Leading 5 |
| 0x69900 | 2D | 4×3 | f32 | — | — | 0x6E3A4 | Ignition Minimum Maybe |
| 0x69EF8 | 2D | 20×18 | u8 | 0.5 | -50 | 0x6EEEC | Ignition Trailing B |
| 0x69F14 | 2D | 20×18 | u8 | 0.5 | -50 | 0x6F0EC | Ignition Trailing A |
| 0x69F30 | 2D | 20×18 | u8 | 0.5 | -50 | 0x6F2EC | Ignition Min Split |
| 0x69CB4 | 2D | 19×11 | f32 | — | — | 0x6F4CC | Ignition 3 |
| 0x69CC8 | 1D | 12 | u8 | 0.5 | -50 | 0x6F78C | Ignition 4 |
| 0x69CF0 | 1D | 12 | u8 | 0.5 | -50 | 0x6F7D0 | Ignition 6 |
| 0x6BF28 | 2D | 9×9 | f32 | — | — | 0x7CB20 | Ignition Dwell Time_ |

> **Verificata (emulatore, `calc_spark_lead_trail_split_0x19220`, 0 mismatch/500k):** TrailingB=desc 0x69EF8, TrailingA=desc 0x69F14, MinSplit=desc 0x69F30; past refs 0x69C60/0x69C7C/0x69C98 are NOT used by 0x19220 (check other refs).

### Fuel System Descriptors (0x69E2C–0x6A580)

| Desc Addr | Kind | Dims | Type | Scale | Offset | Values | Name |
|-----------|------|------|------|-------|--------|--------|------|
| 0x6A2E8 | 1D | 9 | u8 | 0.007812 | 0 | 0x71CD0 | Fuelling - Safe Mode |
| 0x6A310 | 1D | 7 | u8 | 0.007812 | 0 | 0x71D00 | Fuelling 1 |
| 0x6A324 | 1D | 9 | u8 | 0.007812 | 0 | 0x71D2C | Fuelling 2 - Safe Mode |
| 0x6A338 | 1D | 9 | u8 | 0.007812 | 0 | 0x71D5C | Fuelling 3 |
| 0x6A34C | 1D | 7 | u8 | 0.007812 | 0 | 0x71D84 | Fuelling 4 |
| 0x6A360 | 1D | 18 | u8 | 0.003906 | 0 | 0x71DD4 | Fuelling 5 |
| 0x6A374 | 1D | 18 | u8 | 0.003906 | 0 | 0x71E30 | Fuelling 6 |
| 0x6A388 | 1D | 18 | u8 | 0.003906 | 0 | 0x71E8C | Fuelling 7 |
| 0x6A43C | 1D | 7 | u8 | 0.003906 | 0 | 0x72084 | Fuelling 8 |
| 0x6A4BC | 2D | 12×8 | u8 | 0.003906 | 0 | 0x7228C | Fuelling 9 - Safe Mode |
| 0x6A4D8 | 2D | 21×19 | u8 | 0.003906 | 0 | 0x7238C | Fuelling 10 - Safe Mode |
| 0x6A52C | 2D | 12×8 | u8 | 0.003906 | 0 | 0x72584 | Fuelling 13 - Safe Mode |
| 0x6A548 | 2D | 21×19 | u8 | 0.003906 | 0 | 0x72684 | Fuelling 14 - Safe mode |
| 0x6A564 | 2D | 12×8 | u8 | 0.003906 | 0 | 0x72864 | Fuelling 15 |
| 0x6A580 | 2D | 21×19 | u8 | 0.003906 | 0 | 0x72964 | Fuelling 16 |

### Sensor Scaling Descriptors (0x69E14–0x69EB4)

| Desc Addr | Kind | Dims | Type | Values | Name |
|-----------|------|------|------|--------|------|
| 0x69E14 | 1D | 32 | f32 | 0x6F96C | CLT Sensor Scaling |
| 0x69E4C | 1D | 48 | f32 | 0x6FBD8 | MAF Scaling (J-line variant descriptor; in 60E1D400 at 0x6A0E4 — see `SENSOR_PIPELINE.md`) |
| 0x69E58 | 1D | 8 | f32 | 0x6FCF8 | Table 2D - 295 Check DataType |
| 0x69E64 | 1D | 8 | f32 | 0x6FD20 | Table 2D - 296 Check DataType |
| 0x69E70 | 1D | 4 | f32 | 0x6FD38 | Injector Barometric Pressure Comp |
| 0x69E7C | 1D | 11 | f32 | 0x6FD74 | Lambda Sensor Scaling |
| 0x69EB4 | 1D | 16 | f32 | 0x6FFE8 | IAT Sensor Scaling |

### Sensor Conditioning Descriptors (0x69EC0–0x69F98)

| Desc Addr | Kind | Dims | Type | Scale | Offset | Values | Name |
|-----------|------|------|------|-------|--------|--------|------|
| 0x69EC0 | 1D | 10 | u8 | 50 | 0 | 0x70084 | Table 2D - 60_ (MAF filter freq) |
| 0x69ED4 | 1D | 8 | u8 | 0.01 | 0 | 0x700B0 | Table 2D - 61_ (IAT filter) |
| 0x69EE8 | 1D | 10 | u8 | 0.01 | 0 | 0x700E0 | Table 2D - 62_ (CLT filter) |
| 0x69EFC | 1D | 9 | u16 | 0.001 | 0 | 0x70110 | Table 2D - 63_ (Load signal) |
| 0x69F10 | 1D | 16 | u8 | 0.003906 | 0 | 0x70230 | Table 2D - 64_ (Baro adj) |
| 0x69F24 | 1D | 9 | u8 | 0.007812 | 0 | 0x70264 | Table 2D - 65_ (O2 switch) |
| 0x69F38 | 1D | 3 | u8 | 0.01 | 0 | 0x7027C | Table 2D - 66_ |
| 0x69F4C | 1D | 9 | u8 | 0.007812 | 0 | 0x702A4 | Table 2D - 67_ (TPS deadband) |
| 0x69F78 | 1D | 15 | u8 | 0.007812 | 0 | 0x70334 | Table 2D - 68_ |
| 0x69F98 | 1D | 7 | u16 | 0.0001 | -1 | 0x703BC | Table 2D - 69_ (Load smooth) |

### Throttle & Pedal Descriptors (0x6A9C8–0x6AA1C)

| Desc Addr | Kind | Dims | Type | Scale | Offset | Values | Name |
|-----------|------|------|------|-------|--------|--------|------|
| 0x6A9C8 | 2D | 21×18 | u16 | 0.003052 | 0 | 0x74250 | Accel Pedal to Throttle Position #1 |
| 0x6A9E4 | 2D | 21×18 | u16 | 0.003052 | 0 | 0x745E0 | Accel Pedal to Throttle Position #2 |
| 0x6AA00 | 2D | 21×18 | u16 | 0.003052 | 0 | 0x74970 | Accel Pedal to Throttle Position #3 |
| 0x6AA1C | 2D | 21×18 | u16 | 0.003052 | 0 | 0x74D00 | Accel Pedal to Throttle Position #4 |
| 0x6A6D4 | 2D | 26×19 | u16 | 0.003052 | 0 | 0x73090 | Torque To Accel Position |
| 0x6A6F0 | 2D | 14×20 | u16 | 0.007812 | -256 | 0x734F4 | Throttle Position To Torque |

### Knock Control Descriptors (0x6B650–0x6B69C)

| Desc Addr | Kind | Dims | Type | Scale | Offset | Values | Name |
|-----------|------|------|------|-------|--------|--------|------|
| 0x6B650 | 1D | 14 | f32 | — | — | 0x7A38C | Knock Related 1 |
| 0x6B65C | 1D | 14 | f32 | — | — | 0x7A3E0 | Knock Related 2 |
| 0x6B680 | 2D | 6×11 | u8 | 0.05 | 0 | 0x7A450 | Knock Rel #4 |
| 0x6B69C | 2D | 6×11 | u8 | 0.05 | 0 | 0x7A4D8 | Knock Rel #0 |

### Oil Metering Descriptors (0x6B264–0x6B28C)

| Desc Addr | Kind | Dims | Values | Name |
|-----------|------|------|--------|------|
| 0x6B264 | 2D | 19×17 f32 | 0x790C4 | Oil Metering By Load |
| 0x6B278 | 2D | 19×4 f32 | 0x79264 | Oil Metering By Throttle |

### Injector Descriptors (0x6AF38–0x6AF54, 0x6AFCC–0x6AFE0)

| Desc Addr | Kind | Dims | Type | Scale | Values | Name |
|-----------|------|------|------|-------|--------|------|
| 0x6AF38 | 2D | 17×9 | u16 | 1 | 0x77F58 | Injector Latency Secondary |
| 0x6AF54 | 2D | 17×9 | u16 | 1 | 0x780F4 | Injector Latency Primary |
| 0x6AFCC | 1D | 12 | u16 | 5 | 0x78318 | Table 2D - 175_ (Injector deadtime primary) |
| 0x6AFE0 | 1D | 13 | u16 | 5 | 0x78364 | Table 2D - 176_ (Injector deadtime secondary) |

### Load Management Descriptors (0x6BD88–0x6BDA0)

| Desc Addr | Kind | Dims | Type | Scale | Offset | Values | Name |
|-----------|------|------|------|-------|--------|--------|------|
| 0x6BD88 | 1D | 12 | f32 | — | — | 0x7C1B4 | Load Limit A |
| 0x6BD94 | 1D | 12 | f32 | — | — | 0x7C214 | Load Limit B |
| 0x6BDA0 | 1D | 10 | u16 | 0.001 | 0 | 0x7C354 | Load Limit C |
| 0x6B0B0 | 2D | 18×20 | u16 | 1.526e-05 | 0.75 | 0x786E8 | Engine Load Compensation |
| 0x6AF1C | 2D | 17×20 | u16 | 0.003906 | 0 | 0x77C48 | Estimated Manifold Pressure |

> **Full 499-entry descriptor catalog**: `tools/mapscan.py` output or `docs/subsystems/MAPS.md`.

## C Function Cross-Reference

### `maf_sensor_value.c`
| Address | Name | Access | Notes |
|---------|------|--------|-------|
| 0x6FBD8 | **MAF Scaling** | 1D f32[48] thru desc@0x69E4C (J-line variant) | Voltage→g/rev lookup |

### `o2_lambda_subsystem.c` (uses Tables 110/111)
| Address | Name | Access | Notes |
|---------|------|--------|-------|
| 0x72D78 | Y (front O₂ threshold array) | float[4] | Voltage breakpoints |
| 0x72DD0 | **Table 2D - 110_** (front O₂ lookup) | u8[9] | Voltage→trim-index |
| 0x72DE8 | Y (rear O₂ threshold array) | float[4] | Voltage breakpoints |
| 0x72E40 | **Table 2D - 111_** (rear O₂ lookup) | u8[9] | Voltage→trim-index |
| 0x6A868 / 0x6A87C | adaptive trim tables A/B | EEPROM | LTFT banks A & B |
| 0x6E432 | fuel pump mode | u8 | Fuel pump control mode |
| 0x6E435 | fuel pump parameter | u8 | Fuel pump secondary param |

### `calc_adaptive_fuel_trim.c` (STFT/LTFT)
| Address | Access | Notes |
|---------|--------|-------|
| 0x6A868 / 0x6A87C | EEPROM u8[] | Adaptive trim tables A/B |
| 0x72C5C | u16 | 375 RPM enable threshold |
| 0x72C60 | float | 1500.0 (temp low) |
| 0x72C64 | float | ~0.009766 (1/1024) integral gain |
| 0x72C68 | float | 0.6 prop gain |
| 0x72C6C | float | -2.8 (trim limit neg) |
| 0x72C70 | float | 0.7 (trim limit pos) |

### `calc_fuel_pump_duty_trim.c`
| Address | Access | Notes |
|---------|--------|-------|
| 0x6E430 | u8 | Mode selector (0/1/2) |
| 0x6E438 | float | Safe mode front duty |
| 0x6E43C | float | Safe mode rear duty |

### `calc_ignition_all_rotors_13C2C.c` (per-rotor ignition + knock retard)
| Address | Access | Notes |
|---------|--------|-------|
| 0x6B68C | descriptor | Generic 1D ignition correction |
| 0x7987C | float | 0.0f |
| 0x79880 / 0x79888 | float | 1.0f (correction defaults) |
| 0x79890 | float | 2.5° max retard |
| 0x7983B | u8 | RPM threshold |

### `baro_sensor_value.c`
| Address | Access | Notes |
|---------|--------|-------|
| 0x7978C | float | Sensor gain |
| 0x79790 | float | Offset (Table 2D - 204_, Secondary Fuel Blend Transition RPM) |
| 0x6D46C / 0x6D46E | u16 | Min/Max ADC threshold, both 0x0505 = 1285 |

### `knockRelatedInit.c` / `getKnockSensorADC.c`
| Address | Access | Notes |
|---------|--------|-------|
| 0x78EE0 | float | Filter gain 10.0 |
| 0x78EE4 | float | Threshold 1: 200.0 (low-RPM knee) |
| 0x78EE8 | float | Threshold 2: 2000.0 (high-RPM knee) |
| 0x78EEC | float | IIR coeff 0.004 |
| 0x78EA0 / 0x78EA4 | float | RPM limit 10000.0 |
| 0x7A164 | u8[2] | Per-rotor sensor IDs |

### `sensor_check_float_bounds_adjust.c`
| Address | Access | Notes |
|---------|--------|-------|
| 0x6CF88 | u8 | Counter init |
| 0x6CF8C | float | Comparison threshold |

### `calc_decel_fuel_cut_445AA.c`
| Address | Access | Notes |
|---------|--------|-------|
| 0x7B3DC | u8 | 0x01 = fuel cut enabled |
| 0x7B3DD | u8 | 0x00 = fuel cut disabled |
| 0x7B418 | float | 0.01 (throttle closed) |
| 0x7B41C | float | 50.0 (RPM) |

### `limitKnockRetardMax_ConditionalRPM.c`
| Address | Access | Notes |
|---------|--------|-------|
| 0x693CC | 2D descriptor | Retard limit A (RPM vs load) |
| 0x693B8 | 2D descriptor | Retard limit B (RPM vs load) |
| 0x78544 | u8[] | Intermediate threshold |
| 0x78584 | u8[] | Gain/scaling factor |

### Files Referencing Unmatched ROM Addresses (scalars/small tables)
| File | Addresses |
|------|-----------|
| `2DLookup.c` | 0x677E8, 0x67870 |
| `3dLookup.c` | 0x67898, 0x68114 |
| `getFaultStatus.c` | 0x6743C, 0x67494, 0x7E4DC |
| `can_uds_subsystem.c` | 0x66A14, 0x697E8 |
| `obd_pid_handlers.c` | 0x66258, 0x670B4 |
| `dtc_data_read_60F58.c` | 0x60F58–0x60F6E (12 addrs) |
| `knock_sensor_adc_read.c` | 0x7A178, 0x7A17A, 0x7A1A4, 0x7A1D0 |
| `knockSensorADCFault.c` | 0x6D47C (X), 0x6D47E |
| `knock_sensor_adc_fault.c` | 0x6CF7C, 0x6CF7E |

## Tables Grouped by Subsystem

### Sensor Scaling & Calibration
Baro: 0x6CF6C/0x6CF6E u16 Max/Min ADC (HIGH) · 0x7A930/0x7A934 float Min/Max V · 0x7A9C0 float Slope · 0x7A9BC float Offset (all used by `baro_sensor_value.c`).
MAF: 0x6FBD8 **MAF Scaling** 1D f32[48] (V 0–5), desc 0x69E4C (J-line) / 0x6A0E4 (60E1D400) · 0x7A65C MAF Related 1D u16[8], desc 0x6B6F4.
Temp: 0x6F96C **CLT Scaling** 1D f32[32] · 0x6FFE8 **IAT Scaling** 1D f32[16].
Lambda/O₂: 0x6FD74 **Lambda Scaling** 1D f32[11] · 0x7AF74 Unknown Lambda Input 1D u8[8].

Signal conditioning (Tables 60–69, **MEDIUM**): 0x70084 2D-60 MAF filter freq → `calc_throttle_position_filter` · 0x700B0 2D-61 IAT filtering → `calc_intake_air_temp_compensation` · 0x700E0 2D-62 CLT filtering → `calc_exhaust_gas_temp_trim` · 0x70110 2D-63 load signal → `air_charge_calc` · 0x70230 2D-64 baro adj → `MAP_sensor_scaling` · 0x70264 2D-65 O2 switch → `air_fuel_ratio_feedback_calc` · 0x702A4 2D-67 TPS deadband → `calc_throttle_position_filter` · 0x703BC 2D-69 load smoothing → `engine_load_estimator`.

### Fuel Injection — Base
Main 3D (RPM×Load, u8, scale 0.003906): 0x7238C Fuelling 10 (safe, 21×19, desc 0x6A4D8) · 0x72684 Fuelling 14 (safe, 21×19, 0x6A548) · 0x72964 Fuelling 16 (normal, 21×19, 0x6A580) · 0x72864 Fuelling 15 (normal, 21×19, 0x6A564).
1D corrections: 0x71CD0 Safe (9, 0x6A2E8) · 0x71D00 Fuelling 1 (7, 0x6A310) · 0x71D2C Fuelling 2 safe (9, 0x6A324) · 0x71D5C Fuelling 3 (9, 0x6A338) · 0x71D84 Fuelling 4 (7, 0x6A34C) · 0x71DD4/0x71E30/0x71E8C Fuelling 5/6/7 (18, 0x6A360/0x6A374/0x6A388) · 0x72084 Fuelling 8 (7, 0x6A43C). 2D corrections: 0x7228C Fuelling 9 safe (12×8, 0x6A4BC) · 0x72584 Fuelling 13 safe (12×8, 0x6A52C).

### Fuel Injection — Enrichment & Trims
WOT/Cold: 0x72DD0 2D-110 **WOT Enrichment Threshold** HIGH → `calc_wot_fuel_enrichment` (0x14220) · 0x72E40 2D-111 **Cold Start Enrichment Threshold** HIGH → `calc_cold_start_fuel_enrichment` (0x142E8).
Transient (MEDIUM): 0x73DB4/0x73DD0/0x73DEC 2D-128/129/130 Cold/Warm/Hot → `calc_accel_fuel_enrichment`.
O₂/Lambda: 0x717BC 2D-79 **Lambda Integration Time Constant** HIGH → `calc_lambda_integration_time` (0x1418C) · 0x717F4 2D-80 parameter (MEDIUM).
Adaptive trims: 0x6A868 / 0x6A87C (EEPRom A/B) → `calc_adaptive_fuel_trim.c`, `o2_lambda_subsystem.c`.

### Injector Control
Sizing: 0x783A0 Primary · 0x783A8 Secondary · 0x783B0 Secondary #2 (scalars).
Latency: 0x780F4 Primary 17×9 (0x6AF54) · 0x77F58 Secondary 17×9 (0x6AF38).
Deadtime (MEDIUM): 0x78318 2D-175 Primary / 0x78364 2D-176 Secondary → `secondary_fuel_trimmer` (0x16668) · 0x7850C 2D-350 PW primary control / 0x7853C 2D-179 secondary min PW → `dual_channel_fuel_computation` (0x14BCC).
Secondary fuel (Tables 204–209, MEDIUM unless noted): 0x79790 2D-204 blend transition RPM → `rotary_fuel_enrichment_controller` · 0x797C8 2D-205 blend rate → `rotary_fuel_enrichment_controller` · 0x79814 2D-206 rotor A/B PW limiter **HIGH** → `calc_fuel_injection_all_rotors` (0x13D3C) · 0x798B8 2D-207 enable temp / 0x798D0 2D-208 disable temp / 0x798E8 2D-209 mode selector → `secondary_chamber_activation` (0x1695A).
Fuel pressure limit: 0x78DF8 2D-197 high RPM / 0x78DC0 2D-196 low RPM → `secondary_fuel_trimmer`.
Injection angle: 0x7B2B8 **Injection Angle** 18×8 u16 (0x6BB84) · 0x7AF48 injector angle AFR input 9 u8 (0x6BABC).

### Ignition Timing
Main (20×18, RPM×Load): 0x6DB48 **Ignition Leading Base** (0x69860) · 0x6D748 Leading 1 (0x69828) · 0x6DDD4 Ignition/Trailing (0x69898) · 0x6E1D4 Ignition 1 trailing (0x698D0) · 0x6D948 Leading Base safe (0x69844) · 0x6DFD4 Ignition 0 safe (0x698B4) · 0x6EEEC **Trailing B** (0x69EF8) · 0x6F0EC **Trailing A** (0x69F14) · 0x6F2EC **Min Split** (0x69F30).
Small: 0x6D59C idle base 6 (0x697BC) · 0x6D5C8 temp corr 9 (0x697D0) · 0x6D5EC Ign 2 (0x697E4) · 0x6D618 Leading 0 (0x697F8) · 0x6D668 Timing Lead 10×7 (0x6980C) · 0x6DCF4 Leading 4 10×7 (0x6987C) · 0x6E358 Leading 5 4×3 (0x698EC) · 0x6E3A4 Minimum 4×3 (0x69900) · 0x6F4CC Ign 3 19×11 (0x69CB4) · 0x6F78C Ign 4 12 (0x69CC8) · 0x6F7D0 Ign 6 12 (0x69CF0) · 0x7CB20 **Dwell Time_** 9×9 (0x6BF28).
Knock corrections (Tables 10–15): 0x6E4BC 2D-10 Light **HIGH** / 0x6E4E0 2D-11 Medium **HIGH** / 0x6E504 2D-12 Heavy **HIGH** → `knock_margin_limiter_primary` (0x19000) · 0x6E528 2D-13 detection sensitivity **HIGH** → `write_cyl_A_knock_flag` (0x128FE) · 0x6E54C 2D-14 / 0x6E570 2D-15 retard (MEDIUM).

### Knock Control
0x78EE0/0x78EE4/0x78EE8/0x78EEC floats, 0x7A164 u8[2] — see `knockRelatedInit.c`/`getKnockSensorADC.c`.
Scaling: 0x7A318 Voltage→Magnitude (f32) · 0x7A38C Knock Related 1 1D 14 f32 (0x6B650) · 0x7A3E0 Knock Related 2 1D 14 f32 (0x6B65C) · 0x7A450 Knock Rel #4 2D 6×11 (0x6B680) · 0x7A4D8 Knock Rel #0 2D 6×11 (0x6B69C).

### Idle Control
Targets: 0x6E880 Idle Target 7 (0x69A54) · 0x6E8C0 Idle Target 0 12 (0x69A68) · 0x6E908 Idle Target 1 12 (0x69A7C) · 0x6E950 Idle Target 2 12 (0x69A90) · 0x6E998 Idle Target 3 12 (0x69AA4) · 0x6E9CC Idle Target 4 7 (0x69AB8) · 0x6E9F8 Idle Target 5 7 (0x69ACC) · 0x6EA24 Idle Target 6 7 (0x69AE0) · 0x6EA50 Idle Target 7 7 (0x69AF4). Related: 0x6D1E0 Idle Related 1D 16 (0x69724).

### Throttle & Pedal
Accel→TPS: 0x74250 #1 / 0x745E0 #2 / 0x74970 #3 / 0x74D00 #4 (all 21×18, descs 0x6A9C8/0x6A9E4/0x6AA00/0x6AA1C). Torque→pos: 0x73090 Torque→Accel 26×19 (0x6A6D4) · 0x734F4 TPS→Torque 14×20 (0x6A6F0). Max throttle: 0x73F6C scalar.

### Torque & Load
0x786E8 **Engine Load Compensation** 18×20 (0x6B0B0) · 0x7C1B4 Load Limit A 1D 12 f32 (0x6BD88) · 0x7C214 Load Limit B 1D 12 f32 (0x6BD94) · 0x7C354 Load Limit C 1D 10 u16 (0x6BDA0) · 0x77C48 **Estimated Manifold Pressure** 17×20 (0x6AF1C).
Load limiter (Tables 144–147, MEDIUM): 0x75054 2D-144 MAP requested / 0x750B0 2D-145 smoothing / 0x750F8 2D-146 max / 0x75130 2D-147 idle multiplier → `load_bias_table_interpreter` (0x15254).

### VDI / Oil Metering / Rev Limit
VDI: 0x78CC0 Aux Valve Close · 0x7A5A4 VDI Open (scalars).
Oil: 0x790C4 **Oil Metering By Load** 2D 19×17 f32 (0x6B264) · 0x79264 **By Throttle** 2D 19×4 f32 (0x6B278).
Rev limit: 0x6D544 **Cold Rev Limit** u16 · 0x6D53C Cold Rev Limit Threshold u16 · 0x6D54C **Rev Limit** u16.

### Flex Fuel (all f32 unless noted; 3D u8 for timing/ethanol)
Timing Ethanol Adder Leading/Trailing (3D u8 20×18) · Timing Multiplier (2D 12) · Stoich Fuel Ratio (2D 12) · Ethanol Sample Threshold Engine Speed/Load (1D f32 1) · Cranking Fuel Multiplier (3D u8 12×13).

### Generic / Unidentified Tables (address range, dims, descriptor)

**Tables 0–9 (0x6CFE4–0x6D4D4, Ignition):** 0x6CFE4 2D-0 16 u8 (0x6969C) · 0x6D034 2D-1 16 u8 (0x696B0) · 0x6D084 2D-2 16 u8 (0x696C4) · 0x6D114 2D-3 10 u8 (0x696D8) · 0x6D138 2D-4 6 u8 (0x696EC) · 0x6D2AC 3D-0 16×6 u8 (0x6974C) · 0x6D364 3D-1 16×6 u8 (0x69768) · 0x6D41C 3D-2 16×6 u8 (0x69784) · 0x6D4D4 3D-3 16×6 u8 (0x697A0).

**Tables 16–24 (0x6E5BC–0x6E84C):** 0x6E5BC 2D-16 16 u16 (0x699A0) · 0x6E6F0 2D-17 7 u8 (0x699B4) · 0x6E714 2D-18 7 u8 (0x699C8) · 0x6E738 2D-19 7 u8 (0x699DC) · 0x6E75C 2D-20 7 u8 (0x699F0) · 0x6E780 2D-21 7 u8 (0x69A04) · 0x6E7A4 2D-22 7 u8 (0x69A18) · 0x6E7F8 2D-23 19 u16 (0x69A2C) · 0x6E84C 2D-24 11 u16 (0x69A40).

**Tables 34–46 (0x6EAF8–0x6EDF4, Fuel Trim):** 0x6EAF8 2D-34 9 u8 (0x69B24) · 0x6EB28 2D-35 9 u8 (0x69B38) · 0x6EB58 2D-36 9 u8 (0x69B4C) · 0x6EB88 2D-37 9 u8 (0x69B60) · 0x6EBA8 2D-38 5 u8 (0x69B74) · 0x6EBC8 2D-39 6 u8 (0x69B88) · 0x6EC08 2D-40 14 u8 (0x69B9C) · 0x6EC44 2D-41 4 u16 (0x69BB0) · 0x6EC70 2D-42 9 u16 (0x69BC4) · 0x6ECA8 2D-43 9 u16 (0x69BD8) · 0x6ECE0 2D-44 9 u16 (0x69BEC) · 0x6ED08 2D-45 5 u16 (0x69C00) · 0x6ED3C 2D-46 9 u8 (0x69C14) · 0x6ED78 3D-13 9×3 u8 (0x69C28) · 0x6EDF4 3D-14 12×8 u8 (0x69C44).

**Tables 57–59 (0x6F878–0x6FEE4):** 0x6F878 2D-57 12 u16 (0x69E00) · 0x6FAB0 2D-58 5 u8 (0x69E20) · 0x6FEE4 2D-59 11 u16 (0x69EA0).

**Tables 70–102 (0x715BC–0x7C9B4):** spread across ROM regions; likely fuel corrections, temperature comps, modifiers. See full 499-entry catalog in `docs/subsystems/MAPS.md`.

### Check DataType (f32 intermediate) Tables
105 tables named "Table 2D - NNN Check DataType" — **f32 intermediate calculation results** stored read-only in ROM (pre-computed), not tunable tables.

0x6D158 2D-288 (0x69700) · 0x6D178 2D-289 (0x6970C) · 0x6D198 2D-290 (0x69718) · 0x6FACC 2D-292 (0x69E34) · 0x6FAF4 2D-293 (0x69E40) · 0x6FCF8 2D-295 (0x69E58) · 0x6FD20 2D-296 (0x69E64) · 0x6FDE0 2D-299 (0x69E88) · 0x6FE60 2D-300 (0x69E94). *(Full 105: `cal_tables.csv` filtered by "Check DataType")*

## RomRaider Definition Cross-Reference

RomRaider XML (`refs/rx8defs/RomRaider/rx8_defs.xml`, **not shipped**; ~20,262 `<table>` tags):

| Category | Address Range | Count | Notes |
|----------|--------------|-------|-------|
| Sensors | 0x6CF6C–0x6FFE8 | ~20 | Baro, MAF, CLT, IAT, Lambda scaling |
| Fuel Injection | 0x71CD0–0x72964 | ~30 | Main fuel tables, safe modes |
| Flex Fuel | varies | ~8 | Ethanol tables |
| Ignition | 0x6D59C–0x6F4CC | ~35 | Leading/trailing, dwell |
| Unknown 2D | 0x6CFE4–0x7D92C | ~334 | Numbered, unidentified |
| Unknown 3D | 0x6D2AC–0x7C9B4 | ~80 | Numbered 3D |
| Outputs | varies | ~8 | Fan thresholds |
| Cruise Control | varies | ~2 | Speed thresholds |
| Gear Detection | varies | ~6 | Gear ratio thresholds |
| Immobilizer | varies | ~2 | Bypass switches |

`cal_tables.csv` extracts the **value pointer addresses** of the stored data.

## Analysis Report Identifications (50 New Tables)

Analysis report `ANALYSIS_REPORT_50_NEW_TABLES.md` (private storage) identified 50 unnamed tables.

### HIGH Confidence (15)
| Address | Table | Identification | Function |
|---------|-------|---------------|----------|
| 0x72DD0 | 2D-110 | WOT Enrichment Threshold | `calc_wot_fuel_enrichment` (0x14220) |
| 0x72E40 | 2D-111 | Cold Start Enrichment Threshold | `calc_cold_start_fuel_enrichment` (0x142E8) |
| 0x717BC | 2D-79 | Lambda Integration Time Constant | `calc_lambda_integration_time` (0x1418C) |
| 0x79814 | 2D-206 | Rotor A/B Fuel Pulse Width Limiter | `calc_fuel_injection_all_rotors` (0x13D3C) |
| 0x6E4BC | 2D-10 | Knock Correction - Light | `knock_margin_limiter_primary` (0x19000) |
| 0x6E4E0 | 2D-11 | Knock Correction - Medium | `knock_margin_limiter_primary` (0x19000) |
| 0x6E504 | 2D-12 | Knock Correction - Heavy | `knock_margin_limiter_primary` (0x19000) |
| 0x6E528 | 2D-13 | Knock Detection Sensitivity | `write_cyl_A_knock_flag` (0x128FE) |
| 0x6D138 | 2D-4 | Ignition Idle Timing | `calc_ignition_advance_modifier` (0x13A0E) |
| 0x783A0 | — | Primary Injector Size | fuel calc |
| 0x783A8 | — | Secondary Injector Size | fuel calc |
| 0x73F6C | — | Maximum Throttle Angle | throttle |
| 0x78CC0 | — | Aux Valve Close | VDI |
| 0x7A5A4 | — | VDI Open | VDI |
| 0x6D54C | — | Rev Limit | rev limit |

### MEDIUM Confidence (35)
**Fuel & enrichment (12):** 0x73DB4 2D-128 Cold transient · 0x73DD0 2D-129 Warm · 0x73DEC 2D-130 Hot · 0x78318 2D-175 deadtime primary · 0x78364 2D-176 deadtime secondary · 0x7850C 2D-350 PW primary control · 0x7853C 2D-179 secondary min PW · 0x78DF8 2D-197 fuel pressure high RPM · 0x78DC0 2D-196 fuel pressure low RPM · 0x79790 2D-204 blend transition RPM · 0x797C8 2D-205 blend rate · 0x798B8 2D-207 enable temp.
**Sensor & conditioning (8):** 0x70084 2D-60 MAF filter · 0x700B0 2D-61 IAT filter · 0x700E0 2D-62 CLT filter · 0x70110 2D-63 load signal · 0x70230 2D-64 baro adj · 0x70264 2D-65 O2 switch · 0x702A4 2D-67 TPS deadband · 0x703BC 2D-69 load smoothing.
**Load & boost (5):** 0x75054 2D-144 MAP requested · 0x750B0 2D-145 smoothing · 0x750F8 2D-146 max · 0x75130 2D-147 idle multiplier · 0x798D0 2D-208 disable temp.
**Other (10):** 0x798E8 2D-209 mode selector · 0x79920 2D-210 rotor A/B fuel trim · 0x7995C 2D-211 rotor A/B trim 2 · 0x799A0 2D-212 decel fuel cutoff rate · 0x799B8 2D-213 decel cutoff recovery · 0x799F8 2D-214 fuel pressure regulator duty low · 0x79A1C 2D-215 duty high · 0x79A54 3D-76 regulator 3D · 0x79AD4 3D-77 comp 3D · 0x79B48 3D-78 comp 3D 2.

## Statistics & Coverage

| Metric | Count |
|--------|-------|
| Calibration tables in cal_tables.csv | 1,209 |
| Map descriptors (mapscan.py) | 499 (119 2D + 380 1D) |
| Named/identified tables | ~109 |
| Generic numbered (Table 2D/3D - N) | ~334 |
| Check DataType (f32 intermediate) | ~105 |
| Axis-only entries (X, Y labels) | ~660 |
| C files w/ cal table refs | 19 of 55 |
| Direct C → table name matches | 3 (MAF Scaling, 2D-110, 2D-111) |
| Analysis identifications | 50 (15 HIGH, 35 MEDIUM) |
| RomRaider categories | 12+ |

Coverage by subsystem: Sensor ~17 (12 id'd) · Fuel base ~28 (18) · Fuel enrichment ~20 (12) · Injector ~13 (10) · Ignition ~38 (33) · Knock ~10 (7) · Idle ~12 (10) · Throttle/pedal ~9 (7) · Load mgmt ~13 (8) · VDI 2 · Oil 2 · Rev limit 3 · Generic 334 · Check DataType 105 · Axis ~660. **Total ~109 named / ~1,100 unidentified / ~1,209.**

## Appendices

### A. Source Files
- `symbols/cal_tables.csv` — all table value pointers + names
- `tools/mapscan.py` — ROM descriptor scanner (499 descriptors)
- `c/2DLookup.c`, `c/3dLookup.c` — verified lookup functions
- `c/o2_lambda_subsystem.c`, `c/maf_sensor_value.c`, `c/calc_adaptive_fuel_trim.c`, `c/calc_fuel_pump_duty_trim.c`, `c/calc_ignition_all_rotors_13C2C.c`, `c/baro_sensor_value.c`, `c/knockRelatedInit.c`, `c/getKnockSensorADC.c`, `c/sensor_check_float_bounds_adjust.c`, `c/calc_decel_fuel_cut_445AA.c`, `c/limitKnockRetardMax_ConditionalRPM.c`
- Private storage: `FINAL_ANALYSIS_SUMMARY.txt`, `ANALYSIS_REPORT_50_NEW_TABLES.md`, `RX8_Additional_Tables_Identified.txt`
- `docs/subsystems/MAPS.md` — full 499-descriptor catalog
- `refs/rx8defs/RomRaider/rx8_defs.xml` — RomRaider (not shipped; naming only)

### B. Future Work
- 286 unidentified tables → function cross-referencing.
- 105 Check DataType: validate intermediate vs tunable.
- Match axis pointers to parent tables; add remaining C refs.
- Other ROM variants: N3J6EB, N3M5E, N3YLEE.

*Generated from `cal_tables.csv`, `mapscan.py`, verified C sources in `c/`, and analysis reports (private storage).*
