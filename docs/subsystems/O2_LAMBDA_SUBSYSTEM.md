# RX-8 ECU: O2 / Lambda Sensor Processing & Closed-Loop Fuel Control

Closed-loop fuel trim subsystem (ROM 60E1D400). Narrowband zirconia O2 sensor front (pre-cat) for closed-loop control; second narrowband rear (post-cat) for catalyst efficiency monitoring.

```
Front O2 (ADC) → read_o2_sensor_voltage_trim → calc_closed_loop_fuel_status
  → calc_adaptive_fuel_trim (LTFT learning) → per-rotor trim → injector PW
```

## 1. Key Functions

| Address | Name | Purpose |
|---------|------|---------|
| 0x01412A | read_o2_sensor_voltage_trim | Read raw O2 ADC, validate |
| 0x01418C | calc_lambda_integration_time | Integration timer for closed-loop |
| 0x0141B8 | calc_closed_loop_fuel_status | **Main STFT computation** |
| 0x014220 | calc_o2_voltage_to_index_front | O2 voltage → trim index (front) |
| 0x0142E8 | calc_o2_voltage_to_index_rear | O2 voltage → trim index (rear) |
| 0x01379C | calc_adaptive_fuel_trim | **LTFT adaptation & learning** |
| 0x011A34 | calc_lambda_feedback_pid | Closed-loop task dispatcher (16 jsr + 1 tail jmp); see `PID_CONTROLLERS.md` §4 |
| 0x01437C | calc_engine_temp_fuel_trim | Temperature-based fuel trim |
| 0x014496 | calc_deadband_fuel_trim | Deadband compensation |
| 0x0136F0 | calc_fuel_trim_correction_map | Per-rotor correction map |
| 0x014722 / 0x014742 | calc_fuel_trim_correction_cyl_A/B | Rotor A / B trim application |
| 0x00C508 | lambda_control_closed_loop | Dispatcher for closed-loop modes |
| 0x019480 | exhaust_oxygen_control_19480 | State machine for O2 control |
| 0x01321C | calc_secondary_o2_trim | Secondary O2 trim |
| 0x012B54 | write_o2_sensor_trim | Copy trim to output |
| 0x00D478 | getRearO2Voltage | Read rear O2 voltage |
| 0x01E794 | getRearO2FilteredValue | Filtered rear O2 |
| 0x01B3EA | o2_sensor_transfer_function | O2 transfer characteristics |
| 0x002500 | FUN_00002500 | FMAC helper (fused multiply-accumulate) |
| 0x002404 | FUN_00002404 | Float clamp helper |
| 0x002068 | FUN_00002068 | EEPROM read / interpolation helper |
| 0x002478 / 0x002460 | FUN_00002478 / 0x2460 | Increment / decrement w/ saturation |
| 0x02DDF6 | closed_loop_correction_2DDF6 | Closed-loop correction (STFT) |
| 0x02DF0A | closed_loop_correction_long_2DF0A | Closed-loop correction (LTFT) |

## 2. Front O2 Sensor (Pre-Catalyst)

### `read_o2_sensor_voltage_trim` (0x01412A)
O2 readiness counter @RAM `0xA768`; if value < 21, increment (capped) through `FUN_00002478`. Tracks O2 warm-up/readiness.

RAM: `0xA768` (1B) readiness counter · `0xAA10` (4B float) O2 voltage.

### `calc_lambda_integration_time` (0x01418C)
Manages integration timer `0xFFFFA772`. If engine-speed signal `0xADC8` > cal `0x00072D6C` (= 2.5) → timer decrements from reload 7 (`0x00072D4A`) to 0; if ≤ 2.5 → reload to 7. Hysteresis/delay for entering/exiting closed-loop.

### `calc_closed_loop_fuel_status` (0x0141B8) — main STFT
```c
void calc_closed_loop_fuel_status(void) {
    float o2_state = (float)(*(uint8_t*)0xA768);          // 0..21 counter
    *(float*)0xFFFFA77C = sub_014220(o2_state);           // front trim index
    *(float*)0xFFFFA780 = sub_0142E8(o2_state);           // rear trim index
    float voltage_offset = *(float*)0xAA10 - *(float*)0x00072D70; // - 5.0
    float cal_range      = *(float*)0x00072D74 - *(float*)0x00072D70; // 60.0-5.0 = 55.0
    float trim_factor = clamp(cal_lookup(voltage_offset, cal_range), 0.0f, 1.0f);
    *(float*)0xA760 = *(float*)0xFFFFA77C * trim_factor;  // STFT bank A
    *(float*)0xA764 = *(float*)0xFFFFA780 * trim_factor;  // STFT bank B
}
```
Calibration lookup helper pointer @0x0003ED0C (unresolved).

### Voltage → Index mapping (sub_014220 front / sub_0142E8 rear)
Threshold-based lookup: find first `i` where `o2_state <= threshold[i]` (bound by `0x6A8B9` size flag), then output `index_table[idx]/255.0`.

- Front: thresholds `0x00072D78` = [0.0, 1.0, 2.0, 3.0]; index table `0x00072DD0` = [0x8C(140)..., 0x64(100)...]
- Rear: thresholds `0x00072DE8` = [0.0, 1.0, 2.0, 3.0]; index table `0x00072E40` = [0x8C(140)..., 0x64(100)...]

## 3. Long-Term Fuel Trim (LTFT): `calc_adaptive_fuel_trim` (0x01379C)

```c
void calc_adaptive_fuel_trim(void) {
    float o2_voltage = *(float*)0xB5B8;                    // front O2 (dup)
    float temp       = *(float*)0xC12C;                    // coolant temp
    *(float*)0xFFFFA728 = o2_voltage - *(float*)0xB5C4;    // working store (vs ref)
    // EEPROM adaptive table select: 0x6A868 (A) / 0x6A87C (B)
    //   if *0xB5A4==0: *0xB5AC==0 → A else B
    //   else:          *0xB5AA==1 → A else B
    *(float*)0xFFFFA720 = read_eeprom_adaptive(sel, offset); // via FUN_00002068
    float ltft = 0.0f;
    if (*(uint8_t*)0xAADA == 1 &&                          // closed-loop
        o2_voltage > 1500.0 &&                             // 0x00072C60
        (temp > 0.009765625 || *(uint16_t*)0xA424 >= 375)) // 0x00072C64 | 0x00072C5C
        ltft = *(float*)0xFFFFA720;
    // PI update (status 0xFFFFA730 == 1): P=-2.8 (0x72C6C), I=0.7 (0x72C70), clamp ±0.6 (0x72C68)
    *(float*)0xA718 = clamp(ltft*P + I, -0.6, 0.6);
}
```
EEPROM adaptive tables 0x6A868/0x6A87C store trim indexed by load/RPM cells.

## 4. Rear O2 Sensor (Post-Catalyst)

### `getRearO2Voltage` (0x00D478)
```c
*(float*)0xFFFFA3E4 = (float)*(uint16_t*)0xFFFF9EF2 * 7.62939e-05f; // ADC→V
```
Scale 7.62939e-05 ≈ 1/13107: 0–5V / 65536 counts ≈ 76.3 µV/count (divider for 0–1V O2 signal).

### `getRearO2FilteredValue` (0x01E794)
First-order lag filter (`FUN_000023B0`) on `0xAD98` → `0xFFFFB0F0`; hysteresis comparator vs thresholds `0x00071584`/`0x00071588` and ref `0xB0E8`: filtered < ref → `0xB0EC`=1 (lean); > ref−thr_hi → 0 (rich); else hold (hysteresis).

## 5. Helper Utilities

| Func | Behavior |
|------|----------|
| FUN_00002500 (0x2500) | FMAC: `result = acc + mul * (float)u8_val` |
| FUN_00002404 (0x2404) | Clamp value to [lower, upper] |
| FUN_00002068 (0x2068) | EEPROM table read w/ interpolation (uses FMAC); adaptive trim tables @0x6A868/0x6A87C |
| FUN_000023B0 | First-order filter (`y[n]=g*x+(1-g)*y[n-1]`) |

## 6. Calibration Tables

| Address | Type | Value | Description |
|---------|------|-------|-------------|
| 0x00072C5C | uint16 | 375 | Min RPM for LTFT adaptation |
| 0x00072C60 | float | 1500.0 | O2 voltage threshold for adaptation enable |
| 0x00072C64 | float | 0.009765625 | Coolant temperature threshold |
| 0x00072C68 | float | 0.6 | LTFT trim limit (±60%) |
| 0x00072C6C | float | -2.8 | Proportional gain (P) |
| 0x00072C70 | float | 0.7 | Integral gain (I) |
| 0x00072D6C | float | 2.5 | Integration time calibration |
| 0x00072D4A | uint16 | 7 | Integration timer reload |
| 0x00072D70 | float | 5.0 | O2 voltage offset reference |
| 0x00072D74 | float | 60.0 | Voltage range calibration |
| 0x00072D78 | float[4] | [0,1,2,3] | Front O2 thresholds |
| 0x00072DD0 | uint8[] | [0x8C.., 0x64..] | Front O2 index→value lookup |
| 0x00072DE8 | float[4] | [0,1,2,3] | Rear O2 thresholds |
| 0x00072E40 | uint8[] | [0x8C.., 0x64..] | Rear O2 index→value lookup |
| 0x0006A868 | EEPROM | — | Adaptive trim table A |
| 0x0006A87C | EEPROM | — | Adaptive trim table B |

## 7. RAM Map

**Note:** SH-2E `mov.w` sign-extends addresses with bit 15 set to the 0xFFFFxxxx peripheral RAM region.

| 16-bit | Effective | Size | Type | Description |
|--------|-----------|------|------|-------------|
| 0xA768 | 0xFFFFA768 | 1B | uint8 | O2 readiness counter |
| 0xAA10 | 0xFFFFAA10 | 4B | float | Front O2 voltage |
| 0xA760 | 0xFFFFA760 | 4B | float | STFT bank A |
| 0xA764 | 0xFFFFA764 | 4B | float | STFT bank B |
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
| 0xC12C | 0xFFFFC12C | 4B | float | Coolant temp |
| 0xADC8 | 0xFFFFADC8 | 4B | float | Engine speed/load (timer input) |
| 0xA772 | 0xFFFFA772 | 2B | uint16 | Integration timer |
| 0x9EF2 | 0xFFFF9EF2 | 2B | uint16 | Rear O2 ADC count |
| 0xA3E4 | 0xFFFFA3E4 | 4B | float | Rear O2 voltage |
| 0xB0F0 | 0xFFFFB0F0 | 4B | float | Rear O2 filtered |
| 0xB0EC | 0xFFFFB0EC | 1B | uint8 | Rear O2 lean/rich flag |
| 0xA8B9 | 0x0006A8B9 | 1B | uint8 | O2 lookup table size flag |
| 0xA6B7/0xA6B8/0xA6B9 | 0xFFFFA6B7-9 | 1B | uint8 | Secondary O2 trim flags A/B/C |
| 0xA9DD | 0xFFFFA9DD | 1B | uint8 | O2 control state machine state |
| 0xAD8C | 0xFFFFAD8C | 4B | float | Secondary O2 voltage |
| 0xAA1C | 0xFFFFAA1C | 4B | float | O2-related signal |

## 8. Control Flow & State Machine

**Open-loop → closed-loop** when: O2 readiness counter (0xA768) reaches 21; coolant temp above warm-up threshold; integration timer (0xFFFFA772) counted to 0; engine speed/load in CL enable range. Closed-loop flag `0xAADA` set to 1.

**STFT cycle** (each engine cycle): read O2 voltage → validate readiness → `calc_closed_loop_fuel_status` (front/rear trim index paths; trim factor = lookup of (V−5.0), clamp [0,1]; multiply both banks) → store 0xA760/0xA764 → `calc_adaptive_fuel_trim` (read EEPROM table, check conditions, PI update, clamp ±0.6) → store 0xA718.

**LTFT adaptation requires ALL**: closed-loop (`0xAADA==1`) AND O2 voltage > 1500.0 (0x72C60) AND (coolant temp > 0.0097 (0x72C64) OR RPM ≥ 375 (0x72C5C)).

**Fail-safe** (`exhaust_oxygen_control_19480`): monitors heater status (flags 0xA6B7/0xA6B8/0xA6B9), response time, signal plausibility. On fault: freeze adaptive trim, clear closed-loop (revert open-loop), set DTCs.

## 9. Key Calibration Observations

1. **LTFT PI has negative P gain (−2.8)**: higher LTFT = richer, so negative P gives negative feedback.
2. **Trim limit 0.6 (60%)** is generous — compensates large fuel-system variation.
3. **5.0V reference offset**: narrowband circuit with 5V bias/pull-up.
4. **Timer reload 7 @ threshold 2.5** gives closed-loop entry/exit hysteresis (no oscillation at boundary).
5. **Lookup values 0x8C (140) rich / 0x64 (100) lean** → percent-scale outputs (140%/100% base fuel).

## 10. OBD-II Interface

- **`getSTFTforOBD`** (0x535A6): reads 0xFFFFA77C, bias −1.0, ×100, s8 (−128..+127 → −100%..+99.6%)
- **`getLTFTforOBD`** (0x535CC): reads 0xFFFFA720, ×100, s8

PIDs: 0x06 STFT B1S1 · 0x07 LTFT B1S1 · 0x08 STFT B1S2 · 0x09 LTFT B1S2.

## 11. Open Questions

1. EEPROM adaptive trim structure at 0x6A868/0x6A87C (likely load/RPM-indexed cells) not fully known.
2. Exact per-rotor trim mechanism of `calc_fuel_trim_correction_cyl_A/B` needs analysis.
3. Whether rear O2 (0xFFFFA780 path) actually participates in fuel trim or is catalyst-only.
4. Calibration lookup pointer @0x0003ED0C unresolved.
5. The 1500.0 threshold for O2 voltage seems high — possibly an ECT value misinterpreted.

## 12. Architecture Summary

```
Front O2 ADC → getRearO2Voltage(0xD478)→0xFFFF9EF2/0xFFFFA3E4
  → read_o2_sensor_voltage_trim → counter @0xA768 (warm-up)
  → calc_closed_loop_fuel_status
      ├─ sub_014220 (front idx) → 0xFFFFA77C
      ├─ sub_0142E8 (rear idx)  → 0xFFFFA780
      └─ trim = f(O2V−5.0); STFT_A = idx·trim → 0xA760; STFT_B → 0xA764
  → calc_adaptive_fuel_trim
      ├─ EEPROM 0x6A868/0x6A87C
      ├─ PI (P=−2.8, I=0.7), clamp ±0.6
      └─ LTFT → 0xA718
  → calc_engine_temp_fuel_trim → 0xA788/0xA78C
  → calc_fuel_trim_correction_cyl_A/B (per-rotor)
  → exhaust_oxygen_control_19480 (heater, sensor health, DTCs)
```
