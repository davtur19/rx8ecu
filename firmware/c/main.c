/*
 * main.c — RX-8 ECU Main Loop and RTOS Task Dispatcher
 *
 * 1:1 firmware reconstruction of the cooperative RTOS task dispatcher.
 * This is the main execution loop of the RX-8 ECU firmware.
 *
 * Boot chain ends at main_task_dispatcher (0x6C8):
 *   1. Clear dispatcher flag
 *   2. Constant register setup (r8-r11)
 *   3. LOOP:
 *      a. task_scheduler_dispatch: process EEPROM/diag
 *      b. task_queue_pending_count: check queue
 *      c. If pending == 0 -> idle path
 *      d. task_queue_get_next: get next entry
 *      e. Dispatch based on task[1] & 0xF8
 *      f. watchdogTimerRead
 *      g. Goto LOOP
 *
 * Dispatch table:
 *   0xA8 -> diag_transfer_806
 *   0x88 -> serial_rx_handler_ch0
 *   0x90 -> serial_rx_handler_ch1
 *   0x98 -> serial_data_write_handler
 *   0xA0 -> exception_context_restore
 *   0xB0 -> serial_data_read_handler
 *   0xC0 -> serial_rx_handler_ch2
 *   0xC8 -> fatal_error_infinite_loop (if task[0]==0xFF)
 *
 * Source: rtos_analysis_report.txt
 */

#include "platform.h"
#include "main.h"
#include "serial.h"
#include "eeprom.h"

/* ====================================================================== */
/*  Task Queue Accessors                                                  */
/* ====================================================================== */

/* Read 8-bit value from task queue entry */
static inline uint8_t task_read8(uint16_t idx, uint8_t offset)
{
    uint16_t addr = TASK_QUEUE_BASE + (idx * TASK_QUEUE_ENTRY_SIZE) + offset;
    return *(volatile uint8_t *)(uintptr_t)addr;
}

/* Read 16-bit value from task queue entry */
static inline uint16_t task_read16(uint16_t idx, uint8_t offset)
{
    uint16_t addr = TASK_QUEUE_BASE + (idx * TASK_QUEUE_ENTRY_SIZE) + offset;
    return *(volatile uint16_t *)(uintptr_t)addr;
}

/* Write 16-bit value to task queue entry */
static inline void task_write16(uint16_t idx, uint8_t offset, uint16_t value)
{
    uint16_t addr = TASK_QUEUE_BASE + (idx * TASK_QUEUE_ENTRY_SIZE) + offset;
    *(volatile uint16_t *)(uintptr_t)addr = value;
}

/* ====================================================================== */
/*  Task Queue Operations                                                 */
/* ====================================================================== */

/**
 * task_queue_pending_count — Compute number of pending queue entries.
 *
 * ROM address: 0x3E0
 * Size: 8 bytes
 *
 * Formula: pending = (write_idx - read_idx) mod 100
 * Uses unsigned subtraction and modulo to handle wrap-around.
 *
 * @return Number of pending entries (0-100)
 */
int task_queue_pending_count(void)
{
    uint16_t w = TASK_QUEUE_WRITE_IDX;
    uint16_t r = TASK_QUEUE_READ_IDX;

    /* Unsigned subtraction, mod 100 */
    int diff = (int)w - (int)r;
    if (diff < 0) diff += TASK_QUEUE_SIZE;

    return diff;
}

/**
 * task_queue_get_next — Read next entry from ring buffer.
 *
 * ROM address: 0x3B0
 * Size: 20 bytes
 *
 * Reads entry at: base + (read_idx * 8)
 * Increments read_idx mod 100.
 *
 * @return Read index of the entry just consumed (for state tracking)
 */
uint16_t task_queue_get_next(void)
{
    uint16_t idx = TASK_QUEUE_READ_IDX;

    /* Advance read index */
    TASK_QUEUE_READ_IDX = (idx + 1) % TASK_QUEUE_SIZE;

    return idx;
}

/**
 * task_queue_init — Initialize the task queue.
 *
 * ROM address: 0x3964
 *
 * Clears all 100 entries, sets write/read indices to 0.
 * Initializes each slot marker to 0xFF (-1).
 */
void task_queue_init(void)
{
    /* Clear all queue entries */
    for (uint16_t i = 0; i < TASK_QUEUE_SIZE; i++) {
        for (uint8_t j = 0; j < TASK_QUEUE_ENTRY_SIZE; j++) {
            uint16_t addr = TASK_QUEUE_BASE + (i * TASK_QUEUE_ENTRY_SIZE) + j;
            *(volatile uint8_t *)(uintptr_t)addr = 0xFF;
        }
    }

    /* Reset indices */
    TASK_QUEUE_WRITE_IDX = 0;
    TASK_QUEUE_READ_IDX  = 0;
}

/* ====================================================================== */
/*  Queue Scheduler                                                       */
/* ====================================================================== */

/**
 * task_scheduler_dispatch — Queue scheduler, EEPROM/diag processing.
 *
 * ROM address: 0x364
 * Size: ~44 bytes
 *
 * If busy_flag [0xFFFFDFBA] == 0: call diag_transfer_210 (0x210)
 * Else: call eeprom_read_validate
 * If result == 1: increment write_idx.
 */
void task_scheduler_dispatch(void)
{
    volatile uint8_t *busy_flag = (volatile uint8_t *)0xFFFFDFBA;

    if (*busy_flag == 0) {
        /* Not busy: process diagnostic transfer.
         * review-fix w2 (DOCUMENTED-gap, call intentionally absent):
         * ROM diag_transfer_210 (0x210) contract per IDA_ANALYSIS.md —
         * check PFC 0xFFFFE40E/0xFFFFE41A bit 0x100, then call helper
         * 0xACE(entry, 8, 0, 0xFFFFE4B0) to move bytes into the serial RX
         * path. That 0xACE callee has NO C counterpart yet (serial.c
         * implements neither it nor serial_dispatch/tx_direct/queue_message),
         * so emitting a call would break the link. Needed: IDA read of
         * ROM 0x210 (exact PFC mask/branch + 0xACE signature) and a C
         * implementation of 0xACE; then declare diag_transfer_210 in
         * main.h and call it here. */
    } else {
        /* Busy: try to validate EEPROM data */
        uint8_t temp_buf[8];
        int result = eeprom_read_validate(temp_buf);

        if (result == 1) {
            /* Valid data: increment write index */
            TASK_QUEUE_WRITE_IDX = (TASK_QUEUE_WRITE_IDX + 1) % TASK_QUEUE_SIZE;
        }
    }
}

/* ====================================================================== */
/*  Watchdog Timer Read                                                   */
/* ====================================================================== */

/**
 * cpu_idle_sleep — Enter low-power wait until the next interrupt.
 *
 * Executes the SH-2 `sleep` instruction: the CPU halts until an
 * interrupt (task enqueue, timer tick, serial RX) wakes it. On the host
 * syntax-check build the asm string is opaque and never assembled.
 */
static inline void cpu_idle_sleep(void)
{
    __asm__ __volatile__("sleep");
}

/**
 * watchdogTimerRead — Read and service the watchdog timer.
 *
 * ROM address: 0x31C
 *
 * Reads the WDT status and feeds the watchdog if needed.
 */
void watchdogTimerRead(void)
{
    /* Read watchdog timer status */
    (void)WDT_TCSR;

    /* Feed watchdog to prevent reset */
    WDT_TCSR = 0xA53C;
}

/* ====================================================================== */
/*  Task Dispatch Table                                                   */
/* ====================================================================== */

/**
 * main_task_dispatcher — Main RTOS task dispatch loop.
 *
 * ROM address: 0x6C8
 *
 * The main loop of the RX-8 ECU firmware. Continuously processes
 * pending tasks from the queue and dispatches them to handlers.
 *
 * Register constants (from ROM analysis):
 *   r8  = 0x7C (exception_context_restore)
 *   r9  = 0x64 (serial_rx_handler_ch1)
 *   r10 = 0x4C (serial_rx_handler_ch0)
 *   r11 = 0x3E0 (task_queue_pending_count)
 */
void main_task_dispatcher(void)
{
    /* Step 1: Clear dispatcher flag */
    volatile uint8_t *flag = (volatile uint8_t *)0xFFFFDFB8;
    *flag = 0;

    /* Main loop */
    while (1) {
        /* Step 2: Process queue scheduler */
        task_scheduler_dispatch();

        /* Step 3: Check for pending tasks */
        int pending = task_queue_pending_count();

        if (pending == 0) {
            /* Idle path: no tasks pending — sleep until the next
             * interrupt instead of spinning.
             * review-fix w2: the old code fed the watchdog on EVERY
             * idle spin, so a stuck scheduler (never dispatching) would
             * still look alive to the WDT. Feed only after forward
             * progress (Step 7 below); in idle, sleep and feed at most
             * once per 256 spins as a last-resort keepalive.
             * NEEDS-ROM-CHECK: ROM idle path 0x78C must confirm the
             * real sleep/wake + feed policy. */
            static uint8_t idle_spins = 0;
            cpu_idle_sleep();
            if (++idle_spins == 0) {
                watchdogTimerRead();
            }
            continue;
        }

        /* Step 4: Get next task from queue */
        uint16_t task_idx = task_queue_get_next();

        /* Step 5: Read command byte (task[1] & 0xF8) */
        uint8_t cmd = task_read8(task_idx, TASK_ENTRY_CMD_OFFSET);
        uint8_t dispatch_code = cmd & 0xF8;
        uint8_t src = task_read8(task_idx, TASK_ENTRY_SRC_OFFSET);

        /* Step 6: Dispatch based on command */
        switch (dispatch_code) {
            case DISPATCH_DIAG_TRANSFER:
                /* diag_transfer_806 */
                break;

            case DISPATCH_SERIAL_RX_CH0:
                serial_rx_handler_ch0();
                break;

            case DISPATCH_SERIAL_RX_CH1:
                serial_rx_handler_ch1();
                break;

            case DISPATCH_SERIAL_DATA_WRITE:
                serial_data_write_handler();
                break;

            case DISPATCH_EXCEPTION_RESTORE:
                /* exception_context_restore: restore saved context */
                break;

            case DISPATCH_SERIAL_DATA_READ:
                /* serial_data_read_handler */
                break;

            case DISPATCH_SERIAL_RX_CH2:
                serial_rx_handler_ch2();
                break;

            case DISPATCH_FATAL_ERROR:
                /* Fatal error: if src == 0xFF, halt */
                if (src == 0xFF) {
                    fatal_error_infinite_loop();
                }
                break;

            default:
                /* Unknown command: ignore */
                break;
        }

        /* Step 7: Service watchdog (forward progress: a task dispatched) */
        watchdogTimerRead();
    }
}

/* ====================================================================== */
/*  Fatal Error Handler                                                   */
/* ====================================================================== */

/**
 * fatal_error_infinite_loop — Fatal error handler.
 *
 * ROM address: 0xD8
 *
 * Enters an infinite loop, waiting for the watchdog to reset the ECU.
 * Used for unrecoverable errors.
 */
void fatal_error_infinite_loop(void)
{
    while (1) {
        /* Infinite loop — watchdog will eventually reset */
        __asm__ __volatile__("nop");
    }
}
