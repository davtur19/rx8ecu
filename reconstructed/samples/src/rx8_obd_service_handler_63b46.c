/*
 * =============================================================================
 * rx8_obd_service_handler_63b46.c  —  OBD DEBOUNCE-STATE WRITER LEAF (SIDE EFFECT)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x63B46  (32 bytes, to 0x63B66)
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_obd_service_handler_63b46.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + N random
 *               (r4, idx, b0d, b0e) vectors, 0 mismatches on the return value
 *               AND the two side-effected RAM bytes), in addition to the
 *               existing emulator test c/tests/test_obd_service_handler_63B46.py.
 * Lift (truth): c/obd_service_handler_63B46.c  (same address, same behaviour)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * OBD debounce-state writer leaf.  Called from dtc_handler_61550 (0x61550)
 * mode 3 / mode 1 acceptance paths to fold the new sample value r4 into the
 * debounce/status bytes of the DTC context-table row that is currently being
 * serviced.  The row is selected by the "current DTC index" word @0xFFFF8928;
 * the DTC context table lives at 0xFFFF87D8 with a 16-byte stride (21 rows,
 * 0xFFFF87D8..0xFFFF8928 — the same region as the pending-flag cells at
 * 0xFFFF87CC/0xFFFF87D0 and the DTC table at 0xFFFF8930, FINDINGS.md):
 *
 *   idx = word@0xFFFF8928 & 0xFFFF
 *   p   = 0xFFFF87D8 + idx*16
 *   byte@p+0x0E = (s8(byte@p+0x0E) + s8(byte@p+0x0D) - r4) & 0xFF
 *   byte@p+0x0D = r4 & 0xFF
 *
 * i.e. the previous sample value (p+0x0D) is shifted into the accumulator
 * (p+0x0E) and the new sample r4 is written into p+0x0D.  Both row bytes are
 * read SIGN-EXTENDED (`mov.b @(d,Rn),R0`), so byte values >= 0x80 contribute
 * as negative quantities to the 32-bit sum; only the low byte of the result
 * is stored back, exactly as the `mov.b R0,@(d,Rn)` write stores the low
 * byte of r0.  r4 enters the subtraction as the full 32-bit operand of
 * `sub r4,r6`, so only r4's low byte affects the stored result, but the
 * function returns the untouched full r4 in r0 (the rts delay slot is
 * `mov.b r0,@(0x0D,r5)`, and `mov r4,r0` before it makes r0 = r4).
 *
 * Disassembly of 60E1D400.bin @ 0x63B46 (byte-exact from the ROM):
 *
 *     D358   mov.l  0x63CA8,r3          ; r3 = 0xFFFF8928 (cur DTC index word)
 *     D256   mov.l  0x63CA4,r2          ; r2 = 0xFFFF87D8 (context table base)
 *     6631   mov.w  @r3,r6              ; r6 = cur (sign-extended word)
 *     656D   extu.w r6,r5               ; r5 = cur & 0xFFFF
 *     4508   shll2  r5                  ; \
 *     4508   shll2  r5                  ; / r5 = idx*16
 *     352C   add    r2,r5               ; p = base + idx*16
 *     845D   mov.b  @(0x0D,r5),r0       ; r0 = s8(p[0x0D])
 *     6603   mov    r0,r6               ; r6 = s8(p[0x0D])
 *     845E   mov.b  @(0x0E,r5),r0       ; r0 = s8(p[0x0E])
 *     3648   sub    r4,r6               ; r6 = s8(p[0x0D]) - r4
 *     306C   add    r6,r0               ; r0 = s8(p[0x0E]) + s8(p[0x0D]) - r4
 *     805E   mov.b  r0,@(0x0E,r5)       ; p[0x0E] = r0 & 0xFF
 *     6043   mov    r4,r0               ; r0 = r4
 *     000B   rts
 *     805D   mov.b  r0,@(0x0D,r5)       ; (delay) p[0x0D] = r4 & 0xFF
 *
 * CALLING CONVENTION
 * ------------------
 * Leaf, normal ABI for the argument (r4) and result (r0).  Because the
 * observable behaviour is the RAM side effect (plus the r0 = r4 return
 * value), the equivalence harness seeds the three RAM cells and compares the
 * two written bytes and the return value.
 *
 * RAM SIDE EFFECTS
 * ----------------
 * Writes byte@p+0x0D and byte@p+0x0E of the row selected by word@0xFFFF8928.
 * The harness mirrors both cells on the host via mmap(MAP_FIXED) of the
 * 0xFFFF8000 page (identical trick to the 632D6/63312/63834/648B4 siblings).
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

/* DTC context table row selector + geometry.  The addresses are documented in
 * c/obd_service_handler_63B46.c and FINDINGS.md (OBD DTC-table family). */
#define CTX_BASE   0xFFFF87D8u   /* DTC context table base                */
#define CTX_STRIDE 16u
#define CUR_INDEX  0xFFFF8928u   /* word: current DTC index being serviced */

/* 0x63B46 — fold the new sample r4 into the active context row's two
 * debounce/status bytes and return r4 (port of c/obd_service_handler_63B46.c
 * verbatim; the sign-extended byte reads and the low-byte stores reproduce
 * the SH-2E mov.b semantics exactly). */
uint32_t rx8_obd_service_handler_63b46(uint32_t r4)
{
    uint16_t idx = *(volatile uint16_t *)CUR_INDEX;
    uint8_t *p = (uint8_t *)(uintptr_t)(CTX_BASE
                                        + (uint32_t)(idx & 0xFFFFu)
                                        * CTX_STRIDE);
    p[0x0E] = (uint8_t)((int32_t)(int8_t)p[0x0E] + (int32_t)(int8_t)p[0x0D]
                        - (int32_t)r4);
    p[0x0D] = (uint8_t)r4;
    return r4;
}
