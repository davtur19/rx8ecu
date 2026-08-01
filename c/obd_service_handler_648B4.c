/* obd_service_handler_648B4.c
 *
 * ROM: 60E1D400  |  Address: 0x648B4  |  Size: 48 bytes (to 0x648E4)
 *
 * OBD run-sum update leaf (side-effect only), takes r4 (byte value).
 * Two redundant (value,complement) 16-bit cells at 0xFFFF8E98 / 0xFFFF8E9A
 * track per-DTC encode counters; each is rewritten with the value/complement
 * encoder enc8(x) = (x << 8) | ~x  (the verified leaf 0x2420,
 * c/math_primitives.c `encode()`):
 *
 *   b   = r4 & 0xFF
 *   sum = (s8(high8(word@0xFFFF8E98)) + s8(high8(word@0xFFFF8E9A))
 *          - s8(b)) & 0xFF
 *   word@0xFFFF8E98 = enc8(sum)
 *   word@0xFFFF8E9A = enc8(b)
 *
 * (host-C endian note: byte@addr of a big-endian cell is the high byte of the
 * word; the lift therefore reads the 16-bit cells and extracts the high byte
 * with >>8, the same endian-safe pattern as obd_dtc_row_update_0x64490.)
 *
 * SH-2E asm (mov.b reads are sign-extended; enc8 only looks at the low byte,
 * so the delta folds mod 256 — the first 0x2420 call gets the running delta,
 * the second the raw r4):
 *
 *   0x648B4: sts.l  pr,@-r15
 *   0x648B6: add    #0xFC,r15            ; 4-byte stack slot
 *   0x648B8: mov.l  0x648EC,r2           ; r2 = 0xFFFF8E9A
 *   0x648BA: mov.b  r4,@r15              ; save b = r4&0xFF on stack
 *   0x648BC: mov.b  @r15,r3              ; r3 = s8(b)
 *   0x648BE: mov.b  @r2,r4               ; r4 = s8(byte@0xFFFF8E9A)
 *   0x648C0: mov.l  0x648F4,r2           ; r2 = 0xFFFF8E98
 *   0x648C2: sub    r3,r4                ; r4 = s8(b9A) - s8(b)
 *   0x648C4: mov.b  @r2,r1               ; r1 = s8(byte@0xFFFF8E98)
 *   0x648C6: add    r1,r4                ; r4 = s8(b98) + s8(b9A) - s8(b)
 *   0x648C8: mov.l  0x64904,r1           ; r1 = 0x2420 (enc8)
 *   0x648CA: jsr    @r1
 *   0x648CC: nop
 *   0x648CE: mov.l  0x648F4,r3           ; r3 = 0xFFFF8E98
 *   0x648D0: mov.l  0x64904,r2           ; r2 = 0x2420
 *   0x648D2: mov.w  r0,@r3               ; word@0xFFFF8E98 = enc8(delta)
 *   0x648D4: jsr    @r2
 *   0x648D6: mov.b  @r15,r4              ; (delay) r4 = s8(b)
 *   0x648D8: mov.l  0x648EC,r3           ; r3 = 0xFFFF8E9A
 *   0x648DA: mov.w  r0,@r3               ; word@0xFFFF8E9A = enc8(b)
 *   0x648DC: add    #0x04,r15
 *   0x648DE: lds.l  @r15+,pr
 *   0x648E0: rts
 *   0x648E2: nop
 *
 * Called from can_encode_handler_62ABC (0x62ABC, .py-tested) to fold each
 * encoded DTC into the two running-sum cells.
 *
 * Verified against ROM emulator: c/tests/test_obd_service_handler_648B4.py
 * Host C companion:             c/tests/test_obd_service_handler_648B4.c
 */
#include <stdint.h>

static inline uint16_t enc8(uint8_t x)      /* verified leaf 0x2420          */
{
    return (uint16_t)((x << 8) | (uint8_t)~x);
}

/* 0x648B4 — fold r4 into the two run-sum cells 0xFFFF8E98 / 0xFFFF8E9A */
void obd_service_handler_648B4(uint32_t r4)
{
    uint8_t  b   = (uint8_t)(r4 & 0xFFu);
    /* byte@0xFFFF8E98/0xFFFF8E9A is the high byte of the 16-bit cell; read
     * the cell as a uint16_t and >>8 so the host-C build matches the ROM
     * regardless of host endianness (same pattern as 0x64490). */
    uint16_t w98 = *(volatile uint16_t *)0xFFFF8E98;
    uint16_t w9A = *(volatile uint16_t *)0xFFFF8E9A;
    int32_t  sum = (int32_t)(int8_t)((w98 >> 8) & 0xFF)
                 + (int32_t)(int8_t)((w9A >> 8) & 0xFF)
                 - (int32_t)(int8_t)b;
    *(volatile uint16_t *)0xFFFF8E98 = enc8((uint8_t)sum);
    *(volatile uint16_t *)0xFFFF8E9A = enc8(b);
}
