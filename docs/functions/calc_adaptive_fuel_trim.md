# calc_adaptive_fuel_trim

**Address:** 0x01379C – 0x013880  (228 bytes)
**ROM:** 60E1D400.bin
**Source label:** ida-ai
**Called by:** engineControlCalculateTiming (Phase 2, first call)

---

## Overview

This function computes the **adaptive fuel trim** — a closed-loop correction to
the base fuel injection time based on feedback from the oxygen sensor (lambda).
It implements long-term fuel adaptation to compensate for component wear,
manufacturing tolerances, and changes in fuel quality.

The equinox guide describes adaptive fuel trim as:

> *"The ECU stores learned fuel trims in a table indexed by engine speed and load.
> These trims are applied as multipliers to the base injector pulse width and
> adapt over time to keep the air-fuel ratio at the target lambda."*

---

## Subcalls

| Address | Name | Purpose |
|---------|------|---------|
| 0x2068 | 1D table lookup | Interpolates adaptive trim from calibration table |
| 0x2404 | fpu_compare_and_select | Compares and selects between two float values (for limiting) |

---

## RAM Variables

| Address | Type | Description |
|---------|------|-------------|
| 0xFFFFB5B8 | float | Engine speed (RPM) |
| 0xFFFFB5C4 | float | Fuel trim feedback sensor (lambda / O2 voltage) |
| 0xFFFFB5AC | u8 | Trim table selection flag (0 = table 1, else = table 2) |
| 0xFFFFB5A4 | u8 | Adaptive trim enable flag |
| 0xFFFFA728 | float | Computed load deviation / error signal |
| 0xFFFFA720 | float | **Adaptive trim correction** (output) — final multiplier |
| 0xFFFFA730 | float | RPM threshold status (comparison result) |
| 0xFFFFAADA | float | Output to trailing edge trim |
| 0xFFFFA718 | float | Output to leading edge trim |
| 0xFFFFC084 | u8 | Coolant temperature status (diagnostic enable) |
| 0xFFFFA424 | u8 | Some status flag |

---

## Calibration Tables & Constants

### Table 1 at 0x6A868 — "Table 2D - 106_" (primary adaptive trim)

1D descriptor (type=4 = u8 cells with scale/offset):
| Field | Value |
|-------|-------|
| count_x | 9 |
| type | 4 (u8) |
| axis_x | 0x72C88 |
| values | 0x72CAC |

**X-axis (load deviation, %):**
[-100, -75, -50, -25, 0, 25, 50, 75, 100]

**Values (raw u8, center = 128 = stoich):**
| Load Dev | Raw | Interpretation |
|----------|-----|----------------|
| -100% | 156 | Rich (more fuel) |
| -75% | 148 | Rich |
| -50% | 140 | Rich |
| -25% | 140 | Rich |
| 0% | 128 | Stoich (no correction) |
| +25% | 128 | Stoich |
| +50% | 116 | Lean |
| +75% | 108 | Lean |
| +100% | 96 | Lean (less fuel) |

### Table 2 at 0x6A87C — "Table 2D - 107_" (secondary adaptive trim)

Same axis but different, more conservative values:
| Load Dev | Raw | Interpretation |
|----------|-----|----------------|
| -100% | 156 | Rich |
| -75% | 148 | Rich |
| -50% | 140 | Rich |
| -25% | 140 | Rich |
| 0% | 128 | Stoich |
| +25% | 128 | Stoich |
| +50% | 128 | Stoich |
| +75% | 128 | Stoich |
| +100% | 128 | Stoich |

### Scalar Constants

| Address | Value | Description |
|---------|-------|-------------|
| 0x00072C60 | 1500.0 | RPM threshold for enabling adaptation |
| 0x00072C64 | 0.009766 | Integral gain (~1/1024 per tick) |
| 0x00072C5C | 0.0 | Minimum error threshold (deadband) |
| 0x00072C68 | 0.6 | Adaptation speed / proportional gain |
| 0x00072C6C | -2.8 | Negative trim limit |
| 0x00072C70 | 0.7 | Positive trim limit |

---

## Control Flow

### Phase 1: Load inputs and compute error

```
r3 = 0xFFFFB5B8            ; RPM address
fr15 = [0xFFFFB5B8]        ; load RPM
r2 = 0xFFFFB5C4            ; O2 feedback
fr14 = [0xFFFFB5C4]        ; load O2 sensor / lambda
r1 = 0xFFFFB5??            ; target lambda?
fr3 = [target]             ; load target
fr2 = fr15 - fr3           ; compute error = RPM - target? or actual - target?
[0xFFFFA728] = fr2         ; store error signal
```

### Phase 2: Table selection and interpolation

```
r0 = 0xFFFFB5AC            ; table selection flag
if [0xFFFFB5AC] == 0:
    r4 = 0x6A868            ; use Table 1 (primary trim table)
else:
    if [0xFFFFB5A4] == 0:
        r4 = 0x6A868        ; if not enabled, also use Table 1
    else:
        r4 = 0x6A87C        ; use Table 2 (secondary trim table)

call 0x2068                 ; 1D table lookup(descriptor=r4, input=fr2)
[0xFFFFA720] = fr0          ; store interpolated trim value
```

### Phase 3: Adaptation enable check

```
r3 = 0xFFFFC084             ; coolant temp status
if [0xFFFFC084] == 1:       ; if engine is warm (closed loop enabled)
    r2 = 0x72C60            ; RPM threshold = 1500
    if RPM > 1500:
        r1 = 0x72C64        ; integral gain = 0.009766
        r3 = 0xFFFFC084     ; speed threshold check
        if speed >= threshold:
            ; Adaptation active path
            ; Use trimmed value from 0xFFFFA720
        else:
            ; Zero out trim
            fr15 = 0.0
```

### Phase 4: Limiting and storage

```
fr5 = [0x72C68] = 0.6       ; proportional limit
fr4 = fr5                   ; copy
fr3 = [mova pool] = some value
if fr14 > fr5:              ; if O2 feedback > 0.6
    ; Set enable flag
else:
    ; Check with threshold
    if fr14 > fr4:          ; if O2 feedback > fr4
        ; Clear enable flag

; Apply limits
r2 = [0x72C70] = 0.7        ; positive limit
r3 = [0x72C6C] = -2.8       ; negative limit
call 0x2404                  ; fpu_compare_and_select(trim, -2.8, 0.7)
fr15 = result               ; clipped trim value

; Store output
[0xFFFFA718] = fr15         ; leading edge fuel trim
```

---

## Adaptive Fuel Trim Strategy

The adaptive fuel trim algorithm works as follows:

1. **Error computation:** The difference between the target lambda (or RPM-based
   reference) and the actual O2 sensor reading is computed.

2. **Table lookup:** The error is used to index into one of two 1-D calibration
   tables (selected by a flag). The tables map load deviation to a raw trim
   value (128 = stoich, < 128 = lean, > 128 = rich).

3. **Enable conditions:** Adaptation only runs when:
   - Engine coolant temperature indicates closed-loop operation
   - RPM is above 1500

4. **Integration:** The trimmed value is accumulated with an integral gain of
   ~0.009766 per tick, providing long-term adaptation.

5. **Limiting:** The final trim is clamped to [-2.8%, +0.7%] to prevent
   excessive correction.

6. **Output:** The trim value is written to RAM for consumption by the injector
   pulse width calculation functions.

---

## Relationships

```
engineControlCalculateTiming (0x14584)
  ├── Phase 1: calc_ignition_all_rotors_13C2C  ◄── ignition
  └── Phase 2: calc_adaptive_fuel_trim       ◄── THIS
        ├── 1D lookup 0x2068 (table 0x6A868 or 0x6A87C)
        └── fpu_compare_and_select 0x2404
```

The output at 0xFFFFA720 is read by:
- `calc_fuel_trim_correction_map` (0x136F0)
- `calc_fuel_correction_all_modes` (0x12C8C)
- `fuel_injector_pulse_calc` (0x10620)
