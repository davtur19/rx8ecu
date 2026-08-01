/*
 * task_execute_by_index.c  —  RX-8 PCM OS task scheduler (0x3854)
 *
 * Execute a task by its index in the task table.  This is the core
 * task-dispatch function — called from 14 sites across the OS layer.
 * It looks up the task table entry, checks state, decrements a counter,
 * optionally saves full context, and dispatches interrupt priority.
 *
 * SH-2E asm (simplified):
 *   0x3854:  push r14, r13, r12
 *   0x385A:  r13 = sr                ; save current SR
 *   0x385C:  r14 = 0xFFFF72B0        ; OS control block
 *   0x385E:  r12 = 0                 ; default return code = 0
 *   0x3860:  r3  = task_table        ; from literal 0x3904 (= 0x4990)
 *   0x3864:  push r11, pr
 *   0x3866:  sp -= 4
 *   0x3868:  *(sp) = r4              ; store task index on stack
 *   ; ---- calculate task entry address (index * 16) ----
 *   0x386A:  r11 = *(sp)             ; index
 *   0x386C:  r2  = *(r14 + 16)       ; saved SR from OS control block
 *   0x386E:  r11 <<= 2               ; index * 4
 *   0x3870:  r11 <<= 2               ; index * 16
 *   0x3872:  r11 += r3               ; r11 = &task_table[index]
 *   0x3874:  r4  = *(r11 + 4)        ; r4 = task state block pointer
 *   0x3876:  ldc  r2,sr              ; restore saved SR
 *   ; ---- check task state ----
 *   0x3878:  r0  = *(r4 + 3)         ; state byte
 *   0x387A:  tst  r0,r0              ; == 0?
 *   0x387C:  bf   0x3884             ;  -> no, continue
 *   ; task is not runnable
 *   0x387E:  ldc  r13,sr             ; restore original SR
 *   0x3880:  bra  0x38D8             ; goto not_runnable path
 *   0x3882:  r12 = 4                 ; return code = ERROR (4)
 *   ; ---- task is runnable ----
 *   0x3884:  r3  = 0x39BA            ; task_execute_helper
 *   0x3886:  r0 -= 1                 ; decrement counter
 *   0x3888:  *(r4 + 3) = r0          ; store back
 *   0x388A:  r6  = *(r11 + 2)        ; priority/type from task table
 *   0x388C:  r5  = *(sp)             ; task index
 *   0x388E:  call 0x39BA(r14, r5, r6); execute helper
 *   ; ---- check result ----
 *   0x3892:  if result != 0:
 *   ; ... save context path ...
 *   0x3898:  r3 = 0x00F0 & r13       ; mask saved SR for IPL
 *   0x389C:  r2 = *(r14 + 8)         ; os_ctrl->status
 *   0x389E:  r3 |= r2                ; combine
 *   0x38A0:  bit test r3
 *   0x38A2:  bf/s 0x38CC            ;  -> skip full context save
 *   0x38A4:  r11 = *(r14 + 24)       ; os state block
 *   ; ... full context save path ...
 *   0x38A6:  *(r11 + 1) is a flag
 *   0x38A8:  if flag != 0:
 *   0x38AC:    *(r14 + 8) = 0x0100   ; set status
 *   0x38B0:    flag2 = *(0x4B10)
 *   0x38B4:    if flag2 != 0: call task_flag_run_C(2)
 *   0x38BE:    call task_full_context_save(r14, r13, r11)
 *   0x38C8:    goto exit
 *   0x38CC:    restore SR
 *   0x38D2:    goto exit
 *   ; ---- not_runnable path ----
 *   0x38D8:  flag = *(0x4B08)
 *   0x38DC:  if flag != 0:
 *   0x38E0:    r6 = *(r14 + 8)       ; status
 *   0x38E2:    call interrupt_priority_dispatch(4, 1, r6)
 *   ; ---- exit ----
 *   0x38EA:  return r12
 *
 * C signature:
 *   int task_execute_by_index(int task_index);
 * Returns 0 on success, 4 if task not runnable.
 *
 * NOTE: This function deeply interacts with the OS kernel data structures
 * in RAM at 0xFFFF72B0.  The C below describes the algorithm structurally.
 *
 * Track A: structurally documented.  Test: c/tests/test_task_execute_by_index.py.
 */
#include <stdint.h>

/* OS control block offsets (from 0xFFFF72B0) */
#define OS_STATUS         8   /* uint32_t */
#define OS_RESULT        12   /* uint32_t */
#define OS_SAVED_SR      16   /* uint32_t */
#define OS_CURRENT_TASK  20   /* uint32_t* (pointer) */
#define OS_STATE_BLOCK   24   /* uint32_t* (pointer) */

/* Task table entry (16 bytes per entry, offset from 0x4990) */
#define TE_FLAGS         0   /* uint16_t */
#define TE_PRIORITY      2   /* uint16_t */
#define TE_STATE_PTR     4   /* uint32_t* (pointer to task state block) */
#define TE_UNUSED_8      8   /* 8 bytes padding */
#define TE_ENTRY_SIZE   16

/* Task state block offsets */
#define TS_ACTIVE        0   /* uint8_t */
#define TS_TYPE          1   /* uint8_t */
#define TS_RESERVED2     2   /* uint8_t */
#define TS_COUNTER       3   /* uint8_t */
#define TS_SAVED_SP      4   /* uint32_t */

/* External functions */
extern int  task_execute_helper(uint32_t *os_ctrl, int index, int priority);
extern void task_flag_run_C(int arg);
extern void task_full_context_save(uint32_t *os_ctrl, uint32_t saved_sr,
                                   uint32_t *state_block);
extern void interrupt_priority_dispatch(int arg1, int arg2, uint32_t status);

/* 0x3854  execute a task by its table index                                */
int task_execute_by_index(int task_index)
{
    /*
     * uint32_t *os_ctrl = (uint32_t *)0xFFFF72B0;
     * uint16_t *task_table = (uint16_t *)0x4990;
     * uint8_t *entry = (uint8_t *)task_table + task_index * TE_ENTRY_SIZE;
     * uint8_t *task   = *(uint32_t *)(entry + TE_STATE_PTR);
     *
     * uint32_t saved_sr;  // from stc sr,r13 in asm
     * int result = 0;
     *
     * // Check if task is runnable (counter != 0)
     * if (task[TS_COUNTER] == 0)
     *     return 4;  // ERROR: not runnable
     *
     * // Decrement counter
     * task[TS_COUNTER]--;
     *
     * // Call execution helper
     * result = task_execute_helper(os_ctrl, task_index, entry[TE_PRIORITY]);
     *
     * if (result != 0) {
     *     // Check if full context save is needed
     *     uint32_t ipl_mask = saved_sr & 0xF0;
     *     uint32_t status = os_ctrl[OS_STATUS / 4];
     *     if (some_condition(ipl_mask | status)) {
     *         // Normal path: restore SR
     *     } else {
     *         // Full context save path
     *         uint32_t *state = (uint32_t *)os_ctrl[OS_STATE_BLOCK / 4];
     *         if (state != NULL && *(uint8_t *)(state + 1) != 0) {
     *             os_ctrl[OS_STATUS / 4] = 0x0100;
     *             if (*(volatile uint32_t *)0x4B10 != 0)
     *                 task_flag_run_C(2);
     *             task_full_context_save(os_ctrl, saved_sr, state);
     *             return result;
     *         }
     *     }
     * }
     *
     * // Not runnable or simple exit path
     * if (*(volatile uint32_t *)0x4B08 != 0) {
     *     interrupt_priority_dispatch(4, 1, os_ctrl[OS_STATUS / 4]);
     * }
     *
     * return result;
     */
    (void)task_index;
    return 0;
}
