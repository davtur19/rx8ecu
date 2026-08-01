/* engineControlCalculateTiming.c
 *
 * ROM: 60E1D400  |  Address: 0x14584  |  Size: 414 bytes
 *
 * === DISASSEMBLY (SH-2E (SH7055), big-endian) ===
 *
 * engineControlCalculateTimeting:
 *   ; === Phase 1: context save ===
 *   0x14584: sts.l pr,@-r15          ; push return address
 *   0x14586: add #-4,r15             ; allocate 4 bytes on stack
 *   0x14588: mov.l 0x14784,r3        ; load getSR(0x3920)
 *   0x1458A: jsr @r3                 ; call getSR(16)
 *   0x1458C: mov #16,r4              ; delay slot: arg = 16
 *
 *   0x1458E: mov.l 0x14788,r3        ; load incomplete_stack_save_r14_r13
 *   0x14590: jsr @r3
 *   0x14592: mov.l r0,@r15           ; delay slot: store SR on stack
 *
 *   ; === Phase 1: 8 subsystem calls ===
 *   0x14594: mov.l 0x1478c,r2  ; calc_combustion_efficiency_metric
 *   0x14596: jsr @r2
 *   0x14598: nop
 *   0x1459A: mov.l 0x14790,r3  ; calc_combustion_load_factor
 *   0x1459C: jsr @r3
 *   0x1459E: nop
 *   0x145A0: mov.l 0x14794,r2  ; getKnockControlAllowed
 *   0x145A2: jsr @r2
 *   0x145A4: nop
 *   0x145A6: mov.l 0x14798,r3  ; getKnockSensorFaultedStatus
 *   0x145A8: jsr @r3
 *   0x145AA: nop
 *   0x145AC: mov.l 0x1479c,r2  ; getKnockControlActive
 *   0x145AE: jsr @r2
 *   0x145B0: nop
 *   0x145B2: mov.l 0x147a0,r3  ; updateKnockMaxRAM
 *   0x145B4: jsr @r3
 *   0x145B6: nop
 *   0x145B8: mov.l 0x147a4,r2  ; calc_ignition_all_rotors_13C2C
 *   0x145BA: jsr @r2
 *   0x145BC: nop
 *   0x145BE: mov.l 0x147a8,r3  ; cooling_fan_control_0x17DCC
 *   0x145C0: jsr @r3
 *   0x145C2: nop
 *
 *   ; === Phase 1→2 barrier: restore SR, then re-save ===
 *   0x145C4: mov.l 0x147ac,r3  ; load setSR (0x3934)
 *   0x145C6: jsr @r3
 *   0x145C8: mov.l @r15,r4     ; delay slot: arg = saved SR
 *   0x145CA: mov.l 0x14784,r2  ; load getSR (0x3920)
 *   0x145CC: jsr @r2
 *   0x145CE: mov #16,r4        ; delay slot: arg = 16
 *
 *   ; === Phase 2: 56 subsystem calls ===
 *   0x145D0: mov.l 0x147b0,r3  ; calc_adaptive_fuel_trim (0x1379C)
 *   0x145D2: jsr @r3
 *   0x145D4: mov.l r0,@r15     ; delay slot: store new SR
 *   0x145D6: mov.l 0x147b4,r2  ; calc_accel_fuel_enrichment
 *   ... 55 more calls ...
 *
 *   ; === Restore and return ===
 *   0x1471A: mov.l @r15+,r4    ; pop saved SR
 *   0x1471C: mov.l 0x147ac,r3  ; load setSR
 *   0x1471E: jmp @r3           ; tail-call setSR(saved_sr)
 *   0x14720: lds.l @r15+,pr    ; delay slot: pop return address
 */

#include <stdint.h>

/* ========================================================================
 * Forward declarations of all 66 callees.
 *
 * All subfunctions operate on global RAM/registers with no explicit
 * parameters or return values (void(void) convention inferred from
 * disassembly).  Verified exceptions are noted.
 * ======================================================================== */

/* --- Context / SR management --- */
extern uint32_t getSR(uint32_t mask);    /* r4 = 16 (IMASK bits?) */
extern void     setSR(uint32_t sr);      /* restores saved status register */
extern void     incomplete_stack_save_r14_r13(void);  /* 0x14B04 */

/* --- Combustion / load --- */
extern void calc_combustion_efficiency_metric(void);   /* 0x121F0 */
extern void calc_combustion_load_factor(void);          /* 0x1237C */

/* --- Knock detection & control --- */
extern void getKnockControlAllowed(void);              /* 0x13A0E */
extern void getKnockSensorFaultedStatus(void);         /* 0x13A5E */
extern void getKnockControlActive(void);               /* 0x13A86 */
extern void updateKnockMaxRAM(void);                   /* 0x13B90 */
extern void calc_ignition_all_rotors_13C2C(void);       /* 0x13C2C */
extern void cooling_fan_control(void);                 /* 0x17DCC */

/* --- Fuel trim / adaptation --- */
extern void calc_adaptive_fuel_trim(void);             /* 0x1379C */
extern void calc_accel_fuel_enrichment(void);          /* 0x138CC */
extern void calc_barometric_pressure_trim(void);       /* 0x13F68 */
extern void read_fuel_pressure_feedback_status(void);  /* 0x1408C */
extern void calc_closed_loop_fuel_status(void);        /* 0x141B8 */
extern void read_o2_sensor_voltage_trim(void);         /* 0x1412A */

/* --- Rotor-sync control --- */
extern void calc_rotor_sync_idle_gate_B(void);           /* 0x12BC8 */

/* --- Engine speed / sensors --- */
extern void read_engine_speed_status(void);            /* 0x13070 */
extern void dscRelatedTiming(void);                    /* 0x19220 */

/* --- Sensor range & calibration --- */
extern void sensor_range_calc(void);                   /* 0x44B1C */
extern void sensor_abs_deviation(void);                /* 0x44B9A */

/* --- Driver conditions --- */
extern void calculateDriverConditions(void);           /* 0x43C4A */

/* --- Knock & RPM limits --- */
extern void knock_sensor_threshold(void);              /* 0x43E90 */
extern void rpm_limiter_calc(void);                    /* 0x43E60 */

/* --- Air control --- */
extern void air_bypass_control(void);                  /* 0x43E00 */
extern void air_bleed_control(void);                   /* 0x43EE8 */

/* --- Exhaust / emissions --- */
extern void exhaust_control(void);                     /* 0x43F56 */
extern void sensor_signal_calc(void);                  /* 0x44076 */
extern void fuel_pressure_calc(void);                  /* 0x4409E */
extern void catalyst_control(void);                    /* 0x440DE */
extern void lambda_control_calc(void);                 /* 0x44206 */
extern void emissions_control(void);                   /* 0x4416C */

/* --- Fuel system --- */
extern void fuel_enable_logic(void);                   /* 0x44AB2 */
extern void fuel_cut_logic(void);                      /* 0x4490A */
extern void calc_decel_fuel_cut_445AA(void);             /* 0x445AA */
extern void fuel_correction_update(void);              /* 0x44370 */

/* --- Diagnostics / faults --- */
extern void fault_code_handler(void);                  /* 0x442E8 */
extern void func_0443A2(void);                         /* 0x443A2 */
extern void readiness_check(void);                     /* 0x44530 */
extern void health_check_system(void);                 /* 0x4D0E8 */

/* --- FPU / signal processing --- */
extern void fpu_clear_result(void);                    /* 0x44506 */
extern void fpu_conditional_accumulate_pair_ch0(void); /* 0x14A5C */
extern void fpu_conditional_accumulate_pair_ch1(void); /* 0x14A92 */
extern void sensor_filter_apply_all(void);             /* 0x1061A */
extern void filter_signal_adaptive(void);              /* 0x2CBBA */

/* --- Ignition --- */
extern void ignition_advance_interp(void);             /* 0x446BC */

/* --- Engine state / intake --- */
extern void intake_condition_check(void);              /* 0x44694 */
extern void sensor_select_check(void);                 /* 0x44748 */
extern void rpm_neutral_calc(void);                    /* 0x44782 */
extern void idle_correction_interp(void);              /* 0x447B0 */
extern void knock_control_calc(void);                  /* 0x44824 */
extern void getEngineCrankingStatus(void);             /* 0x1117A */

/* --- Combustion chamber / per-rotor --- */
extern void calc_combustion_chamber_temp(void);        /* 0x12938 */
extern void write_knock_detected_flag(void);           /* 0x128C4 */
extern void calc_rotor_A_pressure_load(void);          /* 0x126EA */
extern void add_fuel_pressure_correction(void);        /* 0x126CA */
extern void calc_intake_pressure_pid_output(void);     /* 0x1252C */
extern void calc_rotor_B_knock_flag(void);             /* 0x12A48 */
extern void write_rotor_A_knock_flag(void);            /* 0x128FE */
extern void calc_rotor_B_pressure_load(void);          /* 0x127DE */
extern void add_rotor_timing_offset(void);             /* 0x126DA */
extern void calc_vis_solenoid_duty_cycle(void);        /* 0x1261C */

/* --- Fuel pump / evap --- */
extern void calc_fuel_pump_duty_trim(void);            /* 0x135F6 */
extern void calc_evap_purge_duty(void);                /* 0x13652 */
extern void check_fuel_pump_relay_enable(void);        /* 0x2CC1C */


/* ========================================================================
 * engineControlCalculateTiming
 *
 * The main engine control dispatch hub — called once per scheduler tick
 * from engineControlTASK (0x11E94).  Orchestrates 66 subfunctions covering
 * every major engine subsystem.
 *
 * Structure:
 *   Phase 1 — Save context, call 8 time-critical subsystems (knock, cooling)
 *   Barrier — Restore SR, re-save (interrupt priority change?)
 *   Phase 2 — Call remaining 56 subsystems (fuel, air, emissions, etc.)
 *   Restore — Pop saved SR and return
 *
 * NOTE: This is a BEHAVIOR sketch.  The ROM implements the dispatch via a
 * flat jump table at 0x14784–0x14888 with zero branches.  Every callee is
 * called unconditionally every invocation.  All subfunctions operate on
 * global RAM — no parameters are passed.
 * ======================================================================== */
void engineControlCalculateTiming(void)
{
    uint32_t saved_sr;

    /* ---- Phase 1 ---- */
    saved_sr = getSR(16);                /* save status register (IMASK) */
    incomplete_stack_save_r14_r13();     /* push r14, r13 */

    calc_combustion_efficiency_metric(); /* 0x121F0 */
    calc_combustion_load_factor();       /* 0x1237C */
    getKnockControlAllowed();            /* 0x13A0E */
    getKnockSensorFaultedStatus();       /* 0x13A5E */
    getKnockControlActive();             /* 0x13A86 */
    updateKnockMaxRAM();                 /* 0x13B90 */
    calc_ignition_all_rotors_13C2C();   /* 0x13C2C */
    cooling_fan_control();               /* 0x17DCC */

    /* ---- Barrier: restore SR, then re-save ---- */
    setSR(saved_sr);                     /* restore original interrupt mask */
    saved_sr = getSR(16);                /* re-save (possibly new mask) */

    /* ---- Phase 2: bulk subsystem dispatch ---- */
    calc_adaptive_fuel_trim();           /* 0x1379C */
    calc_accel_fuel_enrichment();        /* 0x138CC */
    calc_barometric_pressure_trim();     /* 0x13F68 */
    read_fuel_pressure_feedback_status();/* 0x1408C */
    calc_closed_loop_fuel_status();      /* 0x141B8 */
    read_o2_sensor_voltage_trim();       /* 0x1412A */

    calc_rotor_sync_idle_gate_B();       /* 0x12BC8 */
    read_engine_speed_status();          /* 0x13070 */
    dscRelatedTiming();                  /* 0x19220 */

    sensor_range_calc();                 /* 0x44B1C */
    sensor_abs_deviation();              /* 0x44B9A */
    calculateDriverConditions();         /* 0x43C4A */

    knock_sensor_threshold();            /* 0x43E90 */
    rpm_limiter_calc();                  /* 0x43E60 */
    air_bypass_control();                /* 0x43E00 */
    fuel_enable_logic();                 /* 0x44AB2 */
    air_bleed_control();                 /* 0x43EE8 */
    exhaust_control();                   /* 0x43F56 */

    sensor_signal_calc();                /* 0x44076 */
    fuel_pressure_calc();                /* 0x4409E */
    catalyst_control();                  /* 0x440DE */
    lambda_control_calc();               /* 0x44206 */
    emissions_control();                 /* 0x4416C */

    fault_code_handler();                /* 0x442E8 */
    fuel_correction_update();            /* 0x44370 */
    func_0443A2();                       /* 0x443A2 (unknown) */
    fpu_clear_result();                  /* 0x44506 */
    readiness_check();                   /* 0x44530 */

    fuel_cut_logic();                    /* 0x4490A */
    calc_decel_fuel_cut_445AA();         /* 0x445AA */
    intake_condition_check();            /* 0x44694 */
    ignition_advance_interp();           /* 0x446BC */
    sensor_select_check();               /* 0x44748 */
    rpm_neutral_calc();                  /* 0x44782 */
    idle_correction_interp();            /* 0x447B0 */
    knock_control_calc();                /* 0x44824 */

    calc_combustion_chamber_temp();      /* 0x12938 */
    write_knock_detected_flag();         /* 0x128C4 */
    calc_rotor_A_pressure_load();        /* 0x126EA */
    add_fuel_pressure_correction();      /* 0x126CA */
    calc_intake_pressure_pid_output();   /* 0x1252C */
    calc_rotor_B_knock_flag();           /* 0x12A48 */
    write_rotor_A_knock_flag();          /* 0x128FE */
    calc_rotor_B_pressure_load();        /* 0x127DE */
    add_rotor_timing_offset();           /* 0x126DA */
    calc_vis_solenoid_duty_cycle();      /* 0x1261C */

    calc_fuel_pump_duty_trim();          /* 0x135F6 */
    calc_evap_purge_duty();              /* 0x13652 */

    fpu_conditional_accumulate_pair_ch0();/* 0x14A5C */
    fpu_conditional_accumulate_pair_ch1();/* 0x14A92 */

    sensor_filter_apply_all();           /* 0x1061A */
    getEngineCrankingStatus();           /* 0x1117A */
    filter_signal_adaptive();            /* 0x2CBBA */
    check_fuel_pump_relay_enable();      /* 0x2CC1C */
    health_check_system();               /* 0x4D0E8 */

    /* ---- Restore context and return ---- */
    setSR(saved_sr);
}
