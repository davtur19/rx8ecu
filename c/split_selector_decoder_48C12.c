/* split_selector_decoder_48C12.c
 *
 * ROM: 60E1D400  |  Address: 0x48C12  |  Size: 0x30 bytes (48 B)
 *       0x48C12..0x48C40 code (rts @0x48C3E, delay-slot nop); literals shared
 *       with the next function FUN_0x48C42 @0x48C68/0x48C6A/0x48C6C.
 *       VERIFIED vs ROM emulator (0 mismatches, 500000 random inputs).
 *
 * Decodes the gated split-selector byte u8@0xFFFFCCD2 (produced by
 * split_selector_state_ctrl_487DC, stock 0..3) into a 2-bit output pair
 * (u8@0xFFFFCCE2, u8@0xFFFFCCE3):
 *
 *       CCD2 == 0   -> CCE2 = 0, CCE3 = 0   (both modes off)
 *       CCD2 == 1   -> CCE2 = 0, CCE3 = 1   (trailing mode only)
 *       CCD2 >= 2   -> CCE2 = 1, CCE3 = 0   (leading mode only)
 *
 * I.e. a pure 2-bit decoder (bit1 -> CCE2, bit0 -> CCE3) with state 3
 * clamped to the state-2 encoding.  CCE2 is consumed as a byte "== 1" gate by
 * ev_torque_smooth_48F98 (0x48F98), maf_sensor_correction_24234 (0x24234) and
 * can_filter_apply_49216 (0x49216); CCE3 has no other direct literal consumer
 * in this ROM (searched all even-aligned 0xCCE3 words).  CCE2/CCE3 are in the
 * 0xFFFFCCEx spark-control status block (u8@0xFFFFCCE1 is read by
 * rotor_sync_gate_state_ctrl_2100A).  This routine does NOT touch A734/A738.
 *
 * Inputs  (RAM reads):  u8 @0xFFFFCCD2  (state selector, 0..3)
 * Outputs (RAM writes): u8 @0xFFFFCCE2  (mode-enable A / "leading")
 *                        u8 @0xFFFFCCE3  (mode-enable B / "trailing")
 *
 * Verified: 100000 random inputs x 5 seeds (500000 total) vs the ROM emulator,
 * 0 mismatches (c/tests/test_split_selector_decoder_48C12.py).
 */
#include <stdint.h>

#define RAM_CCD2      (*(volatile uint8_t *)0xFFFFCCD2)   /* selector byte */
#define RAM_CCE2      (*(volatile uint8_t *)0xFFFFCCE2)   /* output mode A */
#define RAM_CCE3      (*(volatile uint8_t *)0xFFFFCCE3)   /* output mode B */

void split_selector_decoder_48C12(void)
{
    uint8_t s = RAM_CCD2;

    if (s == 0) {
        RAM_CCE2 = 0;                                   /* 0x48C1C..0x48C26 */
        RAM_CCE3 = 0;
    } else if (s == 1) {
        RAM_CCE2 = 0;                                   /* 0x48C28..0x48C36 */
        RAM_CCE3 = 1;
    } else {
        RAM_CCE2 = 1;                                   /* 0x48C38..0x48C3C */
        RAM_CCE3 = 0;
    }
}
