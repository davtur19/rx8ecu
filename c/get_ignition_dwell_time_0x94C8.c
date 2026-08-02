/* get_ignition_dwell_time_0x94C8.c
 *
 * ROM: 60E1D400  |  Address: 0x94C8  |  Size: 0x30 bytes (code 0x94C8..0x94F6;
 *       literal pool 0x94F8..0x9526, shared with sensor_filter_apply @0x9478;
 *       next function fuel_calc_entry @0x9528).
 *       VERIFIED vs ROM emulator (0 mismatches, c/tests/test_get_ignition_dwell_time_0x94C8.py).
 *
 * Ignition dwell-time lookup.  Reads engine RPM and battery voltage, looks the
 * pair up in the ROM calibration surface "dwell time" (desc @0x6C1C0) via the
 * u16-cell FP-input primitive ThreeDLookup_FP_16bit @0x213C (c/3dLookup.c), adds
 * a u16 offset from RAM and saturates the result at 0xFFFF.
 *
 * Descriptor @0x6C1C0 (28B, layout in c/3dLookup.c's Map2D): count 9x9,
 *   axis_x @0x7CAD8 = RPM  1000..9000 step 1000,
 *   axis_y @0x7CAFC = batt 6.5..16.5 (6.5, 7.75, 9.0, ..., 16.5),
 *   values  @0x7CB20 = u16 dwell cells 395..1895.
 * ThreeDLookup_FP_16bit reads only count_x/count_y/axis_x/axis_y/values from the
 * descriptor (type/scale/offset ignored), truncates the bilinear interpolant to
 * u16.  The 0x213C call is deliberately NOT inlined (kept as an external call,
 * matching the ROM's jsr) — the harness model executes it in a second emulator
 * instance so float rounding matches the ROM exactly.
 *
 * Semantics (execution order):
 *   1. x = RPM (f32@0xFFFF9F80), y = battery voltage (f32@0xFFFF9F68, written
 *      by readECMVoltage @0x735C).
 *   2. r0 = ThreeDLookup_FP_16bit(0x6C1C0, x, y)          (u16 result in r0)
 *   3. r4 = u16(r0) + u16@0xFFFFA0D6                       (32-bit sum)
 *   4. r4 > 0xFFFF  -> u16@0xFFFFA0D4 = 0xFFFF  (saturate)
 *      else          -> u16@0xFFFFA0D4 = u16(r4)
 *
 * Inputs (RAM reads):  9F80 (RPM f32), 9F68 (battV f32), A0D6 (u16 offset).
 * Outputs (RAM writes): A0D4 (u16 dwell time, saturated).
 * ROM: descriptor 0x6C1C0 + axes/cells; call to 0x213C.
 *
 * Callers: 0x8F62 (tail call) and trampoline 0x9148.
 *
 * Verified: 100000 random inputs x 5 seeds (500000 total) vs the ROM emulator,
 * 0 mismatches.
 */
#include <stdint.h>

#define RAM_RPM    (*(volatile float *)0xFFFF9F80)  /* engine speed */
#define RAM_BATTV  (*(volatile float *)0xFFFF9F68)  /* battery voltage (readECMVoltage @0x735C) */
#define RAM_A0D6   (*(volatile uint16_t *)0xFFFFA0D6)  /* dwell offset (u16) */
#define RAM_A0D4   (*(volatile uint16_t *)0xFFFFA0D4)  /* dwell time result (u16, saturated) */

#define DESC_DWELL ((const Map2D *)0x6C1C0)  /* 9x9 u16 dwell-time surface */

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

/* ---- verified leaf ---- */
extern uint16_t ThreeDLookup_FP_16bit(const Map2D *m, float x, float y); /* 0x213C */

void get_ignition_dwell_time_0x94C8(void)
{
    uint16_t cell  = ThreeDLookup_FP_16bit(DESC_DWELL, RAM_RPM, RAM_BATTV);
    uint32_t sum   = (uint32_t)cell + (uint32_t)RAM_A0D6;
    RAM_A0D4       = (sum > 0xFFFFu) ? 0xFFFFu : (uint16_t)sum;
}
