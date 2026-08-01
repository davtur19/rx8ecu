/*
 * =============================================================================
 * rx8_crank_sensor_init.c  —  CRANKSHAFT SENSOR STATE INITIALISATION
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x7C30  (36 bytes: 0x7C30..0x7C52)
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_crank_sensor_init.py
 *               (host-gcc + mmap vs tools/sh2emu.py over random + edge
 *               pre-states; bit-exact RAM side effects incl. the tail-call
 *               boundary; the harness pins the branch target 0x0768C and its
 *               r4 = 0 argument).
 * Lift (truth): c/crankSensorInit.c  (crankSensorInit @ 0x007C30, 36 bytes)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Crankshaft sensor state initialisation run during crank-system init: the two
 * sensor control registers are forced to a known idle state (clear A, all-bits
 * mask B), and if the engine is already marked running (post-init reset) the
 * firmware immediately hands over to the crank-mode state machine.  The ROM
 * sequence (60E1D400.bin @ 0x7C30) is:
 *
 *     D114  mov.l @(0x14,pc),r1   ; r1 = 0xFFFF9FC9  (sensor control reg A)
 *     E200  mov   #0x00,r2        ; r2 = 0
 *     9310  mov.w @(0x10,pc),r3   ; r3 = 0x00FF
 *     2120  mov.b r2,@r1          ; *0xFFFF9FC9 = 0x00   (BYTE store)
 *     D013  mov.l @(0x13,pc),r0   ; r0 = 0xFFFF9FCA  (sensor control reg B)
 *     2030  mov.b r3,@r0          ; *0xFFFF9FCA = 0xFF   (BYTE store)
 *     D40D  mov.l @(0x0D,pc),r4   ; r4 = 0xFFFF9F96  (engine-running flag)
 *     6040  mov.b @r4,r0          ; r0 = (int8) flag      (sign-extend)
 *     600C  extu.b r0,r0          ; r0 = (uint8) flag     (zero-extend)
 *     8801  cmp/eq #0x01,r0       ; T = (flag == 1)
 *     8F04  bf/s  0x7C50          ; flag != 1 -> return (rts)
 *     0009  nop
 *     E200  mov   #0x00,r2
 *     2420  mov.b r2,@r4          ; *flag = 0             (clear the flag)
 *     AD1E  bra   0x0768C         ; tail-call crank_mode_switch
 *     6423  mov   r2,r4           ;   (delay slot) r4 = 0 (argument!)
 *     7C50: 000B  rts             ; flag != 1 path
 *           0009  nop             ;   (delay slot)
 *
 * TAIL-CALL SUBTLETY (verified against the ROM — the one nuance not made
 * explicit by the lift):
 *   The running-flag branch is a `bra` (unconditional tail call), NOT a
 *   `jsr`/`bsr` — PR is never pushed, so crank_mode_switch (0x0768C) runs as
 *   if it had been called directly from crankSensorInit's caller.  Its first
 *   parameter arrives in r4, and the delay-slot `mov r2,r4` (r2 == 0, the
 *   value just written to the flag) means the tail call always carries r4 = 0.
 *   Disassembling 0x0768C:  r4 == 1 -> bsr 0x07FD4, r4 != 1 -> bsr 0x07C00,
 *   so this init function always takes the 0x07C00 path (crank state: write
 *   0xFF to sensor control reg C @0xFFFF9FC6).  The lift's plain
 *   `crank_mode_switch()` call is the correct host model; the harness pins
 *   both the branch target and the r4 = 0 argument by stopping the emulator
 *   at 0x0768C (see harness_crank_sensor_init.py) and checks them against the
 *   oracle's tail-call marker.
 *
 * STORE WIDTH: both control-register writes are `mov.b` (byte) — 0xFFFF9FC9
 * and 0xFFFF9FCA are 8-bit cells, and the flag clear at 0xFFFF9F96 is a byte
 * store that leaves the neighbour 0xFFFF9F97 untouched (sentinel-pinned by
 * the harness).
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"
#include "rx8_hw.h"

/* Sensor control register A (idle clear).  Role: *unknown, matches ROM*
 * (c/crankSensorInit.c; sibling control reg C @0xFFFF9FC6 is written by the
 * tail-called crank_mode_switch @0x0768C). */
#define RX8_CRANK_CTRL_A       0xFFFF9FC9u
/* Sensor control register B (all-bits-set mask).  Role: *unknown, matches ROM*. */
#define RX8_CRANK_CTRL_B       0xFFFF9FCAu
/* Engine-running flag — when == 1 a post-init reset is assumed and the
 * firmware jumps straight into the crank-mode state machine. */
#define RX8_ENGINE_RUNNING_FLAG 0xFFFF9F96u

/* Tail-called crank-mode state machine at 0x0768C (see header: entered with
 * r4 = 0, PR untouched).  Defined by the test rig on the host; on the target
 * it is this very ROM function. */
extern void rx8_crank_mode_switch(void);

/* 0x7C30 — initialise the crankshaft sensor state registers. */
void rx8_crank_sensor_init(void)
{
    RX8_IO8(RX8_CRANK_CTRL_A) = 0x00u;
    RX8_IO8(RX8_CRANK_CTRL_B) = 0xFFu;

    if (RX8_IO8(RX8_ENGINE_RUNNING_FLAG) == 0x01u) {
        RX8_IO8(RX8_ENGINE_RUNNING_FLAG) = 0x00u;
        rx8_crank_mode_switch();        /* ROM: `bra 0x0768C` with r4 = 0 */
    }
}
