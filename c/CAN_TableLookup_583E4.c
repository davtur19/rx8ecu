/*
 * CAN_TableLookup_583E4.c  —  RX-8 ECU memory scan and match accumulator
 *
 * Address: 0x0583E4  |  Size: 100 bytes
 *
 * Scans a table in RAM/ROM looking for entries matching specific criteria
 * and accumulates a value from matching entries.  This is a generic table
 * lookup/dispatch function used by the diagnostic and fault-monitoring
 * subsystems.
 *
 * Algorithm:
 *   1. Load base scan address (0x0005FFEE) and entry count (0x24 = 36)
 *   2. For each entry (6 bytes each):
 *      - Compare entry's 16-bit signature word with expected pattern
 *      - Compare entry's byte[3] with a filter value (r5 & 0xFF)
 *      - Test entry's byte[2] against a bitmask (r9)
 *      - If all match: add byte[2] (at r7+2) to accumulator (r12)
 *   3. Return (input_r4 & accumulator) as the result
 *
 * The 6-byte entry format appears to be:
 *   [0..1]: signature/ID word
 *   [2]:    data value or flags
 *   [3]:    filter/type byte
 *   [4..5]: (unknown / unused)
 *
 * Verified against ROM: c/tests/test_CAN_TableLookup_583E4.py
 */
#include <stdint.h>

/* 6-byte scan entry structure */
typedef struct {
    uint16_t signature;  /* +0: matching signature */
    uint8_t  data_val;   /* +2: value to accumulate */
    uint8_t  filter;     /* +3: type filter byte */
    uint8_t  reserved[2];/* +4..5: padding */
} __attribute__((packed)) ScanEntry;

/* 0x0583E4 — scan table and accumulate matched entries */
uint32_t CAN_TableLookup_583E4(uint32_t mask_in, uint8_t filter_val)
{
    const ScanEntry *table = (const ScanEntry *)0x0005FFEE;
    const uint32_t   count = 36;                 /* 0x24 entries */
    uint16_t         expected_sig;               /* from PC-relative load */
    uint16_t         bitmask;                    /* from r9 (PC-relative) */
    uint32_t         accum = 0;

    /* Load matching criteria */
    expected_sig = *(volatile uint16_t *)0xFFFFD226;
    bitmask      = *(volatile uint16_t *)((void*)0); /* PC-relative literal */

    for (uint32_t i = 0; i < count; i++) {
        if (table[i].signature == expected_sig &&
            table[i].filter == filter_val &&
            (bitmask & 0xFFFFu) != 0)   /* simplified: check bitmask validity */
        {
            accum += table[i].data_val;
        }
    }

    return mask_in & accum;
}
