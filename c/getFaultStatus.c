/**
 * getFaultStatus @ 0x6743C (60E1D400)
 *
 * Purpose:
 *   Check the fault status for a given fault channel index.
 *   Returns 1 if a fault is active/pending, 0 otherwise.
 *   Used as a primary fault query interface (78+ callers).
 *
 * Logic:
 *   1. Load fault enable mask from RAM (0xFFFFD96C)
 *   2. Load fault table entry from ROM (0x0007E4DC + channel*4)
 *   3. If (entry & enable_mask) has any bit in the low 16 bits set:
 *        → immediate fault, return 1
 *   4. Otherwise, call getFaultEvalState(channel) for secondary evaluation
 *   5. If (entry & eval_result) has any bit in the upper 16 bits set:
 *        → confirmed fault, return 1
 *   6. Return 0 (no fault)
 *
 * Parameters:
 *   r4: uint16_t channel — fault channel index (0..N)
 *
 * Returns:
 *   r0: uint8_t — 0 = no fault, 1 = fault present
 *
 * RAM:
 *   0xFFFFD96C  uint32_t  Fault enable mask (runtime-configurable)
 *
 * ROM table:
 *   0x0007E4DC  uint32_t  Fault status table (per-channel entries)
 *
 * Calls:
 *   getFaultEvalState @ 0x67494 — extended fault evaluation
 */

#include <stdint.h>

#define FAULT_ENABLE_MASK  (*(volatile uint32_t *)0xFFFFD96C)
#define FAULT_TABLE(chan)  (*(const uint32_t *)(0x0007E4DC + ((chan) & 0xFFFF) * 4))

extern uint32_t getFaultEvalState(uint16_t channel);

uint8_t getFaultStatus(uint16_t channel)
{
    uint32_t entry;          /* fault table entry from ROM */
    uint32_t enable_mask;    /* runtime enable mask from RAM */
    uint32_t eval_result;    /* extended evaluation */
    uint8_t  result = 0;

    enable_mask = FAULT_ENABLE_MASK;
    entry       = FAULT_TABLE(channel);

    /* Immediate check: low 16 bits of masked entry */
    if ((entry & enable_mask) & 0xFFFF) {
        result = 1;
    } else {
        /* Secondary evaluation: check upper 16 bits */
        eval_result = getFaultEvalState(channel);
        if ((entry & eval_result) & 0xFFFF0000) {
            result = 1;
        }
    }

    return result;
}
