/*
 * =============================================================================
 * rx8_task_end_routine.c  —  RTOS TASK-END / EXIT ROUTINE (tail-jumps scheduler)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x3D58  (58 bytes of code + a 16-byte constant pool ending at
 *                        0x3DAB; the function finishes with an UNCONDITIONAL
 *                        tail-jump into the task dispatcher @0x3C2A and never
 *                        returns on the target).
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_task_end_routine.py
 *               (host-gcc vs tools/sh2emu.py over edge + random vectors;
 *               bit-exact RAM side-effects on the OS control block AND the
 *               task control block, 0 mismatches).  The consistency check and
 *               the dispatcher callees are STUBBED on both sides of the
 *               harness (see CALLEES below); the running-flag barrier @0x35EE
 *               is executed for real on the emulator side.
 * Lift (truth): c/taskEndRoutine.c  (taskEndRoutine @ 0x3D58).  The lift's
 *               per-instruction asm comments were re-checked against the
 *               bytes of 60E1D400.bin during this port and are accurate.
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * One of the 18 "task completed" exit sites of the RX-8 PCM's cooperative RTOS
 * (called from task stubs @0xA12E..0xA288).  It tears down the finished task:
 * restore the saved status register, optionally run the task running-flag
 * barrier @0x35EE (which executes the next task body through the 0x4B10
 * function pointer), bump the task's reference count, publish the TASK_END
 * status, run a consistency check, clear the task's active flag, stash the
 * task's saved return value into the OS control block, and finally tail-jump
 * into the dispatcher @0x3C2A (pr is popped in the jump's delay slot, so the
 * scheduler starts a fresh frame).
 *
 * ROM BODY (60E1D400.bin @0x3D58; constant pool @0x3D94..0x3DAB):
 *
 *     sts.l  pr,@-r15            ; save return address
 *     mov.l  @(0x3C,pc),r14      ; r14 = os_ctrl = 0xFFFF72B0
 *     mov.l  @(0x14,r14),r13     ; r13 = os_ctrl->current_task  (task block ptr)
 *     mov.l  @(0x10,r14),r3      ; r3  = os_ctrl->saved_sr
 *     ldc    r3,sr               ; restore Status Register (IPL)  [no RAM effect]
 *     mov.l  @(0x38,pc),r1       ; r1  = &flag = 0x4B10
 *     mov.l  @r1,r2              ; r2  = *flag  (task-body pointer / 0)
 *     tst    r2,r2 ; bt 0x3D70   ; flag == 0 -> skip the barrier
 *     mov.l  @(0x34,pc),r3       ; r3  = task_flag_run_C (0x35EE)
 *     jsr    @r3                 ; call task_flag_run_C(0)
 *     mov    #0,r4               ;   (delay slot) arg = 0
 *   .refcount:
 *     mov.b  @(3,r13),r0 ; add #1,r0 ; mov.b r0,@(3,r13)   ; task[3]++ (u8)
 *     mov.w  @(0x1C,pc),r3       ; r3 = 0x0100 (TASK_END status)
 *     mov.l  r3,@(8,r14)         ; os_ctrl->status = 0x0100
 *     mov.b  @(1,r13),r0         ; r0 = task->type
 *     mov.l  @(0x24,pc),r3       ; r3 = consistencyCheck (0x3A28)
 *     mov    r0,r5 ; jsr @r3     ; call consistencyCheck(os_ctrl, type)
 *     mov    r14,r4              ;   (delay slot) arg1 = os_ctrl
 *     mov    #0,r2 ; mov r14,r4  ; r2 = 0  (0x3D86's mov r14,r4 is a dead store)
 *     mov.b  r2,@r13             ; task->active = 0
 *     mov.l  @(4,r13),r3         ; r3 = task->saved_sp
 *     mov.l  @(0x18,pc),r2       ; r2 = task_dispatcher (0x3C2A)
 *     mov.l  r3,@(0xC,r14)       ; os_ctrl->result = task->saved_sp
 *     jmp    @r2                 ; tail-jump into the dispatcher
 *     lds.l  @r15+,pr            ;   (delay slot) pop return address
 *
 * CALLING CONVENTION
 * ------------------
 * ABI entry (the caller leaves the OS control block address in r4, but this
 * function never reads it — it anchors os_ctrl at the fixed RAM address
 * 0xFFFF72B0 from the constant pool, exactly like task_flag_run_C @0x35EE).
 * No ABI return: the tail-jump never comes back.
 *
 * CALLEES (emulator side runs REAL ROM bytes except where noted)
 * --------------------------------------------------------------
 *  * task_flag_run_C @0x35EE  — verified tiny leaf (samples/rx8_task_flag_run_c.c,
 *    harness_task_flag_run_c.py).  Executed for REAL by the emulator harness:
 *    it sets bit 15 of the flag word, calls the next task body through the
 *    function pointer at 0x4B10, then clears bit 15.  The harness stubs the
 *    task body (a fixed OR-delta+0x4 stub, exactly like the task_flag_run_c
 *    harness) and the oracle mirrors it.  Modelled here as an external call
 *    because the ROM fetches the callee address from RAM @0x4B10 — an address
 *    below this host's mmap_min_addr — so the 32-bit load is routed through
 *    rx8_task_flag_fetch() (see below).
 *  * consistencyCheck @0x3A28 — declared external and STUBBED (no-op) on both
 *    emulator and host.  Executing its real bytes needs r6/r7 in a specific
 *    state that no taskEndRoutine caller establishes, and the existing lift
 *    c/consistencyCheck.c does NOT match those ROM bytes (the code uses r6/r7
 *    and reads *(r4+8), not the exception-table layout the lift describes) —
 *    out of scope for this port.  The established c/tests/test_taskEndRoutine.py
 *    stubs it the same way.
 *  * task_dispatcher @0x3C2A — declared external and STUBBED (returns) so the
 *    host C can terminate; the jump is a tail-call on the target.
 *
 * THE 0x4B10 FLAG FETCH
 * ---------------------
 * The ROM tests the 32-bit flag at 0x4B10 (a task-body pointer written by the
 * scheduler) with a plain `mov.l @r1,r2`.  0x4B10 lies below mmap_min_addr on
 * this x86-64 host, so the port routes that single load through
 * `rx8_task_flag_fetch()` — supplied by the host oracle, returning the same
 * value the harness seeds at 0x4B10.  Behaviourally identical: the flag is
 * only ever read for a != 0 test.  Same modelling choice as the parameterised
 * fetch in rx8_task_flag_run_c.c.
 *
 * RAM SIDE-EFFECTS (compared bit-exactly by the harness)
 * ------------------------------------------------------
 * os_ctrl @ 0xFFFF72B0 (u32 fields):
 *   +8  status  = 0x00000100 (TASK_END)      [this is ALSO the running-flag
 *                                            word @0xFFFF72B8 that the barrier
 *                                            toggles — one and the same cell]
 *   +12 result  = task->saved_sp
 *   +16 saved_sr= unchanged by this function (reloaded into SR only; note the
 *                 barrier's mark cell @0xFFFF72C0 aliases it in the harness)
 * task block (current_task pointer from os_ctrl+20):
 *   +0  active  = 0 (cleared)
 *   +3  refcount= +1 (u8 wrap)
 * The barrier path additionally rewrites os_ctrl+8/+12/+16 through the task
 * body stub before the TASK_END writes above.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_hw.h"
#include "rx8_samples.h"

/* OS control block (kernel RAM, fixed anchor — constant pool @0x3D98). */
#define RX8_OS_CTRL_ADDR        0xFFFF72B0u
#define OS_CTRL_STATUS           8u   /* u32 TASK_END status / running flag   */
#define OS_CTRL_RESULT          12u   /* u32 saved task return value          */
#define OS_CTRL_SAVED_SR        16u   /* u32 status register snapshot         */
#define OS_CTRL_CURRENT_TASK    20u   /* u32 pointer to the task state block  */

/* Task state block offsets (indirect through os_ctrl->current_task). */
#define TASK_STATE_ACTIVE        0u   /* u8  active flag                      */
#define TASK_STATE_TYPE          1u   /* u8  task type (arg to consistency)   */
#define TASK_STATE_REFCOUNT      3u   /* u8  reference count                  */
#define TASK_STATE_SAVED_SP      4u   /* u32 saved result / return slot       */

#define RX8_TASK_END_STATUS  0x00000100u

/* 0x3D64 — the ROM's 32-bit flag load @0x4B10, routed through an accessor so
 * the host oracle can supply the value (0x4B10 < mmap_min_addr; see header). */
extern uint32_t rx8_task_flag_fetch(void);

/* Callees (see CALLEES in the header): */
extern void task_flag_run_c(int arg);            /* jsr 0x35EE, r4 = 0         */
extern void consistency_check(uint8_t *os_ctrl, int type); /* jsr 0x3A28 (stub) */
extern void task_dispatcher(void);               /* jmp 0x3C2A (stub, no-op)   */

/* 0x3D58  OS task end / exit routine — tear down and re-dispatch. */
void rx8_task_end_routine(void)
{
    volatile uint32_t *os = (volatile uint32_t *)RX8_OS_CTRL_ADDR;
    uint8_t *task;

    /* 0x3D5E-0x3D60  restore the saved status register (IPL).  On the target
     * this is `ldc r3,sr`; it has no RAM side-effect, only the register. */
    (void)os[OS_CTRL_SAVED_SR / 4];

    /* 0x3D62-0x3D68  if the task-body flag @0x4B10 is set, run the verified
     * running-flag barrier @0x35EE with argument 0. */
    if (rx8_task_flag_fetch() != 0u) {
        task_flag_run_c(0);
    }

    task = (uint8_t *)(uintptr_t)os[OS_CTRL_CURRENT_TASK / 4];

    /* 0x3D70-0x3D74  bump the task's reference count (u8, wraps). */
    task[TASK_STATE_REFCOUNT] = (uint8_t)(task[TASK_STATE_REFCOUNT] + 1u);

    /* 0x3D76-0x3D78  publish the TASK_END status. */
    os[OS_CTRL_STATUS / 4] = RX8_TASK_END_STATUS;

    /* 0x3D7A-0x3D82  run the kernel consistency check (stubbed in the harness;
     * the real callee @0x3A28 is separately out of scope — see header). */
    consistency_check((uint8_t *)os, task[TASK_STATE_TYPE]);

    /* 0x3D84-0x3D88  clear the task's active flag. */
    task[TASK_STATE_ACTIVE] = 0;

    /* 0x3D8A-0x3D8E  stash the task's saved return value, then 0x3D90
     * tail-jump into the dispatcher (stubbed in the harness so the host C can
     * return; the target never comes back). */
    os[OS_CTRL_RESULT / 4] = *(const uint32_t *)(uintptr_t)&task[TASK_STATE_SAVED_SP];
    task_dispatcher();
}
