/*
 * =============================================================================
 * rx8_purge_flow_counter_init.c  —  EVAP PURGE-FLOW COUNTER INITIALIZATION
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0xF534  (16 bytes: 0xF534..0xF543)
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_purge_flow_counter_init.py
 *               (host-gcc + mmap vs tools/sh2emu.py over random pre-states),
 *               in addition to the existing emulator entry
 *               c/tests/test_purge_subsystem.py (test_counter_init).
 * Lift (truth): c/purge_flow_counter_init.c  (same address and semantics;
 *               IDA-ai names the leaf `purge_flow_counter_init` and the
 *               purge-subsystem test calls it from 0xF5B4 / 0xF544).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The EVAP purge subsystem keeps a three-byte "purge-flow counter" state cell
 * in on-chip RAM.  This leaf is the startup / purge-disable reset: it writes
 * zero to all three bytes unconditionally — no arguments, no branches, no
 * return value.  The ROM sequence is:
 *
 *     mov.w  @(0xF5E2,pc),r3  ; r3 = 0xA4B0   (16-bit literal, sign-extended
 *                                            ;  -> 0xFFFFA4B0; on-chip RAM is
 *                                            ;  aliased so both forms match)
 *     mov    #0,r4
 *     mov.l  @(0xF5E8,pc),r2  ; r2 = 0xFFFFA4B1
 *     mov.b  r4,@r3           ; flow countdown counter = 0
 *     mov.b  r4,@r2           ; flow state / target   = 0
 *     mov.l  @(0xF5EC,pc),r1  ; r1 = 0xFFFFA4B2
 *     rts
 *     mov.b  r4,@r1           ; decrement enable      = 0   (delay slot)
 *
 * The three addresses have no rx8_hw.h entries yet (not in the project
 * notes); the roles below come from the verified lift c/purge_flow_counter_init.c
 * and are annotated *unknown, matches ROM* accordingly.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"
#include "rx8_hw.h"

/* EVAP purge-flow counter cell — three contiguous bytes in on-chip RAM.
 * Addressed in the ROM through the truncated 16-bit literal 0xA4B0
 * (sign-extended to 0xFFFFA4B0); the other two bytes use full 32-bit
 * pointers.  Roles: *unknown, matches ROM* (lift c/purge_flow_counter_init.c).
 */
#define RX8_PURGE_FLOW_ADDR        0xFFFFA4B0u  /* purge flow countdown (u8)  */
#define RX8_PURGE_FLOW_STATE_ADDR  0xFFFFA4B1u  /* purge flow state (u8)      */
#define RX8_PURGE_DEC_EN_ADDR      0xFFFFA4B2u  /* purge decrement enable (u8) */

/* 0xF534 — zero the three-byte purge-flow cell (startup / purge-disable). */
void rx8_purge_flow_counter_init(void)
{
    RX8_IO8(RX8_PURGE_FLOW_ADDR)       = 0u;
    RX8_IO8(RX8_PURGE_FLOW_STATE_ADDR) = 0u;
    RX8_IO8(RX8_PURGE_DEC_EN_ADDR)     = 0u;
}
