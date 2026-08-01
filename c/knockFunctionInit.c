/*
 * knockFunctionInit.c  —  RX-8 ECU knock detection subsystem init
 *
 * Address: 0x00C31C  |  Size: 42 bytes
 *
 * Initialises the knock detection subsystem.  Called during the power-on
 * initialisation sequence after the ATU waveform generator and knock-
 * related I/O are configured.
 *
 * Algorithm:
 *   1. Call atu2_tior2c_waveform_init (0xC346) — sets up ATU2 compare
 *      output for knock window timing
 *   2. Call knockRelatedInit (0xC3C8) — knock filter/threshold init
 *   3. Write 0xAC08 to two 16-bit registers (knock threshold refs)
 *   4. Load a float constant from PC-relative data and store it
 *      to the knock threshold scaling factor address
 *   5. Clear byte flags at 0xFFFFA38C and 0xFFFFA325
 *
 * Verified against ROM: c/tests/test_knockFunctionInit.py
 */
#include <stdint.h>

/* External sub-calls */
extern void atu2_tior2c_waveform_init(void);
extern void knockRelatedInit(void);

/* 0x00C31C — initialise knock detection subsystem */
void knockFunctionInit(void)
{
    volatile uint16_t *knock_thresh_1 = (volatile uint16_t *)0xFFFFA37A;
    volatile uint16_t *knock_thresh_2 = (volatile uint16_t *)0xFFFFA378;
    volatile float    *knock_scale    = (volatile float    *)0xFFFFA374;
    volatile uint8_t  *knock_flag_a   = (volatile uint8_t  *)0xFFFFA38C;
    volatile uint8_t  *knock_flag_b   = (volatile uint8_t  *)0xFFFFA325;

    atu2_tior2c_waveform_init();
    knockRelatedInit();

    *knock_thresh_1 = 0xAC08;
    *knock_thresh_2 = 0xAC08;

    /* Float constant from PC-relative literal pool (value ~0.0f) */
    *knock_scale = 0.0f;

    *knock_flag_a = 0;
    *knock_flag_b = 0;
}
