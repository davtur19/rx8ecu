# RX-8 ECU Sensor Processing Pipeline

The RX-8 ECU (Renesas SH-2E, HD64F7055) reads analog sensors via on-chip ADC, processes each channel through scaling/linearization, validates against fault thresholds, stores results in global RAM for fuel/ignition use.

```
1. HW ADC READ     sensorADCRead (0x68A8) → readADCResult (0x6FD4) → RAM 0xFFFF9EE4 (32×u16)
2. DEMUX           readADCs_coolantTempInHere (0x6D00) — dispatch on ADC state (8/4/1 ch)
3. SAMPLE LOOP     getSensorStuff @0x60C8 — calls each sensor processor in sequence
4. PER-SENSOR      MAF getMAFSensorValue 0x745C · IAT adcIAT2Volts 0x1C8E2 · Coolant chain 0x7398+
                   Baro getBaroSensorVal 0xD144 · Knock getKnockSensorADC 0xC3CE / knockSensorADCFault 0xC460
                   Rear O2 getRearO2Voltage 0xD478 · Throttle 0x1345C+ · Board temp pcmBoardTempADCtoVolts 0x3F158
5. VALIDATION      checkFloatValidity (0x46CC), adcVoltageOutOfRangeCheck (0x3C992), sensor_check_float_bounds_adjust (0xE0DE)
6. FILTERING       sensor_filter_apply (0x9478), sensor_filter_apply_all (0x1061A), sensor_select_adaptive_filter_ch (0x10A9E); 1st-order IIR
7. POST-PROCESS    calc_maf_sensor_flow (0x1332C), calc_throttle_position_filter (0x1345C), calc_barometric_pressure_trim (0x13F68),
                   calc_lambda_feedback_pid (0x11A34), calc_knock_control_enable (0x14944), knock_detection_processing (0xF770)
```

## 1. ADC Hardware Layer

### `sensorADCRead` @ 0x68A8 (0x68A8–0x6A06)
Reads all HW ADC channels into RAM. Configures ADC control regs, waits for conversion, reads 32×u16.

Registers: `0xF819`/`0xF818`/`0xF838`/`0xF858` ADC control regs. Output buffer `0xFFFF9EE4` (32 × uint16_t, 64 B). ADC state bytes `0xFFFF9F27`/`0xFFFF9F28`/`0xFFFF9F29`; mode/state `0xFFFF9F2F`; data regs `0xF800/0xF802/0xF804`.

### `readADCResult` @ 0x6FD4 (0x6FD4–0x7082)
Single-channel read wrapper. r4 = channel (0x0090-encoded); calls helper 0x3920; waits bit 5 of `0xF858` (conversion complete); reads result `0xF840`; `0xF859` ADC control/status; handles dual-channel flag merge; helper 0x3934 for post-processing. Returns r0.

## 2. ADC Channel Demultiplexing

### `readADCs_coolantTempInHere` @ 0x6D00 (0x6D00–0x6D72)
Demux on state reg `0xFFFF9F2F+2`: if ≤0 return; clears sub/main state; case 8 → read 8 channels `0xF84E–0xF840` into buffer offsets 62..48; case 4 → 4 channels; case 1 → 1 channel. Final value stored at buffer+48.

Channels: `0xF84E` ch0 · `0xF84C` ch1 · `0xF84A` ch2 · `0xF848` ch3 · `0xF846` ch4 · `0xF844` ch5 · `0xF842` ch6 · `0xF840` ch7.

## 3. Main Sensor Sampling Loop

### `getSensorStuff` @ 0x60C8
Main acquisition scheduler, called periodically from RTOS loop.

| Address | Function | Purpose |
|---|---|---|
| 0x68A8 | sensorADCRead | Read all ADC channels |
| 0x72A4 / 0x72B4 | sensor_state_reset_ch0 / sensor_latch_ch0 | Reset/latch ch0 |
| 0x745C | getMAFSensorValue | MAF scaling/lookup |
| 0x73BC | sensor_latch_ch2 | Latch ch2 |
| 0xD3D4 | baro processing | Barometric sensor |
| 0xB568 | sensor_value_copy_dispatch | Copy processed values |
| 0xD478 | getRearO2Voltage | Rear O2 |
| 0x753C | fueling init | Fueling initialization |
| 0xD9A2 | post-processing | Post-sensor processing |

I/O config: `0xF4AB` enable mask (bits 5,6) · `0xF4A4` config · `0xF4AA/0xF4A6/0xF4A8` I/O · `0xF4CB/0xF4C2` PWM/timer.

## 4. Per-Sensor Processing

### 4.1 MAF — `getMAFSensorValue` @ 0x745C
RAM: `0xFFFF9EEA` raw ADC · `0xFFFF9F78` processed (float g/s) · `0xFFFF9F7C` status (0=OK, 1=high, 2=low).

MAF Scaling descriptor @0x6A0E4: count=48, type=0 (no scale/offset). Axis @0x6FB18 (0.859–4.688V), values @0x6FBD8 (1.946–365.2 g/s). Bounds @0x6CF02 (upper 64225), 0x6CF04 (lower 2752). Scale 7.62939e-5.

**Verified MAF curve (48-pt):**

| ADC V | g/s | ADC V | g/s | ADC V | g/s | ADC V | g/s |
|---|---|---|---|---|---|---|---|
| 0.859 | 1.95 | 1.641 | 13.52 | 2.422 | 45.39 | 3.711 | 176.24 |
| 0.977 | 2.89 | 1.719 | 15.47 | 2.539 | 53.04 | 3.828 | 193.91 |
| 1.016 | 3.25 | 1.797 | 17.72 | 2.656 | 61.61 | 3.945 | 212.89 |
| 1.055 | 3.63 | 1.875 | 20.17 | 2.773 | 71.01 | 4.063 | 233.34 |
| 1.094 | 4.05 | 1.953 | 22.83 | 2.891 | 81.21 | 4.180 | 255.13 |
| 1.133 | 4.47 | 2.031 | 25.76 | 3.008 | 92.18 | 4.297 | 278.12 |
| 1.172 | 4.92 | 2.109 | 29.03 | 3.125 | 103.90 | 4.414 | 302.48 |
| 1.211 | 5.45 | 2.188 | 32.58 | 3.242 | 116.47 | 4.492 | 319.54 |
| 1.250 | 6.00 | 2.266 | 36.50 | 3.359 | 129.91 | 4.570 | 337.28 |
| 1.289 | 6.59 | 2.344 | 40.78 | 3.477 | 144.31 | 4.609 | 346.41 |
| 1.328 | 7.22 | 2.422 | 45.39 | 3.594 | 159.74 | 4.648 | 355.72 |
| 1.367 | 7.88 | 1.563 | 11.76 | 3.125 | 103.90 | 4.688 | 365.21 |
| 1.406 | 8.61 | 1.484 | 10.13 | 3.711 | 176.24 | 4.414 | 302.48 |

(Full 48-pt series: 1.250–2.422 and 2.539–4.688 ascending V; endpoints listed above.)

```c
void getMAFSensorValue(void) {
    uint16_t adc = *(uint16_t*)0xFFFF9EEA;
    float maf_flow = TwoDLookup(0x6FBD8, adc * 7.62939e-5f);   // X-axis volts @0x6FB18
    *(float*)0xFFFF9F78 = maf_flow;
    if (adc > 64225)      *(uint8_t*)0xFFFF9F7C = 1;   // over-range high
    else if (adc >= 2752) *(uint8_t*)0xFFFF9F7C = 2;   // over-range low
    else                  *(uint8_t*)0xFFFF9F7C = 0;
}
```

### 4.2 Intake Air Temperature

#### `adcIAT2Volts` @ 0x1C8E2 — `0xFFFF9F1E` ADC → `0xAE38` volts (scale 7.62939e-5).

#### `iat_sensor_3C214` @ 0x3C214 — full IAT processing (ADC → cal lookup → validate → status flags).

RAM: `0xFFFFC5EC` threshold flag · `0xFFFFC5F4` over-temp · `0xFFFFC5F5` range-high · `0xFFFFC5F6` range-low · `0xFFFFC5F8` status byte · `0xFFFFC5F0` temp (°C float). Cal @0x7A9A8. Constants @0x72D5C–0x64: 8000.0 gain, 200.0 ref, 0.1 scale. Status bits: 0=range low, 1=range high, 2=over-temp. C: `c/iat_sensor.c`.

#### `calc_intake_air_temp_compensation` @ 0x13FCC — IAT compensation multiplier (~1% per 10°C from ref); uses 8000/200/0.1.

### 4.3 Coolant — `calculateEngineTemperatures`
Stages: raw ADC `readADCs_coolantTempInHere` (0x6D00) → 0xFFFF9F00; voltage w/ rate-limit `readECMVoltage` @0x735C; temp via CLT Scaling @0x6F96C; fault `coolant_temp_out_of_range_check` @0xE50C; bounds `coolant_temp_boundary_check` @0x1F99A.

#### `readECMVoltage` @ 0x735C — delta-limited filter.
RAM: `0xFFFF9F00` raw ADC · `0xFFFF9F68` voltage out · `0xFFFF9F6C` prev ADC. Cal: `0x6CF50`=256 max delta · `0x6CF4C`=20.0 divider scale. V = clamped × (5.0/65536) × 20.0. C: `c/coolant_temperature_sensor.c`.

CLT Scaling @0x6F96C breakpoints: 36.25, 39.38, 43.13, 46.88, 50.63, 55, 60, 65, 70, 76.88, 84.38, 93.75, 106.25, 123.13, 130, 140 °C.

Fault `coolant_temp_out_of_range_check` @0xE50C: upper @0x6CF90 ~32000 (~2.44V, open) · lower @0x6CF94 ~400 (~0.03V, short); outputs `0xFFFFC5D2` (below-min), `0xFFFFC5D3` (above-max).

### 4.4 Barometric — `getBaroSensorVal` @ 0xD144
RAM: `0xFFFF9F18` raw ADC · `0xFFFFA3DC/0xFFFFA3E0` processed float. Scale 7.62939e-5; bounds @0x6D46C/0x6D46E = 1285 (0x0505); gain/offset floats @0x7978C/0x79790. Max/Min ADC count @0x6CF6C/0x6CF6E. Returns 0 valid / 1 over-high / 2 over-low.

### 4.5 Throttle
Pipeline: `throttle_position_adc_reader` @0x19FC0 (main ADC) · `throttle_position_sub_adc_reader` (sub/redundant) · `calc_throttle_position_filter` @0x1345C (filter + 3D multiplier) · `throttle_position_fault_handler` @0x3EEB8 (range fault) · `throttlePlateSomethingFuelCut` @0xEBA8.

#### `throttle_position_adc_reader` @ 0x19FC0 — `0xFFFFA424` raw → `0xFFFFA428` processed; if ADC > limit @0x6F9B8 → fault handler @0x3EEB8, output 0.

#### `calc_throttle_position_filter` @ 0x1345C — rate-limit + 1st-order filter. RAM: `0xFFFFA6B0` filtered deg, `0xFFFFA6B4` prev, `0xFFFFA6B8` rate limit. 2D TPS voltage→angle @0x6F9B8–0x6F9E8; MultiMap3D @0x6F9E8 (RPM×Load→factor); dual-track redundancy; P0121 if tracks diverge. C: `c/throttle_position_sensor.c`.

### 4.6 O2 / Lambda

| Function | Address | Purpose |
|---|---|---|
| getRearO2Voltage | 0xD478 | Raw rear O2 voltage |
| getRearO2FilteredValue | 0x1E794 | Filtered rear O2 |
| o2_target_increase_step | 0xE4D8 | O2 target ramping |
| calc_lambda_feedback_pid | 0x11A34 | Closed-loop lambda PID |
| write_o2_sensor_trim | 0x12B54 | O2 trim write |
| calc_secondary_o2_trim | 0x1321C | Secondary O2 trim |

Lambda Scaling @0x6FD74 (8-pt): 0.7586, 0.8276, 0.8966, 0.9655, 1.0, 1.0345, 1.1034, 1.1724. DTC handlers: `dtc_p0130_o2` @0x46DD2, `dtc_o2_circuit_fault` @0x45F54, `dtc_o2_response_time` @0x45F9C, `dtc_o2_slow_response` @0x45FA4.

### 4.7 Knock

| Function | Address | Purpose |
|---|---|---|
| knockFunctionInit | 0xC31C | Init |
| knockRelatedInit | 0xC3C8 | Per-rotor init (2 rotors) |
| knockSensorADCFault | 0xC460 | Fault detection |
| getKnockSensorADC | 0xC3CE | ADC read + filter |
| knock_detection_processing | 0xF770 | Main detection |
| write_knock_detected_flag | 0x128C4 | Per-rotor flags |
| calc_knock_control_enable | 0x14944 | Enable conditions |
| knock_retard_apply | 0x23D58 | Ignition retard |
| store_knock_learn_buffer | 0xC2C0 | Store learn params + tail-call setSR |
| limitKnockRetardMax_ConditionalRPM | 0x13AE4 | RPM-dependent max retard |

#### `knockSensorADCFault` @ 0xC460 — `0xFFFF9F0E` ADC; `0xFFFFA325` code. ADC ≥ 51249 → 1 (open, ~3.91V); ADC < 16121 → 2 (short, ~1.23V); else 0. Thresholds @0x6CF7E / 0x6CF7C.

#### `getKnockSensorADC` @ 0xC3CE — 1st-order filter active in RPM band 200–2000; RPM fault limit 10000. RAM: `0xFFFF9F80` RPM ref, `0xFFFF9F0E` raw ADC, `0xFFFFA37A` out copy, `0xFFFFA374` filter state, `0xFFFFA378` filtered int, `0xFFFFA386` fault byte. Cal: `0x78EE4`=200.0, `0x78EE8`=2000.0, `0x78EEC`=0.004 coeff, `0x78EA4`=10000.0. C: `c/getKnockSensorADC.c`.

#### `knockRelatedInit` @ 0xC3C8 — per-rotor threshold 10.0, filter state 0.0, max threshold byte 0xFF; sensor IDs @0x7A164; cal @0x7A178, 0x7A17A, 0x7A1A4, 0x7A1D0.

#### `store_knock_learn_buffer` @ 0xC2C0 — stores r4/r5 (u16) to `0xFFFFA370`/`0xFFFFA372`, tail-call setSR. C: `c/store_knock_learn_buffer.c`.

#### `limitKnockRetardMax_ConditionalRPM` @ 0x13AE4 — selects 2D retard-limit table by flag `0xFFFFA3B8` + sensor byte `0xFFFFA3C4`; RPM `0xFFFFA3A0`, result `0xFFFFA3A4`; tables 0x693CC / 0x693B8; applies sqrt. C: `c/limitKnockRetardMax_ConditionalRPM.c`.

### 4.8 Vehicle Speed — `calc_vehicle_speed_filter` @ 0x133F8
RAM: `0xFFFFA6AC` raw (km/h) · `0xFFFFA6B0` filtered · `0xFFFFA6BC` coeff · `0xFFFFA6C0` rate limit · `0xFFFFA6CC`/`0xFFFFA6D0` state · `0xFFFFA6D4` deadband · `0xFFFFA6D8` prev output · `0xFFFFA6B9` status. Cal: `0x6D470` coeff · `0x6D474` rate limit (km/h per cycle) · `0x6D478` deadband (km/h). Building-block fn @0x23DC: `0x23DC` f0=|fr4-fr5| · `0x23E4` f0=max(|fr4-fr5|,fr5) · `0x23F4` f0=max(fr4,fr5). C: `c/vehicle_speed_sensor.c`.

### 4.9 Battery — `getBatteryVoltageStatus` @ 0x26766
RAM: `0xFFFFB600` voltage · `0xFFFFB67A` compensated · `0xFFFFB6B6` over-volt flag · `0xFFFFB6C4` intermediate · `0xFFFFB6C8` reference. Cal @0x751B0–0xC4: 10.000V over-high, 1.000V hysteresis release, 16.973V critical (alt fail), 10.938V under-voltage. 16.973V = alternator regulator failure protection; 10.938V ≈ 70% charge; 1.0V hysteresis prevents oscillation. C: `c/battery_voltage_monitor.c`.

### 4.10 Barometric Trim — `calc_barometric_pressure_trim` @ 0x13F68
Constants @0x72D4C–0x72D58: four floats = -0.02. `trim = -0.02 × (reference - measured)`. Negative → reduces fuel/ignition at altitude.

## 5. Fault Query & Validation

### `getFaultStatus` @ 0x6743C
Fault channel query; 78+ callers. RAM `0xFFFFD96C` enable mask (u32); ROM table `0x0007E4DC`. Logic: immediate `(table[ch] & mask)` low16 → 1; else `getFaultEvalState(ch)` upper16. C: `c/getFaultStatus.c`.

### Flag setters

| Function | Address | Writes | Effect |
|---|---|---|---|
| setMemInsideFUNCto1 | 0x3E3F0 | 0xFFFFC638 | Flag=1 |
| SetMemoryNotValid2 | 0x3E5A8 | 0xFFFFC63A | Invalid flag=1 |

### `checkFloatValidity` @ 0x46CC
IEEE 754 NaN/Inf detection. Writes `0xFFFF7304` (not 0xFFFF768C as earlier docs). Exp all-1s `0x7F800000` (+Inf bit pattern): mantissa non-zero → 0x044D (NaN); zero → 0x044C (Inf). Valid floats: no write; returns value unchanged. C: `c/checkFloatValidity.c`.

### `adcVoltageOutOfRangeCheck` @ 0x3C992
Bounds @0x796FC/0x79700; flags `0xC5D2` below-min, `0xC5D3` above-max.

### Filter functions

| Function | Address | Description |
|---|---|---|
| sensor_filter_apply | 0x9478 | 1st-order IIR |
| sensor_filter_apply_all | 0x1061A | All channels |
| sensor_select_adaptive_filter_ch | 0x10A9E | Per-channel adaptive |
| firstOrderFilter | 0x23B0 | `y[n]=gain*x[n]+(1-gain)*y[n-1]` |
| sensor_range_limit_with_accumulation | 0x14B08 | Rate limiter w/ accumulation |
| delta_limit_filter | 0x2510 | ADC rate-limiter (clamps delta); used by readECMVoltage |
| speed_abs_diff_minmax | 0x23DC | Abs-diff + min/max; used by VSS filter |

## 6. Calibration Tables (Sensor Region)

### Sensor scaling descriptors (ROM 0x6A0D8–0x6A100)

| Address | Count | Type | Axis | Values | Description |
|---|---|---|---|---|---|
| 0x6A0D8 | 5 | 0 | 0x6FAE0 | 0x6FAF4 | Temp lookup (-20..+20°C, all=100.0) |
| 0x6A0E4 | 48 | 0 | 0x6FB18 | 0x6FBD8 | **MAF Scaling** (0.86–4.69V → 1.95–365.2 g/s) — **base ROM 60E1D400** |
| 0x6A0F0 | 8 | 0 | 0x6FCD8 | 0x6FCF8 | RPM scaling (500–8000 → 0–5000) |
| 0x6A0FC | 8 | 0 | 0x6FD18 | 0x6FD38 | Additional lookup |

### Sensor thresholds (ROM 0x6CF00–0x6D500)

| Address | Value | Description |
|---|---|---|
| 0x6CF02 / 0x6CF04 | 64225 / 2752 | MAF upper / lower threshold |
| 0x6CF4C | 20.0 | Coolant divider scale |
| 0x6CF50 | 0x0100 (256) | Coolant ADC delta threshold |
| 0x6CF90 / 0x6CF94 | ~32000 / ~400 | CLT upper (~2.44V) / lower (~0.03V) fault |
| 0x6CF7E / 0x6CF7C | 51249 / 16121 | Knock max (~3.91V) / min (~1.23V) |
| 0x6D46C / 0x6D46E | 1285 / 1285 | Baro validation min/max (0x0505) |
| 0x751B0 | 10.0 | Battery over-voltage high |
| 0x751B4 | 1.0 | Battery hysteresis release |
| 0x751C0 | 16.973 | Critical over-voltage |
| 0x751C4 | 10.938 | Under-voltage warning |
| 0x72D4C–0x72D58 | -0.02 (×4) | Barometric trim factor |
| 0x72D5C | 8000.0 | IAT gain |
| 0x72D60 | 200.0 | IAT reference |
| 0x72D64 | 0.1 | IAT scale |
| 0x72D68 | 0.5 | IAT additional factor |
| 0x6F9B8 | desc | TPS limit table (count=6) |
| 0x6F9D0 | desc | TPS scalar table (count=3) |
| 0x6F9E8 | desc | TPS MultiMap3D (RPM×Load) |

### Sensor 2D lookup tables (ROM 0x6F000–0x70000)

| Address | Name | Type | Values |
|---|---|---|---|
| 0x6CF6C / 0x6CF6E | Baro Max / Min ADC Count | u16 | Threshold |
| 0x6CF7C / 0x6CF7E | Knock Min / Max Threshold | u16 | 16121 / 51249 |
| 0x6D46C / 0x6D46E | Baro Validation Min / Max | u16 | 0x0505=1285 |
| 0x6F96C | CLT Sensor Scaling | 2D | 16-pt (36–140°C) |
| 0x6FBD8 / 0x6FB18 | MAF Scaling values / axis | 48× float | 1.95–365.2 g/s / 0.86–4.69V |
| 0x6FD74 | Lambda Sensor Scaling | 2D | 8-pt (0.76–1.17 AFR) |
| 0x6FFE8 | IAT Sensor Scaling | 2D | 8-pt (23–119°C) |

### Knock-related calibration (ROM 0x7A000–0x7B000)

| Address | Name | Type |
|---|---|---|
| 0x7A070 | Table 2D - 222_ | 2D |
| 0x7A164 | Per-rotor sensor IDs | u8[2] |
| 0x7A178 | Cal Constant 1 | u16 0x005E=94 |
| 0x7A17A | Cal Constant 2 | u16 0x00C1=193 |
| 0x7A1A4 | Float Param | float 3.6875 |
| 0x7A1D0 | Threshold | float 64.0 |
| 0x7A318 | Voltage→Magnitude | 2D |
| 0x7A38C / 0x7A3E0 / 0x7A400 / 0x7A408 / 0x7A450 / 0x7A4D8 | Knock related tables | table |
| 0x7A838 | Table 3D - 86_ | 3D (RPM×Load) |
| 0x7AC44 | Table 3D - 87_ | 3D |
| 0x7AD30 | Table 3D - 88_ | 3D |
| 0x7ADDC | Table 3D - 89_ | 3D |
| 0x7AABC | Table 3D - 122_ | 3D |
| 0x7AB58 | Table 3D - 123_ | 3D |

## 7. Sensor RAM Map

| Address | Size | Sensor | Description |
|---|---|---|---|
| 0xFFFF9EE4 | 64 | ALL | ADC raw buffer (32×u16) |
| 0xFFFF9EE6 / 0xFFFF9EE8 | 2 | IAT / Battery | Raw ADC |
| 0xFFFF9EEA | 2 | MAF | MAF raw ADC |
| 0xFFFF9EF8 | 2 | Knock | Knock ADC (pre-filter) |
| 0xFFFF9F00 | 2 | Coolant | CLT raw ADC |
| 0xFFFF9F0E | 2 | Knock | Knock ADC (fault) |
| 0xFFFF9F16 / 0xFFFF9F18 / 0xFFFF9F1E | 2 | Board / Baro / IAT | Raw ADC |
| 0xFFFF9F27/8/9 | 1 | ADC | State bytes 1/2/3 |
| 0xFFFF9F2F | 4 | ADC | Control/state regs |
| 0xFFFF9F68 / 0xFFFF9F6C | 4 / 2 | Coolant | Voltage (float) / prev ADC |
| 0xFFFF9F78 / 0xFFFF9F7C | 4 / 1 | MAF | g/s (float) / status |
| 0xFFFF9F80 | 4 | RPM | RPM reference |
| 0xFFFFA324 | 1 | Knock | Fault byte 2 |
| 0xFFFFA325 | 1 | Knock | Fault code (0/1/2) |
| 0xFFFFA328 | 4 | Knock | RPM threshold/cal |
| 0xFFFFA32C | 4 | Knock | Filter state |
| 0xFFFFA334 / 0xFFFFA348 | 4 | Knock | Rotor A threshold / filter state |
| 0xFFFFA350 / 0xFFFFA368 | 4 | Knock | Rotor B threshold / filter state |
| 0xFFFFA360 / 0xFFFFA364 | 4 | Knock | Filter gain (10.0) / secondary state |
| 0xFFFFA37C / 0xFFFFA37E | 2 | Knock | Cal copy 2 / 1 |
| 0xFFFFA384 / 0xFFFFA385 / 0xFFFFA386 | 1 | Knock | Max threshold (0xFF) / counter / fault |
| 0xFFFFA389 | 1 | Knock | Sensor ID (per-rotor) |
| 0xFFFFA3DC | 4 | Baro | Processed baro |
| 0xFFFFA424 / 0xFFFFA428 | 2 | TPS | Main raw / processed ADC |
| 0xFFFFA6AC | 4 | Speed | Raw vehicle speed (float) |
| 0xFFFFA6B0 | 4 | TPS/Speed | Filtered TPS / prev filtered speed |
| 0xFFFFA6B4 / 0xFFFFA6B8 | 4 | TPS | Prev angle / rate limit |
| 0xFFFFA6BC / 0xFFFFA6C0 | 4 | Speed | VSS coeff / rate limit |
| 0xFFFFA6CC / 0xFFFFA6D0 / 0xFFFFA6D4 / 0xFFFFA6D8 | 4 | Speed | State 1/2 / deadband / prev output |
| 0xFFFFA6B9 | 1 | Speed | Status/fault flags |
| 0xFFFFAA14 / 0xFFFFAA18 | 2 | TPS | Sub raw / processed ADC |
| 0xFFFFB600 / 0xFFFFB67A | 4 | Battery | Voltage / compensated |
| 0xFFFFB6B6 | 1 | Battery | Over-voltage flag |
| 0xFFFFB6C4 / 0xFFFFB6C8 | 4 | Battery | Intermediate / reference |
| 0xFFFFC12C | 4 | Coolant | Coolant temp (°C float) |
| 0xFFFFC5D2 / 0xFFFFC5D3 | 1 | ADC | CLT below-min / above-max |
| 0xFFFFC5D8 | 4 | Baro | Baro trim compensation |
| 0xFFFFC5EC | 1 | IAT | Threshold flag |
| 0xFFFFC5F0 | 4 | IAT | Temp (°C float) |
| 0xFFFFC5F4/5/6/8 | 1 | IAT | Over-temp / range-high / range-low / status |
| 0xAE38 | 4 | IAT | IAT voltage (alt) |
| 0xC6A8 | 4 | Board | PCM board temp |

## 8. Data Flow Summary

```
ADC HW (0xF8xx) → sensorADCRead (0x68A8) → BUFFER 0xFFFF9EE4[0..31]
  → readADCs_coolantTempInHere (0x6D00)
  → getSensorStuff loop:
       getMAFSensorValue (0x745C) → 0xFFFF9F78 (MAF g/s)
       adcIAT2Volts (0x1C8E2) → iat_sensor_3C214 (0x3C214) → 0xFFFFC5F0 (IAT °C)
       readECMVoltage (0x735C) → 0xFFFF9F68 (CLT V) → TwoDLookup → 0xFFFFC12C (CLT °C)
       getBaroSensorVal (0xD144) → 0xFFFFA3DC → calc_barometric_pressure_trim (0x13F68)
       getRearO2Voltage (0xD478) → O2 state
       knockSensorADCFault (0xC460) → fault byte; getKnockSensorADC (0xC3CE) → filtered ADC
       throttle_adc_reader (0x19FC0) → 0xFFFFA428 → calc_throttle_pos_filter (0x1345C) → 0xFFFFA6B0
       calc_vehicle_speed_filter (0x133F8) → 0xFFFFA6B0
       getBatteryVoltageStatus (0x26766) → 0xFFFFB6B6 flag
  → Post-processing: Fuel, Ignition, Lambda, Cruise Control
```

## 9. C Implementation Reference

| File | Functions | Status |
|---|---|---|
| `c/2DLookup.c` | TwoDLookup (0x2068) | Verified |
| `c/3dLookup.c` | ThreeDLookup (0x1F28) | Draft |
| `c/maf_sensor_value.c` | getMAFSensorValue (0x745C) | Verified |
| `c/baro_sensor_value.c` | getBaroSensorVal (0xD144), calc_barometric_pressure_trim (0x13F68) | Verified |
| `c/iat_sensor.c` | iat_sensor_3C214 (0x3C214), adcIAT2Volts (0x1C8E2) | Draft |
| `c/coolant_temperature_sensor.c` | readECMVoltage (0x735C), coolantVoltageToTemperature, coolant_temp_out_of_range_check (0xE50C) | Draft |
| `c/throttle_position_sensor.c` | throttle_position_adc_reader (0x19FC0), calc_throttle_position_filter (0x1345C) | Draft |
| `c/vehicle_speed_sensor.c` | calc_vehicle_speed_filter (0x133F8) | Draft |
| `c/battery_voltage_monitor.c` | getBatteryVoltageStatus (0x26766) | Draft |
| `c/o2_lambda_subsystem.c` | getRearO2Voltage (0xD478) | Verified |
| `c/knock_sensor_adc_read.c` | getKnockSensorADC (0xC3CE) | Verified |
| `c/knock_sensor_adc_fault.c` | knockSensorADCFault (0xC460) | Verified |
| `c/firstOrderFilter.c` | firstOrderFilter (0x23B0) | Verified |
| `c/checkFloatValidity.c` | checkFloatValidity (0x46CC) | Verified |

## 10. Key Findings

1. **ADC 16-bit**, scale 7.62939e-5 (= 5.0V/65536), 0–5V range.
2. **All sensor calib are 2D lookup tables** in ROM 0x6F000–0x70000 via `TwoDLookup` (0x2068).
3. **Knock dual-threshold fault:** ADC < 16121 (~1.23V) = short; ADC > 51249 (~3.91V) = open; between = valid.
4. **1st-order IIR filters** on knock and other noisy channels; gain from cal ROM.
5. **2-rotor rotary design:** two knock channels (A/B), per-rotor threshold/filter state, per-rotor sensor IDs.
6. **Common ADC scale** 7.62939e-5 (0x38A0E4 float) across channels — unified ADC interface.
7. **Main loop at RTOS task rate**, reading all sensors sequentially; fuel/ignition use updated global RAM.
8. **MAF table is 48-point** (not 14) @0x6A0E4 (**base ROM 60E1D400**; J-line descriptor @0x69E4C — see `CALIBRATION_TABLES_CROSS_REFERENCE.md` / `MAPS.md`): 0.86–4.69V → 1.95–365.2 g/s.
9. **Delta-limit filters on critical sensors:** coolant delta-limit (@0x2510) clamps per-cycle change to ±256 counts.
10. **Overlapping descriptors 0x6A0D8–0x6A0FC:** MAF (48-pt), RPM (8-pt), temp lookup (5-pt, all=100.0, possibly stub), + 8-pt table.
11. **Battery thresholds:** 10.0V over-warning w/ 1.0V hysteresis; 16.973V critical (alt regulator fail); 10.938V under (≈70% charge).
12. **Baro trim -0.02 /kPa deviation** from sea-level ref; reduces fuel/ignition at altitude.
