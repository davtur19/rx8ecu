/* bitfield_flag_status_decoder_339AC.c
 *
 * ROM: 60E1D400  |  Address: 0x339AC  |  Size: 74 bytes (to 0x339F8)
 *
 * Flag-status decoder leaf (side-effect only): reads a status byte at
 * 0xFFFFCD4E and writes a decoded status code byte to 0xFFFFC04D:
 *
 *   b = byte@0xFFFFCD4E
 *   v = (b & 0x60) ? 0x08 : (b & 0x80) ? 0x02 : 0
 *   byte@0xFFFFC04D = v
 *
 * Bit-test idiom: tst #imm,r0; movt r0; add #0xFF,r0; neg r0,r0;
 * cmp/eq #0x01,r0; bt/s → 0x40|0x20 → 0x08, 0x80 → 0x02, else 0x00.
 * Return r0 is the last-loaded input byte (sign-extended), not meaningful
 * — lift returns void.
 *
 * NOTE: mov.w sign-extends 0xCD4E → input is 0xFFFFCD4E; the output
 * 0xFFFFC04D comes from a mov.l literal (already full address).
 *
 * Verified against ROM emulator: c/tests/test_bitfield_flag_status_decoder_339AC.py
 * Host C companion:             c/tests/test_bitfield_flag_status_decoder_339AC.c
 */
#include <stdint.h>

/* 0x339AC — decode status bits into status code byte */
void bitfield_flag_status_decoder_339AC(void)
{
    uint8_t b = *(volatile uint8_t *)0xFFFFCD4E;
    uint8_t v = (b & 0x60) ? 0x08 : (b & 0x80) ? 0x02 : 0;
    *(volatile uint8_t *)0xFFFFC04D = v;
}
