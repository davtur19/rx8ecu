/*
 * =============================================================================
 * rx8_can_encode_handler_62abc.c  —  DTC MODE-DISPATCH LEAF ON THE CAN-ENCODE PATH
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x62ABC  (size 104 bytes, 0x62ABC..0x62B23)
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_can_encode_handler_62abc.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + N random
 *               vectors; the two run-sum RAM cells compared byte-for-byte).
 * Lift (truth): c/can_encode_handler_62ABC.c  (verified bit-exact via
 *               tools/sh2emu.py; c/tests/test_can_encode_handler_62ABC.py).
 *
 * WHAT THIS IS (and is NOT)
 * -------------------------
 * Despite the "can_encode" name, this is NOT a CAN-frame packer.  It is the
 * common tail of dtc_handler_61550's mode-3 path: it reads a per-DTC mode
 * dispatch byte and, for selected mode values, folds the incoming r5 value
 * into the two 16-bit "run-sum" cells 0xFFFF8E98 / 0xFFFF8E9A via the
 * run-sum leaf obd_service_handler_648B4.  Those cells are the per-DTC
 * encode counters that the OBD/CAN-encode pipeline later transmits, which is
 * where the function's name comes from.  (The original task brief described
 * this as a "CAN message encoder that packs sensor values into a CAN transmit
 * buffer" — the verified lift and the ROM bytes show otherwise; this port
 * follows the lift.)
 *
 *   mode = byte@(0xFFFF8D7C + (dtc & 0xFFFF) * 2)   // per-DTC table, stride 2
 *   vl   = r5 & 0xFF
 *
 *   mode == 0x00          -> obd_service_handler_648B4(r5)
 *   mode == 0x10          -> obd_service_handler_648B4(r5) iff vl==0x20 || vl==0x11
 *   mode == 0x11          -> obd_service_handler_648B4(r5) iff vl==0x20
 *   mode == 0x20 (or any other value) -> no call
 *
 * The mode table is really a 16-bit-per-DTC table — the sibling function at
 * 0x62B24 reads the high byte at 0xFFFF8D7D + dtc*2.  The tests restrict dtc
 * to 0..0x7F so the table read (max 0xFFFF8E7A) stays clear of the run-sum
 * cells at 0xFFFF8E98/0xFFFF8E9A — a test-only bound.
 *
 * SH-2E asm (60E1D400.bin @0x62ABC; both PC-relative literals checked:
 * @0x62B9C = 0xFFFF8D7C, @0x62BA0 = 0x000648B4):
 *
 *     2FE6  mov.l  r14,@-r15           ; prologue
 *     644D  extu.w r4,r4               ; dtc &= 0xFFFF
 *     D036  mov.l  @(0x36,PC),r0       ; r0 = 0xFFFF8D7C (mode table)
 *     6E53  mov    r5,r14              ; r14 = r5
 *     4400  shll   r4                  ; r4 = dtc*2
 *     044C  mov.b  @(r0,r4),r4         ; mode = byte@(table + dtc*2)
 *     604C  extu.b r4,r0               ; r0 = mode & 0xFF
 *     8800  cmp/eq #0,r0 ; bt/s ...    ; mode == 0 -> call
 *     8810  cmp/eq #0x10,r0 ; bt/s ... ; mode 0x10 -> vl==0x20 || vl==0x11
 *     8811  cmp/eq #0x11,r0 ; bt/s ... ; mode 0x11 -> vl==0x20 only
 *     8820  cmp/eq #0x20,r0 ; bt/s ... ; mode 0x20 -> no call (explicit)
 *     4D0B  jsr    @r13                ;   (r13 = 0x648B4, loaded at 0x62ACE)
 *     64E3  mov    r14,r4              ;   (delay) r4 = r5
 *     4F26  6CF6 6DF6 000B 6EF6        ; epilogue: lds pr / r12 / r13; rts; r14
 *
 * CALLING CONVENTION & CALLEE
 * ---------------------------
 * Normal ABI entry: r4 = dtc (u32, masked to 16 bits), r5 = value to fold.
 * void — the whole effect is the RAM write through the external leaf.
 *
 * The callee 0x648B4 is a verified tiny leaf (c/obd_service_handler_648B4.c):
 *   b = r4 & 0xFF
 *   sum = (s8(hi8(word@0xFFFF8E98)) + s8(hi8(word@0xFFFF8E9A)) - s8(b)) & 0xFF
 *   word@0xFFFF8E98 = enc8(sum);  word@0xFFFF8E9A = enc8(b)
 * where enc8(x) = (x<<8) | ~x  (verified leaf 0x2420).  It is NOT inlined
 * here: the sample declares the call exactly as the lift does, and the oracle
 * supplies the leaf's body (a verbatim port of the verified lift) so the host
 * binary mirrors the real RAM side effects — the emulator side runs the REAL
 * 0x648B4 ROM bytes.
 *
 * RAM SIDE EFFECTS (must be mirrored by any oracle):
 *   word@0xFFFF8E98, word@0xFFFF8E9A — updated only when a call is made.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

#define RX8_MODE_TABLE  0xFFFF8D7Cu   /* per-DTC mode dispatch byte table      */

/* 0x648B4 — OBD run-sum update leaf (fold r4 into the two encode counters).
 * A verified tiny leaf with its own lift (c/obd_service_handler_648B4.c); the
 * host oracle provides this body so the reconstructed sample stays a faithful
 * single-purpose port of the lift (same convention as c/dtc_handler_61550.c). */
extern void obd_service_handler_648B4(uint32_t r4);

/* 0x62ABC — dispatch the DTC's mode byte to the run-sum update leaf */
void rx8_can_encode_handler_62abc(uint32_t dtc, uint32_t r5)
{
    uint8_t mode = *(volatile uint8_t *)(uintptr_t)
                   (RX8_MODE_TABLE + ((dtc & 0xFFFFu) << 1));
    uint8_t vl   = (uint8_t)(r5 & 0xFFu);
    int call = 0;

    switch (mode) {
    case 0x00u:                          /* mode 0: unconditional fold         */
        call = 1;
        break;
    case 0x10u:                          /* mode 0x10: fold iff vl==0x20||0x11  */
        call = (vl == 0x20u || vl == 0x11u);
        break;
    case 0x11u:                          /* mode 0x11: fold iff vl==0x20 only   */
        call = (vl == 0x20u);
        break;
    case 0x20u:                          /* explicit no-op path (0x62AE4)       */
    default:                             /* any other mode value: no call       */
        call = 0;
        break;
    }

    if (call)
        obd_service_handler_648B4(r5);
}
