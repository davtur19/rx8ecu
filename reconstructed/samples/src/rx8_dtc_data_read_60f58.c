/*
 * =============================================================================
 * rx8_dtc_data_read_60f58.c  —  DTC STATUS REGION FILL ("RESET DTC DATA")
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x60F58  (16 bytes: 0x60F58..0x60F67)
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_dtc_data_read_60f58.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + random
 *               pre-states, RAM bytes compared byte-for-byte).
 * Lift (truth): c/dtc_data_read_60F58.c  (same address and intent) — BUT the
 *               lift's loop is NOT byte-exact.  The lift fills FOUR uint16
 *               (0xFFFFD6C8..0xFFFFD6CF, 8 bytes) while the ROM fills only
 *               TWO uint16 with a 4-byte stride: 0xFFFFD6C8 and 0xFFFFD6CC
 *               (4 bytes).  The halfwords in between (0xFFFFD6CA,
 *               0xFFFFD6CE) are never written.  This reconstruction follows
 *               the ROM bytes, verified with the emulator (see below).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The OBD DTC machinery keeps a 2×uint16 "status" window in on-chip RAM
 * (0xFFFFD6C8, 0xFFFFD6CC).  This leaf is a "Reset DTC Data" operation:
 * writing 0xFFFF to every status halfword marks all DTC entries as
 * "completed/cleared".  The ROM sequence (disasm_sh2e.py 0x60F58):
 *
 *     mov.l  @(0x1C,pc),r7  ; r7 = 0xFFFFD6C8   (base)
 *     mov    r7,r4
 *     mov.l  @(0x1C,pc),r5  ; r5 = 0x0000FFFF   (fill value)
 *     mov    r7,r6
 *     add    #0x08,r6       ; r6 = base + 8     (loop bound)
 * loop:
 *     mov.w  r5,@r4         ; *(u16*)r4 = 0xFFFF
 *     add    #0x04,r4       ; r4 += 4  (TWO halfwords — stride 4, NOT 2)
 *     cmp/hs r6,r4          ; T = (r4 >= r6)
 *     bf/s   loop           ; while (r4 < r6)
 *     nop
 *     rts
 *     nop
 *
 * The bound is base+8 and the step is 4 bytes, so the loop body runs exactly
 * twice: stores at base and base+4.  The odd halfwords (base+2, base+6) are
 * NOT part of the store set — a genuine quirk of the ROM (the lift's "4 ×
 * uint16" comment notwithstanding).  Empirically confirmed in sh2emu.py: with
 * a 0x5A-seeded 24-byte overlay only 0xFFFFD6C8/0xFFFFD6CC become 0xFFFF,
 * all other bytes keep their pre-state.
 *
 * NOTE on the 0xFFFFD6CA/0xFFFFD6CE pair: this function is the only writer of
 * the window found so far, so those two halfwords are simply left at their
 * pre-state — they are not reset by this code path.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

/* DTC status window in on-chip RAM.  Not yet in rx8_hw.h (no FINDINGS.md
 * entry for it); role: *unknown, matches ROM* (lift c/dtc_data_read_60F58.c). */
#define RX8_DTC_STATUS_BASE  0xFFFFD6C8u

/* 0x60F58 — write 0xFFFF to the two status halfwords of the 8-byte DTC window
 * (base and base+4).  The two odd halfwords inside the window are untouched:
 * the ROM's `add #0x04,r4` walks the pointer in 4-byte steps. */
void rx8_dtc_data_read_60f58(void)
{
    volatile uint16_t *p   = (volatile uint16_t *)RX8_DTC_STATUS_BASE;
    volatile uint16_t *end = (volatile uint16_t *)(RX8_DTC_STATUS_BASE + 8u);
    do {
        *p = 0xFFFFu;
        p += 2;                       /* `add #0x04,r4` — 4-byte stride */
    } while ((uintptr_t)p < (uintptr_t)end);
}
