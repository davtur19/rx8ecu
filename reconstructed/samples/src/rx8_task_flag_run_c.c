/*
 * =============================================================================
 * rx8_task_flag_run_c.c  —  OS TASK RUNNING-FLAG BARRIER (set/clear bit 15)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x35EE
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_task_flag_run_c.py
 *               (host-gcc vs tools/sh2emu.py over 20000 random + edge vectors;
 *               bit-exact RAM side-effects incl. the task body's state edits;
 *               0 mismatches).
 * Lift (truth): c/task_flag_run_C.c  (task_flag_run_C @ 0x35EE)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Part of the preemptive-OS task-switch barrier layer.  Sets bit 15 of a
 * kernel state word, calls the task body through a function pointer stored in
 * RAM, then clears bit 15 — an acquire/release spinlock-style guard that tells
 * the scheduler it is NOT safe to switch tasks while the protected region runs.
 *
 * ROM BODY (disassembled 60E1D400.bin @ 0x35EE; constant pool @ 0x3674/0x3694):
 *
 *     4F22   sts.l  pr,@-r15          ; prologue: save return address
 *     D320   mov.l  @(0x40,pc),r3     ; r3 = 0xFFFF72B8  (state word addr)
 *     D228   mov.l  @(0x50,pc),r2     ; r2 = 0x00008000   (bit-15 mask)
 *     6132   mov.l  @r3,r1            ; r1 = state
 *     212B   or     r2,r1             ; r1 |= 0x8000
 *     2312   mov.l  r1,@r3            ; state = r1          (acquire)
 *     D027   mov.l  @(0x4E,pc),r0     ; r0 = 0x00004B10     (ptr-to-fn-ptr)
 *     6302   mov.l  @r0,r3            ; r3 = *(uint32*)0x4B10  (task body addr)
 *     430B   jsr    @r3               ; call task body
 *     0009   nop
 *     D31C   mov.l  @(0x38,pc),r3     ; r3 = 0xFFFF72B8
 *     D225   mov.l  @(0x4A,pc),r2     ; r2 = 0xFFFF7FFF     (~bit-15 mask)
 *     6132   mov.l  @r3,r1            ; r1 = state          (RE-READ)
 *     2129   and    r2,r1             ; r1 &= 0xFFFF7FFF
 *     4F26   lds.l  @r15+,pr          ; epilogue: restore return address
 *     000B   rts
 *     2312   mov.l  r1,@r3            ;   (delay slot) state = r1  (release)
 *
 * DISCREPANCIES vs the c/ lift (comment-level only; the C body is correct):
 *  * the lift's asm comment reads `jsr @r0` for 0x35FE — the ROM is
 *    `jsr @r3` (0x430B): the callee address is loaded into r3 and called
 *    through it, not through r0.
 *  * the lift's C signature takes the task function as an argument, whereas
 *    the ROM reads the callee address from RAM at 0x4B10 *inside* this
 *    function.  The parameter models that memory fetch: on real firmware the
 *    scheduler writes the next task-body address to 0x4B10 before calling
 *    this barrier, and bit-exactness is unaffected (the harness drives the
 *    emulator with ram[0x4B10] = stub and the host with the same stub
 *    pointer).
 *
 * CALLING CONVENTION
 * ------------------
 * ABI entry (r4..r7 are never read — the function ignores register
 * arguments entirely; its true input is the state word + 0x4B10 in RAM).
 * Returns void in the ABI sense; the r0 left behind is incidental.
 *
 * RAM SIDE-EFFECTS (compared bit-exactly by the harness)
 * ------------------------------------------------------
 * state word @ 0xFFFF72B8 — the only location this function itself writes.
 * The post-call `mov.l @r3,r1` is a genuine RE-READ: any modification the
 * task body makes to the state word while bit 15 is held is preserved, and
 * only bit 15 is cleared on release.  (The harness exploits this: its task
 * stub ORs a per-vector delta + a marker bit into the state word, so a stale
 * cached value, a missing re-read or a wrong release mask all fail.)
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

#define RX8_TASK_STATE_ADDR      0xFFFF72B8u   /* kernel state word        */
#define RX8_TASK_RUNNING_BIT     0x8000u       /* bit 15 = "task running"  */
#define RX8_TASK_RUNNING_MASK    0xFFFF7FFFu   /* ~RX8_TASK_RUNNING_BIT    */

/* 0x35EE  Run a task body under the OS critical-section flag. */
void rx8_task_flag_run_c(void (*task_fn)(void))
{
    volatile uint32_t *state = (volatile uint32_t *)RX8_TASK_STATE_ADDR;
    *state = *state | RX8_TASK_RUNNING_BIT;   /* acquire: set running flag */
    task_fn();                                 /* execute task body         */
    *state = *state & RX8_TASK_RUNNING_MASK;  /* release: clear flag       */
}
