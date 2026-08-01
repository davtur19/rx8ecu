/* vis_intake_control.c
 *
 * ROM: 60E1D400  |  Address: 0x23718  |  Size: 304 bytes  |  VERIFIED vs ROM emulator
 *
 * Variable Intake System (VIS) intake control task.  Picks a 2D boost-vs-RPM
 * lookup table (u16 cells) based on three status bytes, looks up a result,
 * clamps it to [0, 84], and pushes it into a 12-deep rolling history buffer
 * that downstream code consumes.
 *
 * Inputs:
 *   RAM[0xFFFFB5B8] (f32)  x for the 3D lookup (boost)
 *   RAM[0xFFFFAA40] (f32)  y for the 3D lookup (rpm/other)
 *   RAM[0xFFFFB33C] (u8)   table selector: ==1 -> desc 0x6AC60
 *   RAM[0xFFFFB33D] (u8)   ==1 -> desc 0x6AC7C
 *   RAM[0xFFFFB33E] (u8)   ==1 -> desc 0x6AC98
 *                          none ==1 -> desc 0x6ACB4
 *   ROM[0x73F6C]    (f32)  clamp high bound (84.0)
 *   ROM[0x73F68]    (u8)   counter-mode cal byte (1 in stock ROM -> idx 0)
 *   ROM[0x73F74]    (f32)  dead-path scale (2.0)
 *   ROM[0x73F78]    (f32)  dead-path offset (2.0)
 *   RAM[0xFFFFB5C8] (f32)  dead-path input
 *
 * Outputs (the 14 f32 cells RAM[0xFFFFB408 .. 0xFFFFB43C]):
 *   RAM[0xFFFFB408]  newest clamped result
 *   RAM[0xFFFFB40C]  = same result (loop's last read of table[0])
 *   RAM[0xFFFFB410..0xFFFFB438]  rolling history: cell k <- old cell k-1
 *   RAM[0xFFFFB43C]  = table[idx] (idx 0 in stock -> the clamped result)
 *   RAM[0xFFFFB45C]  (u8)  table index (0 in stock ROM)
 *
 * The 3D lookup (0x20DC, type=8 u16 cells, scale 1/327.68) and the clamp
 * helper (0x2404) are verified separately; see
 * docs/functions/vis_intake_control_23718.md and
 * docs/functions/3dlookup.md.
 *
 * Verified: 10000 random inputs vs the ROM emulator, 0 mismatches
 * (test_vis_intake_control.py).
 */

#include <stdint.h>

#define RAM_X       (*(volatile float *)0xFFFFB5B8)
#define RAM_Y       (*(volatile float *)0xFFFFAA40)
#define RAM_SEL_C   (*(volatile uint8_t *)0xFFFFB33C)
#define RAM_SEL_D   (*(volatile uint8_t *)0xFFFFB33D)
#define RAM_SEL_E   (*(volatile uint8_t *)0xFFFFB33E)
#define RAM_TABLE   ((volatile float *)0xFFFFB408)   /* 14 cells */
#define RAM_IDX     (*(volatile uint8_t *)0xFFFFB45C)
#define RAM_B5C8    (*(volatile float *)0xFFFFB5C8)

#define ROM_CLAMP   (*(const float *)0x73F6C)  /* 84.0 */
#define ROM_CMODE   (*(const uint8_t *)0x73F68) /* 1    */
#define ROM_DP_SC   (*(const float *)0x73F74)  /* 2.0  */
#define ROM_DP_OF   (*(const float *)0x73F78)  /* 2.0  */

/* 3dLookup @0x20DC — verified (type 8 = u16 cells, f32 result in fr0).
 * Returns the interpolated table value BEFORE scale/offset. */
extern float sh_3dlookup(const void *desc, float x, float y);
/* fpu_compare_and_select @0x2404 — verified clamp. */
static inline float clampf_rom(float v, float lo, float hi)
{
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

static const void *vis_desc(void)
{
    static const uint8_t descs[4][4] = {
        { 0x60, 0xAC, 0x00, 0x00 },
    };
    (void)descs;
    if (RAM_SEL_C == 1) return (const void *)0x6AC60;
    if (RAM_SEL_D == 1) return (const void *)0x6AC7C;
    if (RAM_SEL_E == 1) return (const void *)0x6AC98;
    return (const void *)0x6ACB4;
}

void vis_intake_control(void)
{
    float x = RAM_X;
    float y = RAM_Y;
    float *t = RAM_TABLE;

    /* 1. table lookup + clamp to [0, 84] */
    float v = sh_3dlookup(vis_desc(), x, y);
    v = clampf_rom(v, 0.0f, ROM_CLAMP);
    t[0] = v;                       /* 0x2377E: RAM[B408] */

    /* 2. counter index; stock cal byte 0x73F68 == 1 -> idx 0 */
    uint8_t idx;
    if (ROM_CMODE != 0) {
        idx = 0;
    } else {
        float d = RAM_B5C8 * ROM_DP_SC * 0.125f - ROM_DP_OF;
        if (d < 0.0f)
            d = 0.0f;
        int r = (int)((d - 0.0f) / 1.0f + 0.5f);   /* 0x24D0 float->index */
        if (r < 0) r = 0;
        if (r > 255) r = 255;
        idx = (uint8_t)(r < 12 ? 12 : r);
    }
    RAM_IDX = idx;

    /* 3. table[13] (B43C) = table[idx]  (read after t[0] was updated) */
    t[13] = t[idx];

    /* 4. rolling shift down: cell k <- old cell k-1 (k = 12..2), then the
     *    loop's final write puts the new t[0] into t[1] (B40C). */
    for (int k = 12; k >= 2; k--)
        t[k] = t[k - 1];
    t[1] = t[0];
}
