# engineControlCalculateTiming @ 0x14584

**Size:** 414 bytes (0x14584–0x14722)

Central engine control loop; largest flat dispatch in the callgraph (66 calls, 0
branches). Runs once per scheduler tick from `engineControlTASK` (0x11E94).

## Caller

| Address | Name | Context |
|---------|------|---------|
| 0x11E94 | `engineControlTASK` | Calls with `mov.l 0x12020,r2; jsr @r2` where literal 0x12020 = 0x14584 |

Stage 3 of 5 in `engineControlTASK`: `updateMemoryAtAddress`-like fn → `FUN_00021c40`
→ **this** → `FUN_00016f70` → conditional getSR chain.

## Structure

```
┌─────────────────────────────────────────────────────────────┐
│ engineControlCalculateTiming (66 calls, 0 branches)          │
│                                                              │
│  Phase 1 — Context save + Phase-1 subsystems                 │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ getSR(16)           save SR to stack                    │  │
│  │ incomplete_stack_save_r14_r13  save r14, r13 to stack   │  │
│  │ calc_spark_advance                       │  │
│  │ calc_spark_advance                             │  │
│  │ getKnockControlAllowed                                │  │
│  │ getKnockSensorFaultedStatus                            │  │
│  │ getKnockControlActive                                   │  │
│  │ updateKnockMaxRAM                                       │  │
│  │ calc_ignition_all_rotors_13C2C                             │  │
│  │ cooling_fan_control_0x17DCC                             │  │
│  │ setSR(saved_SR)          restore SR                     │  │
│  │ getSR(16)                save SR again                  │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  Phase 2 — Bulk subsystem dispatch (56 calls)                │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ FUEL CONTROL                                            │  │
│  │  calc_adaptive_fuel_trim          0x1379C               │  │
│  │  calc_accel_fuel_enrichment       0x138CC               │  │
│  │  calc_barometric_pressure_trim    0x13F68               │  │
│  │  read_fuel_pressure_feedback_status 0x1408C             │  │
│  │  calc_closed_loop_fuel_status     0x141B8               │  │
│  │  read_o2_sensor_voltage_trim      0x1412A               │  │
│  │                                                          │  │
│  │ ROTOR SYNC CONTROL                                       │  │
│  │  calc_rotor_sync_idle_gate_B      0x12BC8               │  │
│  │                                                          │  │
│  │ ENGINE SPEED / SENSOR STATUS                             │  │
│  │  read_engine_speed_status         0x13070               │  │
│  │  sensor_range_calc_44B1C          0x44B1C               │  │
│  │  sensor_abs_deviation_44B9A       0x44B9A               │  │
│  │                                                          │  │
│  │ DRIVER / DSC                                              │  │
│  │  calculateDriverConditions         0x43C4A              │  │
│  │  dscRelatedTiming?                0x19220               │  │
│  │                                                          │  │
│  │ AIR / THROTTLE CONTROL                                   │  │
│  │  air_bypass_control_43E4A         0x43E00               │  │
│  │  air_bleed_control_43F20          0x43EE8               │  │
│  │                                                          │  │
│  │ KNOCK CONTROL                                            │  │
│  │  knock_sensor_threshold_43E90     0x43E90               │  │
│  │  knock_control_calc_44824         0x44824               │  │
│  │  calc_combustion_chamber_temp     0x12938               │  │
│  │  write_knock_detected_flag        0x128C4               │  │
│  │  calc_rotor_B_knock_flag          0x12A48               │  │
│  │  write_rotor_A_knock_flag         0x128FE               │  │
│  │                                                          │  │
│  │ IGNITION                                                  │  │
│  │  ignition_advance_interp_446BC    0x446BC               │  │
│  │                                                          │  │
│  │ RPM / IDLE / NEUTRAL                                     │  │
│  │  rpm_limiter_calc_43E60           0x43E60               │  │
│  │  rpm_neutral_calc_44782           0x44782               │  │
│  │  idle_correction_interp_447B0     0x447B0               │  │
│  │                                                          │  │
│  │ FUEL PRESSURE / INJECTION                                │  │
│  │  fuel_pressure_calc_4409E         0x4409E               │  │
│  │  add_fuel_pressure_correction     0x126CA               │  │
│  │  calc_rotor_A_pressure_load       0x126EA               │  │
│  │  calc_rotor_B_pressure_load       0x127DE               │  │
│  │  calc_intake_pressure_pid_output_1252C  0x1252C          │  │
│  │                                                          │  │
│  │ FUEL CUT / THROTTLE LIFT                                │  │
│  │  fuel_enable_logic_44AB2          0x44AB2               │  │
│  │  fuel_cut_logic_4490A             0x4490A               │  │
│  │  calc_decel_fuel_cut_445AA        0x445AA               │  │
│  │                                                          │  │
│  │ EMISSIONS / EXHAUST / EVAP                              │  │
│  │  exhaust_control_43FE8            0x43F56               │  │
│  │  catalyst_control_440F0           0x440DE               │  │
│  │  lambda_control_calc_44206        0x44206               │  │
│  │  emissions_control_441BA          0x4416C               │  │
│  │  calc_evap_purge_duty             0x13652               │  │
│  │  calc_vis_solenoid_duty_cycle_1261C  0x1261C            │  │
│  │                                                          │  │
│  │ DIAGNOSTICS / FAULT CODES                               │  │
│  │  fault_code_handler_4436E         0x442E8               │  │
│  │  fuel_correction_update_44370     0x44370               │  │
│  │  FUN_0443A2                      0x443A2                │  │
│  │  readiness_check_44546           0x44530                │  │
│  │  health_check_system_4D0E8       0x4D0E8                │  │
│  │                                                          │  │
│  │ FPU / FILTER MAINTENANCE                                │  │
│  │  fpu_clear_result_44506          0x44506                │  │
│  │  fpu_conditional_accumulate_pair_ch0  0x14A5C           │  │
│  │  fpu_conditional_accumulate_pair_ch1  0x14A92           │  │
│  │  sensor_filter_apply_all         0x1061A                │  │
│  │  filter_signal_adaptive_2CBBA    0x2CBBA                │  │
│  │                                                          │  │
│  │ CRANKING / ENGINE STATE                                 │  │
│  │  getEngineCrankingStatus?        0x1117A                │  │
│  │  intake_condition_check_44694    0x44694                │  │
│  │  sensor_select_check_44748       0x44748                │  │
│  │  sensor_signal_calc_44076        0x44076                │  │
│  │                                                          │  │
│  │ FUEL PUMP                                                │  │
│  │  calc_fuel_pump_duty_trim        0x135F6                │  │
│  │  check_fuel_pump_relay_enable_2CC1C  0x2CC1C            │  │
│  │                                                          │  │
│  │ ROTOR SYNC / TIMING OFFSETS                              │  │
│  │  add_rotor_timing_offset         0x126DA                │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  Tail — Context restore                                      │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ setSR(saved_SR)        restore SR and return            │  │
│  └────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

> Naming: `c/calc_rotor_sync_idle_gate_B.c` keeps its IDA-derived filename; it
> implements rotor-sync idle/anti-stall gate (0x12BC8). Rotary has no camshafts;
> "cam timing" = per-rotor sync of the eccentric-shaft angle.

## Disassembly (SH-2E, big-endian)

```
engineControlCalculateTiming:
  ; === Phase 1 preamble ===
  0x14584: sts.l pr,@-r15        ; push return address
  0x14586: add #-4,r15           ; allocate 4 bytes on stack
  0x14588: mov.l 0x14784,r3      ; r3 = getSR (0x3920)
  0x1458A: jsr @r3               ; call getSR(16)
  0x1458C: mov #16,r4            ; delay slot: arg = 16

  0x1458E: mov.l 0x14788,r3      ; r3 = incomplete_stack_save_r14_r13 (0x14B04)
  0x14590: jsr @r3               ; save r14, r13 to stack
  0x14592: mov.l r0,@r15         ; delay slot: store SR on stack

  ; === Phase 1 subsystem calls (8 calls) ===
  0x14594: mov.l 0x1478c,r2  ; -> calc_spark_advance
  0x14596: jsr @r2
  0x14598: nop
  0x1459A: mov.l 0x14790,r3  ; -> calc_spark_advance
  ... (7 more calls, each 4 bytes: mov.l; jsr; nop)

  ; === Phase 1 barrier (restore + re-save SR) ===
  0x145C4: mov.l 0x147ac,r3  ; -> setSR (0x3934)
  0x145C6: jsr @r3
  0x145C8: mov.l @r15,r4     ; delay slot: arg = saved SR
  0x145CA: mov.l 0x14784,r2  ; -> getSR again (0x3920)
  0x145CC: jsr @r2
  0x145CE: mov #16,r4        ; delay slot: arg = 16

  ; === Phase 2 bulk dispatch (50+ calls) ===
  0x145D0: mov.l 0x147b0,r3  ; -> calc_adaptive_fuel_trim (0x1379C)
  0x145D2: jsr @r3
  0x145D4: mov.l r0,@r15     ; delay slot: store new SR on stack
  0x145D6: mov.l 0x147b4,r2  ; -> calc_accel_fuel_enrichment
  ... (50+ calls, every 4 bytes)

  ; === Phase 2 tail — restore SR and return ===
  0x1471A: mov.l @r15+,r4    ; load saved SR from stack
  0x1471C: mov.l 0x147ac,r3  ; -> setSR (0x3934)
  0x1471E: jmp @r3           ; tail call: setSR(saved_SR)
  0x14720: lds.l @r15+,pr    ; delay slot: pop return address
```

## Jump table (literal pool at 0x14784–0x14888)

| Slot | Offset | Target | Name |
|------|--------|--------|------|
| 0 | 0x14784 | 0x003920 | **getSR** |
| 1 | 0x14788 | 0x014B04 | incomplete_stack_save_r14_r13 |
| 2 | 0x1478C | 0x0121F0 | calc_spark_advance |
| 3 | 0x14790 | 0x01237C | calc_spark_advance |
| 4 | 0x14794 | 0x013A0E | getKnockControlAllowed |
| 5 | 0x14798 | 0x013A5E | getKnockSensorFaultedStatus |
| 6 | 0x1479C | 0x013A86 | getKnockControlActive |
| 7 | 0x147A0 | 0x013B90 | updateKnockMaxRAM |
| 8 | 0x147A4 | 0x013C2C | calc_ignition_all_rotors_13C2C |
| 9 | 0x147A8 | 0x017DCC | cooling_fan_control_0x17DCC |
| 10 | 0x147AC | 0x003934 | **setSR** |
| 11 | 0x147B0 | 0x01379C | calc_adaptive_fuel_trim |
| 12 | 0x147B4 | 0x0138CC | calc_accel_fuel_enrichment |
| 13 | 0x147B8 | 0x013F68 | calc_barometric_pressure_trim |
| 14 | 0x147BC | 0x01408C | read_fuel_pressure_feedback_status |
| 15 | 0x147C0 | 0x0141B8 | calc_closed_loop_fuel_status |
| 16 | 0x147C4 | 0x01412A | read_o2_sensor_voltage_trim |
| 17 | 0x147C8 | 0x012BC8 | calc_rotor_sync_idle_gate_B |
| 18 | 0x147CC | 0x013070 | read_engine_speed_status |
| 19 | 0x147D0 | 0x019220 | dscRelatedTiming? |
| 20 | 0x147D4 | 0x044B1C | sensor_range_calc_44B1C |
| 21 | 0x147D8 | 0x044B9A | sensor_abs_deviation_44B9A |
| 22 | 0x147DC | 0x043C4A | calculateDriverConditions |
| 23 | 0x147E0 | 0x043E90 | knock_sensor_threshold_43E90 |
| 24 | 0x147E4 | 0x043E60 | rpm_limiter_calc_43E60 |
| 25 | 0x147E8 | 0x043E00 | air_bypass_control_43E4A |
| 26 | 0x147EC | 0x044AB2 | fuel_enable_logic_44AB2 |
| 27 | 0x147F0 | 0x043EE8 | air_bleed_control_43F20 |
| 28 | 0x147F4 | 0x043F56 | exhaust_control_43FE8 |
| 29 | 0x147F8 | 0x044076 | sensor_signal_calc_44076 |
| 30 | 0x147FC | 0x04409E | fuel_pressure_calc_4409E |
| 31 | 0x14800 | 0x0440DE | catalyst_control_440F0 |
| 32 | 0x14804 | 0x044206 | lambda_control_calc_44206 |
| 33 | 0x14808 | 0x04416C | emissions_control_441BA |
| 34 | 0x1480C | 0x0442E8 | fault_code_handler_4436E |
| 35 | 0x14810 | 0x044370 | fuel_correction_update_44370 |
| 36 | 0x14814 | 0x0443A2 | FUN_0443A2 |
| 37 | 0x14818 | 0x044506 | fpu_clear_result_44506 |
| 38 | 0x1481C | 0x044530 | readiness_check_44546 |
| 39 | 0x14820 | 0x04490A | fuel_cut_logic_4490A |
| 40 | 0x14824 | 0x0445AA | calc_decel_fuel_cut_445AA |
| 41 | 0x14828 | 0x044694 | intake_condition_check_44694 |
| 42 | 0x1482C | 0x0446BC | ignition_advance_interp_446BC |
| 43 | 0x14830 | 0x044748 | sensor_select_check_44748 |
| 44 | 0x14834 | 0x044782 | rpm_neutral_calc_44782 |
| 45 | 0x14838 | 0x0447B0 | idle_correction_interp_447B0 |
| 46 | 0x1483C | 0x044824 | knock_control_calc_44824 |
| 47 | 0x14840 | 0x012938 | calc_combustion_chamber_temp |
| 48 | 0x14844 | 0x0128C4 | write_knock_detected_flag |
| 49 | 0x14848 | 0x0126EA | calc_rotor_A_pressure_load |
| 50 | 0x1484C | 0x0126CA | add_fuel_pressure_correction |
| 51 | 0x14850 | 0x01252C | calc_intake_pressure_pid_output_1252C |
| 52 | 0x14854 | 0x012A48 | calc_rotor_B_knock_flag |
| 53 | 0x14858 | 0x0128FE | write_rotor_A_knock_flag |
| 54 | 0x1485C | 0x0127DE | calc_rotor_B_pressure_load |
| 55 | 0x14860 | 0x0126DA | add_rotor_timing_offset |
| 56 | 0x14864 | 0x01261C | calc_vis_solenoid_duty_cycle_1261C |
| 57 | 0x14868 | 0x0135F6 | calc_fuel_pump_duty_trim |
| 58 | 0x1486C | 0x013652 | calc_evap_purge_duty |
| 59 | 0x14870 | 0x014A5C | fpu_conditional_accumulate_pair_ch0 |
| 60 | 0x14874 | 0x014A92 | fpu_conditional_accumulate_pair_ch1 |
| 61 | 0x14878 | 0x01061A | sensor_filter_apply_all |
| 62 | 0x1487C | 0x01117A | getEngineCrankingStatus? |
| 63 | 0x14880 | 0x02CBBA | filter_signal_adaptive_2CBBA |
| 64 | 0x14884 | 0x02CC1C | check_fuel_pump_relay_enable_2CC1C |
| 65 | 0x14888 | 0x04D0E8 | health_check_system_4D0E8 |

## Subsystem grouping

| Group | Count | Functions |
|-------|-------|-----------|
| **Context mgmt** | 3 | getSR, setSR, incomplete_stack_save_r14_r13 |
| **Knock detection / control** | 9 | getKnockControlAllowed, getKnockSensorFaultedStatus, getKnockControlActive, updateKnockMaxRAM, knock_sensor_threshold_43E90, knock_control_calc_44824, calc_combustion_chamber_temp, write_knock_detected_flag, calc_rotor_B_knock_flag, write_rotor_A_knock_flag |
| **Fuel control** | 9 | calc_adaptive_fuel_trim, calc_accel_fuel_enrichment, calc_barometric_pressure_trim, read_fuel_pressure_feedback_status, calc_closed_loop_fuel_status, read_o2_sensor_voltage_trim, fuel_enable_logic_44AB2, fuel_cut_logic_4490A, fuel_correction_update_44370 |
| **Combustion / load** | 4 | calc_spark_advance, calc_spark_advance, calc_rotor_A_pressure_load, calc_rotor_B_pressure_load |
| **Fuel pressure / injection** | 3 | fuel_pressure_calc_4409E, add_fuel_pressure_correction, calc_intake_pressure_pid_output_1252C |
| **Throttle lift / fuel cut** | 2 | calc_decel_fuel_cut_445AA, FUN_0443A2 |
| **Air control** | 2 | air_bypass_control_43E4A, air_bleed_control_43F20 |
| **Emissions / exhaust** | 4 | exhaust_control_43FE8, catalyst_control_440F0, lambda_control_calc_44206, emissions_control_441BA |
| **Ignition / timing** | 3 | calc_ignition_all_rotors_13C2C, ignition_advance_interp_446BC, dscRelatedTiming? |
| **Rotor sync control** | 2 | calc_rotor_sync_idle_gate_B, add_rotor_timing_offset |
| **Engine speed / RPM** | 3 | read_engine_speed_status, rpm_limiter_calc_43E60, rpm_neutral_calc_44782 |
| **Idle control** | 1 | idle_correction_interp_447B0 |
| **Cooling** | 1 | cooling_fan_control_0x17DCC |
| **Diagnostics / faults** | 3 | fault_code_handler_4436E, readiness_check_44546, health_check_system_4D0E8 |
| **Sensor processing** | 6 | sensor_range_calc_44B1C, sensor_abs_deviation_44B9A, sensor_signal_calc_44076, sensor_select_check_44748, sensor_filter_apply_all, filter_signal_adaptive_2CBBA |
| **Evap / VIS control** | 2 | calc_evap_purge_duty, calc_vis_solenoid_duty_cycle_1261C |
| **Fuel pump** | 2 | calc_fuel_pump_duty_trim, check_fuel_pump_relay_enable_2CC1C |
| **FPU maintenance** | 2 | fpu_clear_result_44506, fpu_conditional_accumulate_pair_{ch0,ch1} |
| **Cranking / engine state** | 2 | getEngineCrankingStatus?, intake_condition_check_44694 |
| **Driver conditions** | 1 | calculateDriverConditions |

## Key observations

1. **Zero branches** — flat sequential dispatch, no `bf`/`bt`/`bra`; every subfunction
   called unconditionally each tick, so all conditional logic is inside the callees.

2. **SR barrier** — getSR/setSR at `0x145C4–0x145CE` likely changes interrupt mask:
   Phase 1 at higher priority (time-critical knock/cooling), Phase 2 at another.
3. **`incomplete_stack_save_r14_r13`** (0x14B04) — non-standard prologue pushing
   r14/r13 beyond normal r15 SP → likely interrupt-context invocation.
4. **No data passage** — all callees use global RAM directly; only args are
   getSR/setSR `r4=16`. Purely a scheduling/timing trigger.
5. **Widest call breadth in ROM** — 66 callees across every major subsystem; best
   entry point for the engine control architecture.
6. **Caller** — `engineControlTASK` (0x11E94), flat dispatch of ~5; this is stage 3.

## Draft C

```c
/* engineControlCalculateTiming — main engine control dispatch hub
 *
 * ROM: 60E1D400  Addr: 0x14584  Size: 414 bytes
 *
 * Called from engineControlTASK (0x11E94) every scheduler tick.
 * Calls 66 subfunctions covering all major engine subsystems.
 * No parameters; all subfunctions operate on global RAM.
 */
void engineControlCalculateTiming(void)
{
    // === Phase 1: context save + early subsystems ===
    uint32_t saved_sr = getSR(16);             // save status register (intr mask)
    incomplete_stack_save_r14_r13();            // push r14, r13

    calc_spark_advance();
    calc_spark_advance();
    getKnockControlAllowed();
    getKnockSensorFaultedStatus();
    getKnockControlActive();
    updateKnockMaxRAM();
    calc_ignition_all_rotors_13C2C();
    cooling_fan_control();

    setSR(saved_sr);                           // restore original SR
    saved_sr = getSR(16);                      // re-save with (possibly new) SR

    // === Phase 2: bulk subsystem dispatch ===
    calc_adaptive_fuel_trim();
    calc_accel_fuel_enrichment();
    calc_barometric_pressure_trim();
    read_fuel_pressure_feedback_status();
    calc_closed_loop_fuel_status();
    read_o2_sensor_voltage_trim();
    calc_rotor_sync_idle_gate_B();
    read_engine_speed_status();
    dscRelatedTiming();
    sensor_range_calc();
    sensor_abs_deviation();
    calculateDriverConditions();
    knock_sensor_threshold();
    rpm_limiter_calc();
    air_bypass_control();
    fuel_enable_logic();
    air_bleed_control();
    exhaust_control();
    sensor_signal_calc();
    fuel_pressure_calc();
    catalyst_control();
    lambda_control_calc();
    emissions_control();
    fault_code_handler();
    fuel_correction_update();
    func_0443A2();
    fpu_clear_result();
    readiness_check();
    fuel_cut_logic();
    throttleLiftFuelCut();
    intake_condition_check();
    ignition_advance_interp();
    sensor_select_check();
    rpm_neutral_calc();
    idle_correction_interp();
    knock_control_calc();
    calc_combustion_chamber_temp();
    write_knock_detected_flag();
    calc_rotor_A_pressure_load();
    add_fuel_pressure_correction();
    calc_intake_pressure_pid_output();
    calc_rotor_B_knock_flag();
    write_rotor_A_knock_flag();
    calc_rotor_B_pressure_load();
    add_rotor_timing_offset();
    calc_vis_solenoid_duty_cycle();
    calc_fuel_pump_duty_trim();
    calc_evap_purge_duty();
    fpu_conditional_accumulate_pair_ch0();
    fpu_conditional_accumulate_pair_ch1();
    sensor_filter_apply_all();
    getEngineCrankingStatus();
    filter_signal_adaptive();
    check_fuel_pump_relay_enable();
    health_check_system();

    // === Restore context and return ===
    setSR(saved_sr);
}
```

## Uncertainties

- **getSR(16) semantics** — `r4 = 16` may select an SR bitmask (IMASK); exact
  interrupt priority unknown.
- **SR barrier purpose** — Phase 1→2 transition may change interrupt masking.
- **`incomplete_stack_save_r14_r13`** (0x14B04) — saves r14/r13 then more work.
  needs separate analysis.
- **Callee signatures** — inferred `void func(void)`; no registers set before calls
  (only `mov #16,r4` before getSR); subfunctions likely operate on globals.
- **callgraph at 0x141FC** — `callgraph.csv` (60E0FC00 set) maps it to 0x141FC with
  different callees (timing/ignition-specific) → firmware offset or symbol
  relocation; 60E1D400 ROM places it at 0x14584 (callees above).
