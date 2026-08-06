/* coil_output_dispatcher_0x110A8.c
 *
 * ROM: 60E1D400 | Address: 0x110A8 | Size: 0x72 (114) bytes, 57 instrs.
 *
 * Function B of the "coil output dispatcher" family.
 *   Entry  : 0x110A8      (0x11010 is NOT a function start -- it is the
 *                          mid-prologue of the sibling function A that begins
 *                          at 0x10FF0; there are no code references to
 *                          0x11010 in the ROM.  This lift is therefore keyed to
 *                          the real dispatcher entry 0x110A8 which is pointed
 *                          to by the function-pointer table element @0x4ED58.)
 *   Range  : 0x110A8 .. 0x1111A  (rts + delay at the end)
 *   Literal: 0x1111C = 0x00B4 (180), 0x11130 -> 0x11218, 0x11134 -> 0x1120A,
 *            0x11138 -> 0xFFFF9F88, 0x1113C -> 0x2158
 *
 * Gate function over a pair of ignition-channel descriptors.  The caller
 * supplies a pointer (r4) to a channel table and a signed 32-bit "limit"
 * (r5).  The function walks the two descriptors (16-byte stride) and returns
 * 1 only if EVERY channel satisfies both bounds; otherwise it returns 0 as
 * soon as any channel fails.
 *
 * Dispatch site 0x110D8..0x110DC is the "dw = returnDwellTime_fp(0x1120A) +
 * output_per_rotor_ignition_dwell(0x11218)" pattern described in
 * c/output_per_rotor_ignition_dwell_0x11218.c.
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py) in
 * c/tests/test_coil_output_dispatcher_0x110A8.py -- 0 mismatches over 5 seeds
 * x default iterations (signed 32-bit comparisons throughout).
 */

#include <stdint.h>

#define IGN_DWELL_SCALE  (*(volatile uint32_t *)0xFFFF9F88)   /* r5 source  */

/* 0x11218 -- output_per_rotor_ignition_dwell (verified leaf, see
 * c/output_per_rotor_ignition_dwell_0x11218.c).
 *   r4 = channel/rotor index (u8, sign-extended by mov.b then extu.b),
 *   reads f32 dwell @0xFFFFBC84 (rotor A) / 0xFFFFBC88 (rotor B),
 *   returns r0 = (uint32)(int32)(dwell / 0.25f). */
extern uint32_t output_per_rotor_ignition_dwell_0x11218(uint32_t channel);

/* 0x1120A -- returnDwellTime_fp (verified leaf, see
 * c/returnDwellTime_fp_0x1120A.c).
 *   returns (uint32)u16@0xFFFFA0D4 * 16 (dwell time, fixed 4-bit).
 *   Takes no arguments. */
extern uint32_t returnDwellTime_fp_0x1120A(void);

/* 0x2158 -- fixed-point 32x32 scale helper (not yet lifted as a source).
 *   r4 = sum (u32), r5 = scale (u32).
 *   Semantics (pinned against the ROM emulator, 100k random inputs):
 *     sum == 0          -> r0 = 0
 *     scale == 0        -> r0 = 0x7FFFFFFF
 *     else              -> r0 = clamp((int64)(int32)sum * 65536 / (int64)(int32)scale
 *                                     truncated toward zero, 0x7FFFFFFF)
 *   i.e. it scales the accumulated dwell count to fixed-point (<<16) then
 *   normalizes by the caller's scale word, saturating to INT32_MAX. */
extern uint32_t fixed_scale_0x2158(uint32_t sum, uint32_t scale);

uint32_t coil_output_dispatcher_0x110A8(uint32_t base, uint32_t limit)
{
    /* Walk the two descriptors at base+0xC and base+0x1C (stride 0x10),
       r14 starts at base+0xC and the loop runs while r14 < base+0x2C. */
    for (uint32_t k = 0; k < 2; k++) {
        volatile uint8_t *d =
            (volatile uint8_t *)(base + 0xC + 0x10u * k);
        uint32_t ch12 = *(volatile uint32_t *)(d + 0xC);  /* channel time u32 */

        /* cmp/gt r2,r9 ; bf/s ret-0 -> require (s32)limit > (s32)ch12 */
        if (!((int32_t)limit > (int32_t)ch12))
            return 0;

        uint32_t ch0     = (uint32_t)*d;                 /* mov.b @r14,r4 */
        uint32_t dwell   = output_per_rotor_ignition_dwell_0x11218(ch0);
        uint32_t dwell16 = returnDwellTime_fp_0x1120A();
        uint32_t sum     = dwell16 + dwell;              /* add r11,r4 */
        uint32_t scale   = IGN_DWELL_SCALE;              /* mov.l @r2,r5 */
        uint32_t f       = fixed_scale_0x2158(sum, scale); /* jsr @r3 */
        uint32_t r4      = (f * 180u) + ch12;            /* mul.l; sts macl; add */

        /* cmp/ge r4,r9 ; bt/s next-slot -> require (int32)limit >= (int32)r4 */
        if (!((int32_t)limit >= (int32_t)r4))
            return 0;
    }
    return 1;
}