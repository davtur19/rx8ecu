/*
 * engine.h — RX-8 ECU Rotary Engine Control Definitions (13B-MSP)
 *
 * Open 1:1 firmware reconstruction for the Mazda RX-8 Renesis 13B-MSP
 * rotary engine control system. Covers eccentric shaft trigger decode,
 * ignition leading/trailing dwell, sequential injection, OMP control,
 * and the 10ms main engine cycle.
 *
 * Rotary-specific terminology:
 *   - Rotor: triangular rotary piston (not cylindrical)
 *   - Eccentric shaft: crankshaft equivalent (rotor orbits around it)
 *   - Leading spark: primary ignition event (front of combustion chamber)
 *   - Trailing spark: secondary ignition event (rear of combustion chamber)
 *   - OMP: Oil Metering Port (apex seal lubrication)
 *   - Primary injector: main fuel delivery
 *   - Secondary injector: enrichment/cold start
 *
 * Trigger wheel: 3x6+1 (20-tooth) on eccentric shaft with gap sync
 *
 * Source: engine_rotary_report.txt, IDA session ae00d360
 */

#ifndef ENGINE_H
#define ENGINE_H

#include <stdint.h>
#include "platform.h"

/* ====================================================================== */
/*  Trigger Wheel Configuration                                            */
/* ====================================================================== */

/*
 * The Renesis 13B-MSP uses a 3x6+1 (20-tooth) trigger wheel on the
 * eccentric shaft. This provides 6 events per rotor face (leading/trailing
 * edges) plus 1 gap for sync detection.
 *
 * Trigger pattern per revolution:
 *   Rotor A: 6 teeth (0-5) + gap (5th to 0th transition)
 *   Rotor B: 6 teeth (0-5) + gap (5th to 0th transition)
 *   Total: 20 teeth (6+1 for rotor A, 6+1 for rotor B, 6 shared)
 */

#define TRIGGER_TEETH_PER_ROTOR  6     /* Teeth per rotor face */
#define TRIGGER_GAP_POSITION     5     /* Gap after tooth 5 */
#define TRIGGER_TOTAL_TEETH      20    /* 3x6+1 total */

/* Eccentric shaft position states (crank_position_state_machine 0x789E) */
#define CRANK_STATE_IDLE         0     /* Not rotating */
#define CRANK_STATE_SEARCHING    1     /* Searching for sync */
#define CRANK_STATE_PARTIAL_SYNC 2     /* Partial synchronization */
#define CRANK_STATE_FULL_SYNC    3     /* Full synchronization */

/* ====================================================================== */
/*  Ignition System Configuration                                          */
/* ====================================================================== */

/*
 * 4 ignition coils (2 per rotor):
 *   - Leading (primary): front of combustion chamber
 *   - Trailing (secondary): rear of combustion chamber
 *
 * Dwell calculation uses 2D lookup table (outputPerRotorIgnitionDwell 0x11218)
 * with per-rotor compensation via can_addr_copy_57/58.
 */

#define IGNITION_COILS_PER_ROTOR  2     /* Leading + trailing */
#define IGNITION_TOTAL_COILS      4     /* 2 rotors × 2 coils */

/* Ignition coil indices */
#define IGN_COIL_ROTOR_A_LEADING  0
#define IGN_COIL_ROTOR_A_TRAILING 1
#define IGN_COIL_ROTOR_B_LEADING  2
#define IGN_COIL_ROTOR_B_TRAILING 3

/* Dwell timing constants */
#define DWELL_MIN_US              500   /* Minimum dwell time (μs) */
#define DWELL_MAX_US              5000  /* Maximum dwell time (μs) */
#define DWELL_BASE_DIVISOR        1000 /* Base divisor for dwell calc (ROM:0x112DC) */

/* ====================================================================== */
/*  Fuel Injection Configuration                                           */
/* ====================================================================== */

/*
 * 4 fuel injectors:
 *   - Primary (main fuel delivery): 2 per rotor
 *   - Secondary (enrichment/cold start): 2 per rotor
 *
 * Sequential injection per rotor face (sequential_fuel_injection_211DC).
 * Duty cycle calculated via math_complement_2440.
 */

#define INJECTORS_PER_ROTOR       2     /* Primary + secondary */
#define INJECTORS_TOTAL           4     /* 2 rotors × 2 injectors */

/* Injector indices */
#define INJ_ROTOR_A_PRIMARY       0
#define INJ_ROTOR_A_SECONDARY     1
#define INJ_ROTOR_B_PRIMARY       2
#define INJ_ROTOR_B_SECONDARY     3

/* Injection timing constants */
#define INJ_MIN_PULSE_US          200   /* Minimum pulse width (μs) */
#define INJ_MAX_PULSE_US          20000 /* Maximum pulse width (μs) */
#define INJ_DEAD_TIME_US          350   /* Injector dead time (μs) */

/* ====================================================================== */
/*  OMP (Oil Metering Port) Configuration                                 */
/* ====================================================================== */

/*
 * OMP controls oil flow to apex seals for lubrication.
 * State machine (omp_control_task_1825E):
 *   0 = OFF
 *   1 = ACTIVE
 *
 * Reads from RAM state variables:
 *   ram_a968, unk_FFFFA969, unk_FFFFA96A, unk_FFFFA96B, ram_a96c
 *
 * Hardware fault check: hwfault_reg (0xFFFF9ECD) bit 1
 * Control output: aux_ctrl_flags_write (0xFFFFA976)
 */

#define OMP_STATE_OFF             0
#define OMP_STATE_ACTIVE          1

/* OMP RAM addresses */
#define OMP_STATE_A968            (*(volatile uint8_t *)0xFFFFA968)
#define OMP_STATE_A969            (*(volatile uint8_t *)0xFFFFA969)
#define OMP_STATE_A96A            (*(volatile uint8_t *)0xFFFFA96A)
#define OMP_STATE_A96B            (*(volatile uint8_t *)0xFFFFA96B)
#define OMP_STATE_A96C            (*(volatile uint8_t *)0xFFFFA96C)

/* OMP hardware fault register (bit 1 = fault) */
#define OMP_HW_FAULT_REG          (*(volatile uint8_t *)0xFFFF9ECD)
#define OMP_HW_FAULT_BIT          0x02

/* OMP control output register */
#define OMP_CONTROL_OUTPUT        (*(volatile uint16_t *)0xFFFFA976)

/* ====================================================================== */
/*  10ms Cycle Configuration                                               */
/* ====================================================================== */

/*
 * main_engine_cycle_10ms (0x17F1C) runs every 10ms.
 * Counter 0xFFFFA964 increments each call and the 80ms subset runs once the
 * counter reaches CYCLE_80MS_DIVIDER (8), then resets (1 of 8 calls).
 *
 * 80ms tasks:
 *   - idle_speed_control_18054
 *   - fuel_pump_control_0x17510
 *   - exhaust_port_control
 *   - intake_air_control_0x177A6
 *   - torque_calc_with_damping
 *   - sub_17014
 *   - ctrl_continuation_17b24
 *
 * 10ms tasks:
 *   - omp_control_task_1825E
 */

#define CYCLE_10MS_PERIOD_US      10000 /* 10ms period (μs) */
#define CYCLE_80MS_DIVIDER        8     /* 80ms = 8 × 10ms */
#define CYCLE_COUNTER_MAX         7     /* 0-7 = 8 counts */

/* 10ms cycle counter RAM */
#define CYCLE_COUNTER_80MS        (*(volatile uint8_t *)0xFFFFA964)

/* ====================================================================== */
/*  Fuel Pipeline Configuration                                            */
/* ====================================================================== */

/*
 * main_fuel_control_pipeline_22094: 28 sequential function calls.
 * Pipeline order (from IDA analysis):
 *   1. calcCLorOLControl
 *   2. setClosedLoopBool
 *   3. calcOpenLoopFuelingTarget
 *   4. manifold_pressure_calc_21190
 *   5. fpu_threshold_accumulate_divide_33C84
 *   6. sequential_fuel_injection_211DC
 *   7. adaptive_ignition_table_213D0
 *   8. fuel_injection_duty_cycle_211CC
 *   9. complex_fpu_compare_calc_31650
 *   10. transmission_load_control_1DDB0
 *   11. secondaryAirRequestStuff
 *   ... (remaining 17 calls marked TODO)
 */

#define FUEL_PIPELINE_CALLS       28    /* Total pipeline calls */

/* ====================================================================== */
/*  Function Prototypes                                                   */
/* ====================================================================== */

/* --- Trigger Decode (eccentric shaft position) --- */

/**
 * crank_gap_detect — Detect missing tooth gap in trigger wheel.
 * ROM address: 0x7E60 (size 0x78)
 *
 * Detects the gap after tooth 5 in the 3x6+1 pattern.
 * Called on each crank sensor interrupt.
 * @param rotor_offset  Input rotor offset from caller (0 or 6, R4 on SH-2).
 */
void crank_gap_detect(uint8_t rotor_offset);

/**
 * crank_position_state_machine — Main eccentric shaft position FSM.
 * ROM address: 0x789E (size 0x20C)
 *
 * States: 0=idle, 1=searching, 2=partial_sync, 3=full_sync
 * Synchronizes to individual rotor faces.
 */
void crank_position_state_machine(void);

/**
 * rotor_position_synchronization — Synchronize rotor position.
 * ROM address: 0xAF10
 *
 * Determines which rotor face is at which eccentric shaft position.
 */
void rotor_position_synchronization(void);

/**
 * crank_timing_update — Trigger timing update (ISR entry).
 * ROM address: 0x7814 (size 0x8A)
 *
 * Called on each eccentric shaft tooth edge interrupt.
 * Reads timer capture, runs state machine, calls gap detect.
 */
void crank_timing_update(void);

/**
 * crank_sync_acquire — Acquire trigger sync.
 * ROM address: 0x7AAA (size 0x2C)
 *
 * Called from crank_timing_update when gap is detected.
 * R4 = rotor offset (0 or 6).
 */
void crank_sync_acquire(uint8_t rotor_offset);

/* --- Ignition System --- */

/**
 * outputPerRotorIgnitionDwell — Calculate per-rotor ignition dwell.
 * ROM address: 0x11218 (size 0x66)
 * @param rotor_idx  Rotor index (0-3, encodes leading/trailing)
 *
 * Uses 2D lookup table with per-rotor compensation.
 * Rotor 0/1 use can_addr_copy_57 (0xFFFFBC84).
 * Rotor 2/3 use can_addr_copy_58 (0xFFFFBC88).
 * Divides by constant from ROM:0x112DC.
 */
void outputPerRotorIgnitionDwell(uint8_t rotor_idx);

/**
 * calc_base_ignition_timing — Calculate base ignition timing.
 * ROM address: 0x11A9C
 *
 * Calls main_fuel_control_pipeline_22094.
 * Base timing from RPM/MAP 2D lookup.
 */
void calc_base_ignition_timing(void);

/**
 * ignition_timing_output — Final ignition timing output.
 * ROM address: 0x1E6B6
 *
 * 2D lookup + filtering for ignition coil drivers.
 */
void ignition_timing_output(void);

/* --- Fuel Injection System --- */

/**
 * sequential_fuel_injection — Sequential fuel injection control.
 * ROM address: 0x211DC (size 0x1F4)
 *
 * Reads can_addr_copy_225 (0xFFFFBF24), unk_FFFFB35C (fuel trim),
 * rotor A/B flags. Uses math_complement_2440 for duty cycle.
 */
void sequential_fuel_injection(void);

/**
 * fuel_injection_duty_cycle — Calculate injector duty cycle.
 * ROM address: 0x211CC
 *
 * fr2 = unk_FFFFB290 * unk_FFFFB29C, stored to unk_FFFFB28C.
 */
void fuel_injection_duty_cycle(void);

/**
 * manifold_pressure_calc — MAP sensor pressure calculation.
 * ROM address: 0x21190
 *
 * 2D lookup for manifold pressure.
 */
void manifold_pressure_calc(void);

/* --- Fuel Pipeline Call Targets --- */

/* Call 1 */
void calcCLorOLControl(void);
/* Call 2 */
void setClosedLoopBool(void);
/* Call 3 */
void calcOpenLoopFuelingTarget(void);
/* Call 5 */
void fpu_threshold_accumulate_divide(void);
/* Call 7 */
void adaptive_ignition_table(void);
/* Call 9 */
void complex_fpu_compare_calc(void);
/* Call 10 */
void transmission_load_control(void);
/* Call 11 */
void secondaryAirRequestStuff(void);
/* Call 12 */
void fuel_trim_update_control(void);
/* Call 14 */
void getRearO2FilteredValue(void);
/* Call 15 */
void wankel_rotary_control(void);
/* Call 16 */
void sensor_validation_monitor(void);
/* Call 17 */
void getMAFOpertionRange(void);
/* Call 18 */
void adaptive_control_logic(void);
/* Call 19 */
void fuel_trim_correction(void);
/* Call 20 */
void coolant_temp_boundary_check(void);
/* Call 22 */
void engine_load_control(void);
/* Call 24 */
void oil_temp_burn_control(void);
/* Call 25 */
void knock_sensor_voltage_limit_check(void);
/* Call 26 */
void idle_speed_range_validator(void);
/* Call 27 */
void cold_start_rpm_limiter(void);

/* --- OMP Control --- */

/**
 * omp_control_task — OMP state machine and control.
 * ROM address: 0x1825E (size 0x2F4)
 *
 * Reads OMP state variables, checks hardware fault,
 * dispatches based on state (0=off, 1=active).
 * Updates control output register.
 */
void omp_control_task(void);

/* --- 10ms Main Cycle --- */

/**
 * main_engine_cycle_10ms — Core 10ms engine control task.
 * ROM address: 0x17F1C (size 0x60)
 *
 * Called every 10ms. Runs OMP every 10ms.
 * Runs subset tasks every 80ms (7 out of 8 calls).
 */
void main_engine_cycle_10ms(void);

/* --- Fuel Pipeline --- */

/**
 * main_fuel_control_pipeline — 28-call fuel control pipeline.
 * ROM address: 0x22094 (size 0xB4)
 *
 * Sequential calls for fuel/ignition calculation.
 */
void main_fuel_control_pipeline(void);

/* --- 80ms Subsystem Tasks --- */

/**
 * idle_speed_control — Idle speed control (80ms).
 * ROM address: 0x18054
 */
void idle_speed_control(void);

/**
 * fuel_pump_control — Fuel pump relay control (80ms).
 * ROM address: 0x17510
 */
void fuel_pump_control(void);

/**
 * exhaust_port_control — Exhaust port timing (80ms).
 * ROM address: 0x17700
 */
void exhaust_port_control(void);

/**
 * intake_air_control — Intake air control (80ms).
 * ROM address: 0x177A6
 */
void intake_air_control(void);

/**
 * torque_calc_with_damping — Torque calculation with damping (80ms).
 * ROM address: 0x17952
 */
void torque_calc_with_damping(void);

/**
 * sub_17014 — 80ms subsystem task.
 * ROM address: 0x17014
 */
void sub_17014(void);

/**
 * ctrl_continuation_17b24 — 80ms control continuation task.
 * ROM address: 0x17B24
 */
void ctrl_continuation_17b24(void);

/* --- Sensor Validation --- */

/**
 * sensor_validation — Validate sensor inputs.
 * ROM address: 0x1F078 (sensor_validation_monitor)
 */
void sensor_validation(void);

/**
 * combustion_control_loop — Combustion control feedback loop.
 * ROM address: 0x1F8E0
 */
void combustion_control_loop(void);

/**
 * ignition_timing_safety_check — Ignition timing safety limits.
 * ROM address: 0x1FAEA
 */
void ignition_timing_safety_check(void);

#endif /* ENGINE_H */
