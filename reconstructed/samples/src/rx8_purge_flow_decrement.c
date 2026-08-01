/*
 * =============================================================================
 * rx8_purge_flow_decrement.c  —  EVAP PURGE-FLOW COUNTDOWN
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0xF5B4  (size 40 bytes; next leaf @0xF5DC)
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_purge_flow_decrement.py
 *               (host-gcc + mmap vs tools/sh2emu.py over random and edge
 *               pre-states), in addition to the existing emulator test
 *               c/tests/test_purge_subsystem.py (5000 random + edges, 0 fails).
 * Lift (truth): c/purge_flow_decrement.c  (same address, same behaviour;
 *               symbol `purge_flow_decrement` also present in
 *               symbols/symbols_60E1D400_merged.csv, source ida-ai).
 *
 * WHAT THIS IS
 * ------------
 * Periodic countdown of the EVAP (canister-purge) flow timer.  Called once per
 * scheduling tick while purge is enabled:
 *
 *     if (RX8_PURGE_DEC_EN == 1)      latch already armed:
 *         if (RX8_PURGE_FLOW > 0)      countdown not exhausted
 *             RX8_PURGE_FLOW--         one tick less
 *     else
 *         RX8_PURGE_DEC_EN = 1         first call: arm the countdown
 *
 * The first invocation only arms the latch (DEC_EN = 1); the FLOW counter is
 * decremented from the second invocation onward until it reaches 0.  DEC_EN is
 * a one-shot "armed" flag, FLOW is the remaining purge-flow countdown value.
 * The counter is published by purge_control_state_update @0xF544 and zeroed by
 * purge_flow_counter_init @0xF534 (see c/purge_control_state_update.c).
 *
 * ROM NOTES (match the lift verbatim)
 * -----------------------------------
 * - FLOW is read with `mov.b` + `extu.b` and tested with `cmp/pl` (a SIGNED
 *   > 0 test on the 0..255 value): any nonzero byte counts as "> 0", so the
 *   counter counts down to exactly 0 and never wraps past it.
 * - DEC_EN is tested with `cmp/eq #1`; any value other than 1 (including
 *   stale/non-canonical bytes) is treated as "not armed" and re-arms.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"
#include "rx8_hw.h"

/* Purge-flow cell group in the on-chip RAM window.  The ROM reaches FLOW
 * through the sign-extended 16-bit literal 0xA4B0 (pool @0xF5E2) and DEC_EN
 * through the 32-bit literal 0xFFFFA4B2 (pool @0xF5EC); on the SH-2 both
 * aliases resolve to the same physical bytes as the 0xFFFFxxxx forms below. */
#define RX8_PURGE_FLOW_ADDR    0xFFFFA4B0u   /* u8 remaining purge-flow ticks */
#define RX8_PURGE_DEC_EN_ADDR  0xFFFFA4B2u   /* u8 countdown "armed" latch    */

/* 0xF5B4 — count down the purge flow timer, arming the latch on first call. */
void rx8_purge_flow_decrement(void)
{
    if (RX8_IO8(RX8_PURGE_DEC_EN_ADDR) == 1u) {
        if (RX8_IO8(RX8_PURGE_FLOW_ADDR) > 0u)
            RX8_IO8(RX8_PURGE_FLOW_ADDR) -= 1u;
    } else {
        RX8_IO8(RX8_PURGE_DEC_EN_ADDR) = 1u;
    }
}
