/*
 * main.h — RX-8 ECU Main Loop and RTOS Task Dispatcher Definitions
 *
 * The main loop is a cooperative RTOS task dispatcher:
 *   main_task_dispatcher (0x6C8)
 *   -> task_scheduler_dispatch (0x364): process EEPROM/diag
 *   -> task_queue_pending_count (0x3E0): check queue
 *   -> task_queue_get_next (0x3B0): get next entry
 *   -> Dispatch based on task[1] & 0xF8:
 *      0xA8 -> diag_transfer_806
 *      0x88 -> serial_rx_handler_ch0
 *      0x90 -> serial_rx_handler_ch1
 *      0x98 -> serial_data_write_handler
 *      0xA0 -> exception_context_restore
 *      0xB0 -> serial_data_read_handler
 *      0xC0 -> serial_rx_handler_ch2
 *      0xC8 -> fatal_error_infinite_loop (if task[0]==0xFF)
 *
 * Scheduling: cooperative (non-preemptive)
 * Priority levels: 4 (0=lowest, 3=highest)
 * Queue: 100 entries, circular buffer at 0xFFFFD4E0
 *
 * Source: rtos_analysis_report.txt
 */

#ifndef MAIN_H
#define MAIN_H

#include <stdint.h>
#include "platform.h"

/* ====================================================================== */
/*  Task Queue Format                                                     */
/* ====================================================================== */

/* Task queue entry format (8 bytes):
 *   [0]: Source/origin byte (compared with 0xFE0)
 *   [1]: Command/type code (dispatched to handlers)
 *   [2-7]: Payload or parameters
 */
#define TASK_ENTRY_SRC_OFFSET   0
#define TASK_ENTRY_CMD_OFFSET   1
#define TASK_ENTRY_PAYLOAD_OFFSET 2

/* ====================================================================== */
/*  Dispatch Table (task[1] & 0xF8)                                       */
/* ====================================================================== */

#define DISPATCH_DIAG_TRANSFER     0xA8  /* diag_transfer_806 */
#define DISPATCH_SERIAL_RX_CH0     0x88  /* serial_rx_handler_ch0 */
#define DISPATCH_SERIAL_RX_CH1     0x90  /* serial_rx_handler_ch1 */
#define DISPATCH_SERIAL_DATA_WRITE 0x98  /* serial_data_write_handler */
#define DISPATCH_EXCEPTION_RESTORE 0xA0  /* exception_context_restore */
#define DISPATCH_SERIAL_DATA_READ  0xB0  /* serial_data_read_handler */
#define DISPATCH_SERIAL_RX_CH2     0xC0  /* serial_rx_handler_ch2 */
#define DISPATCH_FATAL_ERROR       0xC8  /* fatal_error (if src==0xFF) */

/* ====================================================================== */
/*  RTOS Scheduling                                                       */
/* ====================================================================== */

/* Priority levels */
#define PRIORITY_CRITICAL   3   /* Level 3: Critical engine control */
#define PRIORITY_HIGH       2   /* Level 2: Timing/sensor processing */
#define PRIORITY_NORMAL     1   /* Level 1: I/O and communication */
#define PRIORITY_LOW        0   /* Level 0: Background tasks */

/* Task states */
#define TASK_STATE_INACTIVE 0
#define TASK_STATE_READY    1
#define TASK_STATE_RUNNING  2
#define TASK_STATE_BLOCKED  3

/* ====================================================================== */
/*  Task Table (0x6873C)                                                  */
/* ====================================================================== */

/* Task table format: 8-byte packed records:
 *   {uint16_t marker, uint16_t arg_count, uint32_t func_ptr}
 * marker == 0xFFFF: call func_ptr directly (direct-call sentinel)
 * marker == other: call dispatcher 0x5F34 with marker as key
 */
struct task_table_entry {
    uint16_t marker;        /* 0xFFFF = direct call, else dispatcher key */
    uint16_t arg_count;     /* Number of arguments */
    uint32_t func_ptr;      /* Function pointer */
};

#define TASK_TABLE_BASE     0x6873C
#define TASK_TABLE_MAX_ENTRIES 30

/* ====================================================================== */
/*  Main Loop Function Prototypes                                         */
/* ====================================================================== */

/**
 * main_task_dispatcher — Main RTOS task dispatch loop.
 * ROM address: 0x6C8
 *
 * Clears dispatcher flag at 0xFFFFDFB8.
 * Constant register setup:
 *   r8 = 0x7C (exception_context_restore)
 *   r9 = 0x64 (serial_rx_handler_ch1)
 *   r10 = 0x4C (serial_rx_handler_ch0)
 *   r11 = 0x3E0 (task_queue_pending_count)
 *
 * LOOP:
 *   1. Call task_scheduler_dispatch (0x364)
 *   2. Call task_queue_pending_count (0x3E0)
 *   3. If pending == 0 -> idle path (0x78C)
 *   4. Call task_queue_get_next (0x3B0)
 *   5. Compare entry[0] with busy check (0xFFFFDFE0)
 *   6. Extract task[1] & 0xF8 -> dispatch table lookup
 *   7. Call watchdogTimerRead (0x31C)
 *   8. Goto LOOP
 */
void main_task_dispatcher(void);

/**
 * task_scheduler_dispatch — Queue scheduler, EEPROM/diag processing.
 * ROM address: 0x364
 *
 * If busy_flag [0xFFFFDFBA] == 0: diag_transfer_210 (0x210)
 * Else: eeprom_read_validate (0x450)
 * If result == 1: increments write_idx.
 */
void task_scheduler_dispatch(void);

/**
 * diag_transfer_210 — Diagnostic transfer pump (NOT YET IMPLEMENTED).
 * ROM address: 0x210
 *
 * review-fix w2 (DOCUMENTED-gap): contract per IDA_ANALYSIS.md — check
 * PFC 0xFFFFE40E/0xFFFFE41A bit 0x100, then call helper 0xACE(entry, 8,
 * 0, 0xFFFFE4B0). No definition is provided (the 0xACE callee has no C
 * counterpart), so task_scheduler_dispatch deliberately does not call it
 * yet. NEEDS-ROM-CHECK: IDA read of 0x210 + C implementation of 0xACE.
 */
void diag_transfer_210(void);

/**
 * task_queue_pending_count — Compute pending queue entries.
 * ROM address: 0x3E0
 * @return Number of pending entries: (write_idx - read_idx) mod 100
 */
int task_queue_pending_count(void);

/**
 * task_queue_get_next — Read next entry from ring buffer.
 * ROM address: 0x3B0
 * @return Read index of the entry just consumed
 *
 * Advances read_idx by 1 (mod 100).
 */
uint16_t task_queue_get_next(void);

/**
 * task_queue_init — Initialize the task queue.
 * ROM address: 0x3964
 *
 * Clears all 100 entries, sets write/read indices to 0.
 * Initializes each slot to -1 (0xFF).
 */
void task_queue_init(void);

/**
 * watchdogTimerRead — Read and service the watchdog timer.
 * ROM address: 0x31C
 */
void watchdogTimerRead(void);

/**
 * fatal_error_infinite_loop — Fatal error handler.
 * ROM address: 0xD8
 *
 * Infinite loop, waits for watchdog reset.
 */
void fatal_error_infinite_loop(void);

#endif /* MAIN_H */
