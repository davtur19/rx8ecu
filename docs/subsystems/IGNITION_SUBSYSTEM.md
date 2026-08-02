# Ignition / Spark Control Subsystem

**Firmware:** 60E1D400 (RX-8 Renesis 6-speed MT)
**Processor:** Renesas SH-2E (HD64F7055)
**Update:** 2026-07-31
**Functions:** ~59 identified (38 analyzed in detail)

---

## 1. Rotary-Specific Ignition Architecture

The RX-8 Renesis (13B-MSP) has a unique ignition architecture compared to piston engines:

| Feature | Rotary | Piston Engine |
|---------|--------|---------------|
| Plugs per rotor | 2 (leading + trailing) | 1 per cylinder |
| Power strokes | 1 per rotor per e-shaft rev | 1 per 2 crank revs |
| Total plugs | 4 (2 leading, 2 trailing) | 4–16 |
| Firing order | R1 Lead → R1 Trail (few ° later) → R2 Lead → R2 Trail (180° e-shaft after R1) | L1 L2 L3 L4... |
| Angle domain | 1 rotor face-cycle = 360° e-shaft (1 rotor revolution = 3 face-cycles = 1080° e-shaft); fires every 180° e-shaft | 720° per crank cycle |
| Split (lead-trail gap) | 5–20° BTDC typical | N/A |

### Coil Configuration
- **4 coils**: 2 leading (one per rotor) + 2 trailing (one per rotor)
- **Per-e-shaft-rev firing**: each of the 4 coils fires once per e-shaft revolution —
  one leading + one trailing spark per rotor per revolution. Every firing is a real
  combustion event for that rotor (one combustion event per rotor per e-shaft rev =
  2 events/rev total). This is **not** wasted-spark: with one dedicated coil per
  rotor, no firing is "wasted" on an exhaust phase — every firing is a real
  combustion event for that rotor, unlike piston wasted-spark systems, which
  fire a pair of cylinders from one coil.
- **Dwell control**: Independent per coil, battery voltage compensated
- **Spark duration**: ~1.5–2.5 ms depending on load/RPM

### Timer Hardware
The SH-2E MTU2 (Multi-Function Timer Pulse Unit 2) provides **4 output-compare channels** used for spark control:

| Channel | Spark Role | TCNT | TIER | TCR | TSTR/TSR | TGRA | Bit Mask |
|---------|-----------|------|------|-----|----------|------|----------|
| CH 0 | Leading Rotor 1 | 0xFFFFF650 | 0xFFFFF614 | 0xFFFFF604 | 0xFFFFF602 | 0xFFFFF666 | 0x01 |
| CH 1 | Trailing Rotor 1 | 0xFFFFF654 | 0xFFFFF618 | 0xFFFFF608 | 0xFFFFF602 | 0xFFFFF666 | 0x04 |
| CH 2 | Leading Rotor 2 | 0xFFFFF652 | 0xFFFFF616 | 0xFFFFF606 | 0xFFFFF602 | 0xFFFFF666 | 0x02 |
| CH 3 | Trailing Rotor 2 | 0xFFFFF656 | 0xFFFFF61A | 0xFFFFF60A | 0xFFFFF602 | 0xFFFFF666 | 0x08 |

The channel configuration is stored in a **hardware config table** at **0xDAB4** — four 24-byte entries mapping spark index → timer registers.

---

## 2. Ignition Timing Formula

From the equinox documentation and confirmed by decompilation, the Mazda ECU computes final ignition advance as:

```
Final_BTDC = (BaseTimingFinal * CrankAngleMult)
           + ((IdleBaseFinal + IdleSpeedComp + CrankAngleTiming) * (1 - CrankAngleMult))
           + CoolantTempComp - IntakeAirTempComp

where:
  BaseTimingFinal = Leading_Base_Table(RPM, Load) 
                   + KnockRetard
                   + TemperatureCorrection
                   + AC_Retard
  
  Leading Angle = BaseTimingFinal + SplitAngle
  Trailing Angle = BaseTimingFinal
```

The **base timing** is a 3D table lookup (RPM × Load) stored in calibration ROM. Additional corrections include:

| Correction | Source | Range |
|-----------|--------|-------|
| Knock retard | Per-rotor knock detection | 0° to -10° |
| Temperature | ECT + IAT combined | ±3° |
| AC compressor | AC clutch engagement | -2° leading, -1° trailing |
| DSC/Torque management | CAN bus from EBCM | -5° to 0° |
| Idle speed compensation | RPM error × gain | ±2° |
| Cranking angle | Fixed during start | ~5° BTDC |

---

## 3. Software Architecture

### 3.1 Top-Level Call Hierarchy

```
engineControlTASK (0x11E94)
  └── engineControlCalculateTiming (0x14584)
        ├── calc_combustion_efficiency_metric (0x121F0)
        ├── calc_combustion_load_factor (0x1237C)
        ├── getKnockControlAllowed (0x13A0E)
        ├── getKnockSensorFaultedStatus (0x13A5E)
        ├── getKnockControlActive (0x13A86)
        ├── updateKnockMaxRAM (0x13B90)
        ├── calc_ignition_all_rotors_13C2C (0x13C2C)     ← Phase 1 ignition
        ├── [Phase 2: 56+ subsystem calls]
        │     ├── spark_advance_calc_main_1A0C8 (0x1A0C8)
        │     ├── load_based_spark_mapper (0x1BA2C)
        │     ├── temperature_dependent_spark_limiter (0x1BB94)
        │     ├── spark_timing_boundary_limiter (0x162E4)
        │     ├── spark_advance_limiter_19BCA (0x19BCA)
        │     ├── calc_base_ignition_timing_11A9C (0x11A9C)
        │     ├── rotor_sync_gate_state_ctrl_2100A (0x2100A)
        │     └── acCompressorLeadingTimingRetard (0x22334)
        └── [Output chain]
              ├── setupCoilOutputs (0xC98A)
              ├── ignitonSomethingCalc (0x91FE)
              ├── outputSpark1 (0x8DE6)
              ├── outputSpark2 (0x8E20)
              ├── ignitionTimingHardwareTimerSomething (0x8E60)
              └── ignitionDwellOutputInit (0x8F62)
```

### 3.2 Pipeline Flow

```
  [Calculation Layer]
  calc_ignition_all_rotors → combine base + knock + temp corrections
  spark_advance_calc_main → RPM/Load table interpolation
  load_based_spark_mapper → load-dependent advance curve
  calc_base_ignition_timing → 3D table (RPM × Load)
  rotor_sync_gate_state_ctrl_2100A → compute split angle
  
  [Boundary Layer]
  spark_timing_boundary_limiter → clamp to min/max
  spark_advance_limiter_19BCA → rate-of-change limit
  temperature_dependent_spark_limiter → ECT/IAT protection
  
  [Output Layer]
  ignitonSomethingCalc → normalize angle, wrap 720°
  outputSpark1 → program leading spark timer
  outputSpark2 → program trailing spark timer
  ignitionTimingHardwareTimerSomething → set output compare
  
  [Hardware Layer]
  setupCoilOutputs → configure MTU2 channels
  ignitionDwellOutputInit → initialize dwell PWM
  coil_charge_enabled_query → verify coil status
  coil_pwm_init → PWM duty control
```

---

## 4. Function Analysis

### 4.1 `engineControlCalculateTiming` (0x14584) — Main Timing Dispatcher

**Size:** 414 bytes (0x14584–0x14722)
**Called by:** `engineControlTASK` (0x11E94) once per scheduler tick

This is the central engine control loop — 66 sequential function calls with zero branches. It runs in two phases:

- **Phase 1** (7 calls): Context save, knock detection prep, `calc_ignition_all_rotors_13C2C`
- **Phase 2** (56+ calls): Fuel, rotor-position timing (the "cam" group in inherited
  symbol names — the RX-8 is camless), knock, DSC, throttle, sensor, and output chain

The function gates access with `getSR(16)` / `setSR()` critical sections to prevent interrupt races during timing updates.

**Confidence: high** — structure is unambiguous from 66 sequential jsr calls with no conditional branching.

---

### 4.2 `calc_ignition_all_rotors_13C2C` (0x13C2C) — Main Ignition Computation

**Size:** 208 bytes (0x13C2C–0x13CFC)
**Called by:** `engineControlCalculateTiming` Phase 1, slot 7

This function computes the **correction terms** for all rotors and combines them with the base advance value.

**Input RAM:**
| Address | Type | Description |
|---------|------|-------------|
| 0xFFFFA73C | float | Engine speed (RPM) |
| 0xFFFFA740 | u8 | Ignition enable / knock status byte |
| 0xFFFFA744 | float | Previous timing value (base advance) |
| 0xFFFFA748 | u8 | Knock sensor fault status |
| 0xFFFFA749 | u8 | Knock detected flag |
| 0xFFFFA74C | float | Scratch / intermediate |
| 0xFFFFA75C | u8 | Knock control active flag |
| 0xFFFFB5B8 | float | RPM (alternate read, filtered) |
| 0xFFFFC0C4 | u8 | Coolant temp status (warm=1) |
| 0xFFFFC0C5 | u8 | ECT correction enable |

**Calibration Table:** 1D table at **0x6B68C** (RPM-based ignition correction)

| RPM | Correction |
|-----|-----------|
| 2000 | -10.0° |
| 2500 | -10.0° |
| 3000 | -10.0° |
| 4500 | -10.0° |
| 5000 | 0.0° |

**Constants:**
| Address | Value | Purpose |
|---------|-------|---------|
| 0x0007987C | 0.0f | Zero correction |
| 0x00079890 | 2.5f | Max knock retard magnitude |
| 0x00079880 | 1.0f | Warm-up correction (default) |
| 0x00079888 | 1.0f | Alternate correction path |

**Algorithm:**
```
if knock_sensor_faulted:
    correction = 0.0
else:
    if knock_detected:
        if knock_control_active:
            correction = RPM_table_lookup(0x6B68C, RPM)
        else:
            if enabled: correction = 0.0
    else:  # no knock
        correction = 0.0

# Temperature correction
if engine_warm AND ect_enable:
    correction -= 1.0  # retard when warm

# Dispatch results
compare_select_two_float_values()
calc_fuel_pump_control_output(fr15)    → 0xFFFFA744 (trailing edge)
calc_fuel_pressure_load_compensation()  → 0xFFFFA734/0xFFFFA738 (ignition timing
                                          values, written identically)

```

**Output RAM:**
| Address | Description |
|---------|-------------|
| 0xFFFFA744 | Main ignition advance (float, °BTDC) |
| 0xFFFFA734/0xFFFFA738 | Ignition timing values (float, °BTDC) — written identically by calc_ignition_all_rotors_13C2C; the lead/trail split is NOT applied in split_selector_state_ctrl_487DC either (VERIFIED 2026-08-01, emulator 500k inputs 0 mismatches: it is a gated state selector -> u8@0xFFFFCCD2 decoded by split_selector_decoder_48C12; 0x2100A is a cold/validity state controller). **SPLIT ANSWER 2026-08-02:** A734/A738 are also written identically (f32, same value) by calc_fuel_injection_all_rotors (0x13D3C); exhaustive ROM literal scan shows NO function writes them differently — readers are write_knock_detected_flag (0x128C4, reads A734), write_rotor_A_knock_flag (0x128FE, reads A738), updateKnockMaxRAM (0x13B90, reads A734). Lead/trail differentiation NOT FOUND in the analyzed functions; **open item**. |
| 0xFFFFA75C | Knock control active flag (saved back) |

**Confidence: high** — all control paths fully traced.

---

### 4.3 `calc_base_ignition_timing_11A9C` (0x11A9C) — Base Timing Table Interpolation

**Size:** 212 bytes (0x11A9C–0x11B70)
**Called by:** `engineControlCalculateTiming` Phase 2

Performs 3D table lookup (RPM × Load) for base ignition timing, then applies axis scaling. The table format uses the standard SH-2E 3D lookup:

```
base_angle = ThreeDLookup(table_0x??????, rpm, load)
base_angle = base_angle * scale + offset
```

The result is stored as the base timing before corrections are applied.

**Confidence: medium** — table addresses need verification from calibration data.

---

### 4.4 `spark_advance_calc_main_1A0C8` (0x1A0C8) — Main Spark Advance Calculation

**Size:** 850 bytes (0x1A0C8–0x1A41A)
**Called by:** `engineControlCalculateTiming` Phase 2

This is the **largest** spark-related function. It performs:

1. **Load RPM-based advance** from table at literal-pool reference
2. **Check enable conditions** — verifies knock control enabled, sensor valid
3. **Apply torque management** — DSC/TCM torque reduction requests
4. **Rate limiting** — prevents spark angle from jumping excessively between ticks
5. **Store final values** to rotor-specific RAM locations

Key constants discovered:
- Float min/max limits for advance angle bounds
- RPM thresholds for enabling different correction curves

**Confidence: medium** — control flow is clear but table addresses need confirmation.

---

### 4.5 `outputSpark1` (0x8DE6) — Program Leading Spark Timer

**Size:** 58 bytes (0x8DE6–0x8E20)
**Called by:** Output chain

**SuperH assembly (annotated):**
```asm
outputSpark1:
    mov   #4, r0               ; offset 4 for float on stack
    mov.l L_008ebc, r3         ; r3 = getSR function @ 0x3920
    sts.l pr, @-r15
    add   #-12, r15            ; 12 bytes stack frame
    mov.b r4, @r15             ; save spark_index
    fmov.s fr4, @(r0, r15)     ; save dwell_time at sp+4
    jsr   @r3                  ; call getSR(16)
    mov   #16, r4              ; param: interrupt mask level
    mov.l r0, @(8, r15)        ; save SR to sp+8
    mov.b @r15, r4             ; reload spark_index
    mov   #4, r0
    mov.l L_008eb8, r3         ; r3 = spark state base @ 0xFFFFA0D8
L_008dfe:
    extu.b r4, r4              ; zero-extend spark_index
    fmov.s @(r0, r15), fr3     ; load dwell_time from stack
    shll2 r4                   ; index *= 4
    shll  r4                   ; index *= 2 (total: *8)
    add   r3, r4               ; r4 = spark_state_base + spark_index * 8
    fmov.s fr3, @r4            ; store dwell_time at offset +0
    mov   #0, r0
    mov.b r0, @(5, r4)         ; clear offset +5 (enable flag)
    mov   #2, r0
    mov.b r0, @(4, r4)         ; set offset +4 = 2 (output arm)
    bsr   L_0091fe             ; call ignitonSomethingCalc(spark_index)
    mov.b @r15, r4
    mov.l @(8, r15), r4        ; restore SR
    mov.l L_008ec0, r3         ; r3 = setSR @ 0x3934
    add   #12, r15
    jmp   @r3                  ; tail-call setSR(SR)
    lds.l @r15+, pr
```

**Semantics:**
```c
void outputSpark1(uint8_t spark_index, float dwell_time) {
    uint32_t sr = getSR(16);   // disable interrupts
    // Spark state array: 8 bytes per channel at 0xFFFFA0D8
    volatile struct {
        float dwell_time;      // +0: timer compare value
        uint8_t arm_flag;      // +4: 2 = arm output compare
        uint8_t enable_flag;   // +5: 0 = enabled
    } *spark = (void*)(0xFFFFA0D8 + spark_index * 8);
    
    spark->dwell_time = dwell_time;
    spark->enable_flag = 0;     // clear enable
    spark->arm_flag = 2;        // arm the output compare channel
    
    ignitonSomethingCalc(spark_index);  // normalize angle
    setSR(sr);                  // restore interrupts
}
```

**Spark State Array Structure** (base 0xFFFFA0D8):
| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| +0 | 4 | float | Timer compare value (dwell end time) |
| +4 | 1 | u8 | Arm flag: 2 = armed, 0 = idle |
| +5 | 1 | u8 | Enable flag: 0 = enabled, non-zero = disabled |
| +6 | 1 | u8 | Fire request / completion flag |

**Data values:**
- `L_008eb8` = 0xFFFFA0D8 (spark state array base)
- `L_008ebc` = 0x00003920 (getSR function)
- `L_008ec0` = 0x00003934 (setSR function)

**Confidence: high** — all instructions traced, data values confirmed from ROM.

---

### 4.6 `outputSpark2` (0x8E20) — Program Trailing Spark Timer

**Size:** 64 bytes (0x8E20–0x8E60)
**Called by:** Output chain

Similar to `outputSpark1` but uses **16-byte** struct stride and only writes if the `arm_flag == 2`:

```c
void outputSpark2(uint8_t spark_index, float timing_angle) {
    uint32_t sr = getSR(16);
    volatile struct {
        float timing;          // +0
        uint8_t control;       // +4: 2 = armed
        uint8_t unknown;       // +5
        uint8_t fire_flag;     // +6
    } *spark = (void*)(0xFFFFA0D8 + spark_index * 16);
    
    if (spark->control == 2) {
        spark->timing = timing_angle;
    }
    spark->fire_flag = 0;
    ignitonSomethingCalc(spark_index);
    setSR(sr);
}
```

Key difference from `outputSpark1`: uses 16-byte stride instead of 8-byte. This suggests trailing spark channels have more state (possibly dual-output or per-rotor-secondary data).

**Confidence: high** — conditional write pattern is clear.

---

### 4.7 `ignitionTimingHardwareTimerSomething` (0x8E60) — MTU2 Output Compare Setup

**Size:** 190 bytes (0x8E60–0x8F1E)
**Called by:** Timer ISR path

This is the **most complex** hardware-level function. It configures the MTU2 output-compare channel and fires the coil.

```c
void ignitionTimingHardwareTimerSomething(uint8_t spark_id) {
    uint32_t sr = getSR(16);
    
    // Spark state at base + spark_id * 8
    volatile uint8_t *state = (uint8_t*)0xFFFFA0D8 + spark_id * 8;
    
    if (!state[5]) {  // enable_flag == 0?
        state[4] = 0;  // clear arm
        state[5] = 0;  // clear enable
        setSR(sr);
        return;
    }
    
    // Load channel config from table at 0xDAB4
    // Each entry is 24 bytes, indexed by spark_id
    struct ChanCfg {
        uint16_t *tcnt;       // +0: Timer counter register
        uint16_t *tier;       // +4: Timer interrupt enable reg
        uint16_t *tcr;        // +8: Timer control register
        uint16_t *tsr;        // +12: Timer status register
        uint16_t *tgra;        // +16: Timer general register A
        uint16_t enable_bits; // +20: Channel enable bitmask
    } *cfg = (struct ChanCfg*)(0xDAB4 + spark_id * 24);
    
    uint16_t current_timer = *cfg->tcnt;
    uint16_t expected_time = *(uint16_t*)(cfg->tier); // actually timing value
    int32_t delta = expected_time - (current_timer + 3);
    
    if (delta < 0) {
        // Timing window has passed — skip fire
        setSR(sr);
        return;
    }
    
    // Check enable bits: read from tcr and verify against bitmask
    uint16_t en_bits = *cfg->tcr;
    if (en_bits & cfg->enable_bits) {
        // Channel not enabled? Skip
        setSR(sr);
        return;
    }
    
    // Fire the coil
    FUN_0000AA74(cfg->tcnt);  // write timer value, trigger output
    
    // Clear control flags
    state[4] = 0;
    state[5] = 0;
    
    setSR(sr);
}
```

**Data values confirmed:**
- `L_008eb8` = 0xFFFFA0D8 (spark state base)
- `L_008ebc` = 0x00003920 (getSR)
- `L_008fb4` = 0x0000DAB4 (channel config table)
- `L_008fb8` = 0x0000AA74 (coil fire helper)
- `L_008fbc` = 0x00003934 (setSR)

**Confidence: high** — full path traced, register addresses verified against SH-2E MTU2 map.

---

### 4.8 `ignitonSomethingCalc` (0x91FE) — Angle Normalization

**Size:** 582 bytes (0x91FE–0x9444)
**Called by:** `outputSpark1`, `outputSpark2`, hardware timer path

This function normalizes the spark timing angle and handles 720° wrapping for the rotary engine.
(720° here is the software's scheduling angle-domain window, inherited from the generic
4-stroke codebase this ROM shares — physically the rotary fires every 180° of eccentric-shaft
rotation, 2 events/rev, and one rotor face completes its 4 phases per rotor revolution =
1080° of e-shaft.)

```c
void ignitonSomethingCalc(uint8_t rotor_idx) {
    float ref_angle = *(float*)0xFFFFA0FC;     // reference angle
    float *timing = (float*)(0xFFFFA0D8 + rotor_idx * 24); // rotor timing
    float *output = (float*)0xFFFFA0F8;        // normalized output
    
    float delta = *timing - ref_angle;
    
    // Rotary angle wrapping: normalize to [-90, 630) 
    if (delta < -90.0f) {      // L_00924c = -90.0
        delta += 720.0f;        // L_009250 = 720.0
    } else if (delta >= 630.0f) { // L_009254 = 630.0
        delta -= 720.0f;        // L_009258 = -720.0
    }
    
    *output = delta;
    
    // Check secondary flag at offset +5
    uint8_t *flags = (uint8_t*)(0xFFFFA0D8 + rotor_idx * 24);
    if (flags[5] == 0) {
        // Normal path: check if delta > 60°, call special handler
        if (delta > 60.0f) {
            call_rotor_specific_logic(rotor_idx);  // @ 0x9440
        }
    }
}
```

**Constants confirmed from ROM:**
| Label | Address | Value | Meaning |
|-------|---------|-------|---------|
| L_009244 | 0x9244 | 0xFFFFA0D8 | Per-rotor timing array base |
| L_009248 | 0x9248 | 0xFFFFA0FC | Reference angle (current crank pos?) |
| L_00924c | 0x924C | -90.0f | Min valid delta |
| L_009250 | 0x9250 | 720.0f | Full cycle (rotary = 720° crank) |
| L_009254 | 0x9254 | 630.0f | Max valid delta |
| L_009258 | 0x9258 | -720.0f | Negative full cycle |
| L_009274 | 0x9274 | 0xFFFFA0F8 | Normalized timing output |

**Confidence: high** — all constants confirmed, wrapping logic is standard rotary.

---

### 4.9 `setupCoilOutputs` (0xC98A) — MTU2 Channel Configuration

**Size:** 208 bytes (0xC98A–0xCA5A)
**Called by:** `engineControlCalculateTiming` Phase 2

Configures the MTU2 timer channels for output-compare operation. Key operations:

1. **Configure I/O pin** at 0xFFFF9F34 — set bit 6, clear bit 5 (output compare mode)
2. **Calculate RPM-to-timer conversion factor** using 1152.0 constant (likely timer clock prescaler)
3. **Load min/max timing window** from registers at 0xFFFFA37C and 0xFFFFA37E
4. **Write dwell boundaries** to hardware registers
5. **Set PWM output control** via register 0xFFFF9F34 (bits 0-1 select output function)

```c
void setupCoilOutputs(void) {
    // Configure MTU2 I/O pin for output compare
    volatile uint8_t *io_reg = (uint8_t*)0xFFFF9F34;
    *io_reg = (*io_reg & 0xBF) | 0x40;  // set bit 6, clear bit 5
    
    // Calculate conversion factor
    float engine_speed = *(float*)0xFFFF9F88;  // RPM
    float timer_clock = 1152.0f;  // timer clock frequency (scaled)
    float conv_factor = engine_speed / timer_clock;
    
    // Read hardware min/max compare values
    uint16_t min_window = *(uint16_t*)0xFFFFA37E;
    uint16_t max_window = *(uint16_t*)0xFFFFA37C;
    
    // Configure output compare and PWM
    // ...
    
    // Set output control bits
    *io_reg = (*io_reg & 0xFC) | output_bits;
}
```

**Data values:**
| Label | Address | Value |
|-------|---------|-------|
| L_00ca78 | 0xCA78 | 0xFFFF9F34 (I/O control reg) |
| L_00ca7c | 0xCA7C | 0x000071AC (adc_read_and_merge_flags) |
| L_00ca80 | 0xCA80 | 0xFFFF9F88 (engine speed) |
| L_00ca84 | 0xCA84 | 1152.0f (timer clock) |
| L_00ca88 | 0xCA88 | 0xFFFF9F9C (RPM value) |
| L_00ca8c | 0xCA8C | 0xFFFFA37E (min window) |
| L_00ca90 | 0xCA90 | 0x4F000000 (2^31, for fixed-point conv) |
| L_00ca94 | 0xCA94 | 0xFFFFA37C (max window) |
| L_00ca98 | 0xCA98 | 0x00002054 (setSR_PARAM) |

**Confidence: medium** — overall flow clear, exact register names need SH-2E manual verification.

---

### 4.10 `ignitionDwellOutputInit` (0x8F62) — Dwell Initialization

**Size:** 80 bytes (0x8F62–0x8FB2)
**Called by:** Output chain during startup

Initializes the spark state array and clears all coil control flags:

```c
void ignitionDwellOutputInit(void) {
    uint32_t sr = getSR(16);
    
    // Initialize all 4 spark channels (0-3)
    for (int i = 0; i < 4; i++) {
        volatile uint8_t *state = (uint8_t*)0xFFFFA0D8 + i * 8;
        state[4] = 0;  // clear arm flag
        state[5] = 0;  // clear enable flag
    }
    
    // Clear additional state
    *(uint32_t*)0xFFFFA100 = 0;
    
    setSR(sr);
}
```

**Confidence: high** — simple loop, all writes traced.

---

### 4.11 `ignition_advance_limiter` (0xE38C) — Advance Rate Limiter

**Size:** 176 bytes (0xE38C–0xE43C)

Limits the rate of change of ignition advance to prevent sudden jumps:

```c
float ignition_advance_limiter(float desired_advance, float current_advance) {
    float max_rate = getRateLimit();  // from calibration
    float delta = desired_advance - current_advance;
    
    if (delta > max_rate) {
        delta = max_rate;  // retard limit
    } else if (delta < -max_rate) {
        delta = -max_rate;  // advance limit
    }
    
    return current_advance + delta;
}
```

**Confidence: medium** — pattern matches rate limiting, exact calibration source TBD.

---

### 4.12 `coil_pwm_init` (0xE37C) — PWM Coil Driver Init

**Size:** 16 bytes (0xE37C–0xE38C)

Writes a constant to control register to initialize PWM mode for coil drivers:

```c
void coil_pwm_init(void) {
    *(uint8_t*)0xFFFFA100 = coil_pwm_value;  // initial PWM duty
}
```

**Confidence: medium** — very short, purpose inferred.

---

### 4.13 `coil_charge_enabled_query` (0xE450) — Coil Status Check

**Size:** 26 bytes (0xE450–0xE46A)

Tests whether the coil charge circuit is enabled:

```c
bool coil_charge_enabled_query(void) {
    uint8_t status = *(uint8_t*)0xFFFFA0D8;  // status byte
    return (status & 0x01) != 0;
}
```

**Confidence: medium** — bit test on status register.

---

### 4.14 `rotor_sync_gate_state_ctrl_2100A` (0x2100A) — Split Angle Control

**Size:** 352 bytes (0x2100A–0x2116A)

> STATUS 2026-08-01: Lifted and VERIFIED against the ROM emulator (500,000 random inputs, 0 mismatches; see c/rotor_sync_gate_state_ctrl_2100A.c and c/tests/test_rotor_sync_gate_state_ctrl_2100A.py). Despite the IDA name, this function does NOT compute a split angle and does NOT touch A734/A738. It manages a cold/validity flag u8@0xFFFFB240 and two state floats f32@0xFFFFB18C / f32@0xFFFFB188 (set to 1.0 together, decayed independently as max(state − 0.0667, 0.0), or cleared together) gated by temperature hysteresis, engine-off/enable/cal flags, and the shared max helper @0x23E4. A734 == A738 in practice (written identically by calc_ignition_all_rotors_13C2C). The actual lead/trail split is NOT implemented here; see split_selector_state_ctrl_487DC for further analysis.

Determines whether leading-trailing spark split is applied. Checks:
1. **Engine running** — RPM above threshold
2. **Temperature** — ECT in valid range
3. **Load condition** — not in overrun fuel cut
4. **AC status** — AC clutch engaged
5. **Knock status** — no active knock

If conditions met, computes split angle from calibration table:

```
leading_angle  = base_angle + split_angle / 2
trailing_angle = base_angle - split_angle / 2
```

If conditions not met (cold start, overrun, knock), both plugs fire at the same angle (split = 0).

**Confidence: medium** — conditions identified, exact table computation needs more analysis.

---

### 4.15 `load_based_spark_mapper` (0x1BA2C) — Load-Dependent Advance

**Size:** 360 bytes (0x1BA2C–0x1BB94)

Maps engine load to spark advance using a piecewise linear function. Higher loads typically require less advance (more retard) to prevent knock.

**Confidence: medium** — mapping pattern standard, exact breakpoints TBD.

---

### 4.16 `temperature_dependent_spark_limiter` (0x1BB94) — Thermal Protection

**Size:** 282 bytes (0x1BB94–0x1BCAE)

Reduces ignition advance when coolant or intake air temperatures are extreme:
- **Cold engine**: Increase advance for stable combustion
- **Hot engine**: Reduce advance to prevent knock
- **High IAT**: Reduce advance progressively

**Confidence: medium** — standard thermal protection strategy.

---

### 4.17 `spark_timing_boundary_limiter` (0x162E4) — Min/Max Clamping

**Size:** 386 bytes (0x162E4–0x16466)

Clamps final ignition advance to calibration-defined boundaries:

```
if (advance > max_advance)  advance = max_advance;
if (advance < min_advance)  advance = min_advance;
```

Min/max values vary by RPM and load condition. The safe-mode limits provide reduced performance during sensor failures.

**Confidence: medium** — clamp logic standard, exact boundaries calibration dependent.

---

### 4.18 `spark_advance_calc_0x16BE8` (0x16BE8) — RPM-Based Advance

**Size:** 162 bytes (0x16BE8–0x16C8A)

Interpolates base advance from RPM-only table (no load axis). Used as a fallback or for specific operating modes.

**Confidence: low** — short function, purpose inferred.

---

### 4.19 `calc_spark_advance_offset_map` (0x148A8) — Offset Map

**Size:** 102 bytes (0x148A8–0x1490E)

Applies per-rotor offsets to the base spark advance. These offsets provide fine tuning for:
- Rotor-to-rotor variation compensation
- Wear compensation
- Adaptive learning (long-term trim)

**Confidence: low** — offset logic assumed from function name.

---

### 4.20 `calc_ignition_system_diagnostics` (0x1490E) — Diagnostic Monitor

**Size:** 54 bytes (0x1490E–0x14944)

Checks ignition system health:
- Coil primary circuit continuity
- Spark plug firing detection (ion sense or secondary current)
- DTC reporting for ignition faults

**Confidence: low** — diagnostic nature assumed from name, needs verification.

---

### 4.21 `acCompressorLeadingTimingRetard` (0x22334) / `acCompressorTrailingTimingRetard` (0x22434)

**Size:** 194 bytes each

When the AC compressor engages, these functions retard the ignition timing to compensate for the additional load:
- **Leading retard**: ~2° retard typical
- **Trailing retard**: ~1° retard typical

The retard is applied gradually (ramp function) to avoid drivability issues.

**Confidence: medium** — paired functions, pattern matches AC load compensation.

---

## 5. Spark State Data Structures

### 5.1 Spark State Array (0xFFFFA0D8)

The spark state is stored in a **global array** starting at 0xFFFFA0D8. Each channel has either 8-byte or 16-byte alignment depending on function:

**8-byte channel struct** (used by `outputSpark1`, `ignitionTimingHardwareTimerSomething`):
```
Offset  Size  Field
+0      4     dwell_time / timer_compare (float)
+4      1     control_arm (0=idle, 2=armed)
+5      1     enable_flag (0=enabled)
+6      1     fire_flag / status
+7      1     padding
```
Total: 8 bytes. Channels 0-3 occupy 0xFFFFA0D8-0xFFFFA0F7.

**16-byte channel struct** (used by `outputSpark2`):
```
Offset  Size  Field
+0      4     timing_angle (float)
+4      1     control (0=idle, 2=armed)
+5      1     unknown
+6      1     fire_req (0=no request, 1=fire requested)
+7      1     padding
+8      8     extra state (per-channel extension)
```
Total: 16 bytes. Channels 0-1 occupy 0xFFFFA0D8-0xFFFFA0F7.

### 5.2 Rotor Timing Array (0xFFFFA0D8, alternate view)

When indexed by rotor:
```
Offset  Size  Field
+0      4     timing_angle (float, °BTDC)
+4      1     control_flags
+5      1     secondary_enable
+6      1     padding
+7      1     padding
```
Each rotor entry is 24 bytes apart (per-function constant).

### 5.3 Channel Config Table (0xDAB4)

Four 24-byte entries mapping spark channel index to MTU2 hardware registers:

```
Offset  Size  Field                    Example (Ch0)
+0      4     Timer counter (TCNT)     0xFFFFF650
+4      4     Timer interrupt (TIER)   0xFFFFF614
+8      4     Timer control (TCR)      0xFFFFF604
+12     4     Timer status (TSR)       0xFFFFF602 (shared)
+16     4     Timer gen reg A (TGRA)   0xFFFFF666
+20     4     Channel bit mask         0x01000000 (bit 0 in TSTR)
```

| Index | Spark | TCNT | TIER | TCR | TSR | TGRA | Bit mask |
|-------|-------|------|------|-----|-----|------|----------|
| 0 | Leading R1 | 0xFFFFF650 | 0xFFFFF614 | 0xFFFFF604 | 0xFFFFF602 | 0xFFFFF666 | 0x01 |
| 1 | Trailing R1 | 0xFFFFF654 | 0xFFFFF618 | 0xFFFFF608 | 0xFFFFF602 | 0xFFFFF666 | 0x04 |
| 2 | Leading R2 | 0xFFFFF652 | 0xFFFFF616 | 0xFFFFF606 | 0xFFFFF602 | 0xFFFFF666 | 0x02 |
| 3 | Trailing R2 | 0xFFFFF656 | 0xFFFFF61A | 0xFFFFF60A | 0xFFFFF602 | 0xFFFFF666 | 0x08 |

---

## 6. Dwell Control

### 6.1 Strategy

The dwell (coil charge time) is computed from:
1. **Battery voltage** — higher voltage = shorter charge time
2. **Engine RPM** — higher RPM = shorter available time window
3. **Coil energy target** — 30-50 mJ typical for Renesis coils

### 6.2 `getIgnitionDwellTime` (0x9490)

```
dwell_time = ThreeDLookup(table_0x69F30, rpm, battery_voltage)
dwell_time = dwell_time + offset(0xFFFFA0D6)
if (dwell_time > 0xFFFF) dwell_time = 0xFFFF  // clamp
store to 0xFFFFA0D4
```

The 3D table at **0x69F30** maps RPM × battery voltage to dwell time in timer ticks.

### 6.3 `outputPerRotorIgnitionDwell` (0x11218)

Distributes the computed dwell time to each rotor's coil control structure:

```
for rotor in [0, 1, 2]:
    rotor_id = rotor_struct[rotor].id
    dwell = calculate_dwell_helper(rotor_id)
    rotor_struct[rotor].dwell = dwell
```

Helper at **0x10F84** computes per-rotor dwell considering rotor-specific factors.

### 6.4 `returnDwellTime_fp` (0x1120A)

Returns the dwell time as a floating-point value. Essentially a float-to-storage wrapper.

---

## 7. Calibration Tables

The following calibration data structures are referenced by the ignition subsystem:

### 7.1 Main Base Timing Tables

| Address | Name | Dimensions | Description |
|---------|------|-----------|-------------|
| 0x6DB48 | Ignition Leading Base | 3D (RPM × Load) | Main advance for leading plugs |
| 0x6D948 | Ignition Leading Base Safe | 3D (RPM × Load) | Safe-mode advance (sensor fail) |
| 0x6EEEC | Ignition Trailing B | 3D | Trailing plug base (Rotor 2) |
| 0x6F0EC | Ignition Trailing A | 3D | Trailing plug base (Rotor 1) |
| 0x6D59C | Ignition Maybe Idle Base | 1D/2D | Idle advance control |
| 0x6D668 | Ignition Timing Lead | Table | Leading offset table |

### 7.2 Correction Tables

| Address | Name | Description |
|---------|------|-------------|
| 0x6D5C8 | Ignition Temp Correction? | ECT-based timing correction |
| 0x6F2EC | Ignition Min Split | Minimum leading-trailing split angle |
| 0x6B68C | RPM Correction (in code) | RPM-based knock/temp correction |
| 0x69F30 | Dwell Table (in code) | RPM × Battery voltage dwell lookup |
| 0x7CB20 | Ignition Dwell Time_ | Dwell calibration constants |

### 7.3 Boundary Tables

| Address | Name | Description |
|---------|------|-------------|
| (code) | Max advance limits | Per-RPM maximum advance |
| (code) | Min advance limits | Per-RPM minimum advance |
| (code) | Rate limits | Max advance rate-of-change |

---

## 8. MTU2 Hardware Register Map

The SH-2E MTU2 registers used for ignition output compare:

| Address | Register | Description | Usage |
|---------|----------|-------------|-------|
| 0xFFFFF600 | TSTR | Timer Start Register | Channel enable bits |
| 0xFFFFF602 | TSR | Timer Status Register | Compare match flags |
| 0xFFFFF604 | TCR0 | Timer Control Reg Ch0 | Edge/clock config |
| 0xFFFFF606 | TIOR0 | Timer I/O Control Ch0 | Output compare mode |
| 0xFFFFF608 | TCR2 | Timer Control Reg Ch2 | (not ch1 - ch2 uses this) |
| 0xFFFFF60A | TIOR2 | Timer I/O Control Ch2 | |
| 0xFFFFF614 | TCNT0 | Timer Counter Ch0 | Leading R1 timer |
| 0xFFFFF616 | TCNT2 | Timer Counter Ch2 | Leading R2 timer |
| 0xFFFFF618 | TCNT1 | Timer Counter Ch1 | Trailing R1 timer |
| 0xFFFFF61A | TCNT3 | Timer Counter Ch3 | Trailing R2 timer |
| 0xFFFFF650 | TGRA0 | Timer Gen Reg A Ch0 | Leading R1 compare |
| 0xFFFFF652 | TGRA2 | Timer Gen Reg A Ch2 | Leading R2 compare |
| 0xFFFFF654 | TGRA1 | Timer Gen Reg A Ch1 | Trailing R1 compare |
| 0xFFFFF656 | TGRA3 | Timer Gen Reg A Ch3 | Trailing R2 compare |
| 0xFFFFF666 | (shared) | Shared control | Output compare control |

---

## 9. Interrupt Safety

All functions that modify hardware timer registers use **critical section** protection:

```c
uint32_t sr = getSR(16);  // disable interrupts (IMASK=16)
// ... modify timer registers ...
setSR(sr);                 // restore previous mask
```

The `getSR` function (0x3920) reads the status register and sets the interrupt mask to level 16 (disable all interrupts). The `setSR` function (0x3934) restores the previous mask.

This ensures the output-compare programming is atomic and not interrupted by other ISRs that might modify the same timer channels.

---

## 10. Complete Ignition Equation

Combining all the correction terms from the analyzed functions:

```
Raw_Advance  = BaseLookup(RPM, Load)
Correction1  = KnockRetard() + TempCorrection() + ACCompRetard()
Correction2  = DSC/TorqueReduction() + IdleSpeedComp()
SplitAngle   = LeadingTrailingSplit(RPM, Load, conditions)
Final_Lead   = clamp(Raw_Advance - Correction1 - Correction2 + SplitAngle)
Final_Trail  = clamp(Raw_Advance - Correction1 - Correction2)
Dwell_Time   = DwellLookup(RPM, BatteryVoltage) + DwellOffset

Where:
  clamp(x) = min(max(x, MinAdvance(RPM)), MaxAdvance(RPM))
  KnockRetard() = per-rotor retard from knock sensor integration
  TempCorrection() = ECT + IAT combined correction
  ACCompRetard() = -2° lead / -1° trail when AC on
  DSC/TorqueReduction() = CAN bus torque request from EBCM
```

---

## 11. Calibration Table Format

The SH-2E calibration tables use a **header-based descriptor format**:

### 1D Table Descriptor
```
Offset  Size  Field
+0      u16   count_x    Number of X-axis breakpoints
+2      u8    type       Cell data type (0=u8, 1=u16, 2=float, etc.)
+3      u8    padding
+4      f32*  x_axis     Pointer to X breakpoint array
+8      f32*  values     Pointer to Y values array
+12     f32   scale      Output scale factor
+16     f32   offset     Output offset
```

### 2D (3D) Table Descriptor
```
Offset  Size  Field
+0      u16   count_x    Number of X-axis breakpoints
+2      u16   count_y    Number of Y-axis breakpoints
+4      f32*  x_axis     Pointer to X breakpoints
+8      f32*  y_axis     Pointer to Y breakpoints
+12     f32*  values     Pointer to Z values (x × y array)
+16     f32   scale      Scale factor
+20     f32   offset     Offset
```

### Interpolation
The table lookup functions at 0x2068 (1D) and 0x20DC (3D) use **linear interpolation** between breakpoints. The lookup algorithm:
1. Binary search X-axis for interval
2. Binary search Y-axis for interval (3D only)
3. Linear interpolation between surrounding points
4. Apply scale and offset: `result = interpolated_value * scale + offset`

---

## 12. Key Calibration Table Addresses (60E1D400)

| Address | Name | Format | Description |
|---------|------|--------|-------------|
| 0x06B68C | RPM correction | 1D (RPM) | Knock/temp RPM correction |
| 0x069F30 | Dwell time | 3D (RPM × BattV) | Base dwell lookup |
| 0x06DB48 | Leading base | 3D (RPM × Load) | Main leading advance |
| 0x06D948 | Leading safe | 3D (RPM × Load) | Safe-mode leading advance |
| 0x06EEEC | Trailing B | 3D (RPM × Load) | Rotor 2 trailing advance |
| 0x06F0EC | Trailing A | 3D (RPM × Load) | Rotor 1 trailing advance |
| 0x06F2EC | Min split | 1D/2D | Min lead-trail split angle |
| 0x06D59C | Idle base | 2D | Idle advance correction |
| 0x06D5C8 | Temp corr | 2D | Temperature correction |
| 0x07CB20 | Dwell cal | Const | Dwell calibration constants |

---

## 13. Source-Level Code Reconstruction

### 13.1 C Headers

```c
// Hardware register definitions for MTU2 output compare
#define MTU2_TSTR       (*(volatile uint16_t*)0xFFFFF600)
#define MTU2_TSR        (*(volatile uint16_t*)0xFFFFF602)
#define MTU2_TCR0       (*(volatile uint16_t*)0xFFFFF604)
#define MTU2_TIOR0      (*(volatile uint16_t*)0xFFFFF606)
#define MTU2_TCR2       (*(volatile uint16_t*)0xFFFFF608)
#define MTU2_TIOR2      (*(volatile uint16_t*)0xFFFFF60A)
#define MTU2_TCNT0      (*(volatile uint16_t*)0xFFFFF614)
#define MTU2_TCNT1      (*(volatile uint16_t*)0xFFFFF618)
#define MTU2_TCNT2      (*(volatile uint16_t*)0xFFFFF616)
#define MTU2_TCNT3      (*(volatile uint16_t*)0xFFFFF61A)
#define MTU2_TGRA0      (*(volatile uint16_t*)0xFFFFF650)
#define MTU2_TGRA1      (*(volatile uint16_t*)0xFFFFF654)
#define MTU2_TGRA2      (*(volatile uint16_t*)0xFFFFF652)
#define MTU2_TGRA3      (*(volatile uint16_t*)0xFFFFF656)

// Spark state array base
#define SPARK_STATE_BASE    ((volatile uint8_t*)0xFFFFA0D8)

// Channel config table in ROM
#define CHAN_CFG_TABLE      ((const struct chan_cfg*)0xDAB4)

// Port I/O control
#define GPIO_COIL_CTRL      (*(volatile uint8_t*)0xFFFF9F34)

// Critical section
extern uint32_t getSR(uint32_t mask);
extern void setSR(uint32_t sr);
```

### 13.2 Data Structures

```c
// 8-byte per-channel spark state (used by outputSpark1)
struct spark_state_8 {
    float  dwell_time;       // +0: timer compare value
    uint8_t arm_flag;        // +4: 0=idle, 2=armed
    uint8_t enable_flag;     // +5: 0=enabled
    uint8_t fire_flag;       // +6: status/fire request
    uint8_t pad;             // +7
};

// 24-byte MTU2 channel config table entry
struct chan_cfg {
    volatile uint16_t *tcnt;     // +0: Timer counter
    volatile uint16_t *tier;     // +4: Interrupt enable
    volatile uint16_t *tcr;      // +8: Timer control
    volatile uint16_t *tsr;      // +12: Timer status (shared)
    volatile uint16_t *tgra;     // +16: Output compare reg A
    uint32_t           bitmask;  // +20: Channel enable bitmask
};

// 1D table descriptor
struct table_1d {
    uint16_t count;
    uint8_t  type;
    uint8_t  pad;
    const float *x_axis;
    const float *values;
    float scale;
    float offset;
};

// 2D (3D) table descriptor
struct table_2d {
    uint16_t count_x;
    uint16_t count_y;
    const float *x_axis;
    const float *y_axis;
    const float *values;
    float scale;
    float offset;
};
```

### 13.3 Core Functions

```c
// outputSpark1 — Program leading spark timer
void outputSpark1(uint8_t spark_index, float dwell_time) {
    uint32_t sr = getSR(16);
    volatile struct spark_state_8 *spark;
    
    spark = (void*)(SPARK_STATE_BASE + spark_index * 8);
    spark->dwell_time = dwell_time;
    spark->enable_flag = 0;
    spark->arm_flag = 2;
    
    ignitonSomethingCalc(spark_index);
    setSR(sr);
}

// outputSpark2 — Program trailing spark timer
void outputSpark2(uint8_t spark_index, float timing_angle) {
    uint32_t sr = getSR(16);
    volatile struct {
        float timing;
        uint8_t control;
        uint8_t unknown;
        uint8_t fire_flag;
        uint8_t pad;
        uint8_t extra[8];
    } *spark = (void*)(SPARK_STATE_BASE + spark_index * 16);
    
    if (spark->control == 2) {
        spark->timing = timing_angle;
    }
    spark->fire_flag = 0;
    
    ignitonSomethingCalc(spark_index);
    setSR(sr);
}

// ignitionTimingHardwareTimerSomething — Configure MTU2 output compare
void ignitionTimingHardwareTimerSomething(uint8_t spark_id) {
    uint32_t sr = getSR(16);
    volatile uint8_t *state = SPARK_STATE_BASE + spark_id * 8;
    
    if (!state[5]) {  // enable flag not set
        state[4] = 0;
        state[5] = 0;
        setSR(sr);
        return;
    }
    
    const struct chan_cfg *cfg = &CHAN_CFG_TABLE[spark_id];
    uint16_t current = *cfg->tcnt;
    uint16_t target = *(const uint16_t*)(cfg + 1); // timing in tier field
    int32_t delta = target - (current + 3);
    
    if (delta < 0 || (*cfg->tcr & cfg->bitmask)) {
        setSR(sr);
        return;
    }
    
    // Fire coil via helper
    FUN_0000AA74(cfg->tcnt);
    
    state[4] = 0;  // clear arm
    state[5] = 0;  // clear enable
    setSR(sr);
}

// ignitonSomethingCalc — Normalize timing angle with 720° wrapping
float ignitonSomethingCalc(uint8_t rotor_idx) {
    float ref = *(float*)0xFFFFA0FC;
    float timing = *(float*)(SPARK_STATE_BASE + rotor_idx * 6);
    float delta = timing - ref;
    
    if (delta < -90.0f) {
        delta += 720.0f;
    } else if (delta >= 630.0f) {
        delta -= 720.0f;
    }
    
    *(float*)0xFFFFA0F8 = delta;
    
    uint8_t *flags = SPARK_STATE_BASE + rotor_idx * 6;
    if (!flags[5] && delta > 60.0f) {
        FUN_00009440(rotor_idx);
    }
    
    return delta;
}

// calc_ignition_all_rotors_13C2C — Main ignition correction computation
void calc_ignition_all_rotors_13C2C(void) {
    float rpm = *(float*)0xFFFFA73C;
    uint8_t knock_status = *(uint8_t*)0xFFFFA740;
    float *base_timing = (float*)0xFFFFA744;
    uint8_t knock_fault = *(uint8_t*)0xFFFFA748;
    uint8_t knock_detected = *(uint8_t*)0xFFFFA749;
    uint8_t ect_warm = *(uint8_t*)0xFFFFC0C4;
    uint8_t ect_enable = *(uint8_t*)0xFFFFC0C5;
    
    float correction = 0.0f;
    
    if (knock_fault == 0) {
        // No knock sensor fault
        goto skip_knock;
    }
    
    if (knock_detected) {
        uint8_t knock_active = *(uint8_t*)0xFFFFA75C;
        if (knock_active) {
            // Use RPM-based knock correction table
            float rpm2 = *(float*)0xFFFFB5B8;
            correction = table_lookup_1D(0x6B68C, rpm2);
        } else if (knock_status == 1) {
            correction = 0.0f;
        }
    }
    
skip_knock:
    // Temperature correction
    if (ect_warm == 1 && ect_enable != 0) {
        correction -= 1.0f;  // retard when warm
    }
    
    // Apply correction to base timing
    *base_timing -= correction;
    
    // Dispatch results
    compare_select_two_float_values();
    calc_fuel_pump_control_output(*base_timing);
    calc_fuel_pressure_load_compensation();
    
    *(uint8_t*)0xFFFFA75C = knock_status;
}
```

---

## 14. Function Summary Table

| Address | Name | Size | Confidence | Layer |
|---------|------|------|-----------|-------|
| 0x011A9C | calc_base_ignition_timing_11A9C | 212 B | MED | Calculation |
| 0x013C2C | calc_ignition_all_rotors_13C2C | 208 B | HIGH | Calculation |
| 0x01A0C8 | spark_advance_calc_main_1A0C8 | 850 B | MED | Calculation |
| 0x01BA2C | load_based_spark_mapper | 360 B | MED | Calculation |
| 0x016BE8 | spark_advance_calc_0x16BE8 | 162 B | LOW | Calculation |
| 0x0148A8 | calc_spark_advance_offset_map | 102 B | LOW | Calculation |
| 0x02100A | rotor_sync_gate_state_ctrl_2100A | 352 B | MED | Split |
| 0x022334 | acCompressorLeadingTimingRetard | 194 B | MED | Correction |
| 0x022434 | acCompressorTrailingTimingRetard | 194 B | MED | Correction |
| 0x0162E4 | spark_timing_boundary_limiter | 386 B | MED | Boundary |
| 0x01BB94 | temperature_dependent_spark_limiter | 282 B | MED | Boundary |
| 0x019BCA | spark_advance_limiter_19BCA | 532 B | MED | Boundary |
| 0x022B1A | spark_advance_limiter_22B1A | 172 B | MED | Boundary |
| 0x00E38C | ignition_advance_limiter | 176 B | MED | Boundary |
| 0x008DE6 | outputSpark1 | 58 B | HIGH | Output |
| 0x008E20 | outputSpark2 | 64 B | HIGH | Output |
| 0x008E60 | ignitionTimingHardwareTimerSomething | 190 B | HIGH | Output |
| 0x0091FE | ignitonSomethingCalc | 582 B | HIGH | Output |
| 0x00C98A | setupCoilOutputs | 208 B | MED | HW Init |
| 0x008F62 | ignitionDwellOutputInit | 80 B | HIGH | HW Init |
| 0x00E37C | coil_pwm_init | 16 B | MED | HW Init |
| 0x00E448 | flag_set_coil_event | 8 B | MED | Status |
| 0x00E450 | coil_charge_enabled_query | 26 B | MED | Status |
| 0x01A832 | ignition_coil_dispatcher | 14 B | LOW | Dispatch |
| 0x01A9A0 | ignition_timing_priority_dispatcher | 42 B | LOW | Dispatch |
| 0x01B01A | coil_charge_control_flag_set | 6 B | LOW | Status |
| 0x02204C | ignition_timing_pipeline_2204C | 72 B | LOW | Pipeline |
| 0x0222F8 | ignition_schedule_dispatcher_222F8 | 24 B | LOW | Dispatch |
| 0x023378 | ignition_timing_control_task_23378 | 36 B | LOW | Task |
| 0x01E6B6 | ignition_timing_output_1E6B6 | 222 B | LOW | Output |
| 0x007814 | crank_timing_update | 138 B | MED | Crank |
| 0x00837C | ign_timing_task_handler | 142 B | MED | Task |
| 0x00E312 | ignition_trim_table_lookup | 106 B | MED | Calibration |
| 0x00F6E8 | ignition_table_unpack_all_cyls | 96 B | MED | Calibration |
| 0x010408 | lookup_timing_event_table | 60 B | MED | Calibration |
| 0x01120A | returnDwellTime_fp | 14 B | MED | Dwell |
| 0x011218 | outputPerRotorIgnitionDwell | 102 B | MED | Dwell |
| 0x01490E | calc_ignition_system_diagnostics | 54 B | LOW | Diagnostic |
| 0x01FAEA | ignition_timing_safety_check_1FAEA | 328 B | MED | Safety |

---

## 15. Open Questions / Uncertainties

1. **Precise table addresses** — The cal_tables.csv addresses may be from a different ROM version ([REDACTED]). Need to verify against 60E1D400 binary.
2. **Coil fire helper (0xAA74)** — The function that actually triggers the coil output needs separate analysis. It may be a PWM duty cycle write or a compare register update.
3. **Ion sense detection** — Some Mazda ECUs detect misfire via ion sense on the spark plug. The `spark_plug_monitor_0x50A54` function may be related but is in a separate code region.
4. **Split angle computation** — The precise formula for leading-trailing split is not fully verified. The `rotor_sync_gate_state_ctrl_2100A` function needs deeper analysis for the exact lookup.
5. **DSC interaction** — The torque reduction from the EBCM goes through the `dscRelatedTiming` function (0x19220) but the exact CAN message format isn't analyzed.
6. **Check engine light** — The `ignition_fault_monitor_458F4` function needs analysis for DTC trigger conditions.
