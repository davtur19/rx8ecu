/* calculateKnockTimingDerateConditionEvents_0x178E8.c
 *
 * ROM: 60E0FC00.bin | Address: 0x178E8 | Range 0x0178E8..0x01793C (CSV)
 *
 * ENTRY VERIFICATION: 0x178E8 IS the real entry.  Opens with the standard
 * prologue (mov.l r14,@-r15 ; sts.l pr,@-r15) and runs to `rts` @0x17938
 * (delay mov.l @r15+,r14 @0x1793A).  The preceding function FUN_00017584
 * (0x17584) ends rts, so no fall-through.  Two 32-bit ROM references:
 *   - slot @0x14420 of the engineControlCalculateTiming dispatcher (0x141FC)
 *     dispatch table (primary dispatch slot, immediately before the getSR
 *     slot @0x14424)
 *   - slot @0x14648 of the second-stage engine timing dispatcher (0x14620)
 *     dispatch table (0x1463C..)
 * The CSV range end 0x1793C is the start of FUN_0001793c (next row) — code
 * runs to rts @0x1793A, so the range is CORRECT — no correction needed.
 *
 * SEMANTICS: condition-event counter for the knock-timing derate path.  It
 * latches a "knock derate active" cell and, on a fresh active edge, bumps the
 * event counter and packs it into a complementary 16-bit word:
 *
 *   active = isNotZero_0x2440(f32@A72C, 0.0f, 1e-5f)   // |A72C| > 1e-5 -> 1
 *   if (byte@A948 == 0 && active != 0) {               // fresh active edge
 *       byte@A927 = addSaturate8Bit_0x2478(byte@A927, 1);      // event count
 *       v = read_value_complement_check_0x3E0DC(0xFFFF8076, 0); // fault-style
 *           // returns byte@8076 if byte@8076 == ~byte@8077, else the 0 arg
 *       v = addSaturate8Bit_0x2478(v, 1);
 *       word@0xFFFF8076 = pack_complement_0x3E1F8(v);   // (v<<8)|(~v&0xFF)
 *   }
 *   byte@A948 = active;                                 // latch (always)
 *
 * Sub-calls (real ROM functions, executed by this lift's test):
 *   0x2440 isNotZero_wDivideByZeroProtect(value,center,tol): 1 if
 *        |value-center| > tol, NaN -> 0 (leaf, verified in c/math_primitives)
 *   0x2478 addSaturate8Bit(a,b): min(a+b,0xFF) — the task-expected helper
 *   0x3E0DC read_value_complement_check(addr,fallback): returns byte@addr if
 *        byte@addr == ~byte@(addr+1) (complementary storage plausibility),
 *        else fallback; save/restores SR around the check
 *   0x3E1F8 pack_complement(addr,v): writes word@addr = (v<<8) | (~v&0xFF),
 *        returns r0 = 0
 *
 * The complementary 0xFFFF8076/0x8077 pair is the classic dense event counter
 * storage used across this ROM (pair of bytes, hi = count, lo = ~count).
 *
 * Verified byte-exact against tools/sh2emu.py + the real 60E0FC00.bin in
 * c/tests/test_calculateKnockTimingDerateConditionEvents_0x178E8.py — 0
 * mismatches over 5 seeds x 100000 (full post-call RAM overlay, task-stack
 * window skipped).
 */
#include <stdint.h>

/* ---- RAM cells (mov.l literals, 0xFFFFxxxx) ---- */
#define RAM_A72C (*(volatile float  *)0xFFFFA72C) /* knock derate source value */
#define RAM_A948 (*(volatile uint8_t *)0xFFFFA948) /* active latch cell (r/w) */
#define RAM_A927 (*(volatile uint8_t *)0xFFFFA927) /* condition event counter */
#define RAM_8076 (*(volatile uint16_t *)0xFFFF8076) /* packed complementary word */

/* External sub-helpers (in ROM, verified by this lift's test) */
extern uint32_t complement_shift_u32(float value, float center, float tolerance);
/* @0x2440: 1 if |value-center| > tolerance, NaN -> 0 */
extern uint8_t addSaturate8Bit_0x2478(uint8_t a, uint8_t b);
extern uint8_t read_value_complement_check_0x3E0DC(uint16_t addr, uint8_t fallback);
extern uint8_t pack_complement_0x3E1F8(uint16_t addr, uint8_t value);

void calculateKnockTimingDerateConditionEvents_0x178E8(void)
{
    uint8_t active = (uint8_t)(complement_shift_u32(RAM_A72C, 0.0f, 1e-5f) & 0xFF);

    if (RAM_A948 == 0 && active != 0) {
        uint8_t v = addSaturate8Bit_0x2478(RAM_A927, 1);  /* event count++ */
        RAM_A927 = v;
        v = addSaturate8Bit_0x2478(
                read_value_complement_check_0x3E0DC(0xFFFF8076, 0), 1);
        RAM_8076 = (uint16_t)((v << 8) | (uint16_t)(~v & 0xFF));
    }
    RAM_A948 = active;   /* fresh-edge latch always published */
}