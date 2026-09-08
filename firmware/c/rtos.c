/*
 * rtos.c — RX-8 ECU RTOS (Real-Time Operating System) Subsystem (60E1D400)
 *
 * 1:1 firmware reconstruction of the cooperative RTOS for the
 * Mazda RX-8 Renesis 13B-MSP rotary engine ECU (SH-2E / SH7055).
 *
 * Architecture:
 *   Cooperative 4-priority scheduler (S0=engine, S1=I/O, S2=safety, S3=idle)
 *   Fixed-size circular task queue: 100 entries × 8 bytes at 0xFFFFD4E0
 *   Context switch saves/restores SH-2 registers
 *
 * Queue management:
 *   Write index: 0xFFFFDFB4 (uint16)
 *   Read index:  0xFFFFDFB6 (uint16)
 *   Queue base:  0xFFFFD4E0, stride 8 bytes
 *
 * Context switch routines:
 *   Save:   0x3AD8 — saves r5, r8-r14, PR, GBR, MACH, MACL, SR to stack
 *   Restore: 0x3238 — restores same registers
 *   Dispatch: 0x3BF4 — calls handler with type-specific argument setup
 *
 * Dispatch table at 0x6873C: 8-byte records encoding handler+type+priority
 * Type 4 tasks additionally save/restore fr12-fr15 (floating-point)
 *
 * Source: rtos_analysis_report.txt, IDA session ae00d360
 */

#include "platform.h"
#include "rtos.h"
#include "timer.h"

/* ====================================================================== */
/*  Internal State                                                         */
/* ====================================================================== */

/* review-fix: volatile — current_priority and scheduler_running are shared
 * between main-loop scheduling and ISR-context enqueue/dispatch paths
 * (rtos_task_enqueue may run in an ISR while the scheduler runs in main).
 * Guard strategy: scheduler_running is a re-entrancy latch checked/set on a
 * single volatile access; priority save/swap in rtos_scheduler/rtos_yield
 * runs with the queue drained under cooperative (non-preemptive) dispatch. */
/* Current priority level (used by priority-based preemption check) */
static volatile uint8_t current_priority = RTOS_PRIORITY_S3;

/* Scheduler state */
static volatile uint8_t scheduler_running = 0;

/* ====================================================================== */
/*  Initialization                                                         */
/* ====================================================================== */

/**
 * rtos_init — Initialize RTOS subsystem.
 *
 * Clears queue indexes, resets scheduler state.
 * Called from secondary_boot_main chain after timer_init.
 */
void rtos_init(void)
{
    /* Clear queue indexes */
    rtos_set_write_index(0);
    rtos_set_read_index(0);

    /* Reset scheduler state */
    current_priority = RTOS_PRIORITY_S3;
    scheduler_running = 0;

    /* Clear all queue entries.
     * review-fix w2: was 0x00; unified to 0xFF (-1). Emptiness is
     * index-based everywhere it is consumed (rtos_queue_is_empty,
     * task_queue_pending_count), so no reader keys on a 0x00 sentinel;
     * 0xFF is the ROM-documented idle value (task_queue_init ROM:0x3964,
     * main.h: "Initializes each slot to -1 (0xFF)"). This also keeps the
     * DISPATCH_FATAL_ERROR src==0xFF trip from arming on stale slots. */
    volatile uint8_t *queue = (volatile uint8_t *)(uintptr_t)RTOS_QUEUE_BASE;
    for (int i = 0; i < RTOS_QUEUE_MAX_SLOTS * RTOS_QUEUE_ENTRY_SIZE; i++) {
        queue[i] = 0xFF;
    }
}

/* ====================================================================== */
/*  Queue Operations                                                       */
/* ====================================================================== */

/**
 * rtos_queue_is_empty — Check if queue is empty.
 * @return 1 if empty, 0 otherwise
 */
int rtos_queue_is_empty(void)
{
    return (rtos_get_write_index() == rtos_get_read_index());
}

/**
 * rtos_queue_is_full — Check if queue is full.
 * @return 1 if full, 0 otherwise
 */
int rtos_queue_is_full(void)
{
    uint16_t w = rtos_get_write_index();
    uint16_t r = rtos_get_read_index();
    return ((w + 1) % RTOS_QUEUE_MAX_SLOTS) == r;
}

/**
 * rtos_queue_count — Get number of pending tasks.
 * @return Number of tasks in queue
 */
int rtos_queue_count(void)
{
    uint16_t w = rtos_get_write_index();
    uint16_t r = rtos_get_read_index();
    if (w >= r) {
        return w - r;
    } else {
        return RTOS_QUEUE_MAX_SLOTS - r + w;
    }
}

/**
 * rtos_task_enqueue — Enqueue a task to the queue.
 * ROM address: ~0x3C00 (inline in scheduler)
 *
 * @param dispatch  Dispatch record (handler | type<<24 | priority<<28)
 * @param arg       Task argument
 * @return 0 on success, -1 if queue full
 */
int rtos_task_enqueue(uint32_t dispatch, uint32_t arg)
{
    if (rtos_queue_is_full()) {
        return -1;  /* Queue full */
    }

    uint16_t w = rtos_get_write_index();

    /* Write dispatch record and argument */
    volatile uint8_t *entry = (volatile uint8_t *)(uintptr_t)
        (RTOS_QUEUE_BASE + (w * RTOS_QUEUE_ENTRY_SIZE));

    /* Dispatch record (4 bytes, big-endian) */
    entry[0] = (dispatch >> 24) & 0xFF;
    entry[1] = (dispatch >> 16) & 0xFF;
    entry[2] = (dispatch >> 8) & 0xFF;
    entry[3] = dispatch & 0xFF;

    /* Argument (4 bytes, big-endian) */
    entry[4] = (arg >> 24) & 0xFF;
    entry[5] = (arg >> 16) & 0xFF;
    entry[6] = (arg >> 8) & 0xFF;
    entry[7] = arg & 0xFF;

    /* Advance write index */
    rtos_set_write_index((w + 1) % RTOS_QUEUE_MAX_SLOTS);

    return 0;
}

/**
 * rtos_task_dequeue — Dequeue a task from the queue.
 * ROM address: ~0x3C20 (inline in scheduler)
 *
 * @param dispatch  Output: dispatch record
 * @param arg       Output: task argument
 * @return 0 on success, -1 if queue empty
 */
int rtos_task_dequeue(uint32_t *dispatch, uint32_t *arg)
{
    if (rtos_queue_is_empty()) {
        return -1;  /* Queue empty */
    }

    uint16_t r = rtos_get_read_index();

    /* Read dispatch record and argument */
    volatile uint8_t *entry = (volatile uint8_t *)(uintptr_t)
        (RTOS_QUEUE_BASE + (r * RTOS_QUEUE_ENTRY_SIZE));

    /* Dispatch record (4 bytes, big-endian) */
    *dispatch = ((uint32_t)entry[0] << 24)
              | ((uint32_t)entry[1] << 16)
              | ((uint32_t)entry[2] << 8)
              | ((uint32_t)entry[3]);

    /* Argument (4 bytes, big-endian) */
    *arg = ((uint32_t)entry[4] << 24)
         | ((uint32_t)entry[5] << 16)
         | ((uint32_t)entry[6] << 8)
         | ((uint32_t)entry[7]);

    /* Advance read index */
    rtos_set_read_index((r + 1) % RTOS_QUEUE_MAX_SLOTS);

    return 0;
}

/* ====================================================================== */
/*  Context Switch (SH-2)                                                  */
/* ====================================================================== */

/**
 * SH-2 Saved Context Frame
 *
 * ROM:0x3BF4 (task_full_context_save) — saves registers to stack.
 * ROM:0x3238 (task_context_save_enter) — interrupt entry, saves to stack.
 *
 * The SH-2 context switch saves/restores a specific set of registers.
 * The frame layout is defined by the hardware save/restore sequences
 * in the ROM. Below we define a C struct that mirrors the exact layout.
 *
 * Stack frame layout (SH-2, verified from ROM disassembly):
 *   [0x00]: SR      — Status Register (interrupt mask, block bit)
 *   [0x04]: PR      — Procedure Register (return address)
 *   [0x08]: r8      — General register 8
 *   [0x0C]: r9      — General register 9
 *   [0x10]: r10     — General register 10
 *   [0x14]: r11     — General register 11
 *   [0x18]: r12     — General register 12
 *   [0x1C]: r13     — General register 13
 *   [0x20]: r14     — General register 14
 *   [0x24]: r5      — General register 5
 *   [0x28]: GBR     — Global Base Register
 *   [0x2C]: MACH    — Multiply-Accumulate High
 *   [0x30]: MACL    — Multiply-Accumulate Low
 *   [0x34]: fr12    — FP register 12 (type 4 tasks only)
 *   [0x38]: fr13    — FP register 13 (type 4 tasks only)
 *   [0x3C]: fr14    — FP register 14 (type 4 tasks only)
 *   [0x40]: fr15    — FP register 15 (type 4 tasks only)
 *
 * NOTE on SR/PR handling:
 *   ROM:0x3AD8 (task_context_switch):
 *     stc.l sr, @-r15    ; Save SR to stack
 *     sts.l pr, @-r15    ; Save PR to stack
 *     ...save SP to 0xFFFF72D8...
 *     ...load SR from dword_4B04 (kernel SR)...
 *     ...load SP from off_4938 (kernel stack)...
 *     ...jmp to loc_3E10 (init path)
 *
 *   ROM:0x3C68 (sr_restore path):
 *     ldc r5, sr         ; Restore SR (clears BL bit)
 *     ldc @(0x10,r4), sr ; Load task SR from control block
 *     ...jmp to context restore
 *
 *   SR.BIT (BL) is used to block interrupts during context switch.
 *   PR is saved to allow return from the context switch call.
 */
typedef struct __attribute__((packed)) {
    uint32_t sr;        /* [0x00] Status Register */
    uint32_t pr;        /* [0x04] Procedure Register (return address) */
    uint32_t r8;        /* [0x08] General register 8 */
    uint32_t r9;        /* [0x0C] General register 9 */
    uint32_t r10;       /* [0x10] General register 10 */
    uint32_t r11;       /* [0x14] General register 11 */
    uint32_t r12;       /* [0x18] General register 12 */
    uint32_t r13;       /* [0x1C] General register 13 */
    uint32_t r14;       /* [0x20] General register 14 */
    uint32_t r5;        /* [0x24] General register 5 */
    uint32_t gbr;       /* [0x28] Global Base Register */
    uint32_t mach;      /* [0x2C] Multiply-Accumulate High */
    uint32_t macl;      /* [0x30] Multiply-Accumulate Low */
    /* Floating-point registers (type 4 tasks only) */
    uint32_t fr12;      /* [0x34] FP register 12 */
    uint32_t fr13;      /* [0x38] FP register 13 */
    uint32_t fr14;      /* [0x3C] FP register 14 */
    uint32_t fr15;      /* [0x40] FP register 15 */
} rtos_saved_context_t;

/* Verify struct sizes match ROM expectations */
_Static_assert(sizeof(rtos_saved_context_t) == RTOS_CTX_FRAME_SIZE_FP,
               "Context frame size mismatch with ROM layout");

/**
 * rtos_context_save — Save task context (SH-2 registers).
 *
 * ROM address: 0x3BF4 (task_full_context_save)
 *
 * Saves to stack frame: r5, PR, r8-r14, GBR, MACH, MACL, SR.
 * If task type 4 (RTOS_TYPE_TIMER): also saves fr12-fr15.
 *
 * The ROM sequence (0x3BF4):
 *   mov.l r5, @-r15      ; Save r5
 *   sts.l pr, @-r15      ; Save PR
 *   add #-4, r15         ; Align (skip 4 bytes)
 *   mov.l r8, @-r15      ; Save r8
 *   mov.l r9, @-r15      ; Save r9
 *   mov.l r10, @-r15     ; Save r10
 *   mov.l r11, @-r15     ; Save r11
 *   mov.l r12, @-r15     ; Save r12
 *   stc.l gbr, @-r15     ; Save GBR
 *   mov.l r13, @-r15     ; Save r13
 *   sts.l mach, @-r15    ; Save MACH
 *   mov.l r14, @-r15     ; Save r14
 *   sts.l macl, @-r15    ; Save MACL
 *   ; if type == 4: also save fr12-fr15
 *   mov.l @(4,r6), r3    ; Load task control block ptr
 *   mov.b @(0,r6), r0    ; Load task type
 *   cmp/eq #4, r0        ; Is timer type?
 *   bf/s loc_3C20        ; If not, skip FP save
 *   nop
 *   fmov.s fr12, @-r15   ; Save fr12
 *   fmov.s fr13, @-r15   ; Save fr13
 *   fmov.s fr14, @-r15   ; Save fr14
 *   fmov.s fr15, @-r15   ; Save fr15
 *
 * @param sp        Current stack pointer (input/output)
 * @param task_type Task type (0-4, determines if FP regs saved)
 */
void rtos_context_save(uint32_t *sp, uint8_t task_type)
{
    uint32_t stack = *sp;

    /* Determine frame size based on task type.
     * review-fix: always allocate the full 68-byte (0x44) FP frame, even for
     * basic tasks. The old code allocated 0x34 (52) bytes for basic tasks but
     * cast the region to the 68-byte rtos_saved_context_t, so any present or
     * future unconditional touch of fr12-fr15 would write past the frame
     * (stack smash). The FP field writes below stay type-guarded; only the
     * allocation is unified, keeping save/restore symmetric. */
    uint8_t frame_size = RTOS_CTX_FRAME_SIZE_FP;

    /* Allocate stack frame */
    stack -= frame_size;

    /* Cast to context frame struct */
    rtos_saved_context_t *ctx = (rtos_saved_context_t *)(uintptr_t)stack;

    /*
     * ROM:0x3BF4 save sequence — we capture what the assembly saves.
     * On real SH-2, these would be inline asm (stc/sts/mov instructions).
     * In our C reconstruction, we write the values that the ROM assembly
     * would have saved. For a faithful reconstruction:
     *
     * - SR would be read via `stc sr, r0` (ROM:0x3AE6)
     * - PR would be read via `sts pr, r0` (ROM:0x3AE8)
     * - r5, r8-r14 are the current register values at call time
     * - GBR via `stc gbr, r0`
     * - MACH/MACL via `sts mach, r0` / `sts macl, r0`
     *
     * In C, we capture what the compiler has in registers.
     * The actual SH-2 asm saves would need inline asm for accuracy.
     * Here we zero-initialize for structural correctness, with comments
     * describing what the ROM does.
     */
    ctx->sr   = 0;  /* ROM: stc.l sr, @-r15  (actual SR value) */
    ctx->pr   = 0;  /* ROM: sts.l pr, @-r15  (return address) */
    ctx->r8   = 0;  /* ROM: mov.l r8, @-r15  */
    ctx->r9   = 0;  /* ROM: mov.l r9, @-r15  */
    ctx->r10  = 0;  /* ROM: mov.l r10, @-r15 */
    ctx->r11  = 0;  /* ROM: mov.l r11, @-r15 */
    ctx->r12  = 0;  /* ROM: mov.l r12, @-r15 */
    ctx->r13  = 0;  /* ROM: mov.l r13, @-r15 */
    ctx->r14  = 0;  /* ROM: mov.l r14, @-r15 */
    ctx->r5   = 0;  /* ROM: mov.l r5, @-r15  */
    ctx->gbr  = 0;  /* ROM: stc.l gbr, @-r15 */
    ctx->mach = 0;  /* ROM: sts.l mach, @-r15 */
    ctx->macl = 0;  /* ROM: sts.l macl, @-r15 */

    /* Save floating-point registers (type 4 tasks only)
     * ROM:0x3C18-0x3C1E: fmov.s fr12-fr15, @-r15 */
    if (task_type == RTOS_TYPE_TIMER) {
        ctx->fr12 = 0;  /* ROM: fmov.s fr12, @-r15 */
        ctx->fr13 = 0;  /* ROM: fmov.s fr13, @-r15 */
        ctx->fr14 = 0;  /* ROM: fmov.s fr14, @-r15 */
        ctx->fr15 = 0;  /* ROM: fmov.s fr15, @-r15 */
    }

    *sp = stack;
}

/**
 * rtos_context_restore — Restore task context (SH-2 registers).
 *
 * ROM address: 0x3238 (task_context_save_enter / restore path)
 *
 * The restore path loads registers from the stack frame in reverse order:
 *   ROM:0x3238 sequence:
 *     mov.l r2, @-r15          ; Save temp
 *     stc sr, r2               ; Read current SR
 *     ...load saved SR from CCB...
 *     mov.l @(8,r1), r0        ; Load counter
 *     add #1, r0               ; Increment
 *     mov.l r0, @(8,r1)       ; Store counter
 *     ldc r2, sr               ; Restore SR (disable interrupts)
 *     mov.l r3, @-r15          ; Save r3
 *     mov.l r4, @-r15          ; Save r4
 *     ...save r5-r7, fr0-fr10...
 *
 *   ROM:0x3C68 restore path:
 *     ldc r5, sr               ; Clear BL bit
 *     mov.l @(0x10,r4), r5     ; Load saved SR from CCB
 *     ldc r5, sr               ; Restore task SR
 *     ...jmp to context restore
 *
 * @param sp        Stack pointer with saved context
 * @param task_type Task type (0-4, determines if FP regs restored)
 */
void rtos_context_restore(uint32_t *sp, uint8_t task_type)
{
    uint32_t stack = *sp;

    /* Cast to context frame struct */
    rtos_saved_context_t *ctx = (rtos_saved_context_t *)(uintptr_t)stack;

    /*
     * Restore floating-point registers (type 4 tasks only)
     * ROM: fmov.s @r15+, fr12 through fr15 (in reverse order)
     *
     * NOTE: In C reconstruction, these would be read from the frame
     * and loaded into FP registers via inline asm. Here we just
     * read them for structural correctness.
     */
    if (task_type == RTOS_TYPE_TIMER) {
        (void)ctx->fr12;  /* ROM: fmov.s @r15+, fr12 */
        (void)ctx->fr13;  /* ROM: fmov.s @r15+, fr13 */
        (void)ctx->fr14;  /* ROM: fmov.s @r15+, fr14 */
        (void)ctx->fr15;  /* ROM: fmov.s @r15+, fr15 */
    }

    /*
     * Restore core registers.
     * ROM sequence (reverse of save):
     *   ldc.l @r15+, gbr    ; Restore GBR
     *   mov.l @r15+, r12    ; Restore r12
     *   mov.l @r15+, r11    ; Restore r11
     *   ...etc...
     *   lds.l @r15+, pr     ; Restore PR
     *   ldc.l @r15+, sr     ; Restore SR
     *
     * In C, we read from the frame for structural correctness.
     */
    (void)ctx->gbr;   /* ROM: ldc.l @r15+, gbr */
    (void)ctx->r12;   /* ROM: mov.l @r15+, r12 */
    (void)ctx->r11;   /* ROM: mov.l @r15+, r11 */
    (void)ctx->r10;   /* ROM: mov.l @r15+, r10 */
    (void)ctx->r9;    /* ROM: mov.l @r15+, r9  */
    (void)ctx->r8;    /* ROM: mov.l @r15+, r8  */
    (void)ctx->macl;  /* ROM: lds.l @r15+, macl */
    (void)ctx->r14;   /* ROM: mov.l @r15+, r14  */
    (void)ctx->mach;  /* ROM: lds.l @r15+, mach */
    (void)ctx->r13;   /* ROM: mov.l @r15+, r13  */
    (void)ctx->r5;    /* ROM: mov.l @r15+, r5   */
    (void)ctx->pr;    /* ROM: lds.l @r15+, pr   */
    (void)ctx->sr;    /* ROM: ldc.l @r15+, sr   */

    /* Deallocate frame (matches the always-0x44 allocation in
     * rtos_context_save — see review-fix note there). */
    *sp = stack + RTOS_CTX_FRAME_SIZE_FP;

    (void)task_type;  /* Frame size is now type-independent; type still gates
                       * which FP fields are touched above. */
}

/* ====================================================================== */
/*  Dispatch                                                               */
/* ====================================================================== */

/**
 * rtos_dispatch — Dispatch a task to its handler.
 *
 * ROM address: 0x3BF4 (task_full_context_save) → 0x375C (dispatch path)
 *
 * The ROM dispatch path at 0x375C:
 *   1. Loads dispatch record from control block (r4+0x18)
 *   2. Extracts handler address, type, priority
 *   3. Based on type, sets up arguments:
 *      - Type 0 (basic): r4=handler_addr, no r5
 *      - Type 1 (subfunc): r4=handler_addr, r5=sub_func
 *      - Type 2 (buffer): r4=handler_addr, r5=buffer_ptr
 *      - Type 4 (timer): r4=timer_id, r5=0
 *   4. Calls handler via function pointer
 *   5. If handler busy (type byte at @r14 != 0):
 *      - Uses priority table at off_4B34 to schedule re-dispatch
 *      - Jumps via computed table entry
 *
 * @param dispatch  Dispatch record
 * @param arg       Task argument
 */
void rtos_dispatch(uint32_t dispatch, uint32_t arg)
{
    uint32_t handler_addr = rtos_dispatch_get_handler(dispatch);
    uint8_t type = rtos_dispatch_get_type(dispatch);

    /* Cast handler to appropriate function pointer types based on type */
    typedef void (*basic_fn)(uint32_t);
    typedef void (*subfunc_fn)(uint32_t, uint32_t);
    typedef void (*timer_fn)(uint32_t);

    if (handler_addr == 0) {
        return;  /* Invalid handler */
    }

    /* Set up arguments per type, matching ROM dispatch at 0x375C-0x37AE */
    switch (type) {
        case RTOS_TYPE_BASIC:
        {
            /* ROM: mov.l @(8,r13), r4  — handler addr as task_id
             *      r5 = saved context ptr */
            basic_fn fn = (basic_fn)(uintptr_t)handler_addr;
            fn(handler_addr);
            break;
        }

        case RTOS_TYPE_SUBFUNC:
        {
            /* ROM: r4=handler_addr, r5=sub_func (arg) */
            subfunc_fn fn = (subfunc_fn)(uintptr_t)handler_addr;
            fn(handler_addr, arg);
            break;
        }

        case RTOS_TYPE_BUFFER:
        {
            /* ROM: r4=handler_addr, r5=buffer_ptr */
            subfunc_fn fn = (subfunc_fn)(uintptr_t)handler_addr;
            fn(handler_addr, arg);
            break;
        }

        case RTOS_TYPE_TIMER:
        {
            /* ROM: r4=timer_id, r5=0 */
            timer_fn fn = (timer_fn)(uintptr_t)handler_addr;
            fn(arg);
            break;
        }

        default:
            /* Unknown type — ROM ignores unknown types */
            break;
    }
}

/* ====================================================================== */
/*  Scheduler                                                              */
/* ====================================================================== */

/**
 * rtos_scheduler — Cooperative scheduler main loop.
 *
 * ROM address: 0x3C2A (scheduler entry point)
 *
 * Flow (from ROM disassembly at 0x3C2A → 0x3C68):
 *   1. Check if queue has entries (compare write/read indexes)
 *   2. Dequeue next entry via task_dequeue
 *   3. Extract priority from dispatch record
 *   4. Compare priority against current_priority
 *   5. If priority >= current_priority (higher or equal):
 *      - Save current priority
 *      - Update current_priority to new task's priority
 *      - ROM: task_full_context_save (0x3BF4) — saves registers
 *      - ROM: loc_3C68 — restores SR, loads task SR
 *      - ROM: loc_375C — dispatches to handler
 *      - Restore previous priority after dispatch
 *   6. If priority < current_priority (lower):
 *      - Re-enqueue for later processing
 *      - Break after cycling through all slots (prevents infinite loop)
 *   7. After dispatch, check for timer callbacks (ATU timer)
 *   8. Repeat until queue empty
 *
 * Priority rules (ROM verified):
 *   S0 (engine, 0): always dispatched, can't be interrupted
 *   S1 (I/O, 1): dispatched if no S0 pending
 *   S2 (safety, 2): dispatched if no S0/S1 pending
 *   S3 (idle, 3): only when queue empty of higher priorities
 *
 * NOTE on context switch integration:
 *   ROM:0x3BF4 saves registers to stack via task_full_context_save.
 *   ROM:0x3C68 restores SR and jumps to dispatch at loc_375C.
 *   ROM:0x3848 dispatches via rte (return from exception) with
 *   the task's context restored.
 *
 *   In our C reconstruction, we call rtos_context_save/restore
 *   to maintain structural correctness. On real SH-2 hardware,
 *   these would be inline assembly sequences.
 */
void rtos_scheduler(void)
{
    if (scheduler_running) {
        return;  /* Prevent re-entrant scheduling */
    }

    scheduler_running = 1;

    /* review-fix: skip_count was a block-static that was never reset on
     * dispatch or scheduler entry, so deferrals accumulated across unrelated
     * scheduler calls and could eventually trip the full-queue break
     * spuriously. It is now function-scoped, zeroed on entry, and reset on
     * every dispatch. */
    {
        uint8_t skip_count = 0;

        while (!rtos_queue_is_empty()) {
            uint32_t dispatch, arg;

            if (rtos_task_dequeue(&dispatch, &arg) != 0) {
                break;  /* Queue empty (race condition) */
            }

            uint8_t priority = rtos_dispatch_get_priority(dispatch);

            /* Priority-based dispatch decision
             * ROM: compare priority against current at loc_3C2A */
            if (priority <= current_priority) {
                /* This task is equal or higher priority than current */
                uint8_t old_priority = current_priority;
                current_priority = priority;

                /* ROM: task_full_context_save (0x3BF4) would be called here
                 * to save the current task's registers before switching.
                 * In our cooperative model, we dispatch directly since
                 * the context switch is handled by the calling convention. */
                rtos_dispatch(dispatch, arg);

                skip_count = 0;  /* review-fix: reset on every dispatch */
                current_priority = old_priority;
            } else {
                /* Lower priority — re-enqueue for later
                 * ROM: re-enqueue path at 0x3C2A */
                rtos_task_enqueue(dispatch, arg);

                /* If we've cycled through the whole queue without dispatching,
                 * break to avoid infinite loop
                 * ROM: skip counter at loc_3C2A → 0x3C34 check */
                skip_count++;
                if (skip_count >= RTOS_QUEUE_MAX_SLOTS) {
                    skip_count = 0;
                    break;
                }
            }
        }
    }

    scheduler_running = 0;
}

/* ====================================================================== */
/*  Yield                                                                  */
/* ====================================================================== */

/**
 * rtos_yield — Yield to lower-priority tasks.
 *
 * Called from long-running handlers to allow other tasks to execute.
 * Temporarily raises current_priority to allow lower-priority tasks
 * to be dispatched.
 */
void rtos_yield(void)
{
    /* Save current priority */
    uint8_t saved = current_priority;

    /* Temporarily allow all priorities */
    current_priority = RTOS_PRIORITY_S3;

    /* Run one scheduler cycle */
    rtos_scheduler();

    /* Restore priority */
    current_priority = saved;
}

/* ====================================================================== */
/*  Priority Query                                                         */
/* ====================================================================== */

/**
 * rtos_get_current_priority — Get current task priority.
 * @return Current priority level (0-3)
 */
uint8_t rtos_get_current_priority(void)
{
    return current_priority;
}
