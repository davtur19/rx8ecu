/* temperature_gauge_0x5AA5C.c
 *
 * ROM: 60E1D400  |  Address: 0x5AA5C  |  Size: 130 bytes (to 0x5AADE)
 *
 * Gauge-value setter leaf (side-effect only): reads a status byte at
 * 0xFFFFCD4C and writes a gauge value byte to 0xFFFFD2C4:
 *
 *   b = byte@0xFFFFCD4C
 *   v = (b & 0x7C) ? 7 : (b & 0x80) ? 6 : 0      // bits 0x40|0x20|0x10|0x08|0x04
 *   byte@0xFFFFD2C4 = v
 *
 * SH-2E pattern per bit: tst #imm,r0; movt r0; add #0xFF,r0; neg r0,r0;
 * cmp/eq #0x01,r0; bt/s → r2 = 7  (0x40/0x20/0x10/0x08/0x04 checked first,
 * 0x80 → r2 = 6 last, else r1 = 0).  Return r0 is the last-loaded input
 * byte (sign-extended), not meaningful — lift returns void.
 *
 * NOTE: mov.w @(disp,PC) sign-extends the short literals: disassembler
 * prints 0xD2C4/0xCD4C but the real addresses are 0xFFFFD2C4/0xFFFFCD4C.
 *
 * Verified against ROM emulator: c/tests/test_temperature_gauge_0x5AA5C.py
 * Host C companion:             c/tests/test_temperature_gauge_0x5AA5C.c
 */
#include <stdint.h>

/* 0x5AA5C — map status byte bits to gauge value */
void temperature_gauge_0x5AA5C(void)
{
    uint8_t b = *(volatile uint8_t *)0xFFFFCD4C;
    uint8_t v = (b & 0x7C) ? 7 : (b & 0x80) ? 6 : 0;
    *(volatile uint8_t *)0xFFFFD2C4 = v;
}
