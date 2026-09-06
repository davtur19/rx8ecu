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

/* Current priority level (used by priority-based preemption check) */
static uint8_t current_priority = RTOS_PRIORITY_S3;

/* Scheduler state */
static uint8_t scheduler_running = 0;

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

    /* Clear all queue entries */
    volatile uint8_t *queue = (volatile uint8_t *)(uintptr_t)RTOS_QUEUE_BASE;
    for (int i = 0; i < RTOS_QUEUE_MAX_SLOTS * RTOS_QUEUE_ENTRY_SIZE; i++) {
        queue[i] = 0;
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
 * rtos_context_save — Save task context (SH-2 registers).
 * ROM address: 0x3AD8, Size: ~60 bytes
 *
 * Saves to stack: r5, r8-r14, PR, GBR, MACH, MACL, SR
 * If task type 4: also saves fr12-fr15 (floating-point)
 *
 * SH-2 stack frame layout:
 *   [SP+0x00]: SR
 *   [SP+0x04]: PR (return address)
 *   [SP+0x08]: r8
 *   [SP+0x0C]: r9
 *   [SP+0x10]: r10
 *   [SP+0x14]: r11
 *   [SP+0x18]: r12
 *   [SP+0x1C]: r13
 *   [SP+0x20]: r14
 *   [SP+0x24]: r5
 *   [SP+0x28]: GBR
 *   [SP+0x2C]: MACH
 *   [SP+0x30]: MACL
 *   [SP+0x34]: fr12 (type 4 only)
 *   [SP+0x38]: fr13 (type 4 only)
 *   [SP+0x3C]: fr14 (type 4 only)
 *   [SP+0x40]: fr15 (type 4 only)
 *
 * @param sp        Current stack pointer (input/output)
 * @param task_type Task type (0-4, determines if FP regs saved)
 */
void rtos_context_save(uint32_t *sp, uint8_t task_type)
{
    uint32_t stack = *sp;

    /* Determine frame size */
    uint8_t frame_size = (task_type == RTOS_TYPE_TIMER)
                         ? RTOS_CTX_FRAME_SIZE_FP
                         : RTOS_CTX_FRAME_SIZE;

    /* Allocate stack frame */
    stack -= frame_size;

    /* Save core registers */
    volatile uint32_t *frame = (volatile uint32_t *)(uintptr_t)stack;

    /* TODO: Actual SH-2 register save uses inline assembly.
     * The ROM implementation at 0x3AD8 uses mov instruction sequence:
     *   stc.l sr, @-sp
     *   sts.l pr, @-sp
     *   mov.l r8, @(0x08, sp)
     *   mov.l r9, @(0x0C, sp)
     *   ... etc
     *
     * For the C reconstruction, we provide the structural framework.
     * Full assembly is needed for actual register save/restore. */

    /* Placeholder: write known values for verification */
    frame[0] = 0x00000000;  /* SR — will be overwritten by stc sr */
    frame[1] = 0x00000000;  /* PR — will be overwritten by sts pr */
    frame[2] = 0x00000000;  /* r8 */
    frame[3] = 0x00000000;  /* r9 */
    frame[4] = 0x00000000;  /* r10 */
    frame[5] = 0x00000000;  /* r11 */
    frame[6] = 0x00000000;  /* r12 */
    frame[7] = 0x00000000;  /* r13 */
    frame[8] = 0x00000000;  /* r14 */
    frame[9] = 0x00000000;  /* r5 */
    frame[10] = 0x00000000; /* GBR */
    frame[11] = 0x00000000; /* MACH */
    frame[12] = 0x00000000; /* MACL */

    /* Save floating-point registers (type 4 tasks only) */
    if (task_type == RTOS_TYPE_TIMER) {
        volatile uint32_t *fp = (volatile uint32_t *)(uintptr_t)(stack + 0x34);
        fp[0] = 0x00000000; /* fr12 */
        fp[1] = 0x00000000; /* fr13 */
        fp[2] = 0x00000000; /* fr14 */
        fp[3] = 0x00000000; /* fr15 */
    }

    *sp = stack;
}

/**
 * rtos_context_restore — Restore task context (SH-2 registers).
 * ROM address: 0x3238, Size: ~60 bytes
 *
 * Restores from stack: r5, r8-r14, PR, GBR, MACH, MACL, SR
 * If task type 4: also restores fr12-fr15
 *
 * @param sp        Stack pointer with saved context
 * @param task_type Task type (0-4, determines if FP regs restored)
 */
void rtos_context_restore(uint32_t *sp, uint8_t task_type)
{
    uint32_t stack = *sp;

    /* TODO: Actual SH-2 register restore uses inline assembly.
     * The ROM implementation at 0x3238 uses mov instruction sequence:
     *   mov.l @(0x08, sp), r8
     *   mov.l @(0x0C, sp), r9
     *   ... etc
     *   lds.l @sp+, pr
     *   ldc.l @sp+, sr
     *
     * For the C reconstruction, we provide the structural framework. */

    /* Restore floating-point registers (type 4 tasks only) */
    if (task_type == RTOS_TYPE_TIMER) {
        volatile uint32_t *fp = (volatile uint32_t *)(uintptr_t)(stack + 0x34);
        (void)fp[0]; /* fr12 */
        (void)fp[1]; /* fr13 */
        (void)fp[2]; /* fr14 */
        (void)fp[3]; /* fr15 */
    }

    /* Determine frame size and deallocate */
    uint8_t frame_size = (task_type == RTOS_TYPE_TIMER)
                         ? RTOS_CTX_FRAME_SIZE_FP
                         : RTOS_CTX_FRAME_SIZE;

    *sp = stack + frame_size;
}

/* ====================================================================== */
/*  Dispatch                                                               */
/* ====================================================================== */

/**
 * rtos_dispatch — Dispatch a task to its handler.
 * ROM address: 0x3BF4, Size: ~40 bytes
 *
 * Reads dispatch record, extracts handler/type/priority,
 * sets up arguments based on type:
 *   Type 0 (basic):     r4=task_id
 *   Type 1 (subfunc):   r4=task_id, r5=sub_func
 *   Type 2 (buffer):    r4=task_id, r5=buffer_ptr
 *   Type 4 (timer):     r4=timer_id
 *
 * @param dispatch  Dispatch record
 * @param arg       Task argument
 */
void rtos_dispatch(uint32_t dispatch, uint32_t arg)
{
    uint32_t handler_addr = rtos_dispatch_get_handler(dispatch);
    uint8_t type = rtos_dispatch_get_type(dispatch);

    /* Cast handler to function pointer */
    typedef void (*handler_fn)(uint32_t, uint32_t);
    handler_fn fn = (handler_fn)(uintptr_t)handler_addr;

    if (fn == 0) {
        return;  /* Invalid handler */
    }

    /* Call handler with type-specific argument */
    switch (type) {
        case RTOS_TYPE_BASIC:
            /* r4=task_id (dispatch word), no r5 */
            fn(handler_addr, 0);
            break;

        case RTOS_TYPE_SUBFUNC:
            /* r4=task_id, r5=sub_func */
            fn(handler_addr, arg);
            break;

        case RTOS_TYPE_BUFFER:
            /* r4=task_id, r5=buffer_ptr */
            fn(handler_addr, arg);
            break;

        case RTOS_TYPE_TIMER:
            /* r4=timer_id */
            fn(arg, 0);
            break;

        default:
            /* Unknown type, ignore */
            break;
    }
}

/* ====================================================================== */
/*  Scheduler                                                              */
/* ====================================================================== */

/**
 * rtos_scheduler — Cooperative scheduler main loop.
 *
 * ROM address: 0x3C50 (main scheduler loop)
 *
 * Flow:
 *   1. Check if queue has entries
 *   2. Dequeue next entry
 *   3. Extract priority from dispatch record
 *   4. If priority >= current_priority: dispatch
 *   5. If priority < current_priority: re-enqueue (lower priority waiting)
 *   6. After dispatch, check for timer callbacks
 *   7. Repeat until queue empty or yield requested
 *
 * Priority rules:
 *   S0 (engine): always dispatched, can't be interrupted
 *   S1 (I/O): dispatched if no S0 pending
 *   S2 (safety): dispatched if no S0/S1 pending
 *   S3 (idle): only when queue empty of higher priorities
 */
void rtos_scheduler(void)
{
    if (scheduler_running) {
        return;  /* Prevent re-entrant scheduling */
    }

    scheduler_running = 1;

    while (!rtos_queue_is_empty()) {
        uint32_t dispatch, arg;

        if (rtos_task_dequeue(&dispatch, &arg) != 0) {
            break;  /* Queue empty (race condition) */
        }

        uint8_t priority = rtos_dispatch_get_priority(dispatch);

        /* Priority-based dispatch decision */
        if (priority <= current_priority) {
            /* This task is equal or higher priority than current */
            uint8_t old_priority = current_priority;
            current_priority = priority;

            /* Context switch and dispatch */
            /* TODO: Actual context switch requires assembly:
             *   mov sp, r4
             *   bsrf @rtos_context_save  (or inline)
             *   ...
             *   mov r4, sp
             *   bsrf @rtos_dispatch
             *   ...
             *   mov r4, sp
             *   bsrf @rtos_context_restore
             *
             * For now, just dispatch directly. */
            rtos_dispatch(dispatch, arg);

            current_priority = old_priority;
        } else {
            /* Lower priority — re-enqueue for later */
            rtos_task_enqueue(dispatch, arg);

            /* If we've cycled through the whole queue without dispatching,
             * break to avoid infinite loop */
            static uint8_t skip_count = 0;
            skip_count++;
            if (skip_count >= RTOS_QUEUE_MAX_SLOTS) {
                skip_count = 0;
                break;
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
