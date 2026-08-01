/* calc_lambda_feedback_pid.c
 *
 * ROM: 60E1D400  |  Address: 0x11A34  |  Size: 104 bytes  |  VERIFIED vs ROM emulator
 *
 * Closed-loop lambda feedback — task-dispatch wrapper.
 *
 * IMPORTANT: this "PID" is NOT a single Kp/Ki/Kd controller.  It is a
 * sequential task dispatcher: it jsr's 16 sub-functions in fixed order, then
 * tail-jmp's (not jsr's) into the 17th, 0x16E6A — the final jmp @r3 restores
 * PR first (lds.l @r15+,pr delay slot), so 0x16E6A returns directly to OUR
 * caller.  0x16E6A is therefore invoked exactly ONCE, via the tail call.
 * Each callee is itself a state-machine/task block of the closed-loop fuel
 * (lambda) subsystem; the FP-math-heavy ones (0x1ACDE: 247 FPU ops,
 * 0x17F7C: 143 FPU ops, 0x32A9C: 92, 0x3A1CC: 84, 0x2204C: 32) implement
 * the actual trimming/feedback calculations, calling the shared verified
 * math leaves (0x23B0 firstOrderFilter, 0x23E4, 0x2404 clamp, 0x2460,
 * 0x2478 saturating adds, 0x2068/0x20DC map lookups).
 *
 * Dispatch table (order = ROM order, verified by emulator instruction trace):
 *
 *   1. 0x1ACDE  lambda-feedback core #1   (644 i, 247 FPU) — O2 conditioning,
 *              filter, window compares; callee of helpers + 0x44C6E/0x44C86
 *   2. 0x2F51E  (216 i, 5 FPU)            — status/bank trimming chain
 *   3. 0x3A1CC  (872 i, 84 FPU)           — secondary lambda math
 *   4. 0x2204C  (640 i, 32 FPU)           — trim/learn chain
 *   5. 0x1490E  (161 i, 0 FPU)            — no-FPU state updates
 *   6. 0x2766A  (115 i, 3 FPU)            — sensor status chain
 *   7. 0x16AA8  (278 i, 21 FPU)           — fuel-cut / transient logic
 *   8. 0x3FCE0  (108 i, 19 FPU)           — O2 sensor conditioning
 *   9. 0x32A9C  (650 i, 92 FPU)           — fueling trim core
 *  10. 0x17F7C  (611 i, 143 FPU)          — lambda feedback core #2
 *  11. 0x225A2  (464 i, 8 FPU)            — closed-loop enable logic
 *  12. 0x35B6A  (167 i, 9 FPU)
 *  13. 0x35B96  (145 i, 8 FPU)
 *  14. 0x2971C  (646 i, 0 FPU)            — DTC/fault chain (no FP)
 *  15. 0x2B0D6  (610 i, 9 FPU)            — O2 heater control
 *  16. 0x67482  (7 i)                     — wrapper -> 0x60DB4, stores u16 to
 *                                            RAM[0xFFFFD96C]
 *  17. 0x16E6A  (23 i)                    — status latch; may jmp 0x16D04
 *              (called via TAIL jmp @r3, exactly once)
 *
 * Every callee begins with 0x3920(0x10) (SR save/enter) and ends through
 * 0x3934 (SR restore/exit) — the RTOS task boundary pattern documented in
 * RTOS_SUBSYSTEM.md.
 *
 * Verified: full ROM chain executes end-to-end under the SH-2E emulator
 * (returns r0 = 0x28 = 40); instruction trace confirms exactly 16 jsr
 * targets + 1 tail jmp in the order below.
 */

#include <stdint.h>

/* ---- callee task stubs (each is a separate verified subsystem block) ---- */
extern void lambda_core_1ACDE(void);      /* O2 conditioning / filter / trim core */
extern void lambda_chain_2F51E(void);
extern void lambda_core_3A1CC(void);
extern void lambda_trim_2204C(void);
extern void lambda_state_1490E(void);
extern void lambda_sensor_2766A(void);
extern void lambda_transient_16AA8(void);
extern void lambda_o2_3FCE0(void);
extern void lambda_fueling_32A9C(void);
extern void lambda_core_17F7C(void);
extern void lambda_enable_225A2(void);
extern void lambda_status_35B6A(void);
extern void lambda_status_35B96(void);
extern void lambda_dtc_2971C(void);
extern void lambda_heater_2B0D6(void);
extern void lambda_wrap_67482(void);
extern void lambda_latch_16E6A(void);

void calc_lambda_feedback_pid(void)
{
    lambda_core_1ACDE();
    lambda_chain_2F51E();
    lambda_core_3A1CC();
    lambda_trim_2204C();
    lambda_state_1490E();
    lambda_sensor_2766A();
    lambda_transient_16AA8();
    lambda_o2_3FCE0();
    lambda_fueling_32A9C();
    lambda_core_17F7C();
    lambda_enable_225A2();
    lambda_status_35B6A();
    lambda_status_35B96();
    lambda_dtc_2971C();
    lambda_heater_2B0D6();
    lambda_wrap_67482();
    lambda_latch_16E6A();   /* tail jmp @r3: returns directly to our caller */
}
