/* obd_service_handler_63B46.c
 *
 * ROM: 60E1D400  |  Address: 0x63B46  |  Size: 32 bytes (to 0x63B66)
 *
 * OBD debounce-state writer leaf, takes r4 (byte value).  Addresses the DTC
 * context-table row selected by the "current DTC index" word @0xFFFF8928
 * (base 0xFFFF87D8, 16-byte stride) and folds r4 into the row's two
 * debounce/status bytes at +0x0E and +0x0D:
 *
 *   idx = word@0xFFFF8928 & 0xFFFF
 *   p   = 0xFFFF87D8 + idx*16
 *   byte@p+0x0E = (s8(byte@p+0x0E) + s8(byte@p+0x0D) - r4) & 0xFF
 *   byte@p+0x0D = r4 & 0xFF
 *
 * (byte reads are sign-extended mov.b; the sum is stored low-byte.  r0 = r4
 * on exit — the lift returns it for completeness, matching rts delay slot.)
 *
 * SH-2E asm:
 *   0x63B46: mov.l  0x63CA8,r3            ; r3 = 0xFFFF8928
 *   0x63B48: mov.l  0x63CA4,r2            ; r2 = 0xFFFF87D8
 *   0x63B4A: mov.w  @r3,r6                ; r6 = cur
 *   0x63B4C: extu.w r6,r5                 ; r5 = cur & 0xFFFF
 *   0x63B4E: shll2  r5
 *   0x63B50: shll2  r5                    ; r5 = idx*16
 *   0x63B52: add    r2,r5                 ; p = base + idx*16
 *   0x63B54: mov.b  @(0x0D,r5),r0         ; r0 = s8(p[0x0D])
 *   0x63B56: mov    r0,r6                 ; r6 = s8(p[0x0D])
 *   0x63B58: mov.b  @(0x0E,r5),r0         ; r0 = s8(p[0x0E])
 *   0x63B5A: sub    r4,r6                 ; r6 = s8(p[0x0D]) - r4
 *   0x63B5C: add    r6,r0                 ; r0 = s8(p[0x0E]) + s8(p[0x0D]) - r4
 *   0x63B5E: mov.b  r0,@(0x0E,r5)         ; p[0x0E] = r0 & 0xFF
 *   0x63B60: mov    r4,r0                 ; r0 = r4
 *   0x63B62: rts
 *   0x63B64: mov.b  r0,@(0x0D,r5)         ; (delay) p[0x0D] = r4 & 0xFF
 *
 * Called from dtc_handler_61550 (0x61550) mode 3 / mode 1 acceptance paths
 * to write the debounce state back into the DTC's context row.
 *
 * Verified against ROM emulator: c/tests/test_obd_service_handler_63B46.py
 * Host C companion:             c/tests/test_obd_service_handler_63B46.c
 */
#include <stdint.h>

#define CTX_BASE   0xFFFF87D8u   /* DTC context table base                */
#define CTX_STRIDE 16u
#define CUR_INDEX  0xFFFF8928u   /* word: current DTC index being serviced */

/* 0x63B46 — write r4 into the active context row's debounce bytes */
uint32_t obd_service_handler_63B46(uint32_t r4)
{
    uint16_t idx = *(volatile uint16_t *)CUR_INDEX;
    uint8_t *p = (uint8_t *)(CTX_BASE + (uint32_t)(idx & 0xFFFFu) * CTX_STRIDE);
    p[0x0E] = (uint8_t)((int32_t)(int8_t)p[0x0E] + (int32_t)(int8_t)p[0x0D]
                        - (int32_t)r4);
    p[0x0D] = (uint8_t)r4;
    return r4;
}
