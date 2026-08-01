# RX-8 ECU: O2 / Lambda Sensor Processing & Closed-Loop Fuel Control Subsystem

## Overview

This document details the complete closed-loop fuel trim subsystem in the Mazda RX-8
ECU firmware (ROM 60E1D400). The ECU uses a conventional narrowband zirconia O2
sensor in the front (pre-cat) position for closed-loop fuel control, and a second
narrowband sensor in the rear (post-cat) position for catalyst efficiency monitoring.

The control flow is:

```
Front O2 Sensor (ADC) → read_o2_sensor_voltage_trim → calc_closed_loop_fuel_status
  → calc_adaptive_fuel_trim (LTFT learning)
  → Per-rotor trim correction
  → Fuel injector pulse width application
```

---

## 1. Key Functions Summary

| Address | Name | Purpose |
|---------|------|---------|
| 0x01412A | read_o2_sensor_voltage_trim | Read raw O2 sensor ADC, validate |
| 0x01418C | calc_lambda_integration_time | Integration timer for closed-loop |
| 0x0141B8 | calc_closed_loop_fuel_status | **Main STFT computation** |
| 0x014220 | sub_014220 (calc_o2_voltage_to_index_front) | Map O2 voltage to trim index (front) |
| 0x0142E8 | sub_0142E8 (calc_o2_voltage_to_index_rear) | Map O2 voltage to trim index (rear) |
| 0x01379C | calc_adaptive_fuel_trim | **LTFT adaptation & learning** |
| 0x011A34 | calc_lambda_feedback_pid | Closed-loop task dispatcher (16 jsr + 1 tail jmp); see `PID_CONTROLLERS.md` §4 |
| 0x01437C | calc_engine_temp_fuel_trim | Temperature-based fuel trim |
| 0x014496 | calc_deadband_fuel_trim | Deadband compensation |
| 0x0136F0 | calc_fuel_trim_correction_map | Per-rotor correction map |
| 0x014722 | calc_fuel_trim_correction_cyl_A | Rotor A trim application |
| 0x014742 | calc_fuel_trim_correction_cyl_B | Rotor B trim application |
| 0x00C508 | lambda_control_closed_loop | Dispatcher for closed-loop modes |
| 0x019480 | exhaust_oxygen_control_19480 | State machine for O2 sensor control |
| 0x01321C | calc_secondary_o2_trim | Secondary O2 sensor trim |
| 0x012B54 | write_o2_sensor_trim | Copy O2 sensor trim to output |
| 0x00D478 | getRearO2Voltage | Read rear O2 sensor voltage |
| 0x01E794 | getRearO2FilteredValue | Filtered rear O2 sensor reading |
| 0x01B3EA | o2_sensor_transfer_function | O2 sensor transfer characteristics |
| 0x002500 | FUN_00002500 | FMAC helper (fused multiply-accumulate) |
| 0x002404 | FUN_00002404 | Float clamp helper |
| 0x002068 | FUN_00002068 | EEPROM read / interpolation helper |
| 0x002478 | FUN_00002478 | Increment with saturation |
| 0x002460 | FUN_00002460 | Decrement with saturation |
| 0x02DDF6 | closed_loop_correction_2DDF6 | Closed-loop correction (STFT) |
| 0x02DF0A | closed_loop_correction_long_2DF0A | Closed-loop correction (LTFT) |

---

## 2. Front O2 Sensor (Pre-Catalyst)

### 2.1 Raw ADC Read: `read_o2_sensor_voltage_trim` (0x01412A)

```asm
read_o2_sensor_voltage_trim:
  mov    #0x15, r1           ; threshold = 21
  mov.w  @(0x1E,pc), r2      ; r2 = &0xA768
  mov.b  @r2, r4             ; r4 = byte from 0xA768 (O2 sensor state)
  extu.b r4, r3
  cmp/ge r1, r3              ; if r3 >= 21
  bt     skip_increment      ;   skip increment
  mov.l  @(0x26,pc), r3      ; r3 = FUN_00002478 (increment with saturation)
  jsr    @r3
  mov    #0x01, r5           ; r5 = 1 (increment amount)
  mov.w  @(0x0C,pc), r2      ; r2 = &0xA768
  mov.b  r0, @r2             ; store back
skip_increment:
  rts
```

**Logic**: Reads an O2 sensor readiness counter at RAM 0xA768. If the value is
less than 21, it increments it (capped). This counter tracks O2 sensor warm-up /
readiness state.

RAM map:
- `0xA768` (1 byte): O2 sensor readiness counter
- `0xAA10` (4 bytes): O2 sensor voltage (float)

### 2.2 Integration Time: `calc_lambda_integration_time` (0x01418C)

```asm
calc_lambda_integration_time:
  mov.l  @(0x8A,pc), r5      ; r5 = &0xFFFFA772 (timer)
  mov.l  @(0x8C,pc), r3      ; r3 = &0x00072D6C (cal: 2.5)
  mov.w  @(0x102,pc), r2     ; r2 = &0xADC8 (engine speed threshold)
  fmov.s @r3, fr3            ; fr3 = 2.5 (calibration)
  fmov.s @r2, fr2            ; fr2 = engine speed value
  fcmp/gt fr2, fr3           ; if engine_speed > 2.5?
  bt     decrement            ;   branch to decrement
  mov.l  @(0x86,pc), r1      ; r1 = &0x00072D4A (cal: 0x0007 = 7)
  mov.w  @r1, r0             ; r0 = 7
  bra    store
  mov.w  r0, @r5             ; timer = 7
decrement:
  mov.w  @r5, r4             ; r4 = timer
  extu.w r4, r1
  cmp/pl r1                  ; if timer > 0
  bf     done
  mov.l  @(0x80,pc), r1      ; r1 = 0x0000FFFF
  add    r1, r4              ; r4 = timer - 1 (decrement)
  mov.w  r4, @r5             ; store timer
done:
  rts
```

This function manages an integration timer for closed-loop operation. When the
engine speed (or related signal from 0xADC8) exceeds the calibration threshold
of 2.5 (units unknown), the timer decrements from its reload value of 7 down
to 0. When the signal drops below 2.5, the timer is reloaded to 7.

This provides a hysteresis/delay mechanism for entering/exiting closed-loop.

### 2.3 Main STFT Computation: `calc_closed_loop_fuel_status` (0x0141B8)

This is the core closed-loop fuel trim computation function. It computes the
Short-Term Fuel Trim (STFT) based on O2 sensor voltage readings.

**Disassembly:**

```asm
calc_closed_loop_fuel_status:
  fmov.s fr15, @-r15          ; save regs
  fmov.s fr14, @-r15
  fmov.s fr13, @-r15
  fldi1  fr14                 ; fr14 = 1.0 (constant)
  mov.w  @(0xD4,pc), r3       ; r3 = &0xA768 (O2 sensor ready counter)
  fldi0  fr13                 ; fr13 = 0.0 (constant)
  mov.l  @(0x76,pc), r2       ; r2 = FUN_00002500 (FMAC helper)
  fmov   fr14, fr4            ; fr4 = 1.0
  sts.l  pr, @-r15
  fmov   fr13, fr5            ; fr5 = 0.0
  jsr    @r2                  ; call FMAC helper
  mov.b  @r3, r4              ; r4 = byte from 0xA768 (O2 state)
  ; fr0 = result of helper (r4 * 1.0 + 0.0 = r4 as float)
  fmov   fr0, fr15            ; fr15 = float(O2_sensor_state)

  bsr    sub_014220           ; call O2 voltage → index mapping (front O2)
  fmov   fr0, fr4             ; fr4 = O2_sensor_state (as float)

  mov.l  @(0x70,pc), r2       ; r2 = &0xFFFFA77C (STFT output)
  fmov.s fr0, @r2             ; store STFT from sub_014220

  bsr    sub_0142E8           ; call O2 voltage → index mapping (rear O2)
  fmov   fr15, fr4            ; fr4 = O2_sensor_state (as float)

  mov.l  @(0x6E,pc), r2       ; r2 = &0xFFFFA780 (LTFT-ish output)
  fmov.s fr0, @r2             ; store result

  ; Compute the actual fuel trim correction
  mov.l  @(0x6E,pc), r4       ; r4 = &0x00072D70 (cal: 5.0)
  mov.w  @(0xB2,pc), r3       ; r3 = &0xAA10 (O2 voltage float)
  fmov.s @r4, fr3             ; fr3 = 5.0
  fmov.s @r3, fr4             ; fr4 = O2_voltage
  fsub   fr3, fr4             ; fr4 = O2_voltage - 5.0

  mov.l  @(0x6A,pc), r1       ; r1 = &0x00072D74 (cal: 60.0)
  fmov.s @r1, fr5             ; fr5 = 60.0
  mov.l  @(0x6A,pc), r2       ; r2 = &0x0003ED0C (cal table)
  jsr    @r2                  ; call calibration lookup
  fsub   fr3, fr5             ; fr5 = 60.0 - 5.0 = 55.0
  ; fr0 = result of calibration lookup

  fmov   fr0, fr4
  mov.l  @(0x68,pc), r3       ; r3 = FUN_00002404 (clamp helper)
  fmov   fr14, fr6            ; fr6 = 1.0 (upper clamp bound)
  jsr    @r3
  fmov   fr13, fr5            ; fr5 = 0.0 (lower clamp bound)
  ; fr0 = clamped value

  mov.l  @(0x5A,pc), r3       ; r3 = &0xFFFFA77C (STFT value)
  fmov   fr0, fr4
  mov.w  @(0x94,pc), r2       ; r2 = &0xA760 (STFT output bank A)
  fmov.s @r3, fr3             ; fr3 = STFT value
  mov.l  @(0x58,pc), r1       ; r1 = &0xFFFFA780 (LTFT-ish)
  fmul   fr4, fr3             ; fr3 = STFT * trim_factor
  mov.w  @(0x8E,pc), r3       ; r3 = &0xA764 (STFT output bank B)
  fmov.s fr3, @r2             ; store to 0xA760
  fmov.s @r1, fr2             ; fr2 = LTFT-ish value
  fmul   fr4, fr2             ; fr2 = LTFT-ish * trim_factor
  fmov.s fr2, @r3             ; store to 0xA764
  ; epilogue / return
```

**Simplified C code:**

```c
void calc_closed_loop_fuel_status(void) {
    volatile uint8_t  *o2_sensor_ready = (volatile uint8_t  *)0xA768;
    volatile float    *o2_voltage      = (volatile float    *)0xAA10;
    volatile float    *stft_out        = (volatile float    *)0xFFFFA77C;
    volatile float    *ltft_out        = (volatile float    *)0xFFFFA780;
    volatile float    *stft_bankA      = (volatile float    *)0xA760;
    volatile float    *stft_bankB      = (volatile float    *)0xA764;

    float o2_state = (float)(*o2_sensor_ready); // 0..21 counter
    // Calibration constants
    float cal_5_0  = *(volatile float *)0x00072D70;  // = 5.0
    float cal_60_0 = *(volatile float *)0x00072D74;  // = 60.0

    // Map O2 state to STFT and LTFT-ish values
    *stft_out = sub_014220(o2_state);   // Front O2 trim index
    *ltft_out = sub_0142E8(o2_state);   // Rear O2 trim index  ?

    // Compute voltage offset from 5.0V reference
    float voltage_offset = *o2_voltage - cal_5_0;     // range ~ -5V to +5V
    float cal_range      = cal_60_0 - cal_5_0;         // = 55.0

    // Look up trim factor from calibration table
    float trim_factor = calibration_lookup(voltage_offset, cal_range);
    // Clamp to [0.0, 1.0]
    trim_factor = clamp_float(trim_factor, 0.0f, 1.0f);

    // Apply trim factor to both banks
    *stft_bankA = *stft_out * trim_factor;
    *stft_bankB = *ltft_out * trim_factor;
}
```

### 2.4 O2 Voltage → Index Mapping (Front): `sub_014220` (0x014220)

This subroutine maps the O2 sensor state value to a trim index using a
threshold-based lookup:

```c
// Called with fr4 = o2_sensor_state (float)
float sub_014220(float o2_state) {
    volatile uint8_t *result     = (volatile uint8_t *)0xFFFFA784;
    float *threshold_table       = (float *)0x00072D78;  // [0.0, 1.0, 2.0, 3.0]
    uint8_t *index_table         = (uint8_t *)0x00072DD0; // [0x8C, 0x8C, 0x8C, ...]
    uint8_t *some_flag           = (uint8_t *)0x0006A8B9;

    // Check if o2_state > threshold_table[0] (0.0)
    if (o2_state > threshold_table[0]) {
        uint8_t max_idx = *some_flag + 0xFF;  // 0xFF is added for unsigned wrap
        max_idx = (uint8_t)max_idx; 
        // Actually: r6 = (*some_flag) + 0xFF (wrapping around)
        // The table at threshold_table uses r5 as base, indexed by shifted values

        // Search loop: find the right trim index
        for (uint8_t i = 0; i < max_idx; i++) {
            if (o2_state <= threshold_table[i]) {
                if (i+1 >= max_idx || o2_state > threshold_table[i+1]) {
                    *result = i;
                    break;
                }
            }
        }
    }
    // Look up index from index_table and interpolate
    uint8_t idx = *result;
    float result_val = index_table[idx] / 255.0f * 1.0f + 0.0f; // scaled
    return result_val;
}
```

The lookup tables at:
- `0x00072D78`: `[0.0, 1.0, 2.0, 3.0]` (voltage thresholds as float[4])
- `0x00072DD0`: `[0x8C(140), 0x8C(140), ..., 0x64(100), ...]` (output scale bytes)

The equivalent table for the rear O2 path is at:
- `0x00072DE8`: `[0.0, 1.0, 2.0, 3.0]`
- `0x00072E40`: `[0x8C(140), 0x8C(140), ..., 0x64(100), ...]`

---

## 3. Long-Term Fuel Trim (LTFT): `calc_adaptive_fuel_trim` (0x01379C)

This is the adaptive (long-term) fuel trim learning function. It reads STFT
values over time and integrates them into EEPROM-stored adaptive tables.

```asm
calc_adaptive_fuel_trim:
  mov.l  r14, @-r15
  mov.l  r13, @-r15
  fmov.s fr15, @-r15
  fmov.s fr14, @-r15
  mov.w  @(0xD8,pc), r3       ; r3 = &0xB5B8 (front O2 voltage)
  sts.l  pr, @-r15
  fmov.s @r3, fr15            ; fr15 = front O2 voltage
  mov.w  @(0xD4,pc), r2       ; r2 = &0xC12C (engine coolant temp)
  mov.l  @(0x72,pc), r4       ; r4 = &0xFFFFA728 (LTFT working store)
  fmov   fr15, fr2
  mov.l  @(0x72,pc), r13      ; r13 = FUN_00002068 (EEPROM read helper)
  fmov.s @r2, fr14            ; fr14 = coolant temp
  mov.w  @(0xCC,pc), r1       ; r1 = &0xB5C4 (reference voltage?)
  fmov.s @r1, fr3
  mov.l  @(0x70,pc), r14      ; r14 = &0xFFFFA720 (LTFT memory)
  fsub   fr3, fr2             ; fr2 = O2_voltage - reference
  mov.w  @(0xC6,pc), r0       ; r0 = &0xB5A4 (status flag)
  fmov.s fr2, @r4             ; store to working store
  mov.b  @r0, r3
  tst    r3, r3               ; if status == 0
  bf     check_mode
  ; Status == 0 path
  mov.w  @(0xBC,pc), r2       ; r2 = &0xB5AC (another flag)
  mov.b  @r2, r3
  tst    r3, r3
  bf     status_b5ac_set
  ; flag == 0: use EEPROM table 0x6A868
  mov.l  @(0x66,pc), r4       ; r4 = &0x0006A868 (EEPROM adaptive table)
  bra    do_eeprom_read
status_b5ac_set:
  ; flag == 1: use EEPROM table 0x6A87C
  mov.l  @(0x64,pc), r4       ; r4 = &0x0006A87C (EEPROM adaptive table)
do_eeprom_read:
  jsr    @r13                 ; call EEPROM read
  fmov.s fr0, @r14            ; store result to LTFT memory
  bra    check_closed_loop
check_mode:
  mov.w  @(0xA4,pc), r3       ; r3 = &0xB5AA (mode flag)
  mov.b  @r3, r0
  extu.b r0, r0
  cmp/eq #0x01, r0            ; if mode == 1
  bf     use_table2
  mov.l  @(0x58,pc), r4       ; r4 = &0x0006A868
  bra    do_eeprom_read2
use_table2:
  mov.l  @(0x56,pc), r4       ; r4 = &0x0006A87C
do_eeprom_read2:
  jsr    @r13
  fmov.s fr0, @r14            ; store to LTFT memory

check_closed_loop:
  mov.w  @(0x8C,pc), r3       ; r3 = &0xAADA (closed-loop status)
  mov.b  @r3, r0
  extu.b r0, r0
  cmp/eq #0x01, r0            ; if closed_loop == 1
  bf     skip_learning
  ; Closed-loop active - check adapt enable conditions
  mov.l  @(0x4E,pc), r2       ; r2 = &0x00072C60 (cal: 1500.0)
  fmov.s @r2, fr3
  fcmp/gt fr15, fr3           ; if O2_voltage > 1500.0?
  bf     skip_learning
  mov.l  @(0x4C,pc), r1       ; r1 = &0x00072C64 (cal: 0.009765625)
  mov.w  @(0x76,pc), r3       ; r3 = &0xC084 (another temp sensor)
  fmov.s @r1, fr2
  fmov.s @r3, fr1
  fcmp/gt fr1, fr2            ; if temp_sensor2 > 0.009765625?
  bt     force_adapt
  mov.w  @(0x6C,pc), r2       ; r2 = &0xA424 (RPM)
  mov.w  @r2, r0
  mov.l  @(0x44,pc), r1       ; r1 = &0x00072C5C (cal: RPM threshold = 375)
  mov.w  @r1, r3
  cmp/hs r3, r0               ; if RPM >= 375
  bf     skip_learning
force_adapt:
  ; Adaptation is enabled
  bra    do_adapt
  fmov.s @r14, fr15           ; fr15 = current LTFT value
skip_learning:
  fldi0  fr15                 ; fr15 = 0.0 (no adaptation)

do_adapt:
  ; Now compute the adaptive update
  mov.l  @(0x3E,pc), r3       ; r3 = &0x00072C68 (cal: 0.6 = trim limit)
  fmov.s @r3, fr5             ; fr5 = 0.6 (trim limit)
  mova   @(0x3E,pc), r0
  fmov   fr5, fr4
  mov.l  @(0x3E,pc), r4       ; r4 = &0xFFFFA730 (status byte)
  fcmp/gt fr14, fr5           ; if coolant_temp > 0.6 ?
  fmov.s @r0, fr3             ; load second threshold
  bt     check_hysteresis
  mov    #0x01, r1
  bra    store_status
  mov.b  r1, @r4              ; status = 1 (needs adaptation)
check_hysteresis:
  fcmp/gt fr14, fr4           ; if coolant_temp > fr4 (fr4 = 0.6)?
  bf     store_status
  mov    #0x00, r2
  mov.b  r2, @r4              ; status = 0

store_status:
  ; Check status
  mov.b  @r4, r0
  extu.b r0, r0
  cmp/eq #0x01, r0
  bf     skip_pi_compute
  ; Compute PI correction
  mov.l  @(0x2E,pc), r2       ; r2 = &0x00072C70 (cal: 0.7 = I gain)
  fmov.s @r2, fr6             ; fr6 = 0.7 (integral gain)
  mov.l  @(0x2E,pc), r3       ; r3 = &0x00072C6C (cal: -2.8 = P gain)
  fmov.s @r3, fr5             ; fr5 = -2.8 (proportional gain)
  mov.l  @(0x2E,pc), r1       ; r1 = FUN_00002404 (clamp helper)
  jsr    @r1
  fmov   fr15, fr4            ; fr4 = LTFT current value
  ; fr0 = PI_result = clamp(LTFT * P + I, ...)
  fmov   fr0, fr15            ; fr15 = updated LTFT

skip_pi_compute:
  mov.w  @(0x1E,pc), r3       ; r3 = &0xA718 (LTFT final output)
  fmov.s fr15, @r3            ; store LTFT
  ; epilogue / return
```

**Simplified C code:**

```c
void calc_adaptive_fuel_trim(void) {
    volatile float  *front_o2_volt  = (volatile float  *)0xB5B8;
    volatile float  *coolant_temp   = (volatile float  *)0xC12C;
    volatile float  *ref_voltage    = (volatile float  *)0xB5C4;
    volatile float  *ltft_mem       = (volatile float  *)0xFFFFA720;
    volatile float  *ltft_working   = (volatile float  *)0xFFFFA728;
    volatile float  *ltft_output    = (volatile float  *)0xA718;
    volatile uint8_t *status_A      = (volatile uint8_t *)0xB5A4;
    volatile uint8_t *status_B      = (volatile uint8_t *)0xB5AC;
    volatile uint8_t *mode_flag     = (volatile uint8_t *)0xB5AA;
    volatile uint8_t *closed_loop   = (volatile uint8_t *)0xAADA;
    volatile uint16_t *rpm          = (volatile uint16_t *)0xA424;

    // Calibration constants
    float cal_temp_lo    = *(volatile float *)0x00072C60;  // 1500.0
    float cal_temp_hi    = *(volatile float *)0x00072C64;  // 0.009765625
    float cal_trim_limit = *(volatile float *)0x00072C68;  // 0.6
    float cal_P_gain     = *(volatile float *)0x00072C6C;  // -2.8
    float cal_I_gain     = *(volatile float *)0x00072C70;  // 0.7
    uint16_t cal_rpm_min = *(volatile uint16_t *)0x00072C5C; // 375 rpm

    float o2_voltage = *front_o2_volt;
    float temp       = *coolant_temp;

    // Compute voltage offset
    float voltage_offset = o2_voltage - *ref_voltage;
    *ltft_working = voltage_offset;

    // Read from EEPROM adaptive tables
    if (*status_A == 0) {
        if (*status_B == 0)
            *ltft_mem = read_eeprom_adaptive(&0x0006A868, voltage_offset);
        else
            *ltft_mem = read_eeprom_adaptive(&0x0006A87C, voltage_offset);
    } else {
        if (*mode_flag == 1)
            *ltft_mem = read_eeprom_adaptive(&0x0006A868, voltage_offset);
        else
            *ltft_mem = read_eeprom_adaptive(&0x0006A87C, voltage_offset);
    }

    // Check if adaptation should run
    float ltft = 0.0f;
    if (*closed_loop == 1 &&
        o2_voltage > cal_temp_lo &&       // O2 voltage > 1500.0?
        (temp > cal_temp_hi ||            // temp > 0.0097 OR
         *rpm >= cal_rpm_min)) {          // RPM >= 375
        ltft = *ltft_mem;                 // enable adaptation
    }

    // Determine if temp conditions favor adaptation
    if (temp > cal_trim_limit) {
        ; // need adaptation flag set
    }

    // PI adaptive computation
    if (adaptation_needed(temp, cal_trim_limit)) {
        // P gain: -2.8, I gain: 0.7
        ltft = clamp_float(ltft * cal_P_gain + cal_I_gain,
                           -cal_trim_limit, cal_trim_limit);
    }

    *ltft_output = ltft;
}
```

---

## 4. Rear O2 Sensor (Post-Catalyst)

### 4.1 `getRearO2Voltage` (0x00D478)

Reads the rear O2 sensor ADC value and converts to voltage:

```c
void getRearO2Voltage(void) {
    volatile uint16_t *adc_addr = (volatile uint16_t *)0xFFFF9EF2;
    volatile float    *out_addr = (volatile float    *)0xFFFFA3E4;
    uint16_t adc_count = *adc_addr;
    float voltage = (float)adc_count * 7.62939e-05f;  // scale = 1/13107
    *out_addr = voltage;
}
```

The scaling factor 7.62939e-05 ≈ 1/13107 converts a 14-bit ADC reading to
voltage (5V reference / 65536 range gives ~0.076mV per count, or 1/13107 ≈
76.3µV per count, suggesting the ADC uses a ~5V reference for a 0-1V O2
signal range with voltage divider).

### 4.2 `getRearO2FilteredValue` (0x01E794)

Applies a first-order lag filter with hysteresis:

```c
void getRearO2FilteredValue(void) {
    volatile float *filtered = (volatile float *)0xFFFFB0F0;
    volatile float *threshold_lo = (volatile float *)0x00071584;
    volatile float *threshold_hi = (volatile float *)0x00071588;
    volatile float *rear_o2_raw   = (volatile float *)0xAD98;
    volatile uint8_t *flag_out    = (volatile uint8_t *)0xB0EC;
    volatile float *flag_ref      = (volatile float *)0xB0E8;

    // Apply first-order filter using FUN_000023B0
    float new_filtered = filtering_function(*filtered, *rear_o2_raw, ...);
    *filtered = new_filtered;

    // Hysteresis comparator for lean/rich detection
    if (new_filtered < *flag_ref) {
        *flag_out = 1;  // lean
    } else if (new_filtered > (*flag_ref - *threshold_hi)) {
        *flag_out = 0;  // rich
    }
    // else: maintain previous state (hysteresis)
}
```

---

## 5. Helper Utilities

### 5.1 `FUN_00002500` (FMAC Helper, 0x2500)

```c
// Fused multiply-accumulate: result = fr5 + fr4 * (uint8_t)r4
float fmac_helper(uint8_t value, float multiplier, float accumulator) {
    return accumulator + multiplier * (float)value;
}
```

### 5.2 `FUN_00002404` (Float Clamp, 0x2404)

```c
// Clamp fr4 to [fr5, fr6] and return in fr0
float clamp_float(float value, float lower, float upper) {
    if (lower > value) return lower;
    if (value > upper) return upper;
    return value;
}
```

### 5.3 `FUN_00002068` (EEPROM Read / Interpolation, 0x2068)

Reads a value from EEPROM-based lookup tables with interpolation. Uses
the FMAC helper for interpolation between table entries. The tables at
0x6A868 and 0x6A87C are adaptive fuel trim tables stored in EEPROM.

---

## 6. Calibration Tables Summary

| Address | Type | Value | Description |
|---------|------|-------|-------------|
| 0x00072C5C | uint16 | 375 | Minimum RPM for LTFT adaptation |
| 0x00072C60 | float | 1500.0 | O2 voltage threshold for adaptation enable |
| 0x00072C64 | float | 0.009765625 | Coolant temperature threshold |
| 0x00072C68 | float | 0.6 | LTFT trim limit (±60%) |
| 0x00072C6C | float | -2.8 | Proportional gain (P) |
| 0x00072C70 | float | 0.7 | Integral gain (I) |
| 0x00072D6C | float | 2.5 | Integration time calibration |
| 0x00072D4A | uint16 | 7 | Integration timer reload value |
| 0x00072D70 | float | 5.0 | O2 voltage offset reference |
| 0x00072D74 | float | 60.0 | Voltage range calibration |
| 0x00072D78 | float[] | [0.0, 1.0, 2.0, 3.0] | Front O2 threshold table |
| 0x00072DD0 | uint8[] | [0x8C,...,0x64,...] | Front O2 index→value lookup |
| 0x00072DE8 | float[] | [0.0, 1.0, 2.0, 3.0] | Rear O2 threshold table |
| 0x00072E40 | uint8[] | [0x8C,...,0x64,...] | Rear O2 index→value lookup |
| 0x0006A868 | EEPROM | - | Adaptive trim table A |
| 0x0006A87C | EEPROM | - | Adaptive trim table B |

---

## 7. RAM Variable Map

**Addressing note:** The SH-2E CPU uses `mov.w` with sign extension for PC-relative
address loads. Addresses with bit 15 set (≥0x8000) are sign-extended to the
0xFFFFxxxx on-chip peripheral RAM region. The table below lists both the raw
16-bit offset and the effective 32-bit address.

| 16-bit | Effective 32-bit | Size | Type | Description |
|--------|------------------|------|------|-------------|
| 0xA768 | 0xFFFFA768 | 1B | uint8 | O2 sensor readiness counter |
| 0xAA10 | 0xFFFFAA10 | 4B | float | Front O2 sensor voltage |
| 0xA760 | 0xFFFFA760 | 4B | float | STFT output Bank A |
| 0xA764 | 0xFFFFA764 | 4B | float | STFT output Bank B |
| 0xA718 | 0xFFFFA718 | 4B | float | LTFT output |
| 0xA77C | 0xFFFFA77C | 4B | float | Front O2 trim index |
| 0xA780 | 0xFFFFA780 | 4B | float | Rear O2 trim index |
| 0xA720 | 0xFFFFA720 | 4B | float | LTFT memory / working value |
| 0xA728 | 0xFFFFA728 | 4B | float | LTFT working store |
| 0xA730 | 0xFFFFA730 | 1B | uint8 | LTFT adaptation status flag |
| 0xA784 | 0xFFFFA784 | 1B | uint8 | Front O2 lookup result index |
| 0xA785 | 0xFFFFA785 | 1B | uint8 | Rear O2 lookup result index |
| 0xB5B8 | 0xFFFFB5B8 | 4B | float | Front O2 voltage (duplicate) |
| 0xB5C4 | 0xFFFFB5C4 | 4B | float | Reference voltage |
| 0xB5A4 | 0xFFFFB5A4 | 1B | uint8 | O2 status flag A |
| 0xB5AC | 0xFFFFB5AC | 1B | uint8 | O2 status flag B |
| 0xB5AA | 0xFFFFB5AA | 1B | uint8 | O2 mode flag |
| 0xAADA | 0xFFFFAADA | 1B | uint8 | Closed-loop active flag |
| 0xA424 | 0xFFFFA424 | 2B | uint16 | Engine RPM |
| 0xC12C | 0xFFFFC12C | 4B | float | Engine coolant temperature |
| 0xADC8 | 0xFFFFADC8 | 4B | float | Engine speed/load signal for timer |
| 0xA772 | 0xFFFFA772 | 2B | uint16 | Integration timer |
| 0x9EF2 | 0xFFFF9EF2 | 2B | uint16 | Rear O2 ADC count |
| 0xA3E4 | 0xFFFFA3E4 | 4B | float | Rear O2 voltage |
| 0xB0F0 | 0xFFFFB0F0 | 4B | float | Rear O2 filtered value |
| 0xB0EC | 0xFFFFB0EC | 1B | uint8 | Rear O2 lean/rich flag |
| 0xA8B9 | 0x0006A8B9 | 1B | uint8 | O2 lookup table size flag |
| 0xA6B7 | 0xFFFFA6B7 | 1B | uint8 | Secondary O2 trim flag A |
| 0xA6B8 | 0xFFFFA6B8 | 1B | uint8 | Secondary O2 trim flag B |
| 0xA6B9 | 0xFFFFA6B9 | 1B | uint8 | Secondary O2 trim flag C |
| 0xA9DD | 0xFFFFA9DD | 1B | uint8 | O2 control state machine state |
| 0xAD8C | 0xFFFFAD8C | 4B | float | Secondary O2 sensor voltage |
| 0xAA1C | 0xFFFFAA1C | 4B | float | Another O2-related signal |

---

## 8. Control Flow and State Machine

### 8.1 Open-Loop → Closed-Loop Transition

The ECU transitions from open-loop to closed-loop fuel control when:

1. **O2 sensor readiness counter** (0xA768) reaches 21 (incremented by
   `read_o2_sensor_voltage_trim` each cycle)
2. **Coolant temperature** (0xC12C) is above the warm-up threshold
3. **Integration timer** (0xFFFFA772) has counted down to 0 (managed by
   `calc_lambda_integration_time`)
4. **Engine speed** and **load** are within closed-loop enable range

The closed-loop active flag at `0xAADA` is set to 1 when these conditions
are met.

### 8.2 STFT Computation Cycle

Every engine control cycle:

1. Read O2 sensor voltage from ADC → `0xAA10`
2. Validate sensor readiness via counter at `0xA768`
3. Call `calc_closed_loop_fuel_status`:
   - Map O2 state to trim index (2 parallel paths: front/rear)
   - Compute trim factor from voltage offset (re: 5.0V reference)
   - Apply calibration lookup and clamp to [0, 1]
   - Multiply trim index by factor for both banks
   - Store to `0xA760` (Bank A) and `0xA764` (Bank B)
4. Call `calc_adaptive_fuel_trim`:
   - Read current adaptive trim from EEPROM tables
   - Check if adaptation conditions are met (closed-loop, temp, RPM)
   - Apply PI controller (P=-2.8, I=0.7) to LTFT
   - Clamp LTFT to ±0.6 (60%)
   - Store to `0xA718`

### 8.3 LTFT Learning Conditions

LTFT adaptation only occurs when ALL these conditions are met:
- Closed-loop active (`0xAADA == 1`)
- O2 voltage > 1500.0 (calibration `0x00072C60`)
- Either: coolant temperature > 0.0097 (cal `0x00072C64`)
- Or: engine RPM >= 375 (cal `0x00072C5C`)

### 8.4 Fail-Safe and Monitoring

The `exhaust_oxygen_control_19480` function implements a state machine
that monitors:
- O2 sensor heater status (flags at `0xA6B7`, `0xA6B8`, `0xA6B9`)
- Sensor response time
- Sensor signal plausibility

When faults are detected:
- The adaptive trim is frozen (no further learning)
- The closed-loop flag is cleared (revert to open-loop)
- DTCs are set in the diagnostic system

---

## 9. Key Calibration Observations

1. **The PI controller for LTFT uses negative proportional gain (-2.8)**:
   This is because the adaptation likely works in the reverse direction
   (a higher LTFT value means richer, so the controller needs to pull
   back). The negative P gain provides negative feedback to the system.

2. **The trim limit of 0.6 (60%)** is quite generous, allowing the
   adaptive system to compensate for large fuel system variations.

3. **The 5.0V reference offset** in the STFT computation suggests the
   O2 sensor signal is referenced to a 5V bias voltage (common in
   narrowband sensor circuits with pull-up).

4. **Integration timer reload of 7** with the threshold of 2.5 provides
   hysteresis in the closed-loop entry/exit behavior, preventing
   oscillation at the transition boundary.

5. **The lookup tables use value 0x8C (140) for rich and 0x64 (100) for
   lean** output mappings, suggesting these represent percent-scale
   values (140% and 100% of base fuel).

---

## 10. OBD-II Interface

The STFT and LTFT values are made available via OBD-II Mode 22 through:

- **`getSTFTforOBD`** (0x535A6): Reads STFT from 0xFFFFA77C, biases by
  -1.0, multiplies by 100, encodes as s8 (-128 to +127 → -100% to +99.6%)
- **`getLTFTforOBD`** (0x535CC): Reads LTFT from 0xFFFFA720, multiplies
  by 100, encodes as s8

The OBD-II PIDs are:
- PID 0x06: STFT Bank 1 - Sensor 1
- PID 0x07: LTFT Bank 1 - Sensor 1
- PID 0x08: STFT Bank 1 - Sensor 2
- PID 0x09: LTFT Bank 1 - Sensor 2

---

## 11. Open Questions

1. **EEPROM table organization**: The exact structure of the adaptive
   trim tables at 0x6A868 and 0x6A87C is not fully known. They likely
   contain trim values indexed by load/RPM cells.

2. **Per-rotor trim**: The exact mechanism by which `calc_fuel_trim_correction_cyl_A`
   and `calc_fuel_trim_correction_cyl_B` apply individual rotor trims
   needs further analysis.

3. **The rear O2 path through `calc_closed_loop_fuel_status`**: Whether
   the rear O2 sensor actually participates in fuel trim (via the second
   output path to 0xFFFFA780) or is purely for catalyst monitoring is
   uncertain.

4. **Calibration table 0x0003ED0C**: The function pointer at this address
   needs to be resolved to understand the calibration lookup algorithm.

5. **The 1500.0 threshold** for O2 voltage in LTFT adaptation seems
   unusually high. This may be a mistake in the analysis or the value
   may be interpreted differently (possibly an ECT value instead).

---

## 12. Summary Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     O2 / Lambda Subsystem                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Front O2 ADC ──► getRearO2Voltage ──► 0xFFFF9EF2/0xFFFFA3E4   │
│       │                                                          │
│       ▼                                                          │
│  read_o2_sensor_voltage_trim ──► Counter@0xA768 (warm-up)       │
│       │                                                          │
│       ▼                                                          │
│  calc_closed_loop_fuel_status                                    │
│       │                                                          │
│       ├──► sub_014220 (front O2 trim index) ──► 0xFFFFA77C      │
│       ├──► sub_0142E8 (rear O2 trim index)  ──► 0xFFFFA780      │
│       │                                                          │
│       └──► Trim factor = f(O2_voltage - 5.0V)                   │
│            STFT_BankA = trim_idx * trim_factor                   │
│            STFT_BankB = trim_idx * trim_factor                   │
│                                                                  │
│  calc_adaptive_fuel_trim                                         │
│       │                                                          │
│       ├──► EEPROM tables (0x6A868 / 0x6A87C)                    │
│       ├──► PI controller (P=-2.8, I=0.7)                        │
│       ├──► Clamp ±0.6 (60%)                                     │
│       └──► LTFT output ──► 0xA718                               │
│                                                                  │
│  calc_engine_temp_fuel_trim                                      │
│       └──► Temperature-based trim ──► 0xA788/0xA78C             │
│                                                                  │
│  calc_fuel_trim_correction_cyl_A/B                               │
│       └──► Per-rotor corrections                              │
│                                                                  │
│  exhaust_oxygen_control_19480                                    │
│       └──► State machine: heater, sensor health, DTCs            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```
