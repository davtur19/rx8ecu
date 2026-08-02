/* output_per_rotor_ignition_dwell_0x11218.c
 *
 * ROM: 60E1D400  |  Address: 0x11218  |  Size: 0x66 bytes (0x11218..0x1127E)
 *       reachable code 0x11218..0x11234 + 0x11260..0x1127C; literals @0x112D4
 *       (ptr 0xFFFFBC84), @0x112D8 (ptr 0xFFFFBC88), @0x112DC (f32 0.25);
 *       next function @0x1127E.  NOTE: bytes 0x11236..0x1125E are dead code /
 *       data (jump-table strays + 0xFFFF padding; flagged "[padding]" in the
 *       annotated listing) — never reached by the flow above, which always
 *       branches to 0x11260/0x11266/0x1126C.
 *       VERIFIED vs ROM emulator (0 mismatches,
 *       c/tests/test_output_per_rotor_ignition_dwell_0x11218.py).
 *
 * Per-rotor ignition dwell -> integer timer count.  Old IDA name:
 * "apply_rotor_correction_factor" (ghidra-hand-xmap name:
 * "outputPerRotorIgnitionDwell").  The name "output" is generous for this
 * LEAF: it performs NO write itself.  It converts the per-rotor dwell time
 * float to an integer timer count and returns it; the caller @0x1127E (the
 * unlabeled "calculatePerRotorIgnitionDwell" loop, per docs/functions/
 * calculatePerRotorIgnitionDwell.md) then stores the count into the 4-slot
 * LUT RAM32[0xFFFFA0C4 + rotor*4] (same table ignitionDwellOutputInit @0x8F62
 * initialises).
 *
 * Semantics (execution order):
 *   1. r0 = r4 & 0xFF  (extu.b — the rotor index is masked to 8 bits first).
 *   2. rotor A (b == 0 || b == 1)  -> v = f32@0xFFFFBC84 (rotor-A dwell)
 *      rotor B (b == 2 || b == 3)  -> v = f32@0xFFFFBC88 (rotor-B dwell)
 *      any other                   -> v = 0.0f
 *      (4 ignition channels = 2 rotors x leading/trailing; A channels 0/1,
 *       B channels 2/3.)
 *   3. q = v / 0.25f               (fdiv fr3,fr4; 0.25 is the count-to-time
 *                                   scale -> count = 4 * dwell)
 *   4. return (uint32_t)(int32_t)q (ftrc = truncate toward zero)
 *
 * Inputs:  r4 = rotor/channel index (0..3 in practice); RAM f32@0xFFFFBC84 /
 *   0xFFFFBC88 (dwell times, written by a not-yet-lifted producer).
 * Outputs: r0 = integer dwell timer count.  No RAM/HW writes in this leaf.
 *
 * No callee calls in the reachable path — pure leaf, no emulator-in-the-model
 * needed.
 *
 * Verified: 100000 random inputs x 5 seeds (500000 total) vs the ROM emulator,
 * 0 mismatches.
 */
#include <stdint.h>

#define RAM_BC84 (*(volatile float *)0xFFFFBC84) /* rotor-A dwell time (f32) */
#define RAM_BC88 (*(volatile float *)0xFFFFBC88) /* rotor-B dwell time (f32) */

uint32_t output_per_rotor_ignition_dwell_0x11218(uint32_t rotor)
{
    uint8_t b = rotor & 0xFF;          /* 0x11218 extu.b r4,r0 */
    float   v;

    if (b == 0 || b == 1)              /* 0x1121A/0x11220 -> 0x11260 */
        v = RAM_BC84;
    else if (b == 2 || b == 3)         /* 0x11226/0x1122C -> 0x11266 */
        v = RAM_BC88;
    else                               /* 0x11232 -> 0x1126C */
        v = 0.0f;

    return (uint32_t)(int32_t)(v / 0.25f);  /* 0x11272 fdiv, 0x11276 ftrc */
}
