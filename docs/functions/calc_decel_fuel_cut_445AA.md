# calc_decel_fuel_cut_445AA

**Address:** 0x0445AA – 0x044694  (234 bytes)
**ROM:** 60E1D400.bin
**Source label:** ghidra-hand-xmap
**Called by:** engineControlCalculateTiming (Phase 2)

---

## Overview

This function implements the **fuel cut on throttle lift / over-run** strategy.
When the driver lifts off the throttle at speed, fuel injection is temporarily
suspended to improve fuel economy and reduce emissions. The function evaluates
several conditions (throttle position, vehicle speed or RPM, various enable flags)
and sets a fuel-cut flag accordingly.

The equinox guide describes this as:

> *"Deceleration fuel cut — when throttle is closed and RPM is above a threshold,
> fuel injectors are disabled until RPM drops or throttle opens."*

---

## RAM Variables

| Address | Type | Description |
|---------|------|-------------|
| 0xFFFFCA2C | float | Throttle position sensor voltage / angle |
| 0xFFFFCA38 | float | Engine speed (RPM) for fuel cut decision |
| 0xFFFFCAB5 | u8 | **Fuel cut flag** (output): 1 = fuel cut, 0 = normal fueling |
| 0xFFFFCABB | u8 | Override flag: if 1, force NO fuel cut |
| 0xFFFFCAB9 | u8 | Decel fuel cut enable flag |
| 0xFFFFCAB4 | u8 | Fuel cut active status / mode |
| 0xFFFFCAAC | u8 | Fuel cut accumulator / counter |
| 0xFFFFCAB6 | u8 | Secondary fuel cut flag |
| 0xFFFFCA88 | u8 | Saturation accumulator output |

---

## Calibration Constants

| Address | Type | Value | Description |
|---------|------|-------|-------------|
| 0x0007B3DC | u8 | 0x01 | Feature enable byte |
| 0x0007B3DD | u8 | 0x00 | Feature disable byte |
| 0x0007B418 | f32 | 0.01 | Throttle-closed voltage threshold |
| 0x0007B41C | f32 | 50.0 | RPM threshold for fuel cut (x100 RPM? or speed?) |

---

## Control Flow

### Entry
```
push r14, pr
r3 = 0xFFFFCA2C            ; throttle position address
r4 = 0xFFFFCAB5            ; fuel cut flag output address
fr4 = [0xFFFFCA2C]         ; load throttle position
r2 = 0xFFFFCABB            ; override flag address
r0 = [0xFFFFCABB]          ; load override
r5 = 0                     ; default: clear flag (no fuel cut)
```

### Check 1: Override flag
```
if [0xFFFFCABB] == 1:
    goto SET_NO_FUEL_CUT     ; override forces normal fueling
```

### Check 2: Decel fuel cut enable (0xFFFFCAB9)
```
if [0xFFFFCAB9] != 1:
    goto CHECK_THROTTLE_AND_SPEED  ; not enabled, check other conditions

if [0x0007B3DC] != 1:              ; ROM calibration enable check
    goto CHECK_THROTTLE_AND_SPEED
; If both conditions met:
goto SET_NO_FUEL_CUT               ; force no fuel cut
```

### Check 3: Main fuel cut logic
```
L_044608:
if [0xFFFFCAB4] != 1:      ; fuel cut mode check
    goto SET_FUEL_CUT       ; not in override mode → allow fuel cut

; RPM threshold check
fr3 = [0x0007B418] = 0.01   ; throttle closed threshold
fr2 = [0xFFFFCA38]           ; engine speed value
if fr2 > fr3:                ; if speed > threshold
    goto SET_FUEL_CUT        ; → allow fuel cut

; Throttle position check
fr1 = [0xFFFFCA38]           ; re-read speed (or different var)
if fr4 > fr1:                ; if throttle > speed threshold
    goto CHECK_ACCUMULATOR   ; throttle open → check accumulator
    ; (fr4 is throttle position from entry)

; !!! NOTE: The disassembly shows multiple comparisons using
; 0xFFFFCA38, 0xFFFFCAAC, 0x0007B41C (50.0), 0x0007B3DD (0x00)
; These form a hysteresis / debounce logic:

Check accumulator flow:
- If RPM > 50.0: check accumulator
- If accumulator count > 0: allow fuel cut
- If calibration disable byte == 0: skip advanced checks
- If decel flag == 1: set fuel cut
```

### Decision outputs
```
SET_NO_FUEL_CUT:
    [0xFFFFCAB5] = 0        ; clear fuel cut flag (normal fueling)
    goto EXIT

SET_FUEL_CUT:
    [0xFFFFCAB5] = 1        ; set fuel cut flag (suspend fueling)

EXIT:
    ; Accumulator management using addSaturate8Bit (0x2478)
    [0xFFFFCA88] = addSaturate8Bit([0xFFFFCAAC], fuel_cut_flag)
    pop r14, pr
    return
```

---

## Strategy Summary

The throttle lift fuel cut algorithm implements:

```
fuel_cut = 0  (normal fueling)  -- default

IF override_flag == 1:
    fuel_cut = 0                  ; forced normal
ELIF decel_enable == 1 AND cal_enable == 1:
    fuel_cut = 0                  ; forced normal (overrides decel)
ELIF fuel_cut_mode == 0:
    fuel_cut = 1                  ; mode not active → cut fuel
ELIF rpm_sensor > 0.01:
    fuel_cut = 1                  ; speed detected → cut fuel
ELIF throttle > rpm_sensor:
    ; throttle more open than RPM → re-evaluate with hysteresis
    IF accumulator > 0 OR high_RPM:
        fuel_cut = 1
    ELSE:
        fuel_cut = 0
ELIF rpm > 50 AND accumulator > 0:
    fuel_cut = 1
ELIF cal_disable_byte == 0 AND decel_flag == 1:
    fuel_cut = 1
ELSE:
    fuel_cut = 0
```

The fuel cut flag at 0xFFFFCAB5 is read by:
- `fuel_cut_logic` (0x4490A)
- `calc_fuel_cut_flags_merged` (0x11140)
- `calc_fuel_injection_all_rotors` (0x13D3C)

---

## Calibration Effect

The two float constants control the RPM thresholds:
- **0.01** at 0x7B418: effectively zero — any non-zero RPM reading enables fuel cut
- **50.0** at 0x7B41C: secondary RPM threshold for the accumulator/hysteresis path

The two byte constants enable/disable features:
- **0x01** at 0x7B3DC: enables the override path
- **0x00** at 0x7B3DD: calibration disable for the accumulator path
