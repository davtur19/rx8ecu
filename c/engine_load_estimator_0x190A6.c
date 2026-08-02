/* engine_load_estimator_0x190A6.c
 *
 * ROM: 60E1D400  |  Address: 0x190A6  |  Size: 0x5C bytes (code 0x190A6..0x19102);
 *       literal pool @0x19102..0x1913C; next function air_fuel_ratio_feedback_calc @0x1913C.
 *       VERIFIED vs ROM emulator (0 mismatches, c/tests/test_engine_load_estimator_0x190A6.py).
 *
 * Engine-load estimate refresh gate.  Old IDA name "engine_load_estimator" (also
 * the equinox-free [ida-ai] label in src/60E1D400_annotated.s).  The observable
 * effect is a 16-bit counter u16@0xFFFFA9BC that either gets refreshed from a
 * 3-D load map (u16 cells, no scale/offset) or counts down by one.
 *
 * Semantics (execution order):
 *   1. A9D0 (u16@0xFFFFA9D0) = old A9BC value           (always, snapshot copy)
 *   2. If A9BC != 0 OR A9BE != 0 OR (A9B0 >= 0 AND A9B4 >= 0):
 *          countdown:  if A9BC != 0: A9BC -= 1          (no refresh)
 *   3. Else (A9BC == 0, A9BE == 0, and A9B0 < 0 OR A9B4 < 0):
 *          A9BC = ThreeDLookup_FP_16bit(desc 0x69F4C, x = RPM, y = load)
 *   The A9B0/A9B4 float test is `fcmp/gt 0.0,x` — i.e. "x < 0.0" — so NaN
 *   inputs fall through to the countdown path (NaN < 0 is false).  The 3-D
 *   lookup is the verified u16-cell FP sibling @0x213C (c/3dLookup.c): 19x11
 *   surface, axis_x = RPM 0..9000 (f32 @0x6F454), axis_y = load 0..1.25
 *   (f32 @0x6F4A0), u16 cells @0x6F4CC; type/scale/offset never read.
 *   The countdown decrement applies for ANY nonzero A9BC (extu.w -> cmp/pl is
 *   "signed > 0" on the zero-extended u16, true for 0x0001..0xFFFF).
 *
 * Inputs (RAM reads):  A9BC (u16, counter), A9BE (u16, refresh gate), A9B0/A9B4
 *   (f32, refresh condition), B5B8 (f32 RPM), C12C (f32 load).
 * Outputs (RAM writes): A9BC (u16, refreshed or decremented), A9D0 (u16 snapshot).
 *
 * Verified: 100000 random inputs x 5 seeds (500000 total) vs the ROM emulator,
 * 0 mismatches.
 */
#include <stdint.h>

#define RAM_A9BC  (*(volatile uint16_t *)0xFFFFA9BC) /* load-estimate counter   */
#define RAM_A9BE  (*(volatile uint16_t *)0xFFFFA9BE) /* refresh gate            */
#define RAM_A9D0  (*(volatile uint16_t *)0xFFFFA9D0) /* snapshot of old A9BC    */
#define RAM_A9B0  (*(volatile float *)0xFFFFA9B0)    /* refresh cond A          */
#define RAM_A9B4  (*(volatile float *)0xFFFFA9B4)    /* refresh cond B          */
#define RAM_RPM   (*(volatile float *)0xFFFFB5B8)    /* engine speed            */
#define RAM_LOAD  (*(volatile float *)0xFFFFC12C)    /* engine load             */

/* Map2D descriptor layout (28 bytes, big-endian SH-2E) — same as c/3dLookup.c */
typedef struct {
    uint16_t     count_x;
    uint16_t     count_y;
    const float *axis_x;
    const float *axis_y;
    const void  *values;
    uint8_t      type;
    uint8_t      _pad[3];
    float        scale;
    float        offset;
} Map2D;

#define DESC_LOAD  ((const Map2D *)0x69F4C)  /* load-estimate surface */

/* ---- verified leaf ---- */
extern uint16_t ThreeDLookup_FP_16bit(const Map2D *m, float x, float y); /* 0x213C */

void engine_load_estimator_0x190A6(void)
{
    uint16_t a9bc = RAM_A9BC;

    /* 0x190B0 mov.w r3,@r4: snapshot the pre-call counter value */
    RAM_A9D0 = a9bc;

    /* 0x190B4 tst A9D0 + 0x190BE tst A9BE: refresh only when both counters
     * are 0 AND at least one of A9B0/A9B4 is negative (0x190CC/0x190D6
     * fcmp/gt 0.0,x == x < 0.0). */
    if (a9bc == 0 && RAM_A9BE == 0
        && (RAM_A9B0 < 0.0f || RAM_A9B4 < 0.0f)) {
        /* 0x190E4 jsr 0x213C (r4=desc, fr4=RPM, fr5=load) -> 0x190EA write A9BC */
        RAM_A9BC = ThreeDLookup_FP_16bit(DESC_LOAD, RAM_RPM, RAM_LOAD);
        return;
    }

    /* 0x190EC..0x190FA countdown: extu.w -> cmp/pl is true for any nonzero
     * zero-extended u16 (0x0001..0xFFFF), so A9BC -= 1 whenever it was != 0. */
    if (a9bc != 0)
        RAM_A9BC = (uint16_t)(a9bc - 1);
}
