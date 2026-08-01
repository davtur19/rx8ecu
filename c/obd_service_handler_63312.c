/* obd_service_handler_63312.c
 *
 * ROM: 60E1D400  |  Address: 0x63312  |  Size: 30 bytes (to 0x63330)
 *
 * OBD pending-flag clear leaf (side-effect only), identical logic to
 * 0x632D6 but for the flag at 0xFFFF87D0 (just below the DTC context table
 * at 0xFFFF87D8).  Tail-called from dtc_handler_610FA (0x610FA) as the
 * last step of the standard/MIL service chain:
 *
 *   if (byte@0xFFFF87D0 == 0x01)
 *       word@0xFFFF87D0 = enc8(0x00);       // 0x2420(0) == 0x00FF
 *
 * enc8 is the verified leaf 0x2420 (c/math_primitives.c `encode()`):
 * x<<8 | ~x.  Return r0 = the enc8 result — not meaningful; lift returns void.
 *
 * SH-2E asm:
 *   0x63312: sts.l  pr,@-r15
 *   0x63314: mov.l  0x63424,r2            ; r2 = 0xFFFF87D0
 *   0x63316: mov.b  @r2,r0                ; r0 = byte@0xFFFF87D0
 *   0x63318: extu.b r0,r0
 *   0x6331A: cmp/eq #1,r0
 *   0x6331C: bf/s   0x6332A               ; skip unless == 1
 *   0x6331E: nop
 *   0x63320: mov.l  0x63434,r1            ; r1 = 0x2420 (enc8)
 *   0x63322: jsr    @r1
 *   0x63324: mov    #0,r4                 ; (delay) r4 = 0
 *   0x63326: mov.l  0x63424,r3
 *   0x63328: mov.w  r0,@r3                ; word@0xFFFF87D0 = enc8(0)
 *   0x6332A: lds.l  @r15+,pr
 *   0x6332C: rts
 *   0x6332E: nop
 *
 * Part of the byte-pending-flag family 0x632D6/0x632F4/0x63312 (flags
 * 0xFFFF87CC / 0xFFFF87CE / 0xFFFF87D0).
 *
 * Verified against ROM emulator: c/tests/test_obd_service_handler_63312.py
 * Host C companion:             c/tests/test_obd_service_handler_63312.c
 */
#include <stdint.h>

static inline uint16_t enc8(uint8_t x)      /* verified leaf 0x2420          */
{
    return (uint16_t)((x << 8) | (uint8_t)~x);
}

/* 0x63312 — clear the 0xFFFF87D0 pending flag when it reads 1 */
void obd_service_handler_63312(void)
{
    /* byte@0xFFFF87D0 is the high byte of the 16-bit cell; read the cell as
     * a uint16_t and >>8 so the host-C build matches the ROM regardless of
     * host endianness (same pattern as 0x64490). */
    if (((*(volatile uint16_t *)0xFFFF87D0 >> 8) & 0xFFu) == 0x01u)
        *(volatile uint16_t *)0xFFFF87D0 = enc8(0x00u);
}
