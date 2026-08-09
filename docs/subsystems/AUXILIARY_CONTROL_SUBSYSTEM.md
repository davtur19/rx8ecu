# RX-8 ECU Auxiliary & Idle Control Subsystems

Reverse-engineered control strategies for idle regulation and auxiliary subsystems in the Mazda RX-8 Renesis (13B-MSP) ECU firmware (SH-2E, 60E1D400/60E0FC00).

## 1. Idle Speed Control (ISC)

Closed-loop air bypass idle control uses a **linear solenoid** (ISC valve) to vary air past the throttle (no stepper motor).

1. `calc_idle_speed_target()` (0x12F5E) — target
2. `idle_speed_control_18054()` (0x18054) — state machine & mode dispatch
3. `idle_air_control_valve_47848()` (0x47848) — air valve position
4. `adaptive_idle_47754()` (0x47754) — adaptive learning
5. Load comps — warm-up, A/C, power steering

### 1.2 Target RPM (`calc_idle_speed_target`, 0x12F5E, 0x112 B to 0x13070; calls `sensor_range_check_3ED0C`)

```
if (engineOffFlag == 0) AND (engineSpeed > 0x9C3 = 2499 RPM) AND (someFlag == 0):
    idleTarget = sensor_range_check(DAT_c128 - DAT_c12c)  // Temp diff
    STORE idleTarget to output
else:
    idleTarget = 0

if (flagA6A9 == 1 AND condition) OR (flagA6AA == 1 AND condition2):
    counterA68F = -1        // Disable idle correction
elif counterA68F != 0:
    counterA68F--

if counterA68F == 0:
    Load calibrated target from table lookup
```

Result stored to RAM `0xFFFFA678` (float). Key RAM:

| Address | Role |
|---|---|
| `0xFFFFA445` / `0xFFFFA444` | flag bytes |
| `0xFFFFC600` | engine-off flag |
| `0xFFFFA424` | engine speed / RPM (16-bit) |
| `0xFFFFAADA` | flag byte |
| `0xFFFFC128` / `0xFFFFC12C` | target parameters (float) |
| `0xFFFFA678` | computed idle target (float) |
| `0xFFFFA68F` | idle correction counter (signed byte) |
| `0xFFFFA680` | base calibration value |

### 1.3 Idle State Machine (`idle_speed_control_18054`, 0x18054, 0x194 B to 0x181E8; called from `main_engine_cycle_10ms` 0x17F1C)

States: NORMAL(0) closed-loop, CRANK(1) start, WARMUP(2) fast idle, LOAD_COMP(3) A/C/electrical load.

RAM: `0xFFFFA428` engine state (0=running,1=starting), `0xFFFFAAE0` idle enable, `0xFFFFA978` cranking, `0xFFFFA979` idle transition, `0xFFFFA998` flag, `0xFFFFA96C` idle active, `0xFFFFA96A` flag, `0xFFFFA970` previous idle state, `0xFFFFA96E` idle counter (16-bit), `0xFFFFAA14` coolant temp (float), `0xFFFFAA10` temp (float).

```
if engineRunning AND idleControlEnabled: enter idle, clear start request, cranking timer=2
elif engineStarting AND notCranking AND notOtherFlag: set warm-up flag
else:
    if engine stopped AND idleWasOn: query shutdown sensor
    if condition AND cruiseActive AND flag: set idleActive
    if idleEnabled AND idleFlag: clear idle RPM accumulator

// Temp-based RPM limiting
if coolant < -40.0°C: if idleCounter > 499: flag = 0
elif idleCounter > 0x9B (155): flag = 0
idleCounter += 1 (saturated 16-bit add)
```

### 1.4 Idle Air Control Valve (`idle_air_control_valve_47848`, 0x47848, 26 B)

Final ISC solenoid output stage → PWM regs:

```c
void idle_air_control_valve_47848(void) {
    write16(0xFFFF877C, read16(0xFFFF877C, 0));  // 16-bit ISC duty → PWM reg
    write8(0xFFFF8788, 1);                        // enable/flag
}
```

Actual ISC position = f(coolant warm-up, A/C clutch, PS pressure switch, alternator load, adaptive learned base).

### 1.5 Adaptive Idle Learning (`adaptive_idle_47754`, 0x47754, 50 B)

```c
void adaptive_idle_47754(void) {
    if (DAT_ffffa3f0 == 0) write16(0xFFFF8772, 0);   // not inhibited → reset accumulator
    if (read16(0xFFFF8774, 0) != 0) write16(0xFFFF8772, 0);
    write16(0xFFFF8772, 1);                          // enable adaptive learning
}
```

### 1.6-1.10 Load Compensation & Saturation

| Function | Address | Size | Role |
|---|---|---|---|
| `idle_target_increase_step` | 0xE4B4 | 36 | Steps idle target for load comp (A/C, PS, alternator) |
| `idle_warm_up_4790A` | 0x4790A | 8 | Warm-up correction vs coolant |
| `idle_ac_load_47912` | 0x47912 | 20 | Raises target when A/C clutch on |
| `idle_steering_load_47926` | 0x47926 | 26 | Raises target when PS switch active (lock/low speed) |
| `idle_correction_saturation_check` | 0x1B4F8 (0x54 B) | — | Anti-windup clamp on idle integrator during decel return |

### 1.11 ISC Output

ISC solenoid driven by SH-2E MTU (Multi-Function Timer Pulse Unit) PWM; duty controls solenoid position → bypass air.

### 1.12 Calibration (Typical Values)

| Parameter | Range | Units | Notes |
|---|---|---|---|
| Base idle target (warm) | 750-850 | RPM | Closed loop |
| Fast idle (cold) | 1000-1500 | RPM | Engine < 60°C |
| A/C compensation | +50-100 | RPM | Step |
| Power steering comp | +30-50 | RPM | At lock |
| Alternator load comp | +20-50 | RPM | Electrical load |
| ISC PWM frequency | ~100-200 | Hz | Solenoid drive |
| Adaptive range | ±20% | Duty | Learned trim |

## 2. SSV — Secondary Shutter Valve

Two-position intake valve; opens secondary port at RPM threshold through a vacuum actuator + solenoid. Closed <~2000 RPM (low-end torque), open >~2000 RPM (high-end power), hysteresis prevents oscillation.
### 2.2 SSV Control (`ssvControl__`, 0x225C8, 94 B; called from `torque_dispatcher_225A2`/`direct_branch_to_torque_calc_2259C`)

```asm
r11 = read8(0xFFFFAAE0)        // engine state/enable
fr4 = read32(0xFFFFAA10)       // NOT CONFIRMED — see note
fr6 = read32(CAL_SSV_THRESH)   // actuation threshold (NOT verified)
fr5 = fr6 - 3.0                // hysteresis band (3 RPM)
if (fr4 > fr6) write8(SSV_OUTPUT, 1)       // OPEN
else if (fr4 < fr5) write8(SSV_OUTPUT, 0)  // CLOSE
// ramp: r11==0 AND flagB325==1 → load 0xFFFFB322 with CAL_SSV_RAMP_TARGET; else decrement
// enable uVar2 if flagB325_saved OR flagBF39 OR (engineOn AND rampActive AND ssvClosed)
output = alternating_sensor_sm_08_5D3E8(uVar2); write8(0xFFFFB320, output)
setRegister_REG_BIT_VAL(0xFFFFF754, 0x80, output ? 1 : 0)  // Bit 7 = SSV solenoid
write8(0xFFFFB325, r11)
```

> **Threshold NOT verified** — 0xFFFFAA10 is the coolant-temp input in the verified OMP gate (`omp_waveform_state_machine_18860.c`), conflicting with the air-demand/RPM reading assumed; real SSV opens ~3750 RPM per external refs. No new values claimed.

### 2.3 SSV Calibration

| Parameter | Address | Typical Value | Notes |
|---|---|---|---|
| Open threshold | Cal table | NOT confirmed (~200.0 claimed, disputed) | see note above |
| Hysteresis band | Hardcoded | 3.0 | Prevents oscillation |
| Ramp target | 0xFFFFB322 | 0xBC (188) | Ramp-down count for soft close |

### 2.4 Hardware

Port `0xFFFFF754` bit 7 (0x80) · output `0xFFFFB320` (validated command) · ramp `0xFFFFB322`.

## 3. VIS — Variable Intake System

Adjusts intake runner length/cross-section through a multi-position actuator driven by a duty-cycled solenoid.

### 3.2 VIS Intake Control (`vis_intake_control_23718`, 0x23718, 236 B; called from `engine_control_master_task_23DC8`)

```
fr5 = RPM_SENSOR; fr4 = AIR_DEMAND
state selector: DAT_b33c=1 → TABLE_VIS_MODE_1 (0x6AC60); DAT_b33d=1 → 0x6AC7C;
                DAT_b33e=1 → 0x6AC98; else → 0x6ACB4
result = _3dLookup(table)
saturated = fpu_compare_and_select(84.0, result)      // 84.0 RPM limit
store32(0xFFFFB408, saturated)                        // VIS position command
// solenoid duty index: axis_lookup_float_to_index(1.0, saturated), cap 12
store8(0xFFFFB45C, index)
for (step = 11; step >= 0; step--) dutyTable[step] = calc_vis_solenoid_duty(step)
store32(VIS_DUTY_REG, computedDuty)
```

### 3.3 Solenoid Duty (`calc_vis_solenoid_duty_cycle_1261C`, 0x1261C, 0xAE B)

PWM duty for VIS solenoid from position index; calibrated duty values from lookup table.

### 3.4 VIS Calibration Tables

| Address | Description | Format |
|---|---|---|
| 0x6AC60 | VIS position map (mode 1) | 3D float table |
| 0x6AC7C | VIS position map (mode 2) | 3D float table |
| 0x6AC98 | VIS position map (mode 3) | 3D float table |
| 0x6ACB4 | VIS position map (mode 4) | 3D float table |
| 0x6ACxx | VIS duty cycle table | 12-entry float array |

## 4. VFAD — Variable Fresh Air Duct

RX-8-unique auxiliary intake duct opening at high RPM to reduce restriction; vacuum-operated valve + solenoid (like SSV).

### 4.2 VFAD Control (`vfadControl_`, 0x35BBC, 132 B; called from `task_priority_dispatch_wrapper_35B96`)

```asm
fr4 = read32(0xFFFFB5B8)       // RPM or MAF (float)
fr6 = 5250.0                   // open threshold (RPM)
fr5 = fr6 - 188.0              // hysteresis band (5062 RPM)
if (fr4 > fr6) r4 = 1          // OPEN
else if (fr4 < fr5) r4 = 0     // CLOSE
output = alternating_sensor_sm_09_5D800(r4); write8(0xFFFFC234, output)
setRegister_REG_BIT_VAL(0xFFFFF754, 0x400, output ? 1 : 0)  // Bit 10 = VFAD solenoid
```

### 4.3 VFAD Parameters

| Parameter | Value | Notes |
|---|---|---|
| Open threshold | 5250 RPM | Opens for high-RPM airflow |
| Hysteresis | 188 RPM | Closes ~5062 RPM |
| Output port | 0xFFFFF754, bit 10 | Solenoid driver |
| State register | 0xFFFFC234 | Validated command |

### 4.4 VFAD vs SSV

Same design pattern: hysteresis comparator → alternating sensor state machine (debounce) → atomic SR bit write on 0xFFFFF754.

| Feature | SSV | VFAD |
|---|---|---|
| Threshold | ~200 RPM | 5250 RPM |
| Hysteresis | 3 RPM | 188 RPM |
| Port bit | Bit 7 (0x80) | Bit 10 (0x400) |
| State machine | alt_sm_08 | alt_sm_09 |
| Ramping | Yes | No |

## 5. OMP — Oil Metering Pump

Electronically-controlled stepper-motor OMP injecting oil to lubricate apex seals/rotor housings. Delivery varies with RPM, load (TPS/intake vacuum), coolant temp, throttle change rate (accel enrichment).
### 5.2 OMP Control (`omp_control_task_1825E`, 0x1825E, 374 B; called from `main_engine_cycle_10ms`; verified lift `c/omp_control_task_1825E.c`)

```c
void omp_control_task_1825E(void) {
    uint8_t engineState = read8(0xFFFFA96C);
    if ((read8(0xFFFF9ECD) & 2) == 0) DAT_ffffa976 = 0;        // HW fault → disable
    else { if (DAT_ffffa976 == 0) DAT_ffffa987 = 1; DAT_ffffa976 = 1; }
    if (DAT_ffffa988 == 1 && engineState == 0) DAT_ffffa989 = 1;  // accumulate time
    if (DAT_ffffa968 == 0) { DAT_ffffa977 = 0; DAT_ffffa978 = 0; }
    if (DAT_ffffa97b != 0) DAT_ffffa97b--;                       // prime/purge timer
    if (DAT_ffffa97b == 1 && DAT_ffffa968 == 1 && DAT_ffffa982 == 1) {
        DAT_ffffa974 = 0; DAT_ffffa97f = 0; write8(0xFFFF807C, 0); // purge cmd
    }
    if (DAT_ffffa97b != 0) { DAT_ffffa988 = engineState; return; }
    DAT_ffffa974 = DAT_ffffa97f;
    // mode dispatch:
    if (DAT_ffffa998 == 1) omp_cranking_mode();
    else if (DAT_ffffa968 == 1) omp_idle_mode(read8(DAT_ffffa985));
    else if (DAT_ffffa96a == 1 && DAT_ffffcd06 == 0) omp_decel_mode();
    else if (DAT_ffffa96b == 1) omp_warmup_mode();
    else if (DAT_ffffa969 == 1) omp_normal_mode(read8(DAT_ffffa984));
    if (engineState == 1 && DAT_ffffa987 == 1) write8(0xFFFF807A, DAT_ffffa974); // stepper pos
    // 0x807A read is 8-bit: readValue_8bit_ADDRESS_VAL(0xFFFF807A, 0x37)
    uint8_t read7a = readValue_8bit_ADDRESS_VAL(0xFFFF807A, 0x37);
    // Delivery ramp A975: increment saturates via addSaturate8Bit @0x2478 (min(+1,255));
    // decrement wraps mod 256, requires A974 >= CAL37 (0x3C) and pump healthy (A976==1).
    if (DAT_ffffa989 == 1) {
        if (read7a < CAL36 || (DAT_ffffa974 >= CAL37 && DAT_ffffa976 == 0))
            DAT_ffffa975 = addSaturate8Bit(DAT_ffffa975, 1);   // 0x2478
        else if (DAT_ffffa974 >= CAL37 && DAT_ffffa976 == 1 && DAT_ffffa975 != 0)
            DAT_ffffa975--;                                    // wraps mod 256
    }
    if (DAT_ffffa975 == 0) write8(0xFFFF8078, CAL35);          // CAL35 = 0x02
    else if (DAT_ffffa975 != 4) { DAT_ffffa979 = 0; DAT_ffffa982 = 0; }
}
```

> **Verification (2026-08-01):** lifted as `c/omp_control_task_1825E.c`, emulator-verified (150000+ random inputs, 5 seeds, 0 mismatches). Internal tasks 0x18C6C/0x18C5C/0x18C08 run natively in emulator (inlined in lift). Cal bytes: CAL35 @0x78E35 = 0x02, CAL36 @0x78E36 = 0x34, CAL37 @0x78E37 = 0x3C.

### 5.3 OMP Operating Modes

| Mode | Flag | When | Oil Rate |
|---|---|---|---|
| Cranking | `a998==1` | Start | High prime |
| Idle | `a968==1` | Idle control | Low base |
| Decel/FC | `a96a==1` | Decel fuel cut | Reduced |
| Warm-up | `a96b==1` | Engine cold | Medium |
| Normal | `a969==1` | Driving | RPM/load mapped |
| Purge | `a97b timer` | Periodic flush | Full stroke |

### 5.4 OMP Fault Detection (`omp_fault_detect_44DF0`, 0x44DF0, 0x23C B to 0x4502C)

Monitors position feedback: open circuit, short circuit, stall, range fault; each sets a DTC and may illuminate MIL.

### 5.5 OMP Calibration

| Axis | Range |
|---|---|
| RPM | 0-9000 |
| Load (MAP) | 20-100+ kPa |
| Coolant temp | -40 to 120°C |

> **OMP "cold" gate (0x18860 state 1):** the -40.0 threshold at ROM 0x78E68 is a **sensor-validity split**, not cold-calibration A/B: both cal bytes identical in stock ROM (CAL_A @0x78E33 == CAL_B @0x78E34 == 0x3C), so no cold correction applied; pick side by temp (temp< -40.0 → cal A/A978, else cal B/A977; A97E = cal byte).

Delivery rates: Idle ~0.5-1.0 cc/min · Cruise ~1.0-2.0 · Accel ~3.0-5.0 (transient) · High RPM/WOT ~5.0-8.0 · Cranking prime ~10.0 (brief).

### 5.6 Engine-On Time (`getEngineOnTimeForOilMetering`, 0xE492, 34 B)

Cumulative engine-on time used to schedule OMP maintenance cycles (purge, system checks).

## 6. Cooling Fan Control

Dual electric fans, multiple speeds. Controlled by coolant temp (primary), A/C compressor pressure, vehicle speed (ram air), engine load.

### 6.2 Fan 1 (`calcFan1Control`, 0x303A6, 248 B; called from `priority_task_port_init_300F2`)

```c
float coolantTemp = read32(0xFFFFAA10); threshold = 97.0f; hysteresis = 32.0f;
if (coolantTemp > threshold) { /* >97°C fan high */ }
else if (coolantTemp < threshold - hysteresis) { /* <65°C fan off */ }
// secondary stage (FAN1B) same thresholds
// enable conditions: AC request AND NOT thermal protect AND NOT vehicleSpeedCond, etc.
// priority: A/C request > thermal > speed
```

### 6.3 Coolant Temp Fan (`cooling_fan_control_0x17DCC`, 0x17DCC, 68 B; called from `calc_spark_advance_offset_map`)

```c
float coolantTemp = read32(0xFFFFA73C); float threshold = 0.00001f; // const table
uint8_t fanRequest = complement_shift_u32(coolantTemp, threshold);
if (DAT_ffffa95c == 0 && fanRequest != 0) {
    DAT_ffffa93b = addSaturate8Bit(DAT_ffffa93b, 1);
    write8(0xFFFF8076, 0);   // fan relay
}
DAT_ffffa95c = fanRequest;
```

### 6.4 Fan Speed (`fan_speed_calc_1ED40`, 0x1ED40, 82 B; called from `main_control_loop_processor_21C90`)

Uses coolant `0xFFFFAA10`, A/C pressure `0xFFFFAE54`: low/high speed stages by temp/pressure thresholds + vehicle-speed (ram air) correction.

### 6.5 Temperature Thresholds

| Fan Stage | ON | OFF (Hysteresis) | Notes |
|---|---|---|---|
| Fan 1 Low | ~97°C | ~65°C | Primary |
| Fan 1 High | ~100-105°C | ~65°C | Higher speed |
| Fan 2 (Aux) | A/C dependent | A/C dependent | Condenser |
| Thermal protection | ~110-115°C | ~100°C | Emergency override |

### 6.6 Hardware

| Register | Function |
|---|---|
| 0xFFFFB324 | Fan 1 command (0/1) |
| 0xFFFFBE16 | Fan 1 output bit |
| 0xFFFFBE17 | Fan 2 output bit |
| 0xFFFF8766 | Fan PWM/limit reg |
| 0xFFFF8076 | Fan relay output |

## 7. Alternator Voltage Control

Multi-stage voltage control: battery temperature, electrical load, engine state, thermal constraints.

### 7.2 Functions (60E0FC00 binary)

| Function | Address |
|---|---|
| `calculateOutputforAlternator` | 0x25F98 |
| `alternatorStuff` | 0x26044 |
| `calcDesiredAlternatorVoltage` | 0x26520 |
| `getAlternatorFaultStatus` | 0x26298 |
| `getAlternatorSpeedConditonal` | 0x26308 |
| `getVehicleConditionforAlternatorControl` | 0x2639A |
| `calculateAlternatorDiagDCOutput` | 0x26F48 |
| `setAlternatorWarningLight` | 0x27084 |
| `alternatorControlMain` | 0x270EA / 0x2718C |
| `alternatorControl` | 0x27132 |
| `alternatorPIDsomething` | 0x5B394 |
| `setAlternatorFault` | 0x52698 |

### 7.3 Voltage Control (`calcDesiredAlternatorVoltage`, 0x26520)

```c
batteryTemp = read32(0xA9FC); electricalLoad = read32(0xBBE8); voltageAdj = read32(0xB694);
tempLimitLow=0x74AD4; tempLimitMid=0x74AD8; tempLimitHigh=0x74ADC; ctrlMode=read8(0xCEF2);
if (batteryTemp > tempLimitLow) write8(0xB686, 0); else write8(0xB686, 1); // low/high volt mode
if (electricalLoad > tempLimitMid) write8(0xB687, 1); else write8(0xB687, 0); // boost for load
write8(0xB688, electricalLoad > tempLimitHigh ? 1 : 0);
if (ctrlMode == 1) {   // PID regulation
    currentVoltage = read32(0xB66C); targetVoltage = read32(0x74B0C);
    currentVoltage = saturateLow(currentVoltage, read32(0x74B10));
    write32(0xB66C, currentVoltage - minValue(currentVoltage, tempLimitLow));
    if (isNotZero(read32(0xB5E8))) { alternatorPIDsomething(currentVoltage);
        stateCounter = addSaturate8Bit(read8(0xB680), 1); write8(0xB680, stateCounter); }
}
```

### 7.4 Warning Light (`setAlternatorWarningLight`, 0x275BC/0x27084)

Fault OR: charging fault `0xB663` → `0xB600`=1; over-voltage `0xB5FC`; under-voltage `0xB5FD`; control fault `0xB5FE`; thermal `0xC5DB==1`. Else off.

### 7.5 Voltage Targets

| Condition | Target |
|---|---|
| Cold (< -10°C) | ~14.8-15.0V |
| Normal (warm) | ~13.5-14.2V |
| Hot (> 50°C) | ~13.0-13.5V |
| High load | 14.0-14.5V |
| Idle (no load) | ~12.5-13.0V |

## 8. APV — Auxiliary Port Valves

Auxiliary intake ports opening at high RPM for power; vacuum diaphragms + solenoid (like SSV).

### 8.2 APV Control (`calcAPVControl`, 0x32AE8, 398 B; called from `priority_multi_function_dispatch_32A9C`)

```c
float apvPosition = read32(0xFFFFB5B8); float threshold = 48.0f; float hysteresis = 0.0f;
// 0x42480000 = 50.0f
apvMode = read8(0xFFFFBFF5); apvState = read8(0xFFFFBFF6);
if (apvPosition > threshold) /* OPEN */ else if (apvPosition < threshold - 50.0f) /* CLOSE */
if (apvState == 0 && read16(0xFFFFBFFA) > 50) write8(0xFFFFBFF5, 0);
else if (engineOn == 0 && apvPosition < threshold) write8(0xFFFFBFF5, 1);
if (apvMode == 1 && someFlag == 0 && anotherFlag == 0) {
    write8(0xFFFFBFF6, read16(0xFFFFBFF8) < 50);
    write16(0xFFFFBFF8, add16bitSaturate(read16(0xFFFFBFF8), 1));
} else { write8(0xFFFFBFF6, 0); write16(0xFFFFBFF8, 0); }
// position sensor voltage-range check vs APV_MIN_CAL/APV_MAX_CAL → APV_DIAG_OK
```

### 8.3 APV Calibration

| Parameter | Address | Value | Notes |
|---|---|---|---|
| Open threshold | Hardcoded | ~48.0 RPM equiv. | |
| Hysteresis | ~50.0 | Hardcoded | |
| Position sensor | 0xFFFFB5B8 | Float voltage | Feedback |
| Output register | 0xFFFFC001 | Byte | Solenoid command |

## 9. EVAP / Purge Control

Captures fuel tank vapors into charcoal canister; ECU periodically opens purge valve to draw vapors into intake.

### 9.2 Purge Duty (`calc_evap_purge_duty`, 0x13652, 92 B)

```c
float baseDuty = read32(0xFFFFA6F8);
float purgeDuty = baseDuty + read32(0xFFFFA6FC) /* rpm */ + read32(0xFFFFA704) /* load */;
if (purgeDuty < 0) purgeDuty = 0; if (purgeDuty > 100) purgeDuty = 100;
write32(0xFFFFA6EC, purgeDuty);
```

### 9.3 Canister Purge (`canister_purge_control`, 0x18F98, 16 B)

`write8(0xFFFF8082, 0)` // purge solenoid output.

### 9.4 Purge State Machine (`purge_control_3F3FC`, 0x3F3FC, 0x5C B)

States: PURGE_OFF, PURGE_RAMP_UP, PURGE_ACTIVE, PURGE_RAMP_DOWN, PURGE_DIAG. Enable conditions: coolant > 60°C, running > 30 s, not idle, closed-loop active, no EVAP faults.

### 9.5 EVAP Components

| Component | Control |
|---|---|
| Purge solenoid | PWM duty (vapor flow) |
| Vent solenoid | ON/OFF (canister vent) |
| Fuel tank pressure sensor | Analog (leak detection) |
| Canister close valve | ON/OFF (seals for diag) |

## 10. Global Memory Map

`0xFFFF` prefixes are SH-2E peripheral/I/O space; `0x0006xxxx` are calibration table region.

### Idle System

| Address | Type | Description |
|---|---|---|
| 0xFFFFA428 | u8 | Engine state (0=running,1=starting) |
| 0xFFFFAAE0 | u8 | Idle control enabled |
| 0xFFFFA96C | u8 | Idle active flag |
| 0xFFFFA96A | u8 | Idle mode flag |
| 0xFFFFA96E | u16 | Idle counter/accumulator |
| 0xFFFFAA10 | f32 | Coolant temperature |
| 0xFFFFAA14 | f32 | Secondary temperature |
| 0xFFFFA978 | u8 | Cranking state |
| 0xFFFFA970 | u8 | Previous idle state |
| 0xFFFFA68F | s8 | Idle correction counter |
| 0xFFFFA678 | f32 | Computed idle target RPM |
| 0xFFFFA67C | f32 | Idle target (alternate) |
| 0xFFFF877C | u16 | ISC valve PWM duty |
| 0xFFFF8788 | u8 | ISC valve control enable |
| 0xFFFF8772 | u16 | Adaptive idle trim |
| 0xFFFF8774 | u16 | Adaptive idle accumulator |
| 0xFFFFA3F0 | u8 | Adaptive learning inhibit |

### SSV System

| Address | Type | Description |
|---|---|---|
| 0xFFFFAA10 | f32 | Air demand / RPM input |
| 0xFFFFB324 | u8 | SSV solenoid command |
| 0xFFFFB322 | u16 | SSV ramp counter |
| 0xFFFFB325 | u8 | SSV previous engine state |
| 0xFFFFB320 | u8 | SSV validated output |
| 0xFFFFBF39 | u8 | SSV force-close flag |
| 0xFFFFF754 | u16 | SSV/VFAD solenoid port (bit 7) |

### VIS System

| Address | Type | Description |
|---|---|---|
| 0xFFFFB33C | u8 | VIS mode flag 1 |
| 0xFFFFB33D | u8 | VIS mode flag 2 |
| 0xFFFFB33E | u8 | VIS mode flag 3 |
| 0xFFFFB408 | f32 | VIS position command |
| 0xFFFFB45C | u8 | VIS duty cycle index |
| 0x0006AC60 | f32[] | VIS mode 1 table |
| 0x0006AC7C | f32[] | VIS mode 2 table |
| 0x0006AC98 | f32[] | VIS mode 3 table |
| 0x0006ACB4 | f32[] | VIS mode 4 table |

### VFAD System

| Address | Type | Description |
|---|---|---|
| 0xFFFFB5B8 | f32 | RPM / sensor input |
| 0xFFFFC234 | u8 | VFAD validated command |
| 0xFFFFF754 | u16 | Solenoid port (bit 10) |

### OMP System

| Address | Type | Description |
|---|---|---|
| 0xFFFFA976 | u8 | OMP active flag |
| 0xFFFFA987 | u8 | OMP init/prime flag |
| 0xFFFFA988 | u8 | OMP engine-on flag |
| 0xFFFFA989 | u8 | OMP time accumulation |
| 0xFFFFA97B | u8 | OMP purge timer |
| 0xFFFFA974 | u8 | OMP stroke position |
| 0xFFFFA97F | u8 | OMP desired position |
| 0xFFFF807A | u16 | OMP stepper output |
| 0xFFFF807C | u16 | OMP purge command |
| 0xFFFF9ECD | u8 | Hardware fault register |
| 0xFFFFA985 | u8 | OMP idle rate parameter |
| 0xFFFFA984 | u8 | OMP normal rate parameter |
| 0xFFFFCD06 | u8 | Decel fuel cut flag |
| 0xFFFFA96B | u8 | Warm-up active flag |
| 0xFFFFA969 | u8 | Normal running flag |

### Cooling Fan System

| Address | Type | Description |
|---|---|---|
| 0xFFFFAA10 | f32 | Coolant temperature |
| 0xFFFFAA14 | f32 | Aux temperature |
| 0xFFFFBE16 | u8 | Fan 1 output |
| 0xFFFFBE17 | u8 | Fan 2 output |
| 0xFFFFB324 | u8 | Fan command register |
| 0xFFFF8766 | u8 | Fan PWM/limit register |
| 0xFFFF8076 | u8 | Fan relay output |
| 0xFFFFA73C | f32 | Coolant temp (alternate) |
| 0xFFFFA95C | u8 | Fan state flag |
| 0xFFFFAE54 | f32 | A/C pressure sensor |

### Alternator System

| Address | Type | Description |
|---|---|---|
| 0xB686 | u8 | Voltage control byte 1 |
| 0xB687 | u8 | Voltage control byte 2 |
| 0xB688 | u8 | Voltage control byte 3 |
| 0xB66B | u8 | Alternator state indicator |
| 0xB66C | f32 | Output voltage register |
| 0xB680 | u8 | State counter |
| 0xA9FC | f32 | Battery temperature |
| 0xBBE8 | f32 | Alternator current |
| 0xCEF2 | u8 | Operating mode |
| 0xB5FC | u8 | Over-voltage fault |
| 0xB5FD | u8 | Under-voltage fault |
| 0xB5FE | u8 | Control fault |
| 0xC5DB | u8 | Thermal fault |
| 0xB600 | u8 | Warning light output |
| 0xB663 | u8 | Charging system fault |

### EVAP/Purge System

| Address | Type | Description |
|---|---|---|
| 0xFFFFA6EC | f32 | Purge duty output |
| 0xFFFFA6F8 | f32 | Base purge flow |
| 0xFFFFA6FC | f32 | RPM compensation |
| 0xFFFFA704 | f32 | Load compensation |
| 0xFFFF8082 | u8 | Purge solenoid output |
| 0xFFFFA644 | f32 | EVAP calibration value |

## Appendix A: Design Patterns

- **Hysteresis comparator** — `input > threshold → ON; input < threshold-band → OFF; else hold` (SSV, VFAD, fans).
- **Alternating sensor state machines** (0x5D3E8, 0x5D800, …) — require N stable samples before output change, to prevent actuator oscillation.
- **Atomic SR save/restore** — `stc sr`, `ldc r0,sr` (with `0xe0`) around register writes — the standard critical-section idiom used by the aux drivers.

## Appendix B: Common Calibration Constants

| Value | Float Hex | Intended Use |
|---|---|---|
| 200.0 | 0x43480000 | SSV open threshold |
| 3.0 | 0x40400000 | SSV hysteresis band |
| 5250.0 | 0x45A41000 | VFAD open threshold |
| 188.0 | 0x433C0000 | VFAD hysteresis |
| 97.0 | 0x42C20000 | Fan ON threshold |
| 50.0 | 0x42480000 | APV threshold |
| 84.0 | 0x42A80000 | VIS position limit |
| 0.5 | 0x3F000000 | General scaling |
| -40.0 | 0xC2200000 | Temperature limit |

## Appendix C: Summary of Key Functions

| Function | Address | Size | Subsystem |
|---|---|---|---|
| `calc_idle_speed_target` | 0x12F5E | 274 | Idle |
| `idle_speed_control_18054` | 0x18054 | 372 | Idle |
| `idle_air_control_valve_47848` | 0x47848 | 26 | Idle |
| `adaptive_idle_47754` | 0x47754 | 50 | Idle |
| `idle_target_increase_step` | 0xE4B4 | 36 | Idle |
| `idle_speed_range_validator` | 0x19DDE | 130 | Idle |
| `idle_correction_saturation_check` | 0x1B4F8 | 84 | Idle |
| `idle_control_priority_task` | 0x1AA18 | 30 | Idle |
| `idle_warm_up_4790A` | 0x4790A | 8 | Idle |
| `idle_ac_load_47912` | 0x47912 | 20 | Idle |
| `idle_steering_load_47926` | 0x47926 | 26 | Idle |
| `idle_air_control_calc_2DB74` | 0x2DB74 | 22 | Idle |
| `idle_control_motor_3C1D8` | 0x3C0F8 | 230 | Idle |
| `idle_correction_interp_447B0` | 0x447B0 | 52 | Idle |
| `ssvControl__` | 0x225C8 | 94 | SSV |
| `calc_vis_solenoid_duty_cycle_1261C` | 0x1261C | 174 | VIS |
| `vis_intake_control_23718` | 0x23718 | 236 | VIS |
| `vfadControl_` | 0x35BBC | 132 | VFAD |
| `omp_control_task_1825E` | 0x1825E | 374 | OMP |
| `omp_fault_detect_44DF0` | 0x44DF0 | 572 | OMP |
| `getEngineOnTimeForOilMetering` | 0xE492 | 34 | OMP |
| `cooling_fan_control_0x17DCC` | 0x17DCC | 68 | Fans |
| `calcFan1Control` | 0x303A6 | 248 | Fans |
| `fan_speed_calc_1ED40` | 0x1ED40 | 82 | Fans |
| `fan_control_limit_calc_1C386` | 0x1C386 | 30 | Fans |
| `calcDesiredAlternatorVoltage` | 0x26520 | 1332 | Alternator |
| `setAlternatorWarningLight` | 0x275BC | 74 | Alternator |
| `getAlternatorFaultStatus` | 0x2687E | 26 | Alternator |
| `alternatorPIDsomething` | 0x5B394 | 272 | Alternator |
| `calcAPVControl` | 0x32AE8 | 398 | APV |
| `apvPositionVoltageCounter` | 0x32D4A | 60 | APV |
| `calc_evap_purge_duty` | 0x13652 | 92 | EVAP |
| `canister_purge_control` | 0x18F98 | 16 | EVAP |
| `purge_control_3F3FC` | 0x3F3FC | 92 | EVAP |
| `evapRelated` | 0x3A064 | 204 | EVAP |
| `channel_idle_fuel_controller` | 0x15C1C | 208 | Fuel (idle) |
| `idle_processing_dispatch` | 0x16A94 | 20 | Idle |

*Reverse engineering of Mazda RX-8 (13B-MSP) ECU firmware 60E1D400 and 60E0FC00 (Ghidra, IDA Pro, SH-2E disassembler). Source reconstruction is best-effort from assembly/decompilation.*
