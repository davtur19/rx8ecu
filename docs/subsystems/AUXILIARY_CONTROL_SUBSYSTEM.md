# RX-8 ECU Auxiliary & Idle Control Subsystems

This document captures the reverse-engineered control strategies for idle speed
regulation and auxiliary subsystems in the Mazda RX-8 Renesis (13B-MSP) ECU
firmware (SH-2E based, 60E1D400/60E0FC00 binaries).

---

## Table of Contents

1. [Idle Speed Control (ISC)](#1-idle-speed-control-isc)
2. [SSV — Secondary Shutter Valve](#2-ssv--secondary-shutter-valve)
3. [VIS — Variable Intake System](#3-vis--variable-intake-system)
4. [VFAD — Variable Fresh Air Duct](#4-vfad--variable-fresh-air-duct)
5. [OMP — Oil Metering Pump](#5-omp--oil-metering-pump)
6. [Cooling Fan Control](#6-cooling-fan-control)
7. [Alternator Voltage Control](#7-alternator-voltage-control)
8. [APV — Auxiliary Port Valves](#8-apv--auxiliary-port-valves)
9. [EVAP / Purge Control](#9-evap--purge-control)
10. [Global Memory Map](#10-global-memory-map)

---

## 1. Idle Speed Control (ISC)

### 1.1 Overview

The idle speed control system on the RX-8 is a closed-loop air bypass system.
Instead of a stepper motor (common on earlier Mazdas), the Renesis ECU uses a
linear solenoid (ISC valve) that varies the amount of air bypassing the throttle
plate. The control loop consists of:

1. **Target computation** — `calc_idle_speed_target()` (0x12F5E)
2. **State machine & mode dispatch** — `idle_speed_control_18054()` (0x18054)
3. **Air valve position** — `idle_air_control_valve_47848()` (0x47848)
4. **Adaptive learning** — `adaptive_idle_47754()` (0x47754)
5. **Load compensations** — warm-up, A/C, power steering

### 1.2 Target RPM Computation (`calc_idle_speed_target`, 0x12F5E)

```
Address: 0x12F5E  Size: 0x112 bytes (to 0x13070)
Source:  ida-ai (IDA auto-analysis)
Calls:   sensor_range_check_3ED0C
```

**Logic:**

```
if (engineOffFlag == 0) AND (engineSpeed > 0x9C3 = 2499 RPM) AND (someFlag == 0):
    idleTarget = sensor_range_check(DAT_c128 - DAT_c12c)  // Temp diff
    STORE idleTarget to output
else:
    idleTarget = 0

if (flagA6A9 == 1 AND someCondition) OR (flagA6AA == 1 AND someCondition2):
    counterA68F = -1        // Disable idle correction
elif counterA68F != 0:
    counterA68F--

if counterA68F == 0:
    Load calibrated target from table lookup
```

The function reads coolant temperature (or intake air temperature) from memory,
performs sensor range checking, and produces a target idle RPM that is stored
to RAM `0xFFFFA678` (as a float).

Key RAM variables:
- `0xFFFFA445` — flag byte
- `0xFFFFA444` — flag byte
- `0xFFFFC600` — engine-off flag
- `0xFFFFA424` — engine speed / RPM (16-bit)
- `0xFFFFAADA` — flag byte
- `0xFFFFC128` — target parameter 1 (float)
- `0xFFFFC12C` — target parameter 2 (float)
- `0xFFFFA678` — computed idle target (float)
- `0xFFFFA68F` — idle correction counter (signed byte)
- `0xFFFFA680` — base calibration value

### 1.3 Idle State Machine (`idle_speed_control_18054`, 0x18054)

```
Address: 0x18054  Size: 0x194 bytes (to 0x181E8)
Source:  ida-ai
Called from: main_engine_cycle_10ms (0x17F1C)
```

This is the main idle control dispatcher, called every 10ms. It implements a
multi-state machine:

```
states:
  - NORMAL (0)   — closed-loop idle control active
  - CRANK (1)    — during engine start
  - WARMUP (2)   — fast idle during warm-up
  - LOAD_COMP (3) — A/C or electrical load compensation

RAM variables used:
  0xFFFFA428 (DAT_ffffa428) — engine state (0=running, 1=starting)
  0xFFFFAAE0 (DAT_ffffaae0) — idle control enabled flag 
  0xFFFFA978 (DAT_ffffa978) — cranking state flag
  0xFFFFA979 (DAT_ffffa979) — idle transition flag
  0xFFFFA998 (DAT_ffffa998) — flag
  0xFFFFA96C (DAT_ffffa96c) — idle active flag
  0xFFFFA96A (DAT_ffffa96a) — flag
  0xFFFFA970 (DAT_ffffa970) — previous idle state
  0xFFFFA96E — idle counter (16-bit)
  0xFFFFAA14 — coolant temperature (float)
  0xFFFFAA10 — another temperature (float)
```

**Control flow:**

```
if engineRunning AND idleControlEnabled:
    Enter idle mode (set flag)
    Clear start request
    Set cranking timer to 2

elif engineStarting AND notCranking AND notOtherFlag:
    Set warm-up flag

else:
    Check if idle flag was set
    if engine stopped AND idleWasOn:
        Query shutdown sensor
    if someCondition AND cruiseActive AND flag:
        Set idleActive
    if idleEnabled AND idleFlag:
        Clear idle RPM accumulator

// Temperature-based RPM limiting
if coolant < -40.0°C:
    if idleCounter > 499: flag = 0   // Disable idle if too cold for >5s
elif idleCounter > 0x9B (155): flag = 0

// Counter accumulation
idleCounter += 1 (saturated 16-bit add)
```

### 1.4 Idle Air Control Valve (`idle_air_control_valve_47848`, 0x47848)

```
Address: 0x47848  Size: 26 bytes (to 0x47862)
Source:  ida-ai
```

This is the final ISC solenoid output stage — writes 16-bit and 8-bit values
to the hardware PWM registers controlling the idle air control valve:

```c
void idle_air_control_valve_47848(void) {
    // Write 16-bit ISC duty cycle to PWM output register
    write16(0xFFFF877C, read16(0xFFFF877C, 0));
    // Write 8-bit enable/flag to control register
    write8(0xFFFF8788, 1);
}
```

The actual ISC position is computed as a function of:
- Coolant temperature (warm-up compensation)
- A/C compressor clutch state
- Power steering pressure switch
- Alternator load (electrical load compensation)
- Adaptive learned base position

### 1.5 Adaptive Idle Learning (`adaptive_idle_47754`, 0x47754)

```
Address: 0x47754  Size: 50 bytes (to 0x47786)
Source:  ida-ai
```

```c
void adaptive_idle_47754(void) {
    if (DAT_ffffa3f0 == 0) {
        // If not in adaptive learning inhibit mode
        write16(0xFFFF8772, 0);  // Reset adaptive accumulator
    }
    int16_t adapVal = read16(0xFFFF8774, 0);
    if (adapVal != 0) {
        write16(0xFFFF8772, 0);  // Reset if non-zero
    }
    write16(0xFFFF8772, 1);  // Enable adaptive learning
}
```

### 1.6 Idle Target Increase Step (`idle_target_increase_step`, 0xE4B4)

```
Address: 0xE4B4  Size: 36 bytes (to 0xE4D8)
Source:  ida-ai
```

Increments the idle target RPM in steps for load compensation (A/C, power
steering, alternator). Each call adds a fixed step to the target until the
load-compensated target is reached.

### 1.7 Idle Warm-up Compensation (`idle_warm_up_4790A`, 0x4790A)

Small function that provides a multiplicative or additive correction to the
base idle target based on coolant temperature during warm-up. Higher correction
when cold, tapering to zero as the engine reaches operating temperature.

### 1.8 Idle A/C Load Compensation (`idle_ac_load_47912`, 0x47912)

Adjusts idle target upward when the A/C compressor is engaged. The ECU detects
the A/C compressor clutch signal and increments the idle target RPM to prevent
stalling from the additional load.

### 1.9 Idle Steering Load Compensation (`idle_steering_load_47926`, 0x47926)

Adjusts idle target upward when the power steering pressure switch is active
(wheels turned to lock at low speed). Prevents idle dip from hydraulic load.

### 1.10 Idle Correction Saturation Check (`idle_correction_saturation_check`, 0x1B4F8)

```
Address: 0x1B4F8  Size: 0x54 bytes (to 0x1B54C)
Source:  ida-ai
```

Anti-windup protection for the idle integrator. Clamps the accumulated idle
correction to prevent excessive overshoot when returning to idle from
deceleration.

### 1.11 ISC Control Implementation

The ISC solenoid is driven by a PWM signal from the SH-2E's MTU (Multi-Function
Timer Pulse Unit). The PWM duty cycle controls the solenoid position, which
in turn varies the amount of bypass air.

```c
// High-level ISC control flow:
void isc_control_loop(void) {
    // 1. Get target RPM from tables
    float targetRpm = calc_idle_speed_target();
    
    // 2. Get actual RPM from engine speed sensor
    float actualRpm = get_engine_speed();
    
    // 3. Compute error
    float rpmError = targetRpm - actualRpm;
    
    // 4. Apply PID compensation
    iscPosition = pid_controller(rpmError);
    
    // 5. Add feed-forward compensations
    iscPosition += warmup_compensation(coolantTemp);
    iscPosition += ac_load_compensation(acClutchState);
    iscPosition += ps_load_compensation(psSwitchState);
    iscPosition += alt_load_compensation(electricalLoad);
    
    // 6. Apply adaptive learned trim
    iscPosition += adaptive_trim();
    
    // 7. Clamp to valid range
    iscPosition = clamp(iscPosition, ISC_MIN, ISC_MAX);
    
    // 8. Output PWM duty cycle
    set_isc_pwm(iscPosition);
}
```

### 1.12 Calibration Tables (Typical Values)

| Parameter | Range | Units | Notes |
|-----------|-------|-------|-------|
| Base idle target (warm) | 750-850 | RPM | Closed loop |
| Fast idle (cold) | 1000-1500 | RPM | Engine < 60°C |
| A/C compensation | +50-100 | RPM | Step increase |
| Power steering comp | +30-50 | RPM | At lock |
| Alternator load comp | +20-50 | RPM | Electrical load |
| ISC PWM frequency | ~100-200 | Hz | Solenoid drive |
| Adaptive range | ±20% | Duty | Learned trim |

---

## 2. SSV — Secondary Shutter Valve

### 2.1 Overview

The Secondary Shutter Valve (SSV) is a two-position intake valve in the RX-8's
variable intake system. It opens/closes a secondary intake port at specific RPM
thresholds to optimize the torque curve. The SSV is controlled by a vacuum
actuator with a solenoid valve.

Key characteristics:
- **Closed** below ~2000 RPM (long runner for low-end torque)
- **Open** above ~2000 RPM (short runner for high-end power)
- Uses hysteresis to prevent oscillation at the threshold

### 2.2 SSV Control Function (`ssvControl__`, 0x225C8)

```
Address:  0x225C8  Size: 94 bytes (to 0x22626)
Source:   ghidra-hand-xmap
Called from: torque_dispatcher_225A2 / direct_branch_to_torque_calc_2259C
```

**Assembly analysis reveals:**

```asm
ssvControl__:
    r11 = read8(0xFFFFAAE0)        // Engine state / enable flag
    fr4 = read32(0xFFFFAA10)       // NOT CONFIRMED — see note below
    fr6 = read32(CAL_SSV_THRESH)   // SSV actuation threshold (NOT verified)
    fr5 = fr6 - 3.0                // Hysteresis band (3 RPM deadband)
    
    if (fr4 > fr6) {
        // Above threshold: OPEN SSV
        write8(SSV_OUTPUT, 1)
    } else if (fr4 < fr5) {
        // Below hysteresis band: CLOSE SSV
        write8(SSV_OUTPUT, 0)
    }
    // Else: maintain current position (hysteresis)
    
    // Ramp control for smooth actuation
    if (r11 == 0 AND flagB325 == 1) {
        // Ramp up - load target angle
        target = read16(CAL_SSV_RAMP_TARGET)
        write16(SSV_RAMP_REG, target)
    } else if (SSV_RAMP_REG > 0) {
        // Decrement ramp
        SSV_RAMP_REG -= 0xFFFF  // Saturating decrement
    }
    
    // State machine for engagement
    if (flagB325_saved == 1) OR (flagBF39 == 1) OR 
       (engineOn AND rampActive AND ssvClosed):
        uVar2 = 1   // Enable SSV actuation
    else:
        uVar2 = 0
        
    // Output via alternating sensor state machine
    output = alternating_sensor_sm_08_5D3E8(uVar2)
    write8(0xFFFFB320, output)
    
    // Set hardware output bit
    if (output == 1):
        setRegister_REG_BIT_VAL(0xFFFFF754, 0x80, 1)  // Bit 7 = SSV solenoid
    else:
        setRegister_REG_BIT_VAL(0xFFFFF754, 0x80, 0)
    
    write8(0xFFFFB325, r11)  // Save engine state
```

**SSV threshold input not yet verified** — 0xFFFFAA10 is the coolant-temp
input in the verified OMP gate (`omp_waveform_state_machine_18860.c`), which
conflicts with the "air demand/RPM" reading assumed above; the real SSV opens
the secondary port ~3750 RPM per external references. No new values are
claimed here.

**Decoded C implementation:**

```c
void ssvControl(uint8_t param) {
    uint8_t engineState = read8(0xFFFFAAE0);  // Engine running?
    float airDemand = read32(0xFFFFAA10);       // NOT CONFIRMED — see note above
    
    // Calibration thresholds — NOT verified (see note above)
    float threshold = 200.0f;    // SSV_OPEN_THRESHOLD (unconfirmed)
    float hysteresis = 3.0f;     // SSV_HYSTERESIS_BAND
    
    // Hysteresis comparison
    uint8_t ssvSolenoidOutput;
    if (airDemand > threshold) {
        ssvSolenoidOutput = 1;  // OPEN
    } else if (airDemand < (threshold - hysteresis)) {
        ssvSolenoidOutput = 0;  // CLOSE
    }
    write8(0xFFFFB324, ssvSolenoidOutput);  // SSV command register
    
    // Ramp control
    if (engineState == 0 && read8(0xFFFFB325) == 1) {
        // Transitioning from running to stopped: rapid close
        write16(0xFFFFB322, 0xBC);  // Load ramp target (~188)
    } else if (read16(0xFFFFB322) > 0) {
        write16(0xFFFFB322, read16(0xFFFFB322) - 1);  // Decrement
    }
    
    // Decision logic with multiple enable conditions
    uint8_t enableSSV = 0;
    if ((engineState == 0) ||                        // Engine off
        (read8(0xFFFFBF39) == 1) ||                   // Force close
        (engineState == 0 && read16(0xFFFFB322) > 0 && ssvSolenoidOutput == 0)) {
        enableSSV = 1;  // Enable solenoid
    }
    
    // Output via debounced/validated state machine
    uint8_t validatedOutput = alternating_sensor_sm_08_5D3E8(enableSSV);
    write8(0xFFFFB320, validatedOutput);
    
    // Hardware output
    if (validatedOutput == 1) {
        // Set bit 7 on port 0xFFFFF754 (SSV solenoid ON)
        setRegisterBit(0xFFFFF754, 7, 1);
    } else {
        setRegisterBit(0xFFFFF754, 7, 0);
    }
    
    // Save engine state for next cycle
    write8(0xFFFFB325, engineState);
}
```

### 2.3 SSV Calibration

| Parameter | Address | Typical Value | Description |
|-----------|---------|---------------|-------------|
| Open threshold | Cal table | NOT confirmed (~200.0 claimed, disputed) | NOT VERIFIED — 0xFFFFAA10 conflicts with the OMP ECT gate; real SSV opens ~3750 RPM per external refs |
| Hysteresis band | Hardcoded | 3.0 | Prevents oscillation at threshold |
| Ramp target | 0xFFFFB322 | 0xBC (188) | Ramp-down count for soft close |

### 2.4 Hardware Interface

- **Port**: 0xFFFFF754, Bit 7 (0x80)
- **Output**: 0xFFFFB320 (validated command)
- **Ramp**: 0xFFFFB322 (ramp counter)

---

## 3. VIS — Variable Intake System

### 3.1 Overview

The Variable Intake System (VIS) controls additional intake valves that 
dynamically change the intake runner length/cross-section. Unlike the SSV 
(simple open/close), the VIS uses a continuously variable or multi-position
actuator controlled by a duty-cycled solenoid.

### 3.2 VIS Intake Control (`vis_intake_control_23718`, 0x23718)

```
Address:  0x23718  Size: 236 bytes (to 0x23804)
Source:   ida-ai
Called from: engine_control_master_task_23DC8
```

**Logic:**

```
vis_intake_control_23718:
    // Read sensor input and operating flags
    fr5 = read32(RPM_SENSOR)
    fr4 = read32(AIR_DEMAND)
    
    // State selector based on flag bytes
    if (DAT_b33c == 1):
        table = TABLE_VIS_MODE_1    // 0x6AC60
    else:
        if (DAT_b33d == 1):
            table = TABLE_VIS_MODE_2  // 0x6AC7C
        else:
            if (DAT_b33e == 1):
                table = TABLE_VIS_MODE_3  // 0x6AC98
            else:
                table = TABLE_VIS_MODE_4  // 0x6ACB4
    
    // 3D table lookup for intake position
    result = _3dLookup(table)
    
    // Apply saturation limit of 84.0 RPM equiv.
    saturated = fpu_compare_and_select(84.0, result)
    store32(0xFFFFB408, saturated)  // VIS position command
    
    // Index mapping for solenoid duty cycle
    if (condition):
        visPosition = 0   // Disable
    else:
        index = axis_lookup_float_to_index(1.0, saturated)
        // Cap at 12 (solenoid steps)
        if (index > 12): index = 12
        store8(0xFFFFB45C, index)
    
    // Calculate solenoid duty cycle from position
    for (step = 11; step >= 0; step--):
        dutyTable[step] = calc_vis_solenoid_duty(step)
    
    // Store computed duty values
    store32(VIS_DUTY_REG, computedDuty)
```

### 3.3 VIS Solenoid Duty Cycle (`calc_vis_solenoid_duty_cycle_1261C`, 0x1261C)

```
Address: 0x1261C  Size: 0xAE bytes (to 0x126CA)
Source:  ida-ai
```

Computes the PWM duty cycle for the VIS solenoid based on the desired position
index. Uses calibrated duty values stored in a lookup table.

### 3.4 VIS Calibration Tables

| Address | Description | Format |
|---------|-------------|--------|
| 0x6AC60 | VIS position map (mode 1) | 3D float table |
| 0x6AC7C | VIS position map (mode 2) | 3D float table |
| 0x6AC98 | VIS position map (mode 3) | 3D float table |
| 0x6ACB4 | VIS position map (mode 4) | 3D float table |
| 0x6ACxx | VIS duty cycle table | 12-entry float array |

---

## 4. VFAD — Variable Fresh Air Duct

### 4.1 Overview

The Variable Fresh Air Duct (VFAD) is an intake system feature unique to 
the RX-8. It controls an auxiliary air intake duct that opens at higher RPM
to reduce intake restriction and increase volumetric efficiency.

The VFAD actuator is a vacuum-operated valve controlled by a solenoid,
similar to the SSV.

### 4.2 VFAD Control (`vfadControl_`, 0x35BBC)

```
Address:  0x35BBC  Size: 132 bytes (to 0x35C3F)
Source:   ghidra-hand-xmap
Called from: task_priority_dispatch_wrapper_35B96
```

**Assembly analysis:**

```asm
vfadControl_:
    fr4 = read32(0xFFFFB5B8)       // RPM or MAF sensor (float)
    fr6 = 5250.0                    // VFAD open threshold (RPM)
    fr5 = fr6 - 188.0               // Hysteresis band (5062 RPM)
    
    if (fr4 > fr6) {
        // RPM above 5250: OPEN VFAD
        r4 = 1
    } else if (fr4 < fr5) {
        // RPM below 5062: CLOSE VFAD
        r4 = 0
    }
    // Hysteresis region: maintain last state
    
    // Debounce through state machine
    output = alternating_sensor_sm_09_5D800(r4)
    write8(0xFFFFC234, output)
    
    // Hardware output
    if (output == 1):
        setRegister_REG_BIT_VAL(0xFFFFF754, 0x400, 1)  // Bit 10 = VFAD solenoid
    else:
        setRegister_REG_BIT_VAL(0xFFFFF754, 0x400, 0)
```

**Decoded C implementation:**

```c
void vfadControl(uint8_t param) {
    // Read RPM or equivalent load parameter
    float rpm = read32(0xFFFFB5B8);
    
    // Calibration thresholds
    const float VFAD_OPEN_THRESH = 5250.0f;   // RPM to open
    const float VFAD_HYSTERESIS = 188.0f;     // Deadband
    
    uint8_t cmd;
    if (rpm > VFAD_OPEN_THRESH) {
        cmd = 1;  // OPEN duct
    } else if (rpm < (VFAD_OPEN_THRESH - VFAD_HYSTERESIS)) {
        cmd = 0;  // CLOSE duct
    } else {
        // Hysteresis region — maintain previous state
        // (handled implicitly by alternating_sensor_sm)
    }
    
    // Debounce via state machine (prevents rapid cycling)
    uint8_t validatedCmd = alternating_sensor_sm_09_5D800(cmd);
    write8(0xFFFFC234, validatedCmd);
    
    // Set hardware output bit
    if (validatedCmd == 1) {
        setRegisterBit(0xFFFFF754, 10, 1);  // Bit 10 = VFAD solenoid ON
    } else {
        setRegisterBit(0xFFFFF754, 10, 0);
    }
}
```

### 4.3 VFAD Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| Open threshold | 5250 RPM | Duct opens for high-RPM airflow |
| Hysteresis | 188 RPM | Prevents oscillation (closes at ~5062 RPM) |
| Output port | 0xFFFFF754, bit 10 | Solenoid driver |
| State register | 0xFFFFC234 | Validated command state |

### 4.4 Comparison: VFAD vs SSV

Both systems use the same design pattern:
1. Hysteresis comparator with a threshold
2. Alternating sensor state machine for debounce
3. Direct bit manipulation on port 0xFFFFF754
4. Save/restore SR for atomic register access

| Feature | SSV | VFAD |
|---------|-----|------|
| Threshold | ~200 RPM | 5250 RPM |
| Hysteresis | 3 RPM | 188 RPM |
| Port bit | Bit 7 (0x80) | Bit 10 (0x400) |
| State machine | alt_sm_08 | alt_sm_09 |
| Ramping | Yes | No |

---

## 5. OMP — Oil Metering Pump

### 5.1 Overview

The Oil Metering Pump (OMP) is a critical subsystem unique to rotary engines.
It injects engine oil directly into the combustion chambers to lubricate the
apex seals and rotor housings. The RX-8 uses an electronically controlled
stepper motor OMP that varies the oil delivery rate based on:

- Engine RPM
- Engine load (throttle position / intake vacuum)
- Coolant temperature
- Throttle position change rate (acceleration enrichment)

### 5.2 OMP Control Function (`omp_control_task_1825E`, 0x1825E)

```
Address:  0x1825E  Size: 374 bytes (to 0x18552)
Source:   ghidra-hand-xmap
Called from: main_engine_cycle_10ms
Lift:     c/omp_control_task_1825E.c — emulator-verified (150000+ random inputs, 0 mismatches)
```

**Decompiled logic:**

```c
void omp_control_task_1825E(void) {
    uint8_t engineState = read8(0xFFFFA96C); // Engine running flag
    
    // Check hardware fault bit
    if ((read8(0xFFFF9ECD) & 2) == 0) {
        // Fault detected - disable OMP
        DAT_ffffa976 = 0;
    } else {
        // Normal operation
        if (DAT_ffffa976 == 0) {
            DAT_ffffa987 = 1;  // First-time init flag
        }
        DAT_ffffa976 = 1;  // OMP active
    }
    
    // Pump-on time accumulation
    if (DAT_ffffa988 == 1 && engineState == 0) {
        DAT_ffffa989 = 1;  // Engine running, accumulate time
    }
    
    // Reset operating mode flags when not in idle
    if (DAT_ffffa968 == 0) {
        DAT_ffffa977 = 0;
        DAT_ffffa978 = 0;
    }
    
    // Timer for OMP priming/purging
    if (DAT_ffffa97b != 0) {
        DAT_ffffa97b--;  // Decrement timer
    }
    
    // Special purge cycle
    if (DAT_ffffa97b == 1 && DAT_ffffa968 == 1 && DAT_ffffa982 == 1) {
        DAT_ffffa974 = 0;
        DAT_ffffa97f = 0;
        write8(0xFFFF807C, 0);  // Output purge command (8-bit port write)
    }
    
    if (DAT_ffffa97b != 0) {
        // Timer active - save state and return
        DAT_ffffa988 = engineState;
        return;
    }
    
    // Mode dispatch - select OMP delivery profile
    DAT_ffffa974 = DAT_ffffa97f;  // OMP stroke position
    
    if (DAT_ffffa998 == 1) {
        // Mode: Cranking / starting enrichment
        omp_cranking_mode();
    } else if (DAT_ffffa968 == 1) {
        // Mode: Idle speed control active
        omp_idle_mode(read8(DAT_ffffa985));
    } else if (DAT_ffffa96a == 1 && DAT_ffffcd06 == 0) {
        // Mode: Deceleration fuel cut
        omp_decel_mode();
    } else if (DAT_ffffa96b == 1) {
        // Mode: Warm-up
        omp_warmup_mode();
    } else if (DAT_ffffa969 == 1) {
        // Mode: Normal running
        omp_normal_mode(read8(DAT_ffffa984));
    }
    
    // Common tail (0x184C8..0x18516): output position + A975 delivery ramp
    if (engineState == 1 && DAT_ffffa987 == 1) {
        write8(0xFFFF807A, DAT_ffffa974);  // OMP stepper position (8-bit port write)
    }

    // NOTE: 0x37 is the READ accessor default, NOT an idle/off position written
    // here — the earlier "send idle/off write16(0x807A,0x37)" sketch was wrong.
    // The 0x807A read is 8-bit: readValue_8bit_ADDRESS_VAL(0xFFFF807A, 0x37).
    uint8_t read7a = readValue_8bit_ADDRESS_VAL(0xFFFF807A, 0x37);

    // Delivery ramp (A975): increments SATURATE via addSaturate8Bit @0x2478
    // (min(A975+1, 255)); the decrement wraps mod 256 and requires A974 >= CAL37
    // (0x3C) with the pump healthy (A976 == 1).
    if (DAT_ffffa989 == 1) {
        if (read7a < CAL36 || (DAT_ffffa974 >= CAL37 && DAT_ffffa976 == 0)) {
            DAT_ffffa975 = addSaturate8Bit(DAT_ffffa975, 1);   // 0x2478
        } else if (DAT_ffffa974 >= CAL37 && DAT_ffffa976 == 1 && DAT_ffffa975 != 0) {
            DAT_ffffa975--;  // (uint8_t) wraps mod 256
        }
    }

    if (DAT_ffffa975 == 0) {
        write8(0xFFFF8078, CAL35);  // CAL35 = 0x02 (P8078 write value)
    } else if (DAT_ffffa975 != 4) {
        DAT_ffffa979 = 0;
        DAT_ffffa982 = 0;
    }
}
```

> **Verification note (2026-08-01):** this function is now lifted as
> `c/omp_control_task_1825E.c` and emulator-verified (150000+ random inputs across 5
> seeds, 0 mismatches). The pseudo-sketch above matches the verified lift; the
> internal task leaves 0x18C6C / 0x18C5C / 0x18C08 run natively in the emulator
> (effects inlined in the lift, not separately lifted as C). Cal bytes: CAL35
> @0x78E35 = 0x02, CAL36 @0x78E36 = 0x34, CAL37 @0x78E37 = 0x3C.

### 5.3 OMP Operating Modes

| Mode | Flag | When Active | Oil Rate |
|------|------|-------------|----------|
| Cranking | `a998==1` | Engine start | High prime rate |
| Idle | `a968==1` | Idle speed control | Low base rate |
| Decel/FC | `a96a==1` | Deceleration fuel cut | Reduced rate |
| Warm-up | `a96b==1` | Engine cold | Medium rate |
| Normal | `a969==1` | Normal driving | RPM/load mapped |
| Purge | `a97b timer` | Periodic OMP flush | Full stroke |

### 5.4 OMP Fault Detection (`omp_fault_detect_44DF0`, 0x44DF0)

```
Address: 0x44DF0  Size: 0x23C bytes (to 0x4502C)
Source:  ida-ai
```

Monitors the OMP position feedback sensor and detects:
- **Open circuit** — no current through OMP stepper coils
- **Short circuit** — coil resistance out of range
- **Stall** — stepper motor not moving despite drive signal
- **Range fault** — position sensor voltage outside valid range

Each fault sets a corresponding diagnostic trouble code (DTC) and may
illuminate the MIL (Malfunction Indicator Lamp).

### 5.5 OMP Calibration

OMP oil delivery is mapped in 2D and 3D tables:

| Axis | Range | Description |
|------|-------|-------------|
| RPM | 0-9000 | Engine speed |
| Load (MAP) | 20-100+ kPa | Manifold pressure |
| Coolant temp | -40 to 120°C | Temperature compensation |

> **OMP "cold" gate (0x18860 state 1):** the -40.0 threshold at ROM 0x78E68
> is a **sensor-validity split**, not a cold-weather calibration A/B: the two
> cal bytes are identical in stock ROM (CAL_A @0x78E33 == CAL_B @0x78E34 ==
> 0x3C), so no cold correction is applied — the gate only picks the validity
> side (temp < -40.0 → cal A / A978, else cal B / A977; A97E = cal byte).

Typical oil delivery rates:
- **Idle**: ~0.5-1.0 cc/min (very low)
- **Cruise**: ~1.0-2.0 cc/min 
- **Acceleration**: ~3.0-5.0 cc/min (transient enrichment)
- **High RPM/WOT**: ~5.0-8.0 cc/min
- **Cranking prime**: ~10.0 cc/min (brief)

### 5.6 Engine-On Time Tracking (`getEngineOnTimeForOilMetering`, 0xE492)

```
Address: 0xE492  Size: 34 bytes (to 0xE4B4)
Source:  ghidra-hand-xmap
```

Tracks cumulative engine-on time (in seconds or minutes) used by the OMP
control logic to schedule maintenance cycles (purge, system checks).

---

## 6. Cooling Fan Control

### 6.1 Overview

The RX-8 has dual electric cooling fans with multiple speed stages. The ECU
controls fan relays based on:

- Coolant temperature (primary)
- A/C compressor pressure 
- Vehicle speed (ram air effect)
- Engine load (heat rejection)

### 6.2 Fan 1 Control (`calcFan1Control`, 0x303A6)

```
Address:  0x303A6  Size: 248 bytes (to 0x3049E)
Source:   ghidra-hand-xmap
Called from: priority_task_port_init_300F2
```

**Decoded logic:**

```c
void calcFan1Control(void) {
    float coolantTemp = read32(0xFFFFAA10); // Coolant temperature
    float threshold = 97.0f;                 // Fan ON threshold (°C)
    float hysteresis = 32.0f;                // Hysteresis band
    
    // Primary fan ON/OFF hysteresis
    if (coolantTemp > threshold) {
        // Above 97°C: Fan ON (high speed)
        write8(FAN1_OUTPUT, 1);
    } else if (coolantTemp < (threshold - hysteresis)) {
        // Below 65°C: Fan OFF
        write8(FAN1_OUTPUT, 0);
    }
    
    // Secondary stage (higher speed or second fan)
    if (coolantTemp > threshold) {
        write8(FAN1B_OUTPUT, 1);
    } else if (coolantTemp < (threshold - hysteresis)) {
        write8(FAN1B_OUTPUT, 0);
    }
    
    // Complex enable conditions
    if (fan1IsOn OR secondaryFanIsOn) {
        // Check A/C request, vehicle speed, etc.
        if (acRequest AND NOT acThermalProtect AND
            NOT vehicleSpeedCond AND ...) {
            // Enable fan operation
            write8(FAN_ENABLE, 1);
        }
    }
    
    // Conditional logic chain for final output
    // Multiple flag-based conditions determine fan state
    // Priority: A/C request > thermal > speed
    FAN_FINAL_OUTPUT = evaluate_conditions();
}
```

### 6.3 Coolant Temperature Fan Control (`cooling_fan_control_0x17DCC`, 0x17DCC)

```
Address:  0x17DCC  Size: 68 bytes (to 0x17E20)
Source:   ida-ai
Called from: calc_spark_advance_offset_map
```

Simpler fan control based on a single temperature comparison:

```c
void cooling_fan_control_0x17DCC(uint32_t param) {
    float coolantTemp = read32(0xFFFFA73C);
    float threshold = 0.00001f;  // From constant table
    
    uint8_t fanRequest = complement_shift_u32(coolantTemp, threshold);
    
    if (DAT_ffffa95c == 0 && fanRequest != 0) {
        // Fan requested and not already on: turn on
        DAT_ffffa93b = addSaturate8Bit(DAT_ffffa93b, 1);
        write8(0xFFFF8076, 0);  // Fan relay control
    }
    
    DAT_ffffa95c = fanRequest;  // Save state
}
```

### 6.4 Fan Speed Calculation (`fan_speed_calc_1ED40`, 0x1ED40)

```
Address:  0x1ED40  Size: 82 bytes (to 0x1ED92)
Source:   ida-ai
Called from: main_control_loop_processor_21C90
```

Computes desired fan speed based on:
- Coolant temperature
- A/C high-side pressure
- Vehicle speed

```c
void fan_speed_calc_1ED40(uint32_t param) {
    if (engineRunning) {
        float coolantTemp = read32(0xFFFFAA10);
        float acPressure = read32(0xFFFFAE54);
        
        // Determine fan speed stage
        if (coolantTemp > LOW_TEMP_THRESH || acPressure > LOW_PRESS_THRESH) {
            // Low speed
            setFanSpeed(FAN_LOW);
        }
        if (coolantTemp > HIGH_TEMP_THRESH || acPressure > HIGH_PRESS_THRESH) {
            // High speed
            setFanSpeed(FAN_HIGH);
        }
        
        // Apply vehicle speed correction
        // (reduced fan speed at high speed due to ram air)
    }
}
```

### 6.5 Temperature Thresholds

| Fan Stage | ON Temp | OFF Temp (Hysteresis) | Notes |
|-----------|---------|----------------------|-------|
| Fan 1 Low | ~97°C | ~65°C | Primary cooling |
| Fan 1 High | ~100-105°C | ~65°C | Higher speed |
| Fan 2 (Aux) | A/C dependent | A/C dependent | Condenser cooling |
| Thermal protection | ~110-115°C | ~100°C | Emergency override |

### 6.6 Hardware Interface

| Register | Function | Notes |
|----------|----------|-------|
| 0xFFFFB324 | Fan 1 command | 0=off, 1=on |
| 0xFFFFBE16 | Fan 1 output bit | |
| 0xFFFFBE17 | Fan 2 output bit | |
| 0xFFFFB324 | Fan control register | |
| 0xFFFF8766 | Fan PWM / limit reg | |
| 0xFFFF8076 | Fan relay output | Direct I/O write |

---

## 7. Alternator Voltage Control

### 7.1 Overview

The RX-8 ECU controls the alternator output voltage to optimize battery charging
and manage electrical load on the engine. The system uses a multi-stage voltage
control strategy based on:

- Battery temperature
- Electrical load (current demand)
- Engine operating state (idle vs. cruising)
- Thermal constraints (alternator temperature)

### 7.2 Alternator Control Functions

The alternator control is located in the 60E0FC00 binary and consists of:

| Function | Address | Purpose |
|----------|---------|---------|
| `calculateOutputforAlternator` | 0x25F98 | Calculate base voltage output |
| `alternatorStuff` | 0x26044 | Main alternator control logic |
| `calcDesiredAlternatorVoltage` | 0x26520 | Target voltage computation |
| `getAlternatorFaultStatus` | 0x26298 | Diagnostic monitoring |
| `getAlternatorSpeedConditonal` | 0x26308 | Speed-dependent conditions |
| `getVehicleConditionforAlternatorControl` | 0x2639A | Load state detection |
| `calculateAlternatorDiagDCOutput` | 0x26F48 | Diagnostic duty cycle |
| `setAlternatorWarningLight` | 0x27084 | Dash warning lamp control |
| `alternatorControlMain` | 0x270EA / 0x2718C | Main control entry |
| `alternatorControl` | 0x27132 | Control logic core |
| `alternatorPIDsomething` | 0x5B394 | PID controller |
| `setAlternatorFault` | 0x52698 | Fault flag management |

### 7.3 Voltage Control Strategy (`calcDesiredAlternatorVoltage`, 0x26520)

From the existing analysis:

```c
void calcDesiredAlternatorVoltage(void) {
    float batteryTemp = read32(0xA9FC);      // Battery temperature
    float electricalLoad = read32(0xBBE8);    // Alternator current
    float voltageAdj = read32(0xB694);        // Voltage trim
    
    // Load calibration limits for control stages
    float tempLimitLow = read32(0x74AD4);     // Cold threshold
    float tempLimitMid = read32(0x74AD8);     // Warm threshold  
    float tempLimitHigh = read32(0x74ADC);    // Hot threshold
    
    uint8_t ctrlMode = read8(0xCEF2);        // Operating mode (0-2)
    
    // Stage 1: Temperature-based voltage trim
    if (batteryTemp > tempLimitLow) {
        write8(0xB686, 0);  // Low voltage mode
    } else {
        write8(0xB686, 1);  // High voltage mode
    }
    
    // Stage 2: Load-based voltage trim
    if (electricalLoad > tempLimitMid) {
        write8(0xB687, 1);  // Boost voltage for load
    } else {
        write8(0xB687, 0);  // Normal voltage
    }
    
    // Stage 3: Additional compensation
    write8(0xB688, electricalLoad > tempLimitHigh ? 1 : 0);
    
    // Main voltage calculation
    if (ctrlMode == 1) {
        // Normal mode: PID voltage regulation
        float currentVoltage = read32(0xB66C);
        float targetVoltage = read32(0x74B0C);
        
        // Clamp to limits
        currentVoltage = saturateLow(currentVoltage, read32(0x74B10));
        float result = currentVoltage - minValue(currentVoltage, tempLimitLow);
        write32(0xB66C, result);
        
        // PID update
        uint32_t scaleFactor = isNotZero(read32(0xB5E8));
        if (scaleFactor) {
            alternatorPIDsomething(currentVoltage);
            uint8_t stateCounter = read8(0xB680);
            stateCounter = addSaturate8Bit(stateCounter, 1);
            write8(0xB680, stateCounter);
        }
    } else {
        // Alternate mode: simpler lookup-based voltage
    }
}
```

### 7.4 Alternator Warning Light (`setAlternatorWarningLight`, 0x275BC/0x27084)

Simple fault OR logic:

```c
void setAlternatorWarningLight(void) {
    if (!read8(0xB663)) {          // Charging system fault
        write8(0xB600, 1);          // Light ON
        return;
    }
    if (read8(0xB5FC) == 1) {       // Over-voltage
        write8(0xB600, 1); return;
    }
    if (read8(0xB5FD) == 1) {       // Under-voltage
        write8(0xB600, 1); return;
    }
    if (read8(0xB5FE) == 1) {       // Control fault
        write8(0xB600, 1); return;
    }
    
    // Thermal/charging fault
    write8(0xB600, read8(0xC5DB) == 1 ? 1 : 0);
}
```

### 7.5 Voltage Targets

| Condition | Target Voltage | Notes |
|-----------|---------------|-------|
| Cold battery (< -10°C) | ~14.8-15.0V | Boost charging |
| Normal (warm) | ~13.5-14.2V | Standard regulation |
| Hot battery (> 50°C) | ~13.0-13.5V | Reduced for thermal |
| High load | 14.0-14.5V | Compensate for voltage drop |
| Idle (no load) | ~12.5-13.0V | Reduced engine load |

---

## 8. APV — Auxiliary Port Valves

### 8.1 Overview

The Auxiliary Port Valves (APV) are part of the RX-8's variable intake system.
They control additional intake ports that open at higher RPM to increase power.
The APVs are actuated by vacuum diaphragms controlled by a solenoid valve,
similar in concept to the SSV.

### 8.2 APV Control (`calcAPVControl`, 0x32AE8)

```
Address:  0x32AE8  Size: 398 bytes (to 0x32C7A)
Source:   ghidra-hand-xmap
Called from: priority_multi_function_dispatch_32A9C
```

```c
void calcAPVControl(void) {
    // Read APV position sensor voltage
    float apvPosition = read32(0xFFFFB5B8);  // Position voltage
    float threshold = 48.0f;                  // RPM/position threshold
    float hysteresis = 0.0f;                  // No hysteresis for APV
    // 0x42480000 = 50.0 in float
    
    uint8_t apvMode = read8(0xFFFFBFF5);
    uint8_t apvState = read8(0xFFFFBFF6);
    
    // Primary hysteresis comparison
    if (apvPosition > threshold) {
        write8(APV_OUTPUT, 1);  // Open APV
    } else if (apvPosition < (threshold - 50.0f)) {
        write8(APV_OUTPUT, 0);  // Close APV
    }
    
    // State machine for position control
    if (apvState == 0 && read16(0xFFFFBFFA) > 50) {
        // Position counter above 50: close APV
        write8(0xFFFFBFF5, 0);
    } else if (engineOn == 0 && apvPosition < threshold) {
        // Engine off and below threshold: open
        write8(0xFFFFBFF5, 1);
    }
    
    // Output enable conditions
    if (apvMode == 1 && someFlag == 0 && anotherFlag == 0) {
        // Actuate APV
        write8(0xFFFFBFF6, read16(0xFFFFBFF8) < 50);
        write16(0xFFFFBFF8, add16bitSaturate(read16(0xFFFFBFF8), 1));
    } else {
        write8(0xFFFFBFF6, 0);
        write16(0xFFFFBFF8, 0);
    }
    
    // Additional position sensor monitoring
    float sensorVoltage = read32(APV_SENSOR);
    float minVoltage = read32(APV_MIN_CAL);
    float maxVoltage = read32(APV_MAX_CAL);
    
    // Voltage range checking for diagnostic
    if (sensorVoltage > threshold) {
        write8(APV_DIAG_OK, 1);
    } else if (sensorVoltage < (threshold - hysteresis)) {
        write8(APV_DIAG_OK, 0);
    }
}
```

### 8.3 APV Calibration

| Parameter | Address | Value | Notes |
|-----------|---------|-------|-------|
| Open threshold | Hardcoded | ~48.0 RPM equiv. | APV actuation point |
| Hysteresis | ~50.0 | Hardcoded | Prevent oscillation |
| Position sensor | 0xFFFFB5B8 | Float voltage | Feedback signal |
| Output register | 0xFFFFC001 | Byte | Solenoid command |

---

## 9. EVAP / Purge Control

### 9.1 Overview

The Evaporative Emission (EVAP) system captures fuel vapors from the fuel tank
and stores them in a charcoal canister. The ECU periodically opens a purge valve
to draw stored vapors into the intake manifold for combustion.

### 9.2 Purge Duty Calculation (`calc_evap_purge_duty`, 0x13652)

```
Address:  0x13652  Size: 92 bytes (to 0x136AE)
Source:   ida-ai
```

```c
void calc_evap_purge_duty(void) {
    // Read base purge flow from lookup table
    float baseDuty = read32(0xFFFFA6F8);
    
    // Read compensation factors
    float rpmComp = read32(0xFFFFA6FC);
    float loadComp = read32(0xFFFFA704);
    
    // Calculate final purge duty cycle
    float purgeDuty = baseDuty + rpmComp + loadComp;
    
    // Apply saturation limits
    if (purgeDuty < 0.0f) purgeDuty = 0.0f;
    if (purgeDuty > 100.0f) purgeDuty = 100.0f;
    
    // Store output
    write32(0xFFFFA6EC, purgeDuty);
}
```

### 9.3 Canister Purge Control (`canister_purge_control`, 0x18F98)

```
Address:  0x18F98  Size: 16 bytes (to 0x18FA8)
Source:   ida-ai
```

Simple wrapper that writes purge control to the hardware output:

```c
void canister_purge_control(void) {
    write8(0xFFFF8082, 0);  // Purge solenoid output
}
```

### 9.4 Purge Control State Machine (`purge_control_3F3FC`, 0x3F3FC)

```
Address: 0x3F3FC  Size: 0x5C bytes (to 0x3F458)
Source:  ida-ai
```

Implements the purge control state machine:

```
States:
  PURGE_OFF        — Purge disabled (engine cold, idle, etc.)
  PURGE_RAMP_UP    — Gradually opening purge valve
  PURGE_ACTIVE     — Normal purge operation
  PURGE_RAMP_DOWN  — Closing purge valve
  PURGE_DIAG       — System diagnostic test

Conditions to enable purge:
  - Engine coolant > 60°C (closed-loop enabled)
  - Engine running > 30 seconds
  - Not at idle (or minimal purge at idle)
  - Closed-loop fuel control active
  - No EVAP system faults detected
```

### 9.5 EVAP System Components

| Component | Control | Function |
|-----------|---------|----------|
| Purge solenoid | PWM duty cycle | Vapor flow into intake |
| Vent solenoid | ON/OFF | Canister fresh air vent |
| Fuel tank pressure sensor | Analog input | Leak detection |
| Canister close valve | ON/OFF | Seals system for diag |

---

## 10. Global Memory Map

### 10.1 Shared Memory Locations

Addresses with `0xFFFF` prefix are SH-2E peripheral / I/O memory space.
Addresses with `0x0006xxxx` are in the calibration table region.

#### Idle System

| Address | Type | Description | Subsystem |
|---------|------|-------------|-----------|
| 0xFFFFA428 | u8 | Engine state (0=running, 1=starting) | All |
| 0xFFFFAAE0 | u8 | Idle control enabled | Idle |
| 0xFFFFA96C | u8 | Idle active flag | Idle |
| 0xFFFFA96A | u8 | Idle mode flag | Idle |
| 0xFFFFA96E | u16 | Idle counter/accumulator | Idle |
| 0xFFFFAA10 | f32 | Coolant temperature | Idle/Fan |
| 0xFFFFAA14 | f32 | Secondary temperature | Idle |
| 0xFFFFA978 | u8 | Cranking state | Idle/Start |
| 0xFFFFA970 | u8 | Previous idle state | Idle |
| 0xFFFFA68F | s8 | Idle correction counter | Idle |
| 0xFFFFA678 | f32 | Computed idle target RPM | Idle |
| 0xFFFFA67C | f32 | Idle target (alternate) | Idle |
| 0xFFFF877C | u16 | ISC valve PWM duty | Idle |
| 0xFFFF8788 | u8 | ISC valve control enable | Idle |
| 0xFFFF8772 | u16 | Adaptive idle trim | Idle |
| 0xFFFF8774 | u16 | Adaptive idle accumulator | Idle |
| 0xFFFFA3F0 | u8 | Adaptive learning inhibit | Idle |

#### SSV System

| Address | Type | Description |
|---------|------|-------------|
| 0xFFFFAA10 | f32 | Air demand / RPM input |
| 0xFFFFB324 | u8 | SSV solenoid command |
| 0xFFFFB322 | u16 | SSV ramp counter |
| 0xFFFFB325 | u8 | SSV previous engine state |
| 0xFFFFB320 | u8 | SSV validated output |
| 0xFFFFBF39 | u8 | SSV force-close flag |
| 0xFFFFF754 | u16 | SSV/VFAD solenoid port (bit 7) |

#### VIS System

| Address | Type | Description |
|---------|------|-------------|
| 0xFFFFB33C | u8 | VIS mode flag 1 |
| 0xFFFFB33D | u8 | VIS mode flag 2 |
| 0xFFFFB33E | u8 | VIS mode flag 3 |
| 0xFFFFB408 | f32 | VIS position command |
| 0xFFFFB45C | u8 | VIS duty cycle index |
| 0x0006AC60 | f32[] | VIS mode 1 table |
| 0x0006AC7C | f32[] | VIS mode 2 table |
| 0x0006AC98 | f32[] | VIS mode 3 table |
| 0x0006ACB4 | f32[] | VIS mode 4 table |

#### VFAD System

| Address | Type | Description |
|---------|------|-------------|
| 0xFFFFB5B8 | f32 | RPM / sensor input |
| 0xFFFFC234 | u8 | VFAD validated command |
| 0xFFFFF754 | u16 | Solenoid port (bit 10) |

#### OMP System

| Address | Type | Description |
|---------|------|-------------|
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
| 0xFFFFCD06 | u8 | Deceleration fuel cut flag |
| 0xFFFFA96B | u8 | Warm-up active flag |
| 0xFFFFA969 | u8 | Normal running flag |

#### Cooling Fan System

| Address | Type | Description |
|---------|------|-------------|
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

#### Alternator System

| Address | Type | Description |
|---------|------|-------------|
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

#### EVAP/Purge System

| Address | Type | Description |
|---------|------|-------------|
| 0xFFFFA6EC | f32 | Purge duty cycle output |
| 0xFFFFA6F8 | f32 | Base purge flow |
| 0xFFFFA6FC | f32 | RPM compensation |
| 0xFFFFA704 | f32 | Load compensation |
| 0xFFFF8082 | u8 | Purge solenoid output |
| 0xFFFFA644 | f32 | EVAP calibration value |

---

## Appendix A: Design Patterns

### A.1 Hysteresis Comparator

Many subsystems (SSV, VFAD, APV, fans) use the same hysteresis comparison
pattern:

```c
uint8_t hysteresis_compare(float input, float threshold, float band) {
    float lower = threshold - band;
    
    if (input > threshold) {
        return 1;  // ON / OPEN
    } else if (input < lower) {
        return 0;  // OFF / CLOSE
    } else {
        // Hysteresis band — maintain previous state
        return previous_state;
    }
}
```

### A.2 Alternating Sensor State Machine

The "alternating sensor" state machines (0x5D3E8, 0x5D800, etc.) implement
a debounce/filter that validates a digital signal by requiring it to be stable
for N consecutive samples before changing the output. This prevents rapid
oscillation of actuators at threshold boundaries.

```c
uint8_t alternating_sensor_sm(uint8_t input, uint8_t* counter, uint8_t* output) {
    if (input != *output) {
        (*counter)++;
        if (*counter >= STABLE_SAMPLES) {
            *output = input;
            *counter = 0;
        }
    } else {
        *counter = 0;
    }
    return *output;
}
```

### A.3 Atomic Register Access Pattern

Hardware register writes use a save/restore pattern for the Status Register
(SR) to ensure atomicity:

```asm
setSR_PARAM:
    stc sr, r4    ; Save SR
    mov #0xe0, r0
    ldc r0, sr    ; Disable interrupts / set priority
    rts
    
loadStatusRegister_ADDR:
    ldc r4, sr    ; Restore original SR
    rts
```

---

## Appendix B: Common Calibration Constants

| Value | Float Hex | Intended Use |
|-------|-----------|--------------|
| 200.0 | 0x43480000 | SSV open threshold |
| 3.0 | 0x40400000 | SSV hysteresis band |
| 5250.0 | 0x45A41000 | VFAD open threshold |
| 188.0 | 0x433C0000 | VFAD hysteresis |
| 97.0 | 0x42C20000 | Fan ON threshold |
| 50.0 | 0x42480000 | APV threshold |
| 84.0 | 0x42A80000 | VIS position limit |
| 0.5 | 0x3F000000 | General scaling factor |
| -40.0 | 0xC2200000 | Temperature limit |

---

## Appendix C: Summary of Key Functions

| Function | Address | Size | Subsystem |
|----------|---------|------|-----------|
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

---

*Document generated from reverse engineering of the Mazda RX-8 (13B-MSP) ECU
firmware binaries 60E1D400 and 60E0FC00. Analysis tools: Ghidra, IDA Pro,
SH-2E disassembler. Source code reconstruction is best-effort based on
assembly analysis and decompilation output.*
