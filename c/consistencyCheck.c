/* ====================================================================
 * consistencyCheck — Exception/interrupt consistency validation
 *
 * Address:  0x3A28 (ROM 60E1D400)
 * Size:     124 bytes
 * Source:   ghidra-hand-xmap
 * Callers:  taskEndRoutine (0x3D58), FUN_00003490 (0x3490)
 *
 * This function validates exception/interrupt handling consistency.
 * It is called when an exception occurs to verify the exception state
 * and manage the exception handling lifecycle.
 *
 * Calling convention (SH-2E):
 *   R4 = pointer to exception control block
 *   R5 = exception number (byte, sign-extended)
 * Returns: 0 = not handled, 1 = handled
 *
 * Control block structure (at R4):
 *   [0]   = current exception number (uint8_t)
 *   [6-7] = error code result (uint16_t)
 *   [0x20] = pointer to exception table
 *
 * Exception table (8-byte entries):
 *   [0-1]   = initial counter/restore value (uint16_t)
 *   [2-3]   = expected buffer counter (uint16_t)
 *   [4-7]   = pointer to buffer (uint32_t)
 *
 * Buffer (4 bytes at pointer from entry[4]):
 *   [0-1] = current counter 0 (uint16_t)
 *   [2-3] = current counter 1 (uint16_t)
 *
 * Notes:
 * - Uses PC-relative data at 0x3D50 (bit-clear masks) and
 *   addresses 0xFFFF72E0 (exception pending flags) and
 *   0xFFFF7234 (error code lookup table).
 * - Calls handleHUDIException (0x3C80) when the exception
 *   is confirmed as the active exception on first occurrence.
 * ==================================================================== */

#include <stdint.h>

/* Bit-clear mask table at ROM 0x3D50: each mask clears one bit position */
static const uint8_t bit_clear_masks[8] = {
    0xFE, 0xFD, 0xFB, 0xF7, 0xEF, 0xDF, 0xBF, 0x7F
};

/* Hardwired peripheral addresses */
#define EXCEPTION_PENDING_FLAGS ((volatile uint8_t *)0xFFFF72E0)
#define ERROR_CODE_TABLE         ((volatile uint16_t *)0xFFFF7234)

/* Forward declaration of exception handler call */
extern void handleHUDIException(void);

int32_t consistencyCheck(uint8_t *ctrl_block, int8_t exc_num_s8)
{
    uint32_t exc_num;             /* Zero-extended exception number */
    uint8_t  *table_ptr;          /* Exception table pointer from ctrl_block[0x20] */
    uint16_t *entry;              /* 8-byte entry in the table */
    uint16_t *buffer;             /* 4-byte counter buffer */
    uint16_t  counter0, counter1; /* The two consistency counters */
    uint8_t  *flag_ptr;           /* Pointer to the pending flag byte */
    uint8_t   clear_mask;         /* Bit-clear mask for this exception's bit */
    uint8_t   r3;                 /* Current exception from ctrl_block[0] */

    exc_num = (uint32_t)(int32_t)exc_num_s8;  /* sign-extend then zero-extend for addressing */

    /* Load exception table pointer from control block offset 0x20 */
    table_ptr = *(uint8_t **)(ctrl_block + 0x20);

    /* Index into table: each entry is 8 bytes */
    entry = (uint16_t *)(table_ptr + exc_num * 8);

    /* Load the buffer pointer from entry[2] (byte offset 4) */
    buffer = *(uint16_t **)(entry + 2);

    /* Read both 16-bit counters from the buffer */
    counter0 = buffer[0];
    counter1 = buffer[1];

    if (counter0 == counter1) {
        /* ---------------------------------------------------------------
         * Path A: counters match — first occurrence of this exception
         * --------------------------------------------------------------- */

        /* Mark as handled by writing 0xFFFF to counter0 */
        buffer[0] = 0xFFFF;

        /* Clear the pending bit for this exception in the flags byte.
         * The flags byte is at 0xFFFF72E0 + (exc_num >> 3).
         * The bit position within the byte is (exc_num & 7). */
        flag_ptr  = (uint8_t *)(EXCEPTION_PENDING_FLAGS + (exc_num >> 3));
        clear_mask = bit_clear_masks[exc_num & 7];
        *flag_ptr &= clear_mask;

        /* Check whether this exception matches the currently active one */
        r3 = ctrl_block[0];
        if ((uint8_t)exc_num != r3) {
            return 0;   /* Not the active exception — don't call handler */
        }

        /* This IS the active exception: call the HUDI exception handler */
        handleHUDIException();

        /* Fall through to return 1 below */
    } else {
        /* ---------------------------------------------------------------
         * Path B: counters mismatch — exception was already seen
         * --------------------------------------------------------------- */

        if (counter0 == entry[1]) {
            /* Counter equals the expected value from the entry — restore */
            buffer[0] = entry[0];
        } else {
            /* Unexpected value — just increment the counter */
            buffer[0] = counter0 + 1;
        }

        /* Check whether this exception matches the currently active one */
        r3 = ctrl_block[0];
        if ((uint8_t)exc_num != r3) {
            return 0;   /* Not the active exception */
        }

        /* Look up error code from the table at 0xFFFF7234,
         * indexed by the current counter value (word index). */
        *(uint16_t *)(ctrl_block + 6) = ERROR_CODE_TABLE[buffer[0]];
    }

    return 1;   /* Exception was handled */
}
