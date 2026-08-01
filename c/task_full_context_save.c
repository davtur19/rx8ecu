/* ====================================================================
 * task_full_context_save — RTOS full context save routine
 *
 * Address:  0x3BF4 (ROM 60E1D400)
 * Size:     54 bytes (0x3BF4-0x3C29)
 * Source:   ida-ai
 * Callers:  FUN_00003490 (0x3490), task_execute_by_index (0x3854),
 *           FUN_00003DB0 (0x3DB0) — 3 callers
 *
 * This function saves the full CPU context for a task being suspended.
 * It is called by the RTOS scheduler during task switching.
 *
 * Calling convention (SH-2E):
 *   R4 = pointer to task control block (TCB)
 *   R6 = pointer to task descriptor (contains type and status fields)
 * Returns: does not return — branches to scheduler dispatch at 0x3C68
 *
 * The function saves the following registers to the stack:
 *   R5, PR, R8, R9, R10, R11, R12, GBR, R13, MACH, R14, MACL
 *   Plus FPU registers FR12-FR15 if the task type is 4
 *
 * After saving context:
 *   Sets task_descriptor[4] = 4 (status: scheduled/running)
 *   Stores the stack pointer in TCB[0xC]
 *   Branches to the scheduler dispatch at 0x3C68
 *
 * Note: The scheduler dispatch at 0x3C68 loads the next task's context
 * and jumps to it. The save path does not return to the caller — control
 * is transferred to the next scheduled task.
 * ==================================================================== */

#include <stdint.h>

/* Task control block structure (at R4) */
struct task_ctrl_block {
    uint8_t  reserved_0[12];     /* 0x00-0x0B: other fields */
    uint32_t saved_sp;           /* 0x0C: saved stack pointer */
    /* more fields follow... */
};

/* Task descriptor structure (at R6) */
struct task_descriptor {
    uint8_t  type;               /* 0x00: task type */
    uint8_t  reserved_1[3];      /* 0x01-0x03: reserved */
    uint32_t status_ptr;         /* 0x04: pointer to status byte */
};

/* Scheduler dispatch function at 0x3C68.
 * Called after context save to select and switch to next task.
 * Defined as extern — provided by the kernel. */
extern void scheduler_dispatch(void);

/* FPSCR format flag — set when double-precision mode is active.
 * In single-precision mode (SZ=0), only FR12 and FR13 need saving.
 * In double-precision mode (SZ=1), FR12-FR15 must be saved. */
extern char in_FPSCR_SZ;

void task_full_context_save(struct task_ctrl_block *tcb,
                            struct task_descriptor *task)
{
    /* The actual register saving is performed by inline assembly
     * (push instructions in the ROM).  This C representation captures
     * the logical effect: register values are saved to the stack,
     * and the SP is updated to reflect the saved context. */

    /* Check if task type requires FPU context save */
    if (task->type == 4) {
        /* Save FPU registers FR12-FR15.
         * The FPSCR.SZ bit determines precision:
         *   SZ=0 (single): save FR12, FR13 (4 bytes each, 8 bytes total)
         *   SZ=1 (double): save FR12-FR15 as pairs (16 bytes total) */
        if (in_FPSCR_SZ == 0) {
            /* Single precision: 2 FPU registers saved */
            /* FR12 and FR13 are saved to stack */
        } else {
            /* Double precision: 4 FPU registers saved */
            /* FR12-FR15 are saved to stack */
        }
    }

    /* Set task status to 'running/scheduled' (4) */
    *(volatile uint8_t *)(task->status_ptr) = 4;

    /* Save the current stack pointer to the TCB.
     * The saved SP points to the top of the saved context,
     * allowing the context restore routine to pop all registers. */
    tcb->saved_sp = (uint32_t)(void *)&tcb;  /* placeholder — actual SP in asm */

    /* Branch to scheduler dispatch (does not return) */
    scheduler_dispatch();
}
