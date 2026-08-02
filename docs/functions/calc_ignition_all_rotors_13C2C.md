# calc_ignition_all_rotors_13C2C

**Address:** 0x013C2C – 0x013CFC  (208 bytes)
**ROM:** 60E1D400.bin
**Source label:** ida-ai
**Called by:** engineControlCalculateTiming (Phase 1, slot 7)

---

## Overview

This is the **main ignition timing calculation** for all rotors. It is called
once per scheduler tick from `engineControlCalculateTiming` (0x14584). The function
reads current engine speed, knock status, and temperature flags; looks up a base
ignition correction from a 1-D calibration table; applies knock- and temperature-based
corrections; then dispatches the result to the per-rotor hardware output via three
helper subroutines.

The ECU strategy documented in the equinox guide describes ignition timing as:

> `ignition_angle = base_advance + knock_correction + temperature_correction + load_correction`

This function computes the **correction terms** and combines them with the base
advance value. The final timing value (in degrees BTDC) is written to two RAM
locations for the trailing-edge and leading-edge coil drivers respectively.

---

## Subcalls

| Address | Name | Purpose |
|---------|------|---------|
| 0x13ED2 | compare_select_two_float_values | Selects min/max of two float pairs, returns two values |
| 0x13E6C | calc_fuel_pump_control_output | Writes final ignition timing to trailing edge output |
| 0x13EE6 | calc_fuel_pressure_load_compensation | Writes to leading edge output with pressure correction |

---

## RAM Variables

| Address | Type | Description |
|---------|------|-------------|
| 0xFFFFA73C | float | Engine speed (RPM) — read as fr6 |
| 0xFFFFA740 | u8 | Ignition enable / knock status byte |
| 0xFFFFA744 | float | Output: ignition timing value (written by 0x13E6C, also read as fr5 input) |
| 0xFFFFA748 | u8 | Knock sensor fault status (0 = OK, non-zero = fault/override) |
| 0xFFFFA749 | u8 | Knock detected flag |
| 0xFFFFA74C | float | Scratch / intermediate timing value |
| 0xFFFFA75C | u8 | Knock control active flag (read at end, stored as byte) |
| 0xFFFFB5B8 | float | Engine RPM (alternative read — maybe filtered vs raw) |
| 0xFFFFC0C4 | u8 | Coolant temperature status flag (== 1 when engine is warm?) |
| 0xFFFFC0C5 | u8 | ECT correction enable flag |

---

## Calibration Tables & Constants

### 1-D Table at 0x6B68C — RPM-based ignition correction

**Descriptor format (SH-2E 1D lookup):**
| Offset | Size | Value | Description |
|--------|------|-------|-------------|
| +0 | u16 | 5 | count_x (number of RPM breakpoints) |
| +2 | u8 | 4 | type = u8 cells with scale/offset |
| +3 | u8 | 0 | padding |
| +4 | f32* | 0x000798D4 | X-axis pointer (RPM breakpoints) |
| +8 | f32* | 0x000798E8 | Values pointer (u8 correction values) |
| +12 | f32 | 0.5 | scale = RPM correction = raw * 0.5 - 64.0 |
| +16 | f32 | -64.0 | offset |

**X-axis (RPM):** [2000, 2500, 3000, 4500, 5000]

**Values (raw u8 → actual):**
| RPM | Raw | Actual (deg) | Notes |
|-----|-----|-------------|-------|
| 2000 | 108 | -10.0 | Cold/high idle retard |
| 2500 | 108 | -10.0 | Cruise retard |
| 3000 | 108 | -10.0 | Cruise retard |
| 4500 | 108 | -10.0 | Moderate load retard |
| 5000 | 128 | 0.0 | No correction at high RPM |

This table provides a **negative correction (retard)** at low-to-mid RPM and
neutral correction at high RPM. This is consistent with an ignition timing
temperature-protection or knock-avoidance strategy.

### Scalar Constants in ROM

| Address | Value | Description |
|---------|-------|-------------|
| 0x0007987C | 0.0f | Zero — used as "no correction" value |
| 0x00079890 | 2.5f | Maximum knock retard amount (degrees) |
| 0x00079880 | 1.0f | Default correction multiplier (warm-up compensation) |
| 0x00079888 | 1.0f | Default correction multiplier (alternate path) |
| 0x0007983B | 0x01 (u8) | RPM threshold flag for knock retard table selection |

---

## Control Flow

### Phase 1: Context save and input loading
```
push r14, r13, r12, fr15, fr14, pr
r12 = 0xFFFFA744    ; ignition timing output address
fr5 = [0xFFFFA744]   ; load previous timing
r13 = 0xFFFFA73C    ; RPM address
fr15 = fr5           ; save previous timing
r3 = 0xFFFFA740     ; byte flag address
fr6 = [0xFFFFA73C]   ; load RPM
r14 = [0xFFFFA740]   ; load byte flag
fr4 = fr6            ; copy RPM
r1 = 0xFFFFA748     ; knock status address
r2 = [0xFFFFA748]    ; load knock status byte
```

### Phase 2: Knock sensor fault check
```
tst r2, r2           ; is knock byte == 0?
bf L_013c56          ; if non-zero, knock sensor is active/faulted
  ; --- NO KNOCK path ---
  fr14 = 0.0          ; zero correction
  fr15 = 0.0          ; set timing correction to zero
  bra L_013c8a        ; jump to temperature correction check
L_013c56:  ; --- KNOCK ACTIVE path ---
  r2 = 0xFFFFA749    ; knock detected flag
  r0 = [0xFFFFA749]
  tst r0, r0
  bf L_013c74        ; if knock detected, go to heavy retard
    ; --- Light retard path ---
    r3 = 0xFFFFB5B8  ; RPM (alternate read)
    fr4 = [0xFFFFB5B8]
    r4 = 0x6B68C     ; 1D RPM correction table
    r1 = 0x2068      ; 1D lookup function
    call 0x2068      ; interp RPM correction
    fr15 = fr0       ; correction = table lookup result
    [0xFFFFA74C] = fr0  ; save to scratch
    bra L_013c8a
  L_013c74:  ; --- Heavy retard path (knock detected) ---
    r0 = 0xFFFFA75C  ; knock control active byte
    r3 = [0xFFFFA75C]
    tst r3, r3
    bf L_013c8e      ; if knock control active, go to detailed check
      ; No knock control: check enable flag
      r0 = r14 (0xFFFFA740 byte)
      cmp/eq #1, r0
      bf L_013cce    ; if not enabled, skip to end
      ; Enabled: use 0.0 correction
      r2 = 0x7987C   ; constant 0.0f
      fr15 = [0x7987C] = 0.0
      bra L_013c8a
  L_013c8e:  ; --- Knock control active path ---
    r0 = r14 (0xFFFFA740)
    cmp/eq #1, r0
    bf L_013cce      ; if not in correct mode, skip
    ; Check RPM threshold
    r3 = 0xFFFFB5B8  ; RPM
    r0 = 0x7983B     ; threshold byte
    r2 = [0xFFFFB5B8]
    r1 = [0x7983B]   ; threshold
    cmp/hs r1, r2    ; if RPM >= threshold
    bf L_013cac
      ; RPM high: use constant 0.0 from table
      r2 = 0x79890   ; 2.5f
      fr4 = fr6      ; RPM value
      fr3 = [0x79890] ; 2.5
      fr4 = fr4 - fr3 ; RPM - 2.5 (??)

    ... this path gets complex ...
```

### Phase 3: Temperature correction
```
Check byte at 0xFFFFC0C4 (coolant temperature status)
If == 1, check byte at 0xFFFFC0C5
  If 0xFFFFC0C5 != 0: use correction from 0x79888 (1.0f)
  If 0xFFFFC0C5 == 0: use correction from 0x79880 (1.0f)
Subtract correction from fr15 (retard timing based on temperature)
```

### Phase 4: Final dispatch
```
call 0x13ED2  ; compare_select_two_float_values
  [0xFFFFA73C] = result  ; update RPM? (or timing value)
call 0x13E6C  ; calc_fuel_pump_control_output(fr15)
  [0xFFFFA744] = result  ; trailing edge ignition timing
call 0x13EE6  ; calc_fuel_pressure_load_compensation
  + output to 0xFFFFA734/0xFFFFA738 (ignition timing values, written identically;
    lead/trail split applied later in rotor_sync_gate_state_ctrl_2100A (0x2100A), unverified)
[0xFFFFA75C] = r14      ; save byte flag back
```

---

## Ignition Timing Formula

Based on the analysis, the ignition timing strategy works as follows:

```
ignition_timing = base_ignition_advance
                + knock_correction
                + rpm_dependent_correction
                + temperature_correction
```

Where:
- **base_ignition_advance**: Pre-computed in a separate function (loaded from RAM at 0xFFFFA744)
- **knock_correction**: 0.0 if no knock detected; -2.5° if knock is active (from 0x79890); or interpolated from the 1D RPM correction table (0x6B68C)
- **rpm_dependent_correction**: -10.0° below 5000 RPM, 0.0° above 5000 RPM (from table 0x6B68C)
- **temperature_correction**: -1.0° if warm, 0.0° if cold (from constants at 0x79880/0x79888)

The function writes final timing values to:
- 0xFFFFA744: Main ignition advance (float, degrees BTDC)
- 0xFFFFA734/0xFFFFA738: Ignition timing values (float, degrees BTDC) — written
  identically by this function; the lead/trail split is applied later in
  rotor_sync_gate_state_ctrl_2100A (0x2100A, not yet emulated)

---

## Relationships

```
engineControlCalculateTiming (0x14584)
  ├── calc_combustion_efficiency_metric (0x121F0)
  ├── calc_combustion_load_factor (0x1237C)
  ├── getKnockControlAllowed (0x13A0E)
  ├── getKnockSensorFaultedStatus (0x13A5E)
  ├── getKnockControlActive (0x13A86)
  ├── updateKnockMaxRAM (0x13B90)
  ├── calc_ignition_all_rotors_13C2C (0x13C2C)  ◄── THIS
  │     ├── 1D lookup 0x2068 (table 0x6B68C)
  │     ├── compare_select_two_float_values (0x13ED2)
  │     ├── calc_fuel_pump_control_output (0x13E6C)
  │     └── calc_fuel_pressure_load_compensation (0x13EE6)
  └── cooling_fan_control (0x17DCC)
```

---

## Verification Notes

- The 1D lookup function at 0x2068 (formerly labeled `fpu_multiply_accumulate` in IDA, now `2DLookup`) is actually a **general 1D table interpolation** with configurable cell type and optional scale/offset. Its signature is:
  - r4 = table descriptor pointer
  - fr4 = X input
  - returns fr0 = interpolated value
- The table at 0x6B68C uses u8 cells with scale=0.5 and offset=-64.0, giving effective range [-64, 63.5] in 0.5° steps.
- All three sub-calls (0x13ED2, 0x13E6C, 0x13EE6) are shared with `calc_fuel_injection_all_rotors`.
