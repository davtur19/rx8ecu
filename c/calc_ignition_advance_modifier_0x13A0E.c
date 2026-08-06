/* calc_ignition_advance_modifier_0x13A0E.c
 *
 * ROM: 60E1D400 | Address: 0x13A0E | Size: 0x50 (80) bytes per CSV range
 * 0x13A0E..0x13A5E.  Code ends at the `rts` @0x13A5A (delay nop @0x13A5C);
 * the literal pool sits @0x13AA8..0x13AE4 (mov.w/mov.l PC-relative loads).
 * The next function calc_rotor_sync_base_A (0x13A5E) starts at the CSV end.
 *
 * Entry  : 0x13A0E — matches the symbols CSV row (0x013A0E,0x013A5E).  Valid
 *           entry (starts straight with the first load, no incoming branches
 *           into the middle; the preceding function calc_rotor_sync_base_B
 *           ends with `rts` @0x13A0A so there is no fall-through into us).
 *           Called via the function-pointer dispatch slot @0x14794 of the
 *           engineControlCalculateTiming dispatcher (0x14584) — dispatch
 *           phase 1, immediately before calc_rotor_sync_base_A (0x14798),
 *           getKnockControlActive (0x1479C), updateKnockMaxRAM (0x147A0) and
 *           calc_ignition_all_rotors (0x147A4).  The CSV address IS the real
 *           entry point.
 *
 * Range  : 0x13A0E .. 0x13A5E
 *
 * Literal pool (values verified against roms/stock/60E1D400.bin):
 *   0x13AB0 0xB5B8        (mov.w -> f32 @0xFFFFB5B8, loaded in delay slot)
 *   0x13ACC 0xFFFFA748    (mov.l -> u8 output flag @0xFFFFA748)
 *   0x13AD0 0x0007A172    (mov.l -> u8 ROM hard-disable gate)
 *   0x13AB2 0xA424        (mov.w -> u16 @0xFFFFA424)
 *   0x13AD4 0x0007983C    (mov.l -> u16 ROM threshold)
 *   0x13AD8 0x00079840    (mov.l -> f32 ROM constant A)
 *   0x13AB4 0xAA10        (mov.w -> f32 @0xFFFFAA10)
 *   0x13ADC 0x00079844    (mov.l -> f32 ROM constant B)
 *   0x13AB6 0xC12C        (mov.w -> f32 @0xFFFFC12C)
 *   0x13AE0 0x00079848    (mov.l -> f32 ROM constant C)
 *
 * Semantics (instruction-for-instruction, see disasm): compute the ignition
 * advance modifier enable flag u8@0xFFFFA748:
 *   1. gate: if u8@0x0007A172 != 0 -> flag = 0 (hard disable).
 *   2. else if (u32)(s16)u16@0xFFFFA424 < (u32)(s16)u16@0x0007983C
 *        (cmp/hs, unsigned on sign-extended mov.w values) -> flag = 0.
 *   3. else if f32@0x00079840 > f32@0xFFFFAA10            -> flag = 0.
 *   4. else if f32@0x00079844 > f32@0xFFFFC12C            -> flag = 0.
 *   5. else if !(f32@0x00079848 > f32@0xFFFFB5B8)         -> flag = 0.
 *   6. else -> flag = 1.
 * The flag A748 is one of the two gate inputs of getKnockControlActive
 * (0x13A86, which ANDs A748 and A749 into A740).
 *
 * No stack frame, no sub-calls; only the u8@A748 store is a RAM side effect.
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py) in
 * c/tests/test_calc_ignition_advance_modifier_0x13A0E.py — 0 mismatches over
 * 5 seeds x 100000 iterations (byte-exact full post-call RAM overlay + r0).
 */
#include <stdint.h>

/* ---- RAM globals (mov.w sign-extends to 0xFFFFxxxx) ---- */
#define OUT_A748   (*(volatile uint8_t *)0xFFFFA748)  /* u8 enable flag output */
#define RAM_A424   (*(volatile uint16_t*)0xFFFFA424)  /* u16 compare input     */
#define RAM_AA10   (*(volatile float   *)0xFFFFAA10)  /* f32 compare input     */
#define RAM_C12C   (*(volatile float   *)0xFFFFC12C)  /* f32 compare input     */
#define RAM_B5B8   (*(volatile float   *)0xFFFFB5B8)  /* f32 compare input     */

/* ROM constants (mov.l/mov.w PC-relative; mov.w values sign-extended) */
#define ROM_GATE   (*(volatile uint8_t *)0x0007A172)  /* u8 hard-disable gate  */
#define ROM_THR    (*(volatile uint16_t*)0x0007983C)  /* u16 threshold         */
#define ROM_CA     (*(volatile float   *)0x00079840)  /* f32 const A           */
#define ROM_CB     (*(volatile float   *)0x00079844)  /* f32 const B           */
#define ROM_CC     (*(volatile float   *)0x00079848)  /* f32 const C           */

void calc_ignition_advance_modifier_0x13A0E(void)
{
    uint8_t out = 0;

    /* 0x13A14..0x13A18: tst r2,r2 ; bf/s 0x13A56 (r2 = s8 @0x7A172) */
    if ((int8_t)ROM_GATE == 0) {
        /* 0x13A1C..0x13A26: cmp/hs r3,r2 (unsigned on sign-extended mov.w) */
        uint32_t r2 = (uint32_t)(int32_t)(int16_t)RAM_A424;
        uint32_t r3 = (uint32_t)(int32_t)(int16_t)ROM_THR;
        if (r2 >= r3) {
            /* 0x13A2A..0x13A34: fcmp/gt fr2,fr3 -> T = (fr3 > fr2) */
            if (!(ROM_CA > RAM_AA10)) {
                /* 0x13A38..0x13A42: fcmp/gt fr0,fr1 -> T = (fr1 > fr0) */
                if (!(ROM_CB > RAM_C12C)) {
                    /* 0x13A46..0x13A4C: fcmp/gt fr4,fr3 -> T = (fr3 > fr4) */
                    if (ROM_CC > RAM_B5B8)
                        out = 1;    /* 0x13A50..0x13A54: A748 = 1 */
                }
            }
        }
    }

    OUT_A748 = out;                 /* 0x13A56..0x13A58: A748 = 0 (or bra delay) */
}