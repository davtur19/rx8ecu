/* calc_fuel_trims_adaptive_117B4.c
 *
 * ROM: 60E1D400  |  Address: 0x117B4  |  Size: 68 bytes (0x117B4..0x117F8)
 *
 * Adaptive fuel-trim task-dispatch WRAPPER (RTOS "outer"), same skeleton as
 * c/calc_lambda_feedback_pid_11A34.c (the previously solved sibling @0x11A34).
 *
 * SIGNATURE:  void calc_fuel_trims_adaptive_117B4(void)
 *   - no arguments (r4..r7 are NOT read; the body touches none of them before
 *     dispatch),
 *   - no return value of its own: the function tail-calls the 11th task, and
 *     what the ROM leaves in r0 on exit is whatever the last task leaves there
 *     (verified: r0 == 0x0 with all-zero RAM, all 11 real tasks run),
 *   - r15/PR discipline: pushes PR, dispatches 10 tasks via jsr (the emulator
 *     models jsr as pr=pc+4, no stack push), then `jmp @r3` into the 11th
 *     task with `lds.l @r15+,pr` in the DELAY SLOT — so the 11th task returns
 *     directly to OUR caller and r15 is restored to its entry value.
 *
 * RAM IN / RAM OUT (of the outer itself):
 *   NONE.  The wrapper body is a pure dispatch skeleton:
 *       sts.l pr,@-r15
 *       10x (mov.l <pool>,rN ; jsr @rN ; nop)
 *       mov.l 0x119A4,r3 ; jmp @r3
 *       lds.l @r15+,pr              (delay slot of the jmp)
 *   Its entire observable effect is the dispatch SEQUENCE (order + count),
 *   the tail-call stack discipline, and the cumulative RAM effects of the 11
 *   dispatched tasks.  The tasks themselves are separate subsystem blocks
 *   (documented in the dispatch table below); they are the ones that read the
 *   sensor / trim / status words and write the fuel-trim learning RAM.  Deep
 *   callee effects are NOT inlined here: each task is left as an extern helper
 *   (see notes below).
 *
 * DISPATCH TABLE (ROM order, literal pool @0x1197C..0x119A4 — 10 jsr + 1 tail
 * jmp; addresses verified byte-level against 60E1D400.bin):
 *
 *   #   addr    size   helper name                    semantic hypothesis (from disasm + IDA map)
 *   1  0x1AB70 134B   coil_charging_control_task      coil charging / dwell control task; jsr 0x3920 (getSR),
 *                                                     0x4B804 (charging math), 0x1B5A8.. (fuel pump / coil chain)
 *   2  0x3A064 204B   sensor_monitoring_dispatcher     sensor-status dispatch; jsr 0x3920, 0x3E9A6 (sensor monitor)
 *   3  0x1475A  42B   calc_intake_pressure_target      intake-pressure target for high-load; jsr 0x3920, 0x12B70
 *   4  0x27622  72B   fuel_control_task_dispatcher     fuel-control task dispatch; jsr 0x3920, 0x2687E (fuel ctrl)
 *   5  0x24596  24B   engine_task_dispatcher_24596     engine task dispatch; jsr 0x3920, 0x24440
 *   6  0x2B08E  42B   table_axis_increment_2B08E       table/axis increment helper; jsr 0x3920, 0x0DE8E
 *   7  0x1ABF4  24B   transmission_control_priority     transmission control priority task; jsr 0x3920, 0x34CDE
 *   8  0x35C84  36B   task_sensor_fault_dispatch        sensor fault task dispatch; jsr 0x3920, 0x38840
 *   9  0x5F030  66B   fault_condition_check_5F030       fault-condition check (mov.w 0x5F080 -> RAM flag byte,
 *                                                       cmp/eq #1 branch on 0xAAF9); NO getSR prologue
 *  10  0x16E08  48B   solenoid_drive_control            solenoid drive control (mov.w 0x16F00 -> 0xDFA0 flag,
 *                                                       tst/bf path -> r0=0x28 mov.w 0x16F02->0xDF70); NO getSR
 *  11  0x39302  16B   trampoline_vdi_39302              status trampoline; jsr 0x3920, 0x38C64 — invoked ONCE
 *                                                       via the outer's tail jmp.
 *
 * Every one of the 9 jsr'd getSR tasks opens with jsr 0x3920 (getSR /
 * SR-save-enter) — the RTOS task boundary pattern (RTOS_SUBSYSTEM.md).
 * 0x5F030 / 0x16E08 / 0x39302 are the exceptions (plain leafs / trampoline).
 *
 * STRUCTURE: all 11 dispatches are UNCONDITIONAL — straight-line sts.l +
 * 10x(mov.l,jsr,nop) + mov.l,jmp + lds.l in the delay slot; there are NO
 * bt/bf branches between the jsr's (byte-checked 0x117B4..0x117F8).
 *
 * CALLEES-AS-HELPERS note: per the repo's dispatch/tail-call wrapper pattern
 * (cf. c/omp_control_task_1825E.c), the 11 tasks are NOT inlined here.  Each
 * is a subsystem block with its own sub-chain; the differential test
 * c/tests/test_calc_fuel_trims_adaptive_117B4.py stubs them (both in the SH-2
 * emulator via the RAM overlay and in the host-C oracle) to pin the OUTER's
 * own observable behavior bit-exactly: dispatch order/count, the tail-call
 * stack discipline (r15 + PR word), r0/r1, and the trace RAM span.
 */

#include <stdint.h>

/* ---- callee task stubs (each is a separate subsystem block, see above) ---- */
extern void coil_charging_control_task(void);          /* coil charging control     */
extern void sensor_monitoring_dispatcher_3A064(void);  /* sensor-status dispatch    */
extern void calc_intake_pressure_target_1475A(void);   /* intake pressure target    */
extern void fuel_control_task_dispatcher_27622(void);  /* fuel-control task dispatch */
extern void engine_task_dispatcher_24596(void);        /* engine task dispatch      */
extern void table_axis_increment_2B08E(void);          /* table/axis increment      */
extern void transmission_control_priority_1ABF4(void); /* transmission priority     */
extern void task_sensor_fault_dispatch_35C84(void);    /* sensor fault dispatch     */
extern void fault_condition_check_5F030(void);         /* fault-condition check     */
extern void solenoid_drive_control_16E08(void);        /* solenoid drive control    */
extern void trampoline_vdi_39302(void);                /* status trampoline (tail)  */

void calc_fuel_trims_adaptive_117B4(void)
{
    coil_charging_control_task();
    sensor_monitoring_dispatcher_3A064();
    calc_intake_pressure_target_1475A();
    fuel_control_task_dispatcher_27622();
    engine_task_dispatcher_24596();
    table_axis_increment_2B08E();
    transmission_control_priority_1ABF4();
    task_sensor_fault_dispatch_35C84();
    fault_condition_check_5F030();
    solenoid_drive_control_16E08();
    trampoline_vdi_39302();   /* tail jmp @r3: returns directly to our caller */
}
