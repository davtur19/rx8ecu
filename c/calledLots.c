/*
 * calledLots.c  —  RX-8 ECU byte counter with saturation guard
 *
 * Address: 0x00A486  |  Size: 54 bytes
 *
 * Reads a byte from RAM at a computed offset, increments it (with a
 * saturation check at 0xFF), and writes it back.  The offset is computed
 * as: (arg * 2) + some pointer.  Used as a frequent periodic increment
 * for counters or time accumulators.
 *
 * Algorithm:
 *   1. Call initialization at 0x3920 → 0x2054  (get pointer/context)
 *   2. Compute byte address = base_ptr + (arg * 2)
 *   3. Read byte; if < 0xFF, increment and write back
 *   4. Call finalization at 0x3920 → 0x2064
 *
 * The saturation prevents the counter from wrapping past 0xFF.
 *
 * Verified against ROM: c/tests/test_calledLots.py
 */
#include <stdint.h>

/* External helper: these indirect through 0x3920 */
extern uint32_t call_via_3920(uint32_t r4);
extern uint32_t call_via_3920_b(uint32_t r4);

/* 0x00A486 — increment a saturating byte counter at a computed address */
void calledLots(uint8_t index)
{
    /*
     * In the SH-2E this calls through a dispatch table at 0x3920.
     * The first call (at 0x2054) initializes/gets the base pointer.
     * The byte address is: base_ptr + (index * 2) as word from call.
     * The second call (at 0x2064) finalizes.
     *
     * Simplified C equivalent:
     */
    volatile uint8_t *counter_ptr; /* retrieved from subsystem */
    uint8_t val;

    /* Get base pointer via subsystem call (r15 stack frame ptr) */
    counter_ptr = (volatile uint8_t *)(uintptr_t)call_via_3920(0);

    /* Index into the counter array — each counter is word-spaced */
    counter_ptr += (uint32_t)index * 2;

    /* Read, increment-with-saturation, write back */
    val = *counter_ptr;
    if (val < 0xFFu) {
        *counter_ptr = val + 1;
    }

    /* Finalize */
    call_via_3920_b(0);
}
