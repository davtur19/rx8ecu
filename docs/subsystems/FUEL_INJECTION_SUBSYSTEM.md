# Fuel Injection Control Subsystem — RX-8 PCM (60E1D400)

**ROM:** 60E1D400 (N3J1EM, 6-Port MT, 2004–08) · **Cross-ref:** 60E0FC00 (USDM) · **Functions:** ~93 fuel/injection-related · **Updated:** 2026-07-31

## 1. Overall Fueling Architecture

**Speed-density** fueling strategy:

```
SENSORS (RPM, MAF/VAF, MAP, TPS, IAT, CLT, O2/Lambda)
  → LOAD CALC → BASE FUEL MASS (AFR from table)
  → CORRECTIONS ×1.23 (WU, AC, CL, FT, FP, FL)
  → PULSE WIDTH CALC (ms → timer ticks) — Per Rotor A, Rotor B (leading + trailing ports)
```

### Pipeline Stages

| Stage | Functions | Tick |
|---|---|---|
| Sensor acquisition | MAF, MAP, TPS, IAT, CLT, O2, RPM | Pre-tick (interrupt) |
| Load calculation | `calc_spark_advance`, `calc_spark_advance` | Phase 1 |
| Main fuel corrections | `calc_adaptive_fuel_trim`, `calc_accel_fuel_enrichment`, `calc_barometric_pressure_trim`, `calc_closed_loop_fuel_status`, `read_o2_sensor_voltage_trim` | Phase 2 |
| Fuel cut arbitration | `calc_decel_fuel_cut_445AA`, `fuel_cut_logic`, `fuel_enable_logic`, `arbitrateFuelCut` | Phase 2 |
| Pulse width calc | `fuel_injector_pulse_calc`, `calc_fuel_injection_all_rotors`, `injectorPulseSet` | Post-Phase 2 |
| Fuel pump control | `calc_fuel_pump_duty_trim`, `calc_fuel_pump_control_output`, `check_fuel_pump_relay_enable` | Phase 2 |
| Output to hardware | `injection_pulse_decoder_main`, `injector_timing_output_copy`, `injector_control_write` | End of cycle |

All functions called **unconditionally** from `engineControlCalculateTiming` (0x14584) every scheduler tick (~10ms); conditional logic is pushed into each subfunction (global RAM read/write).

## 2. Fuel Mass Calculation Strategy

Speed-density with MAF validation.

### 2.1 Air Mass

```
Air Mass (g/rev) = f(MAF_sensor_voltage, RPM, IAT, barometric_pressure)
```

MAF sensor: hot-wire (Mazda PN N3H1-13-215). Calibration curve in `MAF Scaling` table @0x6FBD8 (48-point 1D lookup, float).

Key sensor processing: `maf_sensor_value` (linearize MAF ADC), `baro_sensor_value`, `sensor_signal_calc_44076`.

### 2.2 Base Fuel Mass (Open Loop)

From the Equinox guide:
> Open Loop Lambda values are stored as the decimal part (ECU adds 1; defs subtract 1 for readability)

```
OpenLoop = max(OpenLoopTarget, TipInTarget * TipInBaroCorr) * CoolantTempCorr
```

Multiple fuel tables selected by operating mode:

| Table | Address (60E1D400) | Type | Description |
|---|---|---|---|
| Fuelling - Safe Mode | 0x71CD0 | 1D ×9 | Default/safe lambda target |
| Fuelling 0 | 0x71CE0 | 1D | Normal operating fuel map |
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

**Key function:** `calcOpenLoopFuelingTarget` (0x1FD8E, 578 B) — selects among tables by mode, applies `CoolantTempCorr`.

### 2.3 Lambda → Pulse Width

```
InjectorPulse_ms = (FuelMass_g * StoichAFR) / (InjectorFlow_cc/min * Latency_correction)
```
Steps: fuel mass = AirMass / CommandedLambda / StoichAFR → pulse = FuelMass/(FlowRate × NumInjectors) × 60000 → + dead time → convert to timer ticks (× 65536 or ÷ 16 by stage).

Key functions: `fuel_injector_pulse_calc` (0x10620, 708 B) · `injector_pulse_width_calc` (0xB2E4, 198 B) · `injector_pulse_width_calculator` (0xAEFA, 4 B trampoline) · `fuel_pulse_width_calc_saturated` (0xB4D8, 100 B).

## 3. Correction Hierarchy

Applied in order, multiplying/adding to base fuel mass:

1. **Warm-up enrichment** `calc_engine_temp_fuel_trim` @0x1437C — coolant-based; tapers off warm. Tables e.g. 0x71D00, 0x71D84.
2. **Cold start enrichment** `calc_cold_start_fuel_enrichment` @0x142E8 — decays with time/temp. `after_start_fuel_enrichment_task` (0x1A95C), `setStartupInjectorPwMult` (0x3126E), `calcInjectorCrankingTime` (0x31088), `getCrankingInjectorPulseTime` (0x310D4).
3. **Acceleration enrichment** `calc_accel_fuel_enrichment` @0x138CC — tip-in on TPS rate-of-change + MAP/RPM.
4. **Closed-loop / O2** `calc_closed_loop_fuel_status` @0x141B8 — when O2 warm, targets λ=1.0. Reads `read_o2_sensor_voltage_trim` (0x1412A).
5. **Adaptive fuel trim** `calc_adaptive_fuel_trim` @0x1379C — long-term from O2. Two 1D tables (0x6A868, 0x6A87C) 9 breakpoints. Clamp [-2.8%, +0.7%], gain ~0.009766. Enabled: RPM > 1500 AND coolant warm (closed loop).
6. **Barometric trim** `calc_barometric_pressure_trim` @0x13F68 — altitude compensation (reduces fuel at altitude).
7. **WOT enrichment** `calc_wot_fuel_enrichment` @0x14220 — open-loop rich (λ<1) for power/cooling. Tables Fuelling 15/16.
8. **Catalyst warm-up** — `CatWarmup = (LoadBasedEnrich * LoadComp) + EngineSpeedEnrich`; active cold start.
9. **Fuel pressure correction** `add_fuel_pressure_correction` @0x126CA — low pressure → wider pulse. `fuel_pressure_calc_4409E` (0x4409E), `read_fuel_pressure_feedback_status` (0x1408C).
10. **Fuel cut** (overrides all): `calc_decel_fuel_cut_445AA` (0x445AA), `fuel_cut_logic` (0x4490A), `rpm_limiter_fuel_cutoff` (0xC59E), `calculateRevLimiterFuelCut` (0xF192), `arbitrateFuelCut` (0xE56C).

### Accumulation Model

```c
float computeFinalPulseWidth(void) {
    float open_loop = max(getBaseOpenLoopTarget(), getTipInEnrichment() * getBarometricPressureCorr()) * getCoolantTempCorr();
    float cat_warmup = getLoadBasedEnrich() * getLoadComp() + getEngineSpeedEnrich();
    float commanded_lambda = (open_loop + cat_warmup) * (1.0 + getAdaptiveFuelTrim() + getClosedLoopCorrection());
    float pulse_ms = (getAirMassPerCycle() / (commanded_lambda * STOICH_AFR)) / injector_flow_rate * 60000.0f + injector_latency;
    return pulse_ms;
}
```

## 4. Injector Flow Rate and Latency Calibration

### 4.1 Injector Sizing

Two-stage injection (primary + secondary per rotor):

| Parameter | Address | Units |
|---|---|---|
| Primary Injector Size | 0x0783A0 | cc/min (or g/sec) |
| Secondary Injector Size | 0x0783A8 | cc/min |
| Secondary Injector Size #2 | 0x0783B0 | cc/min |

Stock: **Primary** 420 cc/min @ 3.9 bar (DENSO 195500-4450) · **Secondary** 420 cc/min @ 3.9 bar (DENSO 195500-4450).

### 4.2 Latency (Dead Time)

| Table | Address | Type |
|---|---|---|
| Injector Latency Primary | 0x780F4 | 2D 17×9 (dead time vs voltage) |
| Injector Latency Secondary | 0x77F58 | 2D 17×9 |

Functions: `setFuelInjectorLatency` (0x86F8, 16 B — writes latency to 3 channels, paired primary/shadow at 0xFFFFA094) · `getFuelInectorLatencyCals` (0x30DE8, 146 B) · `getInjectorTempBasedMultiplierLookups` (0x30BCA, 60 B).

### 4.3 Pulse Calculation Flow

```
Engine Speed / Load / Target Lambda → Base Fuel Mass (= air / lambda)
→ Injector Pulse (= fuel / flow) → + Latency(V) → Timer Ticks (×65536)
→ Saturation & Limit Check → Write to HW OC Reg
```

### 4.4 Hardware Output Registers

`0xFFFFA004` injector state array (12 B/injector × 6 = 72 B) · `0xFFFFA094` injector calibration map (32 B/injector) · HW timer/OC regs `0xF440` (16-bit) and `0xF66C` (injector enable bits).

## 5. Fuel Cut Logic

### 5.1 Sources

| Source | Function | Address | Condition |
|---|---|---|---|
| Throttle lift (decel) | `calc_decel_fuel_cut_445AA` | 0x445AA | Throttle closed, RPM above threshold |
| Rev limit | `calculateRevLimiterFuelCut` | 0xF192 | RPM exceeds hard limit |
| Rev limit init | `revLimitFuelCutInit` | 0xF0FC | Power-on init |
| RPM limiter | `rpm_limiter_fuel_cutoff` | 0xC59E | Soft limit (per rotor) |
| Cold rev limit | `calculateRevLimiterFuelCut` (cold) | — | Lower limit when cold |
| DSC/TC request | `arbitrateDSCFuelCut` | 0x2D994 | Stability control torque reduction |
| Diagnostic | `calcDiagFuelInjectorTrim` | 0x4C6C4 | Diagnostic injector cut |
| Fault conditions | `arbitrateFuelCut` | 0xE56C | 13 fault condition flags |

### 5.2 Arbitration

`arbitrateFuelCut` (0xE56C) ORs fuel cut request flags → 2-bit result:
- **Bit 0 (0x01):** primary fuel cut — throttle lift, rev limit
- **Bit 1 (0x02):** secondary protection — fault/error conditions

Stored at `0xA430`; read by `getFuelCutRequestStatus` (0xFF08), `calc_fuel_injection_all_rotors` (0x13D3C, disables injection when cut), `fuel_cut_logic_4490A` (0x4490A, applies with hysteresis).

Condition flags — primary set: `0xA444, 0xA4A4, 0xA9D4, 0xC89C, 0xCB41, 0xBCB6, 0xCB42, 0xC945, 0xCC8A, 0xCC8B, 0xCC8C, 0xCC8D` + `0xC1EC` (non-zero). Secondary set: same list with `0xA445, 0xA4A5, 0xBCB7, 0xCB43` substituted for `0xA444, 0xA4A4, 0xBCB6, 0xCB42`.

### 5.3 Rev Limit Strategy

Fuel-cut strategy (not ignition cut):
1. **Soft limit:** begins cutting ~9000 RPM (calibratable via `Rev Limit` table @0x6D54C)
2. **Hard limit:** complete cut ~9500 RPM
3. **Cold limit:** ~4000 RPM when coolant below threshold (`Cold Rev Limit Threshold` @0x6D53C, `Cold Rev Limit` @0x6D544)

`rpm_limiter_fuel_cutoff` (0xC59E) cuts one rotor at a time for smooth engagement.

### 5.4 Deceleration Fuel Cut

`calc_decel_fuel_cut_445AA` (0x445AA): TPS < closed threshold (~0.01 V/angle), RPM > min threshold, not in override (DSC etc.), feature enabled (cal `0x7B3DC` = 0x01). Hysteresis via saturating accumulator (addSaturate8Bit); cut stays until RPM drops below re-enable threshold.

## 6. Per-Rotor Fueling

```
fuel_calc_entry (0x9528, 12 B trampoline)
  └── fuel_calc_per_rotor (0x9534, 262 B)
        ├── rotor_fuel_calc_dispatcher (0xB57A, 268 B)
        │     ├── calc_fuel_correction_all_modes (0x12C8C, 614 B)
        │     ├── calc_fuel_trim_correction_map (0x136F0, 140 B)
        │     └── dual_channel_fuel_computation (0x14BAC, 88 B)
        ├── fuel_injector_pulse_calc (0x10620, 708 B)  — all 6 injectors (3/rotor × 2)
        └── calc_fuel_injection_all_rotors (0x13D3C, 236 B)
              ├── applies fuel cut flags; per-rotor via compare_select_two_float_values
              ├── calc_fuel_pump_control_output (0x13E6C)
              └── calc_fuel_pressure_load_compensation (0x13EE6)
```

### Per-Rotor Trim

| Function | Address | Purpose |
|---|---|---|
| `calc_fuel_trim_correction_cyl_A` | 0x14722 | Rotor A trim |
| `calc_fuel_trim_correction_cyl_B` | 0x14742 | Rotor B trim |
| `calc_cyl_B_fuel_pulse_width` | 0x14464 | Rotor B pulse width |

### Injection Timing

| Function | Address | Purpose |
|---|---|---|
| `injectionTimingMaybe` | 0xE726 | Timing angle computation |
| `injection_timing_calculator` | 0xFCE6 | Main calculator |
| `injection_timing_calc_3BA3E` | 0x3BA3E | Variant |
| `injection_timing_calc_409CE` | 0x409C6 | Specific mode |
| `injection_timing_decrement_44A12` | 0x44A12 | Countdown/advance |

### Hardware Output

| Function | Address | Purpose |
|---|---|---|
| `injectorPulseSet` | 0x8A68 | Write pulse to HW reg |
| `injector_control_write_2CCBC` | 0x2CCBC | Direct register write |
| `injection_pulse_decoder_main` | 0xFA90 | Decode pulse timing |
| `injector_timing_output_copy` | 0xBB28 | Copy timing to output |
| `injector_timing_scheduler_229C0` | 0x229C0 | Schedule events |

### Cranking vs Running

| Function | Address | Purpose |
|---|---|---|
| `calcInjectorCrankingTime` | 0x31088 | Base cranking pulse |
| `getCrankingInjectorPulseTime` | 0x310D4 | Temp-compensated cranking pulse |
| `setStartupInjectorPwMult` | 0x3126E | Startup multiplier (deflood-aware) |
| `getDiagnosticFuelPulseCranking` | 0x310FC | Diagnostic cranking pulse |
| `crank_gated_fuel_pressure_proc` | 0xE6DC | Cranking fuel pressure |
| `crank_inject_count_44988` | 0x44988 | Crank injector event count |

## 7. Fuel Pump Control

Pump speed modulated via PWM (noise reduction, pressure regulation).

| Function | Address | Purpose |
|---|---|---|
| `calc_fuel_pump_duty_trim` | 0x135F6 | Duty trim by mode |
| `calc_fuel_pump_control_output` | 0x13E6C | Main pump output |
| `calc_fuel_pump_pwm_output` | 0x11EEA | PWM duty generation |
| `fuel_pump_speed_controller` | 0x1B5A8 | Speed control loop |
| `fuel_pump_rpm_scale_262FA` | 0x262FA | RPM scaling |
| `pump_control_output_2602C` | 0x2602C | Output stage |

Pressure regulation: `fuel_pressure_calc` (0x15D82, 1642 B) · `fuel_pressure_calc_with_interpolation` (0xE6EC) · `calc_fuel_pressure_feedback` (0x11BC0) · `calc_fuel_pressure_error_integral` (0x140A4) · `calc_fuel_pressure_load_compensation` (0x13EE6) · `fuel_rail_pressure_state_machine` (0x197B8) · `fuel_rail_pressure_limiter_21B40` (0x21B40) · `read_fuel_pressure_feedback_status` (0x1408C).

Priming/safety: `calc_fuel_pump_priming` (0x14962, prime on ignition-on) · `pump_prime_watchdog_2611E` (0x2611E) · `pump_prime_wrapper_26244` (0x26244) · `pump_ready_flag_26208` (0x26208) · `check_fuel_pump_relay_enable` (0x2CC1C) · `fuel_pump_control_0x17510` (0x17510, full state machine).

## 8. Key Calibration Tables

### 8.1 Fueling Targets (Open Loop)

| Address | Name | Dimensions | Type | Scale |
|---|---|---|---|---|
| 0x71CD0 | Fuelling - Safe Mode | 1D ×9 | u8 | 0.007812 |
| 0x71D00 | Fuelling 1 | 1D ×7 | u8 | 0.007812 |
| 0x71D2C | Fuelling 2 - Safe Mode | 1D ×9 | u8 | 0.007812 |
| 0x71D5C | Fuelling 3 | 1D ×9 | u8 | 0.007812 |
| 0x71D84 | Fuelling 4 | 1D ×7 | u8 | 0.007812 |
| 0x71DD4 | Fuelling 5 | 1D ×18 | u8 | 0.003906 |
| 0x71E30 | Fuelling 6 | 1D ×18 | u8 | 0.003906 |
| 0x71E8C | Fuelling 7 | 1D ×18 | u8 | 0.003906 |
| 0x72084 | Fuelling 8 | 1D ×7 | u8 | 0.003906 |
| 0x7228C | Fuelling 9 - Safe Mode | 2D 12×8 | u8 | 0.003906 |
| 0x7238C | Fuelling 10 - Safe Mode | 2D 21×19 | u8 | 0.003906 |
| 0x72864 | Fuelling 15 | 2D 12×8 | u8 | 0.003906 |
| 0x72964 | Fuelling 16 | 2D 21×19 | u8 | 0.003906 |

### 8.2 Adaptive Trim

| Address | Name | Dims | Type | Scale |
|---|---|---|---|---|
| 0x72CAC | Table 2D - 106_ | 1D ×9 | u8 | 0.25 / -32 off |
| 0x72CDC | Table 2D - 107_ | 1D ×9 | u8 | 0.25 / -32 off |

### 8.3 Injector Cal

| Address | Name | Dims | Type |
|---|---|---|---|
| 0x0783A0 | Primary Injector Size | Scalar | u32 |
| 0x0783A8 | Secondary Injector Size | Scalar | u32 |
| 0x0783B0 | Secondary Injector Size #2 | Scalar | u32 |
| 0x780F4 | Injector Latency Primary | 2D 17×9 | u16 |
| 0x77F58 | Injector Latency Secondary | 2D 17×9 | u16 |
| 0x6FD38 | Injector Barometric Pressure Compensation | 1D ×4 | f32 |

### 8.4 Warm-up / Enrichment

| Address | Name |
|---|---|
| 0x72C20 | Table 2D - 104_ (temp correction A) |
| 0x72C50 | Table 2D - 105_ (temp correction B) |
| 0x72E84 | Table 2D - 112_ (warm-up enrichment A) |
| 0x72EB4 | Table 2D - 113_ (warm-up enrichment B) |

### 8.5 Lambda / AFR

| Address | Name |
|---|---|
| 0x6FD74 | Lambda Sensor Scaling (O2 linearization) |
| 0x7AF48 | Injection Angle Related AFR Input |
| 0x7AF74 | Unknown Lambda Input (secondary) |

### 8.6 Rev Limit / Fuel Cut

| Address | Name |
|---|---|
| 0x6D54C | Rev Limit (hard RPM limit) |
| 0x6D544 | Cold Rev Limit |
| 0x6D53C | Cold Rev Limit Threshold (coolant temp °C) |

## 9. Complete Fuel Function Catalog

### Main Pipeline (5)

| Address | Name | Size | Description |
|---|---|---|---|
| 0x09528 | fuel_calc_entry | 12 | Entry trampoline |
| 0x09534 | fuel_calc_per_rotor | 262 | Per-rotor dispatch |
| 0x0B57A | rotor_fuel_calc_dispatcher | 268 | Rotor calc dispatcher |
| 0x0B7D2 | fuel_calc_task_dispatcher | 176 | Task-level dispatcher |
| 0x22094 | main_fuel_control_pipeline_22094 | 180 | Main pipeline orchestrator |

### Base Fuel Calculation (8)

| Address | Name | Size | Description |
|---|---|---|---|
| 0x1FD8E | calcOpenLoopFuelingTarget | 558 | Open loop target calc |
| 0x12C8C | calc_fuel_correction_all_modes | 614 | Multi-mode correction |
| 0x0B2E4 | injector_pulse_width_calc | 198 | Base pulse width |
| 0x0D3DC | fuel_air_bilinear_interpolation | 106 | Fuel-air interpolation |
| 0x0B4D8 | fuel_pulse_width_calc_saturated | 100 | Saturated pulse calc |
| 0x0B3AA | atu_injector_enable_update | 40 | Injector enable update |
| 0x3BAD4 | base_fuel_calc_3BAD4 | 60 | Base fuel stub |
| 0x3B8B0 | fuel_calc_processor_3b8b0 | 398 | Fuel calc processor |

### Fuel Trims / Corrections (17)

| Address | Name | Size | Description |
|---|---|---|---|
| 0x1379C | calc_adaptive_fuel_trim | 228 | Long-term adaptive trim |
| 0x138CC | calc_accel_fuel_enrichment | 228 | Acceleration enrichment |
| 0x13F68 | calc_barometric_pressure_trim | ? | Barometric trim |
| 0x14220 | calc_wot_fuel_enrichment | 118 | WOT enrichment |
| 0x142E8 | calc_cold_start_fuel_enrichment | 118 | Cold start enrichment |
| 0x1437C | calc_engine_temp_fuel_trim | 82 | Coolant temp trim |
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
|---|---|---|---|
| 0x141B8 | calc_closed_loop_fuel_status | 104 | Closed loop status |
| 0x1412A | read_o2_sensor_voltage_trim | 142 | O2 voltage trim |
| 0x1913C | air_fuel_ratio_feedback_calc | 84 | AFR feedback |
| 0x21A18 | air_fuel_ratio_check_21A18 | 76 | AFR check |
| 0x230D0 | air_fuel_ratio_check_230D0 | 224 | AFR check 2 |
| 0x1A95C | after_start_fuel_enrichment_task | 68 | Post-start enrichment |

### Cranking / Startup (11)

| Address | Name | Size | Description |
|---|---|---|---|
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
|---|---|---|---|
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
|---|---|---|---|
| 0x135F6 | calc_fuel_pump_duty_trim | 92 | Pump duty trim |
| 0x13E6C | calc_fuel_pump_control_output | 102 | Pump output |
| 0x13EE6 | calc_fuel_pressure_load_compensation | 56 | Pressure load comp |
| 0x11EEA | calc_fuel_pump_pwm_output | 48 | PWM output |
| 0x14962 | calc_fuel_pump_priming | 42 | Priming |
| 0x15D82 | fuel_pressure_calc | 1642 | Main pressure calc |
| 0x11BC0 | calc_fuel_pressure_feedback | 158 | Pressure feedback |
| 0x10444 | calc_fuel_pressure_div | 72 | Pressure division |
| 0x126CA | add_fuel_pressure_correction | 16 | Pressure correction adder |
| 0x1408C | read_fuel_pressure_feedback_status | 24 | Pressure feedback status |
| 0x140A4 | calc_fuel_pressure_error_integral | 134 | Error integrator |
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
| 0x45B0A | fuel_pressure_storage_45B0A | 50 | Pressure storage |
| 0x25CDC | fuel_pressure_storage_25CDC | 26 | Pressure storage alt |
| 0x1B5A8 | fuel_pump_speed_controller | 114 | Pump speed control |
| 0x262FA | fuel_pump_rpm_scale_262FA | 72 | Pump RPM scaling |
| 0x2CC1C | check_fuel_pump_relay_enable_2CC1C | 136 | Relay enable check |
| 0x2611E | pump_prime_watchdog_2611E | 178 | Prime watchdog |

### Injector Control / Hardware (16)

| Address | Name | Size | Description |
|---|---|---|---|
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
|---|---|---|---|
| 0x4C6C4 | calcDiagFuelInjectorTrim | 154 | Diagnostic injector trim |
| 0x24440 | injector_checksum_validation_24440 | 170 | Injector checksum |
| 0x1A41A | fuel_injector_error_calc | 76 | Injector error calc |
| 0x457A2 | fuel_injection_monitoring_457A2 | 338 | Injection monitoring |
| 0x43476 | dtc_status_check_injector_43476 | 132 | DTC injector check |
| 0x25312 | fuel_system_health_check_25312 | 1676 | Full health check |

## 10. C Code for Key Functions

### `arbitrateFuelCut` (0xE56C, 358 B) — produces 2-bit result

```c
void arbitrateFuelCut(void) {
    uint8_t result = 0;
    // Primary (bit 0): 12 flags 0xA444,0xA4A4,0xA9D4,0xC89C,0xCB41,0xBCB6,0xCB42,
    //   0xC945,0xCC8A,0xCC8B,0xCC8C,0xCC8D (==1) OR 0xC1EC (!=0) → result |= 0x01
    // Secondary (bit 1): same with 0xA445,0xA4A5,0xBCB7,0xCB43 → result |= 0x02
    *(volatile uint16_t*)0xA430 = result;
}
```

### `calc_fuel_pump_duty_trim` (0x135F6, 92 B) — pump duty by mode

Modes: 0 → load base duty, store; 1 → `trim = base + load_comp + rpm_comp` per rotor (distinct cal addends); 2 → use safe default cal values. Cal constants at 0x136B8-0x136E0.

### `calc_fuel_injection_all_rotors` (0x13D3C, 236 B)

Reads main injection value `0xFFFFA744` and engine speed `0xFFFFB5B8`; checks fuel-cut/injection-mode flags; applies load correction (+accel enrichment if flagged); dispatches per rotor via `compare_select_two_float_values` (0x13ED2), `calc_fuel_pump_control_output` (0x13E6C), `calc_fuel_pressure_load_compensation` (0x13EE6). Writes identical value to `0xFFFFA734`/`0xFFFFA738` (no lead/trail split here).

### `calc_adaptive_fuel_trim` (0x1379C, 228 B)

Deviation from reference (RPM `0xFFFFB5B8`, lambda `0xFFFFB5C4`) → stored `0xFFFFA728`. Table selector `0xFFFFB5AC`/`0xFFFFB5A4` → 1D tables 0x6A868 / 0x6A87C (9 bp); result `0xFFFFA720`. Integrates with gain ~0.009766 when `0xFFFFC084==1 && RPM>1500`; clamps [-2.8, +0.7]; output `0xFFFFA718`.

### `setFuelInjectorLatency` (0x86F8, 16 B)

Writes latency to paired primary/shadow regs at base `0xFFFFA094`: channel i → `base[i]=latency`, `base[i+3]=latency` for i in 0..2.

## 11. Test Strategy

- **Unit tests**: reconstruct each C function and verify against emulator `sh2emu.py` (`c/tests/`; covers 2D/3D table lookups, math primitives, memory accessors, emulator harness). New: `test_fuel_injector_pulse_calc.py`, `test_fuel_pump_duty_trim.py`.
- **Integration**: drive `engineControlCalculateTiming` (0x14584) with sensor inputs (RPM 0xFFFFB5B8, O2 0xFFFFB5C4, TPS 0xFFFFCA2C, CLT 0xFFFFA9FC) and verify injector outputs (0xF440+2i ×6) and adaptive trim bounds.
- **Calibration verification**: cross-reference `symbols/cal_tables.csv` (RX8Defs XML naming), mapscan (`python tools/mapscan.py roms/stock/60E1D400.bin --dump 0x<addr>`), and ROM bytes. Addresses differ between ROM variants.

## 12. Open Questions

1. **Speed-density vs MAF?** ROM has MAF processing but equinox mentions g/rev load — primary calc MAF-based with speed-density backup, or purely speed-density?
2. **Open loop target address?** Exact RAM of computed open-loop lambda target (pre-correction) unidentified.
3. **Adaptive trim reference?** Source of the reference deviated from RPM/lambda in `calc_adaptive_fuel_trim` unidentified.
4. **Injector flow units?** Scalar size values (0x783A0 et al.) units unconfirmed (cc/min, g/sec, or lb/hr?).
5. **Injection timing strategy?** Sequential vs batch vs semi-sequential unconfirmed.
6. **Secondary injector staging?** RPM/load threshold for activation not traced.
7. **Lambda target interpolation?** Interpolation between Fuelling 0-16 by load/RPM/mode needs full decoding.
8. **Fuel pressure sensor?** Returnless (with sensor) vs return (with regulator) affects `fuel_pressure_calc`.

## References

- equinox92 user guide: `CREDITS.md`
- RX8Defs calibration definitions (RomRaider XML, not shipped)
- Calibration table catalog: `docs/subsystems/MAPS.md`
- Symbol table (merged): `symbols_60E1D400_merged.csv`
- Annotated assembly: `src/60E1D400_annotated.s`
- Function analysis docs: `docs/functions/`
- Existing C models: `c/`
