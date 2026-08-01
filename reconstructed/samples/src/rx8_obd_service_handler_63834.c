/*
 * =============================================================================
 * rx8_obd_service_handler_63834.c  —  OBD MODE-1 STATUS READ LEAF
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x63834  (82 bytes, to 0x63886)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_obd_service_handler_63834.py
 *               (host-gcc vs tools/sh2emu.py over 20000 random + edge vectors;
 *               0 mismatches).
 * Lift (truth): c/obd_service_handler_63834.c  (obd_service_handler_63834,
 *               0x63834..0x63886; also verified by
 *               c/tests/test_obd_service_handler_63834.{py,c})
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * OBD mode-1 status read leaf: it scans the 21-entry DTC context table
 * (base 0xFFFF87D8, 16-byte stride, code word @+0, type byte @+6) for the
 * first entry whose 16-bit code equals (r4 & 0xFFFF) and whose row index
 * differs from the "current DTC index" word @0xFFFF8928.  It returns the type
 * byte at +6, sign-extended (mov.b), else 0.  dtc_handler_61550 calls it on
 * the mode-1 (pending) and mode-2 (confirmed) paths to read a DTC's status
 * byte before re-encoding it.
 *
 * Disassembly of 60E1D400.bin @ 0x63834 (from the lift; dead code marked):
 *
 *     0x63834  mov.l  0x63A00,r0        ; r0 = 0x0000FFFF (unused mask)
 *     0x63836  mov    #0,r5             ; i = 0
 *     0x63838  mov.l  0x63A04,r6        ; r6 = 0xFFFF87D8 (table base)
 *     0x6383A  mov    #0x15,r1          ; r1 = 21 (bound)
 *     0x6383C  mov    r5,r7             ; r7 = 0 (default result)
 *     L:       mov    r5,r3             ; r3 = i
 *     0x63840  shll2  r3                ;   (x2)
 *     0x63842  shll2  r3                ; r3 = i*16
 *     0x63844  add    r6,r3             ; p = base + i*16
 *     0x63846  mov.w  @r3,r2            ; code = word@p
 *     0x63848  extu.w r2,r2
 *     0x6384A  extu.w r4,r3             ; r3 = r4 & 0xFFFF
 *     0x6384C  cmp/eq r3,r2             ; T = (code == r4)
 *     0x6384E  bf/s   0x6386C           ; no match -> loop tail
 *     0x63850  nop
 *     0x63852  mov.l  0x639FC,r2        ; r2 = 0xFFFF8928
 *     0x63854  mov.w  @r2,r3            ; r3 = cur
 *     0x63856  extu.w r3,r3             ; r3 = cur & 0xFFFF
 *     0x63858  cmp/eq r5,r3             ; T = (i == cur)
 *     0x6385A  bt/s   0x6386C           ; current row -> skip
 *     0x6385C  nop
 *     0x6385E  mov    r5,r7
 *     0x63860  shll2  r7                ;   (x2)
 *     0x63862  shll2  r7
 *     0x63864  add    r6,r7             ; r7 = p
 *     0x63866  mov.b  @(0x06,r7),r0     ; r0 = s8(p[6])
 *     0x63868  bra    0x63882
 *     0x6386A  mov    r0,r7             ;   (delay) r7 = s8(p[6])
 *     0x6386C  mov    r5,r3             ; loop tail
 *     0x6386E  shll2  r3
 *     0x63870  shll2  r3
 *     0x63872  add    r6,r3
 *     0x63874  mov.w  @r3,r2            ; (dead) re-read
 *     0x63876  add    #1,r5             ; i++
 *     0x63878  extu.w r2,r2
 *     0x6387A  cmp/eq r0,r2             ; (dead; T overwritten)
 *     0x6387C  cmp/ge r1,r5             ; T = (i >= 21)
 *     0x6387E  bf/s   0x6383E           ; i < 21 -> L
 *     0x63880  nop
 *     0x63882  rts
 *     0x63884  mov    r7,r0             ; return r7 (delay)
 *
 * The scan is a do-while (i is bumped in the loop tail and re-read at the top)
 * which executes rows 0..20 exactly like a `for (i = 0; i < 21; i++)`.  Two
 * instructions are dead: the `cmp/eq r0,r2` at 0x6387A never selects anything
 * because its T bit is overwritten by the `cmp/ge` that follows.
 *
 * RAM SIDE EFFECTS
 * ----------------
 * NONE — the function only READS the on-chip RAM window (the context table
 * and the current-index word); it never stores.  Equivalence therefore
 * compares the 32-bit return value only, but the oracle still mirrors the
 * table + index state on the host (MAP_FIXED, see the harness) because that
 * state is what the scan runs over.
 *
 * CALLING CONVENTION
 * ------------------
 * Entry is the normal ABI: r4 = 16-bit DTC code (only r4 & 0xFFFF is used),
 * result returned in r0 (sign-extended int32, or 0).
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

#define CTX_BASE   0xFFFF87D8u   /* DTC context table base                */
#define CTX_STRIDE 16u
#define CTX_COUNT  21u           /* 0xFFFF87D8 + 21*16 == 0xFFFF8928      */
#define CUR_INDEX  0xFFFF8928u   /* word: current DTC index being serviced */

/* 0x63834 — return the type byte of the table entry matching r4, else 0.
 *
 *   cur = u16@0xFFFF8928
 *   for i in 0..20:
 *       p = 0xFFFF87D8 + i*16
 *       if u16@p == (r4 & 0xFFFF) and i != (cur & 0xFFFF):
 *           return (int32_t)(int8_t)p[6]      ; mov.b sign-extends
 *   return 0
 *
 * (int8_t) reproduces the sign-extending byte load; the (int32_t) cast gives
 * the sign-extended r0 the ROM returns. */
int32_t obd_service_handler_63834(uint32_t r4)
{
    uint16_t cur = *(volatile uint16_t *)CUR_INDEX;
    for (uint32_t i = 0; i < CTX_COUNT; i++) {
        uint8_t *p = (uint8_t *)(uintptr_t)(CTX_BASE + i * CTX_STRIDE);
        if (*(volatile uint16_t *)p == (uint16_t)(r4 & 0xFFFFu)
            && i != (uint32_t)(cur & 0xFFFFu))
            return (int32_t)(int8_t)p[6];
    }
    return 0;
}
