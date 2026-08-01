/*
 * =============================================================================
 * rx8_get_hcan_register_address.c  —  HCAN REGISTER BLOCK ADDRESS CALCULATOR
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0xD198
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_get_hcan_register_address.py
 *               (host-gcc vs tools/sh2emu.py over 20000 random + edge vectors;
 *               0 mismatches).
 * Lift (truth): c/getHCANRegisterAddress.c  (getHCANRegisterAddress @ 0xD198)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * A tiny pure-arithmetic leaf consulted all over the HCAN init path (callers:
 * can_set_mailbox_mode_dlc @0xCDC4, can_set_mailbox_ptr_control @0xCDFA and
 * the canSetup chain) to turn a channel/mailbox index into the base address of
 * that channel's register bank in the SH7055 on-chip CAN controller.  Given a
 * channel index in r4 and a register-block base in r5 it returns either the
 * base (channel 0) or base + 0x0200 (every other channel).  0x0200 is the
 * per-channel register-bank stride of the HCAN block.  Disassembly of
 * 60E1D400.bin @ 0xD198:
 *
 *     644C   extu.b r4,r4          ; idx = r4 & 0xFF
 *     2448   tst    r4,r4          ; T = (idx == 0)
 *     8F02   bf/s   .nonzero       ;   idx != 0 -> base + 0x200
 *     0009   nop                   ;   (delay)
 *     A002   bra    .ret           ;   idx == 0 -> base
 *     6453   mov    r5,r4          ;   (delay) r4 = base
 * .nonzero:
 *     9409   mov.w  @(0x12,pc),r4  ; r4 = 0x0200  (literal pool @0xD1BA)
 *     345C   add    r5,r4          ; r4 = base + 0x200
 * .ret:
 *     000B   rts
 *     6043   mov    r4,r0          ;   (delay) r0 = result
 *
 * The 0x0200 literal is fetched PC-relative from the literal pool at 0xD1BA
 * (which sits between this function and can_get_mailbox_config @0xD1AC), so
 * the function body is exactly the 20 bytes 0xD198..0xD1AB.
 *
 * CALLING CONVENTION
 * ------------------
 * Entry is the normal ABI: r4 = channel index (masked to 8 bits by the very
 * first `extu.b`), r5 = register-block base; result returned in r0.  So the
 * reconstructed signature is (idx, base) in THAT order, matching the ROM's
 * r4/r5 register order.
 *
 * DISCREPANCY vs THE LIFT (documented)
 * ------------------------------------
 * c/getHCANRegisterAddress.c declares `getHCANRegisterAddress(uint32_t base,
 * uint8_t idx)` — the two parameters are swapped relative to the ROM's ABI
 * order (r4 = idx, r5 = base).  The behaviour is identical either way; only
 * the argument order differs.  The reconstruction below keeps the ROM's
 * register order (idx first, base second) so that a caller written against
 * the SH-2E ABI (r4/r5) maps 1:1 onto it.
 *
 * Semantics verbatim from c/getHCANRegisterAddress.c (re-verified against the
 * 60E1D400.bin bytes here):
 *   idx == 0            -> base
 *   idx != 0            -> base + 0x0200
 * The `extu.b r4,r4` masks the index to 8 bits first; `uint8_t idx` performs
 * the identical truncation.  base + 0x0200 wraps through 32-bit arithmetic,
 * exactly like the ROM's `add r5,r4` (e.g. base = 0xFFFFFFFF -> 0x000001FF).
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

/* 0xD198 — return the HCAN register-bank address for channel `idx` at `base`. */
uint32_t rx8_get_hcan_register_address(uint8_t idx, uint32_t base)
{
    return (idx == 0) ? base : base + 0x200u;
}
