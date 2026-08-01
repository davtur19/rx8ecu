/* obd_service_handler_632D6.c
 *
 * ROM: 60E1D400  |  Address: 0x632D6  |  Size: 30 bytes (to 0x632F4)
 *
 * OBD pending-flag clear leaf (side-effect only).  If the byte at 0xFFFF87CC
 * (a "pending service" marker just below the DTC context table at 0xFFFF87D8)
 * equals 1, it is rewritten as the value/complement encoding of 0, i.e. the
 * 16-bit cell word@0xFFFF87CC = enc8(0) = 0x00FF, marking the flag "no
 * longer pending" in the redundant-storage convention:
 *
 *   if (byte@0xFFFF87CC == 0x01)
 *       word@0xFFFF87CC = enc8(0x00);       // 0x2420(0) == 0x00FF
 *
 * enc8 is the verified leaf 0x2420 (c/math_primitives.c `encode()`):
 * x<<8 | ~x.  Return r0 = the enc8 result — not meaningful; lift returns void.
 *
 * SH-2E asm:
 *   0x632D6: sts.l  pr,@-r15
 *   0x632D8: mov.l  0x6341C,r3            ; r3 = 0xFFFF87CC
 *   0x632DA: mov.b  @r3,r0                ; r0 = byte@0xFFFF87CC
 *   0x632DC: extu.b r0,r0
 *   0x632DE: cmp/eq #1,r0
 *   0x632E0: bf/s   0x632EE               ; skip unless == 1
 *   0x632E2: nop
 *   0x632E4: mov.l  0x63434,r1            ; r1 = 0x2420 (enc8)
 *   0x632E6: jsr    @r1
 *   0x632E8: mov    #0,r4                 ; (delay) r4 = 0
 *   0x632EA: mov.l  0x6341C,r3
 *   0x632EC: mov.w  r0,@r3                ; word@0xFFFF87CC = enc8(0)
 *   0x632EE: lds.l  @r15+,pr
 *   0x632F0: rts
 *   0x632F2: nop
 *
 * Part of the byte-pending-flag family 0x632D6/0x632F4/0x63312 (flags
 * 0xFFFF87CC / 0xFFFF87CE / 0xFFFF87D0), tail-called from the DTC handlers.
 *
 * Verified against ROM emulator: c/tests/test_obd_service_handler_632D6.py
 * Host C companion:             c/tests/test_obd_service_handler_632D6.c
 */
#include <stdint.h>

static inline uint16_t enc8(uint8_t x)      /* verified leaf 0x2420          */
{
    return (uint16_t)((x << 8) | (uint8_t)~x);
}

/* 0x632D6 — clear the 0xFFFF87CC pending flag when it reads 1 */
void obd_service_handler_632D6(void)
{
    /* byte@0xFFFF87CC is the high byte of the 16-bit cell; read the cell as
     * a uint16_t and >>8 so the host-C build matches the ROM regardless of
     * host endianness (same pattern as 0x64490). */
    if (((*(volatile uint16_t *)0xFFFF87CC >> 8) & 0xFFu) == 0x01u)
        *(volatile uint16_t *)0xFFFF87CC = enc8(0x00u);
}
