/*
 * task_flag_run_C.c  —  RX-8 PCM OS: task running-flag set/clear (0x0035EE)
 *
 * Part of the preemptive OS task-switch barrier layer.  Sets bit 15
 * of the kernel state word at 0xFFFF72B8, calls an indirect function
 * (the actual task executor), then clears bit 15.
 *
 * This is analogous to a spinlock acquire/release: the flag tells the
 * scheduler it is NOT safe to switch tasks because we are inside the
 * protected region.
 *
 * SH-2E asm:
 *   0x0035EE: sts.l  pr,@-r15           ; save return address
 *   0x0035F0: mov.l  @(0x40,pc),r3      ; r3 = &state  (0xFFFF72B8)
 *   0x0035F2: mov.l  @(0x50,pc),r2      ; r2 = 0x8000  (bit 15 mask)
 *   0x0035F4: mov.l  @r3,r1             ; r1 = state
 *   0x0035F6: or     r2,r1              ; r1 |= 0x8000  (set bit 15)
 *   0x0035F8: mov.l  r1,@r3             ; store state
 *   0x0035FA: mov.l  @(0x4E,pc),r0      ; r0 = ptr to function ptr
 *   0x0035FC: mov.l  @r0,r3             ; r3 = function to call
 *   0x0035FE: jsr    @r0                ; call the task function
 *   0x003600: nop
 *   0x003602: mov.l  @(0x38,pc),r3      ; r3 = &state
 *   0x003604: mov.l  @(0x4A,pc),r2      ; r2 = 0xFFFF7FFF  (~bit 15 mask)
 *   0x003606: mov.l  @r3,r1             ; r1 = state
 *   0x003608: and    r2,r1              ; r1 &= ~0x8000  (clear bit 15)
 *   0x00360A: lds.l  @r15+,pr           ; restore return address
 *   0x00360C: rts
 *   0x00360E: mov.l  r1,@r3             ; store state (delay slot)
 *
 * The function pointer at (0x4B10) varies: it is set up by the scheduler
 * to point to the next task-body to run.
 */
#include <stdint.h>

#define STATE_ADDR  0xFFFF72B8u

/* 0x0035EE  Run a task-body under the OS critical-section flag         */
void task_flag_run_C(void (*task_fn)(void))
{
    volatile uint32_t *state = (volatile uint32_t *)STATE_ADDR;
    *state = *state | 0x8000u;       /* acquire: set running flag */
    task_fn();                        /* execute task body         */
    *state = *state & 0xFFFF7FFFu;   /* release: clear flag       */
}
