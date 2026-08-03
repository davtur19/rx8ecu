/* calc_lambda_feedback_pid_11A34.c
 *
 * ROM: 60E1D400  |  Address: 0x11A34  |  Size: 104 bytes (0x11A34..0x11A9B)
 *                  (naming-convention sibling of c/calc_lambda_feedback_pid.c)
 *
 * Closed-loop lambda feedback — RTOS task-dispatch WRAPPER (the "outer").
 *
 * SIGNATURE:  void calc_lambda_feedback_pid_11A34(void)
 *   - no arguments (r4..r7 are NOT read; SH-2 call convention would pass them
 *     in r4/r5/r6/r7, but the body touches none of them before dispatch),
 *   - no return value of its own: the function tail-calls the 17th task, and
 *     what the ROM leaves in r0 on exit is whatever the last task leaves there
 *     (verified: r0 == 0x28 = 40 with all-zero RAM, all 17 real tasks run),
 *   - r15/PR discipline: pushes PR, dispatches 16 tasks via jsr (the emulator
 *     models jsr as pr=pc+4, no stack push), then `jmp @r3` into the 17th
 *     task with `lds.l @r15+,pr` in the DELAY SLOT — so 0x16E6A returns
 *     directly to OUR caller and r15 is restored to its entry value.
 *
 * RAM IN / RAM OUT (of the outer itself):
 *   NONE.  The wrapper body is a pure dispatch skeleton:
 *       sts.l pr,@-r15
 *       16x (mov.l <pool>,rN ; jsr @rN ; nop)
 *       mov.l 0x11CA0,r3 ; jmp @r3
 *       lds.l @r15+,pr              (delay slot of the jmp)
 *   Its entire observable effect is the dispatch SEQUENCE (order + count),
 *   the tail-call stack discipline, and the cumulative RAM effects of the 17
 *   dispatched tasks.  The tasks themselves are separate subsystem blocks
 *   (documented in the dispatch table below); they are the ones that read
 *   the lambda-sensor state words (0xFFFFA8xx..0xFFFFB5xx cluster, sensor
 *   averages, filter/trim RAM, integrator-state words) and write the fuel
 *   trim / closed-loop status words.  Deep callee effects are NOT inlined
 *   here: each task is left as an extern helper (see notes below).
 *
 * DISPATCH TABLE (ROM order, literal pool @0x11C60..0x11CA0 — 16 jsr + 1
 * tail jmp; addresses verified byte-level against 60E1D400.bin):
 *
 *   #  addr    size   helper name                semantic hypothesis (from disasm)
 *   1  0x1ACDE  72B   lambda_core_1ACDE          O2/emission conditioning core; jsr 0x1B5A8 (fuel pump speed),
 *                                                0x44C6E/0x44C86 (TPS->float, APV range), 0x2CCA4/0x2CCCC,
 *                                                0x2CF80/0x2CFE6 (gear bools / debounce), 0x2D1B0/0x2D23E
 *   2  0x2F51E  90B   lambda_chain_2F51E          status/health-report chain; jsr 0x4D26C..0x4E912 (diag/health block)
 *   3  0x3A1CC  42B   lambda_core_3A1CC          secondary-lambda math entry; jsr 0x4A9EC/0x4AAC4 (intr mask/status),
 *                                                0x3975E/0x397EC (counters)
 *   4  0x2204C  72B   lambda_trim_2204C          trim/learn chain; jsr 0x20E7C/0x205F2/0x20C8C/0x2100A (chamber/combustion),
 *                                                0xE7F8 (ignition timing), 0x321B8/0x3234C/0x324A0, 0x30BCA
 *   5  0x1490E  54B   lambda_state_1490E         no-FPU state updates; jsr 0x19000/0x190A6/0x19190/0x1913C
 *                                                (knock margin, load estimator, air-charge, A/F feedback), 0x4488E/0x449BA
 *   6  0x2766A  66B   lambda_sensor_2766A        sensor-status chain; jsr 0x26610 (secondary fuel ctrl),
 *                                                0x26766 (battery status), 0x268FC, 0x271B8, 0x2734C, 0x275BC,
 *                                                0x54FCC/0x54FE2
 *   7  0x16AA8 174B   lambda_transient_16AA8     fuel-cut / transient logic (biggest dispatch of the 16);
 *                                                jsr 0x14B8C..0x16BE8 (load/map/rotor-sync/fuel cluster),
 *                                                0x34204/0x343D6/0x358D0/0x35A94, 0x22534
 *   8  0x3FCE0  30B   lambda_o2_3FCE0            O2 sensor conditioning; jsr 0x3F94E/0x3FA5E
 *   9  0x32A9C  48B   lambda_fueling_32A9C       fueling-trim core; jsr 0x32AE8 (APV control), 0x32D4A/0x32D86/0x32DAE,
 *                                                0x32A68
 *  10  0x17F7C  24B   lambda_core_17F7C          lambda feedback core #2; jsr 0x18CC0 (OMP overshoot det.)
 *  11  0x225A2  24B   lambda_enable_225A2        closed-loop enable logic; jsr 0x225C8 (SSV control)
 *  12  0x35B6A  24B   lambda_status_35B6A        status dispatch; jsr 0x35AC4 (VDI control)
 *  13  0x35B96  24B   lambda_status_35B96        status dispatch #2; jsr 0x35BBC (VFAD control)
 *  14  0x2971C  60B   lambda_dtc_2971C           DTC/fault chain (no FP); jsr 0x2990C, 0x45984/0x45B44/0x455DC/
 *                                                0x45CA0/0x45740 (fuel-system DTC resets), 0x2786C
 *  15  0x2B0D6  96B   lambda_heater_2B0D6        O2 heater / status dispatch; jsr 0x2C13C..0x2C5EC (counter/
 *                                                threshold/flag checks), 0x2BE6E, 0x2BF7E/0x2BFA6/0x2BFD2
 *  16  0x67482  18B   lambda_wrap_67482          wrapper -> 0x60DB4 (dtc_data_read_60DB4), stores u16 to
 *                                                RAM[0xFFFFD96C]
 *  17  0x16E6A  44B   lambda_latch_16E6A         status latch; tail `jmp 0x16D04` on a condition (0x16D04 = the
 *                                                latch body, 126 B) — invoked ONCE via the outer's tail jmp.
 *
 * Every one of the 16 jsr'd tasks opens with jsr 0x3920 (getSR / SR-save-enter)
 * and closes with tail jmp 0x3934 (setSR / SR-restore-exit) — the RTOS task
 * boundary pattern (RTOS_SUBSYSTEM.md).  0x67482/0x16E6A are the exceptions
 * (plain leaf / latch).
 *
 * CALLEES-AS-HELPERS note: per the repo's dispatch/tail-call wrapper pattern
 * (cf. c/omp_control_task_1825E.c, reconstructed/samples/tests/harness_*),
 * the 17 tasks are NOT inlined here.  Each is a large subsystem block with its
 * own sub-chain (2nd level mapped in docs/notes/FINDINGS.md); the differential
 * test c/tests/test_calc_lambda_feedback_pid_11A34.py stubs them (both in the
 * SH-2 emulator via the RAM overlay and in the host-C oracle) to pin the
 * OUTER's own observable behavior bit-exactly: dispatch order/count, the
 * tail-call stack discipline (r15 + PR word), r0/r1, and the trace RAM span.
 */

#include <stdint.h>

/* ---- callee task stubs (each is a separate subsystem block, see above) ---- */
extern void lambda_core_1ACDE(void);      /* O2/emission conditioning core      */
extern void lambda_chain_2F51E(void);     /* status/health-report chain         */
extern void lambda_core_3A1CC(void);      /* secondary-lambda math entry        */
extern void lambda_trim_2204C(void);      /* trim/learn chain                   */
extern void lambda_state_1490E(void);     /* no-FPU state updates               */
extern void lambda_sensor_2766A(void);    /* sensor-status chain                */
extern void lambda_transient_16AA8(void); /* fuel-cut / transient logic         */
extern void lambda_o2_3FCE0(void);        /* O2 sensor conditioning             */
extern void lambda_fueling_32A9C(void);   /* fueling-trim core                  */
extern void lambda_core_17F7C(void);      /* lambda feedback core #2            */
extern void lambda_enable_225A2(void);    /* closed-loop enable logic           */
extern void lambda_status_35B6A(void);    /* status dispatch                    */
extern void lambda_status_35B96(void);    /* status dispatch #2                 */
extern void lambda_dtc_2971C(void);       /* DTC/fault chain (no FP)            */
extern void lambda_heater_2B0D6(void);    /* O2 heater / status dispatch        */
extern void lambda_wrap_67482(void);      /* wrapper -> 0x60DB4 -> RAM[D96C]    */
extern void lambda_latch_16E6A(void);     /* status latch (tail-call target)    */

void calc_lambda_feedback_pid_11A34(void)
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
