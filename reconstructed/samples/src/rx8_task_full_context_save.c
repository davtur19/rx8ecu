/*
 * =============================================================================
 * rx8_task_full_context_save.c  —  RTOS FULL CONTEXT SAVE (idle -> task switch)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x3BF4  (54 bytes of code, 0x3BF4..0x3C29 inclusive; the
 *                       function ends with an unconditional `bra 0x3C68` that
 *                       tail-jumps into the scheduler dispatch and NEVER
 *                       returns on the target).
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_task_full_context_save.py
 *               (host-gcc vs tools/sh2emu.py over edge + N random vectors;
 *               bit-exact RAM side-effects on the saved-context stack block,
 *               the task status cell AND the TCB saved-sp word; 0 mismatches).
 * Lift (truth): c/task_full_context_save.c  (task_full_context_save @ 0x3BF4).
 *               The edge + random harness drives the scheduler dispatch tail-jump
 *               (0x3C68) with an `rts; nop` stub on the emulator side and a
 *               returning stub on the host side, exactly like the established
 *               c/tests/test_taskEndRoutine.py pattern.
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * One of the three suspend/context-switch entry points of the RX-8 PCM's
 * cooperative RTOS (callers: FUN_00003490 @0x3490, task_execute_by_index
 * @0x3854, FUN_00003DB0 @0x3DB0).  It captures the suspended task's full CPU
 * context onto the kernel stack, publishes the task's scheduled status, records
 * the resulting stack pointer in the task control block, and then hands control
 * to the scheduler dispatch @0x3C68 (which selects and switches to the next).
 *
 * ROM BODY (disassembled 60E1D400.bin @ 0x3BF4):
 *
 *     2F56   mov.l   r5,@-r15             ; push r5                      (0x3BF4)
 *     4F22   sts.l   pr,@-r15             ; push pr                       (0x3BF6)
 *     7FFC   add     #-4,r15              ; reserve 1 slot                (0x3BF8)
 *     2F86   mov.l   r8,@-r15             ; push r8                       (0x3BFA)
 *     2F96   mov.l   r9,@-r15             ; push r9                       (0x3BFC)
 *     2FA6   mov.l   r10,@-r15            ; push r10                      (0x3BFE)
 *     2FB6   mov.l   r11,@-r15            ; push r11                      (0x3C00)
 *     2FC6   mov.l   r12,@-r15            ; push r12                      (0x3C02)
 *     4F13   stc.l   GBR,@-r15            ; push GBR                      (0x3C04)
 *     2FD6   mov.l   r13,@-r15            ; push r13                      (0x3C06)
 *     4F02   sts.l   mach,@-r15           ; push mach                     (0x3C08)
 *     2FE6   mov.l   r14,@-r15            ; push r14                      (0x3C0A)
 *     4F12   sts.l   macl,@-r15           ; push macl (final sp, no FPU)   (0x3C0C)
 *     5361   mov.l   @(0x4,r6),r3         ; r3 = *(desc+4) = status_ptr    (0x3C0E)
 *     8460   mov.b   @(0x00,r6),r0        ; r0 = desc[0] (task type)       (0x3C10)
 *     8804   cmp/eq  #0x04,r0             ; type == 4?                     (0x3C12)
 *     8F04   bf/s    0x3C20               ; no -> skip the FPU block       (0x3C14)
 *     0009   nop                          ;   (delay slot)
 *     FFCB   fmov.s  fr12,@-r15           ; push fr12                      (0x3C18)
 *     FFDB   fmov.s  fr13,@-r15           ; push fr13                      (0x3C1A)
 *     FFEB   fmov.s  fr14,@-r15           ; push fr14                      (0x3C1C)
 *     FFFB   fmov.s  fr15,@-r15           ; push fr15 (final sp w/ FPU)    (0x3C1E)
 *   .status:                             ;                                (0x3C20)
 *     E004   mov     #0x04,r0             ; r0 = 4 (scheduled status)      (0x3C20)
 *     8030   mov.b   r0,@(0,r3)           ; *(u8)status_ptr = 4            (0x3C22)
 *     14F3   mov.l   r15,@(0xC,r4)        ; tcb->saved_sp(+0xC) = r15      (0x3C24)
 *     A01F   bra     0x3C68               ; tail-jump scheduler dispatch   (0x3C26)
 *     0009   nop                          ;   (delay slot)                 (0x3C28)
 *
 * CALLING CONVENTION
 * ------------------
 * ABI entry: r4 = task control block (TCB) base, r5 = the task's saved SR /
 * context word (pushed verbatim as part of the context), r6 = task descriptor
 * (type byte at +0, status POINTER u32 at +0x04).  The ground truth
 * c/task_full_context_save.c documents r4 = TCB and r6 = task descriptor; the
 * call sites confirm r4 = os_ctrl (the TCB anchor) and r6 = task state block.
 * r5 is NOT read for control flow - only pushed.  No ABI return: the tail-branch
 * at 0x3C26 never comes back to the caller.
 *
 * RAM SIDE-EFFECTS (compared bit-exactly by the harness)
 * ------------------------------------------------------
 *  * Saved-context block pushed onto the kernel stack @ 0xFFFFDF00 (the ROM's
 *    r15 on entry), 52 bytes for type != 4, 68 for type == 4.  Reading 17 u32
 *    words starting at the FINAL saved SP:
 *      non-FPU final sp = 0xFFFFDECC              FPU final sp = 0xFFFFDEBC
 *      sp+0x00 macl = 0    sp+0x28 r10 = 0         sp+0x40..0x4C fr12..fr15 = 0 (FPU)
 *      sp+0x04 r14 = 0     sp+0x2C r9  = 0
 *      sp+0x08 mach= 0     sp+0x30 r8  = 0
 *      sp+0x0C r13 = 0     sp+0x34 reserved = 0 (the add #-4 slot, never written)
 *      sp+0x10 gbr = 0     sp+0x38 pr = 0xEEEE0000 (emulator return sentinel)
 *      sp+0x14 r12 = 0     sp+0x3C r5 = <argument value>
 *      sp+0x18 r11 = 0
 *    All non-pr/r5 register values are 0 in the executing state; the block is
 *    identical between host and emulator because both start with the same
 *    register defaults and the same r15 stack top.
 *  * Byte STATUS_CELL = *(u32*)&desc[+0x04] <- 0x04     (status/scheduled)
 *  * tcb+0xC (u32)                                      <- final SP (saved_sp)
 *  * The reserved stack slot (TOP-12) and everything above the pushed block
 *    stays zero on both sides.
 * Every other cell stays seeded / zero.
 *
 * CALLEES (emulator side runs REAL ROM bytes except where noted)
 * --------------------------------------------------------------
 *  * scheduler dispatch @0x3C68 - the ROM tail-branches here (0x3C26) and
 *    NEVER returns. The harness overlays an `rts; nop` stub at 0x3C68 so the
 *    emulator returns (via pr = sentinel); the host oracle supplies a
 *    returning stub. This mirrors the task_dispatcher stub used by the
 *    rx8_task_end_routine.c / rx8_task_flag_run_c.c rigs.
 *
 * DISCREPANCIES vs c/task_full_context_save.c (the ROM bytes are authoritative):
 *  1. Status write: the lift says "Sets task_descriptor[4] = 4". The ROM
 *     actually reads descriptor+0x04 (a POINTER) and writes the byte
 *     `*(u8*)(desc+0x04) = 0x04` - it dereferences through the pointer. This
 *     port models the dereference.
 *  2. FPU save: the lift implies fr12..fr15 are conditional on FPSCR.SZ. The
 *     ROM saves fr12..fr15 UNCONDITIONALLY when type == 0x04 (four
 *     `fmov.s @-r15`), with NO SZ/flag-gated branch.
 *  3. saved_sp: the lift's placeholder `tcb->saved_sp = &tcb` is not what the
 *     ROM does; the ROM stores the ACTUAL r15 after the push sequence. This
 *     port reproduces the real r15 (RX_STACK_TOP - 52 or - 68).
 *  4. The lift leaves the register-saving as inline-asm placeholders; this
 *     sample spells the pushes out as explicit RAM writes to reproduce the
 *     context block byte-for-byte on the host.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_hw.h"

#define RX_TCB_SAVED_SP   0x0Cu   /* u32  saved SP in the task control block */
#define RX_DESC_TYPE      0x00u   /* u8   task type */
#define RX_DESC_STATUS_PTR 0x04u  /* u32  pointer to a status byte */

/* Kernel stack the context is pushed onto (the ROM's r15 on entry). The value
 * 0xFFFFDF00 is the emulator default r15 at a call() - kept identical on the
 * host so the context block lands at the same byte addresses. */
#define RX_STACK_TOP      0xFFFFDF00u

#define RX_TASK_TYPE_FPU  4u      /* type 0x04 triggers the FPU block */
#define RX_STATUS_RUNNING 4u      /* "scheduled"/"running" status    */

/* Return sentinel value the emulator (tools/sh2emu.py) starts pr at; the ROM
 * pushes pr as part of the context, so the host mirrors the same constant. */
#define RX_EMU_PR_SENTINEL 0xEEEE0000u

/* Scheduler dispatch @0x3C68 - the ROM tail-branches here and never returns.
 * Supplied by the host oracle as a returning stub so the byte-exact RAM effects
 * can be observed; the emulator harness overlays an `rts; nop` at 0x3C68. */
extern void rx8_os_dispatch(void);

/* Write a big-endian 32-bit word to an absolute (already mmap'd) address. */
static inline void w32(uint32_t addr, uint32_t val)
{
    *(volatile uint32_t *)(uintptr_t)addr = val;
}

/* 0x3BF4  OS full context save - push a task's registers, tag it RUNNING,
 * record the SP and hand off to the scheduler. */
void rx8_task_full_context_save(uint8_t *tcb, const uint8_t *desc, uint32_t r5)
{
    uint32_t status_ptr =
        ((uint32_t)desc[RX_DESC_STATUS_PTR] << 24) |
        ((uint32_t)desc[RX_DESC_STATUS_PTR + 1] << 16) |
        ((uint32_t)desc[RX_DESC_STATUS_PTR + 2] << 8) |
        (uint32_t)desc[RX_DESC_STATUS_PTR + 3];

    w32(RX_STACK_TOP - 4u, r5);               /* 0x3BF4 push r5  */
    w32(RX_STACK_TOP - 8u, RX_EMU_PR_SENTINEL); /* 0x3BF6 push pr */
    /* 0x3BF8 add #-4,r15 : reserved cell @TOP-12 stays zero (never written). */
    w32(RX_STACK_TOP - 16u, 0);               /* 0x3BFA push r8  */
    w32(RX_STACK_TOP - 20u, 0);               /* 0x3BFC push r9  */
    w32(RX_STACK_TOP - 24u, 0);               /* 0x3BFE push r10 */
    w32(RX_STACK_TOP - 28u, 0);               /* 0x3C00 push r11 */
    w32(RX_STACK_TOP - 32u, 0);               /* 0x3C02 push r12 */
    w32(RX_STACK_TOP - 36u, 0);               /* 0x3C04 push GBR */
    w32(RX_STACK_TOP - 40u, 0);               /* 0x3C06 push r13 */
    w32(RX_STACK_TOP - 44u, 0);               /* 0x3C08 push mach */
    w32(RX_STACK_TOP - 48u, 0);               /* 0x3C0A push r14 */
    w32(RX_STACK_TOP - 52u, 0);               /* 0x3C0C push macl */
    uint32_t sp = RX_STACK_TOP - 52u;

    if (desc[RX_DESC_TYPE] == RX_TASK_TYPE_FPU) {      /* 0x3C12 cmp/eq #4 */
        w32(RX_STACK_TOP - 56u, 0);           /* 0x3C18 fmov.s fr12,@-r15 */
        w32(RX_STACK_TOP - 60u, 0);           /* 0x3C1A fmov.s fr13,@-r15 */
        w32(RX_STACK_TOP - 64u, 0);           /* 0x3C1C fmov.s fr14,@-r15 */
        w32(RX_STACK_TOP - 68u, 0);           /* 0x3C1E fmov.s fr15,@-r15 */
        sp = RX_STACK_TOP - 68u;
    }

    *(volatile uint8_t *)(uintptr_t)status_ptr = RX_STATUS_RUNNING;   /* 0x3C22 */
    w32((uintptr_t)tcb + RX_TCB_SAVED_SP, sp);                 /* 0x3C24 saved_sp */

    rx8_os_dispatch();                                        /* 0x3C26 bra 0x3C68 */
}