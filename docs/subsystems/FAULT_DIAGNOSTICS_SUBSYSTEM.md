# RX-8 ECU Fault Handling & Diagnostics Subsystem (60E1D400.bin)

## Overview

OBD-II-compliant fault handling subsystem: fault detection, persistent DTC storage with debounce, DTC set/clear/report, readiness monitors, limp mode, recovery.

## Memory Map

| Address Range | Region | Description |
|---|---|---|
| `0x00000000-0x0007FFFF` | Flash ROM | Program + constant data (512KB) |
| `0xFFFF8000-0xFFFFF000` | Backup RAM | Fault flags, DTC storage, runtime vars |
| `0x0007E4DC` | ROM | Fault Status Definition Table |
| `0x0007ECD0` | ROM | Alternative fault check reference table |

### Fault Status Table (@0x7E4DC)

32-bit-per-entry, indexed by fault code (word-offset = code×4):

```
Bit 31-16 (Upper Word):  Secondary check bitmask
Bit 15-0  (Lower Word):  Primary classification/mask
```

Observed values:

| Value | Meaning |
|---|---|
| `0x08800004` | C ranked, emission-related |
| `0x00800004` | Standard (lower 8 bits = 0x04) |
| `0x00800006` | Standard, higher severity (0x06) |
| `0x40800004` | Performance/serious |
| `0x40800006` | Performance, higher severity |
| `0x48800004` | Critical (CPU/memory related) |
| `0x48800006` | Critical, elevated severity |
| `0x58800004` | Most severe fault class |
| `0x08800000` | C class, no flags |
| `0x08800006` | C class, elevated severity |

Upper byte (bits 31-24) = fault class: `0x08`=Class C (emissions, CARB mandated) · `0x40`=Class B (performance/powertrain) · `0x48`=Class A (critical) · `0x58`=Class 0 (most critical).
Lower byte (bits 7-0) = severity/action: `0x04`=Standard (MIL on) · `0x06`=Severe (MIL + power reduction) · `0x00`=Info only.

### Backup RAM Locations (@0xFFFFD000)

| Address | Size | Description |
|---|---|---|
| `0xFFFFD494` | N | DTC enable/disable flags by fault code |
| `0xFFFFD638` | N | Secondary DTC type flags |
| `0xFFFFD6C4` | 1 | Global fault status enable flag |
| `0xFFFFD6C8` | N words | DTC code storage array |
| `0xFFFFD96C` | 4 | Primary fault status bitmask (accumulated) |
| `0xFFFF9EC8` | 2 | System status word |
| `0xFFFF8928` | 2 | Current DTCCodeIndex for handler dispatch |
| `0xFFFF87D8` | N*16 | DTC handler context table (16 B/entry) |
| `0xFFFF87DE` | N | DTC handler byte-code opcodes |

## Core Functions

### 1. `getFaultStatus` (0x06743C)

`uint8_t getFaultStatus(uint16_t faultCode)` — returns 1 if fault active; **0 = not active, 1 = active**. Primary fault status query, called by **78 callers**.

Two-tier check: primary tests global fault mask against table entry (lower 16 bits); if no match, secondary condition checks (`getFaultStatus_subcheck` bitmask AND table upper word).

```c
#define FAULT_STATUS_TABLE ((volatile uint32_t*)0x7E4DC)
#define FAULT_MASK_PTR     ((volatile uint32_t*)0xFFFFD96C)
uint8_t getFaultStatus(uint16_t faultCode) {
    uint32_t globalMask = *FAULT_MASK_PTR;
    uint32_t tableEntry = FAULT_STATUS_TABLE[faultCode];
    if ((globalMask & tableEntry) & 0xFFFF) return 1;
    uint32_t secondaryResult = getFaultStatus_subcheck(faultCode);
    if ((secondaryResult & tableEntry) & 0xFFFF0000) return 1;
    return 0;
}
```

Major callers: `omp_fault_detect_44DF0` (0x44DF0), `dtc_processor_0x50F1C` (0x50F1C), `fault_code_logger_0x50C8C` (0x50C8C), `fault_code_handler_4436E` (0x442E8), various `fault_condition_check_*` at 0x5Exxx.

### 2. `getFaultStatus_subcheck` (0x067494)

`uint32_t getFaultStatus_subcheck(uint16_t faultCode)` — runs condition checks; each sets a unique bit. Caller ANDs result with table upper word.

| # | Address | Bit | Check | Description |
|---|---|---|---|---|
| 1 | 0x67534 | 31 | null | Always returns 0 (stub) |
| 2 | 0x67538 | 30 | DTC walk | Iterates DTC reference table; checks code's entry valid |
| 3 | 0x67534 | 29 | null | Redundant stub |
| 4 | 0x675AC | 28 | indirect | Double-indirect via two word-index tables |
| 5 | 0x675CA | 27 | DTC valid | Calls `dtc_data_read_60DEE` for integrity |
| 6 | 0x67534 | 26 | null | Redundant stub |
| 7 | 0x67534 | 25 | null | Redundant stub |
| 8 | 0x67534 | 24 | null | Redundant stub |
| 9 | 0x675E6 | 23 | byte lookup | Two-element loop via byte table @0x7E734 |

Redundant `check_cond_A` calls (always 0) suggest 8 distinct checks once existed; some later stubbed/merged.

### 3. `check_cond_B` (0x067538) — DTC Table Walker

`uint8_t check_cond_B(uint16_t faultCode)` — deref DTC reference table `0x7ECD0` → entry list; iterate (0xFFFE-terminated, bound 50) validating each via `dtc_data_read_60EB4` (0x60EB4); return 1 if any valid.

```c
uint8_t check_cond_B(uint16_t faultCode) {
    uint16_t* entryList = (uint16_t*)0x7ECD0[faultCode];
    for (uint8_t c = 0; c < 50; c++) {
        uint16_t e = *entryList;
        if (e == 0xFFFE) break;              // terminator
        if (dtc_data_read_60EB4(e) == 1) return 1;
        entryList++;
    }
    return 0;
}
```

### 4. `check_cond_C` (0x0675AC) — Indirect Table Lookup

`uint8_t check_cond_C(uint16_t faultCode)` — double-indirect: `WORD_TABLE_LEVEL1[0x7DAEA][code]` → index into `BYTE_TABLE_LEVEL2[0xFFFF8D7C]`; returns presence flag (non-zero → 1).

```c
uint8_t check_cond_C(uint16_t faultCode) {
    return ((uint8_t*)0xFFFF8D7C)[((uint16_t*)0x7DAEA)[faultCode]] != 0;
}
```

### 5. `check_cond_D` (0x0675CA) — DTC Data Check

`uint8_t check_cond_D(uint16_t faultCode)` — returns 1 if `dtc_data_read_60DEE(faultCode)` non-zero.

### 6. `check_cond_E` (0x0675E6) — Byte-Indexed Lookup

`uint8_t check_cond_E(uint16_t faultCode)` — two-element loop (index 0,1): set found if `dtc_data_read_60EFE(i) & byte_table[0x7E734][code][i]`.

### 7. `setFaultEvalState` (0x060DB4)

`uint8_t setFaultEvalState(void)` — returns evaluation state bitmask.

```c
#define SYS_STATUS_RUN ((volatile uint8_t*)0xFFFFD1E9)
#define SYS_FLAGS_WORD ((volatile uint16_t*)0xFFFF9EC8)
#define SYS_STATUS_2   ((volatile uint8_t*)0xFFFFD1D4)
uint8_t setFaultEvalState(void) {
    uint8_t state = 0x03;                       // default: key-on, engine-off
    if (*SYS_STATUS_RUN == 1) state = 0x01;     // engine running
    if (*SYS_FLAGS_WORD & 0x0001) state |= 0x04; // system flag active
    if (*SYS_STATUS_2 == 1) state |= 0x08;       // secondary diagnostic mode
    return state;
}
```
Bits: 0x01 engine running, 0x02 key-on/engine-off (KOEO), 0x04 system flag, 0x08 secondary diag.

### 8. `getFaultEvalState` (0x067482)

`uint16_t getFaultEvalState(void)` — wrapper calling `setFaultEvalState` (0x60DB4); zero-extends result and stores to fault mask `0xFFFFD96C` — a "freeze frame" of evaluation context at detection.

### 9. `updateFaultStatusTHUNK` (0x060778)

Thunk on mode (r6). mode==0 → default r6=0xFFFF (init/no-op). mode!=0: faultCode==1 sets global fault flag `0xFFFFD6C4`; faultCode==0 clears it; others no-op.

```c
#define GLOBAL_FAULT_FLAG ((volatile uint8_t*)0xFFFFD6C4)
void updateFaultStatusTHUNK(uint16_t mode, uint8_t faultCode) {
    if (mode == 0) return;
    if (faultCode == 1) *GLOBAL_FAULT_FLAG = 1;
    else if (faultCode == 0) *GLOBAL_FAULT_FLAG = 0;
}
```

### 10. `dtcRelated` (0x062002)

`uint8_t dtcRelated(uint8_t param, uint16_t data, uint8_t* outputArray)` — main DTC dispatch loop.

```
Loop DTC index 0-20 (21 iterations):
  - read DTC code from index table 0xFFFF8928; 0 → break
  - handler context @0xFFFF87D8 [index*16]; type field @+6
  - read enable flags 0x7E220, type flags 0x7E2AC
  - for each type code (0x00,0x60,0x80,0xC0,0xC1,0xF0,0x50,0x70):
      match type dispatch table, store to output array, increment count
  - return total processed count
```

DTC type dispatch (mode selects type):

| Mode | Type |
|---|---|
| 0x00 | All enabled DTCs |
| 0x60 | Pending |
| 0x80 | Confirmed |
| 0xC0 | Permanent |
| 0xC1 | Warm-up cycle |
| 0xF0 | Readiness |
| 0x50 | MIL |

### 11. `dtc_code_set` (0x046780) / `dtc_code_clear` (0x0467AA)

Low-level Backup RAM DTC storage. set: `memory_set_byte(0x8788, 1)` (@0x3ED3C), then clears `0x875C`/`0x875E` (@0x3EE58). clear: clears both.

```c
#define DTC_FLAG_ADDR   ((volatile uint8_t*)0x8788)
#define DTC_STORAGE_1   ((volatile uint8_t*)0x875C)
#define DTC_STORAGE_2   ((volatile uint8_t*)0x875E)
void dtc_code_set(void) {
    if (memory_set_byte(DTC_FLAG_ADDR, 1) == 1) memory_clear_byte(DTC_STORAGE_1, 0);
    memory_clear_byte(DTC_STORAGE_2, 0);
}
void dtc_code_clear(void) {
    memory_clear_byte(DTC_STORAGE_1, 0);
    memory_clear_byte(DTC_STORAGE_2, 0);
}
```

### 12. `dtc_handler_610FA` (Main DTC Handler Dispatcher)

Reads DTC index `0xFFFF8928`, handler type table `0xFFFF87DE` (stride 16). Only type 0x50 (MIL) or 0 (standard) are processed → run chain `0x62FAC(8)`, `0x64258()`, `0x63312()`. Other types skipped.

### 13. `dtc_handler_61550` (Detailed DTC Handler — 358 B)

`void dtc_handler_61550(uint16_t dtcCode, uint8_t mode)` — type-specific evaluation, debounce counters, status flags; stores to Backup RAM status @0xFFFFD6F8.

```c
void dtc_handler_61550(uint16_t dtcCode, uint8_t mode) {
    uint8_t faultStatus, debounceState, checkResult, finalResult = 0;
    if (mode == 0) {                                             // standard
        faultStatus   = ((uint8_t(*)(uint16_t))0x61712)(dtcCode);
        debounceState = ((uint8_t(*)(uint16_t,uint8_t,uint8_t))0x62334)(dtcCode, faultStatus, mode);
        checkResult   = ((uint8_t(*)(uint8_t))0x62E5C)(debounceState);
        if (checkResult == 1) {
            ((void(*)(uint16_t,uint8_t))0x61818)(dtcCode, faultStatus);
            ((void(*)())0x61994)();
            ((void(*)(uint16_t))0x62B74)(dtcCode);
            ((void(*)(uint16_t,int))0x6193E)(dtcCode, 0x20);
            ((void(*)(uint8_t))0x63B46)(debounceState);
            ((void(*)(uint8_t))0x63A62)(mode);
            ((void(*)(int))0x63AD4)(1);
        }
    } else if (mode == 1) {                                      // pending
        checkResult = ((uint8_t(*)(uint16_t))0x63834)(dtcCode);
        if (checkResult & 0x80) finalResult = 0;
        debounceState = ((uint8_t(*)(uint16_t,uint8_t,uint8_t))0x62334)(dtcCode, finalResult, mode);
        if (((uint8_t(*)(uint8_t))0x62E5C)(debounceState) == 1) {
            if ((finalResult & 0x80) == 0) ((void(*)(uint8_t))0x63814)(finalResult);
            ((void(*)(uint8_t))0x63B46)(debounceState);
            ((void(*)(uint8_t))0x63A62)(mode);
        }
    } else if (mode == 2) {                                      // confirmed
        finalResult = ((uint8_t(*)(uint16_t))0x63834)(dtcCode);
        debounceState = ((uint8_t(*)(uint16_t,uint8_t,uint8_t))0x62334)(dtcCode, finalResult, mode);
        if (((uint8_t(*)(uint8_t))0x62E5C)(debounceState) == 1) ((void(*)(uint8_t))0x63A62)(mode);
    }
    ((volatile uint8_t*)0xFFFFD6F8)[4] = debounceState;
    ((volatile uint8_t*)0xFFFFD6F8)[7] = finalResult;
    if (dtcCode == *(uint16_t*)0xFFFFD700) ((void(*)(uint16_t,int))0x62ABC)(dtcCode, 0x20);
    ((void(*)(uint16_t,uint8_t,int))0x62B24)(dtcCode, finalResult, 0x20);
    ((void(*)(uint16_t,uint8_t))0x632D6)(dtcCode, finalResult);
}
```

### 14. `dtc_debounce_monitor_43760` (Debounce — 282 B)

Multi-stage counter debounce to prevent transient-triggered faults.

| Address | Size | Name | Role |
|---|---|---|---|
| `0xFFFFC9EF` | 1 | DebounceFlag1 | First debounce stage |
| `0xFFFFC9F0` | 1 | DebounceFlag2 | Second debounce stage |
| `0xFFFFC9FE` | 2 | DebounceCounter1 | First timer |
| `0xFFFFCA00` | 2 | DebounceCounter2 | Second timer |
| `0xFFFFCA02` | 2 | FailCounter | Fail threshold counter |
| `0xFFFFC9E8` | 1 | EnableDebounce | Enable flag |
| `0x7D97C` | 2 | Threshold1 | Counter1 threshold |
| `0x7D984` | 2 | Threshold2 | Counter2 threshold |
| `0x7D988` | 2 | FailThreshold | Fail threshold |
| `0x7D978` | 2 | MaxCount1 | Counter1 max |
| `0x7D97A` | 2 | MaxCount2 | Counter2 max |

If debounce disabled or sensor `0xB3C8` inactive → clear all counters/flags. Else count up via saturation fn `0x2460`; DCNT1≥Threshold1 → Flag1, DCNT2≥Threshold2 → Flag2; fail counter updates while sensor active.

### 15. Sensor-Specific Fault Detection

| Function | Size | Purpose |
|---|---|---|
| `dtc_misfire_detection_468D6` | 208B | Misfire (P0300-P0304); eccentric-shaft accel vs RPM thresholds |
| `dtc_o2_circuit_fault_45F54` | 72B | O2 circuit; voltage/response/heater continuity |
| `dtc_cat_system_monitor_45FFC` | 772B | Catalyst efficiency; upstream vs downstream O2 switch freq |
| `omp_fault_detect_44DF0` | 572B | Output stage opens/shorts (injectors, coils, relays); `getFaultStatus(44)` + 7 sensor checks |

### 16. `fault_code_dispatch_2D89C`

`void fault_code_dispatch_2D89C(uint8_t faultClass)` — dispatch by fault class.

| Class | Action |
|---|---|
| 0 | Clear fault code flags |
| 1 | Set MIL, log |
| 2 | Set MIL, limp mode |
| 3 | Set MIL, extended logging |
| 4+ | Reserved/ignored |

### 17. `fault_recovery_4ABC4`

`void fault_recovery_4ABC4(void)` — tests status bytes; all cleared → recovery flag 1, any active → 0.

## Fault Detection Pipeline

```
Sensor Input → Sensor Monitors (0x46BCC-0x47000, e.g. coolant_temp_monitor_0x4F81E, sensor_ect_monitor_46BCC)
    → dtc_debounce_monitor_43760 (debounce)
    → dtc_code_set_46780 (Backup RAM storage)
    → dtcRelated_62002 (dispatch)
    → getFaultStatus_6743C (query)
    → Response: MIL / limp mode / DTC history / OBD readiness
```

## Key Memory Structures

### DTC Handler Context Table (`0xFFFF87D8`) — 16 B/entry

```
+0  HandlerID          +6  HandlerType (0x00, 0x50=MIL, 0x60, 0x80, 0xC0)
+2  HandlerFlags       +7  Reserved/Status
+4  DebouncePreset     +8  HandlerFunctionPtr (4)
+12 HandlerParameter   +14 NextHandlerOffset
```

### Fault Status Table @0x7E4DC

32-bit/entry, ROM, indexed by fault code; classification + required-check metadata.

```
Bit 31-28 Fault Class (0x0 standard, 0x4 performance, 0x5 most critical)
Bit 27-24 Severity    (0x8 = OBD-II monitored)
Bit 23-20 System      (0x0 general, 0x8 ECU/CPU self-test)
Bit 19-16 Reserved
Bit 15-0  Mask/Flags
```

## Call Graph

```
sensor_fault_handler_3b14c (dispatcher to 33 sensor monitors)
  ├─ dtc_o2_response_time_45F9C, dtc_p0120_tps_46DCA, dtc_p0100_maf_46DA0
  ├─ dtc_cat_system_monitor_45FFC (772B), omp_fault_detect_44DF0
  ├─ fault_code_handler_4436E, sensor_fault_detect_cyl_selectivity, +28 more
  └─ dtc_snapshot_manager_3b3bc → dtcRelated_62002
        ├─ dtc_handler_610FA, dtc_handler_61550 (358B), dtc_handler_61D2A (266B)
        ├─ dtc_handler_6184C (242B), dtc_handler_6155A (230B)
        ├─ dtc_handler_61304 (230B), dtc_handler_61712 (216B)
        └─ getFaultStatus_6743C (78 callers)
              └─ getFaultStatus_subcheck
                    ├─ check_cond_A (stub), check_cond_B (DTC walk)
                    ├─ check_cond_C (indirect), check_cond_D (data)
                    └─ check_cond_E (byte lookup)
```

## OBD-II Readiness Monitors

| Monitor | Function | Address | Size |
|---|---|---|---|
| Misfire | `dtc_misfire_detection_468D6` | 0x468D6 | 208B |
| Fuel System | `fuel_injection_monitoring_457A2` | 0x457A2 | 338B |
| Comprehensive Component | `sensor_fault_handler_3b14c` | 0x3B14C | 206B |
| Catalyst | `dtc_cat_system_monitor_45FFC` | 0x45FFC | 772B |
| Heated Catalyst | combined w/ catalyst | — | — |
| EVAP | DTC P0400 @0x47058 | 0x47058 | 14B |
| Secondary Air | not implemented | — | — |
| A/C Refrigerant | not implemented | — | — |
| O2 Sensor | `sensor_lambda_monitor_45F00` | 0x45F00 | 18B |
| O2 Heater | `dtc_o2_circuit_fault_45F54` | 0x45F54 | 72B |
| EGR/VVT | n/a on Renesis (no EGR/VVT); 0x47058 = EVAP purge monitor | — | — |

## Limp Mode

Critical faults → `limp_mode_detection_25E36`: CKP loss (no crank), APP loss (no throttle response), MAF loss (limited fuel calc), knock loss (retarded timing) → reduce power / limit RPM + set MIL.

## Summary

- **ROM Fault Status Table** `0x7E4DC`: 32-bit/entry fault classification/behavior metadata.
- **Backup RAM storage** (`0xFFFFD000`): battery-backed fault memory.
- **Two-tier fault check**: primary global mask + independent secondary condition checks.
- **Debounce**: multi-stage counters (`dtc_debounce_monitor_43760`).
- **Handler chain**: `dtcRelated` → `dtc_handler_*` → `getFaultStatus`.
- **Readiness monitoring**: pending/confirmed/permanent DTC status.
- **Recovery**: `fault_recovery_4ABC4` clears when conditions normalize.
