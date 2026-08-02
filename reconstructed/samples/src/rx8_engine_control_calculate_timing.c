/*
 * =============================================================================
 * rx8_engine_control_calculate_timing.c  —  MASTER ENGINE-CONTROL DISPATCH HUB
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x14584  (code 0x14584..0x14720, literal pool 0x14784..0x1488C;
 *               414 bytes)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_engine_control_calculate_timing.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + N random
 *               initial-SR vectors; bit-exact final SR, r4/final-setSR argument,
 *               r15 and the two dispatcher stack cells, plus a bit-exact
 *               comparison of the full 68-entry dispatch call sequence;
 *               0 mismatches).
 * Lift (truth): c/engineControlCalculateTiming.c  (engineControlCalculateTiming
 *               @ 0x14584, same address, same size)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The largest flat dispatch function in the callgraph: called once per
 * scheduler tick from engineControlTASK (0x11E94) as the 3rd of 5 control
 * stages.  It is a zero-branch sequence of 66 unconditional calls covering
 * every major engine subsystem (knock, cooling, fuel trim, air, emissions,
 * diagnostics, ignition, rotor sync, fuel pump, ...) split into two phases by
 * an interrupt-mask barrier.  Disassembly of 60E1D400.bin @ 0x14584
 * (condensed, see c/ for the full trace):
 *
 *     4F22   sts.l  pr,@-r15             ; push return address (-> 0xFFFFDEFC)
 *     7FFC   add    #-4,r15              ; allocate the saved-SR slot
 *     D37E   mov.l  @(0x7E,pc),r3 = 0x3920   ; getSR
 *     430B   jsr    @r3                  ; call getSR(16)
 *     E410   mov    #0x10,r4             ;   (delay) r4 = IMASK level 16
 *     D37E   mov.l  @(0x7E,pc),r3 = 0x14B04  ; incomplete_stack_save_r14_r13
 *     430B   jsr    @r3
 *     2F02   mov.l  r0,@r15              ;   (delay) [r15] = SR & 0xF0 (saved)
 *     ... 8 phase-1 jsr's (knock/cooling subsystems) ...
 *     mov.l  @(..,pc),r3 = 0x3934 ; jsr @r3 ; mov.l @r15,r4  ; setSR(saved_sr)
 *     mov.l  @(..,pc),r2 = 0x3920 ; jsr @r2 ; mov #0x10,r4   ; getSR(16) again
 *     ... 55 phase-2 jsr's (fuel/air/emissions/diag subsystems) ...
 *     mov.l  r0,@r15                    ;   (delay) [r15] = re-saved SR
 *     mov.l  @r15+,r4                    ; pop the re-saved SR into r4
 *     mov.l  @(..,pc),r3 = 0x3934
 *     jmp    @r3                         ; TAIL-CALL setSR(re-saved SR)
 *     lds.l  @r15+,pr                    ;   (delay) pop the return address
 *
 * CALLING CONVENTION
 * ------------------
 * `void rx8_engine_control_calculate_timing(void)` — normal ABI entry, no
 * input registers, no meaningful return value.  The two context helpers do
 * take a register argument (the only argument setup in the whole function):
 * r4 = 16 for getSR and r4 = saved SR for setSR.  All 63 subsystem callees
 * are `void(void)` — they communicate exclusively through global RAM.
 *
 * The dispatcher itself has NO RAM/calibration inputs and NO branches: its
 * whole observable behaviour is (a) the exact dispatch sequence, (b) the
 * interrupt-mask save/restore pair, and (c) two stack cells.  The equivalence
 * check therefore compares those, not subsystem RAM side-effects (on the host
 * the 63 subsystems are recording stubs; in the emulator the REAL ROM bytes
 * of every subsystem run, exactly as they do in the c/ track-A rigs).
 *
 * SR SEMANTICS (getSR @0x3920 / setSR @0x3934, verified against the ROM)
 * ---------------------------------------------------------------------
 *   - getSR(16): returns r0 = SR & 0xF0 (the interrupt-mask field); if that
 *     field is BELOW the requested level (16), SR is raised to 16 in the rts
 *     delay slot (`cmp/hi` + `ldc r4,SR`).  The 0xF0 mask is hard-coded in
 *     the ROM.
 *   - setSR(r4): `ldc r4,SR` — restores SR to the argument.  The r4 == 0
 *     special path (kernel detour through 0x3DB0) is NOT exercised by the
 *     harness (see DISCREPANCIES).
 *   Net effect on this function: for an entry SR with (SR & 0xF0) >= 0x10
 *   the mask field is unchanged and the final SR equals (SR_entry & 0xF0);
 *   the barrier "restores then re-saves" is a no-op on the value.
 *
 * RAM SIDE EFFECTS (dispatcher's own; subsystem callees listed in the header
 * of each subsystem lift — they run as real ROM bytes in the emulator and are
 * stubbed on the host, so their cells are NOT compared here)
 * -------------------------------------------------------------------------
 *   WRITE 0xFFFFDEF8 u32 saved-SR slot  (phase-1 value, then re-saved value)
 *   WRITE 0xFFFFDEFC u32 saved return address (0xEEEE0000 = emulator sentinel)
 *   r15 balanced to 0xFFFFDF00 at return; r4 = re-saved SR at return.
 *   No other RAM is touched by the dispatcher itself.
 *
 * CALIBRATION (fixed ROM)
 * -----------------------
 * None read by the dispatcher itself.  Every calibration table lives inside
 * the 63 subsystem callees (e.g. the ignition tables of 0x13C2C); those bytes
 * run for real in the emulator and are stubbed on the host.
 *
 * INTERNAL CALLEES (66; order = the exact dispatch order below)
 * -------------------------------------------------------------
 *   0x003920 getSR(16)                    0x014B04 incomplete_stack_save
 *   Phase 1 (8):  0x121F0 0x1237C 0x13A0E 0x13A5E 0x13A86 0x13B90 0x13C2C
 *                 0x17DCC
 *   0x003934 setSR (barrier)  →  0x003920 getSR(16) (re-save)
 *   Phase 2 (55): 0x1379C 0x138CC 0x13F68 0x1408C 0x141B8 0x1412A 0x12BC8
 *                 0x13070 0x19220 0x44B1C 0x44B9A 0x43C4A 0x43E90 0x43E60
 *                 0x43E00 0x44AB2 0x43EE8 0x43F56 0x44076 0x4409E 0x440DE
 *                 0x44206 0x4416C 0x442E8 0x44370 0x443A2 0x44506 0x44530
 *                 0x4490A 0x445AA 0x44694 0x446BC 0x44748 0x44782 0x447B0
 *                 0x44824 0x12938 0x128C4 0x126EA 0x126CA 0x1252C 0x12A48
 *                 0x128FE 0x127DE 0x126DA 0x1261C 0x135F6 0x13652 0x14A5C
 *                 0x14A92 0x1061A 0x1117A 0x2CBBA 0x2CC1C 0x4D0E8
 *   0x003934 setSR (tail-call, re-saved SR)
 *
 * LIFT-vs-ROM DISCREPANCIES
 * -------------------------
 * None in the dispatch logic: c/engineControlCalculateTiming.c matches the
 * 60E1D400.bin bytes instruction-for-instruction, including the exact phase-2
 * order, the barrier and the tail-call restore.  Two lift/ROM points are
 * pinned here, not fixed (the ROM wins):
 *   1. setSR's r4 == 0 path detours through the kernel routine 0x3DB0
 *      (reads 0xFFFF72B0/0xFFFF72C8 etc.).  The host model implements only
 *      the r4 != 0 path; the harness vectors therefore keep the saved SR
 *      non-zero ((SR_entry & 0xF0) >= 0x10), which is also the only regime
 *      where the ROM leaves the return-address stack cell at 0xFFFFDEFC
 *      intact (0x3DB0 overwrites it when reached).
 *   2. getSR's `mask` argument (r4 = 16) is an interrupt-mask LEVEL, not a
 *      mask; the model raises SR to 16 only when (SR & 0xF0) < 16.
 * =============================================================================
 */
#include <stdint.h>

/* ---- context / interrupt-mask helpers (r4-based; see header) ---- */
extern uint32_t rx8_getSR(uint32_t imask_level);          /* 0x003920 */
extern void     rx8_setSR(uint32_t sr);                   /* 0x003934 */
extern void     rx8_incomplete_stack_save_r14_r13(void);  /* 0x014B04 */

/* ---- Phase-1 subsystems (8) ---- */
extern void rx8_calc_combustion_efficiency_metric(void);  /* 0x121F0 */
extern void rx8_calc_combustion_load_factor(void);        /* 0x1237C */
extern void rx8_get_knock_control_allowed(void);          /* 0x13A0E */
extern void rx8_get_knock_sensor_faulted_status(void);    /* 0x13A5E */
extern void rx8_get_knock_control_active(void);           /* 0x13A86 */
extern void rx8_update_knock_max_ram(void);               /* 0x13B90 */
extern void rx8_calc_ignition_all_rotors_13c2c(void);     /* 0x13C2C */
extern void rx8_cooling_fan_control(void);                /* 0x17DCC */

/* ---- Phase-2 subsystems (55) ---- */
extern void rx8_calc_adaptive_fuel_trim(void);            /* 0x1379C */
extern void rx8_calc_accel_fuel_enrichment(void);         /* 0x138CC */
extern void rx8_calc_barometric_pressure_trim(void);      /* 0x13F68 */
extern void rx8_read_fuel_pressure_feedback_status(void); /* 0x1408C */
extern void rx8_calc_closed_loop_fuel_status(void);       /* 0x141B8 */
extern void rx8_read_o2_sensor_voltage_trim(void);        /* 0x1412A */
extern void rx8_calc_rotor_sync_idle_gate_b(void);        /* 0x12BC8 */
extern void rx8_read_engine_speed_status(void);           /* 0x13070 */
extern void rx8_dsc_related_timing(void);                 /* 0x19220 */
extern void rx8_sensor_range_calc(void);                  /* 0x44B1C */
extern void rx8_sensor_abs_deviation(void);               /* 0x44B9A */
extern void rx8_calculate_driver_conditions(void);        /* 0x43C4A */
extern void rx8_knock_sensor_threshold(void);             /* 0x43E90 */
extern void rx8_rpm_limiter_calc(void);                   /* 0x43E60 */
extern void rx8_air_bypass_control(void);                 /* 0x43E00 */
extern void rx8_fuel_enable_logic(void);                  /* 0x44AB2 */
extern void rx8_air_bleed_control(void);                  /* 0x43EE8 */
extern void rx8_exhaust_control(void);                    /* 0x43F56 */
extern void rx8_sensor_signal_calc(void);                 /* 0x44076 */
extern void rx8_fuel_pressure_calc(void);                 /* 0x4409E */
extern void rx8_catalyst_control(void);                   /* 0x440DE */
extern void rx8_lambda_control_calc(void);                /* 0x44206 */
extern void rx8_emissions_control(void);                  /* 0x4416C */
extern void rx8_fault_code_handler(void);                 /* 0x442E8 */
extern void rx8_fuel_correction_update(void);             /* 0x44370 */
extern void rx8_func_0443a2(void);                        /* 0x443A2 */
extern void rx8_fpu_clear_result(void);                   /* 0x44506 */
extern void rx8_readiness_check(void);                    /* 0x44530 */
extern void rx8_fuel_cut_logic(void);                     /* 0x4490A */
extern void rx8_calc_decel_fuel_cut_445aa(void);          /* 0x445AA */
extern void rx8_intake_condition_check(void);             /* 0x44694 */
extern void rx8_ignition_advance_interp(void);            /* 0x446BC */
extern void rx8_sensor_select_check(void);                /* 0x44748 */
extern void rx8_rpm_neutral_calc(void);                   /* 0x44782 */
extern void rx8_idle_correction_interp(void);             /* 0x447B0 */
extern void rx8_knock_control_calc(void);                 /* 0x44824 */
extern void rx8_calc_combustion_chamber_temp(void);       /* 0x12938 */
extern void rx8_write_knock_detected_flag(void);          /* 0x128C4 */
extern void rx8_calc_rotor_a_pressure_load(void);         /* 0x126EA */
extern void rx8_add_fuel_pressure_correction(void);       /* 0x126CA */
extern void rx8_calc_intake_pressure_pid_output(void);    /* 0x1252C */
extern void rx8_calc_rotor_b_knock_flag(void);            /* 0x12A48 */
extern void rx8_write_rotor_a_knock_flag(void);           /* 0x128FE */
extern void rx8_calc_rotor_b_pressure_load(void);         /* 0x127DE */
extern void rx8_add_rotor_timing_offset(void);            /* 0x126DA */
extern void rx8_calc_vis_solenoid_duty_cycle(void);       /* 0x1261C */
extern void rx8_calc_fuel_pump_duty_trim(void);           /* 0x135F6 */
extern void rx8_calc_evap_purge_duty(void);               /* 0x13652 */
extern void rx8_fpu_conditional_accumulate_pair_ch0(void);/* 0x14A5C */
extern void rx8_fpu_conditional_accumulate_pair_ch1(void);/* 0x14A92 */
extern void rx8_sensor_filter_apply_all(void);            /* 0x1061A */
extern void rx8_get_engine_cranking_status(void);         /* 0x1117A */
extern void rx8_filter_signal_adaptive(void);             /* 0x2CBBA */
extern void rx8_check_fuel_pump_relay_enable(void);       /* 0x2CC1C */
extern void rx8_health_check_system(void);                /* 0x4D0E8 */

/* ============================================================================
 * engineControlCalculateTiming — once-per-tick engine control dispatch.
 *
 * Phase 1  — save the interrupt-mask field, run the 8 time-critical knock /
 *            cooling subsystems, restore the mask.
 * Barrier  — restore SR then re-save it (no-op on the value for normal IMASK,
 *            see SR SEMANTICS above).
 * Phase 2  — run the remaining 55 subsystems (fuel, air, emissions, ignition,
 *            rotor sync, diagnostics, fuel pump, ...).
 * Restore  — tail-call setSR(re-saved SR) with r4 = re-saved SR.
 * ==========================================================================*/
void rx8_engine_control_calculate_timing(void)
{
    uint32_t saved_sr;

    /* ---- Phase 1: context save + time-critical subsystems ---- */
    saved_sr = rx8_getSR(16);              /* SR & 0xF0; SR raised to 16 if low */
    rx8_incomplete_stack_save_r14_r13();   /* push r14/r13 (interrupt context) */

    rx8_calc_combustion_efficiency_metric();
    rx8_calc_combustion_load_factor();
    rx8_get_knock_control_allowed();
    rx8_get_knock_sensor_faulted_status();
    rx8_get_knock_control_active();
    rx8_update_knock_max_ram();
    rx8_calc_ignition_all_rotors_13c2c();
    rx8_cooling_fan_control();

    /* ---- Phase 1 -> 2 barrier: restore SR, then re-save ---- */
    rx8_setSR(saved_sr);                   /* restore the original mask field */
    saved_sr = rx8_getSR(16);              /* re-save (possibly raised) field  */

    /* ---- Phase 2: bulk subsystem dispatch ---- */
    rx8_calc_adaptive_fuel_trim();
    rx8_calc_accel_fuel_enrichment();
    rx8_calc_barometric_pressure_trim();
    rx8_read_fuel_pressure_feedback_status();
    rx8_calc_closed_loop_fuel_status();
    rx8_read_o2_sensor_voltage_trim();
    rx8_calc_rotor_sync_idle_gate_b();
    rx8_read_engine_speed_status();
    rx8_dsc_related_timing();
    rx8_sensor_range_calc();
    rx8_sensor_abs_deviation();
    rx8_calculate_driver_conditions();
    rx8_knock_sensor_threshold();
    rx8_rpm_limiter_calc();
    rx8_air_bypass_control();
    rx8_fuel_enable_logic();
    rx8_air_bleed_control();
    rx8_exhaust_control();
    rx8_sensor_signal_calc();
    rx8_fuel_pressure_calc();
    rx8_catalyst_control();
    rx8_lambda_control_calc();
    rx8_emissions_control();
    rx8_fault_code_handler();
    rx8_fuel_correction_update();
    rx8_func_0443a2();
    rx8_fpu_clear_result();
    rx8_readiness_check();
    rx8_fuel_cut_logic();
    rx8_calc_decel_fuel_cut_445aa();
    rx8_intake_condition_check();
    rx8_ignition_advance_interp();
    rx8_sensor_select_check();
    rx8_rpm_neutral_calc();
    rx8_idle_correction_interp();
    rx8_knock_control_calc();
    rx8_calc_combustion_chamber_temp();
    rx8_write_knock_detected_flag();
    rx8_calc_rotor_a_pressure_load();
    rx8_add_fuel_pressure_correction();
    rx8_calc_intake_pressure_pid_output();
    rx8_calc_rotor_b_knock_flag();
    rx8_write_rotor_a_knock_flag();
    rx8_calc_rotor_b_pressure_load();
    rx8_add_rotor_timing_offset();
    rx8_calc_vis_solenoid_duty_cycle();
    rx8_calc_fuel_pump_duty_trim();
    rx8_calc_evap_purge_duty();
    rx8_fpu_conditional_accumulate_pair_ch0();
    rx8_fpu_conditional_accumulate_pair_ch1();
    rx8_sensor_filter_apply_all();
    rx8_get_engine_cranking_status();
    rx8_filter_signal_adaptive();
    rx8_check_fuel_pump_relay_enable();
    rx8_health_check_system();

    /* ---- Restore context and return (tail-call setSR) ---- */
    rx8_setSR(saved_sr);
}
