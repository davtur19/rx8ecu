/*
 * canSetup.c  —  RX-8 ECU CAN controller initialisation
 *
 * Address: 0x00DC8C  |  Size: 160 bytes
 *
 * Initialises the CAN controller with retry logic.  Reads a configuration
 * bit to select between two CAN instance addresses, then attempts to
 * initialise the controller up to 2 times.  Sets an error flag in the
 * status register if initialisation fails.
 *
 * Algorithm:
 *   1. Save registers, allocate stack frame
 *   2. Clear retry counter (r3=0), set max_retries=2 (r8=2)
 *   3. Check a hardware status bit at (0xB5A4)
 *   4. If bit-1-set:  use CAN address A (0x4EA60)
 *      If bit-1-clear: use CAN address B (0x4EB60)
 *   5. For each attempt:
 *      - Call CAN init with appropriate address
 *      - Check return code; OR into accumulated status
 *      - If failed: increment retry counter
 *   6. After loop: if retries exhausted (>=2), set persistent error flag
 *   7. Clear another error flag and return
 *
 * Verified against ROM: c/tests/test_canSetup.py
 */
#include <stdint.h>

/* External CAN HAL functions */
extern uint32_t can_init_channel(uint32_t base_addr, uint32_t chan, uint32_t mode);
extern uint32_t can_chk_status(uint32_t base_addr, uint32_t chan);

/* 0x00DC8C — initialise CAN controller with retry */
void canSetup(void)
{
    volatile uint8_t  *config_bit   = (volatile uint8_t  *)0x0000B5A4;
    volatile uint8_t  *retry_count  = (volatile uint8_t  *)0xFFFFA40E;
    volatile uint8_t  *err_flag_a   = (volatile uint8_t  *)0xFFFFA410;
    volatile uint8_t  *err_flag_b   = (volatile uint8_t  *)0xFFFFA411;
    uint32_t can_base;
    uint32_t status = 0;
    uint8_t  retries = 0;
    uint8_t  max_retries = 2;

    /* Select CAN instance based on hardware config bit */
    if ((*config_bit & 0x01) == 0x01) {
        can_base = 0x0004EA60;   /* CAN instance A */
    } else {
        can_base = 0x0004EB60;   /* CAN instance B */
    }

    /* Reset retry counter */
    *retry_count = 0;

    /* Loop with retry */
    while (retries < max_retries) {
        uint32_t chan_status;

        /* Initialize CAN channel 0 with mode 0x10 */
        chan_status = can_init_channel(can_base, 0, 0x10);

        /* Check channel status */
        status |= can_chk_status(can_base, 0);

        /* Collect result */
        status |= chan_status;
        status &= 0xFF;   /* extu.b */

        if (status != 0) {
            /* Failure: increment retry counter */
            (*retry_count)++;
            retries = *retry_count;
        } else {
            break;  /* success */
        }
    }

    /* Check if all retries exhausted */
    if (retries >= max_retries) {
        *err_flag_a = 1;   /* set persistent CAN error */
    }

    /* Clear secondary error flag */
    *err_flag_b = 0;
}
