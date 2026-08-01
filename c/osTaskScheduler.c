/*
 * osTaskScheduler.c  —  RX-8 PCM @ ROM 0x9668 (60E1D400), xmapped from equinox
 * hand-Ghidra name. The core RTOS task dispatcher: looks up a task entry by
 * (task_id, entry_idx), copies caller arguments onto a stack frame, then either
 * calls the task function directly (marker == 0xFFFF) or dispatches through the
 * scheduler at 0x5F34 (marker != 0xFFFF).
 *
 * This is the central dispatch point for the ECU's cooperative multitasking
 * RTOS.  Task stubs (at 0xA12E..0xA288) each represent one task; they call a
 * timer check (0x3854), then a schedule wrapper (0xA486), ultimately reaching
 * here to execute the actual task function.
 *
 * SH-2E calling convention: int args r4..r6, return r0.
 *
 * Original SH-2E (big-endian SH-2A, 110 bytes from 0x9668):
 *
 *   ; r4 = task_id (uint8_t), r5 = entry_idx (uint16_t), r6 = args (uint32_t*)
 *   0x9668: mov.l r14,@-r15        ; save r14
 *   0x966A: extu.w r5,r5           ; r5 = (uint16_t)entry_idx
 *   0x966C: mov.l 0x9780,r0        ; r0 = g_task_table_ptr (= 0xDB14)
 *   0x966E: shll2 r5               ; r5 = entry_idx * 4
 *   0x9670: mov.l r13,@-r15        ; save r13
 *   0x9672: shll r5                ; r5 = entry_idx * 8
 *   0x9674: mov.l r12,@-r15        ; save r12
 *   0x9676: extu.b r4,r13          ; r13 = (uint8_t)task_id
 *   0x9678: sts.l pr,@-r15         ; save pr
 *   0x967A: shll2 r13              ; r13 = task_id * 4
 *   0x967C: add #-20,r15           ; allocate 32-byte frame
 *   0x967E: mov r15,r14            ; r14 = frame pointer
 *   0x9680: mov.l @(r0,r13),r13    ; r13 = g_task_table[task_id]
 *   0x9682: add r5,r13             ; r13 = &task_struct[entry_idx]
 *   0x9684: mov.l @(4,r13),r3      ; r3 = entry.func_ptr
 *   0x9686: mov r6,r5              ; r5 = args (was r6)
 *   0x9688: mov.l r3,@r14          ; frame[0] = func_ptr
 *   0x968A: bra 0x9698             ; jump to loop test
 *   0x968C: mov #1,r4              ; r4 = 1  (delay slot: loop counter)
 *
 *   ; copy-loop body
 *   0x968E: mov r4,r0              ; r0 = counter
 *   0x9690: mov.l @r5+,r3          ; r3 = *args++
 *   0x9692: shll2 r0               ; r0 = counter * 4
 *   0x9694: mov.l r3,@(r0,r14)     ; frame[counter] = r3
 *   0x9696: add #1,r4              ; counter++
 *
 *   ; loop test
 *   0x9698: mov.w @(2,r13),r0      ; r0 = entry.arg_count (u16 at r13+2)
 *   0x969A: extu.w r0,r0           ; zero-extend
 *   0x969C: cmp/gt r0,r4           ; is counter > arg_count?
 *   0x969E: bf/s 0x968e            ; if not, loop back
 *   0x96A0: nop
 *
 *   0x96A2: mov.w @r13,r4          ; r4 = entry.marker (u16 at r13+0)
 *   0x96A4: mov.l 0x9784,r3        ; r3 = 0xFFFF (DIRECT_CALL_MARKER)
 *   0x96A6: extu.w r4,r2           ; r2 = (uint16_t)marker
 *   0x96A8: cmp/eq r3,r2           ; marker == 0xFFFF?
 *   0x96AA: bf/s 0x96ba            ; if not, go to dispatcher path
 *   0x96AC: mov #0,r12             ; r12 = 0 (delay slot: default return)
 *
 *   ; DIRECT CALL: marker == 0xFFFF
 *   0x96AE: mov r14,r4             ; r4 = frame
 *   0x96B0: mov.l @(4,r13),r1      ; r1 = entry.func_ptr (reload)
 *   0x96B2: jsr @r1                ; call func_ptr(frame+4) with r4 = frame
 *   0x96B4: add #4,r4              ; r4 = &frame[1] (first arg) (delay slot)
 *   0x96B6: bra 0x96c8             ; goto epilogue
 *   0x96B8: nop
 *
 *   ; DISPATCHER PATH: marker != 0xFFFF  (marker is a handler ID)
 *   0x96BA: mov.l 0x9788,r2        ; r2 = g_dispatcher_fn (= 0x5F34)
 *   0x96BC: jsr @r2                ; call dispatcher(frame)
 *   0x96BE: mov r14,r5             ; r5 = frame (delay slot)
 *   0x96C0: tst r0,r0              ; test dispatcher result
 *   0x96C2: bt/s 0x96c8            ; if zero, skip
 *   0x96C4: nop
 *   0x96C6: mov #1,r12             ; r12 = 1 (reschedule requested)
 *
 *   ; epilogue
 *   0x96C8: mov r12,r0             ; r0 = return value (0 or 1)
 *   0x96CA: add #20,r15            ; deallocate frame
 *   0x96CC: lds.l @r15+,pr         ; restore pr
 *   0x96CE: mov.l @r15+,r12        ; restore r12
 *   0x96D0: mov.l @r15+,r13        ; restore r13
 *   0x96D2: rts
 *   0x96D4: mov.l @r15+,r14        ; restore r14 (delay slot)
 *
 * Track A candidate — NOT YET VERIFIED against the emulated ROM.
 * The function is inherently system-coupling: it reads indexed ROM structures
 * and calls indirect function pointers.  A mock of the task table and the
 * dispatcher is needed for host-side verification.
 */
#include <stdint.h>

/* ------------------------------------------------------------------ */
/*  ROM data tables                                                    */
/* ------------------------------------------------------------------ */

/* The global task table pointer at ROM 0x9780 (loaded as a 32-bit literal).
 * In 60E1D400: *(uint32_t *)0x9780 = 0x0000DB14.
 * This is the base of a pointer table indexed by task_id (0..N).
 * Each entry is a uint32_t pointer to a task structure (an array of
 * 8-byte TaskEntry records).  */
#define G_TASK_TABLE_PTR  (*(const uint32_t *)0x9780)

/* When entry.marker == 0xFFFF the task is called directly (no dispatching). */
#define DIRECT_CALL_MARKER  0xFFFFu

/* The dispatcher function at 0x5F34, used when entry.marker != 0xFFFF.
 * int dispatcher(uint16_t marker_id, uint32_t *frame);
 * The marker ID encodes the task type/priority for the scheduler. */
#define DISPATCHER_ADDR     (*(const uint32_t *)0x9788)   /* = 0x5F34 */

/* ------------------------------------------------------------------ */
/*  Data types                                                         */
/* ------------------------------------------------------------------ */

/** One entry within a task structure.  Task entries are densely packed
 *  in 8-byte records (confirmed from the SH-2E big-endian ROM layout).
 *  A task block is a variable-length array of these entries.
 *
 *  NOTE: On the SH-2E, func_ptr is stored as a 32-bit code address.
 *  For host-side testing we treat it as uint32_t and cast at call sites. */
struct TaskEntry {
    uint16_t marker;        /* +0: 0xFFFF → direct call, else dispatch ID  */
    uint16_t arg_count;     /* +2: how many extra u32 args to copy         */
    uint32_t func_ptr;      /* +4: function pointer (32-bit code address)  */
} __attribute__((packed));

/* ------------------------------------------------------------------ */
/*  osTaskScheduler                                                    */
/* ------------------------------------------------------------------ */

/**
 * osTaskScheduler  —  lookup a task entry, prepare args, and dispatch.
 *
 * @param task_id   8-bit index into the global task pointer table.
 *                  Each entry in that table points to a task structure
 *                  (an array of 8-byte TaskEntry records).
 * @param entry_idx Index of the entry within the task structure to
 *                  dispatch (entry is at offset entry_idx * 8).
 * @param args      Pointer to caller-supplied argument words.  Exactly
 *                  entry.arg_count words are copied onto the stack frame
 *                  before the call.
 * @return 0 on normal completion, 1 if the dispatcher requested a
 *         reschedule (only meaningful when marker != 0xFFFF).
 *
 * Behavioral notes:
 *   - If entry.marker == 0xFFFF, the function at entry.func_ptr is called
 *     directly as:  func_ptr(&stack_frame[1]), i.e. the first argument is
 *     the address of the copied args on the stack.
 *   - If entry.marker != 0xFFFF, the dispatcher at DISPATCHER_ADDR is
 *     called with r4 = marker and r5 = stack frame pointer.  The
 *     dispatcher manages queue insertion, priority, etc., and returns
 *     0 (done) or 1 (task was re-queued).
 *   - The stack frame is 32 bytes (8 × u32).  frame[0] holds the function
 *     pointer; frame[1..arg_count] hold the copied args.
 */
int osTaskScheduler(uint8_t task_id, uint16_t entry_idx, const uint32_t *args)
{
    /* Resolve the global task table.
     * G_TASK_TABLE_PTR is a uint32_t loaded from ROM (32-bit SH-2A address).
     * Cast through uintptr_t for host portability. */
    uintptr_t table_base = G_TASK_TABLE_PTR;
    const uint32_t *task_table = (const uint32_t *)table_base;

    /* Get the task structure pointer for this task_id */
    uintptr_t struct_base = task_table[task_id];
    const uint8_t *task_struct = (const uint8_t *)struct_base;

    /* Locate the specific entry within the task structure */
    const struct TaskEntry *entry =
        (const struct TaskEntry *)(task_struct + (entry_idx * 8u));

    /* Allocate a stack frame (32 bytes).  In the original SH-2E this
     * is add #-20,r15 (32 bytes).  We model it as a local array. */
    uint32_t frame[8];
    uint32_t *fp = frame;

    /* Save the function pointer at frame[0] */
    fp[0] = entry->func_ptr;

    /* Copy arg_count words from caller args to frame[1..] */
    uint16_t count = entry->arg_count;
    uint16_t i;
    const uint32_t *ap = args;
    for (i = 1; i <= count; i++) {
        fp[i] = *ap++;
    }

    /* Check the marker to decide dispatch method */
    uint8_t result = 0;          /* r12 in the original */

    if (entry->marker == DIRECT_CALL_MARKER) {
        /* Direct call: invoke the function pointer.
         * The SH-2E convention passes r4 = &frame[1] (first argument).
         * On the target (SH-2A) pointers are 32 bits; on the host we use
         * uintptr_t to bridge the size gap. */
        void (*func)(uint32_t *) = (void (*)(uint32_t *))(uintptr_t)(uint32_t)entry->func_ptr;
        func(&fp[1]);
    } else {
        /* Dispatcher path: call the scheduler dispatcher.
         * The dispatcher receives r4=marker, r5=frame pointer. */
        int (*dispatcher)(uint16_t, uint32_t *) =
            (int (*)(uint16_t, uint32_t *))(uintptr_t)(uint32_t)DISPATCHER_ADDR;
        int dispatcher_result = dispatcher(entry->marker, fp);
        if (dispatcher_result != 0) {
            result = 1;          /* reschedule requested */
        }
    }

    return result;
}
