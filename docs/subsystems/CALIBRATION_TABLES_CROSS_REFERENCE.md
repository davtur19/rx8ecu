# RX-8 ECU Calibration Table Cross-Reference Document

> **WARNING:** the descriptor addresses below reference a **private ROM variant**
> (J-line shift +0x298); on the shipped `60E1D400.bin` apply a **+0x298** shift
> (verified: Ignition Leading Base @0x69AF8, MAF @0x6A0E4, deadtime @0x6B264).
> Always verify with `tools/mapscan.py`.

> **ROM:** N3J1EL (60E1D400)  
> **ECU:** Mazda RX-8 S1 (2004–2008), Renesis dual-rotor 1.3L  
> **CPU:** Renesas SH7055 (SH-2E)  
> **ROM Size:** 512 KB (file offset 0x00000–0x7FFFF)  
> **Generated:** July 2026  
> **Sources:** `cal_tables.csv`, `mapscan.py`, verified C functions in `c/`, IDA Pro analysis reports (moved to private storage), RomRaider `rx8_defs.xml` (not redistributed; naming here follows its conventions)

---

## Table of Contents

1. [Document Overview](#1-document-overview)
2. [Architecture of Calibration Table Lookups](#2-architecture-of-calibration-table-lookups)
3. [Descriptor-to-Value Mapping](#3-descriptor-to-value-mapping)
4. [C Function Cross-Reference](#4-c-function-cross-reference)
5. [Tables Grouped by Subsystem](#5-tables-grouped-by-subsystem)
   - [5.1 Sensor Scaling & Calibration](#51-sensor-scaling--calibration)
   - [5.2 Fuel Injection - Base Fueling](#52-fuel-injection---base-fueling)
   - [5.3 Fuel Injection - Enrichment & Trims](#53-fuel-injection---enrichment--trims)
   - [5.4 Fuel Injection - Injector Control](#54-fuel-injection---injector-control)
   - [5.5 Ignition Timing](#55-ignition-timing)
   - [5.6 Knock Control](#56-knock-control)
   - [5.7 Idle Control](#57-idle-control)
   - [5.8 Throttle & Pedal Control](#58-throttle--pedal-control)
   - [5.9 Torque & Load Management](#59-torque--load-management)
   - [5.10 VDI Control](#510-vdi-control)
   - [5.11 Oil Metering](#511-oil-metering)
   - [5.12 Rev Limit](#512-rev-limit)
   - [5.13 Flex Fuel](#513-flex-fuel)
   - [5.14 Generic / Unidentified Tables](#514-generic--unidentified-tables)
   - [5.15 Check DataType (f32 intermediate) Tables](#515-check-datatype-f32-intermediate-tables)
6. [RomRaider Definition Cross-Reference](#6-romraider-definition-cross-reference)
7. [Analysis Report Cross-Reference (50 New Tables)](#7-analysis-report-cross-reference-50-new-tables)
8. [Statistics & Coverage](#8-statistics--coverage)
9. [Appendices](#9-appendices)

---

## 1. Document Overview

This document maps every identified calibration table in the RX-8 ECU firmware to:

- The **functions** that consume the table data (from verified C source in `c/`)
- The **map descriptor** that defines the lookup (from `mapscan.py`)
- The **RomRaider definition** name and category (naming follows `rx8_defs.xml` conventions; original XML not redistributed)
- The **analysis report** identification (from analysis reports moved to private storage)

The firmware uses two table-lookup functions:

| Function | ROM Address | Purpose | C Source |
|----------|-------------|---------|----------|
| `TwoDLookup` | 0x2068 | 1D table lookup (axis + value array) | `c/2DLookup.c` |
| `ThreeDLookup` | 0x20DC | 2D/3D table lookup (X axis + Y axis + grid) | `c/3dLookup.c` |

Both read a **descriptor structure** from ROM that contains pointers to axis arrays and value arrays. The descriptor format:

```
Map1D (20 bytes): u16 count; u8 type; f32* axis@4; void* values@8; f32 scale@12; f32 offset@16
Map2D (28 bytes): u16 count_x; u16 count_y; f32* axis_x@4; f32* axis_y@8; void* values@12;
                  u8 type@16; f32 scale@20; f32 offset@24
```

**Type codes:** 0=f32 cells (no scale/offset) | 4=u8 | 8=u16 | 12=s8 | 16=s16

Physical value = `raw * scale + offset` (for integer types); f32 values are stored as-is.

---

## 2. Architecture of Calibration Table Lookups

```
┌──────────────────────────────────────────────────────────────────────┐
│  ROM Code (verified C functions)                                     │
│  e.g. calc_adaptive_fuel_trim, o2_lambda_subsystem, ...              │
│                                                                      │
│  Loads descriptor address into R4, calls TwoDLookup/ThreeDLookup     │
└─────────────────────┬────────────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Descriptor Struct (ROM, file offset 0x6969C–0x6BFC0)                │
│                                                                      │
│  Contains: count, type, axis_ptr, values_ptr, scale, offset          │
│  499 descriptors found by mapscan.py (119 × 2D, 380 × 1D)            │
└─────────────────────┬────────────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Value Arrays & Axis Arrays (ROM, file offset 0x6CFA4–0x7D92C)      │
│                                                                      │
│  These are the addresses listed in cal_tables.csv / RomRaider defs    │
│  ~1,209 named entries (value pointers + axis pointers)                │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Descriptor-to-Value Mapping

The 499 descriptors found by `mapscan.py` form the bridge between ROM code and calibration values. The descriptor address is what code passes to `TwoDLookup`/`ThreeDLookup`.

Below is the complete descriptor catalog, grouped by functional region:

### 3.1 Ignition System Descriptors (0x697BC–0x69C98)

| Desc Addr | Kind | Dims | Type | Scale | Offset | Values Addr | Cal Table Name |
|-----------|------|------|------|-------|--------|-------------|----------------|
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
| 0x69BF28 | 2D | 9×9 | f32 | — | — | 0x7CB20 | Ignition Dwell Time_ |

> **Nota (verificata):** Descriptori verificati via emulatore da `calc_spark_lead_trail_split_0x19220` (0 mismatch/500k): TrailingB=desc 0x69EF8, TrailingA=desc 0x69F14, MinSplit=desc 0x69F30; i desc riferiti nel passato 0x69C60/0x69C7C/0x69C98 non sono usati da 0x19220 (verificare eventuali altri riferimenti).

### 3.2 Fuel System Descriptors (0x69E2C–0x6A580)

| Desc Addr | Kind | Dims | Type | Scale | Offset | Values Addr | Cal Table Name |
|-----------|------|------|------|-------|--------|-------------|----------------|
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

### 3.3 Sensor Scaling Descriptors (0x69E14–0x69EB4)

| Desc Addr | Kind | Dims | Type | Scale | Offset | Values Addr | Cal Table Name |
|-----------|------|------|------|-------|--------|-------------|----------------|
| 0x69E14 | 1D | 32 | f32 | — | — | 0x6F96C | CLT Sensor Scaling |
| 0x69E4C | 1D | 48 | f32 | — | — | 0x6FBD8 | MAF Scaling (J-line variant descriptor; in 60E1D400 this descriptor is at 0x6A0E4 — see `SENSOR_PIPELINE.md`) |
| 0x69E58 | 1D | 8 | f32 | — | — | 0x6FCF8 | Table 2D - 295 Check DataType |
| 0x69E64 | 1D | 8 | f32 | — | — | 0x6FD20 | Table 2D - 296 Check DataType |
| 0x69E70 | 1D | 4 | f32 | — | — | 0x6FD38 | Injector Barometric Pressure Comp |
| 0x69E7C | 1D | 11 | f32 | — | — | 0x6FD74 | Lambda Sensor Scaling |
| 0x69EB4 | 1D | 16 | f32 | — | — | 0x6FFE8 | IAT Sensor Scaling |

### 3.4 Sensor Conditioning Descriptors (0x69EC0–0x69F98)

| Desc Addr | Kind | Dims | Type | Scale | Offset | Values Addr | Cal Table Name |
|-----------|------|------|------|-------|--------|-------------|----------------|
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

### 3.5 Throttle & Pedal Descriptors (0x6A9C8–0x6AA1C)

| Desc Addr | Kind | Dims | Type | Scale | Offset | Values Addr | Cal Table Name |
|-----------|------|------|------|-------|--------|-------------|----------------|
| 0x6A9C8 | 2D | 21×18 | u16 | 0.003052 | 0 | 0x74250 | Accel Pedal to Throttle Position #1 |
| 0x6A9E4 | 2D | 21×18 | u16 | 0.003052 | 0 | 0x745E0 | Accel Pedal to Throttle Position #2 |
| 0x6AA00 | 2D | 21×18 | u16 | 0.003052 | 0 | 0x74970 | Accel Pedal to Throttle Position #3 |
| 0x6AA1C | 2D | 21×18 | u16 | 0.003052 | 0 | 0x74D00 | Accel Pedal to Throttle Position #4 |
| 0x6A6D4 | 2D | 26×19 | u16 | 0.003052 | 0 | 0x73090 | Torque To Accel Position |
| 0x6A6F0 | 2D | 14×20 | u16 | 0.007812 | -256 | 0x734F4 | Throttle Position To Torque |

### 3.6 Knock Control Descriptors (0x6B650–0x6B69C)

| Desc Addr | Kind | Dims | Type | Scale | Offset | Values Addr | Cal Table Name |
|-----------|------|------|------|-------|--------|-------------|----------------|
| 0x6B650 | 1D | 14 | f32 | — | — | 0x7A38C | Knock Related 1 |
| 0x6B65C | 1D | 14 | f32 | — | — | 0x7A3E0 | Knock Related 2 |
| 0x6B680 | 2D | 6×11 | u8 | 0.05 | 0 | 0x7A450 | Knock Rel #4 |
| 0x6B69C | 2D | 6×11 | u8 | 0.05 | 0 | 0x7A4D8 | Knock Rel #0 |

### 3.7 Oil Metering Descriptors (0x6B264–0x6B28C)

| Desc Addr | Kind | Dims | Type | Scale | Offset | Values Addr | Cal Table Name |
|-----------|------|------|------|-------|--------|-------------|----------------|
| 0x6B264 | 2D | 19×17 | f32 | — | — | 0x790C4 | Oil Metering By Load |
| 0x6B278 | 2D | 19×4 | f32 | — | — | 0x79264 | Oil Metering By Throttle |

### 3.8 Injector Descriptors (0x6AF38–0x6AF54, 0x6AFCC–0x6AFE0)

| Desc Addr | Kind | Dims | Type | Scale | Offset | Values Addr | Cal Table Name |
|-----------|------|------|------|-------|--------|-------------|----------------|
| 0x6AF38 | 2D | 17×9 | u16 | 1 | 0 | 0x77F58 | Injector Latency Secondary |
| 0x6AF54 | 2D | 17×9 | u16 | 1 | 0 | 0x780F4 | Injector Latency Primary |
| 0x6AFCC | 1D | 12 | u16 | 5 | 0 | 0x78318 | Table 2D - 175_ (Injector deadtime primary) |
| 0x6AFE0 | 1D | 13 | u16 | 5 | 0 | 0x78364 | Table 2D - 176_ (Injector deadtime secondary) |

### 3.9 Load Management Descriptors (0x6BD88–0x6BDA0)

| Desc Addr | Kind | Dims | Type | Scale | Offset | Values Addr | Cal Table Name |
|-----------|------|------|------|-------|--------|-------------|----------------|
| 0x6BD88 | 1D | 12 | f32 | — | — | 0x7C1B4 | Load Limit A |
| 0x6BD94 | 1D | 12 | f32 | — | — | 0x7C214 | Load Limit B |
| 0x6BDA0 | 1D | 10 | u16 | 0.001 | 0 | 0x7C354 | Load Limit C |
| 0x6B0B0 | 2D | 18×20 | u16 | 1.526e-05 | 0.75 | 0x786E8 | Engine Load Compensation |
| 0x6AF1C | 2D | 17×20 | u16 | 0.003906 | 0 | 0x77C48 | Estimated Manifold Pressure |

> **Full 499-entry descriptor catalog** is available in `tools/mapscan.py` output or `docs/subsystems/MAPS.md`.

---

## 4. C Function Cross-Reference

The following verified C source files (`c/*.c`) reference calibration tables directly. Each entry shows which tables the function reads and how they are used.

### 4.1 `maf_sensor_value.c`
Reads the MAF scaling curve to convert raw MAF sensor frequency to air mass flow.

| Address | Cal Table Name | Access | Notes |
|---------|---------------|--------|-------|
| 0x6FBD8 | **MAF Scaling** | 1D f32[48] thru desc@0x69E4C (J-line variant) | Voltage→g/rev lookup |

### 4.2 `o2_lambda_subsystem.c`
Front and rear O₂ sensor voltage→index mapping, plus adaptive trim tables.

| Address | Cal Table Name | Access | Notes |
|---------|---------------|--------|-------|
| 0x72D78 | Y (front O₂ threshold array) | float[4] | Voltage breakpoints |
| 0x72DD0 | **Table 2D - 110_** (front O₂ lookup) | u8[9] | Voltage→trim-index mapping |
| 0x72DE8 | Y (rear O₂ threshold array) | float[4] | Voltage breakpoints |
| 0x72E40 | **Table 2D - 111_** (rear O₂ lookup) | u8[9] | Voltage→trim-index mapping |
| 0x6A868 | (adaptive trim table A) | EEPROM | Long-term fuel trim bank A |
| 0x6A87C | (adaptive trim table B) | EEPROM | Long-term fuel trim bank B |
| 0x6E432 | (fuel pump mode) | u8 | Fuel pump control mode byte |
| 0x6E435 | (fuel pump parameter) | u8 | Fuel pump secondary param |

**Identified as (from analysis report):**
- 0x72DD0 → **WOT Enrichment Threshold** (HIGH confidence)
- 0x72E40 → **Cold Start Enrichment Threshold** (HIGH confidence)

### 4.3 `calc_adaptive_fuel_trim.c`
Computes adaptive fuel trim corrections (STFT/LTFT).

| Address | Cal Table Name | Access | Notes |
|---------|---------------|--------|-------|
| 0x6A868 | (primary trim table) | EEPROM u8[] | Adaptive trim table A |
| 0x6A87C | (secondary trim table) | EEPROM u8[] | Adaptive trim table B |
| 0x72C5C | (RPM threshold) | u16 | 375 RPM enable threshold |
| 0x72C60 | (temp low threshold) | float | 1500.0 |
| 0x72C64 | (temp high threshold) | float | ~0.009766 (1/1024) integral gain |
| 0x72C68 | (error deadband) | float | 0.6 prop gain |
| 0x72C6C | (trim limit neg) | float | -2.8 |
| 0x72C70 | (trim limit pos) | float | 0.7 |

### 4.4 `calc_fuel_pump_duty_trim.c`
Controls fuel pump duty cycle.

| Address | Cal Table Name | Access | Notes |
|---------|---------------|--------|-------|
| 0x6E430 | (fuel pump mode byte) | u8 | Mode selector (0/1/2) |
| 0x6E438 | (front safe duty) | float | Safe mode front channel |
| 0x6E43C | (rear safe duty) | float | Safe mode rear channel |

### 4.5 `calc_ignition_all_rotors_13C2C.c`
Per-rotor ignition timing calculation with knock retard.

| Address | Cal Table Name | Access | Notes |
|---------|---------------|--------|-------|
| 0x6B68C | (1D lookup descriptor) | descriptor | Generic 1D table for ignition correction |
| 0x7987C | (zero constant) | float | 0.0f |
| 0x79880 | (correction default 1) | float | 1.0f |
| 0x79888 | (correction default 2) | float | 1.0f |
| 0x79890 | (max knock retard) | float | 2.5° max retard |
| 0x7983B | (RPM threshold byte) | u8 | RPM threshold for correction |

### 4.6 `baro_sensor_value.c`
Barometric pressure sensor linearization.

| Address | Cal Table Name | Access | Notes |
|---------|---------------|--------|-------|
| 0x7978C | (linearization gain) | float | Sensor gain |
| 0x79790 | **Table 2D - 204_** | float | Sensor offset (Secondary Fuel Blend Transition RPM) |
| 0x6D46C | (min ADC threshold) | u16 | 0x0505 = 1285 |
| 0x6D46E | (max ADC threshold) | u16 | 0x0505 = 1285 |

### 4.7 `knockRelatedInit.c`
Knock sensor initialization constants.

| Address | Cal Table Name | Access | Notes |
|---------|---------------|--------|-------|
| 0x78EE0 | (filter gain) | float | 10.0 |
| 0x78EE4 | (threshold 1) | float | 200.0 (low-RPM knee) |
| 0x78EE8 | (threshold 2) | float | 2000.0 (high-RPM knee) |
| 0x78EEC | (filter coeff) | float | 0.004 (IIR coefficient) |
| 0x7A164 | (sensor ID table) | u8[2] | Per-rotor sensor IDs |

### 4.8 `getKnockSensorADC.c`
Knock sensor ADC reading and filtering.

| Address | Cal Table Name | Access | Notes |
|---------|---------------|--------|-------|
| 0x78EE4 | (threshold 1) | float | 200.0 |
| 0x78EE8 | (threshold 2) | float | 2000.0 |
| 0x78EEC | (filter coeff) | float | 0.004 |
| 0x78EA0 | (RPM limit) | float | 10000.0 |
| 0x78EA4 | (RPM limit dup) | float | 10000.0 |

### 4.9 `sensor_check_float_bounds_adjust.c`
Generic sensor bounds checking with debounce.

| Address | Cal Table Name | Access | Notes |
|---------|---------------|--------|-------|
| 0x6CF88 | (fault init value) | u8 | Counter initialization |
| 0x6CF8C | (threshold) | float | Comparison threshold |

### 4.10 `calc_decel_fuel_cut_445AA.c`
Deceleration fuel cut logic.

| Address | Cal Table Name | Access | Notes |
|---------|---------------|--------|-------|
| 0x7B3DC | (feature enable) | u8 | 0x01 = fuel cut enabled |
| 0x7B3DD | (feature disable) | u8 | 0x00 = fuel cut disabled |
| 0x7B418 | (throttle closed threshold) | float | 0.01 |
| 0x7B41C | (RPM threshold) | float | 50.0 |

### 4.11 `limitKnockRetardMax_ConditionalRPM.c`
Conditional knock retard limiting by RPM.

| Address | Cal Table Name | Access | Notes |
|---------|---------------|--------|-------|
| 0x693CC | (retard limit table A) | 2D descriptor | RPM vs load |
| 0x693B8 | (retard limit table B) | 2D descriptor | RPM vs load |
| 0x78544 | (threshold table) | u8[] | Intermediate threshold |
| 0x78584 | (gain table) | u8[] | Gain/scaling factor |

### 4.12 Files Referencing ROM Addresses (Unmatched to Named Tables)

These C files reference ROM addresses that are not yet matched to named calibration tables. They likely represent scalar constants or small inline data tables.

| File | Addresses Referenced | Likely Purpose |
|------|-------------------|----------------|
| `2DLookup.c` | 0x677E8, 0x67870 | Descriptor templates or test data |
| `3dLookup.c` | 0x67898, 0x68114 | Descriptor templates or test data |
| `getFaultStatus.c` | 0x6743C, 0x67494, 0x7E4DC | Fault status table references |
| `can_uds_subsystem.c` | 0x66A14, 0x697E8 | CAN UDS constants |
| `obd_pid_handlers.c` | 0x66258, 0x670B4 | OBD PID constant tables |
| `dtc_data_read_60F58.c` | 0x60F58–0x60F6E | DTC data region (12 addresses) |
| `knock_sensor_adc_read.c` | 0x7A178, 0x7A17A, 0x7A1A4, 0x7A1D0 | Knock sensor constants |
| `knockSensorADCFault.c` | 0x6D47C (X), 0x6D47E | Knock sensor fault thresholds |
| `knock_sensor_adc_fault.c` | 0x6CF7C, 0x6CF7E | Knock sensor fault thresholds |

---

## 5. Tables Grouped by Subsystem

### 5.1 Sensor Scaling & Calibration

#### Barometric Pressure Sensor
| Address | Name | Type | Used By | Confidence |
|---------|------|------|---------|-----------|
| 0x6CF6C | Barometric Pressure Sensor Max ADC Count | u16 | `baro_sensor_value.c` | HIGH |
| 0x6CF6E | Barometric Pressure Sensor Min ADC Count | u16 | `baro_sensor_value.c` | HIGH |
| 0x7A930 | Barometric Pressure Sensor Min Voltage | float | sensor pipeline | HIGH |
| 0x7A934 | Barometric Pressure Sensor Max Voltage | float | sensor pipeline | HIGH |
| 0x7A9C0 | Barometric Pressure Sensor Slope | float | sensor pipeline | HIGH |
| 0x7A9BC | Barometric Pressure Sensor Offset | float | sensor pipeline | HIGH |

#### MAF Sensor
| Address | Name | Type | Axis | Used By | Descriptor |
|---------|------|------|------|---------|------------|
| 0x6FBD8 | **MAF Scaling** | 1D f32[48] | Voltage (0–5V) | `maf_sensor_value.c` | 0x69E4C (J-line variant) |
| 0x7A65C | MAF Related | 1D u16[8] | — | sensor pipeline | 0x6B6F4 |

#### Temperature Sensors
| Address | Name | Type | Used By |
|---------|------|------|---------|
| 0x6F96C | **CLT Sensor Scaling** | 1D f32[32] | coolant processing |
| 0x6FFE8 | **IAT Sensor Scaling** | 1D f32[16] | intake air processing |

#### Lambda / O₂ Sensors
| Address | Name | Type | Used By |
|---------|------|------|---------|
| 0x6FD74 | **Lambda Sensor Scaling** | 1D f32[11] | O₂ sensor processing |
| 0x7AF74 | Unknown Lambda Input | 1D u8[8] | O₂ subsystem |

#### Sensor Signal Conditioning (Tables 60–69)
| Address | Table | Identified Purpose | Used By | ROM Region |
|---------|-------|-------------------|---------|------------|
| 0x70084 | 2D-60 | MAF Sensor Output Filter Frequency | `calc_throttle_position_filter` | 0x6F000–0x70000 |
| 0x700B0 | 2D-61 | Intake Air Temperature Filtering | `calc_intake_air_temp_compensation` | 0x6F000–0x70000 |
| 0x700E0 | 2D-62 | Coolant Temperature Filtering | `calc_exhaust_gas_temp_trim` | 0x6F000–0x70000 |
| 0x70110 | 2D-63 | Engine Load Signal Conditioning | `air_charge_calc` | 0x6F000–0x70000 |
| 0x70230 | 2D-64 | Barometric Pressure Adjustment | `MAP_sensor_scaling` | 0x6F000–0x70000 |
| 0x70264 | 2D-65 | Oxygen Sensor Switching Point | `air_fuel_ratio_feedback_calc` | 0x6F000–0x70000 |
| 0x702A4 | 2D-67 | Throttle Position Sensor Deadband | `calc_throttle_position_filter` | 0x6F000–0x70000 |
| 0x703BC | 2D-69 | Load Estimation Smoothing Factor | `engine_load_estimator` | 0x6F000–0x70000 |

All **MEDIUM confidence** from the 50-table analysis report.

### 5.2 Fuel Injection - Base Fueling

#### Main Fuel Tables (3D, RPM vs Load)
| Address | Name | Dims | Type | Scale | Descriptor | Notes |
|---------|------|------|------|-------|-----------|-------|
| 0x7238C | Fuelling 10 - Safe Mode | 21×19 | u8 | 0.003906 | 0x6A4D8 | Primary fuel table (safe) |
| 0x72684 | Fuelling 14 - Safe mode | 21×19 | u8 | 0.003906 | 0x6A548 | Secondary fuel table (safe) |
| 0x72964 | Fuelling 16 | 21×19 | u8 | 0.003906 | 0x6A580 | Primary fuel table (normal) |
| 0x72864 | Fuelling 15 | 21×19 | u8 | 0.003906 | 0x6A564 | Secondary fuel table (normal) |

#### 1D Fuel Correction Tables
| Address | Name | Dims | Descriptor | Notes |
|---------|------|------|-----------|-------|
| 0x71CD0 | Fuelling - Safe Mode | 9 | 0x6A2E8 | Safe mode fuel multiplier |
| 0x71D00 | Fuelling 1 | 7 | 0x6A310 | Fuel correction 1 |
| 0x71D2C | Fuelling 2 - Safe Mode | 9 | 0x6A324 | Fuel correction 2 (safe) |
| 0x71D5C | Fuelling 3 | 9 | 0x6A338 | Fuel correction 3 |
| 0x71D84 | Fuelling 4 | 7 | 0x6A34C | Fuel correction 4 |
| 0x71DD4 | Fuelling 5 | 18 | 0x6A360 | Fuel correction 5 |
| 0x71E30 | Fuelling 6 | 18 | 0x6A374 | Fuel correction 6 |
| 0x71E8C | Fuelling 7 | 18 | 0x6A388 | Fuel correction 7 |
| 0x72084 | Fuelling 8 | 7 | 0x6A43C | Fuel correction 8 |
| 0x7228C | Fuelling 9 - Safe Mode | 12×8 | 0x6A4BC | 2D fuel correction (safe) |
| 0x72584 | Fuelling 13 - Safe Mode | 12×8 | 0x6A52C | 2D fuel correction (safe) |

### 5.3 Fuel Injection - Enrichment & Trims

#### WOT & Cold Start Enrichment
| Address | Table | Identified Purpose | Used By | Confidence |
|---------|-------|-------------------|---------|-----------|
| 0x72DD0 | 2D-110 | **WOT Enrichment Threshold** | `calc_wot_fuel_enrichment` (0x14220) | **HIGH** |
| 0x72E40 | 2D-111 | **Cold Start Enrichment Threshold** | `calc_cold_start_fuel_enrichment` (0x142E8) | **HIGH** |

#### Transient Enrichment (Tables 128–130)
| Address | Table | Identified Purpose | Used By | Confidence |
|---------|-------|-------------------|---------|-----------|
| 0x73DB4 | 2D-128 | Transient Fuel Enrichment - Cold Phase | `calc_accel_fuel_enrichment` | MEDIUM |
| 0x73DD0 | 2D-129 | Transient Fuel Enrichment - Warm Phase | `calc_accel_fuel_enrichment` | MEDIUM |
| 0x73DEC | 2D-130 | Transient Fuel Enrichment - Hot Phase | `calc_accel_fuel_enrichment` | MEDIUM |

#### O₂ / Lambda Control
| Address | Table | Identified Purpose | Used By | Confidence |
|---------|-------|-------------------|---------|-----------|
| 0x717BC | 2D-79 | **Lambda Integration Time Constant** | `calc_lambda_integration_time` (0x1418C) | **HIGH** |
| 0x717F4 | 2D-80 | Lambda control parameter | O₂ subsystem | MEDIUM |

#### Adaptive Fuel Trim Tables
| Address | Table | Used By |
|---------|-------|---------|
| 0x6A868 | (adaptive trim table A, EEPROM) | `calc_adaptive_fuel_trim.c`, `o2_lambda_subsystem.c` |
| 0x6A87C | (adaptive trim table B, EEPROM) | `calc_adaptive_fuel_trim.c`, `o2_lambda_subsystem.c` |

### 5.4 Fuel Injection - Injector Control

#### Injector Sizing
| Address | Name | Type | Used By |
|---------|------|------|---------|
| 0x783A0 | **Primary Injector Size** | scalar | fuel calculation |
| 0x783A8 | **Secondary Injector Size** | scalar | fuel calculation |
| 0x783B0 | **Secondary Injector Size #2** | scalar | fuel calculation |

#### Injector Latency (Dead Time)
| Address | Name | Dims | Type | Descriptor |
|---------|------|------|------|-----------|
| 0x780F4 | **Injector Latency Primary** | 17×9 | u16 | 0x6AF54 |
| 0x77F58 | **Injector Latency Secondary** | 17×9 | u16 | 0x6AF38 |

#### Injector Dead Time Compensation
| Address | Table | Identified Purpose | Used By | Confidence |
|---------|-------|-------------------|---------|-----------|
| 0x78318 | 2D-175 | Injector Dead Time (Primary) Compensation | `secondary_fuel_trimmer` (0x16668) | MEDIUM |
| 0x78364 | 2D-176 | Injector Dead Time (Secondary) Compensation | `secondary_fuel_trimmer` (0x16668) | MEDIUM |
| 0x7850C | 2D-350 | Injection Pulse Width Primary Control | `dual_channel_fuel_computation` (0x14BCC) | MEDIUM |
| 0x7853C | 2D-179 | Secondary Injector Minimum Pulse Width | `dual_channel_fuel_computation` (0x14BCC) | MEDIUM |

#### Secondary Fuel System (Tables 204–209)
| Address | Table | Identified Purpose | Used By | Confidence |
|---------|-------|-------------------|---------|-----------|
| 0x79790 | 2D-204 | Secondary Fuel Blend Transition RPM | `rotary_fuel_enrichment_controller` | MEDIUM |
| 0x797C8 | 2D-205 | Secondary Fuel Blend Rate of Change | `rotary_fuel_enrichment_controller` | MEDIUM |
| 0x79814 | 2D-206 | Rotor A/B Fuel Pulse Width Limiter | `calc_fuel_injection_all_rotors` (0x13D3C) | **HIGH** |
| 0x798B8 | 2D-207 | Secondary Fuel Enable Temperature | `secondary_chamber_activation` (0x1695A) | MEDIUM |
| 0x798D0 | 2D-208 | Secondary Fuel Disable Temperature | `secondary_chamber_activation` (0x1695A) | MEDIUM |
| 0x798E8 | 2D-209 | Secondary Fuel Mode Selector | `secondary_chamber_activation` (0x1695A) | MEDIUM |

#### Fuel Pressure Limiting
| Address | Table | Identified Purpose | Used By | Confidence |
|---------|-------|-------------------|---------|-----------|
| 0x78DF8 | 2D-197 | Fuel Pressure Limiter (High RPM) | `secondary_fuel_trimmer` | MEDIUM |
| 0x78DC0 | 2D-196 | Fuel Pressure Limiter (Low RPM) | `secondary_fuel_trimmer` | MEDIUM |

#### Injection Angle
| Address | Name | Dims | Type | Descriptor |
|---------|------|------|------|-----------|
| 0x7B2B8 | **Injection Angle** | 18×8 | u16 | 0x6BB84 |
| 0x7AF48 | Injection Angle Related AFR Input | 9 | u8 | 0x6BABC |

### 5.5 Ignition Timing

#### Main Ignition Timing Tables (20×18, RPM × Load)
| Address | Name | Descriptor | Notes |
|---------|------|-----------|-------|
| 0x6DB48 | **Ignition Leading Base** | 0x69860 | Main leading ignition map |
| 0x6D748 | Ignition Leading 1 | 0x69828 | Alt leading ignition map |
| 0x6DDD4 | Ignition (Trailing) | 0x69898 | Main trailing ignition map |
| 0x6E1D4 | Ignition 1 (Trailing) | 0x698D0 | Alt trailing map |
| 0x6D948 | Ignition Leading Base - Safe Mode | 0x69844 | Safe mode leading |
| 0x6DFD4 | Ignition 0 - Safe Mode | 0x698B4 | Safe mode trailing |
| 0x6EEEC | **Ignition Trailing B** | 0x69EF8 | Secondary trailing |
| 0x6F0EC | **Ignition Trailing A** | 0x69F14 | Primary trailing |
| 0x6F2EC | **Ignition Min Split** | 0x69F30 | Min trailing/leading split |

#### Small Ignition Tables
| Address | Name | Dims | Descriptor |
|---------|------|------|-----------|
| 0x6D59C | Ignition Maybe Idle Base | 1D 6 | 0x697BC |
| 0x6D5C8 | Ignition Temp Correction? | 1D 9 | 0x697D0 |
| 0x6D5EC | Ignition 2 | 1D 6 | 0x697E4 |
| 0x6D618 | Ignition Leading 0 | 1D 9 | 0x697F8 |
| 0x6D668 | Ignition Timing Lead | 2D 10×7 | 0x6980C |
| 0x6DCF4 | Ignition Leading 4 | 2D 10×7 | 0x6987C |
| 0x6E358 | Ignition Leading 5 | 2D 4×3 | 0x698EC |
| 0x6E3A4 | Ignition Minimum Maybe | 2D 4×3 | 0x69900 |
| 0x6F4CC | Ignition 3 | 2D 19×11 | 0x69CB4 |
| 0x6F78C | Ignition 4 | 1D 12 | 0x69CC8 |
| 0x6F7D0 | Ignition 6 | 1D 12 | 0x69CF0 |
| 0x7CB20 | **Ignition Dwell Time_** | 2D 9×9 | 0x6BF28 |

#### Ignition Correction Tables (Tables 10–15 — Knock-Related)
| Address | Table | Identified Purpose | Used By | Confidence |
|---------|-------|-------------------|---------|-----------|
| 0x6E4BC | 2D-10 | **Knock Correction - Light Knock** | `knock_margin_limiter_primary` | **HIGH** |
| 0x6E4E0 | 2D-11 | **Knock Correction - Medium Knock** | `knock_margin_limiter_primary` | **HIGH** |
| 0x6E504 | 2D-12 | **Knock Correction - Heavy Knock** | `knock_margin_limiter_primary` | **HIGH** |
| 0x6E528 | 2D-13 | **Knock Detection Sensitivity** | `write_cyl_A_knock_flag` (0x128FE) | **HIGH** |
| 0x6E54C | 2D-14 | Knock retard table | knock control | MEDIUM |
| 0x6E570 | 2D-15 | Knock retard table | knock control | MEDIUM |

### 5.6 Knock Control

#### Knock Sensor Processing
| Address | Name | Type | Used By |
|---------|------|------|---------|
| 0x78EE0 | (filter gain) | float | `knockRelatedInit.c`, `getKnockSensorADC.c` |
| 0x78EE4 | (threshold 1) | float | `knockRelatedInit.c`, `getKnockSensorADC.c` |
| 0x78EE8 | (threshold 2) | float | `knockRelatedInit.c`, `getKnockSensorADC.c` |
| 0x78EEC | (filter coeff) | float | `knockRelatedInit.c`, `getKnockSensorADC.c` |
| 0x7A164 | (sensor ID table) | u8[2] | `knockRelatedInit.c` |

#### Knock Scaling Tables
| Address | Name | Dims | Descriptor |
|---------|------|------|-----------|
| 0x7A318 | Knock Voltage To Magnitude | — | Not in mapscan (f32 table) |
| 0x7A38C | Knock Related 1 | 1D 14 f32 | 0x6B650 |
| 0x7A3E0 | Knock Related 2 | 1D 14 f32 | 0x6B65C |
| 0x7A450 | Knock Rel #4 | 2D 6×11 | 0x6B680 |
| 0x7A4D8 | Knock Rel #0 | 2D 6×11 | 0x6B69C |

### 5.7 Idle Control

#### Idle Target Speed Tables
| Address | Name | Dims | Descriptor |
|---------|------|------|-----------|
| 0x6E880 | Idle Target | 1D 7 | 0x69A54 |
| 0x6E8C0 | Idle Target 0 | 1D 12 | 0x69A68 |
| 0x6E908 | Idle Target 1 | 1D 12 | 0x69A7C |
| 0x6E950 | Idle Target 2 | 1D 12 | 0x69A90 |
| 0x6E998 | Idle Target 3 | 1D 12 | 0x69AA4 |
| 0x6E9CC | Idle Target 4 | 1D 7 | 0x69AB8 |
| 0x6E9F8 | Idle Target 5 | 1D 7 | 0x69ACC |
| 0x6EA24 | Idle Target 6 | 1D 7 | 0x69AE0 |
| 0x6EA50 | Idle Target 7 | 1D 7 | 0x69AF4 |

#### Idle Related
| Address | Name | Dims | Descriptor |
|---------|------|------|-----------|
| 0x6D1E0 | Idle Related | 1D 16 | 0x69724 |

### 5.8 Throttle & Pedal Control

#### Accel Pedal → Throttle Position
| Address | Name | Dims | Descriptor |
|---------|------|------|-----------|
| 0x74250 | **Accel Pedal to Throttle Position #1** | 21×18 | 0x6A9C8 |
| 0x745E0 | **Accel Pedal to Throttle Position #2** | 21×18 | 0x6A9E4 |
| 0x74970 | **Accel Pedal to Throttle Position #3** | 21×18 | 0x6AA00 |
| 0x74D00 | **Accel Pedal to Throttle Position #4** | 21×18 | 0x6AA1C |

#### Torque <-> Position Conversion
| Address | Name | Dims | Descriptor |
|---------|------|------|-----------|
| 0x73090 | **Torque To Accel Position** | 26×19 | 0x6A6D4 |
| 0x734F4 | **Throttle Position To Torque** | 14×20 | 0x6A6F0 |

#### Throttle Limits
| Address | Name | Type | Notes |
|---------|------|------|-------|
| 0x73F6C | **Maximum Throttle Angle** | scalar | Max allowed throttle opening |

### 5.9 Torque & Load Management

#### Engine Load Compensation
| Address | Name | Dims | Descriptor |
|---------|------|------|-----------|
| 0x786E8 | **Engine Load Compensation** | 18×20 | 0x6B0B0 |

#### Load Limit Tables
| Address | Name | Dims | Descriptor |
|---------|------|------|-----------|
| 0x7C1B4 | **Load Limit A** | 1D 12 f32 | 0x6BD88 |
| 0x7C214 | **Load Limit B** | 1D 12 f32 | 0x6BD94 |
| 0x7C354 | **Load Limit C** | 1D 10 u16 | 0x6BDA0 |

#### Estimated Manifold Pressure
| Address | Name | Dims | Descriptor |
|---------|------|------|-----------|
| 0x77C48 | **Estimated Manifold Pressure** | 17×20 | 0x6AF1C |

#### Load Limiter (Tables 144–147) — Identified by Analysis Report
| Address | Table | Identified Purpose | Used By | Confidence |
|---------|-------|-------------------|---------|-----------|
| 0x75054 | 2D-144 | Manifold Absolute Pressure Requested | `load_bias_table_interpreter` (0x15254) | MEDIUM |
| 0x750B0 | 2D-145 | Load Limiter Smoothing Factor | `load_bias_table_interpreter` (0x15254) | MEDIUM |
| 0x750F8 | 2D-146 | Load Limiter Maximum Value | `load_bias_table_interpreter` (0x15254) | MEDIUM |
| 0x75130 | 2D-147 | Load Compensation Multiplier Idle | `load_bias_table_interpreter` (0x15254) | MEDIUM |

### 5.10 VDI Control (Variable Dynamic Intake)
| Address | Name | Type | Notes |
|---------|------|------|-------|
| 0x78CC0 | **Auxillary Valve Close** | scalar | VDI valve close point |
| 0x7A5A4 | **VDI Open** | scalar | VDI valve open point |

### 5.11 Oil Metering
| Address | Name | Dims | Descriptor |
|---------|------|------|-----------|
| 0x790C4 | **Oil Metering By Load** | 2D 19×17 f32 | 0x6B264 |
| 0x79264 | **Oil Metering By Throttle** | 2D 19×4 f32 | 0x6B278 |

### 5.12 Rev Limit
| Address | Name | Type | Notes |
|---------|------|------|-------|
| 0x6D544 | **Cold Rev Limit** | u16 | RPM limit when cold |
| 0x6D53C | **Cold Rev Limit Threshold** | u16 | Temperature threshold for cold limit |
| 0x6D54C | **Rev Limit** | u16 | Maximum engine speed |

### 5.13 Flex Fuel
These tables are named per the RomRaider `rx8_defs.xml` conventions (original XML not redistributed) and are defined for the N3J1EL ROM:

| Table Name | Category | Type | Size |
|-----------|----------|------|------|
| Table 3D - Timing Ethanol Adder - Leading | Flex Fuel | 3D u8 | 20×18 |
| Table 3D - Timing Ethanol Adder - Trailing | Flex Fuel | 3D u8 | 20×18 |
| Table 2D - Timing Multiplier | Flex Fuel | 2D f32 | 12 |
| Table 2D - Stoich Fuel Ratio | Flex Fuel | 2D f32 | 12 |
| Ethanol Content Sample Threshold - Engine Speed | Flex Fuel | 1D f32 | 1 |
| Ethanol Content Sample Threshold - Engine Load | Flex Fuel | 1D f32 | 1 |
| Table 3D - Cranking Fuel Multiplier | Flex Fuel | 3D u8 | 12×13 |

### 5.14 Generic / Unidentified Tables

The following tables are numbered sequentially in the RomRaider definitions but have not yet been assigned a specific function. They are listed here grouped by address range for future analysis.

#### Tables 0–9 (0x6CFE4–0x6D4D4) — Ignition Region
| Address | Table | Dims | Type | Descriptor |
|---------|-------|------|------|-----------|
| 0x6CFE4 | Table 2D - 0_ | 16 | u8 | 0x6969C |
| 0x6D034 | Table 2D - 1_ | 16 | u8 | 0x696B0 |
| 0x6D084 | Table 2D - 2_ | 16 | u8 | 0x696C4 |
| 0x6D114 | Table 2D - 3_ | 10 | u8 | 0x696D8 |
| 0x6D138 | Table 2D - 4_ | 6 | u8 | 0x696EC |
| 0x6D2AC | Table 3D - 0_ | 16×6 | u8 | 0x6974C |
| 0x6D364 | Table 3D - 1_ | 16×6 | u8 | 0x69768 |
| 0x6D41C | Table 3D - 2_ | 16×6 | u8 | 0x69784 |
| 0x6D4D4 | Table 3D - 3_ | 16×6 | u8 | 0x697A0 |

#### Tables 16–24 (0x6E5BC–0x6E84C) — Unknown
| Address | Table | DIM | Type | Descriptor |
|---------|-------|-----|------|-----------|
| 0x6E5BC | Table 2D - 16_ | 16 | u16 | 0x699A0 |
| 0x6E6F0 | Table 2D - 17_ | 7 | u8 | 0x699B4 |
| 0x6E714 | Table 2D - 18_ | 7 | u8 | 0x699C8 |
| 0x6E738 | Table 2D - 19_ | 7 | u8 | 0x699DC |
| 0x6E75C | Table 2D - 20_ | 7 | u8 | 0x699F0 |
| 0x6E780 | Table 2D - 21_ | 7 | u8 | 0x69A04 |
| 0x6E7A4 | Table 2D - 22_ | 7 | u8 | 0x69A18 |
| 0x6E7F8 | Table 2D - 23_ | 19 | u16 | 0x69A2C |
| 0x6E84C | Table 2D - 24_ | 11 | u16 | 0x69A40 |

#### Tables 34–46 (0x6EAF8–0x6EDF4) — Fuel Trim Region
| Address | Table | Dims | Type | Descriptor |
|---------|-------|------|------|-----------|
| 0x6EAF8 | Table 2D - 34_ | 9 | u8 | 0x69B24 |
| 0x6EB28 | Table 2D - 35_ | 9 | u8 | 0x69B38 |
| 0x6EB58 | Table 2D - 36_ | 9 | u8 | 0x69B4C |
| 0x6EB88 | Table 2D - 37_ | 9 | u8 | 0x69B60 |
| 0x6EBA8 | Table 2D - 38_ | 5 | u8 | 0x69B74 |
| 0x6EBC8 | Table 2D - 39_ | 6 | u8 | 0x69B88 |
| 0x6EC08 | Table 2D - 40_ | 14 | u8 | 0x69B9C |
| 0x6EC44 | Table 2D - 41_ | 4 | u16 | 0x69BB0 |
| 0x6EC70 | Table 2D - 42_ | 9 | u16 | 0x69BC4 |
| 0x6ECA8 | Table 2D - 43_ | 9 | u16 | 0x69BD8 |
| 0x6ECE0 | Table 2D - 44_ | 9 | u16 | 0x69BEC |
| 0x6ED08 | Table 2D - 45_ | 5 | u16 | 0x69C00 |
| 0x6ED3C | Table 2D - 46_ | 9 | u8 | 0x69C14 |
| 0x6ED78 | Table 3D - 13_ | 9×3 | u8 | 0x69C28 |
| 0x6EDF4 | Table 3D - 14_ | 12×8 | u8 | 0x69C44 |

#### Tables 57–59 (0x6F878–0x6FEE4)
| Address | Table | Dims | Type | Descriptor |
|---------|-------|------|------|-----------|
| 0x6F878 | Table 2D - 57_ | 12 | u16 | 0x69E00 |
| 0x6FAB0 | Table 2D - 58_ | 5 | u8 | 0x69E20 |
| 0x6FEE4 | Table 2D - 59_ | 11 | u16 | 0x69EA0 |

#### Tables 70–102 (0x715BC–0x7C9B4) — Various Regions
These tables span multiple ROM regions and likely include fuel corrections, temperature compensations, and other modifiers. See the full descriptor listing in `docs/subsystems/MAPS.md` for the complete 499-entry catalog.

### 5.15 Check DataType (f32 intermediate) Tables

105 tables are named "Table 2D - NNN Check DataType" in the RomRaider definitions. These are **f32 intermediate calculation results** stored in ROM as read-only lookup tables. They are not tunable calibration tables in the traditional sense — they represent pre-computed values used by the 1D/2D lookup engine.

| Address | Name | Descriptor |
|---------|------|-----------|
| 0x6D158 | Table 2D - 288 Check DataType | 0x69700 |
| 0x6D178 | Table 2D - 289 Check DataType | 0x6970C |
| 0x6D198 | Table 2D - 290 Check DataType | 0x69718 |
| 0x6FACC | Table 2D - 292 Check DataType | 0x69E34 |
| 0x6FAF4 | Table 2D - 293 Check DataType | 0x69E40 |
| 0x6FCF8 | Table 2D - 295 Check DataType | 0x69E58 |
| 0x6FD20 | Table 2D - 296 Check DataType | 0x69E64 |
| 0x6FDE0 | Table 2D - 299 Check DataType | 0x69E88 |
| 0x6FE60 | Table 2D - 300 Check DataType | 0x69E94 |

*(Full list of 105 entries available in `cal_tables.csv` filtered by "Check DataType")*

---

## 6. RomRaider Definition Cross-Reference

The RomRaider XML definition file (`refs/rx8defs/RomRaider/rx8_defs.xml`, **not shipped** — this doc only follows its naming conventions) contains ~20,262 `<table>` tags across many categories. The following table maps RomRaider categories to address ranges:

| RomRaider Category | Address Range | Number of Tables | Notes |
|--------------------|--------------|-----------------|-------|
| Sensors | 0x6CF6C–0x6FFE8 | ~20 | Baro, MAF, CLT, IAT, Lambda scaling |
| Fuel Injection | 0x71CD0–0x72964 | ~30 | Main fuel tables, safe mode variants |
| Flex Fuel | varies | ~8 | Ethanol-related tables |
| Ignition | 0x6D59C–0x6F4CC | ~35 | Leading/trailing timing, dwell |
| Unknown 2D | 0x6CFE4–0x7D92C | ~334 | Numbered tables awaiting identification |
| Unknown 3D | 0x6D2AC–0x7C9B4 | ~80 | Numbered 3D tables awaiting identification |
| Outputs | varies | ~8 | Fan control thresholds |
| Cruise Control | varies | ~2 | Speed thresholds |
| Gear Detection | varies | ~6 | Gear ratio thresholds |
| Immobilizer | varies | ~2 | Immobilizer bypass switches |

The RomRaider definition file contains many more categories and individual tables than captured in `cal_tables.csv`. The `cal_tables.csv` specifically extracts the **value pointer addresses** that correspond to the actual stored calibration data.

---

## 7. Analysis Report Cross-Reference (50 New Tables)

The analysis report `ANALYSIS_REPORT_50_NEW_TABLES.md` (moved to private storage, not shipped) identified 50 previously unnamed RomRaider tables. Below is the cross-reference of those identifications:

### HIGH Confidence Identifications (15 tables)

| Address | Table | Identification | ROM Function | C Verification |
|---------|-------|---------------|-------------|----------------|
| 0x72DD0 | 2D-110 | WOT Enrichment Threshold | `calc_wot_fuel_enrichment` (0x14220) | `o2_lambda_subsystem.c` |
| 0x72E40 | 2D-111 | Cold Start Enrichment Threshold | `calc_cold_start_fuel_enrichment` (0x142E8) | `o2_lambda_subsystem.c` |
| 0x717BC | 2D-79 | Lambda Integration Time Constant | `calc_lambda_integration_time` (0x1418C) | — |
| 0x79814 | 2D-206 | Rotor A/B Fuel Pulse Width Limiter | `calc_fuel_injection_all_rotors` (0x13D3C) | — |
| 0x6E4BC | 2D-10 | Knock Correction - Light Knock | `knock_margin_limiter_primary` (0x19000) | — |
| 0x6E4E0 | 2D-11 | Knock Correction - Medium Knock | `knock_margin_limiter_primary` (0x19000) | — |
| 0x6E504 | 2D-12 | Knock Correction - Heavy Knock | `knock_margin_limiter_primary` (0x19000) | — |
| 0x6E528 | 2D-13 | Knock Detection Sensitivity Threshold | `write_cyl_A_knock_flag` (0x128FE) | — |
| 0x6D138 | 2D-4 | Ignition Idle Timing Table | `calc_ignition_advance_modifier` (0x13A0E) | — |
| 0x783A0 | — | Primary Injector Size | fuel calculation | — |
| 0x783A8 | — | Secondary Injector Size | fuel calculation | — |
| 0x73F6C | — | Maximum Throttle Angle | throttle control | — |
| 0x78CC0 | — | Auxillary Valve Close | VDI control | — |
| 0x7A5A4 | — | VDI Open | VDI control | — |
| 0x6D54C | — | Rev Limit | rev limiting | — |

### MEDIUM Confidence Identifications (35 tables)

**Fuel Injection & Enrichment (12):**
| Address | Table | Identification |
|---------|-------|---------------|
| 0x73DB4 | 2D-128 | Transient Fuel Enrichment - Cold Phase |
| 0x73DD0 | 2D-129 | Transient Fuel Enrichment - Warm Phase |
| 0x73DEC | 2D-130 | Transient Fuel Enrichment - Hot Phase |
| 0x78318 | 2D-175 | Injector Dead Time (Primary) Compensation |
| 0x78364 | 2D-176 | Injector Dead Time (Secondary) Compensation |
| 0x7850C | 2D-350 | Injection Pulse Width Primary Control |
| 0x7853C | 2D-179 | Secondary Injector Minimum Pulse Width |
| 0x78DF8 | 2D-197 | Fuel Pressure Limiter (High RPM) |
| 0x78DC0 | 2D-196 | Fuel Pressure Limiter (Low RPM) |
| 0x79790 | 2D-204 | Secondary Fuel Blend Transition RPM |
| 0x797C8 | 2D-205 | Secondary Fuel Blend Rate of Change |
| 0x798B8 | 2D-207 | Secondary Fuel Enable Temperature |

**Sensor & Signal Conditioning (8):**
| Address | Table | Identification |
|---------|-------|---------------|
| 0x70084 | 2D-60 | MAF Sensor Output Filter Frequency |
| 0x700B0 | 2D-61 | Intake Air Temperature Filtering |
| 0x700E0 | 2D-62 | Coolant Temperature Filtering |
| 0x70110 | 2D-63 | Engine Load Signal Conditioning |
| 0x70230 | 2D-64 | Barometric Pressure Adjustment |
| 0x70264 | 2D-65 | Oxygen Sensor Switching Point |
| 0x702A4 | 2D-67 | Throttle Position Sensor Deadband |
| 0x703BC | 2D-69 | Load Estimation Smoothing Factor |

**Load & Boost Control (5):**
| Address | Table | Identification |
|---------|-------|---------------|
| 0x75054 | 2D-144 | Manifold Absolute Pressure Requested |
| 0x750B0 | 2D-145 | Load Limiter Smoothing Factor |
| 0x750F8 | 2D-146 | Load Limiter Maximum Value |
| 0x75130 | 2D-147 | Load Compensation Multiplier Idle |
| 0x798D0 | 2D-208 | Secondary Fuel Disable Temperature |

**Other (10):**
| Address | Table | Identification |
|---------|-------|---------------|
| 0x798E8 | 2D-209 | Secondary Fuel Mode Selector |
| 0x79920 | 2D-210 | Rotor A/B Fuel Distribution Trim |
| 0x7995C | 2D-211 | Rotor A/B Fuel Distribution Trim 2 |
| 0x799A0 | 2D-212 | Deceleration Fuel Cutoff Rate |
| 0x799B8 | 2D-213 | Deceleration Fuel Cutoff Recovery |
| 0x799F8 | 2D-214 | Fuel Pressure Regulator Duty (Low) |
| 0x79A1C | 2D-215 | Fuel Pressure Regulator Duty (High) |
| 0x79A54 | 3D-76 | Fuel Pressure Regulator 3D |
| 0x79AD4 | 3D-77 | Fuel Pressure Comp 3D |
| 0x79B48 | 3D-78 | Fuel Pressure Comp 3D 2 |

---

## 8. Statistics & Coverage

### Overall Statistics

| Metric | Count |
|--------|-------|
| **Calibration tables in cal_tables.csv** | 1,209 |
| **Map descriptors decoded (mapscan.py)** | 499 (119 2D + 380 1D) |
| **Named/identified tables** | ~109 |
| **Generic numbered tables (Table 2D/3D - N)** | ~334 |
| **Check DataType (f32 intermediate) tables** | ~105 |
| **Axis-only entries (X, Y labels)** | ~660 |
| **C files with calibration table references** | 19 of 55 |
| **Direct C file → table name matches** | 3 (MAF Scaling, Table 2D-110, Table 2D-111) |
| **Analysis report new identifications** | 50 (15 HIGH, 35 MEDIUM) |
| **RomRaider categories referenced** | 12+ |

### Coverage by Subsystem

| Subsystem | Tables Identified | Still Unidentified | Total in ROM |
|-----------|------------------|-------------------|-------------|
| Sensor Scaling | 12 | ~5 | ~17 |
| Fuel Injection - Base | 18 | ~10 | ~28 |
| Fuel Injection - Enrichment | 12 | ~8 | ~20 |
| Injector Control | 10 | ~3 | ~13 |
| Ignition Timing | 33 | ~5 | ~38 |
| Knock Control | 7 | ~3 | ~10 |
| Idle Control | 10 | ~2 | ~12 |
| Throttle/Pedal | 7 | ~2 | ~9 |
| Load Management | 8 | ~5 | ~13 |
| VDI Control | 2 | 0 | 2 |
| Oil Metering | 2 | 0 | 2 |
| Rev Limit | 3 | 0 | 3 |
| Generic numbered | 0 | 334 | 334 |
| Check DataType | 0 | 105 | 105 |
| Axis entries | 0 | ~660 | ~660 |
| **Total** | **~109 named** | **~1,100** | **~1,209** |

---

## 9. Appendices

### A. Source Files Index

| File | Purpose |
|------|---------|
| `symbols/cal_tables.csv` | All calibration table value pointer addresses + names |
| `tools/mapscan.py` | ROM descriptor scanner (finds 499 descriptors) |
| `c/2DLookup.c` | Verified 1D table lookup function |
| `c/3dLookup.c` | Verified 2D/3D table lookup function |
| `c/o2_lambda_subsystem.c` | O₂ sensor feedback control (uses Tables 110, 111) |
| `c/maf_sensor_value.c` | MAF sensor scaling (uses MAF Scaling table) |
| `c/calc_adaptive_fuel_trim.c` | Adaptive fuel trim calculation |
| `c/calc_fuel_pump_duty_trim.c` | Fuel pump PWM control |
| `c/calc_ignition_all_rotors_13C2C.c` | Per-rotor ignition with knock retard |
| `c/baro_sensor_value.c` | Barometric pressure sensor linearization |
| `c/knockRelatedInit.c` | Knock sensor initialization |
| `c/getKnockSensorADC.c` | Knock sensor ADC reading + filtering |
| `c/sensor_check_float_bounds_adjust.c` | Sensor bounds checker |
| `c/calc_decel_fuel_cut_445AA.c` | Deceleration fuel cut |
| `c/limitKnockRetardMax_ConditionalRPM.c` | Conditional knock retard limiting |
| `FINAL_ANALYSIS_SUMMARY.txt` (private storage) | 50-table analysis executive summary |
| `ANALYSIS_REPORT_50_NEW_TABLES.md` (private storage) | Detailed 50-table analysis report |
| `RX8_Additional_Tables_Identified.txt` (private storage) | 50-table identification evidence |
| `docs/subsystems/MAPS.md` | Full 499-descriptor catalog |
| `refs/rx8defs/RomRaider/rx8_defs.xml` | RomRaider definition file (not shipped; naming conventions only) |

### B. How to Use This Document

1. **Finding a table by address:** Use Section 5 (grouped by subsystem) or search for the hex address.
2. **Finding which function uses a table:** Check Section 4 (C function cross-reference).
3. **Understanding table dimensions:** Look up the descriptor in Section 3 or `docs/subsystems/MAPS.md`.
4. **Verifying with RomRaider:** Use Section 6 to map to the XML definition.
5. **Viewing analysis evidence:** Section 7 links to the 50-table analysis report.

### C. Future Work

- **286 remaining unidentified RomRaider tables** need function cross-referencing.
- **105 Check DataType tables** should be validated as intermediate vs. tunable.
- **Axis pointer entries** need to be matched to their parent tables.
- **Add remaining C files** that reference table addresses to Section 4.
- **Cross-reference with other ROM variants** (N3J6EB, N3M5E, N3YLEE).

---

*Document generated from `cal_tables.csv`, `mapscan.py`, verified C sources in `c/`, and analysis reports (moved to private storage).*
