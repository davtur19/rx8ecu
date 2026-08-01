/*
 * =============================================================================
 * rx8_purge_control_state_update.c  —  EVAP PURGE-CONTROL STATE UPDATE
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0xF544  (size 112 bytes; next leaf purge_flow_decrement @0xF5B4)
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_purge_control_state_update.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + random
 *               pre-states; RAM side-effects compared byte-for-byte), in
 *               addition to the existing emulator test
 *               c/tests/test_purge_subsystem.py (10000 random + exhaustive
 *               demand/trigger combos, 0 failures).
 * Lift (truth): c/purge_control_state_update.c  (same address, same
 *               behaviour; the ground truth for this port).
 *
 * WHAT THIS IS
 * ------------
 * EVAP purge-control state update, called from the periodic task layer.  It
 * reads the purge enable/trigger byte and, depending on it and on the purge
 * "flow demand" byte, picks a small calibration value to publish into the
 * purge-flow counter that purge_flow_decrement() @0xF5B4 counts down.
 *
 * ROM path (60E1D400.bin @0xF544):
 *
 *     sts.l  pr,@-r15                 ; save return address
 *     mov.l  @lit,r3 ; jsr @r3        ; leaf 0x104C8: r0 = RAM[0xFFFFBED0]
 *     mov    r0,r5 ; extu.b r5,r0     ; v = trigger & 0xFF
 *     mov.b  @r3,r2 ; mov.b r2,@r6    ; RAM[0xFFFFA4B3] = RAM[0xFFFF9F94]
 *                                      ;   (latch flow demand, UNCONDITIONAL)
 *     cmp/eq #1,r0 ; bf/s else        ; if (v == 1):
 *       mov.b @r6,r5 ; extu.b r5,r5   ;   t = RAM[0xFFFFA4B3]
 *       cmp/gt thr_low,t ; bt next    ;   if (t <= ROM[0x792FC])  out=ROM[0x792FE]
 *       cmp/gt thr_hi,t  ; bt hi      ;   else if (t <= ROM[0x792FD]) out=ROM[0x792FF]
 *       ...                           ;   else out = ROM[0x79300]
 *     else:                           ; else:
 *       cmp/eq #1,RAM[0xFFFFCE6E]     ;   out = (RAM[0xFFFFCE6E] == 1)
 *                                      ;           ? ROM[0x79301] : 0
 *     mov.b  @state,r3 ; mov.b r3,@r2 ; RAM[0xFFFFA4B0] = RAM[0xFFFFA4B1]
 *     lds.l  @r15+,pr ; rts           ;   (store sits in the rts delay slot)
 *
 * The 6 calibration bytes at 0x792FC..0x79301 in the stock bin are
 * `04 0A 01 00 00 00`: thresholds 4/10, outputs 1/0/0/0 — i.e. demand
 * <= 4 selects purge flow 1, anything above selects 0.  On the host the
 * oracle maps that ROM page and seeds the real bytes, so the reconstructed
 * function reads them through the very same addresses the ROM uses.
 *
 * NOTE ON THE TRIGGER READ: the ROM performs it through a `jsr` to the leaf
 * @0x104C8 (`mov.w @lit,r3` -> 0xFFFFBED0; `rts` with `mov.b @r3,r0` in the
 * delay slot), then `extu.b`s the byte in the caller.  Behaviourally that is
 * identical to a direct 8-bit read of RAM[0xFFFFBED0], which is what this
 * port models (the emulator test runs the real jsr).
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"
#include "rx8_hw.h"

/* Purge-cell group in the on-chip RAM window (0xFFFF6000..0xFFFFDFFF),
 * documented in the purge-subsystem lifts (c/purge_control_state_update.c,
 * c/purge_state_query.c, c/purge_flow_decrement.c) and c/tests/test_purge_subsystem.py. */
#define RX8_PURGE_FLOW_ADDR     0xFFFFA4B0u  /* u8 purge-flow counter (published) */
#define RX8_PURGE_STATE_ADDR    0xFFFFA4B1u  /* u8 selected purge-flow state      */
#define RX8_PURGE_DEMAND_ADDR   0xFFFFA4B3u  /* u8 latched flow demand            */
#define RX8_FLOW_DEMAND_ADDR    0xFFFF9F94u  /* u8 purge flow demand input        */
#define RX8_ALT_TRIGGER_ADDR    0xFFFFCE6Eu  /* u8 alternate purge trigger input  */
#define RX8_PURGE_TRIGGER_ADDR  0xFFFFBED0u  /* u8 purge trigger (leaf @0x104C8)  */

/* Calibration table the ROM reads at 0x792FC..0x79301 (stock: 04 0A 01 00 00 00).
 * The oracle maps the page and seeds the real ROM bytes, so these pointers
 * stay live on the host exactly as they are on the target. */
#define ROM_THR_LOW   (*(const uint8_t *)0x000792FCu)   /* 4  */
#define ROM_THR_HIGH  (*(const uint8_t *)0x000792FDu)   /* 10 */
#define ROM_OUT_LOW   (*(const uint8_t *)0x000792FEu)   /* 1  */
#define ROM_OUT_MID   (*(const uint8_t *)0x000792FFu)   /* 0  */
#define ROM_OUT_HIGH  (*(const uint8_t *)0x00079300u)   /* 0  */
#define ROM_OUT_ALT   (*(const uint8_t *)0x00079301u)   /* 0  */

/* 0xF544 — select the purge flow target byte from the trigger + demand. */
void rx8_purge_control_state_update(void)
{
    uint8_t v = RX8_IO8(RX8_PURGE_TRIGGER_ADDR);   /* leaf 0x104C8 -> RAM[0xBED0] */
    uint8_t t, out;

    /* Latch the flow-demand byte before the branch — the ROM does this
     * unconditionally (0xF558-0xF55A). */
    RX8_IO8(RX8_PURGE_DEMAND_ADDR) = RX8_IO8(RX8_FLOW_DEMAND_ADDR);

    if (v == 1u) {
        t = RX8_IO8(RX8_PURGE_DEMAND_ADDR);
        if (t <= ROM_THR_LOW)       out = ROM_OUT_LOW;    /* <= 4  -> 1 */
        else if (t <= ROM_THR_HIGH) out = ROM_OUT_MID;    /* <= 10 -> 0 */
        else                        out = ROM_OUT_HIGH;   /* > 10  -> 0 */
        RX8_IO8(RX8_PURGE_STATE_ADDR) = out;
    } else {
        /* Trigger off: only the alternate trigger arms a nonzero target. */
        RX8_IO8(RX8_PURGE_STATE_ADDR) =
            (RX8_IO8(RX8_ALT_TRIGGER_ADDR) == 1u) ? ROM_OUT_ALT : 0u;
    }

    /* Publish the state byte to the flow counter that purge_flow_decrement()
     * @0xF5B4 counts down (store in the rts delay slot, 0xF5AA-0xF5B2). */
    RX8_IO8(RX8_PURGE_FLOW_ADDR) = RX8_IO8(RX8_PURGE_STATE_ADDR);
}
