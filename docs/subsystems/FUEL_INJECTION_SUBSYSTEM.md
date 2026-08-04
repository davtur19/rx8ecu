# Fuel Injection Control Subsystem — RX-8 PCM (60E1D400)

**ROM:** 60E1D400 (N3J1EM, 6-Port MT, 2004–08)  
**Cross-reference:** 60E0FC00 (USDM), 60E1D400 (baseline)  
**Functions:** ~93 fuel/injection-related functions  
**Last updated:** 2026-07-31

---

## Table of Contents

1. [Overall Fueling Architecture](#1-overall-fueling-architecture)
2. [Fuel Mass Calculation Strategy](#2-fuel-mass-calculation-strategy)
3. [Correction Hierarchy](#3-correction-hierarchy)
4. [Injector Flow Rate and Latency Calibration](#4-injector-flow-rate-and-latency-calibration)
5. [Fuel Cut Logic](#5-fuel-cut-logic)
6. [Per-Rotor Fueling](#6-per-rotor-fueling)
7. [Fuel Pump Control](#7-fuel-pump-control)
8. [Key Calibration Tables](#8-key-calibration-tables)
9. [Complete Fuel Function Catalog](#9-complete-fuel-function-catalog)
10. [C Code for Key Functions](#10-c-code-for-key-functions)
11. [Test Strategy](#11-test-strategy)
12. [Open Questions](#12-open-questions)

---

## 1. Overall Fueling Architecture

The RX-8 PCM uses a **speed-density** fueling strategy, with the following high-level pipeline:

```
┌─────────────────────────────────────────────────────────────────────┐
│                   FUELING CONTROL PIPELINE                          │
│                                                                     │
│  SENSORS ──► LOAD ──► BASE FUEL ──► CORRECTIONS ──► PULSE WIDTH    │
│  RPM           CALC      MASS          × 1.23          CALC         │
│  MAF/VAF                 (AFR             ┌──┬──┬──┐   (ms)         │
│  MAP                      from        ──► │WU│AC│CL├─►              │
│  TPS                      table)          │FT│FP│FL│                │
│  IAT                                       └──┴──┴──┘                │
│  CLT                                                                 │
│  O2/Lambda ─────────────────────────────────────────────────────►    │
│                                                                     │
│  Output: Injector pulse width in microseconds/timer ticks           │
│  Per: Rotor A, Rotor B (leading + trailing ports)                   │
└─────────────────────────────────────────────────────────────────────┘
```

### Pipeline Stages (in order of execution):

| Stage | Functions | Tick |
|-------|-----------|------|
| **Sensor acquisition** | MAF, MAP, TPS, IAT, CLT, O2, RPM | Pre-tick (interrupt) |
| **Load calculation** | `calc_combustion_load_factor`, `calc_combustion_efficiency_metric` | Phase 1 |
| **Main fuel corrections** | `calc_adaptive_fuel_trim`, `calc_accel_fuel_enrichment`, `calc_barometric_pressure_trim`, `calc_closed_loop_fuel_status`, `read_o2_sensor_voltage_trim` | Phase 2 |
| **Fuel cut arbitration** | `calc_decel_fuel_cut_445AA`, `fuel_cut_logic`, `fuel_enable_logic`, `arbitrateFuelCut` | Phase 2 |
| **Pulse width calc** | `fuel_injector_pulse_calc`, `calc_fuel_injection_all_rotors`, `fuel_injector_pulse_calc`, `injectorPulseSet` | Post-Phase 2 |
| **Fuel pump control** | `calc_fuel_pump_duty_trim`, `calc_fuel_pump_control_output`, `check_fuel_pump_relay_enable` | Phase 2 |
| **Output to hardware** | `injection_pulse_decoder_main`, `injector_timing_output_copy`, `injector_control_write` | End of cycle |

All functions are called **unconditionally** from `engineControlCalculateTiming` (0x14584), which runs every scheduler tick (~10ms). Conditional logic is pushed *into* each subfunction, which reads/writes global RAM directly.

---

## 2. Fuel Mass Calculation Strategy

The RX-8 uses a **speed-density** system with MAF sensor validation:

### 2.1 Air Mass Determination

```
Air Mass (g/rev) = f(MAF_sensor_voltage, RPM, IAT, barometric_pressure)
```

The MAF sensor is a hot-wire type (Mazda PN: N3H1-13-215). The calibration curve is stored in the `MAF Scaling` table at 0x6FBD8 (48-point 1D lookup, float type). This converts MAF voltage to air mass flow.

**Key sensor processing functions:**
- `maf_sensor_value` — reads and linearizes MAF sensor ADC input
- `baro_sensor_value` — barometric pressure sensor compensation
- `sensor_signal_calc_44076` — general sensor signal conditioning

### 2.2 Base Fuel Mass (Open Loop Target)

From the Equinox guide:

> Open Loop Lambda values are stored as the decimal part (ECU adds 1; defs subtract 1 for readability)

```
OpenLoop = max(OpenLoopTarget, TipInTarget * TipInBaroCorr) * CoolantTempCorr
```

The base fuel mass is derived from **Fuelling** calibration maps (1D and 2D tables indexed by load and RPM). There are multiple fuel tables selected by operating mode:

| Table | Address (60E1D400) | Type | Description |
|-------|----------------|------|-------------|
| Fuelling - Safe Mode | 0x71CD0 | 1D ×9 | Default/safe lambda target |
| Fuelling 0 | 0x71CE0 | 1D ×? | Normal operating fuel map |
| Fuelling 1 | 0x71D00 | 1D ×7 | Light load fuel target |
| Fuelling 2 - Safe Mode | 0x71D2C | 1D ×9 | Safe mode backup |
| Fuelling 3 | 0x71D5C | 1D ×9 | Medium load |
| Fuelling 4 | 0x71D84 | 1D ×7 | High load |
| Fuelling 5 | 0x71DD4 | 1D ×18 | RPM-based enrichment |
| Fuelling 6 | 0x71E30 | 1D ×18 | RPM-based enrichment 2 |
| Fuelling 7 | 0x71E8C | 1D ×18 | RPM-based enrichment 3 |
| Fuelling 8 | 0x72084 | 1D ×7 | Idle compensation |
| Fuelling 9 - Safe Mode | 0x7228C | 2D 12×8 | Safe 3D fuel map |
| Fuelling 10 - Safe Mode | 0x7238C | 2D 21×19 | Safe 3D fuel map (large) |
| Fuelling 13 - Safe Mode | 0x72584 | 2D 12×8 | Alternative safe map |
| Fuelling 14 - Safe mode | 0x72684 | 2D 21×19 | Alternative safe map |
| Fuelling 15 | 0x72864 | 2D 12×8 | Normal 3D fuel map A |
| Fuelling 16 | 0x72964 | 2D 21×19 | Normal 3D fuel map B |

**Key function:** `calcOpenLoopFuelingTarget` (0x1FD8E, 578 bytes) appears to be the main open-loop target calculation, selecting among these tables based on operating mode and applying the `CoolantTempCorr` from the equinox formula.

### 2.3 Lambda to Injector Pulse Width Conversion

The ECU converts the commanded lambda / fuel mass to an injector pulse width using:

```
InjectorPulse_ms = (FuelMass_g * StoichAFR) / (InjectorFlow_cc/min * Latency_correction)
```

This involves:
1. Calculating the required fuel mass per cycle: `FuelMass = AirMass / CommandedLambda / StoichAFR`
2. Converting to injector open time: `PulseWidth = FuelMass / (InjectorFlowRate * NumInjectors) * 60000`
3. Adding injector dead time / latency
4. Converting to timer ticks (× 65536 or ÷ 16 depending on stage)

**Key functions:**
- `fuel_injector_pulse_calc` (0x10620, 708 bytes) — main pulse width calculator
- `injector_pulse_width_calc` (0xB2E4, 198 bytes) — lower-level pulse computation
- `injector_pulse_width_calculator` (0xAEFA, 4 bytes — trampoline)
- `fuel_pulse_width_calc_saturated` (0xB4D8, 100 bytes) — saturated variant

---

## 3. Correction Hierarchy

The fueling corrections are applied in a specific order, with each correction multiplying or adding to the base fuel mass:

### Correction Pipeline (applied in order)

```
Base Fuel Mass (from OpenLoopTarget table)
  │
  ├── 1. Warm-up enrichment (calc_engine_temp_fuel_trim @ 0x1437C)
  │      Based on coolant temperature. Higher enrichment when cold,
  │      tapers off as engine warms to operating temperature.
  │      Table: Fuelling temp correction (e.g., 0x71D00, 0x71D84)
  │
  ├── 2. Cold start enrichment (calc_cold_start_fuel_enrichment @ 0x142E8)
  │      Extra fuel during initial start-up, decays with time/temperature.
  │      Functions: after_start_fuel_enrichment_task (0x1A95C)
  │                setStartupInjectorPwMult (0x3126E)
  │                calcInjectorCrankingTime (0x31088)
  │                getCrankingInjectorPulseTime (0x310D4)
  │
  ├── 3. Acceleration enrichment (calc_accel_fuel_enrichment @ 0x138CC)
  │      Transient enrichment when throttle opens rapidly (tip-in).
  │      Based on TPS rate-of-change and MAP/RPM.
  │      Prevents lean spike during acceleration.
  │
  ├── 4. Closed-loop / O2 feedback (calc_closed_loop_fuel_status @ 0x141B8)
  │      Active when O2 sensor is warm and engine is in closed-loop mode.
  │      Reads: read_o2_sensor_voltage_trim (0x1412A)
  │      Targets stoichiometric (lambda = 1.0) during cruise.
  │
  ├── 5. Adaptive fuel trim (calc_adaptive_fuel_trim @ 0x1379C)
  │      Long-term correction learned from O2 feedback.
  │      Two 1D tables (0x6A868, 0x6A87C) with 9 breakpoints.
  │      Limited to [-2.8%, +0.7%], integrates with gain ~0.009766.
  │      Enabled when: RPM > 1500 AND coolant warm (closed loop).
  │
  ├── 6. Barometric pressure trim (calc_barometric_pressure_trim @ 0x13F68)
  │      Altitude compensation. Reduces fuel at high altitude
  │      (lower air density). Uses barometric pressure sensor.
  │
  ├── 7. WOT enrichment (calc_wot_fuel_enrichment @ 0x14220)
  │      Open-loop enrichment at wide-open throttle for power.
  │      Richer mixture (lambda < 1.0) for maximum power / cooling.
  │      Tables: Fuelling 15, Fuelling 16 (2D, RPM × load).
  │
  ├── 8. Catalyst warm-up enrichment
  │      From equinox: CatWarmup = (LoadBasedEnrich * LoadComp) + EngineSpeedEnrich
  │      Active during cold start to heat the catalytic converter quickly.
  │      Adds enrichment on top of normal open-loop target.
  │
  ├── 9. Fuel pressure correction (add_fuel_pressure_correction @ 0x126CA)
  │      Compensates for actual fuel rail pressure vs. reference.
  │      If pressure is low → increase pulse width.
  │      Uses: fuel_pressure_calc_4409E (0x4409E), read_fuel_pressure_feedback_status (0x1408C)
  │
  └── 10. Fuel cut (applied at end — overrides everything)
        calc_decel_fuel_cut_445AA (0x445AA)
        fuel_cut_logic (0x4490A)
        rpm_limiter_fuel_cutoff (0xC59E)
        calculateRevLimiterFuelCut (0xF192)
        arbitrateFuelCut (0xE56C)
```

### Correction Accumulation Model

Based on the Equinox guide formula and decompilation analysis:

```c
// Simplified correction accumulation
float computeFinalPulseWidth(void) {
    float base_afr = getBaseOpenLoopTarget();          // from fuel table
    float tip_in = getTipInEnrichment();               // accel enrichment
    float baro_corr = getBarometricPressureCorr();
    float clt_corr = getCoolantTempCorr();
    
    // Open loop target (from equinox guide)
    float open_loop = max(base_afr, tip_in * baro_corr) * clt_corr;
    
    // Add cat warmup enrichment
    float cat_warmup = getLoadBasedEnrich() * getLoadComp() + getEngineSpeedEnrich();
    
    // Apply adaptive trim
    float trim = getAdaptiveFuelTrim();                 // [-2.8%, +0.7%]
    
    // Apply closed-loop correction
    float cl_correction = getClosedLoopCorrection();    // ±~15%
    
    // Final commanded lambda
    float commanded_lambda = (open_loop + cat_warmup) * (1.0 + trim + cl_correction);
    
    // Convert to injector pulse width
    float air_mass_per_cycle = getAirMassPerCycle();
    float fuel_mass = air_mass_per_cycle / (commanded_lambda * STOICH_AFR);
    float pulse_ms = fuel_mass / injector_flow_rate * 60000.0f + injector_latency;
    
    return pulse_ms;
}
```

---

## 4. Injector Flow Rate and Latency Calibration

### 4.1 Injector Sizing

The RX-8 uses two-stage injection (primary + secondary injectors per rotor):

| Parameter | Address (60E1D400) | Units |
|-----------|----------------|-------|
| Primary Injector Size | 0x0783A0 | cc/min (or g/sec) |
| Secondary Injector Size | 0x0783A8 | cc/min |
| Secondary Injector Size #2 | 0x0783B0 | cc/min |

The stock RX-8 injectors are:
- **Primary:** 420 cc/min @ 3.9 bar (DENSO 195500-4450)
- **Secondary:** 420 cc/min @ 3.9 bar (DENSO 195500-4450)

### 4.2 Injector Latency (Dead Time)

Injector latency (dead time) is the time required for the injector to open after the solenoid is energized. It varies with battery voltage.

**Calibration tables:**
| Table | Address (60E1D400) | Type | Description |
|-------|----------------|------|-------------|
| Injector Latency Primary | 0x780F4 | 2D 17×9 | Primary injector dead time vs. voltage |
| Injector Latency Secondary | 0x77F58 | 2D 17×9 | Secondary injector dead time vs. voltage |

**Key functions:**
- `setFuelInjectorLatency` (0x86F8, 16 bytes) — writes latency value to registers (3 channels, paired primary/shadow writes)
- `getFuelInectorLatencyCals` (0x30DE8, 146 bytes) — loads latency calibration from tables
- `getInjectorTempBasedMultiplierLookups` (0x30BCA, 60 bytes) — temperature-based latency adjustment

### 4.3 Injector Pulse Calculation Flow

```
                  ┌──────────────────┐
                  │  Engine Speed    │
                  │  Load (g/rev)    │
                  │  Target Lambda   │
                  └────────┬─────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │  Base Fuel Mass  │
                  │  = air / lambda  │
                  └────────┬─────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │  Injector Pulse  │
                  │  = fuel / flow   │
                  └────────┬─────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │  + Injector      │
                  │    Latency (V)   │
                  └────────┬─────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │  Convert to      │
                  │  Timer Ticks     │
                  │  (× 65536)       │
                  └────────┬─────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │  Saturation      │
                  │  & Limit Check   │
                  └────────┬─────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │  Write to        │
                  │  Hardware OC Reg │
                  └──────────────────┘
```

### 4.4 Hardware Output Register Layout

The injector control registers are at 0xFFFFA004 (injector state array, 12 bytes per injector × 6 injectors = 72 bytes) and 0xFFFFA094 (injector calibration map, 32 bytes per injector).

The hardware timer/output-compare registers are at 0xF440 (16-bit) and 0xF66C (injector enable bits).

---

## 5. Fuel Cut Logic

Fuel cut is a critical safety and economy feature. The RX-8 ECU implements multiple independent fuel cut conditions:

### 5.1 Fuel Cut Sources

| Source | Function | Address | Condition |
|--------|----------|---------|-----------|
| **Throttle lift (decel)** | `calc_decel_fuel_cut_445AA` | 0x445AA | Throttle closed, RPM above threshold |
| **Rev limit** | `calculateRevLimiterFuelCut` | 0xF192 | RPM exceeds hard limit |
| **Rev limit init** | `revLimitFuelCutInit` | 0xF0FC | Initialize at power-on |
| **RPM limiter** | `rpm_limiter_fuel_cutoff` | 0xC59E | Soft limit (fuel cut per rotor) |
| **Cold rev limit** | `calculateRevLimiterFuelCut` (w/ cold threshold) | — | Lower RPM limit when cold |
| **DSC/TC request** | `arbitrateDSCFuelCut` | 0x2D994 | Stability control torque reduction |
| **Diagnostic** | `calcDiagFuelInjectorTrim` | 0x4C6C4 | Diagnostic injector cut |
| **Fault conditions** | `arbitrateFuelCut` | 0xE56C | 13 fault condition flags |

### 5.2 Fuel Cut Arbitration

The function `arbitrateFuelCut` (0xE56C) OR's together multiple fuel cut request flags and produces a 2-bit result:
- **Bit 0 (0x01):** Primary fuel cut — normal condition (throttle lift, rev limit)
- **Bit 1 (0x02):** Secondary protection — fault/error conditions

The result is stored at `0xA430`, which is read by:
- `getFuelCutRequestStatus` (0xFF08) — returns fuel cut status word
- `calc_fuel_injection_all_rotors` (0x13D3C) — disables injection when cut is active
- `fuel_cut_logic_4490A` (0x4490A) — applies fuel cut with hysteresis

### 5.3 Rev Limit Strategy

The rev limiter uses a **fuel-cut** strategy (not ignition cut):

1. **Soft limit:** Begins cutting fuel at ~9000 RPM (calibratable via `Rev Limit` table at 0x6D54C)
2. **Hard limit:** Complete fuel cut at ~9500 RPM
3. **Cold limit:** Lower limit (~4000 RPM) when coolant temp is below threshold (`Cold Rev Limit Threshold` at 0x6D53C, `Cold Rev Limit` at 0x6D544)

The RPM limiter fuel cut function `rpm_limiter_fuel_cutoff` (0xC59E) implements a progressive cut—one rotor at a time—to allow smooth engagement.

### 5.4 Deceleration Fuel Cut

`calc_decel_fuel_cut_445AA` (0x445AA) implements over-run fuel cut:

```
Conditions for fuel cut on throttle lift:
1. Throttle position < closed threshold (~0.01 V / angle)
2. Engine speed > minimum threshold (calibratable)
3. Not in override mode (DSC torque request, etc.)
4. Feature is enabled (calibration: 0x7B3DC = 0x01)

Hysteresis:
- Uses a saturating accumulator (addSaturate8Bit) to prevent rapid on/off cycling
- Fuel cut remains active until RPM drops below re-enable threshold
```

---

## 6. Per-Rotor Fueling

The RX-8 uses a 2-rotor (13B-MSP Renesis) engine, requiring per-rotor fuel delivery.

### 6.1 Rotor Fuel Dispatch

```
fuel_calc_entry (0x9528, 12 bytes — trampoline)
  └── fuel_calc_per_rotor (0x9534, 262 bytes)
        ├── rotor_fuel_calc_dispatcher (0xB57A, 268 bytes)
        │     ├── calc_fuel_correction_all_modes (0x12C8C, 614 bytes)
        │     ├── calc_fuel_trim_correction_map (0x136F0, 140 bytes)
        │     └── dual_channel_fuel_computation (0x14BAC, 88 bytes)
        │
        ├── fuel_injector_pulse_calc (0x10620, 708 bytes)
        │     └── Per-injector PWM calculation for all 6 injectors (3/rotor × 2 rotors)
        │
        └── calc_fuel_injection_all_rotors (0x13D3C, 236 bytes)
              ├── Applies fuel cut flags
              ├── Per-rotor dispatch via compare_select_two_float_values
              ├── calc_fuel_pump_control_output (0x13E6C)
              └── calc_fuel_pressure_load_compensation (0x13EE6)
```

### 6.2 Per-Rotor Trim Functions

Each rotor (A and B) has its own fuel trim calculation:

| Function | Address | Purpose |
|----------|---------|---------|
| `calc_fuel_trim_correction_cyl_A` | 0x14722 | Rotor A fuel trim |
| `calc_fuel_trim_correction_cyl_B` | 0x14742 | Rotor B fuel trim |
| `calc_cyl_B_fuel_pulse_width` | 0x14464 | Rotor B pulse width |

### 6.3 Injection Timing (Per Rotor)

The injection timing (when in the cycle fuel is delivered) is computed per-rotor:

| Function | Address | Purpose |
|----------|---------|---------|
| `injectionTimingMaybe` | 0xE726 | Injection timing angle computation |
| `injection_timing_calculator` | 0xFCE6 | Main timing calculator |
| `injection_timing_calc_3BA3E` | 0x3BA3E | Timing calculation variant |
| `injection_timing_calc_409CE` | 0x409C6 | Timing for specific mode |
| `injection_timing_decrement_44A12` | 0x44A12 | Timing countdown/advance |

### 6.4 Hardware Output

The final injector pulse is written to hardware output-compare registers:

| Function | Address | Purpose |
|----------|---------|---------|
| `injectorPulseSet` | 0x8A68 | Write computed pulse to HW register |
| `injector_control_write_2CCBC` | 0x2CCBC | Direct register write |
| `injection_pulse_decoder_main` | 0xFA90 | Decodes pulse timing for output |
| `injector_timing_output_copy` | 0xBB28 | Copies timing to output buffer |
| `injector_timing_scheduler_229C0` | 0x229C0 | Schedules injector events |

### 6.5 Cranking vs. Running Injection

During cranking, a separate set of functions handles fuel delivery:

| Function | Address | Purpose |
|----------|---------|---------|
| `calcInjectorCrankingTime` | 0x31088 | Base cranking pulse width |
| `getCrankingInjectorPulseTime` | 0x310D4 | Temperature-compensated cranking pulse |
| `setStartupInjectorPwMult` | 0x3126E | Startup multiplier (deflood-aware) |
| `getDiagnosticFuelPulseCranking` | 0x310FC | Diagnostic cranking pulse |
| `crank_gated_fuel_pressure_proc` | 0xE6DC | Cranking fuel pressure |
| `crank_inject_count_44988` | 0x44988 | Cranking injector event count |

---

## 7. Fuel Pump Control

### 7.1 Fuel Pump PWM Control

The fuel pump speed is modulated via PWM for noise reduction and pressure regulation:

| Function | Address | Purpose |
|----------|---------|---------|
| `calc_fuel_pump_duty_trim` | 0x135F6 | Pump duty cycle trim based on mode |
| `calc_fuel_pump_control_output` | 0x13E6C | Main pump output calculation |
| `calc_fuel_pump_pwm_output` | 0x11EEA | PWM duty generation |
| `fuel_pump_speed_controller` | 0x1B5A8 | Speed control loop |
| `fuel_pump_rpm_scale_262FA` | 0x262FA | RPM-based scaling |
| `pump_control_output_2602C` | 0x2602C | Output stage |

### 7.2 Fuel Pressure Regulation

| Function | Address | Purpose |
|----------|---------|---------|
| `fuel_pressure_calc` | 0x15D82 | Main fuel pressure calculation |
| `fuel_pressure_calc_with_interpolation` | 0xE6EC | Interpolated pressure calc |
| `calc_fuel_pressure_feedback` | 0x11BC0 | Pressure feedback PID |
| `calc_fuel_pressure_error_integral` | 0x140A4 | Integral term for pressure control |
| `calc_fuel_pressure_load_compensation` | 0x13EE6 | Load-based pressure target |
| `fuel_rail_pressure_state_machine` | 0x197B8 | Pressure control state machine |
| `fuel_rail_pressure_limiter_21B40` | 0x21B40 | Over-pressure protection |
| `read_fuel_pressure_feedback_status` | 0x1408C | Pressure sensor status |

### 7.3 Fuel Pump Priming and Safety

| Function | Address | Purpose |
|----------|---------|---------|
| `calc_fuel_pump_priming` | 0x14962 | Prime on ignition-on |
| `pump_prime_watchdog_2611E` | 0x2611E | Prime timeout/safety |
| `pump_prime_wrapper_26244` | 0x26244 | Prime sequence wrapper |
| `pump_ready_flag_26208` | 0x26208 | Ready flag |
| `check_fuel_pump_relay_enable` | 0x2CC1C | Relay control |
| `fuel_pump_control_0x17510` | 0x17510 | Full pump control state machine |

---

## 8. Key Calibration Tables

### 8.1 Fueling Target Tables (Open Loop)

| Address (60E1D400) | Name | Dimensions | Type | Scale | Description |
|----------------|------|------------|------|-------|-------------|
| 0x71CD0 | Fuelling - Safe Mode | 1D ×9 | u8 | 0.007812 | Default lambda when in safe mode |
| 0x71D00 | Fuelling 1 | 1D ×7 | u8 | 0.007812 | Light load fueling |
| 0x71D2C | Fuelling 2 - Safe Mode | 1D ×9 | u8 | 0.007812 | Safe mode backup |
| 0x71D5C | Fuelling 3 | 1D ×9 | u8 | 0.007812 | Medium load fueling |
| 0x71D84 | Fuelling 4 | 1D ×7 | u8 | 0.007812 | High load fueling |
| 0x71DD4 | Fuelling 5 | 1D ×18 | u8 | 0.003906 | RPM-based enrichment A |
| 0x71E30 | Fuelling 6 | 1D ×18 | u8 | 0.003906 | RPM-based enrichment B |
| 0x71E8C | Fuelling 7 | 1D ×18 | u8 | 0.003906 | RPM-based enrichment C |
| 0x72084 | Fuelling 8 | 1D ×7 | u8 | 0.003906 | Idle fuel trim |
| 0x7228C | Fuelling 9 - Safe Mode | 2D 12×8 | u8 | 0.003906 | Safe mode 3D map A |
| 0x7238C | Fuelling 10 - Safe Mode | 2D 21×19 | u8 | 0.003906 | Safe mode 3D map B |
| 0x72864 | Fuelling 15 | 2D 12×8 | u8 | 0.003906 | Normal 3D fuel map A |
| 0x72964 | Fuelling 16 | 2D 21×19 | u8 | 0.003906 | Normal 3D fuel map B |

### 8.2 Adaptive Trim Tables

| Address (60E1D400) | Name | Dimensions | Type | Scale | Description |
|----------------|------|------------|------|-------|-------------|
| 0x72CAC | Table 2D - 106_ | 1D ×9 | u8 | 0.25 / -32 offset | Primary adaptive trim |
| 0x72CDC | Table 2D - 107_ | 1D ×9 | u8 | 0.25 / -32 offset | Secondary adaptive trim |

### 8.3 Injector Calibration

| Address (60E1D400) | Name | Dimensions | Type | Scale | Description |
|----------------|------|------------|------|-------|-------------|
| 0x0783A0 | Primary Injector Size | Scalar | u32 | — | Flow rate cc/min |
| 0x0783A8 | Secondary Injector Size | Scalar | u32 | — | Flow rate cc/min |
| 0x0783B0 | Secondary Injector Size #2 | Scalar | u32 | — | Flow rate cc/min |
| 0x780F4 | Injector Latency Primary | 2D 17×9 | u16 | 1 | Dead time vs. voltage |
| 0x77F58 | Injector Latency Secondary | 2D 17×9 | u16 | 1 | Dead time vs. voltage |
| 0x6FD38 | Injector Barometric Pressure Compensation | 1D ×4 | f32 | — | Altitude correction |

### 8.4 Warm-up / Enrichment Tables

| Address (60E1D400) | Name | Description |
|----------------|------|-------------|
| 0x72C20 | Table 2D - 104_ | Temperature correction A |
| 0x72C50 | Table 2D - 105_ | Temperature correction B |
| 0x72E84 | Table 2D - 112_ | Warm-up enrichment A |
| 0x72EB4 | Table 2D - 113_ | Warm-up enrichment B |

### 8.5 Lambda / AFR Related

| Address (60E1D400) | Name | Description |
|----------------|------|-------------|
| 0x6FD74 | Lambda Sensor Scaling | O2 sensor linearization |
| 0x7AF48 | Injection Angle Related AFR Input | AFR for injection timing |
| 0x7AF74 | Unknown Lambda Input | Secondary lambda input |

### 8.6 Rev Limit / Fuel Cut

| Address (60E1D400) | Name | Description |
|----------------|------|-------------|
| 0x6D54C | Rev Limit | Hard RPM limit |
| 0x6D544 | Cold Rev Limit | Cold engine RPM limit |
| 0x6D53C | Cold Rev Limit Threshold | Coolant temp threshold °C |

---

## 9. Complete Fuel Function Catalog

The 93 fuel-related functions, organized by subsystem:

### Main Pipeline (5)

| Address | Name | Size | Description |
|---------|------|------|-------------|
| 0x09528 | fuel_calc_entry | 12 | Entry trampoline |
| 0x09534 | fuel_calc_per_rotor | 262 | Per-rotor fuel dispatch |
| 0x0B57A | rotor_fuel_calc_dispatcher | 268 | Rotor calc dispatcher |
| 0x0B7D2 | fuel_calc_task_dispatcher | 176 | Task-level dispatcher |
| 0x22094 | main_fuel_control_pipeline_22094 | 180 | Main pipeline orchestrator |

### Base Fuel Calculation (8)

| Address | Name | Size | Description |
|---------|------|------|-------------|
| 0x1FD8E | calcOpenLoopFuelingTarget | 558 | Open loop target calculation |
| 0x12C8C | calc_fuel_correction_all_modes | 614 | Multi-mode correction calc |
| 0x0B2E4 | injector_pulse_width_calc | 198 | Base pulse width calc |
| 0x0D3DC | fuel_air_bilinear_interpolation | 106 | Fuel-air interpolation |
| 0x0B4D8 | fuel_pulse_width_calc_saturated | 100 | Saturated pulse calc |
| 0x0B3AA | atu_injector_enable_update | 40 | Injector enable update |
| 0x3BAD4 | base_fuel_calc_3BAD4 | 60 | Base fuel calc stub |
| 0x3B8B0 | fuel_calc_processor_3b8b0 | 398 | Fuel calc processor |

### Fuel Trims / Corrections (17)

| Address | Name | Size | Description |
|---------|------|------|-------------|
| 0x1379C | calc_adaptive_fuel_trim | 228 | Long-term adaptive trim |
| 0x138CC | calc_accel_fuel_enrichment | 228 | Acceleration enrichment |
| 0x13F68 | calc_barometric_pressure_trim | ? | Barometric pressure trim |
| 0x14220 | calc_wot_fuel_enrichment | 118 | WOT enrichment |
| 0x142E8 | calc_cold_start_fuel_enrichment | 118 | Cold start enrichment |
| 0x1437C | calc_engine_temp_fuel_trim | 82 | Coolant temp fuel trim |
| 0x14496 | calc_deadband_fuel_trim | 50 | Deadband trim |
| 0x136F0 | calc_fuel_trim_correction_map | 140 | Trim correction map |
| 0x14722 | calc_fuel_trim_correction_cyl_A | 32 | Rotor A trim |
| 0x14742 | calc_fuel_trim_correction_cyl_B | 24 | Rotor B trim |
| 0x16668 | secondary_fuel_trimmer | 118 | Secondary trim circuit |
| 0x145C | multi_table_fuel_compensation | 228 | Multi-table compensation |
| 0x15C1C | channel_idle_fuel_controller | 208 | Idle fuel controller |
| 0x1DB78 | fuel_enrichment_control_1DB78 | 490 | Enrichment control |
| 0x1E5F8 | fuel_trim_update_control_1E5F8 | 190 | Trim update control |
| 0x1F844 | fuel_trim_correction_1F844 | 106 | Trim correction |
| 0x426A6 | fuel_calculation_callback_426A6 | 240 | Calculation callback |

### Closed-Loop / O2 Feedback (6)

| Address | Name | Size | Description |
|---------|------|------|-------------|
| 0x141B8 | calc_closed_loop_fuel_status | 104 | Closed loop status |
| 0x1412A | read_o2_sensor_voltage_trim | 142 | O2 voltage trim |
| 0x1913C | air_fuel_ratio_feedback_calc | 84 | AFR feedback calc |
| 0x21A18 | air_fuel_ratio_check_21A18 | 76 | AFR check |
| 0x230D0 | air_fuel_ratio_check_230D0 | 224 | AFR check 2 |
| 0x1A95C | after_start_fuel_enrichment_task | 68 | Post-start enrichment |

### Cranking / Startup (11)

| Address | Name | Size | Description |
|---------|------|------|-------------|
| 0x31088 | calcInjectorCrankingTime | 76 | Cranking pulse width |
| 0x310D4 | getCrankingInjectorPulseTime | 40 | Get cranking pulse |
| 0x30D18 | injectorPulseTimeArbitrate_crankAddTimer | 164 | Crank timing arbitration |
| 0x3126E | setStartupInjectorPwMult | 36 | Startup multiplier |
| 0x30DE8 | getFuelInectorLatencyCals | 146 | Latency cal lookup |
| 0x30BCA | getInjectorTempBasedMultiplierLookups | 60 | Temp multiplier lookup |
| 0x310FC | getDiagnosticFuelPulseCranking | 276 | Diagnostic cranking pulse |
| 0x314E8 | diagCrankingInjectorPulseAdder | 50 | Diagnostic adder |
| 0xE6DC | crank_gated_fuel_pressure_proc | 16 | Cranking fuel pressure |
| 0xE6EC | fuel_pressure_calc_with_interpolation | 58 | Crank pressure calc |
| 0x44988 | crank_inject_count_44988 | 50 | Crank injector counting |

### Fuel Cut / Limits (18)

| Address | Name | Size | Description |
|---------|------|------|-------------|
| 0xE56C | arbitrateFuelCut | 358 | Fuel cut arbitration |
| 0xEBA8 | throttlePlateSomethingFuelCut | 1146 | Throttle plate fuel cut |
| 0xF05C | fuelCutArbitration_weirdBlock | 134 | Arbitration block |
| 0xF0FC | revLimitFuelCutInit | 30 | Rev limit init |
| 0xF192 | calculateRevLimiterFuelCut | 454 | Rev limit fuel cut |
| 0x445AA | calc_decel_fuel_cut_445AA | 234 | Throttle lift fuel cut |
| 0x4490A | fuel_cut_logic_4490A | 126 | Fuel cut logic |
| 0x44AB2 | fuel_enable_logic_44AB2 | 66 | Fuel enable logic |
| 0x3BE5C | fuel_cut_logic_3BF70 | 352 | Fuel cut logic alt |
| 0x39C0A | fuel_cut_control_39C0A | 44 | Fuel cut control |
| 0x44370 | fuel_correction_update_44370 | 52 | Correction update |
| 0x26898 | fuel_cutoff_check_26898 | 44 | Cutoff check |
| 0x268C4 | fuel_transient_limit_268C4 | 56 | Transient limit |
| 0x4561E | fuel_flow_limiter_4561E | 282 | Flow limiter |
| 0x45B6C | fuel_flow_limiter_45B6C | 72 | Flow limiter alt |
| 0x47A2E | rpm_limiter_fuel_cut_47A2E | 150 | RPM limiter cut |
| 0xC59E | rpm_limiter_fuel_cutoff | 280 | RPM limiter cutoff |
| 0x47DBA | fuelCutSomethingSomething | 312 | Unidentified cut logic |

### Fuel Pump & Pressure (27)

| Address | Name | Size | Description |
|---------|------|------|-------------|
| 0x135F6 | calc_fuel_pump_duty_trim | 92 | Pump duty cycle trim |
| 0x13E6C | calc_fuel_pump_control_output | 102 | Pump control output |
| 0x13EE6 | calc_fuel_pressure_load_compensation | 56 | Pressure load comp |
| 0x11EEA | calc_fuel_pump_pwm_output | 48 | PWM output |
| 0x14962 | calc_fuel_pump_priming | 42 | Priming |
| 0x15D82 | fuel_pressure_calc | 1642 | Main pressure calc |
| 0x11BC0 | calc_fuel_pressure_feedback | 158 | Pressure feedback |
| 0x10444 | calc_fuel_pressure_div | 72 | Pressure division |
| 0x126CA | add_fuel_pressure_correction | 16 | Pressure correction adder |
| 0x1408C | read_fuel_pressure_feedback_status | 24 | Pressure feedback status |
| 0x140A4 | calc_fuel_pressure_error_integral | 134 | Pressure error integrator |
| 0x197B8 | fuel_rail_pressure_state_machine | 222 | Pressure state machine |
| 0x23A38 | fuel_pressure_control_23A38 | 298 | Pressure control |
| 0x4409E | fuel_pressure_calc_4409E | 64 | Pressure calc snippet |
| 0x40974 | fuel_pressure_control_40974 | 82 | Pressure control snippet |
| 0x21B40 | fuel_rail_pressure_limiter_21B40 | 100 | Pressure limiter |
| 0x17510 | fuel_pump_control_0x17510 | 496 | Pump control state machine |
| 0x45CA0 | fuel_pump_control_45CA0 | 50 | Pump control snippet |
| 0x504EA | fuel_pump_ctrl_0x504EA | 78 | Pump control snippet |
| 0x50590 | fuel_pressure_monitor_0x50590 | 342 | Pressure monitor |
| 0x45984 | fuel_pressure_monitor_reset_45984 | 46 | Pressure monitor reset |
| 0x45B0A | fuel_pressure_storage_45B0A | 50 | Pressure data storage |
| 0x25CDC | fuel_pressure_storage_25CDC | 26 | Pressure storage alt |
| 0x1B5A8 | fuel_pump_speed_controller | 114 | Pump speed control |
| 0x262FA | fuel_pump_rpm_scale_262FA | 72 | Pump RPM scaling |
| 0x2CC1C | check_fuel_pump_relay_enable_2CC1C | 136 | Relay enable check |
| 0x2611E | pump_prime_watchdog_2611E | 178 | Prime watchdog timer |

### Injector Control / Hardware (16)

| Address | Name | Size | Description |
|---------|------|------|-------------|
| 0x10620 | fuel_injector_pulse_calc | 708 | Main injector pulse calc |
| 0x13D3C | calc_fuel_injection_all_rotors | 236 | Per-rotor injection dispatch |
| 0xFA90 | injection_pulse_decoder_main | 208 | Pulse decoder |
| 0xFB68 | injection_channel_init_all | 78 | Channel init |
| 0xFBB6 | fuel_inject_pulse_foreach_cyl | 38 | For-each rotor |
| 0x8A68 | injectorPulseSet | 48 | Write pulse to HW |
| 0x86F8 | setFuelInjectorLatency | 16 | Set latency register |
| 0x8402 | injectorRelatedFunc | 244 | Related injector function |
| 0xFC8A | pulse_filter_update | 20 | Pulse filter update |
| 0xFCA6 | pulse_period_filter | 44 | Period filter |
| 0xFCD2 | pulse_window_compute | 20 | Window compute |
| 0xFE24 | setFuelCutDriver | 338 | Fuel cut driver output |
| 0xFCE6 | injection_timing_calculator | 318 | Timing calculator |
| 0x2CCBC | injector_control_write_2CCBC | 8 | Direct register write |
| 0x21DEA | injector_event_dispatcher_21DEA | 36 | Event dispatcher |
| 0x229C0 | injector_timing_scheduler_229C0 | 6 | Timing scheduler trampoline |

### Diagnostics / OBD (6)

| Address | Name | Size | Description |
|---------|------|------|-------------|
| 0x4C6C4 | calcDiagFuelInjectorTrim | 154 | Diagnostic injector trim |
| 0x24440 | injector_checksum_validation_24440 | 170 | Injector checksum |
| 0x1A41A | fuel_injector_error_calc | 76 | Injector error calc |
| 0x457A2 | fuel_injection_monitoring_457A2 | 338 | Injection monitoring |
| 0x43476 | dtc_status_check_injector_43476 | 132 | DTC injector check |
| 0x25312 | fuel_system_health_check_25312 | 1676 | Full health check |

---

## 10. C Code for Key Functions

### 10.1 `calc_fuel_pump_duty_trim` (0x135F6)

This function computes the fuel pump duty cycle trim based on the operating mode:

```c
/* calc_fuel_pump_duty_trim — fuel pump duty cycle trim calculation
 *
 * ROM: 60E1D400  |  Address: 0x135F6  |  Size: 92 bytes
 *
 * Called from engineControlCalculateTiming Phase 2.
 * Computes trim values for fuel pump duty cycle based on mode:
 *   Mode 0: No trim (use base values from calibration)
 *   Mode 1: Compute additive trims (load + RPM components) for both rotors
 *   Mode 2: Use calibration default values (safe backup)
 *
 * RAM read/write via global addresses.
 */

/* ---- RAM Globals ---- */
#define RAM_PUMP_MODE_FLAG    (*(volatile uint8_t *)0xFFFFA7??)  /* mode selector */
#define RAM_PUMP_BASE_DUTY_R  (*(volatile float *)0xFFFFA7??)   /* base duty cycle (R rotor?) */
#define RAM_PUMP_TRIM_OUT_R   (*(volatile float *)0xFFFFA7??)   /* trimmed output R */
#define RAM_PUMP_TRIM_OUT_L   (*(volatile float *)0xFFFFA7??)   /* trimmed output L (or F) */

/* ---- Calibration ROM constants ---- */
#define CAL_TRIM_LOAD_R       (*(const float *)0x000136B8)      /* load trim addend */
#define CAL_TRIM_LOAD_L       (*(const float *)0x000136BA)      /* load trim addend (L) */
#define CAL_TRIM_RPM_R        (*(const float *)0x000136BC)      /* RPM trim addend R */
#define CAL_TRIM_RPM_L        (*(const float *)0x000136BE)      /* RPM trim addend L */
#define CAL_TRIM_FINAL_R      (*(const float *)0x000136C0)      /* final trim target R */
#define CAL_TRIM_FINAL_L      (*(const float *)0x000136CC)      /* final trim target L */
#define CAL_DEFAULT_DUTY_R    (*(const float *)0x000136DC)      /* safe default R */
#define CAL_DEFAULT_DUTY_L    (*(const float *)0x000136E0)      /* safe default L */

void calc_fuel_pump_duty_trim(void)
{
    uint8_t mode = RAM_PUMP_MODE_FLAG;

    if (mode == 0) {
        /* Mode 0: Load base duty from calibration and store */
        float base_r = RAM_PUMP_BASE_DUTY_R;        /* or a calibration constant */
        RAM_PUMP_TRIM_OUT_R = base_r;
        /* (Mode 0 path in ROM loads a float and stores it) */
    }

    if (mode == 1) {
        /* Mode 1: Compute active trims.
         * Formula: trim = base + load_comp + rpm_comp
         * Both rotors computed identically with different calibration constants.
         */
        float base = RAM_PUMP_BASE_DUTY_R;

        /* Rotor R (or Front): */
        float load_r = CAL_TRIM_LOAD_R;              /* load compensation addend */
        float rpm_r  = CAL_TRIM_RPM_R;               /* RPM compensation addend */
        float trim_r = base + load_r + rpm_r;
        RAM_PUMP_TRIM_OUT_R = trim_r;

        /* Rotor L (or Rear): */
        float load_l = CAL_TRIM_LOAD_L;
        float rpm_l  = CAL_TRIM_RPM_L;
        float trim_l = base + load_l + rpm_l;
        RAM_PUMP_TRIM_OUT_L = trim_l;
    }

    if (mode == 2) {
        /* Mode 2: Use calibration default/safe values directly */
        RAM_PUMP_TRIM_OUT_R = CAL_DEFAULT_DUTY_R;
        RAM_PUMP_TRIM_OUT_L = CAL_DEFAULT_DUTY_L;
    }
}
```

### 10.2 `arbitrateFuelCut` (0xE56C)

```c
/* arbitrateFuelCut — fuel cut arbitration
 *
 * ROM: 60E1D400  |  Address: 0xE56C  |  Size: 358 bytes
 *
 * Evaluates two sets of fault/protection conditions and produces
 * a 2-bit fuel cut result:
 *   Bit 0: Primary fuel cut (normal conditions)
 *   Bit 1: Secondary protection (fault/error conditions)
 */

void arbitrateFuelCut(void)
{
    uint8_t result = 0;

    /* ---- Condition Set 1: Primary fuel cut (bit 0) ---- */
    /* 12 fault flags checked: any == 1 triggers cut */
    uint8_t cond1_set[] = {
        *(volatile uint8_t *)0xA444,
        *(volatile uint8_t *)0xA4A4,
        *(volatile uint8_t *)0xA9D4,
        *(volatile uint8_t *)0xC89C,
        *(volatile uint8_t *)0xCB41,
        *(volatile uint8_t *)0xBCB6,
        *(volatile uint8_t *)0xCB42,
        *(volatile uint8_t *)0xC945,
        *(volatile uint8_t *)0xCC8A,
        *(volatile uint8_t *)0xCC8B,
        *(volatile uint8_t *)0xCC8C,
        *(volatile uint8_t *)0xCC8D,
    };
    for (int i = 0; i < 12; i++) {
        if (cond1_set[i] == 1) { result |= 0x01; break; }
    }
    /* Also check 0xC1EC (non-zero triggers cut) */
    if (*(volatile uint8_t *)0xC1EC != 0) result |= 0x01;

    /* ---- Condition Set 2: Secondary protection (bit 1) ---- */
    uint8_t cond2_set[] = {
        *(volatile uint8_t *)0xA445,
        *(volatile uint8_t *)0xA4A5,
        *(volatile uint8_t *)0xA9D4,
        *(volatile uint8_t *)0xC89C,
        *(volatile uint8_t *)0xCB41,
        *(volatile uint8_t *)0xBCB7,
        *(volatile uint8_t *)0xCB43,
        *(volatile uint8_t *)0xC945,
        *(volatile uint8_t *)0xCC8A,
        *(volatile uint8_t *)0xCC8B,
        *(volatile uint8_t *)0xCC8C,
        *(volatile uint8_t *)0xCC8D,
    };
    for (int i = 0; i < 12; i++) {
        if (cond2_set[i] == 1) { result |= 0x02; break; }
    }
    if (*(volatile uint8_t *)0xC1EC != 0) result |= 0x02;

    *(volatile uint16_t *)0xA430 = result;
}
```

### 10.3 `calc_fuel_injection_all_rotors` (0x13D3C)

```c
/* calc_fuel_injection_all_rotors — fuel injection dispatch for all rotors
 *
 * ROM: 60E1D400  |  Address: 0x13D3C  |  Size: 236 bytes
 *
 * Computes per-rotor injection timing and dispatches to output helpers.
 * Structurally parallel to calc_ignition_all_rotors_13C2C.
 *
 * Inputs:
 *   - RAM main injection value at 0xFFFFA744 (float)
 *   - RAM engine speed at 0xFFFFB5B8 (float)
 *   - Fuel cut flag, injection enable flag
 *
 * Outputs:
 *   - Ignition timing values at 0xFFFFA734/0xFFFFA738 (float) — written
 *     identically by calc_ignition_all_rotors_13C2C; lead/trail split applied
 *     later in rotor_sync_gate_state_ctrl_2100A (0x2100A, formerly leading_trailing_spark_control, unverified)
 */

void calc_fuel_injection_all_rotors(void)
{
    float main_inj = *(volatile float *)0xFFFFA744;   /* fr14: main injection value */
    float engine_rpm = *(volatile float *)0xFFFFB5B8;  /* fr15: engine speed */

    uint8_t fuel_cut_flag = *(volatile uint8_t *)0x????;   /* fuel cut active? */
    uint8_t mode12_flag  = *(volatile uint8_t *)0x????;    /* injection mode flag */

    /* ---- Fuel cut check ---- */
    if (fuel_cut_flag != 0) {
        /* Fuel cut active — skip normal injection */
        /* Clear injection enable and return */
        *(volatile uint8_t *)0x???? = 0;
        return;
    }

    /* ---- Mode check: cranking vs. running injection ---- */
    if (mode12_flag != 0) {
        /* Normal running mode or specific injection mode */
        uint8_t temp_ok = *(volatile uint8_t *)0x????;  /* coolant temp OK? */
        if (temp_ok < some_threshold) {
            /* Apply injection correction */
            float corr_val = *(volatile float *)0x????;  /* load correction */
            float adjusted = main_inj + corr_val;       /* fr15 = corrected */
            uint8_t accel_flag = *(volatile uint8_t *)0x????;
            if (accel_flag != 0) {
                /* Apply acceleration enrichment on top */
                float accel_val = *(volatile float *)0x????;
                adjusted = some_interpolation(adjusted, accel_val);
            }
            main_inj = adjusted;
        }
    }

    /* ---- Per-rotor dispatch ---- */
    /* Check individual rotor/injector enable flags */
    /* Dispatch to output helpers that write to hardware */
    compare_select_two_float_values(main_inj, ...);   /* 0x13ED2 */
    calc_fuel_pump_control_output(...);               /* 0x13E6C */
    calc_fuel_pressure_load_compensation(...);         /* 0x13EE6 */

    /* Write outputs — both cells get the same value (no lead/trail split here;
       that happens later in rotor_sync_gate_state_ctrl_2100A (0x2100A), unverified) */
    *(volatile float *)0xFFFFA734 = main_inj;  /* ignition timing values (A734/A738) */
    *(volatile float *)0xFFFFA738 = main_inj;
}
```

### 10.4 `setFuelInjectorLatency` (0x86F8)

```c
/* setFuelInjectorLatency — set injector latency/dead-time
 *
 * ROM: 60E1D400  |  Address: 0x86F8  |  Size: 16 bytes
 *
 * Writes a latency value (timer ticks) to paired primary/shadow
 * registers for one of three injector channels.
 *
 * Parameters:
 *   r4 — injector channel (0, 1, 2)
 *   r5 — latency value (unsigned 32-bit)
 *
 * Register layout at 0xFFFFA094:
 *   [0]:  channel 0 primary
 *   [1]:  channel 1 primary
 *   [2]:  channel 2 primary
 *   [3]:  channel 0 shadow
 *   [4]:  channel 1 shadow
 *   [5]:  channel 2 shadow
 */

void setFuelInjectorLatency(int injector_idx, uint32_t latency)
{
    volatile uint32_t *base = (volatile uint32_t *)0xFFFFA094;

    switch (injector_idx) {
        case 0:
            base[0] = latency;  /* primary */
            base[3] = latency;  /* shadow */
            break;
        case 1:
            base[1] = latency;
            base[4] = latency;
            break;
        case 2:
            base[2] = latency;
            base[5] = latency;
            break;
        /* No default — no action for invalid index */
    }
}
```

### 10.5 `calc_adaptive_fuel_trim` (0x1379C)

```c
/* calc_adaptive_fuel_trim — long-term adaptive fuel trim
 *
 * ROM: 60E1D400  |  Address: 0x1379C  |  Size: 228 bytes
 *
 * Computes a long-term fuel trim based on O2 feedback.
 * Integrated over time with a leaky integrator, clipped
 * to [-2.8%, +0.7%].
 *
 * Called first in Phase 2 of engineControlCalculateTiming.
 */

void calc_adaptive_fuel_trim(void)
{
    float engine_rpm      = *(volatile float *)0xFFFFB5B8;
    float lambda_feedback = *(volatile float *)0xFFFFB5C4;

    /* Compute deviation from reference target */
    float deviation = compute_deviation(engine_rpm, lambda_feedback);
    *(volatile float *)0xFFFFA728 = deviation;  /* store error signal */

    /* Select trim table */
    uint8_t table_select = *(volatile uint8_t *)0xFFFFB5AC;
    const void *table_desc;
    if (table_select == 0) {
        table_desc = (const void *)0x6A868;      /* primary trim table */
    } else {
        uint8_t trim_enable = *(volatile uint8_t *)0xFFFFB5A4;
        table_desc = (trim_enable == 0)
            ? (const void *)0x6A868
            : (const void *)0x6A87C;             /* secondary trim table */
    }

    /* 1D table lookup */
    float trim_value = table1D_lookup(table_desc, deviation);
    *(volatile float *)0xFFFFA720 = trim_value;

    /* Enable conditions for integration */
    uint8_t ect_status = *(volatile uint8_t *)0xFFFFC084;
    float trimmed;

    if (ect_status == 1 && engine_rpm > 1500.0f) {
        /* Adaptation active — leaky integrator */
        float previous_trim = trim_value;         /* or from stored state */
        float gain = 0.009766f;                   /* ~1/1024 per tick */
        trimmed = previous_trim + gain * (trim_value - previous_trim);
    } else {
        trimmed = 0.0f;  /* No adaptation when cold or below RPM threshold */
    }

    /* Clamp to safe limits */
    if (trimmed < -2.8f) trimmed = -2.8f;
    if (trimmed > 0.7f)  trimmed = 0.7f;

    /* Write outputs */
    *(volatile float *)0xFFFFA718 = trimmed;   /* leading edge trim */
    /* Also written to trailing edge trim at 0xFFFFAADA */
}
```

---

## 11. Test Strategy

### 11.1 Unit Tests (Against Emulator `sh2emu.py`)

Each reconstructed C function should be verified against the emulator:

```python
# Example test: calc_fuel_pump_duty_trim
def test_calc_fuel_pump_duty_trim():
    """Verify fuel pump duty trim calculation against ROM behavior."""
    
    # Initialize emulator with ROM
    emu = sh2emu.SH2Emulator('roms/stock/60E1D400.bin')
    
    # Set up test inputs
    emu.write_byte(0xFFFFA7??, 1)    # mode = 1 (active trim)
    emu.write_float(0xFFFFA7??, 50.0) # base duty = 50%
    
    # Execute function
    emu.call(0x135F6)
    
    # Read outputs
    trim_r = emu.read_float(0x????)
    trim_l = emu.read_float(0x????)
    
    # Verify: base + load_comp + rpm_comp
    assert trim_r >= 0 and trim_r <= 100, f"Trim R {trim_r} out of range"
    assert trim_l >= 0 and trim_l <= 100, f"Trim L {trim_l} out of range"
```

### 11.2 Integration Tests

Test the complete pipeline by setting up sensor inputs and verifying injector outputs:

```python
def test_fuel_injection_pipeline():
    """End-to-end: sensor inputs → injector pulse width output."""
    
    emu = sh2emu.SH2Emulator('roms/stock/60E1D400.bin')
    
    # Set simulated sensor values
    emu.write_float(0xFFFFB5B8, 2000.0)   # RPM = 2000
    emu.write_float(0xFFFFB5C4, 0.8)       # O2 sensor = 0.8V (rich)
    emu.write_float(0xFFFFCA2C, 0.5)       # TPS = 50%
    emu.write_float(0xFFFFA9FC, 85.0)      # CLT = 85°C (warm)
    
    # Execute engine control tick
    emu.call(0x14584)  # engineControlCalculateTiming
    
    # Read fueling outputs
    adapt_trim = emu.read_float(0xFFFFA718)
    pulse_widths = [emu.read_word(0xF440 + i*2) for i in range(6)]
    
    # Verify
    assert -2.8 <= adapt_trim <= 0.7, f"Adaptive trim {adapt_trim} out of range"
```

### 11.3 Existing Test Infrastructure

Tests live in `c/tests/`. The existing tests cover:
- 2D/3D table lookups
- Math primitives (saturation, addition, filtering)
- Memory accessors
- Emulator verification harness

New fuel-specific tests should be added as `test_fuel_injector_pulse_calc.py`, `test_fuel_pump_duty_trim.py`, etc.

### 11.4 Calibration Table Verification

Cross-reference all calibration table addresses between:
1. `symbols/cal_tables.csv` (naming follows RX8Defs XML conventions; original XML not redistributed)
2. MAP scan output (`python tools/mapscan.py roms/stock/60E1D400.bin --dump 0x<addr>`)
3. Actual ROM bytes at the target address

Note: Addresses may differ between ROM variants — verify before assuming equivalence.

---

## 12. Open Questions

1. **Speed-density vs. MAF?** The equinox guide mentions load in g/rev, but the ROM has MAF sensor processing — is the primary fuel calculation MAF-based with speed-density as backup, or purely speed-density?

2. **Open loop target address?** The exact RAM location of the computed open loop lambda target (before corrections are applied) needs identification.

3. **Reference for adaptive trim deviation?** The `calc_adaptive_fuel_trim` deviation computation subtracts a reference value from engine RPM or lambda — the source of this reference value is not fully identified.

4. **Injector flow rate units?** The scalar injector size values (Primary Injector Size at 0x783A0 et al.) need their exact units confirmed (cc/min, g/sec, or lb/hr?).

5. **Injection timing strategy?** Sequential vs. batch fire vs. semi-sequential — the injection timing functions suggest sequential per-rotor injection, but the exact strategy (when in the cycle each injector fires) needs confirmation.

6. **Secondary injector staging?** At what RPM/load threshold do the secondary injectors activate? The `Injector Barometric Pressure Compensation` and staging logic needs tracing.

7. **Lambda target interpolation?** The exact interpolation between the multiple fueling maps (Fuelling 0-16) based on load, RPM, and operating mode needs full decoding.

8. **Fuel pressure sensor?** Does the RX-8 use a returnless fuel system with a pressure sensor, or a return system with a pressure regulator? This affects how `fuel_pressure_calc` works.

---

## References

- equinox92 user guide (captured from RX8Club; provenance and credits): `CREDITS.md`
- RX8Defs calibration definitions: RomRaider RX8Defs XML (not shipped)
- Calibration table catalog: `docs/subsystems/MAPS.md`
- Symbol table (merged): `symbols_60E1D400_merged.csv`
- Annotated assembly: `src/60E1D400_annotated.s`
- Function analysis docs: `docs/functions/`
- Existing C models: `c/`
- Engine fundamentals: `renesis_i_rotary_engine_fundamentals.pdf` (moved to private storage, not shipped)
