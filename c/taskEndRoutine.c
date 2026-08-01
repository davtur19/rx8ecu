/*
 * taskEndRoutine.c  —  RX-8 PCM OS task end / exit routine (0x3D58)
 *
 * Called from 18 sites when a task completes execution.  This function
 * restores the saved status register, optionally signals the run flag,
 * increments a reference count, runs a consistency check, clears the
 * task active flag, and dispatches to the next task.
 *
 * SH-2E asm (with literal translations):
 *   0x3D58:  sts.l    pr,@-r15         ; push return address
 *   0x3D5A:  mov.l    0x3D98,r14       ; r14 = os_ctrl = *(0x3D98) = 0xFFFF72B0
 *   0x3D5C:  mov.l    @(20,r14),r13    ; r13 = task_state = os_ctrl->current_task
 *   0x3D5E:  mov.l    @(16,r14),r3     ; r3  = os_ctrl->saved_sr
 *   0x3D60:  ldc      r3,sr           ; restore Status Register (IPL)
 *   0x3D62:  mov.l    0x3D9C,r1       ; r1 = &flag = 0x4B10
 *   0x3D64:  mov.l    @r1,r2           ; r2 = *flag
 *   0x3D66:  tst      r2,r2           ; flag == 0?
 *   0x3D68:  bt       0x3D70          ;  -> yes, skip
 *   0x3D6A:  mov.l    0x3DA0,r3       ; r3 = task_flag_run_C (0x35EE)
 *   0x3D6C:  jsr      @r3             ; call task_flag_run_C(0)
 *   0x3D6E:  mov      #0,r4           ; [delay] arg = 0
 *   ; ---- increment refcount ----
 *   0x3D70:  mov.b    @(3,r13),r0     ; r0 = task_state->refcount
 *   0x3D72:  add      #1,r0           ; ++refcount
 *   0x3D74:  mov.b    r0,@(3,r13)     ; store back
 *   ; ---- set status word ----
 *   0x3D76:  mov.w    0x3D94,r3       ; r3 = 0x0100 (TASK_END status)
 *   0x3D78:  mov.l    r3,@(8,r14)     ; os_ctrl->status = 0x0100
 *   ; ---- consistency check ----
 *   0x3D7A:  mov.b    @(1,r13),r0     ; r0 = task_state->type
 *   0x3D7C:  mov.l    0x3DA4,r3       ; r3 = consistencyCheck (0x3A28)
 *   0x3D7E:  mov      r0,r5           ; arg2 = type
 *   0x3D80:  jsr      @r3             ; call consistencyCheck(os_ctrl, type)
 *   0x3D82:  mov      r14,r4          ; [delay] arg1 = os_ctrl
 *   ; ---- clear task active flag ----
 *   0x3D84:  mov      #0,r2
 *   0x3D86:  mov      r14,r4          ; (dead store, r14 preserved in delay of jsr)
 *   0x3D88:  mov.b    r2,@r13         ; *task_state->active = 0
 *   ; ---- save return state, dispatch ----
 *   0x3D8A:  mov.l    @(4,r13),r3     ; r3 = task_state->saved_sp_or_result
 *   0x3D8C:  mov.l    0x3DA8,r2       ; r2 = task_dispatcher (0x3C2A)
 *   0x3D8E:  mov.l    r3,@(12,r14)    ; os_ctrl->result = r3
 *   0x3D90:  jmp      @r2             ; goto dispatcher
 *   0x3D92:  lds.l    @r15+,pr        ; [delay] pop return address
 *
 * C signature (caller sets up r4 = OS control block ptr):
 *   void taskEndRoutine(void);
 *
 * NOTE: This function reads/writes kernel structures in RAM at 0xFFFF72B0.
 * The C below describes the algorithm; verification uses the emulator with
 * a RAM overlay representing the OS state.
 *
 * Track A: structurally documented.  Test: c/tests/test_taskEndRoutine.py.
 */
#include <stdint.h>

/* Kernel structure offsets (inferred from disassembly) */
#define OS_CTRL_SAVED_SR      16   /* uint32_t */
#define OS_CTRL_CURRENT_TASK  20   /* uint32_t* (pointer to task state) */
#define OS_CTRL_STATUS         8   /* uint32_t */
#define OS_CTRL_RESULT        12   /* uint32_t */

#define TASK_STATE_ACTIVE      0   /* uint8_t */
#define TASK_STATE_TYPE        1   /* uint8_t */
#define TASK_STATE_REFCOUNT    3   /* uint8_t */
#define TASK_STATE_SAVED_SP    4   /* uint32_t */

/* External references (lifted elsewhere) */
extern void task_flag_run_C(int arg);
extern void consistencyCheck(uint32_t *os_ctrl, int type);
extern void task_dispatcher(void);

/* 0x3D58  OS task end / exit routine                                      */
void taskEndRoutine(void)
{
    /* These would come from the OS control block pointer (set by caller in r4
     * or anchored at a fixed RAM address 0xFFFF72B0).  For clarity we show
     * the algorithm.
     *
     * uint32_t *os_ctrl = (uint32_t *)0xFFFF72B0;
     * uint8_t  *task    = (uint8_t  *)os_ctrl[OS_CTRL_CURRENT_TASK / 4];
     *
     * // Restore SR (interrupt priority)
     * // ldc os_ctrl[OS_CTRL_SAVED_SR / 4], sr
     *
     * // Optionally signal task run flag
     * // if (*(volatile uint32_t *)0x4B10 != 0)
     * //     task_flag_run_C(0);
     *
     * // Increment reference count
     * task[TASK_STATE_REFCOUNT]++;
     *
     * // Set status to TASK_END
     * os_ctrl[OS_CTRL_STATUS / 4] = 0x0100;
     *
     * // Consistency check
     * consistencyCheck(os_ctrl, task[TASK_STATE_TYPE]);
     *
     * // Clear active flag
     * task[TASK_STATE_ACTIVE] = 0;
     *
     * // Save result, dispatch to next task
     * os_ctrl[OS_CTRL_RESULT / 4] = *(uint32_t *)&task[TASK_STATE_SAVED_SP];
     * task_dispatcher();
     */
}
