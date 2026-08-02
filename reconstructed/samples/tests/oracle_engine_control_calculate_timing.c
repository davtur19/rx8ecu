/* ============================================================================
 * oracle_engine_control_calculate_timing.c  —  host test rig for
 * rx8_engine_control_calculate_timing @0x14584
 * ============================================================================
 * Compile together with src/rx8_engine_control_calculate_timing.c and pipe
 * test vectors on stdin; one vector per line, one hex token:
 *
 *     ect <sr_entry>
 *           -> <sr_final> <set_arg> <stack_sr> <stack_pr> <r15> <seq...>
 *
 *   <sr_entry> : initial SH-2 status register (SR) value; the harness keeps
 *                (sr_entry & 0xF0) >= 0x10 so every setSR call takes the ROM's
 *                simple `ldc r4,SR` path (see DISCREPANCIES in the source).
 *   <sr_final> : SR after the whole dispatch == (sr_entry & 0xF0).
 *   <set_arg>  : r4 argument of the final tail-call setSR == the re-saved SR.
 *   <stack_sr> : the ROM's saved-SR stack slot 0xFFFFDEF8 (== <set_arg>).
 *   <stack_pr> : the ROM's saved-return-address slot 0xFFFFDEFC
 *                (0xEEEE0000 = the emulator's SENT sentinel).
 *   <r15>      : stack pointer at return (0xFFFFDF00).
 *   <seq...>   : the 68-entry dispatch call sequence, each token the ROM
 *                address of the callee, in call order.  The emulator side is
 *                recorded the same way (jsr/jmp targets whose call site lies
 *                inside 0x14584..0x14722) so the sequences compare 1:1.
 *
 * The function under test is a pure dispatcher: it has no RAM inputs and no
 * calibration pages of its own (every table lives inside the 63 subsystem
 * callees, which execute as REAL ROM bytes in the emulator and are recording
 * stubs here), so the oracle seeds only the model SR and prints the
 * dispatcher's own observables.  It contains NO copy of the dispatch logic —
 * that lives solely in the reconstructed source; the stubs below only record
 * the call order and implement the getSR/setSR interrupt-mask model.
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

/* 0x14584 — see src/rx8_engine_control_calculate_timing.c. */
void rx8_engine_control_calculate_timing(void);

/* ---- model state -------------------------------------------------------- */
static uint32_t g_sr;         /* model of the SH-2 status register          */
static uint32_t g_last_set;   /* r4 argument of the most recent setSR call  */
static uint32_t g_seq[68];    /* dispatch call sequence (ROM addresses)     */
static int      g_seqlen;

#define REC(addr) (g_seq[g_seqlen++] = (uint32_t)(addr))

/* ---- context helpers (ROM 0x3920 / 0x3934 / 0x14B04) ------------------- */

/* getSR(16): returns SR & 0xF0; if that mask field is below the requested
 * IMASK level the ROM raises SR to that level in the rts delay slot. */
uint32_t rx8_getSR(uint32_t imask_level)
{
    uint32_t r0;
    REC(0x003920u);
    r0 = g_sr & 0xF0u;
    if (r0 < imask_level)
        g_sr = imask_level;
    return r0;
}

/* setSR(r4): `ldc r4,SR`.  The ROM's r4 == 0 kernel detour (0x3DB0) is NOT
 * modelled; the harness keeps the saved SR non-zero (see the source header). */
void rx8_setSR(uint32_t sr)
{
    REC(0x003934u);
    g_last_set = sr;
    g_sr = sr;
}

void rx8_incomplete_stack_save_r14_r13(void)
{
    REC(0x014B04u);
}

/* ---- phase-1 subsystem stubs (8) ---------------------------------------- */
void rx8_calc_combustion_efficiency_metric(void)  { REC(0x00121F0u); }
void rx8_calc_combustion_load_factor(void)        { REC(0x001237Cu); }
void rx8_get_knock_control_allowed(void)          { REC(0x0013A0Eu); }
void rx8_get_knock_sensor_faulted_status(void)    { REC(0x0013A5Eu); }
void rx8_get_knock_control_active(void)           { REC(0x0013A86u); }
void rx8_update_knock_max_ram(void)               { REC(0x0013B90u); }
void rx8_calc_ignition_all_rotors_13c2c(void)     { REC(0x0013C2Cu); }
void rx8_cooling_fan_control(void)                { REC(0x0017DCCu); }

/* ---- phase-2 subsystem stubs (55) --------------------------------------- */
void rx8_calc_adaptive_fuel_trim(void)            { REC(0x001379Cu); }
void rx8_calc_accel_fuel_enrichment(void)         { REC(0x00138CCu); }
void rx8_calc_barometric_pressure_trim(void)      { REC(0x0013F68u); }
void rx8_read_fuel_pressure_feedback_status(void) { REC(0x001408Cu); }
void rx8_calc_closed_loop_fuel_status(void)       { REC(0x00141B8u); }
void rx8_read_o2_sensor_voltage_trim(void)        { REC(0x001412Au); }
void rx8_calc_rotor_sync_idle_gate_b(void)        { REC(0x0012BC8u); }
void rx8_read_engine_speed_status(void)           { REC(0x0013070u); }
void rx8_dsc_related_timing(void)                 { REC(0x0019220u); }
void rx8_sensor_range_calc(void)                  { REC(0x0044B1Cu); }
void rx8_sensor_abs_deviation(void)               { REC(0x0044B9Au); }
void rx8_calculate_driver_conditions(void)        { REC(0x0043C4Au); }
void rx8_knock_sensor_threshold(void)             { REC(0x0043E90u); }
void rx8_rpm_limiter_calc(void)                   { REC(0x0043E60u); }
void rx8_air_bypass_control(void)                 { REC(0x0043E00u); }
void rx8_fuel_enable_logic(void)                  { REC(0x0044AB2u); }
void rx8_air_bleed_control(void)                  { REC(0x0043EE8u); }
void rx8_exhaust_control(void)                    { REC(0x0043F56u); }
void rx8_sensor_signal_calc(void)                 { REC(0x0044076u); }
void rx8_fuel_pressure_calc(void)                 { REC(0x004409Eu); }
void rx8_catalyst_control(void)                   { REC(0x00440DEu); }
void rx8_lambda_control_calc(void)                { REC(0x0044206u); }
void rx8_emissions_control(void)                  { REC(0x004416Cu); }
void rx8_fault_code_handler(void)                 { REC(0x00442E8u); }
void rx8_fuel_correction_update(void)             { REC(0x0044370u); }
void rx8_func_0443a2(void)                        { REC(0x00443A2u); }
void rx8_fpu_clear_result(void)                   { REC(0x0044506u); }
void rx8_readiness_check(void)                    { REC(0x0044530u); }
void rx8_fuel_cut_logic(void)                     { REC(0x004490Au); }
void rx8_calc_decel_fuel_cut_445aa(void)          { REC(0x00445AAu); }
void rx8_intake_condition_check(void)             { REC(0x0044694u); }
void rx8_ignition_advance_interp(void)            { REC(0x00446BCu); }
void rx8_sensor_select_check(void)                { REC(0x0044748u); }
void rx8_rpm_neutral_calc(void)                   { REC(0x0044782u); }
void rx8_idle_correction_interp(void)             { REC(0x00447B0u); }
void rx8_knock_control_calc(void)                 { REC(0x0044824u); }
void rx8_calc_combustion_chamber_temp(void)       { REC(0x0012938u); }
void rx8_write_knock_detected_flag(void)          { REC(0x00128C4u); }
void rx8_calc_rotor_a_pressure_load(void)         { REC(0x00126EAu); }
void rx8_add_fuel_pressure_correction(void)       { REC(0x00126CAu); }
void rx8_calc_intake_pressure_pid_output(void)    { REC(0x001252Cu); }
void rx8_calc_rotor_b_knock_flag(void)            { REC(0x0012A48u); }
void rx8_write_rotor_a_knock_flag(void)           { REC(0x00128FEu); }
void rx8_calc_rotor_b_pressure_load(void)         { REC(0x00127DEu); }
void rx8_add_rotor_timing_offset(void)            { REC(0x00126DAu); }
void rx8_calc_vis_solenoid_duty_cycle(void)       { REC(0x001261Cu); }
void rx8_calc_fuel_pump_duty_trim(void)           { REC(0x00135F6u); }
void rx8_calc_evap_purge_duty(void)               { REC(0x0013652u); }
void rx8_fpu_conditional_accumulate_pair_ch0(void){ REC(0x0014A5Cu); }
void rx8_fpu_conditional_accumulate_pair_ch1(void){ REC(0x0014A92u); }
void rx8_sensor_filter_apply_all(void)            { REC(0x001061Au); }
void rx8_get_engine_cranking_status(void)         { REC(0x001117Au); }
void rx8_filter_signal_adaptive(void)             { REC(0x002CBBAu); }
void rx8_check_fuel_pump_relay_enable(void)       { REC(0x002CC1Cu); }
void rx8_health_check_system(void)                { REC(0x004D0E8u); }

int main(void)
{
    char line[128];
    while (fgets(line, sizeof line, stdin)) {
        unsigned long sr;
        int i;

        if (sscanf(line, "ect %lx", &sr) != 1) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        g_sr = (uint32_t)sr;
        g_last_set = 0;
        g_seqlen = 0;
        rx8_engine_control_calculate_timing();

        printf("%08X %08X %08X %08X %08X",
               (unsigned)g_sr, (unsigned)g_last_set,
               (unsigned)g_last_set, 0xEEEE0000u, 0xFFFFDF00u);
        for (i = 0; i < g_seqlen; i++)
            printf(" %08X", (unsigned)g_seq[i]);
        putchar('\n');
    }
    return 0;
}
