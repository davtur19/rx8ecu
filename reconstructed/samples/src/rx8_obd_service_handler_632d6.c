/*
 * =============================================================================
 * rx8_obd_service_handler_632d6.c  —  OBD PENDING-FLAG CLEAR LEAF (SIDE EFFECT)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x632D6
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_obd_service_handler_632d6.py
 *               (host-gcc vs tools/sh2emu.py over exhaustive + 20000 random
 *               (flag, pad) vectors, 0 mismatches on the RAM side effect).
 * Lift (truth): c/obd_service_handler_632D6.c  (30 bytes, to 0x632F4)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * One of the byte-pending-flag family 0x632D6 / 0x632F4 / 0x63312 (flags at
 * 0xFFFF87CC / 0xFFFF87CE / 0xFFFF87D0), tail-called from the DTC handlers.
 * Each clears its 16-bit "pending service" cell when the flag byte reads 1,
 * rewriting it with the value/complement encoding of 0 via the verified enc8
 * leaf 0x2420 (c/math_primitives.c `encode()`):  enc8(0) == 0x00FF.
 *
 * Disassembly of 60E1D400.bin @ 0x632D6:
 *
 *     4F22   sts.l  pr,@-r15             ; prologue
 *     D350   mov.l  0x6341C,r3           ; r3 = 0xFFFF87CC
 *     6030   mov.b  @r3,r0               ; r0 = byte@0xFFFF87CC
 *     600C   extu.b r0,r0
 *     8801   cmp/eq #1,r0
 *     8F05   bf/s   0x632EE              ; skip unless the flag byte == 1
 *     0009   nop
 *     D153   mov.l  0x63434,r1           ; r1 = 0x2420 (enc8)
 *     410B   jsr    @r1
 *     E400   mov    #0,r4                ;   (delay) r4 = 0
 *     D34C   mov.l  0x6341C,r3           ; r3 = 0xFFFF87CC again
 *     2301   mov.w  r0,@r3               ; word@0xFFFF87CC = enc8(0) == 0x00FF
 *     4F26   lds.l  @r15+,pr
 *     000B   rts
 *     0009   nop
 *
 * CALLING CONVENTION
 * ------------------
 * ABI-clean but takes no arguments and returns nothing meaningful (r0 holds
 * the enc8 result on the write path — the lift deliberately returns void).
 * All observable behaviour is the RAM side effect on the 16-bit cell at
 * 0xFFFF87CC, which sits just below the DTC context table at 0xFFFF87D8.
 *
 * ENDIANNESS
 * ----------
 * The SH-2E is big-endian: byte@0xFFFF87CC is the HIGH byte of the 16-bit
 * cell word.  The cell is therefore read as a uint16_t and shifted >>8 so the
 * host-C build matches the ROM regardless of host endianness (same convention
 * as 0x64490, c/obd_dtc_row_update_0x64490.c); all seeding/checking in the
 * harness and oracle goes through the uint16_t word value.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

/* enc8 = verified leaf 0x2420 (c/math_primitives.c `encode()`): x<<8 | ~x.
 * (SH-2E: shll8 + not + extu.b + add — addition carries never touch bit 7,
 *  so x<<8 | ~x and x<<8 + (~x & 0xFF) are identical.) */
static inline uint16_t enc8(uint8_t x)
{
    return (uint16_t)((x << 8) | (uint8_t)~x);
}

/* 0x632D6 — if the pending-flag byte at 0xFFFF87CC reads 1, rewrite the whole
 * 16-bit cell as enc8(0) = 0x00FF, i.e. "no longer pending".  Anything else
 * leaves the cell untouched. */
void rx8_obd_service_handler_632d6(void)
{
    if (((*(volatile uint16_t *)0xFFFF87CCu >> 8) & 0xFFu) == 0x01u)
        *(volatile uint16_t *)0xFFFF87CCu = enc8(0x00u);
}
