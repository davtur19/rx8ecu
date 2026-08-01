/* calibration_apply_4B770.c
 *
 * ROM: 60E1D400  |  Address: 0x4B770  |  Size: 46 bytes (to 0x4B7CC)
 *                 (0x4B782..0x4B7AA is a literal pool, not code)
 *
 * Calibration-apply leaf (side-effect only): reads three input bytes and
 * writes one flag byte:
 *
 *   b201  = byte@0xFFFFD201   (mov.w literal 0xD201, sign-extended)
 *   bCE00 = byte@0xFFFFCE00   (mov.w literal 0xCE00)
 *   bCE01 = byte@0xFFFFCE01   (mov.w literal 0xCE01)
 *   v = (b201 != 1 && bCE00 == 0 && bCE01 == 0) ? 1 : 0
 *   byte@0xFFFFCDFD = v       (mov.w literal 0xCDFD)
 *
 * Flow: if b201 == 1 → store 0; else if bCE00==0 and bCE01==0 → store 1;
 * else store 0 (r5 = 0 was set in the delay slot of the first bf/s).
 * Return r0 not meaningful — lift returns void.
 *
 * Verified against ROM emulator: c/tests/test_calibration_apply_4B770.py
 * Host C companion:             c/tests/test_calibration_apply_4B770.c
 */
#include <stdint.h>

/* 0x4B770 — apply calibration when inputs are in the idle state */
void calibration_apply_4B770(void)
{
    uint8_t b201 = *(volatile uint8_t *)0xFFFFD201;
    uint8_t bCE00 = *(volatile uint8_t *)0xFFFFCE00;
    uint8_t bCE01 = *(volatile uint8_t *)0xFFFFCE01;
    uint8_t v = (b201 != 1 && bCE00 == 0 && bCE01 == 0) ? 1 : 0;
    *(volatile uint8_t *)0xFFFFCDFD = v;
}
