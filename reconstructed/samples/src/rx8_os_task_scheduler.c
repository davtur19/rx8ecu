/*
 * =============================================================================
 * rx8_os_task_scheduler.c  —  OS TASK SCHEDULER: LOOKUP + DISPATCH TASK ENTRY
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x9668  (110 bytes of code + a 16-byte constant pool ending at
 *                        0x96D6; the pool at 0x9780/0x9784/0x9788 holds
 *                        0x0000DB14 / 0x0000FFFF / 0x00005F34).
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_os_task_scheduler.py
 *               (host-gcc vs tools/sh2emu.py over edge + random vectors;
 *               bit-exact return value AND RAM side-effects on the record
 *               area, the running-mark cell and the dispatcher marker cell;
 *               0 mismatches).
 * Lift (truth): c/osTaskScheduler.c  (osTaskScheduler @ 0x9668).  The lift's
 *               asm trace was re-checked against the bytes of 60E1D400.bin
 *               during this port; the lift's "32-byte frame" comment is
 *               corrected here — the frame is 20 bytes (`add #-20,r15`).
 *
 * WHAT THIS IS
 * ------------
 * The central dispatch point of the RX-8 PCM's cooperative RTOS.  The task
 * stubs (@0xA12E..0xA288) each represent one task; they run a timer check,
 * then a schedule wrapper that lands here.  Given (task_id, entry_idx) the
 * function resolves the task entry from the kernel task pointer table, copies
 * the caller's argument words onto a small stack frame and then either
 *  - DIRECT  : marker == 0xFFFF — call the entry's own function pointer with
 *              r4 = &frame[1] (the copied args) and return 0, or
 *  - DISPATCH: marker != 0xFFFF — call the scheduler dispatcher @0x5F34 with
 *              r4 = marker, r5 = frame; return 1 iff the dispatcher result is
 *              non-zero (a reschedule request), else 0.
 *
 * ROM BODY (disassembled 60E1D400.bin @ 0x9668; constant pool @ 0x9780..0x978C:
 *   0x9780 = 0x0000DB14 g_task_table_ptr | 0x9784 = 0x0000FFFF DIRECT marker |
 *   0x9788 = 0x00005F34 dispatcher | 0x978C = 0x0000DB28):
 *
 *     mov.l r14,@-r15            ; save r14 / r13 / r12 / pr
 *     extu.w r5,r5               ; r5  = (uint16_t)entry_idx
 *     mov.l @(0x30,pc),r0        ; r0  = g_task_table_ptr (0xDB14)
 *     shll2 r5 / shll r5         ; r5  = entry_idx * 8
 *     extu.b r4,r13 / shll2 r13  ; r13 = (uint8_t)task_id * 4
 *     add  #-20,r15              ; frame: 20 bytes (5 x u32)
 *     mov  r15,r14               ; r14 = frame
 *     mov.l @(r0,r13),r13        ; r13 = g_task_table[task_id]  (struct base)
 *     add  r5,r13                ; r13 = &entry (base + entry_idx*8)
 *     mov.l @(4,r13),r3          ; r3  = entry.func_ptr
 *     mov  r6,r5                 ; r5  = args
 *     mov.l r3,@r14              ; frame[0] = func_ptr
 *     bra 0x9698 / mov #1,r4     ; r4  = 1 (copy-loop counter)
 *   .loop:
 *     mov  r4,r0 / mov.l @r5+,r3 ; r3  = *args++
 *     shll2 r0 / mov.l r3,@(r0,r14) ; frame[r4] = r3
 *     add  #1,r4
 *   .test:
 *     mov.w @(2,r13),r0          ; r0  = entry.arg_count (u16)
 *     extu.w r0,r0 / cmp/gt r0,r4; while r4 <= arg_count: loop
 *     bf/s 0x968e / nop
 *     mov.w @r13,r4              ; r4  = entry.marker
 *     mov.l @(0x30,pc),r3        ; r3  = 0xFFFF
 *     extu.w r4,r2 / cmp/eq r3,r2
 *     bf/s 0x96ba / mov #0,r12   ; r12 = 0 (default return)
 *   .direct:                     ; marker == 0xFFFF
 *     mov r14,r4 / mov.l @(4,r13),r1
 *     jsr @r1 / add #4,r4        ; call func(&frame[1])
 *     bra 0x96c8 / nop
 *   .dispatch:                   ; marker != 0xFFFF
 *     mov.l @(0x34,pc),r2        ; r2  = dispatcher (0x5F34)
 *     jsr @r2 / mov r14,r5       ; call dispatcher(marker, frame)
 *     tst r0,r0 / bt/s 0x96c8 / nop
 *     mov #1,r12                 ; non-zero result -> reschedule
 *   .exit:
 *     mov r12,r0 / add #20,r15
 *     lds.l @r15+,pr / mov.l @r15+,r12 / mov.l @r15+,r13
 *     rts / mov.l @r15+,r14      ; (delay slot)
 *
 * CALLING CONVENTION
 * ------------------
 * ABI entry (r4 = task_id, r5 = entry_idx, r6 = args).  task_id is truncated
 * to 8 bits, entry_idx to 16 bits.  Returns r0 = 0 (direct call or dispatcher
 * result zero) or r0 = 1 (dispatcher requested a reschedule).
 *
 * FRAME SIZE (a genuine ROM constraint, verified by the harness)
 * ---------------------------------------------------------------
 * The frame is 20 bytes (`add #-20,r15` = 5 x u32), NOT 32 as the lift's
 * comment claims.  The copy loop writes frame[1..arg_count]; for arg_count > 4
 * the real ROM overruns the frame into the pushed saved registers and corrupts
 * the epilogue (pr pops as the 5th copied word — the harness confines the
 * vectors to arg_count <= 4, matching every real task-table entry, whose
 * largest arg_count is 4).
 *
 * SYSTEM COUPLINGS (modelled as parameters — same convention as
 * rx8_task_execute_by_index.c / rx8_task_flag_run_c.c):
 *  * `task_table`  models the 32-bit fetch at 0x9780 (0xDB14).  0xDB14 lies
 *    below this host's mmap_min_addr, so the pointer table is handed in; the
 *    harness seeds byte-identical values on both sides.
 *  * `direct_fn`   models entry.func_ptr: the ROM reads the 32-bit function
 *    address from the (RAM) task entry and calls it.  On the host the entry
 *    still carries the ROM-address value (echoed through frame[0] and compared
 *    bit-exactly via the harness record), while the invocation itself goes
 *    through `direct_fn` — the same parameterisation rx8_task_flag_run_c.c
 *    uses for the task body.
 *  * `rx8_os_dispatcher()`  models the fixed ROM constant 0x5F34 (the
 *    scheduler dispatcher).  Declared external; the host oracle implements the
 *    same tiny stub the emulator harness overlays onto 0x5F34.
 *
 * RAM SIDE-EFFECTS (compared bit-exactly by the harness)
 * ------------------------------------------------------
 * DIRECT path: the record area @0x00101030 (REC[0] = arg_count, then the 32-bit
 * words echoed from frame[0..arg_count] — the entry function pointer followed
 * by the copied args) and the running-mark cell @0x00101058 (0xA5).  DISPATCH
 * path: the dispatcher marker cell @0xFFFFA100 (the marker id the ROM passed
 * in r4) — every other cell stays seeded.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_hw.h"
#include "rx8_samples.h"

/* The frame the ROM allocates with `add #-20,r15` — 5 x u32. */
#define RX8_FRAME_WORDS  5u

/* The dispatcher at fixed ROM address 0x5F34, called when marker != 0xFFFF.
 * Returns non-zero to request a reschedule.  Implemented by the host oracle
 * as the same stub the emulator harness installs over the ROM bytes. */
extern int rx8_os_dispatcher(uint16_t marker, uint32_t *frame);

/* The direct-call target, invoked when marker == 0xFFFF.  Receives
 * r4 = &frame[1] (the first copied argument word), exactly like the ROM's
 * `jsr @r1 / add #4,r4`. */
typedef void (*rx8_os_task_fn)(uint32_t *frame_args);

/* One 8-byte task entry inside a task structure (dense records; the table is
 * indexed by task_id, then entry_idx * 8 bytes). */
struct rx8_task_entry {
    uint16_t marker;       /* +0  0xFFFF -> direct call, else dispatch id */
    uint16_t arg_count;    /* +2  number of u32 args to copy (<= 4)       */
    uint32_t func_ptr;     /* +4  function pointer (32-bit code address)  */
} __attribute__((packed));

/* 0x9668  Look up a task entry, copy the caller args onto the stack frame and
 * dispatch either directly to the entry's function or to the scheduler. */
int rx8_os_task_scheduler(uint8_t task_id, uint16_t entry_idx,
                          const uint32_t *args,
                          const uint32_t *task_table,
                          rx8_os_task_fn direct_fn)
{
    /* g_task_table[task_id] -> task structure base (RAM pointer table). */
    uintptr_t struct_base = task_table[task_id];
    const uint8_t *task_struct = (const uint8_t *)(uintptr_t)struct_base;
    const struct rx8_task_entry *entry =
        (const struct rx8_task_entry *)(task_struct + (uintptr_t)entry_idx * 8u);

    /* 20-byte stack frame: frame[0] = func_ptr, frame[1..arg_count] = args. */
    uint32_t frame[RX8_FRAME_WORDS];
    uint32_t *fp = frame;

    fp[0] = entry->func_ptr;                       /* mov.l r3,@r14          */

    for (uint16_t i = 1; i <= entry->arg_count; i++) {
        fp[i] = args[i - 1];                       /* mov.l @r5+,r3; store   */
    }

    if (entry->marker == 0xFFFFu) {
        direct_fn(&fp[1]);                         /* jsr @func; add #4,r4   */
        return 0;                                  /* mov #0,r12 (r12=0)     */
    }

    if (rx8_os_dispatcher(entry->marker, fp) != 0) {
        return 1;                                  /* mov #1,r12             */
    }
    return 0;
}
