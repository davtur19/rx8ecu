/*
 * rtos.h — RX-8 ECU RTOS (Real-Time Operating System) Subsystem Definitions
 *
 * 1:1 firmware reconstruction of the cooperative RTOS for the
 * Mazda RX-8 Renesis 13B-MSP rotary engine ECU (SH-2E / SH7055).
 *
 * Architecture:
 *   Cooperative 4-priority scheduler (S0=engine, S1=I/O, S2=safety, S3=idle)
 *   Fixed-size circular task queue: 100 entries × 8 bytes at 0xFFFFD4E0
 *   Context switch saves/restores SH-2 registers
 *   Dispatch table: 8-byte records (handler_addr | type << 24 | priority << 28)
 *
 * Queue management:
 *   Write index: 0xFFFFDFB4 (uint16)
 *   Read index:  0xFFFFDFB6 (uint16)
 *   Queue base:  0xFFFFD4E0
 *   Entry stride: 8 bytes
 *
 * Source: rtos_analysis_report.txt, IDA session ae00d360
 */

#ifndef RTOS_H
#define RTOS_H

#include <stdint.h>
#include "platform.h"

/* ====================================================================== */
/*  Task Queue Layout                                                      */
/* ====================================================================== */

/* Fixed-size circular queue: 100 entries × 8 bytes at 0xFFFFD4E0 */
#define RTOS_QUEUE_BASE         0xFFFFD4E0
#define RTOS_QUEUE_ENTRY_SIZE   8       /* 8 bytes per record */
#define RTOS_QUEUE_MAX_SLOTS    100

/* Queue indexes */
#define RTOS_QUEUE_WRITE_ADDR   0xFFFFDFB4  /* uint16: next write slot */
#define RTOS_QUEUE_READ_ADDR    0xFFFFDFB6  /* uint16: next read slot */

/* ====================================================================== */
/*  Dispatch Table Layout                                                  */
/* ====================================================================== */

/* Dispatch table: 8-byte records at 0x6873C (ROM) */
#define RTOS_DISPATCH_TABLE_BASE 0x6873C
#define RTOS_DISPATCH_ENTRY_SIZE 8

/* Record layout (8 bytes):
 *   +0x00: uint32 Handler address (ROM, 2-byte aligned)
 *   +0x04: uint8  Type (0-4) << 24 bits in word
 *   +0x05: uint8  Priority (0-3) << 28 bits in word
 *   +0x06: uint16 Padding
 *
 * Type encoding (bits 24-26 of dword at +0):
 *   0: Basic handler (r4=task_id, no extra args)
 *   1: With sub-function (r4=task_id, r5=sub_func)
 *   2: With buffer pointer (r4=task_id, r5=buffer_ptr)
 *   3: Reserved
 *   4: Timer callback (r4=timer_id)
 */
#define RTOS_DISP_HANDLER_OFFSET 0x00    /* uint32: handler address */
#define RTOS_DISP_TYPE_OFFSET    0x04    /* uint8: type (bits 24-26) */
#define RTOS_DISP_PRIO_OFFSET    0x05    /* uint8: priority (bits 28-29) */

/* ====================================================================== */
/*  Priority Levels                                                        */
/* ====================================================================== */

#define RTOS_PRIORITY_S0         0       /* Engine control (highest) */
#define RTOS_PRIORITY_S1         1       /* I/O processing */
#define RTOS_PRIORITY_S2         2       /* Safety monitoring */
#define RTOS_PRIORITY_S3         3       /* Idle / background (lowest) */

/* ====================================================================== */
/*  Task Type Encodings                                                    */
/* ====================================================================== */

#define RTOS_TYPE_BASIC          0       /* Basic handler */
#define RTOS_TYPE_SUBFUNC        1       /* With sub-function argument */
#define RTOS_TYPE_BUFFER         2       /* With buffer pointer */
#define RTOS_TYPE_RESERVED       3       /* Reserved */
#define RTOS_TYPE_TIMER          4       /* Timer callback */

/* ====================================================================== */
/*  Dispatch Record Bit Layout                                             */
/* ====================================================================== */

/*
 * The dispatch record is a uint32 + padding:
 *   word = handler_addr | (type << 24) | (priority << 28)
 *
 * To extract:
 *   handler = word & 0x00FFFFFF
 *   type    = (word >> 24) & 0x07
 *   priority = (word >> 28) & 0x03
 *
 * review-fix N2: HANDLER_MASK was 0x0FFFFFFF, which includes the type bits
 * 24-26 and priority bit 28 — the first typed enqueue (type>=1 or
 * priority>=1... any nonzero type/prio bits) would call a type-polluted
 * address. Handler ROM addresses fit in 24 bits (512 KB flash @ 0x000000),
 * so mask to 0x00FFFFFF. Verified: the only mask users are the inline
 * accessors below (rtos_dispatch_get_handler / rtos_build_dispatch,
 * consumed by rtos_dispatch + rtos_scheduler in firmware/c/rtos.c), and
 * the RTOS queue has no external producers today (only the scheduler's
 * own lower-priority re-enqueue) — nothing depends on bits 24-28
 * surviving in the handler address.
 */
#define RTOS_DISP_HANDLER_MASK   0x00FFFFFF
#define RTOS_DISP_TYPE_SHIFT     24
#define RTOS_DISP_TYPE_MASK      0x07
#define RTOS_DISP_PRIO_SHIFT     28
#define RTOS_DISP_PRIO_MASK      0x03

/* ====================================================================== */
/*  Context Switch Layout                                                  */
/* ====================================================================== */

/*
 * Context switch saves/restores SH-2 registers:
 *   Core: r5, r8-r14, PR, GBR, MACH, MACL, SR
 *   SP (stack pointer)
 *   Floating-point: fr12-fr15 (if type 4 tasks)
 *
 * Stack frame layout (SH-2):
 *   [SP+0x00]: SR
 *   [SP+0x04]: PR
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
 */
#define RTOS_CTX_FRAME_SIZE     0x34    /* 52 bytes (basic) */
#define RTOS_CTX_FRAME_SIZE_FP  0x44    /* 68 bytes (with fr12-15) */

/* Stack frame offsets */
#define RTOS_CTX_SR_OFFSET      0x00
#define RTOS_CTX_PR_OFFSET      0x04
#define RTOS_CTX_R8_OFFSET      0x08
#define RTOS_CTX_R9_OFFSET      0x0C
#define RTOS_CTX_R10_OFFSET     0x10
#define RTOS_CTX_R11_OFFSET     0x14
#define RTOS_CTX_R12_OFFSET     0x18
#define RTOS_CTX_R13_OFFSET     0x1C
#define RTOS_CTX_R14_OFFSET     0x20
#define RTOS_CTX_R5_OFFSET      0x24
#define RTOS_CTX_GBR_OFFSET     0x28
#define RTOS_CTX_MACH_OFFSET    0x2C
#define RTOS_CTX_MACL_OFFSET    0x30
#define RTOS_CTX_FR12_OFFSET    0x34
#define RTOS_CTX_FR13_OFFSET    0x38
#define RTOS_CTX_FR14_OFFSET    0x3C
#define RTOS_CTX_FR15_OFFSET    0x40

/* ====================================================================== */
/*  Task Queue Entry Layout                                                */
/* ====================================================================== */

/*
 * Queue entry (8 bytes):
 *   +0x00: uint32 Dispatch record (handler | type<<24 | priority<<28)
 *   +0x04: uint32 Argument (task_id, sub_func, buffer_ptr, or timer_id)
 */
#define RTOS_ENTRY_DISPATCH_OFFSET  0x00    /* uint32: dispatch word */
#define RTOS_ENTRY_ARG_OFFSET       0x04    /* uint32: argument */

/* ====================================================================== */
/*  Function Prototypes                                                    */
/* ====================================================================== */

/**
 * rtos_init — Initialize RTOS subsystem.
 *
 * Clears queue indexes, initializes dispatch table context.
 * Called from secondary_boot_main chain.
 */
void rtos_init(void);

/**
 * rtos_scheduler — Cooperative scheduler main loop.
 *
 * Reads queue entries, dispatches to handlers based on type/priority.
 * Processes entries until queue is empty or yields to engine cycle.
 */
void rtos_scheduler(void);

/**
 * rtos_task_enqueue — Enqueue a task to the queue.
 *
 * @param dispatch  Dispatch record (handler | type<<24 | priority<<28)
 * @param arg       Task argument
 * @return 0 on success, -1 if queue full
 */
int rtos_task_enqueue(uint32_t dispatch, uint32_t arg);

/**
 * rtos_task_dequeue — Dequeue a task from the queue.
 *
 * @param dispatch  Output: dispatch record
 * @param arg       Output: task argument
 * @return 0 on success, -1 if queue empty
 */
int rtos_task_dequeue(uint32_t *dispatch, uint32_t *arg);

/**
 * rtos_context_save — Save task context (SH-2 registers).
 * ROM address: 0x3AD8
 *
 * Saves: r5, r8-r14, PR, GBR, MACH, MACL, SR
 * If type 4 task: also saves fr12-fr15
 *
 * @param sp        Current stack pointer (input/output)
 * @param task_type Task type (0-4, determines if FP regs saved)
 */
void rtos_context_save(uint32_t *sp, uint8_t task_type);

/**
 * rtos_context_restore — Restore task context (SH-2 registers).
 * ROM address: 0x3238
 *
 * Restores: r5, r8-r14, PR, GBR, MACH, MACL, SR
 * If type 4 task: also restores fr12-fr15
 *
 * @param sp        Stack pointer with saved context
 * @param task_type Task type (0-4, determines if FP regs restored)
 */
void rtos_context_restore(uint32_t *sp, uint8_t task_type);

/**
 * rtos_dispatch — Dispatch a task to its handler.
 * ROM address: 0x3BF4
 *
 * Reads dispatch record, extracts handler/type/priority,
 * sets up arguments, and calls handler function.
 *
 * @param dispatch  Dispatch record
 * @param arg       Task argument
 */
void rtos_dispatch(uint32_t dispatch, uint32_t arg);

/**
 * rtos_queue_is_empty — Check if queue is empty.
 * @return 1 if empty, 0 otherwise
 */
int rtos_queue_is_empty(void);

/**
 * rtos_queue_is_full — Check if queue is full.
 * @return 1 if full, 0 otherwise
 */
int rtos_queue_is_full(void);

/**
 * rtos_queue_count — Get number of pending tasks.
 * @return Number of tasks in queue
 */
int rtos_queue_count(void);

/**
 * rtos_yield — Yield to lower-priority tasks.
 *
 * Called from long-running handlers to allow other tasks to execute.
 */
void rtos_yield(void);

/**
 * rtos_get_current_priority — Get current task priority.
 * @return Current priority level (0-3)
 */
uint8_t rtos_get_current_priority(void);

/* ====================================================================== */
/*  Inline Queue Accessors                                                 */
/* ====================================================================== */

static inline uint16_t rtos_get_write_index(void)
{
    return *(volatile uint16_t *)RTOS_QUEUE_WRITE_ADDR;
}

static inline uint16_t rtos_get_read_index(void)
{
    return *(volatile uint16_t *)RTOS_QUEUE_READ_ADDR;
}

static inline void rtos_set_write_index(uint16_t idx)
{
    *(volatile uint16_t *)RTOS_QUEUE_WRITE_ADDR = idx;
}

static inline void rtos_set_read_index(uint16_t idx)
{
    *(volatile uint16_t *)RTOS_QUEUE_READ_ADDR = idx;
}

/* Get dispatch record from queue slot */
static inline uint32_t rtos_queue_get_dispatch(uint8_t slot)
{
    uint32_t addr = RTOS_QUEUE_BASE + (slot * RTOS_QUEUE_ENTRY_SIZE)
                    + RTOS_ENTRY_DISPATCH_OFFSET;
    return *(volatile uint32_t *)(uintptr_t)addr;
}

/* Get argument from queue slot */
static inline uint32_t rtos_queue_get_arg(uint8_t slot)
{
    uint32_t addr = RTOS_QUEUE_BASE + (slot * RTOS_QUEUE_ENTRY_SIZE)
                    + RTOS_ENTRY_ARG_OFFSET;
    return *(volatile uint32_t *)(uintptr_t)addr;
}

/* Extract handler address from dispatch word */
static inline uint32_t rtos_dispatch_get_handler(uint32_t dispatch)
{
    return dispatch & RTOS_DISP_HANDLER_MASK;
}

/* Extract type from dispatch word */
static inline uint8_t rtos_dispatch_get_type(uint32_t dispatch)
{
    return (dispatch >> RTOS_DISP_TYPE_SHIFT) & RTOS_DISP_TYPE_MASK;
}

/* Extract priority from dispatch word */
static inline uint8_t rtos_dispatch_get_priority(uint32_t dispatch)
{
    return (dispatch >> RTOS_DISP_PRIO_SHIFT) & RTOS_DISP_PRIO_MASK;
}

/* Build dispatch word from components */
static inline uint32_t rtos_build_dispatch(uint32_t handler, uint8_t type,
                                           uint8_t priority)
{
    return (handler & RTOS_DISP_HANDLER_MASK)
           | ((uint32_t)(type & RTOS_DISP_TYPE_MASK) << RTOS_DISP_TYPE_SHIFT)
           | ((uint32_t)(priority & RTOS_DISP_PRIO_MASK) << RTOS_DISP_PRIO_SHIFT);
}

#endif /* RTOS_H */
