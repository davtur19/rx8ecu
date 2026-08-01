/* warning_light_0x5AADE.c
 *
 * ROM: 60E1D400  |  Address: 0x5AADE  |  Size: 68 bytes (to 0x5AB66)
 *
 * Warning-light value setter leaf (side-effect only): reads a status byte
 * at 0xFFFFCD4C and writes a warning-light value byte to 0xFFFFD2C5:
 *
 *   b = byte@0xFFFFCD4C
 *   v = (b & 0x60) ? 0x6D : (b & 0x1C) ? 0x69 : (b & 0x80) ? 0x68 : 0
 *   byte@0xFFFFD2C5 = v
 *
 * Same tst/movt/add/neg/cmp/eq bit-test idiom as temperature_gauge_0x5AA5C;
 * bit order checked: 0x40→0x6D, 0x20→0x6D, 0x10→0x69, 0x08→0x69, 0x04→0x69,
 * 0x80→0x68, else 0.  Return r0 not meaningful — lift returns void.
 *
 * NOTE: mov.w sign-extends — 0xD2C5/0xCD4C are really 0xFFFFD2C5/0xFFFFCD4C.
 *
 * Verified against ROM emulator: c/tests/test_warning_light_0x5AADE.py
 * Host C companion:             c/tests/test_warning_light_0x5AADE.c
 */
#include <stdint.h>

/* 0x5AADE — map status byte bits to warning-light value */
void warning_light_0x5AADE(void)
{
    uint8_t b = *(volatile uint8_t *)0xFFFFCD4C;
    uint8_t v = (b & 0x60) ? 0x6D : (b & 0x1C) ? 0x69 : (b & 0x80) ? 0x68 : 0;
    *(volatile uint8_t *)0xFFFFD2C5 = v;
}
