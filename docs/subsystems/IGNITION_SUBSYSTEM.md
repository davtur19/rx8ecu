# Ignition / Spark Control Subsystem

**Firmware:** 60E1D400 (RX-8 Renesis 6-speed MT)
**Processor:** Renesas SH-2E (HD64F7055)
**Update:** 2026-07-31
**Functions:** ~59 identified (38 analyzed in detail)

## 1. Rotary-Specific Ignition Architecture

| Feature | Rotary | Piston Engine |
|---|---|---|
| Plugs per rotor | 2 (leading + trailing) | 1 per cylinder |
| Power strokes | 1 per rotor per e-shaft rev | 1 per 2 crank revs |
| Total plugs | 4 (2 leading, 2 trailing) | 4–16 |
| Firing order | R1 Lead → R1 Trail (few ° later) → R2 Lead → R2 Trail (180° e-shaft after R1) | L1 L2 L3 L4... |
| Angle domain | 1 rotor face-cycle = 360° e-shaft (1 rotor revolution = 3 face-cycles = 1080° e-shaft); fires every 180° e-shaft | 720° per crank cycle |
| Split (lead-trail gap) | 5–20° BTDC typical | N/A |

### Coil Configuration
- **4 coils**: 2 leading (one per rotor) + 2 trailing (one per rotor)
- **Per-e-shaft-rev firing**: each of 4 coils fires once per e-shaft rev (one lead + one trail spark per rotor per rev = one combustion event per rotor per rev, 2 events/rev total). **Not** wasted-spark: dedicated coil per rotor means no firing lands on an exhaust phase.
- **Dwell control**: independent per coil, battery-voltage compensated
- **Spark duration**: ~1.5–2.5 ms by load/RPM

### Timer Hardware
SH-2E MTU2 (Multi-Function Timer Pulse Unit 2), **4 output-compare channels**:

| Channel | Spark Role | TCNT | TIER | TCR | TSTR/TSR | TGRA | Bit Mask |
|---|---|---|---|---|---|---|---|
| CH 0 | Leading Rotor 1 | 0xFFFFF650 | 0xFFFFF614 | 0xFFFFF604 | 0xFFFFF602 | 0xFFFFF666 | 0x01 |
| CH 1 | Trailing Rotor 1 | 0xFFFFF654 | 0xFFFFF618 | 0xFFFFF608 | 0xFFFFF602 | 0xFFFFF666 | 0x04 |
| CH 2 | Leading Rotor 2 | 0xFFFFF652 | 0xFFFFF616 | 0xFFFFF606 | 0xFFFFF602 | 0xFFFFF666 | 0x02 |
| CH 3 | Trailing Rotor 2 | 0xFFFFF656 | 0xFFFFF61A | 0xFFFFF60A | 0xFFFFF602 | 0xFFFFF666 | 0x08 |

Channel config stored in a **hardware config table @0xDAB4** — four 24-byte entries mapping spark index → timer registers.

## 2. Ignition Timing Formula

```
Final_BTDC = (BaseTimingFinal * CrankAngleMult)
           + ((IdleBaseFinal + IdleSpeedComp + CrankAngleTiming) * (1 - CrankAngleMult))
           + CoolantTempComp - IntakeAirTempComp

where:
  BaseTimingFinal = Leading_Base_Table(RPM, Load) + KnockRetard + TemperatureCorrection + AC_Retard
  Leading Angle = BaseTimingFinal + SplitAngle
  Trailing Angle = BaseTimingFinal
```

Base timing is a 3D table (RPM × Load). Corrections:

| Correction | Source | Range |
|---|---|---|
| Knock retard | Per-rotor knock detection | 0° to -10° |
| Temperature | ECT + IAT combined | ±3° |
| AC compressor | AC clutch engagement | -2° leading, -1° trailing |
| DSC/Torque mgmt | CAN bus from EBCM | -5° to 0° |
| Idle speed comp | RPM error × gain | ±2° |
| Cranking angle | Fixed during start | ~5° BTDC |

## 3. Software Architecture

### Call Hierarchy

```
engineControlTASK (0x11E94)
  └── engineControlCalculateTiming (0x14584)
        ├── calc_spark_advance (0x121F0)
        ├── calc_spark_advance (0x1237C)
        ├── getKnockControlAllowed (0x13A0E)
        ├── getKnockSensorFaultedStatus (0x13A5E)
        ├── getKnockControlActive (0x13A86)
        ├── updateKnockMaxRAM (0x13B90)
        ├── calc_ignition_all_rotors_13C2C (0x13C2C)  ← Phase 1 ignition
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
              ├── setupCoilOutputs (0xC98A)  ├── ignitonSomethingCalc (0x91FE)
              ├── outputSpark1 (0x8DE6)      ├── outputSpark2 (0x8E20)
              ├── ignitionTimingHardwareTimerSomething (0x8E60)
              └── ignitionDwellOutputInit (0x8F62)
```

Pipeline layers: **Calculation** (combine base+knock+temp; RPM/Load interpolation) → **Boundary** (min/max clamp, rate-of-change, ECT/IAT protection) → **Output** (normalize angle, wrap 720°, program lead/trail timers, set output compare) → **Hardware** (MTU2 channel setup, dwell PWM init, coil status).

## 4. Function Analysis

### 4.1 `engineControlCalculateTiming` (0x14584) — Main Timing Dispatcher
414 B (0x14584–0x14722), called once per scheduler tick from `engineControlTASK` (0x11E94). Central engine control loop — 66 sequential calls with zero branches:
- **Phase 1** (7 calls): context save, knock prep, `calc_ignition_all_rotors_13C2C`
- **Phase 2** (56+ calls): fuel, rotor-position timing (the "cam" group — RX-8 is camless), knock, DSC, throttle, sensor, output chain

Gated by `getSR(16)`/`setSR()` critical sections. **Confidence: high** — 66 sequential jsr, no conditional branching.

### 4.2 `calc_ignition_all_rotors_13C2C` (0x13C2C) — Main Ignition Computation
208 B (0x13C2C–0x13CFC), called Phase 1 slot 7. Computes correction terms for all rotors and combines with base advance.

**Input RAM:** `0xFFFFA73C` RPM (float) · `0xFFFFA740` ignition enable/knock status · `0xFFFFA744` prev timing (base advance) · `0xFFFFA748` knock sensor fault status · `0xFFFFA749` knock detected · `0xFFFFA74C` scratch · `0xFFFFA75C` knock control active · `0xFFFFB5B8` RPM (filtered) · `0xFFFFC0C4` coolant temp status (warm=1) · `0xFFFFC0C5` ECT correction enable

**Calibration:** 1D @0x6B68C (RPM-based correction): 2000–4500 → -10.0°, 5000 → 0.0°

**Constants:** 0x0007987C=0.0f (zero), 0x00079890=2.5f (max knock retard), 0x00079880=1.0f (warm-up default), 0x00079888=1.0f (alternate path)

```
if knock_sensor_faulted: correction = 0.0
else:
    if knock_detected: if knock_control_active: correction = RPM_table_lookup(0x6B68C, RPM)
                      else: if enabled: correction = 0.0
    else: correction = 0.0
if engine_warm AND ect_enable: correction -= 1.0   # retard when warm
compare_select_two_float_values()
calc_fuel_pump_control_output(fr15)                → 0xFFFFA744 (trailing edge)
calc_fuel_pressure_load_compensation()             → 0xFFFFA734/0xFFFFA738
```

**Output RAM:** `0xFFFFA744` main ignition advance (float °BTDC) · `0xFFFFA75C` knock control active (saved back).

> `0xFFFFA734`/`0xFFFFA738` ignition timing values (float °BTDC) — written **identically** (same value) by `calc_ignition_all_rotors_13C2C`; lead/trail split NOT applied in `split_selector_state_ctrl_487DC` either (VERIFIED 2026-08-01, emulator 500k inputs 0 mismatches: it is a gated state selector → u8 @0xFFFFCCD2 decoded by `split_selector_decoder_48C12`; 0x2100A is a cold/validity state controller). **SPLIT ANSWER 2026-08-02:** A734/A738 also written identically by `calc_fuel_injection_all_rotors` (0x13D3C); exhaustive ROM literal scan shows NO function writes them differently — readers are `write_knock_detected_flag` (0x128C4, reads A734), `write_rotor_A_knock_flag` (0x128FE, reads A738), `updateKnockMaxRAM` (0x13B90, reads A734). Lead/trail differentiation NOT found in analyzed functions; **open item**.

**Confidence: high** — all paths traced.

### 4.3 `calc_base_ignition_timing_11A9C` (0x11A9C) — Base Timing Interpolation
212 B (0x11A9C–0x11B70), Phase 2. 3D lookup (RPM × Load), then `base_angle = base_angle * scale + offset`. **Confidence: medium** — table addresses unverified.

### 4.4 `spark_advance_calc_main_1A0C8` (0x1A0C8) — Main Spark Advance
850 B (0x1A0C8–0x1A41A), Phase 2. **Largest** spark function: RPM-based advance lookup, enable-condition check (knock enabled, sensor valid), torque management (DSC/TCM reduction), rate limiting, store to rotor RAM. **Confidence: medium**.

### 4.5 `outputSpark1` (0x8DE6) — Program Leading Spark Timer
58 B (0x8DE6–0x8E20), output chain.

```asm
outputSpark1:
    mov   #4, r0                ; offset 4 for float on stack
    mov.l L_008ebc, r3          ; r3 = getSR @ 0x3920
    sts.l pr, @-r15
    add   #-12, r15
    mov.b r4, @r15              ; save spark_index
    fmov.s fr4, @(r0, r15)      ; save dwell_time at sp+4
    jsr   @r3;  mov #16, r4     ; getSR(16)
    mov.l r0, @(8, r15)
    mov.b @r15, r4;  mov #4, r0
    mov.l L_008eb8, r3          ; r3 = spark state base @ 0xFFFFA0D8
L_008dfe:
    extu.b r4, r4;  fmov.s @(r0, r15), fr3
    shll2 r4;  shll r4          ; index * 8
    add   r3, r4
    fmov.s fr3, @r4             ; store dwell_time @ +0
    mov   #0, r0;  mov.b r0, @(5, r4)   ; clear +5 (enable flag)
    mov   #2, r0;  mov.b r0, @(4, r4)   ; set +4 = 2 (arm)
    bsr   L_0091fe              ; ignitonSomethingCalc(spark_index)
    mov.b @r15, r4
    mov.l @(8, r15), r4;  mov.l L_008ec0, r3   ; setSR @ 0x3934
    add   #12, r15
    jmp   @r3;  lds.l @r15+, pr
```

```c
void outputSpark1(uint8_t spark_index, float dwell_time) {
    uint32_t sr = getSR(16);
    volatile struct { float dwell_time; uint8_t arm_flag; uint8_t enable_flag; }
        *spark = (void*)(0xFFFFA0D8 + spark_index * 8);
    spark->dwell_time = dwell_time;
    spark->enable_flag = 0;  // clear enable
    spark->arm_flag = 2;     // arm output compare
    ignitonSomethingCalc(spark_index);  // normalize angle
    setSR(sr);
}
```

**Spark State Array** (base 0xFFFFA0D8): `+0` float timer compare · `+4` u8 arm (2=armed, 0=idle) · `+5` u8 enable (0=enabled) · `+6` u8 fire request/completion.
Data: `L_008eb8`=0xFFFFA0D8, `L_008ebc`=0x3920 (getSR), `L_008ec0`=0x3934 (setSR). **Confidence: high**.

### 4.6 `outputSpark2` (0x8E20) — Program Trailing Spark Timer
64 B (0x8E20–0x8E60). Like `outputSpark1` but **16-byte** stride; only writes if `arm(control)==2`:

```c
void outputSpark2(uint8_t spark_index, float timing_angle) {
    uint32_t sr = getSR(16);
    volatile struct { float timing; uint8_t control; uint8_t unknown; uint8_t fire_flag; }
        *spark = (void*)(0xFFFFA0D8 + spark_index * 16);
    if (spark->control == 2) spark->timing = timing_angle;
    spark->fire_flag = 0;
    ignitonSomethingCalc(spark_index);
    setSR(sr);
}
```
16-byte stride suggests trailing channels hold more state (possibly dual-output/per-rotor secondary data). **Confidence: high**.

### 4.7 `ignitionTimingHardwareTimerSomething` (0x8E60) — MTU2 Output Compare Setup
190 B (0x8E60–0x8F1E), timer ISR path. Most complex hardware-level function; configures MTU2 output-compare and fires coil.

```c
void ignitionTimingHardwareTimerSomething(uint8_t spark_id) {
    uint32_t sr = getSR(16);
    volatile uint8_t *state = (uint8_t*)0xFFFFA0D8 + spark_id * 8;
    if (!state[5]) { state[4] = 0; state[5] = 0; setSR(sr); return; }  // enable==0
    struct ChanCfg { uint16_t *tcnt; uint16_t *tier; uint16_t *tcr; uint16_t *tsr;
                     uint16_t *tgra; uint16_t enable_bits; } *cfg = (struct ChanCfg*)(0xDAB4 + spark_id*24);
    int32_t delta = *(uint16_t*)(cfg->tier) - (*cfg->tcnt + 3);
    if (delta < 0) { setSR(sr); return; }                    // window passed, skip
    if (*cfg->tcr & cfg->enable_bits) { setSR(sr); return; } // channel disabled
    FUN_0000AA74(cfg->tcnt);                                 // fire coil
    state[4] = 0; state[5] = 0;
    setSR(sr);
}
```
Data: `L_008fb4`=0xDAB4 (config table), `L_008fb8`=0xAA74 (coil fire helper). **Confidence: high**.

### 4.8 `ignitonSomethingCalc` (0x91FE) — Angle Normalization
582 B (0x91FE–0x9444). Normalizes spark angle with 720° wrapping. (720° is the software scheduling window inherited from the generic 4-stroke codebase; physically the rotary fires every 180° e-shaft, 2 events/rev, one rotor face completes its 4 phases per rotor revolution = 1080° e-shaft.)

```c
void ignitonSomethingCalc(uint8_t rotor_idx) {
    float ref_angle = *(float*)0xFFFFA0FC;
    float *timing = (float*)(0xFFFFA0D8 + rotor_idx * 24);
    float *output = (float*)0xFFFFA0F8;
    float delta = *timing - ref_angle;
    if (delta < -90.0f)      delta += 720.0f;   // L_00924c = -90.0
    else if (delta >= 630.0f) delta -= 720.0f;  // L_009254 = 630.0
    *output = delta;
    uint8_t *flags = (uint8_t*)(0xFFFFA0D8 + rotor_idx * 24);
    if (flags[5] == 0 && delta > 60.0f) call_rotor_specific_logic(rotor_idx);  // @0x9440
}
```
Constants: `L_009244`=0xFFFFA0D8 (rotor timing base) · `L_009248`=0xFFFFA0FC (ref angle) · `L_00924c`=-90.0 · `L_009250`=720.0 · `L_009254`=630.0 · `L_009258`=-720.0 · `L_009274`=0xFFFFA0F8 (normalized output). **Confidence: high**.

### 4.9 `setupCoilOutputs` (0xC98A) — MTU2 Channel Configuration
208 B (0xC98A–0xCA5A), Phase 2. Configure I/O pin 0xFFFF9F34 (set bit 6, clear bit 5, output-compare mode); RPM→timer conversion factor with 1152.0 constant (timer clock prescaler); load min/max window from 0xFFFFA37C/0xFFFFA37E; write dwell boundaries; PWM control via 0xFFFF9F34 bits 0-1.

```c
*io_reg = (*io_reg & 0xBF) | 0x40;
float conv_factor = *(float*)0xFFFF9F88 /* RPM */ / 1152.0f;
uint16_t min_window = *(uint16_t*)0xFFFFA37E;
uint16_t max_window = *(uint16_t*)0xFFFFA37C;
*io_reg = (*io_reg & 0xFC) | output_bits;
```
Data: `L_00ca78`=0xFFFF9F34 · `L_00ca7c`=0x71AC (adc_read_and_merge_flags) · `L_00ca80`=0xFFFF9F88 · `L_00ca84`=1152.0f · `L_00ca88`=0xFFFF9F9C · `L_00ca8c`=0xFFFFA37E · `L_00ca90`=0x4F000000 (2^31) · `L_00ca94`=0xFFFFA37C · `L_00ca98`=0x2054 (setSR_PARAM). **Confidence: medium**.

### 4.10 `ignitionDwellOutputInit` (0x8F62) — Dwell Initialization
80 B (0x8F62–0x8FB2). Clears all coil control flags in spark state array (channels 0-3, stride 8: `state[4]=0`, `state[5]=0`) and `0xFFFFA100=0`, inside getSR/setSR. **Confidence: high**.

### 4.11 `ignition_advance_limiter` (0xE38C) — Rate Limiter
176 B (0xE38C–0xE43C). Clamps advance rate of change: `delta = clamp(desired-current, ±max_rate)`. **Confidence: medium**.

### 4.12 `coil_pwm_init` (0xE37C) — PWM Coil Init
16 B (0xE37C–0xE38C). Writes initial PWM duty to `0xFFFFA100`. **Confidence: medium**.

### 4.13 `coil_charge_enabled_query` (0xE450) — Coil Status
26 B (0xE450–0xE46A). Tests `*(uint8_t*)0xFFFFA0D8 & 0x01`. **Confidence: medium**.

### 4.14 `rotor_sync_gate_state_ctrl_2100A` (0x2100A) — Split Angle Control
352 B (0x2100A–0x2116A).

> STATUS 2026-08-01: Lifted and VERIFIED against the ROM emulator (500,000 random inputs, 0 mismatches; see c/rotor_sync_gate_state_ctrl_2100A.c and c/tests/test_rotor_sync_gate_state_ctrl_2100A.py). Despite the IDA name, this function does NOT compute a split angle and does NOT touch A734/A738. It manages a cold/validity flag u8@0xFFFFB240 and two state floats f32@0xFFFFB18C / f32@0xFFFFB188 (set to 1.0 together, decayed independently as max(state − 0.0667, 0.0), or cleared together) gated by temperature hysteresis, engine-off/enable/cal flags, and the shared max helper @0x23E4. A734 == A738 in practice (written identically by calc_ignition_all_rotors_13C2C). The actual lead/trail split is NOT implemented here; see split_selector_state_ctrl_487DC for further analysis.

> **NOTA (verificata, provenienza emulatore):** Split site `0x19220` (`calc_spark_lead_trail_split_19220`, chiamato da `engineControlCalculateTiming` @0x14584 dispatch 0x147D0): A9A0=leading, A9AC=trailing (selector @0xBCEF: 1/3→byte 0x6ED98/0x6ED99 costante=126 *0.5-50; 2→ThreeD(desc 0x69F14 TrailingA); 0→ThreeD(desc 0x69EF8 TrailingB)), minSplit=ThreeD(desc 0x69F30 MinSplit, load, RPM); A9A8=max(A9A0,A9AC); A9A4=A9A8+minSplit; A9C0=(lead>trail)?0:1. NOTA: alcuni doc vecchi chiamano "dwell" il desc 0x69F30 (MinSplit) — il nome corretto è MinSplit (verificato emulatore); il **dwell** vero è identificato in **§6.2** (`getIgnitionDwellTime` 0x94C8, desc 0x6C1C0, dati 0x7CB20).

Otherwise checks engine-running, temperature, load, AC, knock conditions to enable lead/trail split; if not met (cold start, overrun, knock) both plugs fire same angle. **Confidence: medium**.

### 4.15-4.22 Short Functions

| Function | Address | Size | Role |
|---|---|---|---|
| `load_based_spark_mapper` | 0x1BA2C | 360 B | Piecewise load→advance; more retard at high load (knock) |
| `temperature_dependent_spark_limiter` | 0x1BB94 | 282 B | Cold: +advance; hot/high IAT: -advance |
| `spark_timing_boundary_limiter` | 0x162E4 | 386 B | Clamp to min/max (RPM/load dependent); safe-mode limits on sensor fail |
| `spark_advance_calc_0x16BE8` | 0x16BE8 | 162 B | RPM-only advance (no load axis) fallback |
| `calc_spark_advance_offset_map` | 0x148A8 | 102 B | Per-rotor offsets (variation/wear/adaptive trim) |
| `calc_ignition_system_diagnostics` | 0x1490E | 54 B | Coil continuity, firing detect, DTC reporting |
| `acCompressorLeadingTimingRetard` | 0x22334 | 194 B | -2° leading when AC on (ramped) |
| `acCompressorTrailingTimingRetard` | 0x22434 | 194 B | -1° trailing when AC on (ramped) |

## 5. Spark State Data Structures

### Spark State Array (0xFFFFA0D8)
**8-byte channel** (`outputSpark1`, `ignitionTimingHardwareTimerSomething`):
```
+0 float dwell_time/timer_compare   +6 u8 fire_flag/status
+4 u8  control_arm (0/2=armed)      +7 padding
+5 u8  enable_flag (0=enabled)
```
Channels 0-3 → 0xFFFFA0D8-0xFFFFA0F7.

**16-byte channel** (`outputSpark2`): `+0` float timing · `+4` control (0/2) · `+5` unknown · `+6` fire_req · `+7` pad · `+8` 8B extra state.

**Rotor-timing view**: `+0` float timing °BTDC · `+4` control_flags · `+5` secondary_enable · per-rotor 24-byte stride.

### Channel Config Table (0xDAB4) — 4 × 24 B

```
+0 TCNT   +4 TIER   +8 TCR   +12 TSR (shared 0xFFFFF602)   +16 TGRA   +20 bitmask
```

| Index | Spark | TCNT | TIER | TCR | TSR | TGRA | Bit mask |
|---|---|---|---|---|---|---|---|
| 0 | Leading R1 | 0xFFFFF650 | 0xFFFFF614 | 0xFFFFF604 | 0xFFFFF602 | 0xFFFFF666 | 0x01 |
| 1 | Trailing R1 | 0xFFFFF654 | 0xFFFFF618 | 0xFFFFF608 | 0xFFFFF602 | 0xFFFFF666 | 0x04 |
| 2 | Leading R2 | 0xFFFFF652 | 0xFFFFF616 | 0xFFFFF606 | 0xFFFFF602 | 0xFFFFF666 | 0x02 |
| 3 | Trailing R2 | 0xFFFFF656 | 0xFFFFF61A | 0xFFFFF60A | 0xFFFFF602 | 0xFFFFF666 | 0x08 |

## 6. Dwell Control

Dwell (coil charge time) from: battery voltage (higher → shorter), RPM (higher → shorter window), coil energy target 30-50 mJ.

### 6.2 `getIgnitionDwellTime` (0x94C8)
```
dwell_time = ThreeDLookup(table_dwell desc 0x6C1C0, dati 0x7CB20)  // NON 0x69F30, che è MinSplit
dwell_time = dwell_time + offset(0xFFFFA0D6)
if (dwell_time > 0xFFFF) dwell_time = 0xFFFF
store to 0xFFFFA0D4
```
> **0x69F30** = **MinSplit** (3D lookup, verificato) — non è il dwell. Il dwell usa desc **0x6C1C0** (dati **0x7CB20**).

### 6.3 `outputPerRotorIgnitionDwell` (0x11218)
Distributes dwell per rotor; helper @0x10F84 computes per-rotor dwell.

### 6.4 `returnDwellTime_fp` (0x1120A)
Returns dwell as float; float-to-storage wrapper.

## 7. Calibration Tables

| Address | Name | Dims | Description |
|---|---|---|---|
| 0x6DB48 | Ignition Leading Base | 3D (RPM×Load) | Leading main advance |
| 0x6D948 | Leading Base Safe | 3D (RPM×Load) | Safe-mode (sensor fail) |
| 0x6EEEC | Trailing B | 3D | Rotor 2 trailing |
| 0x6F0EC | Trailing A | 3D | Rotor 1 trailing |
| 0x6D59C | Maybe Idle Base | 1D/2D | Idle advance |
| 0x6D668 | Timing Lead | table | Leading offset |
| 0x6D5C8 | Temp Correction? | — | ECT-based |
| 0x6F2EC | Min Split | — | Min lead-trail split |
| 0x6B68C | RPM Correction (code) | 1D | RPM knock/temp correction |
| 0x69F30 | MinSplit (verificato) | 3D (load×RPM) | Min lead-trail split |
| 0x7CB20 | Dwell Time | — | Dwell calibration |

Boundary tables (code): Max/Min advance per-RPM, rate limits.

## 8. MTU2 Hardware Register Map

| Address | Register | Usage |
|---|---|---|
| 0xFFFFF600 | TSTR | Channel enable bits |
| 0xFFFFF602 | TSR | Compare match flags |
| 0xFFFFF604 | TCR0 | Ch0 edge/clock |
| 0xFFFFF606 | TIOR0 | Ch0 output compare mode |
| 0xFFFFF608 | TCR2 | Ch2 edge/clock |
| 0xFFFFF60A | TIOR2 | Ch2 |
| 0xFFFFF614 | TCNT0 | Leading R1 |
| 0xFFFFF616 | TCNT2 | Leading R2 |
| 0xFFFFF618 | TCNT1 | Trailing R1 |
| 0xFFFFF61A | TCNT3 | Trailing R2 |
| 0xFFFFF650 | TGRA0 | Leading R1 compare |
| 0xFFFFF652 | TGRA2 | Leading R2 compare |
| 0xFFFFF654 | TGRA1 | Trailing R1 compare |
| 0xFFFFF656 | TGRA3 | Trailing R2 compare |
| 0xFFFFF666 | shared | Output compare control |

## 9. Interrupt Safety

Timer-modifying functions use `getSR(16)` (set IMASK=16, disable all interrupts) / `setSR` (restore) around register writes to keep output-compare programming atomic. `getSR`=0x3920, `setSR`=0x3934.

## 10. Complete Ignition Equation

```
Raw_Advance  = BaseLookup(RPM, Load)
Correction1  = KnockRetard() + TempCorrection() + ACCompRetard()
Correction2  = DSC/TorqueReduction() + IdleSpeedComp()
SplitAngle   = LeadingTrailingSplit(RPM, Load, conditions)
Final_Lead   = clamp(Raw_Advance - Correction1 - Correction2 + SplitAngle)
Final_Trail  = clamp(Raw_Advance - Correction1 - Correction2)
Dwell_Time   = DwellLookup(RPM, BatteryVoltage) + DwellOffset
```
`clamp(x)=min(max(x, MinAdvance(RPM)), MaxAdvance(RPM))`; DSC/TorqueReduction = CAN torque request from EBCM.

## 11. Calibration Table Format

**1D descriptor:** `+0` u16 count_x · `+2` u8 type (0=u8,1=u16,2=float) · `+3` pad · `+4` f32* x_axis · `+8` f32* values · `+12` f32 scale · `+16` f32 offset

**2D/3D descriptor:** `+0` u16 count_x · `+2` u16 count_y · `+4` f32* x_axis · `+8` f32* y_axis · `+12` f32* values · `+16` f32 scale · `+20` f32 offset

Lookup fns @0x2068 (1D) and 0x20DC (3D): binary-search axis intervals, linear interpolation, `result = value * scale + offset`.

## 12. Key Calibration Table Addresses (60E1D400)

| Address | Name | Format |
|---|---|---|
| 0x06B68C | RPM correction | 1D (RPM) |
| 0x069F30 | MinSplit (verificato) | 3D (load×RPM) |
| 0x06DB48 | Leading base | 3D (RPM×Load) |
| 0x06D948 | Leading safe | 3D |
| 0x06EEEC | Trailing B | 3D |
| 0x06F0EC | Trailing A | 3D |
| 0x06F2EC | Min split | 1D/2D |
| 0x06D59C | Idle base | 2D |
| 0x06D5C8 | Temp corr | 2D |
| 0x07CB20 | Dwell cal | Const |

## 13. Function Summary Table

| Address | Name | Size | Conf | Layer |
|---|---|---|---|---|
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

**C headers/structs:** MTU2 register defines (sec 1/8), spark_state_8 (sec 4.5/5), chan_cfg 24B@0xDAB4 (sec 5), table_1d/table_2d descriptors (sec 11) serve as the reconstruction headers.

## 14. Open Questions / Uncertainties

1. **Precise table addresses** — cal_tables.csv addresses are J-line variant layout; verify vs 60E1D400.
2. **Coil fire helper (0xAA74)** — may be PWM duty write or compare-register update; needs analysis.
3. **Ion sense detection** — `coil_correction_write_0x50A54` may relate (separate code region).
4. **Split angle formula** — precise lead/trail split not fully verified; `rotor_sync_gate_state_ctrl_2100A` deeper analysis needed.
5. **DSC interaction** — EBCM torque reduction via `dscRelatedTiming` (0x19220); CAN message format unanalyzed.
6. **Check engine light** — `ignition_fault_monitor_458F4` DTC trigger conditions need analysis.
