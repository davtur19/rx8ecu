/*
 * =============================================================================
 * rx8_purge_state_query.c  —  EVAP PURGE FLOW-STATE QUERY
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0xF5DC
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_purge_state_query.py
 *               (host-gcc vs tools/sh2emu.py over edge + random state bytes),
 *               in addition to the existing emulator test
 *               c/tests/test_purge_subsystem.py (exhaustive 0..255, 0
 *               mismatches).
 * Lift (truth): c/purge_state_query.c  (same address; symbol
 *               `purge_state_query`, IDA-ai, 6-byte leaf).
 *
 * WHAT THIS IS
 * ------------
 * EVAP purge flow-state query.  Returns the current purge flow state byte,
 * RAM[0xFFFFA4B1] — the value produced by purge_control_state_update()
 * @0xF544 and consumed by purge_flow_decrement() @0xF5B4 and the OBD
 * purge-monitor path.  The ROM leaf is exactly 6 bytes: a pc-relative
 * `mov.l @lit,r3` that loads the 32-bit pointer 0xFFFFA4B1, followed by
 * `rts` whose delay slot (`mov.b @r3,r0`) sign-extends the byte into r0.
 * It is a pure read: no arguments, no side effects.
 *
 * NOTE ON SIGN-EXTENSION (matches the ROM): the SH-2 `mov.b @Rm,Rn` is a
 * sign-extending load, so r0 comes back 0xFFFFFF80..0xFFFFFFFF for state
 * bytes 0x80..0xFF.  Callers of this query always consume the low byte (the
 * value is an unsigned u8), which is exactly what the uint8_t return below
 * models.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

/* Purge flow-state byte, written by purge_control_state_update() @0xF544.
 * Documented in the EVAP purge subsystem lifts (c/purge_state_query.c,
 * c/purge_control_state_update.c, c/purge_flow_counter_init.c) and the
 * subsystem test c/tests/test_purge_subsystem.py.  Kept here as an explicit
 * pointer (rx8_hw.h is not extended — not yet in the project's documented
 * address table). */
#define RX8_RAM_PURGE_FLOW_STATE (*(volatile uint8_t *)0xFFFFA4B1u)

uint8_t rx8_purge_state_query(void)
{
    return RX8_RAM_PURGE_FLOW_STATE;
}
