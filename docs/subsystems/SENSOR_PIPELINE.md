# RX-8 ECU Sensor Processing Pipeline

## Overview

The RX-8 ECU (Renesas SH-2E, HD64F7055) reads analog sensors via an on-chip ADC peripheral,
processes each channel through scaling/linearization, validates readings against fault
thresholds, and stores results in global RAM for use by fuel, ignition, and other subsystems.

The sensor pipeline is organized in layers:

```
┌──────────────────────────────────────────────────────────────────┐
│ 1. HARDWARE ADC READ                                            │
│    sensorADCRead (0x68A8) → readADCResult (0x6FD4)               │
│    Reads ADC hardware registers (0xF8xx), stores raw u16 values  │
│    to RAM buffer at 0xFFFF9EE4 (32 channels × 16-bit)             │
├──────────────────────────────────────────────────────────────────┤
│ 2. CHANNEL DEMULTIPLEXING                                        │
│    readADCs_coolantTempInHere (0x6D00)                            │
│    Dispatches based on ADC state register (8/4/1 channels)       │
├──────────────────────────────────────────────────────────────────┤
│ 3. MAIN SENSOR SAMPLING LOOP                                     │
│    getSensorStuff @ 0x60C8 area                                  │
│    Calls each sensor processing function in sequence             │
├──────────────────────────────────────────────────────────────────┤
│ 4. PER-SENSOR PROCESSING                                         │
│    ┌───────────────┬──────────┬────────────────────────┐         │
│    │ Sensor        │ Function │ Address                │         │
│    ├───────────────┼──────────┼────────────────────────┤         │
│    │ MAF           │ getMAFSensorValue  │ 0x745C      │         │
│    │ IAT           │ adcIAT2Volts       │ 0x1C8E2     │         │
│    │ Coolant       │ through calc chain │ 0x7398+     │         │
│    │ Baro          │ getBaroSensorVal   │ 0xD144      │         │
│    │ Knock         │ getKnockSensorADC  │ 0xC3CE      │         │
│    │ Knock Fault   │ knockSensorADCFault│ 0xC460      │         │
│    │ Rear O2       │ getRearO2Voltage   │ 0xD478      │         │
│    │ Throttle      │ (multi-stage)      │ 0x1345C+    │         │
│    │ Board Temp    │ pcmBoardTempADCtoVolts│ 0x3F158   │         │
│    └───────────────┴──────────┴────────────────────────┘         │
├──────────────────────────────────────────────────────────────────┤
│ 5. FAULT DETECTION & VALIDATION                                  │
│    checkFloatValidity (0x46CC) — IEEE 754 NaN/Inf detection      │
│    adcVoltageOutOfRangeCheck (0x3C992) — voltage bound check     │
│    sensor_check_float_bounds_adjust (0xE0DE)                     │
│    Various sensor-specific fault handlers                        │
├──────────────────────────────────────────────────────────────────┤
│ 6. FILTERING                                                     │
│    sensor_filter_apply (0x9478)                                  │
│    sensor_filter_apply_all (0x1061A)                             │
│    sensor_select_adaptive_filter_ch (0x10A9E)                    │
│    First-order IIR low-pass filters throughout                   │
├──────────────────────────────────────────────────────────────────┤
│ 7. POST-PROCESSING (fuel/ignition)                               │
│    calc_maf_sensor_flow (0x1332C)                                │
│    calc_throttle_position_filter (0x1345C)                       │
│    calc_barometric_pressure_trim (0x13F68)                       │
│    calc_lambda_feedback_pid (0x11A34)                            │
│    calc_knock_control_enable (0x14944)                           │
│    knock_detection_processing (0xF770)                           │
└──────────────────────────────────────────────────────────────────┘
```

---

## 1. ADC Hardware Layer

### 1.1 `sensorADCRead` @ 0x68A8 (0x68A8–0x6A06)

**Purpose:** Read all hardware ADC channels from the SH-2E ADC peripheral
into a RAM buffer. Configures ADC control registers, waits for conversion
complete, then reads 32 channels of 16-bit results.

**Hardware registers used:**
| Address | Description |
|---------|-------------|
| 0xF819  | ADC control register 0 |
| 0xF818  | ADC control register 1 |
| 0xF838  | ADC control register 2 |
| 0xF858  | ADC control register 3 |

**RAM output buffer:** 0xFFFF9EE4 — array of 32 × uint16_t (64 bytes total)

**References:**
- ROM 0xFFFF9F27, 0xFFFF9F28, 0xFFFF9F29: ADC state byte registers
- RAM 0xFFFF9F2F: ADC mode/state register
- 0xF800, 0xF802, 0xF804: ADC data registers (first 3 channels)

**Pseudocode:**
```c
void sensorADCRead(void) {
    // Configure ADC control registers
    // Set conversion mode and start conversion on multiple ADC units
    // Wait for conversion complete (poll status bits)
    // Read 32 × uint16_t from ADC data registers
    // Store to RAM buffer at 0xFFFF9EE4[0..31]
}
```

### 1.2 `readADCResult` @ 0x6FD4 (0x6FD4–0x7082)

**Purpose:** Higher-level ADC read wrapper that handles single-channel
conversion with wait-for-complete and status flag management.

**Inputs:**
- r4: ADC channel number (from 0x0090 encoded value)
- Calls function at 0x3920 (ADC trigger/read helper)

**Outputs:** Returns converted value in r0

**Behavior:**
1. Call ADC helper (0x3920) to trigger conversion
2. Read ADC status from 0xF858 (status register)
3. Check bit 5 (conversion complete flag)
4. If complete, clear flag and proceed
5. Read ADC result from 0xF840
6. Handle dual-channel mode with flag merging
7. Call helper at 0x3934 for post-processing
8. Return result

**Hardware registers:**
- 0xF858: ADC status register (bit 5 = conversion complete)
- 0xF859: ADC control/status
- 0xF840: ADC data register

---

## 2. ADC Channel Demultiplexing

### 2.1 `readADCs_coolantTempInHere` @ 0x6D00 (0x6D00–0x6D72)

**Purpose:** Demultiplex ADC results based on a state register that
selects between 8-channel, 4-channel, or 1-channel scan modes.

**Inputs:**
- 0xFFFF9F2F: ADC state/control register (byte at +2 offset)
- 0xFFFF9EE4: Base of ADC result buffer

**Hardware ADC registers:**
| Address | Description |
|---------|-------------|
| 0xF84E | ADC channel 0 data |
| 0xF84C | ADC channel 1 data |
| 0xF84A | ADC channel 2 data |
| 0xF848 | ADC channel 3 data |
| 0xF846 | ADC channel 4 data |
| 0xF844 | ADC channel 5 data |
| 0xF842 | ADC channel 6 data |
| 0xF840 | ADC channel 7 data |

**Behavior:**
1. Read ADC control value at 0xFFFF9F2F+2
2. If <= 0, return immediately
3. Switch on control value:
   - Case 8: Read all 8 ADC channels from 0xF84E–0xF840,
     store to RAM buffer at offsets 62, 60, 58, ... 48
   - Case 4: Read 4 channels (same pattern, fewer channels)
   - Case 1: Read 1 channel
4. Store final ADC value at buffer base + 48

**Pseudocode:**
```c
void readADCs_coolantTempInHere(void) {
    uint8_t ctrl = *(uint8_t*)(0xFFFF9F2F + 2);
    if (ctrl <= 0) return;
    
    uint16_t* adc_buf = (uint16_t*)0xFFFF9EE4;
    *(uint8_t*)(0xFFFF9F2F + 1) = 0;  // clear sub-state
    *(uint8_t*)0xFFFF9F2F = 0;        // clear main state
    
    switch (ctrl) {
    case 8:
        adc_buf[31] = *(uint16_t*)0xF84E;  // CH0
        adc_buf[30] = *(uint16_t*)0xF84C;  // CH1
        adc_buf[29] = *(uint16_t*)0xF84A;  // CH2
        adc_buf[28] = *(uint16_t*)0xF848;  // CH3
        adc_buf[27] = *(uint16_t*)0xF846;  // CH4
        adc_buf[26] = *(uint16_t*)0xF844;  // CH5
        adc_buf[25] = *(uint16_t*)0xF842;  // CH6
        adc_buf[24] = *(uint16_t*)0xF840;  // CH7
        break;
    case 4:  /* 4 channels */ break;
    case 1:  /* 1 channel  */ break;
    }
}
```

---

## 3. Main Sensor Sampling Loop

### 3.1 `getSensorStuff` @ 0x60C8

**Purpose:** Main sensor acquisition scheduler. Called periodically
from the RTOS main loop to read all analog sensors.

**Called functions (in order):**
| Address | Function Name | Purpose |
|---------|--------------|---------|
| 0x68A8 | sensorADCRead | Read all hardware ADC channels |
| 0x72A4 | sensor_state_reset_ch0 | Reset sensor state machine ch0 |
| 0x72B4 | sensor_latch_ch0 | Latch sensor ch0 value |
| 0x74D0 | (MAF processing) | Process MAF ADC |
| 0x745C | getMAFSensorValue | MAF sensor scaling/lookup |
| 0x72B4 | sensor_latch_ch0 | Re-latch ch0 |
| 0x73BC | sensor_latch_ch2 | Latch ch2 |
| 0xD3D4 | (baro processing) | Barometric sensor |
| 0xB568 | sensor_value_copy_dispatch | Copy processed values |
| 0xD478 | getRearO2Voltage | Rear O2 sensor |
| 0x753C | (fueling init) | Fueling initialization |
| 0xD9A2 | (post-processing) | Post-sensor processing |

**I/O register configuration:**
- 0xF4AB: Sensor enable mask (bits 5, 6 set)
- 0xF4A4: Sensor configuration
- 0xF4AA, 0xF4A6, 0xF4A8: Additional I/O config
- 0xF4CB, 0xF4C2: PWM/timer config for sensors

---

## 4. Per-Sensor Processing

### 4.1 MAF Sensor — `getMAFSensorValue` @ 0x745C

**Purpose:** Read Mass Air Flow sensor, apply 2D calibration lookup,
and validate against bounds.

**RAM:**
- 0xFFFF9EEA: Raw MAF ADC value (uint16_t)
- 0xFFFF9F78: Processed MAF value (float, g/s)
- 0xFFFF9F7C: MAF status flag (uint8_t: 0=OK, 1=high, 2=low)

**Calibration:**
- MAF Scaling table descriptor @ 0x6A0E4
  - count=48, type=0 (no scale/offset — returns u16 values directly)
  - Axis breakpoints @ 0x6FB18: 48 voltage values (0.859V–4.688V)
  - Values @ 0x6FBD8: 48 air flow values (1.946–365.2 g/s)
- Bounds thresholds @ 0x6CF02 (upper=64225) and 0x6CF04 (lower=2752)

**Verified MAF calibration curve (48-point):**
| ADC Voltage (V) | Air Flow (g/s) |
|-----------------|----------------|
| 0.859 | 1.95 |
| 0.977 | 2.89 |
| 1.016 | 3.25 |
| 1.055 | 3.63 |
| 1.094 | 4.05 |
| 1.133 | 4.47 |
| 1.172 | 4.92 |
| 1.211 | 5.45 |
| 1.250 | 6.00 |
| 1.289 | 6.59 |
| 1.328 | 7.22 |
| 1.367 | 7.88 |
| 1.406 | 8.61 |
| 1.484 | 10.13 |
| 1.563 | 11.76 |
| 1.641 | 13.52 |
| 1.719 | 15.47 |
| 1.797 | 17.72 |
| 1.875 | 20.17 |
| 1.953 | 22.83 |
| 2.031 | 25.76 |
| 2.109 | 29.03 |
| 2.188 | 32.58 |
| 2.266 | 36.50 |
| 2.344 | 40.78 |
| 2.422 | 45.39 |
| 2.539 | 53.04 |
| 2.656 | 61.61 |
| 2.773 | 71.01 |
| 2.891 | 81.21 |
| 3.008 | 92.18 |
| 3.125 | 103.90 |
| 3.242 | 116.47 |
| 3.359 | 129.91 |
| 3.477 | 144.31 |
| 3.594 | 159.74 |
| 3.711 | 176.24 |
| 3.828 | 193.91 |
| 3.945 | 212.89 |
| 4.063 | 233.34 |
| 4.180 | 255.13 |
| 4.297 | 278.12 |
| 4.414 | 302.48 |
| 4.492 | 319.54 |
| 4.570 | 337.28 |
| 4.609 | 346.41 |
| 4.648 | 355.72 |
| 4.688 | 365.21 |

**Constants:**
- Scale factor: 7.62939e-5 (1/13107, for 16-bit ADC to voltage)
- ADC address: 0xFFFF9EEA (MAF sensor raw ADC)
- Output address: 0xFFFF9F78 (processed g/s float)
- Status address: 0xFFFF9F7C (uint8_t: 0=OK, 1=high, 2=low)

**Pseudocode:**
```c
void getMAFSensorValue(void) {
    uint16_t maf_adc = *(uint16_t*)0xFFFF9EEA;
    
    // Scale ADC to voltage
    float maf_voltage = (float)maf_adc * 7.62939e-5f;
    
    // 2D calibration lookup (voltage → g/s)
    float maf_flow = TwoDLookup(0x6FBD8, maf_voltage);
    *(float*)0xFFFF9F78 = maf_flow;
    
    // Bounds checking
    if (maf_adc > MAF_UPPER_LIMIT)
        *(uint8_t*)0xFFFF9F7C = 1;  // Over-range high
    else if (maf_adc >= MAF_LOWER_LIMIT)
        *(uint8_t*)0xFFFF9F7C = 2;  // Over-range low
    else
        *(uint8_t*)0xFFFF9F7C = 0;  // Normal
}
```

### 4.2 Intake Air Temperature

#### 4.2.1 `adcIAT2Volts` @ 0x1C8E2

**Purpose:** Convert IAT sensor raw ADC to voltage.

**RAM:**
- 0xFFFF9F1E: IAT ADC raw value (uint16_t)
- 0xAE38: IAT voltage (float, 0–5V)

**Constants:**
- Scale: 7.62939e-5 (5V/65536 ADC counts)

**Pseudocode:**
```c
void adcIAT2Volts(void) {
    uint16_t iat_adc = *(uint16_t*)0xFFFF9F1E;
    float iat_volts = fixedPointToFloat_16bit(iat_adc, 7.62939e-5f, 0.0f);
    *(float*)0xAE38 = iat_volts;
}
```

#### 4.2.2 `iat_sensor_3C214` @ 0x3C214

**Purpose:** Full IAT sensor processing — reads ADC, applies calibration table
lookup, validates against thresholds, and writes status flags.

**RAM:**
| Address | Size | Description |
|---------|------|-------------|
| 0xFFFFC5EC | 1 | IAT threshold compare flag |
| 0xFFFFC5F4 | 1 | IAT over-temperature flag |
| 0xFFFFC5F5 | 1 | IAT range-high fault flag |
| 0xFFFFC5F6 | 1 | IAT range-low fault flag |
| 0xFFFFC5F8 | 1 | IAT combined status byte |
| 0xFFFFC5F0 | 4 | IAT processed temperature (float, °C) |

**Calibration table @ 0x7A9A8:**
- Byte 0: Threshold value for sensor comparison
- Additional calibration parameters for temperature lookup

**Constants (ROM literal pool @ 0x72D5C–0x72D64):**
| Address | Value | Description |
|---------|-------|-------------|
| 0x72D5C | 8000.0 | IAT compensation gain |
| 0x72D60 | 200.0 | IAT compensation reference |
| 0x72D64 | 0.1 | IAT compensation scale |

**Status byte encoding:**
- Bit 0: Range low fault (ADC below minimum)
- Bit 1: Range high fault (ADC above maximum)
- Bit 2: Over-temperature warning

**C implementation:** `c/iat_sensor.c`

#### 4.2.3 `calc_intake_air_temp_compensation` @ 0x13FCC

**Purpose:** Calculates IAT-based compensation multiplier for fuel/ignition.
Uses constants 8000, 200, 0.1 from ROM 0x72D5C–0x72D64.

The compensation adjusts air density calculations based on intake temperature,
applying a correction factor of approximately 1% per 10°C from reference.

### 4.3 Coolant Temperature — `calculateEngineTemperatures`

**Purpose:** Coolant temperature is processed through multiple stages:
1. Raw ADC read via `readADCs_coolantTempInHere` (0x6D00) → 0xFFFF9F00
2. Voltage conversion with rate-limiting via `readECMVoltage` @ 0x735C
3. Temperature calculation via CLT Sensor Scaling table @ 0x6F96C
4. Fault detection via `coolant_temp_out_of_range_check` @ 0xE50C
5. Bounds validation via `coolant_temp_boundary_check` @ 0x1F99A

#### 4.3.1 `readECMVoltage` @ 0x735C

**Purpose:** Read coolant temperature ADC with rate-limiting filter. Applies
a delta-limit algorithm to filter noise on the coolant temp signal.

**RAM:**
| Address | Size | Type | Description |
|---------|------|------|-------------|
| 0xFFFF9F00 | 2 | u16 | Coolant temp raw ADC (input) |
| 0xFFFF9F68 | 4 | float | Processed coolant voltage (output) |
| 0xFFFF9F6C | 2 | u16 | Previous raw ADC (for delta check) |

**Calibration constants (ROM):**
| Address | Value | Description |
|---------|-------|-------------|
| 0x6CF50 | 0x0100 (256) | Max delta threshold (ADC counts/cycle) |
| 0x6CF4C | 20.0 (float) | Voltage divider scale factor |

**Algorithm:**
1. Read current ADC from 0xFFFF9F00
2. Load previous ADC from 0xFFFF9F6C
3. Load delta threshold from 0x6CF50 (256 counts)
4. Compute delta = |current - previous|
5. If delta > threshold, clamp to previous ± threshold
6. Convert clamped ADC to voltage: V = clamped × (5.0/65536) × 20.0
7. Store voltage to 0xFFFF9F68
8. Store current ADC to 0xFFFF9F6C for next cycle

The divider factor of 20.0 accounts for the voltage divider network
in the coolant temperature measurement circuit.

**C implementation:** `c/coolant_temperature_sensor.c`

**Calibration:** CLT Sensor Scaling table @ 0x6F96C
- Temperature/voltage curve with breakpoints at:
  36.25, 39.38, 43.13, 46.88, 50.63, 55, 60, 65, 70, 76.88, 84.38, 93.75, 106.25, 123.13, 130, 140 °C

**Fault detection:** `coolant_temp_out_of_range_check` @ 0xE50C
- Upper threshold @ 0x6CF90: ~32000 counts (~2.44V, open circuit)
- Lower threshold @ 0x6CF94: ~400 counts (~0.03V, short circuit)
- Outputs: 0xFFFFC5D2 (below-min), 0xFFFFC5D3 (above-max)

### 4.4 Barometric Pressure — `getBaroSensorVal` @ 0xD144

**Purpose:** Read barometric pressure sensor, convert to float with
linearization, validate against calibration bounds.

**RAM:**
- 0xFFFF9F18: Baro ADC raw value (uint16_t)
- 0xFFFFA3DC/0xFFFFA3E0: Processed baro value (float)

**Constants:**
- Scale: 7.62939e-5
- Min threshold @ 0x6D46C: 0x0505 = 1285
- Max threshold @ 0x6D46E: 0x0505 = 1285
- Calibration values @ 0x7978C and 0x79790 (float offsets)

**Calibration tables:**
- Barometric Pressure Sensor Max ADC Count @ 0x6CF6C
- Barometric Pressure Sensor Min ADC Count @ 0x6CF6E

**Pseudocode:**
```c
uint8_t getBaroSensorVal(uint16_t* out_raw, float* out_normalized) {
    uint16_t adc = *(volatile uint16_t*)0xFFFF9F18;
    uint16_t scaled = fixedPointScaling(adc);
    *out_raw = scaled;
    
    float f_scaled = (float)scaled * 7.62939e-5f;
    float offset = *(float*)0x79790;
    float gain = *(float*)0x7978C;
    *out_normalized = offset + gain * f_scaled;
    
    if (scaled > BARO_MAX) return 1;  // Over-range high
    if (scaled >= BARO_MIN) return 0; // Valid
    return 2;  // Over-range low
}
```

### 4.5 Throttle Position Sensor

**Pipeline (multi-stage):**
1. `throttle_position_adc_reader` @ 0x19FC0 — reads TPS main ADC
2. `throttle_position_sub_adc_reader` — reads TPS sub ADC (redundant track)
3. `calc_throttle_position_filter` @ 0x1345C — applies filtering & 3D multiplier
4. `throttle_position_fault_handler` @ 0x3EEB8 — out-of-range fault handling
5. `throttlePlateSomethingFuelCut` @ 0xEBA8 — fuel cut on closed throttle

#### 4.5.1 `throttle_position_adc_reader` @ 0x19FC0

**Purpose:** Read main TPS ADC from RAM, validate against calibration limits,
and handle out-of-range conditions.

**RAM:**
| Address | Size | Description |
|---------|------|-------------|
| 0xFFFFA424 | 2 | Main TPS raw ADC (input from ADC scan) |
| 0xFFFFA428 | 2 | Main TPS processed ADC (output) |

**Algorithm:**
1. Load main TPS ADC from 0xFFFFA424
2. Compare against maximum limit from calibration table @ 0x6F9B8
3. If ADC > limit: call fault handler @ 0x3EEB8, set output to 0
4. If ADC <= limit: store ADC to 0xFFFFA428, return valid

**Fault handler @ 0x3EEB8:**
- Takes the out-of-range ADC value in r4 and float version in fr4
- Records the fault condition and sets DTC flags
- Returns with safe default value

#### 4.5.2 `calc_throttle_position_filter` @ 0x1345C

**Purpose:** Applies rate-of-change limiting and first-order filtering
to the raw TPS angle. Uses MultiMap3D tables for RPM/load-dependent
filtering characteristics.

**RAM:**
| Address | Size | Description |
|---------|------|-------------|
| 0xFFFFA6B0 | 4 | Filtered TPS angle (float, deg) |
| 0xFFFFA6B4 | 4 | Previous filtered angle |
| 0xFFFFA6B8 | 4 | Rate of change limit |

**Throttle calibration:**
- 2D lookup tables for TPS voltage → throttle angle (region 0x6F9B8–0x6F9E8)
- MultiMap3D table @ 0x6F9E8 for RPM×Load→filter_factor
- Dual-track (two ADC channels) for redundancy
- Fault detection if tracks disagree beyond threshold (P0121)

**C implementation:** `c/throttle_position_sensor.c`

### 4.6 O2 / Lambda Sensors

**Functions:**

| Function | Address | Purpose |
|----------|---------|---------|
| `getRearO2Voltage` | 0xD478 | Read rear O2 sensor raw voltage |
| `getRearO2FilteredValue` | 0x1E794 | Filtered rear O2 reading |
| `o2_target_increase_step` | 0xE4D8 | O2 target ramping |
| `calc_lambda_feedback_pid` | 0x11A34 | Closed-loop lambda PID control |
| `write_o2_sensor_trim` | 0x12B54 | Write O2 trim correction |
| `calc_secondary_o2_trim` | 0x1321C | Secondary O2 trim calculation |

**Calibration:**
- Lambda Sensor Scaling @ 0x6FD74 (6-point curve)
  - Values: 0.7586, 0.8276, 0.8966, 0.9655, 1.0, 1.0345, 1.1034, 1.1724 AFR ratio
- O2 fault DTC handlers:
  - `dtc_p0130_o2` @ 0x46DD2
  - `dtc_o2_circuit_fault` @ 0x45F54
  - `dtc_o2_response_time` @ 0x45F9C
  - `dtc_o2_slow_response` @ 0x45FA4

### 4.7 Knock Sensor

The knock sensor system is complex, with multiple functions:

| Function | Address | Purpose |
|----------|---------|---------|
| `knockFunctionInit` | 0xC31C | Initialization |
| `knockRelatedInit` | 0xC3C8 | Per-rotor init (2 rotors) |
| `knockSensorADCFault` | 0xC460 | Fault detection |
| `getKnockSensorADC` | 0xC3CE | ADC read + filter |
| `knock_detection_processing` | 0xF770 | Main detection logic |
| `write_knock_detected_flag` | 0x128C4 | Per-rotor knock flags |
| `calc_knock_control_enable` | 0x14944 | Enable conditions |
| `knock_retard_apply` | 0x23D58 | Apply ignition retard |
| `store_knock_learn_buffer` | 0xC2C0 | Store learn parameters + tail-call setSR |
| `limitKnockRetardMax_ConditionalRPM` | 0x13AE4 | RPM-dependent max retard limiting |

#### 4.7.1 `knockSensorADCFault` @ 0xC460

**Purpose:** Validate knock sensor raw ADC against bounds.
Detects open circuit (ADC too high) and short circuit (ADC too low).

**RAM:**
- 0xFFFF9F0E: Raw knock sensor ADC (uint16_t)
- 0xFFFFA325: Fault code (0=OK, 1=open circuit, 2=short circuit)

**Thresholds (ROM):**
- Max threshold @ 0x6CF7E: 0xC831 = 51249 counts (~3.91V with 5V ref)
- Min threshold @ 0x6CF7C: 0x3EF9 = 16121 counts (~1.23V with 5V ref)

```c
void knockSensorADCFault(void) {
    uint16_t adc = *(uint16_t*)0xFFFF9F0E;
    
    if (adc >= 51249)               // Open circuit (voltage rail)
        *(uint8_t*)0xFFFFA325 = 1;
    else if (adc < 16121)           // Short circuit (ground)
        *(uint8_t*)0xFFFFA325 = 2;
    else
        *(uint8_t*)0xFFFFA325 = 0;  // OK
}
```

#### 4.7.2 `getKnockSensorADC` @ 0xC3CE

**Purpose:** Read knock sensor ADC, copy to output buffer, apply
first-order low-pass filter when RPM is within the 200-2000 RPM band,
and validate RPM reference against a 10000 RPM fault limit.

**C implementation:** `c/getKnockSensorADC.c`

**RAM I/O:**
| Address | Size | Type | Description |
|---------|------|------|-------------|
| 0xFFFF9F80 | 4 | float | RPM reference |
| 0xFFFF9F0E | 2 | uint16_t | Knock sensor raw ADC (input) |
| 0xFFFFA37A | 2 | uint16_t | ADC output copy |
| 0xFFFFA374 | 4 | float | Filter state (previous output) |
| 0xFFFFA378 | 2 | uint16_t | Filtered integer output |
| 0xFFFFA386 | 1 | uint8_t | Fault byte (0=OK, 1=RPM fault) |

**Calibration constants (ROM):**
| Address | Value | Description |
|---------|-------|-------------|
| 0x78EE4 | 200.0 | Low-RPM threshold for filter activation |
| 0x78EE8 | 2000.0 | High-RPM threshold for filter deactivation |
| 0x78EEC | 0.004 | First-order IIR filter coefficient |
| 0x78EA4 | 10000.0 | RPM fault limit |

#### 4.7.3 `knockRelatedInit` @ 0xC3C8

**Purpose:** Initialize all knock detection state for 2-rotor engine.

**Initialization values:**
- Per-rotor threshold: 10.0
- Filter state: 0.0
- Max threshold byte: 0xFF
- Per-rotor sensor IDs loaded from ROM @ 0x7A164
- Calibration constants loaded from ROM @ 0x7A178, 0x7A17A, 0x7A1A4, 0x7A1D0

#### 4.7.4 `store_knock_learn_buffer` @ 0xC2C0

**Purpose:** Store two uint16 learn parameters from registers r4/r5
into RAM knock copies at 0xFFFFA370 and 0xFFFFA372, then tail-call
`setSR` to update SH-2E status register.

**C implementation:** `c/store_knock_learn_buffer.c`

**RAM I/O:**
| Address | Size | Description |
|---------|------|-------------|
| 0xFFFFA370 | 2 | Knock learn parameter 1 (uint16) |
| 0xFFFFA372 | 2 | Knock learn parameter 2 (uint16) |

#### 4.7.5 `limitKnockRetardMax_ConditionalRPM` @ 0x13AE4

**Purpose:** Select between two 2D retard-limit lookup tables based on
a condition flag and a sensor byte, then apply the limit via sqrt.

**C implementation:** `c/limitKnockRetardMax_ConditionalRPM.c`

**RAM I/O:**
| Address | Size | Description |
|---------|------|-------------|
| 0xFFFFA3B8 | 1 | Flag byte: selects table |
| 0xFFFFA3C4 | 2 | Sensor byte: second selection criterion |
| 0xFFFFA3A0 | 4 | RPM input (float) |
| 0xFFFFA3A4 | 4 | Result output (float) |

**ROM tables:**
| Address | Description |
|---------|-------------|
| 0x693CC | First 2D retard-limit lookup table |
| 0x693B8 | Second 2D retard-limit lookup table |

---

### 4.8 Vehicle Speed Sensor

**Primary function:** `calc_vehicle_speed_filter` @ 0x133F8

**Purpose:** Filter the raw vehicle speed signal from the transmission VSS
using a first-order IIR filter with rate limiting and deadband.

**RAM:**
| Address | Size | Type | Description |
|---------|------|------|-------------|
| 0xFFFFA6AC | 4 | float | Current raw speed (km/h) |
| 0xFFFFA6B0 | 4 | float | Filtered speed output (km/h) |
| 0xFFFFA6BC | 4 | float | Filter coefficient (time constant) |
| 0xFFFFA6C0 | 4 | float | Rate limit (max accel/decel per cycle) |
| 0xFFFFA6CC | 4 | float | Filter state / temp storage |
| 0xFFFFA6D0 | 4 | float | Filter state / temp storage |
| 0xFFFFA6D4 | 4 | float | Deadband (min change to update) |
| 0xFFFFA6D8 | 4 | float | Previous filter output |
| 0xFFFFA6B9 | 1 | u8 | Speed status / fault flags |

**Calibration constants:**
| Address | Value | Description |
|---------|-------|-------------|
| 0x6D470 | float | Filter coefficient (0-1) |
| 0x6D474 | float | Rate limit (km/h per cycle) |
| 0x6D478 | float | Deadband (km/h) |

**Filter function @ 0x23DC:**
Building-block function performing abs diff and min/max operations:
- Entry 0x23DC: `f0 = |fr4 - fr5|` (abs difference)
- Entry 0x23E4: `f0 = max(|fr4-fr5|, fr5)` (max of diff and threshold)
- Entry 0x23F4: `f0 = max(fr4, fr5)` (maximum)

**Algorithm:**
1. Read raw speed from pulse measurement (0xFFFFA6AC)
2. Load previous filtered speed (0xFFFFA6B0)
3. Compute rate of change: delta = raw - previous
4. Apply rate limit: clamp delta to ±VSS_RATE_LIMIT
5. Apply first-order IIR filter using VSS_FILTER_COEFF
6. Apply deadband: if |change| < VSS_MIN_DEADBAND, hold previous
7. Store filtered result and update state

**C implementation:** `c/vehicle_speed_sensor.c`

### 4.9 Battery Voltage Monitoring

**Primary function:** `getBatteryVoltageStatus` @ 0x26766

**Purpose:** Monitor battery voltage for over-voltage, under-voltage,
and charging system faults. Battery voltage affects alternator field
control, fuel pump output, and idle speed compensation.

**RAM:**
| Address | Size | Type | Description |
|---------|------|------|-------------|
| 0xFFFFB600 | 4 | float | Current battery voltage (V) |
| 0xFFFFB67A | 4 | float | Compensated battery voltage |
| 0xFFFFB6B6 | 1 | u8 | Over-voltage flag |
| 0xFFFFB6C4 | 4 | float | ADC processing intermediate |
| 0xFFFFB6C8 | 4 | float | Reference voltage for comparison |

**Calibration constants (ROM 0x751B0–0x751C4):**
| Address | Value | Description |
|---------|-------|-------------|
| 0x751B0 | 10.000 V | Over-voltage threshold high |
| 0x751B4 | 1.000 V | Over-voltage threshold low (hysteresis release) |
| 0x751C0 | 16.973 V | Critical over-voltage threshold (alternator fail) |
| 0x751C4 | 10.938 V | Under-voltage warning threshold |

**Algorithm:**
1. Load battery voltage from RAM (0xFFFFB600)
2. Compare against over-voltage threshold (10.0V):
   - If voltage > 10.0V: set over-voltage flag at 0xFFFFB6B6
   - If voltage <= 1.0V: clear flag (hysteresis prevents oscillation)
3. Check for critical over-voltage (> 16.973V):
   - If voltage exceeds this threshold, alternator regulator failure suspected
   - Triggers protection response
4. Under-voltage detection (< 10.938V):
   - System may compensate by increasing idle speed
   - Warning for battery health monitoring

**Notes:**
- 16.973V threshold suggests protection against alternator regulator failure
- 10.938V under-voltage threshold (~70% charge on 12V lead-acid)
- 1.0V hysteresis prevents oscillation around the threshold
- ADC voltage divider allows measurement of 0–20V range

**C implementation:** `c/battery_voltage_monitor.c`

### 4.10 Barometric Pressure Trim

**Primary function:** `calc_barometric_pressure_trim` @ 0x13F68

**Purpose:** Calculate barometric pressure compensation trim for
fuel and ignition adjustments based on altitude.

**Constants @ 0x72D4C–0x72D58:** All four floats = -0.02 (correction factor)

**Formula:** `trim = -0.02 × (reference_pressure - measured_pressure)`

The negative trim factor reduces fuel and ignition advance at high altitude.

### 5.0 Fault Query — `getFaultStatus` @ 0x6743C

**Purpose:** Primary fault query interface. Checks a fault channel index
and returns 0 (no fault) or 1 (fault active). Called from 78+ locations
across the ECU firmware for sensor, actuator, and subsystem fault checking.

**C implementation:** `c/getFaultStatus.c`

**RAM:**
- 0xFFFFD96C: Fault enable mask (uint32_t, runtime-configurable)

**ROM table:**
- 0x0007E4DC: Fault status table (per-channel, 32-bit entries)

**Logic:**
1. Immediate check: `(table[channel] & enable_mask)` low 16 bits → return 1
2. Secondary check: call `getFaultEvalState(channel)`, check upper 16 bits
3. Returns 0 if neither check fires

### 5.0a Memory Flag Setters

Simple helper functions that write fault/invalid flags to RAM:

| Function | Address | Writes to | Effect |
|----------|---------|-----------|--------|
| `setMemInsideFUNCto1` | 0x3E3F0 | 0xFFFFC638 | Set flag byte to 1 |
| `SetMemoryNotValid2` | 0x3E5A8 | 0xFFFFC63A | Set invalid flag to 1 |

**C implementations:** `c/setMemInsideFUNCto1.c`, `c/SetMemoryNotValid2.c`

## 5. Validation & Filtering

### 5.1 `checkFloatValidity` @ 0x46CC

**Purpose:** IEEE 754 floating-point validation. Detects NaN and
Infinity conditions.

**C implementation:** `c/checkFloatValidity.c`

**Updated analysis (60E1D400 image):**
- Writes status code to 0xFFFF7304 (not 0xFFFF768C as earlier documentation noted)
- Status codes: 0x044D = NaN, 0x044C = Infinity
- For normal/subnormal/zero floats, no status write occurs
- Returns the original float value unchanged

```c
float checkFloatValidity(float value) {
    uint32_t bits = *(uint32_t*)&value;
    
    if ((bits & 0x7F800000) == 0x7F800000) {
        // Exponent all 1s = special value
        if (bits & 0x007FFFFF) {
            *(uint16_t*)0xFFFF7304 = 0x044D;  // NaN detected
        } else {
            *(uint16_t*)0xFFFF7304 = 0x044C;  // Infinity detected
        }
    }
    // else: no status write for valid values
    return value;
}
```

### 5.2 `adcVoltageOutOfRangeCheck` @ 0x3C992

**Purpose:** Check if ADC voltage is within calibration bounds.

**ROM constants:**
- Min bound @ 0x796FC (float)
- Max bound @ 0x79700 (float)

**Output flags:**
- 0xC5D2: Below minimum flag (1 = out-of-range low)
- 0xC5D3: Above maximum flag (1 = out-of-range high)

### 5.3 Filter Functions

| Function | Address | Description |
|----------|---------|-------------|
| `sensor_filter_apply` | 0x9478 | First-order IIR filter |
| `sensor_filter_apply_all` | 0x1061A | Apply filter to all channels |
| `sensor_select_adaptive_filter_ch` | 0x10A9E | Select adaptive filter per channel |
| `firstOrderFilter` | 0x23B0 | Generic 1st-order filter: `y[n] = gain * x[n] + (1-gain) * y[n-1]` |
| `sensor_range_limit_with_accumulation` | 0x14B08 | Rate-limiter with accumulation |
| `delta_limit_filter` | 0x2510 | ADC rate-limiter: clamps delta between current/prev ADC values; used by readECMVoltage |
| `speed_abs_diff_minmax` | 0x23DC | Abs-diff + min/max building block; used by VSS filter |

---

## 6. Calibration Tables (Sensor Region)

### Sensor scaling table descriptors (ROM 0x6A0D8–0x6A100):

| Address | Count | Type | Axis Addr | Values Addr | Description |
|---------|-------|------|-----------|-------------|-------------|
| 0x6A0D8 | 5 | 0 | 0x6FAE0 | 0x6FAF4 | Temp lookup (-20°C to +20°C, all values = 100.0) |
| 0x6A0E4 | 48 | 0 | 0x6FB18 | 0x6FBD8 | **MAF Scaling** (0.86V–4.69V → 1.95–365.2 g/s) — **base ROM: 60E1D400** |
| 0x6A0F0 | 8 | 0 | 0x6FCD8 | 0x6FCF8 | RPM scaling (500–8000 RPM → 0–5000 output) |
| 0x6A0FC | 8 | 0 | 0x6FD18 | 0x6FD38 | Additional lookup table |

### Sensor threshold & constant values (ROM 0x6CF00–0x6D500):

| Address | Value | Description |
|---------|-------|-------------|
| **MAF Sensor:** | | |
| 0x6CF02 | 64225 (u16) | MAF upper threshold |
| 0x6CF04 | 2752 (u16) | MAF lower threshold |
| **Coolant Sensor:** | | |
| 0x6CF4C | 20.0 (float) | Voltage divider scale factor |
| 0x6CF50 | 0x0100=256 (u16) | ADC delta threshold for filter |
| 0x6CF90 | ~32000 (u16) | CLT upper fault threshold (~2.44V) |
| 0x6CF94 | ~400 (u16) | CLT lower fault threshold (~0.03V) |
| **Knock Sensor:** | | |
| 0x6CF7C | 16121 (u16) | Knock min threshold (~1.23V) |
| 0x6CF7E | 51249 (u16) | Knock max threshold (~3.91V) |
| **Baro Sensor:** | | |
| 0x6D46C | 1285 (u16, 0x0505) | Baro validation min |
| 0x6D46E | 1285 (u16, 0x0505) | Baro validation max |
| **Battery Voltage:** | | |
| 0x751B0 | 10.0 (float) | Over-voltage threshold high |
| 0x751B4 | 1.0 (float) | Over-voltage hysteresis release |
| 0x751C0 | 16.973 (float) | Critical over-voltage threshold |
| 0x751C4 | 10.938 (float) | Under-voltage warning threshold |
| **Barometric Trim:** | | |
| 0x72D4C–0x72D58 | -0.02 (float, ×4) | Barometric pressure correction factor |
| **IAT Compensation:** | | |
| 0x72D5C | 8000.0 (float) | IAT compensation gain |
| 0x72D60 | 200.0 (float) | IAT compensation reference |
| 0x72D64 | 0.1 (float) | IAT compensation scale |
| 0x72D68 | 0.5 (float) | IAT compensation additional factor |
| **TPS Sensor:** | | |
| 0x6F9B8 | Table descriptor | TPS limit table (count=6, type=0) |
| 0x6F9D0 | Table descriptor | TPS scalar table (count=3, type=0) |
| 0x6F9E8 | Table descriptor | TPS MultiMap3D RPM×Load table |

### Sensor 2D lookup tables (ROM 0x6F000–0x70000):

| Address | Name | Type | Values |
|---------|------|------|--------|
| 0x6CF6C | Barometric Pressure Sensor Max ADC Count | u16 | Threshold |
| 0x6CF6E | Barometric Pressure Sensor Min ADC Count | u16 | Threshold |
| 0x6CF7C | Knock Sensor Min Threshold | u16 | 16121 (~1.23V) |
| 0x6CF7E | Knock Sensor Max Threshold | u16 | 51249 (~3.91V) |
| 0x6D46C | Baro Sensor Validation Min | u16 | 0x0505=1285 |
| 0x6D46E | Baro Sensor Validation Max | u16 | 0x0505=1285 |
| 0x6F96C | CLT Sensor Scaling | 2D | 16-pt temp/voltage curve (36–140°C) |
| 0x6FBD8 | MAF Scaling values | 48× float | Air flow (1.95–365.2 g/s) |
| 0x6FB18 | MAF Scaling axis | 48× float | Voltage (0.86–4.69V) |
| 0x6FD74 | Lambda Sensor Scaling | 2D | 8-pt lambda/voltage curve (0.76–1.17 AFR) |
| 0x6FFE8 | IAT Sensor Scaling | 2D | 8-pt temp/voltage curve (23–119°C) |

### Knock-related calibration tables (ROM 0x7A000–0x7B000):

| Address | Name | Type |
|---------|------|------|
| 0x7A070 | Table 2D - 222_ | 2D |
| 0x7A164 | Per-rotor sensor IDs | u8[2] |
| 0x7A178 | Knock Sensor Cal Constant 1 | u16 (0x005E=94) |
| 0x7A17A | Knock Sensor Cal Constant 2 | u16 (0x00C1=193) |
| 0x7A1A4 | Knock Sensor Float Param | float (3.6875) |
| 0x7A1D0 | Knock Sensor Threshold | float (64.0) |
| 0x7A318 | Knock Voltage To Magnitude | 2D lookup |
| 0x7A38C | Knock Related 1 | table |
| 0x7A3E0 | Knock Related 2 | table |
| 0x7A400 | Knock Related | table |
| 0x7A408 | Knock Related 3 | table |
| 0x7A450 | Knock Rel #4 | table |
| 0x7A4D8 | Knock Rel #0 | table |
| 0x7A838 | Table 3D - 86_ | 3D (RPM × Load) |
| 0x7AC44 | Table 3D - 87_ | 3D |
| 0x7AD30 | Table 3D - 88_ | 3D |
| 0x7ADDC | Table 3D - 89_ | 3D |
| 0x7AABC | Table 3D - 122_ | 3D |
| 0x7AB58 | Table 3D - 123_ | 3D |

---

## 7. Sensor RAM Map

| Address | Size | Sensor | Description |
|---------|------|--------|-------------|
| 0xFFFF9EE4 | 64 | ALL | ADC raw buffer (32 × uint16_t) |
| 0xFFFF9EE6 | 2 | IAT | IAT sensor raw ADC |
| 0xFFFF9EE8 | 2 | Battery | Battery voltage ADC |
| 0xFFFF9EEA | 2 | MAF | MAF sensor raw ADC |
| 0xFFFF9EF8 | 2 | Knock | Knock sensor raw ADC (pre-filter) |
| 0xFFFF9F00 | 2 | Coolant | Coolant temp raw ADC |
| 0xFFFF9F0E | 2 | Knock | Knock sensor ADC (for fault detection) |
| 0xFFFF9F16 | 2 | Board | PCM board temp ADC |
| 0xFFFF9F18 | 2 | Baro | Barometric pressure ADC |
| 0xFFFF9F1E | 2 | IAT | Intake air temp ADC (alt) |
| 0xFFFF9F27 | 1 | ADC | ADC state byte 1 |
| 0xFFFF9F28 | 1 | ADC | ADC state byte 2 |
| 0xFFFF9F29 | 1 | ADC | ADC state byte 3 |
| 0xFFFF9F2F | 4 | ADC | ADC control/state registers |
| 0xFFFF9F68 | 4 | Coolant | Processed coolant voltage (float) |
| 0xFFFF9F6C | 2 | Coolant | Previous coolant raw ADC (for delta filter) |
| 0xFFFF9F78 | 4 | MAF | Processed MAF value (float, g/s) |
| 0xFFFF9F7C | 1 | MAF | MAF status (0=OK, 1=high, 2=low) |
| 0xFFFF9F80 | 4 | RPM | RPM reference (float) |
| 0xFFFFA324 | 1 | Knock | Knock fault byte 2 |
| 0xFFFFA325 | 1 | Knock | Knock fault code (0=OK, 1=open, 2=short) |
| 0xFFFFA328 | 4 | Knock | RPM threshold or calibration float |
| 0xFFFFA32C | 4 | Knock | Filter state float |
| 0xFFFFA334 | 4 | Knock | Per-rotor threshold (rotor A) |
| 0xFFFFA348 | 4 | Knock | Per-rotor filter state (rotor A) |
| 0xFFFFA350 | 4 | Knock | Per-rotor threshold (rotor B) |
| 0xFFFFA360 | 4 | Knock | Filter gain (float, typically 10.0) |
| 0xFFFFA364 | 4 | Knock | Secondary filter state |
| 0xFFFFA368 | 4 | Knock | Per-rotor filter state (rotor B) |
| 0xFFFFA37C | 2 | Knock | Knock sensor cal copy 2 |
| 0xFFFFA37E | 2 | Knock | Knock sensor cal copy 1 |
| 0xFFFFA384 | 1 | Knock | Max threshold byte (0xFF) |
| 0xFFFFA385 | 1 | Knock | Knock counter |
| 0xFFFFA386 | 1 | Knock | Fault byte |
| 0xFFFFA389 | 1 | Knock | Sensor ID (per-rotor selector) |
| 0xFFFFA3DC | 4 | Baro | Processed baro value (float) |
| 0xFFFFA424 | 2 | TPS | Main TPS raw ADC |
| 0xFFFFA428 | 2 | TPS | Main TPS processed ADC |
| 0xFFFFA6AC | 4 | Speed | Raw vehicle speed (float, km/h) |
| 0xFFFFA6B0 | 4 | TPS/Speed | Filtered TPS angle / prev filtered speed (float) |
| 0xFFFFA6B4 | 4 | TPS | Previous filtered TPS angle |
| 0xFFFFA6B8 | 4 | TPS | TPS rate of change limit |
| 0xFFFFA6BC | 4 | Speed | VSS filter coefficient (float) |
| 0xFFFFA6C0 | 4 | Speed | VSS rate limit (float) |
| 0xFFFFA6CC | 4 | Speed | VSS filter state 1 |
| 0xFFFFA6D0 | 4 | Speed | VSS filter state 2 |
| 0xFFFFA6D4 | 4 | Speed | VSS deadband (float) |
| 0xFFFFA6D8 | 4 | Speed | VSS previous output |
| 0xFFFFA6B9 | 1 | Speed | VSS status / fault flags |
| 0xFFFFAA14 | 2 | TPS | Sub TPS raw ADC |
| 0xFFFFAA18 | 2 | TPS | Sub TPS processed ADC |
| 0xFFFFB600 | 4 | Battery | Battery voltage (float, V) |
| 0xFFFFB67A | 4 | Battery | Compensated battery voltage |
| 0xFFFFB6B6 | 1 | Battery | Over-voltage flag |
| 0xFFFFB6C4 | 4 | Battery | ADC processing intermediate |
| 0xFFFFB6C8 | 4 | Battery | Reference voltage for comparison |
| 0xFFFFC12C | 4 | Coolant | Engine coolant temperature (float, °C) |
| 0xFFFFC5D2 | 1 | ADC | Coolant below-min flag |
| 0xFFFFC5D3 | 1 | ADC | Coolant above-max flag |
| 0xFFFFC5D8 | 4 | Baro | Barometric pressure trim compensation |
| 0xFFFFC5EC | 1 | IAT | IAT threshold compare flag |
| 0xFFFFC5F0 | 4 | IAT | IAT processed temperature (float, °C) |
| 0xFFFFC5F4 | 1 | IAT | IAT over-temperature flag |
| 0xFFFFC5F5 | 1 | IAT | IAT range-high fault flag |
| 0xFFFFC5F6 | 1 | IAT | IAT range-low fault flag |
| 0xFFFFC5F8 | 1 | IAT | IAT combined status byte |
| 0xAE38 | 4 | IAT | IAT voltage (alt, float) |
| 0xC6A8 | 4 | Board | PCM board temp (float) |

---

## 8. Data Flow Summary

```
ADC Hardware (0xF8xx registers)
    │
    ▼
sensorADCRead (0x68A8)  ──→  ADC RAM Buffer (0xFFFF9EE4[0..31])
    │
    ▼
readADCs_coolantTempInHere (0x6D00)
    │  (demux by state register)
    ▼
getSensorStuff loop ──┬──→ getMAFSensorValue (0x745C)       ──→ 0xFFFF9F78 (MAF g/s)
    │                  │
    │                  ├──→ adcIAT2Volts (0x1C8E2)           ──→ IAT voltage
    │                  │    └── iat_sensor_3C214 (0x3C214)   ──→ 0xFFFFC5F0 (IAT °C)
    │                  │
    │                  ├──→ Coolant temp chain:
    │                  │    ├── readECMVoltage (0x735C)       ──→ 0xFFFF9F68 (CLT V)
    │                  │    └── TwoDLookup(CLT table)        ──→ 0xFFFFC12C (CLT °C)
    │                  │
    │                  ├──→ getBaroSensorVal (0xD144)        ──→ 0xFFFFA3DC (Baro)
    │                  │    └── calc_barometric_pressure_trim (0x13F68) ──→ trim
    │                  │
    │                  ├──→ getRearO2Voltage (0xD478)        ──→ O2 trim state
    │                  │
    │                  ├──→ Knock pipeline:
    │                  │    ├── knockSensorADCFault (0xC460)  → fault byte
    │                  │    └── getKnockSensorADC (0xC3CE)    → filtered ADC
    │                  │
    │                  ├──→ Throttle position chain:
    │                  │    ├── throttle_adc_reader (0x19FC0) → 0xFFFFA428
    │                  │    └── calc_throttle_pos_filter (0x1345C) → 0xFFFFA6B0
    │                  │
    │                  ├──→ calc_vehicle_speed_filter (0x133F8) ──→ 0xFFFFA6B0
    │                  │
    │                  └──→ getBatteryVoltageStatus (0x26766) ──→ 0xFFFFB6B6 flag
    │
    ▼
Post-processing: Fuel, Ignition, Lambda Control, Cruise Control
```

---

## 9. C Implementation Reference

The following C implementations exist for sensor pipeline functions:

| File | Functions | Status |
|------|-----------|--------|
| `c/2DLookup.c` | TwoDLookup (0x2068) | Verified |
| `c/3dLookup.c` | ThreeDLookup (0x1F28) | Draft |
| `c/maf_sensor_value.c` | getMAFSensorValue (0x745C) | Verified |
| `c/baro_sensor_value.c` | getBaroSensorVal (0xD144), calc_barometric_pressure_trim (0x13F68) | Verified |
| `c/iat_sensor.c` | iat_sensor_3C214 (0x3C214), adcIAT2Volts (0x1C8E2) | Draft |
| `c/coolant_temperature_sensor.c` | readECMVoltage (0x735C), coolantVoltageToTemperature, coolant_temp_out_of_range_check (0xE50C) | Draft |
| `c/throttle_position_sensor.c` | throttle_position_adc_reader (0x19FC0), calc_throttle_position_filter (0x1345C) | Draft |
| `c/vehicle_speed_sensor.c` | calc_vehicle_speed_filter (0x133F8) | Draft |
| `c/battery_voltage_monitor.c` | getBatteryVoltageStatus (0x26766) | Draft |
| `c/o2_lambda_subsystem.c` | getRearO2Voltage (0xD478), O2 subsystem | Verified |
| `c/knock_sensor_adc_read.c` | getKnockSensorADC (0xC3CE) | Verified |
| `c/knock_sensor_adc_fault.c` | knockSensorADCFault (0xC460) | Verified |
| `c/firstOrderFilter.c` | firstOrderFilter (0x23B0) | Verified |
| `c/checkFloatValidity.c` | checkFloatValidity (0x46CC) | Verified |

## 10. Key Findings

1. **ADC is 16-bit resolution** — all raw values are uint16_t with
   scale factor 7.62939e-5 (= 5.0V / 65536), giving 0–5V input range.

2. **All sensor calibrations are 2D lookup tables** in ROM region
   0x6F000–0x70000, using the generic `TwoDLookup` function at 0x2068.

3. **Knock detection uses dual-threshold fault detection:**
   - ADC < 16121 (~1.23V) → short circuit (sensor grounded)
   - ADC > 51249 (~3.91V) → open circuit (sensor disconnected)
   - Range 16121–51249 → valid knock signal

4. **First-order IIR filters** are applied to knock sensor and other
   noisy channels, with gain/coefficient constants from calibration ROM.

5. **The sensor system is designed for a 2-rotor rotary engine:**
   - Two knock detection channels (rotor A/B)
   - Per-rotor knock threshold and filter state
   - Rotor-specific sensor IDs loaded from ROM table

6. **Common scale factor across all ADC channels:** 7.62939e-5
   (0x38A0E4 as IEEE 754 float), suggesting unified ADC interface.

7. **The main sensor loop runs at the RTOS task rate**, reading all
   sensors sequentially and updating global RAM before fuel/ignition
   calculations use the values.

8. **MAF table is 48-points (not 14):** The MAF scaling table at 0x6A0E4
   (**base ROM: 60E1D400**; the J-line variant descriptor lives at 0x69E4C —
   see `CALIBRATION_TABLES_CROSS_REFERENCE.md` / `MAPS.md`)
   contains 48 breakpoints spanning 0.86V–4.69V → 1.95–365.2 g/s, providing
   fine resolution across the entire operating range.

9. **Delta-limiting filters are used on critical sensors:** The coolant
   temperature sensor uses a delta-limit algorithm (function @ 0x2510) that
   clamps the per-cycle ADC change to ±256 counts at most. This prevents
   noise spikes from causing erroneous temperature readings.

10. **Overlapping calibration table descriptors at 0x6A0D8–0x6A0FC:**
    Four consecutive 20-byte table descriptors were discovered, covering:
    - MAF Scaling (48-point, 0x6A0E4)
    - RPM scaling (8-point, 0x6A0F0)
    - Temperature lookup (5-point, 0x6A0D8, all values = 100.0 — possibly stub)
    - Additional 8-point table (0x6A0FC)

11. **Battery voltage thresholds suggest robust charging system monitoring:**
    - 10.0V: Over-voltage detection with 1.0V hysteresis
    - 16.973V: Critical over-voltage (alternator regulator failure)
    - 10.938V: Under-voltage warning (~70% battery charge)
    The wide deadband (1V) prevents threshold oscillation.

12. **Barometric pressure trim correction is -0.02 per kPa deviation**
    from sea level reference. This negative factor reduces fuel and ignition
    at altitude, consistent with naturally aspirated engine compensation.
